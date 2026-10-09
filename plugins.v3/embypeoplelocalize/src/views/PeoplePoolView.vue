<script setup>
import { computed, inject, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import api from '../api/client.js'
import ConfirmDlg from '../components/ConfirmDlg.vue'
import TaskGuardDlg from '../components/TaskGuardDlg.vue'
import { useConfirm } from '../components/useConfirm.js'
import { useTaskGuard } from '../components/useTaskGuard.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action', 'view-task'])
const toast = inject('moviepilot:toast', null)

const { cState, askConfirm, cOk, cCancel } = useConfirm()
// v4.6.70：统一任务守卫（清池 / 重筛 / 池编辑 / 同步 / 批量翻译 / 重拉 / 导入 共用同一把锁）
const guard = useTaskGuard()

function notify(msg, type = 'error') {
  const t = toast; if (t && typeof t[type] === 'function') t[type](msg)
}

const TYPE_LABELS = { Actor: '演员', VoiceActor: '声优', Director: '导演', Writer: '编剧', Producer: '制片', GuestStar: '客串' }
// v4.6.79（人名池显示口径）：**演员类**身份（主演 Actor / 声优 VoiceActor / 客串 GuestStar）在显示层
// 统一合并为「演员」—— 「客串 / 声优」本质也是演戏，与「演员」并列只是噪声；只有导演 / 编剧 / 制片
// 等「特别身份」才单独显示。**仅改显示**：拉取类型 / 重筛 / 翻译类型开关仍用原始 Emby 类型，功能不变。
const ACTING_TYPES = ['Actor', 'VoiceActor', 'GuestStar']
const ACTING_LABEL = '演员'
const TYPE_FILTERS = [
  { value: '', title: '全部' },
  { value: 'Actor', title: '演员' },
  { value: 'Director', title: '导演' },
  { value: 'Writer', title: '编剧' },
  { value: 'Producer', title: '制片' },
  { value: 'GuestStar', title: '客串' },
]
const STATUS_FILTERS = [
  { value: '', title: '全部' },
  { value: 'pending', title: '待翻译' },
  { value: 'no_change', title: '无需操作' },
  { value: 'translated', title: '待同步' },
  { value: 'synced', title: '已同步' },
  { value: 'failed', title: '同步失败' },
]

const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(50)
const keyword = ref('')
const status = ref('')
const type = ref('')
const loading = ref(true)

const filterOpen = ref(false)
const filterRef = ref(null)
const selCount = computed(() => (status.value ? 1 : 0) + (type.value ? 1 : 0))

function onDocPointerDown(e) {
  if (!filterOpen.value) return
  const el = filterRef.value
  if (el && !el.contains(e.target)) filterOpen.value = false
}

const counts = ref({ total: 0, pending: 0, no_change: 0, translated: 0, synced: 0, failed: 0 })
const fetchState = ref({ running: false, total: 0, done: 0, current: '', added: 0, updated: 0, unchanged: 0, filtered: 0, failed: 0 })
const txState = ref({})
const poolTaskRunning = ref(false)
const pluginEnabled = computed(() => props.enabled !== false)
const pluginOffTitle = computed(() => (pluginEnabled.value ? '' : '插件未启用：请先在设置页打开「启用插件」'))
const txRunning = computed(() => !!txState.value.running)
const poolFetchDisabled = computed(() => !pluginEnabled.value || txRunning.value || poolTaskRunning.value)
const poolFetchTitle = computed(() => {
  if (!pluginEnabled.value) return '插件未启用：请先在设置页打开「启用插件」'
  if (txRunning.value) return 'AI 翻译进行中，暂不可拉取人名（翻译与拉取互斥），等翻译完成后再试'
  if (poolTaskRunning.value) return '人名池任务（拉取/同步）进行中，完成后可用'
  return ''
})
const poolSyncDisabled = computed(() => !pluginEnabled.value || poolTaskRunning.value)
const poolDataOpBlocked = computed(() => !pluginEnabled.value || txRunning.value || poolTaskRunning.value)
const poolDataOpBlockedHint = computed(() => {
  if (!pluginEnabled.value) return '插件未启用：请先在设置页打开「启用插件」'
  if (txRunning.value) return 'AI 翻译进行中，请先「终止」或等待完成后再操作（避免边翻译边清库）'
  if (poolTaskRunning.value) return '人名池任务（拉取/同步）进行中，请先「终止」或等待完成后再操作'
  return ''
})
const scope = ref('libraries')

// 出现清单（懒加载，只展示不编辑）
const occOpen = ref('')
const occLoading = ref(false)
const occRows = ref([])

const detailOpen = ref('')

// 弹窗
const editDlg = ref(false)
const editRow = ref(null)
const editZh = ref('')
const editSaved = ref(false)
const editSyncEmby = ref(false)
const transDlg = ref(false)
const transSync = ref(false)
const syncDlg = ref(false)
const fetchDlg = ref(false)
const busy = ref(false)
const refetchKey = ref('')   // 正在「重拉」的行 key（按钮 loading 用）

let timer = null

function parseJsonArray(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.trim()) {
    try {
      const a = JSON.parse(v)
      return Array.isArray(a) ? a : []
    } catch (e) { return [] }
  }
  return []
}

function typeList(row) {
  let arr = parseJsonArray(row?.person_types)
  if (!arr.length && row?.person_type) {
    arr = String(row.person_type).split(',').map(s => s.trim()).filter(Boolean)
  }
  const out = []
  let hasActing = false
  for (const x of arr) {
    // 演员类（主演 / 声优 / 客串）→ 合并为「演员」，只占一枚
    if (ACTING_TYPES.includes(x)) { hasActing = true; continue }
    const label = TYPE_LABELS[x] || x
    if (label && !out.includes(label)) out.push(label)
  }
  // 「演员」作为主要身份排在最前，特别身份（导演/编剧/制片…）按原顺序跟随
  return hasActing ? [ACTING_LABEL, ...out] : out
}

function typeText(row) {
  const arr = typeList(row)
  return arr.length ? arr.join(' / ') : '未分类'
}

