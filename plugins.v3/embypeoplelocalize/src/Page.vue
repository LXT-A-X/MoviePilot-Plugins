<script setup>
import { computed, getCurrentInstance, inject, onMounted, ref, watch, onActivated } from 'vue'
import api from './api/client.js'
import Dashboard from './views/DashboardView.vue'
import Library from './views/LibraryView.vue'
import PeoplePool from './views/PeoplePoolView.vue'
import Settings from './views/SettingsView.vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'EmbyPeopleLocalize' },
  sourcePluginId: { type: String, default: '' },
  initialConfig: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'layout', 'close', 'save'])
const instance = getCurrentInstance()
const toast = inject('moviepilot:toast', null)

const pluginConfig = ref({ enabled: true, ...(props.initialConfig || {}) })
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false)

async function initConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await api.get(props.api, '/config')
    if (data && typeof data === 'object') {
      pluginConfig.value = { ...pluginConfig.value, ...data }
    }
  } catch (e) {
    // 读取失败则沿用 initialConfig
  }
}

function onConfigSave(payload) {
  if (payload && typeof payload === 'object') {
    pluginConfig.value = { ...pluginConfig.value, ...payload }
  }
}

const navItems = [
  { key: 'dashboard', title: '仪表盘', icon: 'mdi-view-dashboard-outline' },
  { key: 'library', title: '库', icon: 'mdi-library' },
  { key: 'pool', title: '人名池', icon: 'mdi-account-search' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
]

const active = ref('dashboard')
const loading = ref(true)
const mobileSheet = ref(false)
const refreshKey = ref(0)

const currentNavItem = computed(() => navItems.find(item => item.key === active.value) || navItems[0])

function gotoNav(key) {
  active.value = key
  mobileSheet.value = false
}

const views = { dashboard: Dashboard, library: Library, pool: PeoplePool, settings: Settings }
const currentView = computed(() => views[active.value] || Dashboard)

function notify(message, type = 'error') {
  if (toast && typeof toast[type] === 'function') toast[type](message)
}

function handleAction(payload) {
  refreshKey.value++
  emit('action', payload)
}

watch(() => active.value, () => {
  refreshKey.value++
})

onActivated(() => {
  refreshKey.value++
})

function closePlugin() {
  try {
    emit('close')
  } catch (e) {
    // ignore
  }
}

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '68rem' })
  loading.value = true
  try {
    emit('action')
  } catch (e) {
    // ignore
  } finally {
    loading.value = false
  }
  initConfig()
})
</script>

<template>
  <div class="epl-app">
    <div class="epl-layout">
      <nav class="epl-nav epl-card-bg" aria-label="主导航">
        <div class="epl-nav-header">
          <div class="epl-app-title">
            <v-icon start>mdi-account-group-outline</v-icon>
            演职人员中文化
          </div>
          <div class="epl-app-subtitle">Emby People Localize</div>
        </div>
        <v-divider class="epl-divider"></v-divider>
        <v-list class="epl-nav-list" density="compact" nav>
          <v-list-item
            v-for="item in navItems"
            :key="item.key"
            :active="active === item.key"
            class="epl-nav-item"
            rounded="lg"
            @click="active = item.key"
          >
            <v-list-item-title class="epl-nav-text">
              <v-icon start :size="18">{{ item.icon }}</v-icon>
              {{ item.title }}
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </nav>

      <main class="epl-content">
        <v-progress-circular
          v-if="loading"
          indeterminate
          color="primary"
          class="epl-loading"
        ></v-progress-circular>
        <keep-alive v-else>
          <component
            :is="currentView"
            :key="active"
            :api="props.api"
            :target="active"
            :enabled="pluginEnabled"
            :refresh-key="refreshKey"
            :initial-config="props.initialConfig"
            @notify="notify"
            @action="handleAction"
            @view-task="active = 'dashboard'"
            @save="onConfigSave"
          />
        </keep-alive>
      </main>
    </div>

    <div class="epl-mobile-nav epl-card-bg">
      <button type="button" class="epl-mnav-current" @click="mobileSheet = true">
        <v-icon :size="20">{{ currentNavItem.icon }}</v-icon>
        <span>{{ currentNavItem.title }}</span>
        <v-icon size="16" class="epl-mnav-caret">mdi-chevron-down</v-icon>
      </button>
    </div>

    <v-bottom-sheet v-model="mobileSheet" class="epl-sheet">
      <div class="epl-sheet-card epl-card-bg">
        <div class="epl-sheet-title">切换页面</div>
        <v-divider class="epl-divider"></v-divider>
        <v-list class="epl-sheet-list">
          <v-list-item
            v-for="item in navItems"
            :key="item.key"
            :active="active === item.key"
            color="primary"
            rounded="lg"
            class="epl-sheet-item"
            @click="gotoNav(item.key)"
          >
            <template #prepend>
              <v-icon :size="20">{{ item.icon }}</v-icon>
            </template>
            <v-list-item-title>{{ item.title }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </div>
    </v-bottom-sheet>

    <div v-if="!pluginEnabled && active !== 'settings'" class="epl-disabled-mask">
      <div class="epl-disabled-card epl-card-bg">
        <v-icon color="grey" size="44" class="mb-2">mdi-power-off</v-icon>
        <div class="epl-disabled-title">插件已停用</div>
        <div class="epl-disabled-desc">插件已被关闭，其他页面暂不可用</div>
        <v-btn color="primary" variant="tonal" class="mt-3" @click="active = 'settings'">
          <v-icon start size="18">mdi-cog-outline</v-icon>前往设置启用
        </v-btn>
      </div>
    </div>

    <v-alert
      v-if="!pluginEnabled && active === 'settings'"
      density="compact"
      variant="flat"
      icon="mdi-alert-circle-outline"
      class="epl-disabled-banner"
    >
      插件当前已停用：其他页面不可操作，请在本页开启「插件总开关」并保存。
    </v-alert>

    <v-btn
      icon="mdi-close"
      size="small"
      variant="tonal"
      class="epl-close-btn"
      title="关闭插件"
      aria-label="关闭插件"
      @click="closePlugin"
    ></v-btn>
  </div>
</template>

<style>
.epl-card-bg {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}
</style>

<style scoped>
.epl-app {
  width: 100%;
  max-width: 1080px;
  height: min(760px, calc(100vh - 80px));
  min-height: 480px;
  overflow: hidden;
  box-sizing: border-box;
  position: relative;
  margin: 0 auto;
}

.epl-layout {
  display: flex;
  flex-direction: row;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100%;
}

.epl-nav {
  width: 180px;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid rgba(128, 128, 128, 0.25);
  overflow-y: auto;
  box-sizing: border-box;
  padding: 16px 0;
}

.epl-nav-header {
  padding: 0 16px 16px;
}

.epl-app-title {
  font-weight: 600;
  font-size: 16px;
}
.epl-app-subtitle {
  font-size: 12px;
  opacity: 0.7;
}

.epl-nav-list {
  background: transparent !important;
  padding: 0 8px;
}

.epl-nav-item {
  margin: 2px 0;
}

.epl-nav-text {
  font-size: 14px;
}

.epl-content {
  flex-grow: 1;
  flex-shrink: 1;
  height: 100%;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px;
  box-sizing: border-box;
  position: relative;
}

.epl-close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 30;
}

