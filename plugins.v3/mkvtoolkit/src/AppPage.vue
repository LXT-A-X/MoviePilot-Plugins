<script setup>
/**
 * MKV 工具箱 · 主页面
 * 顶栏（品牌 / 引擎状态 / 三 Tab / 设置 / 退出）+ 编辑页（目录树 + 编辑器）+ 队列 + 历史 + 设置
 * 编辑页只维护“期望状态”，执行必须走 /plan 预览确认后再入队
 */
import { computed, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import logoUrl from '../icon.png'
import { createApi } from './api.js'
import Config from './Config.vue'
import FileTree from './components/FileTree.vue'
import TrackEditor from './components/TrackEditor.vue'
import SiblingPanel from './components/SiblingPanel.vue'
import PreviewDialog from './components/PreviewDialog.vue'
import FilePickerDialog from './components/FilePickerDialog.vue'
import UploadDialog from './components/UploadDialog.vue'
import QueuePage from './components/QueuePage.vue'
import HistoryPage from './components/HistoryPage.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import {
  baseName,
  extName,
  fmtBytes,
  fmtDuration,
  fmtChannels,
  codecLabel,
  stripExt,
  ARCHIVE_EXTENSIONS,
  isArchiveName,
} from './utils.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MkvToolkit' },
  navKey: { type: String, default: 'main' },
  initialConfig: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  showClose: { type: Boolean, default: false },
})

const emit = defineEmits(['action', 'close', 'switch'])
const display = useDisplay()
const mobile = computed(() => !display.mdAndUp.value)
// 按插件根容器自身宽度分三档（PC 模式下视口宽但容器窄，不能只用视口断点）：
// narrow: 真手机竖屏 / 容器 < 720；medium: 720~1100；wide: >= 1100
const rootRef = ref(null)
// 是否运行在宿主「插件卡片弹窗」（PluginDataDialog 的 VDialog）里
const inHostDialog = ref(false)
const containerWidth = ref(0)
const narrow = computed(() => mobile.value || (containerWidth.value > 0 && containerWidth.value < 720))
const medium = computed(() => !narrow.value && containerWidth.value > 0 && containerWidth.value < 1100)
const wide = computed(() => !narrow.value && !medium.value)
const layoutMode = computed(() => (narrow.value ? 'narrow' : medium.value ? 'medium' : 'wide'))
let resizeObserver = null
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()
const api = createApi(props)

// ---------------------------------------------------------------- 基础状态
const navItems = [
  { key: 'edit', label: '编辑' },
  { key: 'queue', label: '队列' },
  { key: 'history', label: '历史' },
]
const editorTabs = [
  { key: 'video', label: '视频' },
  { key: 'audio', label: '音频' },
  { key: 'subtitle', label: '字幕' },
  { key: 'attach', label: '附件' },
  { key: 'chapter', label: '章节' },
  { key: 'advanced', label: '高级' },
]

const tab = ref('edit')
const status = ref({})
const statusLoaded = ref(false)
const pluginDisabled = computed(() => status.value?.enabled === false)
// 停用遮罩延迟显示：避免弹窗打开瞬间用旧的/未就绪状态闪一下「插件已停用」
const showDisabledMask = ref(false)
let disabledMaskTimer = null
watch(pluginDisabled, (value) => {
  if (disabledMaskTimer) {
    clearTimeout(disabledMaskTimer)
    disabledMaskTimer = null
  }
  if (value) {
    disabledMaskTimer = setTimeout(() => {
      if (pluginDisabled.value) showDisabledMask.value = true
    }, 400)
  } else {
    showDisabledMask.value = false
  }
}, { immediate: true })
function reloadPage() {
  window.location.reload()
}

/** 停用状态下直接打开本插件设置页（可在「启用插件」开关里重新启用并保存）。 */
function openSettingsFromDisabled() {
  showDisabledMask.value = false
  switchTab('settings')
}
// 前端构建版本（与后端版本独立，便于确认浏览器加载的是新 bundle）
const UI_BUILD = '0.1.50'
const config = ref({ ...(props.initialConfig || {}) })
const error = ref('')
const treeDialog = ref(false)
// 递增后 FileTree 重新拉取 /file-statuses（打开文件 / 切换页签时）
const fileStatusTick = ref(0)
// 当前文件的队列/历史状态（提交后状态条 + 标题徽标）
const fileStatusMap = ref({})
const currentFileStatus = ref(null)
const statusDismissed = ref(false)
// 重复提交保护：检测到同 path 的 pending/running 任务时弹出三选一
const duplicateState = ref({ open: false, action: '', conflict: null })
let statusPollTimer = null
const snackbar = ref({ show: false, text: '', color: 'success' })

// 探测与编辑状态
const currentPath = ref('')
const probe = ref(null)
const probeLoading = ref(false)
const editorTab = ref('video')
const trackViews = ref([])
const attachments = ref([])
const siblings = ref([])
// 自动导入默认值（设置页开关控制打开文件时是否自动挂载）
const autoSubtitle = computed(() => Boolean(config.value.auto_subtitle))
const autoAudio = computed(() => Boolean(config.value.auto_audio))
const autoFonts = computed(() => Boolean(config.value.auto_fonts))
// 由「自动导入 / 挂载按钮」加入的条目路径（用于双向挂载按钮只收回自己加的条目）
const autoMountedPaths = ref({ subtitle: [], audio: [], font: [] })
// 未保存修改基线（关闭文件时用来判断是否需要确认）
const editorBaseline = ref('')
const title = ref('')
const chapterMode = ref('keep')
const chapterFile = ref('')
const extraArgsText = ref('')
// 附加参数「验证并应用」状态
const extraArgsChecking = ref(false)
const extraArgsError = ref('')
const extraArgsOk = ref('')
const outputMode = ref('dir')
const outputDir = ref('')
// 原地替换时不保存备份（不可回滚），仅在 mode=replace 时生效
const noBackup = ref(false)
const savingPlan = ref(false)
const holdSubmitting = ref(false)
// 队列内编辑：非空时两个提交按钮都改为更新该排队任务
const editingJobId = ref('')
const editingJobName = ref('')

// 预览
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewSubmitting = ref(false)
const planResult = ref(null)
// /plan warnings 出现 duration_mismatch 时必须显式勾选「我已知晓」才能提交
const durationMismatchConfirmed = ref(false)
const hasDurationMismatch = computed(() =>
  (planResult.value?.warnings || []).some((item) => (item?.code || '') === 'duration_mismatch'),
)

// 选择器 / 上传
const picker = ref({ open: false, kind: 'subtitle', title: '', initialPath: '', exts: [] })
const uploadDialog = ref({ open: false, kind: 'subtitle' })
// 压缩包解压（字体）
const archiveTools = ref({ tools: {}, extensions: [] })
const archiveLoading = ref(false)
const archiveDialog = ref({ open: false, path: '', recursive: false, loading: false })

// 确认弹窗
const confirmState = ref({
  open: false,
  title: '',
  text: '',
  detail: '',
  confirmText: '确定',
  color: 'primary',
  loading: false,
  action: null,
})

// 队列 / 历史
const queueJobs = ref([])
const queuePaused = ref(false)
const queueLoading = ref(false)
const historyItems = ref([])
const historyTotal = ref(0)
const historyLoading = ref(false)

// 安装
const installStarting = ref(false)

let statusTimer = null
let queueTimer = null
let installTimer = null

// ---------------------------------------------------------------- 计算属性
const engine = computed(() => status.value?.engine || {})
const engineInstall = computed(() => status.value?.engine_install || {})
const engineReady = computed(() => {
  if (engine.value.mode === 'none') return false
  if (engine.value.mkvmerge?.ok) return true
  return Boolean(config.value.allow_ffmpeg_fallback && engine.value.ffmpeg?.ok)
})
const mkvmergeChip = computed(() => {
  const info = engine.value.mkvmerge || {}
  if (info.ok) return `mkvmerge${info.version ? ` v${info.version}` : ''}`
  return 'mkvmerge 未安装'
})
const ffmpegChip = computed(() => {
  const info = engine.value.ffmpeg || {}
  if (info.ok) return `ffmpeg${info.version ? ` ${info.version}` : ''}`
  return 'ffmpeg 未检测到'
})
const runningJob = computed(() => queueJobs.value.find((job) => job.status === 'running') || null)
// 宿主卡片弹窗里：空状态固定 900 上限；有内容按内容撑高，最高 1000
const hasContent = computed(() => Boolean(
  probe.value
  || currentPath.value
  || runningJob.value
  || queueJobs.value.length
  || historyItems.value.length,
))
const pendingJobs = computed(() => queueJobs.value.filter((job) => job.status === 'pending'))
const queueCount = computed(() => {
  const fromStatus = Number(status.value?.queue?.pending)
  if (Number.isFinite(fromStatus) && fromStatus >= 0) return fromStatus
  return pendingJobs.value.length
})
const queueBadge = computed(() => (queueCount.value > 0 ? queueCount.value : 0))
const hasActiveJobs = computed(() => {
  if (runningJob.value || pendingJobs.value.length) return true
  const queue = status.value?.queue || {}
  return Number(queue.running) > 0 || Number(queue.pending) > 0
})
const bottomBarVisible = computed(() => Boolean(runningJob.value || queueCount.value > 0))

const container = computed(() => probe.value?.container || {})
const videoTrack = computed(() => (probe.value?.tracks || []).find((track) => track.type === 'video') || null)
const chapters = computed(() => probe.value?.chapters || [])
const audioTracks = computed(() => trackViews.value.filter((track) => track.type === 'audio'))
const subtitleTracks = computed(() => trackViews.value.filter((track) => track.type === 'subtitle'))
const mediaTitle = computed(() => (probe.value?.name ? String(probe.value.name) : '未选择文件'))
const sourceExt = computed(() => extName(currentPath.value || '').toLowerCase())
// m2ts/ts 源必须重封装成 MKV：不能原地替换，输出名自动改为 .mkv
const isNonMkvSource = computed(() => Boolean(currentPath.value) && sourceExt.value !== '.mkv')
// 备份目录/保留份数：后端 GET /config 已补默认值，这里再做兜底
const backupDir = computed(() => String(config.value.backup_dir || '/config/plugins/MkvToolkit/backup'))
const backupKeep = computed(() => (Number(config.value.backup_keep) > 0 ? Number(config.value.backup_keep) : 3))
const uploadMaxMb = computed(() => (Number(config.value.upload_max_mb) > 0 ? Number(config.value.upload_max_mb) : 50))
// 压缩包支持提示：7z/unrar 都不可用时提示需容器安装
const archiveHint = computed(() => {
  const tools = archiveTools.value?.tools || {}
  if (!tools['7z'] && !tools.unrar) {
    return 'zip/tar 可直接解压；7z/rar 需在容器安装 7z 或 unrar'
  }
  const names = []
  if (tools['7z'] || tools.unrar) names.push('7z/rar')
  return `支持 zip/tar${names.length ? '、7z/rar' : ''}；解压出的字体自动加入附件`
})
const archiveExtensions = computed(() =>
  Array.isArray(archiveTools.value?.extensions) && archiveTools.value.extensions.length
    ? archiveTools.value.extensions
    : ARCHIVE_EXTENSIONS,
)
// 顶部引擎区的压缩包依赖状态：zip/tar 内置，7z/rar 取决于系统工具
const archiveChipOk = computed(() => {
  const tools = archiveTools.value?.tools || {}
  return Boolean(tools['7z'] || tools.unrar)
})
const archiveChip = computed(() => (archiveChipOk.value ? '压缩包 zip/tar/7z/rar' : '压缩包 zip/tar'))

const runningProgress = computed(() => {
  const value = Number(runningJob.value?.progress)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
})

// 当前文件状态徽标/状态条文案（pending 阶段为「等待中」时优先显示等待中）
const statusMeta = computed(() => {
  const status = currentFileStatus.value
  if (!status?.state) return null
  const labels = { pending: '待开始', running: '运行中', success: '已完成', failed: '失败', cancelled: '已取消' }
  let label = labels[status.state] || status.state
  if (status.state === 'pending' && String(status.stage || '').includes('等待')) label = '等待中'
  return { label, state: status.state, id: status.job_id || '' }
})
const statusBannerVisible = computed(() => Boolean(statusMeta.value) && !statusDismissed.value)

function statusIcon(state) {
  return (
    {
      pending: 'mdi-clock-outline',
      running: 'mdi-progress-clock',
      success: 'mdi-check-circle-outline',
      failed: 'mdi-alert-circle-outline',
      cancelled: 'mdi-cancel',
    }[state] || 'mdi-information-outline'
  )
}

const siblingItems = computed(() => {
  const data = probe.value?.siblings
  if (!data) return []
  const list = []
  for (const kind of ['subtitle', 'audio', 'font']) {
    const key = kind === 'subtitle' ? 'subtitles' : kind === 'audio' ? 'audios' : 'fonts'
    for (const item of data[key] || []) {
      list.push({
        key: `${kind}:${item.path}`,
        kind,
        name: item.name,
        path: item.path,
        size: item.size,
        ext: item.ext || extName(item.name),
        language: item.language || '',
        matched: Boolean(item.matched),
        checked: isAddedSource(kind, item.path),
      })
    }
  }
  return list
})

// 同级自动发现面板按页签分类型：字幕/音频/附件各看各的，视频/章节/高级不显示
const siblingKind = computed(() => (editorTab.value === 'audio' ? 'audio' : editorTab.value === 'attach' ? 'font' : 'subtitle'))
const showSiblings = computed(() => ['subtitle', 'audio', 'attach'].includes(editorTab.value))

/** 当前页签可挂载的候选：字幕/音频为前缀匹配项，字体为同目录全部字体。 */
function siblingCandidates(kind) {
  const sib = probe.value?.siblings || {}
  if (kind === 'font') return sib.fonts || []
  return (kind === 'audio' ? sib.audios : sib.subtitles) || []
}

function autoList(kind) {
  return autoMountedPaths.value[kind] || []
}

function isAutoMounted(kind, path) {
  return autoList(kind).includes(path)
}

function markAutoMounted(kind, path) {
  if (!path || isAutoMounted(kind, path)) return
  autoMountedPaths.value = { ...autoMountedPaths.value, [kind]: [...autoList(kind), path] }
}

function forgetAutoMounted(kind, path) {
  if (!path || !isAutoMounted(kind, path)) return
  autoMountedPaths.value = { ...autoMountedPaths.value, [kind]: autoList(kind).filter((item) => item !== path) }
}

function clearAutoMounted() {
  autoMountedPaths.value = { subtitle: [], audio: [], font: [] }
}

// 当前类型可挂载候选是否都已挂载（状态看实际存在，收回只看自动加入的路径集合）
const siblingMounted = computed(() => {
  const kind = siblingKind.value
  const candidates = siblingCandidates(kind)
  if (!candidates.length) return false
  return candidates.every((item) => isCandidatePresent(kind, item.path))
})

/** 候选是否已存在于编辑器（新增轨道/新增附件）。 */
function isCandidatePresent(kind, path) {
  if (kind === 'font') return attachments.value.some((item) => item.added && item.file?.path === path)
  return trackViews.value.some((track) => track.added && track.file?.path === path)
}

// ---------------------------------------------------------------- 提示
function toastMsg(kind, message) {
  const text = String(message || '')
  if (toast && typeof toast[kind] === 'function') {
    toast[kind](text)
    return
  }
  snackbar.value = {
    show: true,
    text,
    color: kind === 'error' ? 'error' : kind === 'warning' ? 'warning' : kind === 'info' ? 'info' : 'success',
  }
}

