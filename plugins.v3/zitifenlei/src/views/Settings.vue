<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  // 宿主在打开配置弹窗时通过 GET /plugin/form/{id} 拉取的合并 model（默认值+已存配置）
  initialConfig: { type: Object, default: () => ({}) },
  // 插件总开关（数据页传入，与 config.enabled 同源；声明用于避免 attrs 落到根元素）
  enabled: { type: Boolean, default: true },
})
const emit = defineEmits(['notify', 'save'])

const DEFAULT_CONFIG = {
  enabled: true,
  input_dir: '',
  lib_dir: '',
  ass_dir: '',
  subset_dir: '',
  // 字体监控目录内的压缩包：解压整理成功后是否自动清理（只作用于直接归档成功的包）
  archive_cleanup_enabled: false,
  // 清理方式：move = 移到对应监控目录下的「已处理压缩包/」；delete = 直接删除
  archive_cleanup_action: 'move',
  // 字幕压缩包筛选：all=全部 / sc=仅简体 / tc=仅繁体 / custom=自定义关键词
  subtitle_archive_filter: 'all',
  subtitle_archive_keywords: '',
  archive_mode: 'copy',
  // 移动归档时删除判重跳过的残留源文件（只作用于「移动原文件」模式）
  move_delete_duplicate: true,
  // 是否利用字体内部名称命名（开：用字体内部 PostScript 名；关：保持原文件名）
  font_name_internal: false,
  // 单字体文件大小上限（MB）：超过该值不做哈希/解析、不接受上传
  max_font_mb: 128,
  auto_inbound: true,
  auto_collect: true,
  notify_enabled: false,
  // 索引维护：启动轻检（stat 级校验，索引为空时从磁盘重建）+ 每周差异核对（定时增量比对）
  startup_light_check: true,
  weekly_reconcile: true,
  auto_subset: false,
  // MP 入库成品是否直接替换媒体库原字幕（与「监控目录输出方式」独立）
  inbound_subset_overwrite: false,
  subset_out_dir: '',
  subset_out_mode: 'copy',
  // HDR 字幕亮度：hdr_brightness=开关（选档位即自动开启），hdr_brightness_level=档位（空=关闭）
  hdr_brightness: false,
  hdr_brightness_level: '',
  // 种子字体收集：总开关 + 兜底扫描间隔 + 关键词/上限 + 收集去向
  torrent_enabled: false,
  torrent_scan_interval_min: 30,
  torrent_keywords: 'font,fonts,字体',
  torrent_max_file_mb: 2048,
  torrent_max_files: 500,
  torrent_to_pending: false,
}

// 数据源：宿主 initial-config（默认值+已存配置）；进入页面后立即用后端权威配置回填，
// 避免详情页（Page 场景）拿不到 initialConfig 时表单显示默认空值、一保存就覆盖真实配置。
const config = ref({ ...DEFAULT_CONFIG, ...(props.initialConfig || {}) })
const saving = ref(false)

const archiveModes = [
  { title: '复制保留原文件', value: 'copy', description: '归档时复制字体到字体库目录' },
  { title: '移动原文件', value: 'move', description: '归档时移动字体到字体库目录' },
]
// 压缩包清理方式（archive_cleanup_action）：长文案用单选而非下拉，手机端不截断
const archiveCleanupActions = [
  { title: '移动到「已处理压缩包」/（可找回，推荐）', value: 'move', description: '在对应监控目录下单独存放，确认无用后可自行删除' },
  { title: '直接删除（不可恢复）', value: 'delete', description: '处理成功后立即删除原压缩包：省空间，但删了找不回' },
]
// 字幕压缩包：一个包常同时有 SC（简体）/ TC（繁体）两个字幕，按文件名选择要处理的
const subtitleArchiveFilters = [
  { title: '全部字幕（默认）', value: 'all' },
  { title: '仅简体（SC / CHS / 简 / zh-hans）', value: 'sc' },
  { title: '仅繁体（TC / CHT / 繁 / zh-hant）', value: 'tc' },
  { title: '自定义关键词（自己填）', value: 'custom' },
]
const subsetOutModes = [
  { title: '复制到输出目录', value: 'copy', description: '成品复制到输出目录，监控目录的源字幕保留（默认）' },
  { title: '移动到输出目录', value: 'move', description: '成品移动到输出目录，输出成功后删除监控目录的源字幕' },
]
// HDR 字幕亮度档位（关闭 / 档位即纯白亮度百分比，对应 ASS 色码压暗比例）
const hdrLevels = [
  { title: '关闭（不调整亮度）', value: '' },
  { title: '100% 纯白（&H00FFFFFF）· 仅 SDR 片源', value: '100' },
  { title: '85%（&H00D9D9D9）· 折中保守档', value: '85' },
  { title: '80%（&H00CCCCCC）· HDR 主流推荐 ⭐', value: '80' },
  { title: '75%（&H00BFBFBF）· 暗场多的片子', value: '75' },
  { title: '70%（&H00B2B2B2）· OLED/MiniLED 暗室', value: '70' },
  { title: '63%（&H00A1A1A1）· 模拟 SDR 白观感', value: '63' },
  { title: '50% 中灰（&H00808080）· 极端场景', value: '50' },
]
// MP 入库时对字幕做什么（映射 auto_inbound / auto_subset，两者互斥）
const inboundModes = [
  { title: '不处理（入库时不碰字幕）', value: 'none' },
  { title: '自动检查字幕（扫描该剧 ASS，汇总缺失字体）', value: 'check' },
  { title: '自动子集化（新增字幕子集化并内嵌字体）', value: 'subset' },
]

