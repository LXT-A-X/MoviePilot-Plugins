<script setup>
import { computed, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createApi } from './api.js'
import Config from './Config.vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OpenClashPanel' },
  navKey: { type: String, default: 'main' },
  initialConfig: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  showClose: { type: Boolean, default: false },
})

const emit = defineEmits(['action', 'close', 'switch'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()
const api = createApi(props)

const tab = ref('panel')
const loading = ref(true)
const error = ref('')
const busy = ref(false)
const testing = ref(false)
const testingProgress = ref({ done: 0, total: 0 })
const refreshing = ref('')
const saving = ref(false)
const status = ref({})
const groups = ref([])
const providers = ref([])
const delays = ref({})
const testingOne = ref({})
const activeGroupName = ref('')
const config = ref({ ...props.initialConfig })

const logs = ref([])
const logsRunning = ref(false)
const logsExists = ref(true)
const logsPath = ref('')
const logsLoading = ref(false)
const logSource = ref('plugin')
const logLevel = ref('all')
const logLevels = ['all', 'info', 'warning', 'error', 'debug']

const netMode = ref('kernel')
const netResults = ref([])
const netLoading = ref(false)
const netChecking = ref(false)
const netUpdatedAt = ref(0)
const netNote = ref('')
const netProxy = ref('')

const netUpdatedText = computed(() => {
  if (!netUpdatedAt.value) return ''
  return new Date(netUpdatedAt.value * 1000).toLocaleTimeString()
})

// ------------------------------------------------------------------ OpenClash 管理（OpenWrt/LuCI）
const ocwebLoading = ref(false)
const ocweb = ref({
  run_mode: '',
  config_name: '',
  config_files: [],
  rule_mode: '',
  mixed_port: '',
  oversea: '0',
  sniffer: false,
  respect: false,
  stream: false,
})
const apiEndpoint = computed(() => {
  try {
    const url = new URL(config.value.api_url || '')
    return `${url.hostname}:${url.port || '9090'}`
  } catch (e) {
    return config.value.api_url || '—'
  }
})
const mixedPort = computed(() => ocweb.value.mixed_port || '7893')
const ocwebInfo = ref({ toolbar: {}, subinfo: {} })

const subinfoItems = computed(() => {
  const raw = ocwebInfo.value.subinfo || {}
  const list = raw.providers || raw.data || (Array.isArray(raw) ? raw : [])
  if (!Array.isArray(list)) return []
  return list.map((item) => ({
    name: item.name || item.filename || '订阅',
    surplus: item.surplus,
    total: item.total ?? item.used ?? '',
    day_left: item.day_left,
  }))
})

async function loadOcwebInfo() {
  if (!config.value.openwrt_enabled) return
  try {
    const res = await api.get('/ocweb/info')
    ocwebInfo.value = {
      toolbar: (res && res.toolbar) || {},
      subinfo: (res && res.subinfo) || {},
    }
  } catch (e) {
    // 资源信息读取失败不阻塞面板
  }
}

function copyText(text) {
  if (!text || text === '—') return
  try {
    navigator.clipboard.writeText(String(text))
    toastMsg('success', '已复制')
  } catch (e) {
    toastMsg('error', '复制失败')
  }
}

const modeOptions = [
  { value: 'rule', label: '规则' },
  { value: 'global', label: '全局' },
  { value: 'direct', label: '直连' },
]
const DEFAULT_NET_SITES = ['百度搜索', '网易云音乐', 'GitHub', 'YouTube']
const netSites = computed(() => {
  const cfgSites = Array.isArray(config.value.netcheck_sites) ? config.value.netcheck_sites : []
  const sites = cfgSites.length
    ? cfgSites.map((item) => ({ name: typeof item === 'string' ? item : item.name }))
    : DEFAULT_NET_SITES.map((name) => ({ name }))
  for (const item of netResults.value) {
    if (!sites.some((site) => site.name === item.name)) sites.push({ name: item.name })
  }
  return sites
})
function netResultFor(name) {
  return netResults.value.find((item) => item.name === name) || null
}

const netModeOptions = [
  { value: 'kernel', label: '内核' },
  { value: 'mp', label: 'MP' },
  { value: 'clash', label: 'OpenClash' },
]

const runModeOptions = [
  { value: '', label: '基础' },
  { value: '-tun', label: '增强(TUN)' },
  { value: '-mix', label: '混合(MIX)' },
]

function modeLabel(mode) {
  const value = String(mode || '').toLowerCase()
  return { rule: '规则', global: '全局', direct: '直连' }[value] || (mode || '—')
}

function runModeLabel(mode) {
  const text = String(mode || '')
  if (text.endsWith('-tun')) return '增强(TUN)'
  if (text.endsWith('-mix')) return '混合(MIX)'
  return text ? '基础' : '—'
}

function isRunMode(value) {
  const current = String(ocweb.value.run_mode || '')
  if (value === '') return !current.endsWith('-tun') && !current.endsWith('-mix')
  return current.endsWith(value)
}

async function loadOcweb() {
  if (!config.value.openwrt_enabled) return
  ocwebLoading.value = true
  try {
    const res = await api.get('/ocweb/status')
    const status = (res && res.status) || {}
    const settings = (res && res.settings) || {}
    const files = (res && res.config_files) || []
    ocweb.value = {
      run_mode: (res && res.run_mode) || '',
      config_name: (res && res.config_name) || '',
      config_files: files.map((item) =>
        typeof item === 'string' ? item : item?.name || item?.filename || String(item),
      ),
      rule_mode: status.rule_mode || '',
      mixed_port: status.mixed_port || '',
      oversea: String(settings.oversea ?? '0'),
      sniffer: String(settings.meta_sniffer ?? '0') === '1',
      respect: String(settings.respect_rules ?? '0') === '1',
      stream: String(settings.stream_unlock ?? '0') === '1',
    }
  } catch (e) {
    toastMsg('error', `读取 OpenWrt 状态失败：${e.message}`)
  } finally {
    ocwebLoading.value = false
  }
  loadOcwebInfo()
}

async function ocwebAction(op, params = {}, confirmText = '') {
  if (confirmText && !window.confirm(confirmText)) return
  ocwebLoading.value = true
  try {
    const res = await api.post('/ocweb/manage', { op, ...params })
    toastMsg('success', (res && res.message) || '操作已执行')
    setTimeout(() => loadOcweb(), 1500)
  } catch (e) {
    toastMsg('error', `操作失败：${e.message}`)
  } finally {
    ocwebLoading.value = false
  }
}

function switchRunMode(item) {
  ocwebAction(
    'run_mode',
    { run_mode: item.value },
    `切换运行模式为「${item.label}」？会重启 OpenClash，全屋网络会短暂中断。`,
  )
}

function switchOversea(value) {
  ocwebAction('setting', { setting: 'oversea', value: String(value) }, '切换区域绕过？会重载 OpenClash 配置。')
}

function toggleOcwebSetting(setting, enabled, label) {
  ocwebAction('setting', { setting, value: enabled ? '1' : '0' }, `切换「${label}」？`)
}

let refreshTimer = null
let netTimer = null

const currentGroup = computed(
  () => groups.value.find((g) => g.name === activeGroupName.value) || groups.value[0] || null,
)
const modeModel = computed(() => status.value?.mode || 'rule')
const filteredLogs = computed(() =>
  logLevel.value === 'all' ? logs.value : logs.value.filter((item) => item.level === logLevel.value),
)
const currentNowText = computed(() => {
  const group = currentGroup.value
  if (!group) return ''
  if (group.type === 'Smart' || String(group.now || '').startsWith('Smart')) return '智能自动选路'
  return group.now || '未选择'
})
const currentIsSmart = computed(() => currentGroup.value?.type === 'Smart')

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message)
}

