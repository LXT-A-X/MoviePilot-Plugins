<script setup>
/**
 * 从目录选择素材：调用 /fs/list，按 kind 过滤，选中后返回服务器路径
 */
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { SUBTITLE_EXTENSIONS, AUDIO_EXTENSIONS, FONT_EXTENSIONS, ARCHIVE_EXTENSIONS, fmtBytes } from '../utils.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  api: { type: Object, required: true },
  kind: { type: String, default: 'subtitle' },
  title: { type: String, default: '' },
  roots: { type: Array, default: () => [] },
  initialPath: { type: String, default: '' },
  exts: { type: Array, default: () => [] },
  // 布局三档：narrow 全屏；medium 半屏窗口（min(620px,55vw)）；wide 680px
  layout: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'select'])
const display = useDisplay()
const effectiveLayout = computed(() => props.layout || (display.mdAndUp.value ? 'wide' : 'narrow'))
const mobile = computed(() => effectiveLayout.value === 'narrow')
const dialogMaxWidth = computed(() => {
  if (mobile.value) return undefined
  return effectiveLayout.value === 'medium' ? 'min(620px, 55vw)' : 680
})

const KIND_TITLE = { subtitle: '选择字幕文件', audio: '选择音频文件', font: '选择字体文件', chapter: '选择章节文件', archive: '选择字体压缩包' }
const KIND_EXT = {
  subtitle: SUBTITLE_EXTENSIONS,
  audio: AUDIO_EXTENSIONS,
  font: FONT_EXTENSIONS,
  chapter: ['.xml', '.txt', '.ogm'],
  archive: ARCHIVE_EXTENSIONS,
}

const activeRoot = ref('')
const currentPath = ref('')
const parentPath = ref('')
const dirs = ref([])
const files = ref([])
const selected = ref(null)
const loading = ref(false)
const error = ref('')

const dialogTitle = computed(() => props.title || KIND_TITLE[props.kind] || '选择文件')
const allowedExts = computed(() => (props.exts?.length ? props.exts : KIND_EXT[props.kind] || []))
// 压缩包由后端 /fs/list 的 archive kind 直接过滤
const listKind = computed(() => (props.kind === 'chapter' ? 'all' : props.kind))
const rootList = computed(() => (Array.isArray(props.roots) ? props.roots.filter(Boolean) : []))
const manualPath = ref('')

function isFileLike(path) {
  const last = String(path || '').split('/').pop() || ''
  return last.includes('.')
}

function dirName(path) {
  const normalized = String(path || '').replace(/\/+$/, '')
  const index = normalized.lastIndexOf('/')
  return index > 0 ? normalized.slice(0, index) : '/'
}

function resolveRoot(path) {
  for (const root of rootList.value) {
    const clean = String(root).replace(/\/+$/, '')
    if (path === clean || path === root || String(path).startsWith(`${clean}/`)) return root
  }
  return rootList.value[0] || ''
}

function matchesExt(name) {
  if (!allowedExts.value.length) return true
  const lower = String(name || '').toLowerCase()
  return allowedExts.value.some((ext) => lower.endsWith(ext))
}

async function load(path) {
  const target = path || activeRoot.value
  loading.value = true
  error.value = ''
  selected.value = null
  try {
    const data = await props.api.post('/fs/list', {
      root: activeRoot.value,
      path: target,
      kind: listKind.value,
    })
    currentPath.value = data?.path || target
    parentPath.value = data?.parent || ''
    dirs.value = (data?.dirs || []).map((item) => ({
      name: item.name,
      path: item.path,
      fileCount: item.file_count ?? null,
    }))
    files.value = (data?.files || [])
      .filter((item) => matchesExt(item.name))
      .map((item) => ({
        name: item.name,
        path: item.path,
        size: item.size ?? null,
        ext: item.ext || '',
      }))
  } catch (err) {
    error.value = err.message || '读取目录失败'
    dirs.value = []
    files.value = []
  } finally {
    loading.value = false
  }
}

