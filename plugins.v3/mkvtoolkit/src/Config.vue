<script setup>
/**
 * MkvToolkit 设置页（同时作为 ./Config 联邦暴露）
 * 引擎检测与安装 / 根目录 / 输出与备份 / 字幕与语言 / 执行与校验 / 上传 / 诊断
 * 配置读写统一走 GET /config、POST /config
 */
import { computed, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { createApi } from './api.js'
import { fmtBytes } from './utils.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MkvToolkit' },
  initialConfig: { type: Object, default: () => ({}) },
  // 作为 AppPage 设置 Tab 内嵌时不要再改宿主 layout（AppPage 已按分栏宽度申请）
  embedded: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'close', 'switch'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()
const api = createApi(props)

const DEFAULTS = {
  enabled: true,
  roots: [],
  engine_mode: 'auto',
  mkvmerge_path: '',
  mkvpropedit_path: '',
  mkvextract_path: '',
  ffmpeg_path: '',
  output_mode: 'dir',
  output_dir: '/config/plugins/MkvToolkit/output',
  backup_dir: '/config/plugins/MkvToolkit/backup',
  backup_keep: 3,
  subtitle_after: 'keep',
  subtitle_encoding: 'auto',
  language_map: {
    '.zh': 'chi',
    '.chs': 'chi',
    '.cht': 'chi',
    '.jpn': 'jpn',
    '.eng': 'eng',
    '.yue': 'yue',
  },
  concurrency: 1,
  validation_tolerance: 2,
  strict_duration_check: false,
  history_keep: 200,
  upload_max_mb: 50,
  allow_ffmpeg_fallback: false,
  auto_subtitle: false,
  auto_audio: false,
  auto_fonts: false,
}

const ENGINE_KEYS = [
  { key: 'mkvmerge', label: 'mkvmerge', required: true, tip: '封装 / 轨道管理主引擎' },
  { key: 'mkvpropedit', label: 'mkvpropedit', required: false, tip: '只改元数据（标题/语言）时用' },
  { key: 'mkvextract', label: 'mkvextract', required: false, tip: '章节/附件提取用' },
  { key: 'ffprobe', label: 'ffprobe', required: false, tip: '探测兜底' },
  { key: 'ffmpeg', label: 'ffmpeg', required: false, tip: '降级封装（能力减配）' },
]

const OUTPUT_MODES = [
  { title: '输出到目录', value: 'dir' },
  { title: '原地替换', value: 'replace' },
]
const SUBTITLE_AFTER = [
  { title: '保留', value: 'keep' },
  { title: '移到归档目录', value: 'archive' },
  { title: '删除', value: 'delete' },
]
const SUBTITLE_ENCODINGS = [
  { title: '自动探测', value: 'auto' },
  { title: 'UTF-8', value: 'utf-8' },
  { title: 'GBK', value: 'gbk' },
  { title: 'BIG5', value: 'big5' },
]
const ENGINE_MODES = [
  { title: '自动（优先 mkvmerge）', value: 'auto' },
  { title: '仅 mkvmerge', value: 'mkvmerge' },
  { title: '仅 ffmpeg（降级）', value: 'ffmpeg' },
]
const INSTALL_METHODS = [
  { title: 'apt 安装', value: 'apt', desc: '从 Debian 源安装 mkvtoolnix（官方镜像 trixie 源为 92.0）' },
  { title: 'AppImage 解包', value: 'appimage', desc: '下载官方 AppImage 并解包到插件数据目录' },
  { title: '手动指定路径', value: 'path', desc: '已在宿主机放好二进制时，直接指定 mkvmerge 路径' },
]

const cfg = ref({ ...DEFAULTS, ...(props.initialConfig || {}) })
const status = ref({})
const loading = ref(true)
const saving = ref(false)
const error = ref('')

// ---------------- 引擎安装 ----------------
const installOpen = ref(false)
const installMethod = ref('apt')
const installTarget = ref('all')
const installPath = ref('')
const installStarted = ref(false)
const installRunning = ref(false)
const installOk = ref(true)
const installLog = ref('')
const installError = ref('')
let installTimer = null

// ---------------- 根目录 ----------------
const rootDialog = ref(false)
const newRoot = ref('')

// ---------------- 语言映射 ----------------
const languageDialog = ref(false)
const languageText = ref('')

// ---------------- 诊断 ----------------
const diagnoseLoading = ref(false)
const diagnoseResults = ref([])
const diagnoseNote = ref('')

