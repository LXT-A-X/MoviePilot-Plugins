<script setup>
/**
 * 同级自动发现（按页签分类型显示）：
 * 字幕页只看同名字幕、音频页只看同名音频、附件页只看同目录字体；
 * 勾选 = 作为新增轨道 / 附件写入，不复制、不移动原文件
 */
import { computed } from 'vue'

const props = defineProps({
  // 全部候选（AppPage 已按 kind 分组好的扁平列表）
  items: { type: Array, default: () => [] },
  // narrow 单列；medium/wide 两列
  layout: { type: String, default: 'wide' },
  // 当前页签类型：subtitle | audio | font
  kind: { type: String, default: 'subtitle' },
  // 当前类型候选是否都已由自动导入/挂载按钮挂载
  mounted: { type: Boolean, default: false },
})

const narrow = computed(() => props.layout === 'narrow')
const emit = defineEmits(['toggle', 'mount-toggle'])

const KIND_META = {
  subtitle: {
    label: '同名字幕',
    hint: '只显示与视频同名前缀匹配的字幕；勾选后作为新增字幕轨写入',
    empty: '未发现同名字幕（srt / ass / ssa / vtt）',
    mountTip: '把前缀匹配的同名字幕一键加入字幕轨',
  },
  audio: {
    label: '同名音频',
    hint: '只显示与视频同名前缀匹配的音频；勾选后作为新增音轨写入',
    empty: '未发现同名音频（mka / flac / aac 等）',
    mountTip: '把前缀匹配的同名音频一键加入音轨',
  },
  font: {
    label: '同目录字体',
    hint: '只显示同目录（含 fonts/ 子目录）字体；勾选后作为字体附件写入',
    empty: '未发现同目录字体（ttf / otf / ttc）',
    mountTip: '把同目录字体一键加入附件',
  },
}
const meta = computed(() => KIND_META[props.kind] || KIND_META.subtitle)

// 只渲染当前页签对应类型
const kindItems = computed(() => props.items.filter((item) => item.kind === props.kind))
// 字幕/音频只挂载前缀匹配项；字体全部可挂载
const matchedCount = computed(() =>
  props.kind === 'font' ? kindItems.value.length : kindItems.value.filter((item) => item.matched).length,
)

function tagText(item) {
  const lang = item.language || ''
  const ext = String(item.ext || '').replace('.', '').toUpperCase()
  return [lang, ext].filter(Boolean).join(' · ')
}

function confirmToggle(item, value) {
  emit('toggle', item, value)
}
</script>

<template>
  <v-card variant="flat" class="sibling-card" :class="{ 'sibling-card--narrow': narrow }">
    <div class="sibling-title">
      同级自动发现 · {{ meta.label }}
      <span class="sibling-hint">{{ meta.hint }}</span>
      <v-spacer />
      <v-btn
        size="small"
        :variant="mounted ? 'flat' : 'tonal'"
        :color="mounted ? 'success' : undefined"
        :prepend-icon="mounted ? 'mdi-check-circle-outline' : 'mdi-auto-fix'"
        :disabled="!mounted && !matchedCount"
        :title="mounted ? '收回由自动导入/挂载加入的条目（手动添加的不会被删除）' : meta.mountTip"
        @click="emit('mount-toggle')"
      >
        {{ mounted ? '已挂载 · 点击收回' : '挂载' }}
      </v-btn>
    </div>
    <div v-if="!kindItems.length" class="sibling-empty">{{ meta.empty }}</div>
    <div v-else class="sibling-grid">
      <label v-for="item in kindItems" :key="item.key" class="sibling-row">
        <span class="sib-check">
          <v-checkbox-btn
            :model-value="item.checked"
            density="compact"
            color="primary"
            hide-details
            @update:model-value="confirmToggle(item, $event)"
          />
        </span>
        <span class="sibling-name" :title="item.path">{{ item.name }}</span>
        <span class="sibling-tag">{{ tagText(item) }}</span>
      </label>
    </div>
  </v-card>
</template>

<style scoped>
.sibling-card {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
}
.sibling-title {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sibling-hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-weight: 400;
}
.sibling-empty {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  padding: 4px 0;
}
.sibling-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 18px;
}
.sibling-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  cursor: pointer;
  min-width: 0;
  padding: 2px 0;
}
.sib-check {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
}
.sibling-name {
  color: rgb(var(--v-theme-on-surface));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.sibling-tag {
  flex: 0 0 auto;
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 5px;
  padding: 1px 6px;
}
.sibling-kind {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
/* narrow（真手机 / 容器 < 720）：单列 */
.sibling-card--narrow {
  padding: 12px;
}
.sibling-card--narrow .sibling-grid {
  grid-template-columns: 1fr;
  gap: 4px;
}
.sibling-card--narrow .sibling-row {
  font-size: 12px;
  min-height: 34px;
}
@media (max-width: 959px) {
  .sibling-card {
    padding: 12px;
  }
  .sibling-grid {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .sibling-row {
    font-size: 12px;
    min-height: 34px;
  }
}
</style>
