<script setup>
import { computed, watch, onActivated, onMounted, onUnmounted, ref } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  // 插件总开关：停用时操作按钮置灰禁用
  enabled: { type: Boolean, default: true },
  // 数据变更信号（Page 递推）：其他页完成重新识别厂商等操作后，本页重拉最新数据
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

// ===== 查询状态（本地全量，前端构建目录树） =====
const search = ref('')
const vendorFilter = ref('')
const allFonts = ref([])       // 全量字体（来自 /fonts/tree）
const libDir = ref('')         // 字体库根目录
const loadingList = ref(false)
const loaded = ref(false)

// ===== 选中字体（右栏详情） =====
const selectedId = ref(null)
const selectedFont = computed(() => allFonts.value.find(f => f.id === selectedId.value) || null)

// ===== 「目录自动收集」开关联动 =====
// 开：监控字体自动归档进字体库，刷新时失效选中自动清理（现状）；
// 关：监控字体进「待确认」不归档，用户在整理时保留选中不被刷新打断
const autoCollect = ref(true)
async function refreshCollectFlag() {
  try {
    const data = await apiModule.get(props.api, '/config')
    autoCollect.value = data?.auto_collect !== false
  } catch (e) {
    /* 拉取失败保持默认（开） */
  }
}

// ===== 目录树 =====
const expandedDirs = ref(new Set())

// ===== 删除字体（记录+本地文件，二次确认） =====
const deleteDialog = ref(false)
const deleteTarget = ref(null)
const deleting = ref(false)

// ===== 待确认上传 =====
const pendingFonts = ref([])
const loadingPending = ref(false)
const uploadRef = ref(null)
const uploading = ref(false)
const confirming = ref(false)
const discarding = ref(false)
// 全量检查运行中：按钮转圈禁用，结束才恢复（防重复点击）
const scanning = ref(false)

// ===== 数据库备份/恢复 =====
const dbImportRef = ref(null)
const dbBusy = ref(false)
const clearDialog = ref(false)

// ===== 预览 =====
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const previewName = ref('')
const previewFamily = ref('')
const previewFont = ref(null)
const faceLoading = ref(false)
const faceError = ref('')
const PREVIEW_FONT_FAMILY = 'zt-preview-font'

function disposePreviewFont() {
  if (previewFont.value && document.fonts) {
    try {
      document.fonts.delete(previewFont.value)
    } catch (e) {
      // 忽略
    }
  }
  previewFont.value = null
}

// base64 -> ArrayBuffer（绕过 data URL 网络管线，根治 "A network error occurred"）
function base64ToArrayBuffer(b64) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes.buffer
}

// 用 ArrayBuffer 创建并加载 FontFace，避免 data: URL 被浏览器当作网络资源
async function loadPreviewFace(data) {
  const face = new FontFace(PREVIEW_FONT_FAMILY, base64ToArrayBuffer(data))
  await face.load()
  if (document.fonts) document.fonts.add(face)
  return face
}

// 把浏览器裸错误转成用户可读的中文提示
function friendlyPreviewError(e) {
  const msg = (e && e.message) || ''
  if (/Invalid font data|Unexpected end|Not a valid|Failed to decode|Couldn't parse/i.test(msg)) {
    return '该字体文件无法解析（可能是被截断、损坏，或为 TTC 集合等浏览器不支持的格式）'
  }
  return msg || '预览失败'
}

const previewStyle = computed(() => {
  if (!previewFont.value) return {}
  return { fontFamily: `'${PREVIEW_FONT_FAMILY}', sans-serif` }
})

// 厂商列表（来自 vendors 接口 + 当前列表聚合）
const vendorOptions = ref([])

// ===== 目录计算：file_path 相对 lib_dir 的所在目录 =====
function relDirOf(filePath) {
  if (!filePath) return ''
  let p = String(filePath).replace(/\\/g, '/')
  let base = libDir.value ? String(libDir.value).replace(/\\/g, '/').replace(/\/+$/, '') : ''
  if (base && p.startsWith(base + '/')) {
    p = p.slice(base.length + 1)
  }
  const idx = p.lastIndexOf('/')
  return idx >= 0 ? p.slice(0, idx) : ''
}

