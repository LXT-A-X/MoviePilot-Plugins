<script setup>
/**
 * 队列页：运行中 / 等待中 / 待启动，进度、取消、置顶/上移/下移、开始、全部开始、暂停、清空等待；
 * 待启动或暂停中的等待任务支持「编辑」（回填编辑器后重新提交更新）。
 */
import { computed } from 'vue'
import { fmtDateTime, fmtDuration } from '../utils.js'

const props = defineProps({
  jobs: { type: Array, default: () => [] },
  paused: { type: Boolean, default: false },
  concurrency: { type: Number, default: 1 },
  held: { type: Number, default: 0 },
  editingId: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  // narrow: 卡片；medium: 紧凑表格；wide: 普通表格
  layout: { type: String, default: 'wide' },
})

const emit = defineEmits(['refresh', 'cancel', 'move', 'pause', 'clear', 'start', 'start-all', 'edit', 'set-concurrency'])

const narrow = computed(() => props.layout === 'narrow')
const medium = computed(() => props.layout === 'medium')

const running = computed(() => props.jobs.filter((job) => job.status === 'running'))
const pending = computed(() => props.jobs.filter((job) => job.status === 'pending'))
const rows = computed(() => running.value.concat(pending.value))
const heldJobs = computed(() => pending.value.filter((job) => Boolean(job.hold)))
// 以任务列表为准，status.queue.held 作为兜底（列表还没刷到时的页头数量）
const heldCount = computed(() => Math.max(Number(props.held) || 0, heldJobs.value.length))

const concurrencyItems = [1, 2, 3]

function isHeld(job) {
  return Boolean(job?.hold) && job?.status === 'pending'
}

// 队列内编辑：待启动任务，或队列暂停时的等待任务（后端只允许改 pending）
function canEdit(job) {
  return job?.status === 'pending' && (Boolean(job.hold) || props.paused)
}

function statusLabel(job) {
  if (job.status === 'running') return job.stage ? String(job.stage) : '运行中'
  if (job.status === 'pending') return job.hold ? '待启动' : '等待中'
  if (job.status === 'cancelled') return '已取消'
  if (job.status === 'failed') return '失败'
  if (job.status === 'success') return '成功'
  return job.status || '—'
}

function stateClass(job) {
  if (job.status === 'running') return 'badge-state--run'
  if (isHeld(job)) return 'badge-state--hold'
  return 'badge-state--wait'
}

function progressOf(job) {
  const value = Number(job.progress)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}

function etaText(job) {
  if (job.status !== 'running') return ''
  const progress = progressOf(job)
  if (progress <= 0) return ''
  const elapsed = Number(job.duration) > 0 ? Number(job.duration) : 0
  if (!elapsed) return ''
  const remaining = (elapsed / progress) * (100 - progress)
  if (!Number.isFinite(remaining) || remaining <= 0) return ''
  return `${fmtDuration(remaining)} 剩余`
}

function progressText(job) {
  const progress = progressOf(job)
  if (job.status !== 'running') return ''
  const eta = etaText(job)
  return eta ? `${progress}% · 约 ${eta}` : `${progress}%`
}

function moveTo(job, to) {
  emit('move', job, to)
}

function cancel(job) {
  emit('cancel', job)
}

function togglePause() {
  emit('pause', !props.paused)
}

function changeConcurrency(value) {
  const num = Number(value)
  if (!num || num === props.concurrency) return
  emit('set-concurrency', num)
}
</script>

