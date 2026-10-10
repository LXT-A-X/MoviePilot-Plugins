<script setup>
import { computed, onMounted, ref } from 'vue'
import { inject } from 'vue'
import api from '../api/client.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  initialConfig: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['save', 'notify', 'action'])
const toast = inject('moviepilot:toast', null)

const DEFAULT = {
  enabled: false,
  enable_ai: true,
  lock_cast: false,
  emby_name_sync: true,
  emby_role_sync: false,
  translate_actor: true,
  translate_director: false,
  translate_writer: false,
  translate_producer: false,
  translate_guest_star: false,     // 客串/配角
  translate_all: false,
  translate_role: true,
  ja_name_policy: 'convert',       // 已合并进演员（固定自动判断），保留键兼容旧配置
  overwrite_chinese: false,
  notify_on_complete: false,
  use_proxy: false,                // 仅插件 LLM 配置时显示
  max_people_per_batch: 30,
  max_guest_per_episode: 5,
  actor_limit: 10,
  guest_limit: 10,
  director_limit: 3,
  writer_limit: 3,
  movie_actor_limit: 10,        // 电影 nfo 演员人数
  movie_guest_limit: 10,        // 电影 nfo 客串/配角人数
  movie_director_limit: 3,      // 电影 nfo 导演人数
  movie_writer_limit: 3,        // 电影 nfo 编剧/制片人人数
  tv_actor_limit: 10,           // 剧 tvshow.nfo 主演人数
  ep_actor_limit: 10,           // 各集 episode.nfo 演员人数
  tv_guest_limit: 10,           // 剧/集 客串/配角人数
  tv_director_limit: 3,         // 剧/集 导演人数
  tv_writer_limit: 3,           // 剧/集 编剧/制片人人数
  schedule_enabled: false,
  schedule_interval_hours: 24,
  probe_enabled: false,
  probe_interval_minutes: 60,
  webhook_delay: 60,
  series_ingest_all: false,   // 整剧全收（含旧集）；默认关 = 只收本次新增的集
  llm_mode: 'system',       // LLM 来源：system=系统配置 / plugin=插件配置
  llm_base_url: '',
  llm_api_key: '',
  has_api_key: false,          // 后端只下发「是否已配置」+ 掩码（SEC-001）
  llm_api_key_masked: '',
  llm_model: '',
  llm_timeout: 120,
  llm_verify_ssl: true,
  translate_batching: 'per_title',
  prompt_template: '',   // AI 翻译引导词，留空用内置默认
  scan_mode: 'nfo',      // 翻译模式 api / nfo
  nfo_roots: '',
  nfo_recursive: true,
  nfo_include_episodes: false,
  nfo_backup: true,       // 写回前自动 .bak 备份（可关闭开关）
  nfo_episode_overwrite: false,   // NFO 剧→集同步（覆盖语义），与 sync_direction=s2e 搭配
  sync_direction: 's2e',
  nfo_preview: false,     // 预览模式：扫描只采集入库原文，不翻译；翻译由库页「全部翻译」触发
  nfo_dead_grace_hours: 24,
  libraries: [],
  pool_fetch_scope: 'libraries',
  pool_fetch_types: ['Actor'],   // 人名池「拉取类型」独立配置（Actor 勾选即含 VoiceActor）
  pool_translation_enabled: true,
  pool_auto_translate: false,
  pool_auto_sync: false,
  pool_keep_unknown: true,
  pool_tmdb_fill: true,
  pool_tmdb_credits: false,
  auto_translate_webhook: false,
  auto_translate_scan: false,
  webhook_enabled: false,
  translate_person: true,
  nfo_path_mappings: [],
  auto_writeback: true,
  llm_min_interval: 3.0,
  llm_tpm_budget: 0,
  llm_thinking_off: true,
  llm_thinking_params: '',
}
const llmModes = [
  { text: '系统配置（MoviePilot 全局）', value: 'system' },
  { text: '插件配置（单独填写）', value: 'plugin' },
]
const config = ref({ ...DEFAULT, ...(props.initialConfig || {}) })
const saving = ref(false)
const aiOn = computed(() => !!config.value.enable_ai)
// SEC-001：API Key 不回显原值 —— 留空 = 保持不变；清除需显式标记
const clearApiKeyFlag = ref(false)
const apiKeyPlaceholder = computed(() => {
  if (clearApiKeyFlag.value) return '保存后清除该 Key（当前留空）'
  return config.value.has_api_key
    ? `已配置：${config.value.llm_api_key_masked || '****'}（留空 = 保持不变）`
    : '未配置'
})
function clearApiKey() {
  config.value.llm_api_key = ''
  clearApiKeyFlag.value = true
}

const libs = ref([])
const libBusy = ref(false)
const libError = ref('')
const checkAllBusy = ref(false)
const pathCheck = ref({})   // key = `${server_id}:${lib_id}` → 预检结果（/nfo/path/check）

function mappingOf(serverId) {
  const arr = config.value.nfo_path_mappings
  if (!Array.isArray(arr)) return null
  return arr.find(m => m && m.server_id === serverId) || null
}
function setMapping(serverId, key, val) {
  const arr = Array.isArray(config.value.nfo_path_mappings) ? [...config.value.nfo_path_mappings] : []
  let m = arr.find(x => x && x.server_id === serverId)
  if (!m) { m = { server_id: serverId, from: '', to: '' }; arr.push(m) }
  m[key] = val == null ? '' : val
  config.value.nfo_path_mappings = arr
}
function clearMapping(serverId) {
  const arr = (config.value.nfo_path_mappings || []).filter(m => !(m && m.server_id === serverId))
  config.value.nfo_path_mappings = arr
}
const libGroups = computed(() => {
  const groups = []
  const byId = {}
  for (const l of (libs.value || [])) {
    const sid = l.server_id || l.skey || ''
    if (!byId[sid]) { byId[sid] = { server_id: sid, server_name: l.server_name || sid || 'Emby', libs: [], mappingFrom: '', mappingTo: '' }; groups.push(byId[sid]) }
    byId[sid].libs.push(l)
  }
  for (const g of groups) {
    const m = mappingOf(g.server_id)
    g.mappingFrom = (m && m.from) || ''
    g.mappingTo = (m && m.to) || ''
  }
  return groups
})
function isLibSelected(fullKey) { return (config.value.libraries || []).includes(fullKey) }
function toggleLib(fullKey, v) {
  const cur = Array.isArray(config.value.libraries) ? [...config.value.libraries] : []
  const i = cur.indexOf(fullKey)
  if (v && i < 0) cur.push(fullKey)
  else if (!v && i >= 0) cur.splice(i, 1)
  config.value.libraries = cur
}
const libOpen = ref({})
function isLibOpen(l) { return !!libOpen.value[String(l.full_key || l.lib_id || '')] }
function toggleLibOpen(l) {
  const k = String(l.full_key || l.lib_id || '')
  libOpen.value = { ...libOpen.value, [k]: !libOpen.value[k] }
}
function checkOf(l) { return pathCheck.value[`${l.server_id}:${l.lib_id}`] }
function libOk(l) {
  const c = checkOf(l)
  if (c && !c.loading && Object.prototype.hasOwnProperty.call(c, 'exists')) return !!(c.exists && c.is_dir && c.readable)
  return !!(l.path_exists && l.path_readable && l.path_is_dir)
}
function libStatusText(l) {
  const c = checkOf(l)
  if (c && c.loading) return '检测中…'
  if (c && c.message) return c.message
  if (!l.path) return '未配置映射且无 Emby Path'
  if (!l.path_exists) return '路径不存在'
  if (!l.path_is_dir) return '不是目录'
  if (!l.path_readable) return '无读取权限'
  return '可访问'
}

