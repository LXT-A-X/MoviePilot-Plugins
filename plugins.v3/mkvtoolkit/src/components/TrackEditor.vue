<script setup>
/**
 * 音频/字幕轨道编辑器：桌面表格 + 手机卡片
 * - 保留勾选（取消 = 删除），新增轨道删除 = 直接移除
 * - ↑↓ 调整顺序（不做拖拽）
 * - 语言 / 轨道名 / 默认 / 强制
 */
import { computed, ref } from 'vue'
import { fmtChannels, codecLabel, SUBTITLE_ENCODINGS, LANGUAGE_ITEMS } from '../utils.js'

// 轨道编辑里的编码选项用紧凑文案，避免手机卡片宽度不足被截断
const TRACK_ENCODINGS = SUBTITLE_ENCODINGS.map((item) =>
  item.value === 'auto' ? { ...item, title: '自动' } : item,
)

const props = defineProps({
  kind: { type: String, required: true }, // audio | subtitle
  tracks: { type: Array, default: () => [] },
  // narrow: 卡片；medium: 紧凑表格；wide: 普通表格
  layout: { type: String, default: 'wide' },
})

const emit = defineEmits(['pick', 'upload', 'move', 'remove', 'estimate'])

const narrow = computed(() => props.layout === 'narrow')
const medium = computed(() => props.layout === 'medium')
const isAudio = computed(() => props.kind === 'audio')
const kindLabel = computed(() => (isAudio.value ? '音频' : '字幕'))

// 同一类轨道（同页签）内可自由移动，不区分原有/新增
function canMove(track, delta) {
  const list = props.tracks
  const index = list.findIndex((item) => item === track)
  const target = index + delta
  return index >= 0 && target >= 0 && target < list.length
}

function move(track, delta) {
  if (!canMove(track, delta)) return
  emit('move', track, delta)
}

function remove(track) {
  emit('remove', track)
}

function toggleKeep(track) {
  // 原有轨道：取消勾选 → 标记删除；新增轨道：取消勾选 → 本次不添加
  track.keep = !track.keep
}

function addTrack() {
  emit('pick', props.kind)
}

function uploadTrack() {
  emit('upload', props.kind)
}

// 由 AppPage 调 /analyze/offset 并把结果写回 track.sync_ms
function estimate(track) {
  emit('estimate', track)
}

function numberLabel(index) {
  return String(index + 1)
}

function sourceLabel(track) {
  if (!track.added) {
    // 原有字幕轨来自容器内部，标注「内嵌」；原有音频轨只显示编码
    const label = codecLabel(track)
    return props.kind === 'subtitle' ? `${label} · 内嵌` : label
  }
  const name = track.file?.name || track.file?.path || ''
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : '外部文件'
}

// 旧文件的 ISO 代码 / 其它 BCP47 变体统一映射到简体/繁体下拉项
function normalizeLang(value) {
  const code = String(value || 'und').trim()
  const lower = code.toLowerCase()
  if (['chi', 'zho', 'cmn', 'zh', 'zh-cn', 'zh-sg', 'zh-hans'].includes(lower)) return 'zh-Hans'
  if (['zh-tw', 'zh-hk', 'zh-mo', 'zh-hant'].includes(lower)) return 'zh-Hant'
  return code || 'und'
}

function displayLang(track) {
  return normalizeLang(track.language)
}

// 语言下拉：ISO 639-2 / BCP47 代码 + 中文名，支持「自定义…」手动输入
const CUSTOM_LANG = '__custom_lang__'
const customLang = ref({ open: false, value: '', track: null })

function languageItemsFor(track) {
  const code = normalizeLang(track.language)
  const known = LANGUAGE_ITEMS.some((item) => item.value === code)
  const base = known ? [...LANGUAGE_ITEMS] : [...LANGUAGE_ITEMS, { title: `${code}（自定义）`, value: code }]
  return [...base, { title: '自定义…', value: CUSTOM_LANG }]
}

function onLanguageChange(track, value) {
  if (value === CUSTOM_LANG) {
    customLang.value = { open: true, value: String(track.language || ''), track }
    return
  }
  // 保留 BCP47 大小写（zh-Hant），不要强转小写
  track.language = String(value || '').trim() || 'und'
}

function cancelCustomLang() {
  customLang.value = { open: false, value: '', track: null }
}

