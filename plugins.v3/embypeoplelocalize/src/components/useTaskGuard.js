/**
 * 统一「任务进行中禁止修改数据」守卫（v4.6.70 · 审查报告第四 / 十五节 TaskGuard）。
 *
 * 目的：把「编辑 / 保存 / 重新翻译 / 全部翻译 / 全部写回 / 单条写回 / 删除 / 导入 / 清库 /
 * 人名池清空·重筛·同步 / 重扫」等**修改型操作**统一挂在同一把锁上，避免与后台的
 * 扫描 / AI 翻译 / 写回 / 人名池任务 / 探测库并发读写同一批数据而互相覆盖。
 *
 * 用法（任意视图）：
 *   import { useTaskGuard } from '../components/useTaskGuard.js'
 *   const guard = useTaskGuard()
 *   guard.loadStatus(st)                      // 每次拿到 /status 后同步
 *   function doSomething() {
 *     if (!guard.check('重新翻译')) return     // 锁定 → 弹统一拦截弹窗并返回 false
 *     ...
 *   }
 * 模板：
 *   <TaskGuardDlg v-model="guard.dlg.value" :reason="guard.reason.value"
 *                 :action="guard.pendingLabel.value" @view-task="..." />
 *   <v-btn :disabled="guard.lock.value" ...>重新翻译</v-btn>
 */
import { computed, ref } from 'vue'

const KIND_ORDER = ['scan', 'translate', 'writeback', 'pool', 'probe']
const KIND_LABEL = {
  scan: 'NFO 扫描',
  translate: 'AI 翻译',
  writeback: '写回 NFO',
  pool: '人名池任务',
  probe: '探测库',
}
// v4.6.73：统一任务状态机（报告第十五节）→ 中文状态名
const STATE_LABEL = {
  IDLE: '空闲',
  SCANNING: 'NFO 扫描中',
  PROBING: '探测库中',
  TRANSLATING: 'AI 翻译中',
  WRITING: '写回 NFO 中',
  POOL_FETCHING: '拉取人名中',
  POOL_SYNCING: '人名池同步中',
  STOPPING: '正在停止',
}

export function useTaskGuard() {
  const kinds = ref({ scan: false, translate: false, writeback: false, pool: false, probe: false })
  const isRunning = ref(false)     // 宿主任务状态机（_is_running）
  const txRequested = ref(false)   // 常驻翻译 worker 的消费许可（不置 _is_running，需单独看）
  const state = ref('IDLE')        // 统一任务状态机（后端 task_state.state）
  const dataLocked = ref(false)    // 后端 task_state.data_mutation_locked
  const dlg = ref(false)
  const pendingLabel = ref('')

  const activeKinds = computed(() => {
    const out = []
    for (const k of KIND_ORDER) {
      if (kinds.value && kinds.value[k]) out.push(KIND_LABEL[k])
    }
    // 兜底：任务状态机说在跑、或常驻翻译 worker 持有许可，但 kinds 未覆盖 → 至少标「AI 翻译」
    if (!out.length && (isRunning.value || txRequested.value)) out.push(KIND_LABEL.translate)
    return out
  })
  const stateLabel = computed(() => STATE_LABEL[state.value] || state.value || '空闲')
  const lock = computed(() => dataLocked.value || activeKinds.value.length > 0)
  const reason = computed(() => {
    const r = activeKinds.value.join(' / ')
    if (r) return r
    return dataLocked.value ? stateLabel.value : ''
  })
  const hint = computed(() => (lock.value
    ? `任务正在执行（${reason.value}）：为避免翻译结果 / 写回内容 / 人工修改互相覆盖，修改型操作已锁定`
    : ''))

  function loadStatus(st) {
    const ts = (st && st.task_state) || null
    if (ts) {
      state.value = ts.state || 'IDLE'
      dataLocked.value = !!ts.data_mutation_locked
      const tt = ts.tasks || {}
      kinds.value = {
        scan: !!tt.scan, translate: !!tt.translate, writeback: !!tt.writeback,
        pool: !!tt.pool, probe: !!tt.probe,
      }
    } else {
      const t = (st && st.tasks) || {}
      kinds.value = {
        scan: !!t.scan, translate: !!t.translate, writeback: !!t.writeback,
        pool: !!t.pool, probe: !!t.probe,
      }
      dataLocked.value = false
      state.value = 'IDLE'
    }
    isRunning.value = !!(st && st.is_running)
    txRequested.value = !!(
      (st && st.tx && (st.tx.requested || st.tx.running))
      || (st && st.translate_status && st.translate_status.running)
    )
  }

  /** 修改型操作入口守卫：锁定 → 记录操作名、弹统一弹窗、返回 false；未锁定 → true。 */
  function check(label = '') {
    if (!lock.value) return true
    pendingLabel.value = label
    dlg.value = true
    return false
  }

  return { kinds, isRunning, txRequested, state, stateLabel, dataLocked,
           dlg, pendingLabel, lock, reason, hint, loadStatus, check }
}
