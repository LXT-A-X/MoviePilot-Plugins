<script setup>
import { computed, inject, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import api from '../api/client.js'
import ConfirmDlg from '../components/ConfirmDlg.vue'
import TaskGuardDlg from '../components/TaskGuardDlg.vue'
import { useConfirm } from '../components/useConfirm.js'
import { useTaskGuard } from '../components/useTaskGuard.js'

const props = defineProps({ api: { type: Object, default: () => ({}) } })
const emit = defineEmits(['notify', 'view-task'])
const toast = inject('moviepilot:toast', null)
const { cState, askConfirm, cOk, cCancel } = useConfirm()
// v4.6.70：统一任务守卫（编辑 / 重翻 / 全部翻译 / 写回 / 删除 / 导入 / 清库 等修改型操作共用）
const guard = useTaskGuard()

const items = ref([])
const search = ref('')
const filterType = ref('')   // 左侧类型筛选 全部/剧集(Series+Episode)/电影(Movie)
const expandedLibs = ref(new Set())
const selected = ref(null)
const people = ref([])
const itemMeta = ref(null)
const loadingList = ref(true)
const loadingPeople = ref(false)
const posterData = ref(null)
const logoData = ref(null)

function notify(msg, type = 'error') {
  const t = toast; if (t && typeof t[type] === 'function') t[type](msg)
}

// 按分库分组（仿字体库目录树的一级分组）
const groups = computed(() => {
  const map = {}
  const kw = (search.value || '').trim().toLowerCase()
  const ft = filterType.value   // '' 全部 / Series 剧集 / Movie 电影
  for (const it of items.value) {
    if (kw && !String(it.title).toLowerCase().includes(kw)) continue
    const t = String(it.item_type || '').toLowerCase()
    if (ft === 'Series' && !['series', 'episode', '剧', '电视剧'].includes(t)) continue
    if (ft === 'Movie' && !['movie', '电影', '影片'].includes(t)) continue
    const lib = it.library_name || '未分类'
    ;(map[lib] = map[lib] || []).push(it)
  }
  for (const k of Object.keys(map)) {
    map[k].sort((a, b) => {
      const da = a.deleted_at ? 2 : (a.deleted_eps > 0 ? 1 : 0)
      const db = b.deleted_at ? 2 : (b.deleted_eps > 0 ? 1 : 0)
      if (da !== db) return db - da
      return (b.updated_at || '').localeCompare(a.updated_at || '')
    })
  }
  return map
})

// 扁平可见节点：分库节点永远显示，条目受展开状态控制
const visibleNodes = computed(() => {
  const out = []
  const entries = Object.entries(groups.value)
    .sort((a, b) => { const o = ['未分类']; const ia = o.includes(a[0]) ? 1 : 0, ib = o.includes(b[0]) ? 1 : 0; return ia - ib || b[1].length - a[1].length })
  for (const [lib, list] of entries) {
    out.push({ type: 'group', lib, depth: 0, count: list.length })
    if (expandedLibs.value.has(lib) || (search.value || '').trim()) {
      for (const it of list) out.push({ type: 'item', item: it, depth: 1 })
    }
  }
  return out
})

// ── 库列表分页（UI-PAGE）：与分集同款滚动自加载 ──
const ITEM_PAGE_SIZE = 100
const itemHasMore = ref(false)
const itemSentinel = ref(null)
let itemsSeq = 0
let itemLoadingMore = false
let _itemObserver = null

// 兼容两种响应体：分页时 data={items,total,has_more}；未分页/旧后端 data=数组
function _normItems(resp) {
  if (Array.isArray(resp)) return { list: resp, total: resp.length, hasMore: false }
  const list = Array.isArray(resp?.items) ? resp.items : []
  return { list, total: Number(resp?.total ?? list.length) || list.length, hasMore: !!resp?.has_more }
}

let _itemsInflight = false
// v4.6.104（LIB-006）：左栏每一行真正渲染出来的字段 —— 只比这些；签名一致就整段跳过赋值。
const _ITEM_SIG_FIELDS = ['title', 'item_type', 'library_name', 'deleted_at', 'deleted_eps', 'person_count', 'episode_count']
function _itemSig(it) {
  let s = ''
  for (const f of _ITEM_SIG_FIELDS) s += String((it && it[f]) != null ? it[f] : '') + '\u0001'
  return s
}
// 两轮数据完全等价？—— 等价则跳过赋值：不触发 computed、不让 v-list 整列重建（滚动跳动/闪烁的来源）
function _itemsSame(a, b) {
  if (a === b) return true
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (itemKey(a[i]) !== itemKey(b[i])) return false
    if (_itemSig(a[i]) !== _itemSig(b[i])) return false
  }
  return true
}
// 原地合并（v4.6.104 · LIB-007 / LIB-010）：同 key 的条目**保留对象引用**只改字段、顺序不变；
// 新 key 追加。未变化的行引用不变 → Vue 不重建 DOM，滚动位置与展开状态都稳住。
// removeMissing 只在「本次请求已覆盖服务端全部条目」时为 true（见 loadItems）——
// 若本次只取回一个不完整窗口（还在分页 / limit < total），绝不能把 cur 里 next 没出现的
// 条目删掉：列表按 translated_at 倒序，翻译一发生顺序就变，上一窗口的条目会落到新窗口外，
// 一删就是「分库整组消失、下次再补回来」的无限抖动（用户实测 v4.6.104 前一版）。
function _mergeItems(cur, next, removeMissing = true) {
  const byKey = new Map()
  for (const it of next) { const k = itemKey(it); if (k) byKey.set(k, it) }
  const out = []
  const used = new Set()
  for (const it of cur) {
    const k = itemKey(it)
    const n = k ? byKey.get(k) : null
    if (!n) {
      if (removeMissing) continue   // 已确认拉全 → 服务端真的没了，移除
      out.push(it)                  // 窗口不完整 → 保留已加载的，一个都不丢
      continue
    }
    used.add(k)
    for (const f of Object.keys(n)) { if (it[f] !== n[f]) it[f] = n[f] }
    out.push(it)
  }
  for (const it of next) {
    const k = itemKey(it)
    if (!k || used.has(k)) continue
    used.add(k)
    out.push(it)
  }
  return out
}
async function loadItems(silent = false) {
  // v4.6.103（LIB-004）：单飞守卫 —— 与 loadTxPreview 的 _txPreviewInflight 同款。
  // 症状（用户实测 v4.6.102，库内 360 条目）：左侧条目早已渲染出来，进度条却一直转、停不下来。
  // 成因：轮询每 8s 调 loadItems(true)，若 /db/items 响应慢于 8s，老请求会被新请求顶掉
  // （seq 不匹配 → early return，finally 不清 loadingList），而新请求又被下一轮顶掉……
  // 于是「永远没有一个请求是"最新一代"」，loadingList 永远为 true。在飞期间直接丢弃本轮调用，
  // 保证在飞的唯一请求一定是最新一代 → 其 finally 必然清掉 loadingList。
  if (_itemsInflight) {
    if (!silent) loadingList.value = true   // 手动刷新时至少给出转圈反馈（由在飞请求收尾清除）
    return
  }
  _itemsInflight = true
  // 请求代次（LIB-003）：连点刷新/轮询叠加时，只有最新一轮响应能写状态
  const seq = ++itemsSeq
  if (!silent) loadingList.value = true
  try {
    // v4.6.104（LIB-006/007）：静默轮询不再把列表塌回第 1 页、也不再整段换新数组。
    // 症状（用户实测 v4.6.103，库内 360 条目）：每次刷新页面都「拉一下、加载一下」。
    // 成因：本函数固定 limit=100/offset=0 且无条件 items.value = list —— 用户滚动加载出来的
    // 后续条目被整段丢弃、列表塌回 100 条（视觉跳变），底部哨兵又把它们补回来，
    // 「刷新 → 塌陷 → 重新加载」每 8s 循环一次。现按当前窗口大小请求，并按 key 原地合并。
    const limit = Math.max(ITEM_PAGE_SIZE, items.value.length)
    const resp = await api.get(props.api, '/db/items', { limit, offset: 0 })
    if (seq !== itemsSeq) return
    const { list, total, hasMore } = _normItems(resp)
    // v4.6.104（LIB-010）：只有「本次请求覆盖了服务端全部条目」时，才允许移除服务端已消失的条目；
    // 否则（还有下一页 / limit < total）只做「改字段 + 追加」，绝不删 —— 防止分库整组消失再补回。
    const _complete = list.length >= total
    if (silent && _itemsSame(items.value, list)) {   // 无变化：不赋值、不触发渲染
      itemHasMore.value = hasMore
      return
    }
    items.value = _mergeItems(items.value, list, _complete)
    itemHasMore.value = hasMore
  } catch (e) { if (seq === itemsSeq && !silent) notify(e.message, 'error') }
  finally {
    if (seq === itemsSeq) loadingList.value = false
    _itemsInflight = false
  }
}

// 滚动到底部自动追加下一页：按「来源 + item_id」复合键去重，避免分页边界重复
async function loadMoreItems() {
  if (itemLoadingMore || !itemHasMore.value) return
  itemLoadingMore = true
  const seq = itemsSeq
  try {
    const resp = await api.get(props.api, '/db/items', { limit: ITEM_PAGE_SIZE, offset: items.value.length })
    if (seq !== itemsSeq) return
    const { list, hasMore } = _normItems(resp)
    const seen = new Set(items.value.map((it) => itemKey(it)))
    for (const it of list) {
      const k = itemKey(it)
      if (k && seen.has(k)) continue
      seen.add(k)
      items.value.push(it)
    }
    itemHasMore.value = hasMore
  } catch (e) { /* 静默：滚动加载失败不打断浏览，点刷新可重试 */ }
  finally {
    itemLoadingMore = false
    // 若哨兵仍在视口内（首屏未填满），继续补下一页，直到填满或加载完
    nextTick(() => {
      const el = itemSentinel.value
      if (itemHasMore.value && el && el.getBoundingClientRect().top <= (window.innerHeight + 200)) loadMoreItems()
    })
  }
}
function setupItemObserver() {
  teardownItemObserver()
  if (!itemSentinel.value) return
  _itemObserver = new IntersectionObserver((entries) => {
    if (entries.some(e => e.isIntersecting)) loadMoreItems()
  }, { rootMargin: '200px' })
  _itemObserver.observe(itemSentinel.value)
}
function teardownItemObserver() {
  if (_itemObserver) { _itemObserver.disconnect(); _itemObserver = null }
}
watch(itemSentinel, (el) => { if (el) setupItemObserver(); else teardownItemObserver() })

function toggleGroup(lib) {
  const set = new Set(expandedLibs.value)
  if (set.has(lib)) set.delete(lib); else set.add(lib)
  expandedLibs.value = set
}

function libIcon(name) {
  const n = name || ''
  if (n.includes('番') || n.includes('动漫') || n.includes('动画')) return 'mdi-television-classic'
  if (n.includes('剧') || n.includes('TV')) return 'mdi-movie-open-outline'
  if (n.includes('电影') || n.includes('影片')) return 'mdi-filmstrip'
  return 'mdi-folder-multiple-outline'
}

// v4.6.83：左栏条目图标按类型区分 —— 电影 / 剧集一眼可分（纯字体图标，零请求）。
function itemIcon(it) {
  const t = String(it?.item_type || '').trim().toLowerCase()
  if (['series', 'tvshow', 'tv', 'season', '剧', '电视剧', '番', '动漫', '动画'].includes(t)) {
    return 'mdi-television-classic'
  }
  return 'mdi-movie-outline'
}

async function selectItem(item) {
  selected.value = item
  loadingPeople.value = true
  people.value = []
  itemMeta.value = null
  posterData.value = null
  logoData.value = null
  libMainCast.value = []
  libEpisodes.value = []
  epLoadedCount.value = 0
  editDlgOpen.value = false
  loadPoster(item)
  loadLogo(item)
  try {
    const data = await api.get(props.api, '/db/people', { item_id: item.item_id, server_id: item.server_id || '' })
    if (selected.value !== item) return   // 已切到别的条目 → 丢弃旧响应（LIB-002）
    people.value = data?.people || []
    itemMeta.value = data?.item || item
    libMainCast.value = data?.main_cast || []
    libEpisodes.value = data?.episodes || []
    const _slist = Array.from(new Set(libEpisodes.value.map(e => e.season ?? 0))).sort((a, b) => a - b)
    epCurrentSeason.value = _slist.length ? _slist[0] : null
    epLoadedCount.value = Math.min(EP_PAGE_SIZE,
      libEpisodes.value.filter(e => (e.season ?? 0) === epCurrentSeason.value).length)
  } catch (e) { if (selected.value === item) notify(e.message, 'error') }
  if (selected.value !== item) return
  loadingPeople.value = false
  await nextTick()
  setupEpObserver()
}