// ===== 构建扁平目录树节点 =====
const flatNodes = computed(() => {
  const dirMap = new Map() // relDir -> { path, label, depth, fonts: [] }
  const getDir = (relDir) => {
    if (!relDir) {
      const key = '__root__'
      if (!dirMap.has(key)) dirMap.set(key, { key, path: '', label: '未分类', depth: 0, fonts: [] })
      return dirMap.get(key)
    }
    const segs = relDir.split('/').filter(Boolean)
    const path = segs.join('/')
    if (dirMap.has(path)) return dirMap.get(path)
    const node = {
      key: 'dir:' + path,
      path,
      label: segs[segs.length - 1],
      depth: segs.length,
      fonts: [],
    }
    dirMap.set(path, node)
    return node
  }
  // 确保父目录节点存在
  const ensureParents = (dirNode) => {
    if (!dirNode || dirNode.depth <= 0 || dirNode.path.indexOf('/') < 0) return
    const parentPath = dirNode.path.slice(0, dirNode.path.lastIndexOf('/'))
    const parent = getDir(parentPath)
    ensureParents(parent)
  }

  let list = allFonts.value
  // 厂商过滤
  if (vendorFilter.value) {
    list = list.filter(f => f.vendor === vendorFilter.value)
  }
  // 关键字过滤：匹配时也保留目录
  const kw = (search.value || '').trim().toLowerCase()
  if (kw) {
    list = list.filter(f =>
      [f.name, f.family, f.vendor, f.designer, f.file_name].some(v => v && String(v).toLowerCase().includes(kw))
    )
  }
  for (const f of list) {
    const relDir = relDirOf(f.file_path)
    const dirNode = getDir(relDir)
    ensureParents(dirNode)
    dirNode.fonts.push(f)
  }
  // 递归统计：每个目录节点 = 自身直接字体 + 全部子目录（含嵌套）字体数，
  // 保证按格式分子文件夹后「厂商」层显示的是该厂商全部字体（如 方正/ttf/…ttf 归到方正 47）
  const dirKeys = [...dirMap.keys()].filter(k => k !== '__root__').sort((a, b) => b.split('/').length - a.split('/').length)
  for (const k of dirKeys) {
    const d = dirMap.get(k)
    d.total_fonts = d.total_fonts || d.fonts.length
    const parentPath = k.includes('/') ? k.slice(0, k.lastIndexOf('/')) : ''
    const parent = dirMap.get(parentPath)
    if (parent) parent.total_fonts = (parent.total_fonts || parent.fonts.length) + d.total_fonts
  }
  // 剔除空目录（关键字过滤后可能没有字体）
  const nodes = []
  const walk = (dirNode) => {
    if (!dirNode.fonts.length && dirNode.path !== '' && ![...dirMap.values()].some(d => d.path.startsWith(dirNode.path + '/'))) {
      return false // 空目录，不输出子节点
    }
    const dirChildren = [...dirMap.values()]
      .filter(d => d.depth === dirNode.depth + 1 && (d.path.startsWith(dirNode.path + '/') || (dirNode.path === '' && d.path.indexOf('/') < 0)))
      .sort((a, b) => {
        // 厂商层（一级目录）按字体数量从多到少，数量相同按名称；格式等子层保持名称排序
        if (dirNode.depth === 0) {
          return (b.total_fonts || 0) - (a.total_fonts || 0) || (a.label < b.label ? -1 : 1)
        }
        return a.label < b.label ? -1 : 1
      })
    const hasVisible = dirNode.fonts.length > 0 || dirChildren.length > 0
    if (hasVisible) {
      nodes.push({ key: 'dir:' + dirNode.path, type: 'dir', dir: dirNode, depth: dirNode.depth })
    }
    const isExpanded = kw ? true : expandedDirs.value.has(dirNode.path) || expandedDirs.value.has('__root__')
    if (isExpanded) {
      for (const child of dirChildren) walk(child)
      for (const f of [...dirNode.fonts].sort((a, b) => (a.id > b.id ? -1 : 1))) {
        nodes.push({ key: 'font:' + f.id, type: 'font', font: f, fontDir: dirNode, depth: dirNode.depth + 1 })
      }
    }
  }
  // 根目录下直接文件（厂商层：按字体数量从多到少，数量相同按名称）
  const rootChildren = [...dirMap.values()]
    .filter(d => d.depth === 1)
    .sort((a, b) => (b.total_fonts || 0) - (a.total_fonts || 0) || (a.label < b.label ? -1 : 1))
  const hasRoot = dirMap.has('__root__')
  const rootDir = dirMap.get('__root__')
  if (hasRoot && rootDir.fonts.length) {
    nodes.push({ key: 'dir:__root__', type: 'dir', dir: rootDir, depth: 0 })
    if (expandedDirs.value.has('__root__') || kw) {
      for (const f of [...rootDir.fonts].sort((a, b) => (a.id > b.id ? -1 : 1))) {
        nodes.push({ key: 'font:' + f.id, type: 'font', font: f, fontDir: rootDir, depth: 1 })
      }
    }
  }
  for (const child of rootChildren) walk(child)
  return nodes
})