<template>
  <div class="queue-page" :class="{ 'queue-page--medium': medium }">
    <div class="page-head">
      <h2 class="page-title">队列</h2>
      <span class="page-count">
        {{ running.length }} 运行中 · {{ pending.length }} 等待中
        <span v-if="heldCount" class="page-held">· {{ heldCount }} 个待启动</span>
        <span v-if="paused" class="page-paused">（已暂停）</span>
      </span>
      <div class="page-actions">
        <v-btn
          size="small"
          color="primary"
          variant="flat"
          prepend-icon="mdi-play-circle-outline"
          :disabled="!heldCount"
          @click="emit('start-all')"
        >
          全部开始
        </v-btn>
        <label class="queue-concurrency">
          并发
          <v-select
            :model-value="concurrency"
            :items="concurrencyItems"
            density="compact"
            variant="outlined"
            hide-details
            class="concurrency-select"
            @update:model-value="changeConcurrency"
          />
        </label>
        <v-btn size="small" variant="tonal" :prepend-icon="paused ? 'mdi-play' : 'mdi-pause'" @click="togglePause">
          {{ paused ? '继续队列' : '暂停队列' }}
        </v-btn>
        <v-btn size="small" variant="text" :disabled="!pending.length" @click="emit('clear')">清空等待</v-btn>
        <v-btn size="small" variant="text" icon="mdi-refresh" :loading="loading" title="刷新" @click="emit('refresh')" />
      </div>
    </div>

    <v-skeleton-loader v-if="loading && !rows.length" type="list-item@4" />

    <div v-else-if="!rows.length" class="page-empty">
      队列为空。去「编辑」页选择文件，预览确认后会加入队列。
    </div>

    <template v-else>
      <!-- 桌面：表格 -->
      <v-card v-if="!narrow" variant="flat" class="queue-table-card">
        <table class="queue-table">
          <thead>
            <tr>
              <th class="col-no"></th>
              <th class="col-status">状态</th>
              <th>文件</th>
              <th class="col-summary">操作摘要</th>
              <th class="col-progress">进度</th>
              <th class="col-ops"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(job, index) in rows" :key="job.id" class="queue-row">
              <td class="col-no">{{ index + 1 }}</td>
              <td class="col-status">
                <span class="badge-state" :class="stateClass(job)">
                  <i v-if="job.status === 'running'" class="badge-dot" />
                  {{ statusLabel(job) }}
                </span>
              </td>
              <td class="name-cell">
                <div class="file-name" :title="job.path">
                  {{ job.name || job.path }}
                  <v-chip v-if="editingId === job.id" size="x-small" color="info" variant="tonal" class="editing-tag">
                    编辑中
                  </v-chip>
                </div>
                <div class="file-sub">{{ job.engine || '' }}<span v-if="job.error"> · {{ job.error }}</span></div>
              </td>
              <td class="summary-cell">{{ job.summary || '—' }}</td>
              <td class="progress-cell">
                <template v-if="job.status === 'running'">
                  <v-progress-linear :model-value="progressOf(job)" height="6" rounded color="primary" />
                  <div class="progress-text">{{ progressText(job) }}</div>
                </template>
                <span v-else class="progress-idle">—</span>
              </td>
              <td class="ops-cell">
                <div class="row-ops">
                  <template v-if="job.status === 'running'">
                    <v-btn size="x-small" variant="tonal" @click="cancel(job)">取消</v-btn>
                  </template>
                  <template v-else>
                    <v-btn
                      v-if="canEdit(job)"
                      size="x-small"
                      variant="tonal"
                      prepend-icon="mdi-pencil"
                      @click="emit('edit', job)"
                    >
                      编辑
                    </v-btn>
                    <v-btn
                      v-if="isHeld(job)"
                      size="x-small"
                      color="primary"
                      variant="flat"
                      prepend-icon="mdi-play"
                      @click="emit('start', job)"
                    >
                      开始
                    </v-btn>
                    <v-btn size="x-small" variant="tonal" :disabled="index <= running.length" @click="moveTo(job, 'top')">置顶</v-btn>
                    <v-btn size="x-small" variant="tonal" icon="mdi-arrow-up" title="上移" @click="moveTo(job, 'up')" />
                    <v-btn size="x-small" variant="tonal" icon="mdi-arrow-down" title="下移" @click="moveTo(job, 'down')" />
                    <v-btn size="x-small" variant="tonal" icon="mdi-close" title="取消排队" @click="cancel(job)" />
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </v-card>

      <!-- 手机：卡片 -->
      <div v-else class="queue-cards">
        <div v-for="job in rows" :key="job.id" class="m-card">
          <div class="m-card-head">
            <span class="badge-state" :class="stateClass(job)">
              <i v-if="job.status === 'running'" class="badge-dot" />
              {{ statusLabel(job) }}
            </span>
            <span class="m-name" :title="job.path">{{ job.name || job.path }}</span>
            <v-chip v-if="editingId === job.id" size="x-small" color="info" variant="tonal" class="editing-tag">
              编辑中
            </v-chip>
          </div>
          <div class="m-ops-sum">{{ job.summary || '—' }}</div>
          <template v-if="job.status === 'running'">
            <v-progress-linear :model-value="progressOf(job)" height="6" rounded color="primary" class="mt-2" />
            <div class="m-card-foot">
              <span>{{ progressText(job) }}</span>
              <v-spacer />
              <v-btn size="small" variant="tonal" @click="cancel(job)">取消</v-btn>
            </div>
          </template>
          <div v-else class="m-card-foot">
            <span class="m-time">{{ fmtDateTime(job.created_at, true) }}</span>
            <v-spacer />
            <v-btn
              v-if="canEdit(job)"
              size="small"
              variant="tonal"
              prepend-icon="mdi-pencil"
              @click="emit('edit', job)"
            >
              编辑
            </v-btn>
            <v-btn
              v-if="isHeld(job)"
              size="small"
              color="primary"
              variant="flat"
              prepend-icon="mdi-play"
              @click="emit('start', job)"
            >
              开始
            </v-btn>
            <v-btn size="small" variant="tonal" @click="moveTo(job, 'top')">置顶</v-btn>
            <v-btn size="small" variant="tonal" icon="mdi-arrow-up" title="上移" @click="moveTo(job, 'up')" />
            <v-btn size="small" variant="tonal" icon="mdi-arrow-down" title="下移" @click="moveTo(job, 'down')" />
            <v-btn size="small" variant="tonal" icon="mdi-close" title="取消排队" @click="cancel(job)" />
          </div>
        </div>
      </div>

      <div class="page-tip">
        「待启动」任务只进队列、不会被调度，点行内「开始」或页头「全部开始」后才会执行。
        待启动任务、以及队列暂停时的等待任务可以「编辑」，提交后会直接更新该任务（不会新建）。
        排序用「置顶 / 上移 / 下移」，不做拖拽；正在运行的任务只能取消，不能调序。
        插件重载后等待任务自动恢复，运行中的任务会标记为中断。
      </div>
    </template>
  </div>