function chooseDefaultGroup(list) {
  if (!list.length) return ''
  for (const keyword of ['默认代理', '全部节点']) {
    const hit = list.find((g) => g.name.includes(keyword))
    if (hit) return hit.name
  }
  return list[0].name
}

// 组测速返回的 children 是 {成员名: 延迟}，合并进 delays 状态
function mergeDelayResults(results) {
  if (!results || typeof results !== 'object') return
  const next = { ...delays.value }
  for (const [key, value] of Object.entries(results)) {
    if (value && value.children && typeof value.children === 'object') {
      for (const [child, ms] of Object.entries(value.children)) {
        next[child] = { delay: ms, error: null, skipped: false }
      }
    }
    next[key] = {
      delay: value?.delay ?? null,
      error: value?.error ?? null,
      skipped: Boolean(value?.skipped),
    }
  }
  delays.value = next
}

async function loadConfig() {
  try {
    const cfg = await api.get('/config')
    config.value = { ...config.value, ...(cfg || {}) }
  } catch (e) {
    // 配置读取失败不阻塞主面板
  }
}

async function loadAll(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [s, g, p] = await Promise.all([
      api.get('/status'),
      api.get('/groups'),
      api.get('/providers'),
    ])
    status.value = s || {}
    const list = (g && g.groups) || []
    groups.value = list
    if (!list.some((item) => item.name === activeGroupName.value)) {
      activeGroupName.value = chooseDefaultGroup(list)
    }
    providers.value = (p && p.providers) || []
  } catch (e) {
    error.value = e.message || '加载 OpenClash 数据失败'
  } finally {
    loading.value = false
  }
  if (config.value.openwrt_enabled) {
    loadOcwebInfo()
  }
}

async function loadLogs(silent = false) {
  if (!silent) logsLoading.value = true
  try {
    const res = await api.get('/logs', { lines: 200, source: logSource.value })
    logs.value = (res && res.logs) || []
    logsRunning.value = Boolean(res && res.running)
    logsExists.value = res && res.exists !== false
    logsPath.value = (res && res.path) || ''
  } catch (e) {
    if (!silent) toastMsg('error', `读取日志失败：${e.message}`)
  } finally {
    logsLoading.value = false
  }
}

async function checkNet(force = false, retry = 0) {
  if (typeof force !== 'boolean') force = false
  if (force) netLoading.value = true
  try {
    const res = await api.get('/netcheck', { mode: netMode.value, refresh: force ? 1 : 0 })
    if (res && Array.isArray(res.results) && res.results.length) {
      const merged = new Map(netResults.value.map((item) => [item.name, item]))
      for (const item of res.results) merged.set(item.name, item)
      netResults.value = Array.from(merged.values())
    }
    netNote.value = (res && res.note) || ''
    netProxy.value = (res && res.proxy) || ''
    netUpdatedAt.value = Number((res && res.updated_at) || 0)
    netChecking.value = Boolean(res && res.checking)
    if (netChecking.value && retry < 12) {
      setTimeout(() => checkNet(false, retry + 1), 1500)
    }
  } catch (e) {
    if (force) toastMsg('error', `访问检查失败：${e.message}`)
  } finally {
    netLoading.value = false
  }
}