function toggleDir(dir) {
  const set = new Set(expandedDirs.value)
  const key = dir.path || '__root__'
  if (set.has(key)) set.delete(key)
  else set.add(key)
  expandedDirs.value = set
}

// ===== 数据加载 =====
async function loadFonts() {
  loadingList.value = true
  try {
    const data = await apiModule.get(props.api, '/fonts/tree')
    allFonts.value = data.list || []
    libDir.value = data.lib_dir || ''
    loaded.value = true
    // 若当前选中字体已不存在则清除：
    // 目录自动收集开启时监控自动入库、删除后选中失效应自动清理；
    // 关闭时（监控字体在待确认、用户正在整理）保留选中，不做自动清理
    if (
      selectedId.value &&
      !allFonts.value.some(f => f.id === selectedId.value) &&
      autoCollect.value
    ) {
      selectedId.value = null
    }
  } catch (e) {
    emit('notify', e.message || '加载字体库失败')
  } finally {
    loadingList.value = false
  }
}

async function loadPending() {
  loadingPending.value = true
  try {
    pendingFonts.value = await apiModule.get(props.api, '/fonts/pending')
  } catch (e) {
    emit('notify', e.message || '加载待确认列表失败')
  } finally {
    loadingPending.value = false
  }
}

async function loadVendors() {
  try {
    vendorOptions.value = await apiModule.get(props.api, '/vendors')
  } catch (e) {
    // 忽略
  }
}

// ===== 交互（纯前端过滤，computed 自动响应） =====

// 点击左侧列表的「空白」区域取消选中（停止对焦）
function onListClick(e) {
  const el = e.target
  if (!el || !el.closest) return
  if (el.closest('.zt-font-item, .zt-dir-item, .zt-fav-icon, .v-chip, .v-btn')) return
  selectedId.value = null
}

// ===== 右栏详情：选中 + 加载真实字体大样 =====
async function selectFont(font) {
  if (!font) return
  selectedId.value = font.id
  disposePreviewFont()
  previewFont.value = null
  faceLoading.value = true
  faceError.value = ''
  try {
    const res = await apiModule.get(props.api, '/fonts/preview', { id: font.id })
    const data = res?.data || ''
    if (!data) {
      faceError.value = '该字体文件不存在或无法读取'
      return
    }
    const face = await loadPreviewFace(data)
    previewFont.value = face
  } catch (e) {
    faceError.value = friendlyPreviewError(e)
  } finally {
    faceLoading.value = false
  }
}

// ===== 删除字体（❌）：记录 + 本地文件 =====
function askDelete(font) {
  deleteTarget.value = font
  deleteDialog.value = true
}

async function confirmDelete() {
  const font = deleteTarget.value
  if (!font) return
  deleting.value = true
  try {
    const res = await apiModule.del(props.api, '/fonts/delete', { id: font.id })
    emit('notify', res?.file_deleted ? '字体及本地文件已删除' : '字体记录已删除', 'success')
    allFonts.value = allFonts.value.filter(f => f.id !== font.id)
    if (selectedId.value === font.id) selectedId.value = null
    loadPending()
    // 通知 Page 递推 refreshKey：仪表盘统计/厂商分布同步刷新
    emit('action', { type: 'font_deleted' })
  } catch (e) {
    emit('notify', e.message || '删除失败')
  } finally {
    deleting.value = false
    deleteDialog.value = false
    deleteTarget.value = null
  }
}

async function toggleFavorite(font) {
  try {
    await apiModule.post(props.api, '/fonts/toggle_favorite', { id: font.id })
    font.favorite = font.favorite ? 0 : 1
  } catch (e) {
    emit('notify', e.message || '收藏操作失败')
  }
}

