<script setup>
import { computed, onActivated, onMounted, onUnmounted, ref, watch } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  // 插件总开关（声明用于避免 attrs 落到根元素）
  enabled: { type: Boolean, default: true },
  // 数据变更信号（Page 递推）：字体库删除字体等操作后，本页重拉统计/厂商分布
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

const loading = ref(true)
const stats = ref({ total: 0, pending: 0, archived: 0, error: 0, db_ok: true, last_scan: '' })
const vendors = ref([])
const dirs = ref([])
const logs = ref([])
// 运行依赖检测：fontTools / watchdog / SQLite
const deps = ref({ items: [], ok_count: 0, total: 0 })
const depsDialog = ref(false)
const depsLoading = ref(false)

let refreshTimer = null

async function loadDeps() {
  depsLoading.value = true
  try {
    const data = await apiModule.get(props.api, '/deps/check')
    deps.value = data && data.items ? data : { items: [], ok_count: 0, total: 0 }
  } catch (e) {
    // 接口异常不打扰
  } finally {
    depsLoading.value = false
  }
}

const depsOk = computed(() => deps.value.total > 0 && deps.value.ok_count === deps.value.total)

async function loadStats() {
  try {
    stats.value = await apiModule.get(props.api, '/stats')
  } catch (e) {
    emit('notify', e.message || '加载统计失败')
  }
}

async function loadVendors() {
  try {
    vendors.value = await apiModule.get(props.api, '/vendors')
  } catch (e) {
    // 忽略
  }
}

async function loadConfig() {
  try {
    const cfg = await apiModule.get(props.api, '/config')
    dirs.value = cfg.dirs || []
  } catch (e) {
    // 忽略
  }
}

async function loadLogs() {
  try {
    logs.value = await apiModule.get(props.api, '/logs', { limit: 10 })
  } catch (e) {
    // 忽略
  }
}

function refreshAll() {
  loadStats()
  loadVendors()
  loadLogs()
}

onMounted(() => {
  loadStats()
  loadVendors()
  loadConfig()
  loadLogs()
  loadDeps()
  refreshTimer = setInterval(loadLogs, 30000)
})