const EP_PAGE_SIZE = 50
const libMainCast = ref([])
const libEpisodes = ref([])
const epLoadedCount = ref(0)
const epSentinel = ref(null)
const editDlgOpen = ref(false)
const editDlgForm = ref({})
const editDlgRoleScope = ref('single')
// v4.6.74（报告第十四节）：人名作用域 —— 默认「仅当前这一条」（不再默认全库同名）
const editDlgNameScope = ref('single')
const editDlgSaving = ref(false)
const editDlgOcc = ref({ count: 0, series: [] })
const editDlgSyncEmby = ref(false)
watch(editDlgOpen, (v) => { if (v) editDlgSyncEmby.value = false })
const editDlgNameChanged = computed(() => {
  const f = editDlgForm.value || {}
  return !!(f.name_after && f.name_after !== f.name_before)
})

function isSeriesSelected() {
  return String(itemMeta.value?.item_type || selected.value?.item_type || '').toLowerCase() === 'series'
}
const epVisible = computed(() => epSeasonEps.value.slice(0, epLoadedCount.value))
const epAllLoaded = computed(() => epLoadedCount.value >= epSeasonEps.value.length)

const epSeasonMap = computed(() => {
  const map = new Map()
  for (const ep of libEpisodes.value) {
    const s = ep.season ?? 0
    if (!map.has(s)) map.set(s, [])
    map.get(s).push(ep)
  }
  // v4.6.75（规范 §十一/§二-2）：季内按集号数字排序（接口顺序不保证 E01 在前）
  for (const list of map.values()) list.sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0))
  return map
})
const epSeasons = computed(() =>
  Array.from(epSeasonMap.value.entries())
    .map(([season, list]) => ({ season, count: list.length }))
    // v4.6.75（规范 §二-2）：季序按**数字**排序 —— S1 / S2 / S3 / S10 / S20，
    // 不再出现 S1、S10、S2 这种字符串序（Map 插入序不可靠）。
    .sort((a, b) => a.season - b.season)
)
const epMultiSeason = computed(() => epSeasons.value.length > 1)
const epCurrentSeason = ref(null)
const epSeasonEps = computed(() => epSeasonMap.value.get(epCurrentSeason.value) || [])
const epPanelRef = ref(null)
function selectSeason(s) {
  epCurrentSeason.value = s
  // v4.6.75（规范 §二-3/§十一-9）：重置该季懒加载计数 + 重建观察器（旧 Observer 先销毁），
  // 避免上一季的加载状态污染下一季；并把视图滚回「本季开头（E01）」。
  epLoadedCount.value = Math.min(EP_PAGE_SIZE, (epSeasonMap.value.get(s) || []).length)
  nextTick(() => {
    setupEpObserver()
    try { epPanelRef.value?.scrollIntoView({ block: 'start', behavior: 'smooth' }) } catch (e) { /* 忽略 */ }
  })
}
// 季内面板标题只显示 E01（季号已在标签上，避免 S1E01 重复）；单季平铺仍用全标签
const epLabelShort = (ep) => (ep.episode != null ? `E${String(ep.episode).padStart(2, '0')}` : '—')
const epPanelLabel = (ep) => (epMultiSeason.value ? epLabelShort(ep) : epLabel(ep))
const epTitle = (ep) => String(ep.title || '').trim()

const epIsDeleted = (ep) => (ep.people || []).some(p => String(p.deleted_at || ''))
const epDeletedCountBySeason = computed(() => {
  const map = new Map()
  for (const ep of libEpisodes.value) {
    if (epIsDeleted(ep)) {
      const s = ep.season ?? 0
      map.set(s, (map.get(s) || 0) + 1)
    }
  }
  return map
})
const epDeletedTotal = computed(() =>
  Array.from(epDeletedCountBySeason.value.values()).reduce((a, b) => a + b, 0))

async function refreshDetailSoft() {
  if (!selected.value || loadingPeople.value || editDlgOpen.value) return
  try {
    const data = await api.get(props.api, '/db/people', {
      item_id: selected.value.item_id, server_id: selected.value.server_id || '',
    })
    people.value = data?.people || []
    libMainCast.value = data?.main_cast || []
    libEpisodes.value = data?.episodes || []
    const _cnt = (epSeasonMap.value.get(epCurrentSeason.value) || []).length
    if (epLoadedCount.value > _cnt) epLoadedCount.value = _cnt
  } catch (e) { /* 静默：刷新失败不影响浏览 */ }
}
let _epObserver = null
function setupEpObserver() {
  teardownEpObserver()
  if (!epSentinel.value) return
  _epObserver = new IntersectionObserver((entries) => {
    if (entries.some(e => e.isIntersecting) && !epAllLoaded.value) loadMoreEps()
  }, { rootMargin: '200px' })
  _epObserver.observe(epSentinel.value)
}
function teardownEpObserver() {
  if (_epObserver) { _epObserver.disconnect(); _epObserver = null }
}
function loadMoreEps() {
  if (epAllLoaded.value) return
  epLoadedCount.value = Math.min(epLoadedCount.value + EP_PAGE_SIZE, libEpisodes.value.length)
}
const isVoiceActor = (p) => {
  const t = String(p.type || '').toLowerCase()
  return t.includes('voice') || String(p.role_after || '').includes('配音')
}
// 稳定复合键（LIB-001/LIB-008）：条目 = 来源 + item_id；集 = 物理 nfo_path + 季集
const itemKey = (it) => (it ? `${it.server_id || ''}:${it.item_id || ''}` : '')
const epKey = (ep) => `${ep.nfo_path || ''}@s${ep.season ?? 0}e${ep.episode ?? 0}`
const epLabel = (ep) => {
  const s = ep.season != null ? `S${ep.season}` : ''
  const e = ep.episode != null ? `E${String(ep.episode).padStart(2, '0')}` : ''
  return `${s}${e}`
}
function openEpEdit(p, ep) {
  const _t = String(itemMeta.value?.title || selected.value?.title || '')
  editDlgForm.value = {
    item_id: selected.value?.item_id || '', server_id: selected.value?.server_id || '',
    series_name: _t,
    name_before: p.name_before,
    name_after: p.name_after || p.name_before || '',
    name_after0: p.name_after || p.name_before || '',
    role_before: p.role_before || '',
    role_after: p.role_after || p.role_before || '',
    role_after0: p.role_after || p.role_before || '',
    season_num: ep?.season ?? null, episode_num: ep?.episode ?? null,
    index: p.index,
    role_level: ep ? 'ep' : 'tv',
    loc: ep ? `${_t || '该剧'} · ${epLabel(ep)}` : `${_t || '该剧'} · 剧级名单`,
  }
  editDlgRoleScope.value = ep ? 'single' : 'tv'
  editDlgNameScope.value = 'single'   // v4.6.74：人名默认只改当前这一条
  editDlgOpen.value = true
  loadEditDlgOcc()
}
async function loadEditDlgOcc() {
  const nb = String(editDlgForm.value?.name_before || '').trim()
  editDlgOcc.value = { count: 0, series: [] }
  if (!nb) return
  try {
    const rows = (await api.get(props.api, '/db/person_occurrences', { name_before: nb })) || []
    const series = []
    for (const r of rows) {
      const s = String(r.series_name || r.title || '').trim()
      if (s && !series.includes(s)) series.push(s)
    }
    editDlgOcc.value = { count: rows.length, series }
  } catch (e) { /* 统计失败不影响编辑 */ }
}
function roleScopeHint() {
  const f = editDlgForm.value || {}
  const sc = editDlgRoleScope.value
  if (sc === 'single') return `角色只改：${f.loc || '当前这一条'}`
  if (sc === 'season') return `角色改：${f.series_name || '该剧'} · 第 ${f.season_num ?? '?'} 季全部集`
  if (sc === 'tv') return `角色只改：${f.series_name || '该剧'} · 剧级名单`
  return `角色改：${f.series_name || '该剧'} 全剧（所有季的所有集）`
}
function nameScopeHint() {
  const f = editDlgForm.value || {}
  const sc = editDlgNameScope.value
  if (sc === 'single') return `人名只改：${f.loc || '当前这一条'}（不影响其它作品里的同名人物）`
  if (sc === 'series') return `人名改：${f.series_name || '该作品'} 内所有季/集的同名人物（不影响其它作品）`
  return `人名改：全库所有作品里的同名人物 —— 可能包含不同真人，请确认后再保存`
}
function nameScopeLabel() {
  return { single: '仅当前这一条', series: '该作品内同名', library: '全库同名' }[editDlgNameScope.value] || editDlgNameScope.value
}
async function saveEditDialog() {
  if (editDlgSaving.value) return
  await loadStatus()   // v4.6.70：保存前刷新任务状态 —— 若期间后台起了翻译/写回，统一守卫会拦截
  if (!guard.check('保存人工修改')) return
  const f = editDlgForm.value || {}
  const roleScope = editDlgRoleScope.value
  const _n0 = String(f.name_after0 ?? '').trim()
  const _r0 = String(f.role_after0 ?? '').trim()
  const _na = String(f.name_after ?? '').trim()
  const _ra = String(f.role_after ?? '').trim()
  const _nb = String(f.name_before ?? '').trim()
  // v4.6.53：与「打开弹窗时的现有值」比较（而非与原文比较）——
  // 这样「把译名改回与原文相同 / 留空」也是合法修改（= 清除错译、恢复原文）
  const nameChanged = _na !== _n0
  const roleChanged = _ra !== _r0
  if (!nameChanged && !roleChanged) { notify('没有需要修改的内容', 'warning'); return }
  const nameIsRestore = nameChanged && (_na === '' || _na === _nb)
  if (nameChanged && !nameIsRestore) {
    // v4.6.74（报告第十四节）：人名默认只改当前人物身份；「全库同名」必须主动选择 + 危险确认
    const _sc = editDlgNameScope.value
    const _cnt = editDlgOcc.value?.count || 0
    const _shows = (editDlgOcc.value?.series || []).length
    const _syncTxt = editDlgSyncEmby.value ? '，并同步到 Emby（同一演员的所有作品一起变）' : '；不改 Emby，仅改本插件库'
    if (_sc === 'library') {
      if (!await askConfirm({
        title: '修改人名（全库同名 · 危险）',
        text: `将把「${f.name_before}」改成「${f.name_after}」：会影响全库所有作品里的同名人物 —— 库中同名共 ${_cnt || '?'} 处${_shows ? `（${_shows} 部作品）` : ''}${_syncTxt}。`,
        detail: '这会修改所有同名人物，可能包含不同真人。如果你只想改这一个（或这一部作品），请把上方「范围」改成「仅当前这一条」或「该作品内同名」。',
        okText: '我确认，全库修改',
        color: 'error',
      })) return
    } else if (!await askConfirm({
      title: `修改人名（${nameScopeLabel()}）`,
      text: `将把「${f.name_before}」改成「${f.name_after}」（范围：${nameScopeLabel()}）${_syncTxt}。`,
      detail: '只影响所选范围；其它作品里的同名人物不会被改动。',
      okText: '确认修改',
      color: 'warning',
    })) return
  }
  editDlgSaving.value = true
  try {
    const r = await api.post(props.api, '/db/update_person_scope', {
      item_id: f.item_id, server_id: f.server_id,
      name_before: f.name_before, name_after: f.name_after,
      name_scope: nameChanged ? editDlgNameScope.value : 'single',
      role_before: f.role_before, role_after: f.role_after,
      role_scope: roleChanged ? roleScope : 'single',
      season_num: f.season_num, episode_num: f.episode_num, index: f.index,
      sync_emby: !!editDlgSyncEmby.value,
      name_force: nameChanged, role_force: roleChanged,
    })
    notify(r?.message || '已更新', 'success')
    editDlgOpen.value = false
    if (occKey.value) { const _k = occKey.value; occKey.value = ''; await toggleOcc({ name_before: _k }) }
    if (searchMode.value) searchPeople()
    await refreshDetailSoft()
    loadItems(true)
    emit('action')
  } catch (e) { notify((e && e.message) || '保存失败', 'error') } finally { editDlgSaving.value = false }
}

// v4.6.70（报告第二十~三十四节）：第二排角色跨集复用的「记忆」唯一清除入口 ——
// 删除/恢复/清空翻译记录都不会清记忆（洗版重建仍复用旧译文），只有这里会。
const roleMemBusy = ref(false)
async function clearRoleMemory() {
  const f = editDlgForm.value || {}
  const _iid = String(f.item_id || '').trim()
  const _sn = String(f.series_name || '').trim()
  if (!_iid && !_sn) { notify('无法定位该剧（缺条目 ID / 剧名）', 'warning'); return }
  await loadStatus()
  if (!guard.check('清除该剧角色翻译记忆')) return
  if (!await askConfirm({
    title: '清除该剧角色翻译记忆',
    text: `清除「${_sn || _iid}」的第二排角色翻译记忆？`,
    detail: '清除后该剧各集的角色名需要重新翻译（重新消耗 AI）。注意：删除/恢复/清空翻译记录都不会清记忆，只有这里会。',
    okText: '清除',
    color: 'error',
  })) return
  roleMemBusy.value = true
  try {
    const r = await api.post(props.api, '/db/role_memory/clear',
                             { item_id: _iid, series_name: _sn, server_id: f.server_id || '' })
    notify(r?.message || '已清除该剧角色翻译记忆', 'success')
  } catch (e) { notify((e && e.message) || '清除失败', 'error') } finally { roleMemBusy.value = false }
}