const engine = computed(() => status.value?.engine || {})
const engineInstall = computed(() => status.value?.engine_install || {})
// 压缩包解压工具（7z/unrar）状态：zip/tar 内置，7z/rar 依赖系统工具
const archiveTools = computed(() => status.value?.archive?.tools || {})
const archive7z = computed(() => Boolean(archiveTools.value['7z']))
const archiveUnrar = computed(() => Boolean(archiveTools.value.unrar))
// rar 可以用 unrar，也可以直接用 7z 解压
const archiveRar = computed(() => archiveUnrar.value || archive7z.value)
const TARGET_LABELS = {
  all: '全部引擎 + 压缩包工具',
  mkvmerge: 'mkvmerge',
  mkvpropedit: 'mkvpropedit',
  mkvextract: 'mkvextract',
  ffmpeg: 'ffmpeg',
  ffprobe: 'ffprobe',
  '7z': '7z 解压工具',
  unrar: 'unrar 解压工具',
}
const installTargetLabel = computed(() => TARGET_LABELS[installTarget.value] || '引擎')
const engineRows = computed(() =>
  ENGINE_KEYS.map((item) => {
    const info = engine.value[item.key] || {}
    const configured = cfg.value[`${item.key}_path`] || ''
    return {
      ...item,
      ok: Boolean(info.ok),
      version: info.version || '',
      path: info.path || '',
      configured,
    }
  }),
)
const mkvReady = computed(() => {
  const mode = engine.value.mode
  if (mode === 'none') return false
  return Boolean(engine.value.mkvmerge?.ok) || mode === 'ffmpeg'
})
const languageMapCount = computed(() => Object.keys(cfg.value.language_map || {}).length)

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message)
}

async function loadStatus() {
  try {
    status.value = await api.get('/status')
    const info = status.value?.engine_install || {}
    if (info.running && !installRunning.value) {
      installRunning.value = true
      installStarted.value = true
      installLog.value = info.log_tail || ''
      scheduleInstallPoll()
    }
  } catch (err) {
    // 状态读取失败不阻塞设置页
  }
}

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.get('/config')
    cfg.value = { ...DEFAULTS, ...(props.initialConfig || {}), ...(data || {}) }
    cfg.value.roots = Array.isArray(cfg.value.roots) ? cfg.value.roots : []
    cfg.value.language_map = { ...DEFAULTS.language_map, ...(cfg.value.language_map || {}) }
  } catch (err) {
    error.value = err.message || '读取配置失败'
    toastMsg('error', `读取配置失败：${err.message}`)
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  error.value = ''
  try {
    const payload = {
      ...cfg.value,
      roots: [...(cfg.value.roots || [])],
      language_map: { ...(cfg.value.language_map || {}) },
    }
    const saved = await api.post('/config', payload)
    cfg.value = { ...DEFAULTS, ...cfg.value, ...(saved || {}) }
    emit('save', { ...cfg.value })
    toastMsg('success', '配置已保存')
  } catch (err) {
    error.value = err.message
    toastMsg('error', `保存失败：${err.message}`)
  } finally {
    saving.value = false
  }
}

async function checkEngine() {
  try {
    const data = await api.post('/engine/check')
    status.value = { ...status.value, engine: data || {} }
    toastMsg('success', mkvReady.value ? '引擎检测完成' : '未检测到 MKVToolNix')
  } catch (err) {
    toastMsg('error', `检测失败：${err.message}`)
  }
}

function openInstall(method, target = 'all') {
  installTarget.value = target
  // 7z/unrar 只能通过 apt 安装
  installMethod.value = target === '7z' || target === 'unrar' ? 'apt' : method
  installPath.value = ''
  installStarted.value = false
  installRunning.value = false
  installLog.value = ''
  installError.value = ''
  installOk.value = true
  installOpen.value = true
}

function currentMethodDesc() {
  return INSTALL_METHODS.find((item) => item.value === installMethod.value) || INSTALL_METHODS[0]
}

async function startInstall() {
  if (installMethod.value === 'path' && !installPath.value.trim()) {
    installError.value = '请填写 mkvmerge 可执行文件的绝对路径'
    return
  }
  installError.value = ''
  try {
    const payload = { method: installMethod.value, target: installTarget.value }
    if (installMethod.value === 'path') payload.path = installPath.value.trim()
    await api.post('/engine/install', payload)
    installStarted.value = true
    installRunning.value = true
    installLog.value = '安装任务已启动，正在等待日志…'
    scheduleInstallPoll()
  } catch (err) {
    installError.value = err.message || '安装启动失败'
  }
}

function scheduleInstallPoll() {
  if (installTimer) clearTimeout(installTimer)
  installTimer = setTimeout(pollInstall, 1000)
}

