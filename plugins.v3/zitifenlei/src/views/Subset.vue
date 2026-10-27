<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

// ===== 子集化引擎状态（内置 HarfBuzz）=====
const status = ref({ engine: 'harfbuzz', hb_ok: false, font_index: {}, lib_dir: '' })
const statusLoaded = ref(false)
const engineReady = computed(() => !!status.value.hb_ok)
const indexReady = computed(() => !!status.value.font_index?.faces)
const indexCount = computed(() => status.value.font_index?.faces || 0)
// 文件数：TTC/OTC 一个文件含多个 face，face 数必然大于文件数，两个口径并列显示
const indexFileCount = computed(() => status.value.font_index?.files || 0)
// 索引重建中（全部重建/启动轻检/每周核对都可能触发）：UI 明确显示进度，
// 否则只看到「（—」会以为索引坏了
const indexRebuilding = computed(() => !!status.value.rebuilding)
const indexProgressText = computed(() => {
  const p = status.value.rebuild_progress || {}
  const done = Number(p.done || 0)
  const total = Number(p.total || 0)
  return total > 0 ? `（已处理 ${done}/${total}）` : ''
})

// ===== 左栏：待处理 =====
const pendingList = ref([])
const loadingPending = ref(false)
const uploadRef = ref(null)
const uploading = ref(false)
// 处理中：按钮转圈禁用，防重复点击
const scanning = ref(false)

// ===== 右栏：结果 =====
const records = ref([])
const loadingRecords = ref(false)
const downloadingId = ref(null)
const recordTotal = ref(0)
const retriableCount = ref(0)
const recordPage = ref(1)
const recordLimit = 20
const recordReachedEnd = ref(false)
// 筛选：状态下拉 + 文件名搜索
const filterStatus = ref('')
const recordSearch = ref('')
const statusFilterOptions = [
  { title: '全部状态', value: '' },
  { title: '成功', value: 'success' },
  { title: '可重试', value: 'retryable' },
  { title: '缺字体', value: 'missing' },
  { title: '跳过', value: 'skipped' },
  { title: '失败', value: 'error' },
]

async function loadStatus() {
  try {
    status.value = await apiModule.get(props.api, '/subset/index')
    // 重建中（可能是本页触发，也可能是启动轻检/周核对）：开启 2 秒快轮询看进度
    if (status.value.rebuilding) startRebuildPolling()
    else stopRebuildPolling()
  } catch (e) { /* 忽略 */ } finally {
    statusLoaded.value = true
  }
}
// 重建进度快轮询（2 秒）：重建结束自动停，页面切走也会停
let rebuildPollTimer = null
function startRebuildPolling() {
  if (rebuildPollTimer) return
  rebuildPollTimer = setInterval(async () => {
    try {
      status.value = await apiModule.get(props.api, '/subset/index')
    } catch (e) { /* 忽略单次失败 */ }
    if (!status.value.rebuilding) stopRebuildPolling()
  }, 2000)
}
function stopRebuildPolling() {
  if (rebuildPollTimer) clearInterval(rebuildPollTimer)
  rebuildPollTimer = null
}
// 全部重建字体库：清空索引后逐文件重新解析（日常归档/入库是增量增/减，不走这里）
const rebuildingIndex = ref(false)
const rebuildConfirm = ref(false)
async function rebuildIndex() {
  if (rebuildingIndex.value) return
  rebuildingIndex.value = true
  rebuildConfirm.value = false
  // 重建是同步阻塞接口：先开快轮询，让顶部状态条在等待期间就能显示「正在重建 / 已处理 N/M」
  startRebuildPolling()
  try {
    await apiModule.post(props.api, '/subset/rebuild_index')
    emit('notify', '字体库已全部重建（逐文件重新解析）', 'success')
    emit('action', { type: 'subset_done' })
  } catch (e) {
    emit('notify', e.message || '全部重建失败')
  } finally {
    rebuildingIndex.value = false
    stopRebuildPolling()
    await loadStatus()
  }
}
async function loadPending() {
  loadingPending.value = true
  try {
    pendingList.value = await apiModule.get(props.api, '/subset/pending')
  } catch (e) {
    emit('notify', e.message || '读取待处理列表失败')
  } finally {
    loadingPending.value = false
  }
}
async function loadRecords(reset = false, force = false) {
  // 30 秒轮询（refreshCurrentPage）会占住这把锁：用户操作后的强制刷新不能被它吞掉，
  // 否则子集化/删除完成时列表停在旧数据，看起来像没生效（必须等下一轮轮询才补上）
  if (loadingRecords.value && !force) return
  if (reset) {
    recordPage.value = 1
    recordReachedEnd.value = false
    records.value = []
  } else if (recordReachedEnd.value) {
    return
  }
  loadingRecords.value = true
  try {
    const data = await apiModule.get(props.api, '/subset/records', {
      status: filterStatus.value,
      search: recordSearch.value,
      page: recordPage.value,
      limit: recordLimit,
    })
    const list = (data && data.list) || []
    recordTotal.value = (data && data.total) || 0
    if (typeof data?.retriable === 'number') retriableCount.value = data.retriable
    records.value = reset ? list : [...records.value, ...list]
    if (records.value.length >= recordTotal.value || !list.length) {
      recordReachedEnd.value = true
    }
  } catch (e) {
    emit('notify', e.message || '读取子集化记录失败')
  } finally {
    loadingRecords.value = false
  }
}