// ---------------------------------------------------------------- 配置 / 状态
async function loadConfig() {
  try {
    const data = await api.get('/config')
    config.value = { ...config.value, ...(data || {}) }
  } catch (err) {
    // 配置读取失败时用宿主注入的 initialConfig 兜底
  }
  if (!currentPath.value) {
    outputMode.value = config.value.output_mode || 'dir'
    outputDir.value = config.value.output_dir || ''
  }
}

async function loadStatus() {
  try {
    status.value = await api.get('/status') || {}
    // 诊断用：记录每次 /status 的 enabled，复现“闪现停用页”时可在控制台导出
    if (typeof window !== 'undefined') {
      window.__mkvToolkitStatus = window.__mkvToolkitStatus || []
      window.__mkvToolkitStatus.push({
        t: new Date().toISOString(),
        enabled: status.value?.enabled,
        version: status.value?.version,
      })
      if (window.__mkvToolkitStatus.length > 300) window.__mkvToolkitStatus.shift()
    }
    if (status.value?.enabled === false) {
      console.warn('[MkvToolkit] /status 返回 enabled=false', status.value?.version)
    }
    if (status.value?.engine_install?.running && !installTimer) {
      installStarting.value = true
      pollEngineInstall()
    }
  } catch (err) {
    // 轮询失败静默
  }
}

// ---------------------------------------------------------------- 文件状态条 / 轮询
function stopStatusPoll() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

/** 拉取 /file-statuses，按当前 path 更新状态条与标题徽标。 */
async function refreshFileStatuses() {
  try {
    const data = await api.get('/file-statuses')
    const map = {}
    for (const item of data?.items || []) {
      if (item?.path) map[item.path] = item
    }
    fileStatusMap.value = map
    currentFileStatus.value = currentPath.value ? (map[currentPath.value] || null) : null
  } catch (err) {
    // 状态读取失败静默，不影响编辑
  }
  ensureStatusPoll()
}

/** 提交/更新成功后立即用返回的 job 填充状态条（无需等下一轮 /file-statuses）。 */
function seedSubmittedJob(job, fallbackPath) {
  const path = job?.path || fallbackPath || currentPath.value
  if (!path) return
  const entry = {
    path,
    name: baseName(path),
    state: job?.status || 'pending',
    stage: job?.stage || '等待中',
    job_id: job?.id || job?.job_id || '',
    updated_at: '',
  }
  fileStatusMap.value = { ...fileStatusMap.value, [path]: entry }
  if (!currentPath.value || path === currentPath.value) {
    currentFileStatus.value = entry
    statusDismissed.value = false
  }
  fileStatusTick.value += 1
  ensureStatusPoll()
}

/** pending/running 状态下每 5 秒轮询；离开编辑页/关闭文件/终态停止。 */
function ensureStatusPoll() {
  const shouldPoll =
    tab.value === 'edit' &&
    Boolean(currentPath.value) &&
    ['pending', 'running'].includes(currentFileStatus.value?.state)
  if (!shouldPoll) {
    stopStatusPoll()
    return
  }
  if (statusPollTimer) return
  statusPollTimer = setInterval(() => {
    refreshFileStatuses()
  }, 5000)
}

// ---------------------------------------------------------------- 重复提交保护
/** 再请求一次 /file-statuses，判断当前 path 是否已有 pending/running 任务。 */
async function findActiveJobForCurrentPath() {
  if (!currentPath.value) return null
  try {
    const data = await api.get('/file-statuses')
    const map = {}
    for (const item of data?.items || []) {
      if (item?.path) map[item.path] = item
    }
    fileStatusMap.value = map
    const hit = map[currentPath.value]
    if (hit) currentFileStatus.value = hit
    return hit && ['pending', 'running'].includes(hit.state) ? hit : null
  } catch (err) {
    const hit = fileStatusMap.value[currentPath.value]
    return hit && ['pending', 'running'].includes(hit.state) ? hit : null
  }
}

/** 返回 true 表示可继续提交；false 表示已弹出三选一对话框。 */
async function guardDuplicateSubmission(action) {
  // 队列内编辑态：直接走 update，跳过重复保护
  if (editingJobId.value) return true
  const conflict = await findActiveJobForCurrentPath()
  if (!conflict) return true
  duplicateState.value = { open: true, action, conflict }
  return false
}

/** 三选一：更新现有队列任务（只调用 update，不新建）。 */
async function updateExistingJobFromConflict(conflict) {
  const jobId = conflict?.job_id
  if (!jobId) return
  try {
    const data = await api.post(`/jobs/${encodeURIComponent(jobId)}/update`, { plan: buildPlan() })
    toastMsg('success', '已更新队列任务')
    seedSubmittedJob(data || { id: jobId, status: 'pending', path: currentPath.value })
    await loadQueue(true)
    await loadStatus()
  } catch (err) {
    toastMsg('error', `更新队列任务失败：${err.message}`)
    await refreshFileStatuses()
  }
}

async function chooseDuplicate(choice) {
  const action = duplicateState.value.action
  const conflict = duplicateState.value.conflict
  duplicateState.value = { open: false, action: '', conflict: null }
  if (choice === 'cancel') return
  if (choice === 'update') {
    await updateExistingJobFromConflict(conflict)
    return
  }
  // 再提交一个新任务：继续原提交流程
  if (action === 'preview') await openPreview(true)
  else await enqueueHold(true)
}

async function loadQueue(silent = true) {
  if (!silent) queueLoading.value = true
  try {
    const data = await api.get('/jobs', { status: 'all' })
    queueJobs.value = data?.jobs || []
    queuePaused.value = Boolean(data?.paused)
  } catch (err) {
    if (!silent) toastMsg('error', `读取队列失败：${err.message}`)
  } finally {
    queueLoading.value = false
  }
}

async function loadHistory(silent = true) {
  if (!silent) historyLoading.value = true
  try {
    const data = await api.get('/history', { limit: 50, offset: 0 })
    historyItems.value = data?.items || []
    historyTotal.value = Number(data?.total) || historyItems.value.length
  } catch (err) {
    if (!silent) toastMsg('error', `读取历史失败：${err.message}`)
  } finally {
    historyLoading.value = false
  }
}

// ---------------------------------------------------------------- 文件选择与探测
function dirOf(path) {
  const normalized = String(path || '').replace(/\/+$/, '')
  const index = normalized.lastIndexOf('/')
  return index > 0 ? normalized.slice(0, index) : normalized
}

function applyProbe(data, keepTab = false) {
  probe.value = data || null
  if (!data) return
  error.value = ''
  if (!keepTab) editorTab.value = 'video'
  title.value = data.container?.title || stripExt(data.name || baseName(data.path))
  trackViews.value = (data.tracks || [])
    .filter((track) => ['video', 'audio', 'subtitle'].includes(track.type))
    .map((track) => ({
      id: track.id,
      type: track.type,
      codec: track.codec,
      codec_detail: track.codec_detail,
      channels: track.channels,
      sample_rate: track.sample_rate,
      width: track.width,
      height: track.height,
      fps: track.fps,
      hdr: track.hdr,
      bitrate: track.bitrate,
      bitrate_estimated: Boolean(track.bitrate_estimated),
      duration: track.duration,
      language: track.language || 'und',
      name: track.name || '',
      default: Boolean(track.default),
      forced: Boolean(track.forced),
      keep: true,
      added: false,
      readonly: track.type === 'video',
      _orig: {
        language: track.language || 'und',
        name: track.name || '',
        default: Boolean(track.default),
        forced: Boolean(track.forced),
      },
    }))
  attachments.value = (data.attachments || []).map((item, index) => ({
    id: item.id ?? index,
    name: item.name,
    mime: item.mime || '',
    size: item.size ?? null,
    keep: true,
    added: false,
  }))
  // 同级自动发现：仅前缀匹配的字幕默认勾选（音频/字体需手动确认）
  siblings.value = []
  clearAutoMounted()
  const sib = data.siblings || {}
  for (const item of sib.subtitles || []) {
    siblings.value.push({ kind: 'subtitle', ...item, checked: Boolean(item.matched) })
  }
  for (const item of sib.audios || []) {
    siblings.value.push({ kind: 'audio', ...item, checked: false })
  }
  for (const item of sib.fonts || []) {
    siblings.value.push({ kind: 'font', ...item, checked: false })
  }
  chapterMode.value = 'keep'
  chapterFile.value = ''
  extraArgsText.value = ''
  // m2ts/ts 源不能原地替换，强制输出到目录（后端会重封装为 .mkv）
  const nonMkv = extName(data.path || '').toLowerCase() !== '.mkv'
  outputMode.value = nonMkv ? 'dir' : (config.value.output_mode || 'dir')
  outputDir.value = config.value.output_dir || ''
  noBackup.value = false
  // 打开文件时按当前开关自动导入同级素材（前缀匹配的字幕/音频、同目录字体）
  applyAutoImport()
  editorBaseline.value = editorSnapshot()
}

// ---------------------------------------------------------------- 关闭文件 / 未保存修改
/** 当前编辑状态的稳定快照（用于判断是否有未提交修改）。 */
function editorSnapshot() {
  if (!probe.value) return ''
  return JSON.stringify({
    path: currentPath.value,
    title: title.value,
    chapterMode: chapterMode.value,
    chapterFile: chapterFile.value,
    extraArgsText: extraArgsText.value,
    outputMode: outputMode.value,
    outputDir: outputDir.value,
    noBackup: noBackup.value,
    tracks: trackViews.value.map((track) => ({
      id: track.id,
      keep: track.keep,
      added: track.added,
      language: track.language,
      name: track.name,
      default: Boolean(track.default),
      forced: Boolean(track.forced),
      encoding: track.encoding,
      sync_ms: track.sync_ms,
      file: track.file?.path || '',
    })),
    attachments: attachments.value.map((item) => ({
      id: item.id,
      keep: item.keep,
      added: item.added,
      name: item.name,
      file: item.file?.path || '',
    })),
  })
}

const editorDirty = computed(() => Boolean(probe.value) && editorSnapshot() !== editorBaseline.value)

function doClearFile() {
  currentPath.value = ''
  probe.value = null
  trackViews.value = []
  attachments.value = []
  siblings.value = []
  title.value = ''
  chapterMode.value = 'keep'
  chapterFile.value = ''
  extraArgsText.value = ''
  outputMode.value = config.value.output_mode || 'dir'
  outputDir.value = config.value.output_dir || ''
  noBackup.value = false
  error.value = ''
  editingJobId.value = ''
  editingJobName.value = ''
  editorBaseline.value = ''
  currentFileStatus.value = null
  statusDismissed.value = false
  stopStatusPoll()
  clearAutoMounted()
}

function clearFile() {
  if (!probe.value) return
  if (!editorDirty.value) {
    doClearFile()
    return
  }
  askConfirm({
    title: '关闭文件',
    text: '当前编辑有未保存的修改，关闭后会丢弃这些修改。',
    confirmText: '丢弃并关闭',
    color: 'warning',
    action: doClearFile,
  })
}

async function loadProbe(path, keepTab = false) {
  if (!path) return false
  probeLoading.value = true
  error.value = ''
  try {
    const data = await api.post('/probe', { path })
    currentPath.value = path
    applyProbe(data, keepTab)
    return true
  } catch (err) {
    error.value = err.message
    toastMsg('error', `探测失败：${err.message}`)
    return false
  } finally {
    probeLoading.value = false
    // 打开/重新探测文件后刷新状态条
    refreshFileStatuses()
  }
}

function onSelectFile(path) {
  treeDialog.value = false
  // 编辑队列任务时切换文件，视为放弃本次编辑
  if (editingJobId.value && path !== currentPath.value) {
    editingJobId.value = ''
    editingJobName.value = ''
    toastMsg('info', '已取消队列任务编辑')
  }
  loadProbe(path).finally(() => {
    // 打开文件后刷新文件树的队列/历史状态徽标
    fileStatusTick.value += 1
  })
}

function reprobe() {
  if (!currentPath.value) return
  loadProbe(currentPath.value, true).finally(() => {
    fileStatusTick.value += 1
  })
}

