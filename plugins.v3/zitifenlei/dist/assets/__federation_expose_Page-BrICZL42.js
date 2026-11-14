import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, u as uploadAcceptFor, a as DESKTOP_ACCEPT_ASS, b as apiModule, f as formatNotes, c as DESKTOP_ACCEPT_FONT, S as Settings, C as Check, F as FontLibrary, D as Dashboard } from './Settings-CcBv-bt-.js';

const {createTextVNode:_createTextVNode$3,resolveComponent:_resolveComponent$3,withCtx:_withCtx$3,createVNode:_createVNode$3,unref:_unref$1,createElementVNode:_createElementVNode$3,toDisplayString:_toDisplayString$3,Fragment:_Fragment$3,openBlock:_openBlock$3,createElementBlock:_createElementBlock$3,createCommentVNode:_createCommentVNode$3,createBlock:_createBlock$3,renderList:_renderList$3,withModifiers:_withModifiers,normalizeClass:_normalizeClass$1} = await importShared('vue');


const _hoisted_1$3 = { class: "zt-subset" };
const _hoisted_2$3 = { class: "zt-topbar" };
const _hoisted_3$3 = ["accept"];
const _hoisted_4$3 = { class: "zt-status-hint text-body-2" };
const _hoisted_5$3 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_6$3 = {
  key: 2,
  class: "zt-list-body"
};
const _hoisted_7$3 = { class: "zt-title-text" };
const _hoisted_8$3 = { class: "zt-title-actions" };
const _hoisted_9$3 = { class: "zt-filter-row" };
const _hoisted_10$3 = {
  key: 0,
  class: "zt-empty pa-6"
};
const _hoisted_11$2 = ["onClick"];
const _hoisted_12$2 = { class: "zt-group-name" };
const _hoisted_13$2 = { class: "zt-group-count" };
const _hoisted_14$2 = { class: "zt-group-stats" };
const _hoisted_15$2 = { class: "zt-group-actions" };
const _hoisted_16$2 = {
  key: 0,
  class: "zt-group-body"
};
const _hoisted_17$2 = {
  key: 3,
  class: "ml-2"
};
const _hoisted_18$2 = {
  key: 0,
  class: "zt-loading-more pa-2 text-center"
};
const _hoisted_19$2 = {
  key: 1,
  class: "zt-loading-more pa-2 text-center"
};

const {computed: computed$3,onActivated: onActivated$3,onDeactivated: onDeactivated$1,onMounted: onMounted$3,onUnmounted: onUnmounted$1,ref: ref$3,watch} = await importShared('vue');

const RENDER_STEP = 60;

