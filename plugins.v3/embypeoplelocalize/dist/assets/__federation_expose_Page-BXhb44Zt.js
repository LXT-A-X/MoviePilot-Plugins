import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { a as api } from './client-Dg9zA7Bo.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {toDisplayString:_toDisplayString$6,createTextVNode:_createTextVNode$6,resolveComponent:_resolveComponent$6,withCtx:_withCtx$6,createVNode:_createVNode$6,openBlock:_openBlock$6,createElementBlock:_createElementBlock$6,createCommentVNode:_createCommentVNode$6,normalizeClass:_normalizeClass$4,createBlock:_createBlock$6} = await importShared('vue');


const _hoisted_1$6 = {
  key: 0,
  class: "cfm-text"
};


const _sfc_main$6 = {
  __name: 'ConfirmDlg',
  props: {
  state: { type: Object, required: true },
  onOk: { type: Function, required: true },
  onCancel: { type: Function, required: true },
},
  setup(__props) {



return (_ctx, _cache) => {
  const _component_v_card_title = _resolveComponent$6("v-card-title");
  const _component_v_card_text = _resolveComponent$6("v-card-text");
  const _component_v_spacer = _resolveComponent$6("v-spacer");
  const _component_v_btn = _resolveComponent$6("v-btn");
  const _component_v_card_actions = _resolveComponent$6("v-card-actions");
  const _component_v_card = _resolveComponent$6("v-card");
  const _component_v_dialog = _resolveComponent$6("v-dialog");

  return (_openBlock$6(), _createBlock$6(_component_v_dialog, {
    "model-value": !!__props.state.open,
    "max-width": "460",
    "onUpdate:modelValue": _cache[0] || (_cache[0] = (v) => { if (!v) __props.onCancel(); })
  }, {
    default: _withCtx$6(() => [
      _createVNode$6(_component_v_card, null, {
        default: _withCtx$6(() => [
          _createVNode$6(_component_v_card_title, null, {
            default: _withCtx$6(() => [
              _createTextVNode$6(_toDisplayString$6(__props.state.title || '请确认'), 1)
            ]),
            _: 1
          }),
          _createVNode$6(_component_v_card_text, null, {
            default: _withCtx$6(() => [
              (__props.state.text)
                ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_1$6, _toDisplayString$6(__props.state.text), 1))
                : _createCommentVNode$6("", true),
              (__props.state.detail)
                ? (_openBlock$6(), _createElementBlock$6("div", {
                    key: 1,
                    class: _normalizeClass$4(["cfm-detail", { 'is-danger': __props.state.color === 'error' }])
                  }, _toDisplayString$6(__props.state.detail), 3))
                : _createCommentVNode$6("", true)
            ]),
            _: 1
          }),
          _createVNode$6(_component_v_card_actions, null, {
            default: _withCtx$6(() => [
              _createVNode$6(_component_v_spacer),
              _createVNode$6(_component_v_btn, {
                variant: "text",
                onClick: __props.onCancel
              }, {
                default: _withCtx$6(() => [...(_cache[1] || (_cache[1] = [
                  _createTextVNode$6("取消", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"]),
              _createVNode$6(_component_v_btn, {
                variant: "flat",
                color: __props.state.color || 'warning',
                onClick: __props.onOk
              }, {
                default: _withCtx$6(() => [
                  _createTextVNode$6(_toDisplayString$6(__props.state.okText || '确认'), 1)
                ]),
                _: 1
              }, 8, ["color", "onClick"])
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};
const ConfirmDlg = /*#__PURE__*/_export_sfc(_sfc_main$6, [['__scopeId',"data-v-c47cfce7"]]);

const {reactive} = await importShared('vue');


function useConfirm() {
  const cState = reactive({
    open: false, title: '', text: '', detail: '',
    okText: '确认', color: 'warning', _resolve: null,
  });

  function askConfirm(opts = {}) {
    return new Promise((resolve) => {
      cState.open = true;
      cState.title = opts.title || '请确认';
      cState.text = opts.text || '';
      cState.detail = opts.detail || '';
      cState.okText = opts.okText || '确认';
      cState.color = opts.color || 'warning';
      cState._resolve = resolve;
    })
  }

  function _finish(v) {
    cState.open = false;
    const r = cState._resolve;
    cState._resolve = null;
    if (r) r(v);
  }

  return { cState, askConfirm, cOk: () => _finish(true), cCancel: () => _finish(false) }
}

const {normalizeClass:_normalizeClass$3,createElementVNode:_createElementVNode$5,toDisplayString:_toDisplayString$5,createTextVNode:_createTextVNode$5,resolveComponent:_resolveComponent$5,withCtx:_withCtx$5,createVNode:_createVNode$5,openBlock:_openBlock$5,createElementBlock:_createElementBlock$5,createCommentVNode:_createCommentVNode$5,Fragment:_Fragment$4,createBlock:_createBlock$5,renderList:_renderList$4,mergeProps:_mergeProps$2,unref:_unref$2} = await importShared('vue');


const _hoisted_1$5 = { class: "epl-view" };
const _hoisted_2$5 = { class: "epl-st" };
const _hoisted_3$5 = { class: "epl-st" };
const _hoisted_4$4 = { class: "epl-st" };
const _hoisted_5$4 = {
  key: 0,
  class: "epl-st-sub text-error"
};
const _hoisted_6$4 = {
  key: 1,
  class: "epl-st-sub"
};
const _hoisted_7$4 = { class: "epl-st" };
const _hoisted_8$4 = { class: "epl-st" };
const _hoisted_9$4 = {
  key: 0,
  class: "epl-st-sub"
};
const _hoisted_10$4 = {
  key: 1,
  class: "epl-st-sub"
};
const _hoisted_11$3 = {
  key: 2,
  class: "epl-st-sub"
};
const _hoisted_12$3 = {
  key: 0,
  class: "epl-st-progress"
};
const _hoisted_13$3 = {
  key: 1,
  class: "epl-st-progress"
};
const _hoisted_14$3 = {
  key: 2,
  class: "epl-st-progress"
};
const _hoisted_15$3 = {
  class: "d-flex align-center flex-wrap ga-2",
  style: {"font-size":"13px"}
};
const _hoisted_16$3 = { key: 0 };
const _hoisted_17$3 = {
  key: 0,
  class: "epl-empty pa-4"
};
const _hoisted_18$3 = { class: "text-body-2 font-weight-medium mr-2" };
const _hoisted_19$3 = { class: "epl-stage-name" };
const _hoisted_20$3 = { class: "epl-stage-num" };
const _hoisted_21$3 = {
  key: 1,
  class: "epl-stage-idle"
};
const _hoisted_22$3 = { class: "epl-stat-value text-primary" };
const _hoisted_23$3 = { class: "epl-stat-value text-info" };
const _hoisted_24$3 = { class: "epl-stat-value text-success" };
const _hoisted_25$3 = { class: "epl-stat-sub" };
const _hoisted_26$3 = { class: "epl-stat-value text-warning" };
const _hoisted_27$3 = { class: "epl-wh-scroll epl-failed-scroll" };
const _hoisted_28$3 = {
  key: 0,
  class: "epl-empty"
};
const _hoisted_29$3 = { class: "epl-log-time" };
const _hoisted_30$3 = { class: "epl-log-msg" };
const _hoisted_31$3 = {
  class: "d-flex align-center flex-wrap ga-2",
  style: {"font-size":"13px"}
};
const _hoisted_32$3 = { class: "epl-wh-col-title" };
const _hoisted_33$3 = { class: "epl-wh-scroll" };
const _hoisted_34$3 = {
  key: 0,
  class: "epl-empty pa-4"
};
const _hoisted_35$3 = { class: "epl-log-time" };
const _hoisted_36$3 = ["title"];
const _hoisted_37$3 = {
  class: "text-caption",
  style: {"opacity":".7"}
};
const _hoisted_38$3 = { class: "epl-log-msg" };
const _hoisted_39$3 = { class: "epl-wh-col-title" };
const _hoisted_40$3 = { class: "epl-wh-scroll" };
const _hoisted_41$3 = {
  key: 0,
  class: "epl-empty pa-4"
};

const {computed: computed$5,inject: inject$4,onActivated: onActivated$3,onDeactivated: onDeactivated$2,onMounted: onMounted$4,onUnmounted,ref: ref$5,watch: watch$3} = await importShared('vue');


const _sfc_main$5 = {
  __name: 'DashboardView',
  props: {
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
},
  emits: ['action', 'notify'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject$4('moviepilot:toast', null);
const { cState, askConfirm, cOk, cCancel } = useConfirm();

const loading = ref$5(true);
const status = ref$5(null);
const dbStats = ref$5(null);
const logs = ref$5([]);
const webhookEvents = ref$5([]);
const busy = ref$5('');

const deps = ref$5({ items: [], ok_count: 0, total: 0 });
const depsDialog = ref$5(false);
const depsLoading = ref$5(false);

function notify(msg, type = 'error') {
  let handled = false;
  try { if (toast && typeof toast[type] === 'function') { toast[type](msg); handled = true; } } catch (e) {}
  if (!handled) { try { emit('notify', msg, type); } catch (e) {} }
}

function scanStatus() { return status.value?.scan_status || {} }

function fmtTime(ts) {
  if (!ts) return ''
  try {
    const t = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    const p = n => String(n).padStart(2, '0');
    return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())} ${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())}`
  } catch (e) { return '' }
}

async function loadDeps() {
  depsLoading.value = true;
  try {
    const data = await api.get(props.api, '/deps/check');
    deps.value = data?.items ? data : { items: [], ok_count: 0, total: 0 };
  } catch (e) { deps.value = { items: [], ok_count: 0, total: 0 }; }
  depsLoading.value = false;
}

let loadAllBusy = false;
// v4.6.66（P1 仪表盘刷新）：单请求超时保护 —— 任一接口悬挂时 Promise.allSettled 永不返回，
// loadAllBusy 会永久锁死轮询（表现为「开关改了提示不消失，必须进出插件」）。
function withTimeout(p, ms = 15000) {
  return Promise.race([
    p,
    new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)),
  ])
}
async function loadAll() {
  // 轮询锁（UI-002）：上一轮未完成时不叠加新一轮；接口并行取（不再串行 5 个 await）
  if (loadAllBusy) return
  loadAllBusy = true;
  try {
    const [st, db, lg, wh, pd] = await Promise.allSettled([
      withTimeout(api.get(props.api, '/status')),
      withTimeout(api.get(props.api, '/db/stats')),
      withTimeout(api.get(props.api, '/live_log', { limit: 50 })),
      withTimeout(api.get(props.api, '/webhook_events', { limit: 50 })),
      withTimeout(api.get(props.api, '/webhook/pending')),
    ]);
    if (st.status === 'fulfilled' && st.value) status.value = st.value;
    if (db.status === 'fulfilled' && db.value) dbStats.value = db.value;
    if (lg.status === 'fulfilled' && Array.isArray(lg.value)) logs.value = lg.value;
    if (wh.status === 'fulfilled' && Array.isArray(wh.value)) webhookEvents.value = wh.value;
    if (pd.status === 'fulfilled' && pd.value) pendingInfo.value = pd.value;
    loading.value = false;
  } finally {
    loadAllBusy = false;
  }
}

const pendingInfo = ref$5({ count: 0, items: [] });
const pendingBusy = ref$5(false);
const pendingCount = () => pendingInfo.value?.count ?? 0;
async function pendingContinue() {
  if (pendingBusy.value) return
  pendingBusy.value = true;
  try {
    const r = await api.post(props.api, '/webhook/pending_continue');
    notify(r?.message || '已处理', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '操作失败', 'error'); } finally { pendingBusy.value = false; }
}
const pendingClearBusy = ref$5(false);
async function pendingClear() {
  if (pendingClearBusy.value) return
  if (!await askConfirm({
    title: '放弃全部待配置事件',
    text: `确认放弃全部 ${pendingCount()} 个待配置（挂起）事件？`,
    detail: '放弃后这些事件不再自动处理（如需重新处理，再次入库触发即可）。',
    okText: '放弃',
    color: 'warning',
  })) return
  pendingClearBusy.value = true;
  try {
    const r = await api.post(props.api, '/webhook/pending_clear');
    notify(r?.message || '已放弃', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '放弃失败', 'error'); } finally { pendingClearBusy.value = false; }
}

async function clearLogs() {
  if (!await askConfirm({
    title: '清空运行日志',
    text: '确认清空插件日志缓冲？',
    detail: '仅清空插件的日志显示（不影响已写回的 nfo 与翻译记录）；清空后无法恢复。',
    okText: '清空',
    color: 'warning',
  })) return
  try {
    const r = await api.post(props.api, '/clear_logs');
    notify(r?.message || '日志已清空', 'success');
    logs.value = [];
  } catch (e) { notify((e && e.message) || '清空失败', 'error'); }
}

async function clearWhEvents() {
  if (busy.value === 'wh_clear') return
  if (!await askConfirm({
    title: '清空 Webhook 入库事件',
    text: '确认清空全部 Webhook 入库事件记录？',
    detail: '事件列表用于查看入库/失败/「失效·待恢复」状态；清空后这些条目不再显示（翻译记录与已入库内容不受影响，需复查可重新触发入库）。',
    okText: '清空',
    color: 'error',
  })) return
  busy.value = 'wh_clear';
  try {
    const r = await api.post(props.api, '/webhook_events/clear');
    notify(r?.message || 'Webhook 入库事件已清空', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '清空失败', 'error'); }
  finally { busy.value = ''; }
}

async function runOp(action, successMsg) {
  if (busy.value) return
  busy.value = action;
  try {
    const r = await api.post(props.api, '/' + action);
    notify(r?.message || successMsg, 'success');
    emit('action');
    await loadAll();
  } catch (e) {
    notify((e && e.message) || '操作失败', 'error');
  } finally {
    // 不用固定 30 秒计时器假装任务结束（UI-001）：busy 只覆盖「启动请求」本身，
    // 任务是否在跑由 /status 的 is_running + tasks 驱动按钮禁用态。
    busy.value = '';
    await loadAll();
  }
}

async function stopAll() {
  if (busy.value) return
  if (!await askConfirm({
    title: '终止当前任务',
    text: '终止后将立即中断正在运行的扫描 / 拉取人名 / AI 翻译 / 写回任务；已处理的进度与断点保留，之后可点「续跑」或重新发起。',
    detail: 'AI 翻译会立即停止（不再发起新请求）；已翻译入库的内容不受影响。',
    okText: '终止',
    color: 'error',
  })) return
  await runOp('stop', '已请求终止（断点已保存，完成后点「续跑」继续）');
}

async function pauseTasks() {
  try {
    const r = await api.post(props.api, '/task/pause', { target: 'all' });
    notify(r?.message || '已暂停', 'info');
    await loadAll();
  } catch (e) { notify((e && e.message) || '暂停失败', 'error'); }
}
async function resumeTasks() {
  try {
    const r = await api.post(props.api, '/task/resume', { target: 'all' });
    notify(r?.message || '已继续', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '继续失败', 'error'); }
}

const running = () => !!status.value?.is_running;
const mainActionLabel = () => 'NFO 扫描';
const mainActionHint = () => '扫描已勾选媒体库目录下的本地 nfo 文件：采集入库 → 翻译 → 写回文件（有断点则跳过已处理继续扫，否则全量）。只管本地文件，不查 Emby 清单——查 Emby 用「探测库」';
const pluginEnabled = () => (status.value ? !!status.value.enabled : props.enabled !== false);
const whStatusColor = (s) => ({ done: 'success', failed: 'error', skipped: 'warning', waiting: 'info', missing: 'warning', ambiguous: 'warning', running: 'info', received: 'default' })[s] || 'default';
const whStatusLabel = (s) => ({ done: '完成', failed: '失败', skipped: '跳过', waiting: '待配置', missing: '待恢复', ambiguous: '需确认', running: '处理中', received: '已接收' })[s] || s;

const normalEvents = computed$5(() => webhookEvents.value.filter(e => e.status !== 'missing'));
const missingEvents = computed$5(() => webhookEvents.value.filter(e => e.status === 'missing'));
const fmtGraceDate = (s) => { try { const m = /(\d{2}-\d{2} \d{2}:\d{2}) 到期/.exec(String(s || '')); return m ? m[1] : '' } catch (e) { return '' } };

const purgeMissingBusy = ref$5(false);
async function purgeMissing() {
  if (purgeMissingBusy.value || !missingEvents.value.length) return
  if (!await askConfirm({
    title: '立即清除全部失效记录',
    text: `确认立即清除全部失效记录（${missingEvents.value.length} 条）？这些条目的翻译记录将被删除（人名池保留），不再等待观察期。`,
    detail: '注意：若条目正在重新下载/洗版，清除后重新入库会当作全新条目重新翻译（重复消耗 AI 额度）。',
    okText: '清除',
    color: 'error',
  })) return
  purgeMissingBusy.value = true;
  try {
    const r = await api.post(props.api, '/db/purge_missing');
    notify(r?.message || '已清除', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '清除失败', 'error'); } finally { purgeMissingBusy.value = false; }
}

const translateAllBusy = ref$5(false);
const nfoResume = computed$5(() => status.value?.nfo_resume || { ok: false, done: 0 });
const canResume = computed$5(() => !!nfoResume.value?.ok);
const translateAllHint = () => {
  if (!canResume.value) return '没有可续跑的断点（上轮已正常跑完，或配置变更使断点作废）—— 需要全量处理请点「NFO 扫描」；扫描中途点「终止」后，这里就能续跑'
  const p = !!status.value?.nfo_preview;
  const n = nfoResume.value?.done || 0;
  return p
    ? `继续上次未完成的扫描（已处理 ${n} 个文件）：预览模式已开，只翻译写入库，不写文件；确认后去「库」页点「全部写回」落盘`
    : `继续上次未完成的扫描（已处理 ${n} 个文件）：跳过已处理的，翻译并写回文件`
};
async function runTranslateAll() {
  if (busy.value || translateAllBusy.value) return
  translateAllBusy.value = true;
  try {
    const r = await api.post(props.api, '/translate_all');
    notify(r?.message || '续跑已启动', r?.success === false ? 'error' : 'success');
    emit('action');
    await loadAll();
  } catch (e) { notify((e && e.message) || '启动失败', 'error'); } finally { translateAllBusy.value = false; }
}

const probeBusy = ref$5(false);
async function runProbeNow() {
  if (probeBusy.value) return
  probeBusy.value = true;
  try {
    const r = await api.post(props.api, '/probe/run');
    notify(r?.message || '探测已启动', r?.success === false ? 'error' : 'success');
    emit('action');
    await loadAll();
  } catch (e) { notify((e && e.message) || '探测启动失败', 'error'); } finally { probeBusy.value = false; }
}

// 顶部状态灯：按真实任务逐项显示，不再把任何任务都写成「扫描中」（UI-003）
const TASK_LABELS = { scan: '扫描中', translate: '翻译中', writeback: '写回中', pool: '拉取人名中', probe: '探测库中' };
const activeTasks = computed$5(() => {
  const t = status.value?.tasks || {};
  return Object.keys(TASK_LABELS).filter(k => !!t[k])
});
const svc = computed$5(() => {
  const keys = activeTasks.value;
  if (!keys.length) return { txt: '空闲', cls: 'idle' }
  return { txt: keys.map(k => TASK_LABELS[k]).join(' + '), cls: 'ok' }
});
const dbOk = computed$5(() => {
  const d = status.value?.deps;
  return d?.db_ready !== undefined ? !!d.db_ready : dbStats.value !== null
});
const depOk = computed$5(() => deps.value.total > 0 && deps.value.ok_count === deps.value.total);
const whOk = computed$5(() => {
  const w = status.value?.webhook;
  if (!w) return false
  return !w.last_error
});
const whEnabled = computed$5(() => !!status.value?.webhook?.enabled);
const whPending = computed$5(() => Number(status.value?.webhook?.pending_count || 0));
const whHeld = computed$5(() => {
  const w = status.value?.webhook;
  if (!w) return 0
  return Number(w.held_count ?? (Number(w.pending_count || 0) + Number(w.scheduled_count || 0)))
});

const LLM_ERR_LABEL = {
  rate_limited: '限速',
  quota_exceeded: '配额不足',
  authentication_failed: '认证失败',
  context_length_exceeded: '上下文过长',
  server_error: '服务异常',
  network_error: '网络异常',
  empty_response: '空响应'
};
const llmGate = computed$5(() => status.value?.llm_gate || {});
const llmLimitedLeft = computed$5(() => {
  const _until = Number(llmGate.value.limited_until || 0);
  return _until > Date.now() / 1000 ? Math.ceil(_until - Date.now() / 1000) : 0
});
const llmTxt = computed$5(() => {
  if (llmLimitedLeft.value > 0) return `限速 ${llmLimitedLeft.value}s`
  const k = String(llmGate.value.error_kind || '');
  return LLM_ERR_LABEL[k] || '正常'
});
const llmCls = computed$5(() => {
  if (llmLimitedLeft.value > 0) return 'warn'
  const k = String(llmGate.value.error_kind || '');
  if (!k) return 'ok'
  // 可自愈/短暂类 → 警告色；需人工介入类 → 错误色
  if (['rate_limited', 'server_error', 'network_error', 'empty_response'].includes(k)) return 'warn'
  return 'bad'
});

const tx = computed$5(() => status.value?.tx || {});
const txOnline = computed$5(() => !!tx.value.online);
const txPaused = computed$5(() => String(tx.value.paused || ''));
const txUserPaused = computed$5(() => !!tx.value.user_paused);
const anyTaskPaused = computed$5(() => txUserPaused.value
  || !!scanStatus()?.paused || !!status.value?.pool_status?.paused);
const txState = computed$5(() => {
  if (!txOnline.value) return '离线'
  if (tx.value.user_paused) return '已暂停（手动）'
  if (txPaused.value === 'rate_limited') return '限流暂停'
  if (txPaused.value === 'authentication_failed') return '认证暂停'
  if (txPaused.value === 'quota_exceeded') return '配额暂停'
  return tx.value.requested ? '正在翻译' : '待命'
});
const txTxt = computed$5(() => (txOnline.value ? `在线 · ${txState.value}` : '离线'));
const txCls = computed$5(() => {
  if (!txOnline.value) return 'bad'
  if (['authentication_failed', 'quota_exceeded'].includes(txPaused.value)) return 'bad'
  if (txPaused.value === 'rate_limited') return 'warn'
  if (tx.value.user_paused) return 'warn'
  return tx.value.requested ? 'warn' : 'ok'
});
const txPauseLeft = computed$5(() => Number(tx.value.pause_left || 0));
const txPending = computed$5(() => Number(tx.value.pending || 0));
const txScope = computed$5(() => String(tx.value.scope || ''));
const txProgress = computed$5(() => {
  const tr = status.value?.translate_status || {};
  if (!tr.running) return ''
  const t = Number(tr.total || 0), dn = Number(tr.done || 0);
  return `${dn} / ${t || '…'}`
});

const stageRows = computed$5(() => {
  const out = [];
  const sc = scanStatus();
  const scanRunning = sc.tasks ? !!sc.tasks.scan : !!sc.running;
  if (scanRunning) {
    out.push({ key: 'scan', name: 'NFO 扫描', color: 'primary', percent: Number(sc.percent || 0),
               text: `${sc.done || 0} / ${sc.total || 0}${sc.current_title ? ' · ' + sc.current_title : ''}` });
  }
  const pf = status.value?.pool_status || {};
  if (pf.running) {
    const pt = Number(pf.total || 0), pdn = Number(pf.done || 0);
    out.push({ key: 'pool', name: '拉取人名', color: 'info', percent: pt ? Math.min(100, Math.round(pdn / pt * 100)) : 0,
               text: `${pdn} / ${pt || '…'}${pf.current ? ' · ' + pf.current : ''}` });
  }
  const tr = status.value?.translate_status || {};
  if (tr.running) {
    const t = Number(tr.total || 0), dn = Number(tr.done || 0);
    out.push({ key: 'translate', name: 'AI 翻译', color: 'deep-purple', percent: t ? Math.min(100, Math.round(dn / t * 100)) : 0,
               text: `${dn} / ${t || '…'}${tr.current ? ' · ' + tr.current : ''}` });
  }
  const wb = status.value?.writeback_status || {};
  if (wb.running) {
    const t = Number(wb.total || 0), dn = Number(wb.done || 0);
    out.push({ key: 'writeback', name: 'NFO 写回', color: 'teal', percent: t ? Math.min(100, Math.round(dn / t * 100)) : 0,
               text: `${dn} / ${t || '…'}${wb.current ? ' · ' + wb.current : ''}` });
  }
  return out
});

const poolCounts = computed$5(() => status.value?.pool_counts || {});
const poolFetchState = computed$5(() => status.value?.pool_status || {});
// 探测库独立状态（UI-004）：不再从 scan_status 借用，避免被显示为「扫描中」
const probeStatus = computed$5(() => status.value?.probe_status || {});
const poolTaskRunning = computed$5(() => !!(status.value?.tasks?.pool || poolFetchState.value.running));
const translateRunning = computed$5(() => !!(status.value?.tasks?.translate || status.value?.translate_status?.running));
const poolFetchDisabled = computed$5(() => poolTaskRunning.value || translateRunning.value || !pluginEnabled());
const poolFetchHint = computed$5(() => {
  if (!pluginEnabled()) return '插件未启用：请先在设置页打开「启用插件」'
  if (translateRunning.value) return 'AI 翻译进行中，暂不可拉取人名（翻译与拉取互斥），等翻译完成后再试'
  if (poolTaskRunning.value) return '人名池任务（拉取/同步）进行中，完成后可用'
  return ''
});
const dataOpBlocked = computed$5(() => !pluginEnabled() || running() || translateRunning.value);
const dataOpBlockedHint = computed$5(() => {
  if (!pluginEnabled()) return '插件未启用：请先在设置页打开「启用插件」'
  if (translateRunning.value || running()) return '任务正在运行中，请先「终止」或等待完成后再操作'
  return ''
});
const poolFetchBusy = ref$5(false);
function poolFetchLabel() {
  const st = poolFetchState.value;
  if (st.running) return `拉取中 ${st.done || 0}/${st.total || '…'}`
  return '拉取人名'
}
async function startPoolFetch() {
  if (poolFetchBusy.value || poolFetchState.value.running) return
  poolFetchBusy.value = true;
  try {
    const r = await api.post(props.api, '/pool/fetch', {});
    notify(r?.message || '拉取人名已启动', r?.success === false ? 'error' : 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '拉取启动失败', 'error'); } finally { poolFetchBusy.value = false; }
}

const failedTerms = computed$5(() => status.value?.failed_translations?.terms || []);
const failedDetail = (t) => status.value?.failed_translations?.detail?.[t] || '翻译失败';
const failedBusy = ref$5('');
async function retryFailed() {
  if (failedBusy.value) return
  failedBusy.value = 'retry';
  try {
    const r = await api.post(props.api, '/translate/retry_failed');
    notify(r?.message || '重试已启动', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '重试失败', 'error'); } finally { failedBusy.value = ''; }
}
async function clearFailed() {
  if (failedBusy.value) return
  if (!await askConfirm({
    title: '清空失败清单',
    text: `确认清空失败清单（${failedTerms.value.length} 个词条）？`,
    detail: '清空后这些词条不再出现在「翻译失败词条」里，不会自动重试（下次扫描会重新尝试翻译）。',
    okText: '清空',
    color: 'error',
  })) return
  failedBusy.value = 'clear';
  try {
    const r = await api.post(props.api, '/translate/clear_failed');
    notify(r?.message || '已清空', 'success');
    await loadAll();
  } catch (e) { notify((e && e.message) || '清空失败', 'error'); } finally { failedBusy.value = ''; }
}

let pollTimer = null;
function startPoll() {
  if (pollTimer) return
  // 递归定时（UI-002）：上一轮 loadAll 完成后才安排下一轮，慢接口不会造成请求堆积
  const tick = async () => {
    await loadAll();
    if (pollTimer) pollTimer = setTimeout(tick, 5000);
  };
  pollTimer = setTimeout(tick, 0);
}
function stopPoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
}
// v4.6.66（P1 仪表盘刷新）：页面重新激活 / 切页操作（refreshKey 递增）/ 窗口回到前台
// 时立即强制刷新一次，并解除上一轮遗留的轮询锁 —— 修复「Webhook 开关改了、仪表盘提示
// 必须进出插件才消失」。
function forceRefresh() {
  loadAllBusy = false;
  loadAll();
}
watch$3(() => props.refreshKey, () => forceRefresh());
function onWindowVisible() {
  if (typeof document === 'undefined' || document.visibilityState === 'visible') forceRefresh();
}
onMounted$4(() => {
  loadDeps();
  startPoll();
  try {
    document.addEventListener('visibilitychange', onWindowVisible);
    window.addEventListener('focus', onWindowVisible);
  } catch (e) { /* 非浏览器环境忽略 */ }
});
onActivated$3(() => { forceRefresh(); startPoll(); });
onDeactivated$2(stopPoll);
onUnmounted(() => {
  stopPoll();
  try {
    document.removeEventListener('visibilitychange', onWindowVisible);
    window.removeEventListener('focus', onWindowVisible);
  } catch (e) { /* ignore */ }
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$5("v-icon");
  const _component_v_card_text = _resolveComponent$5("v-card-text");
  const _component_v_card = _resolveComponent$5("v-card");
  const _component_v_btn = _resolveComponent$5("v-btn");
  const _component_v_alert = _resolveComponent$5("v-alert");
  const _component_v_spacer = _resolveComponent$5("v-spacer");
  const _component_v_card_title = _resolveComponent$5("v-card-title");
  const _component_v_chip = _resolveComponent$5("v-chip");
  const _component_v_list_item_title = _resolveComponent$5("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$5("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$5("v-list-item");
  const _component_v_list = _resolveComponent$5("v-list");
  const _component_v_dialog = _resolveComponent$5("v-dialog");
  const _component_v_tooltip = _resolveComponent$5("v-tooltip");
  const _component_v_progress_circular = _resolveComponent$5("v-progress-circular");
  const _component_v_progress_linear = _resolveComponent$5("v-progress-linear");
  const _component_v_col = _resolveComponent$5("v-col");
  const _component_v_row = _resolveComponent$5("v-row");
  const _component_v_table = _resolveComponent$5("v-table");
  const _component_v_divider = _resolveComponent$5("v-divider");

  return (_openBlock$5(), _createElementBlock$5("div", _hoisted_1$5, [
    _createVNode$5(_component_v_card, {
      variant: "tonal",
      class: "mb-4 epl-statusbar"
    }, {
      default: _withCtx$5(() => [
        _createVNode$5(_component_v_card_text, { class: "py-2 epl-statusrow" }, {
          default: _withCtx$5(() => [
            _createElementVNode$5("div", _hoisted_2$5, [
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-dot", svc.value.cls])
              }, null, 2),
              _cache[3] || (_cache[3] = _createElementVNode$5("span", { class: "epl-st-name" }, "服务", -1)),
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-st-val", svc.value.cls])
              }, _toDisplayString$5(svc.value.txt), 3)
            ]),
            _createElementVNode$5("div", _hoisted_3$5, [
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-dot", dbOk.value ? 'ok' : 'bad'])
              }, null, 2),
              _cache[4] || (_cache[4] = _createElementVNode$5("span", { class: "epl-st-name" }, "数据库", -1)),
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-st-val", dbOk.value ? 'ok' : 'bad'])
              }, _toDisplayString$5(dbOk.value ? '正常' : '异常'), 3)
            ]),
            _createElementVNode$5("div", {
              class: _normalizeClass$3(["epl-st epl-st-deps", depOk.value ? '' : 'text-error']),
              onClick: _cache[0] || (_cache[0] = $event => (depsDialog.value = true))
            }, [
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-dot", depOk.value ? 'ok' : 'bad'])
              }, null, 2),
              _cache[5] || (_cache[5] = _createElementVNode$5("span", { class: "epl-st-name" }, "依赖", -1)),
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-st-val", depOk.value ? 'ok' : 'bad'])
              }, _toDisplayString$5(depsLoading.value ? '检测中…' : (depOk.value ? '正常' : '异常')), 3),
              _createVNode$5(_component_v_icon, { size: "14" }, {
                default: _withCtx$5(() => [
                  _createTextVNode$5(_toDisplayString$5(depsLoading.value ? 'mdi-loading mdi-spin' : 'mdi-dots-horizontal'), 1)
                ]),
                _: 1
              })
            ], 2),
            _createElementVNode$5("div", _hoisted_4$4, [
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-dot", !whEnabled.value ? 'idle' : (whOk.value ? 'ok' : 'bad')])
              }, null, 2),
              _cache[6] || (_cache[6] = _createElementVNode$5("span", { class: "epl-st-name" }, "Webhook", -1)),
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-st-val", !whEnabled.value ? 'idle' : (whOk.value ? 'ok' : 'bad')])
              }, _toDisplayString$5(whEnabled.value ? '● 已开启' : '○ 已关闭'), 3),
              (whEnabled.value && !whOk.value)
                ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_5$4, "异常"))
                : (whEnabled.value && whPending.value > 0)
                  ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_6$4, "待配置 " + _toDisplayString$5(whPending.value), 1))
                  : _createCommentVNode$5("", true)
            ]),
            _createElementVNode$5("div", _hoisted_7$4, [
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-dot", llmCls.value])
              }, null, 2),
              _cache[7] || (_cache[7] = _createElementVNode$5("span", { class: "epl-st-name" }, "LLM", -1)),
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-st-val", llmCls.value])
              }, _toDisplayString$5(llmTxt.value), 3)
            ]),
            _createElementVNode$5("div", _hoisted_8$4, [
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-dot", txCls.value])
              }, null, 2),
              _cache[8] || (_cache[8] = _createElementVNode$5("span", { class: "epl-st-name" }, "AI 翻译 Worker", -1)),
              _createElementVNode$5("span", {
                class: _normalizeClass$3(["epl-st-val", txCls.value])
              }, _toDisplayString$5(txTxt.value), 3),
              (txPaused.value && txPauseLeft.value > 0)
                ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_9$4, "剩余约 " + _toDisplayString$5(Math.ceil(txPauseLeft.value / 60)) + " 分钟", 1))
                : (txOnline.value && tx.value.requested && txScope.value)
                  ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_10$4, [
                      _createTextVNode$5("目标 " + _toDisplayString$5(txScope.value), 1),
                      (txProgress.value)
                        ? (_openBlock$5(), _createElementBlock$5(_Fragment$4, { key: 0 }, [
                            _createTextVNode$5(" · " + _toDisplayString$5(txProgress.value), 1)
                          ], 64))
                        : _createCommentVNode$5("", true)
                    ]))
                  : (_openBlock$5(), _createElementBlock$5("span", _hoisted_11$3, "待翻译 " + _toDisplayString$5(txPending.value), 1))
            ]),
            (poolFetchState.value.running)
              ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_12$3, [
                  _createVNode$5(_component_v_icon, { size: "15" }, {
                    default: _withCtx$5(() => [...(_cache[9] || (_cache[9] = [
                      _createTextVNode$5("mdi-account-arrow-down-outline", -1)
                    ]))]),
                    _: 1
                  }),
                  _createTextVNode$5("拉取人名 " + _toDisplayString$5(poolFetchState.value.done || 0) + "/" + _toDisplayString$5(poolFetchState.value.total || '…'), 1)
                ]))
              : (probeStatus.value.running)
                ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_13$3, [
                    _createVNode$5(_component_v_icon, { size: "15" }, {
                      default: _withCtx$5(() => [...(_cache[10] || (_cache[10] = [
                        _createTextVNode$5("mdi-magnify-scan", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$5(_toDisplayString$5(probeStatus.value.current_title || '探测库中…'), 1)
                  ]))
                : (scanStatus().current_title)
                  ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_14$3, [
                      _createVNode$5(_component_v_icon, { size: "15" }, {
                        default: _withCtx$5(() => [...(_cache[11] || (_cache[11] = [
                          _createTextVNode$5("mdi-progress-clock", -1)
                        ]))]),
                        _: 1
                      }),
                      _createTextVNode$5(_toDisplayString$5(scanStatus().current_title) + " ", 1),
                      (scanStatus().total)
                        ? (_openBlock$5(), _createElementBlock$5(_Fragment$4, { key: 0 }, [
                            _createTextVNode$5("（" + _toDisplayString$5(scanStatus().done) + "/" + _toDisplayString$5(scanStatus().total) + " · " + _toDisplayString$5(scanStatus().percent) + "%）", 1)
                          ], 64))
                        : _createCommentVNode$5("", true)
                    ]))
                  : _createCommentVNode$5("", true)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (!loading.value && !whEnabled.value)
      ? (_openBlock$5(), _createBlock$5(_component_v_alert, {
          key: 0,
          type: "warning",
          variant: "tonal",
          density: "compact",
          class: "mb-4 epl-wh-off-alert"
        }, {
          default: _withCtx$5(() => [
            _createElementVNode$5("div", _hoisted_15$3, [
              _cache[14] || (_cache[14] = _createElementVNode$5("span", null, "Webhook 已关闭：新入库事件不会接收。NFO 扫描 / 探测库仍可发现新条目。", -1)),
              (whHeld.value > 0)
                ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_16$3, "已有挂起事件：" + _toDisplayString$5(whHeld.value) + "（关闭期间冻结不丢失，重新开启后自动续跑）。", 1))
                : _createCommentVNode$5("", true),
              (pendingCount() > 0)
                ? (_openBlock$5(), _createBlock$5(_component_v_btn, {
                    key: 1,
                    size: "small",
                    color: "warning",
                    variant: "flat",
                    loading: pendingBusy.value,
                    onClick: pendingContinue
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_icon, {
                        start: "",
                        size: "16"
                      }, {
                        default: _withCtx$5(() => [...(_cache[12] || (_cache[12] = [
                          _createTextVNode$5("mdi-play", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[13] || (_cache[13] = _createTextVNode$5("继续处理待配置事件 ", -1))
                    ]),
                    _: 1
                  }, 8, ["loading"]))
                : _createCommentVNode$5("", true)
            ])
          ]),
          _: 1
        }))
      : _createCommentVNode$5("", true),
    _createVNode$5(_component_v_dialog, {
      modelValue: depsDialog.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((depsDialog).value = $event)),
      "max-width": "460"
    }, {
      default: _withCtx$5(() => [
        _createVNode$5(_component_v_card, null, {
          default: _withCtx$5(() => [
            _createVNode$5(_component_v_card_title, { class: "epl-card-title" }, {
              default: _withCtx$5(() => [
                _createVNode$5(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$5(() => [...(_cache[15] || (_cache[15] = [
                    _createTextVNode$5("mdi-package-variant-closed", -1)
                  ]))]),
                  _: 1
                }),
                _cache[18] || (_cache[18] = _createTextVNode$5(" 运行依赖 ", -1)),
                _createVNode$5(_component_v_spacer),
                _createVNode$5(_component_v_btn, {
                  size: "small",
                  variant: "tonal",
                  loading: depsLoading.value,
                  onClick: loadDeps
                }, {
                  default: _withCtx$5(() => [
                    _createVNode$5(_component_v_icon, {
                      start: "",
                      size: "14"
                    }, {
                      default: _withCtx$5(() => [...(_cache[16] || (_cache[16] = [
                        _createTextVNode$5("mdi-refresh", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[17] || (_cache[17] = _createTextVNode$5(" 重新检测 ", -1))
                  ]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            }),
            _createVNode$5(_component_v_card_text, { class: "pt-0" }, {
              default: _withCtx$5(() => [
                (!deps.value.items.length)
                  ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_17$3, "暂未检测"))
                  : (_openBlock$5(), _createBlock$5(_component_v_list, {
                      key: 1,
                      density: "compact",
                      lines: "two",
                      class: "pa-0"
                    }, {
                      default: _withCtx$5(() => [
                        (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$4(deps.value.items, (d) => {
                          return (_openBlock$5(), _createBlock$5(_component_v_list_item, {
                            key: d.key
                          }, {
                            prepend: _withCtx$5(() => [
                              _createVNode$5(_component_v_icon, {
                                color: d.ok ? 'success' : 'error',
                                size: "20"
                              }, {
                                default: _withCtx$5(() => [
                                  _createTextVNode$5(_toDisplayString$5(d.ok ? 'mdi-check-circle' : 'mdi-close-circle'), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"])
                            ]),
                            default: _withCtx$5(() => [
                              _createVNode$5(_component_v_list_item_title, null, {
                                default: _withCtx$5(() => [
                                  _createTextVNode$5(_toDisplayString$5(d.name) + " ", 1),
                                  _createVNode$5(_component_v_chip, {
                                    color: d.ok ? 'success' : 'error',
                                    size: "x-small",
                                    variant: "tonal",
                                    class: "ml-1"
                                  }, {
                                    default: _withCtx$5(() => [
                                      _createTextVNode$5(_toDisplayString$5(d.ok ? '正常' : '未安装'), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"])
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode$5(_component_v_list_item_subtitle, null, {
                                default: _withCtx$5(() => [
                                  _createTextVNode$5(_toDisplayString$5(d.ok ? d.detail : d.detail + '（' + d.impact + '）'), 1)
                                ]),
                                _: 2
                              }, 1024)
                            ]),
                            _: 2
                          }, 1024))
                        }), 128))
                      ]),
                      _: 1
                    })),
                _cache[19] || (_cache[19] = _createElementVNode$5("div", { class: "epl-deps-hint text-body-2" }, " 依赖由 MoviePilot 安装插件时按 requirements.txt 自动安装；缺失时功能降级（见各项说明）。 ", -1))
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$5(_component_v_card, {
      variant: "tonal",
      class: "mb-4 epl-opcard"
    }, {
      default: _withCtx$5(() => [
        _createVNode$5(_component_v_card_text, { class: "d-flex align-center flex-wrap ga-2" }, {
          default: _withCtx$5(() => [
            _createElementVNode$5("span", _hoisted_18$3, [
              _createVNode$5(_component_v_icon, {
                start: "",
                size: "18"
              }, {
                default: _withCtx$5(() => [...(_cache[20] || (_cache[20] = [
                  _createTextVNode$5("mdi-play-box-outline", -1)
                ]))]),
                _: 1
              }),
              _cache[21] || (_cache[21] = _createTextVNode$5("运行操作", -1))
            ]),
            _createVNode$5(_component_v_tooltip, {
              text: pluginEnabled() ? mainActionHint() : '插件未启用：请先在设置页打开「启用插件」',
              location: "top",
              "max-width": "320"
            }, {
              activator: _withCtx$5(({ props: tp }) => [
                _createVNode$5(_component_v_btn, _mergeProps$2({
                  size: "small",
                  color: "primary",
                  variant: "tonal",
                  disabled: running() || !pluginEnabled(),
                  loading: busy.value==='scan'
                }, tp, {
                  onClick: _cache[2] || (_cache[2] = $event => (runOp('scan', 'NFO 扫描已启动')))
                }), {
                  default: _withCtx$5(() => [
                    _createVNode$5(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$5(() => [...(_cache[22] || (_cache[22] = [
                        _createTextVNode$5("mdi-file-document-check-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$5(_toDisplayString$5(mainActionLabel()), 1)
                  ]),
                  _: 1
                }, 16, ["disabled", "loading"])
              ]),
              _: 1
            }, 8, ["text"]),
            _createVNode$5(_component_v_tooltip, {
              text: pluginEnabled() ? translateAllHint() : '插件未启用',
              location: "top",
              "max-width": "320"
            }, {
              activator: _withCtx$5(({ props: tp }) => [
                _createVNode$5(_component_v_btn, _mergeProps$2({
                  size: "small",
                  color: "success",
                  variant: "tonal",
                  disabled: running() || !pluginEnabled() || !canResume.value,
                  loading: translateAllBusy.value
                }, tp, { onClick: runTranslateAll }), {
                  default: _withCtx$5(() => [
                    _createVNode$5(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$5(() => [...(_cache[23] || (_cache[23] = [
                        _createTextVNode$5("mdi-play-circle-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[24] || (_cache[24] = _createTextVNode$5("续跑 ", -1))
                  ]),
                  _: 1
                }, 16, ["disabled", "loading"])
              ]),
              _: 1
            }, 8, ["text"]),
            _createVNode$5(_component_v_tooltip, {
              location: "top",
              "max-width": "300",
              text: "立即跑一轮探测库：Emby 缺的集/新条目补翻；Emby 已删的集标「待恢复」（有任务在跑会跳过）"
            }, {
              activator: _withCtx$5(({ props: tp }) => [
                _createVNode$5(_component_v_btn, _mergeProps$2({
                  size: "small",
                  color: "info",
                  variant: "tonal",
                  disabled: running() || !pluginEnabled(),
                  loading: probeBusy.value
                }, tp, { onClick: runProbeNow }), {
                  default: _withCtx$5(() => [
                    _createVNode$5(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$5(() => [...(_cache[25] || (_cache[25] = [
                        _createTextVNode$5("mdi-radar", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[26] || (_cache[26] = _createTextVNode$5("探测库 ", -1))
                  ]),
                  _: 1
                }, 16, ["disabled", "loading"])
              ]),
              _: 1
            }),
            _createVNode$5(_component_v_tooltip, {
              location: "top",
              "max-width": "300",
              text: poolFetchHint.value || '把 Emby 的 Person 拉进人名池（翻译一次全局复用）：按设置页「翻译范围」的人名类型开关拉取；拉取期间入库事件自动排队'
            }, {
              activator: _withCtx$5(({ props: tp }) => [
                _createVNode$5(_component_v_btn, _mergeProps$2({
                  size: "small",
                  color: "info",
                  variant: "flat",
                  disabled: poolFetchDisabled.value,
                  loading: poolFetchBusy.value
                }, tp, { onClick: startPoolFetch }), {
                  default: _withCtx$5(() => [
                    _createVNode$5(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$5(() => [...(_cache[27] || (_cache[27] = [
                        _createTextVNode$5("mdi-account-arrow-down-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$5(_toDisplayString$5(poolFetchLabel()), 1)
                  ]),
                  _: 1
                }, 16, ["disabled", "loading"])
              ]),
              _: 1
            }, 8, ["text"]),
            (!anyTaskPaused.value)
              ? (_openBlock$5(), _createBlock$5(_component_v_tooltip, {
                  key: 0,
                  location: "top",
                  "max-width": "300",
                  text: "暂停正在运行的任务（扫描 / 拉取人名 / AI 翻译）：进度与词条都保留；翻译会等当前一批完成后停，点「继续」接着跑"
                }, {
                  activator: _withCtx$5(({ props: tp }) => [
                    _createVNode$5(_component_v_btn, _mergeProps$2({
                      size: "small",
                      color: "warning",
                      variant: "tonal"
                    }, tp, {
                      disabled: (!running() && !tx.value.requested) || !pluginEnabled(),
                      onClick: pauseTasks
                    }), {
                      default: _withCtx$5(() => [
                        _createVNode$5(_component_v_icon, {
                          start: "",
                          size: "18"
                        }, {
                          default: _withCtx$5(() => [...(_cache[28] || (_cache[28] = [
                            _createTextVNode$5("mdi-pause", -1)
                          ]))]),
                          _: 1
                        }),
                        _cache[29] || (_cache[29] = _createTextVNode$5("暂停 ", -1))
                      ]),
                      _: 1
                    }, 16, ["disabled"])
                  ]),
                  _: 1
                }))
              : (_openBlock$5(), _createBlock$5(_component_v_tooltip, {
                  key: 1,
                  location: "top",
                  "max-width": "300",
                  text: pluginEnabled() ? '继续之前暂停的任务（扫描 / 拉取人名 / AI 翻译）' : '插件未启用：请先在设置页打开「启用插件」'
                }, {
                  activator: _withCtx$5(({ props: tp }) => [
                    _createVNode$5(_component_v_btn, _mergeProps$2({
                      size: "small",
                      color: "success",
                      variant: "flat",
                      disabled: !pluginEnabled()
                    }, tp, { onClick: resumeTasks }), {
                      default: _withCtx$5(() => [
                        _createVNode$5(_component_v_icon, {
                          start: "",
                          size: "18"
                        }, {
                          default: _withCtx$5(() => [...(_cache[30] || (_cache[30] = [
                            _createTextVNode$5("mdi-play", -1)
                          ]))]),
                          _: 1
                        }),
                        _cache[31] || (_cache[31] = _createTextVNode$5("继续 ", -1))
                      ]),
                      _: 1
                    }, 16, ["disabled"])
                  ]),
                  _: 1
                }, 8, ["text"])),
            _createVNode$5(_component_v_btn, {
              size: "small",
              color: "error",
              variant: "tonal",
              disabled: !running() && !tx.value.requested,
              loading: busy.value==='stop',
              onClick: stopAll
            }, {
              default: _withCtx$5(() => [
                _createVNode$5(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$5(() => [...(_cache[32] || (_cache[32] = [
                    _createTextVNode$5("mdi-stop", -1)
                  ]))]),
                  _: 1
                }),
                _cache[33] || (_cache[33] = _createTextVNode$5("终止 ", -1))
              ]),
              _: 1
            }, 8, ["disabled", "loading"]),
            (!pluginEnabled())
              ? (_openBlock$5(), _createBlock$5(_component_v_chip, {
                  key: 2,
                  size: "small",
                  color: "warning",
                  variant: "tonal"
                }, {
                  default: _withCtx$5(() => [
                    _createVNode$5(_component_v_icon, {
                      start: "",
                      size: "14"
                    }, {
                      default: _withCtx$5(() => [...(_cache[34] || (_cache[34] = [
                        _createTextVNode$5("mdi-alert-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[35] || (_cache[35] = _createTextVNode$5("插件未启用，操作已锁定 ", -1))
                  ]),
                  _: 1
                }))
              : _createCommentVNode$5("", true)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (loading.value)
      ? (_openBlock$5(), _createBlock$5(_component_v_progress_circular, {
          key: 1,
          indeterminate: "",
          color: "primary",
          class: "epl-center"
        }))
      : (_openBlock$5(), _createElementBlock$5(_Fragment$4, { key: 2 }, [
          _createVNode$5(_component_v_card, {
            variant: "tonal",
            class: "mb-4 epl-stagecard"
          }, {
            default: _withCtx$5(() => [
              _createVNode$5(_component_v_card_text, { class: "py-2" }, {
                default: _withCtx$5(() => [
                  (stageRows.value.length)
                    ? (_openBlock$5(true), _createElementBlock$5(_Fragment$4, { key: 0 }, _renderList$4(stageRows.value, (s) => {
                        return (_openBlock$5(), _createElementBlock$5("div", {
                          key: s.key,
                          class: "epl-stage-row"
                        }, [
                          _createElementVNode$5("span", _hoisted_19$3, _toDisplayString$5(s.name), 1),
                          _createVNode$5(_component_v_progress_linear, {
                            "model-value": s.percent,
                            color: s.color,
                            height: "8",
                            rounded: "",
                            indeterminate: !s.percent,
                            class: "epl-stage-bar"
                          }, null, 8, ["model-value", "color", "indeterminate"]),
                          _createElementVNode$5("span", _hoisted_20$3, _toDisplayString$5(s.text), 1)
                        ]))
                      }), 128))
                    : (_openBlock$5(), _createElementBlock$5("div", _hoisted_21$3, [
                        _createVNode$5(_component_v_icon, { size: "15" }, {
                          default: _withCtx$5(() => [...(_cache[36] || (_cache[36] = [
                            _createTextVNode$5("mdi-circle-slice-8", -1)
                          ]))]),
                          _: 1
                        }),
                        _cache[37] || (_cache[37] = _createTextVNode$5(" 当前没有运行中的阶段任务（扫描 → 翻译 → 写回 自动衔接；终止互不影响） ", -1))
                      ]))
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode$5(_component_v_row, null, {
            default: _withCtx$5(() => [
              _createVNode$5(_component_v_col, {
                cols: "6",
                sm: "6",
                md: "3"
              }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_card, {
                    class: "epl-card-bg epl-stat-card",
                    height: "100%"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_card_text, { class: "text-center pa-4" }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_22$3, _toDisplayString$5(dbStats.value?.item_count ?? 0), 1),
                          _cache[38] || (_cache[38] = _createElementVNode$5("div", { class: "epl-stat-label" }, "库中条目", -1)),
                          _cache[39] || (_cache[39] = _createElementVNode$5("div", { class: "epl-stat-sub" }, "已采集入库的作品数", -1))
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              _createVNode$5(_component_v_col, {
                cols: "6",
                sm: "6",
                md: "3"
              }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_card, {
                    class: "epl-card-bg epl-stat-card",
                    height: "100%"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_card_text, { class: "text-center pa-4" }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_23$3, _toDisplayString$5(status.value?.pool_hit_rate ?? 0) + "%", 1),
                          _cache[40] || (_cache[40] = _createElementVNode$5("div", { class: "epl-stat-label" }, "池命中率", -1)),
                          _cache[41] || (_cache[41] = _createElementVNode$5("div", { class: "epl-stat-sub" }, "池/繁简命中不调 AI 的比例", -1))
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              _createVNode$5(_component_v_col, {
                cols: "6",
                sm: "6",
                md: "3"
              }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_card, {
                    class: "epl-card-bg epl-stat-card",
                    height: "100%"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_card_text, { class: "text-center pa-4" }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_24$3, _toDisplayString$5(poolCounts.value.total ?? 0), 1),
                          _cache[42] || (_cache[42] = _createElementVNode$5("div", { class: "epl-stat-label" }, "人名池", -1)),
                          _createElementVNode$5("div", _hoisted_25$3, "待翻 " + _toDisplayString$5(poolCounts.value.pending ?? 0) + " · 待同步 " + _toDisplayString$5(poolCounts.value.translated ?? 0), 1)
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              _createVNode$5(_component_v_col, {
                cols: "6",
                sm: "6",
                md: "3"
              }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_card, {
                    class: "epl-card-bg epl-stat-card",
                    height: "100%"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_card_text, { class: "text-center pa-4" }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_26$3, _toDisplayString$5(status.value?.webhook?.processed ?? 0), 1),
                          _cache[43] || (_cache[43] = _createElementVNode$5("div", { class: "epl-stat-label" }, "Webhook 已处理", -1)),
                          _cache[44] || (_cache[44] = _createElementVNode$5("div", { class: "epl-stat-sub" }, "入库事件自动翻译计数", -1))
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          (failedTerms.value.length)
            ? (_openBlock$5(), _createBlock$5(_component_v_card, {
                key: 0,
                class: "epl-card-bg mt-4 epl-failed-card"
              }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_card_title, { class: "epl-card-title" }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_icon, {
                        start: "",
                        size: "18",
                        color: "error"
                      }, {
                        default: _withCtx$5(() => [...(_cache[45] || (_cache[45] = [
                          _createTextVNode$5("mdi-alert-circle-outline", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[50] || (_cache[50] = _createTextVNode$5(" 翻译失败词条 ", -1)),
                      _createVNode$5(_component_v_chip, {
                        size: "x-small",
                        color: "error",
                        variant: "tonal",
                        class: "ml-2"
                      }, {
                        default: _withCtx$5(() => [
                          _createTextVNode$5(_toDisplayString$5(failedTerms.value.length), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode$5(_component_v_spacer),
                      _createVNode$5(_component_v_btn, {
                        size: "small",
                        variant: "tonal",
                        color: "warning",
                        loading: failedBusy.value==='retry',
                        onClick: retryFailed
                      }, {
                        default: _withCtx$5(() => [
                          _createVNode$5(_component_v_icon, {
                            start: "",
                            size: "16"
                          }, {
                            default: _withCtx$5(() => [...(_cache[46] || (_cache[46] = [
                              _createTextVNode$5("mdi-refresh", -1)
                            ]))]),
                            _: 1
                          }),
                          _cache[47] || (_cache[47] = _createTextVNode$5("重试失败项 ", -1))
                        ]),
                        _: 1
                      }, 8, ["loading"]),
                      _createVNode$5(_component_v_btn, {
                        size: "small",
                        variant: "tonal",
                        color: "error",
                        disabled: dataOpBlocked.value,
                        title: dataOpBlockedHint.value,
                        loading: failedBusy.value==='clear',
                        onClick: clearFailed
                      }, {
                        default: _withCtx$5(() => [
                          _createVNode$5(_component_v_icon, {
                            start: "",
                            size: "16"
                          }, {
                            default: _withCtx$5(() => [...(_cache[48] || (_cache[48] = [
                              _createTextVNode$5("mdi-delete-outline", -1)
                            ]))]),
                            _: 1
                          }),
                          _cache[49] || (_cache[49] = _createTextVNode$5("清空 ", -1))
                        ]),
                        _: 1
                      }, 8, ["disabled", "title", "loading"])
                    ]),
                    _: 1
                  }),
                  _createVNode$5(_component_v_card_text, { class: "pt-0" }, {
                    default: _withCtx$5(() => [
                      _createElementVNode$5("div", _hoisted_27$3, [
                        _createVNode$5(_component_v_list, {
                          density: "compact",
                          class: "pa-0"
                        }, {
                          default: _withCtx$5(() => [
                            (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$4(failedTerms.value, (t) => {
                              return (_openBlock$5(), _createBlock$5(_component_v_list_item, {
                                key: t,
                                class: "epl-failed-item"
                              }, {
                                default: _withCtx$5(() => [
                                  _createVNode$5(_component_v_list_item_title, { class: "epl-failed-term" }, {
                                    default: _withCtx$5(() => [
                                      _createTextVNode$5(_toDisplayString$5(t), 1)
                                    ]),
                                    _: 2
                                  }, 1024),
                                  _createVNode$5(_component_v_list_item_subtitle, { class: "epl-failed-reason" }, {
                                    default: _withCtx$5(() => [
                                      _createTextVNode$5(_toDisplayString$5(failedDetail(t)), 1)
                                    ]),
                                    _: 2
                                  }, 1024)
                                ]),
                                _: 2
                              }, 1024))
                            }), 128))
                          ]),
                          _: 1
                        })
                      ])
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }))
            : _createCommentVNode$5("", true),
          _createVNode$5(_component_v_card, { class: "epl-card-bg mt-4 epl-log-card" }, {
            default: _withCtx$5(() => [
              _createVNode$5(_component_v_card_title, { class: "epl-card-title" }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$5(() => [...(_cache[51] || (_cache[51] = [
                      _createTextVNode$5("mdi-text-box-outline", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[54] || (_cache[54] = _createTextVNode$5(" 实时日志 ", -1)),
                  _createVNode$5(_component_v_spacer),
                  _createVNode$5(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    onClick: loadAll,
                    title: "刷新"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_icon, { size: "16" }, {
                        default: _withCtx$5(() => [...(_cache[52] || (_cache[52] = [
                          _createTextVNode$5("mdi-refresh", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode$5(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    color: "error",
                    onClick: clearLogs,
                    title: "清空日志"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_icon, { size: "16" }, {
                        default: _withCtx$5(() => [...(_cache[53] || (_cache[53] = [
                          _createTextVNode$5("mdi-delete-outline", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              _createVNode$5(_component_v_card_text, { class: "pt-0 epl-scroll-body" }, {
                default: _withCtx$5(() => [
                  (!logs.value.length)
                    ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_28$3, [...(_cache[55] || (_cache[55] = [
                        _createElementVNode$5("div", null, "暂无日志", -1),
                        _createElementVNode$5("div", {
                          class: "text-caption",
                          style: {"opacity":".65"}
                        }, "启动/扫描/保存配置等操作后会在此滚动显示", -1)
                      ]))]))
                    : (_openBlock$5(), _createBlock$5(_component_v_table, {
                        key: 1,
                        density: "compact",
                        class: "epl-logtable"
                      }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("tbody", null, [
                            (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$4(logs.value, (l) => {
                              return (_openBlock$5(), _createElementBlock$5("tr", {
                                key: 'log-' + l.time + '-' + (l.level || '') + '-' + String(l.msg || l.message || '').slice(0, 60)
                              }, [
                                _createElementVNode$5("td", _hoisted_29$3, _toDisplayString$5(fmtTime(l.time)), 1),
                                _createElementVNode$5("td", null, [
                                  _createVNode$5(_component_v_chip, {
                                    size: "x-small",
                                    color: l.level === 'error' ? 'error' : l.level === 'warning' ? 'warning' : 'info',
                                    variant: "tonal",
                                    class: "mr-2"
                                  }, {
                                    default: _withCtx$5(() => [
                                      _createTextVNode$5(_toDisplayString$5((l.level || 'info').toUpperCase()), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"]),
                                  _createElementVNode$5("span", _hoisted_30$3, _toDisplayString$5(l.msg || l.message || ''), 1)
                                ])
                              ]))
                            }), 128))
                          ])
                        ]),
                        _: 1
                      }))
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode$5(_component_v_card, { class: "epl-card-bg mt-4 epl-wh-card" }, {
            default: _withCtx$5(() => [
              _createVNode$5(_component_v_card_title, { class: "epl-card-title" }, {
                default: _withCtx$5(() => [
                  _createVNode$5(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$5(() => [...(_cache[56] || (_cache[56] = [
                      _createTextVNode$5("mdi-webhook", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[60] || (_cache[60] = _createTextVNode$5("Webhook 最近事件 ", -1)),
                  (pendingCount() > 0)
                    ? (_openBlock$5(), _createBlock$5(_component_v_chip, {
                        key: 0,
                        size: "x-small",
                        color: "warning",
                        variant: "tonal",
                        class: "ml-2"
                      }, {
                        default: _withCtx$5(() => [
                          _createVNode$5(_component_v_icon, {
                            start: "",
                            size: "13"
                          }, {
                            default: _withCtx$5(() => [...(_cache[57] || (_cache[57] = [
                              _createTextVNode$5("mdi-pause-circle-outline", -1)
                            ]))]),
                            _: 1
                          }),
                          _createTextVNode$5("待配置 " + _toDisplayString$5(pendingCount()), 1)
                        ]),
                        _: 1
                      }))
                    : _createCommentVNode$5("", true),
                  (status.value?.webhook)
                    ? (_openBlock$5(), _createBlock$5(_component_v_chip, {
                        key: 1,
                        size: "x-small",
                        variant: "tonal",
                        class: "ml-2"
                      }, {
                        default: _withCtx$5(() => [
                          _createTextVNode$5(" 收 " + _toDisplayString$5(status.value.webhook.total_received ?? 0) + " / 成 " + _toDisplayString$5(status.value.webhook.processed ?? 0) + " / 败 " + _toDisplayString$5(status.value.webhook.failed ?? 0), 1)
                        ]),
                        _: 1
                      }))
                    : _createCommentVNode$5("", true),
                  (status.value?.webhook?.last_error)
                    ? (_openBlock$5(), _createBlock$5(_component_v_chip, {
                        key: 2,
                        size: "x-small",
                        color: "error",
                        variant: "tonal",
                        class: "ml-1"
                      }, {
                        default: _withCtx$5(() => [
                          _createTextVNode$5(_toDisplayString$5(String(status.value.webhook.last_error).slice(0, 40)), 1)
                        ]),
                        _: 1
                      }))
                    : _createCommentVNode$5("", true),
                  _createVNode$5(_component_v_spacer),
                  _createVNode$5(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    onClick: loadAll,
                    title: "刷新"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_icon, { size: "16" }, {
                        default: _withCtx$5(() => [...(_cache[58] || (_cache[58] = [
                          _createTextVNode$5("mdi-refresh", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode$5(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    color: "error",
                    disabled: dataOpBlocked.value,
                    title: dataOpBlockedHint.value || '清空事件',
                    onClick: clearWhEvents,
                    loading: busy.value==='wh_clear'
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_icon, { size: "16" }, {
                        default: _withCtx$5(() => [...(_cache[59] || (_cache[59] = [
                          _createTextVNode$5("mdi-delete-outline", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["disabled", "title", "loading"])
                ]),
                _: 1
              }),
              _createVNode$5(_component_v_card_text, { class: "pa-0 epl-wh-body" }, {
                default: _withCtx$5(() => [
                  (pendingCount() > 0)
                    ? (_openBlock$5(), _createBlock$5(_component_v_alert, {
                        key: 0,
                        type: "warning",
                        variant: "tonal",
                        density: "compact",
                        class: "ma-2 mb-0"
                      }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_31$3, [
                            _createElementVNode$5("span", null, "有 " + _toDisplayString$5(pendingCount()) + " 个入库事件因目录映射不命中而挂起（待配置）。请到设置页确认已选择该媒体库（必要时调整「路径前缀替换」）后，再点「继续处理」自动翻译；不想处理可点「放弃全部」。", 1),
                            _createVNode$5(_component_v_btn, {
                              size: "small",
                              color: "warning",
                              variant: "flat",
                              loading: pendingBusy.value,
                              onClick: pendingContinue
                            }, {
                              default: _withCtx$5(() => [
                                _createVNode$5(_component_v_icon, {
                                  start: "",
                                  size: "16"
                                }, {
                                  default: _withCtx$5(() => [...(_cache[61] || (_cache[61] = [
                                    _createTextVNode$5("mdi-play", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[62] || (_cache[62] = _createTextVNode$5("继续处理 ", -1))
                              ]),
                              _: 1
                            }, 8, ["loading"]),
                            _createVNode$5(_component_v_btn, {
                              size: "small",
                              color: "error",
                              variant: "tonal",
                              disabled: dataOpBlocked.value,
                              title: dataOpBlockedHint.value,
                              loading: pendingClearBusy.value,
                              onClick: pendingClear
                            }, {
                              default: _withCtx$5(() => [
                                _createVNode$5(_component_v_icon, {
                                  start: "",
                                  size: "16"
                                }, {
                                  default: _withCtx$5(() => [...(_cache[63] || (_cache[63] = [
                                    _createTextVNode$5("mdi-delete-sweep-outline", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[64] || (_cache[64] = _createTextVNode$5("放弃全部 ", -1))
                              ]),
                              _: 1
                            }, 8, ["disabled", "title", "loading"])
                          ])
                        ]),
                        _: 1
                      }))
                    : _createCommentVNode$5("", true),
                  _createVNode$5(_component_v_row, {
                    "no-gutters": "",
                    class: "epl-wh-cols"
                  }, {
                    default: _withCtx$5(() => [
                      _createVNode$5(_component_v_col, {
                        cols: "12",
                        sm: "6",
                        class: "epl-wh-col"
                      }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_32$3, [
                            _createVNode$5(_component_v_icon, {
                              size: "15",
                              class: "mr-1"
                            }, {
                              default: _withCtx$5(() => [...(_cache[65] || (_cache[65] = [
                                _createTextVNode$5("mdi-webhook", -1)
                              ]))]),
                              _: 1
                            }),
                            _cache[66] || (_cache[66] = _createTextVNode$5("入库事件 ", -1)),
                            _createVNode$5(_component_v_chip, {
                              size: "x-small",
                              variant: "tonal",
                              class: "ml-1"
                            }, {
                              default: _withCtx$5(() => [
                                _createTextVNode$5(_toDisplayString$5(normalEvents.value.length), 1)
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$5("div", _hoisted_33$3, [
                            (!normalEvents.value.length)
                              ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_34$3, [...(_cache[67] || (_cache[67] = [
                                  _createElementVNode$5("div", null, "暂无入库事件", -1),
                                  _createElementVNode$5("div", {
                                    class: "text-caption",
                                    style: {"opacity":".65"}
                                  }, "Emby 有入库事件后这里会显示处理结果", -1)
                                ]))]))
                              : (_openBlock$5(), _createBlock$5(_component_v_table, {
                                  key: 1,
                                  density: "compact",
                                  class: "epl-logtable"
                                }, {
                                  default: _withCtx$5(() => [
                                    _createElementVNode$5("tbody", null, [
                                      (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$4(normalEvents.value, (e) => {
                                        return (_openBlock$5(), _createElementBlock$5("tr", {
                                          key: 'ev-' + e.time + '-' + (e.item_id || '') + '-' + (e.status || '')
                                        }, [
                                          _createElementVNode$5("td", _hoisted_35$3, _toDisplayString$5(e.time), 1),
                                          _createElementVNode$5("td", null, [
                                            _createElementVNode$5("div", {
                                              class: "epl-wh-name",
                                              title: e.series_name || e.name || e.item_id
                                            }, _toDisplayString$5(e.series_name || e.name || e.item_id), 9, _hoisted_36$3),
                                            _createElementVNode$5("div", _hoisted_37$3, [
                                              (e.episode != null)
                                                ? (_openBlock$5(), _createElementBlock$5(_Fragment$4, { key: 0 }, [
                                                    _createTextVNode$5("S" + _toDisplayString$5(e.season) + "E" + _toDisplayString$5(e.episode) + " · ", 1)
                                                  ], 64))
                                                : _createCommentVNode$5("", true),
                                              _createVNode$5(_component_v_chip, {
                                                size: "x-small",
                                                color: whStatusColor(e.status),
                                                variant: "tonal"
                                              }, {
                                                default: _withCtx$5(() => [
                                                  _createTextVNode$5(_toDisplayString$5(whStatusLabel(e.status)), 1)
                                                ]),
                                                _: 2
                                              }, 1032, ["color"])
                                            ]),
                                            _createElementVNode$5("div", _hoisted_38$3, _toDisplayString$5(e.msg), 1)
                                          ])
                                        ]))
                                      }), 128))
                                    ])
                                  ]),
                                  _: 1
                                }))
                          ])
                        ]),
                        _: 1
                      }),
                      _createVNode$5(_component_v_divider, {
                        vertical: "",
                        class: "epl-wh-divider",
                        style: {"opacity":".25"}
                      }),
                      _createVNode$5(_component_v_col, {
                        cols: "12",
                        sm: "6",
                        class: "epl-wh-col"
                      }, {
                        default: _withCtx$5(() => [
                          _createElementVNode$5("div", _hoisted_39$3, [
                            _createVNode$5(_component_v_icon, {
                              size: "15",
                              class: "mr-1"
                            }, {
                              default: _withCtx$5(() => [...(_cache[68] || (_cache[68] = [
                                _createTextVNode$5("mdi-progress-clock", -1)
                              ]))]),
                              _: 1
                            }),
                            _cache[71] || (_cache[71] = _createTextVNode$5("失效 / 待恢复 ", -1)),
                            _createVNode$5(_component_v_chip, {
                              size: "x-small",
                              color: "warning",
                              variant: "tonal",
                              class: "ml-1"
                            }, {
                              default: _withCtx$5(() => [
                                _createTextVNode$5(_toDisplayString$5(missingEvents.value.length), 1)
                              ]),
                              _: 1
                            }),
                            _createVNode$5(_component_v_spacer),
                            (missingEvents.value.length)
                              ? (_openBlock$5(), _createBlock$5(_component_v_btn, {
                                  key: 0,
                                  size: "x-small",
                                  variant: "text",
                                  color: "error",
                                  disabled: dataOpBlocked.value,
                                  title: dataOpBlockedHint.value || '清除全部失效记录（立即判定为真删除）',
                                  loading: purgeMissingBusy.value,
                                  onClick: purgeMissing
                                }, {
                                  default: _withCtx$5(() => [
                                    _createVNode$5(_component_v_icon, { size: "15" }, {
                                      default: _withCtx$5(() => [...(_cache[69] || (_cache[69] = [
                                        _createTextVNode$5("mdi-delete-sweep-outline", -1)
                                      ]))]),
                                      _: 1
                                    }),
                                    _cache[70] || (_cache[70] = _createTextVNode$5("清除 ", -1))
                                  ]),
                                  _: 1
                                }, 8, ["disabled", "title", "loading"]))
                              : _createCommentVNode$5("", true)
                          ]),
                          _createElementVNode$5("div", _hoisted_40$3, [
                            (!missingEvents.value.length)
                              ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_41$3, [...(_cache[72] || (_cache[72] = [
                                  _createElementVNode$5("div", null, "暂无失效记录", -1),
                                  _createElementVNode$5("div", {
                                    class: "text-caption",
                                    style: {"opacity":".65"}
                                  }, "nfo 目录消失后会出现在这里（观察期，到期自动检查）", -1)
                                ]))]))
                              : (_openBlock$5(), _createBlock$5(_component_v_list, {
                                  key: 1,
                                  density: "compact",
                                  class: "pa-0",
                                  nav: ""
                                }, {
                                  default: _withCtx$5(() => [
                                    (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$4(missingEvents.value, (e) => {
                                      return (_openBlock$5(), _createBlock$5(_component_v_list_item, {
                                        key: 'ms-' + e.time + '-' + (e.item_id || ''),
                                        class: "epl-wh-missing-item"
                                      }, {
                                        default: _withCtx$5(() => [
                                          _createVNode$5(_component_v_list_item_title, { class: "epl-wh-name" }, {
                                            default: _withCtx$5(() => [
                                              _createTextVNode$5(_toDisplayString$5(e.series_name || e.name || e.item_id), 1)
                                            ]),
                                            _: 2
                                          }, 1024),
                                          _createVNode$5(_component_v_list_item_subtitle, { class: "epl-log-msg" }, {
                                            default: _withCtx$5(() => [
                                              (fmtGraceDate(e.msg))
                                                ? (_openBlock$5(), _createBlock$5(_component_v_chip, {
                                                    key: 0,
                                                    size: "x-small",
                                                    color: "warning",
                                                    variant: "tonal",
                                                    class: "mr-1"
                                                  }, {
                                                    default: _withCtx$5(() => [
                                                      _createTextVNode$5("到期 " + _toDisplayString$5(fmtGraceDate(e.msg)), 1)
                                                    ]),
                                                    _: 2
                                                  }, 1024))
                                                : _createCommentVNode$5("", true),
                                              _createTextVNode$5(" " + _toDisplayString$5(e.msg), 1)
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ]),
                                        _: 2
                                      }, 1024))
                                    }), 128))
                                  ]),
                                  _: 1
                                }))
                          ])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ], 64)),
    _createVNode$5(ConfirmDlg, {
      state: _unref$2(cState),
      "on-ok": _unref$2(cOk),
      "on-cancel": _unref$2(cCancel)
    }, null, 8, ["state", "on-ok", "on-cancel"])
  ]))
}
}

};
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main$5, [['__scopeId',"data-v-4c9bc22d"]]);

const {createTextVNode:_createTextVNode$4,resolveComponent:_resolveComponent$4,withCtx:_withCtx$4,createVNode:_createVNode$4,toDisplayString:_toDisplayString$4,createElementVNode:_createElementVNode$4,openBlock:_openBlock$4,createElementBlock:_createElementBlock$4,createCommentVNode:_createCommentVNode$4,createBlock:_createBlock$4} = await importShared('vue');


const _hoisted_1$4 = { class: "mb-2" };
const _hoisted_2$4 = {
  key: 0,
  class: "mb-2"
};
const _hoisted_3$4 = {
  key: 1,
  class: "mb-2"
};


const _sfc_main$4 = {
  __name: 'TaskGuardDlg',
  props: {
  modelValue: { type: Boolean, default: false },
  reason: { type: String, default: '' },
  action: { type: String, default: '' },
  state: { type: String, default: '' },   // v4.6.73：统一任务状态名（如「写回 NFO 中」）
},
  emits: ['update:modelValue', 'view-task'],
  setup(__props, { emit: __emit }) {

/**
 * 统一「任务正在执行」拦截弹窗（v4.6.70 · 审查报告第四节）。
 * 不提供「强行继续」——只允许取消，或去看任务进度（切到仪表盘）。
 */
const props = __props;
const emit = __emit;

function close() { emit('update:modelValue', false); }
function viewTask() { close(); emit('view-task'); }

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$4("v-icon");
  const _component_v_card_title = _resolveComponent$4("v-card-title");
  const _component_v_divider = _resolveComponent$4("v-divider");
  const _component_v_card_text = _resolveComponent$4("v-card-text");
  const _component_v_spacer = _resolveComponent$4("v-spacer");
  const _component_v_btn = _resolveComponent$4("v-btn");
  const _component_v_card_actions = _resolveComponent$4("v-card-actions");
  const _component_v_card = _resolveComponent$4("v-card");
  const _component_v_dialog = _resolveComponent$4("v-dialog");

  return (_openBlock$4(), _createBlock$4(_component_v_dialog, {
    "model-value": props.modelValue,
    "max-width": "470",
    "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (emit('update:modelValue', $event)))
  }, {
    default: _withCtx$4(() => [
      _createVNode$4(_component_v_card, null, {
        default: _withCtx$4(() => [
          _createVNode$4(_component_v_card_title, {
            class: "d-flex align-center",
            style: {"font-size":"16px"}
          }, {
            default: _withCtx$4(() => [
              _createVNode$4(_component_v_icon, {
                start: "",
                color: "warning"
              }, {
                default: _withCtx$4(() => [...(_cache[1] || (_cache[1] = [
                  _createTextVNode$4("mdi-lock-alert-outline", -1)
                ]))]),
                _: 1
              }),
              _cache[2] || (_cache[2] = _createTextVNode$4(" 任务正在执行，修改已锁定 ", -1))
            ]),
            _: 1
          }),
          _createVNode$4(_component_v_divider),
          _createVNode$4(_component_v_card_text, null, {
            default: _withCtx$4(() => [
              _createElementVNode$4("div", _hoisted_1$4, [
                _cache[3] || (_cache[3] = _createTextVNode$4("当前正在进行：", -1)),
                _createElementVNode$4("b", null, _toDisplayString$4(props.reason || '后台任务'), 1)
              ]),
              (props.state && props.state !== props.reason)
                ? (_openBlock$4(), _createElementBlock$4("div", _hoisted_2$4, [
                    _cache[4] || (_cache[4] = _createTextVNode$4(" 任务状态：", -1)),
                    _createElementVNode$4("b", null, _toDisplayString$4(props.state), 1),
                    _cache[5] || (_cache[5] = _createElementVNode$4("span", {
                      class: "text-caption",
                      style: {"opacity":".7"}
                    }, "（数据变更已锁定）", -1))
                  ]))
                : _createCommentVNode$4("", true),
              (props.action)
                ? (_openBlock$4(), _createElementBlock$4("div", _hoisted_3$4, [
                    _cache[6] || (_cache[6] = _createTextVNode$4("本次尝试的操作：", -1)),
                    _createElementVNode$4("b", null, _toDisplayString$4(props.action), 1)
                  ]))
                : _createCommentVNode$4("", true),
              _cache[7] || (_cache[7] = _createElementVNode$4("div", {
                class: "text-body-2",
                style: {"opacity":".8"}
              }, " 该操作会修改数据库或文件。为避免翻译结果、写回内容或人工修改互相覆盖， 当前暂不可执行。请等待任务完成，或到仪表盘「终止」后再试。 ", -1))
            ]),
            _: 1
          }),
          _createVNode$4(_component_v_card_actions, null, {
            default: _withCtx$4(() => [
              _createVNode$4(_component_v_spacer),
              _createVNode$4(_component_v_btn, {
                variant: "text",
                onClick: viewTask
              }, {
                default: _withCtx$4(() => [...(_cache[8] || (_cache[8] = [
                  _createTextVNode$4("查看任务", -1)
                ]))]),
                _: 1
              }),
              _createVNode$4(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: close
              }, {
                default: _withCtx$4(() => [...(_cache[9] || (_cache[9] = [
                  _createTextVNode$4("取消", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};

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
const {computed: computed$4,ref: ref$4} = await importShared('vue');


const KIND_ORDER = ['scan', 'translate', 'writeback', 'pool', 'probe'];
const KIND_LABEL = {
  scan: 'NFO 扫描',
  translate: 'AI 翻译',
  writeback: '写回 NFO',
  pool: '人名池任务',
  probe: '探测库',
};
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
};

function useTaskGuard() {
  const kinds = ref$4({ scan: false, translate: false, writeback: false, pool: false, probe: false });
  const isRunning = ref$4(false);     // 宿主任务状态机（_is_running）
  const txRequested = ref$4(false);   // 常驻翻译 worker 的消费许可（不置 _is_running，需单独看）
  const state = ref$4('IDLE');        // 统一任务状态机（后端 task_state.state）
  const dataLocked = ref$4(false);    // 后端 task_state.data_mutation_locked
  const dlg = ref$4(false);
  const pendingLabel = ref$4('');

  const activeKinds = computed$4(() => {
    const out = [];
    for (const k of KIND_ORDER) {
      if (kinds.value && kinds.value[k]) out.push(KIND_LABEL[k]);
    }
    // 兜底：任务状态机说在跑、或常驻翻译 worker 持有许可，但 kinds 未覆盖 → 至少标「AI 翻译」
    if (!out.length && (isRunning.value || txRequested.value)) out.push(KIND_LABEL.translate);
    return out
  });
  const stateLabel = computed$4(() => STATE_LABEL[state.value] || state.value || '空闲');
  const lock = computed$4(() => dataLocked.value || activeKinds.value.length > 0);
  const reason = computed$4(() => {
    const r = activeKinds.value.join(' / ');
    if (r) return r
    return dataLocked.value ? stateLabel.value : ''
  });
  const hint = computed$4(() => (lock.value
    ? `任务正在执行（${reason.value}）：为避免翻译结果 / 写回内容 / 人工修改互相覆盖，修改型操作已锁定`
    : ''));

  function loadStatus(st) {
    const ts = (st && st.task_state) || null;
    if (ts) {
      state.value = ts.state || 'IDLE';
      dataLocked.value = !!ts.data_mutation_locked;
      const tt = ts.tasks || {};
      kinds.value = {
        scan: !!tt.scan, translate: !!tt.translate, writeback: !!tt.writeback,
        pool: !!tt.pool, probe: !!tt.probe,
      };
    } else {
      const t = (st && st.tasks) || {};
      kinds.value = {
        scan: !!t.scan, translate: !!t.translate, writeback: !!t.writeback,
        pool: !!t.pool, probe: !!t.probe,
      };
      dataLocked.value = false;
      state.value = 'IDLE';
    }
    isRunning.value = !!(st && st.is_running);
    txRequested.value = !!(
      (st && st.tx && (st.tx.requested || st.tx.running))
      || (st && st.translate_status && st.translate_status.running)
    );
  }

  /** 修改型操作入口守卫：锁定 → 记录操作名、弹统一弹窗、返回 false；未锁定 → true。 */
  function check(label = '') {
    if (!lock.value) return true
    pendingLabel.value = label;
    dlg.value = true;
    return false
  }

  return { kinds, isRunning, txRequested, state, stateLabel, dataLocked,
           dlg, pendingLabel, lock, reason, hint, loadStatus, check }
}

const {createTextVNode:_createTextVNode$3,resolveComponent:_resolveComponent$3,withCtx:_withCtx$3,createVNode:_createVNode$3,mergeProps:_mergeProps$1,openBlock:_openBlock$3,createBlock:_createBlock$3,createCommentVNode:_createCommentVNode$3,createElementVNode:_createElementVNode$3,createElementBlock:_createElementBlock$3,toDisplayString:_toDisplayString$3,Fragment:_Fragment$3,renderList:_renderList$3,withModifiers:_withModifiers$1,normalizeClass:_normalizeClass$2,normalizeStyle:_normalizeStyle,unref:_unref$1} = await importShared('vue');


const _hoisted_1$3 = { class: "epl-lib" };
const _hoisted_2$3 = { class: "epl-topbar" };
const _hoisted_3$3 = { class: "d-none d-md-flex align-center ga-2" };
const _hoisted_4$3 = { key: 0 };
const _hoisted_5$3 = { key: 2 };
const _hoisted_6$3 = { key: 0 };
const _hoisted_7$3 = { key: 2 };
const _hoisted_8$3 = { class: "epl-sidebar epl-sidebar-top pa-2" };
const _hoisted_9$3 = { class: "d-flex align-center ga-2 flex-wrap" };
const _hoisted_10$3 = {
  key: 1,
  class: "epl-empty pa-6"
};
const _hoisted_11$2 = { class: "epl-group-count" };
const _hoisted_12$2 = {
  key: 4,
  class: "epl-load-sentinel"
};
const _hoisted_13$2 = {
  key: 0,
  class: "pa-3 epl-detail-head"
};
const _hoisted_14$2 = { class: "d-flex align-center" };
const _hoisted_15$2 = { class: "epl-poster-wrap mr-3" };
const _hoisted_16$2 = {
  class: "flex-grow-1",
  style: {"min-width":"0"}
};
const _hoisted_17$2 = ["title"];
const _hoisted_18$2 = { class: "epl-detail-meta" };
const _hoisted_19$2 = {
  class: "d-flex flex-column ga-1 ml-3",
  style: {"flex-shrink":"0"}
};
const _hoisted_20$2 = {
  key: 1,
  class: "epl-sidebar pa-2"
};
const _hoisted_21$2 = {
  class: "d-flex align-center",
  style: {"gap":"6px"}
};
const _hoisted_22$2 = {
  key: 0,
  class: "epl-empty pa-6"
};
const _hoisted_23$2 = {
  key: 1,
  class: "epl-empty pa-6"
};
const _hoisted_24$2 = { class: "pa-3 pb-1 epl-search-title" };
const _hoisted_25$2 = {
  class: "flex-grow-1",
  style: {"min-width":"0"}
};
const _hoisted_26$2 = { class: "epl-person-name" };
const _hoisted_27$2 = {
  key: 0,
  class: "epl-dim",
  style: {"margin-left":"8px"}
};
const _hoisted_28$2 = { class: "epl-person-role" };
const _hoisted_29$2 = ["title"];
const _hoisted_30$2 = {
  key: 0,
  class: "epl-occ-list"
};
const _hoisted_31$2 = {
  key: 0,
  class: "epl-cast-hint pa-2"
};
const _hoisted_32$2 = {
  key: 1,
  class: "epl-cast-hint pa-2"
};
const _hoisted_33$2 = ["title"];
const _hoisted_34$2 = { class: "text-caption epl-person-search-hint" };
const _hoisted_35$2 = {
  key: 0,
  class: "epl-empty pa-6"
};
const _hoisted_36$2 = {
  key: 1,
  class: "pa-4"
};
const _hoisted_37$2 = {
  key: 0,
  class: "epl-empty pa-4"
};
const _hoisted_38$2 = { class: "epl-cast-section" };
const _hoisted_39$2 = { class: "epl-cast-head" };
const _hoisted_40$2 = { class: "epl-cast-title" };
const _hoisted_41$2 = {
  key: 0,
  class: "epl-type-sub"
};
const _hoisted_42$2 = { class: "epl-grp-count" };
const _hoisted_43$2 = { class: "epl-actor-flow epl-actor-grid2" };
const _hoisted_44$2 = { class: "epl-chip-col" };
const _hoisted_45$2 = { class: "epl-chip-name" };
const _hoisted_46$2 = {
  key: 0,
  class: "epl-chip-role"
};
const _hoisted_47$2 = {
  key: 1,
  class: "epl-cast-hint"
};
const _hoisted_48$2 = { class: "epl-ep-toolbar" };
const _hoisted_49$2 = { class: "epl-ep-toolbar-left" };
const _hoisted_50$2 = { class: "epl-cast-hint" };
const _hoisted_51$2 = {
  key: 0,
  class: "epl-cast-hint",
  style: {"color":"rgb(var(--v-theme-error))"}
};
const _hoisted_52$2 = { class: "epl-ep-toolbar-right" };
const _hoisted_53$2 = {
  key: 0,
  class: "epl-season-tabs"
};
const _hoisted_54$2 = ["aria-pressed", "onClick"];
const _hoisted_55$2 = { class: "epl-season-tab-count" };
const _hoisted_56$2 = ["title"];
const _hoisted_57$2 = {
  key: 0,
  class: "epl-ep-dead-tag"
};
const _hoisted_58$2 = {
  key: 0,
  class: "epl-type-sub"
};
const _hoisted_59$2 = { class: "epl-grp-count" };
const _hoisted_60$2 = { class: "epl-actor-flow epl-actor-grid2" };
const _hoisted_61$2 = { class: "epl-chip-col" };
const _hoisted_62$2 = { class: "epl-chip-name" };
const _hoisted_63$2 = {
  key: 0,
  class: "epl-chip-role"
};
const _hoisted_64$2 = {
  key: 1,
  class: "epl-cast-hint"
};
const _hoisted_65$2 = {
  key: 1,
  class: "epl-cast-hint"
};
const _hoisted_66$2 = { class: "epl-cast-head" };
const _hoisted_67$2 = { class: "epl-cast-title" };
const _hoisted_68$2 = { class: "epl-grp-count" };
const _hoisted_69$2 = { class: "epl-actor-flow epl-actor-grid2" };
const _hoisted_70$2 = { class: "epl-chip-col" };
const _hoisted_71$2 = { class: "epl-chip-name" };
const _hoisted_72$2 = {
  key: 0,
  class: "epl-chip-role"
};
const _hoisted_73$2 = { class: "epl-edit-row" };
const _hoisted_74$2 = { class: "epl-edit-orig epl-readonly-box" };
const _hoisted_75$2 = { class: "epl-edit-row" };
const _hoisted_76$2 = { class: "epl-cast-hint mb-1" };
const _hoisted_77$2 = {
  key: 0,
  class: "epl-lock-chip",
  style: {"background":"#b00020","color":"#fff"}
};
const _hoisted_78$2 = {
  key: 1,
  class: "epl-lock-chip"
};
const _hoisted_79$2 = { key: 2 };
const _hoisted_80$2 = { class: "epl-cast-hint mb-2" };
const _hoisted_81$2 = {
  key: 3,
  class: "mb-3"
};
const _hoisted_82$2 = { class: "epl-edit-row" };
const _hoisted_83$2 = { class: "epl-edit-orig epl-readonly-box" };
const _hoisted_84$1 = { class: "epl-edit-row" };
const _hoisted_85$1 = {
  key: 0,
  class: "epl-edit-orig"
};
const _hoisted_86 = { class: "epl-cast-hint" };
const _hoisted_87 = { class: "epl-tx-preview" };
const _hoisted_88 = { class: "epl-tx-num" };
const _hoisted_89 = { class: "epl-tx-num" };
const _hoisted_90 = {
  key: 1,
  class: "epl-tx-current",
  style: {"color":"#ffb74d","white-space":"normal","line-height":"1.5"}
};
const _hoisted_91 = {
  key: 2,
  class: "epl-tx-current",
  style: {"color":"#81c784"}
};
const _hoisted_92 = {
  key: 3,
  class: "epl-tx-current"
};
const _hoisted_93 = { class: "epl-tx-current" };
const _hoisted_94 = {
  class: "text-caption",
  style: {"opacity":".75","margin-bottom":"8px"}
};
const _hoisted_95 = { class: "epl-pend-scroll" };
const _hoisted_96 = {
  key: 0,
  class: "epl-empty",
  style: {"padding":"18px 0"}
};
const _hoisted_97 = { class: "epl-pend-title" };
const _hoisted_98 = {
  key: 0,
  class: "epl-pend-line"
};
const _hoisted_99 = {
  key: 0,
  class: "epl-pend-more"
};
const _hoisted_100 = {
  key: 1,
  class: "epl-pend-line"
};
const _hoisted_101 = {
  key: 0,
  class: "epl-pend-more"
};

const {computed: computed$3,inject: inject$3,nextTick,onActivated: onActivated$2,onBeforeUnmount: onBeforeUnmount$1,onDeactivated: onDeactivated$1,onMounted: onMounted$3,ref: ref$3,watch: watch$2} = await importShared('vue');

const ITEM_PAGE_SIZE = 100;
const EP_PAGE_SIZE = 50;
const FAST_POLL_MS = 8000;

const _sfc_main$3 = {
  __name: 'LibraryView',
  props: { api: { type: Object, default: () => ({}) } },
  emits: ['notify', 'view-task'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject$3('moviepilot:toast', null);
const { cState, askConfirm, cOk, cCancel } = useConfirm();
// v4.6.70：统一任务守卫（编辑 / 重翻 / 全部翻译 / 写回 / 删除 / 导入 / 清库 等修改型操作共用）
const guard = useTaskGuard();

const items = ref$3([]);
const search = ref$3('');
const filterType = ref$3('');   // 左侧类型筛选 全部/剧集(Series+Episode)/电影(Movie)
const expandedLibs = ref$3(new Set());
const selected = ref$3(null);
const people = ref$3([]);
const itemMeta = ref$3(null);
const loadingList = ref$3(true);
const loadingPeople = ref$3(false);
const posterData = ref$3(null);
const logoData = ref$3(null);

function notify(msg, type = 'error') {
  const t = toast; if (t && typeof t[type] === 'function') t[type](msg);
}

// 按分库分组（仿字体库目录树的一级分组）
const groups = computed$3(() => {
  const map = {};
  const kw = (search.value || '').trim().toLowerCase();
  const ft = filterType.value;   // '' 全部 / Series 剧集 / Movie 电影
  for (const it of items.value) {
    if (kw && !String(it.title).toLowerCase().includes(kw)) continue
    const t = String(it.item_type || '').toLowerCase();
    if (ft === 'Series' && !['series', 'episode', '剧', '电视剧'].includes(t)) continue
    if (ft === 'Movie' && !['movie', '电影', '影片'].includes(t)) continue
    const lib = it.library_name || '未分类'
    ;(map[lib] = map[lib] || []).push(it);
  }
  for (const k of Object.keys(map)) {
    map[k].sort((a, b) => {
      const da = a.deleted_at ? 2 : (a.deleted_eps > 0 ? 1 : 0);
      const db = b.deleted_at ? 2 : (b.deleted_eps > 0 ? 1 : 0);
      if (da !== db) return db - da
      return (b.updated_at || '').localeCompare(a.updated_at || '')
    });
  }
  return map
});

// 扁平可见节点：分库节点永远显示，条目受展开状态控制
const visibleNodes = computed$3(() => {
  const out = [];
  const entries = Object.entries(groups.value)
    .sort((a, b) => { const o = ['未分类']; const ia = o.includes(a[0]) ? 1 : 0, ib = o.includes(b[0]) ? 1 : 0; return ia - ib || b[1].length - a[1].length });
  for (const [lib, list] of entries) {
    out.push({ type: 'group', lib, depth: 0, count: list.length });
    if (expandedLibs.value.has(lib) || (search.value || '').trim()) {
      for (const it of list) out.push({ type: 'item', item: it, depth: 1 });
    }
  }
  return out
});

// ── 库列表分页（UI-PAGE）：与分集同款滚动自加载 ──
const itemHasMore = ref$3(false);
const itemSentinel = ref$3(null);
let itemsSeq = 0;
let itemLoadingMore = false;
let _itemObserver = null;

// 兼容两种响应体：分页时 data={items,total,has_more}；未分页/旧后端 data=数组
function _normItems(resp) {
  if (Array.isArray(resp)) return { list: resp, total: resp.length, hasMore: false }
  const list = Array.isArray(resp?.items) ? resp.items : [];
  return { list, total: Number(resp?.total ?? list.length) || list.length, hasMore: !!resp?.has_more }
}

let _itemsInflight = false;
// v4.6.104（LIB-006）：左栏每一行真正渲染出来的字段 —— 只比这些；签名一致就整段跳过赋值。
const _ITEM_SIG_FIELDS = ['title', 'item_type', 'library_name', 'deleted_at', 'deleted_eps', 'person_count', 'episode_count'];
function _itemSig(it) {
  let s = '';
  for (const f of _ITEM_SIG_FIELDS) s += String((it && it[f]) != null ? it[f] : '') + '\u0001';
  return s
}
// 两轮数据完全等价？—— 等价则跳过赋值：不触发 computed、不让 v-list 整列重建（滚动跳动/闪烁的来源）
function _itemsSame(a, b) {
  if (a === b) return true
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (itemKey(a[i]) !== itemKey(b[i])) return false
    if (_itemSig(a[i]) !== _itemSig(b[i])) return false
  }
  return true
}
// 原地合并（v4.6.104 · LIB-007 / LIB-010）：同 key 的条目**保留对象引用**只改字段、顺序不变；
// 新 key 追加。未变化的行引用不变 → Vue 不重建 DOM，滚动位置与展开状态都稳住。
// removeMissing 只在「本次请求已覆盖服务端全部条目」时为 true（见 loadItems）——
// 若本次只取回一个不完整窗口（还在分页 / limit < total），绝不能把 cur 里 next 没出现的
// 条目删掉：列表按 translated_at 倒序，翻译一发生顺序就变，上一窗口的条目会落到新窗口外，
// 一删就是「分库整组消失、下次再补回来」的无限抖动（用户实测 v4.6.104 前一版）。
function _mergeItems(cur, next, removeMissing = true) {
  const byKey = new Map();
  for (const it of next) { const k = itemKey(it); if (k) byKey.set(k, it); }
  const out = [];
  const used = new Set();
  for (const it of cur) {
    const k = itemKey(it);
    const n = k ? byKey.get(k) : null;
    if (!n) {
      if (removeMissing) continue   // 已确认拉全 → 服务端真的没了，移除
      out.push(it);                  // 窗口不完整 → 保留已加载的，一个都不丢
      continue
    }
    used.add(k);
    for (const f of Object.keys(n)) { if (it[f] !== n[f]) it[f] = n[f]; }
    out.push(it);
  }
  for (const it of next) {
    const k = itemKey(it);
    if (!k || used.has(k)) continue
    used.add(k);
    out.push(it);
  }
  return out
}
async function loadItems(silent = false) {
  // v4.6.103（LIB-004）：单飞守卫 —— 与 loadTxPreview 的 _txPreviewInflight 同款。
  // 症状（用户实测 v4.6.102，库内 360 条目）：左侧条目早已渲染出来，进度条却一直转、停不下来。
  // 成因：轮询每 8s 调 loadItems(true)，若 /db/items 响应慢于 8s，老请求会被新请求顶掉
  // （seq 不匹配 → early return，finally 不清 loadingList），而新请求又被下一轮顶掉……
  // 于是「永远没有一个请求是"最新一代"」，loadingList 永远为 true。在飞期间直接丢弃本轮调用，
  // 保证在飞的唯一请求一定是最新一代 → 其 finally 必然清掉 loadingList。
  if (_itemsInflight) {
    if (!silent) loadingList.value = true;   // 手动刷新时至少给出转圈反馈（由在飞请求收尾清除）
    return
  }
  _itemsInflight = true;
  // 请求代次（LIB-003）：连点刷新/轮询叠加时，只有最新一轮响应能写状态
  const seq = ++itemsSeq;
  if (!silent) loadingList.value = true;
  try {
    // v4.6.104（LIB-006/007）：静默轮询不再把列表塌回第 1 页、也不再整段换新数组。
    // 症状（用户实测 v4.6.103，库内 360 条目）：每次刷新页面都「拉一下、加载一下」。
    // 成因：本函数固定 limit=100/offset=0 且无条件 items.value = list —— 用户滚动加载出来的
    // 后续条目被整段丢弃、列表塌回 100 条（视觉跳变），底部哨兵又把它们补回来，
    // 「刷新 → 塌陷 → 重新加载」每 8s 循环一次。现按当前窗口大小请求，并按 key 原地合并。
    const limit = Math.max(ITEM_PAGE_SIZE, items.value.length);
    const resp = await api.get(props.api, '/db/items', { limit, offset: 0 });
    if (seq !== itemsSeq) return
    const { list, total, hasMore } = _normItems(resp);
    // v4.6.104（LIB-010）：只有「本次请求覆盖了服务端全部条目」时，才允许移除服务端已消失的条目；
    // 否则（还有下一页 / limit < total）只做「改字段 + 追加」，绝不删 —— 防止分库整组消失再补回。
    const _complete = list.length >= total;
    if (silent && _itemsSame(items.value, list)) {   // 无变化：不赋值、不触发渲染
      itemHasMore.value = hasMore;
      return
    }
    items.value = _mergeItems(items.value, list, _complete);
    itemHasMore.value = hasMore;
  } catch (e) { if (seq === itemsSeq && !silent) notify(e.message, 'error'); }
  finally {
    if (seq === itemsSeq) loadingList.value = false;
    _itemsInflight = false;
  }
}

// 滚动到底部自动追加下一页：按「来源 + item_id」复合键去重，避免分页边界重复
async function loadMoreItems() {
  if (itemLoadingMore || !itemHasMore.value) return
  itemLoadingMore = true;
  const seq = itemsSeq;
  try {
    const resp = await api.get(props.api, '/db/items', { limit: ITEM_PAGE_SIZE, offset: items.value.length });
    if (seq !== itemsSeq) return
    const { list, hasMore } = _normItems(resp);
    const seen = new Set(items.value.map((it) => itemKey(it)));
    for (const it of list) {
      const k = itemKey(it);
      if (k && seen.has(k)) continue
      seen.add(k);
      items.value.push(it);
    }
    itemHasMore.value = hasMore;
  } catch (e) { /* 静默：滚动加载失败不打断浏览，点刷新可重试 */ }
  finally {
    itemLoadingMore = false;
    // 若哨兵仍在视口内（首屏未填满），继续补下一页，直到填满或加载完
    nextTick(() => {
      const el = itemSentinel.value;
      if (itemHasMore.value && el && el.getBoundingClientRect().top <= (window.innerHeight + 200)) loadMoreItems();
    });
  }
}
function setupItemObserver() {
  teardownItemObserver();
  if (!itemSentinel.value) return
  _itemObserver = new IntersectionObserver((entries) => {
    if (entries.some(e => e.isIntersecting)) loadMoreItems();
  }, { rootMargin: '200px' });
  _itemObserver.observe(itemSentinel.value);
}
function teardownItemObserver() {
  if (_itemObserver) { _itemObserver.disconnect(); _itemObserver = null; }
}
watch$2(itemSentinel, (el) => { if (el) setupItemObserver(); else teardownItemObserver(); });

function toggleGroup(lib) {
  const set = new Set(expandedLibs.value);
  if (set.has(lib)) set.delete(lib); else set.add(lib);
  expandedLibs.value = set;
}

function libIcon(name) {
  const n = name || '';
  if (n.includes('番') || n.includes('动漫') || n.includes('动画')) return 'mdi-television-classic'
  if (n.includes('剧') || n.includes('TV')) return 'mdi-movie-open-outline'
  if (n.includes('电影') || n.includes('影片')) return 'mdi-filmstrip'
  return 'mdi-folder-multiple-outline'
}

// v4.6.83：左栏条目图标按类型区分 —— 电影 / 剧集一眼可分（纯字体图标，零请求）。
function itemIcon(it) {
  const t = String(it?.item_type || '').trim().toLowerCase();
  if (['series', 'tvshow', 'tv', 'season', '剧', '电视剧', '番', '动漫', '动画'].includes(t)) {
    return 'mdi-television-classic'
  }
  return 'mdi-movie-outline'
}

async function selectItem(item) {
  selected.value = item;
  loadingPeople.value = true;
  people.value = [];
  itemMeta.value = null;
  posterData.value = null;
  logoData.value = null;
  libMainCast.value = [];
  libEpisodes.value = [];
  epLoadedCount.value = 0;
  editDlgOpen.value = false;
  loadPoster(item);
  loadLogo(item);
  try {
    const data = await api.get(props.api, '/db/people', { item_id: item.item_id, server_id: item.server_id || '' });
    if (selected.value !== item) return   // 已切到别的条目 → 丢弃旧响应（LIB-002）
    people.value = data?.people || [];
    itemMeta.value = data?.item || item;
    libMainCast.value = data?.main_cast || [];
    libEpisodes.value = data?.episodes || [];
    const _slist = Array.from(new Set(libEpisodes.value.map(e => e.season ?? 0))).sort((a, b) => a - b);
    epCurrentSeason.value = _slist.length ? _slist[0] : null;
    epLoadedCount.value = Math.min(EP_PAGE_SIZE,
      libEpisodes.value.filter(e => (e.season ?? 0) === epCurrentSeason.value).length);
  } catch (e) { if (selected.value === item) notify(e.message, 'error'); }
  if (selected.value !== item) return
  loadingPeople.value = false;
  await nextTick();
  setupEpObserver();
}

const libMainCast = ref$3([]);
const libEpisodes = ref$3([]);
const epLoadedCount = ref$3(0);
const epSentinel = ref$3(null);
const editDlgOpen = ref$3(false);
const editDlgForm = ref$3({});
const editDlgRoleScope = ref$3('single');
// v4.6.74（报告第十四节）：人名作用域 —— 默认「仅当前这一条」（不再默认全库同名）
const editDlgNameScope = ref$3('single');
const editDlgSaving = ref$3(false);
const editDlgOcc = ref$3({ count: 0, series: [] });
const editDlgSyncEmby = ref$3(false);
watch$2(editDlgOpen, (v) => { if (v) editDlgSyncEmby.value = false; });
const editDlgNameChanged = computed$3(() => {
  const f = editDlgForm.value || {};
  return !!(f.name_after && f.name_after !== f.name_before)
});

function isSeriesSelected() {
  return String(itemMeta.value?.item_type || selected.value?.item_type || '').toLowerCase() === 'series'
}
const epVisible = computed$3(() => epSeasonEps.value.slice(0, epLoadedCount.value));
const epAllLoaded = computed$3(() => epLoadedCount.value >= epSeasonEps.value.length);

const epSeasonMap = computed$3(() => {
  const map = new Map();
  for (const ep of libEpisodes.value) {
    const s = ep.season ?? 0;
    if (!map.has(s)) map.set(s, []);
    map.get(s).push(ep);
  }
  // v4.6.75（规范 §十一/§二-2）：季内按集号数字排序（接口顺序不保证 E01 在前）
  for (const list of map.values()) list.sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0));
  return map
});
const epSeasons = computed$3(() =>
  Array.from(epSeasonMap.value.entries())
    .map(([season, list]) => ({ season, count: list.length }))
    // v4.6.75（规范 §二-2）：季序按**数字**排序 —— S1 / S2 / S3 / S10 / S20，
    // 不再出现 S1、S10、S2 这种字符串序（Map 插入序不可靠）。
    .sort((a, b) => a.season - b.season)
);
const epMultiSeason = computed$3(() => epSeasons.value.length > 1);
const epCurrentSeason = ref$3(null);
const epSeasonEps = computed$3(() => epSeasonMap.value.get(epCurrentSeason.value) || []);
const epPanelRef = ref$3(null);
function selectSeason(s) {
  epCurrentSeason.value = s;
  // v4.6.75（规范 §二-3/§十一-9）：重置该季懒加载计数 + 重建观察器（旧 Observer 先销毁），
  // 避免上一季的加载状态污染下一季；并把视图滚回「本季开头（E01）」。
  epLoadedCount.value = Math.min(EP_PAGE_SIZE, (epSeasonMap.value.get(s) || []).length);
  nextTick(() => {
    setupEpObserver();
    try { epPanelRef.value?.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { /* 忽略 */ }
  });
}
// 季内面板标题只显示 E01（季号已在标签上，避免 S1E01 重复）；单季平铺仍用全标签
const epLabelShort = (ep) => (ep.episode != null ? `E${String(ep.episode).padStart(2, '0')}` : '—');
const epPanelLabel = (ep) => (epMultiSeason.value ? epLabelShort(ep) : epLabel(ep));
const epTitle = (ep) => String(ep.title || '').trim();

const epIsDeleted = (ep) => (ep.people || []).some(p => String(p.deleted_at || ''));
const epDeletedCountBySeason = computed$3(() => {
  const map = new Map();
  for (const ep of libEpisodes.value) {
    if (epIsDeleted(ep)) {
      const s = ep.season ?? 0;
      map.set(s, (map.get(s) || 0) + 1);
    }
  }
  return map
});
const epDeletedTotal = computed$3(() =>
  Array.from(epDeletedCountBySeason.value.values()).reduce((a, b) => a + b, 0));

async function refreshDetailSoft() {
  if (!selected.value || loadingPeople.value || editDlgOpen.value) return
  try {
    const data = await api.get(props.api, '/db/people', {
      item_id: selected.value.item_id, server_id: selected.value.server_id || '',
    });
    people.value = data?.people || [];
    libMainCast.value = data?.main_cast || [];
    libEpisodes.value = data?.episodes || [];
    const _cnt = (epSeasonMap.value.get(epCurrentSeason.value) || []).length;
    if (epLoadedCount.value > _cnt) epLoadedCount.value = _cnt;
  } catch (e) { /* 静默：刷新失败不影响浏览 */ }
}
let _epObserver = null;
function setupEpObserver() {
  teardownEpObserver();
  if (!epSentinel.value) return
  _epObserver = new IntersectionObserver((entries) => {
    if (entries.some(e => e.isIntersecting) && !epAllLoaded.value) loadMoreEps();
  }, { rootMargin: '200px' });
  _epObserver.observe(epSentinel.value);
}
function teardownEpObserver() {
  if (_epObserver) { _epObserver.disconnect(); _epObserver = null; }
}
function loadMoreEps() {
  if (epAllLoaded.value) return
  epLoadedCount.value = Math.min(epLoadedCount.value + EP_PAGE_SIZE, libEpisodes.value.length);
}
const isVoiceActor = (p) => {
  const t = String(p.type || '').toLowerCase();
  return t.includes('voice') || String(p.role_after || '').includes('配音')
};
// 稳定复合键（LIB-001/LIB-008）：条目 = 来源 + item_id；集 = 物理 nfo_path + 季集
const itemKey = (it) => (it ? `${it.server_id || ''}:${it.item_id || ''}` : '');
const epKey = (ep) => `${ep.nfo_path || ''}@s${ep.season ?? 0}e${ep.episode ?? 0}`;
const epLabel = (ep) => {
  const s = ep.season != null ? `S${ep.season}` : '';
  const e = ep.episode != null ? `E${String(ep.episode).padStart(2, '0')}` : '';
  return `${s}${e}`
};
function openEpEdit(p, ep) {
  const _t = String(itemMeta.value?.title || selected.value?.title || '');
  editDlgForm.value = {
    item_id: selected.value?.item_id || '', server_id: selected.value?.server_id || '',
    series_name: _t,
    name_before: p.name_before,
    name_after: p.name_after || p.name_before || '',
    name_after0: p.name_after || p.name_before || '',
    role_before: p.role_before || '',
    role_after: p.role_after || p.role_before || '',
    role_after0: p.role_after || p.role_before || '',
    season_num: ep?.season ?? null, episode_num: ep?.episode ?? null,
    index: p.index,
    role_level: ep ? 'ep' : 'tv',
    loc: ep ? `${_t || '该剧'} · ${epLabel(ep)}` : `${_t || '该剧'} · 剧级名单`,
  };
  editDlgRoleScope.value = ep ? 'single' : 'tv';
  editDlgNameScope.value = 'single';   // v4.6.74：人名默认只改当前这一条
  editDlgOpen.value = true;
  loadEditDlgOcc();
}
async function loadEditDlgOcc() {
  const nb = String(editDlgForm.value?.name_before || '').trim();
  editDlgOcc.value = { count: 0, series: [] };
  if (!nb) return
  try {
    const rows = (await api.get(props.api, '/db/person_occurrences', { name_before: nb })) || [];
    const series = [];
    for (const r of rows) {
      const s = String(r.series_name || r.title || '').trim();
      if (s && !series.includes(s)) series.push(s);
    }
    editDlgOcc.value = { count: rows.length, series };
  } catch (e) { /* 统计失败不影响编辑 */ }
}
function roleScopeHint() {
  const f = editDlgForm.value || {};
  const sc = editDlgRoleScope.value;
  if (sc === 'single') return `角色只改：${f.loc || '当前这一条'}`
  if (sc === 'season') return `角色改：${f.series_name || '该剧'} · 第 ${f.season_num ?? '?'} 季全部集`
  if (sc === 'tv') return `角色只改：${f.series_name || '该剧'} · 剧级名单`
  return `角色改：${f.series_name || '该剧'} 全剧（所有季的所有集）`
}
function nameScopeHint() {
  const f = editDlgForm.value || {};
  const sc = editDlgNameScope.value;
  if (sc === 'single') return `人名只改：${f.loc || '当前这一条'}（不影响其它作品里的同名人物）`
  if (sc === 'series') return `人名改：${f.series_name || '该作品'} 内所有季/集的同名人物（不影响其它作品）`
  return `人名改：全库所有作品里的同名人物 —— 可能包含不同真人，请确认后再保存`
}
function nameScopeLabel() {
  return { single: '仅当前这一条', series: '该作品内同名', library: '全库同名' }[editDlgNameScope.value] || editDlgNameScope.value
}
async function saveEditDialog() {
  if (editDlgSaving.value) return
  await loadStatus();   // v4.6.70：保存前刷新任务状态 —— 若期间后台起了翻译/写回，统一守卫会拦截
  if (!guard.check('保存人工修改')) return
  const f = editDlgForm.value || {};
  const roleScope = editDlgRoleScope.value;
  const _n0 = String(f.name_after0 ?? '').trim();
  const _r0 = String(f.role_after0 ?? '').trim();
  const _na = String(f.name_after ?? '').trim();
  const _ra = String(f.role_after ?? '').trim();
  const _nb = String(f.name_before ?? '').trim();
  // v4.6.53：与「打开弹窗时的现有值」比较（而非与原文比较）——
  // 这样「把译名改回与原文相同 / 留空」也是合法修改（= 清除错译、恢复原文）
  const nameChanged = _na !== _n0;
  const roleChanged = _ra !== _r0;
  if (!nameChanged && !roleChanged) { notify('没有需要修改的内容', 'warning'); return }
  const nameIsRestore = nameChanged && (_na === '' || _na === _nb);
  if (nameChanged && !nameIsRestore) {
    // v4.6.74（报告第十四节）：人名默认只改当前人物身份；「全库同名」必须主动选择 + 危险确认
    const _sc = editDlgNameScope.value;
    const _cnt = editDlgOcc.value?.count || 0;
    const _shows = (editDlgOcc.value?.series || []).length;
    const _syncTxt = editDlgSyncEmby.value ? '，并同步到 Emby（同一演员的所有作品一起变）' : '；不改 Emby，仅改本插件库';
    if (_sc === 'library') {
      if (!await askConfirm({
        title: '修改人名（全库同名 · 危险）',
        text: `将把「${f.name_before}」改成「${f.name_after}」：会影响全库所有作品里的同名人物 —— 库中同名共 ${_cnt || '?'} 处${_shows ? `（${_shows} 部作品）` : ''}${_syncTxt}。`,
        detail: '这会修改所有同名人物，可能包含不同真人。如果你只想改这一个（或这一部作品），请把上方「范围」改成「仅当前这一条」或「该作品内同名」。',
        okText: '我确认，全库修改',
        color: 'error',
      })) return
    } else if (!await askConfirm({
      title: `修改人名（${nameScopeLabel()}）`,
      text: `将把「${f.name_before}」改成「${f.name_after}」（范围：${nameScopeLabel()}）${_syncTxt}。`,
      detail: '只影响所选范围；其它作品里的同名人物不会被改动。',
      okText: '确认修改',
      color: 'warning',
    })) return
  }
  editDlgSaving.value = true;
  try {
    const r = await api.post(props.api, '/db/update_person_scope', {
      item_id: f.item_id, server_id: f.server_id,
      name_before: f.name_before, name_after: f.name_after,
      name_scope: nameChanged ? editDlgNameScope.value : 'single',
      role_before: f.role_before, role_after: f.role_after,
      role_scope: roleChanged ? roleScope : 'single',
      season_num: f.season_num, episode_num: f.episode_num, index: f.index,
      sync_emby: !!editDlgSyncEmby.value,
      name_force: nameChanged, role_force: roleChanged,
    });
    notify(r?.message || '已更新', 'success');
    editDlgOpen.value = false;
    if (occKey.value) { const _k = occKey.value; occKey.value = ''; await toggleOcc({ name_before: _k }); }
    if (searchMode.value) searchPeople();
    await refreshDetailSoft();
    loadItems(true);
    emit('action');
  } catch (e) { notify((e && e.message) || '保存失败', 'error'); } finally { editDlgSaving.value = false; }
}

// v4.6.70（报告第二十~三十四节）：第二排角色跨集复用的「记忆」唯一清除入口 ——
// 删除/恢复/清空翻译记录都不会清记忆（洗版重建仍复用旧译文），只有这里会。
const roleMemBusy = ref$3(false);
async function clearRoleMemory() {
  const f = editDlgForm.value || {};
  const _iid = String(f.item_id || '').trim();
  const _sn = String(f.series_name || '').trim();
  if (!_iid && !_sn) { notify('无法定位该剧（缺条目 ID / 剧名）', 'warning'); return }
  await loadStatus();
  if (!guard.check('清除该剧角色翻译记忆')) return
  if (!await askConfirm({
    title: '清除该剧角色翻译记忆',
    text: `清除「${_sn || _iid}」的第二排角色翻译记忆？`,
    detail: '清除后该剧各集的角色名需要重新翻译（重新消耗 AI）。注意：删除/恢复/清空翻译记录都不会清记忆，只有这里会。',
    okText: '清除',
    color: 'error',
  })) return
  roleMemBusy.value = true;
  try {
    const r = await api.post(props.api, '/db/role_memory/clear',
                             { item_id: _iid, series_name: _sn, server_id: f.server_id || '' });
    notify(r?.message || '已清除该剧角色翻译记忆', 'success');
  } catch (e) { notify((e && e.message) || '清除失败', 'error'); } finally { roleMemBusy.value = false; }
}

async function loadPoster(item) {
  try {
    const r = await api.get(props.api, '/poster', { item_id: item.item_id, server_id: item.server_id || '', kind: 'Primary' });
    if (selected.value !== item) return   // 旧响应不得覆盖新选中项（LIB-002）
    if (r) posterData.value = r;
  } catch (e) { if (selected.value === item) posterData.value = null; }
}
async function loadLogo(item) {
  try {
    const r = await api.get(props.api, '/poster', { item_id: item.item_id, server_id: item.server_id || '', kind: 'Logo' });
    if (selected.value !== item) return
    if (r) logoData.value = r;
  } catch (e) { if (selected.value === item) logoData.value = null; }
}

const personSearch = ref$3('');
// v4.6.106（LIB-012）：搜索范围 —— item=仅当前条目（默认，安全）/ all=全库搜索。
// 用户实测：此前只发 keyword、不带条目身份，后端落到「全库搜索」分支，
// 于是「在本剧名单里筛人」实际扫了全库、串到别的剧。现默认锁在当前条目，要全库时手动切。
const personSearchScope = ref$3('item');
const SEARCH_SCOPES = [
  { title: '本条目', value: 'item' },
  { title: '全库', value: 'all' },
];
const searchResults = ref$3([]);
const searchingPeople = ref$3(false);
let personSearchTimer = null;
const searchMode = computed$3(() => (personSearch.value || '').trim().length > 0);
let searchSeq = 0;
async function searchPeople() {
  const kw = (personSearch.value || '').trim();
  if (!kw) { searchResults.value = []; return }
  if (personSearchScope.value !== 'all' && !selected.value) { searchResults.value = []; return }
  const seq = ++searchSeq;
  searchingPeople.value = true;
  try {
    // v4.6.106（LIB-012）：本条目范围带上 item_id / server_id → 后端只在该条目名单里筛；
    // 全库范围保持旧行为（不带条目身份）。两种范围返回同构的「汇总行」，渲染完全一致。
    const params = (personSearchScope.value === 'all')
      ? { keyword: kw }
      : { keyword: kw, item_id: selected.value?.item_id || '', server_id: selected.value?.server_id || '' };
    const data = await api.get(props.api, '/db/people', params);
    if (seq !== searchSeq) return   // 快速输入时只有最后一次结果生效（LIB-004）
    searchResults.value = data?.people || [];
  } catch (e) { if (seq === searchSeq) searchResults.value = []; }
  finally { if (seq === searchSeq) searchingPeople.value = false; }
}
function onPersonSearchInput() {
  clearTimeout(personSearchTimer);
  personSearchTimer = setTimeout(searchPeople, 350);
}
// v4.6.106（LIB-012）：切换搜索范围立即重搜（关键词非空时），否则结果与所选范围对不上
function onSearchScopeChange() {
  if (searchMode.value) searchPeople();
  else searchResults.value = [];
}
function clearPersonSearch() { personSearch.value = ''; searchResults.value = []; }
function openGlobalEdit(row) {
  editDlgForm.value = {
    item_id: '', server_id: '',
    series_name: '',
    name_before: row.name_before,
    name_after: row.name_after || row.name_before || '',
    name_after0: row.name_after || row.name_before || '',
    role_before: '', role_after: '',
    season_num: null, episode_num: null, index: null,
    role_level: 'tv',
    loc: `全库汇总（${row.count || 0} 处）`,
  };
  editDlgRoleScope.value = 'series';
  // v4.6.74：这是「全库同名汇总行」——本身就代表全库，默认即全库同名（弹窗内标红警告）
  editDlgNameScope.value = 'library';
  // 汇总行自带出现次数与剧集列表，直接用（省一次请求）
  editDlgOcc.value = { count: row.count || 0, series: row.series || [] };
  editDlgOpen.value = true;
}

const occKey = ref$3('');          // 当前展开出现清单的原文名
const occRows = ref$3([]);
const occLoading = ref$3(false);

async function toggleOcc(row) {
  const key = String(row.name_before || '');
  if (occKey.value === key) { occKey.value = ''; occRows.value = []; return }
  occKey.value = key;
  occRows.value = [];
  occLoading.value = true;
  try {
    // v4.6.106（LIB-012）：「本条目」范围下出现清单同样限定在该条目内（与搜索范围同口径）
    const _p = (personSearchScope.value === 'all')
      ? { name_before: key }
      : { name_before: key, item_id: selected.value?.item_id || '',
          server_id: selected.value?.server_id || '' };
    occRows.value = (await api.get(props.api, '/db/person_occurrences', _p)) || [];
  } catch (e) { notify((e && e.message) || '读取出现清单失败', 'error'); } finally { occLoading.value = false; }
}
function occLabel(r) {
  const s = String(r.series_name || r.title || '').trim();
  const _lv = String(r.item_type || '') === 'Movie' ? '本片名单' : '本剧名单';
  const se = (r.season_num == null && r.episode_num == null)
    ? _lv
    : `S${r.season_num ?? '?'}E${String(r.episode_num ?? '?').padStart(2, '0')}`;
  return `${s || '（条目）'} · ${se}${r.deleted_at ? '（待恢复）' : ''}`
}
function openOccEdit(r) {
  const _isMovie = String(r.item_type || '') === 'Movie';
  const _isTv = !_isMovie && (r.season_num == null && r.episode_num == null);
  editDlgForm.value = {
    item_id: r.item_id, server_id: r.server_id || '',
    series_name: String(r.series_name || r.title || '').trim(),
    name_before: r.name_before, name_after: r.name_after || r.name_before,
    name_after0: r.name_after || r.name_before,
    role_before: r.role_before || '', role_after: r.role_after || r.role_before || '',
    role_after0: r.role_after || r.role_before || '',
    season_num: r.season_num ?? null, episode_num: r.episode_num ?? null, index: r.index,
    role_level: _isMovie ? 'movie' : (_isTv ? 'tv' : 'ep'),
    loc: occLabel(r),
  };
  editDlgRoleScope.value = _isMovie ? 'single' : (_isTv ? 'tv' : 'single');
  editDlgNameScope.value = 'single';   // v4.6.74：人名默认只改当前这一条
  editDlgOpen.value = true;
  loadEditDlgOcc();
}
function openMovieEdit(row) {
  const _t = String(itemMeta.value?.title || selected.value?.title || '');
  editDlgForm.value = {
    item_id: selected.value?.item_id || '', server_id: selected.value?.server_id || '',
    series_name: _t,
    name_before: row.name_before,
    name_after: row.name_after || row.name_before || '',
    name_after0: row.name_after || row.name_before || '',
    role_before: row.role_before || '',
    role_after: row.role_after || row.role_before || '',
    role_after0: row.role_after || row.role_before || '',
    season_num: null, episode_num: null, index: null,
    role_level: 'movie',
    loc: `${_t || '该条目'} · 本片名单`,
  };
  editDlgRoleScope.value = 'single';
  editDlgNameScope.value = 'single';   // v4.6.74：人名默认只改当前这一条
  editDlgOpen.value = true;
  loadEditDlgOcc();
}

const dbBusy = ref$3('');
async function clearDb() {
  if (!guard.check('清空翻译记录')) return   // v4.6.70：统一守卫
  if (!await askConfirm({
    title: '清空全部翻译记录',
    text: '确认清空全部翻译记录？',
    detail: '此操作不可恢复：只清空翻译记录与写回队列；人名池（含人工修正）保留不受影响，下次扫描会直接用池内译文重建记录，基本不重复消耗 AI 额度。如需清人名池请去「人名池」页。',
    okText: '清空',
    color: 'error',
  })) return
  dbBusy.value = 'clear';
  try {
    const r = await api.post(props.api, '/db/clear');
    notify(r?.message || '已清空', 'success');
    selected.value = null; people.value = [];
    loadItems(); emit('action');
  } catch (e) { notify((e && e.message) || '清空失败', 'error'); } finally { dbBusy.value = ''; }
}
async function exportDb() {
  dbBusy.value = 'export';
  try {
    // client.js unwrap 已解出 data（数组），不能再取 .data
    const r = await api.get(props.api, '/db/export');
    const rows = Array.isArray(r) ? r : [];
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `embypeople_export_${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
    notify(`已导出 ${rows.length} 条记录`, 'success');
  } catch (e) { notify((e && e.message) || '导出失败', 'error'); } finally { dbBusy.value = ''; }
}
ref$3(null);
function onImportPick(e) {
  const f = e.target.files && e.target.files[0];
  if (!f) return
  if (!guard.check('导入翻译记录')) { e.target.value = ''; return }   // v4.6.70：统一守卫
  const reader = new FileReader();
  reader.onload = async () => {
    dbBusy.value = 'import';
    try {
      let rows;
      try { rows = JSON.parse(reader.result); } catch (_) { throw new Error('文件不是有效 JSON') }
      if (!Array.isArray(rows)) rows = rows?.records || rows?.rows || [];
      const r = await api.post(props.api, '/db/import', { rows });
      notify(r?.message || '导入完成', 'success');
      loadItems(); emit('action');
    } catch (err) { notify((err && err.message) || '导入失败', 'error'); } finally { dbBusy.value = ''; e.target.value = ''; }
  };
  reader.readAsText(f);
}
async function delItem(node) {
  if (dbBusy.value === 'del') return
  if (!guard.check('删除翻译记录')) return   // v4.6.70：统一守卫（此前只看 is_running）
  if (!await askConfirm({
    title: '删除翻译记录',
    text: `删除「${node.item.title}」的翻译记录？`,
    detail: '该条目（含各集）的翻译记录将被删除；人名池保留（下次扫描同名命中可直接复用）。',
    okText: '删除',
    color: 'error',
  })) return
  dbBusy.value = 'del';
  try {
    const r = await api.post(props.api, '/db/delete', { item_id: node.item.item_id, server_id: node.item.server_id || '' });
    notify(r?.message || '已删除', 'success');
    if (itemKey(selected.value) && itemKey(selected.value) === itemKey(node.item)) { selected.value = null; people.value = []; }
    loadItems();
  } catch (e) { notify((e && e.message) || '删除失败', 'error'); } finally { dbBusy.value = ''; }
}
const retranslating = ref$3(false);
function isApiItem() {
  return !!selected.value?.server_id
}
const writeBackLabel = () => isApiItem() ? '恢复到 Emby' : '写入';
const writeBackTooltip = () => isApiItem()
  ? '把库中翻译后名单写回 Emby（API 模式）'
  : '两排写入文件；第一排再写入服务器';
async function writeBackItem() {
  if (!selected.value) return
  await loadStatus();   // v4.6.70：单条写回同样过统一守卫
  if (!guard.check('写入（当前条目）')) return
  try {
    const r = await api.post(props.api, '/db/restore', { item_id: selected.value.item_id, server_id: selected.value.server_id || '' });
    notify(r?.message || '写回完成', 'success');
    selectItem(selected.value);
  } catch (e) { notify((e && e.message) || '写回失败', 'error'); }
}
async function retranslateItem() {
  if (!selected.value || retranslating.value) return
  await loadStatus();   // v4.6.70：拉最新任务状态后交给统一守卫（此前只看 is_running）
  if (!guard.check('重新翻译（当前条目）')) return
  // 与「全部翻译」一致：先弹窗确认本次翻译范围（第一排/第二排/两排）
  await openTranslateDlg('item');
}
const rescanning = ref$3(false);
async function rescanItem() {
  if (!selected.value || rescanning.value) return
  await loadStatus();   // v4.6.70：同上 —— 重扫会改库数据，必须过统一守卫
  if (!guard.check('重新拉取（重扫当前条目）')) return
  rescanning.value = true;
  try {
    const r = await api.post(props.api, '/db/rescan_item', { item_id: selected.value.item_id, server_id: selected.value.server_id || '' });
    notify(r?.message || '已重新拉取（重扫这一条）', 'success');
    selectItem(selected.value);
    loadItems();
  } catch (e) { notify((e && e.message) || '重新拉取失败', 'error'); } finally { rescanning.value = false; }
}
const autoWriteback = ref$3(false);
// v4.6.75（规范 §五-1/§五-5）：任务「运行中 → 结束」跳变检测 —— 结束瞬间立即刷新详情与统计，
// 此前只靠 30s 定时器，会出现「翻译已完成但界面仍显示未翻译」。
let _wasTaskRunning = false;
// v4.6.104（LIB-009）：库数据版本号（后端 db_rev，只在 person 表写入时自增）。
// 用户诉求：「有数据更新才刷新，没更新干嘛要刷新」——左侧列表不再按固定周期重拉，
// 改由 8s 的状态轮询带回 items_rev，**只有版本号变了才 loadItems(true)**。
let _lastItemsRev = null;
async function loadStatus() {
  try {
    const st = await api.get(props.api, '/status');
    // v4.6.70：统一任务守卫同步（扫描 / 翻译 / 写回 / 人名池 / 探测库 + 常驻翻译 worker 许可）
    guard.loadStatus(st);
    // v4.6.104（LIB-009）：变更检测 —— 没写库就一个字节都不重拉
    const _rev = (st && st.items_rev != null) ? String(st.items_rev) : '';
    if (_rev && _rev !== _lastItemsRev) {
      if (_lastItemsRev !== null) loadItems(true);   // 首帧列表已由 startPoll 拉过，不重复
      _lastItemsRev = _rev;
    }
    autoWriteback.value = !!st?.auto_writeback;
    const _run = !!(st?.tasks?.translate || st?.tasks?.writeback
                    || (st?.tx && (st.tx.requested || st.tx.running))
                    || st?.translate_status?.running);
    if (_wasTaskRunning && !_run) {
      // 翻译/写回刚结束 → 立即重读最新状态（数据库已更新；不等下一次轮询）
      refreshDetailSoft();
      loadTxPreview(true);
      loadItems(true);
      if (pendingDlg.value) loadPendingDetail(true);
    }
    _wasTaskRunning = _run;
  } catch (e) {}
}
// v4.6.70：改由统一守卫提供（此前只看 is_running，漏了常驻翻译 worker 与写回/池/探测）
const dataOpBlocked = computed$3(() => guard.lock.value);
const dataOpBlockedHint = computed$3(() => guard.hint.value);

const txDlg = ref$3(false);
const txMode = ref$3('library');   // library=全部翻译 / item=重新翻译当前条目
const txBusy = ref$3(false);
const txScope = ref$3('default');   // default=使用设置默认 / person=只翻第一排 / role=只翻第二排 / both=两排都翻
const txPreview = ref$3({ names_pending: 0, roles_pending: 0, names_scope: 0, roles_scope: 0, items_pending: 0, pending_items: [], person_enabled: true, role_enabled: true, loading: false, loaded: false });
const TX_SCOPE_LABEL = { default: '使用设置默认', person: '只翻第一排人物姓名', role: '只翻第二排角色', both: '两排都翻' };
const txScopeLabel = computed$3(() => {
  if (txScope.value === 'default') {
    const _p = txPreview.value.person_enabled, _r = txPreview.value.role_enabled;
    if (_p && _r) return '使用设置默认（第一排 + 第二排）'
    if (_p && !_r) return '使用设置默认（仅第一排）'
    if (!_p && _r) return '使用设置默认（仅第二排）'
    return '使用设置默认（当前设置未开启任何翻译目标）'
  }
  return TX_SCOPE_LABEL[txScope.value] || '使用设置默认'
});
// 「到底是哪个」：把待翻条目标题拼成一行（超 8 条截断并注明总数）
const pendingItemsText = computed$3(() => {
  const _list = txPreview.value.pending_items || [];
  if (!_list.length) return ''
  const _names = _list.map((it) => (it && (it.title || it.item_id)) || '').filter(Boolean);
  const _head = _names.slice(0, 8).join('、');
  return _names.length > 8 ? `${_head} 等共 ${_names.length} 个` : _head
});
let _txPreviewInflight = false;
async function loadTxPreview(silent = false) {
  if (_txPreviewInflight) return
  _txPreviewInflight = true;
  if (!silent) txPreview.value = { ...txPreview.value, loading: true };
  try {
    const r = await api.get(props.api, '/db/translate_preview', _previewQuery());
    txPreview.value = {
      names_pending: r?.names_pending ?? 0,
      roles_pending: r?.roles_pending ?? 0,
      names_scope: r?.names_scope ?? 0,
      roles_scope: r?.roles_scope ?? 0,
      items_pending: r?.items_pending ?? 0,
      pending_items: Array.isArray(r?.pending_items) ? r.pending_items : [],
      // v4.6.61（P1-7）：写回状态独立统计 —— 翻译完成 ≠ 写回完成
      writeback_pending: r?.writeback_pending ?? 0,
      writeback_failed: r?.writeback_failed ?? 0,
      person_enabled: r?.person_enabled !== false,
      role_enabled: r?.role_enabled !== false,
      loading: false, loaded: true,
    };
  } catch (e) {
    txPreview.value = { ...txPreview.value, loading: false, loaded: true };
    if (!silent) notify((e && e.message) || '预估失败', 'error');
  } finally {
    _txPreviewInflight = false;
  }
}
// 弹窗预估：按「本次选的排」+ 设置页总开关，算出「待翻 / 符合范围」各多少
const txEstimate = computed$3(() => {
  const p = txPreview.value;
  const sc = txScope.value;
  const wantP = sc === 'person' || sc === 'both' || (sc === 'default' && p.person_enabled);
  const wantR = sc === 'role' || sc === 'both' || (sc === 'default' && p.role_enabled);
  const names = wantP ? Number(p.names_pending || 0) : 0;
  const roles = wantR ? Number(p.roles_pending || 0) : 0;
  const namesScope = wantP ? Number(p.names_scope || 0) : 0;
  const rolesScope = wantR ? Number(p.roles_scope || 0) : 0;
  return { wantP, wantR, names, roles, namesScope, rolesScope,
           pending: names + roles, scope: namesScope + rolesScope }
});

// 「有任务 · 待翻译」点开后的明细
const pendingDlg = ref$3(false);
const pendingBusy = ref$3(false);
const pendingData = ref$3({ items: [], items_total: 0, names_pending: 0, roles_pending: 0,
                          names_scope: 0, roles_scope: 0, person_on: true, role_on: true });
async function loadPendingDetail (silent = false) {
  if (!silent) pendingBusy.value = true;
  try {
    const r = await api.get(props.api, '/db/pending_detail', { limit_items: 30, terms_per_item: 12 });
    if (r && Array.isArray(r.items)) pendingData.value = r;
  } catch (e) { if (!silent) notify((e && e.message) || '读取待翻译明细失败', 'error'); }
  if (!silent) pendingBusy.value = false;
}
async function openPendingDlg () {
  pendingDlg.value = true;
  await loadPendingDetail(false);
}
// 预估口径：弹窗打开且为「重新翻译」时按当前条目统计；否则按全库（角标/轮询用全库）
function _previewQuery() {
  if (txDlg.value && txMode.value === 'item' && selected.value) {
    return { item_id: selected.value.item_id, server_id: selected.value.server_id || '' }
  }
  return {}
}
async function openTranslateDlg(mode = 'library') {
  // v4.6.70：发起翻译前统一守卫（条目级重翻已在上游 retranslateItem 校验过，这里兜底）
  await loadStatus();
  if (!guard.check(mode === 'item' ? '重新翻译（当前条目）' : '全部翻译')) return
  txMode.value = mode;
  txScope.value = 'default';
  txDlg.value = true;
  await loadTxPreview();
}
async function confirmTranslate() {
  if (txBusy.value) return
  txBusy.value = true;
  try {
    const _scope = txScope.value === 'default' ? 'both' : txScope.value;
    let r;
    if (txMode.value === 'item' && selected.value) {
      r = await api.post(props.api, '/db/retranslate', {
        item_id: selected.value.item_id,
        server_id: selected.value.server_id || '',
        target_scope: _scope,
      });
    } else {
      r = await api.post(props.api, '/db/translate_library', { target_scope: _scope });
    }
    notify(r?.message || '已启动（后台执行）', r?.success === false ? 'error' : 'success');
    txDlg.value = false;
    if (txMode.value === 'item' && selected.value) { selectItem(selected.value); loadItems(); }
    loadTxPreview(true);
  } catch (e) { notify((e && e.message) || '启动失败', 'error'); } finally { txBusy.value = false; }
}
const writebackBusy = ref$3(false);
async function writebackAll() {
  await loadStatus();   // v4.6.70：写回期间禁止再发起（也禁止其它修改型操作）
  if (!guard.check('全部写回')) return
  if (!await askConfirm({
    title: '全部写回 nfo',
    text: '把库中全部条目的已翻译名单批量写回 nfo 文件？',
    detail: '不重新翻译，只落盘；.bak 备份按设置自动保留。',
    okText: '写回',
    color: 'warning',
  })) return
  writebackBusy.value = true;
  try {
    const r = await api.post(props.api, '/db/writeback_all');
    notify(r?.message || '全部写回已启动（后台执行）', 'success');
    loadTxPreview(true);
  } catch (e) { notify((e && e.message) || '启动失败', 'error'); } finally { writebackBusy.value = false; }
}

const isNarrow = ref$3(false);
function _syncNarrow() { try { isNarrow.value = window.innerWidth <= 600; } catch (e) { isNarrow.value = false; } }


const TYPE_LABEL = { Actor: '演员', Director: '导演', Writer: '编剧', Producer: '制片人', VoiceActor: '声优', GuestStar: '客串', Composer: '作曲', Cinematographer: '摄影', Editor: '剪辑' };
// v4.6.97：分集名单 / 主演员名单也「按类型分段」（与电影页同款）——
// 此前平铺只显示「名字 + 饰 角色」，看不出哪个是导演/编剧（用户实测困惑）。
// 类型来自 nfo：<actor> 的 <type>（缺省或 Actor = 演员；显式 GuestStar = 客串），
// <director> = 导演、<writer> = 编剧、<credits> = 制片人
// ——「只有 nfo 明确写客串才算客串，其余都算演员」。
const TYPE_ORDER = ['Actor', 'VoiceActor', 'GuestStar', 'Director', 'Writer', 'Producer',
                    'Composer', 'Cinematographer', 'Editor'];
function typeLabel(t) { return TYPE_LABEL[t] || t || '演员' }
function typeIcon(t) {
  if (t === 'Director') return 'mdi-video-outline'
  if (t === 'Writer') return 'mdi-pencil-outline'
  if (t === 'Producer') return 'mdi-briefcase-outline'
  if (t === 'GuestStar') return 'mdi-account-arrow-right-outline'
  if (t === 'VoiceActor') return 'mdi-microphone-outline'
  return 'mdi-account'
}
// 按类型分组（保序：先 TYPE_ORDER，未知类型按出现顺序追加）→ [{type,label,list}]
function groupByType(list) {
  const map = new Map();
  for (const p of (list || [])) {
    const t = (p && p.type) || 'Actor';
    if (!map.has(t)) map.set(t, []);
    map.get(t).push(p);
  }
  const out = [];
  for (const t of TYPE_ORDER) {
    if (map.has(t)) { out.push({ type: t, label: typeLabel(t), list: map.get(t) }); map.delete(t); }
  }
  for (const [t, l] of map) out.push({ type: t, label: typeLabel(t), list: l });
  return out
}
const mainCastGroups = computed$3(() => groupByType(libMainCast.value));

function srcTag(p) {
  if (p.season_num == null) return '本剧'
  return `S${p.season_num}E${p.episode_num}`
}
const summaryGroups = computed$3(() => {
  const groups = [];
  const idx = {};
  for (const p of people.value) {
    const t = p.type || 'Actor';
    if (!(t in idx)) {
      idx[t] = groups.length;
      groups.push({ type: t, label: TYPE_LABEL[t] || t, list: [] });
    }
    groups[idx[t]].list.push(p);
  }
  for (const g of groups) {
    const byName = new Map();
    for (const p of g.list) {
      // 身份键（UI-009）：以「原文 + 角色」为身份，绝不以译名为键
      // —— 否则两个不同原文被译成同字时会被错误合并成一行
      const key = `${p.name_before || p.name_after || ''}\u0001${p.role_before || p.role_after || ''}`;
      let row = byName.get(key);
      if (!row) {
        row = {
          name_before: p.name_before || '',
          name_after: p.name_after || '',
          role_before: p.role_before || '',
          role_after: p.role_after || '',
          srcs: [],
          befores: [],
        };
        byName.set(key, row);
      }
      if (p.name_before && !row.befores.includes(p.name_before)) row.befores.push(p.name_before);
      // 展示用原文：优先取「与译文不同」的真实原文（剧级中文原文被集级原文覆盖显示）
      if (p.name_before && p.name_after && p.name_before !== p.name_after) {
        row.name_before = p.name_before;
        if (p.role_before) row.role_before = p.role_before;
      }
      const tag = srcTag(p);
      if (!row.srcs.includes(tag)) row.srcs.push(tag);
      if (p.name_after && p.name_after !== p.name_before) row.name_after = p.name_after;
      if (p.role_after && p.role_after !== p.role_before) row.role_after = p.role_after;
    }
    const rows = [...byName.values()];
    for (const r of rows) {
      r.srcs.sort((a, b) => (a === '本剧' ? -1 : b === '本剧' ? 1 : a.localeCompare(b)));
    }
    g.list = rows;
  }
  return groups
});
const summaryTotal = computed$3(() => summaryGroups.value.reduce((n, g) => n + g.list.length, 0));


let pollTimer = null;
let detailTimer = null;
// v4.6.104（LIB-008/009）：列表不再按固定周期重拉。
// 用户反馈①：列表每 8s 全量刷一次观感很差（「页面拉一下」）；
// 用户反馈②：「有数据更新才刷新，没数据更新干嘛要刷新」。
// 现改为**事件驱动**：只有 ①items_rev 变化（真的写库了，见 loadStatus）②任务结束跳变
// ③用户操作（增删改/翻译/导入）④切回前台 —— 才拉列表。状态与统计徽章仍保持 8s（要跟手）。
function startPoll() {
  stopPoll();
  loadItems(true);
  loadStatus();
  loadTxPreview(true);
  // v4.6.60（P1-1）：明细弹窗打开时随轮询一起刷新 —— 此前只在打开时拉一次，
  // 后台翻译完成后弹窗仍显示旧的 3 条（要关掉重开才更新）
  pollTimer = setInterval(() => {
    if (document.hidden) return          // v4.6.104：页面在后台不轮询（省请求；切回来立即补一次）
    loadStatus();                         // 列表刷新由 loadStatus 里的 items_rev 变更检测触发
    loadTxPreview(true);
    if (pendingDlg.value) loadPendingDetail(true);
  }, FAST_POLL_MS);
  detailTimer = setInterval(refreshDetailSoft, 30000);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (detailTimer) { clearInterval(detailTimer); detailTimer = null; }
}
// v4.6.104：从后台切回前台立即补一次（否则最长要等 30s 才看到新数据）
function _onDocVisible() {
  if (document.hidden) return
  loadItems(true); loadStatus(); loadTxPreview(true);
}
onMounted$3(() => {
  startPoll(); _syncNarrow();
  window.addEventListener('resize', _syncNarrow);
  document.addEventListener('visibilitychange', _onDocVisible);
});
onActivated$2(startPoll);
onDeactivated$1(stopPoll);
onBeforeUnmount$1(() => {
  stopPoll(); teardownEpObserver(); teardownItemObserver();
  window.removeEventListener('resize', _syncNarrow);
  document.removeEventListener('visibilitychange', _onDocVisible);
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$3("v-icon");
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_tooltip = _resolveComponent$3("v-tooltip");
  const _component_v_chip = _resolveComponent$3("v-chip");
  const _component_v_list_item = _resolveComponent$3("v-list-item");
  const _component_v_list = _resolveComponent$3("v-list");
  const _component_v_menu = _resolveComponent$3("v-menu");
  const _component_v_text_field = _resolveComponent$3("v-text-field");
  const _component_v_btn_toggle = _resolveComponent$3("v-btn-toggle");
  const _component_v_divider = _resolveComponent$3("v-divider");
  const _component_v_progress_linear = _resolveComponent$3("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$3("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$3("v-list-item-subtitle");
  const _component_v_progress_circular = _resolveComponent$3("v-progress-circular");
  const _component_v_card_text = _resolveComponent$3("v-card-text");
  const _component_v_card = _resolveComponent$3("v-card");
  const _component_v_col = _resolveComponent$3("v-col");
  const _component_v_img = _resolveComponent$3("v-img");
  const _component_v_select = _resolveComponent$3("v-select");
  const _component_v_avatar = _resolveComponent$3("v-avatar");
  const _component_v_expansion_panel = _resolveComponent$3("v-expansion-panel");
  const _component_v_expansion_panels = _resolveComponent$3("v-expansion-panels");
  const _component_v_card_title = _resolveComponent$3("v-card-title");
  const _component_v_alert = _resolveComponent$3("v-alert");
  const _component_v_checkbox = _resolveComponent$3("v-checkbox");
  const _component_v_spacer = _resolveComponent$3("v-spacer");
  const _component_v_card_actions = _resolveComponent$3("v-card-actions");
  const _component_v_dialog = _resolveComponent$3("v-dialog");
  const _component_v_row = _resolveComponent$3("v-row");
  const _component_v_radio = _resolveComponent$3("v-radio");
  const _component_v_radio_group = _resolveComponent$3("v-radio-group");

  return (_openBlock$3(), _createElementBlock$3("div", _hoisted_1$3, [
    _createElementVNode$3("div", _hoisted_2$3, [
      _createVNode$3(_component_v_tooltip, {
        text: dataOpBlockedHint.value || '批量翻译库中未译词条（可选本次翻译范围：第一排/第二排；只写库，自动写回开启时条目翻完自动落盘，否则点「全部写回」）',
        location: "top"
      }, {
        activator: _withCtx$3(({ props: tp }) => [
          _createVNode$3(_component_v_btn, _mergeProps$1({
            size: "small",
            color: "primary",
            variant: "tonal"
          }, tp, {
            loading: txBusy.value,
            disabled: dataOpBlocked.value,
            onClick: openTranslateDlg
          }), {
            default: _withCtx$3(() => [
              _createVNode$3(_component_v_icon, {
                start: "",
                size: "16"
              }, {
                default: _withCtx$3(() => [...(_cache[21] || (_cache[21] = [
                  _createTextVNode$3("mdi-translate", -1)
                ]))]),
                _: 1
              }),
              _cache[22] || (_cache[22] = _createTextVNode$3("全部翻译 ", -1))
            ]),
            _: 1
          }, 16, ["loading", "disabled"])
        ]),
        _: 1
      }, 8, ["text"]),
      (!autoWriteback.value)
        ? (_openBlock$3(), _createBlock$3(_component_v_tooltip, {
            key: 0,
            text: dataOpBlockedHint.value || '把库中已翻译名单批量写回 nfo 文件（不重新翻译）',
            location: "top"
          }, {
            activator: _withCtx$3(({ props: tp }) => [
              _createVNode$3(_component_v_btn, _mergeProps$1({
                size: "small",
                color: "success",
                variant: "tonal"
              }, tp, {
                loading: writebackBusy.value,
                disabled: dataOpBlocked.value,
                onClick: writebackAll
              }), {
                default: _withCtx$3(() => [
                  _createVNode$3(_component_v_icon, {
                    start: "",
                    size: "16"
                  }, {
                    default: _withCtx$3(() => [...(_cache[23] || (_cache[23] = [
                      _createTextVNode$3("mdi-file-import-outline", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[24] || (_cache[24] = _createTextVNode$3("全部写回 ", -1))
                ]),
                _: 1
              }, 16, ["loading", "disabled"])
            ]),
            _: 1
          }, 8, ["text"]))
        : _createCommentVNode$3("", true),
      _createElementVNode$3("div", _hoisted_3$3, [
        _createVNode$3(_component_v_tooltip, {
          text: "导出全部翻译记录为 JSON",
          location: "top"
        }, {
          activator: _withCtx$3(({ props: tp }) => [
            _createVNode$3(_component_v_btn, _mergeProps$1({
              size: "small",
              variant: "tonal"
            }, tp, {
              loading: dbBusy.value==='export',
              onClick: exportDb
            }), {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  start: "",
                  size: "16"
                }, {
                  default: _withCtx$3(() => [...(_cache[25] || (_cache[25] = [
                    _createTextVNode$3("mdi-export-variant", -1)
                  ]))]),
                  _: 1
                }),
                _cache[26] || (_cache[26] = _createTextVNode$3("导出 ", -1))
              ]),
              _: 1
            }, 16, ["loading"])
          ]),
          _: 1
        }),
        _createVNode$3(_component_v_tooltip, {
          text: dataOpBlockedHint.value || '从 JSON 导入翻译记录',
          location: "top"
        }, {
          activator: _withCtx$3(({ props: tp }) => [
            _createVNode$3(_component_v_btn, _mergeProps$1({
              size: "small",
              variant: "tonal"
            }, tp, {
              disabled: dataOpBlocked.value,
              loading: dbBusy.value==='import',
              onClick: _cache[0] || (_cache[0] = $event => (_ctx.$refs.importInput?.click()))
            }), {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  start: "",
                  size: "16"
                }, {
                  default: _withCtx$3(() => [...(_cache[27] || (_cache[27] = [
                    _createTextVNode$3("mdi-import", -1)
                  ]))]),
                  _: 1
                }),
                _cache[28] || (_cache[28] = _createTextVNode$3("导入 ", -1))
              ]),
              _: 1
            }, 16, ["disabled", "loading"])
          ]),
          _: 1
        }, 8, ["text"]),
        _createVNode$3(_component_v_tooltip, {
          text: dataOpBlockedHint.value || '清空全部翻译记录（不可恢复；人名池保留）',
          location: "top"
        }, {
          activator: _withCtx$3(({ props: tp }) => [
            _createVNode$3(_component_v_btn, _mergeProps$1({
              size: "small",
              variant: "tonal",
              color: "error"
            }, tp, {
              disabled: dataOpBlocked.value,
              loading: dbBusy.value==='clear',
              onClick: clearDb
            }), {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  start: "",
                  size: "16"
                }, {
                  default: _withCtx$3(() => [...(_cache[29] || (_cache[29] = [
                    _createTextVNode$3("mdi-delete-sweep-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[30] || (_cache[30] = _createTextVNode$3("清空 ", -1))
              ]),
              _: 1
            }, 16, ["disabled", "loading"])
          ]),
          _: 1
        }, 8, ["text"])
      ]),
      _createVNode$3(_component_v_tooltip, {
        location: "top",
        "max-width": "420",
        text: txPreview.value.loaded
          ? (txPreview.value.items_pending > 0
              ? `待翻译统计：${txPreview.value.items_pending} 个条目未翻完（第一排 ${txPreview.value.names_pending} 词条 · 第二排 ${txPreview.value.roles_pending} 词条）${pendingItemsText.value ? '：' + pendingItemsText.value : ''}`
              : '待翻译统计：所有条目均已翻译完成')
          : '待翻译统计加载中…'
      }, {
        activator: _withCtx$3(({ props: tp }) => [
          _createVNode$3(_component_v_chip, _mergeProps$1(tp, {
            size: "small",
            variant: "tonal",
            link: "",
            class: "epl-pending-chip",
            onClick: openPendingDlg,
            color: !txPreview.value.loaded ? 'grey' : (txPreview.value.items_pending > 0 ? 'warning' : 'success'),
            "prepend-icon": !txPreview.value.loaded ? 'mdi-progress-question' : (txPreview.value.items_pending > 0 ? 'mdi-alert-circle-outline' : 'mdi-check-circle-outline')
          }), {
            default: _withCtx$3(() => [
              (!txPreview.value.loaded)
                ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_4$3, "统计中…"))
                : (txPreview.value.items_pending > 0)
                  ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                      _cache[31] || (_cache[31] = _createElementVNode$3("span", { class: "epl-pending-prefix" }, "有任务 · 待翻译 ", -1)),
                      _createTextVNode$3(_toDisplayString$3(txPreview.value.items_pending) + " 个", 1)
                    ], 64))
                  : (_openBlock$3(), _createElementBlock$3("span", _hoisted_5$3, "无待翻译"))
            ]),
            _: 1
          }, 16, ["color", "prepend-icon"])
        ]),
        _: 1
      }, 8, ["text"]),
      _createVNode$3(_component_v_tooltip, {
        location: "top",
        "max-width": "440",
        text: txPreview.value.loaded
          ? (txPreview.value.writeback_pending > 0
              ? `写回统计：${txPreview.value.writeback_pending} 个条目已翻译但尚未写入 NFO（翻译完成 ≠ 写回完成）。自动写回开启时会自动落盘；未开启请点「全部写回」${txPreview.value.writeback_failed ? '；其中写入失败 ' + txPreview.value.writeback_failed + ' 个（将自动重试）' : ''}`
              : '写回统计：所有已翻译条目都已写入 NFO')
          : '写回统计加载中…'
      }, {
        activator: _withCtx$3(({ props: tp }) => [
          _createVNode$3(_component_v_chip, _mergeProps$1(tp, {
            size: "small",
            variant: "tonal",
            color: !txPreview.value.loaded ? 'grey' : (txPreview.value.writeback_pending > 0 ? 'info' : 'success'),
            "prepend-icon": !txPreview.value.loaded ? 'mdi-progress-question' : (txPreview.value.writeback_pending > 0 ? 'mdi-content-save-move-outline' : 'mdi-check-circle-outline')
          }), {
            default: _withCtx$3(() => [
              (!txPreview.value.loaded)
                ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_6$3, "写回统计中…"))
                : (txPreview.value.writeback_pending > 0)
                  ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                      _createTextVNode$3("待写回 " + _toDisplayString$3(txPreview.value.writeback_pending) + " 个", 1)
                    ], 64))
                  : (_openBlock$3(), _createElementBlock$3("span", _hoisted_7$3, "无待写回"))
            ]),
            _: 1
          }, 16, ["color", "prepend-icon"])
        ]),
        _: 1
      }, 8, ["text"]),
      _createElementVNode$3("input", {
        ref: "importInput",
        type: "file",
        accept: ".json,application/json",
        style: {"display":"none"},
        onChange: onImportPick
      }, null, 544),
      _createVNode$3(_component_v_menu, {
        location: "bottom end",
        class: "d-md-none"
      }, {
        activator: _withCtx$3(({ props: mp }) => [
          _createVNode$3(_component_v_btn, _mergeProps$1({
            size: "small",
            variant: "tonal"
          }, mp, { class: "d-md-none" }), {
            default: _withCtx$3(() => [
              _cache[33] || (_cache[33] = _createTextVNode$3(" 更多", -1)),
              _createVNode$3(_component_v_icon, {
                end: "",
                size: "16"
              }, {
                default: _withCtx$3(() => [...(_cache[32] || (_cache[32] = [
                  _createTextVNode$3("mdi-chevron-down", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          }, 16)
        ]),
        default: _withCtx$3(() => [
          _createVNode$3(_component_v_list, { density: "compact" }, {
            default: _withCtx$3(() => [
              _createVNode$3(_component_v_list_item, {
                "prepend-icon": "mdi-export-variant",
                title: "导出翻译记录（JSON）",
                disabled: dbBusy.value==='export',
                onClick: exportDb
              }, null, 8, ["disabled"]),
              _createVNode$3(_component_v_list_item, {
                "prepend-icon": "mdi-import",
                title: dataOpBlockedHint.value || '导入翻译记录（JSON）',
                disabled: dbBusy.value==='import' || dataOpBlocked.value,
                onClick: _cache[1] || (_cache[1] = $event => (_ctx.$refs.importInput?.click()))
              }, null, 8, ["title", "disabled"]),
              _createVNode$3(_component_v_list_item, {
                "prepend-icon": "mdi-delete-sweep-outline",
                title: dataOpBlockedHint.value || '清空全部翻译记录（不可恢复；人名池保留）',
                disabled: dbBusy.value==='clear' || dataOpBlocked.value,
                "base-color": "error",
                onClick: clearDb
              }, null, 8, ["title", "disabled"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _cache[34] || (_cache[34] = _createElementVNode$3("div", { class: "epl-topbar-right" }, null, -1))
    ]),
    _createVNode$3(_component_v_row, {
      "no-gutters": "",
      class: "epl-lib-row"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_col, {
          cols: "12",
          md: "5"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "epl-card-bg epl-list-card epl-flex-card" }, {
              default: _withCtx$3(() => [
                _createElementVNode$3("div", _hoisted_8$3, [
                  _createElementVNode$3("div", _hoisted_9$3, [
                    _createVNode$3(_component_v_text_field, {
                      modelValue: search.value,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((search).value = $event)),
                      placeholder: "搜索剧集 / 电影标题…",
                      density: "compact",
                      variant: "outlined",
                      "hide-details": "",
                      clearable: "",
                      "prepend-inner-icon": "mdi-magnify",
                      class: "epl-sidebar-search"
                    }, null, 8, ["modelValue"]),
                    _createVNode$3(_component_v_btn_toggle, {
                      modelValue: filterType.value,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((filterType).value = $event)),
                      density: "compact",
                      variant: "tonal",
                      color: "primary",
                      mandatory: "",
                      size: "small"
                    }, {
                      default: _withCtx$3(() => [
                        _createVNode$3(_component_v_btn, { value: "" }, {
                          default: _withCtx$3(() => [...(_cache[35] || (_cache[35] = [
                            _createTextVNode$3("全部", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode$3(_component_v_btn, { value: "Series" }, {
                          default: _withCtx$3(() => [...(_cache[36] || (_cache[36] = [
                            _createTextVNode$3("剧集", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode$3(_component_v_btn, { value: "Movie" }, {
                          default: _withCtx$3(() => [...(_cache[37] || (_cache[37] = [
                            _createTextVNode$3("电影", -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }, 8, ["modelValue"])
                  ])
                ]),
                _createVNode$3(_component_v_divider, { style: {"opacity":".3"} }),
                _createVNode$3(_component_v_card_text, { class: "pa-0 epl-col-body" }, {
                  default: _withCtx$3(() => [
                    (loadingList.value)
                      ? (_openBlock$3(), _createBlock$3(_component_v_progress_linear, {
                          key: 0,
                          indeterminate: "",
                          color: "primary"
                        }))
                      : _createCommentVNode$3("", true),
                    (!loadingList.value && !visibleNodes.value.length)
                      ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_10$3, "暂无翻译记录"))
                      : (_openBlock$3(), _createBlock$3(_component_v_list, {
                          key: 2,
                          density: "compact",
                          class: "pa-0",
                          nav: ""
                        }, {
                          default: _withCtx$3(() => [
                            (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(visibleNodes.value, (node) => {
                              return (_openBlock$3(), _createElementBlock$3(_Fragment$3, {
                                key: node.type + ':' + (itemKey(node.item) || node.lib)
                              }, [
                                (node.type === 'group')
                                  ? (_openBlock$3(), _createBlock$3(_component_v_list_item, {
                                      key: 0,
                                      class: "epl-group-item",
                                      onClick: $event => (toggleGroup(node.lib))
                                    }, {
                                      prepend: _withCtx$3(() => [
                                        _createVNode$3(_component_v_icon, {
                                          size: "16",
                                          class: "mr-1"
                                        }, {
                                          default: _withCtx$3(() => [
                                            _createTextVNode$3(_toDisplayString$3(expandedLibs.value.has(node.lib) ? 'mdi-chevron-down' : 'mdi-chevron-right'), 1)
                                          ]),
                                          _: 2
                                        }, 1024),
                                        _createVNode$3(_component_v_icon, {
                                          size: "14",
                                          color: "info",
                                          class: "mr-1"
                                        }, {
                                          default: _withCtx$3(() => [
                                            _createTextVNode$3(_toDisplayString$3(libIcon(node.lib)), 1)
                                          ]),
                                          _: 2
                                        }, 1024)
                                      ]),
                                      append: _withCtx$3(() => [
                                        _createElementVNode$3("span", _hoisted_11$2, _toDisplayString$3(node.count), 1)
                                      ]),
                                      default: _withCtx$3(() => [
                                        _createVNode$3(_component_v_list_item_title, { class: "epl-group-name" }, {
                                          default: _withCtx$3(() => [
                                            _createTextVNode$3(_toDisplayString$3(node.lib), 1)
                                          ]),
                                          _: 2
                                        }, 1024)
                                      ]),
                                      _: 2
                                    }, 1032, ["onClick"]))
                                  : (_openBlock$3(), _createBlock$3(_component_v_list_item, {
                                      key: 1,
                                      active: itemKey(selected.value) === itemKey(node.item),
                                      class: _normalizeClass$2(["epl-item", { 'epl-item-dead': node.item.deleted_at, 'epl-item-partdead': !node.item.deleted_at && node.item.deleted_eps > 0 }]),
                                      style: _normalizeStyle({ paddingLeft: (node.depth * 6 + 16) + 'px' }),
                                      onClick: $event => (selectItem(node.item))
                                    }, {
                                      prepend: _withCtx$3(() => [
                                        _createVNode$3(_component_v_icon, {
                                          size: "22",
                                          color: "grey",
                                          class: "epl-thumb-placeholder"
                                        }, {
                                          default: _withCtx$3(() => [
                                            _createTextVNode$3(_toDisplayString$3(itemIcon(node.item)), 1)
                                          ]),
                                          _: 2
                                        }, 1024)
                                      ]),
                                      append: _withCtx$3(() => [
                                        _createVNode$3(_component_v_btn, {
                                          size: "x-small",
                                          variant: "text",
                                          color: "error",
                                          onClick: _withModifiers$1($event => (delItem(node)), ["stop"])
                                        }, {
                                          default: _withCtx$3(() => [
                                            _createVNode$3(_component_v_icon, { size: "16" }, {
                                              default: _withCtx$3(() => [...(_cache[41] || (_cache[41] = [
                                                _createTextVNode$3("mdi-close", -1)
                                              ]))]),
                                              _: 1
                                            })
                                          ]),
                                          _: 1
                                        }, 8, ["onClick"])
                                      ]),
                                      default: _withCtx$3(() => [
                                        _createVNode$3(_component_v_list_item_title, {
                                          class: "epl-item-name",
                                          title: node.item.title
                                        }, {
                                          default: _withCtx$3(() => [
                                            _createTextVNode$3(_toDisplayString$3(node.item.title) + " ", 1),
                                            (node.item.deleted_at)
                                              ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                                  key: 0,
                                                  size: "x-small",
                                                  color: "error",
                                                  variant: "flat",
                                                  class: "ml-1"
                                                }, {
                                                  default: _withCtx$3(() => [
                                                    _createVNode$3(_component_v_icon, {
                                                      start: "",
                                                      size: "12"
                                                    }, {
                                                      default: _withCtx$3(() => [...(_cache[38] || (_cache[38] = [
                                                        _createTextVNode$3("mdi-progress-clock", -1)
                                                      ]))]),
                                                      _: 1
                                                    }),
                                                    _cache[39] || (_cache[39] = _createTextVNode$3("待恢复 ", -1))
                                                  ]),
                                                  _: 1
                                                }))
                                              : (node.item.deleted_eps > 0)
                                                ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                                    key: 1,
                                                    size: "x-small",
                                                    color: "warning",
                                                    variant: "flat",
                                                    class: "ml-1",
                                                    title: "部分集被服务器删除，观察期内重新入库自动恢复；超期自动清理（不会一直显示）"
                                                  }, {
                                                    default: _withCtx$3(() => [
                                                      _createVNode$3(_component_v_icon, {
                                                        start: "",
                                                        size: "12"
                                                      }, {
                                                        default: _withCtx$3(() => [...(_cache[40] || (_cache[40] = [
                                                          _createTextVNode$3("mdi-progress-clock", -1)
                                                        ]))]),
                                                        _: 1
                                                      }),
                                                      _createTextVNode$3(_toDisplayString$3(node.item.deleted_eps) + " 集待恢复 ", 1)
                                                    ]),
                                                    _: 2
                                                  }, 1024))
                                                : _createCommentVNode$3("", true)
                                          ]),
                                          _: 2
                                        }, 1032, ["title"]),
                                        _createVNode$3(_component_v_list_item_subtitle, { class: "epl-item-meta" }, {
                                          default: _withCtx$3(() => [
                                            _createTextVNode$3(_toDisplayString$3(node.item.item_type) + " · " + _toDisplayString$3(node.item.person_count) + " 人 ", 1),
                                            (node.item.episode_count)
                                              ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                  _createTextVNode$3(" · " + _toDisplayString$3(node.item.episode_count) + " 集", 1)
                                                ], 64))
                                              : _createCommentVNode$3("", true)
                                          ]),
                                          _: 2
                                        }, 1024)
                                      ]),
                                      _: 2
                                    }, 1032, ["active", "class", "style", "onClick"]))
                              ], 64))
                            }), 128))
                          ]),
                          _: 1
                        })),
                    (itemHasMore.value)
                      ? (_openBlock$3(), _createElementBlock$3("div", {
                          key: 3,
                          ref_key: "itemSentinel",
                          ref: itemSentinel,
                          class: "epl-load-sentinel"
                        }, [
                          _createVNode$3(_component_v_progress_circular, {
                            indeterminate: "",
                            size: "20",
                            class: "my-2"
                          })
                        ], 512))
                      : (!loadingList.value && items.value.length)
                        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_12$2, [...(_cache[42] || (_cache[42] = [
                            _createElementVNode$3("span", { class: "epl-cast-hint" }, "— 已全部加载 —", -1)
                          ]))]))
                        : _createCommentVNode$3("", true)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode$3(_component_v_col, {
          cols: "12",
          md: "7"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "epl-card-bg epl-detail-card epl-flex-card" }, {
              default: _withCtx$3(() => [
                (selected.value)
                  ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_13$2, [
                      _createElementVNode$3("div", _hoisted_14$2, [
                        _createElementVNode$3("div", _hoisted_15$2, [
                          (posterData.value || itemMeta.value?.poster_url)
                            ? (_openBlock$3(), _createBlock$3(_component_v_img, {
                                key: 0,
                                src: posterData.value || itemMeta.value.poster_url,
                                width: "64",
                                height: "92",
                                cover: "",
                                class: "epl-poster"
                              }, null, 8, ["src"]))
                            : (_openBlock$3(), _createBlock$3(_component_v_icon, {
                                key: 1,
                                size: "40",
                                color: "grey"
                              }, {
                                default: _withCtx$3(() => [...(_cache[43] || (_cache[43] = [
                                  _createTextVNode$3("mdi-movie-outline", -1)
                                ]))]),
                                _: 1
                              }))
                        ]),
                        _createElementVNode$3("div", _hoisted_16$2, [
                          _createElementVNode$3("div", {
                            class: "epl-detail-title",
                            title: itemMeta.value?.title || selected.value.title
                          }, _toDisplayString$3(itemMeta.value?.title || selected.value.title), 9, _hoisted_17$2),
                          (logoData.value)
                            ? (_openBlock$3(), _createBlock$3(_component_v_img, {
                                key: 0,
                                src: logoData.value,
                                "max-width": "180",
                                "max-height": "40",
                                contain: "",
                                class: "mb-1 epl-logo"
                              }, null, 8, ["src"]))
                            : _createCommentVNode$3("", true),
                          _createElementVNode$3("div", _hoisted_18$2, [
                            _createTextVNode$3(_toDisplayString$3(itemMeta.value?.item_type || selected.value.item_type) + " · 名单 " + _toDisplayString$3(summaryTotal.value) + " 人 / 全部 " + _toDisplayString$3(people.value.length) + " 条 ", 1),
                            (itemMeta.value?.episode_count)
                              ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                  _createTextVNode$3(" · " + _toDisplayString$3(itemMeta.value.episode_count) + " 集", 1)
                                ], 64))
                              : _createCommentVNode$3("", true)
                          ])
                        ]),
                        _createElementVNode$3("div", _hoisted_19$2, [
                          _createVNode$3(_component_v_tooltip, {
                            text: "重新翻译当前条目（先弹窗选范围：第一排/第二排/两排；只翻这一条，不扫全库）",
                            location: "top"
                          }, {
                            activator: _withCtx$3(({ props: tp }) => [
                              _createVNode$3(_component_v_btn, _mergeProps$1({
                                size: "small",
                                variant: "tonal",
                                color: "warning"
                              }, tp, {
                                loading: retranslating.value,
                                disabled: _ctx.running,
                                onClick: retranslateItem
                              }), {
                                default: _withCtx$3(() => [
                                  _createVNode$3(_component_v_icon, {
                                    start: "",
                                    size: "18"
                                  }, {
                                    default: _withCtx$3(() => [...(_cache[44] || (_cache[44] = [
                                      _createTextVNode$3("mdi-refresh-circle", -1)
                                    ]))]),
                                    _: 1
                                  }),
                                  _cache[45] || (_cache[45] = _createTextVNode$3("重新翻译 ", -1))
                                ]),
                                _: 1
                              }, 16, ["loading", "disabled"])
                            ]),
                            _: 1
                          }),
                          _createVNode$3(_component_v_tooltip, {
                            text: writeBackTooltip(),
                            location: "top"
                          }, {
                            activator: _withCtx$3(({ props: tp }) => [
                              _createVNode$3(_component_v_btn, _mergeProps$1({
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, tp, {
                                disabled: _ctx.running,
                                onClick: writeBackItem
                              }), {
                                default: _withCtx$3(() => [
                                  _createVNode$3(_component_v_icon, {
                                    start: "",
                                    size: "18"
                                  }, {
                                    default: _withCtx$3(() => [
                                      _createTextVNode$3(_toDisplayString$3(isApiItem() ? 'mdi-restore' : 'mdi-file-import-outline'), 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createTextVNode$3(_toDisplayString$3(writeBackLabel()), 1)
                                ]),
                                _: 1
                              }, 16, ["disabled"])
                            ]),
                            _: 1
                          }, 8, ["text"]),
                          _createVNode$3(_component_v_tooltip, {
                            text: "只重扫当前这一条：按本地 NFO 重新采集名单（更新原文/层级/人数，保留已有译文），不翻译、不写文件、不扫全库",
                            location: "left"
                          }, {
                            activator: _withCtx$3(({ props: tp }) => [
                              _createVNode$3(_component_v_btn, _mergeProps$1({
                                size: "small",
                                color: "teal",
                                variant: "tonal"
                              }, tp, {
                                loading: rescanning.value,
                                disabled: _ctx.running,
                                onClick: rescanItem
                              }), {
                                default: _withCtx$3(() => [
                                  _createVNode$3(_component_v_icon, {
                                    start: "",
                                    size: "18"
                                  }, {
                                    default: _withCtx$3(() => [...(_cache[46] || (_cache[46] = [
                                      _createTextVNode$3("mdi-file-refresh-outline", -1)
                                    ]))]),
                                    _: 1
                                  }),
                                  _cache[47] || (_cache[47] = _createTextVNode$3("重新拉取 ", -1))
                                ]),
                                _: 1
                              }, 16, ["loading", "disabled"])
                            ]),
                            _: 1
                          })
                        ])
                      ])
                    ]))
                  : _createCommentVNode$3("", true),
                (selected.value)
                  ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_20$2, [
                      _createElementVNode$3("div", _hoisted_21$2, [
                        _createVNode$3(_component_v_text_field, {
                          modelValue: personSearch.value,
                          "onUpdate:modelValue": [
                            _cache[4] || (_cache[4] = $event => ((personSearch).value = $event)),
                            onPersonSearchInput
                          ],
                          placeholder: "🔍 搜索人物（原文名 / 译文 / 角色）…",
                          density: "compact",
                          variant: "outlined",
                          "hide-details": "",
                          clearable: "",
                          "prepend-inner-icon": "mdi-account-search-outline",
                          class: "flex-grow-1",
                          style: {"min-width":"0"},
                          "onClick:clear": clearPersonSearch
                        }, null, 8, ["modelValue"]),
                        _createVNode$3(_component_v_select, {
                          modelValue: personSearchScope.value,
                          "onUpdate:modelValue": [
                            _cache[5] || (_cache[5] = $event => ((personSearchScope).value = $event)),
                            onSearchScopeChange
                          ],
                          items: SEARCH_SCOPES,
                          "item-title": "title",
                          "item-value": "value",
                          density: "compact",
                          variant: "outlined",
                          "hide-details": "",
                          style: {"max-width":"104px","flex":"0 0 auto"}
                        }, null, 8, ["modelValue"])
                      ])
                    ]))
                  : _createCommentVNode$3("", true),
                _createVNode$3(_component_v_divider, { style: {"opacity":".3"} }),
                _createVNode$3(_component_v_card_text, { class: "pa-0 epl-col-body" }, {
                  default: _withCtx$3(() => [
                    (searchMode.value)
                      ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                          (searchingPeople.value)
                            ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_22$2, [
                                _createVNode$3(_component_v_progress_circular, {
                                  indeterminate: "",
                                  size: "22",
                                  color: "primary"
                                }),
                                _cache[48] || (_cache[48] = _createTextVNode$3(" 搜索中…", -1))
                              ]))
                            : (!searchResults.value.length)
                              ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_23$2, [
                                  (personSearchScope.value === 'all')
                                    ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                        _createTextVNode$3("全库未找到匹配人物（换个关键词试试）")
                                      ], 64))
                                    : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                        _createTextVNode$3("本条目未找到匹配人物（换个关键词，或把搜索范围切到「全库」）")
                                      ], 64))
                                ]))
                              : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 2 }, [
                                  _createElementVNode$3("div", _hoisted_24$2, [
                                    _createVNode$3(_component_v_icon, {
                                      size: "15",
                                      class: "mr-1"
                                    }, {
                                      default: _withCtx$3(() => [...(_cache[49] || (_cache[49] = [
                                        _createTextVNode$3("mdi-account-search-outline", -1)
                                      ]))]),
                                      _: 1
                                    }),
                                    _createTextVNode$3("人物搜索结果：" + _toDisplayString$3(searchResults.value.length) + " 个名字 ", 1),
                                    (personSearchScope.value === 'all')
                                      ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                          key: 0,
                                          size: "x-small",
                                          color: "warning",
                                          variant: "tonal",
                                          class: "ml-1"
                                        }, {
                                          default: _withCtx$3(() => [...(_cache[50] || (_cache[50] = [
                                            _createTextVNode$3("全库 · 含其他作品", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                      : (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                          key: 1,
                                          size: "x-small",
                                          variant: "tonal",
                                          class: "ml-1"
                                        }, {
                                          default: _withCtx$3(() => [...(_cache[51] || (_cache[51] = [
                                            _createTextVNode$3("仅本条目", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                  ]),
                                  _createVNode$3(_component_v_list, {
                                    density: "compact",
                                    class: "pa-0",
                                    nav: ""
                                  }, {
                                    default: _withCtx$3(() => [
                                      (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(searchResults.value, (row, i) => {
                                        return (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: i }, [
                                          _createVNode$3(_component_v_list_item, { class: "epl-person-search-item" }, {
                                            prepend: _withCtx$3(() => [
                                              _createVNode$3(_component_v_avatar, {
                                                size: "30",
                                                color: "rgba(128,128,128,.2)",
                                                class: "mr-2"
                                              }, {
                                                default: _withCtx$3(() => [
                                                  _createVNode$3(_component_v_icon, { size: "16" }, {
                                                    default: _withCtx$3(() => [
                                                      _createTextVNode$3(_toDisplayString$3(row.type === 'Director' ? 'mdi-video-outline' : row.type === 'Writer' ? 'mdi-pencil-outline' : 'mdi-account'), 1)
                                                    ]),
                                                    _: 2
                                                  }, 1024)
                                                ]),
                                                _: 2
                                              }, 1024)
                                            ]),
                                            default: _withCtx$3(() => [
                                              _createElementVNode$3("div", _hoisted_25$2, [
                                                _createElementVNode$3("div", _hoisted_26$2, [
                                                  _createElementVNode$3("span", {
                                                    class: _normalizeClass$2(["epl-new", { 'epl-same': !row.name_after || row.name_after === row.name_before }])
                                                  }, _toDisplayString$3(row.name_after || row.name_before || '—'), 3),
                                                  (row.name_after && row.name_before && row.name_after !== row.name_before)
                                                    ? (_openBlock$3(), _createElementBlock$3("s", _hoisted_27$2, _toDisplayString$3(row.name_before), 1))
                                                    : _createCommentVNode$3("", true),
                                                  _createVNode$3(_component_v_btn, {
                                                    size: "x-small",
                                                    variant: "text",
                                                    icon: "",
                                                    class: "epl-edit-btn",
                                                    title: "编辑译文（弹窗里选范围）",
                                                    onClick: $event => (openGlobalEdit(row))
                                                  }, {
                                                    default: _withCtx$3(() => [
                                                      _createVNode$3(_component_v_icon, { size: "14" }, {
                                                        default: _withCtx$3(() => [...(_cache[52] || (_cache[52] = [
                                                          _createTextVNode$3("mdi-pencil-outline", -1)
                                                        ]))]),
                                                        _: 1
                                                      })
                                                    ]),
                                                    _: 1
                                                  }, 8, ["onClick"])
                                                ]),
                                                _createElementVNode$3("div", _hoisted_28$2, [
                                                  (row.role_after || row.role_before)
                                                    ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                        _createTextVNode$3("饰 " + _toDisplayString$3(row.role_after || row.role_before), 1)
                                                      ], 64))
                                                    : _createCommentVNode$3("", true),
                                                  _createVNode$3(_component_v_chip, {
                                                    size: "x-small",
                                                    variant: "tonal",
                                                    class: "ml-1 epl-occ-toggle",
                                                    title: occKey.value === String(row.name_before || '') ? '收起出现清单' : '展开出现清单（逐处编辑）',
                                                    onClick: _withModifiers$1($event => (toggleOcc(row)), ["stop"])
                                                  }, {
                                                    default: _withCtx$3(() => [
                                                      _createTextVNode$3(_toDisplayString$3(row.count) + " 处 " + _toDisplayString$3(occKey.value === String(row.name_before || '') ? '▴' : '▾'), 1)
                                                    ]),
                                                    _: 2
                                                  }, 1032, ["title", "onClick"]),
                                                  (row.series && row.series.length)
                                                    ? (_openBlock$3(), _createElementBlock$3("span", {
                                                        key: 1,
                                                        class: "epl-src-tags",
                                                        title: row.series.join(' / ')
                                                      }, _toDisplayString$3(row.series.join('、').slice(0, 24)), 9, _hoisted_29$2))
                                                    : _createCommentVNode$3("", true)
                                                ])
                                              ])
                                            ]),
                                            _: 2
                                          }, 1024),
                                          (occKey.value === String(row.name_before || ''))
                                            ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_30$2, [
                                                (occLoading.value)
                                                  ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_31$2, "加载出现清单…"))
                                                  : (!occRows.value.length)
                                                    ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_32$2, "无出现记录"))
                                                    : (_openBlock$3(true), _createElementBlock$3(_Fragment$3, { key: 2 }, _renderList$3(occRows.value, (r, j) => {
                                                        return (_openBlock$3(), _createElementBlock$3("div", {
                                                          key: j,
                                                          class: "epl-occ-row"
                                                        }, [
                                                          _createElementVNode$3("span", {
                                                            class: "epl-occ-label",
                                                            title: occLabel(r)
                                                          }, _toDisplayString$3(occLabel(r)), 9, _hoisted_33$2),
                                                          _createVNode$3(_component_v_btn, {
                                                            icon: "mdi-pencil",
                                                            size: "x-small",
                                                            variant: "text",
                                                            class: "epl-edit-btn",
                                                            onClick: $event => (openOccEdit(r))
                                                          }, null, 8, ["onClick"])
                                                        ]))
                                                      }), 128))
                                              ]))
                                            : _createCommentVNode$3("", true)
                                        ], 64))
                                      }), 128))
                                    ]),
                                    _: 1
                                  }),
                                  _createElementVNode$3("div", _hoisted_34$2, [
                                    (personSearchScope.value === 'all')
                                      ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                          _createTextVNode$3("当前范围「全库」：结果可能来自其他作品；")
                                        ], 64))
                                      : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                          _createTextVNode$3("当前范围「本条目」：只在本条目的名单里筛，「N 处」也只数本条目内的出现；")
                                        ], 64)),
                                    _cache[53] || (_cache[53] = _createTextVNode$3(" 按「原文名」汇总；点「N 处 ▾」展开出现清单可逐处编辑；铅笔（汇总行）= 全库同名改（弹窗里确认数量）；出现清单里的铅笔可选「仅这一处 / 该剧所有集 / 全库同名」。 ", -1))
                                  ])
                                ], 64))
                        ], 64))
                      : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                          (!selected.value)
                            ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_35$2, "点击左侧条目查看翻译前后名单"))
                            : (_openBlock$3(), _createElementBlock$3("div", _hoisted_36$2, [
                                (loadingPeople.value)
                                  ? (_openBlock$3(), _createBlock$3(_component_v_progress_circular, {
                                      key: 0,
                                      indeterminate: "",
                                      color: "primary",
                                      class: "ma-6"
                                    }))
                                  : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                      (!people.value.length)
                                        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_37$2, "该条目无人物记录（先扫描，或开「处理单集」收集各集）"))
                                        : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                            (isSeriesSelected())
                                              ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                  _createElementVNode$3("div", _hoisted_38$2, [
                                                    _createElementVNode$3("div", _hoisted_39$2, [
                                                      _createElementVNode$3("div", _hoisted_40$2, [
                                                        _createVNode$3(_component_v_icon, {
                                                          size: "18",
                                                          color: "primary"
                                                        }, {
                                                          default: _withCtx$3(() => [...(_cache[54] || (_cache[54] = [
                                                            _createTextVNode$3("mdi-account-star", -1)
                                                          ]))]),
                                                          _: 1
                                                        }),
                                                        _cache[55] || (_cache[55] = _createTextVNode$3(" 主演员 ", -1)),
                                                        _cache[56] || (_cache[56] = _createElementVNode$3("span", { class: "epl-cast-hint" }, "（来自 tvshow.nfo · 编辑时在弹窗里选范围）", -1))
                                                      ])
                                                    ]),
                                                    (libMainCast.value.length)
                                                      ? (_openBlock$3(true), _createElementBlock$3(_Fragment$3, { key: 0 }, _renderList$3(mainCastGroups.value, (grp) => {
                                                          return (_openBlock$3(), _createElementBlock$3("div", {
                                                            key: 'main-g-' + grp.type,
                                                            class: "epl-type-block"
                                                          }, [
                                                            (mainCastGroups.value.length > 1)
                                                              ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_41$2, [
                                                                  _createVNode$3(_component_v_icon, { size: "14" }, {
                                                                    default: _withCtx$3(() => [
                                                                      _createTextVNode$3(_toDisplayString$3(typeIcon(grp.type)), 1)
                                                                    ]),
                                                                    _: 2
                                                                  }, 1024),
                                                                  _createTextVNode$3(" " + _toDisplayString$3(grp.label), 1),
                                                                  _createElementVNode$3("span", _hoisted_42$2, _toDisplayString$3(grp.list.length), 1)
                                                                ]))
                                                              : _createCommentVNode$3("", true),
                                                            _createElementVNode$3("div", _hoisted_43$2, [
                                                              (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(grp.list, (p, i) => {
                                                                return (_openBlock$3(), _createElementBlock$3("div", {
                                                                  key: 'main-' + grp.type + '-' + i,
                                                                  class: _normalizeClass$2(["epl-actor-chip", { 'is-voice': isVoiceActor(p) }])
                                                                }, [
                                                                  _createElementVNode$3("div", _hoisted_44$2, [
                                                                    _createElementVNode$3("span", _hoisted_45$2, _toDisplayString$3(p.name_after || p.name_before), 1),
                                                                    (p.role_after || p.role_before)
                                                                      ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_46$2, "饰 " + _toDisplayString$3(p.role_after || p.role_before), 1))
                                                                      : _createCommentVNode$3("", true)
                                                                  ]),
                                                                  _createVNode$3(_component_v_btn, {
                                                                    icon: "mdi-pencil",
                                                                    size: "x-small",
                                                                    variant: "text",
                                                                    class: "epl-chip-edit",
                                                                    onClick: $event => (openEpEdit(p, null))
                                                                  }, null, 8, ["onClick"])
                                                                ], 2))
                                                              }), 128))
                                                            ])
                                                          ]))
                                                        }), 128))
                                                      : (_openBlock$3(), _createElementBlock$3("div", _hoisted_47$2, "（剧文件暂无主演记录，扫描完成后显示）"))
                                                  ]),
                                                  (libEpisodes.value.length)
                                                    ? (_openBlock$3(), _createElementBlock$3("div", {
                                                        key: 0,
                                                        ref_key: "epPanelRef",
                                                        ref: epPanelRef,
                                                        class: "epl-cast-section"
                                                      }, [
                                                        _createElementVNode$3("div", _hoisted_48$2, [
                                                          _createElementVNode$3("div", _hoisted_49$2, [
                                                            _createVNode$3(_component_v_icon, {
                                                              size: "18",
                                                              color: "primary"
                                                            }, {
                                                              default: _withCtx$3(() => [...(_cache[57] || (_cache[57] = [
                                                                _createTextVNode$3("mdi-television-classic", -1)
                                                              ]))]),
                                                              _: 1
                                                            }),
                                                            _cache[59] || (_cache[59] = _createTextVNode$3(" 分集演员 ", -1)),
                                                            _createElementVNode$3("span", _hoisted_50$2, [
                                                              _cache[58] || (_cache[58] = _createTextVNode$3("（", -1)),
                                                              (epMultiSeason.value)
                                                                ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                                    _createTextVNode$3("当前 S" + _toDisplayString$3(epCurrentSeason.value) + " · ", 1)
                                                                  ], 64))
                                                                : _createCommentVNode$3("", true),
                                                              _createTextVNode$3("已显示 " + _toDisplayString$3(epVisible.value.length) + " / " + _toDisplayString$3(epSeasonEps.value.length) + " 集，滚动到底自动加载）", 1)
                                                            ]),
                                                            (!epMultiSeason.value && epDeletedTotal.value)
                                                              ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_51$2, "（" + _toDisplayString$3(epDeletedTotal.value) + " 集待恢复）", 1))
                                                              : _createCommentVNode$3("", true)
                                                          ]),
                                                          _createElementVNode$3("div", _hoisted_52$2, [
                                                            (!epAllLoaded.value)
                                                              ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                                                  key: 0,
                                                                  size: "small",
                                                                  variant: "text",
                                                                  "prepend-icon": "mdi-chevron-double-down",
                                                                  onClick: loadMoreEps
                                                                }, {
                                                                  default: _withCtx$3(() => [...(_cache[60] || (_cache[60] = [
                                                                    _createTextVNode$3("加载更多", -1)
                                                                  ]))]),
                                                                  _: 1
                                                                }))
                                                              : _createCommentVNode$3("", true)
                                                          ])
                                                        ]),
                                                        (epMultiSeason.value)
                                                          ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_53$2, [
                                                              (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(epSeasons.value, (sg) => {
                                                                return (_openBlock$3(), _createBlock$3(_component_v_tooltip, {
                                                                  key: 'stab-' + sg.season,
                                                                  location: "top",
                                                                  text: (epDeletedCountBySeason.value.get(sg.season) || 0) > 0
                                            ? `本季 ${epDeletedCountBySeason.value.get(sg.season)} 集待恢复（服务器已删除，观察期内重新入库会自动恢复）`
                                            : `本季共 ${sg.count} 集`
                                                                }, {
                                                                  activator: _withCtx$3(({ props: tabProps }) => [
                                                                    _createElementVNode$3("button", _mergeProps$1({
                                                                      type: "button",
                                                                      class: ["epl-season-tab", { 'is-active': sg.season === epCurrentSeason.value, 'is-dead': (epDeletedCountBySeason.value.get(sg.season) || 0) > 0 }],
                                                                      "aria-pressed": sg.season === epCurrentSeason.value
                                                                    }, { ref_for: true }, tabProps, {
                                                                      onClick: $event => (selectSeason(sg.season))
                                                                    }), [
                                                                      ((epDeletedCountBySeason.value.get(sg.season) || 0) > 0)
                                                                        ? (_openBlock$3(), _createBlock$3(_component_v_icon, {
                                                                            key: 0,
                                                                            size: "12"
                                                                          }, {
                                                                            default: _withCtx$3(() => [...(_cache[61] || (_cache[61] = [
                                                                              _createTextVNode$3("mdi-alert-outline", -1)
                                                                            ]))]),
                                                                            _: 1
                                                                          }))
                                                                        : _createCommentVNode$3("", true),
                                                                      _createTextVNode$3(" S" + _toDisplayString$3(sg.season) + " ", 1),
                                                                      _createElementVNode$3("span", _hoisted_55$2, _toDisplayString$3(sg.count), 1)
                                                                    ], 16, _hoisted_54$2)
                                                                  ]),
                                                                  _: 2
                                                                }, 1032, ["text"]))
                                                              }), 128))
                                                            ]))
                                                          : _createCommentVNode$3("", true),
                                                        _createVNode$3(_component_v_expansion_panels, {
                                                          variant: "accordion",
                                                          class: "epl-ep-panels"
                                                        }, {
                                                          default: _withCtx$3(() => [
                                                            (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(epVisible.value, (ep) => {
                                                              return (_openBlock$3(), _createBlock$3(_component_v_expansion_panel, {
                                                                key: epKey(ep),
                                                                class: _normalizeClass$2({ 'epl-ep-dead': epIsDeleted(ep) }),
                                                                subtitle: `${ep.people.length} 人`
                                                              }, {
                                                                title: _withCtx$3(() => [
                                                                  _createElementVNode$3("span", {
                                                                    class: "epl-ep-title",
                                                                    title: epTitle(ep) ? (epPanelLabel(ep) + ' ' + epTitle(ep)) : epPanelLabel(ep)
                                                                  }, [
                                                                    _createTextVNode$3(_toDisplayString$3(epPanelLabel(ep)), 1),
                                                                    (epTitle(ep))
                                                                      ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                                          _createTextVNode$3("　" + _toDisplayString$3(epTitle(ep)), 1)
                                                                        ], 64))
                                                                      : _createCommentVNode$3("", true)
                                                                  ], 8, _hoisted_56$2),
                                                                  (epIsDeleted(ep))
                                                                    ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_57$2, "· 待恢复"))
                                                                    : _createCommentVNode$3("", true)
                                                                ]),
                                                                text: _withCtx$3(() => [
                                                                  (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(groupByType(ep.people), (grp) => {
                                                                    return (_openBlock$3(), _createElementBlock$3("div", {
                                                                      key: epKey(ep) + '-g-' + grp.type,
                                                                      class: "epl-type-block"
                                                                    }, [
                                                                      (groupByType(ep.people).length > 1)
                                                                        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_58$2, [
                                                                            _createVNode$3(_component_v_icon, { size: "14" }, {
                                                                              default: _withCtx$3(() => [
                                                                                _createTextVNode$3(_toDisplayString$3(typeIcon(grp.type)), 1)
                                                                              ]),
                                                                              _: 2
                                                                            }, 1024),
                                                                            _createTextVNode$3(" " + _toDisplayString$3(grp.label), 1),
                                                                            _createElementVNode$3("span", _hoisted_59$2, _toDisplayString$3(grp.list.length), 1)
                                                                          ]))
                                                                        : _createCommentVNode$3("", true),
                                                                      _createElementVNode$3("div", _hoisted_60$2, [
                                                                        (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(grp.list, (p, i) => {
                                                                          return (_openBlock$3(), _createElementBlock$3("div", {
                                                                            key: epKey(ep) + '-' + grp.type + '-' + i,
                                                                            class: _normalizeClass$2(["epl-actor-chip", { 'is-voice': isVoiceActor(p) }])
                                                                          }, [
                                                                            _createElementVNode$3("div", _hoisted_61$2, [
                                                                              _createElementVNode$3("span", _hoisted_62$2, _toDisplayString$3(p.name_after || p.name_before), 1),
                                                                              (p.role_after || p.role_before)
                                                                                ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_63$2, "饰 " + _toDisplayString$3(p.role_after || p.role_before), 1))
                                                                                : _createCommentVNode$3("", true)
                                                                            ]),
                                                                            _createVNode$3(_component_v_btn, {
                                                                              icon: "mdi-pencil",
                                                                              size: "x-small",
                                                                              variant: "text",
                                                                              class: "epl-chip-edit",
                                                                              onClick: $event => (openEpEdit(p, ep))
                                                                            }, null, 8, ["onClick"])
                                                                          ], 2))
                                                                        }), 128))
                                                                      ])
                                                                    ]))
                                                                  }), 128))
                                                                ]),
                                                                _: 2
                                                              }, 1032, ["class", "subtitle"]))
                                                            }), 128))
                                                          ]),
                                                          _: 1
                                                        }),
                                                        _createElementVNode$3("div", {
                                                          ref_key: "epSentinel",
                                                          ref: epSentinel,
                                                          class: "epl-load-sentinel"
                                                        }, [
                                                          (!epAllLoaded.value)
                                                            ? (_openBlock$3(), _createBlock$3(_component_v_progress_circular, {
                                                                key: 0,
                                                                indeterminate: "",
                                                                size: "20",
                                                                class: "my-2"
                                                              }))
                                                            : (_openBlock$3(), _createElementBlock$3("span", _hoisted_64$2, "— 已全部加载 —"))
                                                        ], 512)
                                                      ], 512))
                                                    : (_openBlock$3(), _createElementBlock$3("div", _hoisted_65$2, "（暂无分集记录：开「处理单集」重扫，或单集入库后自动收集）"))
                                                ], 64))
                                              : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                                  (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(summaryGroups.value, (grp) => {
                                                    return (_openBlock$3(), _createElementBlock$3("div", {
                                                      key: grp.type,
                                                      class: "epl-cast-section"
                                                    }, [
                                                      _createElementVNode$3("div", _hoisted_66$2, [
                                                        _createElementVNode$3("div", _hoisted_67$2, [
                                                          _createVNode$3(_component_v_icon, {
                                                            size: "18",
                                                            color: "primary"
                                                          }, {
                                                            default: _withCtx$3(() => [
                                                              _createTextVNode$3(_toDisplayString$3(grp.type === 'Director' ? 'mdi-video-outline' : grp.type === 'Writer' ? 'mdi-pencil-outline' : 'mdi-account'), 1)
                                                            ]),
                                                            _: 2
                                                          }, 1024),
                                                          _createTextVNode$3(" " + _toDisplayString$3(grp.label) + " ", 1),
                                                          _createElementVNode$3("span", _hoisted_68$2, _toDisplayString$3(grp.list.length), 1)
                                                        ])
                                                      ]),
                                                      _createElementVNode$3("div", _hoisted_69$2, [
                                                        (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(grp.list, (row) => {
                                                          return (_openBlock$3(), _createElementBlock$3("div", {
                                                            key: grp.type + '\u0001' + row.name_before + '\u0001' + row.role_before,
                                                            class: "epl-actor-chip"
                                                          }, [
                                                            _createElementVNode$3("div", _hoisted_70$2, [
                                                              _createElementVNode$3("span", _hoisted_71$2, _toDisplayString$3(row.name_after || row.name_before || '—'), 1),
                                                              (row.role_before || row.role_after)
                                                                ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_72$2, "饰 " + _toDisplayString$3(row.role_after || row.role_before), 1))
                                                                : _createCommentVNode$3("", true)
                                                            ]),
                                                            _createVNode$3(_component_v_btn, {
                                                              icon: "mdi-pencil",
                                                              size: "x-small",
                                                              variant: "text",
                                                              class: "epl-chip-edit",
                                                              title: "编辑译文（人名=全库统一；角色=仅这一条）",
                                                              onClick: $event => (openMovieEdit(row))
                                                            }, null, 8, ["onClick"])
                                                          ]))
                                                        }), 128))
                                                      ])
                                                    ]))
                                                  }), 128)),
                                                  _cache[62] || (_cache[62] = _createElementVNode$3("div", {
                                                    class: "text-caption",
                                                    style: {"opacity":".6"}
                                                  }, "点铅笔编辑译文（人名 = 全库统一，可选同步 Emby；角色 = 仅这一条）；点「写入」把当前条目已翻译名单写入文件（第一排再写入服务器）。", -1))
                                                ], 64))
                                          ], 64))
                                    ], 64))
                              ]))
                        ], 64)),
                    _createVNode$3(_component_v_dialog, {
                      modelValue: editDlgOpen.value,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((editDlgOpen).value = $event)),
                      "max-width": "480",
                      width: isNarrow.value ? '94vw' : undefined,
                      scrollable: ""
                    }, {
                      default: _withCtx$3(() => [
                        _createVNode$3(_component_v_card, {
                          class: "epl-edit-dlg",
                          style: _normalizeStyle(isNarrow.value ? 'height: 92vh' : '')
                        }, {
                          default: _withCtx$3(() => [
                            _createVNode$3(_component_v_card_title, null, {
                              default: _withCtx$3(() => [...(_cache[63] || (_cache[63] = [
                                _createTextVNode$3("编辑译文", -1)
                              ]))]),
                              _: 1
                            }),
                            _createVNode$3(_component_v_card_text, null, {
                              default: _withCtx$3(() => [
                                (dataOpBlocked.value)
                                  ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
                                      key: 0,
                                      type: "warning",
                                      variant: "tonal",
                                      density: "compact",
                                      class: "mb-2"
                                    }, {
                                      default: _withCtx$3(() => [
                                        _createTextVNode$3(" 任务已启动（" + _toDisplayString$3(_unref$1(guard).reason.value) + "），编辑暂时锁定：可查看，保存按钮已禁用。 ", 1)
                                      ]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$3("", true),
                                _cache[78] || (_cache[78] = _createElementVNode$3("div", { class: "epl-zone-head" }, [
                                  _createTextVNode$3("人名（第一排）"),
                                  _createElementVNode$3("span", { class: "epl-zone-tag" }, "默认只改当前身份")
                                ], -1)),
                                _createElementVNode$3("div", _hoisted_73$2, [
                                  _cache[64] || (_cache[64] = _createElementVNode$3("span", { class: "epl-edit-label" }, "原文", -1)),
                                  _createElementVNode$3("span", _hoisted_74$2, _toDisplayString$3(editDlgForm.value.name_before), 1)
                                ]),
                                _createVNode$3(_component_v_text_field, {
                                  modelValue: editDlgForm.value.name_after,
                                  "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((editDlgForm.value.name_after) = $event)),
                                  label: "人名译名",
                                  density: "compact",
                                  variant: "outlined",
                                  "hide-details": "",
                                  class: "mb-2"
                                }, null, 8, ["modelValue"]),
                                _createElementVNode$3("div", _hoisted_75$2, [
                                  _cache[68] || (_cache[68] = _createElementVNode$3("span", { class: "epl-edit-label" }, "范围", -1)),
                                  _createVNode$3(_component_v_btn_toggle, {
                                    modelValue: editDlgNameScope.value,
                                    "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((editDlgNameScope).value = $event)),
                                    density: "compact",
                                    variant: "tonal",
                                    mandatory: ""
                                  }, {
                                    default: _withCtx$3(() => [
                                      _createVNode$3(_component_v_btn, {
                                        value: "single",
                                        size: "small",
                                        color: "primary"
                                      }, {
                                        default: _withCtx$3(() => [...(_cache[65] || (_cache[65] = [
                                          _createTextVNode$3("仅这一条", -1)
                                        ]))]),
                                        _: 1
                                      }),
                                      _createVNode$3(_component_v_btn, {
                                        value: "series",
                                        size: "small",
                                        color: "primary"
                                      }, {
                                        default: _withCtx$3(() => [...(_cache[66] || (_cache[66] = [
                                          _createTextVNode$3("该作品内同名", -1)
                                        ]))]),
                                        _: 1
                                      }),
                                      _createVNode$3(_component_v_btn, {
                                        value: "library",
                                        size: "small",
                                        color: "error"
                                      }, {
                                        default: _withCtx$3(() => [...(_cache[67] || (_cache[67] = [
                                          _createTextVNode$3("全库同名", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  }, 8, ["modelValue"])
                                ]),
                                _createElementVNode$3("div", _hoisted_76$2, [
                                  (editDlgNameScope.value === 'library')
                                    ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_77$2, "全库同名 · 可能误改不同真人"))
                                    : (_openBlock$3(), _createElementBlock$3("span", _hoisted_78$2, "仅改所选范围 · 不动其它作品")),
                                  (editDlgOcc.value.count)
                                    ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_79$2, "　全库同名共 " + _toDisplayString$3(editDlgOcc.value.count) + " 处 · " + _toDisplayString$3(editDlgOcc.value.series.length) + " 部作品", 1))
                                    : _createCommentVNode$3("", true)
                                ]),
                                (editDlgNameScope.value === 'library')
                                  ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
                                      key: 1,
                                      type: "error",
                                      variant: "tonal",
                                      density: "compact",
                                      class: "mb-1"
                                    }, {
                                      default: _withCtx$3(() => [...(_cache[69] || (_cache[69] = [
                                        _createTextVNode$3(" 全库同名会修改所有同名人物，可能包含不同真人。请优先使用「仅这一条 / 该作品内同名」。 ", -1)
                                      ]))]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$3("", true),
                                _createElementVNode$3("div", _hoisted_80$2, _toDisplayString$3(nameScopeHint()), 1),
                                (editDlgNameChanged.value)
                                  ? (_openBlock$3(), _createBlock$3(_component_v_checkbox, {
                                      key: 2,
                                      modelValue: editDlgSyncEmby.value,
                                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((editDlgSyncEmby).value = $event)),
                                      density: "compact",
                                      "hide-details": "",
                                      color: "primary",
                                      class: "mb-3",
                                      label: "同步到 Emby（改 Emby 演员名，全局生效；默认不改）"
                                    }, null, 8, ["modelValue"]))
                                  : (_openBlock$3(), _createElementBlock$3("div", _hoisted_81$2)),
                                (editDlgForm.value.role_before)
                                  ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 4 }, [
                                      _createVNode$3(_component_v_divider, {
                                        class: "mb-3",
                                        style: {"opacity":".25"}
                                      }),
                                      _cache[77] || (_cache[77] = _createElementVNode$3("div", { class: "epl-zone-head" }, [
                                        _createTextVNode$3("角色（第二排）"),
                                        _createElementVNode$3("span", { class: "epl-zone-tag" }, "可精确到某集")
                                      ], -1)),
                                      _createElementVNode$3("div", _hoisted_82$2, [
                                        _cache[70] || (_cache[70] = _createElementVNode$3("span", { class: "epl-edit-label" }, "原文", -1)),
                                        _createElementVNode$3("span", _hoisted_83$2, _toDisplayString$3(editDlgForm.value.role_before), 1)
                                      ]),
                                      _createVNode$3(_component_v_text_field, {
                                        modelValue: editDlgForm.value.role_after,
                                        "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((editDlgForm.value.role_after) = $event)),
                                        label: "角色译名",
                                        density: "compact",
                                        variant: "outlined",
                                        "hide-details": "",
                                        class: "mb-2"
                                      }, null, 8, ["modelValue"]),
                                      _createElementVNode$3("div", _hoisted_84$1, [
                                        _cache[76] || (_cache[76] = _createElementVNode$3("span", { class: "epl-edit-label" }, "范围", -1)),
                                        (editDlgForm.value.role_level === 'movie')
                                          ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_85$1, "仅这一条（电影只有这一条记录）"))
                                          : (_openBlock$3(), _createBlock$3(_component_v_btn_toggle, {
                                              key: 1,
                                              modelValue: editDlgRoleScope.value,
                                              "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((editDlgRoleScope).value = $event)),
                                              density: "compact",
                                              variant: "tonal",
                                              color: "primary",
                                              mandatory: ""
                                            }, {
                                              default: _withCtx$3(() => [
                                                (editDlgForm.value.role_level === 'ep')
                                                  ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                      _createVNode$3(_component_v_btn, {
                                                        value: "single",
                                                        size: "small"
                                                      }, {
                                                        default: _withCtx$3(() => [...(_cache[71] || (_cache[71] = [
                                                          _createTextVNode$3("仅这一集", -1)
                                                        ]))]),
                                                        _: 1
                                                      }),
                                                      _createVNode$3(_component_v_btn, {
                                                        value: "season",
                                                        size: "small"
                                                      }, {
                                                        default: _withCtx$3(() => [...(_cache[72] || (_cache[72] = [
                                                          _createTextVNode$3("这一季", -1)
                                                        ]))]),
                                                        _: 1
                                                      }),
                                                      _createVNode$3(_component_v_btn, {
                                                        value: "series",
                                                        size: "small"
                                                      }, {
                                                        default: _withCtx$3(() => [...(_cache[73] || (_cache[73] = [
                                                          _createTextVNode$3("这个剧", -1)
                                                        ]))]),
                                                        _: 1
                                                      })
                                                    ], 64))
                                                  : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                                      _createVNode$3(_component_v_btn, {
                                                        value: "tv",
                                                        size: "small"
                                                      }, {
                                                        default: _withCtx$3(() => [...(_cache[74] || (_cache[74] = [
                                                          _createTextVNode$3("仅剧级名单", -1)
                                                        ]))]),
                                                        _: 1
                                                      }),
                                                      _createVNode$3(_component_v_btn, {
                                                        value: "series",
                                                        size: "small"
                                                      }, {
                                                        default: _withCtx$3(() => [...(_cache[75] || (_cache[75] = [
                                                          _createTextVNode$3("这个剧（含各集）", -1)
                                                        ]))]),
                                                        _: 1
                                                      })
                                                    ], 64))
                                              ]),
                                              _: 1
                                            }, 8, ["modelValue"]))
                                      ]),
                                      _createElementVNode$3("div", _hoisted_86, _toDisplayString$3(roleScopeHint()), 1)
                                    ], 64))
                                  : _createCommentVNode$3("", true)
                              ]),
                              _: 1
                            }),
                            _createVNode$3(_component_v_card_actions, null, {
                              default: _withCtx$3(() => [
                                _createVNode$3(_component_v_tooltip, {
                                  text: "清除该剧的「第二排角色跨集复用」记忆（删除/恢复/清库都不会清它）",
                                  location: "top"
                                }, {
                                  activator: _withCtx$3(({ props: tp }) => [
                                    _createVNode$3(_component_v_btn, _mergeProps$1(tp, {
                                      size: "small",
                                      variant: "text",
                                      color: "error",
                                      loading: roleMemBusy.value,
                                      disabled: dataOpBlocked.value,
                                      onClick: clearRoleMemory
                                    }), {
                                      default: _withCtx$3(() => [
                                        _createVNode$3(_component_v_icon, {
                                          start: "",
                                          size: "16"
                                        }, {
                                          default: _withCtx$3(() => [...(_cache[79] || (_cache[79] = [
                                            _createTextVNode$3("mdi-brain", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _cache[80] || (_cache[80] = _createTextVNode$3("清除该剧角色记忆 ", -1))
                                      ]),
                                      _: 1
                                    }, 16, ["loading", "disabled"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$3(_component_v_spacer),
                                _createVNode$3(_component_v_btn, {
                                  variant: "text",
                                  onClick: _cache[11] || (_cache[11] = $event => (editDlgOpen.value = false))
                                }, {
                                  default: _withCtx$3(() => [...(_cache[81] || (_cache[81] = [
                                    _createTextVNode$3("取消", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _createVNode$3(_component_v_tooltip, {
                                  text: dataOpBlocked.value ? dataOpBlockedHint.value : '保存修改',
                                  location: "top"
                                }, {
                                  activator: _withCtx$3(({ props: tp }) => [
                                    _createVNode$3(_component_v_btn, _mergeProps$1(tp, {
                                      color: "primary",
                                      variant: "flat",
                                      loading: editDlgSaving.value,
                                      disabled: dataOpBlocked.value,
                                      onClick: saveEditDialog
                                    }), {
                                      default: _withCtx$3(() => [...(_cache[82] || (_cache[82] = [
                                        _createTextVNode$3("保存", -1)
                                      ]))]),
                                      _: 1
                                    }, 16, ["loading", "disabled"])
                                  ]),
                                  _: 1
                                }, 8, ["text"])
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }, 8, ["style"])
                      ]),
                      _: 1
                    }, 8, ["modelValue", "width"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$3(_component_v_dialog, {
      modelValue: txDlg.value,
      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((txDlg).value = $event)),
      "max-width": "480"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card, null, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$3(() => [...(_cache[83] || (_cache[83] = [
                    _createTextVNode$3("mdi-translate", -1)
                  ]))]),
                  _: 1
                }),
                _createTextVNode$3(_toDisplayString$3(txMode.value === 'item' ? '重新翻译（仅当前条目）' : '批量翻译'), 1)
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_text, null, {
              default: _withCtx$3(() => [
                (txMode.value === 'item')
                  ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
                      key: 0,
                      type: "warning",
                      variant: "tonal",
                      density: "compact",
                      style: {"font-size":"12px"},
                      class: "mb-2"
                    }, {
                      default: _withCtx$3(() => [
                        _createTextVNode$3(" 仅重翻《" + _toDisplayString$3(selected.value?.title || selected.value?.item_id) + "》这一条，不会扫描或翻译其它条目。 ", 1)
                      ]),
                      _: 1
                    }))
                  : _createCommentVNode$3("", true),
                _cache[88] || (_cache[88] = _createElementVNode$3("div", { class: "epl-tx-label" }, "翻译范围", -1)),
                _createVNode$3(_component_v_radio_group, {
                  modelValue: txScope.value,
                  "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((txScope).value = $event)),
                  density: "compact",
                  "hide-details": "",
                  class: "mb-2"
                }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_radio, {
                      value: "default",
                      label: "使用设置默认"
                    }),
                    _createVNode$3(_component_v_radio, {
                      value: "person",
                      label: "只翻第一排人物姓名"
                    }),
                    _createVNode$3(_component_v_radio, {
                      value: "role",
                      label: "只翻第二排角色"
                    }),
                    _createVNode$3(_component_v_radio, {
                      value: "both",
                      label: "两排都翻"
                    })
                  ]),
                  _: 1
                }, 8, ["modelValue"]),
                _createVNode$3(_component_v_alert, {
                  type: "info",
                  variant: "tonal",
                  density: "compact",
                  style: {"font-size":"12px"},
                  class: "mb-2"
                }, {
                  default: _withCtx$3(() => [...(_cache[84] || (_cache[84] = [
                    _createTextVNode$3(" 本次只决定「翻哪一排」，属于一次性任务、不改设置页长期配置；", -1),
                    _createElementVNode$3("b", null, "「翻哪些类型 + 每个人翻几个」由设置页「翻译范围」决定", -1),
                    _createTextVNode$3("，已计入下方预估。 ", -1)
                  ]))]),
                  _: 1
                }),
                _createElementVNode$3("div", _hoisted_87, [
                  _createElementVNode$3("div", {
                    class: _normalizeClass$2(["epl-tx-preview-row", { 'epl-tx-off': !txEstimate.value.wantP }])
                  }, [
                    _cache[85] || (_cache[85] = _createElementVNode$3("span", null, "第一排（人物姓名）", -1)),
                    _createElementVNode$3("span", _hoisted_88, _toDisplayString$3(txPreview.value.loading ? '…' : `待翻 ${txEstimate.value.names} 个 / 范围内 ${txEstimate.value.namesScope} 个`), 1)
                  ], 2),
                  _createElementVNode$3("div", {
                    class: _normalizeClass$2(["epl-tx-preview-row", { 'epl-tx-off': !txEstimate.value.wantR }])
                  }, [
                    _cache[86] || (_cache[86] = _createElementVNode$3("span", null, "第二排（角色名）", -1)),
                    _createElementVNode$3("span", _hoisted_89, _toDisplayString$3(txPreview.value.loading ? '…' : `待翻 ${txEstimate.value.roles} 个 / 范围内 ${txEstimate.value.rolesScope} 个`), 1)
                  ], 2)
                ]),
                (!txPreview.value.loading && txEstimate.value.pending === 0 && txEstimate.value.scope === 0)
                  ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_90, [...(_cache[87] || (_cache[87] = [
                      _createTextVNode$3(" 范围内 0 条 —— 可能是：① 该排总开关没开；② ", -1),
                      _createElementVNode$3("b", null, "类型开关没开", -1),
                      _createTextVNode$3("（例如只填了「客串」的人数、却没打开「客串」开关）；③ 被人数上限挡在外面；④ 库里还没有该范围的记录。请到设置页「翻译范围」确认。 ", -1)
                    ]))]))
                  : (!txPreview.value.loading && txEstimate.value.pending === 0)
                    ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_91, " 范围内 " + _toDisplayString$3(txEstimate.value.scope) + " 条：已翻完 / 原文已是中文，无需翻译。 ", 1))
                    : (_openBlock$3(), _createElementBlock$3("div", _hoisted_92, "点「有任务 · 待翻译」徽章可看具体是哪些条目/词条。")),
                _createElementVNode$3("div", _hoisted_93, "当前选择：" + _toDisplayString$3(txScopeLabel.value), 1)
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_actions, null, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_btn, {
                  variant: "text",
                  size: "small",
                  loading: txPreview.value.loading,
                  onClick: loadTxPreview
                }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, {
                      start: "",
                      size: "16"
                    }, {
                      default: _withCtx$3(() => [...(_cache[89] || (_cache[89] = [
                        _createTextVNode$3("mdi-refresh", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[90] || (_cache[90] = _createTextVNode$3("刷新预估 ", -1))
                  ]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[14] || (_cache[14] = $event => (txDlg.value = false))
                }, {
                  default: _withCtx$3(() => [...(_cache[91] || (_cache[91] = [
                    _createTextVNode$3("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$3(_component_v_btn, {
                  color: "primary",
                  variant: "flat",
                  loading: txBusy.value,
                  onClick: confirmTranslate
                }, {
                  default: _withCtx$3(() => [
                    _createTextVNode$3(_toDisplayString$3(txMode.value === 'item' ? '开始重翻' : '开始翻译'), 1)
                  ]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$3(_component_v_dialog, {
      modelValue: pendingDlg.value,
      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((pendingDlg).value = $event)),
      "max-width": "640"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card, null, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$3(() => [...(_cache[92] || (_cache[92] = [
                    _createTextVNode$3("mdi-format-list-checks", -1)
                  ]))]),
                  _: 1
                }),
                _cache[94] || (_cache[94] = _createTextVNode$3("待翻译明细 ", -1)),
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  icon: "",
                  size: "small",
                  variant: "text",
                  onClick: _cache[16] || (_cache[16] = $event => (pendingDlg.value = false))
                }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, { size: "18" }, {
                      default: _withCtx$3(() => [...(_cache[93] || (_cache[93] = [
                        _createTextVNode$3("mdi-close", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_text, null, {
              default: _withCtx$3(() => [
                (pendingBusy.value)
                  ? (_openBlock$3(), _createBlock$3(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary",
                      height: "3"
                    }))
                  : _createCommentVNode$3("", true),
                _createElementVNode$3("div", _hoisted_94, " 按当前「翻译范围」统计 —— 待翻：第一排 " + _toDisplayString$3(pendingData.value.names_pending) + " · 第二排 " + _toDisplayString$3(pendingData.value.roles_pending) + "； 符合范围：第一排 " + _toDisplayString$3(pendingData.value.names_scope) + " · 第二排 " + _toDisplayString$3(pendingData.value.roles_scope) + "；" + _toDisplayString$3(pendingData.value.items_total) + " 个条目 ", 1),
                _createElementVNode$3("div", _hoisted_95, [
                  (!pendingBusy.value && !pendingData.value.items.length)
                    ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_96, " 没有待翻译条目 —— 要么都翻完了，要么被「类型开关 / 人数上限」挡在外面（去设置页「翻译范围」检查） "))
                    : _createCommentVNode$3("", true),
                  (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(pendingData.value.items, (it) => {
                    return (_openBlock$3(), _createElementBlock$3("div", {
                      key: it.item_id + ':' + it.server_id,
                      class: "epl-pend-item"
                    }, [
                      _createElementVNode$3("div", _hoisted_97, "《" + _toDisplayString$3(it.title) + "》", 1),
                      (it.names_total)
                        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_98, [
                            _cache[95] || (_cache[95] = _createElementVNode$3("span", { class: "epl-pend-tag" }, "第一排", -1)),
                            (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(it.names, (n, i) => {
                              return (_openBlock$3(), _createElementBlock$3("span", {
                                class: "epl-pend-term",
                                key: 'n' + i
                              }, _toDisplayString$3(n), 1))
                            }), 128)),
                            (it.names_total > it.names.length)
                              ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_99, "等共 " + _toDisplayString$3(it.names_total) + " 个", 1))
                              : _createCommentVNode$3("", true)
                          ]))
                        : _createCommentVNode$3("", true),
                      (it.roles_total)
                        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_100, [
                            _cache[96] || (_cache[96] = _createElementVNode$3("span", { class: "epl-pend-tag" }, "第二排", -1)),
                            (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(it.roles, (r, i) => {
                              return (_openBlock$3(), _createElementBlock$3("span", {
                                class: "epl-pend-term",
                                key: 'r' + i
                              }, _toDisplayString$3(r), 1))
                            }), 128)),
                            (it.roles_total > it.roles.length)
                              ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_101, "等共 " + _toDisplayString$3(it.roles_total) + " 个", 1))
                              : _createCommentVNode$3("", true)
                          ]))
                        : _createCommentVNode$3("", true)
                    ]))
                  }), 128))
                ])
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_actions, null, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[17] || (_cache[17] = $event => (pendingDlg.value = false))
                }, {
                  default: _withCtx$3(() => [...(_cache[97] || (_cache[97] = [
                    _createTextVNode$3("关闭", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$3(ConfirmDlg, {
      state: _unref$1(cState),
      "on-ok": _unref$1(cOk),
      "on-cancel": _unref$1(cCancel)
    }, null, 8, ["state", "on-ok", "on-cancel"]),
    _createVNode$3(_sfc_main$4, {
      modelValue: _unref$1(guard).dlg.value,
      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((_unref$1(guard).dlg.value) = $event)),
      reason: _unref$1(guard).reason.value,
      state: _unref$1(guard).stateLabel.value,
      action: _unref$1(guard).pendingLabel.value,
      onViewTask: _cache[20] || (_cache[20] = $event => (emit('view-task')))
    }, null, 8, ["modelValue", "reason", "state", "action"])
  ]))
}
}

};
const Library = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-b6c5178a"]]);

const {toDisplayString:_toDisplayString$2,createElementVNode:_createElementVNode$2,createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode$2,createBlock:_createBlock$2,Fragment:_Fragment$2,withKeys:_withKeys,withModifiers:_withModifiers,renderList:_renderList$2,normalizeClass:_normalizeClass$1,unref:_unref,createStaticVNode:_createStaticVNode} = await importShared('vue');


const _hoisted_1$2 = { class: "epl-pool" };
const _hoisted_2$2 = { class: "epl-pool-head" };
const _hoisted_3$2 = { class: "epl-pool-sub" };
const _hoisted_4$2 = { class: "epl-pool-acts" };
const _hoisted_5$2 = {
  key: 0,
  class: "epl-pool-progress"
};
const _hoisted_6$2 = { class: "epl-pool-progress-line" };
const _hoisted_7$2 = { key: 0 };
const _hoisted_8$2 = { key: 0 };
const _hoisted_9$2 = { key: 1 };
const _hoisted_10$2 = {
  key: 2,
  class: "epl-pool-paused"
};
const _hoisted_11$1 = {
  key: 1,
  class: "epl-pool-progress"
};
const _hoisted_12$1 = { class: "epl-pool-progress-line" };
const _hoisted_13$1 = {
  key: 0,
  class: "epl-pool-paused"
};
const _hoisted_14$1 = { key: 1 };
const _hoisted_15$1 = { class: "epl-pool-search-row" };
const _hoisted_16$1 = {
  key: 0,
  class: "epl-pool-sel"
};
const _hoisted_17$1 = {
  key: 0,
  class: "epl-pool-filter-panel"
};
const _hoisted_18$1 = { class: "epl-pool-panel-rows" };
const _hoisted_19$1 = { class: "epl-pool-chips" };
const _hoisted_20$1 = ["onClick"];
const _hoisted_21$1 = { class: "epl-pool-chips" };
const _hoisted_22$1 = ["onClick"];
const _hoisted_23$1 = { class: "epl-pool-table epl-pool-desktop-table" };
const _hoisted_24$1 = {
  key: 1,
  class: "epl-pool-empty"
};
const _hoisted_25$1 = { class: "epl-pool-tr" };
const _hoisted_26$1 = ["title"];
const _hoisted_27$1 = ["title"];
const _hoisted_28$1 = { class: "c-type" };
const _hoisted_29$1 = { class: "c-status" };
const _hoisted_30$1 = { class: "c-occ" };
const _hoisted_31$1 = { class: "c-op" };
const _hoisted_32$1 = {
  key: 0,
  class: "epl-pool-occ"
};
const _hoisted_33$1 = { class: "epl-pool-occ-head" };
const _hoisted_34$1 = {
  key: 0,
  class: "epl-pool-occ-empty"
};
const _hoisted_35$1 = {
  key: 1,
  class: "epl-pool-occ-empty"
};
const _hoisted_36$1 = {
  key: 2,
  class: "epl-pool-occ-list"
};
const _hoisted_37$1 = { class: "epl-occ-title" };
const _hoisted_38$1 = {
  key: 0,
  class: "epl-occ-count"
};
const _hoisted_39$1 = {
  key: 1,
  class: "epl-occ-del"
};
const _hoisted_40$1 = { class: "epl-pool-mobile-list" };
const _hoisted_41$1 = {
  key: 0,
  class: "epl-pool-empty"
};
const _hoisted_42$1 = { class: "person-card-top" };
const _hoisted_43$1 = ["title"];
const _hoisted_44$1 = { class: "person-card-main" };
const _hoisted_45$1 = ["title"];
const _hoisted_46$1 = { class: "person-card-tools" };
const _hoisted_47$1 = {
  key: 0,
  class: "person-card-detail"
};
const _hoisted_48$1 = { class: "person-card-row" };
const _hoisted_49$1 = { class: "person-card-v" };
const _hoisted_50$1 = { class: "person-card-row" };
const _hoisted_51$1 = { class: "person-card-v" };
const _hoisted_52$1 = { class: "person-card-actions" };
const _hoisted_53$1 = {
  key: 0,
  class: "epl-pool-occ"
};
const _hoisted_54$1 = { class: "epl-pool-occ-head" };
const _hoisted_55$1 = {
  key: 0,
  class: "epl-pool-occ-empty"
};
const _hoisted_56$1 = {
  key: 1,
  class: "epl-pool-occ-empty"
};
const _hoisted_57$1 = {
  key: 2,
  class: "epl-pool-occ-list"
};
const _hoisted_58$1 = { class: "epl-occ-title" };
const _hoisted_59$1 = {
  key: 0,
  class: "epl-occ-count"
};
const _hoisted_60$1 = {
  key: 1,
  class: "epl-occ-del"
};
const _hoisted_61$1 = {
  key: 2,
  class: "epl-pool-page"
};
const _hoisted_62$1 = { class: "epl-dlg" };
const _hoisted_63$1 = { class: "epl-dlg-body" };
const _hoisted_64$1 = { class: "epl-field" };
const _hoisted_65$1 = { class: "epl-field-v" };
const _hoisted_66$1 = { class: "epl-field" };
const _hoisted_67$1 = { class: "epl-field-v" };
const _hoisted_68$1 = { class: "epl-field" };
const _hoisted_69$1 = { class: "epl-field-v" };
const _hoisted_70$1 = { class: "epl-dlg-acts" };
const _hoisted_71$1 = { class: "epl-dlg" };
const _hoisted_72$1 = { class: "epl-dlg-body" };
const _hoisted_73$1 = { class: "epl-dlg-acts" };
const _hoisted_74$1 = { class: "epl-dlg" };
const _hoisted_75$1 = { class: "epl-dlg-body" };
const _hoisted_76$1 = { class: "epl-field" };
const _hoisted_77$1 = { class: "epl-field-v" };
const _hoisted_78$1 = { class: "epl-field" };
const _hoisted_79$1 = { class: "epl-field-v" };
const _hoisted_80$1 = { class: "epl-dlg-acts" };
const _hoisted_81$1 = { class: "epl-dlg" };
const _hoisted_82$1 = { class: "epl-dlg-body" };
const _hoisted_83$1 = { class: "epl-field" };
const _hoisted_84 = { class: "epl-field-v" };
const _hoisted_85 = { class: "epl-dlg-acts" };

const {computed: computed$2,inject: inject$2,onActivated: onActivated$1,onBeforeUnmount,onDeactivated,onMounted: onMounted$2,ref: ref$2,watch: watch$1} = await importShared('vue');

const ACTING_LABEL = '演员';
const MAX_IMPORT_BYTES = 30 * 1024 * 1024;   // 30MB
const MAX_IMPORT_ROWS = 50000;


const _sfc_main$2 = {
  __name: 'PeoplePoolView',
  props: {
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
},
  emits: ['notify', 'action', 'view-task'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject$2('moviepilot:toast', null);

const { cState, askConfirm, cOk, cCancel } = useConfirm();
// v4.6.70：统一任务守卫（清池 / 重筛 / 池编辑 / 同步 / 批量翻译 / 重拉 / 导入 共用同一把锁）
const guard = useTaskGuard();

function notify(msg, type = 'error') {
  const t = toast; if (t && typeof t[type] === 'function') t[type](msg);
}

const TYPE_LABELS = { Actor: '演员', VoiceActor: '声优', Director: '导演', Writer: '编剧', Producer: '制片', GuestStar: '客串' };
// v4.6.79（人名池显示口径）：**演员类**身份（主演 Actor / 声优 VoiceActor / 客串 GuestStar）在显示层
// 统一合并为「演员」—— 「客串 / 声优」本质也是演戏，与「演员」并列只是噪声；只有导演 / 编剧 / 制片
// 等「特别身份」才单独显示。**仅改显示**：拉取类型 / 重筛 / 翻译类型开关仍用原始 Emby 类型，功能不变。
const ACTING_TYPES = ['Actor', 'VoiceActor', 'GuestStar'];
const TYPE_FILTERS = [
  { value: '', title: '全部' },
  { value: 'Actor', title: '演员' },
  { value: 'Director', title: '导演' },
  { value: 'Writer', title: '编剧' },
  { value: 'Producer', title: '制片' },
  { value: 'GuestStar', title: '客串' },
];
const STATUS_FILTERS = [
  { value: '', title: '全部' },
  { value: 'pending', title: '待翻译' },
  { value: 'no_change', title: '无需操作' },
  { value: 'translated', title: '待同步' },
  { value: 'synced', title: '已同步' },
  { value: 'failed', title: '同步失败' },
];

const rows = ref$2([]);
const total = ref$2(0);
const page = ref$2(1);
const size = ref$2(50);
const keyword = ref$2('');
const status = ref$2('');
const type = ref$2('');
const loading = ref$2(true);

const filterOpen = ref$2(false);
const filterRef = ref$2(null);
const selCount = computed$2(() => (status.value ? 1 : 0) + (type.value ? 1 : 0));

function onDocPointerDown(e) {
  if (!filterOpen.value) return
  const el = filterRef.value;
  if (el && !el.contains(e.target)) filterOpen.value = false;
}

const counts = ref$2({ total: 0, pending: 0, no_change: 0, translated: 0, synced: 0, failed: 0 });
const fetchState = ref$2({ running: false, total: 0, done: 0, current: '', added: 0, updated: 0, unchanged: 0, filtered: 0, failed: 0 });
const txState = ref$2({});
const poolTaskRunning = ref$2(false);
const pluginEnabled = computed$2(() => props.enabled !== false);
const pluginOffTitle = computed$2(() => (pluginEnabled.value ? '' : '插件未启用：请先在设置页打开「启用插件」'));
const txRunning = computed$2(() => !!txState.value.running);
const poolFetchDisabled = computed$2(() => !pluginEnabled.value || txRunning.value || poolTaskRunning.value);
const poolFetchTitle = computed$2(() => {
  if (!pluginEnabled.value) return '插件未启用：请先在设置页打开「启用插件」'
  if (txRunning.value) return 'AI 翻译进行中，暂不可拉取人名（翻译与拉取互斥），等翻译完成后再试'
  if (poolTaskRunning.value) return '人名池任务（拉取/同步）进行中，完成后可用'
  return ''
});
const poolSyncDisabled = computed$2(() => !pluginEnabled.value || poolTaskRunning.value);
const poolDataOpBlocked = computed$2(() => !pluginEnabled.value || txRunning.value || poolTaskRunning.value);
const poolDataOpBlockedHint = computed$2(() => {
  if (!pluginEnabled.value) return '插件未启用：请先在设置页打开「启用插件」'
  if (txRunning.value) return 'AI 翻译进行中，请先「终止」或等待完成后再操作（避免边翻译边清库）'
  if (poolTaskRunning.value) return '人名池任务（拉取/同步）进行中，请先「终止」或等待完成后再操作'
  return ''
});
const scope = ref$2('libraries');

// 出现清单（懒加载，只展示不编辑）
const occOpen = ref$2('');
const occLoading = ref$2(false);
const occRows = ref$2([]);

const detailOpen = ref$2('');

// 弹窗
const editDlg = ref$2(false);
const editRow = ref$2(null);
const editZh = ref$2('');
const editSaved = ref$2(false);
const editSyncEmby = ref$2(false);
const transDlg = ref$2(false);
const transSync = ref$2(false);
const syncDlg = ref$2(false);
const fetchDlg = ref$2(false);
const busy = ref$2(false);
const refetchKey = ref$2('');   // 正在「重拉」的行 key（按钮 loading 用）

let timer = null;

function parseJsonArray(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.trim()) {
    try {
      const a = JSON.parse(v);
      return Array.isArray(a) ? a : []
    } catch (e) { return [] }
  }
  return []
}

function typeList(row) {
  let arr = parseJsonArray(row?.person_types);
  if (!arr.length && row?.person_type) {
    arr = String(row.person_type).split(',').map(s => s.trim()).filter(Boolean);
  }
  const out = [];
  let hasActing = false;
  for (const x of arr) {
    // 演员类（主演 / 声优 / 客串）→ 合并为「演员」，只占一枚
    if (ACTING_TYPES.includes(x)) { hasActing = true; continue }
    const label = TYPE_LABELS[x] || x;
    if (label && !out.includes(label)) out.push(label);
  }
  // 「演员」作为主要身份排在最前，特别身份（导演/编剧/制片…）按原顺序跟随
  return hasActing ? [ACTING_LABEL, ...out] : out
}

function typeText(row) {
  const arr = typeList(row);
  return arr.length ? arr.join(' / ') : '未分类'
}

function statusChip(r) {
  if (r.status === '待翻译') return { text: '待翻译', color: 'error', dot: '🔴' }
  if (r.status === '无需操作') return { text: '无需操作', color: 'success', dot: '🟩' }
  if (r.status === '待同步') return { text: '待同步', color: 'warning', dot: '🟡' }
  if (r.status === '同步失败') return { text: '同步失败', color: 'error', dot: '⚠️' }
  return { text: '已同步', color: 'success', dot: '🟢' }
}

function isChineseText(s) {
  // v4.6.80：与后端口径对齐 —— 含汉字且**无假名**即视为「已是中文」；
  // 空格不再作为排除条件（「角田 雄二郎」这类中文带空格的名字此前被判待翻译）。
  const t = String(s || '');
  if (!/[\u4e00-\u9fff]/.test(t)) return false
  return !/[\u3041-\u309f\u30a0-\u30ff]/.test(t)
}
function poolTargetName(r) {
  const orig = String(r?.name_original || '').trim();
  const zh = String(r?.name_zh || '').trim();
  if (zh && zh !== orig) return zh
  if (isChineseText(orig)) return orig
  return ''
}
// v4.6.94：译名列的显示文本 —— 只显示「第一排改过」的最终译名（AI 翻译/人工修改）。
// 没改过（name_zh 为空，或与原文相同）→ 返回空串，由调用方给占位：
//   · 原文已是中文 → 不再重复显示同一个名字（只显示原文名一处）
//   · 改过之后状态自然变成「待同步/已同步」，与没改过的行区分开
// 人工改错也能对照「原文名」列进行修正。
function zhText(r) {
  const orig = String(r?.name_original || '').trim();
  const zh = String(r?.name_zh || '').trim();
  if (!zh || zh === orig) return ''
  return zh
}
function recomputeRowStatus(r) {
  const orig = String(r?.name_original || '').trim();
  const cur = String(r?.name_current || '').trim();
  const target = poolTargetName(r);
  let translation;
  if (target) translation = (String(r?.name_zh || '').trim() && String(r.name_zh).trim() !== orig) ? 'translated' : 'no_change';
  else translation = (r?.translation_status === 'failed') ? 'failed' : 'pending';
  let sync;
  if (!target) sync = 'unknown';
  else if (cur && cur === target) sync = 'synced';
  else if (r?.sync_status === 'failed') sync = 'failed';
  // v4.6.93：原文已是中文 + Emby 当前名未知（扫描缓存行/无身份）→ 无同步可言（不报待同步）
  else if (!cur && translation === 'no_change') sync = 'unknown';
  else sync = 'pending';
  let ui;
  if (translation === 'pending' || translation === 'failed') ui = '待翻译';
  else if (sync === 'failed') ui = '同步失败';
  else if (sync === 'pending') ui = '待同步';
  else if (translation === 'no_change') ui = '无需操作';
  else ui = '已同步';
  r.status = ui;
  r.translation_status = translation;
  r.sync_status = sync;
}

async function loadList(silent = false) {
  if (!silent) loading.value = true;
  try {
    const d = await api.get(props.api, '/pool/list', {
      keyword: keyword.value, status: status.value, type: type.value,
      page: page.value, size: size.value,
    });
    rows.value = d.items || [];
    total.value = d.total || 0;
  } catch (e) {
    if (!silent) notify(e.message, 'error');
  }
  loading.value = false;
}

async function loadStatus() {
  try {
    const d = await api.get(props.api, '/pool/status');
    counts.value = d.counts || counts.value;
    fetchState.value = d.fetch || {};
    txState.value = d.tx || {};
    poolTaskRunning.value = !!d.running;
    if (d.scope) scope.value = d.scope;
    // v4.6.70：同步统一任务守卫（/pool/status 已附 is_running + tasks 快照）
    guard.loadStatus(d);
  } catch (e) { /* 静默 */ }
}

const pulling = computed$2(() => !!fetchState.value.running);
const fetchPercent = computed$2(() => {
  const t = Number(fetchState.value.total || 0);
  const dn = Number(fetchState.value.done || 0);
  if (!t) return 0
  return Math.min(100, Math.round(dn / t * 100))
});

watch$1(pulling, (now, old) => {
  if (old && !now) { loadList(true); loadStatus(); }
});

async function refreshAll(silent = false) {
  await Promise.all([loadList(silent), loadStatus()]);
}

function onSearch() {
  page.value = 1;
  loadList();
}

function resetFilter() {
  keyword.value = '';
  status.value = '';
  type.value = '';
  page.value = 1;
  loadList();
}

function changeStatus(v) {
  status.value = v;
  page.value = 1;
  loadList();
}

function changeType(v) {
  type.value = v;
  page.value = 1;
  loadList();
}

const paused = computed$2(() => !!fetchState.value.paused);

async function pauseFetch() {
  try {
    const d = await api.post(props.api, '/task/pause', { target: 'pool' });
    notify(d?.message || '已暂停', 'info');
    loadStatus();
  } catch (e) { notify(e.message, 'error'); }
}

async function resumeFetch() {
  try {
    const d = await api.post(props.api, '/task/resume', { target: 'pool' });
    notify(d?.message || '已继续', 'success');
    loadStatus();
  } catch (e) { notify(e.message, 'error'); }
}

const txPaused = computed$2(() => !!txState.value.user_paused);

async function pauseTranslate() {
  try {
    const d = await api.post(props.api, '/task/pause', { target: 'translate' });
    notify(d?.message || '翻译已暂停', 'info');
    loadStatus();
  } catch (e) { notify(e.message, 'error'); }
}

async function resumeTranslate() {
  try {
    const d = await api.post(props.api, '/task/resume', { target: 'translate' });
    notify(d?.message || '已继续翻译', 'success');
    loadStatus();
  } catch (e) { notify(e.message, 'error'); }
}

const poolImportInput = ref$2(null);
const poolBusy = ref$2('');

async function exportPool() {
  poolBusy.value = 'export';
  try {
    const r = await api.get(props.api, '/pool/export');
    const rows = Array.isArray(r) ? r : [];
    if (!rows.length) { notify('人名池为空，暂无可导出数据', 'info'); return }
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `embypeople_pool_${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
    notify(`已导出 ${rows.length} 人`, 'success');
  } catch (e) { notify((e && e.message) || '导出失败', 'error'); } finally { poolBusy.value = ''; }
}

function pickPoolImport() { poolImportInput.value?.click(); }

// UI-007：导入前先按文件大小拦一道，避免把超大备份整体读进内存（会冻结浏览器）。
// 超限直接拒绝并说明原因；解析后再限制记录数，防止超大数组把请求体撑爆。
function fmtSize(n) {
  const mb = Number(n || 0) / 1024 / 1024;
  return `${mb.toFixed(1)}MB`
}

async function onPoolImportPick(e) {
  const f = e.target.files && e.target.files[0];
  if (!f) return
  if (!guard.check('导入人名池')) { e.target.value = ''; return }   // v4.6.70：统一守卫
  if (Number(f.size || 0) > MAX_IMPORT_BYTES) {
    notify(`文件过大（${fmtSize(f.size)}，上限 ${fmtSize(MAX_IMPORT_BYTES)}）：请拆分后再导入，或改用服务器端导入`, 'error');
    e.target.value = '';
    return
  }
  const reader = new FileReader();
  reader.onload = async () => {
    poolBusy.value = 'import';
    try {
      let rows;
      try { rows = JSON.parse(reader.result); } catch (_) { throw new Error('文件不是有效 JSON') }
      if (!Array.isArray(rows)) rows = rows?.rows || rows?.data || rows?.records || [];
      if (!Array.isArray(rows) || !rows.length) { notify('文件里没有可导入的数据', 'error'); return }
      if (rows.length > MAX_IMPORT_ROWS) {
        notify(`记录数过多（${rows.length} 条，上限 ${MAX_IMPORT_ROWS} 条）：请拆分后再导入`, 'error');
        return
      }
      const r = await api.post(props.api, '/pool/import', { rows });
      notify(r?.message || '导入完成', 'success');
      refreshAll(true);
    } catch (err) { notify((err && err.message) || '导入失败', 'error'); } finally { poolBusy.value = ''; e.target.value = ''; }
  };
  reader.readAsText(f);
}

async function clearPool() {
  if (!guard.check('清空人名池')) return   // v4.6.70：统一守卫
  if (!await askConfirm({
    title: '清除人名池',
    text: `确认清除人名池全部 ${counts.value.total} 人？`,
    detail: '将删除人名池里的全部条目（原文名 / 译名 / 来源标记）。此操作不可恢复，建议先「导出」备份。',
    okText: '继续',
    color: 'error',
  })) return
  if (!await askConfirm({
    title: '再次确认',
    text: '确定要清空整个人名池吗？',
    detail: '⚠️ 人工修正的译名也会一并删除，且无法恢复。清除后可重新「拉取人名」→「批量翻译」重建。',
    okText: '确认清除',
    color: 'error',
  })) return
  poolBusy.value = 'clear';
  try {
    const r = await api.post(props.api, '/pool/clear');
    notify(r?.message || '人名池已清空', 'success');
    refreshAll(true);
  } catch (e) { notify((e && e.message) || '清除失败', 'error'); } finally { poolBusy.value = ''; }
}

// ── 出现清单 ──
function occTitle(o) {
  return o.series_name || o.title || o.item_id || ''
}

const occUnique = computed$2(() => {
  const map = new Map();
  for (const o of occRows.value) {
    const t = occTitle(o);
    const hit = map.get(t);
    if (hit) { hit.count++; if (o.deleted_at) hit.deleted = true; }
    else map.set(t, { title: t, count: 1, deleted: !!o.deleted_at });
  }
  return Array.from(map.values())
});

// UI-006：key 必须带 server_id 维度，否则两个服务器同名 Person ID/name 的
// 展开/详情状态会互相串（同一 key 命中）。source scope = server_id + 人物标识。
function personKey(r) {
  const sid = String(r?.server_id || '');
  const pid = r?.emby_person_id || r?.name_original || r?.id || '';
  return `${sid}:${pid}`
}

function rowKey(r) { return personKey(r) }

function canSync(r) {
  const t = poolTargetName(r);
  if (!t || t === (r.name_current || '')) return false
  // v4.6.93：原文已是中文 + Emby 当前名未知（扫描缓存行）→ 无同步可言
  // （要补 Emby 身份请点「重拉」或跑「拉取人名」，拉到当前名后若确有差异会再显示「同步」）
  if (!r?.name_current && isChineseText(r?.name_original)) return false
  return true
}

function toggleDetail(r) {
  const k = rowKey(r);
  detailOpen.value = detailOpen.value === k ? '' : k;
}

async function toggleOcc(r) {
  const key = personKey(r);
  if (occOpen.value === key) { occOpen.value = ''; return }
  occOpen.value = key;
  occRows.value = [];
  occLoading.value = true;
  try {
    const d = await api.get(props.api, '/pool/occurrences', {
      name_before: r.name_original, server_id: r.server_id, limit: 500,
    });
    occRows.value = Array.isArray(d) ? d : (d.items || []);
  } catch (e) {
    notify(e.message, 'error');
  }
  occLoading.value = false;
}

function occCount(r) {
  const key = personKey(r);
  if (occOpen.value !== key) return ''
  return occLoading.value ? '查询中…' : `${occRows.value.length} 处`
}

// ── 单条编辑 ──
function openEdit(r) {
  editRow.value = r;
  editZh.value = r.name_zh || '';
  editSaved.value = false;
  editSyncEmby.value = false;
  editDlg.value = true;
}

async function saveEdit() {
  if (!editRow.value) return
  if (!guard.check('保存人名池译名')) return   // v4.6.70：统一守卫
  busy.value = true;
  try {
    const r = editRow.value;
    await api.post(props.api, '/pool/update', {
      server_id: r.server_id, emby_person_id: r.emby_person_id,
      name_original: r.name_original, name_zh: editZh.value,
    });
    r.name_zh = editZh.value;
    r.sync_status = '';
    r.sync_error = '';
    recomputeRowStatus(r);
    editSaved.value = true;
    notify('已保存池译文（未同步 Emby）', 'success');
    loadStatus();
  } catch (e) {
    notify(e.message, 'error');
  }
  busy.value = false;
}

async function syncOne() {
  if (!editRow.value) return
  if (!guard.check('同步该人名到 Emby')) return   // v4.6.70：统一守卫
  busy.value = true;
  try {
    const r = editRow.value;
    if (!editSaved.value && (r.name_zh || '') !== (editZh.value || '')) {
      await api.post(props.api, '/pool/update', {
        server_id: r.server_id, emby_person_id: r.emby_person_id,
        name_original: r.name_original, name_zh: editZh.value,
      });
      r.name_zh = editZh.value;
      editSaved.value = true;
    }
    const d = await api.post(props.api, '/pool/sync_one', {
      server_id: r.server_id, emby_person_id: r.emby_person_id,
      name_original: r.name_original, name_zh: editZh.value, name_current: r.name_current,
    });
    notify(d?.message || '已同步到 Emby', 'success');
    editDlg.value = false;
    loadList(true); loadStatus();
  } catch (e) {
    notify(e.message, 'error');
  }
  busy.value = false;
}

// ── 单条重新拉取（从 Emby 重取该人事实：当前名/类型，legacy 无 ID 行顺带补 Person ID）──
async function refetchOne(r) {
  if (!r || refetchKey.value) return
  if (!guard.check('重拉该人名')) return   // v4.6.70：统一守卫
  refetchKey.value = personKey(r);
  try {
    const d = await api.post(props.api, '/pool/refetch_one', {
      server_id: r.server_id, emby_person_id: r.emby_person_id, name_original: r.name_original,
    });
    notify(d?.message || '已重新拉取', 'success');
    loadList(true); loadStatus();
  } catch (e) {
    notify(e.message, 'error');
  }
  refetchKey.value = '';
}

// ── 拉取 ──
function openFetch() {
  fetchDlg.value = true;
}

async function doFetch() {
  if (!guard.check('拉取人名')) return   // v4.6.70：统一守卫
  busy.value = true;
  try {
    const d = await api.post(props.api, '/pool/fetch', { scope: scope.value });
    notify(d?.message || '拉取已启动', 'success');
    fetchDlg.value = false;
    fetchState.value = { running: true, total: 0, done: 0, current: '准备中…' };
    setTimeout(loadStatus, 600);
  } catch (e) {
    notify(e.message, 'error');
  }
  busy.value = false;
}

async function doRescreen() {
  if (!guard.check('按当前设置重筛池')) return   // v4.6.70：统一守卫
  busy.value = true;
  try {
    const d = await api.post(props.api, '/pool/rescreen', {});
    notify(d?.message || '已重筛', 'success');
    refreshAll(true);
  } catch (e) {
    notify(e.message, 'error');
  }
  busy.value = false;
}

// ── 批量翻译 / 同步 ──
function openTranslate() {
  if (!counts.value.pending) { notify('没有待翻译的人名', 'info'); return }
  transSync.value = false;
  transDlg.value = true;
}

async function doTranslate() {
  if (!guard.check('人名池批量翻译')) return   // v4.6.70：统一守卫
  busy.value = true;
  try {
    const d = await api.post(props.api, '/pool/translate', { sync_after: transSync.value });
    notify(d?.message || '已交后台翻译', 'success');
    transDlg.value = false;
    loadStatus();
  } catch (e) {
    notify(e.message, 'error');
  }
  busy.value = false;
}

function openSync() {
  if (!counts.value.translated) { notify('没有待同步的人名', 'info'); return }
  syncDlg.value = true;
}

async function doSync() {
  if (!guard.check('人名池批量同步')) return   // v4.6.70：统一守卫
  busy.value = true;
  try {
    const d = await api.post(props.api, '/pool/sync', {});
    notify(d?.message || '批量同步已启动', 'success');
    syncDlg.value = false;
    loadStatus();
  } catch (e) {
    notify(e.message, 'error');
  }
  busy.value = false;
}

function startPoll() {
  if (timer) return
  timer = setInterval(() => { loadStatus(); if (pulling.value) loadList(true); }, 3000);
}
function stopPoll() {
  if (timer) { clearInterval(timer); timer = null; }
}
onMounted$2(() => {
  refreshAll();
  startPoll();
  document.addEventListener('pointerdown', onDocPointerDown);
});

onActivated$1(() => { refreshAll(true); startPoll(); });

watch$1(() => props.refreshKey, () => { refreshAll(true); });

onDeactivated(stopPoll);

onBeforeUnmount(() => {
  stopPoll();
  document.removeEventListener('pointerdown', onDocPointerDown);
});

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
  const _component_v_text_field = _resolveComponent$2("v-text-field");
  const _component_v_pagination = _resolveComponent$2("v-pagination");
  const _component_v_checkbox = _resolveComponent$2("v-checkbox");
  const _component_v_dialog = _resolveComponent$2("v-dialog");
  const _component_v_radio = _resolveComponent$2("v-radio");
  const _component_v_radio_group = _resolveComponent$2("v-radio-group");

  return (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
    _createElementVNode$2("div", _hoisted_2$2, [
      _createElementVNode$2("span", _hoisted_3$2, "共 " + _toDisplayString$2(counts.value.total) + " 人 · 待翻 " + _toDisplayString$2(counts.value.pending) + " · 待同步 " + _toDisplayString$2(counts.value.translated) + " · 已同步 " + _toDisplayString$2(counts.value.synced) + "（其中原文已是中文 " + _toDisplayString$2(counts.value.no_change) + "）", 1),
      _createElementVNode$2("div", _hoisted_4$2, [
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "flat",
          color: "info",
          "prepend-icon": "mdi-cloud-download-outline",
          class: "epl-act-fetch",
          disabled: poolFetchDisabled.value,
          title: poolFetchTitle.value,
          onClick: openFetch
        }, {
          default: _withCtx$2(() => [...(_cache[20] || (_cache[20] = [
            _createTextVNode$2("拉取人名", -1)
          ]))]),
          _: 1
        }, 8, ["disabled", "title"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "flat",
          color: "primary",
          "prepend-icon": "mdi-translate",
          disabled: !pluginEnabled.value,
          title: pluginOffTitle.value,
          onClick: openTranslate
        }, {
          default: _withCtx$2(() => [...(_cache[21] || (_cache[21] = [
            _createTextVNode$2("批量翻译", -1)
          ]))]),
          _: 1
        }, 8, ["disabled", "title"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "flat",
          color: "success",
          "prepend-icon": "mdi-sync",
          disabled: poolSyncDisabled.value,
          title: poolFetchTitle.value || pluginOffTitle.value,
          onClick: openSync
        }, {
          default: _withCtx$2(() => [...(_cache[22] || (_cache[22] = [
            _createTextVNode$2("批量同步", -1)
          ]))]),
          _: 1
        }, 8, ["disabled", "title"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "tonal",
          color: "error",
          "prepend-icon": "mdi-delete-sweep-outline",
          disabled: poolDataOpBlocked.value,
          title: poolDataOpBlockedHint.value,
          loading: poolBusy.value === 'clear',
          onClick: clearPool
        }, {
          default: _withCtx$2(() => [...(_cache[23] || (_cache[23] = [
            _createTextVNode$2("清除人名池", -1)
          ]))]),
          _: 1
        }, 8, ["disabled", "title", "loading"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "tonal",
          "prepend-icon": "mdi-export-variant",
          disabled: !pluginEnabled.value,
          title: pluginOffTitle.value,
          loading: poolBusy.value === 'export',
          onClick: exportPool
        }, {
          default: _withCtx$2(() => [...(_cache[24] || (_cache[24] = [
            _createTextVNode$2("导出", -1)
          ]))]),
          _: 1
        }, 8, ["disabled", "title", "loading"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "tonal",
          "prepend-icon": "mdi-import",
          disabled: poolDataOpBlocked.value,
          title: poolDataOpBlockedHint.value,
          loading: poolBusy.value === 'import',
          onClick: pickPoolImport
        }, {
          default: _withCtx$2(() => [...(_cache[25] || (_cache[25] = [
            _createTextVNode$2("导入", -1)
          ]))]),
          _: 1
        }, 8, ["disabled", "title", "loading"]),
        _createElementVNode$2("input", {
          ref_key: "poolImportInput",
          ref: poolImportInput,
          type: "file",
          accept: ".json,application/json",
          style: {"display":"none"},
          onChange: onPoolImportPick
        }, null, 544)
      ])
    ]),
    (pulling.value || fetchState.value.total)
      ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_5$2, [
          _createElementVNode$2("div", _hoisted_6$2, [
            _createVNode$2(_component_v_icon, { size: "16" }, {
              default: _withCtx$2(() => [...(_cache[26] || (_cache[26] = [
                _createTextVNode$2("mdi-progress-download", -1)
              ]))]),
              _: 1
            }),
            (pulling.value)
              ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_7$2, [
                  _createTextVNode$2("已拉取 " + _toDisplayString$2(fetchState.value.done || 0) + " / " + _toDisplayString$2(fetchState.value.total || '…') + " ", 1),
                  (fetchState.value.current)
                    ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_8$2, "· " + _toDisplayString$2(fetchState.value.current), 1))
                    : _createCommentVNode$2("", true)
                ]))
              : (_openBlock$2(), _createElementBlock$2("span", _hoisted_9$2, "上次拉取：新增 " + _toDisplayString$2(fetchState.value.added || 0) + " · 更新 " + _toDisplayString$2(fetchState.value.updated || 0) + " · 无变化 " + _toDisplayString$2(fetchState.value.unchanged || 0) + " · 过滤 " + _toDisplayString$2(fetchState.value.filtered || 0) + " · 失败 " + _toDisplayString$2(fetchState.value.failed || 0), 1)),
            (paused.value)
              ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_10$2, "⏸ 已暂停"))
              : _createCommentVNode$2("", true),
            (pulling.value && !paused.value)
              ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 3,
                  size: "x-small",
                  variant: "tonal",
                  color: "warning",
                  class: "epl-pool-pause-btn",
                  disabled: !pluginEnabled.value,
                  onClick: pauseFetch
                }, {
                  default: _withCtx$2(() => [...(_cache[27] || (_cache[27] = [
                    _createTextVNode$2("暂停", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"]))
              : _createCommentVNode$2("", true),
            (pulling.value && paused.value)
              ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 4,
                  size: "x-small",
                  variant: "flat",
                  color: "success",
                  class: "epl-pool-pause-btn",
                  disabled: !pluginEnabled.value,
                  onClick: resumeFetch
                }, {
                  default: _withCtx$2(() => [...(_cache[28] || (_cache[28] = [
                    _createTextVNode$2("继续", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"]))
              : _createCommentVNode$2("", true)
          ]),
          _createVNode$2(_component_v_progress_linear, {
            "model-value": fetchPercent.value,
            height: "6",
            rounded: "",
            color: "info",
            indeterminate: pulling.value && !fetchPercent.value
          }, null, 8, ["model-value", "indeterminate"])
        ]))
      : _createCommentVNode$2("", true),
    (txState.value.requested || txPaused.value)
      ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_11$1, [
          _createElementVNode$2("div", _hoisted_12$1, [
            _createVNode$2(_component_v_icon, { size: "16" }, {
              default: _withCtx$2(() => [...(_cache[29] || (_cache[29] = [
                _createTextVNode$2("mdi-translate", -1)
              ]))]),
              _: 1
            }),
            (txPaused.value)
              ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_13$1, "⏸ 翻译已暂停（手动）"))
              : (_openBlock$2(), _createElementBlock$2("span", _hoisted_14$1, [
                  _createTextVNode$2("AI 翻译中" + _toDisplayString$2(txState.value.scope ? '（' + txState.value.scope + '）' : ''), 1),
                  (txState.value.total)
                    ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 0 }, [
                        _createTextVNode$2(" · " + _toDisplayString$2(txState.value.done || 0) + "/" + _toDisplayString$2(txState.value.total), 1)
                      ], 64))
                    : _createCommentVNode$2("", true),
                  (txState.value.current)
                    ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 1 }, [
                        _createTextVNode$2(" · " + _toDisplayString$2(txState.value.current), 1)
                      ], 64))
                    : _createCommentVNode$2("", true)
                ])),
            (!txPaused.value)
              ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 2,
                  size: "x-small",
                  variant: "tonal",
                  color: "warning",
                  class: "epl-pool-pause-btn",
                  disabled: !pluginEnabled.value,
                  onClick: pauseTranslate
                }, {
                  default: _withCtx$2(() => [...(_cache[30] || (_cache[30] = [
                    _createTextVNode$2("暂停", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"]))
              : (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 3,
                  size: "x-small",
                  variant: "flat",
                  color: "success",
                  class: "epl-pool-pause-btn",
                  disabled: !pluginEnabled.value,
                  onClick: resumeTranslate
                }, {
                  default: _withCtx$2(() => [...(_cache[31] || (_cache[31] = [
                    _createTextVNode$2("继续", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"]))
          ])
        ]))
      : _createCommentVNode$2("", true),
    _createElementVNode$2("div", {
      ref_key: "filterRef",
      ref: filterRef,
      class: "epl-pool-filter",
      onClick: _cache[2] || (_cache[2] = $event => (filterOpen.value = true))
    }, [
      _createElementVNode$2("div", _hoisted_15$1, [
        _createVNode$2(_component_v_text_field, {
          modelValue: keyword.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((keyword).value = $event)),
          density: "compact",
          variant: "outlined",
          "hide-details": "",
          placeholder: "搜索 原文 / 译名…",
          "prepend-inner-icon": "mdi-magnify",
          class: "epl-pool-search",
          clearable: "",
          onKeyup: _withKeys(onSearch, ["enter"]),
          "onClick:clear": onSearch
        }, null, 8, ["modelValue"]),
        (selCount.value)
          ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_16$1, "已选 " + _toDisplayString$2(selCount.value) + " 项", 1))
          : _createCommentVNode$2("", true),
        _createVNode$2(_component_v_btn, {
          size: "x-small",
          variant: "text",
          icon: "",
          class: "epl-pool-expand",
          "aria-expanded": filterOpen.value ? 'true' : 'false',
          onClick: _cache[1] || (_cache[1] = _withModifiers($event => (filterOpen.value = !filterOpen.value), ["stop"]))
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_icon, {
              icon: filterOpen.value ? 'mdi-chevron-up' : 'mdi-chevron-down'
            }, null, 8, ["icon"])
          ]),
          _: 1
        }, 8, ["aria-expanded"])
      ]),
      (filterOpen.value)
        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_17$1, [
            _createElementVNode$2("div", _hoisted_18$1, [
              _createElementVNode$2("div", _hoisted_19$1, [
                _cache[32] || (_cache[32] = _createElementVNode$2("span", { class: "epl-pool-chips-label" }, "类型", -1)),
                (_openBlock$2(), _createElementBlock$2(_Fragment$2, null, _renderList$2(TYPE_FILTERS, (t) => {
                  return _createElementVNode$2("button", {
                    key: 't' + t.value,
                    type: "button",
                    class: _normalizeClass$1(["epl-chip", { 'is-on': type.value === t.value }]),
                    onClick: $event => (changeType(t.value))
                  }, _toDisplayString$2(t.title), 11, _hoisted_20$1)
                }), 64))
              ]),
              _createElementVNode$2("div", _hoisted_21$1, [
                _cache[33] || (_cache[33] = _createElementVNode$2("span", { class: "epl-pool-chips-label" }, "状态", -1)),
                (_openBlock$2(), _createElementBlock$2(_Fragment$2, null, _renderList$2(STATUS_FILTERS, (s) => {
                  return _createElementVNode$2("button", {
                    key: 's' + s.value,
                    type: "button",
                    class: _normalizeClass$1(["epl-chip", { 'is-on': status.value === s.value }]),
                    onClick: $event => (changeStatus(s.value))
                  }, _toDisplayString$2(s.title), 11, _hoisted_22$1)
                }), 64))
              ])
            ]),
            _createVNode$2(_component_v_btn, {
              size: "x-small",
              variant: "text",
              class: "epl-pool-reset",
              onClick: resetFilter
            }, {
              default: _withCtx$2(() => [...(_cache[34] || (_cache[34] = [
                _createTextVNode$2("重置", -1)
              ]))]),
              _: 1
            })
          ]))
        : _createCommentVNode$2("", true)
    ], 512),
    _createElementVNode$2("div", _hoisted_23$1, [
      _cache[38] || (_cache[38] = _createStaticVNode("<div class=\"epl-pool-th\" data-v-a3db2143><span class=\"c-name\" data-v-a3db2143>原文名</span><span class=\"c-zh\" data-v-a3db2143>译名</span><span class=\"c-type\" data-v-a3db2143>类型</span><span class=\"c-status\" data-v-a3db2143>状态</span><span class=\"c-occ\" data-v-a3db2143>出现</span><span class=\"c-op\" data-v-a3db2143>操作</span></div>", 1)),
      (loading.value)
        ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
            key: 0,
            indeterminate: "",
            color: "primary",
            height: "3"
          }))
        : _createCommentVNode$2("", true),
      (!loading.value && !rows.value.length)
        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_24$1, " 池里还没有人——点右上「拉取人名」把 Emby 的 Person 拉进来 "))
        : _createCommentVNode$2("", true),
      (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(rows.value, (r) => {
        return (_openBlock$2(), _createElementBlock$2(_Fragment$2, {
          key: personKey(r)
        }, [
          _createElementVNode$2("div", _hoisted_25$1, [
            _createElementVNode$2("span", {
              class: "c-name",
              title: r.name_current || r.name_original
            }, _toDisplayString$2(r.name_original), 9, _hoisted_26$1),
            _createElementVNode$2("span", {
              class: "c-zh",
              title: r.name_zh
            }, _toDisplayString$2(zhText(r) || '—'), 9, _hoisted_27$1),
            _createElementVNode$2("span", _hoisted_28$1, _toDisplayString$2(typeText(r)), 1),
            _createElementVNode$2("span", _hoisted_29$1, [
              _createElementVNode$2("span", {
                class: _normalizeClass$1(["epl-badge", 'st-' + statusChip(r).color])
              }, _toDisplayString$2(statusChip(r).dot) + " " + _toDisplayString$2(statusChip(r).text), 3)
            ]),
            _createElementVNode$2("span", _hoisted_30$1, [
              _createVNode$2(_component_v_btn, {
                size: "x-small",
                variant: "text",
                density: "compact",
                onClick: $event => (toggleOcc(r))
              }, {
                default: _withCtx$2(() => [
                  _createTextVNode$2(_toDisplayString$2(occOpen.value === personKey(r) ? '收起' : '查看'), 1)
                ]),
                _: 2
              }, 1032, ["onClick"])
            ]),
            _createElementVNode$2("span", _hoisted_31$1, [
              _createVNode$2(_component_v_btn, {
                size: "x-small",
                variant: "flat",
                color: "primary",
                density: "comfortable",
                onClick: $event => (openEdit(r))
              }, {
                default: _withCtx$2(() => [...(_cache[35] || (_cache[35] = [
                  _createTextVNode$2("改", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"]),
              (canSync(r))
                ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                    key: 0,
                    size: "x-small",
                    variant: "flat",
                    color: "success",
                    density: "comfortable",
                    onClick: $event => (openEdit(r))
                  }, {
                    default: _withCtx$2(() => [...(_cache[36] || (_cache[36] = [
                      _createTextVNode$2("同步", -1)
                    ]))]),
                    _: 1
                  }, 8, ["onClick"]))
                : _createCommentVNode$2("", true),
              _createVNode$2(_component_v_btn, {
                size: "x-small",
                variant: "tonal",
                density: "comfortable",
                title: "从 Emby 重新拉取该人（刷新当前名/类型；legacy 无 ID 行顺带补 Person ID）",
                loading: refetchKey.value === personKey(r),
                onClick: $event => (refetchOne(r))
              }, {
                default: _withCtx$2(() => [...(_cache[37] || (_cache[37] = [
                  _createTextVNode$2("重拉", -1)
                ]))]),
                _: 1
              }, 8, ["loading", "onClick"])
            ])
          ]),
          (occOpen.value === personKey(r))
            ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_32$1, [
                _createElementVNode$2("div", _hoisted_33$1, _toDisplayString$2(r.name_original) + " · " + _toDisplayString$2(occCount(r)), 1),
                (occLoading.value)
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_34$1, "查询中…"))
                  : (!occRows.value.length)
                    ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_35$1, "库里没有该人名的作品记录（可能其作品尚未扫描入库）"))
                    : (_openBlock$2(), _createElementBlock$2("ul", _hoisted_36$1, [
                        (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(occUnique.value, (g, i) => {
                          return (_openBlock$2(), _createElementBlock$2("li", { key: i }, [
                            _createElementVNode$2("span", _hoisted_37$1, "《" + _toDisplayString$2(g.title) + "》", 1),
                            (g.count > 1)
                              ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_38$1, "×" + _toDisplayString$2(g.count), 1))
                              : _createCommentVNode$2("", true),
                            (g.deleted)
                              ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_39$1, "待恢复"))
                              : _createCommentVNode$2("", true)
                          ]))
                        }), 128))
                      ]))
              ]))
            : _createCommentVNode$2("", true)
        ], 64))
      }), 128))
    ]),
    _createElementVNode$2("div", _hoisted_40$1, [
      (!loading.value && !rows.value.length)
        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_41$1, " 池里还没有人——点上方「拉取人名」把 Emby 的 Person 拉进来 "))
        : _createCommentVNode$2("", true),
      (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(rows.value, (r) => {
        return (_openBlock$2(), _createElementBlock$2("div", {
          key: 'm' + personKey(r),
          class: "epl-person-card"
        }, [
          _createElementVNode$2("div", _hoisted_42$1, [
            _createElementVNode$2("span", {
              class: "person-card-name",
              title: r.name_original
            }, _toDisplayString$2(r.name_original), 9, _hoisted_43$1),
            _createElementVNode$2("span", {
              class: _normalizeClass$1(["epl-badge", 'st-' + statusChip(r).color])
            }, _toDisplayString$2(statusChip(r).dot) + " " + _toDisplayString$2(statusChip(r).text), 3)
          ]),
          _createElementVNode$2("div", _hoisted_44$1, [
            _createElementVNode$2("span", {
              class: "person-card-zh",
              title: r.name_zh
            }, _toDisplayString$2(zhText(r) || (isChineseText(r.name_original) ? '—' : '— 未译')), 9, _hoisted_45$1),
            _createElementVNode$2("span", _hoisted_46$1, [
              _createVNode$2(_component_v_btn, {
                size: "x-small",
                variant: "flat",
                color: "primary",
                density: "comfortable",
                onClick: $event => (openEdit(r))
              }, {
                default: _withCtx$2(() => [...(_cache[39] || (_cache[39] = [
                  _createTextVNode$2("编辑", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"]),
              (canSync(r))
                ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                    key: 0,
                    size: "x-small",
                    variant: "flat",
                    color: "success",
                    density: "comfortable",
                    onClick: $event => (openEdit(r))
                  }, {
                    default: _withCtx$2(() => [...(_cache[40] || (_cache[40] = [
                      _createTextVNode$2("同步", -1)
                    ]))]),
                    _: 1
                  }, 8, ["onClick"]))
                : _createCommentVNode$2("", true),
              _createVNode$2(_component_v_btn, {
                size: "x-small",
                variant: "tonal",
                density: "comfortable",
                title: "从 Emby 重新拉取该人",
                loading: refetchKey.value === personKey(r),
                onClick: $event => (refetchOne(r))
              }, {
                default: _withCtx$2(() => [...(_cache[41] || (_cache[41] = [
                  _createTextVNode$2("重拉", -1)
                ]))]),
                _: 1
              }, 8, ["loading", "onClick"]),
              _createVNode$2(_component_v_btn, {
                size: "x-small",
                variant: "tonal",
                density: "comfortable",
                onClick: $event => (toggleDetail(r))
              }, {
                default: _withCtx$2(() => [
                  _createTextVNode$2(_toDisplayString$2(detailOpen.value === rowKey(r) ? '收起' : '更多'), 1)
                ]),
                _: 2
              }, 1032, ["onClick"])
            ])
          ]),
          (detailOpen.value === rowKey(r))
            ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_47$1, [
                _createElementVNode$2("div", _hoisted_48$1, [
                  _cache[42] || (_cache[42] = _createElementVNode$2("span", { class: "person-card-k" }, "类型", -1)),
                  _createElementVNode$2("span", _hoisted_49$1, _toDisplayString$2(typeText(r)), 1)
                ]),
                _createElementVNode$2("div", _hoisted_50$1, [
                  _cache[43] || (_cache[43] = _createElementVNode$2("span", { class: "person-card-k" }, "Emby 当前", -1)),
                  _createElementVNode$2("span", _hoisted_51$1, _toDisplayString$2(r.name_current || '—'), 1)
                ]),
                _createElementVNode$2("div", _hoisted_52$1, [
                  _createVNode$2(_component_v_btn, {
                    size: "x-small",
                    variant: "tonal",
                    onClick: $event => (toggleOcc(r))
                  }, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(occOpen.value === rowKey(r) ? '收起作品' : '出现作品'), 1)
                    ]),
                    _: 2
                  }, 1032, ["onClick"])
                ]),
                (occOpen.value === rowKey(r))
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_53$1, [
                      _createElementVNode$2("div", _hoisted_54$1, _toDisplayString$2(r.name_original) + " · " + _toDisplayString$2(occCount(r)), 1),
                      (occLoading.value)
                        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_55$1, "查询中…"))
                        : (!occRows.value.length)
                          ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_56$1, "库里没有该人名的作品记录（可能其作品尚未扫描入库）"))
                          : (_openBlock$2(), _createElementBlock$2("ul", _hoisted_57$1, [
                              (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(occUnique.value, (g, i) => {
                                return (_openBlock$2(), _createElementBlock$2("li", { key: i }, [
                                  _createElementVNode$2("span", _hoisted_58$1, "《" + _toDisplayString$2(g.title) + "》", 1),
                                  (g.count > 1)
                                    ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_59$1, "×" + _toDisplayString$2(g.count), 1))
                                    : _createCommentVNode$2("", true),
                                  (g.deleted)
                                    ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_60$1, "待恢复"))
                                    : _createCommentVNode$2("", true)
                                ]))
                              }), 128))
                            ]))
                    ]))
                  : _createCommentVNode$2("", true)
              ]))
            : _createCommentVNode$2("", true)
        ]))
      }), 128))
    ]),
    (total.value > size.value)
      ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_61$1, [
          _createVNode$2(_component_v_pagination, {
            modelValue: page.value,
            "onUpdate:modelValue": [
              _cache[3] || (_cache[3] = $event => ((page).value = $event)),
              _cache[4] || (_cache[4] = $event => (loadList()))
            ],
            length: Math.ceil(total.value / size.value),
            "total-visible": "7",
            density: "compact"
          }, null, 8, ["modelValue", "length"])
        ]))
      : _createCommentVNode$2("", true),
    _createVNode$2(_component_v_dialog, {
      modelValue: editDlg.value,
      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((editDlg).value = $event)),
      "max-width": "460"
    }, {
      default: _withCtx$2(() => [
        _createElementVNode$2("div", _hoisted_62$1, [
          _cache[50] || (_cache[50] = _createElementVNode$2("div", { class: "epl-dlg-title" }, "编辑人名", -1)),
          _createElementVNode$2("div", _hoisted_63$1, [
            _createElementVNode$2("div", _hoisted_64$1, [
              _cache[44] || (_cache[44] = _createElementVNode$2("span", { class: "epl-field-k" }, "原文", -1)),
              _createElementVNode$2("span", _hoisted_65$1, _toDisplayString$2(editRow.value?.name_original), 1)
            ]),
            _createElementVNode$2("div", _hoisted_66$1, [
              _cache[45] || (_cache[45] = _createElementVNode$2("span", { class: "epl-field-k" }, "Emby 当前", -1)),
              _createElementVNode$2("span", _hoisted_67$1, _toDisplayString$2(editRow.value?.name_current || '（未记录）'), 1)
            ]),
            _createElementVNode$2("div", _hoisted_68$1, [
              _cache[46] || (_cache[46] = _createElementVNode$2("span", { class: "epl-field-k" }, "类型", -1)),
              _createElementVNode$2("span", _hoisted_69$1, _toDisplayString$2(typeText(editRow.value)), 1)
            ]),
            _createVNode$2(_component_v_text_field, {
              modelValue: editZh.value,
              "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((editZh).value = $event)),
              label: "译名",
              density: "compact",
              variant: "outlined",
              "hide-details": "",
              class: "epl-dlg-input",
              placeholder: "留空 = 清除译文"
            }, null, 8, ["modelValue"]),
            _createVNode$2(_component_v_checkbox, {
              modelValue: editSyncEmby.value,
              "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((editSyncEmby).value = $event)),
              density: "compact",
              "hide-details": "",
              color: "primary",
              label: "同步到 Emby（改 Emby 演员名，全局生效；默认不改）"
            }, null, 8, ["modelValue"]),
            _cache[47] || (_cache[47] = _createElementVNode$2("div", { class: "epl-dlg-tip" }, "保存只改人名池（manual 最高优先级，AI 不覆盖）。勾选上方选项后保存会同时改 Emby Person 实体名（全局生效）。", -1))
          ]),
          _createElementVNode$2("div", _hoisted_70$1, [
            _createVNode$2(_component_v_btn, {
              variant: "text",
              onClick: _cache[7] || (_cache[7] = $event => (editDlg.value = false))
            }, {
              default: _withCtx$2(() => [...(_cache[48] || (_cache[48] = [
                _createTextVNode$2("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode$2(_component_v_btn, {
              variant: "flat",
              color: "primary",
              loading: busy.value,
              onClick: _cache[8] || (_cache[8] = $event => (editSyncEmby.value ? syncOne() : saveEdit()))
            }, {
              default: _withCtx$2(() => [...(_cache[49] || (_cache[49] = [
                _createTextVNode$2("保存", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
        ])
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$2(_component_v_dialog, {
      modelValue: fetchDlg.value,
      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((fetchDlg).value = $event)),
      "max-width": "460"
    }, {
      default: _withCtx$2(() => [
        _createElementVNode$2("div", _hoisted_71$1, [
          _cache[55] || (_cache[55] = _createElementVNode$2("div", { class: "epl-dlg-title" }, "拉取人名", -1)),
          _createElementVNode$2("div", _hoisted_72$1, [
            _cache[51] || (_cache[51] = _createElementVNode$2("div", { class: "epl-dlg-tip" }, "拉取类型跟随设置页「翻译范围」的人名类型开关（不再单独设置）。人物类型优先从 Emby People 关系获取；无法确定类型的全库 Person 不参与按类型筛选，建议使用「已选媒体库」范围。", -1)),
            _createVNode$2(_component_v_radio_group, {
              modelValue: scope.value,
              "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((scope).value = $event)),
              density: "compact",
              "hide-details": "",
              class: "epl-dlg-radio"
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_radio, {
                  value: "libraries",
                  label: "仅已选媒体库中的 Person（推荐，快）"
                }),
                _createVNode$2(_component_v_radio, {
                  value: "all",
                  label: "全库 Person（/Persons 全量，慢）"
                })
              ]),
              _: 1
            }, 8, ["modelValue"])
          ]),
          _createElementVNode$2("div", _hoisted_73$1, [
            _createVNode$2(_component_v_btn, {
              variant: "text",
              onClick: _cache[11] || (_cache[11] = $event => (fetchDlg.value = false))
            }, {
              default: _withCtx$2(() => [...(_cache[52] || (_cache[52] = [
                _createTextVNode$2("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode$2(_component_v_btn, {
              variant: "text",
              color: "warning",
              loading: busy.value,
              onClick: doRescreen
            }, {
              default: _withCtx$2(() => [...(_cache[53] || (_cache[53] = [
                _createTextVNode$2("按当前设置重筛池", -1)
              ]))]),
              _: 1
            }, 8, ["loading"]),
            _createVNode$2(_component_v_btn, {
              variant: "flat",
              color: "info",
              loading: busy.value,
              onClick: doFetch
            }, {
              default: _withCtx$2(() => [...(_cache[54] || (_cache[54] = [
                _createTextVNode$2("开始拉取", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
        ])
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$2(_component_v_dialog, {
      modelValue: transDlg.value,
      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((transDlg).value = $event)),
      "max-width": "420"
    }, {
      default: _withCtx$2(() => [
        _createElementVNode$2("div", _hoisted_74$1, [
          _cache[61] || (_cache[61] = _createElementVNode$2("div", { class: "epl-dlg-title" }, "批量翻译", -1)),
          _createElementVNode$2("div", _hoisted_75$1, [
            _createElementVNode$2("div", _hoisted_76$1, [
              _cache[56] || (_cache[56] = _createElementVNode$2("span", { class: "epl-field-k" }, "待翻译", -1)),
              _createElementVNode$2("span", _hoisted_77$1, _toDisplayString$2(counts.value.pending) + " 个", 1)
            ]),
            _createElementVNode$2("div", _hoisted_78$1, [
              _cache[57] || (_cache[57] = _createElementVNode$2("span", { class: "epl-field-k" }, "无需操作", -1)),
              _createElementVNode$2("span", _hoisted_79$1, _toDisplayString$2(counts.value.no_change) + " 个", 1)
            ]),
            _createVNode$2(_component_v_checkbox, {
              modelValue: transSync.value,
              "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((transSync).value = $event)),
              density: "compact",
              "hide-details": "",
              color: "primary",
              label: "翻译完成后自动同步 Emby（默认关闭）"
            }, null, 8, ["modelValue"]),
            _cache[58] || (_cache[58] = _createElementVNode$2("div", { class: "epl-dlg-tip" }, "翻译由后台常驻 worker 自动完成（限流不丢）；不勾则只写池，之后到「人名池 → 批量同步」手动同步。", -1))
          ]),
          _createElementVNode$2("div", _hoisted_80$1, [
            _createVNode$2(_component_v_btn, {
              variant: "text",
              onClick: _cache[14] || (_cache[14] = $event => (transDlg.value = false))
            }, {
              default: _withCtx$2(() => [...(_cache[59] || (_cache[59] = [
                _createTextVNode$2("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode$2(_component_v_btn, {
              variant: "flat",
              color: "primary",
              loading: busy.value,
              onClick: doTranslate
            }, {
              default: _withCtx$2(() => [...(_cache[60] || (_cache[60] = [
                _createTextVNode$2("开始", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
        ])
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$2(_component_v_dialog, {
      modelValue: syncDlg.value,
      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((syncDlg).value = $event)),
      "max-width": "420"
    }, {
      default: _withCtx$2(() => [
        _createElementVNode$2("div", _hoisted_81$1, [
          _cache[66] || (_cache[66] = _createElementVNode$2("div", { class: "epl-dlg-title" }, "批量同步到 Emby", -1)),
          _createElementVNode$2("div", _hoisted_82$1, [
            _createElementVNode$2("div", _hoisted_83$1, [
              _cache[62] || (_cache[62] = _createElementVNode$2("span", { class: "epl-field-k" }, "待同步", -1)),
              _createElementVNode$2("span", _hoisted_84, _toDisplayString$2(counts.value.translated) + " 个", 1)
            ]),
            _cache[63] || (_cache[63] = _createElementVNode$2("div", { class: "epl-dlg-warn" }, "⚠️ Emby 里改名会全局生效（该 Person 在所有作品中的显示名都会变）。", -1))
          ]),
          _createElementVNode$2("div", _hoisted_85, [
            _createVNode$2(_component_v_btn, {
              variant: "text",
              onClick: _cache[16] || (_cache[16] = $event => (syncDlg.value = false))
            }, {
              default: _withCtx$2(() => [...(_cache[64] || (_cache[64] = [
                _createTextVNode$2("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode$2(_component_v_btn, {
              variant: "flat",
              color: "success",
              loading: busy.value,
              onClick: doSync
            }, {
              default: _withCtx$2(() => [...(_cache[65] || (_cache[65] = [
                _createTextVNode$2("开始", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
        ])
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$2(ConfirmDlg, {
      state: _unref(cState),
      "on-ok": _unref(cOk),
      "on-cancel": _unref(cCancel)
    }, null, 8, ["state", "on-ok", "on-cancel"]),
    _createVNode$2(_sfc_main$4, {
      modelValue: _unref(guard).dlg.value,
      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((_unref(guard).dlg.value) = $event)),
      reason: _unref(guard).reason.value,
      state: _unref(guard).stateLabel.value,
      action: _unref(guard).pendingLabel.value,
      onViewTask: _cache[19] || (_cache[19] = $event => (emit('view-task')))
    }, null, 8, ["modelValue", "reason", "state", "action"])
  ]))
}
}

};
const PeoplePool = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-a3db2143"]]);

const {createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,toDisplayString:_toDisplayString$1,createBlock:_createBlock$1,normalizeClass:_normalizeClass,mergeProps:_mergeProps} = await importShared('vue');


const _hoisted_1$1 = { class: "epl-view" };
const _hoisted_2$1 = { class: "epl-switch-row" };
const _hoisted_3$1 = { class: "epl-switch-row" };
const _hoisted_4$1 = { class: "epl-switch-row" };
const _hoisted_5$1 = { class: "epl-switch-row" };
const _hoisted_6$1 = { class: "epl-switch-row" };
const _hoisted_7$1 = { class: "d-flex align-center mb-1 flex-wrap" };
const _hoisted_8$1 = {
  key: 0,
  class: "epl-switch-desc mb-2"
};
const _hoisted_9$1 = { class: "epl-server-head" };
const _hoisted_10$1 = { class: "epl-server-name" };
const _hoisted_11 = { class: "epl-lib-info" };
const _hoisted_12 = ["title", "onClick"];
const _hoisted_13 = { class: "epl-lib-type" };
const _hoisted_14 = ["title"];
const _hoisted_15 = ["title", "onClick"];
const _hoisted_16 = ["title"];
const _hoisted_17 = ["title", "onClick"];
const _hoisted_18 = { class: "epl-lib-actions" };
const _hoisted_19 = { class: "epl-map-server" };
const _hoisted_20 = { class: "epl-switch-row" };
const _hoisted_21 = { class: "epl-switch-row" };
const _hoisted_22 = { class: "epl-switch-row" };
const _hoisted_23 = { class: "flex-grow-1" };
const _hoisted_24 = { class: "epl-switch-desc" };
const _hoisted_25 = {
  key: 2,
  class: "epl-switch-row"
};
const _hoisted_26 = { class: "flex-grow-1" };
const _hoisted_27 = { class: "epl-switch-desc" };
const _hoisted_28 = { class: "epl-switch-row" };
const _hoisted_29 = { class: "epl-switch-row" };
const _hoisted_30 = { class: "flex-grow-1" };
const _hoisted_31 = { class: "epl-switch-title" };
const _hoisted_32 = { class: "epl-switch-row" };
const _hoisted_33 = { class: "epl-switch-row" };
const _hoisted_34 = { class: "epl-switch-row" };
const _hoisted_35 = { class: "epl-switch-row" };
const _hoisted_36 = {
  key: 3,
  class: "epl-switch-row"
};
const _hoisted_37 = { class: "epl-switch-row" };
const _hoisted_38 = { class: "flex-grow-1" };
const _hoisted_39 = { class: "epl-switch-title" };
const _hoisted_40 = {
  key: 4,
  class: "epl-switch-row"
};
const _hoisted_41 = { class: "d-flex flex-wrap ga-3 mt-1 mb-1" };
const _hoisted_42 = { class: "epl-switch-row mt-1" };
const _hoisted_43 = { class: "epl-switch-row" };
const _hoisted_44 = { class: "epl-switch-row" };
const _hoisted_45 = { class: "epl-switch-row" };
const _hoisted_46 = { class: "flex-grow-1" };
const _hoisted_47 = { class: "epl-switch-title" };
const _hoisted_48 = { class: "epl-switch-row" };
const _hoisted_49 = { class: "epl-switch-row" };
const _hoisted_50 = { class: "epl-switch-row" };
const _hoisted_51 = { class: "epl-switch-row" };
const _hoisted_52 = { class: "epl-switch-row" };
const _hoisted_53 = { class: "epl-switch-row" };
const _hoisted_54 = { class: "epl-switch-row" };
const _hoisted_55 = { class: "epl-switch-row" };
const _hoisted_56 = { class: "flex-grow-1" };
const _hoisted_57 = { class: "epl-switch-title" };
const _hoisted_58 = { class: "epl-switch-row" };
const _hoisted_59 = ["title"];
const _hoisted_60 = { class: "d-flex ga-2" };
const _hoisted_61 = { class: "epl-switch-row" };
const _hoisted_62 = { class: "epl-switch-row" };
const _hoisted_63 = {
  key: 1,
  class: "text-body-2",
  style: {"opacity":"0.75"}
};
const _hoisted_64 = { class: "epl-switch-row" };
const _hoisted_65 = { class: "flex-grow-1" };
const _hoisted_66 = { class: "epl-switch-title" };
const _hoisted_67 = { class: "epl-switch-row" };
const _hoisted_68 = { class: "epl-switch-row" };
const _hoisted_69 = { class: "epl-switch-row" };
const _hoisted_70 = { class: "flex-grow-1" };
const _hoisted_71 = { class: "epl-switch-title" };
const _hoisted_72 = { class: "d-flex ga-2 flex-wrap mt-2" };
const _hoisted_73 = { class: "d-flex align-center mb-1" };
const _hoisted_74 = { class: "epl-switch-row" };
const _hoisted_75 = { class: "epl-switch-row" };
const _hoisted_76 = { class: "epl-switch-row" };
const _hoisted_77 = { class: "d-flex justify-end mt-2" };
const _hoisted_78 = { class: "d-flex ga-1 mb-2 flex-wrap align-center" };
const _hoisted_79 = { class: "epl-browse-list" };
const _hoisted_80 = ["onClick"];
const _hoisted_81 = { class: "epl-browse-name" };
const _hoisted_82 = { class: "epl-browse-size" };
const _hoisted_83 = {
  key: 0,
  class: "epl-switch-desc"
};

const {computed: computed$1,onMounted: onMounted$1,ref: ref$1} = await importShared('vue');

const {inject: inject$1} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'SettingsView',
  props: {
  api: { type: Object, default: () => ({}) },
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['save', 'notify', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject$1('moviepilot:toast', null);

const DEFAULT = {
  enabled: false,
  enable_ai: true,
  lock_cast: false,
  emby_name_sync: true,
  translate_actor: true,
  translate_director: false,
  translate_writer: false,
  translate_producer: false,
  translate_guest_star: false,     // 客串/配角
  translate_all: false,
  translate_role: true,
  ja_name_policy: 'convert',       // 已合并进演员（固定自动判断），保留键兼容旧配置
  overwrite_chinese: false,
  notify_on_complete: false,
  use_proxy: false,                // 仅插件 LLM 配置时显示
  max_people_per_batch: 30,
  max_guest_per_episode: 5,
  actor_limit: 10,
  guest_limit: 10,
  director_limit: 3,
  writer_limit: 3,
  movie_actor_limit: 10,        // 电影 nfo 演员人数
  movie_guest_limit: 10,        // 电影 nfo 客串/配角人数
  movie_director_limit: 3,      // 电影 nfo 导演人数
  movie_writer_limit: 3,        // 电影 nfo 编剧/制片人人数
  tv_actor_limit: 10,           // 剧 tvshow.nfo 主演人数
  ep_actor_limit: 10,           // 各集 episode.nfo 演员人数
  tv_guest_limit: 10,           // 剧/集 客串/配角人数
  tv_director_limit: 3,         // 剧/集 导演人数
  tv_writer_limit: 3,           // 剧/集 编剧/制片人人数
  schedule_enabled: false,
  schedule_interval_hours: 24,
  probe_enabled: false,
  probe_interval_minutes: 60,
  webhook_delay: 60,
  series_ingest_all: false,   // 整剧全收（含旧集）；默认关 = 只收本次新增的集
  llm_mode: 'system',       // LLM 来源：system=系统配置 / plugin=插件配置
  llm_base_url: '',
  llm_api_key: '',
  has_api_key: false,          // 后端只下发「是否已配置」+ 掩码（SEC-001）
  llm_api_key_masked: '',
  llm_model: '',
  llm_timeout: 120,
  llm_verify_ssl: true,
  translate_batching: 'per_title',
  prompt_template: '',   // AI 翻译引导词，留空用内置默认
  scan_mode: 'nfo',      // 翻译模式 api / nfo
  nfo_roots: '',
  nfo_recursive: true,
  nfo_include_episodes: false,
  nfo_backup: true,       // 写回前自动 .bak 备份（可关闭开关）
  nfo_episode_overwrite: false,   // NFO 剧→集同步（覆盖语义），与 sync_direction=s2e 搭配
  sync_direction: 's2e',
  nfo_preview: false,     // 预览模式：扫描只采集入库原文，不翻译；翻译由库页「全部翻译」触发
  nfo_dead_grace_hours: 24,
  libraries: [],
  pool_fetch_scope: 'libraries',
  pool_fetch_types: ['Actor'],   // 人名池「拉取类型」独立配置（Actor 勾选即含 VoiceActor）
  pool_translation_enabled: true,
  pool_auto_translate: false,
  pool_auto_sync: false,
  pool_keep_unknown: true,
  pool_tmdb_fill: true,
  pool_tmdb_credits: false,
  auto_translate_webhook: false,
  auto_translate_scan: false,
  webhook_enabled: false,
  translate_person: true,
  nfo_path_mappings: [],
  auto_writeback: true,
  llm_min_interval: 3.0,
  llm_tpm_budget: 0,
  llm_thinking_off: true,
  llm_thinking_params: '',
};
const llmModes = [
  { text: '系统配置（MoviePilot 全局）', value: 'system' },
  { text: '插件配置（单独填写）', value: 'plugin' },
];
const config = ref$1({ ...DEFAULT, ...(props.initialConfig || {}) });
const saving = ref$1(false);
const aiOn = computed$1(() => !!config.value.enable_ai);
// SEC-001：API Key 不回显原值 —— 留空 = 保持不变；清除需显式标记
const clearApiKeyFlag = ref$1(false);
const apiKeyPlaceholder = computed$1(() => {
  if (clearApiKeyFlag.value) return '保存后清除该 Key（当前留空）'
  return config.value.has_api_key
    ? `已配置：${config.value.llm_api_key_masked || '****'}（留空 = 保持不变）`
    : '未配置'
});
function clearApiKey() {
  config.value.llm_api_key = '';
  clearApiKeyFlag.value = true;
}

const libs = ref$1([]);
const libBusy = ref$1(false);
const libError = ref$1('');
const checkAllBusy = ref$1(false);
const pathCheck = ref$1({});   // key = `${server_id}:${lib_id}` → 预检结果（/nfo/path/check）

function mappingOf(serverId) {
  const arr = config.value.nfo_path_mappings;
  if (!Array.isArray(arr)) return null
  return arr.find(m => m && m.server_id === serverId) || null
}
function setMapping(serverId, key, val) {
  const arr = Array.isArray(config.value.nfo_path_mappings) ? [...config.value.nfo_path_mappings] : [];
  let m = arr.find(x => x && x.server_id === serverId);
  if (!m) { m = { server_id: serverId, from: '', to: '' }; arr.push(m); }
  m[key] = val == null ? '' : val;
  config.value.nfo_path_mappings = arr;
}
function clearMapping(serverId) {
  const arr = (config.value.nfo_path_mappings || []).filter(m => !(m && m.server_id === serverId));
  config.value.nfo_path_mappings = arr;
}
const libGroups = computed$1(() => {
  const groups = [];
  const byId = {};
  for (const l of (libs.value || [])) {
    const sid = l.server_id || l.skey || '';
    if (!byId[sid]) { byId[sid] = { server_id: sid, server_name: l.server_name || sid || 'Emby', libs: [], mappingFrom: '', mappingTo: '' }; groups.push(byId[sid]); }
    byId[sid].libs.push(l);
  }
  for (const g of groups) {
    const m = mappingOf(g.server_id);
    g.mappingFrom = (m && m.from) || '';
    g.mappingTo = (m && m.to) || '';
  }
  return groups
});
function isLibSelected(fullKey) { return (config.value.libraries || []).includes(fullKey) }
function toggleLib(fullKey, v) {
  const cur = Array.isArray(config.value.libraries) ? [...config.value.libraries] : [];
  const i = cur.indexOf(fullKey);
  if (v && i < 0) cur.push(fullKey);
  else if (!v && i >= 0) cur.splice(i, 1);
  config.value.libraries = cur;
}
const libOpen = ref$1({});
function isLibOpen(l) { return !!libOpen.value[String(l.full_key || l.lib_id || '')] }
function toggleLibOpen(l) {
  const k = String(l.full_key || l.lib_id || '');
  libOpen.value = { ...libOpen.value, [k]: !libOpen.value[k] };
}
function checkOf(l) { return pathCheck.value[`${l.server_id}:${l.lib_id}`] }
function libOk(l) {
  const c = checkOf(l);
  if (c && !c.loading && Object.prototype.hasOwnProperty.call(c, 'exists')) return !!(c.exists && c.is_dir && c.readable)
  return !!(l.path_exists && l.path_readable && l.path_is_dir)
}

async function loadLibs() {
  libBusy.value = true;
  libError.value = '';
  try {
    const r = await api.get(props.api, '/emby_libraries');
    const list = Array.isArray(r) ? r : (r?.data || []);
    libs.value = Array.isArray(list) ? list : [];
    try {
      const cur = config.value.nfo_path_mappings;
      if (!Array.isArray(cur) || cur.length === 0) {
        const rc = await api.get(props.api, '/config');
        const rm = rc?.nfo_path_mappings;
        if (Array.isArray(rm) && rm.length) config.value.nfo_path_mappings = rm;
      }
    } catch (e) { /* 迁移可见性回读，失败不影响主流程 */ }
  } catch (e) {
    libError.value = (e && e.message) || '拉取媒体库失败';
    libs.value = [];
  } finally { libBusy.value = false; }
}

async function testLib(serverId, libId) {
  const key = `${serverId}:${libId}`;
  pathCheck.value = { ...pathCheck.value, [key]: { loading: true, message: '检测中…' } };
  try {
    const r = await api.post(props.api, '/nfo/path/check', { server_id: serverId, lib_id: libId });
    pathCheck.value = { ...pathCheck.value, [key]: r || {} };
    const ok = !!(r && r.exists && r.is_dir && r.readable);
    notify((r && r.message) || (ok ? '路径可访问' : '路径检查失败'), ok ? 'success' : 'error');
  } catch (e) {
    const msg = (e && e.message) || '路径检查失败';
    pathCheck.value = { ...pathCheck.value, [key]: { message: msg } };
    notify(msg, 'error');
  }
}

async function testAllPaths() {
  checkAllBusy.value = true;
  try {
    const r = await api.post(props.api, '/nfo/path/check_all');
    const map = {};
    for (const row of (r?.rows || [])) map[`${row.server_id}:${row.lib_id}`] = row;
    pathCheck.value = { ...pathCheck.value, ...map };
    const ok = r?.ok ?? 0, total = r?.total ?? 0;
    notify(`路径检查完成：${ok}/${total} 可访问`, ok === total ? 'success' : 'error');
  } catch (e) { notify((e && e.message) || '批量检查失败', 'error'); } finally { checkAllBusy.value = false; }
}

const browseDlg = ref$1(false);
const browse = ref$1({ server_id: '', lib_id: '', lib_name: '', root: '', path: '', relative: '', entries: [], loading: false, error: '', check: '' });
async function browseLoad(path = '') {
  const b = browse.value;
  b.loading = true; b.error = ''; b.check = '';
  try {
    const r = await api.get(props.api, '/nfo/path/browse', { server_id: b.server_id, lib_id: b.lib_id, path });
    b.root = r?.root || '';
    b.path = r?.path || '';
    b.relative = r?.relative || '';
    b.entries = Array.isArray(r?.entries) ? r.entries : [];
  } catch (e) { b.error = (e && e.message) || '浏览失败'; b.entries = []; } finally { b.loading = false; }
}
async function browseOpen(serverId, libId, libName) {
  browse.value = { server_id: serverId, lib_id: libId, lib_name: libName || libId, root: '', path: '', relative: '', entries: [], loading: true, error: '', check: '' };
  browseDlg.value = true;
  await browseLoad('');
}
function browseLib(g, l) { browseOpen(l.server_id || g.server_id, l.lib_id, l.lib_name); }
function browseServer(g) {
  if (!g || !g.libs || !g.libs.length) return
  const pick = g.libs.find(l => isLibSelected(l.full_key)) || g.libs[0];
  browseOpen(pick.server_id || g.server_id, pick.lib_id, pick.lib_name);
}
function browseRefresh() { browseLoad(browse.value.path || ''); }
function browseUp() {
  const b = browse.value;
  if (!b.path || !b.root) return
  if (String(b.path).replace(/[\\/]+$/, '') === String(b.root).replace(/[\\/]+$/, '')) return
  const parent = String(b.path).replace(/[\\/][^\\/]*$/, '');
  if (!parent || parent.length < b.root.length) return
  browseLoad(parent);
}
async function browseTest() {
  const b = browse.value;
  const key = `${b.server_id}:${b.lib_id}`;
  b.check = '检测中…';
  try {
    const r = await api.post(props.api, '/nfo/path/check', { server_id: b.server_id, lib_id: b.lib_id });
    pathCheck.value = { ...pathCheck.value, [key]: r || {} };
    b.check = (r && r.message) || '完成';
    notify(b.check, (r && r.exists && r.is_dir && r.readable) ? 'success' : 'error');
  } catch (e) { b.check = (e && e.message) || '测试失败'; notify(b.check, 'error'); }
}
function joinPath(base, name) {
  const b = String(base || '').replace(/[\\/]+$/, '');
  return b ? `${b}/${name}` : name
}
function fmtSize(n) {
  const v = Number(n || 0);
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  if (v < 1024 * 1024 * 1024) return `${(v / 1024 / 1024).toFixed(1)} MB`
  return `${(v / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function notify(msg, type='error') {
  if (toast && typeof toast[type] === 'function') toast[type](msg);
}

const syncDirs = [
  { text: '关闭（不互同步）', value: 'off' },
  { text: '剧 → 集', value: 's2e' },
  { text: '集 → 剧', value: 'e2s' },
];
const syncDirDesc = () => ({
  off: '不做演员互同步：剧集与各集各自翻译，互不影响',
  s2e: '把剧（tvshow.nfo）的演员译文写进各集 episode.nfo（下表可设整份覆盖）',
  e2s: '把各集演员（按上方开关 + 人数过滤并翻译后）合并进剧 tvshow.nfo —— 剧里已有的演员不重复添加',
}[config.value.sync_direction] || '');
const nfoEpisodeOverwrite = computed$1({
  get: () => !!config.value.nfo_episode_overwrite,
  set: v => { config.value.nfo_episode_overwrite = v; },
});
const seriesSyncDesc = () => '关（默认）：只把剧集译文写到各集「已出场」的演员身上（按名字精准匹配，集内客串保留）；开：把剧集主演名单整份替换进每集（含未出场）';

function restorePrompt() {
  config.value.prompt_template = config.value.prompt_default || '';
  notify('已填入默认提示词，记得保存', 'success');
}

ref$1(false);
ref$1(null);

// 人名池拉取类型归一：「演员」勾选即含声优（VoiceActor 不再单列）——
// 去掉历史配置里的 VoiceActor，全空则回落到「演员」。
function _normPoolFetchTypes () {
  const _a = Array.isArray(config.value.pool_fetch_types) ? config.value.pool_fetch_types : [];
  const _f = _a.filter((t) => t !== 'VoiceActor');
  config.value.pool_fetch_types = _f.length ? _f : ['Actor'];
}
async function loadConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await api.get(props.api, '/config');
    if (data && typeof data === 'object') config.value = { ...DEFAULT, ...data };
    _normPoolFetchTypes();
    if (!config.value.prompt_template && data?.prompt_default) {
      config.value.prompt_template = data.prompt_default;
    }
  } catch (e) { /* 保持 initialConfig */ }
}

const llmTestBusy = ref$1(false);
async function testLlm() {
  llmTestBusy.value = true;
  try {
    const r = await api.post(props.api, '/llm/test');
    notify(r?.message || '测试完成', r?.success ? 'success' : 'error');
  } catch (e) { notify((e && e.message) || '测试连接失败', 'error'); } finally { llmTestBusy.value = false; }
}

async function save() {
  saving.value = true;
  try {
    config.value.scan_mode = 'nfo';
    if (typeof props.api?.post === 'function') {
      const payload = { ...config.value };
      if (clearApiKeyFlag.value) payload.clear_api_key = true;
      delete payload.has_api_key;
      delete payload.llm_api_key_masked;
      await api.post(props.api, '/config', payload);
      clearApiKeyFlag.value = false;
      try { const d = await api.get(props.api, '/config'); if (d) { config.value = { ...DEFAULT, ...d }; _normPoolFetchTypes(); } } catch (e) {}
      emit('save', { ...config.value });
      notify('配置已保存并生效', 'success');
    } else {
      emit('save', { ...config.value });
      notify('配置已保存', 'success');
    }
  } catch (e) { notify(e.message || '保存失败', 'error'); }
  finally { saving.value = false; }
}

onMounted$1(() => {
  loadConfig();
  loadLibs();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_chip = _resolveComponent$1("v-chip");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_card_title = _resolveComponent$1("v-card-title");
  const _component_v_switch = _resolveComponent$1("v-switch");
  const _component_v_spacer = _resolveComponent$1("v-spacer");
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_checkbox_btn = _resolveComponent$1("v-checkbox-btn");
  const _component_v_alert = _resolveComponent$1("v-alert");
  const _component_v_text_field = _resolveComponent$1("v-text-field");
  const _component_v_select = _resolveComponent$1("v-select");
  const _component_v_tooltip = _resolveComponent$1("v-tooltip");
  const _component_v_radio = _resolveComponent$1("v-radio");
  const _component_v_radio_group = _resolveComponent$1("v-radio-group");
  const _component_v_divider = _resolveComponent$1("v-divider");
  const _component_v_textarea = _resolveComponent$1("v-textarea");
  const _component_v_card_subtitle = _resolveComponent$1("v-card-subtitle");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mb-3"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_text, { class: "pa-3 d-flex align-center" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, {
              start: "",
              color: "primary"
            }, {
              default: _withCtx$1(() => [...(_cache[61] || (_cache[61] = [
                _createTextVNode$1("mdi-file-document-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[63] || (_cache[63] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
              _createElementVNode$1("div", { class: "font-weight-medium" }, "NFO 本地文件模式"),
              _createElementVNode$1("div", {
                class: "text-caption",
                style: {"opacity":".7"}
              }, "直接读写 nfo 文件（省请求、防刮削覆盖），扫描范围按下方 Emby 媒体库选择")
            ], -1)),
            _createVNode$1(_component_v_chip, {
              size: "x-small",
              color: "success",
              variant: "tonal"
            }, {
              default: _withCtx$1(() => [...(_cache[62] || (_cache[62] = [
                _createTextVNode$1("当前", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mb-3"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, { start: "" }, {
              default: _withCtx$1(() => [...(_cache[64] || (_cache[64] = [
                _createTextVNode$1("mdi-cog-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[65] || (_cache[65] = _createTextVNode$1("基础设置", -1))
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, null, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", _hoisted_2$1, [
              _cache[66] || (_cache[66] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "启用插件"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "开启后扫描/入库时自动翻译演职人员")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.enabled,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.value.enabled) = $event)),
                color: "success",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ]),
            _createElementVNode$1("div", _hoisted_3$1, [
              _cache[67] || (_cache[67] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "AI 翻译（LLM）"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "关闭后仅禁用 LLM 翻译：人名池命中 / 繁转简 / 人工修正照常生效，新词条照常采集入库（保留原文）")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.enable_ai,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.enable_ai) = $event)),
                color: "primary",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ]),
            _createElementVNode$1("div", _hoisted_4$1, [
              _cache[68] || (_cache[68] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "完成时发送通知"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                  _createTextVNode$1("以下任务完成时推送通知（含统计与失败提示）：NFO 扫描 / 全部写回 / "),
                  _createElementVNode$1("b", null, "拉取人名 / 批量翻译 / 批量同步"),
                  _createTextVNode$1("（含「翻译完成后自动同步」）；关闭时以上通知都不发（日志里会提示「未发送通知」）")
                ])
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.notify_on_complete,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.notify_on_complete) = $event)),
                color: "primary",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ]),
            _createElementVNode$1("div", _hoisted_5$1, [
              _cache[69] || (_cache[69] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "Webhook 入库后自动翻译"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                  _createTextVNode$1("本开关只负责"),
                  _createElementVNode$1("b", null, "一个入口：Webhook 入库"),
                  _createTextVNode$1("。关闭（默认）：新条目只解析入库为「待翻译」，不调 LLM，可到「库 → 批量翻译」手动开始；开启：入库后立即交后台翻译 Worker 自动翻译。"),
                  _createElementVNode$1("br"),
                  _createTextVNode$1("三个自动翻译开关是三个独立入口（Webhook 入库 / 扫描·探测库入库 / 拉取人名），互不重复——同一人名先被哪个入口翻到，另一个入口都会命中已有译文，不会重复调 AI。")
                ])
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.auto_translate_webhook,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.auto_translate_webhook) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_6$1, [
              _cache[70] || (_cache[70] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "扫描 / 探测库入库后自动翻译"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                  _createTextVNode$1("本开关只负责"),
                  _createElementVNode$1("b", null, "一个入口：NFO 扫描（含全库扫描）· 探测库入库"),
                  _createTextVNode$1("。关闭（默认）：只入库为「待翻译」，可到「库 → 批量翻译」手动开始；开启：入库后立即交后台翻译 Worker 自动翻译（注意：首次全库扫描一次产生的词条较多，LLM 消耗较高）。"),
                  _createElementVNode$1("br"),
                  _createTextVNode$1("三个自动翻译开关是三个独立入口（Webhook 入库 / 扫描·探测库入库 / 拉取人名），互不重复——同一人名先被哪个入口翻到，另一个入口都会命中已有译文，不会重复调 AI。")
                ])
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.auto_translate_scan,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.auto_translate_scan) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (config.value.scan_mode === 'nfo')
      ? (_openBlock$1(), _createBlock$1(_component_v_card, {
          key: 0,
          variant: "tonal",
          class: "mb-3"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card_title, { class: "text-subtitle-1" }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_icon, { start: "" }, {
                  default: _withCtx$1(() => [...(_cache[71] || (_cache[71] = [
                    _createTextVNode$1("mdi-file-document-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[72] || (_cache[72] = _createTextVNode$1("NFO / 扫描", -1))
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_text, null, {
              default: _withCtx$1(() => [
                _createElementVNode$1("div", _hoisted_7$1, [
                  _cache[77] || (_cache[77] = _createElementVNode$1("div", { class: "epl-section-title" }, "媒体库扫描范围", -1)),
                  _createVNode$1(_component_v_spacer),
                  _createVNode$1(_component_v_btn, {
                    size: "x-small",
                    variant: "text",
                    loading: libBusy.value,
                    onClick: loadLibs
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, {
                        start: "",
                        size: "14"
                      }, {
                        default: _withCtx$1(() => [...(_cache[73] || (_cache[73] = [
                          _createTextVNode$1("mdi-refresh", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[74] || (_cache[74] = _createTextVNode$1("刷新 ", -1))
                    ]),
                    _: 1
                  }, 8, ["loading"]),
                  _createVNode$1(_component_v_btn, {
                    size: "x-small",
                    variant: "tonal",
                    class: "ml-1",
                    loading: checkAllBusy.value,
                    onClick: testAllPaths
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, {
                        start: "",
                        size: "14"
                      }, {
                        default: _withCtx$1(() => [...(_cache[75] || (_cache[75] = [
                          _createTextVNode$1("mdi-check-network-outline", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[76] || (_cache[76] = _createTextVNode$1("测试全部路径 ", -1))
                    ]),
                    _: 1
                  }, 8, ["loading"])
                ]),
                _cache[106] || (_cache[106] = _createElementVNode$1("div", {
                  class: "epl-switch-desc mb-2",
                  style: {"opacity":".7"}
                }, "勾选要处理的媒体库；其映射后的本地目录自动作为扫描根目录（可多选，跨服务器独立配置映射）。点击下方 Emby / MP 路径可直接浏览该目录", -1)),
                (!libGroups.value.length)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_8$1, "未获取到媒体库列表（请检查 Emby 配置后点「刷新」）"))
                  : _createCommentVNode$1("", true),
                (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(libGroups.value, (g) => {
                  return (_openBlock$1(), _createElementBlock$1("div", {
                    key: g.server_id,
                    class: "epl-server-group mb-2"
                  }, [
                    _createElementVNode$1("div", _hoisted_9$1, [
                      _createVNode$1(_component_v_icon, { size: "16" }, {
                        default: _withCtx$1(() => [...(_cache[78] || (_cache[78] = [
                          _createTextVNode$1("mdi-server-network", -1)
                        ]))]),
                        _: 1
                      }),
                      _createElementVNode$1("span", _hoisted_10$1, _toDisplayString$1(g.server_name), 1),
                      (g.mappingFrom)
                        ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                            key: 0,
                            size: "x-small",
                            variant: "tonal",
                            color: "primary",
                            class: "ml-2"
                          }, {
                            default: _withCtx$1(() => [
                              _createTextVNode$1(" mapping " + _toDisplayString$1(g.mappingFrom) + " → " + _toDisplayString$1(g.mappingTo || '（空）'), 1)
                            ]),
                            _: 2
                          }, 1024))
                        : (_openBlock$1(), _createBlock$1(_component_v_chip, {
                            key: 1,
                            size: "x-small",
                            variant: "tonal",
                            class: "ml-2"
                          }, {
                            default: _withCtx$1(() => [...(_cache[79] || (_cache[79] = [
                              _createTextVNode$1("未配置 mapping（用 Emby 原路径）", -1)
                            ]))]),
                            _: 1
                          })),
                      _createVNode$1(_component_v_spacer),
                      _createVNode$1(_component_v_btn, {
                        size: "x-small",
                        variant: "text",
                        onClick: $event => (browseServer(g))
                      }, {
                        default: _withCtx$1(() => [
                          _createVNode$1(_component_v_icon, {
                            start: "",
                            size: "14"
                          }, {
                            default: _withCtx$1(() => [...(_cache[80] || (_cache[80] = [
                              _createTextVNode$1("mdi-folder-search-outline", -1)
                            ]))]),
                            _: 1
                          }),
                          _cache[81] || (_cache[81] = _createTextVNode$1("浏览 ", -1))
                        ]),
                        _: 1
                      }, 8, ["onClick"])
                    ]),
                    (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(g.libs, (l) => {
                      return (_openBlock$1(), _createElementBlock$1("div", {
                        key: l.full_key,
                        class: _normalizeClass(["epl-lib-row", { 'epl-lib-open': isLibOpen(l) }])
                      }, [
                        _createVNode$1(_component_v_checkbox_btn, {
                          density: "compact",
                          "hide-details": "",
                          "model-value": isLibSelected(l.full_key),
                          "onUpdate:modelValue": v => toggleLib(l.full_key, !!v)
                        }, null, 8, ["model-value", "onUpdate:modelValue"]),
                        _createElementVNode$1("div", _hoisted_11, [
                          _createElementVNode$1("div", {
                            class: "epl-lib-name epl-lib-toggle",
                            title: isLibOpen(l) ? '收起' : '展开（查看路径与操作）',
                            onClick: $event => (toggleLibOpen(l))
                          }, [
                            _createVNode$1(_component_v_icon, {
                              size: "16",
                              class: "epl-lib-caret"
                            }, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString$1(isLibOpen(l) ? 'mdi-chevron-down' : 'mdi-chevron-right'), 1)
                              ]),
                              _: 2
                            }, 1024),
                            _createTextVNode$1(" " + _toDisplayString$1(l.lib_name) + " ", 1),
                            _createElementVNode$1("span", _hoisted_13, _toDisplayString$1(l.lib_type || '?'), 1)
                          ], 8, _hoisted_12),
                          (isLibOpen(l))
                            ? (_openBlock$1(), _createElementBlock$1(_Fragment$1, { key: 0 }, [
                                _createElementVNode$1("div", {
                                  class: "epl-lib-path",
                                  title: l.emby_path || ''
                                }, [
                                  _cache[82] || (_cache[82] = _createTextVNode$1(" Emby ", -1)),
                                  _createElementVNode$1("code", {
                                    class: _normalizeClass(["epl-path-link", { 'epl-path-off': !l.emby_path }]),
                                    title: l.emby_path ? '点击浏览该路径' : 'Emby 未上报 Path',
                                    onClick: $event => (l.emby_path && browseLib(g, l))
                                  }, _toDisplayString$1(l.emby_path || '—'), 11, _hoisted_15)
                                ], 8, _hoisted_14),
                                _createElementVNode$1("div", {
                                  class: "epl-lib-path",
                                  title: l.path || ''
                                }, [
                                  _cache[83] || (_cache[83] = _createTextVNode$1(" MP   ", -1)),
                                  _createElementVNode$1("code", {
                                    class: _normalizeClass(["epl-path-link", { 'epl-path-off': !l.path }]),
                                    title: l.path ? '点击浏览该路径' : '该媒体库未解析到本机路径（检查路径映射）',
                                    onClick: $event => (l.path && browseLib(g, l))
                                  }, _toDisplayString$1(l.path || '—'), 11, _hoisted_17)
                                ], 8, _hoisted_16),
                                _createElementVNode$1("div", _hoisted_18, [
                                  _createVNode$1(_component_v_btn, {
                                    size: "x-small",
                                    variant: "text",
                                    onClick: $event => (testLib(l.server_id || g.server_id, l.lib_id))
                                  }, {
                                    default: _withCtx$1(() => [...(_cache[84] || (_cache[84] = [
                                      _createTextVNode$1("测试", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"]),
                                  _createVNode$1(_component_v_btn, {
                                    size: "x-small",
                                    variant: "text",
                                    onClick: $event => (browseLib(g, l))
                                  }, {
                                    default: _withCtx$1(() => [...(_cache[85] || (_cache[85] = [
                                      _createTextVNode$1("浏览", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"])
                                ])
                              ], 64))
                            : _createCommentVNode$1("", true)
                        ]),
                        _createVNode$1(_component_v_chip, {
                          size: "x-small",
                          variant: "tonal",
                          color: libOk(l) ? 'success' : 'error',
                          class: "epl-lib-chip"
                        }, {
                          default: _withCtx$1(() => [
                            _createTextVNode$1(_toDisplayString$1(libOk(l) ? '✅ 可访问' : '❌ 不可访问'), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"])
                      ], 2))
                    }), 128))
                  ]))
                }), 128)),
                (libError.value)
                  ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                      key: 1,
                      type: "warning",
                      variant: "tonal",
                      density: "compact",
                      class: "mb-2",
                      style: {"font-size":"12px"}
                    }, {
                      default: _withCtx$1(() => [
                        _createTextVNode$1(_toDisplayString$1(libError.value), 1)
                      ]),
                      _: 1
                    }))
                  : _createCommentVNode$1("", true),
                _cache[107] || (_cache[107] = _createElementVNode$1("div", { class: "epl-section-title mt-2 mb-1" }, "路径映射（Emby Path → 本机 MP 路径）", -1)),
                _cache[108] || (_cache[108] = _createElementVNode$1("div", {
                  class: "epl-switch-desc mb-2",
                  style: {"opacity":".7"}
                }, "每台服务器各一行（MP 读到几台就显示几行）；未配置的服务器直接使用 Emby 原路径", -1)),
                (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(libGroups.value, (g) => {
                  return (_openBlock$1(), _createElementBlock$1("div", {
                    key: 'map-' + g.server_id,
                    class: "epl-map-row"
                  }, [
                    _createElementVNode$1("div", _hoisted_19, _toDisplayString$1(g.server_name), 1),
                    _createVNode$1(_component_v_text_field, {
                      "model-value": g.mappingFrom,
                      label: "从（Emby）",
                      density: "compact",
                      variant: "outlined",
                      "hide-details": "",
                      placeholder: "/mnt/movies",
                      "onUpdate:modelValue": v => setMapping(g.server_id, 'from', v)
                    }, null, 8, ["model-value", "onUpdate:modelValue"]),
                    _createVNode$1(_component_v_text_field, {
                      "model-value": g.mappingTo,
                      label: "到（MP 本机）",
                      density: "compact",
                      variant: "outlined",
                      "hide-details": "",
                      placeholder: "/media/movies",
                      "onUpdate:modelValue": v => setMapping(g.server_id, 'to', v)
                    }, null, 8, ["model-value", "onUpdate:modelValue"]),
                    _createVNode$1(_component_v_btn, {
                      size: "x-small",
                      variant: "text",
                      disabled: !g.mappingFrom,
                      title: "清除该服务器映射",
                      onClick: $event => (clearMapping(g.server_id))
                    }, {
                      default: _withCtx$1(() => [
                        _createVNode$1(_component_v_icon, { size: "16" }, {
                          default: _withCtx$1(() => [...(_cache[86] || (_cache[86] = [
                            _createTextVNode$1("mdi-close", -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }, 8, ["disabled", "onClick"])
                  ]))
                }), 128)),
                _createElementVNode$1("div", _hoisted_20, [
                  _cache[87] || (_cache[87] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "扫描子文件夹"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "递归扫描子目录里的 nfo")
                  ], -1)),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.nfo_recursive,
                    "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.nfo_recursive) = $event)),
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode$1("div", _hoisted_21, [
                  _cache[88] || (_cache[88] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "处理单集"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "开：逐集收集演员并入库（翻译范围开着就翻、可写回）；关：只翻节目的主演（剧集/电影本身）—— 各集原文仍会入库供「库」页查看/编辑，只是不参与翻译")
                  ], -1)),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.nfo_include_episodes,
                    "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.nfo_include_episodes) = $event)),
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode$1("div", _hoisted_22, [
                  _createElementVNode$1("div", _hoisted_23, [
                    _cache[89] || (_cache[89] = _createElementVNode$1("div", { class: "epl-switch-title" }, "集 / 剧演员同步方向", -1)),
                    _createElementVNode$1("div", _hoisted_24, _toDisplayString$1(syncDirDesc()), 1)
                  ]),
                  _createVNode$1(_component_v_select, {
                    modelValue: config.value.sync_direction,
                    "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.sync_direction) = $event)),
                    items: syncDirs,
                    "item-title": "text",
                    "item-value": "value",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    style: {"max-width":"200px"}
                  }, null, 8, ["modelValue"])
                ]),
                (config.value.sync_direction === 's2e')
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_25, [
                      _createElementVNode$1("div", _hoisted_26, [
                        _cache[90] || (_cache[90] = _createElementVNode$1("div", { class: "epl-switch-title" }, "整份覆盖各集名单（剧→集）", -1)),
                        _createElementVNode$1("div", _hoisted_27, _toDisplayString$1(seriesSyncDesc()), 1)
                      ]),
                      _createVNode$1(_component_v_switch, {
                        modelValue: nfoEpisodeOverwrite.value,
                        "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((nfoEpisodeOverwrite).value = $event)),
                        color: "primary",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]))
                  : _createCommentVNode$1("", true),
                _createElementVNode$1("div", _hoisted_28, [
                  _cache[91] || (_cache[91] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "预览模式（不落盘）"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "开：翻译照常自动进行，但不自动写回 nfo（只写库），确认后到「库」页点「全部写回」统一落盘；关：按本卡片下方的「翻译完自动写回」开关决定是否自动落盘")
                  ], -1)),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.nfo_preview,
                    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.nfo_preview) = $event)),
                    color: "warning",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode$1("div", _hoisted_29, [
                  _createElementVNode$1("div", _hoisted_30, [
                    _createElementVNode$1("div", _hoisted_31, [
                      _cache[94] || (_cache[94] = _createTextVNode$1("翻译完自动写回 nfo ", -1)),
                      _createVNode$1(_component_v_tooltip, {
                        location: "top",
                        "max-width": "460"
                      }, {
                        activator: _withCtx$1(({ props: tp }) => [
                          _createVNode$1(_component_v_icon, _mergeProps({
                            size: "14",
                            class: "ml-1",
                            style: {"opacity":".6"}
                          }, tp), {
                            default: _withCtx$1(() => [...(_cache[92] || (_cache[92] = [
                              _createTextVNode$1("mdi-information-outline", -1)
                            ]))]),
                            _: 1
                          }, 16)
                        ]),
                        default: _withCtx$1(() => [
                          _cache[93] || (_cache[93] = _createTextVNode$1(" 条目里的词条全部翻完（按类型/角色开关、失败清单、池命中综合判定）→ 自动把该条目的 tvshow + 各集 nfo 一起写回； 写回是幂等的：同一条目单飞、内容已是译文不重复落盘、文件被外部替换会重新写、失败自动退避重试（绝不误标成功）。 关闭后翻译只写库，确认后到「库」页点「全部写回」统一落盘；上方「预览模式」开启时同样不自动落盘。 ", -1))
                        ]),
                        _: 1
                      })
                    ]),
                    _cache[95] || (_cache[95] = _createElementVNode$1("div", { class: "epl-switch-desc" }, "开：条目翻完 → 自动写回该条目 nfo（幂等，失败重试）；关：只写库，手动「全部写回」落盘", -1))
                  ]),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.auto_writeback,
                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.auto_writeback) = $event)),
                    color: "primary",
                    "hide-details": "",
                    disabled: config.value.nfo_preview
                  }, null, 8, ["modelValue", "disabled"])
                ]),
                _createElementVNode$1("div", _hoisted_32, [
                  _cache[96] || (_cache[96] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "翻译后锁定 Cast"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "写回 nfo 时写入 <lockedfields>Cast</lockedfields> 只锁定演员字段，Emby 重新刮削/刷新时不会覆盖中文名单，剧情/简介/海报等照常更新（新番简介过几天出中文也不受影响）")
                  ], -1)),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.lock_cast,
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.lock_cast) = $event)),
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode$1("div", _hoisted_33, [
                  _cache[97] || (_cache[97] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "写回前 .bak 备份"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "每次写回 nfo 前自动保留一份 .bak 备份（媒体库里看到的 tvshow.nfo.bak / movie.nfo.bak 就是它）；关闭后不再生成，已生成的 .bak 可手动删除")
                  ], -1)),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.nfo_backup,
                    "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.nfo_backup) = $event)),
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode$1("div", _hoisted_34, [
                  _cache[98] || (_cache[98] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "失效宽限期（小时）"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "检测到 nfo 目录消失后先观察这段时间：期内同 ID 新版本入库自动恢复（洗版无缝、不重问 AI），超期仍未恢复才判定为真删除并清理")
                  ], -1)),
                  _createVNode$1(_component_v_text_field, {
                    modelValue: config.value.nfo_dead_grace_hours,
                    "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.nfo_dead_grace_hours) = $event)),
                    modelModifiers: { number: true },
                    type: "number",
                    min: "1",
                    max: "720",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    style: {"max-width":"110px"},
                    suffix: "小时"
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode$1("div", _hoisted_35, [
                  _cache[99] || (_cache[99] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                    _createElementVNode$1("div", { class: "epl-switch-title" }, "定时全量扫库"),
                    _createElementVNode$1("div", { class: "epl-switch-desc" }, "按设定间隔自动全量扫描已选媒体库（断点续扫增量），兜底插件关闭 / 漏接 Webhook 期间的漏入库条目；后台有任务时自动跳过本轮")
                  ], -1)),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.schedule_enabled,
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.schedule_enabled) = $event)),
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                (config.value.schedule_enabled)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_36, [
                      _cache[100] || (_cache[100] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                        _createElementVNode$1("div", { class: "epl-switch-title" }, "扫库间隔（小时）"),
                        _createElementVNode$1("div", { class: "epl-switch-desc" }, "默认 24 小时，最小值 1")
                      ], -1)),
                      _createVNode$1(_component_v_text_field, {
                        modelValue: config.value.schedule_interval_hours,
                        "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.value.schedule_interval_hours) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "1",
                        max: "720",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        style: {"max-width":"110px"},
                        suffix: "小时"
                      }, null, 8, ["modelValue"])
                    ]))
                  : _createCommentVNode$1("", true),
                _createElementVNode$1("div", _hoisted_37, [
                  _createElementVNode$1("div", _hoisted_38, [
                    _createElementVNode$1("div", _hoisted_39, [
                      _cache[103] || (_cache[103] = _createTextVNode$1("探测库 ", -1)),
                      _createVNode$1(_component_v_tooltip, {
                        location: "top",
                        "max-width": "460"
                      }, {
                        activator: _withCtx$1(({ props: tp }) => [
                          _createVNode$1(_component_v_icon, _mergeProps({
                            size: "14",
                            class: "ml-1",
                            style: {"opacity":".6"}
                          }, tp), {
                            default: _withCtx$1(() => [...(_cache[101] || (_cache[101] = [
                              _createTextVNode$1("mdi-information-outline", -1)
                            ]))]),
                            _: 1
                          }, 16)
                        ]),
                        default: _withCtx$1(() => [
                          _cache[102] || (_cache[102] = _createTextVNode$1(" 定时把 Emby 的清单与插件库对一遍，双向都能发现差异：①正向 —— Emby 有、插件库没有的集/整部新条目 → 自动补翻（关插件期间漏的入库都靠它）；②反向 —— 插件库有、Emby 已没有的集（服务器删了但可能漏接删除事件）→ 自动标记「待恢复」观察期，期间重新入库会自动恢复、到期未回来则清理。每轮先做只读对差（计数没变就直接结束），发现缺口才动。本地文件级兜底（Emby 没刮到、nfo 被改过、写失败重试）靠上面的「定时全量扫库」。「NFO 扫描」只管本地文件、不查 Emby 清单，三者互补。手动跑一轮去仪表盘「运行操作」点「探测库」。 ", -1))
                        ]),
                        _: 1
                      })
                    ]),
                    _cache[104] || (_cache[104] = _createElementVNode$1("div", { class: "epl-switch-desc" }, "定时双向对账：Emby 缺的补翻、Emby 已删的标「待恢复」", -1))
                  ]),
                  _createVNode$1(_component_v_switch, {
                    modelValue: config.value.probe_enabled,
                    "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.value.probe_enabled) = $event)),
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                (config.value.probe_enabled)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_40, [
                      _cache[105] || (_cache[105] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                        _createElementVNode$1("div", { class: "epl-switch-title" }, "探测间隔（分钟）"),
                        _createElementVNode$1("div", { class: "epl-switch-desc" }, "默认 60，最小 10；每轮先做只读对差（计数没变就直接结束），发现差异才处理 —— 补翻每轮上限 200 个文件、反向标记每轮上限 50 集")
                      ], -1)),
                      _createVNode$1(_component_v_text_field, {
                        modelValue: config.value.probe_interval_minutes,
                        "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((config.value.probe_interval_minutes) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "10",
                        max: "1440",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        style: {"max-width":"110px"},
                        suffix: "分钟"
                      }, null, 8, ["modelValue"])
                    ]))
                  : _createCommentVNode$1("", true)
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
      : _createCommentVNode$1("", true),
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mb-3"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, { start: "" }, {
              default: _withCtx$1(() => [...(_cache[109] || (_cache[109] = [
                _createTextVNode$1("mdi-account-search", -1)
              ]))]),
              _: 1
            }),
            _cache[111] || (_cache[111] = _createTextVNode$1("人名池 ", -1)),
            _createVNode$1(_component_v_chip, {
              size: "x-small",
              class: "ml-2",
              variant: "tonal"
            }, {
              default: _withCtx$1(() => [...(_cache[110] || (_cache[110] = [
                _createTextVNode$1("拉取类型为独立设置（不跟随「翻译范围」）；池里已有人名时改设置后可在「人名池」页点「按当前设置重筛池」", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, null, {
          default: _withCtx$1(() => [
            _cache[120] || (_cache[120] = _createElementVNode$1("div", { class: "epl-switch-row" }, [
              _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "拉取类型（独立）"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                  _createTextVNode$1("拉取 / 扫描入库时把哪些类型的 Person 收进人名池 —— "),
                  _createElementVNode$1("b", null, "独立于「翻译范围」的类型"),
                  _createTextVNode$1("，也不受翻译人数上限约束。「演员（含声优）」勾上即同时收 Actor 与 VoiceActor。")
                ])
              ])
            ], -1)),
            _createElementVNode$1("div", _hoisted_41, [
              _createVNode$1(_component_v_checkbox_btn, {
                modelValue: config.value.pool_fetch_types,
                "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((config.value.pool_fetch_types) = $event)),
                value: "Actor",
                label: "演员（含声优）",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              _createVNode$1(_component_v_checkbox_btn, {
                modelValue: config.value.pool_fetch_types,
                "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((config.value.pool_fetch_types) = $event)),
                value: "GuestStar",
                label: "客串",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              _createVNode$1(_component_v_checkbox_btn, {
                modelValue: config.value.pool_fetch_types,
                "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((config.value.pool_fetch_types) = $event)),
                value: "Director",
                label: "导演",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              _createVNode$1(_component_v_checkbox_btn, {
                modelValue: config.value.pool_fetch_types,
                "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((config.value.pool_fetch_types) = $event)),
                value: "Writer",
                label: "编剧",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              _createVNode$1(_component_v_checkbox_btn, {
                modelValue: config.value.pool_fetch_types,
                "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((config.value.pool_fetch_types) = $event)),
                value: "Producer",
                label: "制片",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ]),
            _cache[121] || (_cache[121] = _createElementVNode$1("div", { class: "epl-switch-row" }, [
              _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "拉取来源"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "仅已选媒体库（遍历库条目的 People，快）／ 全库 Person（/Persons 全量，慢）")
              ])
            ], -1)),
            _createVNode$1(_component_v_radio_group, {
              modelValue: config.value.pool_fetch_scope,
              "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((config.value.pool_fetch_scope) = $event)),
              density: "compact",
              "hide-details": "",
              inline: "",
              class: "mt-1"
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_radio, {
                  value: "libraries",
                  label: "仅已选媒体库（推荐）"
                }),
                _createVNode$1(_component_v_radio, {
                  value: "all",
                  label: "全库 Person"
                })
              ]),
              _: 1
            }, 8, ["modelValue"]),
            _cache[122] || (_cache[122] = _createElementVNode$1("div", { class: "epl-switch-row mt-3" }, [
              _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "类型未知的人物是否保留？"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "类型未知（Emby 关系里取不到职位）≠ 演员，列表显示为「未分类」；保留时「按当前设置重筛池」不会删除它们")
              ])
            ], -1)),
            _createVNode$1(_component_v_radio_group, {
              modelValue: config.value.pool_keep_unknown,
              "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((config.value.pool_keep_unknown) = $event)),
              density: "compact",
              "hide-details": "",
              inline: "",
              class: "mt-1"
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_radio, {
                  value: true,
                  label: "保留未分类（推荐）"
                }),
                _createVNode$1(_component_v_radio, {
                  value: false,
                  label: "过滤未分类"
                })
              ]),
              _: 1
            }, 8, ["modelValue"]),
            _createElementVNode$1("div", _hoisted_42, [
              _cache[112] || (_cache[112] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "人名池翻译总开关"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "关闭后，池里 pending 的人名不再交给 Worker 翻译（已翻/已同步的条目不受影响）。池条目是否翻译由本开关独立决定")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.pool_translation_enabled,
                "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((config.value.pool_translation_enabled) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_43, [
              _cache[113] || (_cache[113] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "自动翻译新拉取的人名"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                  _createTextVNode$1("本开关只负责"),
                  _createElementVNode$1("b", null, "一个入口：拉取人名（写入「人名池」）"),
                  _createTextVNode$1("。关闭（默认）：拉取只入池、不调 LLM，可到「人名池 → 批量翻译」手动开始；开启：拉取结束后立即交后台翻译 Worker 自动翻译新入池的人物。"),
                  _createElementVNode$1("br"),
                  _createTextVNode$1("三个自动翻译开关是三个独立入口（Webhook 入库 / 扫描·探测库入库 / 拉取人名），互不重复——同一人名先被哪个入口翻到，另一个入口都会命中已有译文，不会重复调 AI。")
                ])
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.pool_auto_translate,
                "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((config.value.pool_auto_translate) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !config.value.pool_translation_enabled || !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_44, [
              _cache[114] || (_cache[114] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "拉取时用 TMDB 刮削补译"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                  _createTextVNode$1("仅对 Emby 当前名非中文的人物：TMDB 有中文别名 → 中文名入池记为 tmdb 来源（繁体在拉取环节即繁转简，一律简体），再由同步流程统一写回 Emby；中文简介/头像即时写回 Emby（简介含锁定）。没有中文名的留给 AI 翻译。已缝合官方「演职人员刮削」，开启后可停用 personmeta 插件。"),
                  _createElementVNode$1("b", null, "不依赖 AI 翻译：TMDB 查询不经 LLM，AI 总开关关闭时同样可用")
                ])
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.pool_tmdb_fill,
                "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((config.value.pool_tmdb_fill) = $event)),
                color: "primary",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ]),
            _createElementVNode$1("div", _hoisted_45, [
              _createElementVNode$1("div", _hoisted_46, [
                _createElementVNode$1("div", _hoisted_47, [
                  _cache[117] || (_cache[117] = _createTextVNode$1("用 TMDB 演职人员表补「第二排角色名」 ", -1)),
                  _createVNode$1(_component_v_tooltip, {
                    location: "top",
                    "max-width": "460"
                  }, {
                    activator: _withCtx$1(({ props: tp }) => [
                      _createVNode$1(_component_v_icon, _mergeProps({
                        size: "14",
                        class: "ml-1",
                        style: {"opacity":".6"}
                      }, tp), {
                        default: _withCtx$1(() => [...(_cache[115] || (_cache[115] = [
                          _createTextVNode$1("mdi-information-outline", -1)
                        ]))]),
                        _: 1
                      }, 16)
                    ]),
                    default: _withCtx$1(() => [
                      _cache[116] || (_cache[116] = _createTextVNode$1(" 豆瓣等来源的 NFO「第二排」（角色名）常为空或只有中文，导致翻译链拿不到英文原文而翻不了； 开启后：按条目的 TMDB ID 拉取演职人员表，用 TMDB 的英文角色名（character）回填这些空/非英文的角色名， 再交给翻译链翻成中文。仅作用于「第二排角色名」范围（受下方「翻译范围 → 第二排角色名」及 Actor/客串等开关约束）； 已有英文角色名的条目不受影响。默认关闭。 ", -1))
                    ]),
                    _: 1
                  })
                ]),
                _cache[118] || (_cache[118] = _createElementVNode$1("div", { class: "epl-switch-desc" }, "开：入库/扫描（含 Webhook）时用 TMDB credits 的英文角色名回填空/非英文角色名再翻；关：保持 NFO 原样 需开启下方「翻译范围 → 第二排角色名」（或「全部类型」），否则不生效", -1))
              ]),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.pool_tmdb_credits,
                "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((config.value.pool_tmdb_credits) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !config.value.translate_role && !config.value.translate_all
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_48, [
              _cache[119] || (_cache[119] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "人名池翻译完成后自动同步 Emby"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "关闭时（默认），翻译只写池，需到「人名池 → 批量同步」手动同步到 Emby；开启后池内待翻全部翻完即自动同步（区别于批量翻译弹窗里一次性的「翻译完成后自动同步」勾选）")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.pool_auto_sync,
                "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((config.value.pool_auto_sync) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mb-3"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, { start: "" }, {
              default: _withCtx$1(() => [...(_cache[123] || (_cache[123] = [
                _createTextVNode$1("mdi-account-multiple-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[125] || (_cache[125] = _createTextVNode$1("翻译范围 ", -1)),
            _createVNode$1(_component_v_chip, {
              size: "x-small",
              class: "ml-2",
              variant: "tonal"
            }, {
              default: _withCtx$1(() => [...(_cache[124] || (_cache[124] = [
                _createTextVNode$1("翻哪排 × 翻哪些类型 × 每类型翻几个", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, null, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_alert, {
              type: "info",
              variant: "tonal",
              density: "compact",
              class: "mb-2",
              style: {"font-size":"12px"}
            }, {
              default: _withCtx$1(() => [...(_cache[126] || (_cache[126] = [
                _createTextVNode$1(" 采集 ≠ 翻译：扫描照常采集入库，本卡片只决定「翻译什么」。下面的", -1),
                _createElementVNode$1("b", null, "类型 + 人数同时对第一排人名与第二排角色名生效", -1),
                _createTextVNode$1(" —— 例如「关第一排 + 开第二排 + 只勾演员」，就只翻演员饰演的角色名。 ", -1)
              ]))]),
              _: 1
            }),
            (!aiOn.value)
              ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                  key: 0,
                  type: "warning",
                  variant: "tonal",
                  density: "compact",
                  class: "mb-2",
                  style: {"font-size":"12px"}
                }, {
                  default: _withCtx$1(() => [...(_cache[127] || (_cache[127] = [
                    _createTextVNode$1(" AI 翻译总开关（LLM）已关闭：本卡片的翻译相关开关暂不可操作；到「基础设置」重新开启「AI 翻译（LLM）」后立即恢复（无需保存）。 ", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode$1("", true),
            _cache[139] || (_cache[139] = _createElementVNode$1("div", { class: "epl-section-title mb-1" }, "① 翻哪排", -1)),
            _createElementVNode$1("div", _hoisted_49, [
              _cache[128] || (_cache[128] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "第一排：人物姓名"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "演员 / 导演等「人」的姓名（Person 数据仍照常采集并交给人名池）")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.translate_person,
                "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((config.value.translate_person) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_50, [
              _cache[129] || (_cache[129] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "第二排：角色名"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "人物饰演的角色名（如 \"Jiro Yakuin (voice)\" → 药院次郎）；关闭后角色名不翻译、也不参与写回等待")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.translate_role,
                "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((config.value.translate_role) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createVNode$1(_component_v_divider, {
              class: "my-2",
              style: {"opacity":".35"}
            }),
            _cache[140] || (_cache[140] = _createElementVNode$1("div", { class: "epl-section-title mb-1" }, "② 翻哪些类型 + 每个文件翻几个", -1)),
            _cache[141] || (_cache[141] = _createElementVNode$1("div", {
              class: "epl-switch-desc mb-2",
              style: {"opacity":".8"}
            }, [
              _createTextVNode$1("开关 = 翻不翻该类型（两排共用）；数字 = 每个文件里该类型最多翻前 N 个"),
              _createElementVNode$1("b", null, "人"),
              _createTextVNode$1("，"),
              _createElementVNode$1("b", null, "0 或留空 = 不限"),
              _createTextVNode$1("。"),
              _createElementVNode$1("b", null, "两排共用这个数字"),
              _createTextVNode$1("：只翻第二排时，「演员=3」= 取前 3 个演员的"),
              _createElementVNode$1("b", null, "角色名"),
              _createTextVNode$1("；数字只在「待翻」里数，已翻完的不占名额。")
            ], -1)),
            _createElementVNode$1("div", _hoisted_51, [
              _cache[130] || (_cache[130] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "演员 Actor"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "主演 / 声优")
              ], -1)),
              _createVNode$1(_component_v_text_field, {
                modelValue: config.value.actor_limit,
                "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((config.value.actor_limit) = $event)),
                modelModifiers: { number: true },
                type: "number",
                min: "0",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                placeholder: "不限",
                style: {"max-width":"104px"},
                class: "mr-2",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"]),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.translate_actor,
                "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((config.value.translate_actor) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_52, [
              _cache[131] || (_cache[131] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "客串 / 配角 GuestStar"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "单集 NFO 里大部分出场人员都是客串")
              ], -1)),
              _createVNode$1(_component_v_text_field, {
                modelValue: config.value.guest_limit,
                "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((config.value.guest_limit) = $event)),
                modelModifiers: { number: true },
                type: "number",
                min: "0",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                placeholder: "不限",
                style: {"max-width":"104px"},
                class: "mr-2",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"]),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.translate_guest_star,
                "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((config.value.translate_guest_star) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_53, [
              _cache[132] || (_cache[132] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "导演 Director"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "导演")
              ], -1)),
              _createVNode$1(_component_v_text_field, {
                modelValue: config.value.director_limit,
                "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((config.value.director_limit) = $event)),
                modelModifiers: { number: true },
                type: "number",
                min: "0",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                placeholder: "不限",
                style: {"max-width":"104px"},
                class: "mr-2",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"]),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.translate_director,
                "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((config.value.translate_director) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_54, [
              _cache[133] || (_cache[133] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "编剧 / 制片人 Writer"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "编剧 / 制片人等非演员人员（共用一个人数）")
              ], -1)),
              _createVNode$1(_component_v_text_field, {
                modelValue: config.value.writer_limit,
                "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((config.value.writer_limit) = $event)),
                modelModifiers: { number: true },
                type: "number",
                min: "0",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                placeholder: "不限",
                style: {"max-width":"104px"},
                class: "mr-2",
                disabled: config.value.translate_all || !aiOn.value
              }, null, 8, ["modelValue", "disabled"]),
              _createVNode$1(_component_v_switch, {
                "model-value": config.value.translate_writer || config.value.translate_producer,
                color: "primary",
                "hide-details": "",
                disabled: config.value.translate_all || !aiOn.value,
                "onUpdate:modelValue": _cache[39] || (_cache[39] = v => { config.value.translate_writer = v; config.value.translate_producer = v; })
              }, null, 8, ["model-value", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_55, [
              _createElementVNode$1("div", _hoisted_56, [
                _createElementVNode$1("div", _hoisted_57, [
                  _cache[136] || (_cache[136] = _createTextVNode$1("全部类型翻译 ", -1)),
                  _createVNode$1(_component_v_tooltip, {
                    location: "top",
                    "max-width": "420"
                  }, {
                    activator: _withCtx$1(({ props: tp }) => [
                      _createVNode$1(_component_v_icon, _mergeProps({
                        size: "14",
                        class: "ml-1",
                        style: {"opacity":".6"}
                      }, tp), {
                        default: _withCtx$1(() => [...(_cache[134] || (_cache[134] = [
                          _createTextVNode$1("mdi-information-outline", -1)
                        ]))]),
                        _: 1
                      }, 16)
                    ]),
                    default: _withCtx$1(() => [
                      _cache[135] || (_cache[135] = _createTextVNode$1(" 这是**运行期覆盖**开关：开启时忽略上方各类型开关（所有职位的人名 + 角色名都翻）， 但不会改写你已保存的类型选择；关闭后自动恢复之前的选择（无需重新勾选）。 ", -1))
                    ]),
                    _: 1
                  })
                ]),
                _cache[137] || (_cache[137] = _createElementVNode$1("div", { class: "epl-switch-desc" }, "开启 = 覆盖所有类型与两排（人数上限仍生效）；关闭后恢复上方原选择（不再永久改写）", -1))
              ]),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.translate_all,
                "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((config.value.translate_all) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _createElementVNode$1("div", _hoisted_58, [
              _cache[138] || (_cache[138] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "重译已有中文名"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, "对已是中文的人名/角色名强制重新翻译")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.overwrite_chinese,
                "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((config.value.overwrite_chinese) = $event)),
                color: "primary",
                "hide-details": "",
                disabled: !aiOn.value
              }, null, 8, ["modelValue", "disabled"])
            ]),
            _cache[142] || (_cache[142] = _createElementVNode$1("div", {
              class: "epl-switch-desc mt-2",
              style: {"opacity":".75"}
            }, "提示：数字按「每个文件各自算前 N 个」（电影 nfo / 剧 tvshow.nfo / 各集 episode.nfo 各自计数，电影与剧共用同一套数字），按「人」计、两排共用；只数「待翻」的，已翻完的不占名额；0/留空 = 不限。", -1))
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mb-3"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, { start: "" }, {
              default: _withCtx$1(() => [...(_cache[143] || (_cache[143] = [
                _createTextVNode$1("mdi-robot", -1)
              ]))]),
              _: 1
            }),
            _cache[144] || (_cache[144] = _createTextVNode$1("LLM 设置", -1))
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, null, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", {
              class: _normalizeClass({ 'epl-ai-off': !aiOn.value }),
              title: !aiOn.value ? 'AI 翻译已关闭：请先在「基础设置」开启「AI 翻译（LLM）」' : ''
            }, [
              _createVNode$1(_component_v_select, {
                modelValue: config.value.llm_mode,
                "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((config.value.llm_mode) = $event)),
                items: llmModes,
                "item-title": "text",
                "item-value": "value",
                label: "LLM 来源",
                density: "compact",
                variant: "outlined",
                class: "mb-2",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              (config.value.llm_mode === 'plugin')
                ? (_openBlock$1(), _createElementBlock$1(_Fragment$1, { key: 0 }, [
                    _createVNode$1(_component_v_text_field, {
                      modelValue: config.value.llm_base_url,
                      "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((config.value.llm_base_url) = $event)),
                      label: "API 地址",
                      placeholder: "https://api.example.com/v1",
                      density: "compact",
                      variant: "outlined",
                      class: "mb-2"
                    }, null, 8, ["modelValue"]),
                    _createElementVNode$1("div", _hoisted_60, [
                      _createVNode$1(_component_v_text_field, {
                        modelValue: config.value.llm_api_key,
                        "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((config.value.llm_api_key) = $event)),
                        label: "API Key",
                        type: "password",
                        density: "compact",
                        variant: "outlined",
                        class: "flex-grow-1",
                        placeholder: apiKeyPlaceholder.value
                      }, null, 8, ["modelValue", "placeholder"]),
                      _createVNode$1(_component_v_btn, {
                        size: "small",
                        variant: "text",
                        disabled: !config.value.has_api_key && !clearApiKeyFlag.value,
                        title: clearApiKeyFlag.value ? '保存后清除已配置的 Key' : '清除已配置的 Key（保存后生效）',
                        onClick: clearApiKey
                      }, {
                        default: _withCtx$1(() => [
                          _createTextVNode$1(_toDisplayString$1(clearApiKeyFlag.value ? '将清除' : '清除'), 1)
                        ]),
                        _: 1
                      }, 8, ["disabled", "title"]),
                      _createVNode$1(_component_v_text_field, {
                        modelValue: config.value.llm_model,
                        "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((config.value.llm_model) = $event)),
                        label: "模型名称",
                        density: "compact",
                        variant: "outlined",
                        class: "flex-grow-1"
                      }, null, 8, ["modelValue"]),
                      _createVNode$1(_component_v_text_field, {
                        modelValue: config.value.llm_timeout,
                        "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((config.value.llm_timeout) = $event)),
                        modelModifiers: { number: true },
                        label: "超时(秒)",
                        type: "number",
                        min: "1",
                        max: "3600",
                        density: "compact",
                        variant: "outlined",
                        style: {"width":"120px"}
                      }, null, 8, ["modelValue"])
                    ]),
                    _createElementVNode$1("div", _hoisted_61, [
                      _cache[145] || (_cache[145] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                        _createElementVNode$1("div", { class: "epl-switch-title" }, "使用代理"),
                        _createElementVNode$1("div", { class: "epl-switch-desc" }, "公网 API / 走系统代理的场景开启")
                      ], -1)),
                      _createVNode$1(_component_v_switch, {
                        modelValue: config.value.use_proxy,
                        "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((config.value.use_proxy) = $event)),
                        color: "primary",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _createElementVNode$1("div", _hoisted_62, [
                      _cache[146] || (_cache[146] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                        _createElementVNode$1("div", { class: "epl-switch-title" }, "关闭 SSL 校验"),
                        _createElementVNode$1("div", { class: "epl-switch-desc" }, "内网自签证书的中转端点（https 握手失败）时开启")
                      ], -1)),
                      _createVNode$1(_component_v_switch, {
                        "model-value": !config.value.llm_verify_ssl,
                        "onUpdate:modelValue": _cache[48] || (_cache[48] = v => { config.value.llm_verify_ssl = !v; }),
                        color: "warning",
                        "hide-details": ""
                      }, null, 8, ["model-value"])
                    ])
                  ], 64))
                : (_openBlock$1(), _createElementBlock$1("div", _hoisted_63, " 使用 MoviePilot 系统 LLM 设置（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），插件内无需填写。 ")),
              _createVNode$1(_component_v_divider, {
                class: "my-3",
                style: {"opacity":".35"}
              }),
              _cache[174] || (_cache[174] = _createElementVNode$1("div", { class: "epl-section-title mb-1" }, "思考与请求", -1)),
              _createElementVNode$1("div", _hoisted_64, [
                _createElementVNode$1("div", _hoisted_65, [
                  _createElementVNode$1("div", _hoisted_66, [
                    _cache[161] || (_cache[161] = _createTextVNode$1("禁用模型深度思考 ", -1)),
                    _createVNode$1(_component_v_tooltip, {
                      location: "top",
                      "max-width": "460"
                    }, {
                      activator: _withCtx$1(({ props: tp }) => [
                        _createVNode$1(_component_v_icon, _mergeProps({
                          size: "14",
                          class: "ml-1",
                          style: {"opacity":".6"}
                        }, tp), {
                          default: _withCtx$1(() => [...(_cache[147] || (_cache[147] = [
                            _createTextVNode$1("mdi-information-outline", -1)
                          ]))]),
                          _: 1
                        }, 16)
                      ]),
                      default: _withCtx$1(() => [
                        _cache[148] || (_cache[148] = _createTextVNode$1(" 思考型模型（DeepSeek 系默认就开思考、默认强度 high）会先把推理过程写一大段，把 max_tokens 全烧在思考上，导致正文为空或输出被截断（finish_reason=length），插件只能反复折半重试、白烧额度。", -1)),
                        _cache[149] || (_cache[149] = _createElementVNode$1("br", null, null, -1)),
                        _cache[150] || (_cache[150] = _createTextVNode$1(" 开启后：无论用什么模型，请求都会带上「关闭思考」参数（不填自定义时，内置依次尝试：", -1)),
                        _cache[151] || (_cache[151] = _createElementVNode$1("code", null, "{\"thinking\":{\"type\":\"disabled\"}}", -1)),
                        _cache[152] || (_cache[152] = _createTextVNode$1(" → ", -1)),
                        _cache[153] || (_cache[153] = _createElementVNode$1("code", null, "{\"reasoning_effort\":\"none\"}", -1)),
                        _cache[154] || (_cache[154] = _createTextVNode$1(" → ", -1)),
                        _cache[155] || (_cache[155] = _createElementVNode$1("code", null, "{\"reasoning_effort\":\"minimal\"}", -1)),
                        _cache[156] || (_cache[156] = _createTextVNode$1(" → ", -1)),
                        _cache[157] || (_cache[157] = _createElementVNode$1("code", null, "chat_template_kwargs", -1)),
                        _cache[158] || (_cache[158] = _createTextVNode$1("，前一种被端点拒绝或没关掉思考就自动换下一种）。", -1)),
                        _cache[159] || (_cache[159] = _createElementVNode$1("br", null, null, -1)),
                        _cache[160] || (_cache[160] = _createTextVNode$1(" 若你的服务商不认内置写法，请在下方「自定义参数」里直接填官方推荐的写法。 ", -1))
                      ]),
                      _: 1
                    })
                  ]),
                  _cache[162] || (_cache[162] = _createElementVNode$1("div", { class: "epl-switch-desc" }, "默认开：无论什么模型都不让它深度思考，直接出结果；写法不兼容会自动换下一种，不会报错", -1))
                ]),
                _createVNode$1(_component_v_switch, {
                  modelValue: config.value.llm_thinking_off,
                  "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((config.value.llm_thinking_off) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode$1("div", _hoisted_67, [
                _cache[163] || (_cache[163] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                  _createElementVNode$1("div", { class: "epl-switch-title" }, "自定义关闭思考参数（JSON，留空=用内置）"),
                  _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                    _createTextVNode$1("各家写法不同，填了就只按你填的这一个发（不再试内置的）。例：DeepSeek 官方 "),
                    _createElementVNode$1("code", null, "{\"thinking\":{\"type\":\"disabled\"}}"),
                    _createTextVNode$1("；OpenAI 系 "),
                    _createElementVNode$1("code", null, "{\"reasoning_effort\":\"none\"}"),
                    _createTextVNode$1("；vLLM/Qwen3 "),
                    _createElementVNode$1("code", null, "{\"chat_template_kwargs\":{\"enable_thinking\":false}}"),
                    _createTextVNode$1("。填错格式会被忽略并记一条提醒日志")
                  ])
                ], -1)),
                _createVNode$1(_component_v_text_field, {
                  modelValue: config.value.llm_thinking_params,
                  "onUpdate:modelValue": _cache[50] || (_cache[50] = $event => ((config.value.llm_thinking_params) = $event)),
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  style: {"max-width":"340px"},
                  placeholder: "{\"thinking\":{\"type\":\"disabled\"}}",
                  disabled: !config.value.llm_thinking_off
                }, null, 8, ["modelValue", "disabled"])
              ]),
              _createElementVNode$1("div", _hoisted_68, [
                _cache[164] || (_cache[164] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                  _createElementVNode$1("div", { class: "epl-switch-title" }, "请求间隔（秒）"),
                  _createElementVNode$1("div", { class: "epl-switch-desc" }, "两次请求之间至少隔多久，唯一的限速项（已合并原「最小请求间隔」与「最大 RPM」）。3 秒 ≈ 每分钟最多 20 次；想做到「每分钟最多 5 次」就填 12。留空或 0 = 不额外限速")
                ], -1)),
                _createVNode$1(_component_v_text_field, {
                  modelValue: config.value.llm_min_interval,
                  "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((config.value.llm_min_interval) = $event)),
                  modelModifiers: { number: true },
                  type: "number",
                  min: "0",
                  max: "600",
                  step: "0.1",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  style: {"max-width":"110px"},
                  suffix: "秒"
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode$1("div", _hoisted_69, [
                _createElementVNode$1("div", _hoisted_70, [
                  _createElementVNode$1("div", _hoisted_71, [
                    _cache[169] || (_cache[169] = _createTextVNode$1("TPM 令牌预算（每分钟，0 = 不限制） ", -1)),
                    _createVNode$1(_component_v_tooltip, {
                      location: "top",
                      "max-width": "440"
                    }, {
                      activator: _withCtx$1(({ props: tp }) => [
                        _createVNode$1(_component_v_icon, _mergeProps({
                          size: "14",
                          class: "ml-1",
                          style: {"opacity":".6"}
                        }, tp), {
                          default: _withCtx$1(() => [...(_cache[165] || (_cache[165] = [
                            _createTextVNode$1("mdi-information-outline", -1)
                          ]))]),
                          _: 1
                        }, 16)
                      ]),
                      default: _withCtx$1(() => [
                        _cache[166] || (_cache[166] = _createTextVNode$1(" 你的服务商明示「TPM 每分钟令牌上限」时填这里：插件发每个请求前会估算 「近 60 秒已用令牌 + 本次请求令牌」，超出预算就先等窗口滑出再发， 避免「429 限流 → 重试 → 再 429 → 熔断」的循环。", -1)),
                        _cache[167] || (_cache[167] = _createElementVNode$1("br", null, null, -1)),
                        _cache[168] || (_cache[168] = _createTextVNode$1(" 不知道填多少就留 0（不限制），配合「请求间隔」即可；估算值 = 提示词长度 ÷ 2 + 输出上限。 ", -1))
                      ]),
                      _: 1
                    })
                  ]),
                  _cache[170] || (_cache[170] = _createElementVNode$1("div", { class: "epl-switch-desc" }, "按估算令牌限速：近 1 分钟累计超过预算先等待再发，显著减少 TPM 限流；0 = 不限制", -1))
                ]),
                _createVNode$1(_component_v_text_field, {
                  modelValue: config.value.llm_tpm_budget,
                  "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((config.value.llm_tpm_budget) = $event)),
                  modelModifiers: { number: true },
                  type: "number",
                  min: "0",
                  step: "100",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  style: {"max-width":"130px"},
                  placeholder: "0"
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode$1("div", _hoisted_72, [
                _createVNode$1(_component_v_text_field, {
                  modelValue: config.value.max_people_per_batch,
                  "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((config.value.max_people_per_batch) = $event)),
                  modelModifiers: { number: true },
                  label: "单批最多翻译条数",
                  type: "number",
                  min: "1",
                  max: "200",
                  density: "compact",
                  variant: "outlined",
                  class: "epl-num"
                }, null, 8, ["modelValue"]),
                _createVNode$1(_component_v_select, {
                  modelValue: config.value.translate_batching,
                  "onUpdate:modelValue": _cache[54] || (_cache[54] = $event => ((config.value.translate_batching) = $event)),
                  items: [
              { text: '按作品分批（同一作品合并，上下文质量优先）', value: 'per_title' },
              { text: '全局聚合（跨作品合并、更省请求，每条词条仍携带作品上下文）', value: 'global' },
            ],
                  "item-title": "text",
                  "item-value": "value",
                  label: "翻译分批模式",
                  density: "compact",
                  variant: "outlined",
                  class: "epl-num",
                  style: {"max-width":"380px"}
                }, null, 8, ["modelValue"])
              ]),
              _createVNode$1(_component_v_divider, {
                class: "my-3",
                style: {"opacity":".35"}
              }),
              _createElementVNode$1("div", _hoisted_73, [
                _cache[173] || (_cache[173] = _createElementVNode$1("div", { class: "epl-switch-title" }, "AI 提示词", -1)),
                _createVNode$1(_component_v_spacer),
                _createVNode$1(_component_v_btn, {
                  size: "small",
                  variant: "tonal",
                  onClick: restorePrompt
                }, {
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_icon, {
                      start: "",
                      size: "14"
                    }, {
                      default: _withCtx$1(() => [...(_cache[171] || (_cache[171] = [
                        _createTextVNode$1("mdi-restore", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[172] || (_cache[172] = _createTextVNode$1("填默认提示词 ", -1))
                  ]),
                  _: 1
                })
              ]),
              _createVNode$1(_component_v_textarea, {
                modelValue: config.value.prompt_template,
                "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((config.value.prompt_template) = $event)),
                rows: "4",
                density: "compact",
                variant: "outlined",
                style: {"max-height":"180px","overflow-y":"auto"},
                hint: "留空使用内置默认提示词；可自行调整要求 LLM 怎么翻人名/角色名",
                placeholder: "你是一位专业的影视人名翻译专家，只返回 JSON……"
              }, null, 8, ["modelValue"])
            ], 10, _hoisted_59)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mb-3"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, { start: "" }, {
              default: _withCtx$1(() => [...(_cache[175] || (_cache[175] = [
                _createTextVNode$1("mdi-webhook", -1)
              ]))]),
              _: 1
            }),
            _cache[176] || (_cache[176] = _createTextVNode$1("Webhook 入库", -1))
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, null, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", _hoisted_74, [
              _cache[177] || (_cache[177] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                _createElementVNode$1("div", { class: "epl-switch-title" }, "启用 Webhook 入库"),
                _createElementVNode$1("div", { class: "epl-switch-desc" }, " 关闭后：不接收新 Webhook / 不排队 / 不处理 / 不通知（已有挂起事件不丢失，重新开启可继续）。但：NFO 扫描 / 探测库仍继续有效。 ")
              ], -1)),
              _createVNode$1(_component_v_switch, {
                modelValue: config.value.webhook_enabled,
                "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((config.value.webhook_enabled) = $event)),
                color: "success",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ]),
            (config.value.webhook_enabled)
              ? (_openBlock$1(), _createElementBlock$1(_Fragment$1, { key: 0 }, [
                  _createElementVNode$1("div", _hoisted_75, [
                    _cache[178] || (_cache[178] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                      _createElementVNode$1("div", { class: "epl-switch-title" }, "入库延迟（秒）"),
                      _createElementVNode$1("div", { class: "epl-switch-desc" }, "Emby 入库后等多少秒再翻译，给刮削留时间")
                    ], -1)),
                    _createVNode$1(_component_v_text_field, {
                      modelValue: config.value.webhook_delay,
                      "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((config.value.webhook_delay) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      min: "0",
                      max: "3600",
                      density: "compact",
                      variant: "outlined",
                      "hide-details": "",
                      style: {"max-width":"110px"},
                      suffix: "秒"
                    }, null, 8, ["modelValue"])
                  ]),
                  _createElementVNode$1("div", _hoisted_76, [
                    _cache[179] || (_cache[179] = _createElementVNode$1("div", { class: "flex-grow-1" }, [
                      _createElementVNode$1("div", { class: "epl-switch-title" }, "整剧全收（包含旧集）"),
                      _createElementVNode$1("div", { class: "epl-switch-desc" }, [
                        _createTextVNode$1(" 关（默认）：Emby 发「整部剧」事件时"),
                        _createElementVNode$1("b", null, "只入库本次新增的集"),
                        _createTextVNode$1("（最近 7 天内加入的），旧集跳过 —— 你只加 3 集就只收这 3 集； 开：把这剧 Emby 里现有的"),
                        _createElementVNode$1("b", null, "全部集"),
                        _createTextVNode$1("都入库（想一次补齐整部剧时用）。 不论开关，要补收旧集都可用："),
                        _createElementVNode$1("b", null, "「扫描」"),
                        _createTextVNode$1("（全量/增量）、"),
                        _createElementVNode$1("b", null, "「探测库」"),
                        _createTextVNode$1("（按 Emby 清单补齐缺集与全新条目）、或对该剧点"),
                        _createElementVNode$1("b", null, "「重新拉取」"),
                        _createTextVNode$1("（按本地 nfo 重采集该条目全部集） ")
                      ])
                    ], -1)),
                    _createVNode$1(_component_v_switch, {
                      modelValue: config.value.series_ingest_all,
                      "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((config.value.series_ingest_all) = $event)),
                      color: "primary",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ])
                ], 64))
              : (_openBlock$1(), _createBlock$1(_component_v_alert, {
                  key: 1,
                  type: "warning",
                  variant: "tonal",
                  density: "compact",
                  style: {"font-size":"12px"}
                }, {
                  default: _withCtx$1(() => [...(_cache[180] || (_cache[180] = [
                    _createTextVNode$1(" Webhook 已关闭：新入库事件不会接收。NFO 扫描 / 探测库仍可发现新条目。 ", -1)
                  ]))]),
                  _: 1
                }))
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createElementVNode$1("div", _hoisted_77, [
      _createVNode$1(_component_v_tooltip, {
        text: "真实调用一次 1 词翻译，检测 LLM 地址/密钥/模型是否可用（地址缺 /v1 会自动尝试）",
        location: "top"
      }, {
        activator: _withCtx$1(({ props: tp }) => [
          _createVNode$1(_component_v_btn, _mergeProps({
            variant: "tonal",
            class: "mr-2",
            loading: llmTestBusy.value,
            disabled: !aiOn.value
          }, tp, { onClick: testLlm }), {
            default: _withCtx$1(() => [
              _createVNode$1(_component_v_icon, {
                start: "",
                size: "18"
              }, {
                default: _withCtx$1(() => [...(_cache[181] || (_cache[181] = [
                  _createTextVNode$1("mdi-flash-outline", -1)
                ]))]),
                _: 1
              }),
              _cache[182] || (_cache[182] = _createTextVNode$1("测试连接 ", -1))
            ]),
            _: 1
          }, 16, ["loading", "disabled"])
        ]),
        _: 1
      }),
      _createVNode$1(_component_v_btn, {
        color: "primary",
        variant: "tonal",
        loading: saving.value,
        onClick: save
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$1(() => [...(_cache[183] || (_cache[183] = [
              _createTextVNode$1("mdi-content-save-outline", -1)
            ]))]),
            _: 1
          }),
          _cache[184] || (_cache[184] = _createTextVNode$1("保存配置 ", -1))
        ]),
        _: 1
      }, 8, ["loading"])
    ]),
    _createVNode$1(_component_v_dialog, {
      modelValue: browseDlg.value,
      "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((browseDlg).value = $event)),
      "max-width": "720",
      scrollable: ""
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card, null, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card_title, { class: "d-flex align-center text-subtitle-1" }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$1(() => [...(_cache[185] || (_cache[185] = [
                    _createTextVNode$1("mdi-folder-search-outline", -1)
                  ]))]),
                  _: 1
                }),
                _createElementVNode$1("span", null, "浏览：" + _toDisplayString$1(browse.value.lib_name), 1),
                _createVNode$1(_component_v_spacer),
                _createVNode$1(_component_v_btn, {
                  size: "x-small",
                  variant: "text",
                  onClick: _cache[59] || (_cache[59] = $event => (browseDlg.value = false))
                }, {
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_icon, { size: "16" }, {
                      default: _withCtx$1(() => [...(_cache[186] || (_cache[186] = [
                        _createTextVNode$1("mdi-close", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_subtitle, { style: {"font-size":"12px"} }, {
              default: _withCtx$1(() => [
                _createElementVNode$1("code", null, _toDisplayString$1(browse.value.path || browse.value.root), 1)
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_text, { style: {"max-height":"440px"} }, {
              default: _withCtx$1(() => [
                _createElementVNode$1("div", _hoisted_78, [
                  _createVNode$1(_component_v_btn, {
                    size: "x-small",
                    variant: "tonal",
                    disabled: !browse.value.path || browse.value.path === browse.value.root,
                    onClick: browseUp
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, {
                        start: "",
                        size: "14"
                      }, {
                        default: _withCtx$1(() => [...(_cache[187] || (_cache[187] = [
                          _createTextVNode$1("mdi-arrow-up", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[188] || (_cache[188] = _createTextVNode$1("返回上级 ", -1))
                    ]),
                    _: 1
                  }, 8, ["disabled"]),
                  _createVNode$1(_component_v_btn, {
                    size: "x-small",
                    variant: "tonal",
                    loading: browse.value.loading,
                    onClick: browseRefresh
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, {
                        start: "",
                        size: "14"
                      }, {
                        default: _withCtx$1(() => [...(_cache[189] || (_cache[189] = [
                          _createTextVNode$1("mdi-refresh", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[190] || (_cache[190] = _createTextVNode$1("刷新 ", -1))
                    ]),
                    _: 1
                  }, 8, ["loading"]),
                  _createVNode$1(_component_v_btn, {
                    size: "x-small",
                    variant: "tonal",
                    onClick: browseTest
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, {
                        start: "",
                        size: "14"
                      }, {
                        default: _withCtx$1(() => [...(_cache[191] || (_cache[191] = [
                          _createTextVNode$1("mdi-check-network-outline", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[192] || (_cache[192] = _createTextVNode$1("测试访问 ", -1))
                    ]),
                    _: 1
                  }),
                  _createVNode$1(_component_v_spacer),
                  (browse.value.check)
                    ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                        key: 0,
                        size: "x-small",
                        variant: "tonal"
                      }, {
                        default: _withCtx$1(() => [
                          _createTextVNode$1(_toDisplayString$1(browse.value.check), 1)
                        ]),
                        _: 1
                      }))
                    : _createCommentVNode$1("", true),
                  _createVNode$1(_component_v_chip, {
                    size: "x-small",
                    variant: "tonal",
                    color: "warning"
                  }, {
                    default: _withCtx$1(() => [...(_cache[193] || (_cache[193] = [
                      _createTextVNode$1("只读", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                (browse.value.error)
                  ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                      key: 0,
                      type: "error",
                      variant: "tonal",
                      density: "compact",
                      class: "mb-2",
                      style: {"font-size":"12px"}
                    }, {
                      default: _withCtx$1(() => [
                        _createTextVNode$1(_toDisplayString$1(browse.value.error), 1)
                      ]),
                      _: 1
                    }))
                  : _createCommentVNode$1("", true),
                _createElementVNode$1("div", _hoisted_79, [
                  (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(browse.value.entries, (e) => {
                    return (_openBlock$1(), _createElementBlock$1("div", {
                      key: e.name,
                      class: _normalizeClass(["epl-browse-row", { 'epl-browse-dir': e.is_dir }]),
                      onClick: $event => (e.is_dir && browseLoad(joinPath(browse.value.path, e.name)))
                    }, [
                      _createVNode$1(_component_v_icon, {
                        size: "16",
                        color: e.is_dir ? 'primary' : undefined
                      }, {
                        default: _withCtx$1(() => [
                          _createTextVNode$1(_toDisplayString$1(e.is_dir ? 'mdi-folder' : 'mdi-file-document-outline'), 1)
                        ]),
                        _: 2
                      }, 1032, ["color"]),
                      _createElementVNode$1("span", _hoisted_81, _toDisplayString$1(e.name), 1),
                      _createElementVNode$1("span", _hoisted_82, _toDisplayString$1(e.is_dir ? '' : fmtSize(e.size)), 1)
                    ], 10, _hoisted_80))
                  }), 128)),
                  (!browse.value.entries.length && !browse.value.loading)
                    ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_83, "（空目录）"))
                    : _createCommentVNode$1("", true)
                ])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Settings = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-08ce107d"]]);

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createBlock:_createBlock,createCommentVNode:_createCommentVNode,resolveDynamicComponent:_resolveDynamicComponent,KeepAlive:_KeepAlive} = await importShared('vue');


const _hoisted_1 = { class: "epl-app" };
const _hoisted_2 = { class: "epl-layout" };
const _hoisted_3 = {
  class: "epl-nav epl-card-bg",
  "aria-label": "主导航"
};
const _hoisted_4 = { class: "epl-nav-header" };
const _hoisted_5 = { class: "epl-app-title" };
const _hoisted_6 = { class: "epl-content" };
const _hoisted_7 = { class: "epl-mobile-nav epl-card-bg" };
const _hoisted_8 = { class: "epl-sheet-card epl-card-bg" };
const _hoisted_9 = {
  key: 0,
  class: "epl-disabled-mask"
};
const _hoisted_10 = { class: "epl-disabled-card epl-card-bg" };

const {computed,getCurrentInstance,inject,onMounted,ref,watch,onActivated} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'EmbyPeopleLocalize' },
  sourcePluginId: { type: String, default: '' },
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['action', 'layout', 'close', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const instance = getCurrentInstance();
const toast = inject('moviepilot:toast', null);

const pluginConfig = ref({ enabled: true, ...(props.initialConfig || {}) });
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false);

async function initConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await api.get(props.api, '/config');
    if (data && typeof data === 'object') {
      pluginConfig.value = { ...pluginConfig.value, ...data };
    }
  } catch (e) {
    // 读取失败则沿用 initialConfig
  }
}

function onConfigSave(payload) {
  if (payload && typeof payload === 'object') {
    pluginConfig.value = { ...pluginConfig.value, ...payload };
  }
}

const navItems = [
  { key: 'dashboard', title: '仪表盘', icon: 'mdi-view-dashboard-outline' },
  { key: 'library', title: '库', icon: 'mdi-library' },
  { key: 'pool', title: '人名池', icon: 'mdi-account-search' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
];

const active = ref('dashboard');
const loading = ref(true);
const mobileSheet = ref(false);
const refreshKey = ref(0);

const currentNavItem = computed(() => navItems.find(item => item.key === active.value) || navItems[0]);

function gotoNav(key) {
  active.value = key;
  mobileSheet.value = false;
}

const views = { dashboard: Dashboard, library: Library, pool: PeoplePool, settings: Settings };
const currentView = computed(() => views[active.value] || Dashboard);

function notify(message, type = 'error') {
  if (toast && typeof toast[type] === 'function') toast[type](message);
}

function handleAction(payload) {
  refreshKey.value++;
  emit('action', payload);
}

watch(() => active.value, () => {
  refreshKey.value++;
});

onActivated(() => {
  refreshKey.value++;
});

function closePlugin() {
  try {
    emit('close');
  } catch (e) {
    // ignore
  }
}

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '68rem' });
  loading.value = true;
  try {
    emit('action');
  } catch (e) {
    // ignore
  } finally {
    loading.value = false;
  }
  initConfig();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_bottom_sheet = _resolveComponent("v-bottom-sheet");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("nav", _hoisted_3, [
        _createElementVNode("div", _hoisted_4, [
          _createElementVNode("div", _hoisted_5, [
            _createVNode(_component_v_icon, { start: "" }, {
              default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
                _createTextVNode("mdi-account-group-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[5] || (_cache[5] = _createTextVNode(" 演职人员中文化 ", -1))
          ]),
          _cache[6] || (_cache[6] = _createElementVNode("div", { class: "epl-app-subtitle" }, "Emby People Localize", -1))
        ]),
        _createVNode(_component_v_divider, { class: "epl-divider" }),
        _createVNode(_component_v_list, {
          class: "epl-nav-list",
          density: "compact",
          nav: ""
        }, {
          default: _withCtx(() => [
            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
              return _createVNode(_component_v_list_item, {
                key: item.key,
                active: active.value === item.key,
                class: "epl-nav-item",
                rounded: "lg",
                onClick: $event => (active.value = item.key)
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_list_item_title, { class: "epl-nav-text" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_icon, {
                        start: "",
                        size: 18
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(item.icon), 1)
                        ]),
                        _: 2
                      }, 1024),
                      _createTextVNode(" " + _toDisplayString(item.title), 1)
                    ]),
                    _: 2
                  }, 1024)
                ]),
                _: 2
              }, 1032, ["active", "onClick"])
            }), 64))
          ]),
          _: 1
        })
      ]),
      _createElementVNode("main", _hoisted_6, [
        (loading.value)
          ? (_openBlock(), _createBlock(_component_v_progress_circular, {
              key: 0,
              indeterminate: "",
              color: "primary",
              class: "epl-loading"
            }))
          : (_openBlock(), _createBlock(_KeepAlive, { key: 1 }, [
              (_openBlock(), _createBlock(_resolveDynamicComponent(currentView.value), {
                key: active.value,
                api: props.api,
                target: active.value,
                enabled: pluginEnabled.value,
                "refresh-key": refreshKey.value,
                "initial-config": props.initialConfig,
                onNotify: notify,
                onAction: handleAction,
                onViewTask: _cache[0] || (_cache[0] = $event => (active.value = 'dashboard')),
                onSave: onConfigSave
              }, null, 40, ["api", "target", "enabled", "refresh-key", "initial-config"]))
            ], 1024))
      ])
    ]),
    _createElementVNode("div", _hoisted_7, [
      _createElementVNode("button", {
        type: "button",
        class: "epl-mnav-current",
        onClick: _cache[1] || (_cache[1] = $event => (mobileSheet.value = true))
      }, [
        _createVNode(_component_v_icon, { size: 20 }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(currentNavItem.value.icon), 1)
          ]),
          _: 1
        }),
        _createElementVNode("span", null, _toDisplayString(currentNavItem.value.title), 1),
        _createVNode(_component_v_icon, {
          size: "16",
          class: "epl-mnav-caret"
        }, {
          default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
            _createTextVNode("mdi-chevron-down", -1)
          ]))]),
          _: 1
        })
      ])
    ]),
    _createVNode(_component_v_bottom_sheet, {
      modelValue: mobileSheet.value,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((mobileSheet).value = $event)),
      class: "epl-sheet"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", _hoisted_8, [
          _cache[8] || (_cache[8] = _createElementVNode("div", { class: "epl-sheet-title" }, "切换页面", -1)),
          _createVNode(_component_v_divider, { class: "epl-divider" }),
          _createVNode(_component_v_list, { class: "epl-sheet-list" }, {
            default: _withCtx(() => [
              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
                return _createVNode(_component_v_list_item, {
                  key: item.key,
                  active: active.value === item.key,
                  color: "primary",
                  rounded: "lg",
                  class: "epl-sheet-item",
                  onClick: $event => (gotoNav(item.key))
                }, {
                  prepend: _withCtx(() => [
                    _createVNode(_component_v_icon, { size: 20 }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(item.icon), 1)
                      ]),
                      _: 2
                    }, 1024)
                  ]),
                  default: _withCtx(() => [
                    _createVNode(_component_v_list_item_title, null, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(item.title), 1)
                      ]),
                      _: 2
                    }, 1024)
                  ]),
                  _: 2
                }, 1032, ["active", "onClick"])
              }), 64))
            ]),
            _: 1
          })
        ])
      ]),
      _: 1
    }, 8, ["modelValue"]),
    (!pluginEnabled.value && active.value !== 'settings')
      ? (_openBlock(), _createElementBlock("div", _hoisted_9, [
          _createElementVNode("div", _hoisted_10, [
            _createVNode(_component_v_icon, {
              color: "grey",
              size: "44",
              class: "mb-2"
            }, {
              default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                _createTextVNode("mdi-power-off", -1)
              ]))]),
              _: 1
            }),
            _cache[12] || (_cache[12] = _createElementVNode("div", { class: "epl-disabled-title" }, "插件已停用", -1)),
            _cache[13] || (_cache[13] = _createElementVNode("div", { class: "epl-disabled-desc" }, "插件已被关闭，其他页面暂不可用", -1)),
            _createVNode(_component_v_btn, {
              color: "primary",
              variant: "tonal",
              class: "mt-3",
              onClick: _cache[3] || (_cache[3] = $event => (active.value = 'settings'))
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
                    _createTextVNode("mdi-cog-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[11] || (_cache[11] = _createTextVNode("前往设置启用 ", -1))
              ]),
              _: 1
            })
          ])
        ]))
      : _createCommentVNode("", true),
    (!pluginEnabled.value && active.value === 'settings')
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 1,
          density: "compact",
          variant: "flat",
          icon: "mdi-alert-circle-outline",
          class: "epl-disabled-banner"
        }, {
          default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
            _createTextVNode(" 插件当前已停用：其他页面不可操作，请在本页开启「插件总开关」并保存。 ", -1)
          ]))]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createVNode(_component_v_btn, {
      icon: "mdi-close",
      size: "small",
      variant: "tonal",
      class: "epl-close-btn",
      title: "关闭插件",
      "aria-label": "关闭插件",
      onClick: closePlugin
    })
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e65d1817"]]);

export { Page as default };