function confirmCustomLang() {
  const track = customLang.value.track
  if (track) track.language = String(customLang.value.value || '').trim() || 'und'
  cancelCustomLang()
}
</script>

<template>
  <v-card variant="flat" class="track-card" :class="{ 'track-card--medium': medium }">
    <div class="track-card-title">
      {{ kindLabel }}轨
      <span class="track-card-hint">
        {{ isAudio ? '取消勾选 = 删除；顺序影响播放器列表' : '取消勾选 = 删除；新增字幕来自同级文件或上传' }}
      </span>
    </div>

    <div v-if="!tracks.length" class="track-empty">
      暂无{{ kindLabel }}轨。{{ isAudio ? '可管理已有轨道，或从目录/上传音频文件新增。' : '可从目录选择或上传字幕文件新增。' }}
    </div>

    <!-- 桌面：表格 -->
    <table v-else-if="!narrow" class="track-table">
      <thead>
        <tr>
          <th class="col-no">#</th>
          <th class="col-keep">保留</th>
          <th>{{ isAudio ? '编码 / 来源' : '格式 / 来源' }}</th>
          <th v-if="isAudio" class="col-channels">声道</th>
          <th class="col-lang">语言</th>
          <th class="col-name">轨道名</th>
          <th class="col-switch">默认</th>
          <th class="col-switch">强制</th>
          <th class="col-ops"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(track, index) in tracks" :key="track.id" :class="{ dropping: !track.keep }">
          <td class="col-no">{{ numberLabel(index) }}</td>
          <td class="col-keep">
            <div class="cell-center">
              <v-checkbox-btn
                :model-value="track.keep"
                density="compact"
                color="primary"
                hide-details
                :aria-label="`保留${kindLabel}轨 ${numberLabel(index)}`"
                @update:model-value="toggleKeep(track)"
              />
            </div>
          </td>
          <td class="track-source">
            <template v-if="!track.added">
              <span class="track-codec">{{ codecLabel(track) }}</span>
              <span v-if="kind === 'subtitle'" class="track-embedded">· 内嵌</span>
            </template>
            <template v-else>
              <div class="added-source">
                <v-chip size="x-small" variant="tonal" color="primary" class="added-tag">新增</v-chip>
                <span class="added-file" :title="track.file?.path">{{ sourceLabel(track) }} · {{ track.file?.name }}</span>
              </div>
              <div class="added-extra">
                <v-select
                  v-if="!isAudio"
                  v-model="track.encoding"
                  :items="TRACK_ENCODINGS"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="encoding-select"
                  title="字幕文件编码"
                />
                <v-text-field
                  v-model.number="track.sync_ms"
                  type="number"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="0"
                  suffix="ms"
                  class="sync-input"
                  :title="isAudio ? '音轨延迟校正（毫秒，正数=延后）' : '字幕延迟校正（毫秒，正数=延后）'"
                />
                <v-btn
                  size="x-small"
                  variant="tonal"
                  prepend-icon="mdi-timer-sync-outline"
                  class="estimate-btn"
                  :loading="Boolean(track._estimating)"
                  :disabled="Boolean(track._estimating) || !track.file?.path"
                  :title="track._offsetHint || '用 ffmpeg 估计与视频的偏移（实验功能，结果需自行确认）'"
                  @click="estimate(track)"
                >
                  估偏移
                </v-btn>
              </div>
            </template>
          </td>
          <td v-if="isAudio" class="col-channels">{{ track.added ? '—' : fmtChannels(track) }}</td>
          <td class="col-lang">
            <v-select
              :model-value="displayLang(track)"
              :items="languageItemsFor(track)"
              density="compact"
              variant="outlined"
              hide-details
              class="lang-input lang-select"
              placeholder="und"
              :aria-label="`${kindLabel}轨 ${numberLabel(index)} 语言`"
              @update:model-value="onLanguageChange(track, $event)"
            />
          </td>
          <td class="col-name">
            <v-text-field
              v-model="track.name"
              density="compact"
              variant="outlined"
              hide-details
              placeholder="轨道名"
              :aria-label="`${kindLabel}轨 ${numberLabel(index)} 名称`"
            />
          </td>
          <td class="col-switch">
            <div class="cell-center">
              <v-switch
                v-model="track.default"
                density="compact"
                color="primary"
                hide-details
                :aria-label="`${kindLabel}轨 ${numberLabel(index)} 默认`"
              />
            </div>
          </td>
          <td class="col-switch">
            <div class="cell-center">
              <v-switch
                v-model="track.forced"
                density="compact"
                color="primary"
                hide-details
                :aria-label="`${kindLabel}轨 ${numberLabel(index)} 强制`"
              />
            </div>
          </td>
          <td class="col-ops">
            <div class="track-ops">
              <v-btn
                size="x-small"
                variant="tonal"
                icon="mdi-arrow-up"
                :disabled="!canMove(track, -1)"
                title="上移"
                @click="move(track, -1)"
              />
              <v-btn
                size="x-small"
                variant="tonal"
                icon="mdi-arrow-down"
                :disabled="!canMove(track, 1)"
                title="下移"
                @click="move(track, 1)"
              />
              <v-btn
                size="x-small"
                variant="tonal"
                :icon="!track.added && !track.keep ? 'mdi-restore' : 'mdi-close'"
                :title="!track.added && !track.keep ? '恢复该轨道' : (track.added ? '移除新增' : '标记删除')"
                @click="remove(track)"
              />
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 手机：卡片 -->
    <div v-else class="track-cards">
      <div v-for="(track, index) in tracks" :key="track.id" class="m-track" :class="{ dropping: !track.keep }">
        <v-checkbox-btn
          :model-value="track.keep"
          density="compact"
          color="primary"
          hide-details
          class="m-track-check"
          @update:model-value="toggleKeep(track)"
        />
        <div class="m-track-main">
          <div class="m-track-title">
            <span class="m-track-no">{{ numberLabel(index) }}</span>
            <span>{{ sourceLabel(track) }}</span>
            <span v-if="isAudio && !track.added" class="m-track-sub">{{ fmtChannels(track) }}</span>
            <span v-if="track.added" class="m-track-tag">新增</span>
          </div>
          <div v-if="track.added" class="m-track-file" :title="track.file?.path">{{ track.file?.name }}</div>
          <div class="m-track-fields">
            <div class="m-field-wrap m-field-lang">
              <span class="m-field-cap">语言</span>
              <v-select
                :model-value="displayLang(track)"
                :items="languageItemsFor(track)"
                placeholder="und"
                density="compact"
                variant="outlined"
                hide-details
                class="m-lang-select"
                @update:model-value="onLanguageChange(track, $event)"
              />
            </div>
            <div class="m-field-wrap m-field-name">
              <span class="m-field-cap">轨道名</span>
              <v-text-field
                v-model="track.name"
                placeholder="轨道名"
                density="compact"
                variant="outlined"
                hide-details
              />
            </div>
          </div>
          <div v-if="track.added" class="m-track-fields">
            <div v-if="!isAudio" class="m-field-wrap m-field-lang">
              <span class="m-field-cap">字幕编码</span>
              <v-select
                v-model="track.encoding"
                :items="TRACK_ENCODINGS"
                density="compact"
                variant="outlined"
                hide-details
              />
            </div>
            <div class="m-field-wrap m-field-lang">
              <span class="m-field-cap">延迟（ms）</span>
              <v-text-field
                v-model.number="track.sync_ms"
                type="number"
                placeholder="0"
                density="compact"
                variant="outlined"
                hide-details
              />
            </div>
            <v-btn
              class="m-estimate"
              size="small"
              variant="tonal"
              prepend-icon="mdi-timer-sync-outline"
              :loading="Boolean(track._estimating)"
              :disabled="Boolean(track._estimating) || !track.file?.path"
              :title="track._offsetHint || '用 ffmpeg 估计与视频的偏移（实验功能，结果需自行确认）'"
              @click="estimate(track)"
            >
              估偏移
            </v-btn>
          </div>
          <div class="m-track-controls">
            <v-switch
              v-model="track.default"
              label="默认"
              density="compact"
              color="primary"
              hide-details
              class="m-switch"
            />
            <v-switch
              v-model="track.forced"
              label="强制"
              density="compact"
              color="primary"
              hide-details
              class="m-switch"
            />
            <v-spacer />
            <div class="m-ops">
              <v-btn size="small" variant="tonal" icon="mdi-arrow-up" :disabled="!canMove(track, -1)" @click="move(track, -1)" />
              <v-btn size="small" variant="tonal" icon="mdi-arrow-down" :disabled="!canMove(track, 1)" @click="move(track, 1)" />
              <v-btn
                size="small"
                variant="tonal"
                :icon="!track.added && !track.keep ? 'mdi-restore' : 'mdi-close'"
                @click="remove(track)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="track-add-row">
      <v-btn size="small" variant="tonal" prepend-icon="mdi-folder-open-outline" @click="addTrack">
        从目录选择{{ kindLabel }}
      </v-btn>
      <v-btn size="small" variant="text" prepend-icon="mdi-upload-outline" @click="uploadTrack">
        上传{{ kindLabel }}
      </v-btn>
    </div>
    <div class="track-hint">
      <template v-if="isAudio">
        支持 aac / flac / mka / ac3 / dts / mp3 / m4a；音频文件通常超过上传上限，建议用目录选择
      </template>
      <template v-else>
        内封 srt / ass / ssa / vtt；编码可自动探测或强制 GBK / BIG5
      </template>
    </div>
    <!-- 自定义语言代码 -->
    <v-dialog v-model="customLang.open" max-width="440">
      <v-card class="custom-lang-dialog">
        <div class="custom-lang-title">自定义语言代码</div>
        <div class="custom-lang-body">
          <v-text-field
            v-model="customLang.value"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="chi / jpn / zh-CN"
            autofocus
            @keyup.enter="confirmCustomLang"
          />
          <div class="custom-lang-hint">需 ISO 639-2 / BCP 47 代码，如 chi、jpn、zh-CN；留空则使用 und</div>
        </div>
        <div class="custom-lang-foot">
          <v-btn variant="text" @click="cancelCustomLang">取消</v-btn>
          <v-btn color="primary" variant="flat" @click="confirmCustomLang">确定</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<style scoped>