async function loadLibs() {
  libBusy.value = true
  libError.value = ''
  try {
    const r = await api.get(props.api, '/emby_libraries')
    const list = Array.isArray(r) ? r : (r?.data || [])
    libs.value = Array.isArray(list) ? list : []
    try {
      const cur = config.value.nfo_path_mappings
      if (!Array.isArray(cur) || cur.length === 0) {
        const rc = await api.get(props.api, '/config')
        const rm = rc?.nfo_path_mappings
        if (Array.isArray(rm) && rm.length) config.value.nfo_path_mappings = rm
      }
    } catch (e) { /* 迁移可见性回读，失败不影响主流程 */ }
  } catch (e) {
    libError.value = (e && e.message) || '拉取媒体库失败'
    libs.value = []
  } finally { libBusy.value = false }
}

async function testLib(serverId, libId) {
  const key = `${serverId}:${libId}`
  pathCheck.value = { ...pathCheck.value, [key]: { loading: true, message: '检测中…' } }
  try {
    const r = await api.post(props.api, '/nfo/path/check', { server_id: serverId, lib_id: libId })
    pathCheck.value = { ...pathCheck.value, [key]: r || {} }
    const ok = !!(r && r.exists && r.is_dir && r.readable)
    notify((r && r.message) || (ok ? '路径可访问' : '路径检查失败'), ok ? 'success' : 'error')
  } catch (e) {
    const msg = (e && e.message) || '路径检查失败'
    pathCheck.value = { ...pathCheck.value, [key]: { message: msg } }
    notify(msg, 'error')
  }
}

async function testAllPaths() {
  checkAllBusy.value = true
  try {
    const r = await api.post(props.api, '/nfo/path/check_all')
    const map = {}
    for (const row of (r?.rows || [])) map[`${row.server_id}:${row.lib_id}`] = row
    pathCheck.value = { ...pathCheck.value, ...map }
    const ok = r?.ok ?? 0, total = r?.total ?? 0
    notify(`路径检查完成：${ok}/${total} 可访问`, ok === total ? 'success' : 'error')
  } catch (e) { notify((e && e.message) || '批量检查失败', 'error') } finally { checkAllBusy.value = false }
}

