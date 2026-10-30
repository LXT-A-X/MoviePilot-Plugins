<script setup>
import { getCurrentInstance, inject, onMounted, ref } from 'vue'
import { createApi } from './api.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OpenClashPanel' },
  initialConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['save', 'close', 'switch'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()
const api = createApi(props)

const DEFAULTS = {
  enabled: true,
  api_url: 'http://192.168.1.1:9090',
  secret: '',
  timeout: 8,
  delay_test_url: 'https://www.gstatic.com/generate_204',
  delay_test_timeout: 5000,
  auto_refresh: 10,
  max_delay_concurrency: 8,
  show_dashboard: true,
  dashboard_url: 'http://192.168.1.1:9090/ui/zashboard/',
  log_level: 'info',
  netcheck_mode: 'kernel',
  netcheck_interval: 30,
  netcheck_timeout: 6,
  netcheck_sites: [
    { name: '百度搜索', url: 'https://www.baidu.com/', via: 'direct' },
    { name: '网易云音乐', url: 'https://music.163.com/', via: 'direct' },
    { name: 'GitHub', url: 'https://github.com/', via: 'proxy' },
    { name: 'YouTube', url: 'https://www.youtube.com/', via: 'proxy' },
  ],
  allow_commands: true,
  openwrt_enabled: false,
  openwrt_host: '192.168.1.1',
  openwrt_scheme: 'http',
  openwrt_username: 'root',
  openwrt_password: '',
}

const DEFAULT_SITES_TEXT =
  '百度搜索|https://www.baidu.com/|direct\n' +
  '网易云音乐|https://music.163.com/|direct\n' +
  'GitHub|https://github.com/|proxy\n' +
  'YouTube|https://www.youtube.com/|proxy'

const cfg = ref({ ...DEFAULTS, ...(props.initialConfig || {}) })
const sitesText = ref(DEFAULT_SITES_TEXT)
const saving = ref(false)
const loading = ref(true)

function sitesToText(sites) {
  if (!Array.isArray(sites) || !sites.length) return DEFAULT_SITES_TEXT
  return sites
    .map((site) => `${site.name || ''}|${site.url || ''}|${site.via === 'proxy' ? 'proxy' : 'direct'}`)
    .join('\n')
}

function textToSites(text) {
  return String(text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
    .map((line) => {
      const parts = line.split('|').map((part) => part.trim())
      if (parts.length < 2) return null
      let url = parts[1]
      if (!/^https?:\/\//i.test(url)) url = `https://${url}`
      const via = (parts[2] || 'direct').toLowerCase() === 'proxy' ? 'proxy' : 'direct'
      return { name: parts[0], url, via }
    })
    .filter(Boolean)
}

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message)
}

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '68rem' })
  try {
    const cur = await api.get('/config')
    cfg.value = { ...DEFAULTS, ...(props.initialConfig || {}), ...(cur || {}) }
    sitesText.value = sitesToText(cfg.value.netcheck_sites)
  } catch (e) {
    toastMsg('error', '加载配置失败：' + e.message)
  } finally {
    loading.value = false
  }
})