/** 复制文本：优先 Clipboard API；http 页面（非安全上下文）回退 execCommand。 */
async function copyToClipboard(text) {
  if (!text) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (err) {
    // 继续尝试回退方案
  }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    area.setSelectionRange(0, text.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch (err) {
    return false
  }
}

async function copyPath() {
  if (!currentPath.value) return
  const ok = await copyToClipboard(currentPath.value)
  if (ok) toastMsg('success', '路径已复制')
  else toastMsg('warning', '复制失败：当前页面不是 https，浏览器禁止剪贴板；请手动选择路径文本')
}

// ---------------------------------------------------------------- 新增轨道 / 附件
function inferLanguage(name) {
  const lower = String(name || '').toLowerCase()
  const map = config.value.language_map || {}
  const entries = Object.entries(map).sort((a, b) => String(b[0]).length - String(a[0]).length)
  for (const [suffix, language] of entries) {
    if (suffix && lower.includes(String(suffix).toLowerCase())) return language
  }
  return 'und'
}

function addTrackFromFile(kind, file, withToast = true) {
  const path = file.path
  if (trackViews.value.some((track) => track.added && track.file?.path === path)) return false
  const language = file.language || inferLanguage(file.name || path)
  trackViews.value = [
    ...trackViews.value,
    {
      id: `add-${kind}-${path}`,
      type: kind,
      kind,
      added: true,
      keep: true,
      language,
      name: '',
      default: false,
      forced: false,
      encoding: 'auto',
      sync_ms: 0,
      file: {
        name: file.name || baseName(path),
        path,
        size: file.size ?? null,
        ext: file.ext || extName(file.name || path),
      },
    },
  ]
  if (withToast) toastMsg('success', `已添加${kind === 'audio' ? '音频' : '字幕'}：${baseName(path)}`)
  return true
}

function addFontFromFile(file) {
  const path = file.path
  const name = String(file.name || baseName(path) || '').trim().toLowerCase()
  // 同一路径或同名（忽略大小写）都视为重复：解压出来的同名字体不再重复加入
  const exists = attachments.value.some((item) => {
    const itemPath = item.added ? item.file?.path : item.path
    const itemName = String(item.name || item.file?.name || '').trim().toLowerCase()
    return (itemPath && itemPath === path) || (name && itemName === name)
  })
  if (exists) return false
  attachments.value = [
    ...attachments.value,
    {
      id: `add-font-${path}`,
      name: file.name || baseName(path),
      mime: '',
      size: file.size ?? null,
      keep: true,
      added: true,
      file: { name: file.name || baseName(path), path, size: file.size ?? null },
    },
  ]
  return true
}

function isAddedSource(kind, path) {
  if (kind === 'font') {
    return attachments.value.some((item) => item.added && item.file?.path === path)
  }
  return trackViews.value.some((track) => track.added && track.file?.path === path)
}

function toggleSibling(item, value) {
  if (item.kind === 'font') {
    if (value) addFontFromFile(item)
    else {
      attachments.value = attachments.value.filter((entry) => !(entry.added && entry.file?.path === item.path))
      forgetAutoMounted('font', item.path)
    }
    return
  }
  if (value) {
    addTrackFromFile(item.kind, item)
  } else {
    trackViews.value = trackViews.value.filter((track) => !(track.added && track.file?.path === item.path))
    forgetAutoMounted(item.kind, item.path)
  }
}

// ---------------------------------------------------------------- 自动导入 / 挂载（打开文件时 + 双向挂载按钮）
/** 按设置默认值自动导入：字幕/音频只取前缀匹配（matched），字体取同目录（含 fonts/ 子目录）全部，并记录路径。 */
function applyAutoImport() {
  const sib = probe.value?.siblings || {}
  if (autoSubtitle.value) {
    for (const item of sib.subtitles || []) {
      if (item.matched && addTrackFromFile('subtitle', item, false)) markAutoMounted('subtitle', item.path)
    }
  }
  if (autoAudio.value) {
    for (const item of sib.audios || []) {
      if (item.matched && addTrackFromFile('audio', item, false)) markAutoMounted('audio', item.path)
    }
  }
  if (autoFonts.value) {
    for (const item of sib.fonts || []) {
      if (addFontFromFile(item)) markAutoMounted('font', item.path)
    }
  }
}

const KIND_LABEL_TEXT = { subtitle: '同名字幕', audio: '同名音频', font: '同目录字体' }

/** 挂载当前页签类型的所有候选，并记录路径。 */
function mountSiblings(kind = 'subtitle') {
  const candidates = siblingCandidates(kind)
  let count = 0
  for (const item of candidates) {
    const ok = kind === 'font' ? addFontFromFile(item) : addTrackFromFile(kind, item, false)
    if (ok) {
      count += 1
      // 只记录由挂载按钮/自动导入加入的路径，收回时也只删这些
      markAutoMounted(kind, item.path)
    }
  }
  const label = KIND_LABEL_TEXT[kind] || '候选'
  if (count) toastMsg('success', `已挂载 ${count} 个${label}`)
  else if (candidates.length) toastMsg('info', `${label}都已在列表中`)
  else toastMsg('info', `没有可挂载的${label}`)
}

/** 收回当前页签由自动导入/挂载按钮加入的条目（用户手动加的不动）。 */
function unmountSiblings(kind = 'subtitle') {
  const paths = new Set(autoList(kind))
  let count = 0
  if (kind === 'font') {
    const before = attachments.value.length
    attachments.value = attachments.value.filter((item) => !(item.added && paths.has(item.file?.path)))
    count = before - attachments.value.length
  } else {
    const before = trackViews.value.length
    trackViews.value = trackViews.value.filter((track) => !(track.added && paths.has(track.file?.path)))
    count = before - trackViews.value.length
  }
  autoMountedPaths.value = { ...autoMountedPaths.value, [kind]: [] }
  const label = KIND_LABEL_TEXT[kind] || '候选'
  if (count) toastMsg('success', `已收回 ${count} 个${label}`)
  else toastMsg('info', `没有可收回的${label}`)
}

function toggleSiblingMount() {
  const kind = siblingKind.value
  if (siblingMounted.value) unmountSiblings(kind)
  else mountSiblings(kind)
}

/** 附件区：扫描同目录字体（含 fonts/ 子目录）并全部加入附件（按路径去重）。 */
function scanSiblingFonts() {
  const fonts = probe.value?.siblings?.fonts || []
  let count = 0
  for (const item of fonts) {
    const before = attachments.value.length
    addFontFromFile(item)
    if (attachments.value.length > before) count += 1
  }
  if (count) toastMsg('success', `已扫描并挂载 ${count} 个同目录字体`)
  else if (fonts.length) toastMsg('info', '同目录字体都已在附件列表中')
  else toastMsg('info', '同目录（含 fonts/ 子目录）没有发现字体文件')
}

function moveTrack(track, delta) {
  // 同类轨道内自由移动（不区分原有 / 新增），其它类型轨道位置保持不变
  const sameType = trackViews.value.filter((item) => item.type === track.type)
  const index = sameType.findIndex((item) => item.id === track.id)
  const neighbor = sameType[index + delta]
  if (!neighbor) return
  const list = [...trackViews.value]
  const from = list.findIndex((item) => item.id === track.id)
  const to = list.findIndex((item) => item.id === neighbor.id)
  if (from < 0 || to < 0) return
  list.splice(from, 1)
  list.splice(to, 0, track)
  trackViews.value = list
}

function removeTrack(track) {
  if (track.added) {
    trackViews.value = trackViews.value.filter((item) => item.id !== track.id)
    forgetAutoMounted(track.type === 'audio' ? 'audio' : 'subtitle', track.file?.path)
    return
  }
  if (track.readonly) return
  track.keep = !track.keep
}

// 估偏移：调用 /analyze/offset，把 offset_ms 写回新增轨的 sync_ms（实验能力，需用户确认）
async function estimateTrackOffset(track) {
  if (!track || !track.added || !track.file?.path || !currentPath.value || track._estimating) return
  track._estimating = true
  try {
    const data = await api.post('/analyze/offset', {
      path: currentPath.value,
      file: track.file.path,
      kind: track.kind || (track.type === 'subtitle' ? 'subtitle' : 'audio'),
    })
    const offset = Math.round(Number(data?.offset_ms) || 0)
    track.sync_ms = offset
    // 后端 confidence 已是 0~100 的整数百分比，不要再乘 100
    const confidence = Math.max(0, Math.min(100, Math.round(Number(data?.confidence) || 0)))
    const reliable = data?.reliable !== false
    const hint = String(data?.hint || '').trim()
    track._offsetHint = [hint, `置信度 ${confidence}%`, data?.margin != null ? `margin ${data.margin}` : '']
      .filter(Boolean)
      .join('；')
    if (offset === 0) {
      // 原本就对齐：不写 sync，提示无需调整
      toastMsg('success', `已对齐，无需调整（置信度 ${confidence}%）`)
    } else if (reliable) {
      toastMsg('success', `估计偏移 ${offset >= 0 ? '+' : ''}${offset}ms（置信度 ${confidence}%）`)
    } else {
      toastMsg('warning', '估计不可靠（可能不是同一版本），请确认后再用')
    }
  } catch (err) {
    toastMsg('error', `估计偏移失败：${err.message}`)
  } finally {
    track._estimating = false
  }
}

function toggleAttachment(item) {
  if (item.added) {
    attachments.value = attachments.value.filter((entry) => entry.id !== item.id)
    forgetAutoMounted('font', item.file?.path)
    return
  }
  item.keep = !item.keep
}

// 附件 MIME → 可读类型
function attachmentType(item) {
  const mime = String(item?.mime || '').toLowerCase()
  const ext = extName(item?.name || '')
  if (mime.includes('truetype') || ext === '.ttf') return 'TrueType'
  if (mime.includes('opentype') || ext === '.otf') return 'OpenType'
  if (mime.includes('collection') || ext === '.ttc') return 'TrueType Collection'
  return '字体'
}

function resetEditor() {
  if (probe.value) {
    applyProbe(probe.value, true)
    toastMsg('info', '已重置本次编辑')
  }
}

// ---------------------------------------------------------------- 压缩包解压（字体）
async function loadArchiveTools() {
  try {
    const data = await api.get('/archive/tools')
    archiveTools.value = {
      tools: data?.tools || {},
      extensions: Array.isArray(data?.extensions) ? data.extensions : [],
    }
  } catch (err) {
    // 能力读取失败时用前端默认扩展名兜底
  }
}

/** 把 /archive/extract 返回的字体加入附件：同名/同路径跳过，返回 {added, skipped}。 */
function addArchiveFonts(data) {
  let added = 0
  let skipped = 0
  const seen = new Set()
  for (const item of data?.items || []) {
    if (!item?.path) continue
    const name = String(item.name || baseName(item.path) || '').trim().toLowerCase()
    if (name && seen.has(name)) {
      skipped += 1
      continue
    }
    if (name) seen.add(name)
    if (addFontFromFile({
      name: item.name || baseName(item.path),
      path: item.path,
      size: item.size ?? null,
      ext: item.ext || extName(item.name || item.path),
    })) {
      added += 1
    } else {
      skipped += 1
    }
  }
  const errors = (data?.archives || []).filter((item) => item?.error)
  if (errors.length) toastMsg('warning', errors[0].error)
  return { added, skipped }
}

/** 生成解压结果的提示文案。 */
function archiveToast(prefix, result) {
  const parts = [`${prefix} ${result.added} 个字体`]
  if (result.skipped) parts.push(`跳过 ${result.skipped} 个重复/已在列表`)
  return parts.join('，')
}

/** 单个压缩包：从目录选择后立即解压。 */
async function extractArchiveFile(path) {
  if (!path || archiveLoading.value) return
  archiveLoading.value = true
  try {
    const data = await api.post('/archive/extract', { path })
    const result = addArchiveFonts(data)
    if (result.added) toastMsg('success', archiveToast('已解压', result))
    else if (result.skipped) toastMsg('info', `字体都已在附件列表中（跳过 ${result.skipped} 个重复）`)
    else if (!(data?.archives || []).some((item) => item?.error)) toastMsg('info', '压缩包里没有字体文件')
  } catch (err) {
    toastMsg('error', `解压失败：${err.message}`)
  } finally {
    archiveLoading.value = false
  }
}

function openArchivePicker() {
  const base = currentPath.value || probe.value?.path || ''
  picker.value = {
    open: true,
    kind: 'archive',
    title: '选择字体压缩包',
    initialPath: base ? dirOf(base) : (config.value.roots?.[0] || ''),
    exts: archiveExtensions.value.length ? archiveExtensions.value : ARCHIVE_EXTENSIONS,
  }
}

function openArchiveBatch() {
  const base = currentPath.value || probe.value?.path || ''
  archiveDialog.value = {
    open: true,
    path: base ? dirOf(base) : (config.value.roots?.[0] || ''),
    recursive: false,
    loading: false,
  }
}

/** 目录批量解压：可包含子目录，扫描目录下压缩包并解出字体。 */
async function runArchiveBatch() {
  const dialog = archiveDialog.value
  if (dialog.loading) return
  if (!String(dialog.path || '').trim()) {
    toastMsg('warning', '请输入要扫描的目录路径')
    return
  }
  dialog.loading = true
  try {
    const data = await api.post('/archive/extract', {
      path: String(dialog.path).trim(),
      recursive: Boolean(dialog.recursive),
    })
    const result = addArchiveFonts(data)
    const scanned = Array.isArray(data?.archives) ? data.archives.length : 0
    if (result.added) {
      toastMsg('success', `扫描 ${scanned} 个压缩包，${archiveToast('解压', result)}`)
    } else if (result.skipped) {
      toastMsg('info', `扫描 ${scanned} 个压缩包，字体都已在附件列表中（跳过 ${result.skipped} 个重复）`)
    } else {
      toastMsg('info', `扫描 ${scanned} 个压缩包，没有找到可加入的字体`)
    }
    dialog.open = false
  } catch (err) {
    toastMsg('error', `解压失败：${err.message}`)
  } finally {
    dialog.loading = false
  }
}

// ---------------------------------------------------------------- 选择器 / 上传
function openPicker(kind) {
  const titles = { subtitle: '选择字幕文件', audio: '选择音频文件', font: '选择字体文件', chapter: '选择章节文件' }
  picker.value = {
    open: true,
    kind,
    title: titles[kind] || '选择文件',
    initialPath: currentPath.value ? dirOf(currentPath.value) : (config.value.roots?.[0] || ''),
    exts: kind === 'chapter' ? ['.xml', '.txt', '.ogm'] : [],
  }
}

function onPicked(file) {
  if (!file) return
  if (file.kind === 'archive') {
    extractArchiveFile(file.path)
    return
  }
  if (file.kind === 'chapter') {
    chapterFile.value = file.path
    chapterMode.value = 'import'
    toastMsg('success', `已选择章节文件：${baseName(file.path)}`)
    return
  }
  if (file.kind === 'font') {
    addFontFromFile(file)
    toastMsg('success', `已添加字体：${file.name || baseName(file.path)}`)
    return
  }
  addTrackFromFile(file.kind, file)
}

function openUpload(kind) {
  uploadDialog.value = { open: true, kind }
}

function onUploaded(data) {
  // 压缩包上传：后端直接解压并返回 items，全部加入附件
  if (Array.isArray(data?.items)) {
    const result = addArchiveFonts(data)
    if (result.added) toastMsg('success', archiveToast('已上传并解压', result))
    else if (result.skipped) toastMsg('info', `字体都已在附件列表中（跳过 ${result.skipped} 个重复）`)
    return
  }
  if (!data?.path) return
  const kind = data.kind || uploadDialog.value.kind
  const file = { name: data.name, path: data.path, size: data.size, ext: extName(data.name) }
  if (kind === 'font') addFontFromFile(file)
  else addTrackFromFile(kind, file, false)
  toastMsg('success', `已上传：${data.name || baseName(data.path)}`)
}

// ---------------------------------------------------------------- 期望状态 → plan
function buildPlan() {
  const originals = trackViews.value.filter((track) => !track.added)
  const added = trackViews.value.filter((track) => track.added)
  // 视频轨恒保留，也要参与 order（后端按 order 决定轨道排列）
  const kept = originals.filter((track) => track.keep)
  const edits = {}
  for (const track of originals) {
    if (track.readonly) continue
    const orig = track._orig || {}
    const changed =
      track.language !== orig.language ||
      track.name !== orig.name ||
      Boolean(track.default) !== Boolean(orig.default) ||
      Boolean(track.forced) !== Boolean(orig.forced)
    if (changed) {
      edits[String(track.id)] = {
        language: track.language || 'und',
        name: track.name || '',
        default: Boolean(track.default),
        forced: Boolean(track.forced),
      }
    }
  }
  // 新增轨道条目（供 order 里用 add:<文件路径> 表示插入位置）
  const addedEntries = added
    .filter((track) => track.keep)
    .map((track) => {
      const base = {
        kind: track.kind,
        file: track.file.path,
        language: track.language || 'und',
        name: track.name || '',
        default: Boolean(track.default),
        forced: Boolean(track.forced),
      }
      return track.kind === 'audio'
        ? { ...base, sync_ms: Number(track.sync_ms) || 0 }
        : { ...base, encoding: track.encoding || 'auto', sync_ms: Number(track.sync_ms) || 0 }
    })
  // 混合顺序：数字 = 原有轨道 ID，add:<路径> = 新增轨道，按当前列表顺序输出
  const order = []
  for (const track of trackViews.value) {
    if (track.added) {
      if (track.keep) order.push(`add:${track.file.path}`)
    } else if (track.keep) {
      order.push(track.id)
    }
  }
  return {
    path: currentPath.value,
    title: title.value,
    chapters: {
      mode: chapterMode.value,
      file: chapterMode.value === 'import' ? chapterFile.value : null,
    },
    tracks: {
      order,
      drop: originals.filter((track) => !track.keep && !track.readonly).map((track) => track.id),
      edits,
      add: addedEntries,
      attachments_add: attachments.value.filter((item) => item.added && item.keep).map((item) => item.file.path),
      attachments_drop: attachments.value.filter((item) => !item.added && !item.keep).map((item) => item.name),
    },
    output: {
      mode: outputMode.value,
      dir: outputDir.value,
      // no_backup 只在原地替换时有意义
      no_backup: outputMode.value === 'replace' ? Boolean(noBackup.value) : false,
    },
    extra_args: extraArgsText.value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean),
    // 时长不一致警告需要用户在预览弹窗显式确认，确认后才随 plan 提交
    ...(durationMismatchConfirmed.value ? { confirmed_duration_mismatch: true } : {}),
  }
}

async function openPreview(skipGuard = false) {
  if (!currentPath.value) return
  // 重复提交保护：pending/running 时先让用户选择更新/新建/取消
  if (!skipGuard && !(await guardDuplicateSubmission('preview'))) return
  durationMismatchConfirmed.value = false
  previewOpen.value = true
  previewLoading.value = true
  planResult.value = null
  try {
    planResult.value = await api.post('/plan', buildPlan())
  } catch (err) {
    previewOpen.value = false
    toastMsg('error', `预览失败：${err.message}`)
  } finally {
    previewLoading.value = false
  }
}