async function pollInstall() {
  try {
    const data = await api.get('/status')
    status.value = data || {}
    const info = data?.engine_install || {}
    installRunning.value = Boolean(info.running)
    installOk.value = info.ok !== false
    installLog.value = info.log_tail || installLog.value
    if (installRunning.value) {
      scheduleInstallPoll()
      return
    }
    // 安装结束：重新检测引擎
    installStarted.value = true
    if (installOk.value) {
      toastMsg('success', `${installTargetLabel.value} 安装完成`)
      try {
        const checked = await api.post('/engine/check')
        status.value = { ...status.value, engine: checked || {} }
      } catch (err) {
        // 忽略二次检测失败
      }
    } else {
      toastMsg('error', '引擎安装失败，请查看日志')
    }
  } catch (err) {
    installError.value = err.message || '读取安装进度失败'
    installRunning.value = false
  }
}

function closeInstall() {
  installOpen.value = false
}

// ---------------- 根目录 ----------------
function addRoot() {
  const value = newRoot.value.trim().replace(/\/+$/, '')
  if (!value) return
  if (!value.startsWith('/')) {
    toastMsg('error', '根目录必须是容器内的绝对路径，例如 /media')
    return
  }
  if ((cfg.value.roots || []).includes(value)) {
    toastMsg('warning', '该根目录已存在')
    return
  }
  cfg.value.roots = [...(cfg.value.roots || []), value]
  newRoot.value = ''
  rootDialog.value = false
}

function removeRoot(root) {
  cfg.value.roots = (cfg.value.roots || []).filter((item) => item !== root)
}

// ---------------- 语言映射 ----------------
function openLanguage() {
  languageText.value = Object.entries(cfg.value.language_map || {})
    .map(([ext, lang]) => `${ext}=${lang}`)
    .join('\n')
  languageDialog.value = true
}

function saveLanguage() {
  const next = {}
  for (const line of String(languageText.value || '').split('\n')) {
    const text = line.trim()
    if (!text || text.startsWith('#')) continue
    const index = text.lastIndexOf('=')
    if (index <= 0) continue
    const ext = text.slice(0, index).trim()
    const lang = text.slice(index + 1).trim()
    if (ext && lang) next[ext] = lang
  }
  cfg.value.language_map = next
  languageDialog.value = false
  toastMsg('success', `语言映射已更新（${Object.keys(next).length} 条），保存后生效`)
}

function languageHint() {
  const entries = Object.entries(cfg.value.language_map || {})
  if (!entries.length) return '未配置'
  return entries.map(([ext, lang]) => `${ext} → ${lang}`).join('　')
}

