<script setup>
import { computed, inject, onMounted, ref, getCurrentInstance } from 'vue'
import Dashboard from './views/Dashboard.vue'
import FontLibrary from './views/FontLibrary.vue'
import Check from './views/Check.vue'
import Settings from './views/Settings.vue'

// 宿主注入的能力
const props = defineProps({
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'Zitifenlei' },
  // 宿主拉取 GET /plugin/form/{id} 返回的合并 model（默认值+已存配置），作为配置唯一数据源
  initialConfig: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'layout', 'close', 'save'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()

// 导航项
const navItems = [
  { key: 'dashboard', title: '仪表盘', icon: 'mdi-view-dashboard-outline' },
  { key: 'fonts', title: '字体库', icon: 'mdi-format-font' },
  { key: 'check', title: '检查', icon: 'mdi-file-document-check-outline' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
]

const active = ref('dashboard')
const loading = ref(true)

// 全局配置：以宿主 initial-config 为准（原生保存后宿主回传的就是这份数据）
const pluginConfig = ref({
  enabled: true,
  input_dir: '',
  lib_dir: '',
  ass_dir: '',
  scan_mode: 'internal',
  archive_mode: 'copy',
  auto_monitor: false,
  auto_check: false,
  notify_enabled: false,
  ...(props.initialConfig || {}),
})
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false)

// 设置页保存回调：仅更新本地开关状态。
// 持久化由设置页 POST /config 交给后端 update_config 完成（对齐 subscribeplus 单通道），
// 不再 emit('save') 转发宿主 PUT，避免双保存冲突。
function onConfigSave(cfg) {
  if (cfg && typeof cfg === 'object') {
    pluginConfig.value = { ...pluginConfig.value, ...cfg }
  }
}

// 视图：点到哪里，右边显示什么
const views = {
  dashboard: Dashboard,
  fonts: FontLibrary,
  check: Check,
  settings: Settings,
}
const currentView = computed(() => views[active.value] || Dashboard)

onMounted(async () => {
  // 通知宿主：最大需要 68rem 宽度
  instance?.emit('layout', { maxWidth: '68rem' })

  try {
    emit('action')
  } catch (e) {
    // 忽略
  } finally {
    loading.value = false
  }
})

function notify(message, type = 'error') {
  if (toast && typeof toast[type] === 'function') {
    toast[type](message)
  }
}

// 关闭插件页（右上角 X）：先走宿主 close 事件，再退浏览器历史兜底
function closePlugin() {
  try {
    emit('close')
  } catch (e) {
    // 忽略
  }
  try {
    if (window.history.length > 1) {
      window.history.back()
    } else if (window.close) {
      window.close()
    }
  } catch (e) {
    // 忽略
  }
}

defineExpose({ notify })
</script>

<template>
  <div class="zt-app">
    <div class="zt-layout">
      <!-- 左侧导航：普通 div，不浮动 -->
      <div class="zt-nav zt-card-bg">
        <div class="zt-nav-header">
          <div class="zt-app-title">
            <v-icon start>mdi-format-font</v-icon>
            字体分类管家
          </div>
          <div class="zt-app-subtitle">Font Manager</div>
        </div>
        <v-divider class="zt-divider"></v-divider>
        <v-list class="zt-nav-list">
          <v-list-item
            v-for="item in navItems"
            :key="item.key"
            :active="active === item.key"
            class="zt-nav-item"
            @click="active = item.key"
          >
            <v-list-item-title class="zt-nav-text">
              <v-icon start :size="18">{{ item.icon }}</v-icon>
              {{ item.title }}
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </div>

      <!-- 右侧内容区：自适应宽度，内部滚动 -->
      <div class="zt-content">
        <v-progress-circular
          v-if="loading"
          indeterminate
          color="primary"
          class="zt-loading"
        ></v-progress-circular>
        <keep-alive v-else>
          <component
            :is="currentView"
            :key="active"
            :api="props.api"
            :target="active"
            :initial-config="pluginConfig"
            :enabled="pluginEnabled"
            @notify="notify"
            @action="emit('action')"
            @save="onConfigSave"
          />
        </keep-alive>
      </div>
    </div>

  <!-- 右上角关闭按钮 -->
  <v-btn
    icon="mdi-close"
    size="small"
    variant="tonal"
    class="zt-close-btn"
    title="关闭插件"
    @click="closePlugin"
  ></v-btn>

  <!-- 插件停用遮罩（其他页不可操作） -->
  <div v-if="!pluginEnabled && active !== 'settings'" class="zt-disabled-mask">
      <div class="zt-disabled-card zt-card-bg">
        <v-icon color="warning" size="44" class="mb-2">mdi-power-off</v-icon>
        <div class="zt-disabled-title">插件已停用</div>
        <div class="zt-disabled-desc">插件已被关闭，其他页面暂不可用</div>
        <v-btn color="primary" variant="tonal" class="mt-3" @click="active = 'settings'">
          <v-icon start size="18">mdi-cog-outline</v-icon>
          前往设置启用
        </v-btn>
      </div>
    </div>
    <!-- 设置页停用横幅 -->
    <v-alert
      v-if="!pluginEnabled && active === 'settings'"
      type="warning"
      density="compact"
      class="zt-disabled-banner"
    >
      插件当前已停用：其他页面不可操作，请在本页开启「插件总开关」并保存。
    </v-alert>
  </div>
</template>

<style>
/* 全局（非 scoped）：深色主题下浅色卡片 + 边框，提升可见性 */
.zt-card-bg {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}
</style>

<style scoped>
/* 根容器：吃满宿主宽度，严禁溢出 */
.zt-app {
  width: 100%;
  height: 100%;
  min-height: 640px;     /* 兜底：即使宿主高度自适应也不塌缩 */
  overflow: hidden;      /* 关键：绝不撑大窗口 */
  box-sizing: border-box;
  position: relative;    /* 停用遮罩的定位基准 */
}

/* Flex 左右布局 */
.zt-layout {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100%;
}

/* 左侧导航：固定宽度，禁止压缩 */
.zt-nav {
  width: 180px;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid rgba(128, 128, 128, 0.25);
  overflow-y: auto;
  box-sizing: border-box;
  padding: 16px 0;
}

.zt-nav-header {
  padding: 0 16px 16px;
}

.zt-app-title {
  font-weight: 600;
  font-size: 16px;
}
.zt-app-subtitle {
  font-size: 12px;
  opacity: 0.7;
}

/* 右侧内容区：吃掉所有剩余空间 */
.zt-content {
  flex-grow: 1;
  flex-shrink: 1;
  height: 100%;
  min-height: 640px;    /* 内容区统一最小高度，任何页面都不再变矮 */
  overflow-y: auto;     /* 内容多了只在右侧内部滚 */
  overflow-x: hidden;
  padding: 20px;
  box-sizing: border-box;
  position: relative;
}

/* 插件停用遮罩 */
.zt-disabled-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
.zt-disabled-card {
  padding: 24px 32px;
  border-radius: 10px;
  text-align: center;
  min-width: 280px;
}
.zt-disabled-title {
  font-size: 17px;
  font-weight: 600;
}
.zt-disabled-desc {
  font-size: 13px;
  opacity: 0.7;
  margin-top: 4px;
}
.zt-disabled-banner {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  z-index: 15;
}
/* 右上角关闭按钮（常驻，悬浮于所有层之上） */
.zt-close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 30;
}

.zt-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
</style>