function init() {
  selected.value = null
  manualPath.value = ''
  error.value = ''
  if (!rootList.value.length) {
    error.value = '还没有配置媒体根目录，请先到设置里添加'
    return
  }
  let start = props.initialPath || ''
  if (start && isFileLike(start)) start = dirName(start)
  activeRoot.value = resolveRoot(start || rootList.value[0])
  const root = activeRoot.value
  if (!start || (start !== root && !String(start).startsWith(`${String(root).replace(/\/+$/, '')}/`))) {
    start = root
  }
  load(start || root)
}

function chooseRoot(root) {
  if (!root) return
  activeRoot.value = root
  load(root)
}

function enterDir(dir) {
  load(dir.path)
}

function goParent() {
  if (!parentPath.value) return
  load(parentPath.value)
}

function pick(file) {
  selected.value = file
}

function archiveExt(name) {
  const lower = String(name || '').toLowerCase()
  return ARCHIVE_EXTENSIONS.find((ext) => lower.endsWith(ext)) || ''
}

/** 压缩包选择兜底：后端 /fs/list 可能不列压缩包，允许直接输入完整路径。 */
function confirmManualArchive() {
  const path = manualPath.value.trim()
  if (!path) return
  const name = path.split('/').pop() || path
  const ext = archiveExt(name)
  if (!ext) {
    error.value = '请输入支持的压缩包路径（zip / 7z / rar / tar）'
    return
  }
  emit('select', { name, path, size: null, ext, kind: 'archive' })
  emit('update:modelValue', false)
}

function pickAndConfirm(file) {
  pick(file)
  confirmPick()
}