async function applyExtraArgs() {
  if (!currentPath.value) {
    toastMsg('warning', '请先选择文件')
    return
  }
  extraArgsChecking.value = true
  extraArgsError.value = ''
  extraArgsOk.value = ''
  try {
    const result = await api.post('/plan', buildPlan())
    planResult.value = result
    const blockers = result.blockers || []
    const argBlocker = blockers.find((item) => ['extra_args', 'extra_args_engine'].includes(item.code))
    if (argBlocker) {
      extraArgsError.value = argBlocker.message
      toastMsg('error', argBlocker.message)
      return
    }
    extraArgsOk.value = '已应用：预览里的命令已包含这些参数'
    previewOpen.value = true
    if (blockers.length) {
      toastMsg('warning', `附加参数已应用，但计划还有 ${blockers.length} 项阻塞，请先处理`)
    } else {
      toastMsg('success', '附加参数已应用')
    }
  } catch (err) {
    extraArgsError.value = err.message
    toastMsg('error', `验证失败：${err.message}`)
  } finally {
    extraArgsChecking.value = false
  }
}

watch(extraArgsText, () => {
  extraArgsError.value = ''
  extraArgsOk.value = ''
})

async function confirmRun() {
  if (!planResult.value || previewSubmitting.value) return
  if ((planResult.value.blockers || []).length) return
  // 有 duration_mismatch 警告时必须先勾选「我已知晓」
  if (hasDurationMismatch.value && !durationMismatchConfirmed.value) {
    toastMsg('warning', '请先勾选「我已知晓时长不一致，仍要执行」再确认')
    return
  }
  previewSubmitting.value = true
  savingPlan.value = true
  try {
    // 编辑队列任务：确认后走 update，不再创建新任务
    if (editingJobId.value) {
      await submitJobUpdate()
      return
    }
    const data = await api.post('/jobs', { plan: buildPlan() })
    previewOpen.value = false
    const jobId = data?.id || data?.job_id
    toastMsg('success', `已加入队列${jobId ? `（${jobId}）` : ''}`)
    seedSubmittedJob(data, currentPath.value)
    await loadQueue(false)
    await loadStatus()
    await refreshFileStatuses()
  } catch (err) {
    toastMsg('error', `入队失败：${err.message}`)
  } finally {
    previewSubmitting.value = false
    savingPlan.value = false
  }
}

// 仅加入队列：先 /plan 校验（blockers 提示，不入队），再以 hold=true 入队，等队列页统一开始
// 编辑队列任务时语义改为「更新且保持原有 hold 状态」
async function enqueueHold(skipGuard = false) {
  if (!currentPath.value || holdSubmitting.value) return
  // 重复提交保护：pending/running 时先让用户选择更新/新建/取消
  if (!skipGuard && !(await guardDuplicateSubmission('enqueue'))) return
  holdSubmitting.value = true
  try {
    const preview = await api.post('/plan', buildPlan())
    if ((preview?.blockers || []).length) {
      const messages = (preview.blockers || [])
        .map((item) => item.message || item.code)
        .filter(Boolean)
        .slice(0, 2)
      toastMsg('error', messages.length ? messages.join('；') : '计划存在阻塞项，无法加入队列')
      return
    }
    // 时长不一致需要显式勾选确认，仅支持走「预览并确认/预览并更新」流程
    if ((preview?.warnings || []).some((item) => (item?.code || '') === 'duration_mismatch')) {
      toastMsg('warning', '计划存在时长不一致警告，请用「预览并确认」勾选确认后再执行')
      return
    }
    if (editingJobId.value) {
      await submitJobUpdate()
      return
    }
    const data = await api.post('/jobs', { plan: buildPlan(), hold: true })
    const jobId = data?.id || data?.job_id
    toastMsg('success', `已加入队列（待启动）${jobId ? `：${jobId}` : ''}，到队列页统一开始`)
    seedSubmittedJob(data, currentPath.value)
    await loadQueue(true)
    await loadStatus()
    await refreshFileStatuses()
  } catch (err) {
    toastMsg('error', `加入队列失败：${err.message}`)
  } finally {
    holdSubmitting.value = false
  }
}

// 更新正在编辑的队列任务（hold 状态由后端保留）
async function submitJobUpdate() {
  const jobId = editingJobId.value
  if (!jobId) return false
  try {
    const data = await api.post(`/jobs/${encodeURIComponent(jobId)}/update`, { plan: buildPlan() })
    editingJobId.value = ''
    editingJobName.value = ''
    previewOpen.value = false
    toastMsg('success', '队列任务已更新')
    seedSubmittedJob(data || { id: jobId, status: 'pending', path: currentPath.value })
    await loadQueue(false)
    await loadStatus()
    await refreshFileStatuses()
    return true
  } catch (err) {
    // 任务已被取消/开始、或新计划出现 blockers 时后端会返回 message：清空编辑态并刷新
    editingJobId.value = ''
    editingJobName.value = ''
    previewOpen.value = false
    toastMsg('error', `队列任务更新失败：${err.message}`)
    await loadQueue(false)
    await loadStatus()
    await refreshFileStatuses()
    return false
  }
}

// 从队列进入编辑：用任务里的原始 plan 回填编辑器
async function startEditJob(job) {
  if (!job?.plan || typeof job.plan !== 'object') {
    toastMsg('warning', '该任务没有可编辑的计划，请取消后重新加入')
    return
  }
  editingJobId.value = job.id
  editingJobName.value = job.name || job.path || job.id
  switchTab('edit')
  currentPath.value = job.path || ''
  const loaded = await loadProbe(job.path)
  if (!loaded) {
    editingJobId.value = ''
    editingJobName.value = ''
    toastMsg('error', '任务文件已失效，无法编辑')
    return
  }
  applyPlanToEditor(job.plan)
  editorTab.value = 'video'
  toastMsg('success', '已载入队列任务，提交后将更新该任务')
}

function cancelEditing() {
  if (!editingJobId.value) return
  editingJobId.value = ''
  editingJobName.value = ''
  toastMsg('info', '已取消队列任务编辑')
}

// ---------------------------------------------------------------- 队列操作
async function cancelJob(job) {
  askConfirm({
    title: '取消任务',
    text: `确定取消「${job.name || job.path}」？运行中的任务会终止并清理临时文件。`,
    confirmText: '取消任务',
    color: 'error',
    action: async () => {
      await api.post(`/jobs/${encodeURIComponent(job.id)}/cancel`)
      toastMsg('success', '已请求取消')
      await loadQueue(false)
      await loadStatus()
    },
  })
}

async function moveJob(job, to) {
  try {
    await api.post(`/jobs/${encodeURIComponent(job.id)}/move`, { to })
    await loadQueue(true)
  } catch (err) {
    toastMsg('error', `调整顺序失败：${err.message}`)
  }
}

async function togglePause(paused) {
  try {
    await api.post('/jobs/pause', { paused })
    queuePaused.value = paused
    toastMsg('success', paused ? '队列已暂停，当前任务结束后不再开始新任务' : '队列已恢复')
    await loadQueue(true)
  } catch (err) {
    toastMsg('error', `操作失败：${err.message}`)
  }
}

function clearPending() {
  askConfirm({
    title: '清空等待队列',
    text: `确定清空 ${pendingJobs.value.length} 个等待中的任务？正在运行的任务不受影响。`,
    confirmText: '清空等待',
    color: 'warning',
    action: async () => {
      await api.post('/jobs/clear')
      toastMsg('success', '已清空等待队列')
      await loadQueue(false)
      await loadStatus()
    },
  })
}

// 启动单个「待启动」任务
async function startJob(job) {
  try {
    await api.post(`/jobs/${encodeURIComponent(job.id)}/start`)
    toastMsg('success', `已开始：${job.name || job.path}`)
    await loadQueue(false)
    await loadStatus()
  } catch (err) {
    toastMsg('error', `启动失败：${err.message}`)
  }
}

// 全部开始：解除所有待启动任务并恢复队列
async function startAllJobs() {
  try {
    const data = await api.post('/jobs/start')
    const started = Number(data?.started) || 0
    toastMsg('success', started ? `已开始 ${started} 个待启动任务` : '没有待启动任务')
    queuePaused.value = Boolean(data?.paused)
    await loadQueue(false)
    await loadStatus()
  } catch (err) {
    toastMsg('error', `全部开始失败：${err.message}`)
  }
}

async function setConcurrency(value) {
  const previous = config.value.concurrency
  config.value = { ...config.value, concurrency: value }
  try {
    const saved = await api.post('/config', { ...config.value })
    config.value = { ...config.value, ...(saved || {}) }
    toastMsg('success', `并发数已设为 ${value}`)
  } catch (err) {
    config.value = { ...config.value, concurrency: previous }
    toastMsg('error', `保存并发数失败：${err.message}`)
  }
}

// ---------------------------------------------------------------- 历史操作
function rollbackHistory(item) {
  askConfirm({
    title: '回滚到备份',
    text: `确定用备份恢复「${item.name || item.path}」？当前文件会被备份版本覆盖。`,
    detail: item.backup_path || '',
    confirmText: '回滚',
    color: 'warning',
    action: async () => {
      await api.post(`/history/${encodeURIComponent(item.id)}/rollback`)
      toastMsg('success', '已从备份回滚')
      await loadHistory(false)
      await loadStatus()
    },
  })
}

// 删除单条历史记录（不会删除备份文件）
function deleteHistory(item) {
  askConfirm({
    title: '删除历史记录',
    text: `确定删除「${item.name || item.path}」这条历史记录？`,
    detail: '只删除记录，不会删除备份文件。',
    confirmText: '删除',
    color: 'error',
    action: async () => {
      const data = await api.post(`/history/${encodeURIComponent(item.id)}/delete`)
      if (data?.deleted) {
        toastMsg('success', '历史记录已删除')
      } else {
        toastMsg('warning', '记录不存在或已删除')
      }
      await loadHistory(false)
    },
  })
}

// 清空全部历史记录（不会删除备份文件）
function clearHistory() {
  askConfirm({
    title: '清空历史记录',
    text: '确定清空全部历史记录？此操作不可撤销。',
    detail: '只删除记录，不会删除备份文件。',
    confirmText: '清空',
    color: 'error',
    action: async () => {
      const data = await api.post('/history/clear')
      const count = Number(data?.deleted) || 0
      toastMsg('success', count ? `已清空 ${count} 条历史记录` : '没有可清空的历史记录')
      await loadHistory(false)
    },
  })
}

/**
 * 把历史记录里的完整 plan 回填到编辑器（先探测、再叠加 plan）
 * 字段与 /plan 请求体一致：tracks.order/drop/edits/add、attachments、chapters、title、output、extra_args
 */
function applyPlanToEditor(plan) {
  if (!plan || typeof plan !== 'object') return false
  // 探测时会自动预勾选匹配的字幕；历史 plan 才是最终状态，先清空所有新增轨道
  const baseOriginals = trackViews.value.filter((track) => !track.added)
  trackViews.value = baseOriginals
  attachments.value = attachments.value.filter((item) => !item.added)

  const trackPlan = plan.tracks && typeof plan.tracks === 'object' ? plan.tracks : {}
  const byId = new Map(baseOriginals.map((track) => [Number(track.id), track]))

  // 1) 轨道顺序：order 里有的按 order，其余（已删除的）追加到末尾保留展示
  const ordered = []
  const seen = new Set()
  for (const rawId of Array.isArray(trackPlan.order) ? trackPlan.order : []) {
    const track = byId.get(Number(rawId))
    if (track && !seen.has(track)) {
      ordered.push(track)
      seen.add(track)
    }
  }
  for (const track of baseOriginals) {
    if (!seen.has(track)) ordered.push(track)
  }

  // 2) 删除标记
  const dropIds = new Set(
    (Array.isArray(trackPlan.drop) ? trackPlan.drop : []).map((id) => Number(id)),
  )
  for (const track of ordered) {
    if (track.readonly) continue
    track.keep = !dropIds.has(Number(track.id))
  }

  // 3) 轨道编辑（语言 / 名称 / 默认 / 强制）
  const edits = trackPlan.edits && typeof trackPlan.edits === 'object' ? trackPlan.edits : {}
  for (const [key, patch] of Object.entries(edits)) {
    const track = byId.get(Number(key))
    if (!track || track.readonly || !patch || typeof patch !== 'object') continue
    if (patch.language != null) track.language = String(patch.language)
    if (patch.name != null) track.name = String(patch.name)
    if (patch.default != null) track.default = Boolean(patch.default)
    if (patch.forced != null) track.forced = Boolean(patch.forced)
  }

  // 4) 新增轨道（字幕 / 音频）
  const addedPaths = new Set()
  for (const item of Array.isArray(trackPlan.add) ? trackPlan.add : []) {
    if (!item || typeof item !== 'object' || !item.file) continue
    const filePath = String(item.file)
    if (!filePath || addedPaths.has(filePath)) continue
    addedPaths.add(filePath)
    const kind = item.kind === 'audio' ? 'audio' : 'subtitle'
    ordered.push({
      id: `add-${kind}-${filePath}`,
      type: kind,
      kind,
      added: true,
      keep: true,
      language: item.language || inferLanguage(baseName(filePath)),
      name: item.name || '',
      default: Boolean(item.default),
      forced: Boolean(item.forced),
      encoding: item.encoding || 'auto',
      sync_ms: Number(item.sync_ms) || 0,
      file: { name: baseName(filePath), path: filePath, size: null, ext: extName(filePath) },
    })
  }
  // 4.5) 混合顺序：order 中 `add:<路径>` 表示新增轨道的插入位置，按 order 重排
  const rawOrder = Array.isArray(trackPlan.order) ? trackPlan.order : []
  if (rawOrder.some((token) => typeof token === 'string' && token.startsWith('add:'))) {
    const originalById = new Map(ordered.filter((track) => !track.added).map((track) => [Number(track.id), track]))
    const addedByPath = new Map(ordered.filter((track) => track.added).map((track) => [track.file?.path, track]))
    const finalOrder = []
    const seenTracks = new Set()
    for (const token of rawOrder) {
      let target = null
      if (typeof token === 'string' && token.startsWith('add:')) {
        target = addedByPath.get(token.slice(4)) || null
      } else {
        const numeric = Number(token)
        if (Number.isFinite(numeric)) target = originalById.get(numeric) || null
      }
      if (target && !seenTracks.has(target)) {
        finalOrder.push(target)
        seenTracks.add(target)
      }
    }
    for (const track of ordered) {
      if (!seenTracks.has(track)) finalOrder.push(track)
    }
    ordered.length = 0
    ordered.push(...finalOrder)
  }
  trackViews.value = ordered

  // 5) 附件：attachments_add 追加为新增字体，attachments_drop 标记删除
  const attachmentByName = new Map(attachments.value.map((item) => [item.name, item]))
  for (const name of Array.isArray(trackPlan.attachments_drop) ? trackPlan.attachments_drop : []) {
    const item = attachmentByName.get(String(name))
    if (item) item.keep = false
  }
  const attachmentPaths = new Set(attachments.value.filter((item) => item.added).map((item) => item.file?.path))
  for (const rawPath of Array.isArray(trackPlan.attachments_add) ? trackPlan.attachments_add : []) {
    const path = String(rawPath || '')
    if (!path || attachmentPaths.has(path)) continue
    attachmentPaths.add(path)
    attachments.value = [
      ...attachments.value,
      {
        id: `add-font-${path}`,
        name: baseName(path),
        mime: '',
        size: null,
        keep: true,
        added: true,
        file: { name: baseName(path), path, size: null },
      },
    ]
  }

  // 6) 章节 / 容器标题
  const chapterPlan = plan.chapters && typeof plan.chapters === 'object' ? plan.chapters : {}
  chapterMode.value = ['keep', 'clear', 'import'].includes(chapterPlan.mode) ? chapterPlan.mode : 'keep'
  chapterFile.value = chapterMode.value === 'import' ? String(chapterPlan.file || '') : ''
  if (plan.title != null) title.value = String(plan.title)

  // 7) 输出
  const outputPlan = plan.output && typeof plan.output === 'object' ? plan.output : {}
  outputMode.value = outputPlan.mode === 'replace' ? 'replace' : 'dir'
  outputDir.value = outputPlan.dir ? String(outputPlan.dir) : (config.value.output_dir || '')
  noBackup.value = outputMode.value === 'replace' && Boolean(outputPlan.no_backup)

  // 8) 附加参数（每行一条）
  const extraArgs = Array.isArray(plan.extra_args) ? plan.extra_args : []
  extraArgsText.value = extraArgs.map((line) => String(line)).join('\n')
  return true
}

