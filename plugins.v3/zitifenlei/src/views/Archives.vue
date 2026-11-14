<script setup>
import { computed, onActivated, onMounted, ref } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
})
const emit = defineEmits(['notify'])

const items = ref([])
const loading = ref(false)
const busy = ref('')
const filter = ref('all')
const viewMode = ref('list')
const configDirs = ref({ input: '', ass: '', subset: '' })
const locations = ref([])
const entriesDialog = ref(false)
const entriesItem = ref(null)
const entries = ref([])
const entriesLoading = ref(false)
const entriesError = ref('')
const entriesMeta = ref({ total: 0, truncated: false, tool: '' })
const treePage = ref(1)
const TREE_PAGE_SIZE = 50
const treeRows = computed(() => {
  const root = { children: new Map() }
  const ensureDir = (node, name) => {
    if (!node.children.has(name)) {
      node.children.set(name, { name, isDir: true, size: 0, children: new Map() })
    }
    return node.children.get(name)
  }
  for (const entry of entries.value) {
    const raw = String(entry.name || '').replace(/\\/g, '/')
    const parts = raw.split('/').filter(Boolean)
    if (!parts.length) continue
    let node = root
    for (let i = 0; i < parts.length - 1; i += 1) {
      node = ensureDir(node, parts[i])
    }
    const leaf = parts[parts.length - 1]
    if (entry.is_dir || raw.endsWith('/')) {
      ensureDir(node, leaf)
    } else if (node.children.has(leaf) && node.children.get(leaf).isDir) {
      node.children.get(leaf).size = Number(entry.size) || 0
    } else {
      node.children.set(leaf, {
        name: leaf,
        isDir: false,
        size: Number(entry.size) || 0,
        children: new Map(),
      })
    }
  }
  const sortMap = (map) => [...map.values()]
    .sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1))
    .map((item) => ({ ...item, children: sortMap(item.children) }))
  const rows = []
  const walk = (nodes, depth, parentPath) => {
    for (const node of nodes) {
      const path = parentPath ? parentPath + '/' + node.name : node.name
      rows.push({ ...node, path, depth })
      if (node.isDir && node.children.length) walk(node.children, depth + 1, path)
    }
  }
  walk(sortMap(root.children), 0, '')
  return rows
})
const treePageCount = computed(() => Math.max(1, Math.ceil(treeRows.value.length / TREE_PAGE_SIZE)))
const treePageRows = computed(() => (
  treeRows.value.slice((treePage.value - 1) * TREE_PAGE_SIZE, treePage.value * TREE_PAGE_SIZE)
))
const moveDialog = ref(false)
const moveItem = ref(null)
const moveTarget = ref('')
const moveBusy = ref(false)
const FILTERS = [
  { title: '全部', value: 'all' },
  { title: '已处理', value: '已处理' },
  { title: '错误', value: '错误' },
  { title: '未分类（旧版）', value: '未分类' },
]
const filtered = computed(() => (
  filter.value === 'all'
    ? items.value
    : items.value.filter((item) => (item.category || '未分类') === filter.value)
))
const totalSize = computed(() => (
  filtered.value.reduce((sum, item) => sum + (Number(item.size) || 0), 0)
))
const moveTargets = computed(() => {
  const candidates = [
    { title: '字体监控目录', value: 'input', dir: configDirs.value.input },
    { title: 'ASS 字幕检查目录', value: 'ass', dir: configDirs.value.ass },
    { title: 'ASS 自动子集化目录', value: 'subset', dir: configDirs.value.subset },
  ]
  return candidates.filter((item) => item.dir).map(({ title, value }) => ({ title, value }))
})

