<script setup>
/**
 * 历史页：结果、耗时、回滚（有备份才显示）、重新打开（回填编辑器）、删除记录
 */
import { computed, ref } from 'vue'
import { fmtDateTime, fmtDuration } from '../utils.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  keep: { type: Number, default: 200 },
  loading: { type: Boolean, default: false },
  // narrow: 卡片；medium: 紧凑表格；wide: 普通表格
  layout: { type: String, default: 'wide' },
})

const emit = defineEmits(['refresh', 'rollback', 'reopen', 'delete', 'clear'])

const narrow = computed(() => props.layout === 'narrow')
const medium = computed(() => props.layout === 'medium')

const filter = ref('all')
const filterItems = [
  { title: '全部', value: 'all' },
  { title: '成功', value: 'success' },
  { title: '失败', value: 'failed' },
  { title: '取消', value: 'cancelled' },
]

const filtered = computed(() => {
  if (filter.value === 'all') return props.items
  return props.items.filter((item) => item.status === filter.value)
})

const STATUS_MAP = {
  success: { text: '成功', cls: 'ok' },
  failed: { text: '失败', cls: 'fail' },
  cancelled: { text: '取消', cls: 'cancel' },
  interrupted: { text: '中断', cls: 'cancel' },
  running: { text: '运行中', cls: 'run' },
}

function statusOf(item) {
  const found = STATUS_MAP[item.status]
  if (found) return found
  return { text: item.status || '—', cls: 'wait' }
}

function canRollback(item) {
  // 临时备份策略：只有失败任务会保留备份，才可回滚
  return item?.status === 'failed' && Boolean(item.backup_path)
}

// 临时备份状态文案：成功后备份已删 / 未做备份 / 失败保留可回滚
function backupState(item) {
  if (item?.backup_deleted) return { text: '备份已删除（不可回滚）', cls: 'deleted' }
  if (item?.no_backup) return { text: '未做临时备份（不可回滚）', cls: 'none' }
  if (item?.status === 'failed' && item?.backup_path) return { text: '备份可回滚', cls: 'rollback' }
  return null
}

function summaryText(item) {
  return item.summary || item.error || '—'
}

// 时长偏差等告警：黄色小标记 + title 展示（预览弹窗里为黄色 warnbox）
function warningList(item) {
  return Array.isArray(item?.warnings) ? item.warnings : []
}

function warningText(item) {
  return warningList(item)
    .map((warning) => warning?.message || warning?.code || '')
    .filter(Boolean)
    .join('\n')
}

function reopen(item) {
  if (!item.path) return
  emit('reopen', item)
}

function rollback(item) {
  if (!canRollback(item)) return
  emit('rollback', item)
}
</script>

<template>
  <div class="history-page" :class="{ 'history-page--medium': medium }">
    <div class="page-head">
      <h2 class="page-title">历史</h2>
      <span class="page-count">共 {{ total || items.length }} 条 · 保留最近 {{ keep }} 条</span>
      <div class="page-actions">
        <v-select
          v-model="filter"
          :items="filterItems"
          density="compact"
          variant="outlined"
          hide-details
          class="filter-select"
        />
        <v-btn
          size="small"
          variant="text"
          color="error"
          prepend-icon="mdi-delete-sweep-outline"
          :disabled="!items.length"
          @click="emit('clear')"
        >
          清空历史
        </v-btn>
        <v-btn size="small" variant="text" icon="mdi-refresh" :loading="loading" title="刷新" @click="emit('refresh')" />
      </div>
    </div>

    <v-skeleton-loader v-if="loading && !items.length" type="list-item@4" />

    <div v-else-if="!filtered.length" class="page-empty">
      {{ items.length ? '没有符合筛选条件的记录' : '还没有处理记录。完成一次任务后会出现在这里。' }}
    </div>

    <template v-else>
      <!-- 桌面：表格 -->
      <v-card v-if="!narrow" variant="flat" class="history-table-card">
        <table class="history-table">
          <thead>
            <tr>
              <th class="col-time">时间</th>
              <th>文件</th>
              <th class="col-output">输出位置</th>
              <th class="col-summary">操作摘要</th>
              <th class="col-result">结果</th>
              <th class="col-duration">耗时</th>
              <th class="col-ops"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filtered" :key="item.id">
              <td class="col-time mono">{{ fmtDateTime(item.created_at, true) }}</td>
              <td class="name-cell">
                <div class="file-name" :title="item.path">
                  {{ item.name || item.path }}
                  <span v-if="warningList(item).length" class="warn-flag" :title="warningText(item)">⚠</span>
                </div>
                <div v-if="item.engine" class="file-sub">{{ item.engine }}</div>
              </td>
              <td class="output-cell mono" :title="item.output_path || '—'">{{ item.output_path || '—' }}</td>
              <td class="summary-cell">{{ summaryText(item) }}</td>
              <td class="col-result">
                <span class="badge-state" :class="`badge-state--${statusOf(item).cls}`">{{ statusOf(item).text }}</span>
              </td>
              <td class="col-duration">{{ fmtDuration(item.duration) }}</td>
              <td class="ops-cell">
                <div class="row-ops">
                  <span
                    v-if="backupState(item)"
                    class="backup-state"
                    :class="`backup-state--${backupState(item).cls}`"
                    :title="backupState(item).text"
                  >
                    {{ backupState(item).text }}
                  </span>
                  <v-btn v-if="canRollback(item)" size="x-small" variant="tonal" @click="rollback(item)">回滚</v-btn>
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    :title="item.plan ? '按记录里的编辑配置回填编辑器' : '该记录没有配置，只打开文件'"
                    @click="reopen(item)"
                  >
                    重新打开
                  </v-btn>
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    color="error"
                    title="删除这条历史记录（不影响备份文件）"
                    @click="emit('delete', item)"
                  >
                    删除
                  </v-btn>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </v-card>

      <!-- 手机：卡片 -->
      <div v-else class="history-cards">
        <div v-for="item in filtered" :key="item.id" class="m-card">
          <div class="m-card-head">
            <span class="badge-state" :class="`badge-state--${statusOf(item).cls}`">{{ statusOf(item).text }}</span>
            <span class="m-name" :title="item.path">{{ item.name || item.path }}</span>
            <span v-if="warningList(item).length" class="warn-flag" :title="warningText(item)">⚠</span>
          </div>
          <div class="m-ops-sum">
            {{ summaryText(item) }}
            <span
              v-if="backupState(item)"
              class="backup-state"
              :class="`backup-state--${backupState(item).cls}`"
              :title="backupState(item).text"
            >
              · {{ backupState(item).text }}
            </span>
          </div>
          <div class="m-output mono" :title="item.output_path || '—'">输出：{{ item.output_path || '—' }}</div>
          <div class="m-card-foot">
            <span>{{ fmtDateTime(item.created_at, true) }} · {{ fmtDuration(item.duration) }}</span>
            <v-spacer />
            <v-btn v-if="canRollback(item)" size="small" variant="tonal" @click="rollback(item)">回滚</v-btn>
            <v-btn
              size="small"
              variant="tonal"
              :title="item.plan ? '按记录里的编辑配置回填编辑器' : '该记录没有配置，只打开文件'"
              @click="reopen(item)"
            >
              重新打开
            </v-btn>
            <v-btn size="small" variant="tonal" color="error" @click="emit('delete', item)">删除</v-btn>
          </div>
        </div>
      </div>

      <div class="page-tip">临时备份策略：原地替换成功后会删除临时备份（不可回滚）；失败时保留备份并可回滚；未做临时备份的记录无恢复副本。「重新打开」会按记录里的配置回填轨道 / 附件 / 章节 / 输出（旧记录没有配置时只打开文件）；删除历史只移除记录，不会删除备份文件。⚠ 标记表示该记录带有时长/轨道等告警。</div>
    </template>
  </div>
