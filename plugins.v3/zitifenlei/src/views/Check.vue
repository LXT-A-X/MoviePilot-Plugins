<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  // 插件总开关：停用时操作按钮置灰禁用
  enabled: { type: Boolean, default: true },
  // 数据变更信号（Page 递推）：字体库删除/新增字体后，本页缺失标记/缺失窗口实时刷新
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

const records = ref([])
const search = ref('')
const filterStatus = ref('')
const statusFilterOptions = [
  { title: '全部状态', value: '' },
  { title: '待检查', value: 'pending' },
  { title: '缺字体', value: 'missing' },
  { title: '完整', value: 'ok' },
]
const loadingList = ref(false)

// 左栏分组抽屉：一次取全量，按压缩包/上传批次/目录分组后前端渐进渲染
const RENDER_STEP = 60
const renderBudget = ref(RENDER_STEP)
const expandedGroups = ref(new Set())
const groupBusy = ref('')
const groupConfirm = ref(false)
const groupTarget = ref(null)
const groupDeleting = ref(false)
// 批量检查（组头「全部检查」/ 顶部「检查」共用）
const batchChecking = ref(false)

const selectedId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const detailOpen = ref(false)

const uploadRef = ref(null)
const uploading = ref(false)
const deletingId = ref(null)
const clearing = ref(false)
const clearConfirm = ref(false)
const checkingId = ref(null)
// 全量扫描（字体监控目录字体直接入库）
const scanning = ref(false)

const activeRecord = computed(() =>
  records.value.find(r => r.id === selectedId.value) || null
)

// 检查「匹配基准」：index=fontTools 字体索引（与子集化同一口径，逐 face/字符覆盖）；
// db=字体库记录（索引不可用时的回退口径，只判字体名）
// 由 /ass/list 响应顶层 match_source 决定（列表为空时也显示）
const matchSource = ref('')
const matchSourceText = computed(() => {
  const s = matchSource.value || records.value[0]?.match_source || ''
  if (s === 'index') return '字体索引（fontTools），与子集化同一口径'
  if (s === 'db') return '字体库记录（索引不可用时的兜底，仅按字体名判缺失）'
  return ''
})

// 列表请求序号守卫：30 秒轮询与搜索/上传后的强制刷新可能交错，
// 只应用最后发起的请求的响应，丢弃过期响应，避免列表重复/错序（Q8 修复）
let listReqSeq = 0
async function loadRecords(reset = false, force = false) {
  if (loadingList.value && !force) return
  const seq = ++listReqSeq
  loadingList.value = true
  try {
    // limit=0：一次取全量（分组计数/组头全部检查都基于完整数据，不受分页截断）
    const data = await apiModule.get(props.api, '/ass/list', {
      page: 1,
      limit: 0,
      search: search.value,
    })
    if (seq !== listReqSeq) return
    const list = data.list || []
    matchSource.value = data.match_source || list[0]?.match_source || matchSource.value
    records.value = list
    if (reset) {
      renderBudget.value = RENDER_STEP
      expandedGroups.value = new Set()
    }
    // 选中的记录被删/被过滤掉时，右侧详情一并清空
    if (selectedId.value && !list.some(r => r.id === selectedId.value)) {
      selectedId.value = null
      detail.value = null
      detailOpen.value = false
    }
    // 注意：不自动选中/不自动加载第一条——右侧只在点击左侧记录时显示
  } catch (e) {
    if (seq === listReqSeq) emit('notify', e.message || '加载检查记录失败')
  } finally {
    if (seq === listReqSeq) loadingList.value = false
  }
}