// 从其他 Tab 直接切回仪表盘（keep-alive 缓存场景）时重拉统计/厂商分布/日志：
// 切 Tab 本身不会推进 refreshKey，必须有 onActivated 兜底才能拿到最新分布
onActivated(() => {
  loadStats()
  loadVendors()
  loadConfig()
  loadLogs()
  loadDeps()
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

// 兄弟页完成数据变更（如字体库删除字体→ Page 递推 refreshKey）：重拉统计与厂商分布
watch(() => props.refreshKey, () => {
  loadStats()
  loadVendors()
  loadConfig()
})
</script>

<template>
  <div class="zt-dashboard">
    <!-- 状态条：优先反映插件启停状态 -->
    <v-alert
      :type="!enabled ? 'warning' : (stats.db_ok ? 'success' : 'error')"
      variant="tonal"
      class="mb-4 zt-status-bar"
      density="compact"
    >
      <div class="d-flex align-center flex-wrap">
        <span class="mr-6">
          <v-icon :size="16">{{ enabled ? 'mdi-server' : 'mdi-power-off' }}</v-icon>
          服务状态：
          <b>{{ !enabled ? '已停用' : (stats.db_ok ? '运行中' : '异常') }}</b>
        </span>
        <span class="mr-6">
          <v-icon :size="16">mdi-clock-outline</v-icon>
          上次全量检查：{{ stats.last_scan || '从未' }}
        </span>
        <span>
          <v-icon :size="16">mdi-database-check</v-icon>
          数据库：
          <b :class="stats.db_ok ? 'text-success' : 'text-error'">
            {{ stats.db_ok ? '正常' : '错误' }}
          </b>
        </span>
        <span
          class="zt-deps-tag"
          :class="!depsLoading && !depsOk ? 'text-error' : 'text-success'"
          title="点击查看依赖明细"
          @click="depsDialog = true"
        >
          <v-icon :size="16">{{ depsLoading ? 'mdi-loading mdi-spin' : (depsOk ? 'mdi-check-circle' : 'mdi-alert-circle') }}</v-icon>
          依赖：
          <b>{{ depsLoading ? '检测中…' : (depsOk ? '正常' : '异常') }}</b>
        </span>
      </div>
    </v-alert>

    <!-- 运行依赖明细 -->
    <v-dialog v-model="depsDialog" max-width="440">
      <v-card class="zt-card-bg">
        <v-card-title class="zt-card-title">
          <v-icon start size="18">mdi-package-variant-closed</v-icon>
          运行依赖
          <v-spacer></v-spacer>
          <v-btn size="small" variant="tonal" :loading="depsLoading" @click="loadDeps">
            <v-icon start size="14">mdi-refresh</v-icon>
            重新检测
          </v-btn>
        </v-card-title>
        <v-card-text class="pt-0">
          <div v-if="!deps.value.items.length" class="zt-empty pa-4">暂未检测</div>
          <v-list v-else density="compact" lines="two" class="pa-0">
            <v-list-item v-for="d in deps.value.items" :key="d.key">
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
          <div class="zt-deps-hint text-body-2">
            依赖由 MoviePilot 安装插件时按 requirements.txt 自动安装；缺失时功能降级（见各项说明）。
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 统计卡片 -->
    <v-row>
      <v-col cols="6" sm="6" md="3">
        <v-card class="zt-card-bg zt-stat-card">
          <v-card-text class="text-center pa-4">
            <div class="zt-stat-value text-primary">{{ stats.total }}</div>
            <div class="zt-stat-label">字体总数</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="6" sm="6" md="3">
        <v-card class="zt-card-bg zt-stat-card">
          <v-card-text class="text-center pa-4">
            <div class="zt-stat-value text-warning">{{ stats.pending }}</div>
            <div class="zt-stat-label">待整理</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="6" sm="6" md="3">
        <v-card class="zt-card-bg zt-stat-card">
          <v-card-text class="text-center pa-4">
            <div class="zt-stat-value text-success">{{ stats.subset ?? stats.archived }}</div>
            <div class="zt-stat-label">最近子集化数量</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="6" sm="6" md="3">
        <v-card class="zt-card-bg zt-stat-card">
          <v-card-text class="text-center pa-4">
            <div class="zt-stat-value text-error">{{ stats.error }}</div>
            <div class="zt-stat-label">缺失字体</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 厂商分布 + 目录健康度 -->
    <v-row class="mt-2">
      <v-col cols="12" md="6">
        <v-card class="zt-card-bg zt-mid-card">
          <v-card-title class="zt-card-title">
            <v-icon start size="18">mdi-chart-bar</v-icon>
            厂商分布
            <span v-if="vendors.length" class="zt-vendor-total">{{ vendors.length }} 家</span>
          </v-card-title>
          <v-card-text class="zt-scroll-body">
            <div v-if="!vendors.length" class="zt-empty mt-2">暂无数据</div>
            <div v-else class="zt-vendor-container">
              <div v-for="item in vendors" :key="item.vendor" class="zt-vendor-row">
                <div class="zt-vendor-head">
                  <span class="zt-vendor-name" :title="item.vendor">{{ item.vendor }}</span>
                  <span class="zt-vendor-count">{{ item.count }}</span>
                </div>
                <div class="zt-vendor-bar-bg">
                  <div
                    class="zt-vendor-bar"
                    :style="{ width: item.percent + '%' }"
                  ></div>
                </div>
                <div class="zt-vendor-percent">{{ item.percent }}%</div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="zt-card-bg zt-mid-card">
          <v-card-title class="zt-card-title">
            <v-icon start size="18">mdi-folder-outline</v-icon>
            目录健康度
          </v-card-title>
          <v-card-text class="zt-scroll-body zt-dir-list">
            <div v-if="!dirs.length" class="zt-empty mt-2">
              尚未在设置中配置目录
            </div>
            <div v-for="dir in dirs" :key="dir.path" class="zt-dir-item">
              <v-icon
                :size="16"
                :class="dir.exists ? 'text-success' : 'text-error'"
                class="mr-2"
              >
                {{ dir.exists ? 'mdi-check-circle' : 'mdi-alert-circle' }}
              </v-icon>
              <div class="flex-grow-1">
                <div class="zt-dir-label">{{ dir.label }}</div>
                <div class="zt-dir-path text-body-2">
                  {{ dir.path || '(未配置)' }}
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 最近操作日志 -->
    <v-card class="zt-card-bg mt-4 zt-log-card">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-text-box-outline</v-icon>
        最近操作日志
      </v-card-title>
      <v-card-text class="pt-0 zt-scroll-body">
        <div v-if="!logs.length" class="zt-empty">暂无日志</div>
        <v-table density="compact">
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td class="zt-log-time">{{ log.time }}</td>
              <td>
                <v-chip
                  size="x-small"
                  :color="log.level === 'error' ? 'error' : log.level === 'warning' ? 'warning' : 'info'"
                  variant="tonal"
                  class="mr-2 zt-log-level"
                >
                  {{ log.level.toUpperCase() }}
                </v-chip>
                <span class="zt-log-message">{{ log.message }}</span>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
    </v-card>
  </div>
</template>

<style scoped>
.zt-status-bar :deep(.v-alert__content) {
  font-size: 13px;
}
.zt-deps-tag {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 24px;
}
.zt-deps-hint {
  opacity: 0.6;
  font-size: 12px;
  margin-top: 8px;
  padding: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.zt-stat-value {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.2;
}
.zt-stat-label {
  font-size: 13px;
  opacity: 0.75;
  margin-top: 4px;
}
.zt-card-title {
  font-size: 15px;
  font-weight: 600;
}
/* 固定高度 + 内部滚动（滑块），防止 UI 被内容拉长 */
.zt-mid-card {
  height: 260px;
  display: flex;
  flex-direction: column;
}
.zt-log-card {
  height: 300px;
  display: flex;
  flex-direction: column;
}
.zt-scroll-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.zt-vendor-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 6px;
  max-height: 100%;
  scrollbar-width: thin;
}
.zt-vendor-row {
  flex: 0 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid rgba(128, 128, 128, 0.16);
  border-radius: 8px;
  background: rgba(128, 128, 128, 0.06);
  box-sizing: border-box;
}
.zt-vendor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.zt-vendor-name {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.zt-vendor-bar-bg {
  width: 100%;
  height: 10px;
  border-radius: 5px;
  background: rgba(128, 128, 128, 0.18);
  overflow: hidden;
}
.zt-vendor-bar {
  height: 100%;
  border-radius: 5px;
  background: linear-gradient(90deg, #5c6bc0, #42a5f5);
}
.zt-vendor-count {
  flex-shrink: 0;
  font-size: 13px;
}
.zt-vendor-percent {
  font-size: 12px;
  opacity: 0.7;
}
.zt-vendor-total {
  font-size: 12px;
  opacity: 0.6;
  margin-left: 4px;
  font-weight: 400;
}
.zt-dir-item {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}
.zt-dir-label {
  font-size: 13px;
  font-weight: 500;
}
.zt-dir-path {
  opacity: 0.7;
  word-break: break-all;
}
.zt-log-time {
  width: 160px;
  white-space: nowrap;
  font-size: 12px;
  opacity: 0.75;
}
.zt-log-level {
  width: 70px;
}
.zt-log-message {
  font-size: 13px;
}
.zt-empty {
  font-size: 13px;
  opacity: 0.6;
  text-align: center;
}
</style>