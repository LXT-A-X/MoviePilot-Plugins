<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

// ===== assfonts 状态 =====
const status = ref({ binary_ok: false, binary_path: '', index: { exists: false, count: 0, mtime: 0, size: 0 }, lib_dir: '' })

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
  } catch (e) { /* 忽略 */ }
}
// 重建 assfonts 字体索引：新归档/删减字体后，让检查与子集化按最新字体库口径比对
const rebuildingIndex = ref(false)
async function rebuildIndex() {
  if (rebuildingIndex.value) return
  rebuildingIndex.value = true
  try {
    await apiModule.post(props.api, '/subset/rebuild_index')
    emit('notify', 'assfonts 索引已重建，检查/子集化将按新字体库口径比对', 'success')
    await loadStatus()
    emit('action', { type: 'subset_done' })
  } catch (e) {
    emit('notify', e.message || '重建索引失败')
  } finally {
    rebuildingIndex.value = false
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
async function loadRecords(reset = false) {
  if (loadingRecords.value) return
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

function indexTime() {
  const t = status.value?.index?.mtime
  if (!t) return ''
  const d = new Date(t * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
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
  try {
    const res = await apiModule.post(props.api, '/subset/all')
    const s = res || {}
    emit('notify', `全量子集化完成：成功 ${s.success ?? 0}，跳过 ${s.skipped ?? 0}，缺字体 ${s.missing ?? 0}，失败 ${s.error ?? 0}`, 'success')
    await loadRecords(true)
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
    await loadRecords(true)
    await loadStatus()
    emit('action', { type: 'subset_done' })
  } catch (e) {
    emit('notify', e.message || '重试失败')
  } finally {
    retrying.value = false
  }
}

// 下载结果文件（base64 → blob）
async function downloadRecord(r) {
  if (downloadingId.value) return
  if (!r.out_file) {
    emit('notify', '无输出文件', 'warning')
    return
  }
  downloadingId.value = r.id
  try {
    const res = await apiModule.get(props.api, '/subset/download', { id: r.id })
    if (!res?.data) {
      emit('notify', '结果文件不存在', 'warning')
      return
    }
    const bytes = Uint8Array.from(atob(res.data), c => c.charCodeAt(0))
    const blob = new Blob([bytes])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = res.name || (r.file_name.replace(/\.ass$/i, '') + '.assfonts.ass')
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    emit('notify', e.message || '下载失败')
  } finally {
    downloadingId.value = null
  }
}

// 可批量下载的记录：已加载的成功且带输出文件
const downloadableRecords = computed(() =>
  records.value.filter(r => r.status === 'success' && r.out_file)
)

// 全部下载：按当前筛选（状态下拉+名称搜索）拉取全部成功成品，串行逐个下载；
// 未选筛选则下载全部分页的成功成品（limit=0 后端返回当前筛选下全部记录，不限页）
const downloadAllBusy = ref(false)
async function downloadAll() {
  if (downloadAllBusy.value) return
  downloadAllBusy.value = true
  let ok = 0
  let fail = 0
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
    for (const r of targets) {
      try {
        await downloadRecord(r)
        ok += 1
      } catch (e) {
        fail += 1
      }
      // 逐条下载间让出事件循环，浏览器同域批量下载逐步放行
      await new Promise(res => setTimeout(res, 350))
    }
    emit('notify', fail ? `已下载 ${ok} 个，${fail} 个失败` : `已下载 ${ok} 个结果文件`, ok ? 'success' : 'warning')
  } catch (e) {
    emit('notify', e.message || '获取结果失败')
  } finally {
    downloadAllBusy.value = false
  }
}

async function deleteRecord(id) {
  try {
    await apiModule.post(props.api, `/subset/delete/${id}`)
    // 删除后软刷新回第 1 页（计数、分页、retriable 一并同步）
    await loadRecords(true)
  } catch (e) {
    emit('notify', e.message || '删除失败')
  }
}

async function clearRecords() {
  try {
    await apiModule.del(props.api, '/subset/clear')
    await loadRecords(true)
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
onUnmounted(() => stopPolling())

let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    loadPending()
    loadRecords(true)
    loadStatus()
  }, 30000)
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
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
        title="上传字幕到「待处理」"
        @click="uploadRef?.click()"
      >
        <v-icon start size="18">mdi-upload</v-icon>
        上传字幕
      </v-btn>
      <input
        ref="uploadRef"
        type="file"
        accept=".ass"
        multiple
        style="display: none"
        @change="handleUpload"
      />
      <v-btn
        color="primary"
        :disabled="!enabled || scanning || !pendingList.length"
        :loading="scanning"
        title="处理「待处理」中的全部字幕（assfonts 子集化并内嵌字体）"
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
        <v-icon :size="15" :color="status.binary_ok ? 'success' : 'error'">
          {{ status.binary_ok ? 'mdi-check-circle' : 'mdi-close-circle' }}
        </v-icon>
        assfonts：{{ status.binary_ok ? '就绪' : '未就绪' }}
        <v-icon :size="15" :color="status.index.exists ? 'success' : 'warning'" class="ml-2">
          {{ status.index.exists ? 'mdi-database-check' : 'mdi-database-off' }}
        </v-icon>
        索引：{{ status.index.exists ? `${status.index.count} 个字体` : '未构建' }}（{{ indexTime() || '—' }}）
      </span>
      <v-btn
        variant="text"
        size="small"
        color="primary"
        class="ml-2"
        :disabled="!enabled || !status.binary_ok"
        :loading="rebuildingIndex"
        title="重新扫描字体库目录生成索引（新归档/删减字体后执行，让检查与子集化口径同步）"
        @click="rebuildIndex"
      >
        <v-icon start size="15">mdi-database-refresh</v-icon>
        重建索引
      </v-btn>
    </div>

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
          <v-card-title class="zt-card-title">
            <v-icon start size="18">mdi-history</v-icon>
            结果（{{ records.length }}/{{ recordTotal }}）
            <v-spacer></v-spacer>
            <v-btn
              size="small"
              variant="tonal"
              color="success"
              :disabled="!enabled || downloadAllBusy || !downloadableRecords.length"
              :loading="downloadAllBusy"
              title="下载当前列表全部成功成品的 .assfonts.ass 文件"
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
              clearable
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