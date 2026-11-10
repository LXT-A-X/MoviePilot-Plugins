<script setup>
/**
 * 预览确认弹窗：展示 /plan 的执行引擎、变更摘要、输出/空间、warnings 与 blockers，
 * blockers 非空时禁止提交；命令详情可展开。
 */
import { computed } from 'vue'
import { useDisplay } from 'vuetify'
import { fmtBytes, baseName } from '../utils.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  path: { type: String, default: '' },
  result: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
  engineReady: { type: Boolean, default: true },
  title: { type: String, default: '确认执行' },
  confirmText: { type: String, default: '确认执行' },
  // duration_mismatch 警告强制勾选状态由父级持有（确认后随 plan 提交）
  confirmed: { type: Boolean, default: false },
  // 布局三档：narrow 全屏；medium/wide 窗口弹窗（不传则按视口回退）
  layout: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'update:confirmed', 'confirm'])
const display = useDisplay()
const effectiveLayout = computed(() => props.layout || (display.mdAndUp.value ? 'wide' : 'narrow'))
const mobile = computed(() => effectiveLayout.value === 'narrow')

const CHANGES_MAP = { keep: '保留', clear: '清空', import: '导入', none: '不写入' }
const ENGINE_MAP = { mkvmerge: 'mkvmerge（重封装）', ffmpeg: 'ffmpeg（降级执行）', none: '未检测到引擎' }

const changes = computed(() => props.result?.changes || {})
const warnings = computed(() => (Array.isArray(props.result?.warnings) ? props.result.warnings : []))
const blockers = computed(() => (Array.isArray(props.result?.blockers) ? props.result.blockers : []))

const addedTracks = computed(() => (Array.isArray(changes.value.add) ? changes.value.add : []))
const addedSubtitles = computed(() => addedTracks.value.filter((item) => item.kind === 'subtitle'))
const addedAudios = computed(() => addedTracks.value.filter((item) => item.kind === 'audio'))
const dropped = computed(() => (Array.isArray(changes.value.drop) ? changes.value.drop : []))
const edits = computed(() => (Array.isArray(changes.value.edit) ? changes.value.edit : []))
const attachmentsAdd = computed(() =>
  Array.isArray(changes.value.attachments_add) ? changes.value.attachments_add : [],
)
const attachmentsDrop = computed(() =>
  Array.isArray(changes.value.attachments_drop) ? changes.value.attachments_drop : [],
)
const commands = computed(() => (Array.isArray(props.result?.commands) ? props.result.commands : []))
// 时长不一致警告：必须显式勾选后才能确认（后端 code 固定为 duration_mismatch）
const durationWarnings = computed(() =>
  warnings.value.filter((item) => (item?.code || '') === 'duration_mismatch'),
)
const hasDurationMismatch = computed(() => durationWarnings.value.length > 0)
const canSubmit = computed(
  () =>
    props.engineReady &&
    !blockers.value.length &&
    !props.loading &&
    !props.submitting &&
    (!hasDurationMismatch.value || props.confirmed),
)

const engineText = computed(() => ENGINE_MAP[props.result?.engine] || props.result?.engine || '—')
const chaptersText = computed(() => {
  const raw = changes.value.chapters
  if (raw == null) return '—'
  if (typeof raw === 'object') {
    return CHANGES_MAP[raw.mode] || raw.mode || '—'
  }
  return CHANGES_MAP[raw] || String(raw)
})
const spaceText = computed(() => {
  const space = props.result?.space
  if (!space) return ''
  const need = fmtBytes(space.need)
  const free = fmtBytes(space.free)
  const enough = Number(space.free) >= Number(space.need)
  return `需要空间：约 ${need}（剩余 ${free} ${enough ? '✓' : '✗'}）`
})
const titleText = computed(() => changes.value.title || '—')
const fileLabel = computed(() => baseName(props.path || props.result?.output_path || ''))

function commandText(command) {
  if (typeof command === 'string') return command
  if (command.display) return command.display
  if (command.tool && Array.isArray(command.args)) return `${command.tool} ${command.args.join(' ')}`
  return JSON.stringify(command)
}

function close() {
  emit('update:modelValue', false)
}