// ---------------- 诊断 ----------------
async function runDiagnose() {
  diagnoseLoading.value = true
  diagnoseResults.value = []
  diagnoseNote.value = ''
  const results = []
  const push = (name, ok, detail) => results.push({ name, ok, detail })
  try {
    // 契约里没有诊断接口，后端若实现 /diagnose 则优先使用
    let remote = null
    try {
      remote = await api.post('/diagnose')
    } catch (err) {
      remote = null
    }
    if (remote && Array.isArray(remote.checks) && remote.checks.length) {
      diagnoseResults.value = remote.checks.map((item) => ({
        name: item.name || item.code || '检查项',
        ok: item.ok !== false,
        detail: item.detail || item.message || '',
      }))
      diagnoseNote.value = remote.message || '诊断完成'
      return
    }

    // 后端 /diagnose 的真实结构：engine / mode / is_root / data_dir / roots / upload_max_mb
    if (remote && remote.engine) {
      const eng = remote.engine || {}
      push(
        'mkvmerge',
        Boolean(eng.mkvmerge?.ok),
        eng.mkvmerge?.ok ? `${eng.mkvmerge.version || ''} ${eng.mkvmerge.path || ''}` : '未找到，需在设置里安装',
      )
      push(
        'mkvpropedit',
        Boolean(eng.mkvpropedit?.ok),
        eng.mkvpropedit?.ok ? `${eng.mkvpropedit.version || ''}` : '缺失（只改元数据时会回退重封装）',
      )
      push(
        'mkvextract',
        Boolean(eng.mkvextract?.ok),
        eng.mkvextract?.ok ? `${eng.mkvextract.version || ''}` : '缺失（章节/附件提取可能受限）',
      )
      push('ffmpeg / ffprobe', Boolean(eng.ffmpeg?.ok) && Boolean(eng.ffprobe?.ok), `ffmpeg ${eng.ffmpeg?.version || '未检测到'}`)
      push('执行模式', String(remote.mode || 'none') !== 'none', `当前引擎：${remote.mode || 'none'}`)
      push('运行身份', Boolean(remote.is_root), remote.is_root ? 'root（权限充足）' : '非 root，注意目录权限')
      push('数据目录', Boolean(remote.data_writable), `${remote.data_dir || '—'} ${remote.data_writable ? '可写' : '不可写'}`)
      for (const root of remote.roots || []) {
        push(
          `根目录 ${root.path || '—'}`,
          Boolean(root.exists && root.writable),
          `${root.exists ? '存在' : '不存在'} · ${root.writable ? '可写' : '不可写'} · 剩余 ${fmtBytes(root.free)}`,
        )
      }
      push(
        '上传上限',
        Number(remote.upload_max_mb) > 0 && Number(remote.upload_max_mb) <= 50,
        `当前 ${remote.upload_max_mb}MB（宿主 nginx 默认 50MB）`,
      )
      diagnoseResults.value = results
      const badRemote = results.filter((item) => !item.ok).length
      diagnoseNote.value = `诊断完成（${remote.timestamp || '—'}）：${badRemote ? `${badRemote} 项需要注意` : '全部通过'}`
      return
    }

    const data = await api.get('/status')
    const eng = data?.engine || {}
    push(
      'mkvmerge',
      Boolean(eng.mkvmerge?.ok),
      eng.mkvmerge?.ok ? `${eng.mkvmerge.version || ''} ${eng.mkvmerge.path || ''}` : '未找到，需在设置里安装',
    )
    push(
      'mkvpropedit',
      Boolean(eng.mkvpropedit?.ok),
      eng.mkvpropedit?.ok ? `${eng.mkvpropedit.version || ''}` : '缺失（只改元数据时会回退重封装）',
    )
    push(
      'mkvextract',
      Boolean(eng.mkvextract?.ok),
      eng.mkvextract?.ok ? `${eng.mkvextract.version || ''}` : '缺失（章节/附件提取可能受限）',
    )
    push('ffmpeg / ffprobe', Boolean(eng.ffmpeg?.ok) && Boolean(eng.ffprobe?.ok), `ffmpeg ${eng.ffmpeg?.version || '未检测到'}`)
    push('媒体根目录', (cfg.value.roots || []).length > 0, (cfg.value.roots || []).join('、') || '未配置，目录树不可用')
    push(
      '输出目录',
      cfg.value.output_mode === 'replace' ? true : Boolean(cfg.value.output_dir),
      cfg.value.output_mode === 'replace' ? '原地替换模式，输出目录不生效' : cfg.value.output_dir || '未填写',
    )
    push(
      '备份目录',
      true,
      cfg.value.backup_dir || '默认：/config/plugins/MkvToolkit/backup（留空自动使用插件数据目录）',
    )
    push('上传上限', Number(cfg.value.upload_max_mb) > 0 && Number(cfg.value.upload_max_mb) <= 50, `当前 ${cfg.value.upload_max_mb}MB（宿主 nginx 默认上限 50MB）`)
    push('并发数', Number(cfg.value.concurrency) >= 1 && Number(cfg.value.concurrency) <= 3, `当前 ${cfg.value.concurrency}`)
    push('插件状态', data?.enabled !== false, data?.enabled === false ? '插件已停用' : `版本 ${data?.version || '—'}`)
    diagnoseResults.value = results
    const bad = results.filter((item) => !item.ok).length
    diagnoseNote.value = bad ? `诊断完成：${bad} 项需要注意` : '诊断完成：全部通过'
  } catch (err) {
    diagnoseNote.value = `诊断失败：${err.message}`
  } finally {
    diagnoseLoading.value = false
  }
}

onMounted(async () => {
  if (!props.embedded) instance?.emit('layout', { maxWidth: '72rem' })
  await loadConfig()
  await loadStatus()
})

onBeforeUnmount(() => {
  if (installTimer) clearTimeout(installTimer)
  installTimer = null
})
</script>

