<script setup>
import { computed, inject, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import api from '../api.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'save'])
const toast = inject('moviepilot:toast', null)

const status = ref(null)
const missing = ref([])
const logs = ref([])
const logBox = ref(null)
const followLog = ref(true)
const busy = ref(false)
const refreshing = ref(false)
let timer = null
let logTimer = null

// ---- 状态卡计算（正常绿 / 异常红）----
const idxReady = computed(() => status.value?.index?.ready === true)
const idxScanning = computed(() => status.value?.index?.scanning === true)
const idxHasDirs = computed(() => (status.value?.index?.dirs?.length ?? 0) > 0)
const idxFaces = computed(() => status.value?.index?.faces ?? 0)
const ftVer = computed(() => status.value?.fonttools_version ?? '?')
const hbVer = computed(() => status.value?.uharfbuzz_version ?? '?')
const idxSub = computed(() => {
  if (idxReady.value) {
    const hbTxt = hbVer.value && hbVer.value !== '?'
      ? ` · uharfbuzz ${hbVer.value}`
      : ' · uharfbuzz 未安装（fontTools 兜底）'
    return '就绪 · fontTools ' + ftVer.value + hbTxt
  }
  if (idxScanning.value) return '扫描中… 已 ' + idxFaces.value + ' 个字体'
  if (idxHasDirs.value) return '等待扫描'
  return '未配置字体目录'
})
const idxColor = computed(() => idxReady.value ? 'success' : 'error')
const proxyOn = computed(() => status.value?.internal_proxy?.enabled === true)
const proxyPort = computed(() => status.value?.internal_proxy?.port ?? null)
const cacheOn = computed(() => !!status.value?.cache?.disk_dir)
const cacheTotal = computed(() => (status.value?.cache?.mem_items ?? 0) + (status.value?.cache?.disk_files ?? 0))
const missTotal = computed(() => status.value?.missing ?? 0)
// 日志有 error 级时视为异常（红），仅 warning 黄色
const logBad = computed(() => logs.value.some(l => (l.level || '') === 'error'))
const logWarn = computed(() => !logBad.value && logs.value.some(l => (l.level || '') === 'warning'))

function fmtTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function toastMsg(type, message) {
  if (toast && typeof toast[type] === 'function') toast[type](message)
}

async function loadStatus() {
  try {
    status.value = await api.get(props.api, '/status')
  } catch (e) {
    toastMsg('error', '获取状态失败: ' + e.message)
  }
}

async function loadMissing() {
  try {
    missing.value = (await api.get(props.api, '/missing')) || []
  } catch (e) {
    toastMsg('error', '获取缺失字体失败: ' + e.message)
  }
}

async function loadLogs() {
  try {
    logs.value = (await api.get(props.api, '/logs', { lines: 300 })) || []
  } catch (e) {
    // 日志读取失败不打扰
  }
  if (followLog.value && logBox.value) {
    await nextTick()
    logBox.value.scrollTop = logBox.value.scrollHeight
  }
}

function onLogScroll() {
  const el = logBox.value
  if (!el) return
  followLog.value = (el.scrollHeight - el.scrollTop - el.clientHeight) < 40
}

async function refresh() {
  refreshing.value = true
  await Promise.all([loadStatus(), loadMissing(), loadLogs()])
  refreshing.value = false
}

async function rebuild() {
  busy.value = true
  try {
    const res = await api.post(props.api, '/rebuild')
    toastMsg('success', res?.message || '字体索引已重建')
    await refresh()
  } catch (e) {
    toastMsg('error', e.message)
  } finally {
    busy.value = false
  }
}

async function clearMissing() {
  if (!missing.value.length) return
  busy.value = true
  try {
    const res = await api.post(props.api, '/missing/clear')
    toastMsg('success', res?.message || '缺失字体记录已清除')
    missing.value = []
    await loadStatus()
  } catch (e) {
    toastMsg('error', e.message)
  } finally {
    busy.value = false
  }
}

async function clearLogs() {
  busy.value = true
  try {
    const res = await api.post(props.api, '/logs/clear')
    toastMsg('success', res?.message || '插件日志已清除')
    logs.value = []
  } catch (e) {
    toastMsg('error', e.message)
  } finally {
    busy.value = false
  }
}

async function clearCache() {
  busy.value = true
  try {
    const res = await api.post(props.api, '/clear_cache')
    toastMsg('success', res?.message || '缓存已清空')
    await refresh()
  } catch (e) {
    toastMsg('error', e.message)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  refresh()
})
onActivated(() => {
  // 从其他页（设置）切回状态页时：立即拉最新数据并重启定时器，
  // 避免 keep-alive 缓存导致界面停留在旧数据
  refresh()
  if (!timer) timer = setInterval(refresh, 10000)
  if (!logTimer) logTimer = setInterval(loadLogs, 8000)
})
onDeactivated(() => {
  if (timer) { clearInterval(timer); timer = null }
  if (logTimer) { clearInterval(logTimer); logTimer = null }
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (logTimer) clearInterval(logTimer)
})
</script>

<template>
  <div>
    <!-- 操作行：刷新 + 清空缓存 + 重建索引（右侧留白避开关闭按钮） -->
    <v-row class="align-center mb-3" no-gutters style="padding-right: 48px;">
      <v-btn size="small" variant="flat" prepend-icon="mdi-refresh" :loading="refreshing" @click="refresh">刷新</v-btn>
      <v-spacer />
      <v-btn size="small" color="error" variant="flat" prepend-icon="mdi-cached" :disabled="busy" class="mr-2"
             @click="clearCache">清空字幕缓存</v-btn>
      <v-btn size="small" color="primary" variant="flat" prepend-icon="mdi-database-sync"
             :disabled="busy || !status?.index?.ready" @click="rebuild">重建字体索引</v-btn>
    </v-row>

    <!-- 等高统计卡（正常绿 / 异常红） -->
    <v-row dense>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="tonal" class="fill-height">
          <v-card-text>
            <div class="text-subtitle-2 text-medium-emphasis d-flex align-center">
              <v-icon :size="16" :color="idxColor" class="mr-1">mdi-circle</v-icon>
              字体索引
            </div>
            <div class="text-h6 mt-1" :class="idxReady ? 'text-success' : 'text-error'">{{ idxFaces }} <span class="text-caption text-medium-emphasis">个字体</span></div>
            <div class="text-caption text-medium-emphasis">{{ idxSub }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="tonal" class="fill-height">
          <v-card-text>
            <div class="text-subtitle-2 text-medium-emphasis d-flex align-center">
              <v-icon :size="16" :color="proxyOn ? 'success' : 'error'" class="mr-1">mdi-circle</v-icon>
              反代端口
            </div>
            <div class="text-h6 mt-1" :class="proxyOn ? 'text-success' : 'text-error'">{{ proxyOn ? proxyPort : '未启用' }}</div>
            <div class="text-caption text-medium-emphasis text-truncate">{{ status?.emby_url || '未配置回源' }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="tonal" class="fill-height">
          <v-card-text>
            <div class="text-subtitle-2 text-medium-emphasis d-flex align-center">
              <v-icon :size="16" :color="cacheOn ? 'success' : 'error'" class="mr-1">mdi-circle</v-icon>
              字幕缓存
            </div>
            <div class="text-h6 mt-1" :class="cacheOn ? 'text-success' : 'text-error'">{{ cacheTotal }} <span class="text-caption text-medium-emphasis">条</span></div>
            <div class="text-caption text-medium-emphasis">内存 {{ status?.cache?.mem_items ?? 0 }} · 磁盘 {{ status?.cache?.disk_files ?? 0 }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="tonal" class="fill-height">
          <v-card-text>
            <div class="text-subtitle-2 text-medium-emphasis d-flex align-center">
              <v-icon :size="16" :color="missTotal === 0 ? 'success' : 'error'" class="mr-1">mdi-circle</v-icon>
              缺失字体
            </div>
            <div class="text-h6 mt-1" :class="missTotal === 0 ? 'text-success' : 'text-error'">{{ missTotal }} <span class="text-caption text-medium-emphasis">种</span></div>
            <div class="text-caption text-medium-emphasis">最近 {{ status?.miss_count ?? 0 }} 次命中</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 缺失字体记录（内部滚动） -->
    <v-card variant="tonal" class="mt-4">
      <v-card-title class="text-subtitle-1 d-flex align-center">
        缺失字体记录
        <v-spacer />
        <v-btn size="small" color="error" variant="flat" density="comfortable" prepend-icon="mdi-delete-outline"
               :disabled="busy || missing.length === 0" @click="clearMissing">清除</v-btn>
      </v-card-title>
      <v-card-text class="fia-list-wrap">
        <v-table v-if="missing.length" density="compact">
          <thead>
            <tr>
              <th>字体名</th>
              <th class="text-center">出现次数</th>
              <th class="text-center">最近出现</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in missing" :key="m.font_name">
              <td>{{ m.font_name }}</td>
              <td class="text-center">{{ m.count }}</td>
              <td class="text-center">{{ fmtTime(m.last_seen) }}</td>
            </tr>
          </tbody>
        </v-table>
        <v-alert v-else type="info" variant="tonal" density="compact" class="mb-0">暂无缺失字体记录</v-alert>
      </v-card-text>
    </v-card>

    <!-- 插件日志（对齐 zitifenlei：时间 + 级别标签，高度 300px 内部滚动） -->
    <v-card variant="tonal" class="mt-4 fia-log-card">
      <v-card-title class="text-subtitle-1 d-flex align-center">
        <v-icon :size="14" :color="logBad ? 'error' : logWarn ? 'warning' : 'success'" class="mr-1">mdi-circle</v-icon>
        插件日志
        <v-spacer />
        <v-btn size="small" color="error" variant="flat" density="comfortable" prepend-icon="mdi-delete-outline"
               :disabled="busy" class="mr-1" @click="clearLogs">清除</v-btn>
      </v-card-title>
      <v-card-text class="pa-0 fia-log-body">
        <div ref="logBox" class="fia-log-box" @scroll="onLogScroll">
          <div v-if="logs.length === 0" class="fia-empty">
            暂无插件日志（播放字幕产生 FontInAssProxy 日志后显示）
          </div>
          <v-table v-else density="compact" class="fia-log-table">
            <tbody>
              <tr v-for="l in logs" :key="l.id">
                <td class="fia-log-time">{{ l.time }}</td>
                <td>
                  <v-chip size="x-small" variant="tonal" class="mr-2 fia-log-level"
                          :color="l.level === 'error' ? 'error' : l.level === 'warning' ? 'warning' : 'info'">
                    {{ (l.level || 'info').toUpperCase() }}
                  </v-chip>
                  <span class="fia-log-message">{{ l.message }}</span>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-card-text>
    </v-card>

  </div>
</template>

<style scoped>
/* 列表容器：限制高度、内部滚动（缺失字体用） */
.fia-list-wrap {
  max-height: 400px;
  overflow-y: auto;
  padding-top: 0 !important;
  padding-bottom: 8px !important;
}
/* 日志卡片（对齐 zitifenlei：固定 300px 高 + 内部滚动） */
.fia-log-card {
  height: 300px;
  display: flex;
  flex-direction: column;
}
.fia-log-body {
  flex: 1;
  min-height: 0;
}
.fia-log-box {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
}
.fia-log-table {
  width: 100%;
}
.fia-log-table :deep(td) {
  padding: 4px 8px;
}
.fia-log-time {
  width: 150px;
  min-width: 150px;
  white-space: nowrap;
  font-size: 12px;
  opacity: 0.75;
}
.fia-log-level {
  width: 64px;
  min-width: 64px;
}
.fia-log-message {
  font-size: 13px;
  word-break: break-all;
}
.fia-empty {
  font-size: 13px;
  opacity: 0.6;
  text-align: center;
  padding: 16px;
}
</style>