<script setup>
/**
 * 上传小文件（字幕 / 音频 / 字体）
 * 前端先用 file.size 校验 upload_max_mb，超限直接拒绝并提示改用「从目录选择」；
 * 后端返回超限错误时同样提示。
 */
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { fmtBytes, SUBTITLE_EXTENSIONS, AUDIO_EXTENSIONS, FONT_EXTENSIONS, ARCHIVE_EXTENSIONS, isArchiveName } from '../utils.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  api: { type: Object, required: true },
  kind: { type: String, default: 'subtitle' },
  maxMb: { type: Number, default: 50 },
  title: { type: String, default: '' },
  // 布局三档：narrow 全屏；medium 520px；wide 540px
  layout: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'uploaded'])
const display = useDisplay()
const effectiveLayout = computed(() => props.layout || (display.mdAndUp.value ? 'wide' : 'narrow'))
const mobile = computed(() => effectiveLayout.value === 'narrow')
const dialogMaxWidth = computed(() => {
  if (mobile.value) return undefined
  return effectiveLayout.value === 'medium' ? 520 : 540
})

const KIND_TITLE = { subtitle: '上传字幕', audio: '上传音频', font: '上传字体' }
const KIND_ACCEPT = {
  subtitle: SUBTITLE_EXTENSIONS.join(','),
  audio: AUDIO_EXTENSIONS.join(','),
  // 字体页同时允许直接上传字体压缩包（走 /archive/upload 解压）
  font: [...FONT_EXTENSIONS, ...ARCHIVE_EXTENSIONS].join(','),
}

const fileInput = ref(null)
const file = ref(null)
const uploading = ref(false)
const error = ref('')
const dragging = ref(false)

const dialogTitle = computed(() => props.title || KIND_TITLE[props.kind] || '上传文件')
const limitMb = computed(() => (Number(props.maxMb) > 0 ? Number(props.maxMb) : 50))
const limitBytes = computed(() => limitMb.value * 1024 * 1024)
const accept = computed(() => KIND_ACCEPT[props.kind] || '')
// 字体页选中压缩包时改走 /archive/upload，上限 512MB
const fileIsArchive = computed(() => props.kind === 'font' && isArchiveName(file.value?.name || ''))
const archiveLimitBytes = 512 * 1024 * 1024
const effectiveLimitBytes = computed(() => (fileIsArchive.value ? archiveLimitBytes : limitBytes.value))
const uploadHint = computed(() =>
  fileIsArchive.value ? '压缩包最大 512MB，上传后自动解压出字体' : `上传上限 ${limitMb.value}MB，超过请改用「从目录选择」`,
)

function reset() {
  file.value = null
  error.value = ''
  uploading.value = false
  dragging.value = false
  if (fileInput.value) fileInput.value.value = ''
}

function pickFile() {
  if (uploading.value) return
  fileInput.value?.click()
}

function validate(f) {
  if (!f) return false
  const isArchive = props.kind === 'font' && isArchiveName(f.name)
  const limit = isArchive ? archiveLimitBytes : limitBytes.value
  if (f.size > limit) {
    file.value = null
    error.value = isArchive
      ? `压缩包 ${fmtBytes(f.size)} 超过 512MB 上限`
      : `文件 ${fmtBytes(f.size)} 超过 ${limitMb.value}MB 上限，请改用「从目录选择」`
    return false
  }
  return true
}

function onFileChange(event) {
  const f = event.target.files?.[0]
  error.value = ''
  if (!validate(f)) {
    file.value = null
    return
  }
  file.value = f
}

function onDrop(event) {
  dragging.value = false
  if (uploading.value) return
  const f = event.dataTransfer?.files?.[0]
  error.value = ''
  if (!validate(f)) {
    file.value = null
    return
  }
  file.value = f
}