// 「MP 入库时」三选一 ↔ auto_inbound / auto_subset 互斥映射（两个都关 = 不处理）
const inboundMode = computed({
  get() {
    if (config.value.auto_subset) return 'subset'
    if (config.value.auto_inbound) return 'check'
    return 'none'
  },
  set(v) {
    config.value.auto_inbound = v === 'check'
    config.value.auto_subset = v === 'subset'
  },
})

// 「HDR 字幕亮度」下拉 ↔ hdr_brightness(bool) + hdr_brightness_level(string)
// 选档位 = 自动开启（保持原有行为）；选「关闭」= 关闭并清空档位
const hdrSelection = computed({
  get() {
    if (!config.value.hdr_brightness) return ''
    return config.value.hdr_brightness_level || '80'
  },
  set(v) {
    if (!v) {
      config.value.hdr_brightness = false
      config.value.hdr_brightness_level = ''
    } else {
      config.value.hdr_brightness = true
      config.value.hdr_brightness_level = String(v)
    }
  },
})

// 拉取后端权威配置回填表单（详情页/配置弹窗统一入口）
// 对齐 subscribeplus：数据页复用配置 UI 时先 GET /config 取当前值，
// 避免表单显示默认值导致一保存就把真实配置覆盖成空。
async function loadConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await apiModule.get(props.api, '/config')
    if (data && typeof data === 'object') {
      const { dirs, ...cfg } = data
      config.value = { ...DEFAULT_CONFIG, ...cfg }
    }
  } catch (e) {
    // 读取失败保持初始配置（弹窗场景 initialConfig 已经够用）
  }
}