// Q7 修复：刷新列表但保持当前页码（替换当前页对应区间的数据）。
// 与 loadRecords(reset=true) 的区别：不重置分页回第 1 页；
// 与 loadRecords(false) 的区别：loadRecords(false) 是"追加下一页"语义，
// 直接用于轮询会重复追加同一页数据。
async function refreshCurrentPage() {
  if (loadingRecords.value) return
  loadingRecords.value = true
  try {
    const data = await apiModule.get(props.api, '/subset/records', {
      status: filterStatus.value,
      search: recordSearch.value,
      page: recordPage.value,
      limit: recordLimit,
    })
    const list = (data && data.list) || []
    recordTotal.value = (data && data.total) || 0
    if (typeof data?.retriable === 'number') retriableCount.value = data.retriable
    // 用最新当前页数据替换 records 中 (recordPage-1)*limit 起的区间，
    // 保留已加载的前面各页，不追加不重置
    const idx = (recordPage.value - 1) * recordLimit
    records.value = [...records.value.slice(0, idx), ...list]
    if (records.value.length >= recordTotal.value || !list.length) {
      recordReachedEnd.value = true
    }
  } catch (e) {
    emit('notify', e.message || '刷新子集化记录失败')
  } finally {
    loadingRecords.value = false
  }
}

// 筛选变化：防抖后回到第 1 页重拉
let filterTimer = null
watch([filterStatus, recordSearch], () => {
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(() => loadRecords(true), 250)
})

// 滚动到底加载下一页
function onRecordsScroll(e) {
  const el = e.target
  if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
    recordPage.value += 1
    loadRecords()
  }
}

// 索引时间文案：优先显示「构建」时间；索引只由逐文件增量入库建立过时没有构建时间，
// 退化为「最近更新」（font_files.indexed_at 最大值），避免只显示一个空破折号
function indexTimeText() {
  const fi = status.value?.font_index || {}
  if (fi.last_rebuild) return `构建 ${fi.last_rebuild}`
  if (fi.last_indexed_at) return `最近更新 ${fi.last_indexed_at}`
  return indexReady.value ? '构建时间未记录' : '—'
}

function statusColor(r) {
  if (r.status === 'success') return 'success'
  if (r.status === 'missing' && r.retryable) return 'primary'
  if (r.status === 'missing') return 'warning'
  if (r.status === 'skipped') return 'info'
  return 'error'
}
function statusText(r) {
  if (r.status === 'success') return '成功'
  if (r.status === 'missing' && r.retryable) return '可重试'
  if (r.status === 'missing') return '缺字体'
  if (r.status === 'skipped') return '跳过'
  return '失败'
}