async function reopenHistory(item) {
  if (!item?.path) {
    toastMsg('error', '该记录没有可打开的文件路径')
    return
  }
  switchTab('edit')
  currentPath.value = item.path
  const loaded = await loadProbe(item.path)
  if (!loaded) {
    toastMsg('error', '该记录的文件已失效，无法回填')
    return
  }
  const planData = item.plan && typeof item.plan === 'object' ? item.plan : null
  if (!planData) {
    toastMsg('warning', '该记录没有可回填的配置，已只打开文件')
    return
  }
  try {
    applyPlanToEditor(planData)
    editorTab.value = 'video'
    toastMsg('success', '已回填历史记录的编辑配置')
  } catch (err) {
    toastMsg('error', `回填失败：${err.message}`)
  }
}

// ---------------------------------------------------------------- 引擎安装
function askInstallEngine() {
  askConfirm({
    title: '安装 MKVToolNix',
    text: '将从 Debian 源执行 apt 安装 mkvtoolnix（约几十 MB），安装过程在后台进行，可在设置页查看日志。',
    confirmText: '开始安装',
    action: async () => {
      await api.post('/engine/install', { method: 'apt' })
      installStarting.value = true
      toastMsg('info', '已开始安装，完成后引擎状态会自动刷新')
      pollEngineInstall()
    },
  })
}

async function pollEngineInstall() {
  if (installTimer) clearTimeout(installTimer)
  installTimer = setTimeout(async () => {
    try {
      const data = await api.get('/status')
      status.value = data || {}
      if (data?.engine_install?.running) {
        pollEngineInstall()
        return
      }
      installTimer = null
      installStarting.value = false
      if (data?.engine_install?.ok === false) {
        toastMsg('error', '引擎安装失败，请到设置页查看日志')
      } else {
        toastMsg('success', '引擎安装完成')
        await loadStatus()
      }
    } catch (err) {
      installTimer = null
      installStarting.value = false
    }
  }, 1000)
}

// ---------------------------------------------------------------- 确认弹窗
function askConfirm(options) {
  confirmState.value = {
    open: true,
    title: options.title || '确认操作',
    text: options.text || '',
    detail: options.detail || '',
    confirmText: options.confirmText || '确定',
    color: options.color || 'primary',
    loading: false,
    action: options.action || null,
  }
}

async function runConfirm() {
  const action = confirmState.value.action
  confirmState.value = { ...confirmState.value, open: false }
  if (!action) return
  try {
    await action()
  } catch (err) {
    toastMsg('error', err.message || '操作失败')
  }
}

// ---------------------------------------------------------------- Tab / 配置保存
const lastNonSettingsTab = ref('edit')

function switchTab(key) {
  if (key === 'settings' && tab.value !== 'settings') {
    lastNonSettingsTab.value = tab.value
  }
  tab.value = key
  // 切换页签时刷新文件树的队列/历史状态徽标
  fileStatusTick.value += 1
  if (key === 'queue') loadQueue(false)
  if (key === 'history') loadHistory(false)
}

/** 从设置页返回上一次停留的主页面（编辑/队列/历史）。 */
function backFromSettings() {
  switchTab(lastNonSettingsTab.value || 'edit')
}

function onConfigSaved(saved) {
  config.value = { ...config.value, ...(saved || {}) }
}

function exitPanel() {
  if (props.showClose) {
    emit('close')
    return
  }
  window.location.href = `${window.location.origin}/#/plugins?tab=installed`
}

// ---------------------------------------------------------------- 定时器
function ensureQueueTimer() {
  if (hasActiveJobs.value && !queueTimer) {
    queueTimer = setInterval(async () => {
      await loadQueue(true)
    }, 1000)
  } else if (!hasActiveJobs.value && queueTimer) {
    clearInterval(queueTimer)
    queueTimer = null
  }
}

watch(hasActiveJobs, ensureQueueTimer)
// 切换文件：重置状态条并按新 path 拉取状态；关闭文件时停止轮询
watch(currentPath, (path) => {
  statusDismissed.value = false
  if (!path) {
    currentFileStatus.value = null
    stopStatusPoll()
    return
  }
  refreshFileStatuses()
})
// 离开编辑页停止轮询，回到编辑页重新拉取
watch(tab, (value) => {
  if (value === 'edit' && currentPath.value) refreshFileStatuses()
  else stopStatusPoll()
})
// 预览弹窗关闭后清空「时长不一致已确认」，避免下次提交误带 confirmed_duration_mismatch
watch(previewOpen, (open) => {
  if (!open) durationMismatchConfirmed.value = false
})

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '100rem' })
  // 监听插件根容器宽度（不依赖视口断点），PC 模式下容器窄时也能切紧凑布局
  if (rootRef.value) {
    // 宿主卡片弹窗（VDialog）内：布局要尽量撑满弹窗，减少上下留白
    inHostDialog.value = Boolean(rootRef.value.closest('.v-dialog'))
    containerWidth.value = rootRef.value.clientWidth || 0
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0]
        const width = entry?.contentRect?.width || entry?.target?.clientWidth || 0
        if (width) containerWidth.value = width
      })
      resizeObserver.observe(rootRef.value)
    }
  }
  await loadConfig()
  await Promise.all([loadStatus(), loadQueue(true), loadHistory(true), loadArchiveTools()])
  statusLoaded.value = true
  await refreshFileStatuses()
  statusTimer = setInterval(async () => {
    await loadStatus()
    if (tab.value === 'queue') await loadQueue(true)
  }, 5000)
  ensureQueueTimer()
})

onBeforeUnmount(() => {
  if (resizeObserver) resizeObserver.disconnect()
  if (disabledMaskTimer) clearTimeout(disabledMaskTimer)
  resizeObserver = null
  stopStatusPoll()
  if (statusTimer) clearInterval(statusTimer)
  if (queueTimer) clearInterval(queueTimer)
  if (installTimer) clearTimeout(installTimer)
  statusTimer = null
  queueTimer = null
  installTimer = null
})
</script>