// 保存（对齐 subscribeplus_v0.23 单通道范式，杜绝双保存冲突）：
// 1) POST /config 由后端 update_config 写入宿主原生配置并热生效；
// 2) GET /config 校验回填权威值（enabled 以运行时为准），开关不再回跳；
// 3) emit('save') 仅用于父组件本地状态同步（停用遮罩即时生效），不请求宿主再 PUT。
async function save() {
  saving.value = true
  try {
    // HDR 开关开启但档位为空 → 给默认推荐档 80%
    if (config.value.hdr_brightness && !config.value.hdr_brightness_level) {
      config.value.hdr_brightness_level = '80'
    }
    if (!config.value.hdr_brightness) {
      config.value.hdr_brightness_level = ''
    }
    // 字体大小上限规范化成整数 MB（越界/空值回落到默认 128，与后端 set_max_font_mb 一致）
    const mb = Number(config.value.max_font_mb)
    config.value.max_font_mb = Number.isFinite(mb) && mb > 0 ? Math.min(4096, Math.max(8, Math.round(mb))) : 128
    // 种子收集数值项规范化（0 对延迟/等待是合法值，不能被默认值吞掉）
    const normInt = (v, d, min, max) => {
      const n = Number(v)
      return Number.isFinite(n) ? Math.min(max, Math.max(min, Math.round(n))) : d
    }
    config.value.torrent_scan_interval_min = normInt(config.value.torrent_scan_interval_min, 30, 1, 1440)
    config.value.torrent_max_file_mb = normInt(config.value.torrent_max_file_mb, 2048, 1, 40960)
    config.value.torrent_max_files = normInt(config.value.torrent_max_files, 500, 1, 5000)
    if (typeof props.api?.post === 'function') {
      await apiModule.post(props.api, '/config', { ...config.value })
      try {
        const data = await apiModule.get(props.api, '/config')
        if (data && typeof data === 'object') {
          const { dirs, ...cfg } = data
          config.value = { ...DEFAULT_CONFIG, ...cfg }
        }
      } catch (e) {
        // 校验回填失败忽略，保留本地已存配置
      }
      emit('save', { ...config.value })
      emit('notify', '配置已保存并生效；插件列表状态将在刷新后更新', 'success')
    } else {
      // 兜底：无 API 通道时交由宿主原生保存
      emit('save', { ...config.value })
      emit('notify', '配置已保存', 'success')
    }
    loadTorrentStatus()
  } catch (e) {
    emit('notify', e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadConfig()
  loadTorrentStatus()
  loadProcessedArchives()
})

// ── 种子字体收集：状态 / 立即检查 / 基线 / 记录 ──────────────────────
const torrentStatus = ref({ downloaders: [], tools: {}, baseline_text: '', running: 0 })
const torrentRecords = ref([])
const torrentStatusLoaded = ref(false)
const torrentBusy = ref(false)
const torrentClearing = ref(false)
// 种子卡默认折叠：折叠时只显示总开关 + 一行状态摘要
const torrentExpanded = ref(false)
// 一键安装容器内解压工具（.7z/.rar 上传与种子字体收集都依赖它）
const archiveToolInstalling = ref(false)

const TORRENT_STATUS_TEXT = { done: '完成', empty: '无字体', failed: '失败', partial: '部分成功' }
const recordStatusText = (s) => TORRENT_STATUS_TEXT[s] || s || ''
const torrentToolText = computed(() => {
  const t = torrentStatus.value.tools || {}
  const parts = ['zip 内置']
  parts.push(t.seven_zip ? '7z 可用' : '7z 未安装')
  parts.push(t.rar ? 'rar 可用' : 'rar 未安装')
  return parts.join(' · ')
})
const torrentDownloaderText = computed(() => {
  const list = torrentStatus.value.downloaders || []
  if (!list.length) return '未发现已启用的下载器'
  return list.map((d) => `${d.name}（${d.type || '未知'}${d.available ? '' : '，不可用'}）`).join('、')
})
// 解压工具状态：未取到数据时显示「检测中…」，取到但无工具信息时显示「未检测到」
const torrentToolStatusText = computed(() => {
  if (!torrentStatusLoaded.value) return '检测中…'
  const t = torrentStatus.value.tools || {}
  if (!Object.keys(t).length) return '未检测到解压工具信息'
  return torrentToolText.value
})
const torrentDownloaderStatusText = computed(() => (
  torrentStatusLoaded.value ? torrentDownloaderText.value : '检测中…'
))
const torrentBaselineStatusText = computed(() => {
  if (!torrentStatusLoaded.value) return '检测中…'
  return torrentStatus.value.baseline_text || '未设置'
})

async function loadTorrentStatus() {
  if (typeof props.api?.get !== 'function') {
    torrentStatusLoaded.value = true
    return
  }
  try {
    const st = await apiModule.get(props.api, '/torrent/status')
    if (st && typeof st === 'object') {
      torrentStatus.value = {
        downloaders: st.downloaders || [],
        tools: st.tools || {},
        baseline_text: st.baseline_text || '',
        running: st.running || 0,
      }
    }
  } catch (e) {
    // 状态读取失败不影响配置编辑
  } finally {
    torrentStatusLoaded.value = true
  }
  try {
    const rec = await apiModule.get(props.api, '/torrent/records', { limit: 5 })
    torrentRecords.value = (rec && rec.items) || []
  } catch (e) {
    torrentRecords.value = []
  }
}

async function scanTorrents() {
  if (torrentBusy.value) return
  torrentBusy.value = true
  try {
    const res = await apiModule.post(props.api, '/torrent/scan', {})
    const scanned = Number(res?.scanned || 0)
    const queued = Number(res?.queued || 0)
    const skipped = Number(res?.skipped || 0)
    emit('notify', `扫描 ${scanned} 个已完成种子，入队 ${queued} 个（跳过历史 ${skipped} 个）`, 'success')
    await loadTorrentStatus()
  } catch (e) {
    emit('notify', e.message || '检查下载器失败')
  } finally {
    torrentBusy.value = false
  }
}

// 一键在容器内安装解压工具（apt/apk 安装 unar/7zip）；容器重建/更新镜像后需要重新安装
async function installArchiveTools() {
  if (archiveToolInstalling.value) return
  archiveToolInstalling.value = true
  try {
    const res = await apiModule.post(props.api, '/archive/tools/install', {})
    emit('notify', res?.message || '解压工具安装完成', 'success')
    await loadTorrentStatus()
  } catch (e) {
    emit('notify', e.message || '安装解压工具失败')
  } finally {
    archiveToolInstalling.value = false
  }
}

async function resetTorrentBaseline() {
  try {
    await apiModule.post(props.api, '/torrent/baseline', {})
    emit('notify', '基线已重置为当前时间，之后完成的种子才会被收集', 'success')
    await loadTorrentStatus()
  } catch (e) {
    emit('notify', e.message || '重置基线失败')
  }
}

async function clearTorrentRecords() {
  if (torrentClearing.value) return
  torrentClearing.value = true
  try {
    const res = await apiModule.del(props.api, '/torrent/records')
    emit('notify', `已清空 ${Number(res?.removed || 0)} 条记录（只删记录，不动字体库与下载目录）`, 'success')
    await loadTorrentStatus()
  } catch (e) {
    emit('notify', e.message || '清空记录失败')
  } finally {
    torrentClearing.value = false
  }
}

// 字体索引状态与「全部重建」已移至子集化页；HarfBuzz 依赖状态见仪表盘-依赖

// 「插件总开关」拨向关闭时拦截：后台有任务（全量检查/扫描/子集化运行中）则弹提示并取消关闭，
// 保住 v1.2.13 优雅停止的前提——先不触发 stop_service，任务跑完再关，不留任何半截状态
const busyDialog = ref(false)
const checkingBusy = ref(false)
async function onEnabledToggle(val) {
  if (val === config.value.enabled) return
  if (val === false) {
    checkingBusy.value = true
    try {
      const st = await apiModule.get(props.api, '/task/status')
      if (st && st.busy) {
        busyDialog.value = true
        return // 有任务运行：不切换，弹提示
      }
    } catch (e) {
      // 接口异常时不拦截，放行（避免查询失败把开关卡死）
    } finally {
      checkingBusy.value = false
    }
  }
  config.value.enabled = val
}

// 「入库自动检查字幕」与「入库后自动子集化」互斥：同一批入库字幕只走一种处理，
// 一次只允许开一个——开检查自动关子集化，开子集化自动关检查，避免用户两开打架。
watch(() => config.value.auto_inbound, (v) => {
  if (v) config.value.auto_subset = false
})
watch(() => config.value.auto_subset, (v) => {
  if (v) config.value.auto_inbound = false
})

// ── 已处理压缩包管理（字体/字幕压缩包清理后移到各目录「已处理压缩包/」）──
const processedArchives = ref([])
const processedLoading = ref(false)
const processedBusy = ref('')
const totalProcessedSize = computed(() => (
  processedArchives.value.reduce((sum, item) => sum + (Number(item.size) || 0), 0)
))
function formatProcessedSize(value) {
  const num = Number(value) || 0
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  if (num < 1024 * 1024 * 1024) return (num / 1024 / 1024).toFixed(1) + ' MB'
  return (num / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}
function formatProcessedTime(ts) {
  try {
    return new Date((Number(ts) || 0) * 1000).toLocaleString()
  } catch (e) {
    return ''
  }
}
async function loadProcessedArchives() {
  if (typeof props.api?.get !== 'function') return
  processedLoading.value = true
  try {
    const data = await apiModule.get(props.api, '/archives/processed')
    processedArchives.value = Array.isArray(data?.items) ? data.items : []
  } catch (e) {
    emit('notify', e.message || '读取已处理压缩包失败', 'error')
  } finally {
    processedLoading.value = false
  }
}
async function removeProcessedArchive(item) {
  if (!item || !item.path) return
  if (!window.confirm('删除压缩包？\n' + item.name + '\n\n（只删「已处理压缩包/」里的副本，不影响原目录）')) return
  processedBusy.value = item.path
  try {
    const res = await apiModule.post(props.api, '/archives/processed/remove', { paths: [item.path] })
    emit('notify', res.message || '已删除压缩包', 'success')
    await loadProcessedArchives()
  } catch (e) {
    emit('notify', e.message || '删除失败', 'error')
  } finally {
    processedBusy.value = ''
  }
}
async function restoreProcessedArchive(item) {
  if (!item || !item.path) return
  if (!window.confirm('恢复压缩包到「' + item.source + '」？\n' + item.name + '\n\n恢复后会重新被监控处理，请确认。')) return
  processedBusy.value = item.path
  try {
    const res = await apiModule.post(props.api, '/archives/processed/restore', { path: item.path })
    emit('notify', res.message || '已恢复压缩包', 'success')
    await loadProcessedArchives()
  } catch (e) {
    emit('notify', e.message || '恢复失败', 'error')
  } finally {
    processedBusy.value = ''
  }
}
async function clearProcessedArchives() {
  if (!processedArchives.value.length) return
  if (!window.confirm('清空全部已处理压缩包？共 ' + processedArchives.value.length + ' 个，不可恢复。\n\n（只删「已处理压缩包/」里的副本，不影响原目录）')) return
  processedBusy.value = 'clear'
  try {
    const res = await apiModule.post(props.api, '/archives/processed/clear', {})
    emit('notify', res.message || '已清空已处理压缩包', 'success')
    await loadProcessedArchives()
  } catch (e) {
    emit('notify', e.message || '清空失败', 'error')
  } finally {
    processedBusy.value = ''
  }
}

</script>

<template>
  <div class="zt-settings" style="max-width: min(100%, 960px)">
    <!-- 1. 插件总开关 -->
    <v-card class="zt-card-bg">
      <v-card-title class="zt-card-title">
        <v-icon start size="18" :color="config.enabled ? 'success' : 'error'">mdi-power</v-icon>
        插件总开关
      </v-card-title>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">启用字体分类管家</div>
            <div class="zt-switch-desc">关闭后插件所有功能不可用、后台定时任务停止，保存配置后生效</div>
          </div>
          <v-switch
            :model-value="config.enabled"
            color="success"
            density="compact"
            hide-details
            :loading="checkingBusy"
            @update:model-value="onEnabledToggle"
          ></v-switch>
        </div>
        <v-alert
          v-if="!config.enabled"
          type="warning"
          density="compact"
          class="mt-2"
        >
          插件已停用：其他页面将不可操作，仅可在本页重新开启。
        </v-alert>
      </v-card-text>
    </v-card>

    <div class="zt-disabled-zone" :class="{ 'is-off': !config.enabled }">
    <!-- 2. 目录与压缩包 -->
    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-folder-cog-outline</v-icon>
        目录与压缩包
      </v-card-title>
      <v-card-text>
        <div class="zt-hint mb-2">
          监控按「目录类型」严格处理：字体监控目录收字体/字体压缩包，ASS 字幕检查目录与自动子集化目录收 .ass/字幕压缩包；
          放错目录的文件会跳过并写入「最近操作日志」，不会误归档或误检查。
        </div>
        <v-row dense>
          <v-col cols="12" sm="6" class="py-2">
            <v-text-field
              v-model="config.input_dir"
              label="字体监控目录"
              placeholder="/media/fonts/incoming"
              density="compact"
              variant="outlined"
              hint="新字体或字体压缩包（.zip/.7z/.rar，自动安全解压后逐个归档）放这里即自动入库"
              persistent-hint
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" class="py-2">
            <v-text-field
              v-model="config.lib_dir"
              label="字体库目录"
              placeholder="/media/fonts/library"
              density="compact"
              variant="outlined"
              hint="字体唯一来源：检查与子集化都按这里的字体逐字符比对"
              persistent-hint
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" class="py-2">
            <v-text-field
              v-model="config.ass_dir"
              label="ASS 字幕检查目录"
              placeholder="/media/subtitles"
              density="compact"
              variant="outlined"
              hint="放入 .ass 或字幕压缩包（.zip/.7z/.rar，只解 .ass）自动检查缺字体"
              persistent-hint
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" class="py-2">
            <v-text-field
              v-model="config.subset_dir"
              label="ASS 自动子集化目录"
              placeholder="/media/subtitles/subset"
              density="compact"
              variant="outlined"
              hint="放入 .ass 或字幕压缩包（.zip/.7z/.rar，只解 .ass）自动子集化并内嵌字体，成品按「输出目录/剧名/」输出"
              persistent-hint
            ></v-text-field>
          </v-col>
          <v-col cols="12" class="py-2">
            <v-text-field
              v-model="config.subset_out_dir"
              label="子集化输出目录"
              placeholder="/media/subtitles/subset-out"
              density="compact"
              variant="outlined"
              hint="「ASS 自动子集化目录」的成品落点，按剧名分到子文件夹；手动上传字幕的结果留在插件临时目录，不受此设置影响"
              persistent-hint
            ></v-text-field>
          </v-col>
        </v-row>

        <!-- 压缩包处理 -->
        <div class="zt-subblock mt-4">
          <div class="zt-option-label mb-1">压缩包处理</div>
          <div class="zt-switch-row">
            <div class="flex-grow-1">
              <div class="zt-switch-title">解压整理后自动清理压缩包</div>
              <div class="zt-switch-desc">作用于字体监控目录（只解字体）和两个 ASS 字幕目录（只解 .ass）：处理成功后清理原包；字体包、字幕包都按各自目录下的「已处理压缩包/」或直接删除处理，其余情况一律保留</div>
            </div>
            <v-switch v-model="config.archive_cleanup_enabled" color="primary" density="compact" hide-details></v-switch>
          </div>
          <v-radio-group
            v-model="config.archive_cleanup_action"
            density="compact"
            :disabled="!config.archive_cleanup_enabled"
            :class="['mt-1 zt-cleanup-radios', { 'is-off': !config.archive_cleanup_enabled }]"
          >
            <v-radio
              v-for="act in archiveCleanupActions"
              :key="act.value"
              :value="act.value"
            >
              <template #label>
                <div>
                  <div class="zt-radio-title">{{ act.title }}</div>
                  <div class="zt-radio-desc">{{ act.description }}</div>
                </div>
              </template>
            </v-radio>
          </v-radio-group>
          <div class="zt-hint">
            开 = 字体包在字体监控目录、字幕包在对应 ASS 目录，且自动执行开启、处理无失败时清理：移到该目录下「已处理压缩包/」或直接删除；
            放错目录、进待确认/待检查/待处理、有失败时一律保留并提醒；该子目录会被插件忽略，请勿在其中放其他文件。
          </div>

          <div class="zt-option-label mb-1 mt-4">字幕压缩包：处理哪些字幕</div>
          <v-select
            v-model="config.subtitle_archive_filter"
            :items="subtitleArchiveFilters"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
          ></v-select>
          <v-text-field
            v-if="config.subtitle_archive_filter === 'custom'"
            v-model="config.subtitle_archive_keywords"
            label="自定义关键词（逗号/空格分隔）"
            placeholder="例如：sc,chs,简,zh-hans"
            density="compact"
            variant="outlined"
            class="mt-2"
            hint="按字幕文件名匹配（英文按单词边界，中文按子串）；留空则不解压处理"
            persistent-hint
          ></v-text-field>
          <div class="zt-hint">
            只作用于「ASS 字幕检查目录」「ASS 自动子集化目录」里的字幕压缩包：一般一个包含 SC（简体）/ TC（繁体）两个字幕，
            可按预设只处理简体/繁体，或选「自定义关键词」自己填（如 chs、简、zh-hans）；字体监控目录不受影响。
            没有符合筛选的字幕时压缩包会保留并提示。
          </div>
        </div>

        <!-- 解压工具（从种子卡移入：上传压缩包与种子收集都依赖它） -->
        <div class="zt-subblock mt-4">
          <div class="zt-option-label mb-1">解压工具</div>
          <div class="zt-hint">解压能力：{{ torrentToolStatusText }}<span v-if="torrentStatus.tools?.hint"> · {{ torrentStatus.tools.hint }}</span></div>
          <div class="d-flex flex-wrap ga-2 mt-2">
            <v-btn
              size="small" color="warning" variant="tonal"
              :loading="archiveToolInstalling"
              :disabled="torrentStatus.tools?.can_install === false"
              title="在容器内用 apt/apk 安装/修复 unar（可解 .7z/.rar）；容器重建后需要重新安装"
              @click="installArchiveTools"
            >
              <v-icon start size="16">mdi-archive-arrow-up-outline</v-icon>
              安装/修复解压工具
            </v-btn>
          </div>
          <div class="zt-hint">安装/修复仅在容器内生效，容器重建或更新镜像后需要重新点一次。</div>
        </div>
      </v-card-text>
    </v-card>

    <!-- 3. 归档设置 -->
    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-tune-variant</v-icon>
        归档设置
      </v-card-title>
      <v-card-text>
        <div class="zt-hint mb-2">字体元数据统一由 fontTools 读取字体内部（名称 / 别名 / 字符覆盖），不再提供「文件名解析」模式。</div>

        <div class="zt-option-label mb-1 mt-3">归档方式</div>
        <v-radio-group v-model="config.archive_mode" density="compact">
          <v-radio
            v-for="mode in archiveModes"
            :key="mode.value"
            :label="mode.title"
            :value="mode.value"
          >
            <template #label>
              <div>
                <div class="zt-radio-title">{{ mode.title }}</div>
                <div class="zt-radio-desc">{{ mode.description }}</div>
              </div>
            </template>
          </v-radio>
        </v-radio-group>
        <div class="zt-switch-row mt-2">
          <div class="flex-grow-1">
            <div class="zt-switch-title">移动归档时删除重复源文件</div>
            <div class="zt-switch-desc">仅作用于「移动原文件」模式：字体库已有同名字体、判重跳过时，自动删除监控目录里残留的重复源文件；复制模式不受影响（源文件本就保留）<span v-if="config.archive_mode !== 'move'" class="zt-inline-flag"> · 仅移动模式生效</span></div>
          </div>
          <v-switch
            v-model="config.move_delete_duplicate"
            color="primary"
            density="compact"
            hide-details
            :disabled="config.archive_mode !== 'move'"
          ></v-switch>
        </div>
        <div class="zt-switch-row mt-2">
          <div class="flex-grow-1">
            <div class="zt-switch-title">利用字体内部名称命名</div>
            <div class="zt-switch-desc">开：归档时用字体内部的 PostScript 名命名（如 SourceHanSansCN-Bold）；关：保持原名（文件名）不变</div>
          </div>
          <v-switch v-model="config.font_name_internal" color="primary" density="compact" hide-details></v-switch>
        </div>
      </v-card-text>
    </v-card>

    <!-- 4. 已处理压缩包管理 -->
    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-archive-eye-outline</v-icon>
        已处理压缩包
      </v-card-title>
      <v-card-text>
        <div class="zt-hint mb-2">
          这里管理自动清理时移动到各监控目录「已处理压缩包/」里的压缩包；可恢复到原目录（会重新被监控处理）或删除。
          原监控目录里的压缩包不在这里，插件不会误删。
        </div>
        <div class="d-flex flex-wrap align-center ga-2">
          <v-btn size="small" variant="tonal" :loading="processedLoading" @click="loadProcessedArchives">
            <v-icon start size="16">mdi-refresh</v-icon>刷新
          </v-btn>
          <v-btn size="small" color="error" variant="text" :disabled="!processedArchives.length" :loading="processedBusy === 'clear'" @click="clearProcessedArchives">
            <v-icon start size="16">mdi-delete-sweep</v-icon>清空全部
          </v-btn>
          <span class="zt-hint ml-auto">共 {{ processedArchives.length }} 个 · {{ formatProcessedSize(totalProcessedSize) }}</span>
        </div>
        <div v-if="processedLoading && !processedArchives.length" class="zt-hint mt-3">读取中…</div>
        <div v-else-if="!processedArchives.length" class="zt-hint mt-3">暂无已处理压缩包</div>
        <div v-else class="mt-2 zt-archive-list">
          <div v-for="item in processedArchives" :key="item.path" class="zt-archive-row">
            <div class="flex-grow-1">
              <div class="zt-archive-name">{{ item.name }}</div>
              <div class="zt-hint">{{ item.source }} · {{ formatProcessedSize(item.size) }} · {{ formatProcessedTime(item.mtime) }}</div>
            </div>
            <v-btn size="x-small" variant="tonal" :loading="processedBusy === item.path" @click="restoreProcessedArchive(item)">恢复</v-btn>
            <v-btn size="x-small" variant="text" color="error" :loading="processedBusy === item.path" @click="removeProcessedArchive(item)">删除</v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <!-- 5. 自动化与通知 -->
    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-cog-refresh-outline</v-icon>
        自动化与通知
      </v-card-title>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">是否自动执行监控结果</div>
            <div class="zt-switch-desc">开：监控到新东西直接执行——字体直接归档（压缩包解压后也直接归档）、字幕直接检查、子集化直接运行；关：待定——字体进待确认（压缩包保留原地）、检查进待检查、子集化进待处理，等手动处理</div>
          </div>
          <v-switch v-model="config.auto_collect" color="primary" density="compact" hide-details></v-switch>
        </div>

        <div class="zt-option-label mb-1 mt-3">MP 入库时</div>
        <v-select
          v-model="inboundMode"
          :items="inboundModes"
          item-title="title"
          item-value="value"
          density="compact"
          variant="outlined"
          hint="MP 转存完成（整理入库）时对该剧字幕做什么；检查与子集化互斥，只能选一个，默认不处理"
          persistent-hint
        ></v-select>

        <div class="zt-switch-row mt-3">
          <div class="flex-grow-1">
            <div class="zt-switch-title">发送通知</div>
            <div class="zt-switch-desc">归档/检查完成时通过系统通知发送结果</div>
          </div>
          <v-switch v-model="config.notify_enabled" color="primary" density="compact" hide-details></v-switch>
        </div>
      </v-card-text>
    </v-card>

    <!-- 5. 子集化与输出 -->
    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-subtitles-outline</v-icon>
        子集化与输出
      </v-card-title>
      <v-card-text>
        <div class="zt-option-label mb-1">监控目录输出方式</div>
        <v-radio-group v-model="config.subset_out_mode" density="compact">
          <v-radio
            v-for="mode in subsetOutModes"
            :key="mode.value"
            :label="mode.title"
            :value="mode.value"
          >
            <template #label>
              <div>
                <div class="zt-radio-title">{{ mode.title }}</div>
                <div class="zt-radio-desc">{{ mode.description }}</div>
              </div>
            </template>
          </v-radio>
        </v-radio-group>
        <div class="zt-hint">目录监控（ASS 自动子集化目录）的字幕成品按「输出目录/剧名/」子文件夹分类输出（如「你的名字.ass」→「你的名字」文件夹），多剧字幕互不混淆；手动上传的字幕子集结果留在插件临时文件夹，不受此设置影响。未配输出目录时不涉及复制/移动：复制=另生成 xx.ziti.ass 并保留源字幕，移动=成品就地替换源字幕</div>
        <div class="zt-hint">字体已内嵌进 .ziti.ass 成品，不再产生 *_subsetted 字体备份夹；旧版本遗留的备份夹会在对应源字幕删除时自动清理</div>

        <div class="zt-switch-row mt-3">
          <div class="flex-grow-1">
            <div class="zt-switch-title">MP 入库替换原字幕</div>
            <div class="zt-switch-desc">开：入库子集化的成品直接替换媒体库原字幕（文件名不变，媒体库只保留一份）；关：保留原字幕，另生成 xx.ziti.ass 成品（默认）。只作用于 MP 入库，目录监控见上方「监控目录输出方式」，手动上传永不覆盖</div>
          </div>
          <v-switch v-model="config.inbound_subset_overwrite" color="primary" density="compact" hide-details></v-switch>
        </div>

        <v-select
          v-model="hdrSelection"
          :items="hdrLevels"
          item-title="title"
          item-value="value"
          label="HDR 字幕亮度"
          density="compact"
          variant="outlined"
          class="mt-3"
          hint="选择档位即自动开启（档位 = 纯白亮度百分比，80% 为 HDR 主流推荐）；选择「关闭」不调整亮度"
          persistent-hint
        ></v-select>
        <div class="zt-hint">应用范围：全量子集化、目录监控自动子集化、入库子集化处理后生成的成品字幕（原始字幕不受影响）</div>
      </v-card-text>
    </v-card>

    <!-- 6. 高级 / 维护（默认折叠） -->
    <v-expansion-panels class="mt-4" flat>
      <v-expansion-panel class="zt-card-bg zt-expand-panel">
        <v-expansion-panel-title class="zt-card-title">
          <v-icon start size="18">mdi-wrench-cog-outline</v-icon>
          高级 / 维护
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="zt-switch-row">
            <div class="flex-grow-1">
              <div class="zt-switch-title">启动轻检</div>
              <div class="zt-switch-desc">插件启动时只按文件大小/修改时间校验索引：磁盘已删除的撤销索引、变更的只重解析该文件、磁盘有而索引没有的新字体一并补索引；索引为空（新装/换库/升级）则自动从磁盘重建字体库。不做全量解析，不拖慢启动</div>
            </div>
            <v-switch v-model="config.startup_light_check" color="primary" density="compact" hide-details></v-switch>
          </div>
          <div class="zt-switch-row">
            <div class="flex-grow-1">
              <div class="zt-switch-title">每周差异核对</div>
              <div class="zt-switch-desc">每周日凌晨 4:30 与磁盘指纹比对一次索引，只重解析差异文件并清理失效记录，另抽检 50 个「未变」文件重算哈希（发现同大小同时间戳的内容替换）；按既定策略默认开启（保存后需重载插件生效）</div>
            </div>
            <v-switch v-model="config.weekly_reconcile" color="primary" density="compact" hide-details></v-switch>
          </div>
          <v-text-field
            v-model="config.max_font_mb"
            label="字体文件大小上限"
            type="number"
            min="8"
            max="4096"
            suffix="MB"
            density="compact"
            variant="outlined"
            class="mt-3"
            hint="超过该值的字体不做哈希/解析、不接受上传（默认 128MB）。超大 TTC 逐 face 读取很吃内存，确有需要再调大；调大后需「全部重建」索引才会纳入"
            persistent-hint
          ></v-text-field>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <!-- 7. 种子字体收集（默认折叠） -->
    <v-card class="zt-card-bg mt-4">
      <div class="zt-collapse-head" @click="torrentExpanded = !torrentExpanded">
        <v-card-title class="zt-card-title">
          <v-icon start size="18">mdi-download-box-outline</v-icon>
          种子字体收集
        </v-card-title>
        <v-btn
          icon
          size="small"
          variant="text"
          :title="torrentExpanded ? '收起' : '展开'"
          @click.stop="torrentExpanded = !torrentExpanded"
        >
          <v-icon>{{ torrentExpanded ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
        </v-btn>
      </div>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">启用种子字体收集</div>
            <div class="zt-switch-desc">只读下载器：从下载完成的种子里按文件清单截取字体（不扫描下载目录、不改下载优先级、不删任何源文件）。开启后按设定间隔轮询下载器，不接 MP 整理事件，要停就关这个总开关</div>
          </div>
          <v-switch v-model="config.torrent_enabled" color="primary" density="compact" hide-details></v-switch>
        </div>

        <!-- 折叠时的状态摘要 -->
        <div v-if="!torrentExpanded" class="zt-hint">
          下载器：{{ torrentDownloaderStatusText }} · 解压能力：{{ torrentToolStatusText }} · 基线：{{ torrentBaselineStatusText }} · 最近记录 {{ torrentRecords.length }} 条<span v-if="torrentStatus.running"> · 正在收集 {{ torrentStatus.running }} 个</span>
        </div>

        <template v-else>
          <v-row dense class="mt-2">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="config.torrent_scan_interval_min"
                type="number" min="1" max="1440"
                label="兜底扫描间隔（分钟）"
                density="compact" variant="outlined"
                hint="定时任务每分钟唤醒、到点才扫下载器；改完保存即时生效，太小会增加下载器查询频率"
                persistent-hint
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="config.torrent_keywords"
                label="关键词（逗号分隔）"
                density="compact" variant="outlined"
                hint="只对压缩包生效；裸字体文件命中后缀即收，不看关键词"
                persistent-hint
              ></v-text-field>
            </v-col>
          </v-row>
          <v-row dense class="mt-2">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="config.torrent_max_file_mb"
                type="number" min="1" max="40960"
                label="单文件上限（MB）"
                density="compact" variant="outlined"
                hide-details
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="config.torrent_max_files"
                type="number" min="1" max="5000"
                label="单种子最多文件"
                density="compact" variant="outlined"
                hide-details
              ></v-text-field>
            </v-col>
          </v-row>
          <div class="zt-switch-row mt-2">
            <div class="flex-grow-1">
              <div class="zt-switch-title">收集后进「待整理」</div>
              <div class="zt-switch-desc">开：截取到的字体先进待整理等你确认；关：直接归档进字体库（默认，走哈希去重与厂商归档）</div>
            </div>
            <v-switch v-model="config.torrent_to_pending" color="primary" density="compact" hide-details></v-switch>
          </div>
          <div class="zt-hint">
            下载器：{{ torrentDownloaderStatusText }}<br>
            解压能力：{{ torrentToolStatusText }}<span v-if="torrentStatus.tools?.hint"> · {{ torrentStatus.tools.hint }}</span><br>
            基线：{{ torrentBaselineStatusText }}（只处理基线之后完成的种子，历史不碰）<span v-if="torrentStatus.running"> · 正在收集 {{ torrentStatus.running }} 个</span>
          </div>
          <div class="d-flex flex-wrap ga-2 mt-2">
            <v-btn
              size="small" color="primary" variant="tonal"
              :loading="torrentBusy" :disabled="!config.torrent_enabled"
              @click="scanTorrents"
            >
              <v-icon start size="16">mdi-magnify-scan</v-icon>
              立即检查下载器
            </v-btn>
            <v-btn size="small" variant="tonal" @click="resetTorrentBaseline">
              <v-icon start size="16">mdi-clock-outline</v-icon>
              重置基线为现在
            </v-btn>
            <v-btn
              size="small" variant="text" color="error"
              :loading="torrentClearing" :disabled="!torrentRecords.length"
              @click="clearTorrentRecords"
            >
              <v-icon start size="16">mdi-delete-sweep</v-icon>
              清空记录
            </v-btn>
          </div>
          <div v-if="torrentRecords.length" class="mt-2">
            <div class="zt-option-label mb-1">最近处理记录</div>
            <div
              v-for="r in torrentRecords"
              :key="r.id"
              class="zt-hint zt-record-line"
            >
              {{ r.created_at }} · {{ recordStatusText(r.status) }} · {{ r.torrent_name || (r.hash || '').slice(0, 8) }} ·
              新增 {{ r.added }} / 跳过 {{ r.skipped }}<span v-if="r.failed"> / 失败 {{ r.failed }}</span>
              <span v-if="r.detail"> — {{ r.detail }}</span>
            </div>
          </div>
          <div v-else class="zt-hint mt-2">暂无处理记录</div>
        </template>
      </v-card-text>
    </v-card>

    </div>

    <div class="d-flex justify-end mt-4">
      <v-btn
        color="primary"
        variant="tonal"
        :loading="saving"
        @click="save"
      >
        <v-icon start size="18">mdi-content-save-outline</v-icon>
        保存配置
      </v-btn>
    </div>

    <v-dialog v-model="busyDialog" max-width="480px">
      <v-card class="zt-card-bg">
        <v-card-title>
          <v-icon start size="20" color="warning">mdi-progress-clock</v-icon>
          后台有任务运行
        </v-card-title>
        <v-card-text class="pt-2">
          当前有全量检查 / 扫描 / 子集化任务正在后台运行，暂时无法关闭插件。<br><br>
          请等待任务完成后再关闭插件，直接关闭可能导致文件入库但记录缺失。
        </v-card-text>
        <v-card-actions>
          <v-btn color="primary" variant="tonal" @click="busyDialog = false">我知道了</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.zt-card-title {
  font-size: 15px;
  font-weight: 600;
}
/* 插件停用时：其他配置黑化且不可点击 */
.zt-disabled-zone.is-off {
  pointer-events: none;
  opacity: 0.45;
  filter: grayscale(0.9);
}
.zt-option-label {
  font-size: 13px;
  color: inherit;
  opacity: 0.8;
}
.zt-radio-title {
  font-size: 13px;
}
.zt-radio-desc {
  font-size: 12px;
  opacity: 0.65;
}
/* 开关行统一：长描述换行时开关与标题首行对齐（不再垂直居中浮动） */
.zt-switch-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 10px 0;
}
/* 左侧文字容器吃满剩余宽度，长英文/路径可折行不撑破布局 */
.zt-switch-row > .flex-grow-1 {
  min-width: 0;
}
/* 右侧开关固定不收缩；上移 4px 对齐标题首行（compact 开关自身有顶部留白） */
.zt-switch-row > .v-switch {
  flex: 0 0 auto;
  margin-top: -4px;
}
.zt-switch-title {
  font-size: 14px;
  font-weight: 500;
}
.zt-switch-desc {
  font-size: 12px;
  opacity: 0.7;
}
/* 子块（压缩包处理 / 解压工具）与上方字段的分隔 */
.zt-subblock {
  border-top: 1px solid rgba(128, 128, 128, 0.18);
  padding-top: 12px;
}
/* 压缩包清理方式：总开关关闭时整体置灰（单选本身也被 disabled） */
.zt-cleanup-radios.is-off {
  opacity: 0.45;
}
/* 条件提示（如「仅移动模式生效」） */
.zt-inline-flag {
  font-weight: 500;
  opacity: 0.95;
}
/* 种子卡折叠标题行：整行可点，右侧箭头按钮 */
.zt-collapse-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-right: 8px;
  cursor: pointer;
  user-select: none;
}
.zt-collapse-head > .zt-card-title {
  flex: 1 1 auto;
  min-width: 0;
}
/* 高级/维护折叠面板：保持卡片观感 */
.zt-expand-panel {
  border-radius: 10px !important;
  overflow: hidden;
}
.zt-hint {
  font-size: 12px;
  opacity: 0.6;
  margin-top: 8px;
  line-height: 1.6;
}
.zt-record-line {
  line-height: 1.5;
}
/* 手机端：开关行间距收紧，保证长描述换行时仍与标题首行对齐 */
.zt-archive-list {
  max-height: 280px;
  overflow-y: auto;
}
.zt-archive-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.12);
}
.zt-archive-row:last-child {
  border-bottom: none;
}
.zt-archive-row > .flex-grow-1 {
  min-width: 0;
}
.zt-archive-name {
  font-size: 13px;
  font-weight: 500;
  word-break: break-all;
}
@media (max-width: 600px) {
  .zt-switch-row {
    gap: 8px;
  }
}
</style>