// 上传字幕（多选，进左栏待处理）
async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  const BATCH = 5
  let total = 0
  uploading.value = true
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH)
      const form = new FormData()
      for (const file of chunk) form.append('file', file)
      const res = await props.api.post(
        'plugin/Zitifenlei/subset/pending/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      const body = res?.data ?? res
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '上传失败'}`)
        break
      } else {
        total += (body?.data?.count ?? chunk.length)
      }
    }
    emit('notify', `已加入待处理 ${total} 个字幕`, 'success')
    loadPending()
  } catch (e) {
    emit('notify', e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

// 移除单条待处理（x）
async function removePending(id) {
  try {
    await apiModule.post(props.api, `/subset/pending/remove/${id}`)
    pendingList.value = pendingList.value.filter(p => p.id !== id)
    emit('notify', '已移除待处理', 'success')
  } catch (e) {
    emit('notify', e.message || '移除失败')
  }
}

async function clearPending() {
  try {
    await apiModule.del(props.api, '/subset/pending/clear')
    pendingList.value = []
    emit('notify', '已清空待处理', 'success')
  } catch (e) {
    emit('notify', e.message || '清空失败')
  }
}

// 全量子集化：处理左栏全部待处理
async function scanAll() {
  if (scanning.value) return
  scanning.value = true
  // 点击即提示：子集化是同步长任务，先给反馈避免用户以为没点上而重复点击
  emit('notify', '正在全量子集化，请勿重复点击', 'info')
  try {
    const res = await apiModule.post(props.api, '/subset/all')
    const s = res || {}
    emit('notify', `全量子集化完成：成功 ${s.success ?? 0}，跳过 ${s.skipped ?? 0}，缺字体 ${s.missing ?? 0}，失败 ${s.error ?? 0}`, 'success')
    await loadRecords(true, true)
    await loadPending()
    await loadStatus()
    emit('action', { type: 'subset_done' })
  } catch (e) {
    emit('notify', e.message || '全量子集化失败')
  } finally {
    scanning.value = false
  }
}

// 状态标签点击：缺字体（未补齐）/失败 → 去缺失字体页处理；可重试不点击（直接点顶部「重试失败」）
function onStatusTagClick(r) {
  if (!props.enabled) return
  if (r.status === 'missing' && !r.retryable) {
    emit('action', { type: 'goto_missing' })
  } else if (r.status === 'error') {
    emit('action', { type: 'goto_missing' })
  }
}

// 重试失败/缺字体的记录（如 MP 入库缺字体，补字后可重跑）
const retrying = ref(false)
function hasRetriable() {
  return retriableCount.value > 0
}
async function retryFailed() {
  if (retrying.value) return
  retrying.value = true
  try {
    const res = await apiModule.post(props.api, '/subset/retry')
    const s = res || {}
    emit('notify', `重试完成：成功 ${s.success ?? 0}，缺字体 ${s.missing ?? 0}，失败 ${s.error ?? 0}`, 'success')
    await loadRecords(true, true)
    await loadStatus()
    emit('action', { type: 'subset_done' })
  } catch (e) {
    emit('notify', e.message || '重试失败')
  } finally {
    retrying.value = false
  }
}

// 下载结果文件（base64 → blob）
// Q10 修复：downloadRecord 返回明确状态（'ok'/'none'/'missing'/'error'/'busy'），
// 不再静默 return，调用方（downloadAll / 单条按钮）可按状态准确统计。
async function downloadRecord(r) {
  if (downloadingId.value) return 'busy'
  if (!r.out_file) {
    emit('notify', '无输出文件', 'warning')
    return 'none'
  }
  downloadingId.value = r.id
  try {
    const st = await _doDownload(r)
    if (st !== 'ok') emit('notify', st === 'missing' ? '结果文件不存在' : '无输出文件', 'warning')
    return st
  } catch (e) {
    emit('notify', e.message || '下载失败')
    return 'error'
  } finally {
    downloadingId.value = null
  }
}

// 内部下载执行：取 base64 → 触发浏览器下载。不占单槽 downloadingId，
// 供「全部下载」并发池并行调用（Q19）。
async function _doDownload(r) {
  if (!r.out_file) return 'none'
  const res = await apiModule.get(props.api, '/subset/download', { id: r.id })
  if (!res?.data) return 'missing'
  const bytes = Uint8Array.from(atob(res.data), c => c.charCodeAt(0))
  const blob = new Blob([bytes])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = res.name || (r.file_name.replace(/\.ass$/i, '') + '.ziti.ass')
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return 'ok'
}

// 可批量下载的记录：已加载的成功且带输出文件
const downloadableRecords = computed(() =>
  records.value.filter(r => r.status === 'success' && r.out_file)
)

// 全部下载：按当前筛选（状态下拉+名称搜索）拉取全部成功成品；
// Q19 修复：限并发 3 的小并发池（文档建议 2~3 并发更快），替代串行逐个 await；
// Q10 修复：按每个记录的返回状态准确统计成功/失败，不再把"被守卫跳过"计入成功。
// 未选筛选则下载全部分页的成功成品（limit=0 后端返回当前筛选下全部记录，不限页）
const downloadAllBusy = ref(false)
async function downloadAll() {
  if (downloadAllBusy.value) return
  // 有单个下载正在进行时直接拒绝，避免与并发池混跑
  if (downloadingId.value) {
    emit('notify', '有下载正在进行，请稍候', 'warning')
    return
  }
  downloadAllBusy.value = true
  try {
    const data = await apiModule.get(props.api, '/subset/records', {
      status: filterStatus.value,
      search: recordSearch.value,
      page: 1,
      limit: 0, // 0 = 当前筛选下全部记录（含未加载的后续页）
    })
    const targets = ((data && data.list) || []).filter(r => r.status === 'success' && r.out_file)
    if (!targets.length) {
      emit('notify', '当前筛选下没有可下载的成功成品', 'warning')
      return
    }
    // 小并发池：最多 3 个并发下载
    const stats = { ok: 0, fail: 0, missing: 0 }
    let head = 0
    const worker = async () => {
      while (head < targets.length) {
        const r = targets[head++]
        try {
          const st = await _doDownload(r)
          if (st === 'ok') stats.ok += 1
          else if (st === 'missing') stats.missing += 1
          else stats.fail += 1
        } catch (e) {
          stats.fail += 1
        }
      }
    }
    await Promise.all([worker(), worker(), worker()])
    const failed = stats.fail + stats.missing
    if (failed) {
      emit('notify', `已下载 ${stats.ok} 个，${stats.fail} 个失败${stats.missing ? `，${stats.missing} 个文件缺失` : ''}`, stats.ok ? 'success' : 'warning')
    } else {
      emit('notify', `已下载 ${stats.ok} 个结果文件`, 'success')
    }
  } catch (e) {
    emit('notify', e.message || '获取结果失败')
  } finally {
    downloadAllBusy.value = false
  }
}

async function deleteRecord(id) {
  try {
    await apiModule.post(props.api, `/subset/delete/${id}`)
    emit('notify', '已删除记录', 'success')
    // 删除后软刷新回第 1 页（计数、分页、retriable 一并同步）
    await loadRecords(true, true)
  } catch (e) {
    emit('notify', e.message || '删除失败')
  }
}

async function clearRecords() {
  try {
    await apiModule.del(props.api, '/subset/clear')
    await loadRecords(true, true)
    emit('notify', '已清空子集化记录', 'success')
  } catch (e) {
    emit('notify', e.message || '清空失败')
  }
}

onMounted(() => {
  loadStatus()
  loadPending()
  loadRecords()
  startPolling()
})
// keep-alive 缓存场景：切回时恢复轮询并重拉数据（Q1 修复；Q14 后切 Tab
// 不再由 Page 广播刷新键，各视图自查自刷）
onActivated(() => {
  loadStatus()
  loadPending()
  refreshCurrentPage()
  startPolling()
})
// 切走（进入 keep-alive 缓存）时停止轮询，避免后台不可见视图持续打接口（Q1 修复）
onDeactivated(() => {
  stopPolling()
})
onUnmounted(() => stopPolling())

let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    loadPending()
    // Q7 修复：轮询刷新保持当前页码（替换当前页区间），不再强制回第 1 页，
    // 避免翻页浏览时每 30 秒被拉回首页；也避免 loadRecords(false) 的
    // 追加语义在轮询里造成重复数据
    refreshCurrentPage()
    loadStatus()
  }, 30000)
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  stopRebuildPolling()
}
</script>

<template>
  <div class="zt-subset">
    <!-- 顶部操作栏 -->
    <div class="zt-topbar">
      <v-btn
        variant="tonal"
        color="primary"
        :disabled="!enabled || uploading"
        :loading="uploading"
        title="上传字幕到「待处理」（支持 .ass 与 .zip 压缩包）"
        @click="uploadRef?.click()"
      >
        <v-icon start size="18">mdi-upload</v-icon>
        上传字幕
      </v-btn>
      <input
        ref="uploadRef"
        type="file"
        accept=".ass,.ASS,.zip"
        multiple
        style="display: none"
        @change="handleUpload"
      />
      <v-btn
        color="primary"
        :disabled="!enabled || scanning || !pendingList.length"
        :loading="scanning"
        title="处理「待处理」中的全部字幕（子集化并内嵌字体）"
        @click="scanAll"
      >
        <v-icon start size="18">mdi-magnify-scan</v-icon>
        全量子集化
      </v-btn>
      <v-btn
        color="warning"
        variant="tonal"
        :disabled="!enabled || retrying || !hasRetriable()"
        :loading="retrying"
        title="对结果区中失败/缺字体的字幕重新子集化（补好缺失字体后使用）"
        @click="retryFailed"
      >
        <v-icon start size="18">mdi-refresh</v-icon>
        重试失败
      </v-btn>
      <v-btn
        variant="tonal"
        :disabled="!enabled || !pendingList.length"
        title="清空左栏待处理"
        @click="clearPending"
      >
        <v-icon start size="18">mdi-delete-sweep-outline</v-icon>
        清空待处理
      </v-btn>
      <v-btn
        variant="tonal"
        :disabled="!enabled || !records.length"
        title="清空全部子集化记录"
        @click="clearRecords"
      >
        <v-icon start size="18">mdi-trash-can-outline</v-icon>
        清空记录
      </v-btn>
      <v-spacer></v-spacer>
      <span class="zt-status-hint text-body-2">
        <v-icon :size="15" :color="indexRebuilding ? 'info' : (indexReady ? 'success' : 'warning')">
          {{ indexRebuilding ? 'mdi-database-sync-outline' : (indexReady ? 'mdi-database-check' : 'mdi-database-off') }}
        </v-icon>
        <template v-if="indexRebuilding">
          字体库索引：正在重建…{{ indexProgressText }}
        </template>
        <template v-else>
          字体库索引：{{ indexReady ? `${indexFileCount} 个文件 / ${indexCount} 个 face` : '未构建' }}（{{ indexTimeText() }}）
        </template>
      </span>
      <v-btn
        variant="text"
        size="small"
        color="primary"
        class="ml-2"
        :disabled="!enabled || indexRebuilding"
        :loading="rebuildingIndex || indexRebuilding"
        title="清空索引后逐文件重新解析字体库（全部重建，非增量；耗时取决于字体数量）"
        @click="rebuildConfirm = true"
      >
        <v-icon start size="15">mdi-database-refresh</v-icon>
        全部重建
      </v-btn>
    </div>

    <v-alert
      v-if="statusLoaded && !engineReady"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3"
    >
      HarfBuzz 子集化引擎未就绪，子集化不可用。请到「仪表盘 → 依赖」中重新安装 uharfbuzz。
    </v-alert>

    <v-row no-gutters class="zt-subset-row">
      <!-- 左栏：待处理 -->
      <v-col cols="12" md="5">
        <v-card class="zt-card-bg zt-list-card">
          <v-card-title class="zt-card-title">
            <v-icon start size="18">mdi-tray-full</v-icon>
            待处理（{{ pendingList.length }}）
          </v-card-title>
          <v-divider></v-divider>
          <v-progress-linear v-if="loadingPending" indeterminate color="primary"></v-progress-linear>
          <div v-if="!loadingPending && !pendingList.length" class="zt-empty pa-6">
            暂无待处理字幕<br />
            <span class="zt-empty-sub">上传字幕，或设置开启「入库后自动子集化」+「目录自动收集」关闭时自动收集</span>
          </div>
          <div v-else class="zt-list-body">
            <v-list density="compact" class="pa-0">
              <v-list-item v-for="p in pendingList" :key="p.id" lines="two">
                <template #prepend>
                  <v-icon color="primary" size="18">mdi-subtitles-outline</v-icon>
                </template>
                <v-list-item-title class="zt-font-name">{{ p.file_name }}</v-list-item-title>
                <v-list-item-subtitle class="zt-font-meta">
                  {{ p.source === 'watch' ? '目录监控' : '手动上传' }} · {{ p.created_at }}
                </v-list-item-subtitle>
                <template #append>
                  <v-btn size="small" variant="text" icon :disabled="!enabled" title="移除该项" @click="removePending(p.id)">
                    <v-icon size="16">mdi-close</v-icon>
                  </v-btn>
                </template>
              </v-list-item>
            </v-list>
          </div>
        </v-card>
      </v-col>

      <!-- 右栏：结果 -->
      <v-col cols="12" md="7">
        <v-card class="zt-card-bg zt-list-card">
          <v-card-title class="zt-card-title zt-card-title-row">
            <v-icon start size="18">mdi-history</v-icon>
            <span class="zt-title-text">结果（{{ records.length }}/{{ recordTotal }}）</span>
            <v-spacer></v-spacer>
            <v-btn
              class="zt-title-action"
              size="small"
              variant="tonal"
              color="success"
              :disabled="!enabled || downloadAllBusy || !downloadableRecords.length"
              :loading="downloadAllBusy"
              title="下载当前列表全部成功成品字幕"
              @click="downloadAll"
            >
              <v-icon start size="15">mdi-download-multiple</v-icon>
              全部下载
            </v-btn>
          </v-card-title>
          <v-divider></v-divider>
          <!-- 筛选栏：状态下拉 + 文件名搜索 -->
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
              v-model="recordSearch"
              density="compact"
              variant="outlined"
              hide-details
              :clearable="!!recordSearch"
              placeholder="搜索字幕名…"
              prepend-inner-icon="mdi-magnify"
              class="zt-filter-search"
            ></v-text-field>
          </div>
          <v-divider></v-divider>
          <v-progress-linear v-if="loadingRecords" indeterminate color="primary"></v-progress-linear>
          <div v-if="!loadingRecords && !records.length" class="zt-empty pa-6">
            暂无{{ filterStatus || recordSearch ? '匹配' : '' }}处理结果<br />
            <span class="zt-empty-sub">处理完成后结果与输出文件在这里展示，可下载</span>
          </div>
          <div v-else class="zt-list-body zt-record-body" @scroll="onRecordsScroll">
            <v-list density="compact" class="pa-0">
              <v-list-item v-for="r in records" :key="r.id" lines="two">
                <template #prepend>
                  <v-chip
                    :color="statusColor(r)"
                    size="x-small"
                    variant="tonal"
                    :title="r.status === 'missing' && !r.retryable ? '缺的字体尚未补齐：点击去「缺失字体」页上传' : (r.status === 'error' ? '处理失败：点击去「缺失字体」页处理' : (r.status === 'missing' && r.retryable ? '缺的字体已入库：点顶部「重试失败」重新子集化' : ''))"
                    :class="{ 'zt-status-link': (r.status === 'missing' && !r.retryable) || r.status === 'error' }"
                    :disabled="!enabled"
                    @click="onStatusTagClick(r)"
                  >{{ statusText(r) }}</v-chip>
                </template>
                <v-list-item-title class="zt-font-name">{{ r.file_name }}</v-list-item-title>
                <v-list-item-subtitle class="zt-font-meta">
                  <template v-if="r.reason">{{ r.reason }}</template>
                  <template v-else-if="r.out_file">{{ r.out_file }}</template>
                  <template v-else>—</template>
                  <span v-if="r.created_at" class="ml-2">{{ r.created_at }}</span>
                </v-list-item-subtitle>
                <!-- 右侧操作区：成功→下载；缺字体/失败→无（左侧标签即可跳转）；跳过→无 -->
                <template #append>
                  <v-btn
                    v-if="r.status === 'success' && r.out_file"
                    size="x-small"
                    variant="tonal"
                    color="success"
                    class="mr-1"
                    title="下载结果文件"
                    :disabled="!enabled || downloadingId === r.id"
                    :loading="downloadingId === r.id"
                    @click="downloadRecord(r)"
                  >
                    <v-icon start size="14">mdi-download</v-icon>
                    下载
                  </v-btn>
                  <v-btn size="small" variant="text" icon :disabled="!enabled" title="删除该记录" @click="deleteRecord(r.id)">
                    <v-icon size="16">mdi-close</v-icon>
                  </v-btn>
                </template>
              </v-list-item>
            </v-list>
            <div v-if="!recordReachedEnd && records.length" class="zt-loading-more pa-2 text-center">
              <v-progress-circular indeterminate size="18" color="primary"></v-progress-circular>
            </div>
            <div v-else-if="recordReachedEnd && records.length" class="zt-loading-more pa-2 text-center text-body-2 zt-font-meta">
              已加载全部
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- 全部重建确认：日常归档/入库是增量/减量，只有这里清空索引逐文件重解析 -->
    <v-dialog v-model="rebuildConfirm" max-width="440">
      <v-card>
        <v-card-title class="text-h6">全部重建字体库？</v-card-title>
        <v-card-text>
          将清空现有字体索引，再逐文件重新解析整个字体库（生成 face/别名/字符覆盖）。
          日常归档与入库仍是增量/减量，不需要用这里。耗时取决于字体数量，期间检索可能变慢。
          人工映射与字幕缺失快照不受影响。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="rebuildConfirm = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" :loading="rebuildingIndex" @click="rebuildIndex">开始重建</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.zt-topbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.zt-list-card {
  height: 620px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.zt-list-body {
  min-height: 60px;
  flex: 1 1 auto;
  overflow-y: auto;
}
/* 结果区筛选栏：状态下拉 + 搜索框 */
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
.zt-record-body {
  min-height: 60px;
  flex: 1 1 auto;
  overflow-y: auto;
}
.zt-loading-more {
  font-size: 12px;
  opacity: 0.7;
}
.zt-card-title {
  font-size: 15px;
  font-weight: 600;
}
/* 结果卡片标题行：Vuetify 的 v-card-title 默认 display:block，放 v-spacer + 按钮会掉到第二行。
   PC 上改成单行 flex，按钮与「结果」同排靠右；手机（<md）时按钮换到下一排、占满整行。 */
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
@media (max-width: 959.95px) {
  .zt-card-title-row {
    flex-wrap: wrap;
    row-gap: 6px;
  }
  .zt-card-title-row .zt-title-action {
    width: 100%;
    margin-inline-start: 0 !important;
  }
}
.zt-empty {
  font-size: 13px;
  opacity: 0.6;
  text-align: center;
  line-height: 1.8;
}
.zt-empty-sub {
  font-size: 12px;
  opacity: 0.55;
}
.zt-font-name {
  font-size: 14px;
  font-weight: 500;
}
/* 缺字体/失败状态标签可点击（跳缺失字体页）：手型 + 虚线提示 */
.zt-status-link {
  cursor: pointer;
  text-decoration: underline dashed;
  text-underline-offset: 2px;
}
.zt-status-link:hover {
  filter: brightness(1.15);
}
.zt-font-meta {
  font-size: 12px;
  opacity: 0.7;
  word-break: break-all;
}
.zt-status-hint {
  opacity: 0.75;
  white-space: nowrap;
}
</style>