<template>
  <div
    ref="rootRef"
    class="mkv-page"
    :class="{ 'mkv-narrow': narrow, 'mkv-medium': medium, 'mkv-wide': wide, 'mkv-host-dialog': inHostDialog, 'mkv-has-content': hasContent }"
  >
    <!-- 插件被停用：只显示启用指引，不显示依赖/引擎提示，也不拦截其它操作 -->
    <div v-if="statusLoaded && showDisabledMask" class="mkv-disabled-mask">
      <div class="mkv-disabled-card">
        <v-icon size="46" color="grey" icon="mdi-power-off" class="mb-2" />
        <div class="mkv-disabled-title">插件已停用</div>
        <div class="mkv-disabled-desc">
          请到 MoviePilot 的「设置 → 插件」页面找到「MKV 工具箱」：<br />
          1. 点击「启用 / 启动」<br />
          2. 点击「应用保存」<br />
          3. 回到本页刷新
        </div>
        <div class="mkv-disabled-actions">
          <v-btn color="primary" variant="flat" prepend-icon="mdi-cog-outline" @click="openSettingsFromDisabled">
            前往设置启用
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="reloadPage">
            刷新页面
          </v-btn>
        </div>
      </div>
    </div>
    <!-- ================= 顶栏 ================= -->
    <header class="mkv-header">
      <div class="mkv-brand">
        <img class="mkv-logo mkv-logo--img" :src="logoUrl" alt="MKV 工具箱" />
        <span v-if="!medium" class="mkv-brand-text">{{ narrow ? '工具箱' : 'MKV 工具箱' }}</span>
        <span v-if="wide" class="mkv-ver">v{{ status.version || '0.1.50' }}</span>
        <span v-if="wide" class="mkv-ver mkv-ver--ui">UI {{ UI_BUILD }}</span>
      </div>

      <div v-if="wide" class="mkv-engine-chips">
        <span class="engine-chip" :class="engine.mkvmerge?.ok ? 'ok' : 'warn'">
          <i class="dot" />{{ mkvmergeChip }}
        </span>
        <span class="engine-chip" :class="engine.ffmpeg?.ok ? 'ok' : 'bad'">
          <i class="dot" />{{ ffmpegChip }}
        </span>
        <span
          class="engine-chip"
          :class="[archiveChipOk ? 'ok' : 'warn', { 'engine-chip--click': !archiveChipOk }]"
          :title="archiveChipOk ? archiveHint : `${archiveHint}（点击去设置安装）`"
          @click="!archiveChipOk && switchTab('settings')"
        >
          <i class="dot" />{{ archiveChip }}
        </span>
      </div>

      <span class="mkv-spacer" />

      <nav class="mkv-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          type="button"
          class="mkv-nav-btn"
          :class="{ active: tab === item.key }"
          @click="switchTab(item.key)"
        >
          {{ item.label }}
          <span v-if="item.key === 'queue' && queueBadge" class="mkv-nav-badge">{{ queueBadge }}</span>
        </button>
      </nav>

      <button
        type="button"
        class="mkv-icon-btn"
        :title="tab === 'settings' ? '返回主页面' : '设置'"
        @click="tab === 'settings' ? backFromSettings() : switchTab('settings')"
      >
        <v-icon size="18" :icon="tab === 'settings' ? 'mdi-arrow-left' : 'mdi-cog-outline'" />
      </button>

      <template v-if="wide">
        <span class="mkv-divider" />
        <button type="button" class="mkv-exit-btn" title="退出插件（返回插件管理页）" @click="exitPanel">
          <v-icon size="14" icon="mdi-close" />
          <span>退出</span>
        </button>
      </template>
      <button v-else type="button" class="mkv-icon-btn" title="退出" @click="exitPanel">
        <v-icon size="18" icon="mdi-close" />
      </button>
    </header>

    <!-- ================= 引擎提示 ================= -->
    <div v-if="!engineReady" class="mkv-banner">
      <v-icon size="16" icon="mdi-alert-outline" />
      <span>未检测到 MKVToolNix，当前只能预览不能执行</span>
      <span class="mkv-spacer" />
      <v-btn size="small" color="primary" variant="flat" :loading="installStarting" @click="askInstallEngine">
        立即安装
      </v-btn>
      <v-btn size="small" variant="text" @click="switchTab('settings')">去设置</v-btn>
    </div>

    <!-- ================= 主区域 ================= -->
    <main class="mkv-body">
      <!-- ---------------- 编辑页 ---------------- -->
      <section v-if="tab === 'edit'" class="mkv-edit">
        <aside v-if="wide" class="mkv-tree-panel">
          <FileTree
            :api="api"
            :roots="config.roots || []"
            :current="currentPath"
            :refresh-tick="fileStatusTick"
            @select="onSelectFile"
          />
        </aside>

        <section class="mkv-editor">
          <!-- 手机文件栏 -->
          <div v-if="!wide" class="mkv-mobile-bar">
            <v-btn size="small" variant="tonal" prepend-icon="mdi-menu" @click="treeDialog = true">文件</v-btn>
            <span class="mkv-mobile-file" :title="currentPath">
              {{ currentPath ? baseName(currentPath) : '未选择文件' }}
            </span>
            <v-btn
              size="small"
              variant="text"
              icon="mdi-refresh"
              :disabled="!currentPath"
              title="重新探测"
              @click="reprobe"
            />
          </div>

          <v-alert
            v-if="error"
            type="error"
            variant="tonal"
            density="compact"
            closable
            class="mb-2"
            @click:close="error = ''"
          >
            {{ error }}
          </v-alert>

          <!-- 队列内编辑提示 -->
          <div v-if="editingJobId" class="editing-banner">
            <v-icon size="16" icon="mdi-pencil-box-outline" />
            <span class="editing-banner-text">
              正在编辑队列任务：<b>{{ editingJobName }}</b>，提交后会更新该任务
            </span>
            <v-btn size="x-small" variant="text" append-icon="mdi-close" @click="cancelEditing">取消编辑</v-btn>
          </div>

          <v-skeleton-loader v-if="probeLoading" type="article, list-item@6" />

          <div v-else-if="!probe" class="mkv-empty-editor">
            <v-icon size="42" icon="mdi-filmstrip-box-multiple" class="mkv-empty-icon" />
            <div class="mkv-empty-title">从{{ !wide ? '「文件」' : '左侧目录' }}选择 .mkv / .m2ts 文件开始编辑</div>
            <div class="mkv-empty-hint">只做容器层调整：内封/删除字幕、管理音轨、加字体附件、改标题与章节，不转码、不剪片</div>
          </div>

          <template v-else>
            <!-- 文件信息 -->
            <div class="file-head">
              <div class="file-head-main">
                <div class="file-title-row">
                  <div class="file-title" :title="mediaTitle">{{ mediaTitle }}</div>
                  <span
                    v-if="statusMeta"
                    class="file-status-chip"
                    :class="`file-status-chip--${statusMeta.state}`"
                  >
                    {{ statusMeta.label }}
                  </span>
                </div>
                <div class="file-path" :title="probe.path">{{ probe.path }}</div>
              </div>
              <div class="file-actions">
                <template v-if="wide">
                  <v-btn size="small" variant="tonal" @click="reprobe">重新探测</v-btn>
                  <v-btn size="small" variant="text" @click="copyPath">复制路径</v-btn>
                </template>
                <v-btn
                  size="small"
                  variant="text"
                  icon="mdi-close"
                  title="关闭文件（回到未选择文件）"
                  aria-label="关闭文件"
                  class="file-close-btn"
                  @click="clearFile"
                />
              </div>
            </div>

            <!-- 提交后状态条：当前文件的队列/历史状态 -->
            <div
              v-if="statusBannerVisible"
              class="submit-status-banner"
              :class="`submit-status-banner--${statusMeta.state}`"
            >
              <v-icon size="15" :icon="statusIcon(statusMeta.state)" />
              <span class="submit-status-text">
                已加入队列<template v-if="statusMeta.id"> · #{{ statusMeta.id }}</template>
                · {{ statusMeta.label }}
              </span>
              <v-spacer />
              <v-btn size="x-small" variant="tonal" @click="switchTab('queue')">去队列编辑</v-btn>
              <v-btn size="x-small" variant="text" @click="statusDismissed = true">关闭提示</v-btn>
            </div>

            <div class="info-strip">
              <span class="info-chip">{{ container.format || 'MKV' }}</span>
              <span class="info-chip">{{ fmtBytes(probe.size) }}</span>
              <span class="info-chip">时长 {{ fmtDuration(container.duration) }}</span>
              <span class="info-chip">{{ probe.tracks?.length || 0 }} 条轨道</span>
              <span class="info-chip">{{ chapters.length }} 章节</span>
              <span class="info-chip">{{ attachments.length }} 附件</span>
            </div>

            <!-- 编辑器 Tab -->
            <nav class="mkv-editor-tabs">
              <button
                v-for="item in editorTabs"
                :key="item.key"
                type="button"
                class="mkv-tab-btn"
                :class="{ active: editorTab === item.key }"
                @click="editorTab = item.key"
              >
                {{ item.label }}
              </button>
            </nav>

            <!-- 视频 -->
            <div v-if="editorTab === 'video'" class="mkv-panel">
              <v-card variant="flat" class="mkv-card">
                <div class="mkv-card-title">
                  视频轨
                  <span class="mkv-card-hint">视频轨不可删除，只读</span>
                </div>
                <div v-if="videoTrack" class="kv-grid">
                  <div class="kv-item"><span>编码</span><b>{{ codecLabel(videoTrack) }}</b></div>
                  <div class="kv-item">
                    <span>分辨率</span>
                    <b>{{ videoTrack.width && videoTrack.height ? `${videoTrack.width} × ${videoTrack.height}` : '—' }}</b>
                  </div>
                  <div class="kv-item"><span>动态范围</span><b>{{ videoTrack.hdr || 'SDR' }}</b></div>
                  <div class="kv-item">
                    <span>码率</span>
                    <b>
                      <template v-if="videoTrack.bitrate">
                        {{ videoTrack.bitrate_estimated ? '≈ ' : '' }}{{ (Number(videoTrack.bitrate) / 1000000).toFixed(1) }} Mbps{{ videoTrack.bitrate_estimated ? '（估算）' : '' }}
                      </template>
                      <template v-else>—</template>
                    </b>
                  </div>
                  <div class="kv-item"><span>帧率</span><b>{{ videoTrack.fps ? `${Number(videoTrack.fps).toFixed(3)} fps` : '—' }}</b></div>
                  <div class="kv-item"><span>时长</span><b>{{ fmtDuration(videoTrack.duration || container.duration, true) }}</b></div>
                  <div class="kv-item"><span>轨道数</span><b>{{ probe.tracks?.length || 0 }}</b></div>
                  <div class="kv-item"><span>容器</span><b>{{ container.format || 'Matroska' }}</b></div>
                </div>
                <div v-else class="mkv-empty-tip">探测结果里没有视频轨（可能是纯音频文件）</div>
              </v-card>
            </div>

            <!-- 音频 -->
            <div v-else-if="editorTab === 'audio'" class="mkv-panel">
              <TrackEditor
                kind="audio"
                :tracks="audioTracks"
                :layout="layoutMode"
                @pick="openPicker"
                @upload="openUpload"
                @move="moveTrack"
                @remove="removeTrack"
                @estimate="estimateTrackOffset"
              />
            </div>

            <!-- 字幕 -->
            <div v-else-if="editorTab === 'subtitle'" class="mkv-panel">
              <TrackEditor
                kind="subtitle"
                :tracks="subtitleTracks"
                :layout="layoutMode"
                @pick="openPicker"
                @upload="openUpload"
                @move="moveTrack"
                @remove="removeTrack"
                @estimate="estimateTrackOffset"
              />
            </div>

            <!-- 附件 -->
            <div v-else-if="editorTab === 'attach'" class="mkv-panel">
              <v-card variant="flat" class="mkv-card">
                <div class="mkv-card-title">附件（仅字体）</div>
                <div v-if="!attachments.length" class="mkv-empty-tip">暂无附件，可从目录选择或上传字体文件</div>
                <table v-else-if="!narrow" class="attach-table">
                  <thead>
                    <tr>
                      <th>文件名</th>
                      <th class="col-mime">类型</th>
                      <th class="col-size">大小</th>
                      <th class="col-ops"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in attachments" :key="item.id" :class="{ dropping: !item.keep }">
                      <td>
                        <span class="attach-name" :title="item.file?.path || item.name">{{ item.name }}</span>
                        <span v-if="item.added" class="attach-tag">新增</span>
                      </td>
                      <td class="col-mime">{{ attachmentType(item) }}</td>
                      <td class="col-size">{{ fmtBytes(item.size) }}</td>
                      <td class="col-ops">
                        <div class="attach-ops">
                          <v-btn
                            size="x-small"
                            variant="tonal"
                            :icon="!item.added && !item.keep ? 'mdi-restore' : 'mdi-close'"
                            :title="!item.added && !item.keep ? '恢复该附件' : (item.added ? '移除新增' : '标记删除')"
                            @click="toggleAttachment(item)"
                          />
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="attach-cards">
                  <div v-for="item in attachments" :key="item.id" class="attach-card" :class="{ dropping: !item.keep }">
                    <div class="attach-card-main">
                      <div class="attach-name" :title="item.file?.path || item.name">{{ item.name }}</div>
                      <div class="attach-sub">{{ attachmentType(item) }} · {{ fmtBytes(item.size) }}</div>
                    </div>
                    <span v-if="item.added" class="attach-tag">新增</span>
                    <v-btn
                      size="small"
                      variant="tonal"
                      :icon="!item.added && !item.keep ? 'mdi-restore' : 'mdi-close'"
                      @click="toggleAttachment(item)"
                    />
                  </div>
                </div>
                <div class="mkv-add-row">
                  <v-btn size="small" variant="tonal" prepend-icon="mdi-folder-open-outline" @click="openPicker('font')">
                    从目录选择字体
                  </v-btn>
                  <v-btn size="small" variant="text" prepend-icon="mdi-upload-outline" @click="openUpload('font')">
                    上传字体
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    prepend-icon="mdi-folder-zip-outline"
                    :loading="archiveLoading"
                    @click="openArchivePicker"
                  >
                    解压字体压缩包
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    prepend-icon="mdi-zip-box-open-outline"
                    @click="openArchiveBatch"
                  >
                    从目录批量解压
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    prepend-icon="mdi-folder-search-outline"
                    class="scan-fonts-btn"
                    @click="scanSiblingFonts"
                  >
                    扫描同目录字体
                  </v-btn>
                </div>
                <div class="archive-hint">{{ archiveHint }}</div>
                <div class="mkv-empty-tip" style="margin-top: 8px">只允许 ttf / otf / ttc；字体文件通常超过上传上限，建议用目录选择</div>
              </v-card>
            </div>

            <!-- 章节 -->
            <div v-else-if="editorTab === 'chapter'" class="mkv-panel">
              <v-card variant="flat" class="mkv-card">
                <div class="mkv-card-title">
                  章节
                  <span class="mkv-card-hint">支持 OGM XML 与 ffmetadata 导入（ffmetadata 由后端先转 OGM）</span>
                </div>
                <div class="mkv-form-row">
                  <label>处理方式</label>
                  <div class="mkv-form-value">
                    <v-btn-toggle
                      :model-value="chapterMode"
                      mandatory
                      density="compact"
                      variant="outlined"
                      divided
                      @update:model-value="chapterMode = $event"
                    >
                      <v-btn value="keep" size="small">保留</v-btn>
                      <v-btn value="clear" size="small">清空</v-btn>
                      <v-btn value="import" size="small">导入 XML</v-btn>
                    </v-btn-toggle>
                    <v-btn size="small" variant="text" prepend-icon="mdi-folder-open-outline" @click="openPicker('chapter')">
                      选择文件…
                    </v-btn>
                    <span v-if="chapterFile" class="mono sub ellipsis" :title="chapterFile">{{ baseName(chapterFile) }}</span>
                  </div>
                </div>
                <div class="mkv-form-row">
                  <label>容器标题</label>
                  <div class="mkv-form-value">
                    <v-text-field
                      v-model="title"
                      density="compact"
                      variant="outlined"
                      hide-details
                      placeholder="留空 = 不修改"
                      class="title-input"
                    />
                  </div>
                </div>
                <div class="mkv-sec-title">
                  现有章节（{{ chapters.length }} 个<template v-if="chapters.length > 3">，预览前 3 个</template>）
                </div>
                <table v-if="chapters.length" class="chapter-table">
                  <tbody>
                    <tr v-for="(chapter, index) in chapters.slice(0, 3)" :key="index">
                      <td class="chapter-time">{{ fmtDuration(chapter.start) }}</td>
                      <td>{{ chapter.title || `章节 ${index + 1}` }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="mkv-empty-tip">原文件没有章节</div>
              </v-card>
            </div>

            <!-- 高级 -->
            <div v-else-if="editorTab === 'advanced'" class="mkv-panel">
              <v-card variant="flat" class="mkv-card">
                <div class="mkv-card-title">
                  附加参数
                  <span class="mkv-card-hint">追加到自动生成的 mkvmerge 命令行（仅 mkvmerge 生效）</span>
                </div>
                <v-textarea
                  v-model="extraArgsText"
                  rows="4"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="mono extra-args"
                  placeholder="--sync 1:-250&#10;--track-name 2:国配"
                />
                <div class="extra-args-actions">
                  <v-btn
                    size="small"
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-check-decagram-outline"
                    :loading="extraArgsChecking"
                    @click="applyExtraArgs"
                  >
                    验证并应用
                  </v-btn>
                  <span v-if="extraArgsError" class="extra-args-msg extra-args-msg--error">{{ extraArgsError }}</span>
                  <span v-else-if="extraArgsOk" class="extra-args-msg extra-args-msg--ok">{{ extraArgsOk }}</span>
                </div>
                <div class="warnbox warnbox--red">
                  禁止参数：<span class="mono">-o / --output</span>（输出路径由插件控制）、输入文件。出现被禁参数会直接拒绝执行。
                </div>
                <div class="mkv-empty-tip">
                  常用示例 <span class="mono">--default-track-flag 2:1</span>、<span class="mono">--language 2:chi</span>、<span class="mono">--no-audio</span>；只填附加参数也会触发一次 mkvmerge 重封装。
                </div>
              </v-card>
            </div>

            <!-- 同级自动发现：仅字幕/音频/附件页显示对应类型 -->
            <SiblingPanel
              v-if="showSiblings"
              :items="siblingItems"
              :layout="layoutMode"
              :kind="siblingKind"
              :mounted="siblingMounted"
              @toggle="toggleSibling"
              @mount-toggle="toggleSiblingMount"
            />

            <!-- 输出 -->
            <div class="output-box">
              <label class="radio">
                <input type="radio" name="mkv-output-mode" :checked="outputMode === 'dir'" @change="outputMode = 'dir'" />
                <span>输出到目录</span>
              </label>
              <v-text-field
                v-if="outputMode === 'dir'"
                v-model="outputDir"
                density="compact"
                variant="outlined"
                hide-details
                class="output-path mono"
                placeholder="/config/plugins/MkvToolkit/output"
              />
              <span v-if="isNonMkvSource" class="output-tag output-tag--warn">输出文件名自动改为 .mkv</span>
              <span v-else class="output-tag">文件名自动＝原名</span>
              <label class="radio output-replace" :class="{ 'output-replace--disabled': isNonMkvSource }">
                <input
                  type="radio"
                  name="mkv-output-mode"
                  :checked="outputMode === 'replace'"
                  :disabled="isNonMkvSource"
                  @change="!isNonMkvSource && (outputMode = 'replace')"
                />
                <span>原地替换</span>
              </label>
            </div>
            <div v-if="isNonMkvSource" class="output-hint output-hint--warn">
              m2ts 需重封装为 MKV，不能原地替换；已自动改为「输出到目录」，输出文件名后缀为 .mkv
            </div>
            <!-- 原地替换的备份信息：默认先备份（可回滚），勾选不保存备份时红字提示 -->
            <div
              v-if="outputMode === 'replace'"
              class="backup-info"
              :class="{ 'backup-info--danger': noBackup }"
            >
              <v-icon
                size="14"
                :icon="noBackup ? 'mdi-alert-outline' : 'mdi-shield-check-outline'"
              />
              <span v-if="noBackup">备份：不做临时备份（替换失败时无恢复副本）</span>
              <span v-else>
                备份：临时备份到
                <span class="backup-dir mono" :title="backupDir">{{ backupDir }}</span>
                （任务成功后删除；失败保留并尝试还原源文件）
              </span>
            </div>
            <div v-if="outputMode === 'replace'" class="no-backup-row">
              <v-checkbox
                v-model="noBackup"
                density="compact"
                color="warning"
                hide-details
                label="不保存临时备份"
                class="no-backup-check"
              />
            </div>
            <div class="output-hint">
              输出目录是容器内路径（如 /media、/downloads），不是 Windows 盘符路径；对应宿主机映射目录
            </div>

            <!-- 执行 -->
            <div class="execute-row">
              <span class="execute-tip">执行前会先弹出预览确认，不会直接写文件</span>
              <span class="mkv-spacer" />
              <div class="execute-btns">
                <v-btn variant="text" @click="resetEditor">重置</v-btn>
                <v-btn
                  variant="tonal"
                  :disabled="!currentPath || !engineReady"
                  :loading="holdSubmitting"
                  @click="enqueueHold()"
                >
                  {{ editingJobId ? '更新任务' : '仅加入队列' }}
                </v-btn>
                <v-btn color="primary" variant="flat" :disabled="!currentPath || !engineReady" @click="openPreview()">
                  {{ engineReady ? (editingJobId ? '预览并更新' : '预览并确认') : '需安装 MKVToolNix' }}
                </v-btn>
              </div>
            </div>
          </template>
        </section>
      </section>

      <!-- ---------------- 队列页 ---------------- -->
      <QueuePage
        v-else-if="tab === 'queue'"
        :jobs="queueJobs"
        :paused="queuePaused"
        :concurrency="Number(config.concurrency) || 1"
        :held="Number(status.queue?.held) || 0"
        :editing-id="editingJobId"
        :loading="queueLoading"
        :layout="layoutMode"
        @refresh="loadQueue(false)"
        @cancel="cancelJob"
        @move="moveJob"
        @pause="togglePause"
        @clear="clearPending"
        @start="startJob"
        @start-all="startAllJobs"
        @edit="startEditJob"
        @set-concurrency="setConcurrency"
      />

      <!-- ---------------- 历史页 ---------------- -->
      <HistoryPage
        v-else-if="tab === 'history'"
        :items="historyItems"
        :total="historyTotal"
        :keep="Number(config.history_keep) || 200"
        :loading="historyLoading"
        :layout="layoutMode"
        @refresh="loadHistory(false)"
        @rollback="rollbackHistory"
        @reopen="reopenHistory"
        @delete="deleteHistory"
        @clear="clearHistory"
      />

      <!-- ---------------- 设置页 ---------------- -->
      <div v-else-if="tab === 'settings'" class="mkv-settings-wrap">
        <div class="mkv-settings-bar">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-arrow-left" @click="backFromSettings()">
            返回主页面
          </v-btn>
          <span class="mkv-settings-title">设置</span>
        </div>
        <div class="mkv-settings-body">
          <Config
            :api="props.api"
            :plugin-id="props.pluginId"
            :initial-config="config"
            :embedded="true"
            @save="onConfigSaved"
          />
        </div>
      </div>
    </main>

    <!-- ================= 底部任务条 ================= -->
    <footer v-if="bottomBarVisible" class="mkv-bottombar">
      <span class="bottom-dot" :class="{ paused: queuePaused }" />
      <span v-if="runningJob" class="bottom-text">运行中 <b>{{ runningJob.name }}</b></span>
      <span v-else class="bottom-text">队列等待中</span>
      <div v-if="runningJob" class="bottom-progress">
        <i :style="{ width: `${runningProgress}%` }" />
      </div>
      <span v-if="runningJob && !narrow" class="bottom-extra">{{ runningProgress }}%</span>
      <span class="mkv-spacer" />
      <span v-if="queueCount" class="bottom-text">队列 <b>{{ queueCount }}</b> 个等待</span>
      <button type="button" class="bottom-link" @click="switchTab('queue')">查看队列 →</button>
    </footer>

    <!-- ================= 目录选择：narrow 全屏 / medium 半屏窗口 ================= -->
    <v-dialog
      v-if="!wide"
      v-model="treeDialog"
      :fullscreen="narrow"
      :max-width="narrow ? undefined : 'min(620px, 55vw)'"
      scrollable
      transition="dialog-bottom-transition"
    >
      <v-card class="mkv-tree-dialog" :class="{ 'mkv-tree-dialog--window': !narrow }">
        <div class="mkv-tree-dialog-head">
          <span>媒体文件</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="treeDialog = false" />
        </div>
        <div class="mkv-tree-dialog-body">
          <FileTree
            :api="api"
            :roots="config.roots || []"
            :current="currentPath"
            :refresh-tick="fileStatusTick"
            @select="onSelectFile"
          />
        </div>
      </v-card>
    </v-dialog>

    <!-- ================= 重复提交保护：三选一 ================= -->
    <v-dialog v-model="duplicateState.open" max-width="560" persistent>
      <v-card class="duplicate-dialog">
        <div class="duplicate-head">
          <span class="duplicate-title">
            {{ duplicateState.conflict?.state === 'running' ? '当前任务正在运行' : '检测到未完成的队列任务' }}
          </span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="chooseDuplicate('cancel')" />
        </div>
        <div class="duplicate-body">
          <p v-if="duplicateState.conflict?.state === 'running'">
            当前文件有正在运行的任务<template v-if="duplicateState.conflict?.job_id">（#{{ duplicateState.conflict.job_id }}）</template>，新任务会在其结束后执行。
          </p>
          <p v-else>
            当前文件已有待开始的队列任务<template v-if="duplicateState.conflict?.job_id">（#{{ duplicateState.conflict.job_id }}）</template>。
            可以更新现有任务，或再提交一个新任务。
          </p>
        </div>
        <div class="duplicate-foot">
          <v-btn
            v-if="duplicateState.conflict?.state !== 'running'"
            color="primary"
            variant="flat"
            @click="chooseDuplicate('update')"
          >
            更新现有队列任务
          </v-btn>
          <v-btn
            :color="duplicateState.conflict?.state !== 'running' ? undefined : 'primary'"
            :variant="duplicateState.conflict?.state !== 'running' ? 'tonal' : 'flat'"
            @click="chooseDuplicate('new')"
          >
            再提交一个新任务
          </v-btn>
          <v-btn variant="text" @click="chooseDuplicate('cancel')">取消</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- ================= 从目录批量解压字体 ================= -->
    <v-dialog v-model="archiveDialog.open" max-width="540">
      <v-card class="archive-dialog">
        <div class="archive-head">
          <span class="archive-title">从目录批量解压字体</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="archiveDialog.open = false" />
        </div>
        <div class="archive-body">
          <div class="archive-field-label">目录路径</div>
          <v-text-field
            v-model="archiveDialog.path"
            placeholder="/media/动画/字体"
            density="compact"
            variant="outlined"
            hide-details
            class="mono"
          />
          <div class="archive-recursive">
            <v-checkbox
              v-model="archiveDialog.recursive"
              density="compact"
              hide-details
              label="包含子目录"
            />
            <span class="archive-tip">扫描目录下的 zip / 7z / rar / tar 压缩包，解压字体加入附件</span>
          </div>
          <div class="archive-support">{{ archiveHint }}</div>
        </div>
        <div class="archive-foot">
          <v-spacer />
          <v-btn variant="text" :disabled="archiveDialog.loading" @click="archiveDialog.open = false">取消</v-btn>
          <v-btn color="primary" variant="flat" :loading="archiveDialog.loading" @click="runArchiveBatch">解压</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- ================= 弹窗 ================= -->
    <PreviewDialog
      v-model="previewOpen"
      v-model:confirmed="durationMismatchConfirmed"
      :path="currentPath"
      :result="planResult"
      :loading="previewLoading"
      :submitting="previewSubmitting"
      :engine-ready="engineReady"
      :layout="layoutMode"
      :title="editingJobId ? '更新队列任务' : '确认执行'"
      :confirm-text="editingJobId ? '确认更新' : '确认执行'"
      @confirm="confirmRun"
    />

    <FilePickerDialog
      v-model="picker.open"
      :api="api"
      :kind="picker.kind"
      :title="picker.title"
      :roots="config.roots || []"
      :initial-path="picker.initialPath"
      :exts="picker.exts"
      :layout="layoutMode"
      @select="onPicked"
    />

    <UploadDialog
      v-model="uploadDialog.open"
      :api="api"
      :kind="uploadDialog.kind"
      :max-mb="uploadMaxMb"
      :layout="layoutMode"
      @uploaded="onUploaded"
    />

    <ConfirmDialog
      v-model="confirmState.open"
      :title="confirmState.title"
      :text="confirmState.text"
      :detail="confirmState.detail"
      :confirm-text="confirmState.confirmText"
      :color="confirmState.color"
      :loading="confirmState.loading"
      @confirm="runConfirm"
    />

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="2200" location="bottom">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
/* ================= 页面骨架 ================= */
.mkv-page {
  display: flex;
  flex-direction: column;
  position: relative;
  /* 宽度交给宿主内容区，避免 100%+1rem 造成底部横向滚动条 */
  width: 100%;
  margin: 0 0 -1.5rem;
  min-height: 520px;
  /* 桌面（侧栏页面）：占满宿主内容区，不再限制 900px 上限 */
  height: calc(100vh - 6rem);
  height: calc(100dvh - 6rem - var(--layout-footer-dock-height, 0px));
  overflow-x: hidden;
  color: rgb(var(--v-theme-on-surface));
}
/* 插件停用时的整页提示（不显示依赖/引擎拦截） */
.mkv-disabled-mask {
  position: absolute;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(var(--v-theme-surface), 0.94);
  backdrop-filter: blur(4px);
}
.mkv-disabled-card {
  max-width: 440px;
  width: 100%;
  padding: 30px 26px;
  text-align: center;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  background: rgba(var(--v-theme-surface), 0.98);
}
.mkv-disabled-title {
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 8px;
}
.mkv-disabled-desc {
  font-size: 13px;
  line-height: 1.8;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.mkv-disabled-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
}
/* 宿主「插件卡片弹窗」：空状态固定高度上限；有内容时窗口到上限，内容区内部滚动 */
.mkv-page.mkv-host-dialog:not(.mkv-narrow) {
  height: calc(100vh - 3rem);
  height: min(900px, calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px)));
  max-height: min(1000px, calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px)));
  margin: 0;
  min-height: 480px;
  overflow: hidden;
}
/* 手机 PC 模式弹窗：空状态 760（参考 Emby 插件），有内容固定 900 上限并内部滚动 */
.mkv-page.mkv-host-dialog.mkv-medium {
  height: min(760px, calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px)));
  max-height: min(900px, calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px)));
}
.mkv-page.mkv-host-dialog.mkv-medium.mkv-has-content {
  height: min(900px, calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px)));
  max-height: min(900px, calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px)));
}
/* 电脑卡片弹窗：高度留足宿主余量（空 820 / 有内容最高 900），内容区内部滚动 */
.mkv-page.mkv-host-dialog.mkv-wide {
  height: min(820px, calc(100dvh - 6rem - var(--layout-footer-dock-height, 0px)));
  max-height: min(900px, calc(100dvh - 6rem - var(--layout-footer-dock-height, 0px)));
}
.mkv-page.mkv-host-dialog.mkv-wide.mkv-has-content {
  height: min(900px, calc(100dvh - 6rem - var(--layout-footer-dock-height, 0px)));
  max-height: min(900px, calc(100dvh - 6rem - var(--layout-footer-dock-height, 0px)));
}
/* 手机全屏弹窗：宿主是全屏 VDialog，撑满整个视口 */
.mkv-page.mkv-host-dialog.mkv-narrow {
  height: calc(100vh);
  height: calc(100dvh - var(--layout-footer-dock-height, 0px));
  margin: 0;
}
/* 三档布局（由根容器宽度决定）：
   - wide（默认）：高度 min(900px, 100dvh - 6rem - dock)，内部区域自己滚动
   - narrow（容器 < 720 / 真手机）：整屏 100dvh - 4rem - dock（保持原手机行为）
   - medium（720 ≤ 容器 < 1100）：不用 100dvh 撑高，内容自然展开，由外层页面滚动 */