async function loadPoster(item) {
  try {
    const r = await api.get(props.api, '/poster', { item_id: item.item_id, server_id: item.server_id || '', kind: 'Primary' })
    if (selected.value !== item) return   // 旧响应不得覆盖新选中项（LIB-002）
    if (r) posterData.value = r
  } catch (e) { if (selected.value === item) posterData.value = null }
}
async function loadLogo(item) {
  try {
    const r = await api.get(props.api, '/poster', { item_id: item.item_id, server_id: item.server_id || '', kind: 'Logo' })
    if (selected.value !== item) return
    if (r) logoData.value = r
  } catch (e) { if (selected.value === item) logoData.value = null }
}

const personSearch = ref('')
const searchResults = ref([])
const searchingPeople = ref(false)
let personSearchTimer = null
const searchMode = computed(() => (personSearch.value || '').trim().length > 0)
let searchSeq = 0
async function searchPeople() {
  const kw = (personSearch.value || '').trim()
  if (!kw) { searchResults.value = []; return }
  const seq = ++searchSeq
  searchingPeople.value = true
  try {
    const data = await api.get(props.api, '/db/people', { keyword: kw })
    if (seq !== searchSeq) return   // 快速输入时只有最后一次结果生效（LIB-004）
    searchResults.value = data?.people || []
  } catch (e) { if (seq === searchSeq) searchResults.value = [] }
  finally { if (seq === searchSeq) searchingPeople.value = false }
}
function onPersonSearchInput() {
  clearTimeout(personSearchTimer)
  personSearchTimer = setTimeout(searchPeople, 350)
}
function clearPersonSearch() { personSearch.value = ''; searchResults.value = [] }
function openGlobalEdit(row) {
  editDlgForm.value = {
    item_id: '', server_id: '',
    series_name: '',
    name_before: row.name_before,
    name_after: row.name_after || row.name_before || '',
    name_after0: row.name_after || row.name_before || '',
    role_before: '', role_after: '',
    season_num: null, episode_num: null, index: null,
    role_level: 'tv',
    loc: `全库汇总（${row.count || 0} 处）`,
  }
  editDlgRoleScope.value = 'series'
  // v4.6.74：这是「全库同名汇总行」——本身就代表全库，默认即全库同名（弹窗内标红警告）
  editDlgNameScope.value = 'library'
  // 汇总行自带出现次数与剧集列表，直接用（省一次请求）
  editDlgOcc.value = { count: row.count || 0, series: row.series || [] }
  editDlgOpen.value = true
}

const occKey = ref('')          // 当前展开出现清单的原文名
const occRows = ref([])
const occLoading = ref(false)

async function toggleOcc(row) {
  const key = String(row.name_before || '')
  if (occKey.value === key) { occKey.value = ''; occRows.value = []; return }
  occKey.value = key
  occRows.value = []
  occLoading.value = true
  try {
    occRows.value = (await api.get(props.api, '/db/person_occurrences', { name_before: key })) || []
  } catch (e) { notify((e && e.message) || '读取出现清单失败', 'error') } finally { occLoading.value = false }
}
function occLabel(r) {
  const s = String(r.series_name || r.title || '').trim()
  const _lv = String(r.item_type || '') === 'Movie' ? '本片名单' : '本剧名单'
  const se = (r.season_num == null && r.episode_num == null)
    ? _lv
    : `S${r.season_num ?? '?'}E${String(r.episode_num ?? '?').padStart(2, '0')}`
  return `${s || '（条目）'} · ${se}${r.deleted_at ? '（待恢复）' : ''}`
}
function openOccEdit(r) {
  const _isMovie = String(r.item_type || '') === 'Movie'
  const _isTv = !_isMovie && (r.season_num == null && r.episode_num == null)
  editDlgForm.value = {
    item_id: r.item_id, server_id: r.server_id || '',
    series_name: String(r.series_name || r.title || '').trim(),
    name_before: r.name_before, name_after: r.name_after || r.name_before,
    name_after0: r.name_after || r.name_before,
    role_before: r.role_before || '', role_after: r.role_after || r.role_before || '',
    role_after0: r.role_after || r.role_before || '',
    season_num: r.season_num ?? null, episode_num: r.episode_num ?? null, index: r.index,
    role_level: _isMovie ? 'movie' : (_isTv ? 'tv' : 'ep'),
    loc: occLabel(r),
  }
  editDlgRoleScope.value = _isMovie ? 'single' : (_isTv ? 'tv' : 'single')
  editDlgNameScope.value = 'single'   // v4.6.74：人名默认只改当前这一条
  editDlgOpen.value = true
  loadEditDlgOcc()
}
function openMovieEdit(row) {
  const _t = String(itemMeta.value?.title || selected.value?.title || '')
  editDlgForm.value = {
    item_id: selected.value?.item_id || '', server_id: selected.value?.server_id || '',
    series_name: _t,
    name_before: row.name_before,
    name_after: row.name_after || row.name_before || '',
    name_after0: row.name_after || row.name_before || '',
    role_before: row.role_before || '',
    role_after: row.role_after || row.role_before || '',
    role_after0: row.role_after || row.role_before || '',
    season_num: null, episode_num: null, index: null,
    role_level: 'movie',
    loc: `${_t || '该条目'} · 本片名单`,
  }
  editDlgRoleScope.value = 'single'
  editDlgNameScope.value = 'single'   // v4.6.74：人名默认只改当前这一条
  editDlgOpen.value = true
  loadEditDlgOcc()
}

const dbBusy = ref('')
async function clearDb() {
  if (!guard.check('清空翻译记录')) return   // v4.6.70：统一守卫
  if (!await askConfirm({
    title: '清空全部翻译记录',
    text: '确认清空全部翻译记录？',
    detail: '此操作不可恢复：只清空翻译记录与写回队列；人名池（含人工修正）保留不受影响，下次扫描会直接用池内译文重建记录，基本不重复消耗 AI 额度。如需清人名池请去「人名池」页。',
    okText: '清空',
    color: 'error',
  })) return
  dbBusy.value = 'clear'
  try {
    const r = await api.post(props.api, '/db/clear')
    notify(r?.message || '已清空', 'success')
    selected.value = null; people.value = []
    loadItems(); emit('action')
  } catch (e) { notify((e && e.message) || '清空失败', 'error') } finally { dbBusy.value = '' }
}
async function exportDb() {
  dbBusy.value = 'export'
  try {
    // client.js unwrap 已解出 data（数组），不能再取 .data
    const r = await api.get(props.api, '/db/export')
    const rows = Array.isArray(r) ? r : []
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `embypeople_export_${Date.now()}.json`; a.click()
    URL.revokeObjectURL(url)
    notify(`已导出 ${rows.length} 条记录`, 'success')
  } catch (e) { notify((e && e.message) || '导出失败', 'error') } finally { dbBusy.value = '' }
}
const importFile = ref(null)
function onImportPick(e) {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  if (!guard.check('导入翻译记录')) { e.target.value = ''; return }   // v4.6.70：统一守卫
  const reader = new FileReader()
  reader.onload = async () => {
    dbBusy.value = 'import'
    try {
      let rows
      try { rows = JSON.parse(reader.result) } catch (_) { throw new Error('文件不是有效 JSON') }
      if (!Array.isArray(rows)) rows = rows?.records || rows?.rows || []
      const r = await api.post(props.api, '/db/import', { rows })
      notify(r?.message || '导入完成', 'success')
      loadItems(); emit('action')
    } catch (err) { notify((err && err.message) || '导入失败', 'error') } finally { dbBusy.value = ''; e.target.value = '' }
  }
  reader.readAsText(f)
}
async function delItem(node) {
  if (dbBusy.value === 'del') return
  if (!guard.check('删除翻译记录')) return   // v4.6.70：统一守卫（此前只看 is_running）
  if (!await askConfirm({
    title: '删除翻译记录',
    text: `删除「${node.item.title}」的翻译记录？`,
    detail: '该条目（含各集）的翻译记录将被删除；人名池保留（下次扫描同名命中可直接复用）。',
    okText: '删除',
    color: 'error',
  })) return
  dbBusy.value = 'del'
  try {
    const r = await api.post(props.api, '/db/delete', { item_id: node.item.item_id, server_id: node.item.server_id || '' })
    notify(r?.message || '已删除', 'success')
    if (itemKey(selected.value) && itemKey(selected.value) === itemKey(node.item)) { selected.value = null; people.value = [] }
    loadItems()
  } catch (e) { notify((e && e.message) || '删除失败', 'error') } finally { dbBusy.value = '' }
}
const retranslating = ref(false)
function isApiItem() {
  return !!selected.value?.server_id
}
const writeBackLabel = () => isApiItem() ? '恢复到 Emby' : '写入'
const writeBackTooltip = () => isApiItem()
  ? '把库中翻译后名单写回 Emby（API 模式）'
  : '两排写入文件；第一排再写入服务器'
async function writeBackItem() {
  if (!selected.value) return
  await loadStatus()   // v4.6.70：单条写回同样过统一守卫
  if (!guard.check('写入（当前条目）')) return
  try {
    const r = await api.post(props.api, '/db/restore', { item_id: selected.value.item_id, server_id: selected.value.server_id || '' })
    notify(r?.message || '写回完成', 'success')
    selectItem(selected.value)
  } catch (e) { notify((e && e.message) || '写回失败', 'error') }
}
async function retranslateItem() {
  if (!selected.value || retranslating.value) return
  await loadStatus()   // v4.6.70：拉最新任务状态后交给统一守卫（此前只看 is_running）
  if (!guard.check('重新翻译（当前条目）')) return
  // 与「全部翻译」一致：先弹窗确认本次翻译范围（第一排/第二排/两排）
  await openTranslateDlg('item')
}
const rescanning = ref(false)
async function rescanItem() {
  if (!selected.value || rescanning.value) return
  await loadStatus()   // v4.6.70：同上 —— 重扫会改库数据，必须过统一守卫
  if (!guard.check('重新拉取（重扫当前条目）')) return
  rescanning.value = true
  try {
    const r = await api.post(props.api, '/db/rescan_item', { item_id: selected.value.item_id, server_id: selected.value.server_id || '' })
    notify(r?.message || '已重新拉取（重扫这一条）', 'success')
    selectItem(selected.value)
    loadItems()
  } catch (e) { notify((e && e.message) || '重新拉取失败', 'error') } finally { rescanning.value = false }
}
const autoWriteback = ref(false)
// v4.6.75（规范 §五-1/§五-5）：任务「运行中 → 结束」跳变检测 —— 结束瞬间立即刷新详情与统计，
// 此前只靠 30s 定时器，会出现「翻译已完成但界面仍显示未翻译」。
let _wasTaskRunning = false
// v4.6.104（LIB-009）：库数据版本号（后端 db_rev，只在 person 表写入时自增）。
// 用户诉求：「有数据更新才刷新，没更新干嘛要刷新」——左侧列表不再按固定周期重拉，
// 改由 8s 的状态轮询带回 items_rev，**只有版本号变了才 loadItems(true)**。
let _lastItemsRev = null
async function loadStatus() {
  try {
    const st = await api.get(props.api, '/status')
    // v4.6.70：统一任务守卫同步（扫描 / 翻译 / 写回 / 人名池 / 探测库 + 常驻翻译 worker 许可）
    guard.loadStatus(st)
    // v4.6.104（LIB-009）：变更检测 —— 没写库就一个字节都不重拉
    const _rev = (st && st.items_rev != null) ? String(st.items_rev) : ''
    if (_rev && _rev !== _lastItemsRev) {
      if (_lastItemsRev !== null) loadItems(true)   // 首帧列表已由 startPoll 拉过，不重复
      _lastItemsRev = _rev
    }
    autoWriteback.value = !!st?.auto_writeback
    const _run = !!(st?.tasks?.translate || st?.tasks?.writeback
                    || (st?.tx && (st.tx.requested || st.tx.running))
                    || st?.translate_status?.running)
    if (_wasTaskRunning && !_run) {
      // 翻译/写回刚结束 → 立即重读最新状态（数据库已更新；不等下一次轮询）
      refreshDetailSoft()
      loadTxPreview(true)
      loadItems(true)
      if (pendingDlg.value) loadPendingDetail(true)
    }
    _wasTaskRunning = _run
  } catch (e) {}
}
// v4.6.70：改由统一守卫提供（此前只看 is_running，漏了常驻翻译 worker 与写回/池/探测）
const dataOpBlocked = computed(() => guard.lock.value)
const dataOpBlockedHint = computed(() => guard.hint.value)