function netColor(item) {
  if (!item || item.delay == null) return 'error'
  if (item.delay < 300) return 'success'
  if (item.delay < 1000) return 'warning'
  return 'error'
}

function netText(item) {
  if (!item || item.delay == null) return '失败'
  return `${item.delay} ms`
}

async function switchNode(node) {
  if (!currentGroup.value || node.selected || busy.value) return
  if (currentIsSmart.value) {
    toastMsg('info', '智能组（Smart）由内核自动选路，不能在组内手动指定节点；可在上层组里选择这个智能组')
    return
  }
  busy.value = true
  try {
    await api.post('/switch', { group: currentGroup.value.name, name: node.name })
    toastMsg('success', `已切换：${node.name}`)
    await loadAll(true)
  } catch (e) {
    error.value = e.message
    toastMsg('error', e.message)
  } finally {
    busy.value = false
  }
}

async function changeMode(value) {
  if (!value || value === status.value.mode) return
  try {
    await api.post('/mode', { mode: value })
    toastMsg('success', `规则模式已切换为 ${value}`)
    await loadAll(true)
  } catch (e) {
    error.value = e.message
    toastMsg('error', e.message)
  }
}

// 单项测速：点延迟徽章或行内「测」按钮，不触发切节点
async function testOne(name) {
  if (!name || testingOne.value[name]) return
  testingOne.value = { ...testingOne.value, [name]: true }
  try {
    const res = await api.post('/delay', {
      names: [name],
      url: config.value.delay_test_url,
      timeout: config.value.delay_test_timeout,
    })
    mergeDelayResults(res && res.results)
  } catch (e) {
    toastMsg('error', `测速失败：${e.message}`)
  } finally {
    const next = { ...testingOne.value }
    delete next[name]
    testingOne.value = next
  }
}

async function testGroup() {
  const group = currentGroup.value
  if (!group || testing.value) return
  testing.value = true
  testingProgress.value = { done: 0, total: 0 }
  try {
    const url = config.value.delay_test_url
    const timeout = config.value.delay_test_timeout
    let success = 0
    let failed = 0
    if (currentIsSmart.value) {
      testingProgress.value = { done: 0, total: 1 }
      const res = await api.post('/delay', { names: [group.name], url, timeout })
      mergeDelayResults(res && res.results)
      for (const item of Object.values((res && res.results) || {})) {
        if (item && item.delay != null) success += 1
        else failed += 1
      }
      testingProgress.value = { done: 1, total: 1 }
    } else {
      const members = group.members.map((m) => m.name)
      const batchSize = 8
      testingProgress.value = { done: 0, total: members.length }
      for (let i = 0; i < members.length; i += batchSize) {
        const batch = members.slice(i, i + batchSize)
        const res = await api.post('/delay', { names: batch, url, timeout })
        mergeDelayResults(res && res.results)
        for (const item of Object.values((res && res.results) || {})) {
          if (item && item.delay != null) success += 1
          else if (item && item.skipped) failed += 0
          else failed += 1
        }
        testingProgress.value.done = Math.min(i + batchSize, members.length)
      }
    }
    if (failed) {
      toastMsg('warning', `测速完成：${success} 成功，${failed} 超时/失败`)
    } else {
      toastMsg('success', `测速完成：${success} 项全部成功`)
    }
  } catch (e) {
    error.value = e.message
    toastMsg('error', e.message)
  } finally {
    testing.value = false
    testingProgress.value = { done: 0, total: 0 }
  }
}

async function refreshProvider(name) {
  refreshing.value = name
  try {
    await api.post('/providers/refresh', { name })
    toastMsg('success', `已触发 ${name} 订阅更新，节点稍后刷新`)
    await loadAll(true)
  } catch (e) {
    error.value = e.message
    toastMsg('error', e.message)
  } finally {
    refreshing.value = ''
  }
}