const _sfc_main$3 = {
  __name: 'Subset',
  props: {
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
},
  emits: ['notify', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

// ===== 子集化引擎状态（内置 HarfBuzz）=====
const status = ref$3({ engine: 'harfbuzz', hb_ok: false, font_index: {}, lib_dir: '' });
const statusLoaded = ref$3(false);
const engineReady = computed$3(() => !!status.value.hb_ok);
const indexReady = computed$3(() => !!status.value.font_index?.faces);
const indexCount = computed$3(() => status.value.font_index?.faces || 0);
// 文件数：TTC/OTC 一个文件含多个 face，face 数必然大于文件数，两个口径并列显示
const indexFileCount = computed$3(() => status.value.font_index?.files || 0);
// 索引重建中（全部重建/启动轻检/每周核对都可能触发）：UI 明确显示进度，
// 否则只看到「（—」会以为索引坏了
const indexRebuilding = computed$3(() => !!status.value.rebuilding);
const indexProgressText = computed$3(() => {
  const p = status.value.rebuild_progress || {};
  const done = Number(p.done || 0);
  const total = Number(p.total || 0);
  return total > 0 ? `（已处理 ${done}/${total}）` : ''
});

// ===== 左栏：待处理 =====
const pendingList = ref$3([]);
const loadingPending = ref$3(false);
const uploadRef = ref$3(null);
const uploading = ref$3(false);
// 处理中：按钮转圈禁用，防重复点击
const scanning = ref$3(false);

// ===== 右栏结果：按剧名/目录分组，折叠抽屉 + 前端渐进渲染 =====
const records = ref$3([]);
const loadingRecords = ref$3(false);
const downloadingId = ref$3(null);
const recordTotal = ref$3(0);
const retriableCount = ref$3(0);
// 渐进渲染：初始渲染 60 条，下拉再加 60（数据一次取全，DOM 分批）
const renderBudget = ref$3(RENDER_STEP);
const expandedGroups = ref$3(new Set());
const groupBusy = ref$3('');
const groupConfirm = ref$3(false);
const groupTarget = ref$3(null);
// 筛选：状态下拉 + 文件名搜索
const filterStatus = ref$3('');
const recordSearch = ref$3('');
const statusFilterOptions = [
  { title: '全部状态', value: '' },
  { title: '成功', value: 'success' },
  { title: '可重试', value: 'retryable' },
  { title: '缺字体', value: 'missing' },
  { title: '跳过', value: 'skipped' },
  { title: '失败', value: 'error' },
];

async function loadStatus() {
  try {
    status.value = await apiModule.get(props.api, '/subset/index');
    // 重建中（可能是本页触发，也可能是启动轻检/周核对）：开启 2 秒快轮询看进度
    if (status.value.rebuilding) startRebuildPolling();
    else stopRebuildPolling();
  } catch (e) { /* 忽略 */ } finally {
    statusLoaded.value = true;
  }
}
// 重建进度快轮询（2 秒）：重建结束自动停，页面切走也会停
let rebuildPollTimer = null;
function startRebuildPolling() {
  if (rebuildPollTimer) return
  rebuildPollTimer = setInterval(async () => {
    try {
      status.value = await apiModule.get(props.api, '/subset/index');
    } catch (e) { /* 忽略单次失败 */ }
    if (!status.value.rebuilding) stopRebuildPolling();
  }, 2000);
}
function stopRebuildPolling() {
  if (rebuildPollTimer) clearInterval(rebuildPollTimer);
  rebuildPollTimer = null;
}
// 全部重建字体库：清空索引后逐文件重新解析（日常归档/入库是增量增/减，不走这里）
const rebuildingIndex = ref$3(false);
const rebuildConfirm = ref$3(false);
async function rebuildIndex() {
  if (rebuildingIndex.value) return
  rebuildingIndex.value = true;
  rebuildConfirm.value = false;
  // 重建是同步阻塞接口：先开快轮询，让顶部状态条在等待期间就能显示「正在重建 / 已处理 N/M」
  startRebuildPolling();
  try {
    await apiModule.post(props.api, '/subset/rebuild_index');
    emit('notify', '字体库已全部重建（逐文件重新解析）', 'success');
    emit('action', { type: 'subset_done' });
  } catch (e) {
    emit('notify', e.message || '全部重建失败');
  } finally {
    rebuildingIndex.value = false;
    stopRebuildPolling();
    await loadStatus();
  }
}
async function loadPending() {
  loadingPending.value = true;
  try {
    pendingList.value = await apiModule.get(props.api, '/subset/pending');
  } catch (e) {
    emit('notify', e.message || '读取待处理列表失败');
  } finally {
    loadingPending.value = false;
  }
}
// 结果记录：一次拉取当前筛选下的全量（几百条级别），前端分组后渐进渲染。
// 这样组头计数、组内「全部下载 / 删除整组」都基于完整数据，不会被分页截断。
async function loadRecords(reset = false, force = false) {
  if (loadingRecords.value && !force) return
  loadingRecords.value = true;
  try {
    const data = await apiModule.get(props.api, '/subset/records', {
      status: filterStatus.value,
      search: recordSearch.value,
      page: 1,
      limit: 0,
    });
    records.value = (data && data.list) || [];
    recordTotal.value = (data && data.total) || 0;
    if (typeof data?.retriable === 'number') retriableCount.value = data.retriable;
    if (reset) {
      renderBudget.value = RENDER_STEP;
      expandedGroups.value = new Set();
    }
  } catch (e) {
    emit('notify', e.message || '读取子集化记录失败');
  } finally {
    loadingRecords.value = false;
  }
}

async function refreshCurrentPage() {
  await loadRecords(false, true);
}

// 筛选变化：防抖后重拉全量并重置展开/渲染预算
let filterTimer = null;
watch([filterStatus, recordSearch], () => {
  if (filterTimer) clearTimeout(filterTimer);
  filterTimer = setTimeout(() => loadRecords(true), 250);
});

// ── 分组：inbound 取媒体库剧名目录（Season 1 上跳一级），watch 取所在子目录，manual 归「手动上传」
const SEASON_RE = /^(season\s*\d+|s\d{1,2}|第.{1,4}季)$/i;
function seasonLike(name) {
  return SEASON_RE.test(String(name || '').trim())
}
function recordGroup(r) {
  const src = String(r.source || '');
  if (src === 'manual') return { key: 'manual', label: '手动上传' }
  const p = String(r.file_path || '').replace(/\\/g, '/');
  const dirs = p ? p.split('/').filter(Boolean).slice(0, -1) : [];
  if (!dirs.length) {
    return { key: `${src || 'unknown'}:`, label: src === 'watch' ? '监控目录' : '未知来源' }
  }
  let idx = dirs.length - 1;
  if (seasonLike(dirs[idx]) && idx > 0) idx -= 1;
  const label = dirs[idx] || '未知目录';
  return {
    key: `${src || 'unknown'}:${dirs.slice(0, idx + 1).join('/')}`,
    label: src === 'watch' ? `监控：${label}` : label,
  }
}
function groupStats(list) {
  const s = { success: 0, missing: 0, retryable: 0, error: 0, skipped: 0 };
  for (const r of list) {
    if (r.status === 'success') s.success += 1;
    else if (r.status === 'error') s.error += 1;
    else if (r.status === 'skipped') s.skipped += 1;
    else if (r.status === 'missing') {
      s.missing += 1;
      if (r.retryable) s.retryable += 1;
    }
  }
  return s
}
const groupedRecords = computed$3(() => {
  const map = new Map();
  for (const r of records.value) {
    const g = recordGroup(r);
    let item = map.get(g.key);
    if (!item) {
      item = { key: g.key, label: g.label, records: [], maxId: 0 };
      map.set(g.key, item);
    }
    item.records.push(r);
    if (Number(r.id) > item.maxId) item.maxId = Number(r.id);
  }
  const groups = [...map.values()].sort((a, b) => b.maxId - a.maxId);
  for (const g of groups) {
    g.stats = groupStats(g.records);
    // 组头颜色：有失败优先红，其次缺字橙，全成功绿，其余灰
    g.color = g.stats.error ? 'error' : (g.stats.missing ? 'warning' : (g.stats.success ? 'success' : 'grey'));
    g.downloadable = g.records.filter(r => r.status === 'success' && r.out_file);
  }
  return groups
});
// 渐进渲染：组头全显示；展开的组内记录消耗渲染预算，下拉到底再加一批
const visibleGroups = computed$3(() => {
  let remain = renderBudget.value;
  return groupedRecords.value.map(g => {
    const expanded = expandedGroups.value.has(g.key);
    let visibleRecords = [];
    let truncated = false;
    if (expanded) {
      visibleRecords = g.records.slice(0, Math.max(0, remain));
      remain -= visibleRecords.length;
      truncated = visibleRecords.length < g.records.length;
    }
    return { ...g, expanded, visibleRecords, truncated }
  })
});
const hasMoreRecords = computed$3(() => visibleGroups.value.some(g => g.truncated));

function toggleGroup(g) {
  const next = new Set(expandedGroups.value);
  if (next.has(g.key)) next.delete(g.key);
  else next.add(g.key);
  expandedGroups.value = next;
}
function onRecordsScroll(e) {
  const el = e.target;
  if (hasMoreRecords.value && el && el.scrollTop + el.clientHeight >= el.scrollHeight - 60) {
    renderBudget.value += RENDER_STEP;
  }
}
function loadMoreRecords() {
  renderBudget.value += RENDER_STEP;
}

// 索引时间文案：优先显示「构建」时间；索引只由逐文件增量入库建立过时没有构建时间，
// 退化为「最近更新」（font_files.indexed_at 最大值），避免只显示一个空破折号
function indexTimeText() {
  const fi = status.value?.font_index || {};
  if (fi.last_rebuild) return `构建 ${fi.last_rebuild}`
  if (fi.last_indexed_at) return `最近更新 ${fi.last_indexed_at}`
  return indexReady.value ? '构建时间未记录' : '—'
}

function statusColor(r) {
  if (r.status === 'success') return 'success'
  if (r.status === 'missing' && r.retryable) return 'primary'
  if (r.status === 'missing') return 'warning'
  if (r.status === 'skipped') return 'info'
  return 'error'
}
function statusText(r) {
  if (r.status === 'success') return '成功'
  if (r.status === 'missing' && r.retryable) return '可重试'
  if (r.status === 'missing') return '缺字体'
  if (r.status === 'skipped') return '跳过'
  return '失败'
}

// 上传字幕（多选，进左栏待处理）
async function handleUpload(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return
  const BATCH = 5;
  let total = 0;
  const notes = [];
  uploading.value = true;
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const form = new FormData();
      for (const file of chunk) form.append('file', file);
      const res = await props.api.post(
        'plugin/Zitifenlei/subset/pending/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      const body = res?.data ?? res;
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '上传失败'}`);
        break
      } else {
        total += (body?.data?.count ?? chunk.length);
        if (Array.isArray(body?.data?.notes)) notes.push(...body.data.notes);
      }
    }
    emit('notify', `已加入待处理 ${total} 个字幕`, 'success');
    const noteText = formatNotes(notes);
    if (noteText) emit('notify', `部分文件被跳过：${noteText}`, 'warning');
    loadPending();
  } catch (e) {
    emit('notify', e.message || '上传失败');
  } finally {
    uploading.value = false;
  }
}

// 移除单条待处理（x）
async function removePending(id) {
  try {
    await apiModule.post(props.api, `/subset/pending/remove/${id}`);
    pendingList.value = pendingList.value.filter(p => p.id !== id);
    emit('notify', '已移除待处理', 'success');
  } catch (e) {
    emit('notify', e.message || '移除失败');
  }
}

async function clearPending() {
  try {
    await apiModule.del(props.api, '/subset/pending/clear');
    pendingList.value = [];
    emit('notify', '已清空待处理', 'success');
  } catch (e) {
    emit('notify', e.message || '清空失败');
  }
}

// 全量子集化：处理左栏全部待处理
async function scanAll() {
  if (scanning.value) return
  scanning.value = true;
  // 点击即提示：子集化是同步长任务，先给反馈避免用户以为没点上而重复点击
  emit('notify', '正在全量子集化，请勿重复点击', 'info');
  try {
    const res = await apiModule.post(props.api, '/subset/all');
    const s = res || {};
    emit('notify', `全量子集化完成：成功 ${s.success ?? 0}，跳过 ${s.skipped ?? 0}，缺字体 ${s.missing ?? 0}，失败 ${s.error ?? 0}`, 'success');
    await loadRecords(true, true);
    await loadPending();
    await loadStatus();
    emit('action', { type: 'subset_done' });
  } catch (e) {
    emit('notify', e.message || '全量子集化失败');
  } finally {
    scanning.value = false;
  }
}

// 状态标签点击：缺字体（未补齐）/失败 → 去缺失字体页处理；可重试不点击（直接点顶部「重试失败」）
function onStatusTagClick(r) {
  if (!props.enabled) return
  if (r.status === 'missing' && !r.retryable) {
    emit('action', { type: 'goto_missing' });
  } else if (r.status === 'error') {
    emit('action', { type: 'goto_missing' });
  }
}

// 重试失败/缺字体的记录（如 MP 入库缺字体，补字后可重跑）
const retrying = ref$3(false);
function hasRetriable() {
  return retriableCount.value > 0
}
async function retryFailed() {
  if (retrying.value) return
  retrying.value = true;
  try {
    const res = await apiModule.post(props.api, '/subset/retry');
    const s = res || {};
    emit('notify', `重试完成：成功 ${s.success ?? 0}，缺字体 ${s.missing ?? 0}，失败 ${s.error ?? 0}`, 'success');
    await loadRecords(true, true);
    await loadStatus();
    emit('action', { type: 'subset_done' });
  } catch (e) {
    emit('notify', e.message || '重试失败');
  } finally {
    retrying.value = false;
  }
}

// 下载结果文件（base64 → blob）
// Q10 修复：downloadRecord 返回明确状态（'ok'/'none'/'missing'/'error'/'busy'），
// 不再静默 return，调用方（downloadAll / 单条按钮）可按状态准确统计。
async function downloadRecord(r) {
  if (downloadingId.value) return 'busy'
  if (!r.out_file) {
    emit('notify', '无输出文件', 'warning');
    return 'none'
  }
  downloadingId.value = r.id;
  try {
    const st = await _doDownload(r);
    if (st !== 'ok') emit('notify', st === 'missing' ? '结果文件不存在' : '无输出文件', 'warning');
    return st
  } catch (e) {
    emit('notify', e.message || '下载失败');
    return 'error'
  } finally {
    downloadingId.value = null;
  }
}

// 内部下载执行：取 base64 → 触发浏览器下载。不占单槽 downloadingId，
// 供「全部下载」并发池并行调用（Q19）。
async function _doDownload(r) {
  if (!r.out_file) return 'none'
  const res = await apiModule.get(props.api, '/subset/download', { id: r.id });
  if (!res?.data) return 'missing'
  const bytes = Uint8Array.from(atob(res.data), c => c.charCodeAt(0));
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = res.name || (r.file_name.replace(/\.ass$/i, '') + '.ziti.ass');
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return 'ok'
}

// 可批量下载的记录：当前筛选下全部成功且带输出文件（已一次性取全）
const downloadableRecords = computed$3(() =>
  records.value.filter(r => r.status === 'success' && r.out_file)
);

// 小并发池：最多 3 个并发下载，按每条记录的返回状态准确统计
async function downloadPool(targets) {
  const stats = { ok: 0, fail: 0, missing: 0 };
  let head = 0;
  const worker = async () => {
    while (head < targets.length) {
      const r = targets[head++];
      try {
        const st = await _doDownload(r);
        if (st === 'ok') stats.ok += 1;
        else if (st === 'missing') stats.missing += 1;
        else stats.fail += 1;
      } catch (e) {
        stats.fail += 1;
      }
    }
  };
  await Promise.all([worker(), worker(), worker()]);
  return stats
}
function notifyDownloadStats(stats, label = '') {
  const failed = stats.fail + stats.missing;
  const prefix = label ? `${label}：` : '';
  if (failed) {
    emit(
      'notify',
      `${prefix}已下载 ${stats.ok} 个，${stats.fail} 个失败${stats.missing ? `，${stats.missing} 个文件缺失` : ''}`,
      stats.ok ? 'success' : 'warning'
    );
  } else {
    emit('notify', `${prefix}已下载 ${stats.ok} 个结果文件`, 'success');
  }
}

const downloadAllBusy = ref$3(false);
async function downloadAll() {
  if (downloadAllBusy.value) return
  if (downloadingId.value) {
    emit('notify', '有下载正在进行，请稍候', 'warning');
    return
  }
  const targets = downloadableRecords.value;
  if (!targets.length) {
    emit('notify', '当前筛选下没有可下载的成功成品', 'warning');
    return
  }
  downloadAllBusy.value = true;
  try {
    notifyDownloadStats(await downloadPool(targets));
  } finally {
    downloadAllBusy.value = false;
  }
}

// 本组全部下载：只下这个抽屉里的成功成品（不依赖是否已展开到该组）
async function downloadGroup(g) {
  if (groupBusy.value || downloadAllBusy.value) return
  if (downloadingId.value) {
    emit('notify', '有下载正在进行，请稍候', 'warning');
    return
  }
  const targets = g.downloadable || [];
  if (!targets.length) {
    emit('notify', '本组没有可下载的成功成品', 'warning');
    return
  }
  groupBusy.value = g.key;
  try {
    notifyDownloadStats(await downloadPool(targets), `本组（${g.label}）`);
  } finally {
    groupBusy.value = '';
  }
}

// 删除整组：有成品时二次确认（监控/上传会连成品一起删，入库只删记录）
function askDeleteGroup(g) {
  groupTarget.value = g;
  groupConfirm.value = true;
}
const groupDeleting = ref$3(false);
async function confirmDeleteGroup() {
  const g = groupTarget.value;
  if (!g || groupDeleting.value) return
  groupDeleting.value = true;
  const ids = g.records.map(r => Number(r.id)).filter(Boolean);
  const errors = [];
  let head = 0;
  const worker = async () => {
    while (head < ids.length) {
      const id = ids[head++];
      try {
        await apiModule.post(props.api, `/subset/delete/${id}`);
      } catch (e) {
        errors.push(id);
      }
    }
  };
  try {
    await Promise.all([worker(), worker(), worker()]);
    groupConfirm.value = false;
    groupTarget.value = null;
    const ok = ids.length - errors.length;
    emit(
      'notify',
      errors.length ? `已删除 ${ok} 条，${errors.length} 条失败` : `已删除本组 ${ok} 条记录`,
      errors.length ? 'warning' : 'success'
    );
    await loadRecords(true, true);
  } finally {
    groupDeleting.value = false;
  }
}

async function deleteRecord(id) {
  try {
    await apiModule.post(props.api, `/subset/delete/${id}`);
    emit('notify', '已删除记录', 'success');
    await loadRecords(true, true);
  } catch (e) {
    emit('notify', e.message || '删除失败');
  }
}

const clearConfirm = ref$3(false);
const clearingRecords = ref$3(false);
async function clearRecords() {
  if (clearingRecords.value) return
  clearingRecords.value = true;
  clearConfirm.value = false;
  try {
    await apiModule.del(props.api, '/subset/clear');
    await loadRecords(true, true);
    emit('notify', '已清空子集化记录', 'success');
  } catch (e) {
    emit('notify', e.message || '清空失败');
  } finally {
    clearingRecords.value = false;
  }
}

onMounted$3(() => {
  loadStatus();
  loadPending();
  loadRecords();
  startPolling();
});
// keep-alive 缓存场景：切回时恢复轮询并重拉数据（Q1 修复；Q14 后切 Tab
// 不再由 Page 广播刷新键，各视图自查自刷）
onActivated$3(() => {
  loadStatus();
  loadPending();
  refreshCurrentPage();
  startPolling();
});
// 切走（进入 keep-alive 缓存）时停止轮询，避免后台不可见视图持续打接口（Q1 修复）
onDeactivated$1(() => {
  stopPolling();
});
onUnmounted$1(() => stopPolling());

let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    loadPending();
    // Q7 修复：轮询刷新保持当前页码（替换当前页区间），不再强制回第 1 页，
    // 避免翻页浏览时每 30 秒被拉回首页；也避免 loadRecords(false) 的
    // 追加语义在轮询里造成重复数据
    refreshCurrentPage();
    loadStatus();
  }, 30000);
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  stopRebuildPolling();
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$3("v-icon");
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_spacer = _resolveComponent$3("v-spacer");
  const _component_v_alert = _resolveComponent$3("v-alert");
  const _component_v_card_title = _resolveComponent$3("v-card-title");
  const _component_v_divider = _resolveComponent$3("v-divider");
  const _component_v_progress_linear = _resolveComponent$3("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$3("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$3("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$3("v-list-item");
  const _component_v_list = _resolveComponent$3("v-list");
  const _component_v_card = _resolveComponent$3("v-card");
  const _component_v_col = _resolveComponent$3("v-col");
  const _component_v_select = _resolveComponent$3("v-select");
  const _component_v_text_field = _resolveComponent$3("v-text-field");
  const _component_v_chip = _resolveComponent$3("v-chip");
  const _component_v_row = _resolveComponent$3("v-row");
  const _component_v_card_text = _resolveComponent$3("v-card-text");
  const _component_v_card_actions = _resolveComponent$3("v-card-actions");
  const _component_v_dialog = _resolveComponent$3("v-dialog");

  return (_openBlock$3(), _createElementBlock$3("div", _hoisted_1$3, [
    _createElementVNode$3("div", _hoisted_2$3, [
      _createVNode$3(_component_v_btn, {
        variant: "tonal",
        color: "primary",
        disabled: !__props.enabled || uploading.value,
        loading: uploading.value,
        title: "上传字幕到「待处理」（支持 .ass 与 .zip/.7z/.rar 压缩包）",
        onClick: _cache[0] || (_cache[0] = $event => (uploadRef.value?.click()))
      }, {
        default: _withCtx$3(() => [
          _createVNode$3(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$3(() => [...(_cache[11] || (_cache[11] = [
              _createTextVNode$3("mdi-upload", -1)
            ]))]),
            _: 1
          }),
          _cache[12] || (_cache[12] = _createTextVNode$3(" 上传字幕 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createElementVNode$3("input", {
        ref_key: "uploadRef",
        ref: uploadRef,
        type: "file",
        accept: _unref$1(uploadAcceptFor)(_unref$1(DESKTOP_ACCEPT_ASS)),
        multiple: "",
        style: {"display":"none"},
        onChange: handleUpload
      }, null, 40, _hoisted_3$3),
      _createVNode$3(_component_v_btn, {
        color: "primary",
        disabled: !__props.enabled || scanning.value || !pendingList.value.length,
        loading: scanning.value,
        title: "处理「待处理」中的全部字幕（子集化并内嵌字体）",
        onClick: scanAll
      }, {
        default: _withCtx$3(() => [
          _createVNode$3(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$3(() => [...(_cache[13] || (_cache[13] = [
              _createTextVNode$3("mdi-magnify-scan", -1)
            ]))]),
            _: 1
          }),
          _cache[14] || (_cache[14] = _createTextVNode$3(" 全量子集化 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createVNode$3(_component_v_btn, {
        variant: "tonal",
        disabled: !__props.enabled || !pendingList.value.length,
        title: "清空左栏待处理",
        onClick: clearPending
      }, {
        default: _withCtx$3(() => [
          _createVNode$3(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$3(() => [...(_cache[15] || (_cache[15] = [
              _createTextVNode$3("mdi-delete-sweep-outline", -1)
            ]))]),
            _: 1
          }),
          _cache[16] || (_cache[16] = _createTextVNode$3(" 清空待处理 ", -1))
        ]),
        _: 1
      }, 8, ["disabled"]),
      _createVNode$3(_component_v_spacer),
      _createElementVNode$3("span", _hoisted_4$3, [
        _createVNode$3(_component_v_icon, {
          size: 15,
          color: indexRebuilding.value ? 'info' : (indexReady.value ? 'success' : 'warning')
        }, {
          default: _withCtx$3(() => [
            _createTextVNode$3(_toDisplayString$3(indexRebuilding.value ? 'mdi-database-sync-outline' : (indexReady.value ? 'mdi-database-check' : 'mdi-database-off')), 1)
          ]),
          _: 1
        }, 8, ["color"]),
        (indexRebuilding.value)
          ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
              _createTextVNode$3(" 字体库索引：正在重建…" + _toDisplayString$3(indexProgressText.value), 1)
            ], 64))
          : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
              _createTextVNode$3(" 字体库索引：" + _toDisplayString$3(indexReady.value ? `${indexFileCount.value} 个文件 / ${indexCount.value} 个 face` : '未构建') + "（" + _toDisplayString$3(indexTimeText()) + "） ", 1)
            ], 64))
      ]),
      _createVNode$3(_component_v_btn, {
        variant: "text",
        size: "small",
        color: "primary",
        class: "ml-2",
        disabled: !__props.enabled || indexRebuilding.value,
        loading: rebuildingIndex.value || indexRebuilding.value,
        title: "清空索引后逐文件重新解析字体库（全部重建，非增量；耗时取决于字体数量）",
        onClick: _cache[1] || (_cache[1] = $event => (rebuildConfirm.value = true))
      }, {
        default: _withCtx$3(() => [
          _createVNode$3(_component_v_icon, {
            start: "",
            size: "15"
          }, {
            default: _withCtx$3(() => [...(_cache[17] || (_cache[17] = [
              _createTextVNode$3("mdi-database-refresh", -1)
            ]))]),
            _: 1
          }),
          _cache[18] || (_cache[18] = _createTextVNode$3(" 全部重建 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"])
    ]),
    (statusLoaded.value && !engineReady.value)
      ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
          key: 0,
          type: "error",
          variant: "tonal",
          density: "compact",
          class: "mb-3"
        }, {
          default: _withCtx$3(() => [...(_cache[19] || (_cache[19] = [
            _createTextVNode$3(" HarfBuzz 子集化引擎未就绪，子集化不可用。请到「仪表盘 → 依赖」中重新安装 uharfbuzz。 ", -1)
          ]))]),
          _: 1
        }))
      : _createCommentVNode$3("", true),
    _createVNode$3(_component_v_row, {
      "no-gutters": "",
      class: "zt-subset-row"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_col, {
          cols: "12",
          md: "5"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-list-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$3(() => [...(_cache[20] || (_cache[20] = [
                        _createTextVNode$3("mdi-tray-full", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$3(" 待处理（" + _toDisplayString$3(pendingList.value.length) + "） ", 1)
                  ]),
                  _: 1
                }),
                _createVNode$3(_component_v_divider),
                (loadingPending.value)
                  ? (_openBlock$3(), _createBlock$3(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$3("", true),
                (!loadingPending.value && !pendingList.value.length)
                  ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_5$3, [...(_cache[21] || (_cache[21] = [
                      _createTextVNode$3(" 暂无待处理字幕", -1),
                      _createElementVNode$3("br", null, null, -1),
                      _createElementVNode$3("span", { class: "zt-empty-sub" }, "上传字幕，或设置开启「入库后自动子集化」+「目录自动收集」关闭时自动收集", -1)
                    ]))]))
                  : (_openBlock$3(), _createElementBlock$3("div", _hoisted_6$3, [
                      _createVNode$3(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$3(() => [
                          (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(pendingList.value, (p) => {
                            return (_openBlock$3(), _createBlock$3(_component_v_list_item, {
                              key: p.id,
                              lines: "two"
                            }, {
                              prepend: _withCtx$3(() => [
                                _createVNode$3(_component_v_icon, {
                                  color: "primary",
                                  size: "18"
                                }, {
                                  default: _withCtx$3(() => [...(_cache[22] || (_cache[22] = [
                                    _createTextVNode$3("mdi-subtitles-outline", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              append: _withCtx$3(() => [
                                _createVNode$3(_component_v_btn, {
                                  size: "small",
                                  variant: "text",
                                  icon: "",
                                  disabled: !__props.enabled,
                                  title: "移除该项",
                                  onClick: $event => (removePending(p.id))
                                }, {
                                  default: _withCtx$3(() => [
                                    _createVNode$3(_component_v_icon, { size: "16" }, {
                                      default: _withCtx$3(() => [...(_cache[23] || (_cache[23] = [
                                        _createTextVNode$3("mdi-close", -1)
                                      ]))]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }, 8, ["disabled", "onClick"])
                              ]),
                              default: _withCtx$3(() => [
                                _createVNode$3(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$3(() => [
                                    _createTextVNode$3(_toDisplayString$3(p.file_name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$3(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$3(() => [
                                    _createTextVNode$3(_toDisplayString$3(p.source === 'watch' ? '目录监控' : '手动上传') + " · " + _toDisplayString$3(p.created_at), 1)
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
                    ]))
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
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-list-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_title, { class: "zt-card-title zt-card-title-row" }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$3(() => [...(_cache[24] || (_cache[24] = [
                        _createTextVNode$3("mdi-history", -1)
                      ]))]),
                      _: 1
                    }),
                    _createElementVNode$3("span", _hoisted_7$3, "结果（" + _toDisplayString$3(recordTotal.value) + "）", 1),
                    _createVNode$3(_component_v_spacer),
                    _createElementVNode$3("div", _hoisted_8$3, [
                      _createVNode$3(_component_v_btn, {
                        size: "small",
                        variant: "tonal",
                        color: "success",
                        disabled: !__props.enabled || downloadAllBusy.value || !downloadableRecords.value.length,
                        loading: downloadAllBusy.value,
                        title: "下载当前筛选下全部成功成品字幕",
                        onClick: downloadAll
                      }, {
                        default: _withCtx$3(() => [
                          _createVNode$3(_component_v_icon, {
                            start: "",
                            size: "15"
                          }, {
                            default: _withCtx$3(() => [...(_cache[25] || (_cache[25] = [
                              _createTextVNode$3("mdi-download-multiple", -1)
                            ]))]),
                            _: 1
                          }),
                          _cache[26] || (_cache[26] = _createElementVNode$3("span", { class: "zt-act-label" }, "全部下载", -1))
                        ]),
                        _: 1
                      }, 8, ["disabled", "loading"]),
                      _createVNode$3(_component_v_btn, {
                        size: "small",
                        variant: "tonal",
                        color: "warning",
                        disabled: !__props.enabled || retrying.value || !hasRetriable(),
                        loading: retrying.value,
                        title: "对失败/缺字体的字幕重新子集化（补好缺失字体后使用）",
                        onClick: retryFailed
                      }, {
                        default: _withCtx$3(() => [
                          _createVNode$3(_component_v_icon, {
                            start: "",
                            size: "15"
                          }, {
                            default: _withCtx$3(() => [...(_cache[27] || (_cache[27] = [
                              _createTextVNode$3("mdi-refresh", -1)
                            ]))]),
                            _: 1
                          }),
                          _cache[28] || (_cache[28] = _createElementVNode$3("span", { class: "zt-act-label" }, "重试失败", -1))
                        ]),
                        _: 1
                      }, 8, ["disabled", "loading"]),
                      _createVNode$3(_component_v_btn, {
                        size: "small",
                        variant: "tonal",
                        color: "error",
                        disabled: !__props.enabled || clearingRecords.value || downloadAllBusy.value || !!downloadingId.value || !records.value.length,
                        loading: clearingRecords.value,
                        title: "清空全部子集化记录（监控/上传来历的成品一并删除；MP 入库只删记录，不动媒体库原字幕）",
                        onClick: _cache[2] || (_cache[2] = $event => (clearConfirm.value = true))
                      }, {
                        default: _withCtx$3(() => [
                          _createVNode$3(_component_v_icon, {
                            start: "",
                            size: "15"
                          }, {
                            default: _withCtx$3(() => [...(_cache[29] || (_cache[29] = [
                              _createTextVNode$3("mdi-delete-sweep", -1)
                            ]))]),
                            _: 1
                          }),
                          _cache[30] || (_cache[30] = _createElementVNode$3("span", { class: "zt-act-label" }, "全部清空", -1))
                        ]),
                        _: 1
                      }, 8, ["disabled", "loading"])
                    ])
                  ]),
                  _: 1
                }),
                _createVNode$3(_component_v_divider),
                _createElementVNode$3("div", _hoisted_9$3, [
                  _createVNode$3(_component_v_select, {
                    modelValue: filterStatus.value,
                    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((filterStatus).value = $event)),
                    items: statusFilterOptions,
                    "item-title": "title",
                    "item-value": "value",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "zt-filter-status"
                  }, null, 8, ["modelValue"]),
                  _createVNode$3(_component_v_text_field, {
                    modelValue: recordSearch.value,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((recordSearch).value = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    clearable: !!recordSearch.value,
                    placeholder: "搜索字幕名…",
                    "prepend-inner-icon": "mdi-magnify",
                    class: "zt-filter-search"
                  }, null, 8, ["modelValue", "clearable"])
                ]),
                _createVNode$3(_component_v_divider),
                (loadingRecords.value)
                  ? (_openBlock$3(), _createBlock$3(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$3("", true),
                _createElementVNode$3("div", {
                  class: "zt-list-body zt-record-body",
                  onScroll: onRecordsScroll
                }, [
                  (!loadingRecords.value && !groupedRecords.value.length)
                    ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_10$3, [
                        _createTextVNode$3(" 暂无" + _toDisplayString$3(filterStatus.value || recordSearch.value ? '匹配' : '') + "处理结果", 1),
                        _cache[31] || (_cache[31] = _createElementVNode$3("br", null, null, -1)),
                        _cache[32] || (_cache[32] = _createElementVNode$3("span", { class: "zt-empty-sub" }, "处理完成后结果与输出文件在这里展示，可下载", -1))
                      ]))
                    : _createCommentVNode$3("", true),
                  (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(visibleGroups.value, (g) => {
                    return (_openBlock$3(), _createElementBlock$3("div", {
                      key: g.key,
                      class: _normalizeClass$1(["zt-group", `zt-group-${g.color}`])
                    }, [
                      _createElementVNode$3("div", {
                        class: "zt-group-head",
                        onClick: $event => (toggleGroup(g))
                      }, [
                        _createVNode$3(_component_v_icon, { size: "18" }, {
                          default: _withCtx$3(() => [
                            _createTextVNode$3(_toDisplayString$3(g.expanded ? 'mdi-chevron-down' : 'mdi-chevron-right'), 1)
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode$3(_component_v_icon, {
                          size: "16",
                          color: g.color === 'grey' ? undefined : g.color
                        }, {
                          default: _withCtx$3(() => [
                            _createTextVNode$3(_toDisplayString$3(g.expanded ? 'mdi-folder-open' : 'mdi-folder'), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"]),
                        _createElementVNode$3("span", _hoisted_12$2, _toDisplayString$3(g.label), 1),
                        _createElementVNode$3("span", _hoisted_13$2, _toDisplayString$3(g.records.length), 1),
                        _createElementVNode$3("span", _hoisted_14$2, [
                          (g.stats.success)
                            ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                key: 0,
                                color: "success",
                                size: "x-small",
                                variant: "tonal"
                              }, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3("✓ " + _toDisplayString$3(g.stats.success), 1)
                                ]),
                                _: 2
                              }, 1024))
                            : _createCommentVNode$3("", true),
                          (g.stats.missing)
                            ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                key: 1,
                                color: "warning",
                                size: "x-small",
                                variant: "tonal"
                              }, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3("⚠ " + _toDisplayString$3(g.stats.missing), 1)
                                ]),
                                _: 2
                              }, 1024))
                            : _createCommentVNode$3("", true),
                          (g.stats.error)
                            ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                key: 2,
                                color: "error",
                                size: "x-small",
                                variant: "tonal"
                              }, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3("✕ " + _toDisplayString$3(g.stats.error), 1)
                                ]),
                                _: 2
                              }, 1024))
                            : _createCommentVNode$3("", true),
                          (g.stats.skipped)
                            ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                key: 3,
                                color: "info",
                                size: "x-small",
                                variant: "tonal"
                              }, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3("跳过 " + _toDisplayString$3(g.stats.skipped), 1)
                                ]),
                                _: 2
                              }, 1024))
                            : _createCommentVNode$3("", true)
                        ]),
                        _createElementVNode$3("span", _hoisted_15$2, [
                          _createVNode$3(_component_v_btn, {
                            size: "x-small",
                            variant: "tonal",
                            color: "success",
                            disabled: !__props.enabled || groupBusy.value === g.key || !g.downloadable.length,
                            loading: groupBusy.value === g.key,
                            title: "只下载本组成功成品",
                            onClick: _withModifiers($event => (downloadGroup(g)), ["stop"])
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_v_icon, {
                                start: "",
                                size: "14"
                              }, {
                                default: _withCtx$3(() => [...(_cache[33] || (_cache[33] = [
                                  _createTextVNode$3("mdi-download-multiple", -1)
                                ]))]),
                                _: 1
                              }),
                              _cache[34] || (_cache[34] = _createElementVNode$3("span", { class: "d-none d-sm-inline" }, "全部下载", -1))
                            ]),
                            _: 1
                          }, 8, ["disabled", "loading", "onClick"]),
                          _createVNode$3(_component_v_btn, {
                            size: "small",
                            variant: "text",
                            icon: "",
                            disabled: !__props.enabled || groupDeleting.value,
                            title: "删除本组全部记录（监控/上传的成品一并删除）",
                            onClick: _withModifiers($event => (askDeleteGroup(g)), ["stop"])
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_v_icon, {
                                size: "16",
                                color: "error"
                              }, {
                                default: _withCtx$3(() => [...(_cache[35] || (_cache[35] = [
                                  _createTextVNode$3("mdi-close", -1)
                                ]))]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }, 8, ["disabled", "onClick"])
                        ])
                      ], 8, _hoisted_11$2),
                      (g.expanded)
                        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_16$2, [
                            _createVNode$3(_component_v_list, {
                              density: "compact",
                              class: "pa-0"
                            }, {
                              default: _withCtx$3(() => [
                                (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(g.visibleRecords, (r) => {
                                  return (_openBlock$3(), _createBlock$3(_component_v_list_item, {
                                    key: r.id,
                                    lines: "two"
                                  }, {
                                    prepend: _withCtx$3(() => [
                                      _createVNode$3(_component_v_chip, {
                                        color: statusColor(r),
                                        size: "x-small",
                                        variant: "tonal",
                                        title: r.status === 'missing' && !r.retryable ? '缺的字体尚未补齐：点击去「缺失字体」页上传' : (r.status === 'error' ? '处理失败：点击去「缺失字体」页处理' : (r.status === 'missing' && r.retryable ? '缺的字体已入库：点抽屉顶部「重试失败」重新子集化' : '')),
                                        class: _normalizeClass$1({ 'zt-status-link': (r.status === 'missing' && !r.retryable) || r.status === 'error' }),
                                        disabled: !__props.enabled,
                                        onClick: $event => (onStatusTagClick(r))
                                      }, {
                                        default: _withCtx$3(() => [
                                          _createTextVNode$3(_toDisplayString$3(statusText(r)), 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["color", "title", "class", "disabled", "onClick"])
                                    ]),
                                    append: _withCtx$3(() => [
                                      (r.status === 'success' && r.out_file)
                                        ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                            key: 0,
                                            size: "x-small",
                                            variant: "tonal",
                                            color: "success",
                                            class: "mr-1",
                                            title: "下载结果文件",
                                            disabled: !__props.enabled || downloadingId.value === r.id,
                                            loading: downloadingId.value === r.id,
                                            onClick: $event => (downloadRecord(r))
                                          }, {
                                            default: _withCtx$3(() => [
                                              _createVNode$3(_component_v_icon, {
                                                start: "",
                                                size: "14"
                                              }, {
                                                default: _withCtx$3(() => [...(_cache[36] || (_cache[36] = [
                                                  _createTextVNode$3("mdi-download", -1)
                                                ]))]),
                                                _: 1
                                              }),
                                              _cache[37] || (_cache[37] = _createTextVNode$3(" 下载 ", -1))
                                            ]),
                                            _: 1
                                          }, 8, ["disabled", "loading", "onClick"]))
                                        : _createCommentVNode$3("", true),
                                      _createVNode$3(_component_v_btn, {
                                        size: "small",
                                        variant: "text",
                                        icon: "",
                                        disabled: !__props.enabled,
                                        title: "删除该记录",
                                        onClick: $event => (deleteRecord(r.id))
                                      }, {
                                        default: _withCtx$3(() => [
                                          _createVNode$3(_component_v_icon, { size: "16" }, {
                                            default: _withCtx$3(() => [...(_cache[38] || (_cache[38] = [
                                              _createTextVNode$3("mdi-close", -1)
                                            ]))]),
                                            _: 1
                                          })
                                        ]),
                                        _: 1
                                      }, 8, ["disabled", "onClick"])
                                    ]),
                                    default: _withCtx$3(() => [
                                      _createVNode$3(_component_v_list_item_title, { class: "zt-font-name" }, {
                                        default: _withCtx$3(() => [
                                          _createTextVNode$3(_toDisplayString$3(r.file_name), 1)
                                        ]),
                                        _: 2
                                      }, 1024),
                                      _createVNode$3(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                        default: _withCtx$3(() => [
                                          (r.reason)
                                            ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                                                _createTextVNode$3(_toDisplayString$3(r.reason), 1)
                                              ], 64))
                                            : (r.out_file)
                                              ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 1 }, [
                                                  _createTextVNode$3(_toDisplayString$3(r.out_file), 1)
                                                ], 64))
                                              : (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 2 }, [
                                                  _createTextVNode$3("—")
                                                ], 64)),
                                          (r.created_at)
                                            ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_17$2, _toDisplayString$3(r.created_at), 1))
                                            : _createCommentVNode$3("", true)
                                        ]),
                                        _: 2
                                      }, 1024)
                                    ]),
                                    _: 2
                                  }, 1024))
                                }), 128))
                              ]),
                              _: 2
                            }, 1024),
                            (g.truncated)
                              ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_18$2, " 还有 " + _toDisplayString$3(g.records.length - g.visibleRecords.length) + " 条，下拉加载… ", 1))
                              : _createCommentVNode$3("", true)
                          ]))
                        : _createCommentVNode$3("", true)
                    ], 2))
                  }), 128)),
                  (hasMoreRecords.value)
                    ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_19$2, [
                        _createVNode$3(_component_v_btn, {
                          size: "small",
                          variant: "text",
                          color: "primary",
                          onClick: loadMoreRecords
                        }, {
                          default: _withCtx$3(() => [...(_cache[39] || (_cache[39] = [
                            _createTextVNode$3("加载更多", -1)
                          ]))]),
                          _: 1
                        })
                      ]))
                    : _createCommentVNode$3("", true)
                ], 32)
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
      modelValue: groupConfirm.value,
      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((groupConfirm).value = $event)),
      "max-width": "440"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card, null, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card_title, { class: "text-h6" }, {
              default: _withCtx$3(() => [
                _createTextVNode$3("删除「" + _toDisplayString$3(groupTarget.value?.label || '') + "」整组？", 1)
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_text, null, {
              default: _withCtx$3(() => [
                _createTextVNode$3(" 将删除本组 " + _toDisplayString$3(groupTarget.value?.records?.length || 0) + " 条子集化记录", 1),
                (groupTarget.value?.records?.some(r => r.out_file))
                  ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 0 }, [
                      _createTextVNode$3("， 并同步删除监控/上传来历的成品文件（含输出目录中对应文件）")
                    ], 64))
                  : _createCommentVNode$3("", true),
                _cache[40] || (_cache[40] = _createTextVNode$3("。 MP 入库记录只删记录，不动媒体库原字幕；字体库与待处理列表不受影响。 ", -1))
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_actions, null, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[5] || (_cache[5] = $event => (groupConfirm.value = false))
                }, {
                  default: _withCtx$3(() => [...(_cache[41] || (_cache[41] = [
                    _createTextVNode$3("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$3(_component_v_btn, {
                  color: "error",
                  variant: "tonal",
                  loading: groupDeleting.value,
                  onClick: confirmDeleteGroup
                }, {
                  default: _withCtx$3(() => [...(_cache[42] || (_cache[42] = [
                    _createTextVNode$3("删除整组", -1)
                  ]))]),
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
      modelValue: clearConfirm.value,
      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((clearConfirm).value = $event)),
      "max-width": "440"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card, null, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card_title, { class: "text-h6" }, {
              default: _withCtx$3(() => [...(_cache[43] || (_cache[43] = [
                _createTextVNode$3("清空全部子集化记录？", -1)
              ]))]),
              _: 1
            }),
            _createVNode$3(_component_v_card_text, null, {
              default: _withCtx$3(() => [...(_cache[44] || (_cache[44] = [
                _createTextVNode$3(" 将删除全部子集化结果记录，并同步删除监控/上传来历的成品文件（含输出目录中对应文件与空的剧名文件夹）。 MP 入库记录只删记录，不动媒体库原字幕；「待处理」列表不受影响。 ", -1)
              ]))]),
              _: 1
            }),
            _createVNode$3(_component_v_card_actions, null, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[7] || (_cache[7] = $event => (clearConfirm.value = false))
                }, {
                  default: _withCtx$3(() => [...(_cache[45] || (_cache[45] = [
                    _createTextVNode$3("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$3(_component_v_btn, {
                  color: "error",
                  variant: "tonal",
                  loading: clearingRecords.value,
                  onClick: clearRecords
                }, {
                  default: _withCtx$3(() => [...(_cache[46] || (_cache[46] = [
                    _createTextVNode$3("全部清空", -1)
                  ]))]),
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
      modelValue: rebuildConfirm.value,
      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((rebuildConfirm).value = $event)),
      "max-width": "440"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card, null, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card_title, { class: "text-h6" }, {
              default: _withCtx$3(() => [...(_cache[47] || (_cache[47] = [
                _createTextVNode$3("全部重建字体库？", -1)
              ]))]),
              _: 1
            }),
            _createVNode$3(_component_v_card_text, null, {
              default: _withCtx$3(() => [...(_cache[48] || (_cache[48] = [
                _createTextVNode$3(" 将清空现有字体索引，再逐文件重新解析整个字体库（生成 face/别名/字符覆盖）。 日常归档与入库仍是增量/减量，不需要用这里。耗时取决于字体数量，期间检索可能变慢。 人工映射与字幕缺失快照不受影响。 ", -1)
              ]))]),
              _: 1
            }),
            _createVNode$3(_component_v_card_actions, null, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[9] || (_cache[9] = $event => (rebuildConfirm.value = false))
                }, {
                  default: _withCtx$3(() => [...(_cache[49] || (_cache[49] = [
                    _createTextVNode$3("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$3(_component_v_btn, {
                  color: "primary",
                  variant: "tonal",
                  loading: rebuildingIndex.value,
                  onClick: rebuildIndex
                }, {
                  default: _withCtx$3(() => [...(_cache[50] || (_cache[50] = [
                    _createTextVNode$3("开始重建", -1)
                  ]))]),
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
    }, 8, ["modelValue"])
  ]))
}
}

};
const Subset = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-32a6e38c"]]);

const {createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,toDisplayString:_toDisplayString$2,createElementVNode:_createElementVNode$2,openBlock:_openBlock$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,renderList:_renderList$2,Fragment:_Fragment$2,createElementBlock:_createElementBlock$2,unref:_unref} = await importShared('vue');


const _hoisted_1$2 = { class: "zt-missing" };
const _hoisted_2$2 = { class: "zt-status-line text-body-2 mb-3" };
const _hoisted_3$2 = { class: "mr-5" };
const _hoisted_4$2 = { class: "mr-5" };
const _hoisted_5$2 = { class: "mr-5" };
const _hoisted_6$2 = {
  key: 1,
  class: "zt-uploads pa-3"
};
const _hoisted_7$2 = {
  key: 0,
  class: "zt-chip-target"
};
const _hoisted_8$2 = { class: "d-flex flex-wrap gap-2 align-center" };
const _hoisted_9$2 = ["accept"];
const _hoisted_10$2 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_11$1 = {
  key: 2,
  class: "zt-list-body"
};
const _hoisted_12$1 = { class: "zt-char-preview" };
const _hoisted_13$1 = {
  key: 0,
  class: "text-center pa-2"
};
const _hoisted_14$1 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_15$1 = {
  key: 2,
  class: "zt-list-body"
};
const _hoisted_16$1 = {
  key: 0,
  class: "text-center pa-2"
};
const _hoisted_17$1 = { class: "text-body-2 mb-3" };
const _hoisted_18$1 = { key: 0 };
const _hoisted_19$1 = {
  key: 0,
  class: "zt-font-meta mb-3"
};

const {computed: computed$2,onActivated: onActivated$2,onDeactivated,onMounted: onMounted$2,onUnmounted,ref: ref$2} = await importShared('vue');

const PREVIEW_N = 5;

// 可选的缺失目标（检查缺失列表），用于上传时人工指定映射

const _sfc_main$2 = {
  __name: 'MissingFonts',
  props: {
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
},
  emits: ['notify', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const summary = ref$2({ check: [], subset: [], lib_dir: '', hb_ok: false, engine: 'harfbuzz', index_faces: 0 });
const uploads = ref$2([]);
const mappings = ref$2([]);
const loading = ref$2(false);
const expanded = ref$2({ check: false, subset: false });
// 严格上传：可选目标缺失字体（人工映射）；不选则按字体内部名称/别名自动匹配
const targetHint = ref$2(null);

const uploadRef = ref$2(null);
const uploading = ref$2(false);
const classifying = ref$2(false);
const clearing = ref$2(false);

const targetOptions = computed$2(() => (summary.value.check || []).map(f => ({
  name: f.name,
  title: f.chars ? `${f.name}（缺 ${f.codepoints_count || 0} 字：${f.chars}）` : f.name,
})));

async function loadSummary() {
  loading.value = true;
  try {
    summary.value = await apiModule.get(props.api, '/missing/summary');
  } catch (e) {
    emit('notify', e.message || '读取缺失字体汇总失败');
  } finally {
    loading.value = false;
  }
}

async function loadUploads() {
  try {
    uploads.value = await apiModule.get(props.api, '/missing/uploads');
  } catch (e) {
    emit('notify', e.message || '读取上传列表失败');
  }
}

// 上传字体（左右两栏共用）：严格校验（名称/别名命中且覆盖缺失字符），可选人工指定目标
async function handleUpload(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 3 个
  const BATCH = 3;
  let total = 0;
  const rejected = [];
  const notes = [];
  uploading.value = true;
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const form = new FormData();
      for (const file of chunk) form.append('file', file);
      if (targetHint.value) form.append('target', targetHint.value);
      const res = await props.api.post(
        'plugin/Zitifenlei/missing/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      const body = res?.data ?? res;
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '上传失败'}`);
        break
      } else {
        total += (body?.data?.count ?? 0);
        for (const r of body?.data?.rejected || []) rejected.push(r);
        if (Array.isArray(body?.data?.notes)) notes.push(...body.data.notes);
      }
    }
    if (total) {
      emit('notify', `已上传 ${total} 个字体（通过缺失校验），点击「归类」入库`, 'success');
    }
    if (rejected.length) {
      const detail = rejected.slice(0, 3).map(r => `${r.file_name}：${r.reason}`).join('；');
      emit('notify', `${rejected.length} 个字体未通过校验：${detail}`, 'warning');
    }
    const noteText = formatNotes(notes);
    if (noteText) emit('notify', `部分文件被跳过：${noteText}`, 'warning');
    if (!total && !rejected.length) emit('notify', '没有字体通过缺失校验', 'warning');
    await loadUploads();
    await loadSummary();
    await loadMappings();
  } catch (e) {
    emit('notify', e.message || '上传失败');
  } finally {
    uploading.value = false;
  }
}