// ── 分组：压缩包一组（后端写入 batch=包名）；单文件上传按一次上传归一组；
// 监控/入库记录没有 batch，按字幕所在目录分组（Season 目录上跳一级）
const SEASON_RE = /^(season\s*\d+|s\d{1,2}|第.{1,4}季)$/i
function seasonLike(name) {
  return SEASON_RE.test(String(name || '').trim())
}
function recordGroup(r) {
  const batch = String(r.batch || '').trim()
  if (batch) return { key: `b:${batch}`, label: batch }
  if (r.source === 'manual') return { key: 'manual', label: '历史上传' }
  const p = String(r.file_path || '').replace(/\\/g, '/')
  const dirs = p ? p.split('/').filter(Boolean).slice(0, -1) : []
  if (!dirs.length) return { key: 'other', label: '其他记录' }
  let idx = dirs.length - 1
  if (seasonLike(dirs[idx]) && idx > 0) idx -= 1
  return { key: `d:${dirs.slice(0, idx + 1).join('/')}`, label: dirs[idx] || '其他记录' }
}
function groupStats(list) {
  const s = { pending: 0, ok: 0, missing: 0 }
  for (const r of list) {
    if (r.status === 'pending') s.pending += 1
    else if (r.status === 'ok' || r.status === 'partial_check') s.ok += 1
    else s.missing += 1
  }
  return s
}
// 可检查项：待检查 + 缺字体（已完整的跳过，避免重复解析）
function checkableOf(list) {
  return list.filter(r => r.status === 'pending' || r.status === 'missing')
}
// 状态筛选：完整含「ok」与「未验证字形（partial_check）」两种结论
const filteredRecords = computed(() => {
  const s = filterStatus.value
  if (!s) return records.value
  if (s === 'ok') return records.value.filter(r => r.status === 'ok' || r.status === 'partial_check')
  return records.value.filter(r => r.status === s)
})
const groupedRecords = computed(() => {
  const map = new Map()
  for (const r of filteredRecords.value) {
    const g = recordGroup(r)
    let item = map.get(g.key)
    if (!item) {
      item = { key: g.key, label: g.label, records: [], maxId: 0 }
      map.set(g.key, item)
    }
    item.records.push(r)
    if (Number(r.id) > item.maxId) item.maxId = Number(r.id)
  }
  const groups = [...map.values()].sort((a, b) => b.maxId - a.maxId)
  for (const g of groups) {
    g.stats = groupStats(g.records)
    // 组头颜色：有缺字体红，有待检查灰，全完整绿
    g.color = g.stats.missing ? 'error' : (g.stats.pending ? 'grey' : 'success')
    g.checkable = checkableOf(g.records)
  }
  return groups
})
// 渐进渲染：组头全显示；展开的组内记录消耗渲染预算，滚到底再加一批
const visibleGroups = computed(() => {
  let remain = renderBudget.value
  return groupedRecords.value.map(g => {
    const expanded = expandedGroups.value.has(g.key)
    let visibleRecords = []
    let truncated = false
    if (expanded) {
      visibleRecords = g.records.slice(0, Math.max(0, remain))
      remain -= visibleRecords.length
      truncated = visibleRecords.length < g.records.length
    }
    return { ...g, expanded, visibleRecords, truncated }
  })
})
const hasMoreRecords = computed(() => visibleGroups.value.some(g => g.truncated))
const checkableRecords = computed(() => checkableOf(records.value))

function toggleGroup(g) {
  const next = new Set(expandedGroups.value)
  if (next.has(g.key)) next.delete(g.key)
  else next.add(g.key)
  expandedGroups.value = next
}
function onRecordsScroll(e) {
  const el = e.target
  if (hasMoreRecords.value && el && el.scrollTop + el.clientHeight >= el.scrollHeight - 60) {
    renderBudget.value += RENDER_STEP
  }
}

async function loadDetail(id) {
  selectedId.value = id
  detailLoading.value = true
  detailOpen.value = true
  try {
    detail.value = await apiModule.get(props.api, '/ass/detail', { id })
  } catch (e) {
    emit('notify', e.message || '加载详情失败')
  } finally {
    detailLoading.value = false
  }
}

let searchTimer = null
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadRecords(true), 300)
})
// 切换状态筛选：重新从第一组、第一批开始渲染
watch(filterStatus, () => {
  renderBudget.value = RENDER_STEP
  expandedGroups.value = new Set()
})

async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 5 个。
  // 同一次选择的所有分片共用一个批次名（单文件上传即一组）；压缩包内文件由后端用包名覆盖
  const BATCH = 5
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const batchLabel = `手动上传 ${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
  let total = 0
  uploading.value = true
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH)
      const form = new FormData()
      for (const file of chunk) form.append('file', file)
      form.append('batch', batchLabel)
      const res = await props.api.post(
        'plugin/Zitifenlei/ass/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      const body = res?.data ?? res
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '字幕上传失败'}`)
        break
      } else {
        total += (body?.data?.count ?? chunk.length)
      }
    }
    emit('notify', `已上传 ${total} 个字幕，点击上方「检查」对比字体库`, 'success')
    // 不自动选中任何记录：右侧保持空，等待点击左侧
    await loadRecords(true, true)
  } catch (e) {
    emit('notify', e.message || '字幕上传失败')
  } finally {
    uploading.value = false
  }
}