async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），改为分批顺序上传，每批 3 个
  const BATCH = 3
  let total = 0
  uploading.value = true
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH)
      const form = new FormData()
      for (const file of chunk) form.append('file', file)
      const res = await props.api.post(
        `plugin/Zitifenlei/fonts/upload_preview`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      const body = res?.data ?? res
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '上传失败'}`)
        break
      } else {
        const item = body?.data ?? body
        total += (item?.count ?? chunk.length)
      }
    }
    emit('notify', `已加入待确认列表 ${total} 个字体`, 'success')
    loadPending()
  } catch (e) {
    emit('notify', e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function confirmUpload() {
  if (!pendingFonts.value.length) {
    emit('notify', '没有待确认的字体', 'warning')
    return
  }
  confirming.value = true
  try {
    const res = await apiModule.post(props.api, '/fonts/confirm_upload')
    const done = res?.processed ?? pendingFonts.value.length
    emit('notify', `已归档 ${done} 个字体`, 'success')
    pendingFonts.value = []
    loadFonts()
    loadPending()
    emit('action', { type: 'fonts_archived' })
  } catch (e) {
    emit('notify', e.message || '整理失败')
  } finally {
    confirming.value = false
  }
}

async function discardUpload() {
  if (!pendingFonts.value.length) return
  discarding.value = true
  try {
    await apiModule.post(props.api, '/fonts/discard_upload')
    emit('notify', '已全部丢弃', 'success')
    pendingFonts.value = []
  } catch (e) {
    emit('notify', e.message || '丢弃失败')
  } finally {
    discarding.value = false
  }
}

async function deletePending(id) {
  try {
    await apiModule.post(props.api, `/fonts/pending_delete/${id}`)
    pendingFonts.value = pendingFonts.value.filter(p => p.id !== id)
    if (!pendingFonts.value.length) {
      loadFonts()
    }
  } catch (e) {
    emit('notify', e.message || '删除失败')
  }
}

async function scanArchive() {
  if (scanning.value) return
  scanning.value = true
  try {
    const res = await apiModule.post(props.api, '/fonts/scan')
    const n = res?.added ?? 0
    if (n) {
      // 「目录自动收集」开启 → 直接入库；关闭 → 加入待确认
      emit('notify', autoCollect.value ? `全量检查完成，已归档 ${n} 个字体` : `全量检查完成，新增 ${n} 个待确认字体`, 'success')
      if (autoCollect.value) {
        loadFonts()
        loadVendors()
        emit('action', { type: 'fonts_archived' })
      }
    } else {
      emit('notify', '全量检查完成，无新增字体（已入库或已在待确认）', 'info')
    }
    loadPending()
  } catch (e) {
    emit('notify', e.message || '全量检查失败')
  } finally {
    scanning.value = false
  }
}

// ===== 数据库备份 / 恢复 / 清空 =====
async function exportDatabase() {
  dbBusy.value = true
  try {
    const data = await apiModule.get(props.api, '/db/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    a.download = `字体库备份_${ts}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    emit('notify', '数据库备份已导出', 'success')
  } catch (e) {
    emit('notify', e.message || '导出数据库失败')
  } finally {
    dbBusy.value = false
  }
}

async function handleDbImport(event) {
  const file = event.target.files?.[0]
  if (!file) return
  dbBusy.value = true
  try {
    const text = await file.text()
    const payload = JSON.parse(text)
    await apiModule.post(props.api, '/db/import', payload)
    emit('notify', '数据库已恢复，列表已刷新', 'success')
    await loadFonts()
    await loadPending()
    loadVendors()
  } catch (e) {
    emit('notify', e.message.includes('Unexpected token') ? '导入失败：备份文件格式不正确' : (e.message || '导入数据库失败'))
  } finally {
    dbBusy.value = false
    event.target.value = ''
  }
}

async function clearDatabase() {
  clearDialog.value = false
  dbBusy.value = true
  try {
    await apiModule.del(props.api, '/db/clear')
    emit('notify', '数据库已清空', 'success')
    selectedId.value = null
    allFonts.value = []
    await loadFonts()
    await loadPending()
    emit('action', { type: 'db_cleared' })
  } catch (e) {
    emit('notify', e.message || '清空数据库失败')
  } finally {
    dbBusy.value = false
  }
}

