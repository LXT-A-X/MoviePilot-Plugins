<script setup>
/**
 * 左侧媒体目录树：根目录切换 + 懒加载 + 客户端搜索（只列 .mkv）
 */
import { computed, onMounted, ref, watch } from 'vue'
import TreeNode from './TreeNode.vue'

const props = defineProps({
  api: { type: Object, required: true },
  roots: { type: Array, default: () => [] },
  current: { type: String, default: '' },
  kind: { type: String, default: 'video' },
  // 由 AppPage 递增，打开文件/切换页签时触发任务状态刷新
  refreshTick: { type: Number, default: 0 },
})

const emit = defineEmits(['select'])

const activeRoot = ref('')
const keyword = ref('')
const nodes = ref([])
const loading = ref(false)
const error = ref('')
// 文件路径 -> /file-statuses 条目
const statuses = ref({})
const statusLoading = ref(false)

const rootList = computed(() => (Array.isArray(props.roots) ? props.roots.filter(Boolean) : []))

// 把已加载的树拍平成文件列表，供搜索使用
function walk(list, out) {
  for (const node of list) {
    if (node.dir) {
      if (node.children?.length) walk(node.children, out)
    } else {
      out.push(node)
    }
  }
  return out
}

const allFiles = computed(() => walk(nodes.value, []))
const searchResults = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return []
  return allFiles.value.filter((node) => node.name.toLowerCase().includes(query))
})

async function loadRoot(root) {
  if (!root) {
    nodes.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = await props.api.post('/fs/list', { root, path: root, kind: props.kind })
    const dirs = (data?.dirs || []).map((item) => ({
      name: item.name,
      path: item.path,
      dir: true,
      expanded: false,
      loaded: false,
      loading: false,
      children: [],
      fileCount: item.file_count ?? null,
    }))
    const files = (data?.files || []).map((item) => ({
      name: item.name,
      path: item.path,
      dir: false,
      size: item.size ?? null,
      ext: item.ext || '',
    }))
    nodes.value = dirs.concat(files)
  } catch (err) {
    nodes.value = []
    error.value = err.message || '读取目录失败'
  } finally {
    loading.value = false
  }
}

function chooseRoot(root) {
  if (!root || root === activeRoot.value) return
  activeRoot.value = root
  keyword.value = ''
  loadRoot(root)
}

function onSelect(path) {
  emit('select', path)
}

/** 拉取文件任务状态（队列优先于历史，后端已按路径去重）。 */
async function loadStatuses() {
  if (statusLoading.value) return
  statusLoading.value = true
  try {
    const data = await props.api.get('/file-statuses')
    const map = {}
    for (const item of data?.items || []) {
      if (item?.path) map[item.path] = item
    }
    statuses.value = map
  } catch (err) {
    // 状态读取失败不影响目录浏览
  } finally {
    statusLoading.value = false
  }
}

onMounted(() => {
  loadStatuses()
  if (rootList.value.length) {
    activeRoot.value = rootList.value[0]
    loadRoot(activeRoot.value)
  }
})

// 打开文件 / 切换页签时刷新任务状态
watch(
  () => props.refreshTick,
  () => loadStatuses(),
)
watch(
  () => props.current,
  () => loadStatuses(),
)

watch(
  rootList,
  (list) => {
    if (!list.length) {
      activeRoot.value = ''
      nodes.value = []
      return
    }
    if (!list.includes(activeRoot.value)) {
      activeRoot.value = list[0]
      loadRoot(activeRoot.value)
    }
  },
  { deep: true },
)
</script>

<template>
  <div class="file-tree">
    <div class="file-tree-head">
      <div class="file-tree-search-row">
        <v-text-field
          v-model="keyword"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          placeholder="搜索片名 / 文件名…"
          prepend-inner-icon="mdi-magnify"
          clearable
        />
        <v-btn
          size="x-small"
          variant="text"
          icon="mdi-refresh"
          title="刷新任务状态"
          :loading="statusLoading"
          class="file-tree-refresh"
          @click="loadStatuses"
        />
      </div>
      <div v-if="rootList.length" class="file-tree-roots">
        <button
          v-for="root in rootList"
          :key="root"
          class="root-chip"
          :class="{ 'root-chip--active': root === activeRoot }"
          :title="root"
          type="button"
          @click="chooseRoot(root)"
        >
          {{ root }}
        </button>
      </div>
    </div>

    <div class="file-tree-body">
      <div v-if="!rootList.length" class="file-tree-tip">
        还没有配置媒体根目录，请先到「设置 → 目录」添加。
      </div>
      <v-skeleton-loader v-else-if="loading" type="list-item@6" />
      <div v-else-if="error" class="file-tree-tip file-tree-tip--error">
        {{ error }}
        <v-btn size="small" variant="text" @click="loadRoot(activeRoot)">重试</v-btn>
      </div>
      <template v-else-if="keyword.trim()">
        <div v-if="searchResults.length" class="file-tree-list">
          <TreeNode
            v-for="node in searchResults"
            :key="node.path"
            :node="node"
            :api="api"
            :root="activeRoot"
            :kind="kind"
            :current="current"
            :statuses="statuses"
            :depth="0"
            @select="onSelect"
          />
        </div>
        <div v-else class="file-tree-tip">没有匹配的文件（只搜索已展开的目录）</div>
      </template>
      <div v-else-if="nodes.length" class="file-tree-list">
        <TreeNode
          v-for="node in nodes"
          :key="node.path"
          :node="node"
          :api="api"
          :root="activeRoot"
          :kind="kind"
          :current="current"
          :statuses="statuses"
          :depth="0"
          @select="onSelect"
        />
      </div>
      <div v-else class="file-tree-tip">当前根目录下没有子目录或 .mkv 文件</div>
    </div>
  </div>
</template>

<style scoped>
.file-tree {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
.file-tree-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 12px 8px;
  flex: 0 0 auto;
}
.file-tree-search-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.file-tree-search-row :deep(.v-field) {
  flex: 1 1 auto;
  min-width: 0;
}
.file-tree-refresh {
  flex: 0 0 auto;
}
.file-tree-roots {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.root-chip {
  font-family: inherit;
  font-size: 11.5px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  color: rgba(var(--v-theme-on-surface), 0.65);
  background: rgba(var(--v-theme-on-surface), 0.05);
  cursor: pointer;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.root-chip:hover {
  color: rgb(var(--v-theme-on-surface));
}
.root-chip--active {
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-primary), 0.1);
}
.file-tree-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 4px 8px 16px;
}
.file-tree-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.file-tree-tip {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  padding: 10px 6px;
  line-height: 1.7;
}
.file-tree-tip--error {
  color: rgb(var(--v-theme-error));
}
@media (max-width: 959px) {
  .file-tree-head {
    padding: 10px 12px 6px;
  }
}
</style>