async function checkRecord(id) {
  if (!id || checkingId.value || batchChecking.value) return null
  checkingId.value = id
  try {
    const data = await apiModule.post(props.api, '/ass/check', { id })
    // 正在查看该条时刷新右侧显示，否则右侧保持原样（不自动选中）
    if (detail.value && detail.value.id === id) {
      await loadDetail(id)
    }
    await loadRecords(false, true)
    return data
  } catch (e) {
    emit('notify', e.message || '检查失败')
    return null
  } finally {
    checkingId.value = null
  }
}

// 批量检查：组头「全部检查」只查本组，顶部「检查」查全部（待检查 + 缺字体）
async function checkIds(list, label = '') {
  if (batchChecking.value || checkingId.value) {
    emit('notify', '正在检查中，请稍候', 'warning')
    return
  }
  const ids = list.map(r => Number(r.id)).filter(Boolean)
  if (!ids.length) {
    emit('notify', records.value.length ? '没有需要检查的字幕（已检查的跳过）' : '请先上传 ASS 字幕', 'warning')
    return
  }
  batchChecking.value = true
  try {
    const res = await apiModule.post(props.api, '/ass/check_batch', { ids })
    const s = res || {}
    let msg = `${label}检查完成：${s.ok ?? 0}/${s.total ?? ids.length} 条`
    if (s.missing) msg += `，${s.missing} 条缺字体`
    if (s.failed) msg += `，${s.failed} 条失败`
    emit('notify', msg, s.failed ? 'warning' : 'success')
    await loadRecords(false, true)
    if (detail.value) await loadDetail(detail.value.id)
  } catch (e) {
    emit('notify', e.message || '批量检查失败')
  } finally {
    batchChecking.value = false
  }
}

async function checkAllPending() {
  await checkIds(checkableRecords.value)
}

async function checkGroup(g) {
  if (groupBusy.value) return
  groupBusy.value = g.key
  try {
    await checkIds(g.checkable, `本组（${g.label}）`)
  } finally {
    groupBusy.value = ''
  }
}

// 删除整组：删记录，上传的临时副本一并清理；监控/媒体库原字幕不动
function askDeleteGroup(g) {
  groupTarget.value = g
  groupConfirm.value = true
}
async function confirmDeleteGroup() {
  const g = groupTarget.value
  if (!g || groupDeleting.value) return
  groupDeleting.value = true
  const ids = g.records.map(r => Number(r.id)).filter(Boolean)
  const errors = []
  let head = 0
  const worker = async () => {
    while (head < ids.length) {
      const id = ids[head++]
      try {
        await apiModule.del(props.api, '/ass/delete', { id })
      } catch (e) {
        errors.push(id)
      }
    }
  }
  try {
    await Promise.all([worker(), worker(), worker()])
    groupConfirm.value = false
    groupTarget.value = null
    const ok = ids.length - errors.length
    emit(
      'notify',
      errors.length ? `已删除 ${ok} 条，${errors.length} 条失败` : `已删除本组 ${ok} 条记录`,
      errors.length ? 'warning' : 'success'
    )
    if (detail.value && ids.includes(Number(detail.value.id))) {
      detail.value = null
      detailOpen.value = false
      selectedId.value = null
    }
    await loadRecords(false, true)
  } finally {
    groupDeleting.value = false
  }
}

// 全量检查：递归扫描 ASS 字幕目录中的全部字幕并检查（存量字幕一键全查，按 file_path upsert 幂等）
async function scanAssAll() {
  if (scanning.value) return
  scanning.value = true
  try {
    const res = await apiModule.post(props.api, '/ass/scan_all')
    emit('notify', res?.message || '全量检查完成', 'success')
    await loadRecords(false, true)
  } catch (e) {
    emit('notify', e.message || '全量检查失败')
  } finally {
    scanning.value = false
  }
}

