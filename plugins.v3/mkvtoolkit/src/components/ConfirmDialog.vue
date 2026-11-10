<script setup>
/**
 * 通用二次确认弹窗
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '确认操作' },
  text: { type: String, default: '' },
  detail: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  color: { type: String, default: 'primary' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'confirm'])
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="480"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="confirm-card">
      <div class="confirm-head">
        <span class="confirm-title">{{ title }}</span>
      </div>
      <div class="confirm-body">
        <div v-if="text" class="confirm-text">{{ text }}</div>
        <div v-if="detail" class="confirm-detail">{{ detail }}</div>
        <slot />
      </div>
      <div class="confirm-foot">
        <v-btn variant="text" :disabled="loading" @click="emit('update:modelValue', false)">取消</v-btn>
        <v-btn :color="props.color" variant="flat" :loading="loading" @click="emit('confirm')">
          {{ confirmText }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.confirm-card {
  /* 弹窗卡片完整包边 */
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  overflow: hidden;
}
.confirm-head {
  padding: 16px 20px 6px;
}
.confirm-title {
  font-size: 14.5px;
  font-weight: 600;
}
.confirm-body {
  padding: 4px 20px 12px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  line-height: 1.7;
}
.confirm-detail {
  margin-top: 6px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  word-break: break-all;
}
.confirm-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 10px 20px 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
@media (max-width: 959px) {
  .confirm-foot > * {
    flex: 1 1 0;
  }
}
</style>