<template>
  <div class="config-page">
    <v-skeleton-loader v-if="loading" type="list-item@8" />

    <template v-else>
      <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-3" closable @click:close="error = ''">
        {{ error }}
      </v-alert>

      <!-- ================= 引擎 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">引擎</div>
        <div class="form-row">
          <label>启用插件</label>
          <div class="value">
            <v-switch v-model="cfg.enabled" density="compact" color="primary" hide-details />
            <span class="sub">关闭后插件停止后台任务队列与相关接口，页面显示停用提示；侧栏入口保留，重新启用需到插件管理页启用并「应用保存」</span>
          </div>
        </div>
        <div class="form-row">
          <label>引擎模式</label>
          <div class="value">
            <v-select
              v-model="cfg.engine_mode"
              :items="ENGINE_MODES"
              density="compact"
              variant="outlined"
              hide-details
              class="w-260"
            />
          </div>
        </div>
        <div v-for="row in engineRows" :key="row.key" class="form-row">
          <label>{{ row.label }}</label>
          <div class="value">
            <v-chip size="x-small" variant="tonal" :color="row.ok ? 'success' : (row.required ? 'error' : 'warning')">
              {{ row.ok ? (row.version || '已就绪') : '未检测到' }}
            </v-chip>
            <span v-if="row.path" class="mono sub ellipsis" :title="row.path">{{ row.path }}</span>
            <span v-else class="sub">{{ row.tip }}</span>
            <v-text-field
              v-if="row.key !== 'ffprobe'"
              v-model="cfg[`${row.key}_path`]"
              density="compact"
              variant="outlined"
              hide-details
              :placeholder="`自定义 ${row.label} 路径（留空=自动探测）`"
              class="path-input"
            />
            <v-btn
              v-if="!row.ok"
              size="x-small"
              variant="tonal"
              color="primary"
              :loading="installRunning && installTarget === row.key"
              @click="openInstall('apt', row.key)"
            >
              安装 {{ row.label }}
            </v-btn>
          </div>
        </div>
        <div class="form-row">
          <label>压缩包解压</label>
          <div class="value">
            <v-chip size="x-small" variant="tonal" :color="archive7z ? 'success' : 'warning'">
              {{ archive7z ? '7z 已就绪' : '7z 未安装' }}
            </v-chip>
            <v-chip size="x-small" variant="tonal" :color="archiveRar ? 'success' : 'warning'">
              {{ archiveRar ? (archiveUnrar ? 'unrar 已就绪' : 'rar 可解压（7z）') : 'rar 未安装' }}
            </v-chip>
            <v-btn v-if="!archive7z" size="x-small" variant="tonal" :loading="installRunning && installTarget === '7z'" @click="openInstall('apt', '7z')">
              安装 7z
            </v-btn>
            <v-btn v-if="!archiveUnrar" size="x-small" variant="tonal" :loading="installRunning && installTarget === 'unrar'" @click="openInstall('apt', 'unrar')">
              安装 unrar
            </v-btn>
            <span class="sub">zip/tar 内置解压；7z/rar 有 7z 即可，unrar 是可选的备选</span>
          </div>
        </div>
        <div class="form-row">
          <label>重新检测</label>
          <div class="value">
            <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="checkEngine">重新检测</v-btn>
            <span class="sub">{{ mkvReady ? '引擎可用，可以执行封装' : '缺少 mkvmerge，当前只能预览不能执行' }}</span>
          </div>
        </div>
        <div class="form-row">
          <label>安装 / 更新</label>
          <div class="value">
            <v-btn size="small" color="primary" variant="flat" prepend-icon="mdi-download" @click="openInstall('apt')">
              一键安装全部（apt）
            </v-btn>
            <v-btn size="small" variant="tonal" @click="openInstall('appimage')">AppImage 解包</v-btn>
            <v-btn size="small" variant="text" @click="openInstall('path')">手动指定路径</v-btn>
          </div>
        </div>
        <div v-if="engineInstall.running" class="form-row">
          <label>安装进度</label>
          <div class="value">
            <v-progress-circular indeterminate size="16" width="2" color="primary" />
            <span class="sub">安装进行中，可在下方诊断里查看结果</span>
          </div>
        </div>
        <div class="form-row">
          <label>降级执行</label>
          <div class="value">
            <v-switch v-model="cfg.allow_ffmpeg_fallback" density="compact" color="primary" hide-details />
            <span class="sub">缺 mkvmerge 时允许用 ffmpeg 真执行（默认关闭，能力减配）</span>
          </div>
        </div>
      </v-card>

      <!-- ================= 目录 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">目录</div>
        <div class="form-row">
          <label>媒体根目录</label>
          <div class="value">
            <div class="root-list">
              <span v-for="root in cfg.roots" :key="root" class="root-tag">
                {{ root }}
                <button type="button" class="root-del" title="移除" @click="removeRoot(root)">✕</button>
              </span>
              <span v-if="!cfg.roots || !cfg.roots.length" class="sub">还没有根目录，插件无法浏览媒体文件</span>
            </div>
            <v-btn size="small" variant="text" prepend-icon="mdi-plus" @click="rootDialog = true">添加</v-btn>
          </div>
        </div>
        <div class="form-row">
          <label>目录树</label>
          <div class="value">
            <span class="sub">只显示 .mkv；懒加载；顶部可搜索；文件路径必须落在根目录内</span>
          </div>
        </div>
      </v-card>

      <!-- ================= 输出与备份 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">输出与备份</div>
        <div class="form-row">
          <label>默认输出</label>
          <div class="value">
            <v-btn-toggle :model-value="cfg.output_mode" mandatory density="compact" variant="outlined" divided
              @update:model-value="cfg.output_mode = $event">
              <v-btn v-for="item in OUTPUT_MODES" :key="item.value" :value="item.value" size="small">
                {{ item.title }}
              </v-btn>
            </v-btn-toggle>
            <span class="sub">原地替换默认会先做临时备份，任务成功后自动删除；失败时保留备份并尝试还原源文件</span>
          </div>
        </div>
        <div class="form-row">
          <label>输出目录</label>
          <div class="value">
            <v-text-field v-model="cfg.output_dir" density="compact" variant="outlined" hide-details class="path-input mono" />
          </div>
        </div>
        <div class="form-row">
          <label>备份目录</label>
          <div class="value">
            <v-text-field
              v-model="cfg.backup_dir"
              density="compact"
              variant="outlined"
              hide-details
              class="path-input mono"
              placeholder="留空则默认：/config/plugins/MkvToolkit/backup"
            />
          </div>
        </div>
        <div class="form-row">
          <label>失败备份保留份数</label>
          <div class="value">
            <v-select
              v-model.number="cfg.backup_keep"
              :items="[1, 3, 5, 10]"
              density="compact"
              variant="outlined"
              hide-details
              class="w-90"
            />
            <span class="sub">份；仅清理失败任务遗留的备份，成功任务会自动删除临时备份</span>
          </div>
        </div>
        <div class="form-row">
          <label></label>
          <div class="value">
            <span class="sub">留空时使用插件数据目录下的 backup；可改成媒体盘等大容量路径</span>
          </div>
        </div>
      </v-card>

      <!-- ================= 字幕与语言 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">字幕与语言</div>
        <div class="form-row">
          <label>内封后外挂字幕</label>
          <div class="value">
            <v-btn-toggle :model-value="cfg.subtitle_after" mandatory density="compact" variant="outlined" divided
              @update:model-value="cfg.subtitle_after = $event">
              <v-btn v-for="item in SUBTITLE_AFTER" :key="item.value" :value="item.value" size="small">
                {{ item.title }}
              </v-btn>
            </v-btn-toggle>
            <span class="sub">默认保留；仅在原地替换模式下生效，输出到新目录时不会移动源字幕</span>
          </div>
        </div>
        <div class="form-row">
          <label>编码兜底</label>
          <div class="value">
            <v-select
              v-model="cfg.subtitle_encoding"
              :items="SUBTITLE_ENCODINGS"
              density="compact"
              variant="outlined"
              hide-details
              class="w-180"
            />
            <span class="sub">自动探测失败时按此编码处理</span>
          </div>
        </div>
        <div class="form-row">
          <label>语言映射</label>
          <div class="value">
            <span class="mono sub ellipsis" :title="languageHint()">{{ languageHint() }}</span>
            <span class="sub">（{{ languageMapCount }} 条）</span>
            <v-btn size="small" variant="text" prepend-icon="mdi-pencil" @click="openLanguage">编辑</v-btn>
          </div>
        </div>
      </v-card>

      <!-- ================= 自动导入 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">自动导入</div>
        <div class="form-row">
          <label>自动导入同名字幕</label>
          <div class="value">
            <v-switch v-model="cfg.auto_subtitle" density="compact" color="primary" hide-details />
            <span class="sub">打开文件时自动导入同名字幕（前缀匹配的候选）</span>
          </div>
        </div>
        <div class="form-row">
          <label>自动导入同名音频</label>
          <div class="value">
            <v-switch v-model="cfg.auto_audio" density="compact" color="primary" hide-details />
            <span class="sub">打开文件时自动导入同名音频（前缀匹配的候选）</span>
          </div>
        </div>
        <div class="form-row">
          <label>自动导入同目录字体</label>
          <div class="value">
            <v-switch v-model="cfg.auto_fonts" density="compact" color="primary" hide-details />
            <span class="sub">打开文件时自动导入同目录（含 fonts/ 子目录）字体为附件</span>
          </div>
        </div>
      </v-card>

      <!-- ================= 执行 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">执行</div>
        <div class="form-row">
          <label>并发数</label>
          <div class="value">
            <v-select
              v-model.number="cfg.concurrency"
              :items="[1, 2, 3]"
              density="compact"
              variant="outlined"
              hide-details
              class="w-90"
            />
            <span class="sub">机械盘建议 1，SSD 可 2~3</span>
          </div>
        </div>
        <div class="form-row">
          <label>校验</label>
          <div class="value">
            <span class="sub">时长误差 &gt;</span>
            <v-text-field
              v-model.number="cfg.validation_tolerance"
              type="number"
              density="compact"
              variant="outlined"
              hide-details
              class="w-90"
            />
            <span class="sub">秒视为失败</span>
            <span class="sub">历史保留</span>
            <v-text-field
              v-model.number="cfg.history_keep"
              type="number"
              density="compact"
              variant="outlined"
              hide-details
              class="w-90"
            />
            <span class="sub">条</span>
          </div>
        </div>
        <div class="form-row">
          <label>严格时长校验</label>
          <div class="value">
            <v-switch v-model="cfg.strict_duration_check" density="compact" color="primary" hide-details />
            <span class="sub">
              关闭时：输出时长与源视频偏差只记警告；开启时：偏差超过上面的阈值（{{ cfg.validation_tolerance }} 秒）判失败
            </span>
          </div>
        </div>
        <div class="form-row">
          <label>上传上限</label>
          <div class="value">
            <v-text-field
              v-model.number="cfg.upload_max_mb"
              type="number"
              density="compact"
              variant="outlined"
              hide-details
              class="w-90"
            />
            <span class="sub">MB，前端与后端双重校验；宿主 nginx 默认 50MB</span>
          </div>
        </div>
      </v-card>

      <!-- ================= 诊断 ================= -->
      <v-card variant="flat" class="config-card">
        <div class="config-card-title">诊断</div>
        <div class="form-row">
          <label>一键诊断</label>
          <div class="value">
            <v-btn size="small" variant="tonal" prepend-icon="mdi-stethoscope" :loading="diagnoseLoading" @click="runDiagnose">
              开始诊断
            </v-btn>
            <span class="sub">检查引擎版本、路径、空间、上传上限、配置一致性</span>
          </div>
        </div>
        <div v-if="diagnoseResults.length" class="diagnose-list">
          <div v-for="(item, index) in diagnoseResults" :key="index" class="diagnose-row">
            <v-icon
              size="15"
              :icon="item.ok ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"
              :color="item.ok ? 'success' : 'warning'"
            />
            <span class="diagnose-name">{{ item.name }}</span>
            <span class="diagnose-detail">{{ item.detail }}</span>
          </div>
        </div>
        <div v-if="diagnoseNote" class="diagnose-note">{{ diagnoseNote }}</div>
      </v-card>

      <!-- ================= 保存 ================= -->
      <div class="config-actions">
        <v-btn variant="text" prepend-icon="mdi-refresh" :disabled="saving" @click="loadConfig">重新加载</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="flat" prepend-icon="mdi-content-save" :loading="saving" @click="saveConfig">
          保存配置
        </v-btn>
      </div>
    </template>

    <!-- ================= 引擎安装对话框 ================= -->
    <v-dialog v-model="installOpen" max-width="620" scrollable>
      <v-card>
        <div class="dialog-head">
          <span class="dialog-title">安装 {{ installTargetLabel }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="closeInstall" />
        </div>
        <div class="dialog-body">
          <template v-if="!installStarted">
            <v-btn-toggle v-model="installMethod" mandatory density="compact" variant="outlined" divided class="mb-3">
              <v-btn v-for="item in INSTALL_METHODS" :key="item.value" :value="item.value" size="small">
                {{ item.title }}
              </v-btn>
            </v-btn-toggle>
            <div class="sub mb-3">{{ currentMethodDesc().desc }}</div>
            <v-text-field
              v-if="installMethod === 'path'"
              v-model="installPath"
              label="mkvmerge 可执行文件路径"
              placeholder="/usr/bin/mkvmerge"
              density="compact"
              variant="outlined"
              hide-details
              class="mono"
            />
            <div v-if="installError" class="install-error">{{ installError }}</div>
            <div class="install-tip">安装过程在后台线程执行，可以关闭此窗口；完成后引擎状态会自动刷新。</div>
          </template>
          <template v-else>
            <div class="install-state">
              <v-progress-circular v-if="installRunning" indeterminate size="16" width="2" color="primary" />
              <v-icon v-else :icon="installOk ? 'mdi-check-circle' : 'mdi-alert-circle'" :color="installOk ? 'success' : 'error'" size="18" />
              <span>{{ installRunning ? '安装中…' : (installOk ? '安装完成' : '安装失败') }}</span>
            </div>
            <pre v-if="installLog" class="install-log">{{ installLog }}</pre>
            <div v-if="installError" class="install-error">{{ installError }}</div>
          </template>
        </div>
        <div class="dialog-foot">
          <v-btn variant="text" @click="closeInstall">{{ installStarted ? '关闭' : '取消' }}</v-btn>
          <v-btn v-if="!installStarted" color="primary" variant="flat" @click="startInstall">开始安装</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- ================= 添加根目录 ================= -->
    <v-dialog v-model="rootDialog" max-width="480">
      <v-card>
        <div class="dialog-head">
          <span class="dialog-title">添加媒体根目录</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="rootDialog = false" />
        </div>
        <div class="dialog-body">
          <v-text-field
            v-model="newRoot"
            label="容器内绝对路径"
            placeholder="/media"
            density="compact"
            variant="outlined"
            hide-details
            class="mono"
            @keyup.enter="addRoot"
          />
          <div class="install-tip">路径必须存在于容器内，例如 <span class="mono">/media</span>、<span class="mono">/downloads</span>。</div>
        </div>
        <div class="dialog-foot">
          <v-btn variant="text" @click="rootDialog = false">取消</v-btn>
          <v-btn color="primary" variant="flat" @click="addRoot">添加</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- ================= 语言映射 ================= -->
    <v-dialog v-model="languageDialog" max-width="560">
      <v-card>
        <div class="dialog-head">
          <span class="dialog-title">编辑语言映射</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="languageDialog = false" />
        </div>
        <div class="dialog-body">
          <v-textarea
            v-model="languageText"
            rows="8"
            density="compact"
            variant="outlined"
            hide-details
            class="mono"
            placeholder=".zh=chi&#10;.chs=chi&#10;.jpn=jpn"
          />
          <div class="install-tip">每行一条：<span class="mono">文件名后缀=ISO639-2 语言码</span>，例如 <span class="mono">.zh=chi</span>。</div>
        </div>
        <div class="dialog-foot">
          <v-btn variant="text" @click="languageDialog = false">取消</v-btn>
          <v-btn color="primary" variant="flat" @click="saveLanguage">确定</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.config-page {
  display: flex;
  flex-direction: column;
  padding: 18px 22px 28px;
  overflow: auto;
  min-height: 0;
  height: 100%;
}
/* 滚动容器里的卡片不允许被 flex 压缩，否则内容会被截断 */
.config-page > * {
  flex: 0 0 auto;
}
.config-card {
  padding: 16px 18px;
  margin-bottom: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
  width: 100%;
}
.config-card-title {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  margin-bottom: 12px;
}
.form-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 10px 16px;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px dashed rgba(var(--v-theme-on-surface), 0.12);
}
.form-row:last-child {
  border-bottom: none;
}
.form-row > label {
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 12.5px;
}
.form-row .value {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
}
.sub {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 11.5px;
  line-height: 1.5;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11.5px;
}
.ellipsis {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.path-input {
  flex: 1 1 240px;
  min-width: 180px;
  max-width: 420px;
}
.w-90 {
  max-width: 90px;
}
.w-180 {
  max-width: 180px;
}
.w-260 {
  max-width: 260px;
}
.root-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.root-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: 7px;
  padding: 3px 9px;
  color: rgba(var(--v-theme-on-surface), 0.75);
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
}
.root-del {
  border: none;
  background: none;
  color: rgba(var(--v-theme-on-surface), 0.45);
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
  font-family: inherit;
}
.root-del:hover {
  color: #ef5350;
}
.diagnose-list {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.diagnose-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  padding: 3px 0;
}
.diagnose-name {
  flex: 0 0 130px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.diagnose-detail {
  flex: 1;
  min-width: 0;
  color: rgba(var(--v-theme-on-surface), 0.5);
  word-break: break-all;
}
.diagnose-note {
  margin-top: 10px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.65);
}
.config-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 2px 4px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.dialog-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.dialog-title {
  font-size: 14.5px;
  font-weight: 600;
}
.dialog-body {
  padding: 16px 20px;
  overflow: auto;
  max-height: 66vh;
}
.dialog-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.install-error {
  margin-top: 10px;
  font-size: 12.5px;
  color: #ef5350;
  background: rgba(239, 83, 80, 0.1);
  border: 1px solid rgba(239, 83, 80, 0.32);
  border-radius: 8px;
  padding: 9px 12px;
}
.install-tip {
  margin-top: 10px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  line-height: 1.6;
}
.install-state {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 10px;
}
.install-log {
  margin: 0;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 12px;
  font-size: 11px;
  line-height: 1.6;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
@media (max-width: 959px) {
  .config-page {
    padding: 12px 12px 20px;
  }
  .config-card {
    padding: 12px 14px;
    border-radius: 12px;
  }
  .form-row {
    grid-template-columns: 1fr;
    gap: 6px;
    padding: 8px 0;
  }
  .form-row > label {
    font-size: 12px;
  }
  .form-row .value {
    flex-wrap: wrap;
    gap: 8px;
  }
  .path-input {
    flex: 1 1 100%;
    max-width: none;
    min-width: 0;
  }
  .w-90,
  .w-180,
  .w-260 {
    max-width: 100%;
  }
  .diagnose-name {
    flex: 0 0 96px;
  }
  .dialog-body {
    padding: 14px;
    max-height: none;
  }
  .dialog-head,
  .dialog-foot {
    padding-left: 14px;
    padding-right: 14px;
  }
  .dialog-foot > * {
    flex: 1 1 0;
  }
}
</style>
