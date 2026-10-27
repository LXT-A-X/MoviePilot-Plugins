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
  // 缺失字体专用接收目录（空=关闭）：严格校验后才入库
  missing_font_dir: '',
  archive_mode: 'copy',
  // 移动归档时删除判重跳过的残留源文件（只作用于「移动原文件」模式）
  move_delete_duplicate: true,
  // 是否利用字体内部名称命名（开：用字体内部 PostScript 名；关：保持原文件名）
  font_name_internal: false,
  // 单字体文件大小上限（MB）：超过该值不做哈希/解析、不接受上传
  max_font_mb: 128,
  // 是否启用监控（总开关）：统一控制字体监控目录 / ASS字幕目录监控 / ASS目录监控子集
  monitor_enabled: false,
  auto_inbound: true,
  auto_collect: true,
  notify_enabled: false,
  // 索引维护：启动轻检（stat 级校验，索引为空时从磁盘重建）+ 每周差异核对（定时增量比对）
  startup_light_check: true,
  weekly_reconcile: true,
  auto_subset: false,
  // 子集化在独立工作进程执行（uharfbuzz 段错误/病态字体只影响当前字幕，不拖垮主进程）
  subset_process_isolation: true,
  // MP 入库成品是否直接替换媒体库原字幕（与「监控目录输出方式」独立）
  inbound_subset_overwrite: false,
  subset_out_dir: '',
  subset_out_mode: 'copy',
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
const subsetOutModes = [
  { title: '复制到输出目录', value: 'copy', description: '成品复制到输出目录，监控目录的源字幕保留（默认）' },
  { title: '移动到输出目录', value: 'move', description: '成品移动到输出目录，输出成功后删除监控目录的源字幕' },
]
// 同步子集字体夹（*_subsetted）：字体已内嵌进成品字幕，夹子仅是备份，默认不保留
// HDR 字幕亮度档位（关/档位选择，对应 ASS 色码压暗比例）
const hdrLevels = [
  { title: '关（不调整亮度）', value: '' },
  { title: '100% 纯白（&H00FFFFFF）· 仅 SDR 片源', value: '100' },
  { title: '85%（&H00D9D9D9）· 折中保守档', value: '85' },
  { title: '80%（&H00CCCCCC）· HDR 主流推荐 ⭐', value: '80' },
  { title: '75%（&H00BFBFBF）· 暗场多的片子', value: '75' },
  { title: '70%（&H00B2B2B2）· OLED/MiniLED 暗室', value: '70' },
  { title: '63%（&H00A1A1A1）· 模拟 SDR 白观感', value: '63' },
  { title: '50% 中灰（&H00808080）· 极端场景', value: '50' },
]

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
})

// ── 种子字体收集：状态 / 立即检查 / 基线 / 记录 ──────────────────────
const torrentStatus = ref({ downloaders: [], tools: {}, baseline_text: '', running: 0 })
const torrentRecords = ref([])
const torrentBusy = ref(false)
const torrentClearing = ref(false)

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

