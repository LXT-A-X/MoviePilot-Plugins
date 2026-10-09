<script setup>
import { inject, onMounted, ref } from 'vue'
import api from './api/client.js'

const props = defineProps({
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'EmbyPeopleLocalize' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
})
const emit = defineEmits(['action'])
const loading = ref(true)
const db = ref(null)

async function load() {
  loading.value = true
  try { db.value = await api.get(props.api, '/db/stats') }
  catch (e) { db.value = null }
  loading.value = false
}
onMounted(load)
</script>

<template>
  <v-hover>
    <template #default="{ isHovering, props: hoverProps }">
      <v-card v-bind="hoverProps" class="w-100">
        <v-card-text class="text-center pa-4">
          <v-progress-circular v-if="loading" indeterminate size="32" color="primary"></v-progress-circular>
          <template v-else>
            <div class="text-h5">{{ db?.item_count ?? 0 }}</div>
            <div class="text-caption text-medium-emphasis">翻译条目</div>
            <div class="text-caption mt-1">{{ db?.person_count ?? 0 }} 个演员 / 已译 {{ db?.translated_people ?? 0 }}</div>
            <v-btn v-if="allowRefresh" size="x-small" variant="text" class="mt-1" @click="load">
              <v-icon size="16">mdi-refresh</v-icon>
            </v-btn>
          </template>
        </v-card-text>
        <div v-show="isHovering" class="absolute right-5 top-5">
          <v-icon class="cursor-move">mdi-drag</v-icon>
        </div>
      </v-card>
    </template>
  </v-hover>
</template>
