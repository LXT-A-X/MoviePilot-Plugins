<script setup>
import { computed, inject, onActivated, onMounted, ref, watch, getCurrentInstance } from 'vue'
import apiModule from './api/fontManager.js'
import Dashboard from './views/Dashboard.vue'
import FontLibrary from './views/FontLibrary.vue'
import Check from './views/Check.vue'
import Subset from './views/Subset.vue'
import MissingFonts from './views/MissingFonts.vue'
import Settings from './views/Settings.vue'

// 宿主注入的能力
const props = defineProps({
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'Zitifenlei' },
  // 宿主若传入初始配置则优先使用（配置弹窗场景）；数据页一般无此 prop，由 GET /config 兜底
  initialConfig: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'layout', 'switch', 'close', 'save'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()

// 导航项
const navItems = [
  { key: 'dashboard', title: '仪表盘', icon: 'mdi-view-dashboard-outline' },
  { key: 'fonts', title: '字体库', icon: 'mdi-format-font' },
  { key: 'check', title: '检查', icon: 'mdi-file-document-check-outline' },
  { key: 'subset', title: '子集化', icon: 'mdi-subtitles-outline' },
  { key: 'missing', title: '缺失字体', icon: 'mdi-alert-circle-outline' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
]

const active = ref('dashboard')
const loading = ref(true)
const mobileSheet = ref(false)
// 数据变更信号：任一子视图完成影响共享数据的操作（如仪表盘「重新识别厂商」）后，
// 递推本值通知 keep-alive 缓存中的各视图（字体库/仪表盘）重拉最新数据，
// 不依赖宿主 keep-alive 的 onActivated 行为，关闭再进入也能拿到最新结果
const refreshKey = ref(0)

// 当前导航项（移动端顶部栏展示）
const currentNavItem = computed(() => navItems.find(item => item.key === active.value) || navItems[0])

function gotoNav(key) {
  active.value = key
  mobileSheet.value = false
}

// 全局配置（对齐 subscribeplus：数据页复用配置 UI 时用 GET /config 读取权威初始值）
const DEFAULT_CONFIG = {
  enabled: true,
  input_dir: '',
  lib_dir: '',
  ass_dir: '',
  scan_mode: 'internal',
  archive_mode: 'copy',
  auto_monitor: false,
  auto_check: false,
  notify_enabled: false,
}
const pluginConfig = ref({ ...DEFAULT_CONFIG, ...(props.initialConfig || {}) })
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false)

async function initConfig() {
  try {
    const data = await apiModule.get(props.api, '/config')
    if (data && typeof data === 'object') {
      const { dirs, ...cfg } = data
      pluginConfig.value = { ...pluginConfig.value, ...cfg }
    }
  } catch (e) {
    // 读取失败保持初始配置
  }
}

// 设置页保存回调：
// 1) 更新本地开关状态（停用遮罩即时生效）；
// 2) 补宿主原生 PUT 双通道：总开关改变时，主动调 PUT plugin/{id}（与宿主配置弹窗
//    保存同一条通道，见 MoviePilot-Frontend PluginConfigDialog）——宿主收到自己的
//    PUT 后会把配置写入宿主存储并重新 init_plugin，保证后端状态即时正确，
//    下次进入插件列表/F5 时卡片即显示最新状态。PUT body 为完整配置、同值覆盖，幂等无冲突；
// 3) emit('save') 兜底转发（宿主若不监听则忽略）。
//    持久化主通道仍是设置页 POST /config（后端 update_config 已落盘）。
// 注意：宿主插件详情页是共享 Dialog（keep-alive 列表不会因关闭弹窗而重新拉取，
// 为宿主通用行为），故保存后不自动退出，留在设置页由 toast 提示。
async function onConfigSave(cfg) {
  // 总开关是否发生变化：以合并前 enabled 与合并后为基准
  const prevEnabled = pluginConfig.value.enabled !== false
  if (cfg && typeof cfg === 'object') {
    pluginConfig.value = { ...pluginConfig.value, ...cfg }
  }
  const payload = { ...pluginConfig.value }
  const nextEnabled = payload.enabled !== false
  try {
    // 仅总开关变化时才走宿主通道（其他字段变化不需要刷新卡片状态）
    if (prevEnabled !== nextEnabled && props.api && typeof props.api.put === 'function') {
      await props.api.put(`plugin/${props.pluginId}`, payload)
    }
  } catch (e) {
    // 宿主通道失败不影响本地位与 POST /config 持久化结果
  }
  try {
    emit('save', payload)
  } catch (e) {
    // 宿主不支持转发则忽略
  }
}

// 子视图数据操作完成（如仪表盘重新识别厂商、字体库删除字体等）：递推刷新键
// 让 keep-alive 缓存中的兄弟视图重拉最新数据，再向宿主转发原 action 事件
function handleAction(payload) {
  refreshKey.value++
  // 检查/子集化页「去缺失字体页」：直接切到缺失字体导航
  if (payload && typeof payload === 'object' && payload.type === 'goto_missing') {
    active.value = 'missing'
  }
  emit('action', payload)
}

// 内部 Tab 切到哪个视图都递推一次刷新键：即使宿主 keep-alive 不传播 onActivated，
// keep-alive 缓存中的仪表盘/字体库也会通过 watch(refreshKey) 拿最新数据
watch(() => active.value, () => {
  refreshKey.value++
})

// 宿主详情页为共享 Dialog（keep-alive 缓存）：重新进入插件时强制各视图刷新，
// 确保「重新识别厂商」「外部删除字体文件」等变化在再次打开时立即生效
onActivated(() => {
  refreshKey.value++
})

// 视图：点到哪里，右边显示什么
const views = {
  dashboard: Dashboard,
  fonts: FontLibrary,
  check: Check,
  subset: Subset,
  missing: MissingFonts,
  settings: Settings,
}
const currentView = computed(() => views[active.value] || Dashboard)

onMounted(async () => {
  // 通知宿主：最大需要 68rem 宽度
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
  if (toast && typeof toast[type] === 'function') {
    toast[type](message)
  }
}

// 关闭插件页（右上角 X）：只通知宿主关闭插件弹窗，宿主负责回到插件列表
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
            :enabled="pluginEnabled"
            :refreshKey="refreshKey"
            @notify="notify"
            @action="handleAction"
            @save="onConfigSave"
          />
        </keep-alive>
      </div>
    </div>

    <!-- 移动端顶部导航（窄屏显示，替代左侧栏）：当前项 + 下拉，点按弹出底部面板选择 -->
    <div class="zt-mobile-nav zt-card-bg">
      <button type="button" class="zt-mnav-current" @click="mobileSheet = true">
        <v-icon :size="20">{{ currentNavItem.icon }}</v-icon>
        <span>{{ currentNavItem.title }}</span>
        <v-icon size="16" class="zt-mnav-caret">mdi-chevron-down</v-icon>
      </button>
    </div>

    <!-- 移动端底部选择面板（VBottomSheet）：列出全部导航项，点选切换 -->
    <v-bottom-sheet v-model="mobileSheet" class="zt-sheet">
      <div class="zt-sheet-card zt-card-bg">
        <div class="zt-sheet-title">切换页面</div>
        <v-divider class="zt-divider"></v-divider>
        <v-list class="zt-sheet-list">
          <v-list-item
            v-for="item in navItems"
            :key="item.key"
            :active="active === item.key"
            color="primary"
            rounded="lg"
            class="zt-sheet-item"
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
/* 根容器：吃满宿主宽度，窗口高度固定（不再随页面内容上下跳动） */
.zt-app {
  width: 100%;
  height: min(720px, calc(100vh - 100px));  /* 固定高度：大屏 720px，小屏随视口收缩 */
  min-height: 560px;
  overflow: hidden;      /* 关键：绝不撑大/缩水宿主窗口 */
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

/* 右侧内容区：吃掉所有剩余空间，高度严格跟随 .zt-app（固定窗口），内容多了内部滚 */
.zt-content {
  flex-grow: 1;
  flex-shrink: 1;
  height: 100%;
  min-height: 0;        /* 允许收缩，避免小屏时内容区撑破固定窗口底部被裁剪 */
  overflow-y: auto;     /* 内容多了只在右侧内部滚（用户要的“滑块”） */
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

/* ── 手机端适配（视口媒体查询，对齐 subscribeplus 全屏方案） ── */
.zt-mobile-nav {
  display: none;   /* 默认隐藏，仅窄屏显示 */
}
@media (max-width: 820px) {
  /* 手机端：全屏铺满视口。dvh 随浏览器地址栏动态收缩，竖屏自适应。 */
  .zt-app {
    width: 100%;
    height: 100dvh;
    max-height: 100dvh;
    min-height: 0;
    border-radius: 0;
    display: flex;
    flex-direction: column;
  }
  /* 隐藏左侧导航 */
  .zt-nav {
    display: none;
  }
  /* 布局列向排列：导航在顶部（order:-1），内容区吃满剩余高度 */
  .zt-layout {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    width: 100%;
  }
  /* 内容区吃满剩余空间（flex 链），内部滚动，底部无缝铺到屏幕底 */
  .zt-content {
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 12px 12px 16px;
  }
  /* 移动端导航：固定在顶部，宽度吃满（flex 链式排列），
     右侧留 48px 给右上角关闭按钮；当前项 + 下拉按钮 */
  .zt-mobile-nav {
    display: flex;
    align-items: center;
    flex: 0 0 auto;
    order: -1;
    position: static;
    left: auto;
    right: auto;
    top: auto;
    bottom: auto;
    z-index: 40;
    height: 56px;
    padding: 0 48px 0 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  }
  .zt-mnav-current {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 100%;
    padding: 0 10px;
    background: transparent;
    border: none;
    color: inherit;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
  }
  .zt-mnav-current :deep(.v-icon) {
    color: var(--v-primary-base);
  }
  .zt-mnav-caret {
    opacity: 0.6;
  }
  /* 底部选择面板：切换页面（对齐 subscribeplus 的 VBottomSheet 交互） */
  .zt-sheet-card {
    padding: 12px 16px 20px;
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
  }
  .zt-sheet-title {
    font-size: 15px;
    font-weight: 600;
    padding: 4px 4px 10px;
  }
  .zt-sheet-list {
    padding: 8px 0 4px;
  }
  .zt-sheet-item {
    margin: 2px 4px;
  }
  /* 右上角关闭按钮：悬浮于页面右上角（导航占顶部，但按钮压在其右上角） */
  .zt-close-btn {
    top: 10px;
    right: 10px !important;
    z-index: 50;
  }
  /* 调整停用卡片宽度 */
  .zt-disabled-card {
    min-width: 240px;
    padding: 18px 24px;
  }
}
</style>