async function deleteRecord(id) {
  deletingId.value = id
  try {
    await apiModule.del(props.api, '/ass/delete', { id })
    emit('notify', '已删除记录', 'success')
    // 删除的是当前正在查看的记录时，清空右侧显示
    if (detail.value && detail.value.id === id) {
      detail.value = null
      detailOpen.value = false
      selectedId.value = null
    }
    await loadRecords(false, true)
  } catch (e) {
    emit('notify', e.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

async function clearAll() {
  clearing.value = true
  try {
    await apiModule.del(props.api, '/ass/clear_all')
    emit('notify', '已清空全部记录', 'success')
    detail.value = null
    detailOpen.value = false
    await loadRecords(true, true)
  } catch (e) {
    emit('notify', e.message || '清空失败')
  } finally {
    clearing.value = false
    clearConfirm.value = false
  }
}

function goFontSearch(name) {
  // 跳转到字体库搜索该字体名：通过宿主路由 or 菜单；这里直接提示
  emit('notify', `可在字体库搜索：${name}`, 'info')
}

// 字形级缺失明细（字体名 → 缺失字符数/字符），来自 /ass/detail 的 missing_details
function missingDetailFor(name) {
  return (detail.value?.missing_details || []).find(x => x.name === name) || null
}

function missingCharText(name) {
  return missingDetailFor(name)?.missing_chars || ''
}

function missingCharCount(name) {
  const d = missingDetailFor(name)
  return d?.missing_count || 0
}

// 软刷新左侧记录列表（保留分组展开状态与当前选中）：
// 切 Tab 回来 / refreshKey 触发 / 30 秒轮询兜底 共用——监控新字幕按 id 倒序出现在列表顶部
async function refreshRecordsSoft() {
  await loadRecords()
  // 详情里的缺失标记与字体库实时同步（兄弟页删字体后无需手动重开）
  if (selectedId.value && detail.value && records.value.some(r => r.id === selectedId.value)) {
    await loadDetail(selectedId.value)
  }
}

// 30 秒轮询兜底：目录监控/入库扫描写入新字幕记录后，页面停留不动也能自动显示
let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(refreshRecordsSoft, 30000)
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 兄弟页完成数据变更（字体库删除字体等 → Page 递推 refreshKey）：
// ① 当前打开的详情缺失标记 + 底部缺失窗口实时重算；
// ② 软刷新左侧记录列表——切 Tab 回来时监控新写入的字幕直接出现在列表顶部（id 倒序），
//    不再需要退出插件重进
watch(() => props.refreshKey, () => {
  refreshRecordsSoft()
})

onMounted(async () => {
  await loadRecords(true)
  startPolling()
})

// keep-alive 缓存场景：切回本视图时恢复轮询（onDeactivated 已停掉），
// 并重拉列表（Q14 后切 Tab 不再由 Page 广播刷新键，各视图自查自刷）
onActivated(() => {
  refreshRecordsSoft()
  startPolling()
})

// 切走视图（进入 keep-alive 缓存）时立即停止轮询，避免后台不可见视图
// 每 30 秒仍打接口（Q1 修复）
onDeactivated(() => {
  stopPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="zt-check">
    <!-- 顶部操作栏：上传 + 检查（检查左侧已选/最近上传的字幕） -->
    <div class="d-flex align-center flex-wrap mb-4">
      <v-btn
        color="primary"
        variant="tonal"
        :disabled="!enabled"
        :loading="uploading"
        title="上传 ASS 字幕（支持 .ass 与 .zip/.7z/.rar 压缩包）"
        @click="uploadRef?.click()"
      >
        <v-icon start size="18">mdi-upload</v-icon>
        上传 ASS 字幕
      </v-btn>
      <input
        ref="uploadRef"
        type="file"
        accept=".ass,.ASS,.zip,.7z,.rar"
        multiple
        style="display: none"
        @change="handleUpload"
      />
      <v-btn
        color="success"
        variant="tonal"
        class="ml-2"
        :disabled="!enabled || !checkableRecords.length || batchChecking || !!checkingId"
        :loading="batchChecking"
        title="一次性检查全部待检查 / 缺字体的字幕（已完整的跳过）"
        @click="checkAllPending"
      >
        <v-icon start size="18">mdi-magnify-scan</v-icon>
        检查
      </v-btn>
      <v-spacer></v-spacer>
      <v-btn
        color="info"
        variant="tonal"
        class="mr-2"
        :disabled="!enabled"
        :loading="scanning"
        title="全量检查：递归扫描 ASS 字幕目录中的全部字幕并检查（存量字幕一键全查）"
        @click="scanAssAll"
      >
        <v-icon start size="18">mdi-magnify-scan</v-icon>
        全量检查
      </v-btn>
    </div>
    <div class="zt-tip text-body-2 mb-2">
      上传字幕仅登记为「待检查」；点顶部「检查」一次性检查全部，或点左侧每组 / 每条的「检查」单独检查；缺字体的补字/入库请到「缺失字体」页
    </div>

    <div v-if="matchSourceText" class="zt-match-source mb-2">
      匹配基准：{{ matchSourceText }}
    </div>

    <v-row no-gutters>
      <!-- 左栏：记录列表，小屏占满整行（上下结构），大屏 5:7 -->
      <v-col cols="12" md="5">
        <v-card class="zt-card-bg zt-list-card">
          <v-card-title class="zt-card-title zt-card-title-row">
            <v-icon start size="18">mdi-file-search-outline</v-icon>
            <span class="zt-title-text">检查记录（{{ filteredRecords.length }}）</span>
            <v-spacer></v-spacer>
            <v-btn
              size="small"
              variant="tonal"
              color="error"
              :disabled="!enabled || !records.length"
              :loading="clearing"
              title="清空全部检查记录（同时删除上传的临时副本；监控目录与媒体库原字幕不动）"
              @click="clearConfirm = true"
            >
              <v-icon start size="15">mdi-delete-sweep</v-icon>
              <span class="d-none d-sm-inline">全部清空</span>
            </v-btn>
          </v-card-title>
          <v-divider></v-divider>
          <!-- 筛选栏：状态下拉 + 文件名搜索（与子集化结果卡片一致） -->
          <div class="zt-filter-row">
            <v-select
              v-model="filterStatus"
              :items="statusFilterOptions"
              item-title="title"
              item-value="value"
              density="compact"
              variant="outlined"
              hide-details
              class="zt-filter-status"
            ></v-select>
            <v-text-field
              v-model="search"
              placeholder="搜索字幕文件名…"
              density="compact"
              variant="outlined"
              hide-details
              :clearable="!!search"
              prepend-inner-icon="mdi-magnify"
              class="zt-filter-search"
            ></v-text-field>
          </div>
          <v-divider></v-divider>
          <v-progress-linear v-if="loadingList" indeterminate color="primary"></v-progress-linear>
          <div class="zt-list-body pa-2" @scroll="onRecordsScroll">
            <div v-if="!loadingList && !groupedRecords.length" class="zt-empty pa-6">
              {{ filterStatus || search ? '暂无匹配的检查记录' : '暂无检查记录，上传 ASS 字幕后点击「检查」对比字体库' }}
            </div>
            <div v-else class="zt-group-wrap">
              <div
                v-for="g in visibleGroups"
                :key="g.key"
                class="zt-group"
                :class="`zt-group-${g.color}`"
              >
                <div class="zt-group-head" @click="toggleGroup(g)">
                  <v-icon size="18">{{ g.expanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                  <v-icon size="16" :color="g.color === 'grey' ? undefined : g.color">
                    {{ g.expanded ? 'mdi-folder-open' : 'mdi-folder' }}
                  </v-icon>
                  <span class="zt-group-name" :title="g.label">{{ g.label }}</span>
                  <span class="zt-group-count">{{ g.records.length }}</span>
                  <span class="zt-group-stats">
                    <v-chip v-if="g.stats.ok" color="success" size="x-small" variant="tonal">✓ {{ g.stats.ok }}</v-chip>
                    <v-chip v-if="g.stats.missing" color="error" size="x-small" variant="tonal">⚠ {{ g.stats.missing }}</v-chip>
                    <v-chip v-if="g.stats.pending" color="warning" size="x-small" variant="tonal">待 {{ g.stats.pending }}</v-chip>
                  </span>
                  <span class="zt-group-actions">
                    <v-btn
                      size="x-small" variant="tonal" color="success"
                      :disabled="!enabled || batchChecking || !!checkingId || !g.checkable.length"
                      :loading="groupBusy === g.key"
                      title="检查本组待检查 / 缺字体的字幕（已完整的跳过）"
                      @click.stop="checkGroup(g)"
                    >
                      <v-icon start size="14">mdi-magnify-scan</v-icon>
                      <span class="d-none d-lg-inline">全部检查</span>
                    </v-btn>
                    <v-btn
                      size="small" variant="text" icon
                      :disabled="!enabled || groupDeleting"
                      title="删除本组全部记录（上传的临时副本一并清理，监控/媒体库原字幕不动）"
                      @click.stop="askDeleteGroup(g)"
                    >
                      <v-icon size="16" color="error">mdi-close</v-icon>
                    </v-btn>
                  </span>
                </div>
                <div v-if="g.expanded" class="zt-group-body">
                  <v-list density="compact" class="pa-0">
                    <v-list-item
                      v-for="rec in g.visibleRecords"
                      :key="rec.id"
                      :active="selectedId === rec.id"
                      class="zt-record-item"
                      @click="loadDetail(rec.id)"
                    >
                      <template #prepend>
                        <v-icon
                          :color="rec.status === 'ok' || rec.status === 'partial_check' ? 'success' : (rec.status === 'pending' ? 'warning' : 'error')"
                          size="18"
                        >
                          {{ rec.status === 'ok' || rec.status === 'partial_check' ? 'mdi-check-circle' : (rec.status === 'pending' ? 'mdi-clock-outline' : 'mdi-alert-circle') }}
                        </v-icon>
                      </template>
                      <v-list-item-title class="zt-record-name text-body-2">
                        {{ rec.file_name }}
                      </v-list-item-title>
                      <v-list-item-subtitle class="zt-record-meta">
                        {{ rec.check_time }}
                        <v-chip
                          v-if="rec.status === 'pending'"
                          size="x-small"
                          color="warning"
                          variant="tonal"
                          class="ml-1"
                        >
                          待检查
                        </v-chip>
                        <v-chip
                          v-else-if="rec.missing_count > 0"
                          size="x-small"
                          color="error"
                          variant="tonal"
                          class="ml-1"
                        >
                          缺 {{ rec.missing_count }} 个
                        </v-chip>
                        <v-chip
                          v-else-if="rec.status === 'partial_check'"
                          size="x-small"
                          color="warning"
                          variant="tonal"
                          class="ml-1"
                        >
                          未验证字形
                        </v-chip>
                        <v-chip
                          v-else
                          size="x-small"
                          color="success"
                          variant="tonal"
                          class="ml-1"
                        >
                          完整
                        </v-chip>
                        <v-chip
                          v-if="rec.subsetted"
                          size="x-small"
                          color="info"
                          variant="tonal"
                          class="ml-1"
                        >
                          已内嵌字体
                        </v-chip>
                      </v-list-item-subtitle>
                      <template #append>
                        <v-btn
                          size="x-small"
                          variant="tonal"
                          :color="rec.status === 'pending' ? 'success' : 'primary'"
                          class="mr-1"
                          :disabled="!enabled || batchChecking || !!checkingId"
                          :loading="checkingId === rec.id"
                          :title="rec.status === 'pending' ? '检查该字幕' : '重新检查该字幕'"
                          @click.stop="checkRecord(rec.id)"
                        >
                          <v-icon start size="14">mdi-magnify-scan</v-icon>
                          检查
                        </v-btn>
                        <v-btn
                          size="small"
                          variant="text"
                          icon
                          color="error"
                          :disabled="!enabled"
                          :loading="deletingId === rec.id"
                          title="删除该字幕（避免误传）"
                          @click.stop="deleteRecord(rec.id)"
                        >
                          <v-icon size="16">mdi-close</v-icon>
                        </v-btn>
                      </template>
                    </v-list-item>
                  </v-list>
                  <div v-if="g.truncated" class="zt-loading-more pa-2 text-center">
                    还有 {{ g.records.length - g.visibleRecords.length }} 条，下拉加载…
                  </div>
                </div>
              </div>
              <div v-if="hasMoreRecords" class="zt-loading-more pa-2 text-center">
                <v-progress-circular indeterminate size="18" color="primary"></v-progress-circular>
              </div>
            </div>
          </div>
        </v-card>
      </v-col>

      <!-- 右栏：详情面板，小屏占满整行（上下结构），大屏 7:5 -->
      <v-col cols="12" md="7">
        <v-card class="zt-card-bg zt-detail-card">
          <v-card-text class="pa-0">
            <v-progress-circular
              v-if="detailLoading"
              indeterminate
              class="zt-detail-loading"
            ></v-progress-circular>
            <div v-else-if="!detail" class="zt-empty pa-6">
              点击左侧记录查看详情
            </div>
            <div v-else class="pa-4">
              <div class="d-flex align-center mb-3 flex-wrap">
                <div class="flex-grow-1">
                  <div class="zt-detail-title text-subtitle-1">{{ detail.file_name }}</div>
                  <div class="zt-detail-meta text-body-2">
                    检查时间：{{ detail.check_time }}
                    <v-chip
                      size="x-small"
                      variant="tonal"
                      :color="detail.status === 'ok' ? 'success' : (detail.status === 'pending' || detail.status === 'partial_check' ? 'warning' : 'error')"
                      class="ml-2"
                    >
                      {{ detail.status === 'ok' ? '字体完整（已逐字符验证）' : (detail.status === 'pending' ? '待检查' : (detail.status === 'partial_check' ? '未验证字形（仅名称匹配）' : `缺 ${detail.missing_count} 个字体`)) }}
                    </v-chip>
                    <v-chip
                      v-if="detail.subsetted"
                      size="x-small"
                      color="info"
                      variant="tonal"
                      class="ml-1"
                    >
                      已内嵌字体
                    </v-chip>
                  </div>
                </div>
              </div>

              <v-alert
                v-if="detail.status === 'pending'"
                type="warning"
                density="compact"
                class="mb-3"
              >
                该字幕尚未检查，点击「检查」按钮对比字体库。
              </v-alert>

              <!-- 未验证字形（partial_check）：仅名称匹配，未做逐字符覆盖验证 -->
              <v-alert
                v-if="detail.status === 'partial_check'"
                type="warning"
                variant="tonal"
                density="compact"
                class="mb-3"
              >
                <v-icon size="16" class="mr-1">mdi-help-circle-outline</v-icon>
                本次检查未完成字形级验证（字体名在库内但未逐字符比对 cmap 覆盖，常见于字体索引未构建、字幕无有效对白或解析异常）。
                如需准确结论，请先确认字体库目录已配置并重建索引，再点击「检查」重新验证。
              </v-alert>

              <!-- 子集化提示：ASS 已内嵌（子集化）字体 -->
              <v-alert
                v-if="detail.subsetted"
                type="success"
                variant="tonal"
                density="compact"
                class="mb-3"
              >
                <v-icon size="16" class="mr-1">mdi-sticker-check-outline</v-icon>
                该字幕已内嵌（子集化）字体，播放时无需另行安装字体
              </v-alert>

              <v-divider class="mb-3"></v-divider>

              <template v-if="detail.status !== 'pending'">
              <!-- 已内嵌（子集化）字幕：自带字体，不报缺失，只提示并列出全部字体 -->
              <div v-if="detail.subsetted" class="mb-4 zt-inline-ok">
                <v-icon start size="16" color="success">mdi-sticker-check-outline</v-icon>
                <span class="zt-section-label">该字幕已内嵌（子集化）字体，无需检查缺失字体</span>
              </div>
              <template v-else>
              <div class="mb-2">
                <v-icon start size="16" color="error">mdi-alert-decagram-outline</v-icon>
                <span class="zt-section-label">缺失字体（{{ detail.missing_fonts?.length || 0 }}）</span>
              </div>
              <div class="zt-missing-list mb-4">
                <div v-if="!(detail.missing_fonts?.length)" class="zt-empty2">
                  <v-icon color="success" size="16" class="mr-1">mdi-check-circle</v-icon>
                  没有缺失字体
                </div>
                <v-chip
                  v-for="f in detail.missing_fonts || []"
                  :key="f"
                  size="small"
                  color="error"
                  variant="tonal"
                  class="ma-1 zt-missing-chip"
                >
                  <div class="zt-missing-chip-body">
                    <span>{{ f }}</span>
                    <span v-if="missingCharText(f)" class="zt-missing-chars">
                      缺 {{ missingCharCount(f) }} 字符：{{ missingCharText(f) }}
                    </span>
                  </div>
                  <v-icon size="14" class="ml-1 zt-search-icon" @click="goFontSearch(f)">
                    mdi-magnify
                  </v-icon>
                </v-chip>
              </div>
              </template>

              <div>
                <v-icon start size="16">mdi-format-font</v-icon>
                <span class="zt-section-label">使用的全部字体（{{ detail.all_fonts?.length || 0 }}）</span>
              </div>
              <!-- 字体库已收录 → 亮绿光；缺失 → 正常显示 -->
              <div class="zt-all-list">
                <v-chip
                  v-for="f in detail.all_fonts || []"
                  :key="f.name || f"
                  size="small"
                  variant="tonal"
                  class="ma-1"
                  :class="{ 'zt-in-lib': f.in_lib }"
                >
                  <template v-if="f.in_lib">
                    <v-icon size="14" class="mr-1 text-success">mdi-check-circle</v-icon>
                  </template>
                  {{ f.name || f }}
                </v-chip>
              </div>
              </template>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 全部清空确认：上传的临时副本一并清理，监控/媒体库原字幕不动 -->
    <v-dialog v-model="clearConfirm" max-width="440">
      <v-card>
        <v-card-title class="text-h6">清空全部检查记录？</v-card-title>
        <v-card-text>
          将删除全部 {{ records.length }} 条检查记录，并清理上传的临时副本。
          监控目录与媒体库里的原字幕只删记录、不动文件；字体库与子集化记录不受影响。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="clearConfirm = false">取消</v-btn>
          <v-btn color="error" variant="tonal" :loading="clearing" @click="clearAll">全部清空</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除整组确认：上传的临时副本一并清理，监控/媒体库原字幕不动 -->
    <v-dialog v-model="groupConfirm" max-width="440">
      <v-card>
        <v-card-title class="text-h6">删除「{{ groupTarget?.label || '' }}」整组？</v-card-title>
        <v-card-text>
          将删除本组 {{ groupTarget?.records?.length || 0 }} 条检查记录，并清理上传的临时副本。
          监控目录与媒体库里的原字幕只删记录、不动文件；字体库与子集化记录不受影响。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="groupConfirm = false">取消</v-btn>
          <v-btn color="error" variant="tonal" :loading="groupDeleting" @click="confirmDeleteGroup">删除整组</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.zt-tip {
  opacity: 0.6;
}
.zt-match-source {
  font-size: 12px;
  opacity: 0.65;
}
.zt-list-card {
  height: 640px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.zt-detail-card {
  height: 640px;
  overflow: auto;
}
.zt-list-body {
  min-height: 60px;
  flex: 1 1 auto;
  overflow-y: auto;
  overscroll-behavior: contain;
}
/* 列表卡片标题行：与子集化结果卡片保持同一套标题 / 筛选栏样式 */
.zt-card-title-row {
  display: flex;
  align-items: center;
}
.zt-card-title-row .zt-title-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.zt-filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}
.zt-filter-status {
  width: 130px;
  flex-shrink: 0;
}
.zt-filter-search {
  flex: 1 1 auto;
  min-width: 120px;
}
@media (max-width: 959.95px) {
  .zt-card-title-row {
    flex-wrap: wrap;
    row-gap: 6px;
  }
}
/* ===== 分组抽屉：组头按状态着色，点击折叠/展开 ===== */
.zt-group {
  --zt-group-color: 158, 158, 158;
  margin-bottom: 8px;
  border: 1px solid rgba(var(--zt-group-color), 0.35);
  border-left: 3px solid rgba(var(--zt-group-color), 0.9);
  border-radius: 8px;
  background: rgba(var(--zt-group-color), 0.06);
  overflow: hidden;
}
.zt-group-success { --zt-group-color: 76, 175, 80; }
.zt-group-warning { --zt-group-color: 255, 152, 0; }
.zt-group-error   { --zt-group-color: 244, 67, 54; }
.zt-group-grey    { --zt-group-color: 158, 158, 158; }
.zt-group-head {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  cursor: pointer;
  user-select: none;
}
.zt-group-head:hover {
  background: rgba(var(--zt-group-color), 0.1);
}
.zt-group-name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 13.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.zt-group-count {
  flex: 0 0 auto;
  font-size: 12px;
  opacity: 0.65;
}
.zt-group-stats,
.zt-group-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}
.zt-group-body {
  border-top: 1px dashed rgba(var(--zt-group-color), 0.3);
}
/* 左栏只有半屏宽：窄屏时组内状态计数收起，避免组头挤成两行 */
@media (max-width: 959.95px) {
  .zt-group-stats { display: none; }
}
.zt-loading-more {
  font-size: 12px;
  opacity: 0.7;
}
.zt-record-name {
  font-weight: 500;
}
.zt-record-meta {
  font-size: 11px;
  opacity: 0.7;
}
.zt-record-item {
  cursor: pointer;
}
.zt-detail-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
.zt-detail-title {
  font-weight: 600;
}
.zt-detail-meta {
  opacity: 0.75;
}
.zt-section-label {
  font-size: 13px;
  font-weight: 600;
}
.zt-empty,
.zt-empty2 {
  font-size: 13px;
  opacity: 0.6;
  text-align: center;
}
.zt-search-icon {
  cursor: pointer;
}
/* 全部字体：字体库已收录 → 绿光 */
.zt-in-lib {
  color: #81c784 !important;
  border-color: rgba(129, 199, 132, 0.55) !important;
  box-shadow: 0 0 8px rgba(76, 175, 80, 0.45) !important;
}
.zt-card-title {
  font-size: 15px;
  font-weight: 600;
}
/* 缺失字体逐字符明细：名称 + 缺失字符行 */
.zt-missing-chip {
  height: auto !important;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}
.zt-missing-chip-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.35;
}
.zt-missing-chars {
  font-size: 11px;
  font-family: monospace;
  opacity: 0.8;
  word-break: break-all;
  max-width: 100%;
}
</style>