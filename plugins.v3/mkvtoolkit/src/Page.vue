<script setup>
import AppPage from './AppPage.vue'

// 宿主注入契约：api / pluginId / navKey / initialConfig / nativeSubscribe
const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MkvToolkit' },
  navKey: { type: String, default: 'main' },
  initialConfig: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
})

const emit = defineEmits(['action', 'close', 'switch'])
</script>

<template>
  <AppPage
    :api="props.api"
    :plugin-id="props.pluginId"
    :nav-key="props.navKey"
    :initial-config="props.initialConfig"
    :native-subscribe="props.nativeSubscribe"
    :show-close="true"
    @action="emit('action')"
    @close="emit('close')"
    @switch="emit('switch')"
  />
</template>