function notify(message, type = 'error') {
  emit('notify', message, type)
}
function fmtSize(value) {
  const num = Number(value) || 0
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  if (num < 1024 * 1024 * 1024) return (num / 1024 / 1024).toFixed(1) + ' MB'
  return (num / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}
function fmtTime(ts) {
  try {
    return new Date((Number(ts) || 0) * 1000).toLocaleString()
  } catch (e) {
    return ''
  }
}
function categoryColor(category) {
  if (category === '已处理') return 'success'
  if (category === '错误') return 'error'
  return 'grey'
}
function categoryIcon(category) {
  if (category === '已处理') return 'mdi-check-circle-outline'
  if (category === '错误') return 'mdi-alert-circle-outline'
  return 'mdi-archive-outline'
}

async function loadConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await apiModule.get(props.api, '/config')
    if (data && typeof data === 'object') {
      configDirs.value = {
        input: data.input_dir || '',
        ass: data.ass_dir || '',
        subset: data.subset_dir || '',
      }
    }
  } catch (e) {
    // 目录未取到不影响列表；错误项会隐藏「移到指定目录」
  }
}

async function load() {
  if (typeof props.api?.get !== 'function') return
  loading.value = true
  try {
    const data = await apiModule.get(props.api, '/archives/processed')
    items.value = Array.isArray(data?.items) ? data.items : []
    locations.value = Array.isArray(data?.locations) ? data.locations : []
  } catch (e) {
    notify(e.message || '读取已处理压缩包失败')
  } finally {
    loading.value = false
  }
}

async function removeItem(item) {
  if (!item?.path) return
  if (!window.confirm('删除压缩包？\n' + item.name + '\n\n（只删「已处理压缩包」里的副本，不影响原目录）')) return
  busy.value = item.path
  try {
    const res = await apiModule.post(props.api, '/archives/processed/remove', { paths: [item.path] })
    notify(res.message || '已删除压缩包', 'success')
    await load()
  } catch (e) {
    notify(e.message || '删除失败')
  } finally {
    busy.value = ''
  }
}

async function restoreItem(item) {
  if (!item?.path) return
  const warn = item.category === '错误'
    ? '\n\n注意：它原本就在错误目录，移回后可能再次被移到「错误/」；建议先改放到正确目录。'
    : ''
  if (!window.confirm('把压缩包移回原目录？\n' + item.name + warn + '\n\n只移动压缩包，不会撤销已归档的字体/已检查的字幕。')) return
  busy.value = item.path
  try {
    const res = await apiModule.post(props.api, '/archives/processed/restore', { path: item.path })
    notify(res.message || '已恢复压缩包', 'success')
    await load()
  } catch (e) {
    notify(e.message || '恢复失败')
  } finally {
    busy.value = ''
  }
}

async function clearCurrent() {
  const scope = filter.value === 'all' ? '' : filter.value
  if (!filtered.value.length) return
  if (!window.confirm('清空「' + (scope || '全部') + '」已处理压缩包？共 ' + filtered.value.length + ' 个，不可恢复。\n\n（只删副本，不影响原目录）')) return
  busy.value = 'clear'
  try {
    const res = await apiModule.post(props.api, '/archives/processed/clear', { category: scope })
    notify(res.message || '已清空', 'success')
    await load()
  } catch (e) {
    notify(e.message || '清空失败')
  } finally {
    busy.value = ''
  }
}

async function copyPath(path) {
  if (!path) return
  try {
    await navigator.clipboard.writeText(path)
    notify('已复制路径', 'success')
  } catch (e) {
    notify('复制失败，请手动选择路径')
  }
}

async function viewItem(item) {
  if (!item?.path) return
  entriesItem.value = item
  entries.value = []
  entriesError.value = ''
  entriesMeta.value = { total: 0, truncated: false, tool: '' }
  entriesDialog.value = true
  entriesLoading.value = true
  try {
    const data = await apiModule.get(props.api, '/archives/processed/entries', { path: item.path })
    entries.value = Array.isArray(data?.entries) ? data.entries : []
    treePage.value = 1
    entriesMeta.value = {
      total: Number(data?.total) || entries.value.length,
      truncated: !!data?.truncated,
      tool: data?.tool || '',
    }
  } catch (e) {
    entriesError.value = e.message || '读取压缩包内容失败'
  } finally {
    entriesLoading.value = false
  }
}