function confirmPick() {
  if (!selected.value) return
  emit('select', { ...selected.value, kind: props.kind })
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) init()
  },
)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    :max-width="dialogMaxWidth"
    :fullscreen="mobile"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="picker-dialog" :class="{ 'dialog-compact': mobile, 'dialog-medium': effectiveLayout === 'medium' }">
      <div class="picker-head">
        <span class="picker-title">{{ dialogTitle }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="emit('update:modelValue', false)" />
      </div>

      <div class="picker-body">
        <div class="picker-toolbar">
          <div class="picker-roots">
            <button
              v-for="root in rootList"
              :key="root"
              type="button"
              class="root-chip"
              :class="{ 'root-chip--active': root === activeRoot }"
              @click="chooseRoot(root)"
            >
              {{ root }}
            </button>
          </div>
          <v-btn
            size="x-small"
            variant="text"
            prepend-icon="mdi-arrow-up"
            :disabled="!parentPath || loading"
            @click="goParent"
          >
            上级
          </v-btn>
        </div>
        <div class="picker-path" :title="currentPath">{{ currentPath || '—' }}</div>

        <div v-if="kind === 'archive'" class="archive-manual">
          <v-text-field
            v-model="manualPath"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="也可直接输入压缩包完整路径，如 /media/fonts.zip"
            class="archive-manual-input mono"
            @keyup.enter="confirmManualArchive"
          />
          <v-btn size="small" variant="tonal" :disabled="!manualPath.trim()" @click="confirmManualArchive">
            使用此压缩包
          </v-btn>
        </div>

        <div class="picker-list">
          <v-progress-linear v-if="loading" indeterminate color="primary" class="picker-loading" />
          <template v-if="!loading">
            <div v-if="error" class="picker-empty picker-empty--error">{{ error }}</div>
            <template v-else>
              <div
                v-for="dir in dirs"
                :key="`dir-${dir.path}`"
                class="picker-row picker-row--dir"
                @click="enterDir(dir)"
              >
                <v-icon size="17" icon="mdi-folder-outline" />
                <span class="picker-name">{{ dir.name }}</span>
                <span v-if="dir.fileCount" class="picker-size">{{ dir.fileCount }} 项</span>
                <v-icon size="15" icon="mdi-chevron-right" class="picker-arrow" />
              </div>
              <div
                v-for="file in files"
                :key="`file-${file.path}`"
                class="picker-row"
                :class="{ 'picker-row--sel': selected && selected.path === file.path }"
                @click="pick(file)"
                @dblclick="pickAndConfirm(file)"
              >
                <v-icon size="17" icon="mdi-file-outline" />
                <span class="picker-name">{{ file.name }}</span>
                <span class="picker-size">{{ fmtBytes(file.size) }}</span>
              </div>
              <div v-if="!dirs.length && !files.length" class="picker-empty">
                当前目录没有可选的{{ kind === 'chapter' ? '章节文件' : '文件' }}
              </div>
            </template>
          </template>
        </div>

        <div class="picker-note">
          只列出当前类型允许的扩展名；选中后作为轨道 / 附件来源写入 MKV，不会复制或移动原文件。
        </div>
      </div>

      <div class="picker-foot">
        <v-spacer />
        <div class="picker-foot-btns">
          <v-btn variant="text" @click="emit('update:modelValue', false)">取消</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!selected" @click="confirmPick">选择此文件</v-btn>
        </div>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.picker-dialog {
  max-height: 70vh;
  /* 弹窗卡片完整包边 */
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
/* PC 模式（medium）：弹窗加高，往下多显示一些 */
.picker-dialog.dialog-medium {
  display: flex;
  flex-direction: column;
  height: min(78vh, 760px);
  max-height: 78vh;
}
.dialog-medium .picker-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow: auto;
}
.picker-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.picker-title {
  font-size: 14.5px;
  font-weight: 600;
}
.picker-body {
  padding: 16px 20px;
  overflow: auto;
  max-height: calc(70vh - 126px);
}
.picker-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.picker-roots {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
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
.root-chip--active {
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-primary), 0.1);
}
.picker-path {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  word-break: break-all;
  margin-bottom: 8px;
}
/* 压缩包选择：后端可能不列压缩包，提供直接输入完整路径的兜底 */
.archive-manual {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.archive-manual-input {
  flex: 1 1 auto;
  min-width: 0;
}
.archive-manual .v-btn {
  flex: 0 0 auto;
}
.picker-list {
  position: relative;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 10px;
  overflow: auto;
  max-height: 340px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.picker-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
}
.picker-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  cursor: pointer;
  min-height: 42px;
}
.picker-row:last-child {
  border-bottom: none;
}
.picker-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.picker-row--sel {
  background: rgba(var(--v-theme-primary), 0.14);
  box-shadow: inset 2px 0 0 rgb(var(--v-theme-primary));
}
.picker-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: rgb(var(--v-theme-on-surface));
}
.picker-size {
  flex: 0 0 auto;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.picker-arrow {
  flex: 0 0 auto;
  opacity: 0.5;
}
.picker-empty {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  padding: 18px 14px;
  text-align: center;
}
.picker-empty--error {
  color: rgb(var(--v-theme-error));
}
.picker-note {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  line-height: 1.6;
}
.picker-foot {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.picker-foot-btns {
  display: flex;
  gap: 10px;
}
/* 紧凑布局（真手机 or PC 模式容器窄）：全屏对话框内部改为纵向撑满 */
.picker-dialog.dialog-compact {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 0;
}
.dialog-compact .picker-body {
  flex: 1 1 auto;
  padding: 12px 14px;
  max-height: none;
}
.dialog-compact .picker-head,
.dialog-compact .picker-foot {
  flex: 0 0 auto;
}
.dialog-compact .picker-head {
  padding: 12px 14px;
}
.dialog-compact .picker-foot {
  padding: 10px 14px;
}
.dialog-compact .picker-foot-btns {
  flex: 1 1 auto;
}
.dialog-compact .picker-foot-btns > * {
  flex: 1 1 0;
}
.dialog-compact .picker-list {
  max-height: 52vh;
}
.dialog-compact .picker-row {
  min-height: 48px;
}
</style>