const browseDlg = ref(false)
const browse = ref({ server_id: '', lib_id: '', lib_name: '', root: '', path: '', relative: '', entries: [], loading: false, error: '', check: '' })
async function browseLoad(path = '') {
  const b = browse.value
  b.loading = true; b.error = ''; b.check = ''
  try {
    const r = await api.get(props.api, '/nfo/path/browse', { server_id: b.server_id, lib_id: b.lib_id, path })
    b.root = r?.root || ''
    b.path = r?.path || ''
    b.relative = r?.relative || ''
    b.entries = Array.isArray(r?.entries) ? r.entries : []
  } catch (e) { b.error = (e && e.message) || '浏览失败'; b.entries = [] } finally { b.loading = false }
}
async function browseOpen(serverId, libId, libName) {
  browse.value = { server_id: serverId, lib_id: libId, lib_name: libName || libId, root: '', path: '', relative: '', entries: [], loading: true, error: '', check: '' }
  browseDlg.value = true
  await browseLoad('')
}
function browseLib(g, l) { browseOpen(l.server_id || g.server_id, l.lib_id, l.lib_name) }
function browseServer(g) {
  if (!g || !g.libs || !g.libs.length) return
  const pick = g.libs.find(l => isLibSelected(l.full_key)) || g.libs[0]
  browseOpen(pick.server_id || g.server_id, pick.lib_id, pick.lib_name)
}
function browseRefresh() { browseLoad(browse.value.path || '') }
function browseUp() {
  const b = browse.value
  if (!b.path || !b.root) return
  if (String(b.path).replace(/[\\/]+$/, '') === String(b.root).replace(/[\\/]+$/, '')) return
  const parent = String(b.path).replace(/[\\/][^\\/]*$/, '')
  if (!parent || parent.length < b.root.length) return
  browseLoad(parent)
}
async function browseTest() {
  const b = browse.value
  const key = `${b.server_id}:${b.lib_id}`
  b.check = '检测中…'
  try {
    const r = await api.post(props.api, '/nfo/path/check', { server_id: b.server_id, lib_id: b.lib_id })
    pathCheck.value = { ...pathCheck.value, [key]: r || {} }
    b.check = (r && r.message) || '完成'
    notify(b.check, (r && r.exists && r.is_dir && r.readable) ? 'success' : 'error')
  } catch (e) { b.check = (e && e.message) || '测试失败'; notify(b.check, 'error') }
}
function joinPath(base, name) {
  const b = String(base || '').replace(/[\\/]+$/, '')
  return b ? `${b}/${name}` : name
}
function fmtSize(n) {
  const v = Number(n || 0)
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  if (v < 1024 * 1024 * 1024) return `${(v / 1024 / 1024).toFixed(1)} MB`
  return `${(v / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function notify(msg, type='error') {
  if (toast && typeof toast[type] === 'function') toast[type](msg)
}

const syncDirs = [
  { text: '关闭（不互同步）', value: 'off' },
  { text: '剧 → 集', value: 's2e' },
  { text: '集 → 剧', value: 'e2s' },
]
const syncDirDesc = () => ({
  off: '不做演员互同步：剧集与各集各自翻译，互不影响',
  s2e: '把剧（tvshow.nfo）的演员译文写进各集 episode.nfo（下表可设整份覆盖）',
  e2s: '把各集演员（按上方开关 + 人数过滤并翻译后）合并进剧 tvshow.nfo —— 剧里已有的演员不重复添加',
}[config.value.sync_direction] || '')
const nfoEpisodeOverwrite = computed({
  get: () => !!config.value.nfo_episode_overwrite,
  set: v => { config.value.nfo_episode_overwrite = v },
})
const seriesSyncDesc = () => '关（默认）：只把剧集译文写到各集「已出场」的演员身上（按名字精准匹配，集内客串保留）；开：把剧集主演名单整份替换进每集（含未出场）'

function restorePrompt() {
  config.value.prompt_template = config.value.prompt_default || ''
  notify('已填入默认提示词，记得保存', 'success')
}

const nfoBusy = ref(false)
const nfoResult = ref(null)
function nfoBody() {
  return {
    root_text: config.value.nfo_roots || '',
    recursive: config.value.nfo_recursive,
    include_episodes: config.value.nfo_include_episodes,
    backup: config.value.nfo_backup,
  }
}
async function testNfo() {
  nfoBusy.value = true
  nfoResult.value = null
  try {
    const r = await api.post(props.api, '/nfo/test', nfoBody())
    nfoResult.value = r
    const s = r?.stat || {}
    notify(`找到 ${r?.files ?? 0} 个 NFO（电影${s.movie ?? 0}/剧集${s.tvshow ?? 0}/单集${s.episode ?? 0}），人名 ${r?.names ?? 0} 条`, 'success')
  } catch (e) {
    notify((e && e.message) || '测试扫描失败', 'error')
  } finally {
    nfoBusy.value = false
  }
}

// 人名池拉取类型归一：「演员」勾选即含声优（VoiceActor 不再单列）——
// 去掉历史配置里的 VoiceActor，全空则回落到「演员」。
function _normPoolFetchTypes () {
  const _a = Array.isArray(config.value.pool_fetch_types) ? config.value.pool_fetch_types : []
  const _f = _a.filter((t) => t !== 'VoiceActor')
  config.value.pool_fetch_types = _f.length ? _f : ['Actor']
}
async function loadConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await api.get(props.api, '/config')
    if (data && typeof data === 'object') config.value = { ...DEFAULT, ...data }
    _normPoolFetchTypes()
    if (!config.value.prompt_template && data?.prompt_default) {
      config.value.prompt_template = data.prompt_default
    }
  } catch (e) { /* 保持 initialConfig */ }
}

const llmTestBusy = ref(false)
async function testLlm() {
  llmTestBusy.value = true
  try {
    const r = await api.post(props.api, '/llm/test')
    notify(r?.message || '测试完成', r?.success ? 'success' : 'error')
  } catch (e) { notify((e && e.message) || '测试连接失败', 'error') } finally { llmTestBusy.value = false }
}

async function save() {
  saving.value = true
  try {
    config.value.scan_mode = 'nfo'
    if (typeof props.api?.post === 'function') {
      const payload = { ...config.value }
      if (clearApiKeyFlag.value) payload.clear_api_key = true
      delete payload.has_api_key
      delete payload.llm_api_key_masked
      await api.post(props.api, '/config', payload)
      clearApiKeyFlag.value = false
      try { const d = await api.get(props.api, '/config'); if (d) { config.value = { ...DEFAULT, ...d }; _normPoolFetchTypes() } } catch (e) {}
      emit('save', { ...config.value })
      notify('配置已保存并生效', 'success')
    } else {
      emit('save', { ...config.value })
      notify('配置已保存', 'success')
    }
  } catch (e) { notify(e.message || '保存失败', 'error') }
  finally { saving.value = false }
}

onMounted(() => {
  loadConfig()
  loadLibs()
})
</script>

<template>
  <div class="epl-view">
    <v-card variant="tonal" class="mb-3">
      <v-card-text class="pa-3 d-flex align-center">
        <v-icon start color="primary">mdi-file-document-outline</v-icon>
        <div class="flex-grow-1">
          <div class="font-weight-medium">NFO 本地文件模式</div>
          <div class="text-caption" style="opacity:.7">直接读写 nfo 文件（省请求、防刮削覆盖），扫描范围按下方 Emby 媒体库选择</div>
        </div>
        <v-chip size="x-small" color="success" variant="tonal">当前</v-chip>
      </v-card-text>
    </v-card>

    <!-- 基础设置 -->
    <v-card variant="tonal" class="mb-3">
      <v-card-title class="text-subtitle-1"><v-icon start>mdi-cog-outline</v-icon>基础设置</v-card-title>
      <v-card-text>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">启用插件</div>
            <div class="epl-switch-desc">开启后扫描/入库时自动翻译演职人员</div>
          </div>
          <v-switch v-model="config.enabled" color="success" hide-details></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">AI 翻译（LLM）</div>
            <div class="epl-switch-desc">关闭后仅禁用 LLM 翻译：人名池命中 / 繁转简 / 人工修正照常生效，新词条照常采集入库（保留原文）</div>
          </div>
          <v-switch v-model="config.enable_ai" color="primary" hide-details></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">完成时发送通知</div>
            <div class="epl-switch-desc">以下任务完成时推送通知（含统计与失败提示）：NFO 扫描 / 全部写回 / <b>拉取人名 / 批量翻译 / 批量同步</b>（含「翻译完成后自动同步」）；关闭时以上通知都不发（日志里会提示「未发送通知」）</div>
          </div>
          <v-switch v-model="config.notify_on_complete" color="primary" hide-details></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">Webhook 入库后自动翻译</div>
            <div class="epl-switch-desc">本开关只负责<b>一个入口：Webhook 入库</b>。关闭（默认）：新条目只解析入库为「待翻译」，不调 LLM，可到「库 → 批量翻译」手动开始；开启：入库后立即交后台翻译 Worker 自动翻译。<br>三个自动翻译开关是三个独立入口（Webhook 入库 / 扫描·探测库入库 / 拉取人名），互不重复——同一人名先被哪个入口翻到，另一个入口都会命中已有译文，不会重复调 AI。</div>
          </div>
          <v-switch v-model="config.auto_translate_webhook" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">扫描 / 探测库入库后自动翻译</div>
            <div class="epl-switch-desc">本开关只负责<b>一个入口：NFO 扫描（含全库扫描）· 探测库入库</b>。关闭（默认）：只入库为「待翻译」，可到「库 → 批量翻译」手动开始；开启：入库后立即交后台翻译 Worker 自动翻译（注意：首次全库扫描一次产生的词条较多，LLM 消耗较高）。<br>三个自动翻译开关是三个独立入口（Webhook 入库 / 扫描·探测库入库 / 拉取人名），互不重复——同一人名先被哪个入口翻到，另一个入口都会命中已有译文，不会重复调 AI。</div>
          </div>
          <v-switch v-model="config.auto_translate_scan" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
      </v-card-text>
    </v-card>

    <!-- NFO / 扫描（从「基础设置」拆出，NFO 专属设置独立成卡） -->
    <v-card v-if="config.scan_mode === 'nfo'" variant="tonal" class="mb-3">
      <v-card-title class="text-subtitle-1"><v-icon start>mdi-file-document-outline</v-icon>NFO / 扫描</v-card-title>
      <v-card-text>
          <div class="d-flex align-center mb-1 flex-wrap">
            <div class="epl-section-title">媒体库扫描范围</div>
            <v-spacer></v-spacer>
            <v-btn size="x-small" variant="text" :loading="libBusy" @click="loadLibs">
              <v-icon start size="14">mdi-refresh</v-icon>刷新
            </v-btn>
            <v-btn size="x-small" variant="tonal" class="ml-1" :loading="checkAllBusy" @click="testAllPaths">
              <v-icon start size="14">mdi-check-network-outline</v-icon>测试全部路径
            </v-btn>
          </div>
          <div class="epl-switch-desc mb-2" style="opacity:.7">勾选要处理的媒体库；其映射后的本地目录自动作为扫描根目录（可多选，跨服务器独立配置映射）。点击下方 Emby / MP 路径可直接浏览该目录</div>
          <div v-if="!libGroups.length" class="epl-switch-desc mb-2">未获取到媒体库列表（请检查 Emby 配置后点「刷新」）</div>
          <div v-for="g in libGroups" :key="g.server_id" class="epl-server-group mb-2">
            <div class="epl-server-head">
              <v-icon size="16">mdi-server-network</v-icon>
              <span class="epl-server-name">{{ g.server_name }}</span>
              <v-chip v-if="g.mappingFrom" size="x-small" variant="tonal" color="primary" class="ml-2">
                mapping {{ g.mappingFrom }} → {{ g.mappingTo || '（空）' }}
              </v-chip>
              <v-chip v-else size="x-small" variant="tonal" class="ml-2">未配置 mapping（用 Emby 原路径）</v-chip>
              <v-spacer></v-spacer>
              <v-btn size="x-small" variant="text" @click="browseServer(g)">
                <v-icon start size="14">mdi-folder-search-outline</v-icon>浏览
              </v-btn>
            </div>
            <div v-for="l in g.libs" :key="l.full_key" class="epl-lib-row" :class="{ 'epl-lib-open': isLibOpen(l) }">
              <v-checkbox-btn density="compact" hide-details
                               :model-value="isLibSelected(l.full_key)"
                               @update:model-value="v => toggleLib(l.full_key, !!v)"></v-checkbox-btn>
              <div class="epl-lib-info">
                <div class="epl-lib-name epl-lib-toggle" :title="isLibOpen(l) ? '收起' : '展开（查看路径与操作）'"
                     @click="toggleLibOpen(l)">
                  <v-icon size="16" class="epl-lib-caret">{{ isLibOpen(l) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                  {{ l.lib_name }} <span class="epl-lib-type">{{ l.lib_type || '?' }}</span>
                </div>
                <template v-if="isLibOpen(l)">
                  <div class="epl-lib-path" :title="l.emby_path || ''">
                    Emby
                    <code class="epl-path-link" :class="{ 'epl-path-off': !l.emby_path }"
                          :title="l.emby_path ? '点击浏览该路径' : 'Emby 未上报 Path'"
                          @click="l.emby_path && browseLib(g, l)">{{ l.emby_path || '—' }}</code>
                  </div>
                  <div class="epl-lib-path" :title="l.path || ''">
                    MP&nbsp;&nbsp;
                    <code class="epl-path-link" :class="{ 'epl-path-off': !l.path }"
                          :title="l.path ? '点击浏览该路径' : '该媒体库未解析到本机路径（检查路径映射）'"
                          @click="l.path && browseLib(g, l)">{{ l.path || '—' }}</code>
                  </div>
                  <div class="epl-lib-actions">
                    <v-btn size="x-small" variant="text" @click="testLib(l.server_id || g.server_id, l.lib_id)">测试</v-btn>
                    <v-btn size="x-small" variant="text" @click="browseLib(g, l)">浏览</v-btn>
                  </div>
                </template>
              </div>
              <v-chip size="x-small" variant="tonal" :color="libOk(l) ? 'success' : 'error'" class="epl-lib-chip">
                {{ libOk(l) ? '✅ 可访问' : '❌ 不可访问' }}
              </v-chip>
            </div>
          </div>
          <v-alert v-if="libError" type="warning" variant="tonal" density="compact" class="mb-2" style="font-size:12px">{{ libError }}</v-alert>

          <div class="epl-section-title mt-2 mb-1">路径映射（Emby Path → 本机 MP 路径）</div>
          <div class="epl-switch-desc mb-2" style="opacity:.7">每台服务器各一行（MP 读到几台就显示几行）；未配置的服务器直接使用 Emby 原路径</div>
          <div v-for="g in libGroups" :key="'map-' + g.server_id" class="epl-map-row">
            <div class="epl-map-server">{{ g.server_name }}</div>
            <v-text-field :model-value="g.mappingFrom" label="从（Emby）" density="compact" variant="outlined" hide-details
                          placeholder="/mnt/movies"
                          @update:model-value="v => setMapping(g.server_id, 'from', v)"></v-text-field>
            <v-text-field :model-value="g.mappingTo" label="到（MP 本机）" density="compact" variant="outlined" hide-details
                          placeholder="/media/movies"
                          @update:model-value="v => setMapping(g.server_id, 'to', v)"></v-text-field>
            <v-btn size="x-small" variant="text" :disabled="!g.mappingFrom" title="清除该服务器映射"
                   @click="clearMapping(g.server_id)"><v-icon size="16">mdi-close</v-icon></v-btn>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">扫描子文件夹</div>
              <div class="epl-switch-desc">递归扫描子目录里的 nfo</div>
            </div>
            <v-switch v-model="config.nfo_recursive" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">处理单集</div>
              <div class="epl-switch-desc">开：逐集收集演员并入库（翻译范围开着就翻、可写回）；关：只翻节目的主演（剧集/电影本身）—— 各集原文仍会入库供「库」页查看/编辑，只是不参与翻译</div>
            </div>
            <v-switch v-model="config.nfo_include_episodes" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">集 / 剧演员同步方向</div>
              <div class="epl-switch-desc">{{ syncDirDesc() }}</div>
            </div>
            <v-select v-model="config.sync_direction" :items="syncDirs" item-title="text" item-value="value"
                      density="compact" variant="outlined" hide-details style="max-width:200px"></v-select>
          </div>
          <div v-if="config.sync_direction === 's2e'" class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">整份覆盖各集名单（剧→集）</div>
              <div class="epl-switch-desc">{{ seriesSyncDesc() }}</div>
            </div>
            <v-switch v-model="nfoEpisodeOverwrite" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">预览模式（不落盘）</div>
              <div class="epl-switch-desc">开：翻译照常自动进行，但不自动写回 nfo（只写库），确认后到「库」页点「全部写回」统一落盘；关：按本卡片下方的「翻译完自动写回」开关决定是否自动落盘</div>
            </div>
            <v-switch v-model="config.nfo_preview" color="warning" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">翻译完自动写回 nfo
                <v-tooltip location="top" max-width="460">
                  <template #activator="{ props: tp }">
                    <v-icon size="14" class="ml-1" style="opacity:.6" v-bind="tp">mdi-information-outline</v-icon>
                  </template>
                  条目里的词条全部翻完（按类型/角色开关、失败清单、池命中综合判定）→ 自动把该条目的 tvshow + 各集 nfo 一起写回；
                  写回是幂等的：同一条目单飞、内容已是译文不重复落盘、文件被外部替换会重新写、失败自动退避重试（绝不误标成功）。
                  关闭后翻译只写库，确认后到「库」页点「全部写回」统一落盘；上方「预览模式」开启时同样不自动落盘。
                </v-tooltip>
              </div>
              <div class="epl-switch-desc">开：条目翻完 → 自动写回该条目 nfo（幂等，失败重试）；关：只写库，手动「全部写回」落盘</div>
            </div>
            <v-switch v-model="config.auto_writeback" color="primary" hide-details
                      :disabled="config.nfo_preview"></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">翻译后锁定 Cast</div>
              <div class="epl-switch-desc">写回 nfo 时写入 &lt;lockedfields&gt;Cast&lt;/lockedfields&gt; 只锁定演员字段，Emby 重新刮削/刷新时不会覆盖中文名单，剧情/简介/海报等照常更新（新番简介过几天出中文也不受影响）</div>
            </div>
            <v-switch v-model="config.lock_cast" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">角色译文同步到 Emby 条目</div>
              <div class="epl-switch-desc">把「第二排角色名」的中文译文写入 Emby 条目级 People[].Role（与第一排同名层级）。只写 nfo 时，Emby 刷新元数据会用它条目级缓存的英文角色名把 nfo 覆盖回去——开启本项后 Emby 自己写 nfo 带的即是中文，不再依赖 Cast 锁能否挡住覆盖。写回后自动执行：每条目 1 次读取，命中才整份回写（只改 Role、不动 Name）；默认关，建议开启</div>
            </div>
            <v-switch v-model="config.emby_role_sync" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">写回前 .bak 备份</div>
              <div class="epl-switch-desc">每次写回 nfo 前自动保留一份 .bak 备份（媒体库里看到的 tvshow.nfo.bak / movie.nfo.bak 就是它）；关闭后不再生成，已生成的 .bak 可手动删除</div>
            </div>
            <v-switch v-model="config.nfo_backup" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">失效宽限期（小时）</div>
              <div class="epl-switch-desc">检测到 nfo 目录消失后先观察这段时间：期内同 ID 新版本入库自动恢复（洗版无缝、不重问 AI），超期仍未恢复才判定为真删除并清理</div>
            </div>
            <v-text-field v-model.number="config.nfo_dead_grace_hours" type="number" min="1" max="720"
                          density="compact" variant="outlined" hide-details
                          style="max-width:110px" suffix="小时"></v-text-field>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">定时全量扫库</div>
              <div class="epl-switch-desc">按设定间隔自动全量扫描已选媒体库（断点续扫增量），兜底插件关闭 / 漏接 Webhook 期间的漏入库条目；后台有任务时自动跳过本轮</div>
            </div>
            <v-switch v-model="config.schedule_enabled" color="primary" hide-details></v-switch>
          </div>
          <div v-if="config.schedule_enabled" class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">扫库间隔（小时）</div>
              <div class="epl-switch-desc">默认 24 小时，最小值 1</div>
            </div>
            <v-text-field v-model.number="config.schedule_interval_hours" type="number" min="1" max="720"
                          density="compact" variant="outlined" hide-details
                          style="max-width:110px" suffix="小时"></v-text-field>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">探测库
                <v-tooltip location="top" max-width="460">
                  <template #activator="{ props: tp }">
                    <v-icon size="14" class="ml-1" style="opacity:.6" v-bind="tp">mdi-information-outline</v-icon>
                  </template>
                  定时把 Emby 的清单与插件库对一遍，双向都能发现差异：①正向 —— Emby 有、插件库没有的集/整部新条目 → 自动补翻（关插件期间漏的入库都靠它）；②反向 —— 插件库有、Emby 已没有的集（服务器删了但可能漏接删除事件）→ 自动标记「待恢复」观察期，期间重新入库会自动恢复、到期未回来则清理。每轮先做只读对差（计数没变就直接结束），发现缺口才动。本地文件级兜底（Emby 没刮到、nfo 被改过、写失败重试）靠上面的「定时全量扫库」。「NFO 扫描」只管本地文件、不查 Emby 清单，三者互补。手动跑一轮去仪表盘「运行操作」点「探测库」。
                </v-tooltip>
              </div>
              <div class="epl-switch-desc">定时双向对账：Emby 缺的补翻、Emby 已删的标「待恢复」</div>
            </div>
            <v-switch v-model="config.probe_enabled" color="primary" hide-details></v-switch>
          </div>
          <div v-if="config.probe_enabled" class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">探测间隔（分钟）</div>
              <div class="epl-switch-desc">默认 60，最小 10；每轮先做只读对差（计数没变就直接结束），发现差异才处理 —— 补翻每轮上限 200 个文件、反向标记每轮上限 50 集</div>
            </div>
            <v-text-field v-model.number="config.probe_interval_minutes" type="number" min="10" max="1440"
                          density="compact" variant="outlined" hide-details
                          style="max-width:110px" suffix="分钟"></v-text-field>
          </div>
      </v-card-text>
    </v-card>

    <v-card variant="tonal" class="mb-3">
      <v-card-title class="text-subtitle-1">
        <v-icon start>mdi-account-search</v-icon>人名池
        <v-chip size="x-small" class="ml-2" variant="tonal">拉取类型为独立设置（不跟随「翻译范围」）；池里已有人名时改设置后可在「人名池」页点「按当前设置重筛池」</v-chip>
      </v-card-title>
      <v-card-text>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">拉取类型（独立）</div>
            <div class="epl-switch-desc">拉取 / 扫描入库时把哪些类型的 Person 收进人名池 —— <b>独立于「翻译范围」的类型</b>，也不受翻译人数上限约束。「演员（含声优）」勾上即同时收 Actor 与 VoiceActor。</div>
          </div>
        </div>
        <div class="d-flex flex-wrap ga-3 mt-1 mb-1">
          <v-checkbox-btn v-model="config.pool_fetch_types" value="Actor" label="演员（含声优）" density="compact" hide-details></v-checkbox-btn>
          <v-checkbox-btn v-model="config.pool_fetch_types" value="GuestStar" label="客串" density="compact" hide-details></v-checkbox-btn>
          <v-checkbox-btn v-model="config.pool_fetch_types" value="Director" label="导演" density="compact" hide-details></v-checkbox-btn>
          <v-checkbox-btn v-model="config.pool_fetch_types" value="Writer" label="编剧" density="compact" hide-details></v-checkbox-btn>
          <v-checkbox-btn v-model="config.pool_fetch_types" value="Producer" label="制片" density="compact" hide-details></v-checkbox-btn>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">拉取来源</div>
            <div class="epl-switch-desc">仅已选媒体库（遍历库条目的 People，快）／ 全库 Person（/Persons 全量，慢）</div>
          </div>
        </div>
        <v-radio-group v-model="config.pool_fetch_scope" density="compact" hide-details inline class="mt-1">
          <v-radio value="libraries" label="仅已选媒体库（推荐）"></v-radio>
          <v-radio value="all" label="全库 Person"></v-radio>
        </v-radio-group>
        <div class="epl-switch-row mt-3">
          <div class="flex-grow-1">
            <div class="epl-switch-title">类型未知的人物是否保留？</div>
            <div class="epl-switch-desc">类型未知（Emby 关系里取不到职位）≠ 演员，列表显示为「未分类」；保留时「按当前设置重筛池」不会删除它们</div>
          </div>
        </div>
        <v-radio-group v-model="config.pool_keep_unknown" density="compact" hide-details inline class="mt-1">
          <v-radio :value="true" label="保留未分类（推荐）"></v-radio>
          <v-radio :value="false" label="过滤未分类"></v-radio>
        </v-radio-group>
        <div class="epl-switch-row mt-1">
          <div class="flex-grow-1">
            <div class="epl-switch-title">人名池翻译总开关</div>
            <div class="epl-switch-desc">关闭后，池里 pending 的人名不再交给 Worker 翻译（已翻/已同步的条目不受影响）。池条目是否翻译由本开关独立决定</div>
          </div>
          <v-switch v-model="config.pool_translation_enabled" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">自动翻译新拉取的人名</div>
            <div class="epl-switch-desc">本开关只负责<b>一个入口：拉取人名（写入「人名池」）</b>。关闭（默认）：拉取只入池、不调 LLM，可到「人名池 → 批量翻译」手动开始；开启：拉取结束后立即交后台翻译 Worker 自动翻译新入池的人物。<br>三个自动翻译开关是三个独立入口（Webhook 入库 / 扫描·探测库入库 / 拉取人名），互不重复——同一人名先被哪个入口翻到，另一个入口都会命中已有译文，不会重复调 AI。</div>
          </div>
          <v-switch v-model="config.pool_auto_translate" color="primary" hide-details :disabled="!config.pool_translation_enabled || !aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">拉取时用 TMDB 刮削补译</div>
            <div class="epl-switch-desc">仅对 Emby 当前名非中文的人物：TMDB 有中文别名 → 中文名入池记为 tmdb 来源（繁体在拉取环节即繁转简，一律简体），再由同步流程统一写回 Emby；中文简介/头像即时写回 Emby（简介含锁定）。没有中文名的留给 AI 翻译。已缝合官方「演职人员刮削」，开启后可停用 personmeta 插件。<b>不依赖 AI 翻译：TMDB 查询不经 LLM，AI 总开关关闭时同样可用</b></div>
          </div>
          <v-switch v-model="config.pool_tmdb_fill" color="primary" hide-details></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">用 TMDB 演职人员表补「第二排角色名」
              <v-tooltip location="top" max-width="460">
                <template #activator="{ props: tp }">
                  <v-icon size="14" class="ml-1" style="opacity:.6" v-bind="tp">mdi-information-outline</v-icon>
                </template>
                豆瓣等来源的 NFO「第二排」（角色名）常为空或只有中文，导致翻译链拿不到英文原文而翻不了；
                开启后：按条目的 TMDB ID 拉取演职人员表，用 TMDB 的英文角色名（character）回填这些空/非英文的角色名，
                再交给翻译链翻成中文。仅作用于「第二排角色名」范围（受下方「翻译范围 → 第二排角色名」及 Actor/客串等开关约束）；
                已有英文角色名的条目不受影响。默认关闭。
              </v-tooltip>
            </div>
            <div class="epl-switch-desc">开：入库/扫描（含 Webhook）时用 TMDB credits 的英文角色名回填空/非英文角色名再翻；关：保持 NFO 原样
              需开启下方「翻译范围 → 第二排角色名」（或「全部类型」），否则不生效</div>
          </div>
          <v-switch v-model="config.pool_tmdb_credits" color="primary" hide-details
                    :disabled="!config.translate_role && !config.translate_all"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">人名池翻译完成后自动同步 Emby</div>
            <div class="epl-switch-desc">关闭时（默认），翻译只写池，需到「人名池 → 批量同步」手动同步到 Emby；开启后池内待翻全部翻完即自动同步（区别于批量翻译弹窗里一次性的「翻译完成后自动同步」勾选）</div>
          </div>
          <v-switch v-model="config.pool_auto_sync" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
      </v-card-text>
    </v-card>

    <!-- 翻译范围（v4.6.48 三段式：翻哪排 × 翻哪些类型 × 每类型翻几个） -->
    <v-card variant="tonal" class="mb-3">
      <v-card-title class="text-subtitle-1">
        <v-icon start>mdi-account-multiple-outline</v-icon>翻译范围
        <v-chip size="x-small" class="ml-2" variant="tonal">翻哪排 × 翻哪些类型 × 每类型翻几个</v-chip>
      </v-card-title>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact" class="mb-2" style="font-size:12px">
          采集 ≠ 翻译：扫描照常采集入库，本卡片只决定「翻译什么」。下面的<b>类型 + 人数同时对第一排人名与第二排角色名生效</b> —— 例如「关第一排 + 开第二排 + 只勾演员」，就只翻演员饰演的角色名。
        </v-alert>
        <v-alert v-if="!aiOn" type="warning" variant="tonal" density="compact" class="mb-2" style="font-size:12px">
          AI 翻译总开关（LLM）已关闭：本卡片的翻译相关开关暂不可操作；到「基础设置」重新开启「AI 翻译（LLM）」后立即恢复（无需保存）。
        </v-alert>
        <div class="epl-section-title mb-1">① 翻哪排</div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">第一排：人物姓名</div>
            <div class="epl-switch-desc">演员 / 导演等「人」的姓名（Person 数据仍照常采集并交给人名池）</div>
          </div>
          <v-switch v-model="config.translate_person" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">第二排：角色名</div>
            <div class="epl-switch-desc">人物饰演的角色名（如 "Jiro Yakuin (voice)" → 药院次郎）；关闭后角色名不翻译、也不参与写回等待</div>
          </div>
          <v-switch v-model="config.translate_role" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
        <v-divider class="my-2" style="opacity:.35"></v-divider>
        <div class="epl-section-title mb-1">② 翻哪些类型 + 每个文件翻几个</div>
        <div class="epl-switch-desc mb-2" style="opacity:.8">开关 = 翻不翻该类型（两排共用）；数字 = 每个文件里该类型最多翻前 N 个<b>人</b>，<b>0 或留空 = 不限</b>。<b>两排共用这个数字</b>：只翻第二排时，「演员=3」= 取前 3 个演员的<b>角色名</b>；数字只在「待翻」里数，已翻完的不占名额。</div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">演员 Actor</div>
            <div class="epl-switch-desc">主演 / 声优</div>
          </div>
          <v-text-field v-model.number="config.actor_limit" type="number" min="0" density="compact" variant="outlined" hide-details placeholder="不限" style="max-width:104px" class="mr-2" :disabled="config.translate_all || !aiOn"></v-text-field>
          <v-switch v-model="config.translate_actor" color="primary" hide-details :disabled="config.translate_all || !aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">客串 / 配角 GuestStar</div>
            <div class="epl-switch-desc">单集 NFO 里大部分出场人员都是客串</div>
          </div>
          <v-text-field v-model.number="config.guest_limit" type="number" min="0" density="compact" variant="outlined" hide-details placeholder="不限" style="max-width:104px" class="mr-2" :disabled="config.translate_all || !aiOn"></v-text-field>
          <v-switch v-model="config.translate_guest_star" color="primary" hide-details :disabled="config.translate_all || !aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">导演 Director</div>
            <div class="epl-switch-desc">导演</div>
          </div>
          <v-text-field v-model.number="config.director_limit" type="number" min="0" density="compact" variant="outlined" hide-details placeholder="不限" style="max-width:104px" class="mr-2" :disabled="config.translate_all || !aiOn"></v-text-field>
          <v-switch v-model="config.translate_director" color="primary" hide-details :disabled="config.translate_all || !aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">编剧 / 制片人 Writer</div>
            <div class="epl-switch-desc">编剧 / 制片人等非演员人员（共用一个人数）</div>
          </div>
          <v-text-field v-model.number="config.writer_limit" type="number" min="0" density="compact" variant="outlined" hide-details placeholder="不限" style="max-width:104px" class="mr-2" :disabled="config.translate_all || !aiOn"></v-text-field>
          <v-switch
            :model-value="config.translate_writer || config.translate_producer"
            color="primary"
            hide-details
            :disabled="config.translate_all || !aiOn"
            @update:model-value="v => { config.translate_writer = v; config.translate_producer = v }"
          ></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">全部类型翻译
              <v-tooltip location="top" max-width="420">
                <template #activator="{ props: tp }">
                  <v-icon size="14" class="ml-1" style="opacity:.6" v-bind="tp">mdi-information-outline</v-icon>
                </template>
                这是**运行期覆盖**开关：开启时忽略上方各类型开关（所有职位的人名 + 角色名都翻），
                但不会改写你已保存的类型选择；关闭后自动恢复之前的选择（无需重新勾选）。
              </v-tooltip>
            </div>
            <div class="epl-switch-desc">开启 = 覆盖所有类型与两排（人数上限仍生效）；关闭后恢复上方原选择（不再永久改写）</div>
          </div>
          <v-switch v-model="config.translate_all" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">重译已有中文名</div>
            <div class="epl-switch-desc">对已是中文的人名/角色名强制重新翻译</div>
          </div>
          <v-switch v-model="config.overwrite_chinese" color="primary" hide-details :disabled="!aiOn"></v-switch>
        </div>
        <div class="epl-switch-desc mt-2" style="opacity:.75">提示：数字按「每个文件各自算前 N 个」（电影 nfo / 剧 tvshow.nfo / 各集 episode.nfo 各自计数，电影与剧共用同一套数字），按「人」计、两排共用；只数「待翻」的，已翻完的不占名额；0/留空 = 不限。</div>
      </v-card-text>
    </v-card>

    <!-- LLM 设置（合并：来源 / 插件配置 / AI 提示词） -->
    <v-card variant="tonal" class="mb-3">
      <v-card-title class="text-subtitle-1"><v-icon start>mdi-robot</v-icon>LLM 设置</v-card-title>
      <v-card-text>
        <div :class="{ 'epl-ai-off': !aiOn }" :title="!aiOn ? 'AI 翻译已关闭：请先在「基础设置」开启「AI 翻译（LLM）」' : ''">
        <v-select
          v-model="config.llm_mode"
          :items="llmModes"
          item-title="text"
          item-value="value"
          label="LLM 来源"
          density="compact"
          variant="outlined"
          class="mb-2"
          hide-details
        ></v-select>
        <template v-if="config.llm_mode === 'plugin'">
          <v-text-field v-model="config.llm_base_url" label="API 地址" placeholder="https://api.example.com/v1" density="compact" variant="outlined" class="mb-2"></v-text-field>
          <div class="d-flex ga-2">
            <v-text-field v-model="config.llm_api_key" label="API Key" type="password" density="compact" variant="outlined" class="flex-grow-1"
                          :placeholder="apiKeyPlaceholder"></v-text-field>
            <v-btn size="small" variant="text" :disabled="!config.has_api_key && !clearApiKeyFlag"
                   :title="clearApiKeyFlag ? '保存后清除已配置的 Key' : '清除已配置的 Key（保存后生效）'"
                   @click="clearApiKey">{{ clearApiKeyFlag ? '将清除' : '清除' }}</v-btn>
            <v-text-field v-model="config.llm_model" label="模型名称" density="compact" variant="outlined" class="flex-grow-1"></v-text-field>
            <v-text-field v-model.number="config.llm_timeout" label="超时(秒)" type="number" min="1" max="3600" density="compact" variant="outlined" style="width:120px"></v-text-field>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">使用代理</div>
              <div class="epl-switch-desc">公网 API / 走系统代理的场景开启</div>
            </div>
            <v-switch v-model="config.use_proxy" color="primary" hide-details></v-switch>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">关闭 SSL 校验</div>
              <div class="epl-switch-desc">内网自签证书的中转端点（https 握手失败）时开启</div>
            </div>
            <v-switch
              :model-value="!config.llm_verify_ssl"
              @update:model-value="v => { config.llm_verify_ssl = !v }"
              color="warning"
              hide-details
            ></v-switch>
          </div>
        </template>
        <template v-else>
          <div class="text-body-2" style="opacity: 0.75">
            使用 MoviePilot 系统 LLM 设置（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），插件内无需填写。
          </div>
        </template>
        <v-divider class="my-3" style="opacity:.35"></v-divider>
        <div class="epl-section-title mb-1">思考与请求</div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">禁用模型深度思考
              <v-tooltip location="top" max-width="460">
                <template #activator="{ props: tp }">
                  <v-icon size="14" class="ml-1" style="opacity:.6" v-bind="tp">mdi-information-outline</v-icon>
                </template>
                思考型模型（DeepSeek 系默认就开思考、默认强度 high）会先把推理过程写一大段，把 max_tokens 全烧在思考上，导致正文为空或输出被截断（finish_reason=length），插件只能反复折半重试、白烧额度。<br>
                开启后：无论用什么模型，请求都会带上「关闭思考」参数（不填自定义时，内置依次尝试：<code>{"thinking":{"type":"disabled"}}</code> → <code>{"reasoning_effort":"none"}</code> → <code>{"reasoning_effort":"minimal"}</code> → <code>chat_template_kwargs</code>，前一种被端点拒绝或没关掉思考就自动换下一种）。<br>
                若你的服务商不认内置写法，请在下方「自定义参数」里直接填官方推荐的写法。
              </v-tooltip>
            </div>
            <div class="epl-switch-desc">默认开：无论什么模型都不让它深度思考，直接出结果；写法不兼容会自动换下一种，不会报错</div>
          </div>
          <v-switch v-model="config.llm_thinking_off" color="primary" hide-details></v-switch>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">自定义关闭思考参数（JSON，留空=用内置）</div>
            <div class="epl-switch-desc">各家写法不同，填了就只按你填的这一个发（不再试内置的）。例：DeepSeek 官方 <code>{"thinking":{"type":"disabled"}}</code>；OpenAI 系 <code>{"reasoning_effort":"none"}</code>；vLLM/Qwen3 <code>{"chat_template_kwargs":{"enable_thinking":false}}</code>。填错格式会被忽略并记一条提醒日志</div>
          </div>
          <v-text-field v-model="config.llm_thinking_params" density="compact" variant="outlined" hide-details
                        style="max-width:340px" placeholder='{"thinking":{"type":"disabled"}}'
                        :disabled="!config.llm_thinking_off"></v-text-field>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">请求间隔（秒）</div>
            <div class="epl-switch-desc">两次请求之间至少隔多久，唯一的限速项（已合并原「最小请求间隔」与「最大 RPM」）。3 秒 ≈ 每分钟最多 20 次；想做到「每分钟最多 5 次」就填 12。留空或 0 = 不额外限速</div>
          </div>
          <v-text-field v-model.number="config.llm_min_interval" type="number" min="0" max="600" step="0.1"
                        density="compact" variant="outlined" hide-details
                        style="max-width:110px" suffix="秒"></v-text-field>
        </div>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">TPM 令牌预算（每分钟，0 = 不限制）
              <v-tooltip location="top" max-width="440">
                <template #activator="{ props: tp }">
                  <v-icon size="14" class="ml-1" style="opacity:.6" v-bind="tp">mdi-information-outline</v-icon>
                </template>
                你的服务商明示「TPM 每分钟令牌上限」时填这里：插件发每个请求前会估算
                「近 60 秒已用令牌 + 本次请求令牌」，超出预算就先等窗口滑出再发，
                避免「429 限流 → 重试 → 再 429 → 熔断」的循环。<br>
                不知道填多少就留 0（不限制），配合「请求间隔」即可；估算值 = 提示词长度 ÷ 2 + 输出上限。
              </v-tooltip>
            </div>
            <div class="epl-switch-desc">按估算令牌限速：近 1 分钟累计超过预算先等待再发，显著减少 TPM 限流；0 = 不限制</div>
          </div>
          <v-text-field v-model.number="config.llm_tpm_budget" type="number" min="0" step="100"
                        density="compact" variant="outlined" hide-details
                        style="max-width:130px" placeholder="0"></v-text-field>
        </div>
        <div class="d-flex ga-2 flex-wrap mt-2">
          <v-text-field v-model.number="config.max_people_per_batch" label="单批最多翻译条数" type="number" min="1" max="200" density="compact" variant="outlined" class="epl-num"></v-text-field>
          <v-select
            v-model="config.translate_batching"
            :items="[
              { text: '按作品分批（同一作品合并，上下文质量优先）', value: 'per_title' },
              { text: '全局聚合（跨作品合并、更省请求，每条词条仍携带作品上下文）', value: 'global' },
            ]"
            item-title="text"
            item-value="value"
            label="翻译分批模式"
            density="compact"
            variant="outlined"
            class="epl-num"
            style="max-width: 380px"
          ></v-select>
        </div>
        <v-divider class="my-3" style="opacity:.35"></v-divider>
        <div class="d-flex align-center mb-1">
          <div class="epl-switch-title">AI 提示词</div>
          <v-spacer></v-spacer>
          <v-btn size="small" variant="tonal" @click="restorePrompt">
            <v-icon start size="14">mdi-restore</v-icon>填默认提示词
          </v-btn>
        </div>
        <v-textarea
          v-model="config.prompt_template"
          rows="4"
          density="compact"
          variant="outlined"
          style="max-height: 180px; overflow-y: auto"
          hint="留空使用内置默认提示词；可自行调整要求 LLM 怎么翻人名/角色名"
          placeholder="你是一位专业的影视人名翻译专家，只返回 JSON……"
        ></v-textarea>
        </div>
      </v-card-text>
    </v-card>

    <!-- Webhook 入库 -->
    <v-card variant="tonal" class="mb-3">
      <v-card-title class="text-subtitle-1"><v-icon start>mdi-webhook</v-icon>Webhook 入库</v-card-title>
      <v-card-text>
        <div class="epl-switch-row">
          <div class="flex-grow-1">
            <div class="epl-switch-title">启用 Webhook 入库</div>
            <div class="epl-switch-desc">
              关闭后：不接收新 Webhook / 不排队 / 不处理 / 不通知（已有挂起事件不丢失，重新开启可继续）。但：NFO 扫描 / 探测库仍继续有效。
            </div>
          </div>
          <v-switch v-model="config.webhook_enabled" color="success" hide-details></v-switch>
        </div>
        <template v-if="config.webhook_enabled">
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">入库延迟（秒）</div>
              <div class="epl-switch-desc">Emby 入库后等多少秒再翻译，给刮削留时间</div>
            </div>
            <v-text-field v-model.number="config.webhook_delay" type="number" min="0" max="3600"
                          density="compact" variant="outlined" hide-details
                          style="max-width:110px" suffix="秒"></v-text-field>
          </div>
          <div class="epl-switch-row">
            <div class="flex-grow-1">
              <div class="epl-switch-title">整剧全收（包含旧集）</div>
              <div class="epl-switch-desc">
                关（默认）：Emby 发「整部剧」事件时<b>只入库本次新增的集</b>（最近 7 天内加入的），旧集跳过 —— 你只加 3 集就只收这 3 集；
                开：把这剧 Emby 里现有的<b>全部集</b>都入库（想一次补齐整部剧时用）。
                不论开关，要补收旧集都可用：<b>「扫描」</b>（全量/增量）、<b>「探测库」</b>（按 Emby 清单补齐缺集与全新条目）、或对该剧点<b>「重新拉取」</b>（按本地 nfo 重采集该条目全部集）
              </div>
            </div>
            <v-switch v-model="config.series_ingest_all" color="primary" hide-details></v-switch>
          </div>
        </template>
        <v-alert v-else type="warning" variant="tonal" density="compact" style="font-size:12px">
          Webhook 已关闭：新入库事件不会接收。NFO 扫描 / 探测库仍可发现新条目。
        </v-alert>
      </v-card-text>
    </v-card>

    <div class="d-flex justify-end mt-2">
      <v-tooltip text="真实调用一次 1 词翻译，检测 LLM 地址/密钥/模型是否可用（地址缺 /v1 会自动尝试）" location="top">
        <template #activator="{ props: tp }">
          <v-btn variant="tonal" class="mr-2" :loading="llmTestBusy" :disabled="!aiOn" v-bind="tp" @click="testLlm">
            <v-icon start size="18">mdi-flash-outline</v-icon>测试连接
          </v-btn>
        </template>
      </v-tooltip>
      <v-btn color="primary" variant="tonal" :loading="saving" @click="save">
        <v-icon start size="18">mdi-content-save-outline</v-icon>保存配置
      </v-btn>
    </div>

    <v-dialog v-model="browseDlg" max-width="720" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center text-subtitle-1">
          <v-icon start size="18">mdi-folder-search-outline</v-icon>
          <span>浏览：{{ browse.lib_name }}</span>
          <v-spacer></v-spacer>
          <v-btn size="x-small" variant="text" @click="browseDlg = false"><v-icon size="16">mdi-close</v-icon></v-btn>
        </v-card-title>
        <v-card-subtitle style="font-size:12px">
          <code>{{ browse.path || browse.root }}</code>
        </v-card-subtitle>
        <v-card-text style="max-height:440px">
          <div class="d-flex ga-1 mb-2 flex-wrap align-center">
            <v-btn size="x-small" variant="tonal"
                   :disabled="!browse.path || browse.path === browse.root" @click="browseUp">
              <v-icon start size="14">mdi-arrow-up</v-icon>返回上级
            </v-btn>
            <v-btn size="x-small" variant="tonal" :loading="browse.loading" @click="browseRefresh">
              <v-icon start size="14">mdi-refresh</v-icon>刷新
            </v-btn>
            <v-btn size="x-small" variant="tonal" @click="browseTest">
              <v-icon start size="14">mdi-check-network-outline</v-icon>测试访问
            </v-btn>
            <v-spacer></v-spacer>
            <v-chip v-if="browse.check" size="x-small" variant="tonal">{{ browse.check }}</v-chip>
            <v-chip size="x-small" variant="tonal" color="warning">只读</v-chip>
          </div>
          <v-alert v-if="browse.error" type="error" variant="tonal" density="compact" class="mb-2" style="font-size:12px">{{ browse.error }}</v-alert>
          <div class="epl-browse-list">
            <div v-for="e in browse.entries" :key="e.name" class="epl-browse-row"
                 :class="{ 'epl-browse-dir': e.is_dir }"
                 @click="e.is_dir && browseLoad(joinPath(browse.path, e.name))">
              <v-icon size="16" :color="e.is_dir ? 'primary' : undefined">{{ e.is_dir ? 'mdi-folder' : 'mdi-file-document-outline' }}</v-icon>
              <span class="epl-browse-name">{{ e.name }}</span>
              <span class="epl-browse-size">{{ e.is_dir ? '' : fmtSize(e.size) }}</span>
            </div>
            <div v-if="!browse.entries.length && !browse.loading" class="epl-switch-desc">（空目录）</div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.epl-view { width: 100%; }
.epl-mode-card { cursor: pointer; border-color: rgba(128,128,128,0.2) !important; transition: all .15s; }
.epl-mode-card:hover { border-color: var(--v-primary-base) !important; }
.epl-mode-active { border: 1px solid var(--v-primary-base) !important; background: rgba(var(--v-theme-primary), .08) !important; }
.epl-switch-row { display: flex; align-items: center; flex-wrap: nowrap; padding: 8px 0; }
.epl-switch-row > .flex-grow-1 { min-width: 0; flex: 1 1 auto; }
.epl-switch-row > .v-switch { flex: 0 0 auto; min-width: 52px; display: flex; justify-content: flex-end; margin-left: 12px; }
.epl-switch-row > .v-btn, .epl-switch-row > .v-text-field { flex: 0 0 auto; margin-left: 12px; }
.epl-switch-title { font-size: 14px; font-weight: 500; }
.epl-switch-desc { font-size: 12px; opacity: 0.7; }
.epl-num { max-width: 200px; }
.epl-limit { max-width: 120px; }
.epl-limit-row { justify-content: flex-end; gap: 8px; padding-top: 0; }
.epl-limit-block { padding: 4px 0 8px; }
.epl-limit-block-title { font-size: 12px; font-weight: 600; opacity: .85; margin-bottom: 6px; color: var(--v-primary-base); }
.epl-limit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.epl-section-title { font-size: 13px; font-weight: 600; color: var(--v-primary-base); opacity: .9; margin-top: 4px; }
/* 服务器分组卡片 */
.epl-server-group { border: 1px solid rgba(128,128,128,0.2); border-radius: 8px; padding: 8px 10px; }
.epl-server-head { display: flex; align-items: center; gap: 6px; padding-bottom: 4px; }
.epl-server-name { font-size: 13px; font-weight: 600; }
/* 单个媒体库行 */
.epl-lib-row { display: flex; align-items: flex-start; gap: 6px; padding: 6px 0; border-top: 1px dashed rgba(128,128,128,0.18); flex-wrap: nowrap; }
.epl-lib-info { min-width: 0; flex: 1 1 auto; }
.epl-lib-name { font-size: 13px; font-weight: 500; }
.epl-lib-type { font-size: 11px; opacity: .6; margin-left: 6px; }
.epl-lib-path { font-size: 11px; opacity: .72; line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.epl-lib-actions { display: flex; gap: 4px; margin-top: 2px; }
.epl-ai-off { opacity: .45; }
.epl-ai-off > * { pointer-events: none; }
.epl-lib-path code, .epl-map-row code { font-size: 11px; opacity: .9; }
.epl-path-link { cursor: pointer; text-decoration: underline dotted; text-underline-offset: 2px; }
.epl-path-link:hover { opacity: 1; text-decoration: underline; color: rgb(var(--v-theme-primary)); }
.epl-path-off { cursor: default; text-decoration: none; opacity: .55; }
.epl-lib-chip { flex: 0 0 auto; }
.epl-lib-toggle { display: flex; align-items: center; gap: 2px; cursor: pointer; user-select: none; }
.epl-lib-toggle:hover { color: rgb(var(--v-theme-primary)); }
.epl-lib-caret { opacity: .75; flex: 0 0 auto; }
.epl-lib-open { background: rgba(var(--v-theme-primary), .04); border-radius: 6px; }
.epl-map-row { display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; padding: 4px 0; }
.epl-map-server { flex: 0 0 132px; font-size: 12px; font-weight: 600; opacity: .85; word-break: break-all; }
.epl-browse-list { border: 1px solid rgba(128,128,128,0.2); border-radius: 6px; overflow: hidden; }
.epl-browse-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-size: 13px; cursor: default; }
.epl-browse-row + .epl-browse-row { border-top: 1px solid rgba(128,128,128,0.12); }
.epl-browse-row:hover { background: rgba(var(--v-theme-primary), .06); }
.epl-browse-dir { cursor: pointer; font-weight: 500; }
.epl-browse-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.epl-browse-size { flex: 0 0 auto; font-size: 11px; opacity: .6; }
@media (max-width: 600px) {
  .epl-switch-row { align-items: stretch; flex-direction: column; gap: 6px; }
  .epl-switch-row > .v-switch {
    margin-left: 0; min-width: 0;
    width: auto; max-width: 100%;
    align-self: flex-end;
  }
  .epl-switch-row > .v-btn, .epl-switch-row > .v-text-field,
  .epl-switch-row > .v-select, .epl-switch-row > .v-slider, .epl-switch-row > .v-radio-group, .epl-switch-row > .v-textarea {
    margin-left: 0; width: 100%; max-width: 100%;
  }
  .epl-num, .epl-limit { max-width: 100%; }
  .epl-limit-row { justify-content: flex-start; }
  .epl-limit-grid { grid-template-columns: 1fr; }
  .epl-lib-row { flex-wrap: wrap; }
  .epl-lib-chip { margin-left: 0; }
  .epl-map-row { flex-wrap: wrap; }
  .epl-map-server { flex: 1 1 100%; }
  .epl-map-row > .v-text-field { flex: 1 1 100%; max-width: 100%; }
  .epl-browse-row { flex-wrap: wrap; }
}
</style>