// 设置 Tab 里的保存：走宿主配置更新接口（PUT /api/v1/plugin/{id}），
// 与 MP 3.2.1 配置弹窗的保存路径一致，避免“参数不正确”。
async function onConfigSaved(cfg) {
  saving.value = true
  try {
    await api.put('', { ...(cfg || {}) })
    toastMsg('success', '配置已保存并生效')
    await loadConfig()
    await loadAll(true)
  } catch (e) {
    error.value = e.message
    toastMsg('error', `保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

function openDashboard() {
  const url = config.value.dashboard_url || 'http://192.168.1.1:9090/ui/zashboard/'
  window.open(url, '_blank', 'noopener')
}

// 「退出」：弹窗场景关闭弹窗；侧栏全页跳 MP 插件管理页（留在插件板块）
function exitPanel() {
  if (props.showClose) {
    emit('close')
    return
  }
  window.location.href = `${window.location.origin}/#/plugins?tab=installed`
}

function delayInfo(name) {
  return delays.value[name] || {}
}

function delayText(name) {
  const info = delayInfo(name)
  if (info.skipped) return '不可测'
  if (info.delay != null) return `${info.delay} ms`
  if (info.error) return '超时'
  return '—'
}

function delayColor(name) {
  const info = delayInfo(name)
  if (info.delay == null) return info.error ? 'error' : undefined
  if (info.delay < 200) return 'success'
  if (info.delay < 500) return 'warning'
  return 'error'
}

function fmtTime(value) {
  if (!value || String(value).startsWith('0001')) return '未知'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString()
}

function fmtBytes(n) {
  if (n == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = Number(n)
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(i ? 1 : 0)} ${units[i]}`
}

function trafficText() {
  return `${fmtBytes(status.value.download_total)} ↓ / ${fmtBytes(status.value.upload_total)} ↑`
}

watch(tab, (value) => {
  if (value === 'logs') loadLogs()
})

watch(logSource, () => loadLogs())

watch(netMode, () => checkNet(true))

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '82rem' })
  await loadConfig()
  await loadAll()
  const savedMode = config.value.netcheck_mode
  netMode.value = ['kernel', 'mp', 'clash'].includes(savedMode) ? savedMode : 'kernel'
  await checkNet(false)
  const seconds = Number(config.value.auto_refresh || 10)
  if (seconds > 0) {
    refreshTimer = setInterval(() => {
      loadAll(true)
      if (tab.value === 'logs') loadLogs(true)
    }, Math.max(3, seconds) * 1000)
  }
  const netSeconds = Number(config.value.netcheck_interval ?? 30)
  if (netSeconds > 0) {
    netTimer = setInterval(() => checkNet(false), Math.max(10, netSeconds) * 1000)
  }
  if (config.value.openwrt_enabled) {
    loadOcweb()
  }
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (netTimer) clearInterval(netTimer)
  refreshTimer = null
  netTimer = null
})
</script>

<template>
  <div class="ocp-page">
    <div class="ocp-header">
      <div class="d-flex align-center flex-wrap ga-2">
        <v-icon icon="mdi-shield-network-outline" color="primary" size="24" />
        <span class="text-h6 ocp-title">OpenClash</span>
        <v-chip v-if="status.meta" size="x-small" variant="tonal">Mihomo</v-chip>
        <v-spacer />
        <v-btn
          size="small"
          variant="text"
          icon="mdi-refresh"
          title="刷新"
          :loading="loading"
          @click="loadAll()"
        />
        <!-- 桌面：文字按钮 -->
        <v-btn
          v-if="config.show_dashboard !== false"
          class="d-none d-sm-flex"
          size="small"
          variant="tonal"
          prepend-icon="mdi-open-in-new"
          @click="openDashboard"
        >
          完整面板
        </v-btn>
        <v-btn class="d-none d-sm-flex" size="small" variant="text" prepend-icon="mdi-close" @click="exitPanel">
          退出
        </v-btn>
        <!-- 手机：图标按钮 -->
        <v-btn
          v-if="config.show_dashboard !== false"
          class="d-flex d-sm-none"
          size="small"
          variant="tonal"
          icon="mdi-open-in-new"
          title="完整面板"
          @click="openDashboard"
        />
        <v-btn class="d-flex d-sm-none" size="small" variant="text" icon="mdi-close" title="退出" @click="exitPanel" />
      </div>
    </div>

    <v-tabs v-model="tab" density="compact" color="primary" class="mt-1 mb-2">
      <v-tab value="panel" prepend-icon="mdi-view-dashboard-outline">面板</v-tab>
      <v-tab value="logs" prepend-icon="mdi-text-box-outline">日志</v-tab>
      <v-tab value="settings" prepend-icon="mdi-cog-outline">设置</v-tab>
    </v-tabs>

    <v-alert v-if="error" type="error" variant="tonal" density="compact" closable class="mb-2" @click:close="error = ''">
      {{ error }}
    </v-alert>

    <!-- ================= 面板 ================= -->
    <div v-if="tab === 'panel'">
      <v-skeleton-loader v-if="loading && !groups.length" type="card, list-item@3" />

      <template v-else>
        <div class="ocp-tiles">
          <v-card variant="tonal" class="ocp-tile ocp-tile--full">
            <div class="d-flex align-center flex-wrap ga-2">
              <span class="ocp-tile-title" style="margin: 0">总状态</span>
              <v-chip v-if="ocweb.run_mode" size="x-small" variant="tonal" color="info">{{ runModeLabel(ocweb.run_mode) }}</v-chip>
              <v-spacer />
              <v-btn size="x-small" variant="tonal" color="error" :loading="ocwebLoading"
                @click="ocwebAction('action', { action: 'restart' }, '确定重启 OpenClash？会短暂断网！')">重启</v-btn>
              <v-btn size="x-small" variant="tonal" :loading="ocwebLoading" @click="loadOcweb">刷新</v-btn>
            </div>
            <div class="ocp-statgrid mt-1">
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">内核</div>
                <div class="ocp-statbox-value">{{ status.version || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">模式</div>
                <div class="ocp-statbox-value">{{ modeLabel(status.mode) }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">运行模式</div>
                <div class="ocp-statbox-value">{{ runModeLabel(ocweb.run_mode) }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">连接</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.connections ?? status.active_connections ?? '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">内存</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.mem || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">CPU</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.cpu || '—' }}%</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">负载</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.load_avg || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">上传</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.up || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">下载</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.down || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">累计上传</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.up_total || fmtBytes(status.upload_total) }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">累计下载</div>
                <div class="ocp-statbox-value">{{ ocwebInfo.toolbar.down_total || fmtBytes(status.download_total) }}</div>
              </div>
            </div>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--wide">
            <div class="ocp-tile-title text-center">快捷操作</div>
            <div class="ocp-center-actions">
              <v-btn size="small" variant="tonal" color="error" :loading="ocwebLoading"
                @click="ocwebAction('close_connections', {}, '断开全部代理连接？')">关闭连接</v-btn>
              <v-btn size="small" variant="tonal" :loading="ocwebLoading"
                @click="ocwebAction('reload_firewall', {}, '重置防火墙规则？')">重置防火墙</v-btn>
              <v-btn size="small" variant="tonal" color="info" :loading="ocwebLoading"
                @click="ocwebAction('flush', { target: 'dns' }, '清空 DNS/Fake-IP 缓存？')">清 DNS 缓存</v-btn>
              <v-btn size="small" variant="tonal" color="info" :loading="ocwebLoading"
                @click="ocwebAction('flush', { target: 'smart' }, '清空 Smart 缓存？')">清 Smart 缓存</v-btn>
            </div>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--wide">
            <div class="ocp-tile-title">快捷设置</div>
            <div class="d-flex align-center flex-wrap ga-3">
              <v-select :model-value="ocweb.oversea"
                :items="[{ title: '关闭', value: '0' }, { title: '绕过大陆', value: '1' }, { title: '绕过海外', value: '2' }]"
                label="区域绕过" density="compact" hide-details style="max-width: 150px"
                @update:model-value="switchOversea" />
              <v-switch :model-value="ocweb.sniffer" label="域名嗅探" density="compact" hide-details
                @update:model-value="(v) => toggleOcwebSetting('meta_sniffer', v, '域名嗅探')" />
              <v-switch :model-value="ocweb.respect" label="DNS 代理" density="compact" hide-details
                @update:model-value="(v) => toggleOcwebSetting('respect_rules', v, 'DNS 代理')" />
              <v-switch :model-value="ocweb.stream" label="流媒体解锁" density="compact" hide-details
                @update:model-value="(v) => toggleOcwebSetting('stream_unlock', v, '流媒体解锁')" />
            </div>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--wide">
            <div class="ocp-modepair">
              <div class="ocp-statbox">
                <div class="ocp-statbox-label text-center">运行模式</div>
                <div class="ocp-center-actions mt-1">
                  <v-btn v-for="item in runModeOptions" :key="item.label" size="small"
                    :variant="isRunMode(item.value) ? 'flat' : 'outlined'"
                    :color="isRunMode(item.value) ? 'primary' : undefined"
                    @click="switchRunMode(item)">{{ item.label }}</v-btn>
                </div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label text-center">代理模式</div>
                <div class="ocp-center-actions mt-1">
                  <v-btn v-for="item in modeOptions" :key="item.value" size="small"
                    :variant="modeModel === item.value ? 'flat' : 'outlined'"
                    :color="modeModel === item.value ? 'primary' : undefined"
                    @click="changeMode(item.value)">{{ item.label }}</v-btn>
                </div>
              </div>
            </div>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--wide">
            <div class="ocp-tile-title">订阅源</div>
            <template v-if="providers.length">
              <div v-for="p in providers" :key="p.name" class="ocp-tile-line">
                {{ p.name }} · {{ p.node_count }} 节点
                <span class="text-caption text-medium-emphasis">更新于 {{ fmtTime(p.updated_at) }}</span>
                <v-btn size="x-small" variant="tonal" class="ml-2" :loading="refreshing === p.name"
                  @click="refreshProvider(p.name)">刷新</v-btn>
              </div>
            </template>
            <div v-else class="text-caption text-medium-emphasis">暂无订阅源</div>
            <template v-if="subinfoItems.length">
              <v-divider class="my-1" />
              <div v-for="item in subinfoItems" :key="item.name" class="ocp-tile-line">
                流量剩余：{{ item.surplus || '—' }}
                <template v-if="item.day_left != null">· 剩余 {{ item.day_left }} 天</template>
              </div>
            </template>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--full">
            <div class="d-flex align-center flex-wrap ga-2">
              <span class="ocp-tile-title" style="margin: 0">访问检查</span>
              <div class="ocp-center-actions">
                <v-btn v-for="item in netModeOptions" :key="item.value" size="x-small"
                  :variant="netMode === item.value ? 'flat' : 'outlined'"
                  :color="netMode === item.value ? 'primary' : undefined"
                  @click="netMode = item.value">{{ item.label }}</v-btn>
              </div>
              <v-spacer />
              <v-chip v-if="netChecking" size="x-small" variant="tonal" color="info">检查中</v-chip>
              <span v-if="netUpdatedAt" class="text-caption text-medium-emphasis">{{ netUpdatedText }}</span>
              <v-btn size="x-small" variant="text" icon="mdi-refresh" :loading="netLoading" @click="checkNet(true)" />
            </div>
            <div class="ocp-netgrid mt-1">
              <div v-for="site in netSites" :key="site.name" class="ocp-netcard">
                <div class="ocp-netcard-name">{{ site.name }}</div>
                <template v-if="netResultFor(site.name)">
                  <div :class="['ocp-netcard-value', `ocp-net-${netColor(netResultFor(site.name))}`]">
                    {{ netText(netResultFor(site.name)) }}
                  </div>
                </template>
                <div v-else class="ocp-netcard-skeleton"></div>
              </div>
              <div v-if="!netResults.length" class="text-caption text-medium-emphasis">
                {{ netLoading ? '检查中…' : '暂无结果，点刷新' }}
              </div>
            </div>
            <div v-if="netNote" class="text-caption text-medium-emphasis mt-1">{{ netNote }}</div>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--wide">
            <div class="ocp-tile-title">端口</div>
            <div class="ocp-statgrid">
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">HTTP</div>
                <div class="ocp-statbox-value">{{ status.ports?.http || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">SOCKS</div>
                <div class="ocp-statbox-value">{{ status.ports?.socks || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">REDIR</div>
                <div class="ocp-statbox-value">{{ status.ports?.redir || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">MIXED</div>
                <div class="ocp-statbox-value">{{ status.ports?.mixed || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">TPROXY</div>
                <div class="ocp-statbox-value">{{ status.ports?.tproxy || '—' }}</div>
              </div>
              <div class="ocp-statbox">
                <div class="ocp-statbox-label">TUN</div>
                <div class="ocp-statbox-value">{{ status.ports?.tun ? '开启' : '关闭' }}</div>
              </div>
            </div>
          </v-card>

          <v-card variant="tonal" class="ocp-tile ocp-tile--wide">
            <div class="ocp-tile-title">配置文件</div>
            <div class="d-flex align-center flex-wrap ga-2">
              <v-select v-model="ocweb.config_name" :items="ocweb.config_files" density="compact" hide-details
                label="配置文件" style="max-width: 200px" />
              <v-btn size="small" variant="tonal" :loading="ocwebLoading"
                @click="ocwebAction('switch_config', { config_name: ocweb.config_name }, '切换配置文件会重启 OpenClash！')">切换</v-btn>
              <v-btn size="small" variant="tonal" :loading="ocwebLoading"
                @click="ocwebAction('update_config', { filename: ocweb.config_name }, '更新当前订阅？')">更新订阅</v-btn>
            </div>
          </v-card>
        </div>

        <v-card variant="tonal" class="pa-2 mt-2">
          <div class="d-flex align-center flex-wrap ga-2">
            <span class="text-subtitle-2">策略组</span>
            <span class="text-caption text-medium-emphasis">{{ groups.length }} 个</span>
            <v-spacer />
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-speedometer"
              :loading="testing"
              :disabled="!currentGroup"
              @click="testGroup"
            >
              测本组延迟
            </v-btn>
            <v-chip v-if="testingProgress.total" size="x-small" variant="tonal" color="info">
              {{ testingProgress.done }}/{{ testingProgress.total }}
            </v-chip>
          </div>

          <div class="ocp-chips mt-2">
            <v-chip
              v-for="g in groups"
              :key="g.name"
              size="small"
              :variant="g.name === currentGroup?.name ? 'flat' : 'outlined'"
              :color="g.name === currentGroup?.name ? 'primary' : undefined"
              @click="activeGroupName = g.name"
            >
              {{ g.name }}
              <span class="ocp-chip-count">{{ g.count }}</span>
            </v-chip>
          </div>

          <div v-if="currentGroup" class="ocp-group-info d-flex align-center flex-wrap ga-2 mt-2">
            <v-chip size="x-small" variant="text">{{ currentGroup.type }}</v-chip>
            <v-chip v-if="currentIsSmart" size="x-small" color="info" variant="tonal">智能组 · 自动选路</v-chip>
            <span class="text-caption text-medium-emphasis">当前：{{ currentNowText }}</span>
            <span v-if="busy" class="text-caption text-medium-emphasis">切换中…</span>
            <span class="text-caption text-medium-emphasis">点延迟徽章或「测」可单独测速</span>
          </div>

          <v-row dense class="mt-1">
            <v-col
              v-for="node in (currentGroup?.members || [])"
              :key="node.name"
              cols="12"
              sm="6"
              md="4"
              lg="3"
            >
              <v-card
                :variant="node.selected ? 'flat' : 'outlined'"
                :color="node.selected ? 'primary' : undefined"
                :class="['ocp-node', currentIsSmart ? 'ocp-node--readonly' : '']"
                @click="switchNode(node)"
              >
                <div class="d-flex align-center ga-2 pa-2">
                  <v-icon
                    :icon="node.selected ? 'mdi-check-circle' : 'mdi-circle-outline'"
                    size="16"
                    :color="node.selected ? 'white' : 'medium-emphasis'"
                  />
                  <span class="ocp-node-name" :title="node.name">{{ node.name }}</span>
                  <v-chip v-if="node.is_group" size="x-small" variant="text" class="ocp-tag">组</v-chip>
                  <v-spacer />
                  <v-btn
                    size="x-small"
                    variant="text"
                    icon="mdi-speedometer"
                    title="单独测这一项"
                    :loading="Boolean(testingOne[node.name])"
                    @click.stop="testOne(node.name)"
                  />
                  <v-chip
                    size="x-small"
                    variant="flat"
                    :color="delayColor(node.name)"
                    class="ocp-delay"
                    title="点击单独测速"
                    @click.stop="testOne(node.name)"
                  >
                    {{ delayText(node.name) }}
                  </v-chip>
                </div>
              </v-card>
            </v-col>
          </v-row>

          <div v-if="!currentGroup" class="text-caption text-medium-emphasis pa-2">
            暂无策略组数据（请检查 API 地址 / Dashboard 密码）
          </div>
          <div v-else-if="currentIsSmart" class="text-caption text-medium-emphasis pa-2">
            智能组由内核自动选路：可查看成员、单测延迟，但不能在组内手动指定节点；需要固定出口请在上层策略组里选择它。
          </div>
        </v-card>


        <div class="text-caption text-medium-emphasis mt-3">
          API：{{ config.api_url || '未配置' }} · 数据每 {{ config.auto_refresh || 10 }} 秒自动刷新
        </div>
      </template>
    </div>

    <!-- ================= 日志 ================= -->
    <div v-else-if="tab === 'logs'">
      <div class="d-flex align-center flex-wrap ga-2 mb-2">
        <span class="text-subtitle-2">日志</span>
        <v-btn-toggle v-model="logSource" mandatory density="compact" variant="outlined" divided>
          <v-btn value="plugin" size="small">插件日志</v-btn>
          <v-btn value="kernel" size="small">内核日志</v-btn>
        </v-btn-toggle>
        <v-chip size="x-small" variant="tonal">{{ logs.length }} 条</v-chip>
        <v-chip v-if="logSource === 'kernel' && logsRunning" size="x-small" color="success" variant="tonal">
          采集中
        </v-chip>
        <v-chip v-if="logSource === 'plugin' && !logsExists" size="x-small" color="warning" variant="tonal">
          文件未生成
        </v-chip>
        <v-spacer />
        <v-select
          v-model="logLevel"
          :items="logLevels"
          label="级别"
          density="compact"
          hide-details
          variant="outlined"
          style="max-width: 120px"
        />
        <v-btn size="small" variant="text" icon="mdi-refresh" :loading="logsLoading" @click="loadLogs" />
      </div>

      <v-alert
        v-if="logSource === 'plugin' && !logsExists"
        type="info"
        variant="tonal"
        density="compact"
        class="mb-2"
      >
        插件日志文件还没生成（{{ logsPath || 'config/logs/plugins/openclashpanel.log' }}）。
        插件启用后执行初始化/切换等操作会写入；也可以切到「内核日志」看 Clash 输出。
      </v-alert>

      <v-card variant="tonal" class="pa-2">
        <div class="ocp-logs">
          <div v-for="(item, index) in filteredLogs" :key="index" class="ocp-log-line">
            <span class="ocp-log-time">{{ item.time }}</span>
            <span :class="['ocp-log-level', `ocp-log-${item.level}`]">{{ item.level }}</span>
            <span class="ocp-log-text">{{ item.text }}</span>
          </div>
          <div v-if="!filteredLogs.length" class="text-caption text-medium-emphasis pa-2">
            {{ logSource === 'plugin' ? '暂无插件日志（插件还没写日志或文件尚未生成）。' : '暂未收到内核日志（可在设置里调日志级别，或产生一点流量）。' }}
          </div>
        </div>
      </v-card>
      <div v-if="logSource === 'plugin' && logsPath" class="text-caption text-medium-emphasis mt-1">
        文件：{{ logsPath }}
      </div>
    </div>

    <!-- ================= 设置 ================= -->
    <div v-else-if="tab === 'settings'">
      <v-alert type="info" variant="tonal" density="compact" class="mb-2">
        保存会写回 MoviePilot 并立即生效；api_url 只填 <code>http://路由器IP:9090</code>（误填 <code>/ui/...</code> 也会自动纠正）。
      </v-alert>
      <Config
        :api="props.api"
        :plugin-id="props.pluginId"
        :initial-config="config"
        @save="onConfigSaved"
      />
      <div v-if="saving" class="text-caption text-medium-emphasis mt-2">正在保存…</div>
    </div>
  </div>
</template>

<style scoped>
.ocp-page {
  padding: 4px 2px 12px;
}
.ocp-header {
  padding-bottom: 2px;
}
.ocp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 132px;
  overflow-y: auto;
}
.ocp-chip-count {
  opacity: 0.6;
  margin-left: 4px;
  font-size: 11px;
}
.ocp-node {
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.ocp-node:hover {
  transform: translateY(-1px);
}
.ocp-node--readonly {
  cursor: default;
}
.ocp-node--readonly:hover {
  transform: none;
}
.ocp-node-name {
  font-size: 13px;
  line-height: 1.25;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}
.ocp-tag {
  flex: 0 0 auto;
  opacity: 0.75;
}
.ocp-delay {
  flex: 0 0 auto;
  cursor: pointer;
}
.ocp-logs {
  max-height: 62vh;
  overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
}
.ocp-log-line {
  display: flex;
  gap: 8px;
  padding: 1px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.12);
}
.ocp-log-time {
  color: rgba(128, 128, 128, 0.9);
  flex: 0 0 auto;
}
.ocp-log-level {
  flex: 0 0 62px;
  text-transform: uppercase;
  font-size: 10px;
  padding-top: 1px;
}
.ocp-log-info {
  color: #4a90d9;
}
.ocp-log-warning {
  color: #d99a2b;
}
.ocp-log-error {
  color: #d9534f;
}
.ocp-log-debug {
  color: #8a8a8a;
}
.ocp-log-text {
  word-break: break-all;
  white-space: pre-wrap;
}
.ocp-netrow {
  display: flex;
  flex-wrap: nowrap;
  gap: 14px;
  overflow-x: auto;
  padding-bottom: 2px;
}
.ocp-netitem {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  white-space: nowrap;
  flex: 0 0 auto;
}
.ocp-netname {
  font-size: 12px;
  opacity: 0.8;
}
.ocp-netdelay {
  font-size: 15px;
  font-weight: 600;
}
.ocp-net-success {
  color: #4caf50;
}
.ocp-net-warning {
  color: #ff9800;
}
.ocp-net-error {
  color: #f44336;
}

/* ---------------- 手机优化 ---------------- */
@media (max-width: 600px) {
  .ocp-page {
    padding: 0 0 8px;
  }
  .ocp-title {
    font-size: 1.05rem !important;
  }
  .ocp-page :deep(.v-card) {
    border-radius: 10px;
  }
  .ocp-chips {
    flex-wrap: nowrap;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 4px;
    -webkit-overflow-scrolling: touch;
  }
  .ocp-chips .v-chip {
    flex: 0 0 auto;
  }
  .ocp-chip-count {
    display: none;
  }
  .ocp-node-name {
    font-size: 14px;
  }
  .ocp-node .v-chip {
    min-height: 26px;
  }
  .ocp-group-info {
    row-gap: 4px;
  }
  .ocp-logs {
    max-height: 52vh;
    font-size: 11px;
  }
  .ocp-log-level {
    flex: 0 0 48px;
  }
}

.ocp-panel-card :deep(.mt-2) {
  margin-top: 4px !important;
}
.ocp-panel-card :deep(.v-btn) {
  min-height: 26px;
}
.ocp-panel-card :deep(.d-flex) {
  gap: 6px;
}
.ocp-panel-card :deep(.v-chip) {
  height: 20px;
}
@media (max-width: 600px) {
  .ocp-panel-card :deep(.v-btn) {
    font-size: 12px;
    padding: 0 8px;
  }
  .ocp-panel-card :deep(.v-select) {
    max-width: 150px !important;
    min-width: 120px;
  }
  .ocp-panel-card :deep(.v-switch) {
    margin: 0;
  }
}

.ocp-tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  grid-auto-rows: minmax(100px, auto);
  gap: 8px;
  margin-bottom: 8px;
}
.ocp-tile--wide {
  grid-column: span 2;
}
@media (max-width: 1000px) {
  .ocp-tiles {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .ocp-tile--wide {
    grid-column: span 3;
  }
}
@media (max-width: 700px) {
  .ocp-tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .ocp-tile--wide {
    grid-column: span 2;
  }
}
@media (max-width: 420px) {
  .ocp-tiles {
    grid-template-columns: minmax(0, 1fr);
  }
  .ocp-tile--wide {
    grid-column: span 1;
  }
}
.ocp-tile {
  padding: 10px 12px;
  border-radius: 12px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.ocp-tile:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
}
.ocp-tile-title {
  font-size: 12px;
  font-weight: 500;
  opacity: 0.72;
  margin-bottom: 6px;
}
.ocp-tile-line {
  font-size: 12px;
  line-height: 1.7;
}
.ocp-tile-value {
  font-size: 15px;
  font-weight: 600;
  color: #4caf50;
  word-break: break-all;
}
.ocp-tile-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}


.ocp-netgrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}
@media (max-width: 700px) {
  .ocp-netgrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.ocp-netcard {
  border: 1px solid rgba(128, 128, 128, 0.18);
  border-radius: 10px;
  padding: 8px 10px;
}
.ocp-netcard-name {
  font-size: 12px;
  opacity: 0.75;
}
.ocp-netcard-value {
  font-size: 18px;
  font-weight: 700;
  margin-top: 2px;
}


.ocp-tile--full {
  grid-column: span 4;
}
.ocp-statrow {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}
.ocp-statitem {
  font-size: 12px;
  white-space: nowrap;
}
.ocp-center {
  text-align: center;
}
.ocp-center-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 6px;
}
@media (max-width: 1000px) {
  .ocp-tile--full {
    grid-column: span 3;
  }
}
@media (max-width: 700px) {
  .ocp-tile--full {
    grid-column: span 2;
  }
}
@media (max-width: 420px) {
  .ocp-tile--full {
    grid-column: span 1;
  }
}
@media (max-width: 600px) {
  .ocp-statrow {
    gap: 2px 10px;
  }
  .ocp-statitem {
    font-size: 11px;
  }
}

.ocp-statgrid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(105px, 1fr));
  gap: 6px;
}
.ocp-statbox {
  border: 1px solid rgba(128, 128, 128, 0.18);
  border-radius: 8px;
  padding: 6px 8px;
  min-width: 0;
}
.ocp-statbox-label {
  font-size: 11px;
  opacity: 0.68;
}
.ocp-statbox-value {
  font-size: 14px;
  font-weight: 600;
  margin-top: 2px;
  word-break: break-all;
}
.ocp-modepair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
@media (max-width: 700px) {
  .ocp-modepair {
    grid-template-columns: 1fr;
  }
}

.ocp-tile,
.ocp-tile-title,
.ocp-tile-line,
.ocp-tile-value,
.ocp-statbox,
.ocp-statbox-label,
.ocp-statbox-value,
.ocp-netcard-name,
.ocp-netcard-value {
  text-align: center;
}
.ocp-tile-actions,
.ocp-center-actions {
  justify-content: center;
}
.ocp-tile .d-flex {
  justify-content: center;
}
.ocp-netcard--loading {
  animation: ocp-pulse 1s ease-in-out infinite;
}
@keyframes ocp-pulse {
  0%, 100% {
    opacity: 0.45;
  }
  50% {
    opacity: 1;
  }
}

.ocp-tile :deep(.v-btn--variant-flat) {
  color: #fff !important;
}

.ocp-netcard-skeleton {
  height: 18px;
  margin-top: 4px;
  border-radius: 6px;
  background: linear-gradient(90deg, rgba(128, 128, 128, 0.12) 25%, rgba(128, 128, 128, 0.3) 37%, rgba(128, 128, 128, 0.12) 63%);
  background-size: 400% 100%;
  animation: ocp-shimmer 1.2s ease infinite;
}
@keyframes ocp-shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: 0 0;
  }
}
</style>