// 保存契约：把配置作为事件参数交给宿主（MP 3.2.1 的配置弹窗会把该参数 PUT 到 /plugin/{id}），
// 不要再自己 POST，否则宿主收到 undefined 会报“参数不正确”。
function save() {
  saving.value = true
  try {
    emit('save', { ...cfg.value, netcheck_sites: textToSites(sitesText.value) })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-card variant="tonal" class="pa-4">
    <v-skeleton-loader v-if="loading" type="list-item@6" />
    <template v-else>
      <v-alert type="info" variant="tonal" density="compact" class="mb-3">
        API 地址只填 <code>http://路由器IP:9090</code>，不要带 <code>/ui/...</code>（误填会自动纠正）。
      </v-alert>
      <v-row dense>
        <v-col cols="12">
          <v-switch
            v-model="cfg.enabled"
            label="启用插件"
            hint="关闭后侧栏入口、日志采集与接口都不再工作"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="8">
          <v-text-field
            v-model="cfg.api_url"
            label="OpenClash API 地址"
            placeholder="http://192.168.1.1:9090"
            hint="external-controller 根地址（默认 9090），不要填 zashboard 的 /ui 地址"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="cfg.secret"
            label="Dashboard 密码"
            type="password"
            hint="OpenClash → 插件设置 → Dashboard 密码"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="cfg.timeout"
            label="请求超时（秒）"
            type="number"
            min="2"
            hint="默认 8 秒"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="cfg.auto_refresh"
            label="自动刷新间隔（秒）"
            type="number"
            min="0"
            hint="0 表示关闭自动刷新，默认 10 秒"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-select
            v-model="cfg.log_level"
            :items="['debug', 'info', 'warning', 'error']"
            label="日志采集级别"
            hint="Clash /logs 的 level 参数"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-select
            v-model="cfg.netcheck_mode"
            :items="[{ title: '内核（与官方一致）', value: 'kernel' }, { title: 'MP 网络', value: 'mp' }, { title: 'OpenClash 代理', value: 'clash' }]"
            label="访问检查视角"
            hint="内核：由 OpenClash 内核测速（官方同款，数字最低）；MP 网络/OpenClash：由 MP 容器测速"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="cfg.netcheck_interval"
            label="访问检查间隔（秒）"
            type="number"
            min="0"
            hint="默认 60，0 表示只手动检查"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="cfg.netcheck_timeout"
            label="访问检查超时（秒）"
            type="number"
            min="2"
            hint="默认 6"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12">
          <v-textarea
            v-model="sitesText"
            label="访问检查站点"
            rows="4"
            auto-grow
            hint="每行一个：名称|URL|direct/proxy；direct=直连，proxy=国外站点走所选通道"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12">
          <v-switch
            v-model="cfg.allow_commands"
            label="允许远程操作命令"
            hint="关闭后 /oc_node、/oc_mode、/oc_refresh 只返回提示；查询命令不受影响"
            persistent-hint
          />
        </v-col>
        <v-col cols="12">
          <v-switch
            v-model="cfg.openwrt_enabled"
            label="启用 OpenWrt 管理（需填写下面地址/用户名/密码）"
            hint="用于启动/停止/重启 OpenClash、切换运行模式、切换配置文件、更新订阅、清缓存、快捷设置"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="cfg.openwrt_host"
            label="OpenWrt 地址"
            placeholder="192.168.1.1"
            hint="路由器 IP 或域名（不含 http://）"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="6" md="2">
          <v-select
            v-model="cfg.openwrt_scheme"
            :items="['http', 'https']"
            label="协议"
            density="comfortable"
          />
        </v-col>
        <v-col cols="6" md="3">
          <v-text-field
            v-model="cfg.openwrt_username"
            label="LuCI 用户名"
            placeholder="root"
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="cfg.openwrt_password"
            type="password"
            label="LuCI 密码"
            hint="仅用于登录路由器，不会写日志"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="8">
          <v-text-field
            v-model="cfg.delay_test_url"
            label="测速地址"
            hint="默认 https://www.gstatic.com/generate_204"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="cfg.delay_test_timeout"
            label="测速超时（毫秒）"
            type="number"
            min="1000"
            hint="默认 5000"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="cfg.max_delay_concurrency"
            label="测速并发数"
            type="number"
            min="1"
            max="32"
            hint="默认 8"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="8">
          <v-text-field
            v-model="cfg.dashboard_url"
            label="完整面板地址（zashboard）"
            placeholder="http://192.168.1.1:9090/ui/zashboard/"
            hint="“完整面板”按钮打开的地址"
            persistent-hint
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="4" class="d-flex align-center">
          <v-switch
            v-model="cfg.show_dashboard"
            label="显示完整面板按钮"
            hint="在新窗口打开 zashboard"
            persistent-hint
          />
        </v-col>
      </v-row>

      <v-row class="justify-end mt-2" no-gutters>
        <v-btn color="primary" :loading="saving" @click="save">保存配置</v-btn>
      </v-row>
    </template>
  </v-card>
</template>
