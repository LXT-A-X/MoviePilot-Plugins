<template>
  <div class="pa-4" style="max-width: 1400px; margin: 0 auto;">
    <!-- Hero Header -->
    <v-card variant="tonal" color="primary" flat class="mb-4 rounded-lg">
      <v-card-item>
        <template #prepend>
          <v-avatar variant="tonal" color="primary" size="52" class="mr-3">
            <v-icon size="28">mdi-translate</v-icon>
          </v-avatar>
        </template>
        <v-card-title class="text-h4 font-weight-black mb-0">
          Emby 演职人员中文化
        </v-card-title>
      </v-card-item>
      <v-card-text class="pt-0">
        利用大模型批量翻译 Emby 中英文名/罗马音/日文假名人名 + 角色字段，并直接写回 Emby。
      </v-card-text>
    </v-card>

    <!-- Statistics Cards -->
    <v-row dense class="mb-2">
      <v-col cols="12" sm="6" md="3" v-for="stat in statsCards" :key="stat.label">
        <v-card :variant="stat.variant" flat elevation="0" class="rounded-lg">
          <v-card-title class="text-subtitle-2 opacity-70 pb-0">{{ stat.label }}</v-card-title>
          <v-card-text class="py-0">
            <div class="text-h4 font-weight-black mb-1">{{ stat.value }}</div>
            <div class="text-caption opacity-60">{{ stat.sub }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-divider class="my-5" />

    <!-- Search & Filter Bar -->
    <v-row dense class="mb-3 align-center">
      <v-col cols="12" sm="5" md="4">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          label="搜索作品名..."
          variant="outlined"
          density="compact"
          hide-details
          clearable
          @update:model-value="onSearchChange"
        />
      </v-col>
      <v-col cols="12" sm="4" md="3">
        <v-select
          v-model="libFilter"
          :items="libOptions"
          label="按库筛选"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          @update:model-value="fetchHistory"
        />
      </v-col>
      <v-col cols="12" sm="3" md="2" class="text-right">
        <v-btn
          variant="tonal"
          color="primary"
          prepend-icon="mdi-cog"
          size="small"
          @click="$emit('navigate', 'config')"
        >
          插件设置
        </v-btn>
      </v-col>
    </v-row>

    <!-- History Table -->
    <v-card flat elevation="0" class="rounded-lg border">
      <v-card-title class="d-flex align-center py-3 px-4">
        <v-icon size="20" class="mr-2">mdi-history</v-icon>
        <span class="text-h6">翻译记录</span>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">{{ totalRecords }} 条记录</span>
      </v-card-title>

      <!-- Loading State -->
      <div v-if="loading" class="text-center py-10">
        <v-progress-circular indeterminate color="primary" size="48" />
        <div class="text-medium-emphasis mt-3">加载中...</div>
      </div>

      <!-- Empty State -->
      <div v-else-if="history.length === 0" class="text-center py-10">
        <v-icon size="64" color="grey-lighten-1" class="mb-3">mdi-inbox-outline</v-icon>
        <div class="text-h6 text-medium-emphasis">暂无翻译记录</div>
        <div class="text-caption text-medium-emphasis mt-1">
          打开「插件设置」→「立即运行一次」开始翻译
        </div>
      </div>

      <!-- History Table -->
      <v-table v-else density="compact" hover>
        <thead>
          <tr>
            <th style="width: 56px"></th>
            <th>作品</th>
            <th style="width: 140px">库 / 服务器</th>
            <th style="width: 80px">字段数</th>
            <th style="width: 150px">更新时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, i) in history" :key="item.key">
            <!-- Poster -->
            <td class="py-1">
              <v-img
                v-if="item.poster_url"
                :src="item.poster_url"
                width="40"
                height="56"
                cover
                class="rounded"
                style="border: 1px solid rgba(128,128,128,0.2)"
              >
                <template #error>
                  <v-icon size="24" color="grey">mdi-image-off</v-icon>
                </template>
              </v-img>
              <v-icon v-else size="28" color="grey-lighten-1">mdi-filmstrip</v-icon>
            </td>
            <!-- Title -->
            <td>
              <div class="text-body-2 font-weight-medium text-truncate" style="max-width: 300px">
                {{ item.title }}
              </div>
            </td>
            <!-- Library / Server -->
            <td>
              <div class="text-caption text-medium-emphasis">
                <v-chip size="x-small" variant="tonal" color="info" class="mr-1">{{ item.lib }}</v-chip>
                <span class="text-caption">{{ item.server }}</span>
              </div>
            </td>
            <!-- Fields count -->
            <td>
              <v-chip size="small" variant="tonal" :color="item.n_trans > 0 ? 'success' : 'grey'">
                {{ item.n_trans }} 字段
              </v-chip>
            </td>
            <!-- Time -->
            <td class="text-caption text-medium-emphasis">{{ formatTime(item.time) }}</td>
          </tr>
        </tbody>
      </v-table>

      <!-- Pagination -->
      <v-card-actions v-if="totalPages > 1" class="px-4 py-2 border-t">
        <v-spacer />
        <v-pagination
          v-model="page"
          :length="totalPages"
          :total-visible="7"
          size="small"
          density="compact"
          variant="tonal"
          @update:model-value="fetchHistory"
        />
        <v-spacer />
      </v-card-actions>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const emit = defineEmits(['navigate'])