// ===== 预览对话框（放大） =====
async function openPreview(font) {
  disposePreviewFont()
  previewOpen.value = true
  previewLoading.value = true
  previewError.value = ''
  previewName.value = font.name || ''
  previewFamily.value = font.family || ''
  try {
    const res = await apiModule.get(props.api, '/fonts/preview', { id: font.id })
    previewName.value = res?.name || font.name || ''
    previewFamily.value = res?.family || font.family || ''
    const data = res?.data || ''
    if (!data) {
      previewError.value = '该字体文件不存在或无法读取'
      return
    }
    const face = await loadPreviewFace(data)
    previewFont.value = face
  } catch (e) {
    previewError.value = friendlyPreviewError(e)
  } finally {
    previewLoading.value = false
  }
}

// 统一数据刷新：全量拉目录树 + 待确认 + 厂商分布（保持选中/展开状态，不重置界面）
function refreshData() {
  loadFonts()
  loadPending()
  loadVendors()
}

// 30 秒轮询兜底：目录监控/入库自动归档写入新字体后，页面停留不动也能自动显示
let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(refreshData, 30000)
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  refreshCollectFlag()
  await loadFonts()
  loadPending()
  loadVendors()
  startPolling()
})

// 宿主详情页以 keep-alive 缓存子视图：每次进入字体库页时重新拉取，
// 确保「重新识别厂商」等操作在其他页完成后，左侧列表/厂商带到最新数据
onActivated(async () => {
  refreshCollectFlag()
  await loadFonts()
  loadPending()
  loadVendors()
})

// 兄弟页完成数据变更（如仪表盘「重新识别厂商」→ Page 递推 refreshKey）：
// 即使本页处于 keep-alive 缓存、未切换 Tab，也立即重拉，杜绝旧数据残留
watch(() => props.refreshKey, () => {
  refreshData()
})

onUnmounted(() => {
  stopPolling()
  disposePreviewFont()
})
</script>

