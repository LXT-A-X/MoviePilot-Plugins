<script setup>
/**
 * 统一「任务正在执行」拦截弹窗（v4.6.70 · 审查报告第四节）。
 * 不提供「强行继续」——只允许取消，或去看任务进度（切到仪表盘）。
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  reason: { type: String, default: '' },
  action: { type: String, default: '' },
  state: { type: String, default: '' },   // v4.6.73：统一任务状态名（如「写回 NFO 中」）
})
const emit = defineEmits(['update:modelValue', 'view-task'])

function close() { emit('update:modelValue', false) }
function viewTask() { close(); emit('view-task') }
</script>

<template>
  <v-dialog
    :model-value="props.modelValue"
    max-width="470"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center" style="font-size:16px">
        <v-icon start color="warning">mdi-lock-alert-outline</v-icon>
        任务正在执行，修改已锁定
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text>
        <div class="mb-2">当前正在进行：<b>{{ props.reason || '后台任务' }}</b></div>
        <div v-if="props.state && props.state !== props.reason" class="mb-2">
          任务状态：<b>{{ props.state }}</b>
          <span class="text-caption" style="opacity:.7">（数据变更已锁定）</span>
        </div>
        <div v-if="props.action" class="mb-2">本次尝试的操作：<b>{{ props.action }}</b></div>
        <div class="text-body-2" style="opacity:.8">
          该操作会修改数据库或文件。为避免翻译结果、写回内容或人工修改互相覆盖，
          当前暂不可执行。请等待任务完成，或到仪表盘「终止」后再试。
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="viewTask">查看任务</v-btn>
        <v-btn color="primary" variant="flat" @click="close">取消</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