const txDlg = ref(false)
const txMode = ref('library')   // library=全部翻译 / item=重新翻译当前条目
const txBusy = ref(false)
const txScope = ref('default')   // default=使用设置默认 / person=只翻第一排 / role=只翻第二排 / both=两排都翻
const txPreview = ref({ names_pending: 0, roles_pending: 0, names_scope: 0, roles_scope: 0, items_pending: 0, pending_items: [], person_enabled: true, role_enabled: true, loading: false, loaded: false })
const TX_SCOPE_LABEL = { default: '使用设置默认', person: '只翻第一排人物姓名', role: '只翻第二排角色', both: '两排都翻' }
const txScopeLabel = computed(() => {
  if (txScope.value === 'default') {
    const _p = txPreview.value.person_enabled, _r = txPreview.value.role_enabled
    if (_p && _r) return '使用设置默认（第一排 + 第二排）'
    if (_p && !_r) return '使用设置默认（仅第一排）'
    if (!_p && _r) return '使用设置默认（仅第二排）'
    return '使用设置默认（当前设置未开启任何翻译目标）'
  }
  return TX_SCOPE_LABEL[txScope.value] || '使用设置默认'
})
// 「到底是哪个」：把待翻条目标题拼成一行（超 8 条截断并注明总数）
const pendingItemsText = computed(() => {
  const _list = txPreview.value.pending_items || []
  if (!_list.length) return ''
  const _names = _list.map((it) => (it && (it.title || it.item_id)) || '').filter(Boolean)
  const _head = _names.slice(0, 8).join('、')
  return _names.length > 8 ? `${_head} 等共 ${_names.length} 个` : _head
})
let _txPreviewInflight = false
async function loadTxPreview(silent = false) {
  if (_txPreviewInflight) return
  _txPreviewInflight = true
  if (!silent) txPreview.value = { ...txPreview.value, loading: true }
  try {
    const r = await api.get(props.api, '/db/translate_preview', _previewQuery())
    txPreview.value = {
      names_pending: r?.names_pending ?? 0,
      roles_pending: r?.roles_pending ?? 0,
      names_scope: r?.names_scope ?? 0,
      roles_scope: r?.roles_scope ?? 0,
      items_pending: r?.items_pending ?? 0,
      pending_items: Array.isArray(r?.pending_items) ? r.pending_items : [],
      // v4.6.61（P1-7）：写回状态独立统计 —— 翻译完成 ≠ 写回完成
      writeback_pending: r?.writeback_pending ?? 0,
      writeback_failed: r?.writeback_failed ?? 0,
      person_enabled: r?.person_enabled !== false,
      role_enabled: r?.role_enabled !== false,
      loading: false, loaded: true,
    }
  } catch (e) {
    txPreview.value = { ...txPreview.value, loading: false, loaded: true }
    if (!silent) notify((e && e.message) || '预估失败', 'error')
  } finally {
    _txPreviewInflight = false
  }
}
// 弹窗预估：按「本次选的排」+ 设置页总开关，算出「待翻 / 符合范围」各多少
const txEstimate = computed(() => {
  const p = txPreview.value
  const sc = txScope.value
  const wantP = sc === 'person' || sc === 'both' || (sc === 'default' && p.person_enabled)
  const wantR = sc === 'role' || sc === 'both' || (sc === 'default' && p.role_enabled)
  const names = wantP ? Number(p.names_pending || 0) : 0
  const roles = wantR ? Number(p.roles_pending || 0) : 0
  const namesScope = wantP ? Number(p.names_scope || 0) : 0
  const rolesScope = wantR ? Number(p.roles_scope || 0) : 0
  return { wantP, wantR, names, roles, namesScope, rolesScope,
           pending: names + roles, scope: namesScope + rolesScope }
})

// 「有任务 · 待翻译」点开后的明细
const pendingDlg = ref(false)
const pendingBusy = ref(false)
const pendingData = ref({ items: [], items_total: 0, names_pending: 0, roles_pending: 0,
                          names_scope: 0, roles_scope: 0, person_on: true, role_on: true })
async function loadPendingDetail (silent = false) {
  if (!silent) pendingBusy.value = true
  try {
    const r = await api.get(props.api, '/db/pending_detail', { limit_items: 30, terms_per_item: 12 })
    if (r && Array.isArray(r.items)) pendingData.value = r
  } catch (e) { if (!silent) notify((e && e.message) || '读取待翻译明细失败', 'error') }
  if (!silent) pendingBusy.value = false
}
async function openPendingDlg () {
  pendingDlg.value = true
  await loadPendingDetail(false)
}
// 预估口径：弹窗打开且为「重新翻译」时按当前条目统计；否则按全库（角标/轮询用全库）
function _previewQuery() {
  if (txDlg.value && txMode.value === 'item' && selected.value) {
    return { item_id: selected.value.item_id, server_id: selected.value.server_id || '' }
  }
  return {}
}
async function openTranslateDlg(mode = 'library') {
  // v4.6.70：发起翻译前统一守卫（条目级重翻已在上游 retranslateItem 校验过，这里兜底）
  await loadStatus()
  if (!guard.check(mode === 'item' ? '重新翻译（当前条目）' : '全部翻译')) return
  txMode.value = mode
  txScope.value = 'default'
  txDlg.value = true
  await loadTxPreview()
}
async function confirmTranslate() {
  if (txBusy.value) return
  txBusy.value = true
  try {
    const _scope = txScope.value === 'default' ? 'both' : txScope.value
    let r
    if (txMode.value === 'item' && selected.value) {
      r = await api.post(props.api, '/db/retranslate', {
        item_id: selected.value.item_id,
        server_id: selected.value.server_id || '',
        target_scope: _scope,
      })
    } else {
      r = await api.post(props.api, '/db/translate_library', { target_scope: _scope })
    }
    notify(r?.message || '已启动（后台执行）', r?.success === false ? 'error' : 'success')
    txDlg.value = false
    if (txMode.value === 'item' && selected.value) { selectItem(selected.value); loadItems() }
    loadTxPreview(true)
  } catch (e) { notify((e && e.message) || '启动失败', 'error') } finally { txBusy.value = false }
}
// 兼容旧引用（若有其它入口调用 translateAll，仍走弹窗）
function translateAll() { openTranslateDlg() }
const writebackBusy = ref(false)
async function writebackAll() {
  await loadStatus()   // v4.6.70：写回期间禁止再发起（也禁止其它修改型操作）
  if (!guard.check('全部写回')) return
  if (!await askConfirm({
    title: '全部写回 nfo',
    text: '把库中全部条目的已翻译名单批量写回 nfo 文件？',
    detail: '不重新翻译，只落盘；.bak 备份按设置自动保留。',
    okText: '写回',
    color: 'warning',
  })) return
  writebackBusy.value = true
  try {
    const r = await api.post(props.api, '/db/writeback_all')
    notify(r?.message || '全部写回已启动（后台执行）', 'success')
    loadTxPreview(true)
  } catch (e) { notify((e && e.message) || '启动失败', 'error') } finally { writebackBusy.value = false }
}

const isNarrow = ref(false)
function _syncNarrow() { try { isNarrow.value = window.innerWidth <= 600 } catch (e) { isNarrow.value = false } }


const TYPE_LABEL = { Actor: '演员', Director: '导演', Writer: '编剧', Producer: '制片人', VoiceActor: '声优', GuestStar: '客串', Composer: '作曲', Cinematographer: '摄影', Editor: '剪辑' }
// v4.6.97：分集名单 / 主演员名单也「按类型分段」（与电影页同款）——
// 此前平铺只显示「名字 + 饰 角色」，看不出哪个是导演/编剧（用户实测困惑）。
// 类型来自 nfo：<actor> 的 <type>（缺省或 Actor = 演员；显式 GuestStar = 客串），
// <director> = 导演、<writer> = 编剧、<credits> = 制片人
// ——「只有 nfo 明确写客串才算客串，其余都算演员」。
const TYPE_ORDER = ['Actor', 'VoiceActor', 'GuestStar', 'Director', 'Writer', 'Producer',
                    'Composer', 'Cinematographer', 'Editor']
function typeLabel(t) { return TYPE_LABEL[t] || t || '演员' }
function typeIcon(t) {
  if (t === 'Director') return 'mdi-video-outline'
  if (t === 'Writer') return 'mdi-pencil-outline'
  if (t === 'Producer') return 'mdi-briefcase-outline'
  if (t === 'GuestStar') return 'mdi-account-arrow-right-outline'
  if (t === 'VoiceActor') return 'mdi-microphone-outline'
  return 'mdi-account'
}
// 按类型分组（保序：先 TYPE_ORDER，未知类型按出现顺序追加）→ [{type,label,list}]
function groupByType(list) {
  const map = new Map()
  for (const p of (list || [])) {
    const t = (p && p.type) || 'Actor'
    if (!map.has(t)) map.set(t, [])
    map.get(t).push(p)
  }
  const out = []
  for (const t of TYPE_ORDER) {
    if (map.has(t)) { out.push({ type: t, label: typeLabel(t), list: map.get(t) }); map.delete(t) }
  }
  for (const [t, l] of map) out.push({ type: t, label: typeLabel(t), list: l })
  return out
}
const mainCastGroups = computed(() => groupByType(libMainCast.value))
function posterUrlOf(it) { return it?.poster_url || '' }

function srcTag(p) {
  if (p.season_num == null) return '本剧'
  return `S${p.season_num}E${p.episode_num}`
}
function fmtSrcs(srcs) {
  const seasons = {}
  let hasSeries = false
  for (const tag of srcs || []) {
    if (tag === '本剧') { hasSeries = true; continue }
    const m = /^S(\d+)E(\d+)$/.exec(tag)
    if (m) {
      const s = +m[1]
      ;(seasons[s] = seasons[s] || []).push(+m[2])
    }
  }
  const parts = []
  for (const s of Object.keys(seasons).map(Number).sort((a, b) => a - b)) {
    const eps = [...new Set(seasons[s])].sort((a, b) => a - b)
    const ranges = []
    let start = eps[0], prev = eps[0]
    for (let i = 1; i < eps.length; i++) {
      if (eps[i] === prev + 1) { prev = eps[i]; continue }
      ranges.push(start === prev ? `E${start}` : `E${start}-${prev}`)
      start = prev = eps[i]
    }
    ranges.push(start === prev ? `E${start}` : `E${start}-${prev}`)
    parts.push(`S${s} ${ranges.join('、')}`)
  }
  let text = parts.join(' / ')
  if (hasSeries) text = text ? `本剧 / ${text}` : '本剧'
  return text || '—'
}
const summaryGroups = computed(() => {
  const groups = []
  const idx = {}
  for (const p of people.value) {
    const t = p.type || 'Actor'
    if (!(t in idx)) {
      idx[t] = groups.length
      groups.push({ type: t, label: TYPE_LABEL[t] || t, list: [] })
    }
    groups[idx[t]].list.push(p)
  }
  for (const g of groups) {
    const byName = new Map()
    for (const p of g.list) {
      // 身份键（UI-009）：以「原文 + 角色」为身份，绝不以译名为键
      // —— 否则两个不同原文被译成同字时会被错误合并成一行
      const key = `${p.name_before || p.name_after || ''}\u0001${p.role_before || p.role_after || ''}`
      let row = byName.get(key)
      if (!row) {
        row = {
          name_before: p.name_before || '',
          name_after: p.name_after || '',
          role_before: p.role_before || '',
          role_after: p.role_after || '',
          srcs: [],
          befores: [],
        }
        byName.set(key, row)
      }
      if (p.name_before && !row.befores.includes(p.name_before)) row.befores.push(p.name_before)
      // 展示用原文：优先取「与译文不同」的真实原文（剧级中文原文被集级原文覆盖显示）
      if (p.name_before && p.name_after && p.name_before !== p.name_after) {
        row.name_before = p.name_before
        if (p.role_before) row.role_before = p.role_before
      }
      const tag = srcTag(p)
      if (!row.srcs.includes(tag)) row.srcs.push(tag)
      if (p.name_after && p.name_after !== p.name_before) row.name_after = p.name_after
      if (p.role_after && p.role_after !== p.role_before) row.role_after = p.role_after
    }
    const rows = [...byName.values()]
    for (const r of rows) {
      r.srcs.sort((a, b) => (a === '本剧' ? -1 : b === '本剧' ? 1 : a.localeCompare(b)))
    }
    g.list = rows
  }
  return groups
})
const summaryTotal = computed(() => summaryGroups.value.reduce((n, g) => n + g.list.length, 0))