</template>

<style scoped>
.history-page {
  display: flex;
  flex-direction: column;
  padding: 16px 22px;
  overflow: auto;
  min-height: 0;
  height: 100%;
}
.history-page > * {
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
.page-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
  align-items: center;
}
.filter-select {
  max-width: 120px;
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
.history-table-card {
  padding: 6px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
}
.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.history-table th {
  text-align: left;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11.5px;
  padding: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  white-space: nowrap;
}
.history-table td {
  padding: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  vertical-align: middle;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.history-table tr:last-child td {
  border-bottom: none;
}
.history-table tbody tr:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.col-time {
  width: 120px;
  white-space: nowrap;
  font-size: 11.5px;
}
.col-summary {
  max-width: 280px;
}
.col-output {
  max-width: 200px;
}
.output-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 11px;
}
.col-result {
  width: 76px;
}
.col-duration {
  width: 84px;
  font-size: 11.5px;
  white-space: nowrap;
}
.col-ops {
  width: 210px;
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
/* 告警标记：时长偏差 / 轨道数量等 */
.warn-flag {
  color: #ffb300;
  margin-left: 5px;
  font-size: 11px;
  cursor: help;
}
/* 临时备份状态（成功已删 / 未做 / 失败可回滚） */
.no-backup-tip {
  font-size: 10.5px;
  color: #ef5350;
  cursor: help;
  white-space: nowrap;
  align-self: center;
}
.backup-state {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  cursor: help;
  white-space: nowrap;
  align-self: center;
}
.backup-state--rollback {
  color: #66bb6a;
}
.backup-state--none,
.backup-state--deleted {
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.file-sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.42);
}
.summary-cell {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 11.5px;
  line-height: 1.5;
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
.badge-state--ok {
  color: #66bb6a;
  border-color: rgba(76, 175, 80, 0.36);
  background: rgba(76, 175, 80, 0.1);
}
.badge-state--fail {
  color: #ef5350;
  border-color: rgba(239, 83, 80, 0.36);
  background: rgba(239, 83, 80, 0.1);
}
.badge-state--cancel {
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.badge-state--run {
  color: #ff9800;
  border-color: rgba(255, 152, 0, 0.42);
  background: rgba(255, 152, 0, 0.1);
}
.history-cards {
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
.m-output {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* medium（720~1100）：保持表格，收紧列宽与内边距，避免横向滚动 */
.history-page--medium {
  padding: 14px 16px;
}
.history-page--medium .history-table th,
.history-page--medium .history-table td {
  padding: 6px;
}
.history-page--medium .col-time {
  width: 104px;
}
.history-page--medium .col-summary {
  width: 180px;
  max-width: 180px;
}
.history-page--medium .col-result {
  width: 60px;
}
.history-page--medium .col-duration {
  width: 70px;
}
.history-page--medium .col-ops {
  width: 200px;
}
.history-page--medium .name-cell {
  min-width: 140px;
  max-width: 190px;
}
@media (max-width: 959px) {
  .history-page {
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
    margin-left: 0;
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