const API_BASE = '/api/v1/plugin/EmbyPeopleLocalize'

// State
const search = ref('')
const libFilter = ref(null)
const page = ref(1)
const limit = 20
const loading = ref(false)
const history = ref([])
const totalRecords = ref(0)
const totalPages = ref(1)
const stats = ref({ titles: 0, fields: 0, history_count: 0, cached: 0 })
const libraries = ref([])

// Debounce search
let searchTimer = null
function onSearchChange() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchHistory()
  }, 300)
}

// Fetch stats
async function fetchStats() {
  try {
    const res = await fetch(`${API_BASE}/stats`)
    if (res.ok) stats.value = await res.json()
  } catch (e) { /* ignore */ }
}

// Fetch history
async function fetchHistory() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: page.value,
      limit: limit,
    })
    if (search.value) params.set('search', search.value)
    if (libFilter.value) params.set('lib', libFilter.value)

    const res = await fetch(`${API_BASE}/history?${params}`)
    if (res.ok) {
      const data = await res.json()
      history.value = data.items || []
      totalRecords.value = data.total || 0
      totalPages.value = Math.ceil(totalRecords.value / limit)
    }
  } catch (e) {
    console.error('Failed to fetch history:', e)
  } finally {
    loading.value = false
  }
}

// Fetch libraries
async function fetchLibraries() {
  try {
    const res = await fetch(`${API_BASE}/libraries`)
    if (res.ok) {
      const data = await res.json()
      libraries.value = data || []
    }
  } catch (e) { /* ignore */ }
}

// Computed
const libOptions = computed(() => {
  return libraries.value.map(l => ({ title: l, value: l }))
})

const statsCards = computed(() => [
  {
    label: '已处理作品数',
    value: stats.value.titles,
    sub: '作品已翻译完成',
    variant: 'tonal',
  },
  {
    label: '已翻译字段数',
    value: stats.value.fields,
    sub: '人名 + 角色累计翻译',
    variant: 'tonal',
  },
  {
    label: '历史记录',
    value: `${stats.value.history_count} 条`,
    sub: '最近更新顶到最前',
    variant: 'tonal',
  },
  {
    label: '人名翻译缓存',
    value: `${stats.value.cached} 条`,
    sub: '重复人名直接复用',
    variant: 'tonal',
  },
])

function formatTime(t) {
  if (!t) return ''
  return t.replace('T', ' ').substring(0, 19)
}

onMounted(() => {
  fetchStats()
  fetchHistory()
  fetchLibraries()
})
</script>

<style scoped>
.v-table {
  border-radius: 0 !important;
}
</style>