function statusChip(r) {
  if (r.status === '待翻译') return { text: '待翻译', color: 'error', dot: '🔴' }
  if (r.status === '无需操作') return { text: '无需操作', color: 'success', dot: '🟩' }
  if (r.status === '待同步') return { text: '待同步', color: 'warning', dot: '🟡' }
  if (r.status === '同步失败') return { text: '同步失败', color: 'error', dot: '⚠️' }
  return { text: '已同步', color: 'success', dot: '🟢' }
}

function isChineseText(s) {
  // v4.6.80：与后端口径对齐 —— 含汉字且**无假名**即视为「已是中文」；
  // 空格不再作为排除条件（「角田 雄二郎」这类中文带空格的名字此前被判待翻译）。
  const t = String(s || '')
  if (!/[\u4e00-\u9fff]/.test(t)) return false
  return !/[\u3041-\u309f\u30a0-\u30ff]/.test(t)
}
function poolTargetName(r) {
  const orig = String(r?.name_original || '').trim()
  const zh = String(r?.name_zh || '').trim()
  if (zh && zh !== orig) return zh
  if (isChineseText(orig)) return orig
  return ''
}
// v4.6.94：译名列的显示文本 —— 只显示「第一排改过」的最终译名（AI 翻译/人工修改）。
// 没改过（name_zh 为空，或与原文相同）→ 返回空串，由调用方给占位：
//   · 原文已是中文 → 不再重复显示同一个名字（只显示原文名一处）
//   · 改过之后状态自然变成「待同步/已同步」，与没改过的行区分开
// 人工改错也能对照「原文名」列进行修正。
function zhText(r) {
  const orig = String(r?.name_original || '').trim()
  const zh = String(r?.name_zh || '').trim()
  if (!zh || zh === orig) return ''
  return zh
}
function recomputeRowStatus(r) {
  const orig = String(r?.name_original || '').trim()
  const cur = String(r?.name_current || '').trim()
  const target = poolTargetName(r)
  let translation
  if (target) translation = (String(r?.name_zh || '').trim() && String(r.name_zh).trim() !== orig) ? 'translated' : 'no_change'
  else translation = (r?.translation_status === 'failed') ? 'failed' : 'pending'
  let sync
  if (!target) sync = 'unknown'
  else if (cur && cur === target) sync = 'synced'
  else if (r?.sync_status === 'failed') sync = 'failed'
  // v4.6.93：原文已是中文 + Emby 当前名未知（扫描缓存行/无身份）→ 无同步可言（不报待同步）
  else if (!cur && translation === 'no_change') sync = 'unknown'
  else sync = 'pending'
  let ui
  if (translation === 'pending' || translation === 'failed') ui = '待翻译'
  else if (sync === 'failed') ui = '同步失败'
  else if (sync === 'pending') ui = '待同步'
  else if (translation === 'no_change') ui = '无需操作'
  else ui = '已同步'
  r.status = ui
  r.translation_status = translation
  r.sync_status = sync
}

async function loadList(silent = false) {
  if (!silent) loading.value = true
  try {
    const d = await api.get(props.api, '/pool/list', {
      keyword: keyword.value, status: status.value, type: type.value,
      page: page.value, size: size.value,
    })
    rows.value = d.items || []
    total.value = d.total || 0
  } catch (e) {
    if (!silent) notify(e.message, 'error')
  }
  loading.value = false
}

async function loadStatus() {
  try {
    const d = await api.get(props.api, '/pool/status')
    counts.value = d.counts || counts.value
    fetchState.value = d.fetch || {}
    txState.value = d.tx || {}
    poolTaskRunning.value = !!d.running
    if (d.scope) scope.value = d.scope
    // v4.6.70：同步统一任务守卫（/pool/status 已附 is_running + tasks 快照）
    guard.loadStatus(d)
  } catch (e) { /* 静默 */ }
}

const pulling = computed(() => !!fetchState.value.running)
const fetchPercent = computed(() => {
  const t = Number(fetchState.value.total || 0)
  const dn = Number(fetchState.value.done || 0)
  if (!t) return 0
  return Math.min(100, Math.round(dn / t * 100))
})

watch(pulling, (now, old) => {
  if (old && !now) { loadList(true); loadStatus() }
})

async function refreshAll(silent = false) {
  await Promise.all([loadList(silent), loadStatus()])
}

function onSearch() {
  page.value = 1
  loadList()
}

function resetFilter() {
  keyword.value = ''
  status.value = ''
  type.value = ''
  page.value = 1
  loadList()
}

function changeStatus(v) {
  status.value = v
  page.value = 1
  loadList()
}

function changeType(v) {
  type.value = v
  page.value = 1
  loadList()
}

const paused = computed(() => !!fetchState.value.paused)

async function pauseFetch() {
  try {
    const d = await api.post(props.api, '/task/pause', { target: 'pool' })
    notify(d?.message || '已暂停', 'info')
    loadStatus()
  } catch (e) { notify(e.message, 'error') }
}

async function resumeFetch() {
  try {
    const d = await api.post(props.api, '/task/resume', { target: 'pool' })
    notify(d?.message || '已继续', 'success')
    loadStatus()
  } catch (e) { notify(e.message, 'error') }
}

const txPaused = computed(() => !!txState.value.user_paused)

async function pauseTranslate() {
  try {
    const d = await api.post(props.api, '/task/pause', { target: 'translate' })
    notify(d?.message || '翻译已暂停', 'info')
    loadStatus()
  } catch (e) { notify(e.message, 'error') }
}

async function resumeTranslate() {
  try {
    const d = await api.post(props.api, '/task/resume', { target: 'translate' })
    notify(d?.message || '已继续翻译', 'success')
    loadStatus()
  } catch (e) { notify(e.message, 'error') }
}

const poolImportInput = ref(null)
const poolBusy = ref('')

async function exportPool() {
  poolBusy.value = 'export'
  try {
    const r = await api.get(props.api, '/pool/export')
    const rows = Array.isArray(r) ? r : []
    if (!rows.length) { notify('人名池为空，暂无可导出数据', 'info'); return }
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `embypeople_pool_${Date.now()}.json`; a.click()
    URL.revokeObjectURL(url)
    notify(`已导出 ${rows.length} 人`, 'success')
  } catch (e) { notify((e && e.message) || '导出失败', 'error') } finally { poolBusy.value = '' }
}