function confirm() {
  if (!canSubmit.value) return
  emit('confirm')
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    :max-width="mobile ? undefined : 820"
    :fullscreen="mobile"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="preview-dialog" :class="{ 'dialog-compact': mobile, 'dialog-medium': effectiveLayout === 'medium' }">
      <div class="preview-head">
        <span class="preview-title">{{ title || '确认执行' }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="close" />
      </div>

      <div class="preview-body">
        <div class="preview-path">{{ path }}</div>

        <v-skeleton-loader v-if="loading && !result" type="list-item-three-line, list-item@3" />

        <template v-else-if="result">
          <div class="preview-summary">
            <div class="sum-item"><span class="sum-k">执行引擎：</span>{{ engineText }}</div>
            <div class="sum-item"><span class="sum-k">保留轨道：</span>{{ changes.keep ?? '—' }} 条</div>
            <div v-if="addedSubtitles.length" class="sum-item sum-add">
              ＋ 新增字幕 {{ addedSubtitles.length }} 条
              <span class="sum-note">{{ addedSubtitles.map((item) => item.name || item.file).join('、') }}</span>
            </div>
            <div v-if="addedAudios.length" class="sum-item sum-add">
              ＋ 新增音轨 {{ addedAudios.length }} 条
              <span class="sum-note">{{ addedAudios.map((item) => item.name || item.file).join('、') }}</span>
            </div>
            <div v-if="attachmentsAdd.length" class="sum-item sum-add">
              ＋ 字体附件 {{ attachmentsAdd.length }} 个
              <span class="sum-note">{{ attachmentsAdd.map((item) => baseName(item)).join('、') }}</span>
            </div>
            <div v-for="item in dropped" :key="`drop-${item.id}`" class="sum-item sum-del">
              ✕ 删除{{ item.type === 'audio' ? '音轨' : item.type === 'subtitle' ? '字幕' : item.type || '轨道' }}
              {{ item.name || `#${item.id}` }}
            </div>
            <div v-for="item in attachmentsDrop" :key="`ad-${item}`" class="sum-item sum-del">
              ✕ 删除字体附件 {{ item }}
            </div>
            <div v-for="item in edits" :key="`edit-${item.id}-${item.field}`" class="sum-item">
              <span class="sum-k">修改 {{ item.field }}：</span>
              <span class="sum-note">#{{ item.id }} {{ item.from }} → {{ item.to }}</span>
            </div>
            <div class="sum-item"><span class="sum-k">章节：</span>{{ chaptersText }}</div>
            <div class="sum-item"><span class="sum-k">容器标题：</span>{{ titleText }}</div>
          </div>

          <div class="preview-out">
            <div>输出：{{ result.output_path || '—' }}</div>
            <div v-if="result.no_backup" class="preview-nobackup">
              不做临时备份，失败时无恢复副本
            </div>
            <template v-else-if="result.output_mode === 'replace'">
              <div class="preview-backup">临时备份：成功后删除，失败保留</div>
              <div v-if="result.backup_path" class="preview-backup-path">备份：{{ result.backup_path }}</div>
            </template>
            <div v-if="spaceText">{{ spaceText }}</div>
          </div>

          <div v-for="(item, index) in blockers" :key="`blk-${index}`" class="warnbox warnbox--red">
            ⚠ {{ item.message || item.code }}
          </div>
          <div v-for="(item, index) in warnings" :key="`warn-${index}`" class="warnbox warnbox--warn">
            ⚠ {{ item.message || item.code }}
          </div>
          <div v-if="!engineReady" class="warnbox warnbox--red">
            ⚠ 未检测到 MKVToolNix，无法执行，请先在设置里安装或指定引擎路径
          </div>

          <!-- 时长不一致：强制勾选确认 -->
          <div v-if="hasDurationMismatch" class="duration-confirm">
            <v-checkbox
              :model-value="confirmed"
              density="compact"
              color="warning"
              hide-details
              label="我已知晓时长不一致，仍要执行"
              @update:model-value="emit('update:confirmed', $event)"
            />
            <div class="duration-confirm-hint">
              音轨 / 字幕与视频时长不一致（可能不是同一版本），执行后可能出现时间轴错位；建议先用「估偏移」校正 sync。
            </div>
          </div>

          <details v-if="commands.length" class="preview-cmd">
            <summary>命令详情（{{ commands.length }} 条）</summary>
            <pre v-for="(command, index) in commands" :key="`cmd-${index}`" class="preview-code">{{ commandText(command) }}</pre>
          </details>
          <div v-else class="preview-empty-cmd">后端未返回命令（无实际写操作时可以忽略）</div>
        </template>

        <v-alert v-else type="error" variant="tonal" density="compact">
          预览生成失败，请检查文件路径与引擎状态后重试
        </v-alert>
      </div>

      <div class="preview-foot">
        <span class="preview-foot-note">{{ fileLabel }}</span>
        <v-spacer />
        <div class="preview-foot-btns">
          <v-btn variant="text" :disabled="submitting" @click="close">取消</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="submitting"
            :disabled="!canSubmit"
            @click="confirm"
          >
            {{ confirmText || '确认执行' }}
          </v-btn>
        </div>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.preview-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.preview-title {
  font-size: 14.5px;
  font-weight: 600;
}
.preview-body {
  padding: 18px 20px;
  overflow: auto;
  max-height: 68vh;
}
/* PC 模式（medium）：预览弹窗加高，向下多显示内容 */
.preview-dialog.dialog-medium {
  display: flex;
  flex-direction: column;
  height: min(82vh, 820px);
  max-height: 82vh;
}
.dialog-medium .preview-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow: auto;
}
.preview-path {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  margin-bottom: 12px;
  word-break: break-all;
}
.preview-summary {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 18px;
  margin-bottom: 16px;
}
.sum-item {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.sum-k {
  color: rgb(var(--v-theme-on-surface));
}
.sum-add {
  color: #66bb6a;
}
.sum-del {
  color: #ef5350;
}
.sum-note {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 11.5px;
  word-break: break-all;
}
.preview-out {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-bottom: 12px;
  line-height: 1.8;
  word-break: break-all;
}
/* 原地替换临时备份信息：成功后自动删除，失败才保留 */
.preview-backup {
  color: rgba(var(--v-theme-on-surface), 0.65);
  line-height: 1.6;
}
.preview-backup-path {
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11px;
  line-height: 1.6;
}
/* 原地替换且不做临时备份：醒目提示无恢复副本 */
.preview-nobackup {
  color: #ef5350;
  font-weight: 600;
  line-height: 1.6;
}
.warnbox {
  border-radius: 9px;
  padding: 10px 12px;
  font-size: 12.5px;
  margin: 8px 0;
  line-height: 1.6;
}
/* 时长不一致强制确认 */
.duration-confirm {
  margin: 8px 0;
  padding: 4px 10px 8px;
  border: 1px solid rgba(255, 179, 0, 0.36);
  border-radius: 9px;
  background: rgba(255, 179, 0, 0.08);
}
.duration-confirm-hint {
  font-size: 11.5px;
  color: #ffb300;
  line-height: 1.6;
  padding-left: 2px;
}
.warnbox--warn {
  background: rgba(255, 179, 0, 0.1);
  border: 1px solid rgba(255, 179, 0, 0.32);
  color: #ffb300;
}
.warnbox--red {
  background: rgba(239, 83, 80, 0.1);
  border: 1px solid rgba(239, 83, 80, 0.32);
  color: #ef5350;
}
.preview-cmd {
  margin-top: 10px;
}
.preview-cmd summary {
  cursor: pointer;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  padding: 4px 0;
}
.preview-code {
  margin: 8px 0 0;
  background: rgba(0, 0, 0, 0.32);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 12px;
  font-size: 11.5px;
  line-height: 1.7;
  color: rgba(var(--v-theme-on-surface), 0.72);
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.preview-empty-cmd {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 10px;
}
.preview-dialog {
  /* 弹窗卡片完整包边 */
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.preview-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  flex-wrap: wrap;
}
.preview-foot-note {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.preview-foot-btns {
  display: flex;
  gap: 10px;
  flex: 0 0 auto;
}
/* 紧凑布局（真手机 or PC 模式容器窄）：全屏对话框内部改为纵向撑满 */
.preview-dialog.dialog-compact {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 0;
}
.dialog-compact .preview-body {
  flex: 1 1 auto;
  max-height: none;
  padding: 14px;
}
.dialog-compact .preview-head,
.dialog-compact .preview-foot {
  flex: 0 0 auto;
}
.dialog-compact .preview-head {
  padding: 12px 14px;
}
.dialog-compact .preview-foot {
  padding: 10px 14px;
}
.dialog-compact .preview-foot-btns {
  flex: 1 1 auto;
}
.dialog-compact .preview-foot-btns > * {
  flex: 1 1 0;
}
.dialog-compact .preview-foot-note {
  display: none;
}
.dialog-compact .preview-summary {
  grid-template-columns: 1fr;
  gap: 8px;
}
</style>