function openMove(item) {
  if (!item?.path) return
  moveItem.value = item
  moveTarget.value = moveTargets.value[0]?.value || ''
  moveDialog.value = true
}

async function doMove() {
  if (!moveItem.value?.path || !moveTarget.value) return
  moveBusy.value = true
  try {
    const res = await apiModule.post(props.api, '/archives/processed/move', {
      path: moveItem.value.path,
      target: moveTarget.value,
    })
    notify(res.message || '已移动压缩包', 'success')
    moveDialog.value = false
    await load()
  } catch (e) {
    notify(e.message || '移动失败')
  } finally {
    moveBusy.value = false
  }
}

onMounted(() => {
  load()
  loadConfig()
})
onActivated(() => {
  load()
  loadConfig()
})
</script>

<template>
  <div class="zt-archives-page">
    <div class="zt-page-title">
      <v-icon start size="22">mdi-archive-eye-outline</v-icon>
      已处理压缩包
    </div>
    <div class="zt-page-desc">
      这里管理插件清理/留档的压缩包副本：<b>已处理/</b> 是成功处理后的副本，
      <b>错误/</b> 是放错目录、不支持格式或包内没有字体/字幕的留档。
      「移回原目录」只会把压缩包移回它原来所在的目录并重新监控处理，
      <b>不会撤销</b>已经归档的字体/已检查的字幕；删除只影响副本，不碰原目录文件。
    </div>

    <div v-if="locations.length" class="zt-locations">
      <div class="zt-loc-title">
        <v-icon size="15">mdi-folder-marker-outline</v-icon>
        当前存放位置
      </div>
      <div v-for="loc in locations" :key="loc.label + loc.path" class="zt-loc">
        <span class="zt-loc-label">{{ loc.label }}</span>
        <code v-if="loc.path" class="zt-loc-path">{{ loc.path }}</code>
        <span v-else class="zt-loc-hint">{{ loc.hint }}</span>
        <v-btn v-if="loc.path" icon size="x-small" variant="text" title="复制路径" @click="copyPath(loc.path)">
          <v-icon size="14">mdi-content-copy</v-icon>
        </v-btn>
      </div>
    </div>

    <v-card class="zt-card-bg mt-4">
      <v-card-text>
        <div class="zt-toolbar">
          <v-select
            v-model="filter"
            :items="FILTERS"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            class="zt-filter"
          ></v-select>
          <v-btn
            size="small"
            variant="tonal"
            :loading="loading"
            @click="load"
          >
            <v-icon start size="16">mdi-refresh</v-icon>刷新
          </v-btn>
          <v-btn-toggle v-model="viewMode" mandatory density="compact" variant="outlined" divided color="primary" class="zt-view-toggle">
            <v-btn value="list" size="small" title="列表">
              <v-icon size="16">mdi-view-list-outline</v-icon>
            </v-btn>
            <v-btn value="card" size="small" title="卡片">
              <v-icon size="16">mdi-view-grid-outline</v-icon>
            </v-btn>
          </v-btn-toggle>
          <v-spacer></v-spacer>
          <span class="zt-count">{{ filtered.length }} 个 · {{ fmtSize(totalSize) }}</span>
          <v-btn
            size="small"
            color="error"
            variant="text"
            :disabled="!filtered.length"
            :loading="busy === 'clear'"
            @click="clearCurrent"
          >
            <v-icon start size="16">mdi-delete-sweep</v-icon>清空当前分类
          </v-btn>
        </div>

        <v-divider class="my-3"></v-divider>

        <div v-if="loading && !items.length" class="zt-empty">
          <v-progress-circular indeterminate color="primary" size="28"></v-progress-circular>
          <div class="mt-2">读取中…</div>
        </div>
        <div v-else-if="!filtered.length" class="zt-empty">
          <v-icon size="46" class="zt-empty-icon">mdi-archive-off-outline</v-icon>
          <div>{{ filter === 'all' ? '暂无已处理压缩包' : '该分类暂无压缩包' }}</div>
          <div class="zt-empty-hint">插件成功清理或移入错误目录后会显示在这里</div>
        </div>
        <div v-else-if="viewMode === 'list'" class="zt-list">
          <div
            v-for="item in filtered"
            :key="item.path"
            class="zt-row"
          >
            <div class="zt-row-main">
              <v-icon :color="categoryColor(item.category)" size="22" class="mr-3">
                {{ categoryIcon(item.category) }}
              </v-icon>
              <div class="zt-row-text">
                <div class="zt-row-name">{{ item.name }}</div>
                <div class="zt-row-meta">
                  <span class="zt-cat" :class="'is-' + categoryColor(item.category)">
                    {{ item.category || '未分类' }}
                  </span>
                  <span>{{ item.source }}</span>
                  <span>{{ fmtSize(item.size) }}</span>
                  <span>{{ fmtTime(item.mtime) }}</span>
                </div>
              </div>
            </div>
            <div class="zt-row-actions">
              <v-btn
                size="x-small"
                variant="text"
                @click="viewItem(item)"
              >
                <v-icon start size="14">mdi-file-eye-outline</v-icon>查看
              </v-btn>
              <v-btn
                size="x-small"
                variant="tonal"
                :disabled="!item.can_restore"
                :loading="busy === item.path"
                :title="item.can_restore ? '移回原目录（不会撤销已处理内容）' : '自定义目录缺少原目录记录，无法移回'"
                @click="restoreItem(item)"
              >
                <v-icon start size="14">mdi-restore</v-icon>移回原目录
              </v-btn>
              <v-btn
                v-if="item.category === '错误' && moveTargets.length"
                size="x-small"
                variant="tonal"
                :loading="busy === item.path"
                @click="openMove(item)"
              >
                <v-icon start size="14">mdi-folder-move-outline</v-icon>移到…
              </v-btn>
              <v-btn
                size="x-small"
                variant="text"
                color="error"
                :loading="busy === item.path"
                @click="removeItem(item)"
              >
                <v-icon start size="14">mdi-delete-outline</v-icon>删除
              </v-btn>
            </div>
          </div>
        </div>
        <div v-else class="zt-cards">
          <div v-for="item in filtered" :key="item.path" class="zt-card-item">
            <div class="zt-card-head">
              <v-icon :color="categoryColor(item.category)" size="24">
                {{ categoryIcon(item.category) }}
              </v-icon>
              <div class="zt-card-title">
                <div class="zt-row-name">{{ item.name }}</div>
                <div class="zt-row-meta">
                  <span class="zt-cat" :class="'is-' + categoryColor(item.category)">
                    {{ item.category || '未分类' }}
                  </span>
                  <span>{{ item.source }}</span>
                </div>
              </div>
            </div>
            <div class="zt-card-meta">
              <span>{{ fmtSize(item.size) }}</span>
              <span>{{ fmtTime(item.mtime) }}</span>
            </div>
            <div class="zt-card-actions">
              <v-btn size="x-small" variant="text" @click="viewItem(item)">
                <v-icon start size="14">mdi-file-eye-outline</v-icon>查看
              </v-btn>
              <v-spacer></v-spacer>
              <v-btn
                size="x-small"
                variant="tonal"
                :disabled="!item.can_restore"
                :loading="busy === item.path"
                @click="restoreItem(item)"
              >移回</v-btn>
              <v-btn
                v-if="item.category === '错误' && moveTargets.length"
                size="x-small"
                variant="tonal"
                :loading="busy === item.path"
                @click="openMove(item)"
              >移到…</v-btn>
              <v-btn
                size="x-small"
                variant="text"
                color="error"
                :loading="busy === item.path"
                @click="removeItem(item)"
              >删除</v-btn>
            </div>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-dialog v-model="moveDialog" max-width="460px">
      <v-card class="zt-card-bg">
        <v-card-title>
          <v-icon start size="20">mdi-folder-move-outline</v-icon>
          移到指定目录
        </v-card-title>
        <v-card-text>
          <div class="zt-hint move-name">{{ moveItem?.name }}</div>
          <v-select
            v-model="moveTarget"
            :items="moveTargets"
            item-title="title"
            item-value="value"
            label="目标监控目录"
            density="compact"
            variant="outlined"
            class="mt-3"
          ></v-select>
          <div class="zt-hint">
            移动后会清除已处理指纹并按新目录重新处理；如果目标目录类型与文件不匹配，会被移到「错误/」。
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="moveDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" :loading="moveBusy" :disabled="!moveTarget" @click="doMove">
            移动
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="entriesDialog" max-width="760px" :fullscreen="$vuetify.display.smAndDown">
      <v-card class="zt-card-bg">
        <v-card-title>
          <v-icon start size="20">mdi-archive-eye-outline</v-icon>
          压缩包内容
        </v-card-title>
        <v-card-text>
          <div class="zt-hint entries-name">{{ entriesItem?.name }}</div>
          <div class="zt-hint entries-path">{{ entriesItem?.path }}</div>
          <div v-if="entriesLoading" class="entries-loading">
            <v-progress-circular indeterminate color="primary" size="28"></v-progress-circular>
            <span class="ml-2">读取中…</span>
          </div>
          <div v-else-if="entriesError" class="entries-error">{{ entriesError }}</div>
          <template v-else>
            <div class="entries-summary">
              共 {{ entriesMeta.total }} 项
              <span v-if="entriesMeta.truncated">（仅显示前 500 项）</span>
              <span v-if="entriesMeta.tool"> · {{ entriesMeta.tool }}</span>
            </div>
            <div v-if="!treeRows.length" class="entries-empty">压缩包为空</div>
            <div v-else class="entries-list">
              <div
                v-for="row in treePageRows"
                :key="row.path"
                class="entry-row"
                :style="{ paddingLeft: (8 + row.depth * 18) + 'px' }"
              >
                <v-icon size="16" class="entry-icon">
                  {{ row.isDir ? 'mdi-folder-outline' : 'mdi-file-outline' }}
                </v-icon>
                <span class="entry-name">{{ row.name }}{{ row.isDir ? '/' : '' }}</span>
                <span class="entry-size">{{ row.isDir ? '' : fmtSize(row.size) }}</span>
              </div>
            </div>
            <div v-if="treePageCount > 1" class="tree-pager">
              <v-btn size="x-small" variant="text" :disabled="treePage <= 1" @click="treePage -= 1">上一页</v-btn>
              <span>第 {{ treePage }} / {{ treePageCount }} 页</span>
              <v-btn size="x-small" variant="text" :disabled="treePage >= treePageCount" @click="treePage += 1">下一页</v-btn>
            </div>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="entriesDialog = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.zt-archives-page {
  max-width: 100%;
  min-width: 0;
  overflow-x: hidden;
}
.zt-archives-page :deep(.v-card),
.zt-archives-page :deep(.v-card-text) {
  min-width: 0;
}
.zt-page-title {
  display: flex;
  align-items: center;
  font-size: 18px;
  font-weight: 600;
}
.zt-page-desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.7;
  opacity: 0.7;
  max-width: 820px;
}
.zt-locations {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.07);
}
.zt-loc-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  opacity: 0.85;
  margin-bottom: 6px;
}
.zt-loc {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 2px 0;
  font-size: 11px;
}
.zt-loc-label {
  flex: 0 0 auto;
  opacity: 0.65;
}
.zt-loc-hint {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11px;
  opacity: 0.7;
  line-height: 1.5;
}
.zt-loc-path {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  opacity: 0.8;
}
.entries-name {
  font-weight: 500;
  word-break: break-all;
  opacity: 0.95;
}
.entries-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  word-break: break-all;
}
.entries-loading {
  display: flex;
  align-items: center;
  padding: 24px 4px;
  font-size: 13px;
  opacity: 0.75;
}
.entries-error {
  margin-top: 12px;
  color: rgb(var(--v-theme-error));
  font-size: 12px;
  line-height: 1.6;
}
.entries-summary {
  margin: 10px 0 6px;
  font-size: 12px;
  opacity: 0.65;
}
.entries-list {
  max-height: 420px;
  overflow-y: auto;
  border-top: 1px solid rgba(128, 128, 128, 0.14);
}
.entry-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 2px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.09);
  font-size: 12px;
}
.entry-icon {
  flex: 0 0 auto;
  opacity: 0.75;
}
.entry-name {
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-all;
}
.entry-size {
  flex: 0 0 auto;
  opacity: 0.55;
  font-size: 11px;
}
.entries-empty {
  padding: 24px 4px;
  font-size: 13px;
  opacity: 0.65;
}
.tree-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 8px;
  font-size: 12px;
  opacity: 0.75;
}
.zt-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.zt-filter {
  max-width: 180px;
}
.zt-view-toggle :deep(.v-btn--active) {
  background: rgba(var(--v-theme-primary), 0.22);
  color: rgb(var(--v-theme-primary));
  opacity: 1;
}
.zt-view-toggle :deep(.v-btn--active .v-icon) {
  opacity: 1;
}
.zt-count {
  font-size: 12px;
  opacity: 0.7;
  margin-left: auto;
  white-space: nowrap;
}
.zt-list {
  display: flex;
  flex-direction: column;
}
.zt-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.zt-card-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.08);
  min-width: 0;
}
.zt-card-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.zt-card-title {
  min-width: 0;
}
.zt-card-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  opacity: 0.6;
  padding-top: 6px;
  border-top: 1px solid rgba(128, 128, 128, 0.12);
}
.zt-card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.zt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 4px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.12);
}
.zt-row:last-child {
  border-bottom: none;
}
.zt-row-main {
  display: flex;
  align-items: center;
  flex: 1 1 auto;
  min-width: 0;
}
.zt-row-text {
  min-width: 0;
}
.zt-row-name {
  font-size: 13px;
  font-weight: 500;
  overflow-wrap: anywhere;
  word-break: normal;
}
.zt-row-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 3px;
  font-size: 11px;
  opacity: 0.65;
}
.zt-cat {
  display: inline-block;
  padding: 0 5px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.18);
}
.zt-cat.is-success { color: rgb(var(--v-theme-success)); }
.zt-cat.is-error { color: rgb(var(--v-theme-error)); }
.zt-row-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 4px;
}
.zt-empty {
  text-align: center;
  padding: 36px 8px;
  font-size: 13px;
  opacity: 0.7;
}
.zt-empty-icon {
  opacity: 0.45;
  margin-bottom: 6px;
}
.move-name {
  font-weight: 500;
  word-break: break-all;
  opacity: 0.95;
}
.zt-empty-hint {
  margin-top: 4px;
  font-size: 11px;
  opacity: 0.7;
}
@media (max-width: 700px) {
  .zt-toolbar {
    gap: 6px;
  }
  .zt-filter {
    max-width: none;
    flex: 1 1 140px;
  }
  .zt-count {
    width: 100%;
    margin-left: 0;
  }
  .zt-row {
    align-items: flex-start;
    flex-wrap: wrap;
    min-width: 0;
  }
  .zt-row-main {
    width: 100%;
  }
  .zt-row-actions {
    width: 100%;
    justify-content: flex-end;
    flex-wrap: wrap;
  }
  .zt-cards {
    grid-template-columns: 1fr;
  }
  .entries-path,
  .entry-name {
    overflow-wrap: anywhere;
    word-break: normal;
  }
}
</style>