<template>
  <div class="zt-font-library">
    <!-- 顶部操作栏：只保留常用按钮，危险操作全部移到底部「数据库管理」 -->
    <div class="zt-topbar">
      <v-btn
        variant="tonal"
        color="primary"
        :disabled="!enabled"
        :loading="uploading"
        @click="uploadRef?.click()"
      >
        <v-icon start size="18">mdi-upload</v-icon>
        上传字体
      </v-btn>
      <input
        ref="uploadRef"
        type="file"
        accept=".ttf,.otf,.TTF,.OTF"
        multiple
        style="display: none"
        @change="handleUpload"
      />
      <v-btn variant="tonal" :disabled="!enabled || scanning" :loading="scanning" title="全量检查：扫描字体监控目录中的字体（目录自动收集开启时直接入库，关闭时加入待确认区；运行中不可重复点击）" @click="scanArchive">
        <v-icon start size="18">mdi-magnify-scan</v-icon>
        全量检查
      </v-btn>
      <v-spacer></v-spacer>
      <span class="zt-total text-body-2">共 {{ allFonts.length }} 个字体</span>
    </div>

    <v-row no-gutters class="zt-font-row">
      <!-- 左栏：搜索 + 筛选 + 目录树 -->
      <v-col cols="12" md="5">
        <v-card class="zt-card-bg zt-list-card">
          <v-card-text class="pa-0">
            <div class="pa-3 pb-2">
              <v-text-field
                v-model="search"
                placeholder="搜索字体名称、厂商、设计师..."
                density="compact"
                variant="outlined"
                hide-details
                clearable
                prepend-inner-icon="mdi-magnify"
              ></v-text-field>
              <v-select
                v-model="vendorFilter"
                :items="vendorOptions"
                item-title="vendor"
                item-value="vendor"
                label="厂商筛选"
                density="compact"
                variant="outlined"
                hide-details
                clearable
                class="mt-2"
              ></v-select>
            </div>
            <v-divider></v-divider>
            <v-progress-linear v-if="loadingList" indeterminate color="primary"></v-progress-linear>
            <div v-if="!loadingList && loaded && !flatNodes.length" class="zt-empty pa-6" @click="selectedId = null">
              暂无字体，点击「上传字体」或「全量检查」添加
            </div>
            <div v-else class="zt-list-body" @click="onListClick">
              <v-list density="compact" class="pa-0" nav>
                <!-- 目录节点：v 箭头展开/收起 -->
                <template v-for="node in flatNodes" :key="node.key">
                  <v-list-item
                    v-if="node.type === 'dir'"
                    class="zt-dir-item"
                    :style="{ paddingLeft: (node.depth * 10) + 'px' }"
                    @click="toggleDir(node.dir)"
                  >
                    <template #prepend>
                      <v-icon size="18" class="mr-1">{{ expandedDirs.has(node.dir.path || '__root__') ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                      <v-icon size="16" color="info" class="mr-1">{{ expandedDirs.has(node.dir.path || '__root__') ? 'mdi-folder-open' : 'mdi-folder' }}</v-icon>
                    </template>
                    <v-list-item-title class="zt-dir-name">{{ node.dir.label }}</v-list-item-title>
                    <template #append>
                      <span class="zt-dir-count">{{ node.dir.total_fonts ?? node.dir.fonts.length }}</span>
                    </template>
                  </v-list-item>
                  <!-- 字体节点：❌ 删除（记录+本地文件） -->
                  <v-list-item
                    v-else
                    :active="selectedId === node.font.id"
                    class="zt-font-item"
                    :style="{ paddingLeft: (node.depth * 6 + (node.fontDir.path ? 10 : 30)) + 'px' }"
                    @click="selectFont(node.font)"
                  >
                    <v-list-item-title class="zt-font-name">
                      {{ node.font.name || node.font.family || node.font.file_name }}
                    </v-list-item-title>
                    <v-list-item-subtitle class="zt-font-meta">
                      {{ node.font.vendor || '未知厂商' }}
                      <v-chip
                        :color="node.font.source === 'manual' ? 'primary' : 'success'"
                        size="x-small"
                        variant="tonal"
                        class="ml-1"
                      >
                        {{ node.font.source === 'manual' ? '手动' : '自动' }}
                      </v-chip>
                    </v-list-item-subtitle>
                    <template #append>
                      <v-btn
                        size="x-small"
                        variant="text"
                        icon
                        class="zt-fav-icon"
                        :disabled="!enabled"
                        title="删除字体（含本地文件）"
                        @click.stop="askDelete(node.font)"
                      >
                        <v-icon size="16" color="error">mdi-close</v-icon>
                      </v-btn>
                    </template>
                  </v-list-item>
                </template>
              </v-list>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- 右栏：详情 + 大样预览 -->
      <v-col cols="12" md="7">
        <v-card class="zt-card-bg zt-detail-card">
          <v-card-text class="pa-0">
            <div v-if="!selectedFont" class="zt-empty pa-6">
              点击左侧字体查看详情与预览
            </div>
            <div v-else class="pa-4">
              <div class="d-flex align-center mb-3">
                <div class="flex-grow-1">
                  <div class="zt-detail-title zt-font-name">{{ selectedFont.name || selectedFont.family || selectedFont.file_name }}</div>
                  <div class="zt-detail-meta">
                    {{ selectedFont.family || '未知字族' }}
                    <v-chip
                      :color="selectedFont.source === 'manual' ? 'primary' : 'success'"
                      size="x-small"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ selectedFont.source === 'manual' ? '手动' : '自动' }}
                    </v-chip>
                    <v-chip
                      v-if="selectedFont.status === '待整理'"
                      size="x-small"
                      variant="tonal"
                      class="ml-1"
                    >
                      <v-icon size="14" class="mr-1">mdi-clock-outline</v-icon>待整理
                    </v-chip>
                  </div>
                </div>
                <v-btn
                  size="small"
                  variant="tonal"
                  :color="selectedFont.favorite ? 'warning' : ''"
                  class="mr-2"
                  :disabled="!enabled"
                  @click="toggleFavorite(selectedFont)"
                >
                  <v-icon size="16">{{ selectedFont.favorite ? 'mdi-star' : 'mdi-star-outline' }}</v-icon>
                  收藏
                </v-btn>
                <v-btn size="small" variant="tonal" @click="openPreview(selectedFont)">
                  <v-icon size="16">mdi-arrow-expand</v-icon>
                  放大
                </v-btn>
              </div>

              <v-divider class="mb-3"></v-divider>

              <!-- 元数据 -->
              <div class="zt-meta-grid mb-3">
                <div class="zt-meta-item">
                  <div class="zt-meta-label">厂商</div>
                  <div class="zt-meta-value">{{ selectedFont.vendor || '未知厂商' }}</div>
                </div>
                <div class="zt-meta-item">
                  <div class="zt-meta-label">设计师</div>
                  <div class="zt-meta-value">{{ selectedFont.designer || '未知设计师' }}</div>
                </div>
                <div class="zt-meta-item">
                  <div class="zt-meta-label">文件名</div>
                  <div class="zt-meta-value">{{ selectedFont.file_name }}</div>
                </div>
                <div class="zt-meta-item">
                  <div class="zt-meta-label">大小</div>
                  <div class="zt-meta-value">{{ selectedFont.file_size ? (selectedFont.file_size / 1024).toFixed(0) + ' KB' : '-' }}</div>
                </div>
              </div>

              <!-- 大样预览 -->
              <div class="zt-section-label mb-2">
                <v-icon start size="16">mdi-format-font</v-icon>
                字体预览
              </div>
              <div class="zt-preview-sample">
                <v-progress-circular
                  v-if="faceLoading"
                  indeterminate
                  size="28"
                  class="ma-4"
                ></v-progress-circular>
                <div v-else-if="faceError" class="zt-empty pa-4">{{ faceError }}</div>
                <div v-else :style="previewStyle">
                  <div style="font-size: 42px; font-weight: 700">观沧海</div>
                  <div style="font-size: 16px; margin-top: 8px">
                    ABCDEFGHIJKLM · abcdefghijklm · 0123456789
                  </div>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 待确认上传区域 -->
    <v-card v-if="pendingFonts.length" class="zt-card-bg mt-4 zt-pending">
      <v-card-title class="zt-card-title">
        <v-icon start size="18" color="warning">mdi-alert-circle-outline</v-icon>
        待确认上传（{{ pendingFonts.length }}）
      </v-card-title>
      <v-card-text class="pa-0">
        <v-list lines="one" density="compact" class="pa-0">
          <v-list-item v-for="p in pendingFonts" :key="p.id">
            <template #prepend>
              <v-icon color="warning" size="18">mdi-alert</v-icon>
            </template>
            <v-list-item-title class="zt-font-name">
              {{ p.name || p.file_name }}
            </v-list-item-title>
            <v-list-item-subtitle class="zt-font-meta">
              {{ p.vendor || '未知厂商' }} · {{ p.file_size ? (p.file_size / 1024).toFixed(0) + 'KB' : '' }}
            </v-list-item-subtitle>
            <template #append>
              <v-btn
                size="small"
                variant="text"
                icon
                :disabled="!enabled"
                title="删除该项"
                @click="deletePending(p.id)"
              >
                <v-icon size="16">mdi-close</v-icon>
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
        <div class="d-flex pa-3 flex-wrap">
          <v-btn
            color="success"
            variant="tonal"
            class="mr-2"
            :disabled="!enabled"
            :loading="confirming"
            @click="confirmUpload"
          >
            <v-icon start size="18">mdi-check-all</v-icon>
            一键整理
          </v-btn>
          <v-btn
            color="error"
            variant="tonal"
            :disabled="!enabled"
            :loading="discarding"
            @click="discardUpload"
          >
            <v-icon start size="18">mdi-trash-can-outline</v-icon>
            全部丢弃
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- 数据库管理区块：危险操作收拢于此，远离顶部关闭按钮 -->
    <v-card class="zt-card-bg mt-4 zt-db-block">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-database-cog-outline</v-icon>
        数据库管理
      </v-card-title>
      <v-card-text class="d-flex align-center flex-wrap pa-3">
        <v-btn
          variant="tonal"
          color="primary"
          size="small"
          class="mr-2 mb-2"
          :disabled="!enabled"
          :loading="dbBusy"
          @click="exportDatabase"
        >
          <v-icon start size="18">mdi-database-export-outline</v-icon>
          导出数据库
        </v-btn>
        <v-btn
          variant="tonal"
          size="small"
          class="mr-2 mb-2"
          :disabled="!enabled"
          :loading="dbBusy"
          @click="dbImportRef?.click()"
        >
          <v-icon start size="18">mdi-database-import-outline</v-icon>
          导入数据库
        </v-btn>
        <input
          ref="dbImportRef"
          type="file"
          accept=".json,application/json"
          style="display: none"
          @change="handleDbImport"
        />
        <v-btn
          variant="tonal"
          color="error"
          size="small"
          class="mb-2"
          :disabled="!enabled"
          @click="clearDialog = true"
        >
          <v-icon start size="18">mdi-database-remove-outline</v-icon>
          清空数据库
        </v-btn>
      </v-card-text>
    </v-card>

    <!-- 删除字体确认对话框 -->
    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card class="zt-card-bg">
        <v-card-title class="zt-card-title">
          <v-icon start size="18" color="error">mdi-alert-outline</v-icon>
          删除字体
        </v-card-title>
        <v-card-text>
          将删除字体「{{ deleteTarget?.name || deleteTarget?.file_name }}」的数据库记录，
          并<strong>同时删除本地字体文件</strong>。此操作不可恢复，是否继续？
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog = false">取消</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleting" @click="confirmDelete">
            <v-icon start size="18">mdi-delete-outline</v-icon>
            确认删除
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 清空数据库确认对话框 -->
    <v-dialog v-model="clearDialog" max-width="420">
      <v-card class="zt-card-bg">
        <v-card-title class="zt-card-title">
          <v-icon start size="18" color="error">mdi-alert-outline</v-icon>
          清空数据库
        </v-card-title>
        <v-card-text>
          将删除所有字体、待确认与 ASS 检查记录。此操作不可恢复，建议先「导出数据库」备份。
          是否继续？
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="clearDialog = false">取消</v-btn>
          <v-btn color="error" variant="tonal" :loading="dbBusy" @click="clearDatabase">
            <v-icon start size="18">mdi-database-remove-outline</v-icon>
            确定清空
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 放大预览对话框 -->
    <v-dialog v-model="previewOpen" max-width="420">
      <v-card class="zt-card-bg">
        <v-card-title class="zt-card-title">
          <v-icon start size="18">mdi-format-font</v-icon>
          字体预览
        </v-card-title>
        <v-card-text>
          <v-progress-circular
            v-if="previewLoading"
            indeterminate
            class="zt-preview-loading"
          ></v-progress-circular>
          <div v-else-if="previewError" class="zt-empty">{{ previewError }}</div>
          <div v-else class="zt-preview-body">
            <div class="zt-preview-name mb-2">{{ previewName }}</div>
            <div class="zt-preview-family mb-3">{{ previewFamily }}</div>
            <div class="zt-preview-sample" :style="previewStyle">
              <span style="font-size: 42px; font-weight: 700">观沧海</span>
              <span style="font-size: 16px; display: block; margin-top: 8px">
                ABCDEFGHIJKLM abcdefghijklm 0123456789
              </span>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.zt-topbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.zt-list-card,
