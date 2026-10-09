<template>
  <v-dialog :model-value="!!state.open" max-width="460"
            @update:model-value="(v) => { if (!v) onCancel() }">
    <v-card>
      <v-card-title>{{ state.title || '请确认' }}</v-card-title>
      <v-card-text>
        <div v-if="state.text" class="cfm-text">{{ state.text }}</div>
        <div v-if="state.detail" class="cfm-detail" :class="{ 'is-danger': state.color === 'error' }">{{ state.detail }}</div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="onCancel">取消</v-btn>
        <v-btn variant="flat" :color="state.color || 'warning'" @click="onOk">{{ state.okText || '确认' }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
defineProps({
  state: { type: Object, required: true },
  onOk: { type: Function, required: true },
  onCancel: { type: Function, required: true },
})
</script>

<style scoped>
.cfm-text { font-size: 14px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.cfm-detail {
  margin-top: 10px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  opacity: .9; background: rgba(128,128,128,.14); border-radius: 6px; padding: 8px 10px;
}
.cfm-detail.is-danger { background: rgba(var(--v-theme-error), .12); }
</style>