async function loadTorrentStatus() {
  if (typeof props.api?.get !== 'function') return
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
</script>

<template>
  <div class="zt-settings" style="max-width: 720px">
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
    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-folder-cog-outline</v-icon>
        目录配置
      </v-card-title>
      <v-card-text>
        <v-text-field
          v-model="config.input_dir"
          label="字体监控目录"
          placeholder="/media/fonts/incoming"
          density="compact"
          variant="outlined"
          class="mb-3"
          hint="新字体放这里自动归档进字体库"
          persistent-hint
        ></v-text-field>
        <v-text-field
          v-model="config.lib_dir"
          label="字体库目录"
          placeholder="/media/fonts/library"
          density="compact"
          variant="outlined"
          class="mb-3 mt-5"
          hint="字体唯一来源：检查与子集化都按这里的字体逐字符比对"
          persistent-hint
        ></v-text-field>
        <v-text-field
          v-model="config.ass_dir"
          label="ASS 字幕检查目录"
          placeholder="/media/subtitles"
          density="compact"
          variant="outlined"
          class="mb-3 mt-5"
          hint="放入字幕自动检查缺字体（不产出子集化成品的目录）"
          persistent-hint
        ></v-text-field>
        <v-text-field
          v-model="config.subset_dir"
          label="ASS 自动子集化目录"
          placeholder="/media/subtitles/subset"
          density="compact"
          variant="outlined"
          class="mb-3 mt-5"
          hint="放入字幕自动子集化并内嵌字体，成品按「输出目录/剧名/」输出"
          persistent-hint
        ></v-text-field>
        <v-text-field
          v-model="config.subset_out_dir"
          label="子集化输出目录"
          placeholder="/media/subtitles/subset-out"
          density="compact"
          variant="outlined"
          hint="「ASS 自动子集化目录」的成品落点，按剧名分到子文件夹；手动上传字幕的结果留在插件临时目录，不受此设置影响"
          persistent-hint
        ></v-text-field>
        <v-text-field
          v-model="config.missing_font_dir"
          label="缺失字体接收目录（严格校验）"
          placeholder="/media/fonts/missing"
          density="compact"
          variant="outlined"
          class="mt-5"
          hint="专门接收「缺失字体页」要补的字体：放入后先等写入完成，再逐 face 校验是否命中缺失目标并真实覆盖缺失字符；通过的直接入库，未通过的移入该目录下 rejected/ 留档（不删文件）。留空=关闭该通道，请勿与其他监控目录相同"
          persistent-hint
        ></v-text-field>
      </v-card-text>
    </v-card>

    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-tune-variant</v-icon>
        归档设置
      </v-card-title>
      <v-card-text>
        <div class="zt-hint mb-3">字体元数据统一由 fontTools 读取字体内部（名称 / 别名 / 字符覆盖），不再提供「文件名解析」模式。</div>

        <div class="zt-option-label mb-1 mt-2">归档模式</div>
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
            <div class="zt-switch-desc">仅作用于「移动原文件」模式：字体库已有同名字体、判重跳过时，自动删除监控目录里残留的重复源文件；复制模式不受影响（源文件本就保留）</div>
          </div>
          <v-switch v-model="config.move_delete_duplicate" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row mt-2">
          <div class="flex-grow-1">
            <div class="zt-switch-title">利用字体内部名称命名</div>
            <div class="zt-switch-desc">开：归档时用字体内部的 PostScript 名命名（如 SourceHanSansCN-Bold）；关：保持原名（文件名）不变</div>
          </div>
          <v-switch v-model="config.font_name_internal" color="primary" hide-details></v-switch>
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
          class="mt-5"
          hint="超过该值的字体不做哈希/解析、不接受上传（默认 128MB）。超大 TTC 逐 face 读取很吃内存，确有需要再调大；调大后需「全部重建」索引才会纳入"
          persistent-hint
        ></v-text-field>
      </v-card-text>
    </v-card>

    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-cog-refresh-outline</v-icon>
        自动化设置
      </v-card-title>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">是否启用监控</div>
            <div class="zt-switch-desc">总开关：统一控制「字体监控目录」「ASS 字幕检查目录」「ASS 自动子集化目录」三个目录的监控启停；关闭则三个目录都不监控</div>
          </div>
          <v-switch v-model="config.monitor_enabled" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">是否自动执行监控结果</div>
            <div class="zt-switch-desc">开：监控到新东西直接执行——字体直接归档、字幕直接检查、子集化直接运行；关：待定——字体进待确认、检查进待检查、子集化进待处理，等手动处理</div>
          </div>
          <v-switch v-model="config.auto_collect" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">启动轻检</div>
            <div class="zt-switch-desc">插件启动时只按文件大小/修改时间校验索引：磁盘已删除的撤销索引、变更的只重解析该文件、磁盘有而索引没有的新字体一并补索引；索引为空（新装/换库/升级）则自动从磁盘重建字体库。不做全量解析，不拖慢启动</div>
          </div>
          <v-switch v-model="config.startup_light_check" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">每周差异核对</div>
            <div class="zt-switch-desc">每周日凌晨 4:30 与磁盘指纹比对一次索引，只重解析差异文件并清理失效记录，另抽检 50 个「未变」文件重算哈希（发现同大小同时间戳的内容替换）；按既定策略默认开启（保存后需重载插件生效）</div>
          </div>
          <v-switch v-model="config.weekly_reconcile" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">入库自动检查字幕</div>
            <div class="zt-switch-desc">MP 转存完成（整理入库）时自动扫描该剧 ASS 字幕并检查字体，汇总通知（与「入库后自动子集化」互斥，同时只能开一个）</div>
          </div>
          <v-switch v-model="config.auto_inbound" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">发送通知</div>
            <div class="zt-switch-desc">归档/检查完成时通过系统通知发送结果</div>
          </div>
          <v-switch v-model="config.notify_enabled" color="primary" hide-details></v-switch>
        </div>
      </v-card-text>
    </v-card>

    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-download-box-outline</v-icon>
        种子字体收集
      </v-card-title>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">启用种子字体收集</div>
            <div class="zt-switch-desc">只读下载器：从下载完成的种子里按文件清单截取字体（不扫描下载目录、不改下载优先级、不删任何源文件）。开启后按设定间隔轮询下载器，不接 MP 整理事件，要停就关这个总开关</div>
          </div>
          <v-switch v-model="config.torrent_enabled" color="primary" hide-details></v-switch>
        </div>
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
          <v-switch v-model="config.torrent_to_pending" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-hint">
          下载器：{{ torrentDownloaderText }}<br>
          解压能力：{{ torrentToolText }}（7z/rar 需容器内安装 p7zip/unar，未装时只解 zip）<br>
          基线：{{ torrentStatus.baseline_text || '未设置' }}（只处理基线之后完成的种子，历史不碰）<span v-if="torrentStatus.running"> · 正在收集 {{ torrentStatus.running }} 个</span>
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
            class="zt-hint" style="line-height: 1.5"
          >
            {{ r.created_at }} · {{ recordStatusText(r.status) }} · {{ r.torrent_name || (r.hash || '').slice(0, 8) }} ·
            新增 {{ r.added }} / 跳过 {{ r.skipped }}<span v-if="r.failed"> / 失败 {{ r.failed }}</span>
            <span v-if="r.detail"> — {{ r.detail }}</span>
          </div>
        </div>
        <div v-else class="zt-hint mt-2">暂无处理记录</div>
      </v-card-text>
    </v-card>

    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-subtitles-outline</v-icon>
        子集化设置
      </v-card-title>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">入库后自动子集化</div>
            <div class="zt-switch-desc">MP 转存完成时，对新增字幕执行子集化并内嵌字体（结果可在「子集化」页查看；与「入库自动检查字幕」互斥，同时只能开一个）</div>
          </div>
          <v-switch v-model="config.auto_subset" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">MP 入库替换原字幕</div>
            <div class="zt-switch-desc">开：入库子集化的成品直接替换媒体库原字幕（文件名不变，媒体库只保留一份）；关：保留原字幕，另生成 xx.ziti.ass 成品（默认）。只作用于 MP 入库，目录监控见下方「监控目录输出方式」，手动上传永不覆盖</div>
          </div>
          <v-switch v-model="config.inbound_subset_overwrite" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">子集化进程隔离</div>
            <div class="zt-switch-desc">开：字体子集化在独立工作进程执行，uharfbuzz 崩溃或病态字体只影响当前字幕，不会拖垮 MoviePilot 主进程；工作进程无法启动时自动回退进程内执行（默认开）</div>
          </div>
          <v-switch v-model="config.subset_process_isolation" color="primary" hide-details></v-switch>
        </div>

        <div class="zt-option-label mb-1 mt-2">监控目录输出方式</div>
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

        <div class="zt-option-label mb-1 mt-2">HDR 字幕亮度</div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">启用 HDR 亮度压暗</div>
            <div class="zt-switch-desc">子集化/上传处理的字幕成品按所选档位压暗主色/描边/阴影，避免 HDR 片源下纯白字幕刺眼</div>
          </div>
          <v-switch v-model="config.hdr_brightness" color="primary" hide-details
            @update:model-value="v => { if (!v) config.hdr_brightness_level = '' }"></v-switch>
        </div>
        <v-select
          v-model="config.hdr_brightness_level"
          :items="hdrLevels"
          item-title="title"
          item-value="value"
          label="亮度档位"
          density="compact"
          variant="outlined"
          class="mt-1"
          :disabled="!config.hdr_brightness"
          hint="档位即纯白亮度百分比（80% ⭐ HDR 主流推荐）；选择「关」或留空则不调整"
          persistent-hint
        ></v-select>
        <div class="zt-hint">应用范围：全量子集化、目录监控自动子集化、入库子集化处理后生成的成品字幕（原始字幕不受影响）</div>
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
.zt-switch-row {
  display: flex;
  align-items: center;
  padding: 8px 0;
}
.zt-switch-title {
  font-size: 14px;
  font-weight: 500;
}
.zt-switch-desc {
  font-size: 12px;
  opacity: 0.7;
}
.zt-hint {
  font-size: 12px;
  opacity: 0.6;
  margin-top: 8px;
  line-height: 1.6;
}
</style>