.zt-detail-card {
  height: 640px;
  overflow: auto;
}
.zt-list-body {
  min-height: 60px;
}
.zt-total {
  opacity: 0.75;
}
.zt-dir-item {
  cursor: pointer;
}
.zt-dir-name {
  font-size: 13px;
  font-weight: 600;
}
.zt-dir-count {
  font-size: 12px;
  opacity: 0.6;
}
.zt-font-item {
  cursor: pointer;
}
.zt-font-name {
  font-size: 14px;
  font-weight: 500;
}
.zt-font-meta {
  font-size: 12px;
  opacity: 0.7;
}
.zt-fav-icon {
  cursor: pointer;
}
.zt-card-title {
  font-size: 15px;
  font-weight: 600;
}
.zt-empty {
  font-size: 13px;
  opacity: 0.6;
  text-align: center;
  cursor: default;
}
.zt-detail-title {
  font-size: 17px;
  font-weight: 600;
}
.zt-detail-meta {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 2px;
}
.zt-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.zt-meta-label {
  font-size: 12px;
  opacity: 0.6;
}
.zt-meta-value {
  font-size: 13px;
  font-weight: 500;
  word-break: break-all;
}
.zt-section-label {
  font-size: 14px;
  font-weight: 600;
}
.zt-preview-sample {
  padding: 16px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  text-align: center;
  min-height: 120px;
}
.zt-preview-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
.zt-preview-name {
  font-size: 16px;
  font-weight: 600;
}
.zt-preview-family {
  font-size: 13px;
  opacity: 0.75;
}
/* 数据库管理区块：与顶部拉开视觉距离，避免误触 */
.zt-db-block {
  border: 1px dashed rgba(255, 255, 255, 0.12);
}
.zt-db-block :deep(.v-card-title) {
  padding-bottom: 4px;
}
</style>