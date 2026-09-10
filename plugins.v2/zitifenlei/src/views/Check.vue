<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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
const total = ref(0)
const page = ref(1)
const limit = 20
const search = ref('')
const loadingList = ref(false)
const reachedEnd = ref(false)

const selectedId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const detailOpen = ref(false)

const uploadRef = ref(null)
const uploading = ref(false)
const deletingId = ref(null)
const clearing = ref(false)
const checkingId = ref(null)
// 全量扫描（字体监控目录字体直接入库）
const scanning = ref(false)

const activeRecord = computed(() =>
  records.value.find(r => r.id === selectedId.value) || null
)

// 检查「匹配基准」：index=assfonts 子集索引（与子集化同一口径，多键匹配更准）；
// db=字体库记录（索引未构建/不可用时的回退口径，可能误报缺失）
// 由 /ass/list 响应顶层 match_source 决定（列表为空时也显示）
const matchSource = ref('')
const matchSourceText = computed(() => {
  const s = matchSource.value || records.value[0]?.match_source || ''
  if (s === 'index') return '子集索引（assfonts fonts.json），与子集化同一口径'
  if (s === 'db') return '字体库记录（索引未构建，去「子集化」页点右上角「重建索引」后可切换为子集索引口径）'
  return ''
})

async function loadRecords(reset = false) {
  if (loadingList.value) return
  if (reset) {
    page.value = 1
    reachedEnd.value = false
    selectedId.value = null
  }
  if (reachedEnd.value) return
  loadingList.value = true
  try {
    const data = await apiModule.get(props.api, '/ass/list', {
      page: page.value,
      limit,
      search: search.value,
    })
    const list = data.list || []
    total.value = data.total || 0
    matchSource.value = data.match_source || list[0]?.match_source || matchSource.value
    records.value = reset ? list : [...records.value, ...list]
    if (!list.length || records.value.length >= total.value) {
      reachedEnd.value = true
    }
    // 注意：不自动选中/不自动加载第一条——右侧只在点击左侧记录时显示
  } catch (e) {
    emit('notify', e.message || '加载检查记录失败')
  } finally {
    loadingList.value = false
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

function loadMore() {
  page.value += 1
  loadRecords()
}

async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 5 个
  const BATCH = 5
  let total = 0
  uploading.value = true
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH)
      const form = new FormData()
      for (const file of chunk) form.append('file', file)
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
    await loadRecords(true)
  } catch (e) {
    emit('notify', e.message || '字幕上传失败')
  } finally {
    uploading.value = false
  }
}

async function checkRecord(id) {
  if (!id || checkingId.value) return null
  checkingId.value = id
  try {
    const data = await apiModule.post(props.api, '/ass/check', { id })
    // 正在查看该条时刷新右侧显示，否则右侧保持原样（不自动选中）
    if (detail.value && detail.value.id === id) {
      await loadDetail(id)
    }
    await loadRecords(true)
    return data
  } catch (e) {
    emit('notify', e.message || '检查失败')
    return null
  } finally {
    checkingId.value = null
  }
}

// 顶部「检查」：批量检查左侧全部「待检查」字幕，结果同步更新左侧列表与底部缺失窗口
async function checkAllPending() {
  if (checkingId.value) return
  const pending = records.value.filter(r => r.status === 'pending')
  if (!pending.length) {
    emit('notify', records.value.length ? '没有待检查的字幕' : '请先上传 ASS 字幕', 'warning')
    return
  }
  let ok = 0
  for (const rec of pending) {
    const data = await checkRecord(rec.id)
    if (data) ok++
  }
  emit('notify', `检查完成：${ok}/${pending.length} 条`, ok === pending.length ? 'success' : 'warning')
}

// 全量检查：递归扫描 ASS 字幕目录中的全部字幕并检查（存量字幕一键全查，按 file_path upsert 幂等）
async function scanAssAll() {
  if (scanning.value) return
  scanning.value = true
  try {
    const res = await apiModule.post(props.api, '/ass/scan_all')
    emit('notify', res?.message || '全量检查完成', 'success')
    await loadRecords(true)
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
    await loadRecords(true)
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
    await loadRecords(true)
  } catch (e) {
    emit('notify', e.message || '清空失败')
  } finally {
    clearing.value = false
  }
}

function goFontSearch(name) {
  // 跳转到字体库搜索该字体名：通过宿主路由 or 菜单；这里直接提示
  emit('notify', `可在字体库搜索：${name}`, 'info')
}

