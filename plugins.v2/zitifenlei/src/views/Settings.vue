<script setup>
import { onMounted, ref, watch } from 'vue'
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
  scan_mode: 'internal',
  archive_mode: 'copy',
  // 是否利用字体内部名称命名（开：用字体内部 PostScript 名；关：保持原文件名）
  font_name_internal: false,
  // 是否启用监控（总开关）：统一控制字体监控目录 / ASS字幕目录监控 / ASS目录监控子集
  monitor_enabled: false,
  auto_inbound: true,
  auto_collect: true,
  notify_enabled: false,
  auto_subset: false,
  subset_overwrite: false,
  subset_out_dir: '',
  subset_out_mode: 'copy',
  subset_sync_subdir: false,
  hdr_brightness: false,
  hdr_brightness_level: '',
}

// 数据源：宿主 initial-config（默认值+已存配置）；进入页面后立即用后端权威配置回填，
// 避免详情页（Page 场景）拿不到 initialConfig 时表单显示默认空值、一保存就覆盖真实配置。
const config = ref({ ...DEFAULT_CONFIG, ...(props.initialConfig || {}) })
const saving = ref(false)

const scanModes = [
  { title: '内部扫描(推荐)', value: 'internal', description: '扫描字体文件内部元数据（需 fontTools）' },
  { title: '文件名解析', value: 'filename', description: '直接从文件名提取信息，速度更快' },
]
const archiveModes = [
  { title: '复制保留原文件', value: 'copy', description: '归档时复制字体到字体库目录' },
  { title: '移动原文件', value: 'move', description: '归档时移动字体到字体库目录' },
]
const subsetOutModes = [
  { title: '复制到输出目录', value: 'copy', description: '把新的字幕（成品）复制到输出目录，旧的源字幕还在原处' },
  { title: '移动到输出目录', value: 'move', description: '把字幕（成品）移动到输出目录，原处不再保留' },
]
// 同步子集字体夹（*_subsetted）：字体已内嵌进成品字幕，夹子仅是 assfonts 的备份，默认不保留
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
  } catch (e) {
    emit('notify', e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)

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
        ></v-text-field>
        <v-text-field
          v-model="config.lib_dir"
          label="字体库目录"
          placeholder="/media/fonts/library"
          density="compact"
          variant="outlined"
          class="mb-3"
        ></v-text-field>
        <v-text-field
          v-model="config.ass_dir"
          label="ASS字幕目录监控"
          placeholder="/media/subtitles"
          density="compact"
          variant="outlined"
          class="mb-3"
        ></v-text-field>
        <v-text-field
          v-model="config.subset_dir"
          label="ASS目录监控子集"
          placeholder="/media/subtitles/subset"
          density="compact"
          variant="outlined"
          class="mb-3"
        ></v-text-field>
        <v-text-field
          v-model="config.subset_out_dir"
          label="子集化输出目录"
          placeholder="/media/subtitles/subset-out"
          density="compact"
          variant="outlined"
          hint="目录监控（ASS目录监控子集）子集化成品（字幕与子集字体夹）的落点，按剧名分到子文件夹；手动上传字幕的子集结果留在插件临时文件夹，不受此设置影响"
          persistent-hint
        ></v-text-field>
      </v-card-text>
    </v-card>

    <v-card class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-tune-variant</v-icon>
        扫描与归档模式
      </v-card-title>
      <v-card-text>
        <div class="zt-option-label mb-1">扫描模式</div>
        <v-radio-group v-model="config.scan_mode" density="compact">
          <v-radio
            v-for="mode in scanModes"
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
            <div class="zt-switch-title">利用字体内部名称命名</div>
            <div class="zt-switch-desc">开：归档时用字体内部的 PostScript 名命名（如 SourceHanSansCN-Bold）；关：保持原名（文件名）不变</div>
          </div>
          <v-switch v-model="config.font_name_internal" color="primary" hide-details></v-switch>
        </div>
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
            <div class="zt-switch-desc">总开关：统一控制「字体监控目录」「ASS字幕目录监控」「ASS目录监控子集」三个目录的监控启停；关闭则三个目录都不监控</div>
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
        <v-icon start size="18">mdi-subtitles-outline</v-icon>
        子集化设置
      </v-card-title>
      <v-card-text>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">入库后自动子集化</div>
            <div class="zt-switch-desc">MP 转存完成时，对新增字幕调用 assfonts 子集化并内嵌字体（结果可在「子集化」页查看；与「入库自动检查字幕」互斥，同时只能开一个）</div>
          </div>
          <v-switch v-model="config.auto_subset" color="primary" hide-details></v-switch>
        </div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">输出覆盖原文件</div>
            <div class="zt-switch-desc">开：子集化结果直接替换原字幕文件（文件名不变，媒体库只保留一份）；关：保留原字幕，另生成 xx.assfonts.ass 成品文件</div>
          </div>
          <v-switch v-model="config.subset_overwrite" color="primary" hide-details></v-switch>
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
        <div class="zt-hint">目录监控（ASS目录监控子集）的字幕成品按「输出目录/剧名/」子文件夹分类输出（如「你的名字.ass」→「你的名字」文件夹），多剧字幕互不混淆；手动上传的字幕子集结果留在插件临时文件夹，不受此设置影响</div>
        <div class="zt-switch-row">
          <div class="flex-grow-1">
            <div class="zt-switch-title">是否在输出端保留子集化字体文件夹</div>
            <div class="zt-switch-desc">管 MP 入库与监控目录子集化：开＝在输出端产生 *_subsetted 字体文件夹；关＝不产生，源字幕目录里的也自动清理。手动上传的字幕子集不受此开关支配（始终不产生）</div>
          </div>
          <v-switch v-model="config.subset_sync_subdir" color="primary" hide-details></v-switch>
        </div>

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
        <div class="zt-hint">assfonts 可执行文件随插件分发（bin/assfonts），字体来源为「字体库目录」；新字体入库后在「子集化」页点击「重建索引」即可生效</div>
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