.track-card {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
}
.track-card-title {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.track-card-hint {
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11px;
  font-weight: 400;
}
.track-empty {
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 12px;
  padding: 8px 0;
  line-height: 1.7;
}
.track-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.track-table th {
  text-align: left;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11.5px;
  padding: 4px 6px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  white-space: nowrap;
}
.track-table td {
  padding: 6px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.7);
  vertical-align: middle;
}
.track-table tr:last-child td {
  border-bottom: none;
}
.track-table tbody tr:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.track-table tr.dropping td {
  opacity: 0.45;
}
.track-table tr.dropping td.col-ops {
  opacity: 1;
}
.col-no {
  width: 26px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  text-align: center;
}
.col-keep {
  width: 42px;
  text-align: center;
}
.col-channels {
  width: 60px;
}
.col-lang {
  width: 130px;
  text-align: center;
}
.col-name {
  min-width: 120px;
  text-align: center;
}
.col-switch {
  width: 54px;
  text-align: center;
}
.track-table th.col-lang,
.track-table th.col-name,
.track-table th.col-channels,
.track-table th.col-ops {
  text-align: center;
}
.track-table td.col-channels,
.track-table td.col-ops {
  text-align: center;
}
/* 语言/轨道名单元格内控件居中且同高
   注意：构建会过滤含 .v- 的选择器，这里用 [class~="..."] 属性选择器，避免规则被剥离 */