.mkv-page.mkv-narrow {
  width: 100%;
  margin: 0;
  min-height: 0;
  height: calc(100vh - 4rem);
  height: calc(100dvh - 4rem - var(--layout-footer-dock-height, 0px));
}
.mkv-page.mkv-medium {
  width: 100%;
  margin: 0;
  height: auto;
  min-height: 520px;
  max-height: none;
}
.mkv-page.mkv-medium .mkv-body {
  min-height: 520px;
}
.mkv-page.mkv-medium .mkv-editor,
.mkv-page.mkv-medium .queue-page,
.mkv-page.mkv-medium .history-page,
.mkv-page.mkv-medium .config-page,
.mkv-page.mkv-medium .mkv-settings-wrap,
.mkv-page.mkv-medium .mkv-settings-body {
  height: auto;
  min-height: 520px;
  overflow: visible;
}
/* medium 只保留少量收紧，不重新堆叠：表格/一行输出继续用 */
.mkv-page.mkv-medium .mkv-edit {
  grid-template-columns: 1fr;
}
.mkv-page.mkv-medium .mkv-header {
  height: 50px;
  flex: 0 0 50px;
  padding: 0 12px;
  gap: 10px;
}
.mkv-page.mkv-medium .mkv-editor {
  padding: 16px 18px 24px;
}
/* 宿主卡片弹窗 + 手机 PC 模式：恢复内部滚动（medium 旧规则 overflow:visible 会把内容裁掉） */
.mkv-page.mkv-host-dialog.mkv-medium .mkv-body {
  min-height: 0;
  overflow: hidden;
}
.mkv-page.mkv-host-dialog.mkv-medium .mkv-editor,
.mkv-page.mkv-host-dialog.mkv-medium .queue-page,
.mkv-page.mkv-host-dialog.mkv-medium .history-page,
.mkv-page.mkv-host-dialog.mkv-medium .config-page,
.mkv-page.mkv-host-dialog.mkv-medium .mkv-settings-wrap,
.mkv-page.mkv-host-dialog.mkv-medium .mkv-settings-body {
  height: 100%;
  min-height: 0;
  overflow: auto;
}
.mkv-page.mkv-medium .mkv-nav-btn {
  padding: 6px 12px;
}
.mkv-page.mkv-medium .info-strip {
  gap: 7px;
  margin: 12px 0;
}
.mkv-page.mkv-medium .mkv-bottombar {
  padding: 7px 12px;
}
/* medium 下的目录/文件选择：半屏窗口卡片（固定较高高度，列表内部滚动） */
.mkv-tree-dialog.mkv-tree-dialog--window {
  height: min(78vh, 820px);
  max-height: 78vh;
  border-radius: 12px;
}
.mkv-tree-dialog--window .mkv-tree-dialog-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow: auto;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.mkv-spacer {
  flex: 1 1 auto;
}

/* ================= 顶栏 ================= */
.mkv-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 16px;
  height: 54px;
  flex: 0 0 54px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  background: rgba(var(--v-theme-surface), 0.6);
}
.mkv-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 600;
  font-size: 15px;
  white-space: nowrap;
  min-width: 0;
}
.mkv-logo {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #ff9800, #ff5722);
  color: #111;
  font-weight: 800;
  font-size: 11px;
  flex: 0 0 auto;
}
.mkv-logo--img {
  display: block;
  object-fit: cover;
  background: none;
}
.mkv-brand-text {
  overflow: hidden;
  text-overflow: ellipsis;
}
.mkv-ver {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.42);
  font-weight: 400;
}
.mkv-ver--ui {
  color: rgba(var(--v-theme-primary), 0.75);
}
.mkv-engine-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.engine-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.66);
  white-space: nowrap;
}
.engine-chip--click {
  cursor: pointer;
}
.engine-chip .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4caf50;
  flex: 0 0 auto;
}
.engine-chip.warn {
  color: #ffb300;
}
.engine-chip.warn .dot {
  background: #ffb300;
}
.engine-chip.bad .dot {
  background: #ef5350;
}
.mkv-nav {
  display: flex;
  gap: 4px;
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 4px;
  border-radius: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  flex: 0 0 auto;
}
.mkv-nav-btn {
  font-family: inherit;
  border: none;
  background: none;
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 13px;
  padding: 6px 16px;
  border-radius: 7px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s ease, color 0.15s ease;
  white-space: nowrap;
}
.mkv-nav-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}
.mkv-nav-btn.active {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  font-weight: 600;
}
.mkv-nav-badge {
  background: rgba(0, 0, 0, 0.24);
  border-radius: 999px;
  padding: 0 7px;
  font-size: 11px;
  line-height: 17px;
}
.mkv-icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: rgba(var(--v-theme-on-surface), 0.66);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  background: none;
  cursor: pointer;
  flex: 0 0 auto;
}
.mkv-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}
.mkv-divider {
  width: 1px;
  height: 22px;
  background: rgba(var(--v-theme-on-surface), 0.16);
}
.mkv-exit-btn {
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 13px;
  border-radius: 9px;
  color: rgba(var(--v-theme-on-surface), 0.66);
  font-size: 12.5px;
  border: 1px solid transparent;
  background: none;
  cursor: pointer;
  white-space: nowrap;
}
.mkv-exit-btn:hover {
  background: rgba(239, 83, 80, 0.1);
  color: #ef5350;
  border-color: rgba(239, 83, 80, 0.3);
}

/* ================= 引擎横幅 ================= */
.mkv-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  font-size: 12.5px;
  background: rgba(255, 179, 0, 0.1);
  border-bottom: 1px solid rgba(255, 179, 0, 0.28);
  color: #ffb300;
  flex-wrap: wrap;
}

/* ================= 主体布局 ================= */
.mkv-body {
  flex: 1 1 auto;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  /* 内容区整体闭合外框：wide 左侧树 + 右侧编辑区共享左右/底部边线 */
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
  overflow: hidden;
  /* 左右共享的半透明毛玻璃底，避免右侧直接透出主题背景 */
  background: rgba(var(--v-theme-surface), 0.55);
  backdrop-filter: blur(18px) saturate(1.15);
  -webkit-backdrop-filter: blur(18px) saturate(1.15);
}
/* 设置页：内容较多，单独给返回按钮与滚动容器 */
.mkv-settings-wrap {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
}
.mkv-settings-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  flex: 0 0 auto;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.mkv-settings-title {
  font-weight: 600;
  font-size: 14px;
}
.mkv-settings-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
.mkv-edit {
  display: grid;
  grid-template-columns: 320px 1fr;
  flex: 1 1 auto;
  min-height: 0;
}
.mkv-tree-panel {
  min-height: 0;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  /* 左树比右侧编辑区略深一点，保持层次（叠加在 .mkv-body 毛玻璃底上） */
  background: rgba(var(--v-theme-surface), 0.32);
  overflow: hidden;
}
.mkv-editor {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 18px 22px 26px;
}
/* 编辑区是滚动容器，子项不能被 flex 压缩 */
.mkv-editor > * {
  flex: 0 0 auto;
}

