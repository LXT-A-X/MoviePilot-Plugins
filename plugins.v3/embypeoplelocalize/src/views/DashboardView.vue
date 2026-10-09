<script setup>
import { computed, inject, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import api from '../api/client.js'
import ConfirmDlg from '../components/ConfirmDlg.vue'
import { useConfirm } from '../components/useConfirm.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['action', 'notify'])
const toast = inject('moviepilot:toast', null)
const { cState, askConfirm, cOk, cCancel } = useConfirm()

const loading = ref(true)
const status = ref(null)
const dbStats = ref(null)
const logs = ref([])
const webhookEvents = ref([])
const busy = ref('')

const deps = ref({ items: [], ok_count: 0, total: 0 })
const depsDialog = ref(false)
const depsLoading = ref(false)

function notify(msg, type = 'error') {
  let handled = false
  try { if (toast && typeof toast[type] === 'function') { toast[type](msg); handled = true } } catch (e) {}
  if (!handled) { try { emit('notify', msg, type) } catch (e) {} }
}

function scanStatus() { return status.value?.scan_status || {} }

function fmtTime(ts) {
  if (!ts) return ''
  try {
    const t = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
    const p = n => String(n).padStart(2, '0')
    return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())} ${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())}`
  } catch (e) { return '' }
}

async function loadDeps() {
  depsLoading.value = true
  try {
    const data = await api.get(props.api, '/deps/check')
    deps.value = data?.items ? data : { items: [], ok_count: 0, total: 0 }
  } catch (e) { deps.value = { items: [], ok_count: 0, total: 0 } }
  depsLoading.value = false
}

let loadAllBusy = false
// v4.6.66（P1 仪表盘刷新）：单请求超时保护 —— 任一接口悬挂时 Promise.allSettled 永不返回，
// loadAllBusy 会永久锁死轮询（表现为「开关改了提示不消失，必须进出插件」）。
function withTimeout(p, ms = 15000) {
  return Promise.race([
    p,
    new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)),
  ])
}
async function loadAll() {
  // 轮询锁（UI-002）：上一轮未完成时不叠加新一轮；接口并行取（不再串行 5 个 await）
  if (loadAllBusy) return
  loadAllBusy = true
  try {
    const [st, db, lg, wh, pd] = await Promise.allSettled([
      withTimeout(api.get(props.api, '/status')),
      withTimeout(api.get(props.api, '/db/stats')),
      withTimeout(api.get(props.api, '/live_log', { limit: 50 })),
      withTimeout(api.get(props.api, '/webhook_events', { limit: 50 })),
      withTimeout(api.get(props.api, '/webhook/pending')),
    ])
    if (st.status === 'fulfilled' && st.value) status.value = st.value
    if (db.status === 'fulfilled' && db.value) dbStats.value = db.value
    if (lg.status === 'fulfilled' && Array.isArray(lg.value)) logs.value = lg.value
    if (wh.status === 'fulfilled' && Array.isArray(wh.value)) webhookEvents.value = wh.value
    if (pd.status === 'fulfilled' && pd.value) pendingInfo.value = pd.value
    loading.value = false
  } finally {
    loadAllBusy = false
  }
}

const pendingInfo = ref({ count: 0, items: [] })
const pendingBusy = ref(false)
const pendingCount = () => pendingInfo.value?.count ?? 0
async function pendingContinue() {
  if (pendingBusy.value) return
  pendingBusy.value = true
  try {
    const r = await api.post(props.api, '/webhook/pending_continue')
    notify(r?.message || '已处理', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '操作失败', 'error') } finally { pendingBusy.value = false }
}
const pendingClearBusy = ref(false)
async function pendingClear() {
  if (pendingClearBusy.value) return
  if (!await askConfirm({
    title: '放弃全部待配置事件',
    text: `确认放弃全部 ${pendingCount()} 个待配置（挂起）事件？`,
    detail: '放弃后这些事件不再自动处理（如需重新处理，再次入库触发即可）。',
    okText: '放弃',
    color: 'warning',
  })) return
  pendingClearBusy.value = true
  try {
    const r = await api.post(props.api, '/webhook/pending_clear')
    notify(r?.message || '已放弃', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '放弃失败', 'error') } finally { pendingClearBusy.value = false }
}

async function clearLogs() {
  if (!await askConfirm({
    title: '清空运行日志',
    text: '确认清空插件日志缓冲？',
    detail: '仅清空插件的日志显示（不影响已写回的 nfo 与翻译记录）；清空后无法恢复。',
    okText: '清空',
    color: 'warning',
  })) return
  try {
    const r = await api.post(props.api, '/clear_logs')
    notify(r?.message || '日志已清空', 'success')
    logs.value = []
  } catch (e) { notify((e && e.message) || '清空失败', 'error') }
}

async function clearWhEvents() {
  if (busy.value === 'wh_clear') return
  if (!await askConfirm({
    title: '清空 Webhook 入库事件',
    text: '确认清空全部 Webhook 入库事件记录？',
    detail: '事件列表用于查看入库/失败/「失效·待恢复」状态；清空后这些条目不再显示（翻译记录与已入库内容不受影响，需复查可重新触发入库）。',
    okText: '清空',
    color: 'error',
  })) return
  busy.value = 'wh_clear'
  try {
    const r = await api.post(props.api, '/webhook_events/clear')
    notify(r?.message || 'Webhook 入库事件已清空', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '清空失败', 'error') }
  finally { busy.value = '' }
}

async function runOp(action, successMsg) {
  if (busy.value) return
  busy.value = action
  try {
    const r = await api.post(props.api, '/' + action)
    notify(r?.message || successMsg, 'success')
    emit('action')
    await loadAll()
  } catch (e) {
    notify((e && e.message) || '操作失败', 'error')
  } finally {
    // 不用固定 30 秒计时器假装任务结束（UI-001）：busy 只覆盖「启动请求」本身，
    // 任务是否在跑由 /status 的 is_running + tasks 驱动按钮禁用态。
    busy.value = ''
    await loadAll()
  }
}

async function stopAll() {
  if (busy.value) return
  if (!await askConfirm({
    title: '终止当前任务',
    text: '终止后将立即中断正在运行的扫描 / 拉取人名 / AI 翻译 / 写回任务；已处理的进度与断点保留，之后可点「续跑」或重新发起。',
    detail: 'AI 翻译会立即停止（不再发起新请求）；已翻译入库的内容不受影响。',
    okText: '终止',
    color: 'error',
  })) return
  await runOp('stop', '已请求终止（断点已保存，完成后点「续跑」继续）')
}

async function pauseTasks() {
  try {
    const r = await api.post(props.api, '/task/pause', { target: 'all' })
    notify(r?.message || '已暂停', 'info')
    await loadAll()
  } catch (e) { notify((e && e.message) || '暂停失败', 'error') }
}
async function resumeTasks() {
  try {
    const r = await api.post(props.api, '/task/resume', { target: 'all' })
    notify(r?.message || '已继续', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '继续失败', 'error') }
}

const running = () => !!status.value?.is_running
const isNfoMode = () => true
const mainActionLabel = () => 'NFO 扫描'
const mainActionHint = () => '扫描已勾选媒体库目录下的本地 nfo 文件：采集入库 → 翻译 → 写回文件（有断点则跳过已处理继续扫，否则全量）。只管本地文件，不查 Emby 清单——查 Emby 用「探测库」'
const pluginEnabled = () => (status.value ? !!status.value.enabled : props.enabled !== false)
const whStatusColor = (s) => ({ done: 'success', failed: 'error', skipped: 'warning', waiting: 'info', missing: 'warning', ambiguous: 'warning', running: 'info', received: 'default' })[s] || 'default'
const whStatusLabel = (s) => ({ done: '完成', failed: '失败', skipped: '跳过', waiting: '待配置', missing: '待恢复', ambiguous: '需确认', running: '处理中', received: '已接收' })[s] || s

const normalEvents = computed(() => webhookEvents.value.filter(e => e.status !== 'missing'))
const missingEvents = computed(() => webhookEvents.value.filter(e => e.status === 'missing'))
const fmtGraceDate = (s) => { try { const m = /(\d{2}-\d{2} \d{2}:\d{2}) 到期/.exec(String(s || '')); return m ? m[1] : '' } catch (e) { return '' } }

const purgeMissingBusy = ref(false)
async function purgeMissing() {
  if (purgeMissingBusy.value || !missingEvents.value.length) return
  if (!await askConfirm({
    title: '立即清除全部失效记录',
    text: `确认立即清除全部失效记录（${missingEvents.value.length} 条）？这些条目的翻译记录将被删除（人名池保留），不再等待观察期。`,
    detail: '注意：若条目正在重新下载/洗版，清除后重新入库会当作全新条目重新翻译（重复消耗 AI 额度）。',
    okText: '清除',
    color: 'error',
  })) return
  purgeMissingBusy.value = true
  try {
    const r = await api.post(props.api, '/db/purge_missing')
    notify(r?.message || '已清除', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '清除失败', 'error') } finally { purgeMissingBusy.value = false }
}

const translateAllBusy = ref(false)
const nfoResume = computed(() => status.value?.nfo_resume || { ok: false, done: 0 })
const canResume = computed(() => !!nfoResume.value?.ok)
const translateAllHint = () => {
  if (!canResume.value) return '没有可续跑的断点（上轮已正常跑完，或配置变更使断点作废）—— 需要全量处理请点「NFO 扫描」；扫描中途点「终止」后，这里就能续跑'
  const p = !!status.value?.nfo_preview
  const n = nfoResume.value?.done || 0
  return p
    ? `继续上次未完成的扫描（已处理 ${n} 个文件）：预览模式已开，只翻译写入库，不写文件；确认后去「库」页点「全部写回」落盘`
    : `继续上次未完成的扫描（已处理 ${n} 个文件）：跳过已处理的，翻译并写回文件`
}
async function runTranslateAll() {
  if (busy.value || translateAllBusy.value) return
  translateAllBusy.value = true
  try {
    const r = await api.post(props.api, '/translate_all')
    notify(r?.message || '续跑已启动', r?.success === false ? 'error' : 'success')
    emit('action')
    await loadAll()
  } catch (e) { notify((e && e.message) || '启动失败', 'error') } finally { translateAllBusy.value = false }
}

const probeBusy = ref(false)
async function runProbeNow() {
  if (probeBusy.value) return
  probeBusy.value = true
  try {
    const r = await api.post(props.api, '/probe/run')
    notify(r?.message || '探测已启动', r?.success === false ? 'error' : 'success')
    emit('action')
    await loadAll()
  } catch (e) { notify((e && e.message) || '探测启动失败', 'error') } finally { probeBusy.value = false }
}

// 顶部状态灯：按真实任务逐项显示，不再把任何任务都写成「扫描中」（UI-003）
const TASK_LABELS = { scan: '扫描中', translate: '翻译中', writeback: '写回中', pool: '拉取人名中', probe: '探测库中' }
const activeTasks = computed(() => {
  const t = status.value?.tasks || {}
  return Object.keys(TASK_LABELS).filter(k => !!t[k])
})
const svc = computed(() => {
  const keys = activeTasks.value
  if (!keys.length) return { txt: '空闲', cls: 'idle' }
  return { txt: keys.map(k => TASK_LABELS[k]).join(' + '), cls: 'ok' }
})
const dbOk = computed(() => {
  const d = status.value?.deps
  return d?.db_ready !== undefined ? !!d.db_ready : dbStats.value !== null
})
const depOk = computed(() => deps.value.total > 0 && deps.value.ok_count === deps.value.total)
const whOk = computed(() => {
  const w = status.value?.webhook
  if (!w) return false
  return !w.last_error
})
const whEnabled = computed(() => !!status.value?.webhook?.enabled)
const whPending = computed(() => Number(status.value?.webhook?.pending_count || 0))
const whHeld = computed(() => {
  const w = status.value?.webhook
  if (!w) return 0
  return Number(w.held_count ?? (Number(w.pending_count || 0) + Number(w.scheduled_count || 0)))
})

const LLM_ERR_LABEL = {
  rate_limited: '限速',
  quota_exceeded: '配额不足',
  authentication_failed: '认证失败',
  context_length_exceeded: '上下文过长',
  server_error: '服务异常',
  network_error: '网络异常',
  empty_response: '空响应'
}
const llmGate = computed(() => status.value?.llm_gate || {})
const llmLimitedLeft = computed(() => {
  const _until = Number(llmGate.value.limited_until || 0)
  return _until > Date.now() / 1000 ? Math.ceil(_until - Date.now() / 1000) : 0
})
const llmTxt = computed(() => {
  if (llmLimitedLeft.value > 0) return `限速 ${llmLimitedLeft.value}s`
  const k = String(llmGate.value.error_kind || '')
  return LLM_ERR_LABEL[k] || '正常'
})
const llmCls = computed(() => {
  if (llmLimitedLeft.value > 0) return 'warn'
  const k = String(llmGate.value.error_kind || '')
  if (!k) return 'ok'
  // 可自愈/短暂类 → 警告色；需人工介入类 → 错误色
  if (['rate_limited', 'server_error', 'network_error', 'empty_response'].includes(k)) return 'warn'
  return 'bad'
})

const tx = computed(() => status.value?.tx || {})
const txOnline = computed(() => !!tx.value.online)
const txPaused = computed(() => String(tx.value.paused || ''))
const txUserPaused = computed(() => !!tx.value.user_paused)
const anyTaskPaused = computed(() => txUserPaused.value
  || !!scanStatus()?.paused || !!status.value?.pool_status?.paused)
const txState = computed(() => {
  if (!txOnline.value) return '离线'
  if (tx.value.user_paused) return '已暂停（手动）'
  if (txPaused.value === 'rate_limited') return '限流暂停'
  if (txPaused.value === 'authentication_failed') return '认证暂停'
  if (txPaused.value === 'quota_exceeded') return '配额暂停'
  return tx.value.requested ? '正在翻译' : '待命'
})
const txTxt = computed(() => (txOnline.value ? `在线 · ${txState.value}` : '离线'))
const txCls = computed(() => {
  if (!txOnline.value) return 'bad'
  if (['authentication_failed', 'quota_exceeded'].includes(txPaused.value)) return 'bad'
  if (txPaused.value === 'rate_limited') return 'warn'
  if (tx.value.user_paused) return 'warn'
  return tx.value.requested ? 'warn' : 'ok'
})
const txPauseLeft = computed(() => Number(tx.value.pause_left || 0))
const txPending = computed(() => Number(tx.value.pending || 0))
const txScope = computed(() => String(tx.value.scope || ''))
const txProgress = computed(() => {
  const tr = status.value?.translate_status || {}
  if (!tr.running) return ''
  const t = Number(tr.total || 0), dn = Number(tr.done || 0)
  return `${dn} / ${t || '…'}`
})

const stageRows = computed(() => {
  const out = []
  const sc = scanStatus()
  const scanRunning = sc.tasks ? !!sc.tasks.scan : !!sc.running
  if (scanRunning) {
    out.push({ key: 'scan', name: 'NFO 扫描', color: 'primary', percent: Number(sc.percent || 0),
               text: `${sc.done || 0} / ${sc.total || 0}${sc.current_title ? ' · ' + sc.current_title : ''}` })
  }
  const pf = status.value?.pool_status || {}
  if (pf.running) {
    const pt = Number(pf.total || 0), pdn = Number(pf.done || 0)
    out.push({ key: 'pool', name: '拉取人名', color: 'info', percent: pt ? Math.min(100, Math.round(pdn / pt * 100)) : 0,
               text: `${pdn} / ${pt || '…'}${pf.current ? ' · ' + pf.current : ''}` })
  }
  const tr = status.value?.translate_status || {}
  if (tr.running) {
    const t = Number(tr.total || 0), dn = Number(tr.done || 0)
    out.push({ key: 'translate', name: 'AI 翻译', color: 'deep-purple', percent: t ? Math.min(100, Math.round(dn / t * 100)) : 0,
               text: `${dn} / ${t || '…'}${tr.current ? ' · ' + tr.current : ''}` })
  }
  const wb = status.value?.writeback_status || {}
  if (wb.running) {
    const t = Number(wb.total || 0), dn = Number(wb.done || 0)
    out.push({ key: 'writeback', name: 'NFO 写回', color: 'teal', percent: t ? Math.min(100, Math.round(dn / t * 100)) : 0,
               text: `${dn} / ${t || '…'}${wb.current ? ' · ' + wb.current : ''}` })
  }
  return out
})

const poolCounts = computed(() => status.value?.pool_counts || {})
const poolFetchState = computed(() => status.value?.pool_status || {})
// 探测库独立状态（UI-004）：不再从 scan_status 借用，避免被显示为「扫描中」
const probeStatus = computed(() => status.value?.probe_status || {})
const poolTaskRunning = computed(() => !!(status.value?.tasks?.pool || poolFetchState.value.running))
const translateRunning = computed(() => !!(status.value?.tasks?.translate || status.value?.translate_status?.running))
const poolFetchDisabled = computed(() => poolTaskRunning.value || translateRunning.value || !pluginEnabled())
const poolFetchHint = computed(() => {
  if (!pluginEnabled()) return '插件未启用：请先在设置页打开「启用插件」'
  if (translateRunning.value) return 'AI 翻译进行中，暂不可拉取人名（翻译与拉取互斥），等翻译完成后再试'
  if (poolTaskRunning.value) return '人名池任务（拉取/同步）进行中，完成后可用'
  return ''
})
const dataOpBlocked = computed(() => !pluginEnabled() || running() || translateRunning.value)
const dataOpBlockedHint = computed(() => {
  if (!pluginEnabled()) return '插件未启用：请先在设置页打开「启用插件」'
  if (translateRunning.value || running()) return '任务正在运行中，请先「终止」或等待完成后再操作'
  return ''
})
const poolFetchBusy = ref(false)
function poolFetchLabel() {
  const st = poolFetchState.value
  if (st.running) return `拉取中 ${st.done || 0}/${st.total || '…'}`
  return '拉取人名'
}
async function startPoolFetch() {
  if (poolFetchBusy.value || poolFetchState.value.running) return
  poolFetchBusy.value = true
  try {
    const r = await api.post(props.api, '/pool/fetch', {})
    notify(r?.message || '拉取人名已启动', r?.success === false ? 'error' : 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '拉取启动失败', 'error') } finally { poolFetchBusy.value = false }
}

const failedTerms = computed(() => status.value?.failed_translations?.terms || [])
const failedDetail = (t) => status.value?.failed_translations?.detail?.[t] || '翻译失败'
const failedBusy = ref('')
async function retryFailed() {
  if (failedBusy.value) return
  failedBusy.value = 'retry'
  try {
    const r = await api.post(props.api, '/translate/retry_failed')
    notify(r?.message || '重试已启动', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '重试失败', 'error') } finally { failedBusy.value = '' }
}
async function clearFailed() {
  if (failedBusy.value) return
  if (!await askConfirm({
    title: '清空失败清单',
    text: `确认清空失败清单（${failedTerms.value.length} 个词条）？`,
    detail: '清空后这些词条不再出现在「翻译失败词条」里，不会自动重试（下次扫描会重新尝试翻译）。',
    okText: '清空',
    color: 'error',
  })) return
  failedBusy.value = 'clear'
  try {
    const r = await api.post(props.api, '/translate/clear_failed')
    notify(r?.message || '已清空', 'success')
    await loadAll()
  } catch (e) { notify((e && e.message) || '清空失败', 'error') } finally { failedBusy.value = '' }
}

let pollTimer = null
function startPoll() {
  if (pollTimer) return
  // 递归定时（UI-002）：上一轮 loadAll 完成后才安排下一轮，慢接口不会造成请求堆积
  const tick = async () => {
    await loadAll()
    if (pollTimer) pollTimer = setTimeout(tick, 5000)
  }
  pollTimer = setTimeout(tick, 0)
}
function stopPoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
}
// v4.6.66（P1 仪表盘刷新）：页面重新激活 / 切页操作（refreshKey 递增）/ 窗口回到前台
// 时立即强制刷新一次，并解除上一轮遗留的轮询锁 —— 修复「Webhook 开关改了、仪表盘提示
// 必须进出插件才消失」。
function forceRefresh() {
  loadAllBusy = false
  loadAll()
}
watch(() => props.refreshKey, () => forceRefresh())
function onWindowVisible() {
  if (typeof document === 'undefined' || document.visibilityState === 'visible') forceRefresh()
}
onMounted(() => {
  loadDeps()
  startPoll()
  try {
    document.addEventListener('visibilitychange', onWindowVisible)
    window.addEventListener('focus', onWindowVisible)
  } catch (e) { /* 非浏览器环境忽略 */ }
})
onActivated(() => { forceRefresh(); startPoll() })
onDeactivated(stopPoll)
onUnmounted(() => {
  stopPoll()
  try {
    document.removeEventListener('visibilitychange', onWindowVisible)
    window.removeEventListener('focus', onWindowVisible)
  } catch (e) { /* ignore */ }
})
</script>

<template>
  <div class="epl-view">
    <!-- 顶部状态灯：服务 / 数据库 / 依赖（点击看明细）/ Webhook -->
    <v-card variant="tonal" class="mb-4 epl-statusbar">
      <v-card-text class="py-2 epl-statusrow">
        <div class="epl-st">
          <span class="epl-dot" :class="svc.cls"></span>
          <span class="epl-st-name">服务</span>
          <span class="epl-st-val" :class="svc.cls">{{ svc.txt }}</span>
        </div>
        <div class="epl-st">
          <span class="epl-dot" :class="dbOk ? 'ok' : 'bad'"></span>
          <span class="epl-st-name">数据库</span>
          <span class="epl-st-val" :class="dbOk ? 'ok' : 'bad'">{{ dbOk ? '正常' : '异常' }}</span>
        </div>
        <div class="epl-st epl-st-deps" :class="depOk ? '' : 'text-error'" @click="depsDialog = true">
          <span class="epl-dot" :class="depOk ? 'ok' : 'bad'"></span>
          <span class="epl-st-name">依赖</span>
          <span class="epl-st-val" :class="depOk ? 'ok' : 'bad'">{{ depsLoading ? '检测中…' : (depOk ? '正常' : '异常') }}</span>
          <v-icon size="14">{{ depsLoading ? 'mdi-loading mdi-spin' : 'mdi-dots-horizontal' }}</v-icon>
        </div>
        <div class="epl-st">
          <span class="epl-dot" :class="!whEnabled ? 'idle' : (whOk ? 'ok' : 'bad')"></span>
          <span class="epl-st-name">Webhook</span>
          <span class="epl-st-val" :class="!whEnabled ? 'idle' : (whOk ? 'ok' : 'bad')">{{ whEnabled ? '● 已开启' : '○ 已关闭' }}</span>
          <span v-if="whEnabled && !whOk" class="epl-st-sub text-error">异常</span>
          <span v-else-if="whEnabled && whPending > 0" class="epl-st-sub">待配置 {{ whPending }}</span>
        </div>
        <div class="epl-st">
          <span class="epl-dot" :class="llmCls"></span>
          <span class="epl-st-name">LLM</span>
          <span class="epl-st-val" :class="llmCls">{{ llmTxt }}</span>
        </div>
        <div class="epl-st">
          <span class="epl-dot" :class="txCls"></span>
          <span class="epl-st-name">AI 翻译 Worker</span>
          <span class="epl-st-val" :class="txCls">{{ txTxt }}</span>
          <span v-if="txPaused && txPauseLeft > 0" class="epl-st-sub">剩余约 {{ Math.ceil(txPauseLeft / 60) }} 分钟</span>
          <span v-else-if="txOnline && tx.requested && txScope" class="epl-st-sub">目标 {{ txScope }}<template v-if="txProgress"> · {{ txProgress }}</template></span>
          <span v-else class="epl-st-sub">待翻译 {{ txPending }}</span>
        </div>
        <span v-if="poolFetchState.running" class="epl-st-progress">
          <v-icon size="15">mdi-account-arrow-down-outline</v-icon>拉取人名 {{ poolFetchState.done || 0 }}/{{ poolFetchState.total || '…' }}
        </span>
        <span v-else-if="probeStatus.running" class="epl-st-progress">
          <v-icon size="15">mdi-magnify-scan</v-icon>{{ probeStatus.current_title || '探测库中…' }}
        </span>
        <span v-else-if="scanStatus().current_title" class="epl-st-progress">
          <v-icon size="15">mdi-progress-clock</v-icon>{{ scanStatus().current_title }}
          <template v-if="scanStatus().total">（{{ scanStatus().done }}/{{ scanStatus().total }} · {{ scanStatus().percent }}%）</template>
        </span>
      </v-card-text>
    </v-card>

    <v-alert v-if="!loading && !whEnabled" type="warning" variant="tonal" density="compact" class="mb-4 epl-wh-off-alert">
      <div class="d-flex align-center flex-wrap ga-2" style="font-size:13px">
        <span>Webhook 已关闭：新入库事件不会接收。NFO 扫描 / 探测库仍可发现新条目。</span>
        <span v-if="whHeld > 0">已有挂起事件：{{ whHeld }}（关闭期间冻结不丢失，重新开启后自动续跑）。</span>
        <v-btn v-if="pendingCount() > 0" size="small" color="warning" variant="flat" :loading="pendingBusy" @click="pendingContinue">
          <v-icon start size="16">mdi-play</v-icon>继续处理待配置事件
        </v-btn>
      </div>
    </v-alert>

    <!-- 依赖明细弹窗 -->
    <v-dialog v-model="depsDialog" max-width="460">
      <v-card>
        <v-card-title class="epl-card-title">
          <v-icon start size="18">mdi-package-variant-closed</v-icon>
          运行依赖
          <v-spacer></v-spacer>
          <v-btn size="small" variant="tonal" :loading="depsLoading" @click="loadDeps">
            <v-icon start size="14">mdi-refresh</v-icon>
            重新检测
          </v-btn>
        </v-card-title>
        <v-card-text class="pt-0">
          <div v-if="!deps.items.length" class="epl-empty pa-4">暂未检测</div>
          <v-list v-else density="compact" lines="two" class="pa-0">
            <v-list-item v-for="d in deps.items" :key="d.key">
              <template #prepend>
                <v-icon :color="d.ok ? 'success' : 'error'" size="20">{{ d.ok ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
              </template>
              <v-list-item-title>
                {{ d.name }}
                <v-chip :color="d.ok ? 'success' : 'error'" size="x-small" variant="tonal" class="ml-1">
                  {{ d.ok ? '正常' : '未安装' }}
                </v-chip>
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ d.ok ? d.detail : d.detail + '（' + d.impact + '）' }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
          <div class="epl-deps-hint text-body-2">
            依赖由 MoviePilot 安装插件时按 requirements.txt 自动安装；缺失时功能降级（见各项说明）。
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 运行操作 -->
    <v-card variant="tonal" class="mb-4 epl-opcard">
      <v-card-text class="d-flex align-center flex-wrap ga-2">
        <span class="text-body-2 font-weight-medium mr-2"><v-icon start size="18">mdi-play-box-outline</v-icon>运行操作</span>
        <v-tooltip :text="pluginEnabled() ? mainActionHint() : '插件未启用：请先在设置页打开「启用插件」'" location="top" max-width="320">
          <template #activator="{ props: tp }">
            <v-btn size="small" color="primary" variant="tonal" :disabled="running() || !pluginEnabled()" :loading="busy==='scan'" v-bind="tp" @click="runOp('scan', 'NFO 扫描已启动')">
              <v-icon start size="18">mdi-file-document-check-outline</v-icon>{{ mainActionLabel() }}
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip :text="pluginEnabled() ? translateAllHint() : '插件未启用'" location="top" max-width="320">
          <template #activator="{ props: tp }">
            <v-btn size="small" color="success" variant="tonal" :disabled="running() || !pluginEnabled() || !canResume" :loading="translateAllBusy" v-bind="tp" @click="runTranslateAll">
              <v-icon start size="18">mdi-play-circle-outline</v-icon>续跑
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip location="top" max-width="300" text="立即跑一轮探测库：Emby 缺的集/新条目补翻；Emby 已删的集标「待恢复」（有任务在跑会跳过）">
          <template #activator="{ props: tp }">
            <v-btn size="small" color="info" variant="tonal" :disabled="running() || !pluginEnabled()" :loading="probeBusy" v-bind="tp" @click="runProbeNow">
              <v-icon start size="18">mdi-radar</v-icon>探测库
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip location="top" max-width="300" :text="poolFetchHint || '把 Emby 的 Person 拉进人名池（翻译一次全局复用）：按设置页「翻译范围」的人名类型开关拉取；拉取期间入库事件自动排队'">
          <template #activator="{ props: tp }">
            <v-btn size="small" color="info" variant="flat" :disabled="poolFetchDisabled" :loading="poolFetchBusy" v-bind="tp" @click="startPoolFetch">
              <v-icon start size="18">mdi-account-arrow-down-outline</v-icon>{{ poolFetchLabel() }}
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip v-if="!anyTaskPaused" location="top" max-width="300"
                   text="暂停正在运行的任务（扫描 / 拉取人名 / AI 翻译）：进度与词条都保留；翻译会等当前一批完成后停，点「继续」接着跑">
          <template #activator="{ props: tp }">
            <v-btn size="small" color="warning" variant="tonal" v-bind="tp"
                   :disabled="(!running() && !tx.requested) || !pluginEnabled()" @click="pauseTasks">
              <v-icon start size="18">mdi-pause</v-icon>暂停
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip v-else location="top" max-width="300"
                   :text="pluginEnabled() ? '继续之前暂停的任务（扫描 / 拉取人名 / AI 翻译）' : '插件未启用：请先在设置页打开「启用插件」'">
          <template #activator="{ props: tp }">
            <v-btn size="small" color="success" variant="flat" :disabled="!pluginEnabled()" v-bind="tp" @click="resumeTasks">
              <v-icon start size="18">mdi-play</v-icon>继续
            </v-btn>
          </template>
        </v-tooltip>
        <v-btn size="small" color="error" variant="tonal" :disabled="!running() && !tx.requested" :loading="busy==='stop'" @click="stopAll">
          <v-icon start size="18">mdi-stop</v-icon>终止
        </v-btn>
        <v-chip v-if="!pluginEnabled()" size="small" color="warning" variant="tonal">
          <v-icon start size="14">mdi-alert-outline</v-icon>插件未启用，操作已锁定
        </v-chip>
      </v-card-text>
    </v-card>

    <v-progress-circular v-if="loading" indeterminate color="primary" class="epl-center"></v-progress-circular>
    <template v-else>
      <v-card variant="tonal" class="mb-4 epl-stagecard">
        <v-card-text class="py-2">
          <template v-if="stageRows.length">
            <div v-for="s in stageRows" :key="s.key" class="epl-stage-row">
              <span class="epl-stage-name">{{ s.name }}</span>
              <v-progress-linear :model-value="s.percent" :color="s.color" height="8" rounded
                                 :indeterminate="!s.percent" class="epl-stage-bar"></v-progress-linear>
              <span class="epl-stage-num">{{ s.text }}</span>
            </div>
          </template>
          <div v-else class="epl-stage-idle">
            <v-icon size="15">mdi-circle-slice-8</v-icon>
            当前没有运行中的阶段任务（扫描 → 翻译 → 写回 自动衔接；终止互不影响）
          </div>
        </v-card-text>
      </v-card>

      <!-- 统计卡片：4 张（v3.4.49: NFO 用户视角——库条目/人物/命中率/Webhook，窄屏 2x2 不裁切）
           「库中人物」改为「人名池」（池人数 + 待翻/待同步，纯展示不可点） -->
      <v-row>
        <v-col cols="6" sm="6" md="3">
          <v-card class="epl-card-bg epl-stat-card" height="100%">
            <v-card-text class="text-center pa-4">
              <div class="epl-stat-value text-primary">{{ dbStats?.item_count ?? 0 }}</div>
              <div class="epl-stat-label">库中条目</div>
              <div class="epl-stat-sub">已采集入库的作品数</div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="6" sm="6" md="3">
          <v-card class="epl-card-bg epl-stat-card" height="100%">
            <v-card-text class="text-center pa-4">
              <div class="epl-stat-value text-info">{{ status?.pool_hit_rate ?? 0 }}%</div>
              <div class="epl-stat-label">池命中率</div>
              <div class="epl-stat-sub">池/繁简命中不调 AI 的比例</div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="6" sm="6" md="3">
          <v-card class="epl-card-bg epl-stat-card" height="100%">
            <v-card-text class="text-center pa-4">
              <div class="epl-stat-value text-success">{{ poolCounts.total ?? 0 }}</div>
              <div class="epl-stat-label">人名池</div>
              <div class="epl-stat-sub">待翻 {{ poolCounts.pending ?? 0 }} · 待同步 {{ poolCounts.translated ?? 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="6" sm="6" md="3">
          <v-card class="epl-card-bg epl-stat-card" height="100%">
            <v-card-text class="text-center pa-4">
              <div class="epl-stat-value text-warning">{{ status?.webhook?.processed ?? 0 }}</div>
              <div class="epl-stat-label">Webhook 已处理</div>
              <div class="epl-stat-sub">入库事件自动翻译计数</div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-card v-if="failedTerms.length" class="epl-card-bg mt-4 epl-failed-card">
        <v-card-title class="epl-card-title">
          <v-icon start size="18" color="error">mdi-alert-circle-outline</v-icon>
          翻译失败词条
          <v-chip size="x-small" color="error" variant="tonal" class="ml-2">{{ failedTerms.length }}</v-chip>
          <v-spacer></v-spacer>
          <v-btn size="small" variant="tonal" color="warning" :loading="failedBusy==='retry'" @click="retryFailed">
            <v-icon start size="16">mdi-refresh</v-icon>重试失败项
          </v-btn>
          <v-btn size="small" variant="tonal" color="error" :disabled="dataOpBlocked" :title="dataOpBlockedHint" :loading="failedBusy==='clear'" @click="clearFailed">
            <v-icon start size="16">mdi-delete-outline</v-icon>清空
          </v-btn>
        </v-card-title>
        <v-card-text class="pt-0">
          <div class="epl-wh-scroll epl-failed-scroll">
            <v-list density="compact" class="pa-0">
              <v-list-item v-for="t in failedTerms" :key="t" class="epl-failed-item">
                <v-list-item-title class="epl-failed-term">{{ t }}</v-list-item-title>
                <v-list-item-subtitle class="epl-failed-reason">{{ failedDetail(t) }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </div>
        </v-card-text>
      </v-card>

      <!-- 实时日志（参考 zitifenlei 表格样式 + 刷新/清空） -->
      <v-card class="epl-card-bg mt-4 epl-log-card">
        <v-card-title class="epl-card-title">
          <v-icon start size="18">mdi-text-box-outline</v-icon>
          实时日志
          <v-spacer></v-spacer>
          <v-btn size="small" variant="text" @click="loadAll" title="刷新"><v-icon size="16">mdi-refresh</v-icon></v-btn>
          <v-btn size="small" variant="text" color="error" @click="clearLogs" title="清空日志">
            <v-icon size="16">mdi-delete-outline</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text class="pt-0 epl-scroll-body">
          <div v-if="!logs.length" class="epl-empty">
            <div>暂无日志</div>
            <div class="text-caption" style="opacity:.65">启动/扫描/保存配置等操作后会在此滚动显示</div>
          </div>
          <v-table v-else density="compact" class="epl-logtable">
            <tbody>
              <tr v-for="l in logs" :key="'log-' + l.time + '-' + (l.level || '') + '-' + String(l.msg || l.message || '').slice(0, 60)">
                <td class="epl-log-time">{{ fmtTime(l.time) }}</td>
                <td>
                  <v-chip size="x-small" :color="l.level === 'error' ? 'error' : l.level === 'warning' ? 'warning' : 'info'"
                          variant="tonal" class="mr-2">{{ (l.level || 'info').toUpperCase() }}</v-chip>
                  <span class="epl-log-msg">{{ l.msg || l.message || '' }}</span>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>

      <!-- Webhook 最近事件（v3.4.27: 列表滚动显示剧名/集/处理状态；v3.4.41: 按钮样式与实时日志卡对齐） -->
      <v-card class="epl-card-bg mt-4 epl-wh-card">
        <v-card-title class="epl-card-title">
          <v-icon start size="18">mdi-webhook</v-icon>Webhook 最近事件
          <v-chip v-if="pendingCount() > 0" size="x-small" color="warning" variant="tonal" class="ml-2">
            <v-icon start size="13">mdi-pause-circle-outline</v-icon>待配置 {{ pendingCount() }}
          </v-chip>
          <v-chip v-if="status?.webhook" size="x-small" variant="tonal" class="ml-2">
            收 {{ status.webhook.total_received ?? 0 }} / 成 {{ status.webhook.processed ?? 0 }} / 败 {{ status.webhook.failed ?? 0 }}
          </v-chip>
          <v-chip v-if="status?.webhook?.last_error" size="x-small" color="error" variant="tonal" class="ml-1">
            {{ String(status.webhook.last_error).slice(0, 40) }}
          </v-chip>
          <v-spacer></v-spacer>
          <v-btn size="small" variant="text" @click="loadAll" title="刷新"><v-icon size="16">mdi-refresh</v-icon></v-btn>
          <v-btn size="small" variant="text" color="error" :disabled="dataOpBlocked" :title="dataOpBlockedHint || '清空事件'" @click="clearWhEvents" :loading="busy==='wh_clear'">
            <v-icon size="16">mdi-delete-outline</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text class="pa-0 epl-wh-body">
          <v-alert v-if="pendingCount() > 0" type="warning" variant="tonal" density="compact" class="ma-2 mb-0">
            <div class="d-flex align-center flex-wrap ga-2" style="font-size:13px">
              <span>有 {{ pendingCount() }} 个入库事件因目录映射不命中而挂起（待配置）。请到设置页确认已选择该媒体库（必要时调整「路径前缀替换」）后，再点「继续处理」自动翻译；不想处理可点「放弃全部」。</span>
              <v-btn size="small" color="warning" variant="flat" :loading="pendingBusy" @click="pendingContinue">
                <v-icon start size="16">mdi-play</v-icon>继续处理
              </v-btn>
              <v-btn size="small" color="error" variant="tonal" :disabled="dataOpBlocked" :title="dataOpBlockedHint" :loading="pendingClearBusy" @click="pendingClear">
                <v-icon start size="16">mdi-delete-sweep-outline</v-icon>放弃全部
              </v-btn>
            </div>
          </v-alert>
          <v-row no-gutters class="epl-wh-cols">
            <v-col cols="12" sm="6" class="epl-wh-col">
              <div class="epl-wh-col-title">
                <v-icon size="15" class="mr-1">mdi-webhook</v-icon>入库事件
                <v-chip size="x-small" variant="tonal" class="ml-1">{{ normalEvents.length }}</v-chip>
              </div>
              <div class="epl-wh-scroll">
                <div v-if="!normalEvents.length" class="epl-empty pa-4">
                  <div>暂无入库事件</div>
                  <div class="text-caption" style="opacity:.65">Emby 有入库事件后这里会显示处理结果</div>
                </div>
                <v-table v-else density="compact" class="epl-logtable">
                  <tbody>
                    <tr v-for="e in normalEvents" :key="'ev-' + e.time + '-' + (e.item_id || '') + '-' + (e.status || '')">
                      <td class="epl-log-time">{{ e.time }}</td>
                      <td>
                        <div class="epl-wh-name" :title="e.series_name || e.name || e.item_id">{{ e.series_name || e.name || e.item_id }}</div>
                        <div class="text-caption" style="opacity:.7">
                          <template v-if="e.episode != null">S{{ e.season }}E{{ e.episode }} · </template>
                          <v-chip size="x-small" :color="whStatusColor(e.status)" variant="tonal">{{ whStatusLabel(e.status) }}</v-chip>
                        </div>
                        <div class="epl-log-msg">{{ e.msg }}</div>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
              </div>
            </v-col>
            <v-divider vertical class="epl-wh-divider" style="opacity:.25"></v-divider>
            <v-col cols="12" sm="6" class="epl-wh-col">
              <div class="epl-wh-col-title">
                <v-icon size="15" class="mr-1">mdi-progress-clock</v-icon>失效 / 待恢复
                <v-chip size="x-small" color="warning" variant="tonal" class="ml-1">{{ missingEvents.length }}</v-chip>
                <v-spacer></v-spacer>
                <v-btn v-if="missingEvents.length" size="x-small" variant="text" color="error" :disabled="dataOpBlocked" :title="dataOpBlockedHint || '清除全部失效记录（立即判定为真删除）'" :loading="purgeMissingBusy" @click="purgeMissing">
                  <v-icon size="15">mdi-delete-sweep-outline</v-icon>清除
                </v-btn>
              </div>
              <div class="epl-wh-scroll">
                <div v-if="!missingEvents.length" class="epl-empty pa-4">
                  <div>暂无失效记录</div>
                  <div class="text-caption" style="opacity:.65">nfo 目录消失后会出现在这里（观察期，到期自动检查）</div>
                </div>
                <v-list v-else density="compact" class="pa-0" nav>
                  <v-list-item v-for="e in missingEvents" :key="'ms-' + e.time + '-' + (e.item_id || '')" class="epl-wh-missing-item">
                    <v-list-item-title class="epl-wh-name">
                      {{ e.series_name || e.name || e.item_id }}
                    </v-list-item-title>
                    <v-list-item-subtitle class="epl-log-msg">
                      <template v-if="fmtGraceDate(e.msg)"><v-chip size="x-small" color="warning" variant="tonal" class="mr-1">到期 {{ fmtGraceDate(e.msg) }}</v-chip></template>
                      {{ e.msg }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </template>

    <ConfirmDlg :state="cState" :on-ok="cOk" :on-cancel="cCancel" />
  </div>
</template>

<style scoped>
.epl-view { width: 100%; }
.epl-statusbar { border: 1px solid rgba(128,128,128,0.16); }
.epl-statusrow { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; }
.epl-st { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
.epl-st-deps { cursor: pointer; }
.epl-st-deps:hover { opacity: 0.85; }
.epl-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.epl-dot.ok { background: #4caf50; box-shadow: 0 0 6px #4caf50; }
.epl-dot.bad { background: #f44336; box-shadow: 0 0 6px #f44336; }
.epl-dot.warn { background: #ff9800; box-shadow: 0 0 6px #ff9800; }
.epl-dot.idle { background: #9e9e9e; }
.epl-st-name { opacity: 0.75; }
.epl-st-val { font-weight: 600; }
.epl-st-val.ok { color: #4caf50; }
.epl-st-val.bad { color: #f44336; }
.epl-st-val.warn { color: #ff9800; }
.epl-st-val.idle { color: #9e9e9e; }
.epl-st-sub { opacity: 0.6; font-size: 12px; }
.epl-st-progress { margin-left: auto; font-size: 13px; color: var(--v-primary-base); }
.epl-deps-hint { opacity: 0.6; font-size: 12px; margin-top: 8px; padding: 8px; border-top: 1px solid rgba(255,255,255,0.08); }
.epl-card-bg { background: rgba(255,255,255,0.05) !important; border: 1px solid rgba(255,255,255,0.08) !important; }
.epl-opcard { border: 1px solid rgba(128,128,128,0.16); }
.epl-stat-value { font-size: clamp(20px, 6vw, 28px); font-weight: 700; line-height: 1.2; word-break: break-word; }
.epl-stat-label { font-size: 13px; opacity: 0.75; margin-top: 4px; }
.epl-stat-sub { font-size: 11.5px; opacity: 0.55; margin-top: 2px; }
.epl-stagecard { border: 1px solid rgba(128,128,128,0.16); }
.epl-stage-row { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.epl-stage-name { flex: 0 0 84px; font-size: 13px; opacity: 0.85; }
.epl-stage-bar { flex: 1 1 auto; min-width: 80px; }
.epl-stage-num { flex: 0 0 auto; font-size: 12.5px; opacity: 0.75; max-width: 46%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.epl-stage-idle { display: flex; align-items: center; gap: 6px; font-size: 12.5px; opacity: 0.6; }
.epl-card-title { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; row-gap: 4px; white-space: normal; }
.epl-card-title .v-chip, .epl-card-title .v-btn { flex-shrink: 0; }
.epl-log-card { height: 320px; display: flex; flex-direction: column; }
.epl-wh-card { display: flex; flex-direction: column; }
.epl-wh-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.epl-wh-cols { flex: 1; min-height: 0; }
.epl-wh-col { display: flex; flex-direction: column; min-height: 0; }
.epl-wh-scroll {
  height: 340px; overflow-y: scroll; overflow-x: hidden;
  scrollbar-width: thin; scrollbar-color: rgba(150,150,150,.65) rgba(255,255,255,.08);
}
.epl-wh-scroll::-webkit-scrollbar { width: 10px; }
.epl-wh-scroll::-webkit-scrollbar-track { background: rgba(255,255,255,.07); border-radius: 6px; }
.epl-wh-scroll::-webkit-scrollbar-thumb {
  background: rgba(150,150,150,.6); border-radius: 6px;
  border: 2px solid transparent; background-clip: content-box;
}
.epl-wh-scroll::-webkit-scrollbar-thumb:hover { background: rgba(215,215,215,.85); background-clip: content-box; }
.epl-failed-scroll { height: 220px; padding-right: 8px; }
.epl-wh-col-title { padding: 6px 12px; font-size: 13px; font-weight: 600; display: flex; align-items: center; border-bottom: 1px solid rgba(255,255,255,.06); flex-shrink: 0; }
.epl-wh-divider { align-self: stretch; }
.epl-wh-name { font-size: 13px; font-weight: 500; white-space: normal; word-break: break-word; line-height: 1.3; }
.epl-scroll-body { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; }
.epl-logtable { background: transparent !important; }
.epl-logtable :deep(tbody tr) { border-bottom: 1px solid rgba(255,255,255,0.05); }
.epl-log-time { width: 150px; white-space: nowrap; font-size: 12px; opacity: 0.75; }
.epl-log-msg { font-size: 13px; opacity: 0.9; white-space: pre-wrap; word-break: break-all; }
.epl-empty { font-size: 13px; opacity: 0.6; text-align: center; padding: 16px 0; }
.epl-center { display: block; margin: 40px auto; }
@media (max-width: 600px) {
  .epl-stage-row { flex-wrap: wrap; gap: 4px 8px; }
  .epl-stage-name { flex: 1 1 auto; }
  .epl-stage-num { flex: 0 1 auto; max-width: 62%; }
  .epl-stage-bar { flex: 1 1 100%; }
  .epl-log-card { height: 260px; }
  .epl-statusrow { gap: 12px; }
  .epl-st-progress { margin-left: 0; width: 100%; }
  .epl-card-title { gap: 6px 8px; }
  .epl-card-title > .v-spacer { display: none; }
}
</style>
