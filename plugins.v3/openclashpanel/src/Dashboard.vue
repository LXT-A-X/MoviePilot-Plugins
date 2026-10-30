<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { createApi } from './api.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OpenClashPanel' },
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
  nativeSubscribe: { type: Function, default: null },
})

const api = createApi(props)
const status = ref({})
const groups = ref([])
const netResults = ref([])
const netMode = ref('mp')
const netChecking = ref(false)
const error = ref('')
let timer = null

const defaultGroup = computed(
  () => groups.value.find((item) => item.name.includes('默认代理')) || groups.value[0] || null,
)

function loadConfigMode() {
  const cfg = props.config || {}
  const saved = cfg.netcheck_mode
  netMode.value = ['kernel', 'mp', 'clash'].includes(saved) ? saved : 'kernel'
}

async function load() {
  error.value = ''
  try {
    const [s, g] = await Promise.all([api.get('/status'), api.get('/groups')])
    status.value = s || {}
    groups.value = (g && g.groups) || []
  } catch (e) {
    error.value = e.message || '加载失败'
  }
  await loadNet(0)
}

async function loadNet(retry) {
  try {
    const res = await api.get('/netcheck', { mode: netMode.value })
    netResults.value = (res && res.results) || []
    netChecking.value = Boolean(res && res.checking)
    if (netChecking.value && retry < 10) {
      setTimeout(() => loadNet(retry + 1), 1500)
    }
  } catch (e) {
    netChecking.value = false
  }
}

function fmtNow(group) {
  if (!group) return ''
  if (group.type === 'Smart') return '智能自动选路'
  return group.now || '—'
}

function netColor(item) {
  if (item.delay == null) return 'error'
  if (item.delay < 300) return 'success'
  if (item.delay < 1000) return 'warning'
  return 'error'
}

function netText(item) {
  return item.delay == null ? '失败' : `${item.delay}ms`
}

function openPanel() {
  window.location.hash = `#/plugin-app/${props.pluginId}/main`
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

onMounted(() => {
  loadConfigMode()
  load()
  timer = setInterval(load, 30000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  timer = null
})
</script>

<template>
  <v-card variant="flat" class="ocp-dash pa-3" @click="openPanel">
    <div class="ocp-dash__head">
      <span class="ocp-dot" :class="status.meta ? 'ocp-dot--ok' : 'ocp-dot--bad'" />
      <span class="ocp-dash__title">OpenClash</span>
      <span class="text-caption">{{ status.version || '—' }}</span>
      <span class="ocp-dash__tag">{{ status.mode || '—' }}</span>
      <span class="text-caption">
        默认代理 → {{ fmtNow(defaultGroup) }}
      </span>
      <v-spacer />
      <span class="text-caption">
        {{ status.active_connections ?? '—' }} 连接 ·
        {{ fmtBytes(status.download_total) }} ↓ / {{ fmtBytes(status.upload_total) }} ↑
      </span>
    </div>

    <div class="ocp-dash__net">
      <span class="text-caption ocp-dash__label">{{ netMode === 'clash' ? 'OpenClash' : netMode === 'kernel' ? '内核' : 'MP' }} 访问检查</span>
      <span v-for="item in netResults" :key="item.name" class="ocp-dash__netitem">
        <span class="ocp-dot" :class="`ocp-dot--${netColor(item)}`" />
        {{ item.name }} {{ netText(item) }}
      </span>
      <span v-if="!netResults.length" class="text-caption">{{ netChecking ? '检查中…' : (error || '暂无结果') }}</span>
    </div>

    <div class="ocp-dash__groups">
      <span class="text-caption ocp-dash__label">策略组（{{ groups.length }}）</span>
      <v-chip
        v-for="group in groups.slice(0, 10)"
        :key="group.name"
        size="x-small"
        :variant="group.name === defaultGroup?.name ? 'flat' : 'outlined'"
        :color="group.name === defaultGroup?.name ? 'primary' : undefined"
      >
        {{ group.name }}<span class="ocp-dash__now">→ {{ fmtNow(group) }}</span>
      </v-chip>
      <span v-if="groups.length > 10" class="text-caption">+{{ groups.length - 10 }}</span>
    </div>

    <div v-if="defaultGroup" class="ocp-dash__nodes">
      <span class="text-caption ocp-dash__label">{{ defaultGroup.name }} 节点</span>
      <v-chip
        v-for="member in (defaultGroup.members || []).slice(0, 10)"
        :key="member.name"
        size="x-small"
        :variant="member.selected ? 'flat' : 'outlined'"
        :color="member.selected ? 'primary' : undefined"
      >
        {{ member.name }}
      </v-chip>
      <span v-if="(defaultGroup.members || []).length > 10" class="text-caption">
        +{{ (defaultGroup.members || []).length - 10 }}
      </span>
    </div>
  </v-card>
</template>

<style scoped>
.ocp-dash {
  cursor: pointer;
  min-height: 120px;
  border-radius: 12px;
}
.ocp-dash__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
}
.ocp-dash__title {
  font-weight: 600;
  font-size: 15px;
}
.ocp-dash__tag {
  font-size: 11px;
  padding: 0 6px;
  border-radius: 6px;
  background: rgba(128, 128, 128, 0.18);
}
.ocp-dash__net,
.ocp-dash__groups,
.ocp-dash__nodes {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(128, 128, 128, 0.16);
}
.ocp-dash__label {
  opacity: 0.75;
  flex: 0 0 auto;
}
.ocp-dash__netitem {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  white-space: nowrap;
}
.ocp-dash__now {
  opacity: 0.7;
  margin-left: 4px;
  font-size: 11px;
}
.ocp-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex: 0 0 auto;
  background: #9e9e9e;
}
.ocp-dot--ok,
.ocp-dot--success {
  background: #4caf50;
}
.ocp-dot--warning {
  background: #ff9800;
}
.ocp-dot--error,
.ocp-dot--bad {
  background: #f44336;
}
</style>