/* ================= 编辑页 ================= */
.mkv-mobile-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.mkv-mobile-file {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.66);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mkv-empty-editor {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 16px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.mkv-empty-icon {
  opacity: 0.5;
}
.mkv-empty-title {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.mkv-empty-hint {
  font-size: 12px;
  max-width: 460px;
  line-height: 1.7;
}
.file-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}
.file-head-main {
  min-width: 0;
  flex: 1;
}
.file-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.file-title-row .file-title {
  flex: 0 1 auto;
  min-width: 0;
}
/* 标题旁的状态徽标 */
.file-status-chip {
  flex: 0 0 auto;
  font-size: 10.5px;
  line-height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  color: rgba(var(--v-theme-on-surface), 0.7);
  background: rgba(var(--v-theme-on-surface), 0.06);
  white-space: nowrap;
}
.file-status-chip--pending {
  color: #64b5f6;
  border-color: rgba(66, 165, 245, 0.4);
  background: rgba(66, 165, 245, 0.12);
}
.file-status-chip--running {
  color: #ffb74d;
  border-color: rgba(255, 152, 0, 0.42);
  background: rgba(255, 152, 0, 0.14);
}
.file-status-chip--success {
  color: #81c784;
  border-color: rgba(76, 175, 80, 0.4);
  background: rgba(76, 175, 80, 0.12);
}
.file-status-chip--failed {
  color: #ef5350;
  border-color: rgba(239, 83, 80, 0.42);
  background: rgba(239, 83, 80, 0.12);
}
/* 提交后状态条 */
.submit-status-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 7px 12px;
  margin: 10px 0 4px;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  background: rgba(var(--v-theme-on-surface), 0.05);
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.submit-status-banner--pending {
  border-color: rgba(66, 165, 245, 0.32);
  background: rgba(66, 165, 245, 0.08);
}
.submit-status-banner--running {
  border-color: rgba(255, 152, 0, 0.34);
  background: rgba(255, 152, 0, 0.08);
}
.submit-status-banner--success {
  border-color: rgba(76, 175, 80, 0.32);
  background: rgba(76, 175, 80, 0.08);
}
.submit-status-banner--failed {
  border-color: rgba(239, 83, 80, 0.34);
  background: rgba(239, 83, 80, 0.08);
}
.submit-status-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 重复提交三选一弹窗 */
.duplicate-dialog {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.duplicate-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px 6px;
}
.duplicate-title {
  font-size: 14.5px;
  font-weight: 600;
}
.duplicate-body {
  padding: 4px 18px 10px;
  font-size: 12.5px;
  line-height: 1.7;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.duplicate-body p {
  margin: 0;
}
.duplicate-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 10px 18px 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  flex-wrap: wrap;
}
.file-title {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-path {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}
.file-close-btn {
  margin-left: 2px;
}
.auto-import-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 6px 12px;
  margin-bottom: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.auto-import-switch {
  flex: 0 0 auto;
  margin: 0;
}
.auto-import-tip {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  line-height: 1.5;
  min-width: 0;
}
.scan-fonts-btn {
  margin-left: auto;
}
.info-strip {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  margin: 12px 0 14px;
}
.info-chip {
  display: inline-flex;
  align-items: center;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.13);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  white-space: nowrap;
}
.mkv-editor-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  margin-bottom: 14px;
  overflow-x: auto;
  scrollbar-width: none;
}
.mkv-editor-tabs::-webkit-scrollbar {
  display: none;
}
.mkv-tab-btn {
  font-family: inherit;
  padding: 8px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 8px 8px 0 0;
  background: none;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  flex: 0 0 auto;
}
.mkv-tab-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgb(var(--v-theme-on-surface));
}
.mkv-tab-btn.active {
  color: rgb(var(--v-theme-primary));
  border-bottom-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
.mkv-panel {
  display: block;
}
.mkv-card {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
}
.mkv-card-title {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.mkv-card-hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-weight: 400;
}
.mkv-empty-tip {
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 12px;
  padding: 6px 0;
  line-height: 1.7;
}
.kv-grid {
  /* 视频参数横向多列：每列「标签 + 值」紧挨，自动填充；wide/medium 同规则 */
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px 24px;
  align-items: baseline;
}
.kv-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: normal;
}
.kv-item > span {
  flex: 0 0 auto;
  white-space: nowrap;
}
.kv-item b {
  min-width: 0;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
  text-align: left;
  overflow-wrap: anywhere;
}
.mkv-form-row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 10px 16px;
  align-items: center;
  padding: 6px 0;
}
.mkv-form-row > label {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.65);
}
.mkv-form-value {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
}
.title-input {
  max-width: 420px;
  flex: 1 1 240px;
}
.mkv-sec-title {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin: 12px 0 6px;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.sub {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.ellipsis {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chapter-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.chapter-table td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.chapter-table tr:last-child td {
  border-bottom: none;
}
.chapter-time {
  width: 90px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11.5px;
}
.extra-args {
  font-size: 12px;
}
.extra-args-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.extra-args-msg {
  font-size: 11.5px;
  line-height: 1.5;
  word-break: break-all;
}
.extra-args-msg--error {
  color: #ef5350;
}
.extra-args-msg--ok {
  color: #66bb6a;
}
.warnbox {
  border-radius: 9px;
  padding: 10px 12px;
  font-size: 12.5px;
  margin: 10px 0 8px;
  line-height: 1.6;
}
.warnbox--red {
  background: rgba(239, 83, 80, 0.08);
  border: 1px solid rgba(239, 83, 80, 0.32);
  color: #ef5350;
}
.attach-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.attach-table th {
  text-align: left;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11.5px;
  padding: 5px 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  white-space: nowrap;
}
.attach-table td {
  padding: 7px 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.7);
  vertical-align: middle;
}
.attach-table tr:last-child td {
  border-bottom: none;
}
.attach-table tr.dropping td {
  opacity: 0.45;
}
.attach-table tr.dropping td.col-ops {
  opacity: 1;
}
.attach-name {
  color: rgb(var(--v-theme-on-surface));
  word-break: break-all;
}
.attach-tag {
  font-size: 10.5px;
  color: rgb(var(--v-theme-primary));
  border: 1px solid rgba(var(--v-theme-primary), 0.4);
  border-radius: 5px;
  padding: 0 5px;
  line-height: 16px;
  margin-left: 6px;
  white-space: nowrap;
}
.col-mime {
  width: 150px;
  font-size: 11.5px;
}
.col-size {
  width: 90px;
  font-size: 11.5px;
}
.col-ops {
  width: 56px;
  text-align: right;
}
.attach-ops {
  display: flex;
  justify-content: flex-end;
}
.attach-cards {
  display: flex;
  flex-direction: column;
}
.attach-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.attach-card:last-child {
  border-bottom: none;
}
.attach-card.dropping {
  opacity: 0.5;
}
.attach-card-main {
  flex: 1;
  min-width: 0;
}
.attach-sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 2px;
}
.mkv-add-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
/* 压缩包解压：能力提示 + 批量解压对话框 */
.archive-hint {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.6;
  margin-top: 8px;
}
.archive-dialog {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.archive-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px 6px;
}
.archive-title {
  font-size: 14.5px;
  font-weight: 600;
}
.archive-body {
  padding: 6px 18px 10px;
}
.archive-field-label {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-bottom: 4px;
}
.archive-recursive {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.archive-tip {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  line-height: 1.6;
  min-width: 0;
}
.archive-support {
  margin-top: 10px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.6;
}
.archive-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.output-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 20px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
  padding: 12px 14px;
  margin-top: 4px;
  background: rgba(var(--v-theme-surface), 0.35);
}
.radio {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.65);
  font-size: 12.5px;
}
.radio input {
  accent-color: rgb(var(--v-theme-primary));
  width: 15px;
  height: 15px;
  cursor: pointer;
}
.output-path {
  max-width: 380px;
  flex: 0 1 380px;
  min-width: 200px;
  font-size: 12px;
}
.output-tag {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 5px;
  padding: 1px 6px;
}
.output-note {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.output-replace {
  margin-left: auto;
}
/* 原地替换「不保存备份」开关 */
.no-backup-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
  padding: 2px 2px 0;
}
.no-backup-check {
  flex: 0 0 auto;
  color: #ffb300;
}
.no-backup-warn {
  font-size: 11.5px;
  color: #ef5350;
  line-height: 1.5;
  font-weight: 500;
}
/* 原地替换备份信息：默认先备份可回滚；不保存备份时红色告警 */
.backup-info {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 11.5px;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.62);
}
.backup-info--danger {
  color: #ef5350;
  font-weight: 500;
}
.backup-dir {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  overflow-wrap: anywhere;
}
/* 输出目录提示：弱化的小字说明容器内路径 */
.output-hint {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.6;
  margin-top: 6px;
}
.output-hint--warn {
  color: #ffb300;
}
.output-tag--warn {
  color: #ffb300;
  border-color: rgba(255, 179, 0, 0.45);
  background: rgba(255, 179, 0, 0.08);
}
.output-replace--disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
/* 真手机底部任务条：分隔线由内容区 .mkv-body 底边提供，这里只加轻微阴影，避免两条线紧贴 */
.mkv-page.mkv-narrow .mkv-bottombar {
  box-shadow: 0 -6px 14px rgba(0, 0, 0, 0.22);
}
/* 队列内编辑提示条 */
.editing-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  margin-bottom: 10px;
  border: 1px solid rgba(66, 165, 245, 0.42);
  border-radius: 8px;
  background: rgba(66, 165, 245, 0.1);
  color: #42a5f5;
  font-size: 12.5px;
  line-height: 1.5;
}
.editing-banner-text {
  flex: 1 1 240px;
  min-width: 0;
  word-break: break-all;
}
.editing-banner-text b {
  color: #90caf9;
  font-weight: 600;
}
.execute-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  flex-wrap: wrap;
}
.execute-btns {
  display: flex;
  gap: 10px;
  flex: 0 0 auto;
  flex-wrap: wrap;
}
.execute-tip {
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11.5px;
}

/* ================= 底部任务条 ================= */
.mkv-bottombar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 16px;
  /* 内容区 .mkv-body 已有底边线，这里不再叠一条紧贴的线 */
  border-top: none;
  background: rgba(var(--v-theme-surface), 0.6);
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  overflow: hidden;
}
.bottom-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff9800;
  flex: 0 0 auto;
  animation: mkv-pulse 1.2s infinite;
}
.bottom-dot.paused {
  background: #ffb300;
  animation: none;
}
@keyframes mkv-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
.bottom-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.bottom-text b {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
}
.bottom-progress {
  flex: 0 0 240px;
  height: 6px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.12);
  overflow: hidden;
}
.bottom-progress > i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #ff9800, #ffb74d);
  transition: width 0.3s ease;
}
.bottom-extra {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.bottom-link {
  font-family: inherit;
  border: none;
  background: none;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  font-size: 12.5px;
  white-space: nowrap;
  padding: 2px 4px;
}
.bottom-link:hover {
  text-decoration: underline;
}

/* ================= 手机目录抽屉 ================= */
.mkv-tree-dialog {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 0;
  /* 弹窗卡片完整包边 */
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.mkv-tree-dialog-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  font-size: 14px;
  font-weight: 600;
  flex: 0 0 auto;
}
.mkv-tree-dialog-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

/* ================= 响应式（< 960px 按 mockup 手机版） ================= */
/* narrow 布局（真手机 / 容器 < 720）：由 AppPage 根节点的 .mkv-narrow 类驱动，不依赖视口断点 */
.mkv-page.mkv-narrow .mkv-header {
    height: 52px;
    flex: 0 0 52px;
    padding: 0 10px;
    gap: 8px;
  }
.mkv-page.mkv-narrow .mkv-brand {
    font-size: 14px;
    gap: 7px;
    min-width: 0;
  }
.mkv-page.mkv-narrow .mkv-logo {
    width: 24px;
    height: 24px;
    border-radius: 7px;
    font-size: 9px;
  }
.mkv-page.mkv-narrow .mkv-nav {
    flex: 1 1 auto;
    min-width: 0;
    padding: 3px;
    gap: 5px;
  }
.mkv-page.mkv-narrow .mkv-nav-btn {
    flex: 1 1 0;
    min-width: 0;
    justify-content: center;
    padding: 6px 3px;
    font-size: 11.5px;
    gap: 3px;
  }
.mkv-page.mkv-narrow .mkv-nav-badge {
    padding: 0 4px;
    font-size: 10px;
    line-height: 15px;
  }
.mkv-page.mkv-narrow .mkv-icon-btn {
    width: 32px;
    height: 32px;
  }
.mkv-page.mkv-narrow .mkv-banner {
    padding: 8px 12px;
    font-size: 12px;
    gap: 6px;
  }
.mkv-page.mkv-narrow .mkv-edit {
    grid-template-columns: 1fr;
  }
.mkv-page.mkv-narrow .mkv-editor {
    padding: 12px 12px 20px;
  }
.mkv-page.mkv-narrow .mkv-editor-tabs {
    margin-bottom: 10px;
  }
.mkv-page.mkv-narrow .mkv-tab-btn {
    padding: 7px 12px;
    font-size: 12.5px;
  }
.mkv-page.mkv-narrow .file-title {
    font-size: 14.5px;
    line-height: 1.35;
  }
.mkv-page.mkv-narrow .file-path {
    font-size: 11px;
    margin-top: 2px;
  }
.mkv-page.mkv-narrow .info-strip {
    gap: 5px;
    margin: 10px 0;
  }
.mkv-page.mkv-narrow .info-chip {
    font-size: 10.5px;
    padding: 2px 8px;
  }
.mkv-page.mkv-narrow .mkv-card {
    padding: 12px;
    border-radius: 12px;
  }
.mkv-page.mkv-narrow .mkv-card-title {
    font-size: 11.5px;
    margin-bottom: 8px;
  }
.mkv-page.mkv-narrow .mkv-card-hint {
    display: none;
  }
.mkv-page.mkv-narrow .kv-grid {
    /* 真手机：固定 2 列，值放不下时在列内换行，不再整块竖排 */
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 12px;
  }
.mkv-page.mkv-narrow .kv-item {
    gap: 6px;
    font-size: 12px;
  }
.mkv-page.mkv-narrow .mkv-form-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
.mkv-page.mkv-narrow .title-input {
    max-width: none;
    flex: 1 1 100%;
  }
.mkv-page.mkv-narrow .output-box {
    gap: 8px 10px;
    padding: 10px 12px;
  }
.mkv-page.mkv-narrow .output-path {
    flex: 1 1 100%;
    max-width: none;
    min-width: 0;
  }
.mkv-page.mkv-narrow .output-tag {
    display: none;
  }
.mkv-page.mkv-narrow .output-replace {
    margin-left: 0;
  }
.mkv-page.mkv-narrow .output-note {
    flex: 1 1 100%;
  }
.mkv-page.mkv-narrow .no-backup-row {
    align-items: flex-start;
    gap: 2px;
  }
.mkv-page.mkv-narrow .no-backup-warn {
    flex: 1 1 100%;
    padding-left: 2px;
  }
.mkv-page.mkv-narrow .execute-row {
    gap: 8px;
  }
.mkv-page.mkv-narrow .execute-tip {
    width: 100%;
    order: 9;
    font-size: 11px;
  }
.mkv-page.mkv-narrow .execute-row :deep(.v-btn) {
    flex: 1 1 0;
  }
.mkv-page.mkv-narrow .execute-btns {
    flex: 1 1 100%;
    flex-wrap: wrap;
  }
.mkv-page.mkv-narrow .execute-btns > * {
    flex: 1 1 0;
    min-width: 92px;
  }
.mkv-page.mkv-narrow .mkv-add-row > * {
    flex: 1 1 100%;
    max-width: 100%;
  }
.mkv-page.mkv-narrow .attach-table {
    display: none;
  }
.mkv-page.mkv-narrow .mkv-bottombar {
    padding: 6px 10px;
    gap: 8px;
    font-size: 11.5px;
  }
.mkv-page.mkv-narrow .bottom-progress {
    display: none;
  }
.mkv-page.mkv-narrow .bottom-link {
    flex: 0 0 auto;
    padding: 4px 6px;
  }
</style>