.epl-disabled-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: rgba(0, 0, 0, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
}

.epl-disabled-card {
  padding: 24px 32px;
  border-radius: 10px;
  text-align: center;
  min-width: 280px;
  background: rgba(22, 24, 28, 0.94) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

.epl-disabled-title {
  font-size: 17px;
  font-weight: 600;
}

.epl-disabled-desc {
  font-size: 13px;
  opacity: 0.7;
  margin-top: 4px;
}

.epl-disabled-banner {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 48px;
  z-index: 15;
  background: #202124 !important;
  color: #e8eaed !important;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  font-size: 12px !important;
}

.epl-disabled-banner :deep(.v-alert__icon) {
  color: #e8eaed !important;
}

.epl-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.epl-mobile-nav {
  display: none;
}

@media (min-width: 821px) and (max-width: 1024px) {
  .epl-nav {
    width: 168px;
  }

  .epl-content {
    padding: 16px;
  }
}

@media (max-width: 820px) {
  .epl-app {
    width: 100%;
    max-width: none;
    height: 100dvh;
    max-height: 100dvh;
    min-height: 0;
    border-radius: 0;
    display: flex;
    flex-direction: column;
  }

  .epl-nav {
    display: none;
  }

  .epl-layout {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    width: 100%;
  }

  .epl-content {
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 10px 12px 16px;
  }

  .epl-mobile-nav {
    display: flex;
    align-items: center;
    flex: 0 0 auto;
    order: -1;
    position: static;
    z-index: 40;
    height: 52px;
    padding: 0 44px 0 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  }

  .epl-mnav-current {
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

  .epl-mnav-current :deep(.v-icon) {
    color: var(--v-primary-base);
  }

  .epl-mnav-caret {
    opacity: 0.6;
  }

  .epl-sheet-card {
    padding: 12px 16px 20px;
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
  }

  .epl-sheet-title {
    font-size: 15px;
    font-weight: 600;
    padding: 4px 4px 10px;
  }

  .epl-sheet-list {
    padding: 8px 0 4px;
  }

  .epl-sheet-item {
    margin: 2px 4px;
  }

  .epl-close-btn {
    top: 10px;
    right: 10px !important;
    z-index: 50;
  }

  .epl-disabled-card {
    min-width: 240px;
    padding: 18px 24px;
  }
}

@media (max-width: 400px) {
  .epl-content {
    padding: 8px 8px 14px;
  }

  .epl-mobile-nav {
    height: 50px;
    padding-left: 6px;
    padding-right: 42px;
  }

  .epl-mnav-current {
    padding: 0 6px;
    font-size: 14px;
  }

  .epl-close-btn {
    top: 7px;
    right: 6px !important;
  }
}

@media (max-width: 340px) {
  .epl-content {
    padding-left: 6px;
    padding-right: 6px;
  }

  .epl-app-title {
    font-size: 15px;
  }

  .epl-mnav-current {
    font-size: 13.5px;
    gap: 4px;
  }
}
</style>