function pickPoolImport() { poolImportInput.value?.click() }

// UI-007：导入前先按文件大小拦一道，避免把超大备份整体读进内存（会冻结浏览器）。
// 超限直接拒绝并说明原因；解析后再限制记录数，防止超大数组把请求体撑爆。
const MAX_IMPORT_BYTES = 30 * 1024 * 1024   // 30MB
const MAX_IMPORT_ROWS = 50000

function fmtSize(n) {
  const mb = Number(n || 0) / 1024 / 1024
  return `${mb.toFixed(1)}MB`
}

async function onPoolImportPick(e) {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  if (!guard.check('导入人名池')) { e.target.value = ''; return }   // v4.6.70：统一守卫
  if (Number(f.size || 0) > MAX_IMPORT_BYTES) {
    notify(`文件过大（${fmtSize(f.size)}，上限 ${fmtSize(MAX_IMPORT_BYTES)}）：请拆分后再导入，或改用服务器端导入`, 'error')
    e.target.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = async () => {
    poolBusy.value = 'import'
    try {
      let rows
      try { rows = JSON.parse(reader.result) } catch (_) { throw new Error('文件不是有效 JSON') }
      if (!Array.isArray(rows)) rows = rows?.rows || rows?.data || rows?.records || []
      if (!Array.isArray(rows) || !rows.length) { notify('文件里没有可导入的数据', 'error'); return }
      if (rows.length > MAX_IMPORT_ROWS) {
        notify(`记录数过多（${rows.length} 条，上限 ${MAX_IMPORT_ROWS} 条）：请拆分后再导入`, 'error')
        return
      }
      const r = await api.post(props.api, '/pool/import', { rows })
      notify(r?.message || '导入完成', 'success')
      refreshAll(true)
    } catch (err) { notify((err && err.message) || '导入失败', 'error') } finally { poolBusy.value = ''; e.target.value = '' }
  }
  reader.readAsText(f)
}

async function clearPool() {
  if (!guard.check('清空人名池')) return   // v4.6.70：统一守卫
  if (!await askConfirm({
    title: '清除人名池',
    text: `确认清除人名池全部 ${counts.value.total} 人？`,
    detail: '将删除人名池里的全部条目（原文名 / 译名 / 来源标记）。此操作不可恢复，建议先「导出」备份。',
    okText: '继续',
    color: 'error',
  })) return
  if (!await askConfirm({
    title: '再次确认',
    text: '确定要清空整个人名池吗？',
    detail: '⚠️ 人工修正的译名也会一并删除，且无法恢复。清除后可重新「拉取人名」→「批量翻译」重建。',
    okText: '确认清除',
    color: 'error',
  })) return
  poolBusy.value = 'clear'
  try {
    const r = await api.post(props.api, '/pool/clear')
    notify(r?.message || '人名池已清空', 'success')
    refreshAll(true)
  } catch (e) { notify((e && e.message) || '清除失败', 'error') } finally { poolBusy.value = '' }
}

// ── 出现清单 ──
function occTitle(o) {
  return o.series_name || o.title || o.item_id || ''
}

const occUnique = computed(() => {
  const map = new Map()
  for (const o of occRows.value) {
    const t = occTitle(o)
    const hit = map.get(t)
    if (hit) { hit.count++; if (o.deleted_at) hit.deleted = true }
    else map.set(t, { title: t, count: 1, deleted: !!o.deleted_at })
  }
  return Array.from(map.values())
})

// UI-006：key 必须带 server_id 维度，否则两个服务器同名 Person ID/name 的
// 展开/详情状态会互相串（同一 key 命中）。source scope = server_id + 人物标识。
function personKey(r) {
  const sid = String(r?.server_id || '')
  const pid = r?.emby_person_id || r?.name_original || r?.id || ''
  return `${sid}:${pid}`
}

function rowKey(r) { return personKey(r) }

function canSync(r) {
  const t = poolTargetName(r)
  if (!t || t === (r.name_current || '')) return false
  // v4.6.93：原文已是中文 + Emby 当前名未知（扫描缓存行）→ 无同步可言
  // （要补 Emby 身份请点「重拉」或跑「拉取人名」，拉到当前名后若确有差异会再显示「同步」）
  if (!r?.name_current && isChineseText(r?.name_original)) return false
  return true
}

function toggleDetail(r) {
  const k = rowKey(r)
  detailOpen.value = detailOpen.value === k ? '' : k
}

async function toggleOcc(r) {
  const key = personKey(r)
  if (occOpen.value === key) { occOpen.value = ''; return }
  occOpen.value = key
  occRows.value = []
  occLoading.value = true
  try {
    const d = await api.get(props.api, '/pool/occurrences', {
      name_before: r.name_original, server_id: r.server_id, limit: 500,
    })
    occRows.value = Array.isArray(d) ? d : (d.items || [])
  } catch (e) {
    notify(e.message, 'error')
  }
  occLoading.value = false
}

function occCount(r) {
  const key = personKey(r)
  if (occOpen.value !== key) return ''
  return occLoading.value ? '查询中…' : `${occRows.value.length} 处`
}

// ── 单条编辑 ──
function openEdit(r) {
  editRow.value = r
  editZh.value = r.name_zh || ''
  editSaved.value = false
  editSyncEmby.value = false
  editDlg.value = true
}

async function saveEdit() {
  if (!editRow.value) return
  if (!guard.check('保存人名池译名')) return   // v4.6.70：统一守卫
  busy.value = true
  try {
    const r = editRow.value
    await api.post(props.api, '/pool/update', {
      server_id: r.server_id, emby_person_id: r.emby_person_id,
      name_original: r.name_original, name_zh: editZh.value,
    })
    r.name_zh = editZh.value
    r.sync_status = ''
    r.sync_error = ''
    recomputeRowStatus(r)
    editSaved.value = true
    notify('已保存池译文（未同步 Emby）', 'success')
    loadStatus()
  } catch (e) {
    notify(e.message, 'error')
  }
  busy.value = false
}

async function syncOne() {
  if (!editRow.value) return
  if (!guard.check('同步该人名到 Emby')) return   // v4.6.70：统一守卫
  busy.value = true
  try {
    const r = editRow.value
    if (!editSaved.value && (r.name_zh || '') !== (editZh.value || '')) {
      await api.post(props.api, '/pool/update', {
        server_id: r.server_id, emby_person_id: r.emby_person_id,
        name_original: r.name_original, name_zh: editZh.value,
      })
      r.name_zh = editZh.value
      editSaved.value = true
    }
    const d = await api.post(props.api, '/pool/sync_one', {
      server_id: r.server_id, emby_person_id: r.emby_person_id,
      name_original: r.name_original, name_zh: editZh.value, name_current: r.name_current,
    })
    notify(d?.message || '已同步到 Emby', 'success')
    editDlg.value = false
    loadList(true); loadStatus()
  } catch (e) {
    notify(e.message, 'error')
  }
  busy.value = false
}

// ── 单条重新拉取（从 Emby 重取该人事实：当前名/类型，legacy 无 ID 行顺带补 Person ID）──
async function refetchOne(r) {
  if (!r || refetchKey.value) return
  if (!guard.check('重拉该人名')) return   // v4.6.70：统一守卫
  refetchKey.value = personKey(r)
  try {
    const d = await api.post(props.api, '/pool/refetch_one', {
      server_id: r.server_id, emby_person_id: r.emby_person_id, name_original: r.name_original,
    })
    notify(d?.message || '已重新拉取', 'success')
    loadList(true); loadStatus()
  } catch (e) {
    notify(e.message, 'error')
  }
  refetchKey.value = ''
}

// ── 拉取 ──
function openFetch() {
  fetchDlg.value = true
}

async function doFetch() {
  if (!guard.check('拉取人名')) return   // v4.6.70：统一守卫
  busy.value = true
  try {
    const d = await api.post(props.api, '/pool/fetch', { scope: scope.value })
    notify(d?.message || '拉取已启动', 'success')
    fetchDlg.value = false
    fetchState.value = { running: true, total: 0, done: 0, current: '准备中…' }
    setTimeout(loadStatus, 600)
  } catch (e) {
    notify(e.message, 'error')
  }
  busy.value = false
}

async function doRescreen() {
  if (!guard.check('按当前设置重筛池')) return   // v4.6.70：统一守卫
  busy.value = true
  try {
    const d = await api.post(props.api, '/pool/rescreen', {})
    notify(d?.message || '已重筛', 'success')
    refreshAll(true)
  } catch (e) {
    notify(e.message, 'error')
  }
  busy.value = false
}

// ── 批量翻译 / 同步 ──
function openTranslate() {
  if (!counts.value.pending) { notify('没有待翻译的人名', 'info'); return }
  transSync.value = false
  transDlg.value = true
}

async function doTranslate() {
  if (!guard.check('人名池批量翻译')) return   // v4.6.70：统一守卫
  busy.value = true
  try {
    const d = await api.post(props.api, '/pool/translate', { sync_after: transSync.value })
    notify(d?.message || '已交后台翻译', 'success')
    transDlg.value = false
    loadStatus()
  } catch (e) {
    notify(e.message, 'error')
  }
  busy.value = false
}

function openSync() {
  if (!counts.value.translated) { notify('没有待同步的人名', 'info'); return }
  syncDlg.value = true
}

async function doSync() {
  if (!guard.check('人名池批量同步')) return   // v4.6.70：统一守卫
  busy.value = true
  try {
    const d = await api.post(props.api, '/pool/sync', {})
    notify(d?.message || '批量同步已启动', 'success')
    syncDlg.value = false
    loadStatus()
  } catch (e) {
    notify(e.message, 'error')
  }
  busy.value = false
}

function startPoll() {
  if (timer) return
  timer = setInterval(() => { loadStatus(); if (pulling.value) loadList(true) }, 3000)
}
function stopPoll() {
  if (timer) { clearInterval(timer); timer = null }
}
onMounted(() => {
  refreshAll()
  startPoll()
  document.addEventListener('pointerdown', onDocPointerDown)
})

onActivated(() => { refreshAll(true); startPoll() })

watch(() => props.refreshKey, () => { refreshAll(true) })

onDeactivated(stopPoll)

onBeforeUnmount(() => {
  stopPoll()
  document.removeEventListener('pointerdown', onDocPointerDown)
})
</script>

<template>
  <div class="epl-pool">
    <!-- 顶部：统计 + 操作（v4.4.7：去掉「人名池」标题与图标，整体左移） -->
    <div class="epl-pool-head">
      <span class="epl-pool-sub">共 {{ counts.total }} 人 · 待翻 {{ counts.pending }} · 待同步 {{ counts.translated }} · 已同步 {{ counts.synced }}（其中原文已是中文 {{ counts.no_change }}）</span>
      <div class="epl-pool-acts">
        <v-btn size="small" variant="flat" color="info" prepend-icon="mdi-cloud-download-outline" class="epl-act-fetch"
               :disabled="poolFetchDisabled" :title="poolFetchTitle"
               @click="openFetch">拉取人名</v-btn>
        <v-btn size="small" variant="flat" color="primary" prepend-icon="mdi-translate"
               :disabled="!pluginEnabled" :title="pluginOffTitle"
               @click="openTranslate">批量翻译</v-btn>
        <v-btn size="small" variant="flat" color="success" prepend-icon="mdi-sync"
               :disabled="poolSyncDisabled" :title="poolFetchTitle || pluginOffTitle"
               @click="openSync">批量同步</v-btn>
        <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-sweep-outline" :disabled="poolDataOpBlocked" :title="poolDataOpBlockedHint" :loading="poolBusy === 'clear'" @click="clearPool">清除人名池</v-btn>
        <v-btn size="small" variant="tonal" prepend-icon="mdi-export-variant" :disabled="!pluginEnabled" :title="pluginOffTitle" :loading="poolBusy === 'export'" @click="exportPool">导出</v-btn>
        <v-btn size="small" variant="tonal" prepend-icon="mdi-import" :disabled="poolDataOpBlocked" :title="poolDataOpBlockedHint" :loading="poolBusy === 'import'" @click="pickPoolImport">导入</v-btn>
        <input ref="poolImportInput" type="file" accept=".json,application/json" style="display:none" @change="onPoolImportPick">
      </div>
    </div>

    <!-- 拉取进度 -->
    <div v-if="pulling || fetchState.total" class="epl-pool-progress">
      <div class="epl-pool-progress-line">
        <v-icon size="16">mdi-progress-download</v-icon>
        <span v-if="pulling">已拉取 {{ fetchState.done || 0 }} / {{ fetchState.total || '…' }}
          <span v-if="fetchState.current">· {{ fetchState.current }}</span></span>
        <span v-else>上次拉取：新增 {{ fetchState.added || 0 }} · 更新 {{ fetchState.updated || 0 }} · 无变化 {{ fetchState.unchanged || 0 }} · 过滤 {{ fetchState.filtered || 0 }} · 失败 {{ fetchState.failed || 0 }}</span>
        <span v-if="paused" class="epl-pool-paused">⏸ 已暂停</span>
        <v-btn v-if="pulling && !paused" size="x-small" variant="tonal" color="warning" class="epl-pool-pause-btn" :disabled="!pluginEnabled" @click="pauseFetch">暂停</v-btn>
        <v-btn v-if="pulling && paused" size="x-small" variant="flat" color="success" class="epl-pool-pause-btn" :disabled="!pluginEnabled" @click="resumeFetch">继续</v-btn>
      </div>
      <v-progress-linear :model-value="fetchPercent" height="6" rounded color="info" :indeterminate="pulling && !fetchPercent"></v-progress-linear>
    </div>

    <div v-if="txState.requested || txPaused" class="epl-pool-progress">
      <div class="epl-pool-progress-line">
        <v-icon size="16">mdi-translate</v-icon>
        <span v-if="txPaused" class="epl-pool-paused">⏸ 翻译已暂停（手动）</span>
        <span v-else>AI 翻译中{{ txState.scope ? '（' + txState.scope + '）' : '' }}<template v-if="txState.total"> · {{ txState.done || 0 }}/{{ txState.total }}</template><template v-if="txState.current"> · {{ txState.current }}</template></span>
        <v-btn v-if="!txPaused" size="x-small" variant="tonal" color="warning" class="epl-pool-pause-btn" :disabled="!pluginEnabled" @click="pauseTranslate">暂停</v-btn>
        <v-btn v-else size="x-small" variant="flat" color="success" class="epl-pool-pause-btn" :disabled="!pluginEnabled" @click="resumeTranslate">继续</v-btn>
      </div>
    </div>

    <!-- 筛选条（v4.4.8：默认只显示搜索框；点击展开「类型 / 状态」面板） -->
    <div ref="filterRef" class="epl-pool-filter" @click="filterOpen = true">
      <div class="epl-pool-search-row">
        <v-text-field
          v-model="keyword"
          density="compact"
          variant="outlined"
          hide-details
          placeholder="搜索 原文 / 译名…"
          prepend-inner-icon="mdi-magnify"
          class="epl-pool-search"
          clearable
          @keyup.enter="onSearch"
          @click:clear="onSearch"
        ></v-text-field>
        <span v-if="selCount" class="epl-pool-sel">已选 {{ selCount }} 项</span>
        <v-btn size="x-small" variant="text" icon class="epl-pool-expand"
               :aria-expanded="filterOpen ? 'true' : 'false'"
               @click.stop="filterOpen = !filterOpen">
          <v-icon :icon="filterOpen ? 'mdi-chevron-up' : 'mdi-chevron-down'"></v-icon>
        </v-btn>
      </div>
      <div v-if="filterOpen" class="epl-pool-filter-panel">
        <div class="epl-pool-panel-rows">
          <div class="epl-pool-chips">
            <span class="epl-pool-chips-label">类型</span>
            <button v-for="t in TYPE_FILTERS" :key="'t' + t.value" type="button"
                    class="epl-chip" :class="{ 'is-on': type === t.value }" @click="changeType(t.value)">{{ t.title }}</button>
          </div>
          <div class="epl-pool-chips">
            <span class="epl-pool-chips-label">状态</span>
            <button v-for="s in STATUS_FILTERS" :key="'s' + s.value" type="button"
                    class="epl-chip" :class="{ 'is-on': status === s.value }" @click="changeStatus(s.value)">{{ s.title }}</button>
          </div>
        </div>
        <v-btn size="x-small" variant="text" class="epl-pool-reset" @click="resetFilter">重置</v-btn>
      </div>
    </div>

    <!-- 列表（PC / 平板：表格） -->
    <div class="epl-pool-table epl-pool-desktop-table">
      <div class="epl-pool-th">
        <span class="c-name">原文名</span>
        <span class="c-zh">译名</span>
        <span class="c-type">类型</span>
        <span class="c-status">状态</span>
        <span class="c-occ">出现</span>
        <span class="c-op">操作</span>
      </div>
      <v-progress-linear v-if="loading" indeterminate color="primary" height="3"></v-progress-linear>
      <div v-if="!loading && !rows.length" class="epl-pool-empty">
        池里还没有人——点右上「拉取人名」把 Emby 的 Person 拉进来
      </div>
      <template v-for="r in rows" :key="personKey(r)">
        <div class="epl-pool-tr">
          <span class="c-name" :title="r.name_current || r.name_original">{{ r.name_original }}</span>
          <span class="c-zh" :title="r.name_zh">{{ zhText(r) || '—' }}</span>
          <span class="c-type">{{ typeText(r) }}</span>
          <span class="c-status">
            <span class="epl-badge" :class="'st-' + statusChip(r).color">{{ statusChip(r).dot }} {{ statusChip(r).text }}</span>
          </span>
          <span class="c-occ">
            <v-btn size="x-small" variant="text" density="compact" @click="toggleOcc(r)">
              {{ occOpen === personKey(r) ? '收起' : '查看' }}
            </v-btn>
          </span>
          <span class="c-op">
            <v-btn size="x-small" variant="flat" color="primary" density="comfortable" @click="openEdit(r)">改</v-btn>
            <v-btn v-if="canSync(r)" size="x-small" variant="flat"
                   color="success" density="comfortable" @click="openEdit(r)">同步</v-btn>
            <v-btn size="x-small" variant="tonal" density="comfortable" title="从 Emby 重新拉取该人（刷新当前名/类型；legacy 无 ID 行顺带补 Person ID）"
                   :loading="refetchKey === personKey(r)" @click="refetchOne(r)">重拉</v-btn>
          </span>
        </div>
        <div v-if="occOpen === personKey(r)" class="epl-pool-occ">
          <div class="epl-pool-occ-head">{{ r.name_original }} · {{ occCount(r) }}</div>
          <div v-if="occLoading" class="epl-pool-occ-empty">查询中…</div>
          <div v-else-if="!occRows.length" class="epl-pool-occ-empty">库里没有该人名的作品记录（可能其作品尚未扫描入库）</div>
          <ul v-else class="epl-pool-occ-list">
            <li v-for="(g, i) in occUnique" :key="i">
              <span class="epl-occ-title">《{{ g.title }}》</span>
              <span v-if="g.count > 1" class="epl-occ-count">×{{ g.count }}</span>
              <span v-if="g.deleted" class="epl-occ-del">待恢复</span>
            </li>
          </ul>
        </div>
      </template>
    </div>

    <!-- 列表（≤400px：卡片，文档 §四） -->
    <div class="epl-pool-mobile-list">
      <div v-if="!loading && !rows.length" class="epl-pool-empty">
        池里还没有人——点上方「拉取人名」把 Emby 的 Person 拉进来
      </div>
      <div v-for="r in rows" :key="'m' + personKey(r)" class="epl-person-card">
        <div class="person-card-top">
          <span class="person-card-name" :title="r.name_original">{{ r.name_original }}</span>
          <span class="epl-badge" :class="'st-' + statusChip(r).color">{{ statusChip(r).dot }} {{ statusChip(r).text }}</span>
        </div>
        <div class="person-card-main">
          <span class="person-card-zh" :title="r.name_zh">{{ zhText(r) || (isChineseText(r.name_original) ? '—' : '— 未译') }}</span>
          <span class="person-card-tools">
            <v-btn size="x-small" variant="flat" color="primary" density="comfortable" @click="openEdit(r)">编辑</v-btn>
            <v-btn v-if="canSync(r)" size="x-small" variant="flat" color="success" density="comfortable" @click="openEdit(r)">同步</v-btn>
            <v-btn size="x-small" variant="tonal" density="comfortable" title="从 Emby 重新拉取该人"
                   :loading="refetchKey === personKey(r)" @click="refetchOne(r)">重拉</v-btn>
            <v-btn size="x-small" variant="tonal" density="comfortable" @click="toggleDetail(r)">
              {{ detailOpen === rowKey(r) ? '收起' : '更多' }}
            </v-btn>
          </span>
        </div>
        <div v-if="detailOpen === rowKey(r)" class="person-card-detail">
          <div class="person-card-row">
            <span class="person-card-k">类型</span>
            <span class="person-card-v">{{ typeText(r) }}</span>
          </div>
          <div class="person-card-row">
            <span class="person-card-k">Emby 当前</span>
            <span class="person-card-v">{{ r.name_current || '—' }}</span>
          </div>
          <div class="person-card-actions">
            <v-btn size="x-small" variant="tonal" @click="toggleOcc(r)">
              {{ occOpen === rowKey(r) ? '收起作品' : '出现作品' }}
            </v-btn>
          </div>
          <div v-if="occOpen === rowKey(r)" class="epl-pool-occ">
            <div class="epl-pool-occ-head">{{ r.name_original }} · {{ occCount(r) }}</div>
            <div v-if="occLoading" class="epl-pool-occ-empty">查询中…</div>
            <div v-else-if="!occRows.length" class="epl-pool-occ-empty">库里没有该人名的作品记录（可能其作品尚未扫描入库）</div>
            <ul v-else class="epl-pool-occ-list">
              <li v-for="(g, i) in occUnique" :key="i">
                <span class="epl-occ-title">《{{ g.title }}》</span>
                <span v-if="g.count > 1" class="epl-occ-count">×{{ g.count }}</span>
                <span v-if="g.deleted" class="epl-occ-del">待恢复</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <div v-if="total > size" class="epl-pool-page">
      <v-pagination v-model="page" :length="Math.ceil(total / size)" total-visible="7" density="compact"
                    @update:model-value="loadList()"></v-pagination>
    </div>

    <!-- 编辑弹窗 -->
    <v-dialog v-model="editDlg" max-width="460">
      <div class="epl-dlg">
        <div class="epl-dlg-title">编辑人名</div>
        <div class="epl-dlg-body">
          <div class="epl-field"><span class="epl-field-k">原文</span><span class="epl-field-v">{{ editRow?.name_original }}</span></div>
          <div class="epl-field"><span class="epl-field-k">Emby 当前</span><span class="epl-field-v">{{ editRow?.name_current || '（未记录）' }}</span></div>
          <div class="epl-field"><span class="epl-field-k">类型</span><span class="epl-field-v">{{ typeText(editRow) }}</span></div>
          <v-text-field v-model="editZh" label="译名" density="compact" variant="outlined" hide-details
                        class="epl-dlg-input" placeholder="留空 = 清除译文"></v-text-field>
          <v-checkbox v-model="editSyncEmby" density="compact" hide-details color="primary"
                      label="同步到 Emby（改 Emby 演员名，全局生效；默认不改）"></v-checkbox>
          <div class="epl-dlg-tip">保存只改人名池（manual 最高优先级，AI 不覆盖）。勾选上方选项后保存会同时改 Emby Person 实体名（全局生效）。</div>
        </div>
        <div class="epl-dlg-acts">
          <v-btn variant="text" @click="editDlg = false">取消</v-btn>
          <v-btn variant="flat" color="primary" :loading="busy" @click="editSyncEmby ? syncOne() : saveEdit()">保存</v-btn>
        </div>
      </div>
    </v-dialog>

    <!-- 拉取弹窗 -->
    <v-dialog v-model="fetchDlg" max-width="460">
      <div class="epl-dlg">
        <div class="epl-dlg-title">拉取人名</div>
        <div class="epl-dlg-body">
          <div class="epl-dlg-tip">拉取类型跟随设置页「翻译范围」的人名类型开关（不再单独设置）。人物类型优先从 Emby People 关系获取；无法确定类型的全库 Person 不参与按类型筛选，建议使用「已选媒体库」范围。</div>
          <v-radio-group v-model="scope" density="compact" hide-details class="epl-dlg-radio">
            <v-radio value="libraries" label="仅已选媒体库中的 Person（推荐，快）"></v-radio>
            <v-radio value="all" label="全库 Person（/Persons 全量，慢）"></v-radio>
          </v-radio-group>
        </div>
        <div class="epl-dlg-acts">
          <v-btn variant="text" @click="fetchDlg = false">取消</v-btn>
          <v-btn variant="text" color="warning" :loading="busy" @click="doRescreen">按当前设置重筛池</v-btn>
          <v-btn variant="flat" color="info" :loading="busy" @click="doFetch">开始拉取</v-btn>
        </div>
      </div>
    </v-dialog>

    <!-- 批量翻译弹窗 -->
    <v-dialog v-model="transDlg" max-width="420">
      <div class="epl-dlg">
        <div class="epl-dlg-title">批量翻译</div>
        <div class="epl-dlg-body">
          <div class="epl-field"><span class="epl-field-k">待翻译</span><span class="epl-field-v">{{ counts.pending }} 个</span></div>
          <div class="epl-field"><span class="epl-field-k">无需操作</span><span class="epl-field-v">{{ counts.no_change }} 个</span></div>
          <v-checkbox v-model="transSync" density="compact" hide-details color="primary"
                      label="翻译完成后自动同步 Emby（默认关闭）"></v-checkbox>
          <div class="epl-dlg-tip">翻译由后台常驻 worker 自动完成（限流不丢）；不勾则只写池，之后到「人名池 → 批量同步」手动同步。</div>
        </div>
        <div class="epl-dlg-acts">
          <v-btn variant="text" @click="transDlg = false">取消</v-btn>
          <v-btn variant="flat" color="primary" :loading="busy" @click="doTranslate">开始</v-btn>
        </div>
      </div>
    </v-dialog>

    <!-- 批量同步弹窗 -->
    <v-dialog v-model="syncDlg" max-width="420">
      <div class="epl-dlg">
        <div class="epl-dlg-title">批量同步到 Emby</div>
        <div class="epl-dlg-body">
          <div class="epl-field"><span class="epl-field-k">待同步</span><span class="epl-field-v">{{ counts.translated }} 个</span></div>
          <div class="epl-dlg-warn">⚠️ Emby 里改名会全局生效（该 Person 在所有作品中的显示名都会变）。</div>
        </div>
        <div class="epl-dlg-acts">
          <v-btn variant="text" @click="syncDlg = false">取消</v-btn>
          <v-btn variant="flat" color="success" :loading="busy" @click="doSync">开始</v-btn>
        </div>
      </div>
    </v-dialog>

    <ConfirmDlg :state="cState" :on-ok="cOk" :on-cancel="cCancel" />
    <!-- v4.6.70：统一「任务进行中」拦截弹窗（人名池修改型操作共用） -->
    <TaskGuardDlg v-model="guard.dlg.value" :reason="guard.reason.value"
                  :state="guard.stateLabel.value"
                  :action="guard.pendingLabel.value" @view-task="emit('view-task')" />
  </div>
</template>

<style scoped>
.epl-pool { display: flex; flex-direction: column; gap: 12px; }

.epl-pool-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.epl-pool-sub { font-size: 12px; opacity: .72; font-weight: 400; }
.epl-pool-acts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.epl-pool-progress { background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.08); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.epl-pool-progress-line { font-size: 12.5px; opacity: .85; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.epl-pool-paused { color: #ffcc80; font-size: 12px; margin-left: 4px; }
.epl-pool-pause-btn { margin-left: 2px; }

.epl-pool-filter { display: flex; flex-direction: column; gap: 8px;
  background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); border-radius: 10px; padding: 10px 12px; }
.epl-pool-search-row { display: flex; align-items: center; gap: 8px; }
.epl-pool-search { flex: 1 1 220px; min-width: 170px; }
.epl-pool-sel { flex: 0 0 auto; font-size: 12px; padding: 2px 10px; border-radius: 12px; white-space: nowrap;
  background: rgba(25,118,210,.22); border: 1px solid rgba(25,118,210,.5); }
.epl-pool-expand { flex: 0 0 auto; }
.epl-pool-filter-panel { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px 12px;
  padding-top: 8px; border-top: 1px dashed rgba(255,255,255,.10); }
.epl-pool-panel-rows { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.epl-pool-chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.epl-pool-chips-label { flex: 0 0 auto; font-size: 12px; opacity: .55; }
.epl-chip { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10); color: inherit; opacity: .8;
  border-radius: 14px; padding: 3px 12px; font-size: 12.5px; cursor: pointer; line-height: 20px; }
.epl-chip:hover { opacity: 1; }
.epl-chip.is-on { background: rgba(25,118,210,.28); border-color: rgba(25,118,210,.6); opacity: 1; font-weight: 600; }
.epl-pool-reset { align-self: center; }

.epl-pool-table { background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); border-radius: 10px; overflow: hidden; }
.epl-pool-th, .epl-pool-tr { display: grid; grid-template-columns: minmax(88px, 1.7fr) minmax(104px, 2fr) minmax(56px, 1fr) minmax(84px, 1.25fr) minmax(52px, .95fr) minmax(140px, 1.6fr); align-items: center; gap: 8px; padding: 5px 14px; }
.epl-pool-th { font-size: 12px; opacity: .65; border-bottom: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.035); }
.epl-pool-tr { font-size: 13px; border-bottom: 1px solid rgba(255,255,255,.05); }
.epl-pool-tr:hover { background: rgba(255,255,255,.035); }
.c-name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-zh { opacity: .92; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-type { justify-self: start; }
.c-status, .c-occ, .c-op { justify-self: center; }
.c-op { display: flex; gap: 4px; flex-wrap: nowrap; justify-content: center; }
.epl-pool-empty { padding: 26px 12px; text-align: center; font-size: 13px; opacity: .6; }

.epl-pool-desktop-table { display: block; }
.epl-pool-mobile-list { display: none; }
.epl-person-card { display: flex; flex-direction: column; gap: 5px; padding: 8px 10px; border-radius: 10px;
  border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.035); }