// 归类：全部上传字体入库 + 重建索引（运行中禁用）
async function classify() {
  if (classifying.value) return
  classifying.value = true;
  try {
    const res = await apiModule.post(props.api, '/missing/classify');
    const recheck = res?.recheck || {};
    let msg = res?.message || '已入库';
    if (recheck.checked) {
      msg += `（已重检 ${recheck.checked} 个字幕：完整 ${recheck.ok}，仍缺 ${recheck.missing}）`;
    }
    emit('notify', msg, 'success');
    if ((res?.failed || []).length) {
      emit('notify', `${res.failed.length} 个字体未入库：${res.failed.slice(0, 3).join('；')}`, 'warning');
    }
    await loadUploads();
    await loadSummary();
    await loadMappings();
    emit('action', { type: 'missing_classified' });
  } catch (e) {
    emit('notify', e.message || '归类失败');
  } finally {
    classifying.value = false;
  }
}

// ===== 人工映射（改派） =====
const remapDialog = ref$2(false);
const remapItem = ref$2(null);
const remapTarget = ref$2('');
const remapping = ref$2(false);

function openRemap(u) {
  remapItem.value = u;
  remapTarget.value = u.matched || '';
  remapDialog.value = true;
}

async function submitRemap() {
  if (!remapItem.value || !remapTarget.value) return
  remapping.value = true;
  try {
    await apiModule.post(props.api, '/missing/remap', {
      path: remapItem.value.path,
      target: remapTarget.value,
    });
    emit('notify', '已改派缺失目标', 'success');
    remapDialog.value = false;
    await loadUploads();
    await loadMappings();
  } catch (e) {
    emit('notify', e.message || '改派失败');
  } finally {
    remapping.value = false;
  }
}

