<script setup>
import { computed, inject, onMounted, ref, getCurrentInstance } from 'vue'
import apiModule from './api.js'
import Status from './views/Status.vue'
import Settings from './views/Settings.vue'

// 宿主注入的能力（对齐 zitifenlei 契约）
const props = defineProps({
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'FontInAssProxy' },
  initialConfig: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'layout', 'switch', 'close', 'save'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()

// 导航项：设置页入口放在导航里，不再“看不见”
const navItems = [
  { key: 'status', title: '状态', icon: 'mdi-view-dashboard-outline' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
]

const active = ref('status')
const loading = ref(true)
const mobileSheet = ref(false)

// 当前导航项（移动端顶部栏展示）
const currentNavItem = computed(() => navItems.find(item => item.key === active.value) || navItems[0])

function gotoNav(key) {
  active.value = key
  mobileSheet.value = false
}

// 全局配置：以 GET /config 为权威（重启/热生效后重新拉取）
const pluginConfig = ref({
  enabled: true,
  ...(props.initialConfig || {}),
})
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false)

async function initConfig() {
  try {
    const data = await apiModule.get(props.api, '/config')
    if (data && typeof data === 'object') {
      pluginConfig.value = { ...pluginConfig.value, ...data }
    }
  } catch (e) {
    // 读取失败保持初始配置
  }
}

// 设置页保存回调：更新本地开关状态（停用遮罩即时生效），转发宿主 save
function onConfigSave() {
  emit('save')
  initConfig()
}

// 视图映射：点击导航切换
const views = {
  status: Status,
  settings: Settings,
}
const currentView = computed(() => views[active.value] || Status)

onMounted(async () => {
  // 通知宿主：最大需要 68rem 宽度（与字体分类管家一致）
  instance?.emit('layout', { maxWidth: '68rem' })
  initConfig()
  try {
    emit('action')
  } catch (e) {
    // 忽略
  } finally {
    loading.value = false
  }
})

function notify(message, type = 'error') {
  if (toast && typeof toast[type] === 'function') toast[type](message)
}

// 关闭插件页（右上角 X）
function closePlugin() {
  try {
    emit('close')
  } catch (e) {
    // 忽略
  }
}

defineExpose({ notify })
</script>

<template>
  <div class="ffa-app">
    <div class="ffa-layout">
      <!-- 左侧导航 -->
      <div class="ffa-nav ffa-card-bg">
        <div class="ffa-nav-header">
          <div class="ffa-app-title">
            <v-icon start>mdi-subtitles-outline</v-icon>
            字幕字体代理
          </div>
          <div class="ffa-app-subtitle">FontInAssProxy</div>
        </div>
        <v-divider class="ffa-divider"></v-divider>
        <v-list class="ffa-nav-list">
          <v-list-item
            v-for="item in navItems"
            :key="item.key"
            :active="active === item.key"
            class="ffa-nav-item"
            @click="active = item.key"
          >
            <v-list-item-title class="ffa-nav-text">
              <v-icon start :size="18">{{ item.icon }}</v-icon>
              {{ item.title }}
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </div>

      <!-- 右侧内容区：自适应宽度，内部滚动 -->
      <div class="ffa-content">
        <v-progress-circular
          v-if="loading"
          indeterminate
          color="primary"
          class="ffa-loading"
        ></v-progress-circular>
        <keep-alive v-else>
          <component
            :is="currentView"
            :api="props.api"
            @save="onConfigSave"
          />
        </keep-alive>
      </div>
    </div>

    <!-- 移动端顶部导航（窄屏显示，替代左侧栏） -->
    <div class="ffa-mobile-nav ffa-card-bg">
      <button type="button" class="ffa-mnav-current" @click="mobileSheet = true">
        <v-icon :size="20">{{ currentNavItem.icon }}</v-icon>
        <span>{{ currentNavItem.title }}</span>
        <v-icon size="16" class="ffa-mnav-caret">mdi-chevron-down</v-icon>
      </button>
    </div>

    <!-- 移动端底部选择面板 -->
    <v-bottom-sheet v-model="mobileSheet" class="ffa-sheet">
      <div class="ffa-sheet-card ffa-card-bg">
        <div class="ffa-sheet-title">切换页面</div>
        <v-divider class="ffa-divider"></v-divider>
        <v-list class="ffa-sheet-list">
          <v-list-item
            v-for="item in navItems"
            :key="item.key"
            :active="active === item.key"
            color="primary"
            rounded="lg"
            class="ffa-sheet-item"
            @click="gotoNav(item.key)"
          >
            <template #prepend><v-icon :size="20">{{ item.icon }}</v-icon></template>
            <v-list-item-title class="font-weight-medium">{{ item.title }}</v-list-item-title>
            <template v-if="active === item.key" #append>
              <v-icon color="primary">mdi-check</v-icon>
            </template>
          </v-list-item>
        </v-list>
      </div>
    </v-bottom-sheet>

    <!-- 右上角关闭按钮 -->
    <v-btn
      icon="mdi-close"
      size="small"
      variant="tonal"
      class="ffa-close-btn"
      title="关闭插件"
      @click="closePlugin"
    ></v-btn>

    <!-- 插件停用遮罩（设置页除外） -->
    <div v-if="!pluginEnabled && active !== 'settings'" class="ffa-disabled-mask">
      <div class="ffa-disabled-card ffa-card-bg">
        <v-icon color="warning" size="44" class="mb-2">mdi-power-off</v-icon>
        <div class="ffa-disabled-title">插件已停用</div>
        <div class="ffa-disabled-desc">插件已被关闭，代理链路暂停，其他页面暂不可用</div>
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
      class="ffa-disabled-banner"
    >
      插件当前已停用：字幕请求将原样透传，请在本页开启「启用插件」并保存。
    </v-alert>
  </div>
</template>

<style>
/* 全局（非 scoped）：深色主题下浅色卡片 + 边框，提升可见性（对齐字体分类管家） */
.ffa-card-bg {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}
</style>

<style scoped>
/* 根容器：吃满宿主宽度，窗口高度固定 */
.ffa-app {
  width: 100%;
  height: min(720px, calc(100vh - 100px));
  min-height: 560px;
  overflow: hidden;
  box-sizing: border-box;
  position: relative;
}

/* Flex 左右布局 */
.ffa-layout {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100%;
}

/* 左侧导航：固定宽度 180px（同字体分类管家） */
.ffa-nav {
  width: 180px;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid rgba(128, 128, 128, 0.25);
  overflow-y: auto;
  box-sizing: border-box;
  padding: 16px 0;
}

.ffa-nav-header {
  padding: 0 16px 16px;
}

.ffa-app-title {
  font-weight: 600;
  font-size: 16px;
}
.ffa-app-subtitle {
  font-size: 12px;
  opacity: 0.7;
}

/* 右侧内容区：吃满剩余空间，内部滚动 */
.ffa-content {
  flex-grow: 1;
  flex-shrink: 1;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px;
  box-sizing: border-box;
  position: relative;
}

/* 插件停用遮罩 */
.ffa-disabled-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ffa-disabled-card {
  padding: 24px 32px;
  border-radius: 10px;
  text-align: center;
  min-width: 280px;
}
.ffa-disabled-title {
  font-size: 17px;
  font-weight: 600;
}
.ffa-disabled-desc {
  font-size: 13px;
  opacity: 0.7;
  margin-top: 4px;
}
.ffa-disabled-banner {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  z-index: 15;
}
/* 右上角关闭按钮（常驻） */
.ffa-close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 30;
}

.ffa-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

/* ── 手机端适配 ── */
.ffa-mobile-nav {
  display: none;
}
@media (max-width: 820px) {
  .ffa-app {
    width: 100%;
    height: 100dvh;
    max-height: 100dvh;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .ffa-nav {
    display: none;
  }
  .ffa-layout {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    width: 100%;
  }
  .ffa-content {
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 12px 12px 16px;
  }
  .ffa-mobile-nav {
    display: block;
    flex: 0 0 auto;
  }
  .ffa-mnav-current {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    gap: 8px;
    padding: 12px;
    background: transparent;
    border: none;
    color: inherit;
    font-size: 15px;
    font-weight: 600;
  }
  .ffa-mnav-caret {
    opacity: 0.6;
  }
}
</style>