.track-table td.col-lang :deep([class~="v-field"]),
.track-table td.col-name :deep([class~="v-field"]) {
  min-height: 34px;
}
.track-table td.col-lang :deep([class~="v-field__input"]),
.track-table td.col-name :deep([class~="v-field__input"]) {
  justify-content: center;
  text-align: center;
}
.track-table td.col-lang :deep([class~="v-select__selection"]),
.track-table td.col-lang :deep([class~="v-select__selection-text"]) {
  justify-content: center;
  text-align: center;
  width: 100%;
}
.track-table td.col-lang :deep(input),
.track-table td.col-name :deep(input) {
  text-align: center;
}
.lang-select {
  min-width: 120px;
}
.track-table th.col-switch {
  text-align: center;
}
.cell-center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
}
.col-ops {
  width: 112px;
}
.track-ops {
  display: flex;
  gap: 4px;
  justify-content: center;
}
.track-source {
  font-size: 12.5px;
}
.track-codec {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
}
.track-embedded {
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-left: 4px;
  font-size: 11.5px;
}
.track-sub {
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-size: 11px;
  margin-left: 6px;
}
.added-source {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.added-tag {
  flex: 0 0 auto;
}
.added-file {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 190px;
}
.added-extra {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.added-extra :deep([class~="v-field"]) {
  min-height: 34px;
}
.added-extra .v-btn {
  height: 34px;
}
.sync-input {
  max-width: 110px;
}
.encoding-select {
  max-width: 130px;
}
.estimate-btn {
  flex: 0 0 auto;
}
.lang-input {
  min-width: 74px;
}
.track-table :deep([class~="v-field"]) {
  font-size: 12px;
}
.track-add-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.track-hint {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 8px;
  line-height: 1.6;
}
/* 自定义语言代码弹窗 */
.custom-lang-dialog {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.custom-lang-title {
  padding: 14px 18px 4px;
  font-size: 14.5px;
  font-weight: 600;
}
.custom-lang-body {
  padding: 6px 18px 10px;
}
.custom-lang-hint {
  margin-top: 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.6;
}
.custom-lang-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 10px 18px 14px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

/* ---------------- 手机卡片 ---------------- */
.track-cards {
  display: flex;
  flex-direction: column;
}
.m-track {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.m-track:last-child {
  border-bottom: none;
}
.m-track.dropping {
  opacity: 0.55;
}
.m-track.dropping .m-track-title {
  text-decoration: line-through;
}
.m-track-check {
  flex: 0 0 auto;
  margin-top: 2px;
}
.m-track-main {
  flex: 1;
  min-width: 0;
}
.m-track-title {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1.4;
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  word-break: break-all;
}
.m-track-no {
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.m-track-sub {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 11.5px;
}
.m-track-tag {
  font-size: 10.5px;
  color: rgb(var(--v-theme-primary));
  border: 1px solid rgba(var(--v-theme-primary), 0.4);
  border-radius: 5px;
  padding: 0 5px;
  line-height: 16px;
}
.m-track-file {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
.m-track-fields {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.m-track-fields :deep([class~="v-field"]) {
  min-height: 36px;
}
.m-field-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
/* 手机卡片：标签左对齐，控件内文字居中
   构建会过滤含 .v- 的选择器，这里用 [class~="..."] 属性选择器；下拉菜单 teleport 到 body 不受影响 */
.m-field-wrap :deep([class~="v-field__input"]) {
  justify-content: center;
  text-align: center;
}
.m-field-wrap :deep([class~="v-select__selection"]),
.m-field-wrap :deep([class~="v-select__selection-text"]) {
  justify-content: center;
  text-align: center;
  width: 100%;
}
.m-field-wrap :deep(input) {
  text-align: center;
}
.m-field-wrap :deep([class~="v-field__field"]) {
  text-align: center;
}
.m-estimate {
  align-self: flex-end;
  margin-bottom: 2px;
  flex: 0 0 auto;
}
.m-field-cap {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.2;
}
.m-field-lang {
  flex: 0 0 138px;
}
.m-field-name {
  flex: 1;
  min-width: 0;
}
.m-track-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.m-switch {
  flex: 0 0 auto;
  margin: 0;
}
.m-ops {
  display: flex;
  gap: 4px;
}
/* medium（720~1100）：保持表格，只收紧列宽/内边距，避免横向滚动 */
.track-card--medium {
  padding: 12px;
}
.track-card--medium .track-table th,
.track-card--medium .track-table td {
  padding: 4px;
}
.track-card--medium .col-no {
  width: 22px;
}
.track-card--medium .col-keep {
  width: 34px;
}
.track-card--medium .col-channels {
  width: 50px;
}
.track-card--medium .col-lang {
  width: 112px;
}
.track-card--medium .col-name {
  min-width: 100px;
}
.track-card--medium .col-switch {
  width: 46px;
}
.track-card--medium .col-ops {
  width: 104px;
}
.track-card--medium .lang-input {
  min-width: 104px;
}
.track-card--medium .added-file {
  max-width: 150px;
}
.track-card--medium .sync-input {
  max-width: 96px;
}
.track-card--medium .encoding-select {
  max-width: 112px;
}
@media (max-width: 959px) {
  .track-card {
    padding: 12px;
  }
  .track-add-row > * {
    flex: 1 1 0;
    min-width: 0;
  }
}
</style>