async function loadMappings() {
  try {
    mappings.value = await apiModule.get(props.api, '/missing/mappings');
  } catch (e) {
    mappings.value = [];
  }
}

async function removeMapping(m) {
  try {
    await apiModule.del(props.api, '/missing/mappings/remove', { id: m.id });
    mappings.value = mappings.value.filter(x => x.id !== m.id);
    emit('notify', '已删除映射记录', 'success');
  } catch (e) {
    emit('notify', e.message || '删除失败');
  }
}

async function clearUploads() {
  if (clearing.value) return
  clearing.value = true;
  try {
    await apiModule.del(props.api, '/missing/uploads/clear');
    uploads.value = [];
    emit('notify', '已清除上传的字体', 'success');
  } catch (e) {
    emit('notify', e.message || '清除失败');
  } finally {
    clearing.value = false;
  }
}

// 删除单条已上传字体（仅删临时文件与内存记录，不影响字体库）
async function removeUpload(path) {
  try {
    await apiModule.del(props.api, '/missing/uploads/remove', { path });
    uploads.value = uploads.value.filter(u => u.path !== path);
    emit('notify', '已移除该字体', 'success');
  } catch (e) {
    emit('notify', e.message || '移除失败');
  }
}

function toggleExpand(side) {
  expanded.value[side] = !expanded.value[side];
}

function shownItems(side) {
  const list = summary.value[side] || [];
  return expanded.value[side] ? list : list.slice(0, PREVIEW_N)
}

onMounted$2(() => {
  loadSummary();
  loadUploads();
  loadMappings();
  startPolling();
});
// keep-alive 缓存场景：切回时恢复轮询并重拉数据（Q1 修复；Q14 后切 Tab
// 不再由 Page 广播刷新键，各视图自查自刷）
onActivated$2(() => {
  loadSummary();
  loadUploads();
  loadMappings();
  startPolling();
});
// 切走（进入 keep-alive 缓存）时停止轮询，避免后台不可见视图持续打接口（Q1 修复）
onDeactivated(() => {
  stopPolling();
});
onUnmounted(() => stopPolling());