async function upload() {
  if (!file.value || uploading.value) return
  // 双保险：上传前再校验一次
  if (!validate(file.value)) return
  uploading.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file.value)
    if (props.kind === 'font' && isArchiveName(file.value.name)) {
      // 压缩包：后端上传后直接解压字体
      const data = await props.api.upload('/archive/upload', form)
      emit('uploaded', { ...(data || {}), kind: 'font', archiveUpload: true })
    } else {
      const data = await props.api.upload('/upload', form, { kind: props.kind })
      emit('uploaded', { ...(data || {}), kind: props.kind })
    }
    emit('update:modelValue', false)
    reset()
  } catch (err) {
    // 后端超限文案已明确（含「请改用从目录选择」），直接展示
    error.value = err.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) reset()
  },
)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    :max-width="dialogMaxWidth"
    :fullscreen="mobile"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="upload-dialog" :class="{ 'dialog-compact': mobile }">
      <div class="upload-head">
        <span class="upload-title">{{ dialogTitle }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="emit('update:modelValue', false)" />
      </div>

      <div class="upload-body">
        <input ref="fileInput" type="file" class="upload-input" :accept="accept" @change="onFileChange" />
        <div
          class="upload-drop"
          :class="{ 'upload-drop--drag': dragging }"
          role="button"
          tabindex="0"
          @click="pickFile"
          @keydown.enter.prevent="pickFile"
          @keydown.space.prevent="pickFile"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <v-icon size="30" icon="mdi-upload-outline" class="upload-big" />
          <div class="upload-main">点击选择文件，或拖到这里</div>
          <div class="upload-sub">{{ uploadHint }}</div>
        </div>

        <div v-if="file" class="upload-selected">
          <v-icon size="16" icon="mdi-file-outline" />
          <span class="upload-fname" :title="file.name">{{ file.name }}</span>
          <span class="upload-fsize">{{ fmtBytes(file.size) }}</span>
          <v-btn size="x-small" variant="text" :disabled="uploading" @click="file = null">移除</v-btn>
        </div>

        <div v-if="error" class="upload-error">{{ error }}</div>

        <div class="upload-warn">
          宿主 nginx 默认请求体上限 50MB，超过会直接失败；音频 / 大字体请用「从目录选择」。
          <template v-if="kind === 'font'">字体压缩包（zip/7z/rar/tar）最大 512MB，上传后自动解压出字体；超过 50MB 的压缩包请放到媒体目录用「从目录批量解压」。</template>
        </div>
        <div class="upload-note">上传的文件存放到插件数据目录，处理完成后不会留在媒体库。</div>
      </div>

      <div class="upload-foot">
        <v-spacer />
        <div class="upload-foot-btns">
          <v-btn variant="text" :disabled="uploading" @click="emit('update:modelValue', false)">取消</v-btn>
          <v-btn color="primary" variant="flat" :loading="uploading" :disabled="!file" @click="upload">上传</v-btn>
        </div>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.upload-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.upload-title {
  font-size: 14.5px;
  font-weight: 600;
}
.upload-body {
  padding: 18px 20px;
}
.upload-input {
  display: none;
}
.upload-drop {
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.28);
  border-radius: 12px;
  padding: 26px 16px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.7);
  background: rgba(var(--v-theme-on-surface), 0.04);
  cursor: pointer;
  transition: border-color 0.15s ease;
}
.upload-drop:hover,
.upload-drop--drag {
  border-color: rgba(var(--v-theme-primary), 0.6);
  color: rgb(var(--v-theme-on-surface));
}
.upload-big {
  margin-bottom: 8px;
  opacity: 0.85;
}
.upload-main {
  font-size: 13px;
}
.upload-sub {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  margin-top: 6px;
}
.upload-selected {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-size: 12.5px;
}
.upload-fname {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.upload-fsize {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 11.5px;
}
.upload-error {
  margin-top: 10px;
  font-size: 12.5px;
  color: #ef5350;
  background: rgba(239, 83, 80, 0.1);
  border: 1px solid rgba(239, 83, 80, 0.32);
  border-radius: 8px;
  padding: 9px 12px;
  line-height: 1.6;
}
.upload-warn {
  font-size: 11.5px;
  color: #ffb300;
  margin-top: 12px;
  line-height: 1.6;
}
.upload-note {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 8px;
  line-height: 1.6;
}
.upload-dialog {
  /* 弹窗卡片完整包边 */
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.upload-foot {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.upload-foot-btns {
  display: flex;
  gap: 10px;
}
/* 紧凑布局（真手机 or PC 模式容器窄）：全屏对话框内部改为纵向撑满 */
.upload-dialog.dialog-compact {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 0;
}
.dialog-compact .upload-body {
  flex: 1 1 auto;
  padding: 14px;
}
.dialog-compact .upload-head,
.dialog-compact .upload-foot {
  flex: 0 0 auto;
}
.dialog-compact .upload-head {
  padding: 12px 14px;
}
.dialog-compact .upload-foot {
  padding: 10px 14px;
}
.dialog-compact .upload-foot-btns {
  flex: 1 1 auto;
}
.dialog-compact .upload-foot-btns > * {
  flex: 1 1 0;
}
.dialog-compact .upload-drop {
  padding: 30px 14px;
}
</style>