let pollTimer = null
let detailTimer = null
// v4.6.104（LIB-008/009）：列表不再按固定周期重拉。
// 用户反馈①：列表每 8s 全量刷一次观感很差（「页面拉一下」）；
// 用户反馈②：「有数据更新才刷新，没数据更新干嘛要刷新」。
// 现改为**事件驱动**：只有 ①items_rev 变化（真的写库了，见 loadStatus）②任务结束跳变
// ③用户操作（增删改/翻译/导入）④切回前台 —— 才拉列表。状态与统计徽章仍保持 8s（要跟手）。
const FAST_POLL_MS = 8000
function startPoll() {
  stopPoll()
  loadItems(true)
  loadStatus()
  loadTxPreview(true)
  // v4.6.60（P1-1）：明细弹窗打开时随轮询一起刷新 —— 此前只在打开时拉一次，
  // 后台翻译完成后弹窗仍显示旧的 3 条（要关掉重开才更新）
  pollTimer = setInterval(() => {
    if (document.hidden) return          // v4.6.104：页面在后台不轮询（省请求；切回来立即补一次）
    loadStatus()                         // 列表刷新由 loadStatus 里的 items_rev 变更检测触发
    loadTxPreview(true)
    if (pendingDlg.value) loadPendingDetail(true)
  }, FAST_POLL_MS)
  detailTimer = setInterval(refreshDetailSoft, 30000)
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (detailTimer) { clearInterval(detailTimer); detailTimer = null }
}
// v4.6.104：从后台切回前台立即补一次（否则最长要等 30s 才看到新数据）
function _onDocVisible() {
  if (document.hidden) return
  loadItems(true); loadStatus(); loadTxPreview(true)
}
onMounted(() => {
  startPoll(); _syncNarrow()
  window.addEventListener('resize', _syncNarrow)
  document.addEventListener('visibilitychange', _onDocVisible)
})
onActivated(startPoll)
onDeactivated(stopPoll)
onBeforeUnmount(() => {
  stopPoll(); teardownEpObserver(); teardownItemObserver()
  window.removeEventListener('resize', _syncNarrow)
  document.removeEventListener('visibilitychange', _onDocVisible)
})
</script>