let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    loadSummary();
    loadUploads();
  }, 30000);
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_card_title = _resolveComponent$2("v-card-title");
  const _component_v_alert = _resolveComponent$2("v-alert");
  const _component_v_chip = _resolveComponent$2("v-chip");
  const _component_v_select = _resolveComponent$2("v-select");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_card_text = _resolveComponent$2("v-card-text");
  const _component_v_card = _resolveComponent$2("v-card");
  const _component_v_divider = _resolveComponent$2("v-divider");
  const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$2("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$2("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$2("v-list-item");
  const _component_v_list = _resolveComponent$2("v-list");
  const _component_v_col = _resolveComponent$2("v-col");
  const _component_v_row = _resolveComponent$2("v-row");
  const _component_v_spacer = _resolveComponent$2("v-spacer");
  const _component_v_card_actions = _resolveComponent$2("v-card-actions");
  const _component_v_dialog = _resolveComponent$2("v-dialog");

  return (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
    _createVNode$2(_component_v_card, { class: "zt-card-bg mb-4" }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_icon, {
              start: "",
              size: "18"
            }, {
              default: _withCtx$2(() => [...(_cache[7] || (_cache[7] = [
                _createTextVNode$2("mdi-alert-circle-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[8] || (_cache[8] = _createTextVNode$2(" 缺失字体统一管理 ", -1))
          ]),
          _: 1
        }),
        _createVNode$2(_component_v_card_text, { class: "pt-0" }, {
          default: _withCtx$2(() => [
            _createElementVNode$2("div", _hoisted_2$2, [
              _createElementVNode$2("span", _hoisted_3$2, [
                _createVNode$2(_component_v_icon, {
                  size: 16,
                  color: summary.value.hb_ok ? 'success' : 'error',
                  class: "mr-1"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(summary.value.hb_ok ? 'mdi-check-circle' : 'mdi-close-circle'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]),
                _createTextVNode$2(" 子集化引擎：" + _toDisplayString$2(summary.value.hb_ok ? 'HarfBuzz' : '未就绪'), 1)
              ]),
              _createElementVNode$2("span", _hoisted_4$2, [
                _createVNode$2(_component_v_icon, {
                  size: 16,
                  color: summary.value.index_faces ? 'success' : 'warning',
                  class: "mr-1"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(summary.value.index_faces ? 'mdi-format-font' : 'mdi-alert'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]),
                _createTextVNode$2(" 字体索引：" + _toDisplayString$2(summary.value.index_faces || 0) + " faces ", 1)
              ]),
              _createElementVNode$2("span", _hoisted_5$2, [
                _createVNode$2(_component_v_icon, {
                  size: 16,
                  color: summary.value.lib_dir ? 'success' : 'warning',
                  class: "mr-1"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(summary.value.lib_dir ? 'mdi-folder-check' : 'mdi-folder-alert'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]),
                _createTextVNode$2(" 字体库：" + _toDisplayString$2(summary.value.lib_dir || '未配置'), 1)
              ]),
              _createElementVNode$2("span", null, [
                _createVNode$2(_component_v_icon, {
                  size: 16,
                  class: "mr-1"
                }, {
                  default: _withCtx$2(() => [...(_cache[9] || (_cache[9] = [
                    _createTextVNode$2("mdi-tray-arrow-up", -1)
                  ]))]),
                  _: 1
                }),
                _createTextVNode$2(" 已上传待归类：" + _toDisplayString$2(uploads.value.length) + " 个 ", 1)
              ])
            ]),
            (uploads.value.length)
              ? (_openBlock$2(), _createBlock$2(_component_v_alert, {
                  key: 0,
                  type: "info",
                  density: "compact",
                  class: "mb-3"
                }, {
                  default: _withCtx$2(() => [...(_cache[10] || (_cache[10] = [
                    _createTextVNode$2(" 上传即校验：字体名/别名必须命中缺失目标，且至少覆盖一个缺失字符；点击已上传字体可「改派」目标。 归类时统一归档并自动重检受影响字幕。 ", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode$2("", true),
            (uploads.value.length)
              ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_6$2, [
                  (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(uploads.value, (u) => {
                    return (_openBlock$2(), _createBlock$2(_component_v_chip, {
                      key: u.path,
                      size: "small",
                      variant: "tonal",
                      color: "primary",
                      class: "mr-2 mb-2 zt-upload-chip",
                      close: "",
                      title: `${u.file_name} → ${u.matched || '?'}${u.covered_chars ? '（覆盖 ' + u.covered_chars + '）' : ''}；点击改派`,
                      onClick: $event => (openRemap(u)),
                      "onClick:close": $event => (removeUpload(u.path))
                    }, {
                      default: _withCtx$2(() => [
                        _createTextVNode$2(_toDisplayString$2(u.file_name) + " ", 1),
                        (u.matched)
                          ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_7$2, "→ " + _toDisplayString$2(u.matched), 1))
                          : _createCommentVNode$2("", true)
                      ]),
                      _: 2
                    }, 1032, ["title", "onClick", "onClick:close"]))
                  }), 128))
                ]))
              : _createCommentVNode$2("", true),
            _createElementVNode$2("div", _hoisted_8$2, [
              _createVNode$2(_component_v_select, {
                modelValue: targetHint.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((targetHint).value = $event)),
                items: targetOptions.value,
                "item-title": "title",
                "item-value": "name",
                label: "目标缺失字体（留空=自动匹配）",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                clearable: !!targetHint.value,
                "no-data-text": "暂无可选的缺失字体",
                class: "zt-target-select"
              }, null, 8, ["modelValue", "items", "clearable"]),
              _createVNode$2(_component_v_btn, {
                color: "primary",
                variant: "tonal",
                disabled: !__props.enabled || uploading.value || classifying.value,
                loading: uploading.value,
                title: "上传字体（支持 ttf/otf/ttc/otc/woff/woff2 与 .zip/.7z/.rar 压缩包）",
                onClick: _cache[1] || (_cache[1] = $event => (uploadRef.value?.click()))
              }, {
                default: _withCtx$2(() => [
                  _createVNode$2(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$2(() => [...(_cache[11] || (_cache[11] = [
                      _createTextVNode$2("mdi-upload", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[12] || (_cache[12] = _createTextVNode$2(" 上传字体 ", -1))
                ]),
                _: 1
              }, 8, ["disabled", "loading"]),
              _createElementVNode$2("input", {
                ref_key: "uploadRef",
                ref: uploadRef,
                type: "file",
                accept: _unref(uploadAcceptFor)(_unref(DESKTOP_ACCEPT_FONT)),
                multiple: "",
                style: {"display":"none"},
                onChange: handleUpload
              }, null, 40, _hoisted_9$2),
              _createVNode$2(_component_v_btn, {
                color: "success",
                variant: "tonal",
                disabled: !__props.enabled || classifying.value || !uploads.value.length,
                loading: classifying.value,
                title: "全部上传字体入库 + 自动增量更新索引（运行中不可重复点击）",
                onClick: classify
              }, {
                default: _withCtx$2(() => [
                  _createVNode$2(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$2(() => [...(_cache[13] || (_cache[13] = [
                      _createTextVNode$2("mdi-database-import", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[14] || (_cache[14] = _createTextVNode$2(" 归类 ", -1))
                ]),
                _: 1
              }, 8, ["disabled", "loading"]),
              _createVNode$2(_component_v_btn, {
                variant: "tonal",
                color: "error",
                disabled: !__props.enabled || clearing.value || !uploads.value.length,
                loading: clearing.value,
                title: "清除已上传的字体",
                onClick: clearUploads
              }, {
                default: _withCtx$2(() => [
                  _createVNode$2(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$2(() => [...(_cache[15] || (_cache[15] = [
                      _createTextVNode$2("mdi-trash-can-outline", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[16] || (_cache[16] = _createTextVNode$2(" 清除全部 ", -1))
                ]),
                _: 1
              }, 8, ["disabled", "loading"])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$2(_component_v_row, {
      "no-gutters": "",
      class: "zt-missing-row"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, { class: "zt-card-bg zt-missing-col" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, {
                      start: "",
                      size: "18",
                      color: "warning"
                    }, {
                      default: _withCtx$2(() => [...(_cache[17] || (_cache[17] = [
                        _createTextVNode$2("mdi-file-document-alert-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$2(" 检查缺失（" + _toDisplayString$2(summary.value.check?.length ?? 0) + "） ", 1)
                  ]),
                  _: 1
                }),
                _createVNode$2(_component_v_divider),
                (loading.value)
                  ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$2("", true),
                (!loading.value && !(summary.value.check || []).length)
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_10$2, " 检查页无缺失字体 "))
                  : (_openBlock$2(), _createElementBlock$2("div", _hoisted_11$1, [
                      _createVNode$2(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$2(() => [
                          (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(shownItems('check'), (f) => {
                            return (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                              key: f.name,
                              lines: "two"
                            }, {
                              prepend: _withCtx$2(() => [
                                _createVNode$2(_component_v_icon, {
                                  color: "warning",
                                  size: "18"
                                }, {
                                  default: _withCtx$2(() => [...(_cache[18] || (_cache[18] = [
                                    _createTextVNode$2("mdi-alert", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              default: _withCtx$2(() => [
                                _createVNode$2(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(f.name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(f.count) + " 个字幕缺失 ", 1),
                                    (f.chars)
                                      ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 0 }, [
                                          _createTextVNode$2(" · 缺 " + _toDisplayString$2(f.codepoints_count || 0) + " 字符：", 1),
                                          _createElementVNode$2("span", _hoisted_12$1, _toDisplayString$2(f.chars), 1)
                                        ], 64))
                                      : (f.glyph)
                                        ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 1 }, [
                                            _createTextVNode$2(" · 字符级缺失")
                                          ], 64))
                                        : _createCommentVNode$2("", true)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1024))
                          }), 128))
                        ]),
                        _: 1
                      }),
                      ((summary.value.check || []).length > PREVIEW_N)
                        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_13$1, [
                            _createVNode$2(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              onClick: _cache[2] || (_cache[2] = $event => (toggleExpand('check')))
                            }, {
                              default: _withCtx$2(() => [
                                _createTextVNode$2(_toDisplayString$2(expanded.value.check ? '收起' : `展开全部（${summary.value.check.length}）`), 1)
                              ]),
                              _: 1
                            })
                          ]))
                        : _createCommentVNode$2("", true)
                    ]))
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode$2(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, { class: "zt-card-bg zt-missing-col" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, {
                      start: "",
                      size: "18",
                      color: "error"
                    }, {
                      default: _withCtx$2(() => [...(_cache[19] || (_cache[19] = [
                        _createTextVNode$2("mdi-subtitles-alert-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$2(" 子集化缺失（" + _toDisplayString$2(summary.value.subset?.length ?? 0) + "） ", 1)
                  ]),
                  _: 1
                }),
                _createVNode$2(_component_v_divider),
                (loading.value)
                  ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$2("", true),
                (!loading.value && !(summary.value.subset || []).length)
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_14$1, " 子集化无缺失字体 "))
                  : (_openBlock$2(), _createElementBlock$2("div", _hoisted_15$1, [
                      _createVNode$2(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$2(() => [
                          (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(shownItems('subset'), (f) => {
                            return (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                              key: f.name,
                              lines: "two"
                            }, {
                              prepend: _withCtx$2(() => [
                                _createVNode$2(_component_v_icon, {
                                  color: "error",
                                  size: "18"
                                }, {
                                  default: _withCtx$2(() => [...(_cache[20] || (_cache[20] = [
                                    _createTextVNode$2("mdi-close-octagon-outline", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              default: _withCtx$2(() => [
                                _createVNode$2(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(f.name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(f.count) + " 个字幕子集化时缺此字体", 1)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1024))
                          }), 128))
                        ]),
                        _: 1
                      }),
                      ((summary.value.subset || []).length > PREVIEW_N)
                        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_16$1, [
                            _createVNode$2(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              onClick: _cache[3] || (_cache[3] = $event => (toggleExpand('subset')))
                            }, {
                              default: _withCtx$2(() => [
                                _createTextVNode$2(_toDisplayString$2(expanded.value.subset ? '收起' : `展开全部（${summary.value.subset.length}）`), 1)
                              ]),
                              _: 1
                            })
                          ]))
                        : _createCommentVNode$2("", true)
                    ]))
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (mappings.value.length)
      ? (_openBlock$2(), _createBlock$2(_component_v_card, {
          key: 0,
          class: "zt-card-bg mt-4"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$2(() => [...(_cache[21] || (_cache[21] = [
                    _createTextVNode$2("mdi-link-variant", -1)
                  ]))]),
                  _: 1
                }),
                _createTextVNode$2(" 人工映射审计（" + _toDisplayString$2(mappings.value.length) + "） ", 1)
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_text, { class: "pt-0" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_list, {
                  density: "compact",
                  class: "pa-0"
                }, {
                  default: _withCtx$2(() => [
                    (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(mappings.value, (m) => {
                      return (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                        key: m.id
                      }, {
                        append: _withCtx$2(() => [
                          _createVNode$2(_component_v_btn, {
                            icon: "mdi-trash-can-outline",
                            size: "x-small",
                            variant: "text",
                            color: "error",
                            title: "删除该映射记录",
                            onClick: $event => (removeMapping(m))
                          }, null, 8, ["onClick"])
                        ]),
                        default: _withCtx$2(() => [
                          _createVNode$2(_component_v_list_item_title, { class: "zt-font-meta" }, {
                            default: _withCtx$2(() => [
                              _createTextVNode$2(_toDisplayString$2(m.source_name) + " → " + _toDisplayString$2(m.target_name), 1)
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                            default: _withCtx$2(() => [
                              _createTextVNode$2(_toDisplayString$2(m.note || '人工映射') + " · " + _toDisplayString$2(m.created_at), 1)
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
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
      : _createCommentVNode$2("", true),
    _cache[26] || (_cache[26] = _createElementVNode$2("div", { class: "zt-tip mt-3 text-body-2" }, " 提示：上传字体（支持 .zip/.7z/.rar）→ 校验通过后点「归类」入库 → 自动重检受影响字幕 → 回到「子集化」页重新运行。 ", -1)),
    _createVNode$2(_component_v_dialog, {
      modelValue: remapDialog.value,
      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((remapDialog).value = $event)),
      "max-width": "460"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$2(() => [...(_cache[22] || (_cache[22] = [
                    _createTextVNode$2("mdi-link-variant", -1)
                  ]))]),
                  _: 1
                }),
                _cache[23] || (_cache[23] = _createTextVNode$2(" 改派缺失目标 ", -1))
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_text, null, {
              default: _withCtx$2(() => [
                _createElementVNode$2("div", _hoisted_17$1, [
                  _createTextVNode$2(" 字体：" + _toDisplayString$2(remapItem.value?.file_name) + " ", 1),
                  (remapItem.value?.name)
                    ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_18$1, "（内部名：" + _toDisplayString$2(remapItem.value.name) + "）", 1))
                    : _createCommentVNode$2("", true)
                ]),
                (remapItem.value?.covered_chars)
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_19$1, " 当前覆盖字符：" + _toDisplayString$2(remapItem.value.covered_chars), 1))
                  : _createCommentVNode$2("", true),
                _createVNode$2(_component_v_select, {
                  modelValue: remapTarget.value,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((remapTarget).value = $event)),
                  items: targetOptions.value,
                  "item-title": "title",
                  "item-value": "name",
                  label: "缺失目标字体",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  "no-data-text": "暂无可选的缺失字体"
                }, null, 8, ["modelValue", "items"])
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_actions, null, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_spacer),
                _createVNode$2(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[5] || (_cache[5] = $event => (remapDialog.value = false))
                }, {
                  default: _withCtx$2(() => [...(_cache[24] || (_cache[24] = [
                    _createTextVNode$2("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$2(_component_v_btn, {
                  color: "primary",
                  variant: "tonal",
                  loading: remapping.value,
                  disabled: !remapTarget.value,
                  onClick: submitRemap
                }, {
                  default: _withCtx$2(() => [...(_cache[25] || (_cache[25] = [
                    _createTextVNode$2(" 确认改派 ", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading", "disabled"])
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
const MissingFonts = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-45072c83"]]);

const {createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,toDisplayString:_toDisplayString$1,createCommentVNode:_createCommentVNode$1,createBlock:_createBlock$1,normalizeClass:_normalizeClass,normalizeStyle:_normalizeStyle} = await importShared('vue');


const _hoisted_1$1 = { class: "zt-archives-page" };
const _hoisted_2$1 = { class: "zt-page-title" };
const _hoisted_3$1 = {
  key: 0,
  class: "zt-locations"
};
const _hoisted_4$1 = { class: "zt-loc-title" };
const _hoisted_5$1 = { class: "zt-loc-label" };
const _hoisted_6$1 = {
  key: 0,
  class: "zt-loc-path"
};
const _hoisted_7$1 = {
  key: 1,
  class: "zt-loc-hint"
};
const _hoisted_8$1 = { class: "zt-toolbar" };
const _hoisted_9$1 = { class: "zt-count" };
const _hoisted_10$1 = {
  key: 0,
  class: "zt-empty"
};
const _hoisted_11 = {
  key: 1,
  class: "zt-empty"
};
const _hoisted_12 = {
  key: 2,
  class: "zt-list"
};
const _hoisted_13 = { class: "zt-row-main" };
const _hoisted_14 = { class: "zt-row-text" };
const _hoisted_15 = { class: "zt-row-name" };
const _hoisted_16 = { class: "zt-row-meta" };
const _hoisted_17 = { class: "zt-row-actions" };
const _hoisted_18 = {
  key: 3,
  class: "zt-cards"
};
const _hoisted_19 = { class: "zt-card-head" };
const _hoisted_20 = { class: "zt-card-title" };
const _hoisted_21 = { class: "zt-row-name" };
const _hoisted_22 = { class: "zt-row-meta" };
const _hoisted_23 = { class: "zt-card-meta" };
const _hoisted_24 = { class: "zt-card-actions" };
const _hoisted_25 = { class: "zt-hint move-name" };
const _hoisted_26 = { class: "zt-hint entries-name" };
const _hoisted_27 = { class: "zt-hint entries-path" };
const _hoisted_28 = {
  key: 0,
  class: "entries-loading"
};
const _hoisted_29 = {
  key: 1,
  class: "entries-error"
};
const _hoisted_30 = { class: "entries-summary" };
const _hoisted_31 = { key: 0 };
const _hoisted_32 = { key: 1 };
const _hoisted_33 = {
  key: 0,
  class: "entries-empty"
};
const _hoisted_34 = {
  key: 1,
  class: "entries-list"
};
const _hoisted_35 = { class: "entry-name" };
const _hoisted_36 = { class: "entry-size" };
const _hoisted_37 = {
  key: 2,
  class: "tree-pager"
};

const {computed: computed$1,onActivated: onActivated$1,onMounted: onMounted$1,ref: ref$1} = await importShared('vue');

const TREE_PAGE_SIZE = 50;

const _sfc_main$1 = {
  __name: 'Archives',
  props: {
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
},
  emits: ['notify'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const items = ref$1([]);
const loading = ref$1(false);
const busy = ref$1('');
const filter = ref$1('all');
const viewMode = ref$1('list');
const configDirs = ref$1({ input: '', ass: '', subset: '' });
const locations = ref$1([]);
const entriesDialog = ref$1(false);
const entriesItem = ref$1(null);
const entries = ref$1([]);
const entriesLoading = ref$1(false);
const entriesError = ref$1('');
const entriesMeta = ref$1({ total: 0, truncated: false, tool: '' });
const treePage = ref$1(1);
const treeRows = computed$1(() => {
  const root = { children: new Map() };
  const ensureDir = (node, name) => {
    if (!node.children.has(name)) {
      node.children.set(name, { name, isDir: true, size: 0, children: new Map() });
    }
    return node.children.get(name)
  };
  for (const entry of entries.value) {
    const raw = String(entry.name || '').replace(/\\/g, '/');
    const parts = raw.split('/').filter(Boolean);
    if (!parts.length) continue
    let node = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      node = ensureDir(node, parts[i]);
    }
    const leaf = parts[parts.length - 1];
    if (entry.is_dir || raw.endsWith('/')) {
      ensureDir(node, leaf);
    } else if (node.children.has(leaf) && node.children.get(leaf).isDir) {
      node.children.get(leaf).size = Number(entry.size) || 0;
    } else {
      node.children.set(leaf, {
        name: leaf,
        isDir: false,
        size: Number(entry.size) || 0,
        children: new Map(),
      });
    }
  }
  const sortMap = (map) => [...map.values()]
    .sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1))
    .map((item) => ({ ...item, children: sortMap(item.children) }));
  const rows = [];
  const walk = (nodes, depth, parentPath) => {
    for (const node of nodes) {
      const path = parentPath ? parentPath + '/' + node.name : node.name;
      rows.push({ ...node, path, depth });
      if (node.isDir && node.children.length) walk(node.children, depth + 1, path);
    }
  };
  walk(sortMap(root.children), 0, '');
  return rows
});
const treePageCount = computed$1(() => Math.max(1, Math.ceil(treeRows.value.length / TREE_PAGE_SIZE)));
const treePageRows = computed$1(() => (
  treeRows.value.slice((treePage.value - 1) * TREE_PAGE_SIZE, treePage.value * TREE_PAGE_SIZE)
));
const moveDialog = ref$1(false);
const moveItem = ref$1(null);
const moveTarget = ref$1('');
const moveBusy = ref$1(false);
const FILTERS = [
  { title: '全部', value: 'all' },
  { title: '已处理', value: '已处理' },
  { title: '错误', value: '错误' },
  { title: '未分类（旧版）', value: '未分类' },
];
const filtered = computed$1(() => (
  filter.value === 'all'
    ? items.value
    : items.value.filter((item) => (item.category || '未分类') === filter.value)
));
const totalSize = computed$1(() => (
  filtered.value.reduce((sum, item) => sum + (Number(item.size) || 0), 0)
));
const moveTargets = computed$1(() => {
  const candidates = [
    { title: '字体监控目录', value: 'input', dir: configDirs.value.input },
    { title: 'ASS 字幕检查目录', value: 'ass', dir: configDirs.value.ass },
    { title: 'ASS 自动子集化目录', value: 'subset', dir: configDirs.value.subset },
  ];
  return candidates.filter((item) => item.dir).map(({ title, value }) => ({ title, value }))
});

function notify(message, type = 'error') {
  emit('notify', message, type);
}
function fmtSize(value) {
  const num = Number(value) || 0;
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  if (num < 1024 * 1024 * 1024) return (num / 1024 / 1024).toFixed(1) + ' MB'
  return (num / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}
function fmtTime(ts) {
  try {
    return new Date((Number(ts) || 0) * 1000).toLocaleString()
  } catch (e) {
    return ''
  }
}
function categoryColor(category) {
  if (category === '已处理') return 'success'
  if (category === '错误') return 'error'
  return 'grey'
}
function categoryIcon(category) {
  if (category === '已处理') return 'mdi-check-circle-outline'
  if (category === '错误') return 'mdi-alert-circle-outline'
  return 'mdi-archive-outline'
}

async function loadConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await apiModule.get(props.api, '/config');
    if (data && typeof data === 'object') {
      configDirs.value = {
        input: data.input_dir || '',
        ass: data.ass_dir || '',
        subset: data.subset_dir || '',
      };
    }
  } catch (e) {
    // 目录未取到不影响列表；错误项会隐藏「移到指定目录」
  }
}

async function load() {
  if (typeof props.api?.get !== 'function') return
  loading.value = true;
  try {
    const data = await apiModule.get(props.api, '/archives/processed');
    items.value = Array.isArray(data?.items) ? data.items : [];
    locations.value = Array.isArray(data?.locations) ? data.locations : [];
  } catch (e) {
    notify(e.message || '读取已处理压缩包失败');
  } finally {
    loading.value = false;
  }
}

async function removeItem(item) {
  if (!item?.path) return
  if (!window.confirm('删除压缩包？\n' + item.name + '\n\n（只删「已处理压缩包」里的副本，不影响原目录）')) return
  busy.value = item.path;
  try {
    const res = await apiModule.post(props.api, '/archives/processed/remove', { paths: [item.path] });
    notify(res.message || '已删除压缩包', 'success');
    await load();
  } catch (e) {
    notify(e.message || '删除失败');
  } finally {
    busy.value = '';
  }
}

async function restoreItem(item) {
  if (!item?.path) return
  const warn = item.category === '错误'
    ? '\n\n注意：它原本就在错误目录，移回后可能再次被移到「错误/」；建议先改放到正确目录。'
    : '';
  if (!window.confirm('把压缩包移回原目录？\n' + item.name + warn + '\n\n只移动压缩包，不会撤销已归档的字体/已检查的字幕。')) return
  busy.value = item.path;
  try {
    const res = await apiModule.post(props.api, '/archives/processed/restore', { path: item.path });
    notify(res.message || '已恢复压缩包', 'success');
    await load();
  } catch (e) {
    notify(e.message || '恢复失败');
  } finally {
    busy.value = '';
  }
}

async function clearCurrent() {
  const scope = filter.value === 'all' ? '' : filter.value;
  if (!filtered.value.length) return
  if (!window.confirm('清空「' + (scope || '全部') + '」已处理压缩包？共 ' + filtered.value.length + ' 个，不可恢复。\n\n（只删副本，不影响原目录）')) return
  busy.value = 'clear';
  try {
    const res = await apiModule.post(props.api, '/archives/processed/clear', { category: scope });
    notify(res.message || '已清空', 'success');
    await load();
  } catch (e) {
    notify(e.message || '清空失败');
  } finally {
    busy.value = '';
  }
}

async function copyPath(path) {
  if (!path) return
  try {
    await navigator.clipboard.writeText(path);
    notify('已复制路径', 'success');
  } catch (e) {
    notify('复制失败，请手动选择路径');
  }
}

async function viewItem(item) {
  if (!item?.path) return
  entriesItem.value = item;
  entries.value = [];
  entriesError.value = '';
  entriesMeta.value = { total: 0, truncated: false, tool: '' };
  entriesDialog.value = true;
  entriesLoading.value = true;
  try {
    const data = await apiModule.get(props.api, '/archives/processed/entries', { path: item.path });
    entries.value = Array.isArray(data?.entries) ? data.entries : [];
    treePage.value = 1;
    entriesMeta.value = {
      total: Number(data?.total) || entries.value.length,
      truncated: !!data?.truncated,
      tool: data?.tool || '',
    };
  } catch (e) {
    entriesError.value = e.message || '读取压缩包内容失败';
  } finally {
    entriesLoading.value = false;
  }
}

function openMove(item) {
  if (!item?.path) return
  moveItem.value = item;
  moveTarget.value = moveTargets.value[0]?.value || '';
  moveDialog.value = true;
}

async function doMove() {
  if (!moveItem.value?.path || !moveTarget.value) return
  moveBusy.value = true;
  try {
    const res = await apiModule.post(props.api, '/archives/processed/move', {
      path: moveItem.value.path,
      target: moveTarget.value,
    });
    notify(res.message || '已移动压缩包', 'success');
    moveDialog.value = false;
    await load();
  } catch (e) {
    notify(e.message || '移动失败');
  } finally {
    moveBusy.value = false;
  }
}

onMounted$1(() => {
  load();
  loadConfig();
});
onActivated$1(() => {
  load();
  loadConfig();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_select = _resolveComponent$1("v-select");
  const _component_v_btn_toggle = _resolveComponent$1("v-btn-toggle");
  const _component_v_spacer = _resolveComponent$1("v-spacer");
  const _component_v_divider = _resolveComponent$1("v-divider");
  const _component_v_progress_circular = _resolveComponent$1("v-progress-circular");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_card_title = _resolveComponent$1("v-card-title");
  const _component_v_card_actions = _resolveComponent$1("v-card-actions");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createElementVNode$1("div", _hoisted_2$1, [
      _createVNode$1(_component_v_icon, {
        start: "",
        size: "22"
      }, {
        default: _withCtx$1(() => [...(_cache[9] || (_cache[9] = [
          _createTextVNode$1("mdi-archive-eye-outline", -1)
        ]))]),
        _: 1
      }),
      _cache[10] || (_cache[10] = _createTextVNode$1(" 已处理压缩包 ", -1))
    ]),
    _cache[47] || (_cache[47] = _createElementVNode$1("div", { class: "zt-page-desc" }, [
      _createTextVNode$1(" 这里管理插件清理/留档的压缩包副本："),
      _createElementVNode$1("b", null, "已处理/"),
      _createTextVNode$1(" 是成功处理后的副本， "),
      _createElementVNode$1("b", null, "错误/"),
      _createTextVNode$1(" 是放错目录、不支持格式或包内没有字体/字幕的留档。 「移回原目录」只会把压缩包移回它原来所在的目录并重新监控处理， "),
      _createElementVNode$1("b", null, "不会撤销"),
      _createTextVNode$1("已经归档的字体/已检查的字幕；删除只影响副本，不碰原目录文件。 ")
    ], -1)),
    (locations.value.length)
      ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_3$1, [
          _createElementVNode$1("div", _hoisted_4$1, [
            _createVNode$1(_component_v_icon, { size: "15" }, {
              default: _withCtx$1(() => [...(_cache[11] || (_cache[11] = [
                _createTextVNode$1("mdi-folder-marker-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[12] || (_cache[12] = _createTextVNode$1(" 当前存放位置 ", -1))
          ]),
          (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(locations.value, (loc) => {
            return (_openBlock$1(), _createElementBlock$1("div", {
              key: loc.label + loc.path,
              class: "zt-loc"
            }, [
              _createElementVNode$1("span", _hoisted_5$1, _toDisplayString$1(loc.label), 1),
              (loc.path)
                ? (_openBlock$1(), _createElementBlock$1("code", _hoisted_6$1, _toDisplayString$1(loc.path), 1))
                : (_openBlock$1(), _createElementBlock$1("span", _hoisted_7$1, _toDisplayString$1(loc.hint), 1)),
              (loc.path)
                ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
                    key: 2,
                    icon: "",
                    size: "x-small",
                    variant: "text",
                    title: "复制路径",
                    onClick: $event => (copyPath(loc.path))
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, { size: "14" }, {
                        default: _withCtx$1(() => [...(_cache[13] || (_cache[13] = [
                          _createTextVNode$1("mdi-content-copy", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["onClick"]))
                : _createCommentVNode$1("", true)
            ]))
          }), 128))
        ]))
      : _createCommentVNode$1("", true),
    _createVNode$1(_component_v_card, { class: "zt-card-bg mt-4" }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_text, null, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", _hoisted_8$1, [
              _createVNode$1(_component_v_select, {
                modelValue: filter.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((filter).value = $event)),
                items: FILTERS,
                "item-title": "title",
                "item-value": "value",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                class: "zt-filter"
              }, null, 8, ["modelValue"]),
              _createVNode$1(_component_v_btn, {
                size: "small",
                variant: "tonal",
                loading: loading.value,
                onClick: load
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_icon, {
                    start: "",
                    size: "16"
                  }, {
                    default: _withCtx$1(() => [...(_cache[14] || (_cache[14] = [
                      _createTextVNode$1("mdi-refresh", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[15] || (_cache[15] = _createTextVNode$1("刷新 ", -1))
                ]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$1(_component_v_btn_toggle, {
                modelValue: viewMode.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((viewMode).value = $event)),
                mandatory: "",
                density: "compact",
                variant: "outlined",
                divided: "",
                color: "primary",
                class: "zt-view-toggle"
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_btn, {
                    value: "list",
                    size: "small",
                    title: "列表"
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, { size: "16" }, {
                        default: _withCtx$1(() => [...(_cache[16] || (_cache[16] = [
                          _createTextVNode$1("mdi-view-list-outline", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode$1(_component_v_btn, {
                    value: "card",
                    size: "small",
                    title: "卡片"
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_v_icon, { size: "16" }, {
                        default: _withCtx$1(() => [...(_cache[17] || (_cache[17] = [
                          _createTextVNode$1("mdi-view-grid-outline", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _createVNode$1(_component_v_spacer),
              _createElementVNode$1("span", _hoisted_9$1, _toDisplayString$1(filtered.value.length) + " 个 · " + _toDisplayString$1(fmtSize(totalSize.value)), 1),
              _createVNode$1(_component_v_btn, {
                size: "small",
                color: "error",
                variant: "text",
                disabled: !filtered.value.length,
                loading: busy.value === 'clear',
                onClick: clearCurrent
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_icon, {
                    start: "",
                    size: "16"
                  }, {
                    default: _withCtx$1(() => [...(_cache[18] || (_cache[18] = [
                      _createTextVNode$1("mdi-delete-sweep", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[19] || (_cache[19] = _createTextVNode$1("清空当前分类 ", -1))
                ]),
                _: 1
              }, 8, ["disabled", "loading"])
            ]),
            _createVNode$1(_component_v_divider, { class: "my-3" }),
            (loading.value && !items.value.length)
              ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_10$1, [
                  _createVNode$1(_component_v_progress_circular, {
                    indeterminate: "",
                    color: "primary",
                    size: "28"
                  }),
                  _cache[20] || (_cache[20] = _createElementVNode$1("div", { class: "mt-2" }, "读取中…", -1))
                ]))
              : (!filtered.value.length)
                ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_11, [
                    _createVNode$1(_component_v_icon, {
                      size: "46",
                      class: "zt-empty-icon"
                    }, {
                      default: _withCtx$1(() => [...(_cache[21] || (_cache[21] = [
                        _createTextVNode$1("mdi-archive-off-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createElementVNode$1("div", null, _toDisplayString$1(filter.value === 'all' ? '暂无已处理压缩包' : '该分类暂无压缩包'), 1),
                    _cache[22] || (_cache[22] = _createElementVNode$1("div", { class: "zt-empty-hint" }, "插件成功清理或移入错误目录后会显示在这里", -1))
                  ]))
                : (viewMode.value === 'list')
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_12, [
                      (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(filtered.value, (item) => {
                        return (_openBlock$1(), _createElementBlock$1("div", {
                          key: item.path,
                          class: "zt-row"
                        }, [
                          _createElementVNode$1("div", _hoisted_13, [
                            _createVNode$1(_component_v_icon, {
                              color: categoryColor(item.category),
                              size: "22",
                              class: "mr-3"
                            }, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString$1(categoryIcon(item.category)), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"]),
                            _createElementVNode$1("div", _hoisted_14, [
                              _createElementVNode$1("div", _hoisted_15, _toDisplayString$1(item.name), 1),
                              _createElementVNode$1("div", _hoisted_16, [
                                _createElementVNode$1("span", {
                                  class: _normalizeClass(["zt-cat", 'is-' + categoryColor(item.category)])
                                }, _toDisplayString$1(item.category || '未分类'), 3),
                                _createElementVNode$1("span", null, _toDisplayString$1(item.source), 1),
                                _createElementVNode$1("span", null, _toDisplayString$1(fmtSize(item.size)), 1),
                                _createElementVNode$1("span", null, _toDisplayString$1(fmtTime(item.mtime)), 1)
                              ])
                            ])
                          ]),
                          _createElementVNode$1("div", _hoisted_17, [
                            _createVNode$1(_component_v_btn, {
                              size: "x-small",
                              variant: "text",
                              onClick: $event => (viewItem(item))
                            }, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  start: "",
                                  size: "14"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[23] || (_cache[23] = [
                                    _createTextVNode$1("mdi-file-eye-outline", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[24] || (_cache[24] = _createTextVNode$1("查看 ", -1))
                              ]),
                              _: 1
                            }, 8, ["onClick"]),
                            _createVNode$1(_component_v_btn, {
                              size: "x-small",
                              variant: "tonal",
                              disabled: !item.can_restore,
                              loading: busy.value === item.path,
                              title: item.can_restore ? '移回原目录（不会撤销已处理内容）' : '自定义目录缺少原目录记录，无法移回',
                              onClick: $event => (restoreItem(item))
                            }, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  start: "",
                                  size: "14"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[25] || (_cache[25] = [
                                    _createTextVNode$1("mdi-restore", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[26] || (_cache[26] = _createTextVNode$1("移回原目录 ", -1))
                              ]),
                              _: 1
                            }, 8, ["disabled", "loading", "title", "onClick"]),
                            (item.category === '错误' && moveTargets.value.length)
                              ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
                                  key: 0,
                                  size: "x-small",
                                  variant: "tonal",
                                  loading: busy.value === item.path,
                                  onClick: $event => (openMove(item))
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_v_icon, {
                                      start: "",
                                      size: "14"
                                    }, {
                                      default: _withCtx$1(() => [...(_cache[27] || (_cache[27] = [
                                        _createTextVNode$1("mdi-folder-move-outline", -1)
                                      ]))]),
                                      _: 1
                                    }),
                                    _cache[28] || (_cache[28] = _createTextVNode$1("移到… ", -1))
                                  ]),
                                  _: 1
                                }, 8, ["loading", "onClick"]))
                              : _createCommentVNode$1("", true),
                            _createVNode$1(_component_v_btn, {
                              size: "x-small",
                              variant: "text",
                              color: "error",
                              loading: busy.value === item.path,
                              onClick: $event => (removeItem(item))
                            }, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  start: "",
                                  size: "14"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[29] || (_cache[29] = [
                                    _createTextVNode$1("mdi-delete-outline", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[30] || (_cache[30] = _createTextVNode$1("删除 ", -1))
                              ]),
                              _: 1
                            }, 8, ["loading", "onClick"])
                          ])
                        ]))
                      }), 128))
                    ]))
                  : (_openBlock$1(), _createElementBlock$1("div", _hoisted_18, [
                      (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(filtered.value, (item) => {
                        return (_openBlock$1(), _createElementBlock$1("div", {
                          key: item.path,
                          class: "zt-card-item"
                        }, [
                          _createElementVNode$1("div", _hoisted_19, [
                            _createVNode$1(_component_v_icon, {
                              color: categoryColor(item.category),
                              size: "24"
                            }, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString$1(categoryIcon(item.category)), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"]),
                            _createElementVNode$1("div", _hoisted_20, [
                              _createElementVNode$1("div", _hoisted_21, _toDisplayString$1(item.name), 1),
                              _createElementVNode$1("div", _hoisted_22, [
                                _createElementVNode$1("span", {
                                  class: _normalizeClass(["zt-cat", 'is-' + categoryColor(item.category)])
                                }, _toDisplayString$1(item.category || '未分类'), 3),
                                _createElementVNode$1("span", null, _toDisplayString$1(item.source), 1)
                              ])
                            ])
                          ]),
                          _createElementVNode$1("div", _hoisted_23, [
                            _createElementVNode$1("span", null, _toDisplayString$1(fmtSize(item.size)), 1),
                            _createElementVNode$1("span", null, _toDisplayString$1(fmtTime(item.mtime)), 1)
                          ]),
                          _createElementVNode$1("div", _hoisted_24, [
                            _createVNode$1(_component_v_btn, {
                              size: "x-small",
                              variant: "text",
                              onClick: $event => (viewItem(item))
                            }, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  start: "",
                                  size: "14"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[31] || (_cache[31] = [
                                    _createTextVNode$1("mdi-file-eye-outline", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[32] || (_cache[32] = _createTextVNode$1("查看 ", -1))
                              ]),
                              _: 1
                            }, 8, ["onClick"]),
                            _createVNode$1(_component_v_spacer),
                            _createVNode$1(_component_v_btn, {
                              size: "x-small",
                              variant: "tonal",
                              disabled: !item.can_restore,
                              loading: busy.value === item.path,
                              onClick: $event => (restoreItem(item))
                            }, {
                              default: _withCtx$1(() => [...(_cache[33] || (_cache[33] = [
                                _createTextVNode$1("移回", -1)
                              ]))]),
                              _: 1
                            }, 8, ["disabled", "loading", "onClick"]),
                            (item.category === '错误' && moveTargets.value.length)
                              ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
                                  key: 0,
                                  size: "x-small",
                                  variant: "tonal",
                                  loading: busy.value === item.path,
                                  onClick: $event => (openMove(item))
                                }, {
                                  default: _withCtx$1(() => [...(_cache[34] || (_cache[34] = [
                                    _createTextVNode$1("移到…", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["loading", "onClick"]))
                              : _createCommentVNode$1("", true),
                            _createVNode$1(_component_v_btn, {
                              size: "x-small",
                              variant: "text",
                              color: "error",
                              loading: busy.value === item.path,
                              onClick: $event => (removeItem(item))
                            }, {
                              default: _withCtx$1(() => [...(_cache[35] || (_cache[35] = [
                                _createTextVNode$1("删除", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading", "onClick"])
                          ])
                        ]))
                      }), 128))
                    ]))
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_dialog, {
      modelValue: moveDialog.value,
      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((moveDialog).value = $event)),
      "max-width": "460px"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card_title, null, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_icon, {
                  start: "",
                  size: "20"
                }, {
                  default: _withCtx$1(() => [...(_cache[36] || (_cache[36] = [
                    _createTextVNode$1("mdi-folder-move-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[37] || (_cache[37] = _createTextVNode$1(" 移到指定目录 ", -1))
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_text, null, {
              default: _withCtx$1(() => [
                _createElementVNode$1("div", _hoisted_25, _toDisplayString$1(moveItem.value?.name), 1),
                _createVNode$1(_component_v_select, {
                  modelValue: moveTarget.value,
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((moveTarget).value = $event)),
                  items: moveTargets.value,
                  "item-title": "title",
                  "item-value": "value",
                  label: "目标监控目录",
                  density: "compact",
                  variant: "outlined",
                  class: "mt-3"
                }, null, 8, ["modelValue", "items"]),
                _cache[38] || (_cache[38] = _createElementVNode$1("div", { class: "zt-hint" }, " 移动后会清除已处理指纹并按新目录重新处理；如果目标目录类型与文件不匹配，会被移到「错误/」。 ", -1))
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_actions, null, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_spacer),
                _createVNode$1(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[3] || (_cache[3] = $event => (moveDialog.value = false))
                }, {
                  default: _withCtx$1(() => [...(_cache[39] || (_cache[39] = [
                    _createTextVNode$1("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$1(_component_v_btn, {
                  color: "primary",
                  variant: "tonal",
                  loading: moveBusy.value,
                  disabled: !moveTarget.value,
                  onClick: doMove
                }, {
                  default: _withCtx$1(() => [...(_cache[40] || (_cache[40] = [
                    _createTextVNode$1(" 移动 ", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading", "disabled"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$1(_component_v_dialog, {
      modelValue: entriesDialog.value,
      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((entriesDialog).value = $event)),
      "max-width": "760px",
      fullscreen: _ctx.$vuetify.display.smAndDown
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card_title, null, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_icon, {
                  start: "",
                  size: "20"
                }, {
                  default: _withCtx$1(() => [...(_cache[41] || (_cache[41] = [
                    _createTextVNode$1("mdi-archive-eye-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[42] || (_cache[42] = _createTextVNode$1(" 压缩包内容 ", -1))
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_text, null, {
              default: _withCtx$1(() => [
                _createElementVNode$1("div", _hoisted_26, _toDisplayString$1(entriesItem.value?.name), 1),
                _createElementVNode$1("div", _hoisted_27, _toDisplayString$1(entriesItem.value?.path), 1),
                (entriesLoading.value)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_28, [
                      _createVNode$1(_component_v_progress_circular, {
                        indeterminate: "",
                        color: "primary",
                        size: "28"
                      }),
                      _cache[43] || (_cache[43] = _createElementVNode$1("span", { class: "ml-2" }, "读取中…", -1))
                    ]))
                  : (entriesError.value)
                    ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_29, _toDisplayString$1(entriesError.value), 1))
                    : (_openBlock$1(), _createElementBlock$1(_Fragment$1, { key: 2 }, [
                        _createElementVNode$1("div", _hoisted_30, [
                          _createTextVNode$1(" 共 " + _toDisplayString$1(entriesMeta.value.total) + " 项 ", 1),
                          (entriesMeta.value.truncated)
                            ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_31, "（仅显示前 500 项）"))
                            : _createCommentVNode$1("", true),
                          (entriesMeta.value.tool)
                            ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_32, " · " + _toDisplayString$1(entriesMeta.value.tool), 1))
                            : _createCommentVNode$1("", true)
                        ]),
                        (!treeRows.value.length)
                          ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_33, "压缩包为空"))
                          : (_openBlock$1(), _createElementBlock$1("div", _hoisted_34, [
                              (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(treePageRows.value, (row) => {
                                return (_openBlock$1(), _createElementBlock$1("div", {
                                  key: row.path,
                                  class: "entry-row",
                                  style: _normalizeStyle({ paddingLeft: (8 + row.depth * 18) + 'px' })
                                }, [
                                  _createVNode$1(_component_v_icon, {
                                    size: "16",
                                    class: "entry-icon"
                                  }, {
                                    default: _withCtx$1(() => [
                                      _createTextVNode$1(_toDisplayString$1(row.isDir ? 'mdi-folder-outline' : 'mdi-file-outline'), 1)
                                    ]),
                                    _: 2
                                  }, 1024),
                                  _createElementVNode$1("span", _hoisted_35, _toDisplayString$1(row.name) + _toDisplayString$1(row.isDir ? '/' : ''), 1),
                                  _createElementVNode$1("span", _hoisted_36, _toDisplayString$1(row.isDir ? '' : fmtSize(row.size)), 1)
                                ], 4))
                              }), 128))
                            ])),
                        (treePageCount.value > 1)
                          ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_37, [
                              _createVNode$1(_component_v_btn, {
                                size: "x-small",
                                variant: "text",
                                disabled: treePage.value <= 1,
                                onClick: _cache[5] || (_cache[5] = $event => (treePage.value -= 1))
                              }, {
                                default: _withCtx$1(() => [...(_cache[44] || (_cache[44] = [
                                  _createTextVNode$1("上一页", -1)
                                ]))]),
                                _: 1
                              }, 8, ["disabled"]),
                              _createElementVNode$1("span", null, "第 " + _toDisplayString$1(treePage.value) + " / " + _toDisplayString$1(treePageCount.value) + " 页", 1),
                              _createVNode$1(_component_v_btn, {
                                size: "x-small",
                                variant: "text",
                                disabled: treePage.value >= treePageCount.value,
                                onClick: _cache[6] || (_cache[6] = $event => (treePage.value += 1))
                              }, {
                                default: _withCtx$1(() => [...(_cache[45] || (_cache[45] = [
                                  _createTextVNode$1("下一页", -1)
                                ]))]),
                                _: 1
                              }, 8, ["disabled"])
                            ]))
                          : _createCommentVNode$1("", true)
                      ], 64))
              ]),
              _: 1
            }),
            _createVNode$1(_component_v_card_actions, null, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_spacer),
                _createVNode$1(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[7] || (_cache[7] = $event => (entriesDialog.value = false))
                }, {
                  default: _withCtx$1(() => [...(_cache[46] || (_cache[46] = [
                    _createTextVNode$1("关闭", -1)
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
    }, 8, ["modelValue", "fullscreen"])
  ]))
}
}

};
const Archives = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-063097a1"]]);

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createBlock:_createBlock,createCommentVNode:_createCommentVNode,resolveDynamicComponent:_resolveDynamicComponent,KeepAlive:_KeepAlive,createSlots:_createSlots} = await importShared('vue');


const _hoisted_1 = { class: "zt-app" };
const _hoisted_2 = { class: "zt-layout" };
const _hoisted_3 = { class: "zt-nav zt-card-bg" };
const _hoisted_4 = { class: "zt-nav-header" };
const _hoisted_5 = { class: "zt-app-title" };
const _hoisted_6 = { class: "zt-content" };
const _hoisted_7 = { class: "zt-mobile-nav zt-card-bg" };
const _hoisted_8 = { class: "zt-sheet-card zt-card-bg" };
const _hoisted_9 = {
  key: 0,
  class: "zt-disabled-mask"
};
const _hoisted_10 = { class: "zt-disabled-card zt-card-bg" };

const {computed,inject,onActivated,onMounted,ref,getCurrentInstance} = await importShared('vue');

// 宿主注入的能力

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'Zitifenlei' },
  // 宿主若传入初始配置则优先使用（配置弹窗场景）；数据页一般无此 prop，由 GET /config 兜底
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['action', 'layout', 'switch', 'close', 'save'],
  setup(__props, { expose: __expose, emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject('moviepilot:toast', null);
const instance = getCurrentInstance();

// 导航项
const navItems = [
  { key: 'dashboard', title: '仪表盘', icon: 'mdi-view-dashboard-outline' },
  { key: 'fonts', title: '字体库', icon: 'mdi-format-font' },
  { key: 'check', title: '检查', icon: 'mdi-file-document-check-outline' },
  { key: 'subset', title: '子集化', icon: 'mdi-subtitles-outline' },
  { key: 'missing', title: '缺失字体', icon: 'mdi-alert-circle-outline' },
  { key: 'archives', title: '已处理压缩包', icon: 'mdi-archive-eye-outline' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
];

const active = ref('dashboard');
const loading = ref(true);
const mobileSheet = ref(false);
// 数据变更信号：任一子视图完成影响共享数据的操作（如仪表盘「重新识别厂商」）后，
// 递推本值通知 keep-alive 缓存中的各视图（字体库/仪表盘）重拉最新数据，
// 不依赖宿主 keep-alive 的 onActivated 行为，关闭再进入也能拿到最新结果
const refreshKey = ref(0);

// 当前导航项（移动端顶部栏展示）
const currentNavItem = computed(() => navItems.find(item => item.key === active.value) || navItems[0]);

function gotoNav(key) {
  active.value = key;
  mobileSheet.value = false;
}

// 全局配置（对齐 subscribeplus：数据页复用配置 UI 时用 GET /config 读取权威初始值）
const DEFAULT_CONFIG = {
  enabled: true,
  input_dir: '',
  lib_dir: '',
  ass_dir: '',
  archive_mode: 'copy',
  notify_enabled: false,
};
const pluginConfig = ref({ ...DEFAULT_CONFIG, ...(props.initialConfig || {}) });
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false);

async function initConfig() {
  try {
    const data = await apiModule.get(props.api, '/config');
    if (data && typeof data === 'object') {
      const { dirs, ...cfg } = data;
      pluginConfig.value = { ...pluginConfig.value, ...cfg };
    }
  } catch (e) {
    // 读取失败保持初始配置
  }
}

// 设置页保存回调：
// 1) 更新本地开关状态（停用遮罩即时生效）；
// 2) 补宿主原生 PUT 双通道：总开关改变时，主动调 PUT plugin/{id}（与宿主配置弹窗
//    保存同一条通道，见 MoviePilot-Frontend PluginConfigDialog）——宿主收到自己的
//    PUT 后会把配置写入宿主存储并重新 init_plugin，保证后端状态即时正确，
//    下次进入插件列表/F5 时卡片即显示最新状态。PUT body 为完整配置、同值覆盖，幂等无冲突；
// 3) emit('save') 兜底转发（宿主若不监听则忽略）。
//    持久化主通道仍是设置页 POST /config（后端 update_config 已落盘）。
// 注意：宿主插件详情页是共享 Dialog（keep-alive 列表不会因关闭弹窗而重新拉取，
// 为宿主通用行为），故保存后不自动退出，留在设置页由 toast 提示。
async function onConfigSave(cfg) {
  // 总开关是否发生变化：以合并前 enabled 与合并后为基准
  const prevEnabled = pluginConfig.value.enabled !== false;
  if (cfg && typeof cfg === 'object') {
    pluginConfig.value = { ...pluginConfig.value, ...cfg };
  }
  const payload = { ...pluginConfig.value };
  const nextEnabled = payload.enabled !== false;
  try {
    // 仅总开关变化时才走宿主通道（其他字段变化不需要刷新卡片状态）
    if (prevEnabled !== nextEnabled && props.api && typeof props.api.put === 'function') {
      await props.api.put(`plugin/${props.pluginId}`, payload);
    }
  } catch (e) {
    // 宿主通道失败不影响本地位与 POST /config 持久化结果
  }
  try {
    emit('save', payload);
  } catch (e) {
    // 宿主不支持转发则忽略
  }
}

// 子视图数据操作完成（如仪表盘重新识别厂商、字体库删除字体等）：递推刷新键
// 让 keep-alive 缓存中的兄弟视图重拉最新数据，再向宿主转发原 action 事件
function handleAction(payload) {
  refreshKey.value++;
  // 检查/子集化页「去缺失字体页」：直接切到缺失字体导航
  if (payload && typeof payload === 'object' && payload.type === 'goto_missing') {
    active.value = 'missing';
  }
  emit('action', payload);
}

// Q14 修复：删除 watch(active) 的全量 refreshKey 广播——切 Tab 时各视图
// 自身 keep-alive 的 onActivated 钩子已负责重拉数据 + 恢复轮询，
// 不再让所有缓存视图（含不可见的）并发拉全量接口。
// refreshKey 仅保留给"子页数据操作"（handleAction）与"宿主重新进入插件"
// （onActivated）两条低频、真需要跨页同步的信号。
// 内部 Tab 切换不再推进刷新键：切回视图由该视图 onActivated 自查自刷

// 宿主详情页为共享 Dialog（keep-alive 缓存）：重新进入插件时强制各视图刷新，
// 确保「重新识别厂商」「外部删除字体文件」等变化在再次打开时立即生效
onActivated(() => {
  refreshKey.value++;
});

// 视图：点到哪里，右边显示什么
const views = {
  dashboard: Dashboard,
  fonts: FontLibrary,
  check: Check,
  subset: Subset,
  missing: MissingFonts,
  archives: Archives,
  settings: Settings,
};
const currentView = computed(() => views[active.value] || Dashboard);

onMounted(async () => {
  // 通知宿主：最大需要 68rem 宽度
  instance?.emit('layout', { maxWidth: '68rem' });

  initConfig();

  try {
    emit('action');
  } catch (e) {
    // 忽略
  } finally {
    loading.value = false;
  }
});

function notify(message, type = 'error') {
  if (toast && typeof toast[type] === 'function') {
    toast[type](message);
  }
}

// 关闭插件页（右上角 X）：只通知宿主关闭插件弹窗，宿主负责回到插件列表
function closePlugin() {
  try {
    emit('close');
  } catch (e) {
    // 忽略
  }
}

__expose({ notify });

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
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("div", _hoisted_4, [
          _createElementVNode("div", _hoisted_5, [
            _createVNode(_component_v_icon, { start: "" }, {
              default: _withCtx(() => [...(_cache[3] || (_cache[3] = [
                _createTextVNode("mdi-format-font", -1)
              ]))]),
              _: 1
            }),
            _cache[4] || (_cache[4] = _createTextVNode(" 字体分类管家 ", -1))
          ]),
          _cache[5] || (_cache[5] = _createElementVNode("div", { class: "zt-app-subtitle" }, "Font Manager", -1))
        ]),
        _createVNode(_component_v_divider, { class: "zt-divider" }),
        _createVNode(_component_v_list, { class: "zt-nav-list" }, {
          default: _withCtx(() => [
            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
              return _createVNode(_component_v_list_item, {
                key: item.key,
                active: active.value === item.key,
                class: "zt-nav-item",
                onClick: $event => (active.value = item.key)
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_list_item_title, { class: "zt-nav-text" }, {
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
      _createElementVNode("div", _hoisted_6, [
        (loading.value)
          ? (_openBlock(), _createBlock(_component_v_progress_circular, {
              key: 0,
              indeterminate: "",
              color: "primary",
              class: "zt-loading"
            }))
          : (_openBlock(), _createBlock(_KeepAlive, { key: 1 }, [
              (_openBlock(), _createBlock(_resolveDynamicComponent(currentView.value), {
                key: active.value,
                api: props.api,
                target: active.value,
                enabled: pluginEnabled.value,
                refreshKey: refreshKey.value,
                onNotify: notify,
                onAction: handleAction,
                onSave: onConfigSave
              }, null, 40, ["api", "target", "enabled", "refreshKey"]))
            ], 1024))
      ])
    ]),
    _createElementVNode("div", _hoisted_7, [
      _createElementVNode("button", {
        type: "button",
        class: "zt-mnav-current",
        onClick: _cache[0] || (_cache[0] = $event => (mobileSheet.value = true))
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
          class: "zt-mnav-caret"
        }, {
          default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
            _createTextVNode("mdi-chevron-down", -1)
          ]))]),
          _: 1
        })
      ])
    ]),
    _createVNode(_component_v_bottom_sheet, {
      modelValue: mobileSheet.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((mobileSheet).value = $event)),
      class: "zt-sheet"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", _hoisted_8, [
          _cache[8] || (_cache[8] = _createElementVNode("div", { class: "zt-sheet-title" }, "切换页面", -1)),
          _createVNode(_component_v_divider, { class: "zt-divider" }),
          _createVNode(_component_v_list, { class: "zt-sheet-list" }, {
            default: _withCtx(() => [
              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
                return _createVNode(_component_v_list_item, {
                  key: item.key,
                  active: active.value === item.key,
                  color: "primary",
                  rounded: "lg",
                  class: "zt-sheet-item",
                  onClick: $event => (gotoNav(item.key))
                }, _createSlots({
                  prepend: _withCtx(() => [
                    _createVNode(_component_v_icon, { size: 20 }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(item.icon), 1)
                      ]),
                      _: 2
                    }, 1024)
                  ]),
                  default: _withCtx(() => [
                    _createVNode(_component_v_list_item_title, { class: "font-weight-medium" }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(item.title), 1)
                      ]),
                      _: 2
                    }, 1024)
                  ]),
                  _: 2
                }, [
                  (active.value === item.key)
                    ? {
                        name: "append",
                        fn: _withCtx(() => [
                          _createVNode(_component_v_icon, { color: "primary" }, {
                            default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
                              _createTextVNode("mdi-check", -1)
                            ]))]),
                            _: 1
                          })
                        ]),
                        key: "0"
                      }
                    : undefined
                ]), 1032, ["active", "onClick"])
              }), 64))
            ]),
            _: 1
          })
        ])
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_btn, {
      icon: "mdi-close",
      size: "small",
      variant: "tonal",
      class: "zt-close-btn",
      title: "关闭插件",
      onClick: closePlugin
    }),
    (!pluginEnabled.value && active.value !== 'settings')
      ? (_openBlock(), _createElementBlock("div", _hoisted_9, [
          _createElementVNode("div", _hoisted_10, [
            _createVNode(_component_v_icon, {
              color: "warning",
              size: "44",
              class: "mb-2"
            }, {
              default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                _createTextVNode("mdi-power-off", -1)
              ]))]),
              _: 1
            }),
            _cache[12] || (_cache[12] = _createElementVNode("div", { class: "zt-disabled-title" }, "插件已停用", -1)),
            _cache[13] || (_cache[13] = _createElementVNode("div", { class: "zt-disabled-desc" }, "插件已被关闭，其他页面暂不可用", -1)),
            _createVNode(_component_v_btn, {
              color: "primary",
              variant: "tonal",
              class: "mt-3",
              onClick: _cache[2] || (_cache[2] = $event => (active.value = 'settings'))
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
                _cache[11] || (_cache[11] = _createTextVNode(" 前往设置启用 ", -1))
              ]),
              _: 1
            })
          ])
        ]))
      : _createCommentVNode("", true),
    (!pluginEnabled.value && active.value === 'settings')
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 1,
          type: "warning",
          density: "compact",
          class: "zt-disabled-banner"
        }, {
          default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
            _createTextVNode(" 插件当前已停用：其他页面不可操作，请在本页开启「插件总开关」并保存。 ", -1)
          ]))]),
          _: 1
        }))
      : _createCommentVNode("", true)
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-559e778b"]]);

export { Page as default };