// 软刷新左侧记录列表 + 缺失窗口（保留当前选中，不重置界面）：
// 切 Tab 回来 / refreshKey 触发 / 30 秒轮询兜底 共用——监控新字幕按 id 倒序出现在列表顶部
async function refreshRecordsSoft() {
  page.value = 1
  reachedEnd.value = false
  loadingList.value = true
  try {
    const data = await apiModule.get(props.api, '/ass/list', {
      page: 1,
      limit,
      search: search.value,
    })
    const list = data.list || []
    total.value = data.total || 0
    matchSource.value = data.match_source || list[0]?.match_source || matchSource.value
    records.value = list
    reachedEnd.value = !list.length || records.value.length >= total.value
    if (selectedId.value && list.some(r => r.id === selectedId.value)) {
      if (detail.value) loadDetail(selectedId.value)
    } else if (selectedId.value) {
      selectedId.value = null
      detail.value = null
      detailOpen.value = false
    }
  } catch (e) {
    emit('notify', e.message || '刷新检查记录失败')
  } finally {
    loadingList.value = false
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
        @click="uploadRef?.click()"
      >
        <v-icon start size="18">mdi-upload</v-icon>
        上传 ASS 字幕
      </v-btn>
      <input
        ref="uploadRef"
        type="file"
        accept=".ass,.ASS"
        multiple
        style="display: none"
        @change="handleUpload"
      />
      <v-btn
        color="success"
        variant="tonal"
        class="ml-2"
        :disabled="!enabled || !records.length"
        :loading="!!checkingId"
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
      <span class="text-body-2 zt-total">共 {{ total }} 条记录</span>
    </div>
    <div class="zt-tip text-body-2 mb-2">
      上传字幕仅登记为「待检查」；点右侧「检查」对比字体库，缺字体的补字/入库请到「缺失字体」页
    </div>

    <v-text-field
      v-model="search"
      placeholder="搜索字幕文件名..."
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="mb-3 zt-search"
      prepend-inner-icon="mdi-magnify"
    ></v-text-field>

    <div v-if="matchSourceText" class="zt-match-source mb-2">
      匹配基准：{{ matchSourceText }}
    </div>

    <v-row no-gutters>
      <!-- 左栏：记录列表，小屏占满整行（上下结构），大屏 5:7 -->
      <v-col cols="12" md="5">
        <v-card class="zt-card-bg zt-list-card">
          <v-card-text class="pa-0">
            <v-progress-linear v-if="loadingList" indeterminate color="primary"></v-progress-linear>
            <div v-if="!loadingList && !records.length" class="zt-empty pa-6">
              暂无检查记录，上传 ASS 字幕后点击「检查」对比字体库
            </div>
            <v-list v-else density="compact" class="pa-0">
              <v-list-item
                v-for="rec in records"
                :key="rec.id"
                :active="selectedId === rec.id"
                class="zt-record-item"
                @click="loadDetail(rec.id)"
              >
                <template #prepend>
                  <v-icon
                    :color="rec.status === 'ok' ? 'success' : 'error'"
                    size="18"
                  >
                    {{ rec.status === 'ok' ? 'mdi-check-circle' : 'mdi-alert-circle' }}
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
                    @click.stop="checkRecord(rec.id)"
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
                <!-- 已上传字幕：❌ 删除（避免误传，还能重新上传） -->
                <template #append>
                  <v-btn
                    size="x-small"
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
              <v-list-item v-if="!reachedEnd && records.length" class="text-center">
                <v-btn variant="text" :loading="loadingList" @click="loadMore">
                  加载更多...
                </v-btn>
              </v-list-item>
            </v-list>
            <!-- 清空全部：放在列表底部，远离右上角关闭按钮 -->
            <div v-if="records.length" class="zt-clear-row pa-3 d-flex justify-end">
              <v-btn color="error" variant="tonal" size="small" :disabled="!enabled" :loading="clearing" @click="clearAll">
                <v-icon start size="16">mdi-trash-can-outline</v-icon>
                清空全部
              </v-btn>
            </div>
          </v-card-text>
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
                      :color="detail.status === 'ok' ? 'success' : (detail.status === 'pending' ? 'warning' : 'error')"
                      class="ml-2"
                    >
                      {{ detail.status === 'ok' ? '字体完整' : (detail.status === 'pending' ? '待检查' : `缺 ${detail.missing_count} 个字体`) }}
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
                  {{ f }}
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
  </div>
</template>

<style scoped>
.zt-search {
  max-width: 360px;
}
.zt-total {
  opacity: 0.75;
}
.zt-tip {
  opacity: 0.6;
}
.zt-match-source {
  font-size: 12px;
  opacity: 0.65;
}
.zt-list-card,
.zt-detail-card {
  height: 640px;
  overflow: auto;
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
.zt-clear-row {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
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
</style>