<template>
  <div class="epl-lib">
    <!-- 顶部操作栏：只留操作按钮（筛选已下沉到左右两栏底部，参考 zitifenlei）
         窄屏（手机 PC 模式）低频按钮收进「更多 ▾」下拉 —— 一排放下，不再折行/左侧留空 -->
    <div class="epl-topbar">
      <v-tooltip :text="dataOpBlockedHint || '批量翻译库中未译词条（可选本次翻译范围：第一排/第二排；只写库，自动写回开启时条目翻完自动落盘，否则点「全部写回」）'" location="top">
        <template #activator="{ props: tp }">
          <v-btn size="small" color="primary" variant="tonal" v-bind="tp" :loading="txBusy" :disabled="dataOpBlocked" @click="openTranslateDlg">
            <v-icon start size="16">mdi-translate</v-icon>全部翻译
          </v-btn>
        </template>
      </v-tooltip>
      <v-tooltip v-if="!autoWriteback" :text="dataOpBlockedHint || '把库中已翻译名单批量写回 nfo 文件（不重新翻译）'" location="top">
        <template #activator="{ props: tp }">
          <v-btn size="small" color="success" variant="tonal" v-bind="tp" :loading="writebackBusy" :disabled="dataOpBlocked" @click="writebackAll">
            <v-icon start size="16">mdi-file-import-outline</v-icon>全部写回
          </v-btn>
        </template>
      </v-tooltip>
      <div class="d-none d-md-flex align-center ga-2">
      <v-tooltip text="导出全部翻译记录为 JSON" location="top">
        <template #activator="{ props: tp }">
          <v-btn size="small" variant="tonal" v-bind="tp" :loading="dbBusy==='export'" @click="exportDb">
            <v-icon start size="16">mdi-export-variant</v-icon>导出
          </v-btn>
        </template>
      </v-tooltip>
      <v-tooltip :text="dataOpBlockedHint || '从 JSON 导入翻译记录'" location="top">
        <template #activator="{ props: tp }">
          <v-btn size="small" variant="tonal" v-bind="tp" :disabled="dataOpBlocked" :loading="dbBusy==='import'" @click="$refs.importInput?.click()">
            <v-icon start size="16">mdi-import</v-icon>导入
          </v-btn>
        </template>
      </v-tooltip>
      <v-tooltip :text="dataOpBlockedHint || '清空全部翻译记录（不可恢复；人名池保留）'" location="top">
        <template #activator="{ props: tp }">
          <v-btn size="small" variant="tonal" color="error" v-bind="tp" :disabled="dataOpBlocked" :loading="dbBusy==='clear'" @click="clearDb">
            <v-icon start size="16">mdi-delete-sweep-outline</v-icon>清空
          </v-btn>
        </template>
      </v-tooltip>
      </div>
      <v-tooltip location="top" max-width="420" :text="txPreview.loaded
          ? (txPreview.items_pending > 0
              ? `待翻译统计：${txPreview.items_pending} 个条目未翻完（第一排 ${txPreview.names_pending} 词条 · 第二排 ${txPreview.roles_pending} 词条）${pendingItemsText ? '：' + pendingItemsText : ''}`
              : '待翻译统计：所有条目均已翻译完成')
          : '待翻译统计加载中…'">
          <template #activator="{ props: tp }">
            <v-chip v-bind="tp" size="small" variant="tonal" link class="epl-pending-chip" @click="openPendingDlg"
                    :color="!txPreview.loaded ? 'grey' : (txPreview.items_pending > 0 ? 'warning' : 'success')"
                    :prepend-icon="!txPreview.loaded ? 'mdi-progress-question' : (txPreview.items_pending > 0 ? 'mdi-alert-circle-outline' : 'mdi-check-circle-outline')">
              <span v-if="!txPreview.loaded">统计中…</span>
              <template v-else-if="txPreview.items_pending > 0"><span class="epl-pending-prefix">有任务 · 待翻译 </span>{{ txPreview.items_pending }} 个</template>
              <span v-else>无待翻译</span>
            </v-chip>
          </template>
        </v-tooltip>
      <!-- v4.6.61（P1-7）：写回状态独立展示 —— 翻译完成 ≠ 写回完成 -->
      <v-tooltip location="top" max-width="440" :text="txPreview.loaded
          ? (txPreview.writeback_pending > 0
              ? `写回统计：${txPreview.writeback_pending} 个条目已翻译但尚未写入 NFO（翻译完成 ≠ 写回完成）。自动写回开启时会自动落盘；未开启请点「全部写回」${txPreview.writeback_failed ? '；其中写入失败 ' + txPreview.writeback_failed + ' 个（将自动重试）' : ''}`
              : '写回统计：所有已翻译条目都已写入 NFO')
          : '写回统计加载中…'">
          <template #activator="{ props: tp }">
            <v-chip v-bind="tp" size="small" variant="tonal"
                    :color="!txPreview.loaded ? 'grey' : (txPreview.writeback_pending > 0 ? 'info' : 'success')"
                    :prepend-icon="!txPreview.loaded ? 'mdi-progress-question' : (txPreview.writeback_pending > 0 ? 'mdi-content-save-move-outline' : 'mdi-check-circle-outline')">
              <span v-if="!txPreview.loaded">写回统计中…</span>
              <template v-else-if="txPreview.writeback_pending > 0">待写回 {{ txPreview.writeback_pending }} 个</template>
              <span v-else>无待写回</span>
            </v-chip>
          </template>
        </v-tooltip>
      <input ref="importInput" type="file" accept=".json,application/json" style="display:none" @change="onImportPick">
      <v-menu location="bottom end" class="d-md-none">
        <template #activator="{ props: mp }">
          <v-btn size="small" variant="tonal" v-bind="mp" class="d-md-none">
            更多<v-icon end size="16">mdi-chevron-down</v-icon>
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item prepend-icon="mdi-export-variant" title="导出翻译记录（JSON）" :disabled="dbBusy==='export'" @click="exportDb"></v-list-item>
          <v-list-item prepend-icon="mdi-import" :title="dataOpBlockedHint || '导入翻译记录（JSON）'" :disabled="dbBusy==='import' || dataOpBlocked" @click="$refs.importInput?.click()"></v-list-item>
          <v-list-item prepend-icon="mdi-delete-sweep-outline" :title="dataOpBlockedHint || '清空全部翻译记录（不可恢复；人名池保留）'" :disabled="dbBusy==='clear' || dataOpBlocked" base-color="error" @click="clearDb"></v-list-item>
        </v-list>
      </v-menu>
      <div class="epl-topbar-right"></div>
    </div>

    <v-row no-gutters class="epl-lib-row">
      <!-- 左栏：分库分组折叠 + 条目（筛选放卡片最顶上，参考 zitifenlei） -->
      <v-col cols="12" md="5">
        <v-card class="epl-card-bg epl-list-card epl-flex-card">
          <div class="epl-sidebar epl-sidebar-top pa-2">
            <div class="d-flex align-center ga-2 flex-wrap">
              <v-text-field v-model="search" placeholder="搜索剧集 / 电影标题…" density="compact" variant="outlined"
                            hide-details clearable prepend-inner-icon="mdi-magnify" class="epl-sidebar-search"></v-text-field>
              <v-btn-toggle v-model="filterType" density="compact" variant="tonal" color="primary" mandatory size="small">
                <v-btn value="">全部</v-btn>
                <v-btn value="Series">剧集</v-btn>
                <v-btn value="Movie">电影</v-btn>
              </v-btn-toggle>
            </div>
          </div>
          <v-divider style="opacity:.3"></v-divider>
          <v-card-text class="pa-0 epl-col-body">
            <v-progress-linear v-if="loadingList" indeterminate color="primary"></v-progress-linear>
            <div v-if="!loadingList && !visibleNodes.length" class="epl-empty pa-6">暂无翻译记录</div>
            <v-list v-else density="compact" class="pa-0" nav>
              <template v-for="node in visibleNodes" :key="node.type + ':' + (itemKey(node.item) || node.lib)">
                <!-- 分库分组节点 -->
                <v-list-item v-if="node.type === 'group'" class="epl-group-item" @click="toggleGroup(node.lib)">
                  <template #prepend>
                    <v-icon size="16" class="mr-1">{{ expandedLibs.has(node.lib) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                    <v-icon size="14" color="info" class="mr-1">{{ libIcon(node.lib) }}</v-icon>
                  </template>
                  <v-list-item-title class="epl-group-name">{{ node.lib }}</v-list-item-title>
                  <template #append><span class="epl-group-count">{{ node.count }}</span></template>
                </v-list-item>
                <!-- 条目节点 -->
                <v-list-item v-else :active="itemKey(selected) === itemKey(node.item)" class="epl-item"
                             :class="{ 'epl-item-dead': node.item.deleted_at, 'epl-item-partdead': !node.item.deleted_at && node.item.deleted_eps > 0 }"
                             :style="{ paddingLeft: (node.depth * 6 + 16) + 'px' }" @click="selectItem(node.item)">
                  <template #prepend>
                    <!-- v4.6.82：左栏一律用图标，不加载海报 —— 逐行图片会在滚动/翻页时
                         对服务器发起大量请求（用户实测：一拉就疯狂请求）。
                         v4.6.83：图标按类型区分（电影 mdi-movie-outline / 剧集 mdi-television-classic）。 -->
                    <v-icon size="22" color="grey" class="epl-thumb-placeholder">{{ itemIcon(node.item) }}</v-icon>
                  </template>
                  <v-list-item-title class="epl-item-name" :title="node.item.title">
                    {{ node.item.title }}
                    <v-chip v-if="node.item.deleted_at" size="x-small" color="error" variant="flat" class="ml-1">
                      <v-icon start size="12">mdi-progress-clock</v-icon>待恢复
                    </v-chip>
                    <v-chip v-else-if="node.item.deleted_eps > 0" size="x-small" color="warning" variant="flat" class="ml-1"
                            title="部分集被服务器删除，观察期内重新入库自动恢复；超期自动清理（不会一直显示）">
                      <v-icon start size="12">mdi-progress-clock</v-icon>{{ node.item.deleted_eps }} 集待恢复
                    </v-chip>
                  </v-list-item-title>
                  <v-list-item-subtitle class="epl-item-meta">
                    {{ node.item.item_type }} · {{ node.item.person_count }} 人
                    <template v-if="node.item.episode_count"> · {{ node.item.episode_count }} 集</template>
                  </v-list-item-subtitle>
                  <template #append>
                    <v-btn size="x-small" variant="text" color="error" @click.stop="delItem(node)">
                      <v-icon size="16">mdi-close</v-icon>
                    </v-btn>
                  </template>
                </v-list-item>
              </template>
            </v-list>
            <div v-if="itemHasMore" ref="itemSentinel" class="epl-load-sentinel">
              <v-progress-circular indeterminate size="20" class="my-2"></v-progress-circular>
            </div>
            <div v-else-if="!loadingList && items.length" class="epl-load-sentinel">
              <span class="epl-cast-hint">— 已全部加载 —</span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- 右栏：人物 —— 顶部保持「海报+标题+按钮」，海报下放人物搜索栏，下面是名单/搜索结果 -->
      <v-col cols="12" md="7">
        <v-card class="epl-card-bg epl-detail-card epl-flex-card">
          <div v-if="selected" class="pa-3 epl-detail-head">
            <div class="d-flex align-center">
              <div class="epl-poster-wrap mr-3">
                <v-img v-if="posterData || itemMeta?.poster_url" :src="posterData || itemMeta.poster_url" width="64" height="92" cover class="epl-poster"></v-img>
                <v-icon v-else size="40" color="grey">mdi-movie-outline</v-icon>
              </div>
              <div class="flex-grow-1" style="min-width:0">
                <div class="epl-detail-title" :title="itemMeta?.title || selected.title">{{ itemMeta?.title || selected.title }}</div>
                <v-img v-if="logoData" :src="logoData" max-width="180" max-height="40" contain class="mb-1 epl-logo"></v-img>
                <div class="epl-detail-meta">
                  {{ itemMeta?.item_type || selected.item_type }} · 名单 {{ summaryTotal }} 人 / 全部 {{ people.length }} 条
                  <template v-if="itemMeta?.episode_count"> · {{ itemMeta.episode_count }} 集</template>
                </div>
              </div>
              <div class="d-flex flex-column ga-1 ml-3" style="flex-shrink:0">
                <v-tooltip text="重新翻译当前条目（先弹窗选范围：第一排/第二排/两排；只翻这一条，不扫全库）" location="top">
                  <template #activator="{ props: tp }">
                    <v-btn size="small" variant="tonal" color="warning" v-bind="tp" :loading="retranslating" :disabled="running" @click="retranslateItem">
                      <v-icon start size="18">mdi-refresh-circle</v-icon>重新翻译
                    </v-btn>
                  </template>
                </v-tooltip>
                <v-tooltip :text="writeBackTooltip()" location="top">
                  <template #activator="{ props: tp }">
                    <v-btn size="small" color="primary" variant="tonal" v-bind="tp" :disabled="running" @click="writeBackItem">
                      <v-icon start size="18">{{ isApiItem() ? 'mdi-restore' : 'mdi-file-import-outline' }}</v-icon>{{ writeBackLabel() }}
                    </v-btn>
                  </template>
                </v-tooltip>
                <v-tooltip text="只重扫当前这一条：按本地 NFO 重新采集名单（更新原文/层级/人数，保留已有译文），不翻译、不写文件、不扫全库" location="left">
                  <template #activator="{ props: tp }">
                    <v-btn size="small" color="teal" variant="tonal" v-bind="tp" :loading="rescanning" :disabled="running" @click="rescanItem">
                      <v-icon start size="18">mdi-file-refresh-outline</v-icon>重新拉取
                    </v-btn>
                  </template>
                </v-tooltip>
              </div>
            </div>
          </div>
          <div v-if="selected" class="epl-sidebar pa-2">
            <v-text-field v-model="personSearch" placeholder="🔍 搜索人物（原文名 / 译文 / 角色）…" density="compact"
                          variant="outlined" hide-details clearable prepend-inner-icon="mdi-account-search-outline"
                          @update:model-value="onPersonSearchInput" @click:clear="clearPersonSearch"></v-text-field>
          </div>
          <v-divider style="opacity:.3"></v-divider>
          <v-card-text class="pa-0 epl-col-body">
            <template v-if="searchMode">
              <div v-if="searchingPeople" class="epl-empty pa-6"><v-progress-circular indeterminate size="22" color="primary"></v-progress-circular> 搜索中…</div>
              <div v-else-if="!searchResults.length" class="epl-empty pa-6">未找到匹配人物（换个关键词试试）</div>
              <template v-else>
                <div class="pa-3 pb-1 epl-search-title">
                  <v-icon size="15" class="mr-1">mdi-account-search-outline</v-icon>人物搜索结果：{{ searchResults.length }} 个名字
                </div>
                <v-list density="compact" class="pa-0" nav>
                  <template v-for="(row, i) in searchResults" :key="i">
                  <v-list-item class="epl-person-search-item">
                    <template #prepend>
                      <v-avatar size="30" color="rgba(128,128,128,.2)" class="mr-2">
                        <v-icon size="16">{{ row.type === 'Director' ? 'mdi-video-outline' : row.type === 'Writer' ? 'mdi-pencil-outline' : 'mdi-account' }}</v-icon>
                      </v-avatar>
                    </template>
                    <div class="flex-grow-1" style="min-width:0">
                      <div class="epl-person-name">
                        <span class="epl-new" :class="{ 'epl-same': !row.name_after || row.name_after === row.name_before }">{{ row.name_after || row.name_before || '—' }}</span>
                        <s v-if="row.name_after && row.name_before && row.name_after !== row.name_before" class="epl-dim" style="margin-left:8px">{{ row.name_before }}</s>
                        <v-btn size="x-small" variant="text" icon class="epl-edit-btn" title="编辑译文（弹窗里选范围）" @click="openGlobalEdit(row)">
                          <v-icon size="14">mdi-pencil-outline</v-icon>
                        </v-btn>
                      </div>
                      <div class="epl-person-role">
                        <template v-if="row.role_after || row.role_before">饰 {{ row.role_after || row.role_before }}</template>
                        <v-chip size="x-small" variant="tonal" class="ml-1 epl-occ-toggle"
                                :title="occKey === String(row.name_before || '') ? '收起出现清单' : '展开出现清单（逐处编辑）'"
                                @click.stop="toggleOcc(row)">
                          {{ row.count }} 处 {{ occKey === String(row.name_before || '') ? '▴' : '▾' }}
                        </v-chip>
                        <span v-if="row.series && row.series.length" class="epl-src-tags" :title="row.series.join(' / ')">{{ row.series.join('、').slice(0, 24) }}</span>
                      </div>
                    </div>
                  </v-list-item>
                  <div v-if="occKey === String(row.name_before || '')" class="epl-occ-list">
                    <div v-if="occLoading" class="epl-cast-hint pa-2">加载出现清单…</div>
                    <div v-else-if="!occRows.length" class="epl-cast-hint pa-2">无出现记录</div>
                    <template v-else>
                      <div v-for="(r, j) in occRows" :key="j" class="epl-occ-row">
                        <span class="epl-occ-label" :title="occLabel(r)">{{ occLabel(r) }}</span>
                        <v-btn icon="mdi-pencil" size="x-small" variant="text" class="epl-edit-btn" @click="openOccEdit(r)"></v-btn>
                      </div>
                    </template>
                  </div>
                  </template>
                </v-list>
                <div class="text-caption epl-person-search-hint">按「原文名」汇总；点「N 处 ▾」展开出现清单可逐处编辑；铅笔（汇总行）= 全库同名改（弹窗里确认数量）；出现清单里的铅笔可选「仅这一处 / 该剧所有集 / 全库同名」。</div>
              </template>
            </template>
            <template v-else>
              <div v-if="!selected" class="epl-empty pa-6">点击左侧条目查看翻译前后名单</div>
              <div v-else class="pa-4">
                <v-progress-circular v-if="loadingPeople" indeterminate color="primary" class="ma-6"></v-progress-circular>
                <template v-else>
                  <div v-if="!people.length" class="epl-empty pa-4">该条目无人物记录（先扫描，或开「处理单集」收集各集）</div>
                  <template v-else>
                    <template v-if="isSeriesSelected()">
                      <div class="epl-cast-section">
                        <div class="epl-cast-head">
                          <div class="epl-cast-title">
                            <v-icon size="18" color="primary">mdi-account-star</v-icon>
                            主演员 <span class="epl-cast-hint">（来自 tvshow.nfo · 编辑时在弹窗里选范围）</span>
                          </div>
                        </div>
                        <template v-if="libMainCast.length">
                          <div v-for="grp in mainCastGroups" :key="'main-g-' + grp.type" class="epl-type-block">
                            <div v-if="mainCastGroups.length > 1" class="epl-type-sub">
                              <v-icon size="14">{{ typeIcon(grp.type) }}</v-icon>
                              {{ grp.label }}<span class="epl-grp-count">{{ grp.list.length }}</span>
                            </div>
                            <div class="epl-actor-flow epl-actor-grid2">
                              <div v-for="(p, i) in grp.list" :key="'main-' + grp.type + '-' + i" class="epl-actor-chip"
                                   :class="{ 'is-voice': isVoiceActor(p) }">
                                <div class="epl-chip-col">
                                  <span class="epl-chip-name">{{ p.name_after || p.name_before }}</span>
                                  <span v-if="p.role_after || p.role_before" class="epl-chip-role">饰 {{ p.role_after || p.role_before }}</span>
                                </div>
                                <v-btn icon="mdi-pencil" size="x-small" variant="text" class="epl-chip-edit" @click="openEpEdit(p, null)"></v-btn>
                              </div>
                            </div>
                          </div>
                        </template>
                        <div v-else class="epl-cast-hint">（剧文件暂无主演记录，扫描完成后显示）</div>
                      </div>

                      <div v-if="libEpisodes.length" ref="epPanelRef" class="epl-cast-section">
                        <div class="epl-ep-toolbar">
                          <div class="epl-ep-toolbar-left">
                            <v-icon size="18" color="primary">mdi-television-classic</v-icon>
                            分集演员
                            <span class="epl-cast-hint">（<template v-if="epMultiSeason">当前 S{{ epCurrentSeason }} · </template>已显示 {{ epVisible.length }} / {{ epSeasonEps.length }} 集，滚动到底自动加载）</span>
                            <span v-if="!epMultiSeason && epDeletedTotal" class="epl-cast-hint" style="color: rgb(var(--v-theme-error))">（{{ epDeletedTotal }} 集待恢复）</span>
                          </div>
                          <div class="epl-ep-toolbar-right">
                            <v-btn v-if="!epAllLoaded" size="small" variant="text"
                                   prepend-icon="mdi-chevron-double-down" @click="loadMoreEps">加载更多</v-btn>
                          </div>
                        </div>
                        <div v-if="epMultiSeason" class="epl-season-tabs">
                          <v-tooltip v-for="sg in epSeasons" :key="'stab-' + sg.season" location="top"
                                     :text="(epDeletedCountBySeason.get(sg.season) || 0) > 0
                                            ? `本季 ${epDeletedCountBySeason.get(sg.season)} 集待恢复（服务器已删除，观察期内重新入库会自动恢复）`
                                            : `本季共 ${sg.count} 集`">
                            <template #activator="{ props: tabProps }">
                              <button type="button" class="epl-season-tab"
                                      :class="{ 'is-active': sg.season === epCurrentSeason, 'is-dead': (epDeletedCountBySeason.get(sg.season) || 0) > 0 }"
                                      :aria-pressed="sg.season === epCurrentSeason"
                                      v-bind="tabProps" @click="selectSeason(sg.season)">
                                <v-icon v-if="(epDeletedCountBySeason.get(sg.season) || 0) > 0" size="12">mdi-alert-outline</v-icon>
                                S{{ sg.season }}
                                <span class="epl-season-tab-count">{{ sg.count }}</span>
                              </button>
                            </template>
                          </v-tooltip>
                        </div>
                        <v-expansion-panels variant="accordion" class="epl-ep-panels">
                          <v-expansion-panel v-for="ep in epVisible" :key="epKey(ep)"
                                             :class="{ 'epl-ep-dead': epIsDeleted(ep) }"
                                             :subtitle="`${ep.people.length} 人`">
                            <template #title>
                              <span class="epl-ep-title" :title="epTitle(ep) ? (epPanelLabel(ep) + ' ' + epTitle(ep)) : epPanelLabel(ep)">{{ epPanelLabel(ep) }}<template v-if="epTitle(ep)">　{{ epTitle(ep) }}</template></span>
                              <span v-if="epIsDeleted(ep)" class="epl-ep-dead-tag">· 待恢复</span>
                            </template>
                            <template #text>
                              <div v-for="grp in groupByType(ep.people)" :key="epKey(ep) + '-g-' + grp.type" class="epl-type-block">
                                <div v-if="groupByType(ep.people).length > 1" class="epl-type-sub">
                                  <v-icon size="14">{{ typeIcon(grp.type) }}</v-icon>
                                  {{ grp.label }}<span class="epl-grp-count">{{ grp.list.length }}</span>
                                </div>
                                <div class="epl-actor-flow epl-actor-grid2">
                                  <div v-for="(p, i) in grp.list" :key="epKey(ep) + '-' + grp.type + '-' + i" class="epl-actor-chip"
                                       :class="{ 'is-voice': isVoiceActor(p) }">
                                    <div class="epl-chip-col">
                                      <span class="epl-chip-name">{{ p.name_after || p.name_before }}</span>
                                      <span v-if="p.role_after || p.role_before" class="epl-chip-role">饰 {{ p.role_after || p.role_before }}</span>
                                    </div>
                                    <v-btn icon="mdi-pencil" size="x-small" variant="text" class="epl-chip-edit" @click="openEpEdit(p, ep)"></v-btn>
                                  </div>
                                </div>
                              </div>
                            </template>
                          </v-expansion-panel>
                        </v-expansion-panels>
                        <div ref="epSentinel" class="epl-load-sentinel">
                          <v-progress-circular v-if="!epAllLoaded" indeterminate size="20" class="my-2"></v-progress-circular>
                          <span v-else class="epl-cast-hint">— 已全部加载 —</span>
                        </div>
                      </div>
                      <div v-else class="epl-cast-hint">（暂无分集记录：开「处理单集」重扫，或单集入库后自动收集）</div>
                    </template>
                    <!-- 电影/非剧集：按类型分段（v4.3.18: 与剧集同款两栏卡片 —— 左列左对齐 / 右列贴右对齐） -->
                    <template v-else>
                    <div v-for="grp in summaryGroups" :key="grp.type" class="epl-cast-section">
                      <div class="epl-cast-head">
                        <div class="epl-cast-title">
                          <v-icon size="18" color="primary">{{ grp.type === 'Director' ? 'mdi-video-outline' : grp.type === 'Writer' ? 'mdi-pencil-outline' : 'mdi-account' }}</v-icon>
                          {{ grp.label }}
                          <span class="epl-grp-count">{{ grp.list.length }}</span>
                        </div>
                      </div>
                      <div class="epl-actor-flow epl-actor-grid2">
                        <div v-for="row in grp.list" :key="grp.type + '\u0001' + row.name_before + '\u0001' + row.role_before" class="epl-actor-chip">
                          <div class="epl-chip-col">
                            <span class="epl-chip-name">{{ row.name_after || row.name_before || '—' }}</span>
                            <span v-if="row.role_before || row.role_after" class="epl-chip-role">饰 {{ row.role_after || row.role_before }}</span>
                          </div>
                          <v-btn icon="mdi-pencil" size="x-small" variant="text" class="epl-chip-edit" title="编辑译文（人名=全库统一；角色=仅这一条）" @click="openMovieEdit(row)"></v-btn>
                        </div>
                      </div>
                    </div>
                    <div class="text-caption" style="opacity:.6">点铅笔编辑译文（人名 = 全库统一，可选同步 Emby；角色 = 仅这一条）；点「写入」把当前条目已翻译名单写入文件（第一排再写入服务器）。</div>
                    </template>
                  </template>
                </template>
              </div>
            </template>

            <v-dialog v-model="editDlgOpen" max-width="480" :width="isNarrow ? '94vw' : undefined" scrollable>
              <v-card class="epl-edit-dlg" :style="isNarrow ? 'height: 92vh' : ''">
                <v-card-title>编辑译文</v-card-title>
                <v-card-text>
                  <!-- v4.6.70：任务期间打开编辑仍可查看，但保存被锁定（避免「编辑半天才被告知不能保存」） -->
                  <v-alert v-if="dataOpBlocked" type="warning" variant="tonal" density="compact" class="mb-2">
                    任务已启动（{{ guard.reason.value }}），编辑暂时锁定：可查看，保存按钮已禁用。
                  </v-alert>
                  <!-- ── 人名区（第一排）：默认只改当前人物身份，全库同名需主动选择 ── -->
                  <div class="epl-zone-head">人名（第一排）<span class="epl-zone-tag">默认只改当前身份</span></div>
                  <div class="epl-edit-row">
                    <span class="epl-edit-label">原文</span>
                    <span class="epl-edit-orig epl-readonly-box">{{ editDlgForm.name_before }}</span>
                  </div>
                  <v-text-field v-model="editDlgForm.name_after" label="人名译名" density="compact" variant="outlined"
                                hide-details class="mb-2"></v-text-field>
                  <div class="epl-edit-row">
                    <span class="epl-edit-label">范围</span>
                    <v-btn-toggle v-model="editDlgNameScope" density="compact" variant="tonal" mandatory>
                      <v-btn value="single" size="small" color="primary">仅这一条</v-btn>
                      <v-btn value="series" size="small" color="primary">该作品内同名</v-btn>
                      <v-btn value="library" size="small" color="error">全库同名</v-btn>
                    </v-btn-toggle>
                  </div>
                  <div class="epl-cast-hint mb-1">
                    <span v-if="editDlgNameScope === 'library'" class="epl-lock-chip" style="background:#b00020;color:#fff">全库同名 · 可能误改不同真人</span>
                    <span v-else class="epl-lock-chip">仅改所选范围 · 不动其它作品</span>
                    <span v-if="editDlgOcc.count">　全库同名共 {{ editDlgOcc.count }} 处 · {{ editDlgOcc.series.length }} 部作品</span>
                  </div>
                  <v-alert v-if="editDlgNameScope === 'library'" type="error" variant="tonal" density="compact" class="mb-1">
                    全库同名会修改所有同名人物，可能包含不同真人。请优先使用「仅这一条 / 该作品内同名」。
                  </v-alert>
                  <div class="epl-cast-hint mb-2">{{ nameScopeHint() }}</div>
                  <v-checkbox v-if="editDlgNameChanged" v-model="editDlgSyncEmby" density="compact" hide-details
                              color="primary" class="mb-3"
                              label="同步到 Emby（改 Emby 演员名，全局生效；默认不改）"></v-checkbox>
                  <div v-else class="mb-3"></div>

                  <!-- ── 角色区（第二排）：可精确到某集 ── -->
                  <template v-if="editDlgForm.role_before">
                    <v-divider class="mb-3" style="opacity:.25"></v-divider>
                    <div class="epl-zone-head">角色（第二排）<span class="epl-zone-tag">可精确到某集</span></div>
                    <div class="epl-edit-row">
                      <span class="epl-edit-label">原文</span>
                      <span class="epl-edit-orig epl-readonly-box">{{ editDlgForm.role_before }}</span>
                    </div>
                    <v-text-field v-model="editDlgForm.role_after" label="角色译名" density="compact"
                                  variant="outlined" hide-details class="mb-2"></v-text-field>
                    <div class="epl-edit-row">
                      <span class="epl-edit-label">范围</span>
                      <span v-if="editDlgForm.role_level === 'movie'" class="epl-edit-orig">仅这一条（电影只有这一条记录）</span>
                      <v-btn-toggle v-else v-model="editDlgRoleScope" density="compact" variant="tonal" color="primary" mandatory>
                        <template v-if="editDlgForm.role_level === 'ep'">
                          <v-btn value="single" size="small">仅这一集</v-btn>
                          <v-btn value="season" size="small">这一季</v-btn>
                          <v-btn value="series" size="small">这个剧</v-btn>
                        </template>
                        <template v-else>
                          <v-btn value="tv" size="small">仅剧级名单</v-btn>
                          <v-btn value="series" size="small">这个剧（含各集）</v-btn>
                        </template>
                      </v-btn-toggle>
                    </div>
                    <div class="epl-cast-hint">{{ roleScopeHint() }}</div>
                  </template>
                </v-card-text>
                <v-card-actions>
                  <v-tooltip text="清除该剧的「第二排角色跨集复用」记忆（删除/恢复/清库都不会清它）" location="top">
                    <template #activator="{ props: tp }">
                      <v-btn v-bind="tp" size="small" variant="text" color="error"
                             :loading="roleMemBusy" :disabled="dataOpBlocked" @click="clearRoleMemory">
                        <v-icon start size="16">mdi-brain</v-icon>清除该剧角色记忆
                      </v-btn>
                    </template>
                  </v-tooltip>
                  <v-spacer></v-spacer>
                  <v-btn variant="text" @click="editDlgOpen = false">取消</v-btn>
                  <v-tooltip :text="dataOpBlocked ? dataOpBlockedHint : '保存修改'" location="top">
                    <template #activator="{ props: tp }">
                      <v-btn v-bind="tp" color="primary" variant="flat" :loading="editDlgSaving" :disabled="dataOpBlocked" @click="saveEditDialog">保存</v-btn>
                    </template>
                  </v-tooltip>
                </v-card-actions>
              </v-card>
            </v-dialog>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="txDlg" max-width="480">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon start size="18">mdi-translate</v-icon>{{ txMode === 'item' ? '重新翻译（仅当前条目）' : '批量翻译' }}
        </v-card-title>
        <v-card-text>
          <v-alert v-if="txMode === 'item'" type="warning" variant="tonal" density="compact" style="font-size:12px" class="mb-2">
            仅重翻《{{ selected?.title || selected?.item_id }}》这一条，不会扫描或翻译其它条目。
          </v-alert>
          <div class="epl-tx-label">翻译范围</div>
          <v-radio-group v-model="txScope" density="compact" hide-details class="mb-2">
            <v-radio value="default" label="使用设置默认"></v-radio>
            <v-radio value="person" label="只翻第一排人物姓名"></v-radio>
            <v-radio value="role" label="只翻第二排角色"></v-radio>
            <v-radio value="both" label="两排都翻"></v-radio>
          </v-radio-group>
          <v-alert type="info" variant="tonal" density="compact" style="font-size:12px" class="mb-2">
            本次只决定「翻哪一排」，属于一次性任务、不改设置页长期配置；<b>「翻哪些类型 + 每个人翻几个」由设置页「翻译范围」决定</b>，已计入下方预估。
          </v-alert>
          <div class="epl-tx-preview">
            <div class="epl-tx-preview-row" :class="{ 'epl-tx-off': !txEstimate.wantP }">
              <span>第一排（人物姓名）</span>
              <span class="epl-tx-num">{{ txPreview.loading ? '…' : `待翻 ${txEstimate.names} 个 / 范围内 ${txEstimate.namesScope} 个` }}</span>
            </div>
            <div class="epl-tx-preview-row" :class="{ 'epl-tx-off': !txEstimate.wantR }">
              <span>第二排（角色名）</span>
              <span class="epl-tx-num">{{ txPreview.loading ? '…' : `待翻 ${txEstimate.roles} 个 / 范围内 ${txEstimate.rolesScope} 个` }}</span>
            </div>
          </div>
          <div v-if="!txPreview.loading && txEstimate.pending === 0 && txEstimate.scope === 0" class="epl-tx-current" style="color:#ffb74d; white-space:normal; line-height:1.5">
            范围内 0 条 —— 可能是：① 该排总开关没开；② <b>类型开关没开</b>（例如只填了「客串」的人数、却没打开「客串」开关）；③ 被人数上限挡在外面；④ 库里还没有该范围的记录。请到设置页「翻译范围」确认。
          </div>
          <div v-else-if="!txPreview.loading && txEstimate.pending === 0" class="epl-tx-current" style="color:#81c784">
            范围内 {{ txEstimate.scope }} 条：已翻完 / 原文已是中文，无需翻译。
          </div>
          <div v-else class="epl-tx-current">点「有任务 · 待翻译」徽章可看具体是哪些条目/词条。</div>
          <div class="epl-tx-current">当前选择：{{ txScopeLabel }}</div>
        </v-card-text>
        <v-card-actions>
          <v-btn variant="text" size="small" :loading="txPreview.loading" @click="loadTxPreview">
            <v-icon start size="16">mdi-refresh</v-icon>刷新预估
          </v-btn>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="txDlg = false">取消</v-btn>
          <v-btn color="primary" variant="flat" :loading="txBusy" @click="confirmTranslate">{{ txMode === 'item' ? '开始重翻' : '开始翻译' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="pendingDlg" max-width="640">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon start size="18">mdi-format-list-checks</v-icon>待翻译明细
          <v-spacer></v-spacer>
          <v-btn icon size="small" variant="text" @click="pendingDlg = false"><v-icon size="18">mdi-close</v-icon></v-btn>
        </v-card-title>
        <v-card-text>
          <v-progress-linear v-if="pendingBusy" indeterminate color="primary" height="3"></v-progress-linear>
          <div class="text-caption" style="opacity:.75; margin-bottom:8px">
            按当前「翻译范围」统计 —— 待翻：第一排 {{ pendingData.names_pending }} · 第二排 {{ pendingData.roles_pending }}；
            符合范围：第一排 {{ pendingData.names_scope }} · 第二排 {{ pendingData.roles_scope }}；{{ pendingData.items_total }} 个条目
          </div>
          <div class="epl-pend-scroll">
            <div v-if="!pendingBusy && !pendingData.items.length" class="epl-empty" style="padding:18px 0">
              没有待翻译条目 —— 要么都翻完了，要么被「类型开关 / 人数上限」挡在外面（去设置页「翻译范围」检查）
            </div>
            <div v-for="it in pendingData.items" :key="it.item_id + ':' + it.server_id" class="epl-pend-item">
              <div class="epl-pend-title">《{{ it.title }}》</div>
              <div v-if="it.names_total" class="epl-pend-line">
                <span class="epl-pend-tag">第一排</span>
                <span class="epl-pend-term" v-for="(n, i) in it.names" :key="'n' + i">{{ n }}</span>
                <span v-if="it.names_total > it.names.length" class="epl-pend-more">等共 {{ it.names_total }} 个</span>
              </div>
              <div v-if="it.roles_total" class="epl-pend-line">
                <span class="epl-pend-tag">第二排</span>
                <span class="epl-pend-term" v-for="(r, i) in it.roles" :key="'r' + i">{{ r }}</span>
                <span v-if="it.roles_total > it.roles.length" class="epl-pend-more">等共 {{ it.roles_total }} 个</span>
              </div>
            </div>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="pendingDlg = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDlg :state="cState" :on-ok="cOk" :on-cancel="cCancel" />
    <!-- v4.6.70：统一「任务进行中」拦截弹窗（修改型操作共用；不提供强行继续） -->
    <TaskGuardDlg v-model="guard.dlg.value" :reason="guard.reason.value"
                  :state="guard.stateLabel.value"
                  :action="guard.pendingLabel.value" @view-task="emit('view-task')" />
  </div>
</template>

<style scoped>
.epl-lib { width: 100%; }
.epl-topbar { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; padding-right: 52px; }
.epl-total { opacity: 0.75; }
.epl-pending-chip { cursor: pointer; }
.epl-topbar-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.epl-card-bg { background: rgba(255,255,255,0.05) !important; border: 1px solid rgba(255,255,255,0.08) !important; }
.epl-thumb { border-radius: 3px; overflow: hidden; flex-shrink: 0; object-fit: cover !important; }
.epl-thumb-placeholder { margin: 0 6px; }
.epl-grp-title { font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
.epl-grp-count { font-size: 12px; opacity: .6; background: rgba(128,128,128,.18); border-radius: 10px; padding: 0 8px; flex-shrink: 0; }
.epl-person { display: flex; align-items: center; }
.epl-person-name { font-size: 14px; font-weight: 600; display: flex; align-items: center; }
.epl-person-role { font-size: 12px; opacity: .75; margin-top: 1px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.epl-src-tags { font-size: 11px; opacity: .55; background: rgba(128,128,128,.14); border-radius: 8px; padding: 0 6px; }
.epl-same { color: inherit; }
.epl-dim { opacity: .55; }
.epl-list-card, .epl-detail-card { height: 640px; overflow: hidden; }
.epl-flex-card { display: flex; flex-direction: column; }
.epl-col-body { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; }
.epl-sidebar { border-top: 1px solid rgba(255,255,255,.06); background: rgba(255,255,255,.03); flex-shrink: 0; }
.epl-sidebar-top { border-top: none; border-bottom: 1px solid rgba(255,255,255,.06); }
.epl-sidebar-search { flex: 1; min-width: 120px; }
.epl-search-title { font-size: 13px; opacity: .85; display: flex; align-items: center; }
.epl-detail-head { border-bottom: 1px solid rgba(255,255,255,.06); background: rgba(255,255,255,.02); }
.epl-group-item { cursor: pointer; }
.epl-group-name { font-size: 13px; font-weight: 600; }
.epl-group-count { font-size: 12px; opacity: 0.6; background: rgba(128,128,128,0.18); border-radius: 10px; padding: 0 8px; }
.epl-item { cursor: pointer; }
.epl-item-dead { background: rgba(var(--v-theme-error), .10) !important; border-left: 3px solid rgb(var(--v-theme-error)); }
.epl-item-dead .epl-item-name { color: rgb(var(--v-theme-error)); }
.epl-item-partdead { background: rgba(var(--v-theme-warning), .08) !important; border-left: 3px solid rgb(var(--v-theme-warning)); }
.epl-item-partdead .epl-item-name { color: rgb(var(--v-theme-warning)); }
.epl-item-name { font-size: 14px; font-weight: 500; white-space: normal; word-break: break-word; line-height: 1.3; }
.epl-item-meta { font-size: 12px; opacity: 0.7; }
.epl-detail-title { font-size: 17px; font-weight: 600; white-space: normal; word-break: break-word; line-height: 1.3; }
.epl-poster-wrap { width: 64px; height: 92px; flex-shrink: 0 !important; background: rgba(128,128,128,.12); border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center; }
.epl-poster { border-radius: 4px; object-fit: cover !important; object-position: center top; }
.epl-detail-meta { font-size: 12px; opacity: 0.7; margin-top: 2px; }
.epl-edit-btn { opacity: .55; transition: opacity .15s; margin-left: 4px; }
.epl-person:hover .epl-edit-btn, .epl-person-search-item:hover .epl-edit-btn,
.epl-occ-row:hover .epl-edit-btn { opacity: 1; }
.epl-empty { font-size: 13px; opacity: 0.6; text-align: center; }
.epl-person-search-item { cursor: default; padding-right: 8px; }
.epl-person-search-hint { opacity: .55; padding: 8px 12px 10px; border-top: 1px solid rgba(255,255,255,.06); }
.epl-occ-list { padding: 0 8px 6px 42px; }
.epl-occ-row { display: flex; align-items: center; gap: 4px; font-size: 12px; opacity: .88; padding: 1px 0; }
.epl-occ-label { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.epl-occ-toggle { cursor: pointer; }
@media (max-width: 600px) {
  .epl-poster-wrap { width: 52px; height: 74px; }
  .epl-detail-title { font-size: 15px; }
  .epl-topbar .v-text-field { max-width: 100% !important; }
  .epl-topbar { gap: 6px; }
  .epl-topbar .epl-total { display: none; }
  .epl-pending-prefix { display: none; }
}
.epl-cast-section { margin-bottom: 14px; }
.epl-cast-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.epl-cast-title { font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 6px; }
.epl-cast-hint { font-size: 12px; opacity: .6; font-weight: 400; }
.epl-actor-flow { display: flex; flex-wrap: wrap; gap: 6px 8px; }
.epl-actor-chip {
  display: inline-flex; align-items: center; gap: 2px; padding: 4px 6px 4px 10px;
  background: rgba(128,128,128,.16); border: 1px solid rgba(128,128,128,.22);
  border-radius: 10px;
}
.epl-chip-col { display: flex; flex-direction: column; align-items: flex-start; min-width: 0; }
.epl-chip-name { font-weight: 500; font-size: 13px; line-height: 1.35; }
.epl-chip-role { opacity: .7; font-size: 12px; line-height: 1.35; }
.epl-chip-edit { opacity: .4; flex-shrink: 0; }
.epl-actor-chip:hover .epl-chip-edit { opacity: 1; }
.epl-actor-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 10px; }
.epl-actor-grid2 .epl-actor-chip { width: 100%; }
.epl-actor-grid2 .epl-actor-chip:nth-child(even) { justify-content: flex-end; }
.epl-actor-grid2 .epl-actor-chip:nth-child(even) .epl-chip-col { align-items: flex-end; text-align: right; }
/* v4.6.97：分集/主演员「按类型分段」的段标题（与电影页 .epl-cast-title 同款观感，更紧凑） */
.epl-type-block { margin-top: 8px; }
.epl-type-block:first-child { margin-top: 0; }
.epl-type-sub { display: flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700;
                opacity: .85; margin-bottom: 5px; }
.epl-type-sub .epl-grp-count { opacity: .6; font-weight: 400; }
.epl-ep-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.epl-ep-toolbar-left { display: flex; align-items: center; gap: 6px; flex: 1 1 auto; min-width: 0; font-size: 14px; font-weight: 700; }
.epl-ep-toolbar-right { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.epl-ep-panels :deep(.v-expansion-panel-title) { min-height: 42px; padding: 6px 12px; font-size: 13px; }
.epl-ep-panels :deep(.v-expansion-panel-text__wrapper) { padding: 8px 12px 12px; }
.epl-ep-panels :deep(.v-expansion-panel) { background: rgba(255,255,255,.035) !important; }
.epl-ep-panels :deep(.v-expansion-panel-title) { background: rgba(255,255,255,.045) !important; }
.epl-ep-panels :deep(.v-expansion-panel--active > .v-expansion-panel-title) { background: rgba(255,255,255,.085) !important; }
.epl-ep-panels :deep(.v-expansion-panel-text) { background: rgba(255,255,255,.02) !important; }
/* v4.6.75（规范 §二-1 / §十一-3/4）：季选择器限高 + 内部滚动 ——
   季数多时不再无限换行把剧集列表顶出屏幕（移动端 S1-S20 也不撑长）。 */
.epl-season-tabs {
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;
  max-height: 92px; overflow-y: auto; align-content: flex-start;
  padding-right: 2px;
}
.epl-season-tabs::-webkit-scrollbar { width: 8px; }
.epl-season-tabs::-webkit-scrollbar-thumb { background: rgba(128, 128, 128, .45); border-radius: 4px; }
.epl-season-tab {
  display: inline-flex; align-items: center; gap: 4px; cursor: pointer;
  background: rgba(128,128,128,.14); border: 1px solid rgba(128,128,128,.22);
  color: inherit; opacity: .82; border-radius: 999px; padding: 3px 10px;
  font-size: 13px; font-weight: 500; line-height: 1.5;
}
.epl-season-tab:hover { opacity: 1; }
.epl-season-tab.is-active {
  border-color: rgb(var(--v-theme-primary)); color: rgb(var(--v-theme-primary));
  background: transparent; font-weight: 600; opacity: 1;
}
.epl-season-tab-count { font-size: 11px; opacity: .72; }
.epl-season-tab.is-dead { border-color: rgb(var(--v-theme-error)); color: rgb(var(--v-theme-error)); }
.epl-season-tab.is-dead .epl-season-tab-count { color: rgb(var(--v-theme-error)); opacity: .85; }
.epl-ep-dead { box-shadow: inset 3px 0 0 rgb(var(--v-theme-error)); border-radius: 4px; }
.epl-ep-dead :deep(.v-expansion-panel-title) { color: rgb(var(--v-theme-error)); }
.epl-ep-dead-tag { color: rgb(var(--v-theme-error)); font-weight: 600; font-size: 12px; margin-left: 4px; }
.epl-ep-title { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.epl-load-sentinel { display: flex; align-items: center; justify-content: center; min-height: 44px; padding: 10px 0; }
.epl-edit-row { display: flex; gap: 8px; align-items: baseline; margin-bottom: 8px; font-size: 13px; }
.epl-edit-label { opacity: .65; flex: 0 0 48px; }
.epl-edit-orig { font-weight: 500; }
.epl-zone-head { font-size: 13px; font-weight: 700; margin: 2px 0 6px; display: flex; align-items: center; gap: 8px; }
.epl-zone-tag { font-size: 11px; font-weight: 400; opacity: .6; }
.epl-lock-chip { font-size: 11px; opacity: .85; background: rgba(128,128,128,.16); border: 1px solid rgba(128,128,128,.4); border-radius: 999px; padding: 1px 8px; }
@media (max-width: 600px) {
  .epl-ep-toolbar { flex-wrap: wrap; }
}
.epl-readonly-box {
  flex: 1 1 auto; min-width: 0; display: block;
  padding: 6px 10px; border: 1px solid rgba(255,255,255,.14); border-radius: 8px;
  background: rgba(255,255,255,.03); word-break: break-word;
}
.epl-edit-dlg :deep(.v-field) { border-radius: 8px; background: rgba(0,0,0,.20); }
.epl-edit-dlg :deep(.v-field__outline) { --v-field-border-opacity: .55; }
.epl-edit-dlg :deep(.v-field--focused .v-field__outline) { --v-field-border-opacity: 1; }
.epl-edit-dlg :deep(.v-field--focused) { box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), .22); }
.epl-tx-label { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
.epl-tx-preview { border: 1px solid rgba(128,128,128,0.2); border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; }
.epl-tx-preview-row { display: flex; align-items: center; justify-content: space-between; font-size: 13px; padding: 2px 0; }
.epl-tx-off { opacity: .45; }
.epl-pend-scroll { max-height: 56vh; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; }
.epl-pend-item { border-top: 1px solid rgba(128,128,128,.16); padding: 8px 0; }
.epl-pend-item:first-of-type { border-top: 0; }
.epl-pend-title { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.epl-pend-line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 3px; font-size: 12.5px; }
.epl-pend-tag { flex: 0 0 auto; opacity: .6; }
.epl-pend-term { background: rgba(128,128,128,.14); border: 1px solid rgba(128,128,128,.22); border-radius: 10px; padding: 1px 8px; }
.epl-pend-more { opacity: .6; }
.epl-tx-num { font-weight: 600; color: var(--v-primary-base); }
.epl-tx-current { font-size: 12px; opacity: .8; }
@media (max-width: 400px) {
  .epl-actor-grid2 { grid-template-columns: 1fr; gap: 6px; }
  .epl-actor-grid2 .epl-actor-chip:nth-child(even) { justify-content: flex-start; }
  .epl-actor-grid2 .epl-actor-chip:nth-child(even) .epl-chip-col { align-items: flex-start; text-align: left; }
  .epl-edit-row { flex-wrap: wrap; }
  .epl-edit-label { flex: 0 0 auto; }
}
</style>