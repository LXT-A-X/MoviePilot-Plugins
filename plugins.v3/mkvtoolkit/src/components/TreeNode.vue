<script setup>
/**
 * 目录树节点（递归）
 * 懒加载：首次展开目录时才请求 /fs/list；目录节点带 file_count 时显示数量
 */
import { computed, inject } from 'vue'
import { fmtBytes } from '../utils.js'

const props = defineProps({
  node: { type: Object, required: true },
  api: { type: Object, required: true },
  root: { type: String, default: '' },
  kind: { type: String, default: 'video' },
  current: { type: String, default: '' },
  // 文件路径 -> /file-statuses 条目
  statuses: { type: Object, default: () => ({}) },
  depth: { type: Number, default: 0 },
})

const emit = defineEmits(['select'])
const toast = inject('moviepilot:toast', null)

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message)
}

async function loadChildren() {
  const node = props.node
  if (!node.dir || node.loaded || node.loading) return
  node.loading = true
  try {
    const data = await props.api.post('/fs/list', {
      root: props.root,
      path: node.path,
      kind: props.kind,
    })
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
    node.children = dirs.concat(files)
    node.loaded = true
  } catch (err) {
    node.loaded = true
    node.children = []
    toastMsg('error', `读取目录失败：${err.message}`)
  } finally {
    node.loading = false
  }
}

async function onClick() {
  if (props.node.dir) {
    await loadChildren()
    props.node.expanded = !props.node.expanded
  } else {
    emit('select', props.node.path)
  }
}

function indent() {
  return `${props.depth * 14 + 8}px`
}

// 文件行状态徽标：pending/running/success/failed/cancelled
const STATUS_BADGE = {
  pending: { text: '待开始', cls: 'pending' },
  running: { text: '运行中', cls: 'running' },
  success: { text: '已完成', cls: 'success' },
  failed: { text: '失败', cls: 'failed' },
  cancelled: { text: '已取消', cls: 'cancelled' },
}

const badge = computed(() => {
  if (props.node.dir) return null
  const info = props.statuses?.[props.node.path]
  if (!info) return null
  const found = STATUS_BADGE[info.state]
  if (!found) return null
  // 队列 pending 且阶段为「等待中」时显示等待中
  if (info.state === 'pending' && String(info.stage || '').includes('等待')) {
    return { text: '等待中', cls: 'pending' }
  }
  return found
})
</script>

<template>
  <div class="tree-node">
    <div
      class="tree-row"
      :class="{ 'tree-row--file': !node.dir, 'tree-row--active': !node.dir && node.path === current }"
      :style="{ paddingLeft: indent() }"
      :title="node.path"
      @click="onClick"
    >
      <span class="tree-ic">
        <v-progress-circular v-if="node.loading" indeterminate size="12" width="2" />
        <v-icon v-else-if="node.dir" size="15" :icon="node.expanded ? 'mdi-chevron-down' : 'mdi-chevron-right'" />
        <v-icon v-else size="15" icon="mdi-filmstrip" />
      </span>
      <span class="tree-name">{{ node.name }}</span>
      <span v-if="badge" class="tree-badge" :class="`tree-badge--${badge.cls}`">{{ badge.text }}</span>
      <span class="tree-mini">
        <span v-if="node.dir && node.fileCount"> {{ node.fileCount }} </span>
        <span v-else-if="!node.dir">{{ fmtBytes(node.size, 0) }}</span>
      </span>
    </div>
    <template v-if="node.dir && node.expanded && node.children && node.children.length">
      <TreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :api="api"
        :root="root"
        :kind="kind"
        :current="current"
        :statuses="statuses"
        :depth="depth + 1"
        @select="emit('select', $event)"
      />
    </template>
    <div
      v-else-if="node.dir && node.expanded && node.loaded"
      class="tree-empty"
      :style="{ paddingLeft: `${depth * 14 + 26}px` }"
    >
      （空目录）
    </div>
  </div>
</template>

<style scoped>
.tree-node {
  min-width: 0;
}
.tree-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 8px;
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.66);
  cursor: pointer;
  line-height: 1.25;
  min-height: 30px;
  user-select: none;
}
.tree-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface));
}
.tree-row--file {
  color: rgba(var(--v-theme-on-surface), 0.82);
}
.tree-row--active {
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.36);
}
.tree-ic {
  flex: 0 0 16px;
  width: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0.9;
}
.tree-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12.5px;
}
/* 文件任务状态徽标：紧凑不换行，文件名仍可截断 */
.tree-badge {
  flex: 0 0 auto;
  font-size: 10px;
  line-height: 16px;
  padding: 0 5px;
  border-radius: 5px;
  white-space: nowrap;
  border: 1px solid transparent;
}
.tree-badge--pending {
  color: #64b5f6;
  border-color: rgba(66, 165, 245, 0.4);
  background: rgba(66, 165, 245, 0.12);
}
.tree-badge--running {
  color: #ffb74d;
  border-color: rgba(255, 152, 0, 0.42);
  background: rgba(255, 152, 0, 0.14);
}
.tree-badge--success {
  color: #81c784;
  border-color: rgba(76, 175, 80, 0.4);
  background: rgba(76, 175, 80, 0.12);
}
.tree-badge--failed {
  color: #ef5350;
  border-color: rgba(239, 83, 80, 0.42);
  background: rgba(239, 83, 80, 0.12);
}
.tree-badge--cancelled {
  color: rgba(var(--v-theme-on-surface), 0.55);
  border-color: rgba(var(--v-theme-on-surface), 0.22);
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.tree-mini {
  flex: 0 0 auto;
  display: flex;
  gap: 4px;
}
.tree-mini span {
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  background: rgba(var(--v-theme-on-surface), 0.07);
  border-radius: 5px;
  padding: 1px 5px;
  white-space: nowrap;
}
.tree-empty {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  padding: 4px 0;
}
@media (max-width: 959px) {
  .tree-row {
    min-height: 38px;
    padding-top: 8px;
    padding-bottom: 8px;
  }
  .tree-name {
    font-size: 13.5px;
  }
}
</style>