.person-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.person-card-name { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.person-card-main { display: flex; align-items: center; gap: 6px; }
.person-card-zh { flex: 1 1 auto; min-width: 0; font-size: 13px; opacity: .92; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.person-card-tools { flex: 0 0 auto; display: flex; align-items: center; gap: 4px; }
.person-card-detail { display: flex; flex-direction: column; gap: 5px; margin-top: 2px; padding-top: 6px; border-top: 1px dashed rgba(255,255,255,.10); }
.person-card-row { display: flex; gap: 8px; font-size: 12.5px; align-items: baseline; }
.person-card-k { opacity: .6; min-width: 58px; flex-shrink: 0; }
.person-card-v { opacity: .95; word-break: break-all; }
.person-card-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }

.epl-badge { font-size: 12px; padding: 1px 8px; border-radius: 10px; border: 1px solid transparent; white-space: nowrap; }
.epl-badge.st-error { background: rgba(244,67,54,.16); border-color: rgba(244,67,54,.42); }
.epl-badge.st-warning { background: rgba(255,152,0,.16); border-color: rgba(255,152,0,.42); }
.epl-badge.st-success { background: rgba(76,175,80,.16); border-color: rgba(76,175,80,.42); }

.epl-pool-occ { padding: 6px 12px 12px 22px; background: rgba(255,255,255,.02); border-bottom: 1px solid rgba(255,255,255,.05); }
.epl-pool-occ-head { font-size: 12.5px; opacity: .75; margin: 4px 0 6px; }
.epl-pool-occ-empty { font-size: 12.5px; opacity: .6; }
.epl-pool-occ-list { margin: 0; padding-left: 16px; max-height: 180px; overflow-y: auto; font-size: 12.5px; }
.epl-pool-occ-list li { margin: 2px 0; }
.epl-occ-title { opacity: .9; }
.epl-occ-count { opacity: .68; margin-left: 8px; font-size: 12px; }
.epl-occ-del { color: #ff8a80; margin-left: 8px; }

.epl-pool-page { display: flex; justify-content: center; }

.epl-dlg { background: #1f2430; border: 1px solid rgba(255,255,255,.12); border-radius: 14px; padding: 16px 18px 12px; color: #e6e8ee; }
.epl-dlg-title { font-size: 15.5px; font-weight: 600; margin-bottom: 10px; }
.epl-dlg-body { display: flex; flex-direction: column; gap: 8px; }
.epl-field { display: flex; gap: 8px; font-size: 13px; }
.epl-field-k { opacity: .6; min-width: 76px; }
.epl-field-v { opacity: .95; word-break: break-all; }
.epl-dlg-input { margin-top: 2px; }
.epl-dlg :deep(.v-field) { border-radius: 8px; background: rgba(0,0,0,.28); }
.epl-dlg :deep(.v-field__outline) { --v-field-border-opacity: .6; }
.epl-dlg :deep(.v-field--focused .v-field__outline) { --v-field-border-opacity: 1; }
.epl-dlg :deep(.v-field--focused) { box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), .25); }
.epl-dlg-tip { font-size: 12px; opacity: .62; line-height: 1.5; }
.epl-dlg-warn { font-size: 12.5px; color: #ffcc80; line-height: 1.5; }
.epl-dlg-radio { margin-top: 2px; }
.epl-dlg-acts { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; flex-wrap: wrap; }

@media (max-width: 820px) {
  .epl-pool-th, .epl-pool-tr { grid-template-columns: minmax(76px, 1.7fr) minmax(92px, 2fr) minmax(48px, 1fr) minmax(72px, 1.25fr) minmax(46px, .95fr) minmax(132px, 1.6fr); font-size: 12.5px; padding: 6px 8px; gap: 5px; }
  /* 文档 §八：弹窗不超出屏幕 */
  .epl-dlg { max-width: calc(100vw - 20px); }
}

@media (max-width: 600px) {
  .epl-pool-desktop-table { display: none; }
  .epl-pool-mobile-list { display: flex; flex-direction: column; gap: 8px; }
  .epl-pool-sub { width: 100%; margin-left: 0; }
}

@media (max-width: 400px) {
  /* 文档 §五：顶部按钮 2 列网格，「拉取人名」占满首行 */
  .epl-pool-head { align-items: flex-start; }
  .epl-pool-acts { width: 100%; display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .epl-pool-acts :deep(.v-btn) { width: 100%; min-width: 0; }
  .epl-act-fetch { grid-column: span 2; }

  .epl-pool-search { flex: 1 1 auto; min-width: 0; }
  .epl-pool-filter-panel { grid-template-columns: 1fr; }
  .epl-pool-reset { justify-self: end; }

  /* 文档 §八：弹窗宽度 */
  .epl-dlg { width: calc(100vw - 20px); max-width: calc(100vw - 20px); }
}

@media (max-width: 340px) {
  .epl-pool-acts { grid-template-columns: 1fr; }
  .epl-act-fetch { grid-column: span 1; }
  .epl-chip { padding: 3px 8px; font-size: 11.5px; }
  .epl-dlg { width: calc(100vw - 12px); max-width: calc(100vw - 12px); padding: 12px; }
  .epl-dlg-acts { gap: 6px; }
}
</style>