</template>

<style scoped>
.queue-page {
  display: flex;
  flex-direction: column;
  padding: 16px 22px;
  overflow: auto;
  min-height: 0;
  height: 100%;
}
.queue-page > * {
  flex: 0 0 auto;
}
.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.page-title {
  font-size: 15px;
  margin: 0;
  font-weight: 600;
}
.page-count {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12px;
}
.page-paused {
  color: #ffb300;
}
.page-held {
  color: #42a5f5;
}
.page-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.queue-concurrency {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.concurrency-select {
  max-width: 76px;
  min-width: 64px;
}
.page-empty {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  padding: 28px 4px;
  line-height: 1.8;
}
.page-tip {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 12px;
  line-height: 1.7;
}
.queue-table-card {
  padding: 6px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
}
.queue-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.queue-table th {
  text-align: left;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11.5px;
  padding: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  white-space: nowrap;
}
.queue-table td {
  padding: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  vertical-align: middle;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.queue-table tr:last-child td {
  border-bottom: none;
}
.queue-table tbody tr:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.col-no {
  width: 30px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  text-align: center;
}
.col-status {
  width: 108px;
}
.col-summary {
  max-width: 260px;
}
.col-progress {
  width: 190px;
}
.col-ops {
  width: 330px;
}
.name-cell {
  min-width: 180px;
  max-width: 280px;
}
.file-name {
  color: rgb(var(--v-theme-on-surface));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.editing-tag {
  margin-left: 6px;
  vertical-align: middle;
}
.file-sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.42);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-cell {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 11.5px;
  line-height: 1.5;
}
.progress-cell {
  min-width: 150px;
}
.progress-text {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  margin-top: 4px;
}
.progress-idle {
  color: rgba(var(--v-theme-on-surface), 0.35);
}
.ops-cell {
  text-align: right;
}
.row-ops {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  flex-wrap: wrap;
}
.badge-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  color: rgba(var(--v-theme-on-surface), 0.7);
  background: rgba(var(--v-theme-on-surface), 0.06);
  white-space: nowrap;
}
.badge-state--run {
  color: #ff9800;
  border-color: rgba(255, 152, 0, 0.42);
  background: rgba(255, 152, 0, 0.1);
}
.badge-state--wait {
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.badge-state--hold {
  color: #42a5f5;
  border-color: rgba(66, 165, 245, 0.42);
  background: rgba(66, 165, 245, 0.1);
}
.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ff9800;
  display: inline-block;
}
.queue-cards {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.m-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  padding: 10px 12px;
}
.m-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.m-name {
  font-size: 12.5px;
  color: rgb(var(--v-theme-on-surface));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  flex: 1;
  min-width: 0;
}
.m-ops-sum {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-top: 5px;
  line-height: 1.5;
}
.m-card-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  flex-wrap: wrap;
}
.m-time {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* medium（720~1100）：保持表格，收紧列宽与内边距，避免横向滚动 */
.queue-page--medium {
  padding: 14px 16px;
}
.queue-page--medium .queue-table th,
.queue-page--medium .queue-table td {
  padding: 6px;
}
.queue-page--medium .col-status {
  width: 86px;
}
.queue-page--medium .col-summary {
  width: 160px;
  max-width: 160px;
}
.queue-page--medium .col-progress {
  width: 136px;
}
.queue-page--medium .col-ops {
  width: 300px;
}
.queue-page--medium .name-cell {
  min-width: 130px;
  max-width: 160px;
}
.queue-page--medium .page-actions {
  gap: 6px;
}
@media (max-width: 959px) {
  .queue-page {
    padding: 12px 12px 16px;
  }
  .page-head {
    gap: 8px;
    margin-bottom: 10px;
  }
  .page-title {
    font-size: 14.5px;
  }
  .page-actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 6px;
  }
}
</style>
