import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, a as apiModule, S as Settings, C as Check, F as FontLibrary, D as Dashboard } from './Settings-D6EzJD4i.js';

const {createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,openBlock:_openBlock$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,createElementBlock:_createElementBlock$2,renderList:_renderList$2,Fragment:_Fragment$2,normalizeClass:_normalizeClass} = await importShared('vue');


const _hoisted_1$2 = { class: "zt-subset" };
const _hoisted_2$2 = { class: "zt-topbar" };
const _hoisted_3$2 = { class: "zt-status-hint text-body-2" };
const _hoisted_4$2 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_5$2 = {
  key: 2,
  class: "zt-list-body"
};
const _hoisted_6$2 = { class: "zt-filter-row" };
const _hoisted_7$2 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_8$2 = {
  key: 3,
  class: "ml-2"
};
const _hoisted_9$2 = {
  key: 0,
  class: "zt-loading-more pa-2 text-center"
};
const _hoisted_10$2 = {
  key: 1,
  class: "zt-loading-more pa-2 text-center text-body-2 zt-font-meta"
};

const {computed: computed$1,onMounted: onMounted$2,onUnmounted: onUnmounted$1,ref: ref$2,watch: watch$1} = await importShared('vue');

const recordLimit = 20;

const _sfc_main$2 = {
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

// ===== assfonts 状态 =====
const status = ref$2({ binary_ok: false, binary_path: '', index: { exists: false, count: 0, mtime: 0, size: 0 }, lib_dir: '' });

// ===== 左栏：待处理 =====
const pendingList = ref$2([]);
const loadingPending = ref$2(false);
const uploadRef = ref$2(null);
const uploading = ref$2(false);
// 处理中：按钮转圈禁用，防重复点击
const scanning = ref$2(false);

// ===== 右栏：结果 =====
const records = ref$2([]);
const loadingRecords = ref$2(false);
const downloadingId = ref$2(null);
const recordTotal = ref$2(0);
const retriableCount = ref$2(0);
const recordPage = ref$2(1);
const recordReachedEnd = ref$2(false);
// 筛选：状态下拉 + 文件名搜索
const filterStatus = ref$2('');
const recordSearch = ref$2('');
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
  } catch (e) { /* 忽略 */ }
}
// 重建 assfonts 字体索引：新归档/删减字体后，让检查与子集化按最新字体库口径比对
const rebuildingIndex = ref$2(false);
async function rebuildIndex() {
  if (rebuildingIndex.value) return
  rebuildingIndex.value = true;
  try {
    await apiModule.post(props.api, '/subset/rebuild_index');
    emit('notify', 'assfonts 索引已重建，检查/子集化将按新字体库口径比对', 'success');
    await loadStatus();
    emit('action', { type: 'subset_done' });
  } catch (e) {
    emit('notify', e.message || '重建索引失败');
  } finally {
    rebuildingIndex.value = false;
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
async function loadRecords(reset = false) {
  if (loadingRecords.value) return
  if (reset) {
    recordPage.value = 1;
    recordReachedEnd.value = false;
    records.value = [];
  } else if (recordReachedEnd.value) {
    return
  }
  loadingRecords.value = true;
  try {
    const data = await apiModule.get(props.api, '/subset/records', {
      status: filterStatus.value,
      search: recordSearch.value,
      page: recordPage.value,
      limit: recordLimit,
    });
    const list = (data && data.list) || [];
    recordTotal.value = (data && data.total) || 0;
    if (typeof data?.retriable === 'number') retriableCount.value = data.retriable;
    records.value = reset ? list : [...records.value, ...list];
    if (records.value.length >= recordTotal.value || !list.length) {
      recordReachedEnd.value = true;
    }
  } catch (e) {
    emit('notify', e.message || '读取子集化记录失败');
  } finally {
    loadingRecords.value = false;
  }
}

// 筛选变化：防抖后回到第 1 页重拉
let filterTimer = null;
watch$1([filterStatus, recordSearch], () => {
  if (filterTimer) clearTimeout(filterTimer);
  filterTimer = setTimeout(() => loadRecords(true), 250);
});

// 滚动到底加载下一页
function onRecordsScroll(e) {
  const el = e.target;
  if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
    recordPage.value += 1;
    loadRecords();
  }
}

function indexTime() {
  const t = status.value?.index?.mtime;
  if (!t) return ''
  const d = new Date(t * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
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
      }
    }
    emit('notify', `已加入待处理 ${total} 个字幕`, 'success');
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
  try {
    const res = await apiModule.post(props.api, '/subset/all');
    const s = res || {};
    emit('notify', `全量子集化完成：成功 ${s.success ?? 0}，跳过 ${s.skipped ?? 0}，缺字体 ${s.missing ?? 0}，失败 ${s.error ?? 0}`, 'success');
    await loadRecords(true);
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
const retrying = ref$2(false);
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
    await loadRecords(true);
    await loadStatus();
    emit('action', { type: 'subset_done' });
  } catch (e) {
    emit('notify', e.message || '重试失败');
  } finally {
    retrying.value = false;
  }
}

// 下载结果文件（base64 → blob）
async function downloadRecord(r) {
  if (downloadingId.value) return
  if (!r.out_file) {
    emit('notify', '无输出文件', 'warning');
    return
  }
  downloadingId.value = r.id;
  try {
    const res = await apiModule.get(props.api, '/subset/download', { id: r.id });
    if (!res?.data) {
      emit('notify', '结果文件不存在', 'warning');
      return
    }
    const bytes = Uint8Array.from(atob(res.data), c => c.charCodeAt(0));
    const blob = new Blob([bytes]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = res.name || (r.file_name.replace(/\.ass$/i, '') + '.assfonts.ass');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    emit('notify', e.message || '下载失败');
  } finally {
    downloadingId.value = null;
  }
}

// 可批量下载的记录：已加载的成功且带输出文件
const downloadableRecords = computed$1(() =>
  records.value.filter(r => r.status === 'success' && r.out_file)
);

// 全部下载：按当前筛选（状态下拉+名称搜索）拉取全部成功成品，串行逐个下载；
// 未选筛选则下载全部分页的成功成品（limit=0 后端返回当前筛选下全部记录，不限页）
const downloadAllBusy = ref$2(false);
async function downloadAll() {
  if (downloadAllBusy.value) return
  downloadAllBusy.value = true;
  let ok = 0;
  let fail = 0;
  try {
    const data = await apiModule.get(props.api, '/subset/records', {
      status: filterStatus.value,
      search: recordSearch.value,
      page: 1,
      limit: 0, // 0 = 当前筛选下全部记录（含未加载的后续页）
    });
    const targets = ((data && data.list) || []).filter(r => r.status === 'success' && r.out_file);
    if (!targets.length) {
      emit('notify', '当前筛选下没有可下载的成功成品', 'warning');
      return
    }
    for (const r of targets) {
      try {
        await downloadRecord(r);
        ok += 1;
      } catch (e) {
        fail += 1;
      }
      // 逐条下载间让出事件循环，浏览器同域批量下载逐步放行
      await new Promise(res => setTimeout(res, 350));
    }
    emit('notify', fail ? `已下载 ${ok} 个，${fail} 个失败` : `已下载 ${ok} 个结果文件`, ok ? 'success' : 'warning');
  } catch (e) {
    emit('notify', e.message || '获取结果失败');
  } finally {
    downloadAllBusy.value = false;
  }
}

async function deleteRecord(id) {
  try {
    await apiModule.post(props.api, `/subset/delete/${id}`);
    // 删除后软刷新回第 1 页（计数、分页、retriable 一并同步）
    await loadRecords(true);
  } catch (e) {
    emit('notify', e.message || '删除失败');
  }
}

async function clearRecords() {
  try {
    await apiModule.del(props.api, '/subset/clear');
    await loadRecords(true);
    emit('notify', '已清空子集化记录', 'success');
  } catch (e) {
    emit('notify', e.message || '清空失败');
  }
}

onMounted$2(() => {
  loadStatus();
  loadPending();
  loadRecords();
  startPolling();
});
onUnmounted$1(() => stopPolling());

let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    loadPending();
    loadRecords(true);
    loadStatus();
  }, 30000);
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_spacer = _resolveComponent$2("v-spacer");
  const _component_v_card_title = _resolveComponent$2("v-card-title");
  const _component_v_divider = _resolveComponent$2("v-divider");
  const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$2("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$2("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$2("v-list-item");
  const _component_v_list = _resolveComponent$2("v-list");
  const _component_v_card = _resolveComponent$2("v-card");
  const _component_v_col = _resolveComponent$2("v-col");
  const _component_v_select = _resolveComponent$2("v-select");
  const _component_v_text_field = _resolveComponent$2("v-text-field");
  const _component_v_chip = _resolveComponent$2("v-chip");
  const _component_v_progress_circular = _resolveComponent$2("v-progress-circular");
  const _component_v_row = _resolveComponent$2("v-row");

  return (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
    _createElementVNode$2("div", _hoisted_2$2, [
      _createVNode$2(_component_v_btn, {
        variant: "tonal",
        color: "primary",
        disabled: !__props.enabled || uploading.value,
        loading: uploading.value,
        title: "上传字幕到「待处理」",
        onClick: _cache[0] || (_cache[0] = $event => (uploadRef.value?.click()))
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[3] || (_cache[3] = [
              _createTextVNode$2("mdi-upload", -1)
            ]))]),
            _: 1
          }),
          _cache[4] || (_cache[4] = _createTextVNode$2(" 上传字幕 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createElementVNode$2("input", {
        ref_key: "uploadRef",
        ref: uploadRef,
        type: "file",
        accept: ".ass",
        multiple: "",
        style: {"display":"none"},
        onChange: handleUpload
      }, null, 544),
      _createVNode$2(_component_v_btn, {
        color: "primary",
        disabled: !__props.enabled || scanning.value || !pendingList.value.length,
        loading: scanning.value,
        title: "处理「待处理」中的全部字幕（assfonts 子集化并内嵌字体）",
        onClick: scanAll
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[5] || (_cache[5] = [
              _createTextVNode$2("mdi-magnify-scan", -1)
            ]))]),
            _: 1
          }),
          _cache[6] || (_cache[6] = _createTextVNode$2(" 全量子集化 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createVNode$2(_component_v_btn, {
        color: "warning",
        variant: "tonal",
        disabled: !__props.enabled || retrying.value || !hasRetriable(),
        loading: retrying.value,
        title: "对结果区中失败/缺字体的字幕重新子集化（补好缺失字体后使用）",
        onClick: retryFailed
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[7] || (_cache[7] = [
              _createTextVNode$2("mdi-refresh", -1)
            ]))]),
            _: 1
          }),
          _cache[8] || (_cache[8] = _createTextVNode$2(" 重试失败 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createVNode$2(_component_v_btn, {
        variant: "tonal",
        disabled: !__props.enabled || !pendingList.value.length,
        title: "清空左栏待处理",
        onClick: clearPending
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[9] || (_cache[9] = [
              _createTextVNode$2("mdi-delete-sweep-outline", -1)
            ]))]),
            _: 1
          }),
          _cache[10] || (_cache[10] = _createTextVNode$2(" 清空待处理 ", -1))
        ]),
        _: 1
      }, 8, ["disabled"]),
      _createVNode$2(_component_v_btn, {
        variant: "tonal",
        disabled: !__props.enabled || !records.value.length,
        title: "清空全部子集化记录",
        onClick: clearRecords
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[11] || (_cache[11] = [
              _createTextVNode$2("mdi-trash-can-outline", -1)
            ]))]),
            _: 1
          }),
          _cache[12] || (_cache[12] = _createTextVNode$2(" 清空记录 ", -1))
        ]),
        _: 1
      }, 8, ["disabled"]),
      _createVNode$2(_component_v_spacer),
      _createElementVNode$2("span", _hoisted_3$2, [
        _createVNode$2(_component_v_icon, {
          size: 15,
          color: status.value.binary_ok ? 'success' : 'error'
        }, {
          default: _withCtx$2(() => [
            _createTextVNode$2(_toDisplayString$2(status.value.binary_ok ? 'mdi-check-circle' : 'mdi-close-circle'), 1)
          ]),
          _: 1
        }, 8, ["color"]),
        _createTextVNode$2(" assfonts：" + _toDisplayString$2(status.value.binary_ok ? '就绪' : '未就绪') + " ", 1),
        _createVNode$2(_component_v_icon, {
          size: 15,
          color: status.value.index.exists ? 'success' : 'warning',
          class: "ml-2"
        }, {
          default: _withCtx$2(() => [
            _createTextVNode$2(_toDisplayString$2(status.value.index.exists ? 'mdi-database-check' : 'mdi-database-off'), 1)
          ]),
          _: 1
        }, 8, ["color"]),
        _createTextVNode$2(" 索引：" + _toDisplayString$2(status.value.index.exists ? `${status.value.index.count} 个字体` : '未构建') + "（" + _toDisplayString$2(indexTime() || '—') + "） ", 1)
      ]),
      _createVNode$2(_component_v_btn, {
        variant: "text",
        size: "small",
        color: "primary",
        class: "ml-2",
        disabled: !__props.enabled || !status.value.binary_ok,
        loading: rebuildingIndex.value,
        title: "重新扫描字体库目录生成索引（新归档/删减字体后执行，让检查与子集化口径同步）",
        onClick: rebuildIndex
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "15"
          }, {
            default: _withCtx$2(() => [...(_cache[13] || (_cache[13] = [
              _createTextVNode$2("mdi-database-refresh", -1)
            ]))]),
            _: 1
          }),
          _cache[14] || (_cache[14] = _createTextVNode$2(" 重建索引 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"])
    ]),
    _createVNode$2(_component_v_row, {
      "no-gutters": "",
      class: "zt-subset-row"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_col, {
          cols: "12",
          md: "5"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, { class: "zt-card-bg zt-list-card" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$2(() => [...(_cache[15] || (_cache[15] = [
                        _createTextVNode$2("mdi-tray-full", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$2(" 待处理（" + _toDisplayString$2(pendingList.value.length) + "） ", 1)
                  ]),
                  _: 1
                }),
                _createVNode$2(_component_v_divider),
                (loadingPending.value)
                  ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$2("", true),
                (!loadingPending.value && !pendingList.value.length)
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_4$2, [...(_cache[16] || (_cache[16] = [
                      _createTextVNode$2(" 暂无待处理字幕", -1),
                      _createElementVNode$2("br", null, null, -1),
                      _createElementVNode$2("span", { class: "zt-empty-sub" }, "上传字幕，或设置开启「入库后自动子集化」+「目录自动收集」关闭时自动收集", -1)
                    ]))]))
                  : (_openBlock$2(), _createElementBlock$2("div", _hoisted_5$2, [
                      _createVNode$2(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$2(() => [
                          (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(pendingList.value, (p) => {
                            return (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                              key: p.id,
                              lines: "two"
                            }, {
                              prepend: _withCtx$2(() => [
                                _createVNode$2(_component_v_icon, {
                                  color: "primary",
                                  size: "18"
                                }, {
                                  default: _withCtx$2(() => [...(_cache[17] || (_cache[17] = [
                                    _createTextVNode$2("mdi-subtitles-outline", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              append: _withCtx$2(() => [
                                _createVNode$2(_component_v_btn, {
                                  size: "small",
                                  variant: "text",
                                  icon: "",
                                  disabled: !__props.enabled,
                                  title: "移除该项",
                                  onClick: $event => (removePending(p.id))
                                }, {
                                  default: _withCtx$2(() => [
                                    _createVNode$2(_component_v_icon, { size: "16" }, {
                                      default: _withCtx$2(() => [...(_cache[18] || (_cache[18] = [
                                        _createTextVNode$2("mdi-close", -1)
                                      ]))]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }, 8, ["disabled", "onClick"])
                              ]),
                              default: _withCtx$2(() => [
                                _createVNode$2(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(p.file_name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(p.source === 'watch' ? '目录监控' : '手动上传') + " · " + _toDisplayString$2(p.created_at), 1)
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
        _createVNode$2(_component_v_col, {
          cols: "12",
          md: "7"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, { class: "zt-card-bg zt-list-card" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$2(() => [...(_cache[19] || (_cache[19] = [
                        _createTextVNode$2("mdi-history", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$2(" 结果（" + _toDisplayString$2(records.value.length) + "/" + _toDisplayString$2(recordTotal.value) + "） ", 1),
                    _createVNode$2(_component_v_spacer),
                    _createVNode$2(_component_v_btn, {
                      size: "small",
                      variant: "tonal",
                      color: "success",
                      disabled: !__props.enabled || downloadAllBusy.value || !downloadableRecords.value.length,
                      loading: downloadAllBusy.value,
                      title: "下载当前列表全部成功成品的 .assfonts.ass 文件",
                      onClick: downloadAll
                    }, {
                      default: _withCtx$2(() => [
                        _createVNode$2(_component_v_icon, {
                          start: "",
                          size: "15"
                        }, {
                          default: _withCtx$2(() => [...(_cache[20] || (_cache[20] = [
                            _createTextVNode$2("mdi-download-multiple", -1)
                          ]))]),
                          _: 1
                        }),
                        _cache[21] || (_cache[21] = _createTextVNode$2(" 全部下载 ", -1))
                      ]),
                      _: 1
                    }, 8, ["disabled", "loading"])
                  ]),
                  _: 1
                }),
                _createVNode$2(_component_v_divider),
                _createElementVNode$2("div", _hoisted_6$2, [
                  _createVNode$2(_component_v_select, {
                    modelValue: filterStatus.value,
                    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((filterStatus).value = $event)),
                    items: statusFilterOptions,
                    "item-title": "title",
                    "item-value": "value",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "zt-filter-status"
                  }, null, 8, ["modelValue"]),
                  _createVNode$2(_component_v_text_field, {
                    modelValue: recordSearch.value,
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((recordSearch).value = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    clearable: "",
                    placeholder: "搜索字幕名…",
                    "prepend-inner-icon": "mdi-magnify",
                    class: "zt-filter-search"
                  }, null, 8, ["modelValue"])
                ]),
                _createVNode$2(_component_v_divider),
                (loadingRecords.value)
                  ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$2("", true),
                (!loadingRecords.value && !records.value.length)
                  ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_7$2, [
                      _createTextVNode$2(" 暂无" + _toDisplayString$2(filterStatus.value || recordSearch.value ? '匹配' : '') + "处理结果", 1),
                      _cache[22] || (_cache[22] = _createElementVNode$2("br", null, null, -1)),
                      _cache[23] || (_cache[23] = _createElementVNode$2("span", { class: "zt-empty-sub" }, "处理完成后结果与输出文件在这里展示，可下载", -1))
                    ]))
                  : (_openBlock$2(), _createElementBlock$2("div", {
                      key: 2,
                      class: "zt-list-body zt-record-body",
                      onScroll: onRecordsScroll
                    }, [
                      _createVNode$2(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$2(() => [
                          (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(records.value, (r) => {
                            return (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                              key: r.id,
                              lines: "two"
                            }, {
                              prepend: _withCtx$2(() => [
                                _createVNode$2(_component_v_chip, {
                                  color: statusColor(r),
                                  size: "x-small",
                                  variant: "tonal",
                                  title: r.status === 'missing' && !r.retryable ? '缺的字体尚未补齐：点击去「缺失字体」页上传' : (r.status === 'error' ? '处理失败：点击去「缺失字体」页处理' : (r.status === 'missing' && r.retryable ? '缺的字体已入库：点顶部「重试失败」重新子集化' : '')),
                                  class: _normalizeClass({ 'zt-status-link': (r.status === 'missing' && !r.retryable) || r.status === 'error' }),
                                  disabled: !__props.enabled,
                                  onClick: $event => (onStatusTagClick(r))
                                }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(statusText(r)), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["color", "title", "class", "disabled", "onClick"])
                              ]),
                              append: _withCtx$2(() => [
                                (r.status === 'success' && r.out_file)
                                  ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
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
                                      default: _withCtx$2(() => [
                                        _createVNode$2(_component_v_icon, {
                                          start: "",
                                          size: "14"
                                        }, {
                                          default: _withCtx$2(() => [...(_cache[24] || (_cache[24] = [
                                            _createTextVNode$2("mdi-download", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _cache[25] || (_cache[25] = _createTextVNode$2(" 下载 ", -1))
                                      ]),
                                      _: 1
                                    }, 8, ["disabled", "loading", "onClick"]))
                                  : _createCommentVNode$2("", true),
                                _createVNode$2(_component_v_btn, {
                                  size: "small",
                                  variant: "text",
                                  icon: "",
                                  disabled: !__props.enabled,
                                  title: "删除该记录",
                                  onClick: $event => (deleteRecord(r.id))
                                }, {
                                  default: _withCtx$2(() => [
                                    _createVNode$2(_component_v_icon, { size: "16" }, {
                                      default: _withCtx$2(() => [...(_cache[26] || (_cache[26] = [
                                        _createTextVNode$2("mdi-close", -1)
                                      ]))]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }, 8, ["disabled", "onClick"])
                              ]),
                              default: _withCtx$2(() => [
                                _createVNode$2(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(r.file_name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$2(() => [
                                    (r.reason)
                                      ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 0 }, [
                                          _createTextVNode$2(_toDisplayString$2(r.reason), 1)
                                        ], 64))
                                      : (r.out_file)
                                        ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 1 }, [
                                            _createTextVNode$2(_toDisplayString$2(r.out_file), 1)
                                          ], 64))
                                        : (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 2 }, [
                                            _createTextVNode$2("—")
                                          ], 64)),
                                    (r.created_at)
                                      ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_8$2, _toDisplayString$2(r.created_at), 1))
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
                      (!recordReachedEnd.value && records.value.length)
                        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_9$2, [
                            _createVNode$2(_component_v_progress_circular, {
                              indeterminate: "",
                              size: "18",
                              color: "primary"
                            })
                          ]))
                        : (recordReachedEnd.value && records.value.length)
                          ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_10$2, " 已加载全部 "))
                          : _createCommentVNode$2("", true)
                    ], 32))
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const Subset = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-c7aa3cca"]]);

const {createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,toDisplayString:_toDisplayString$1,createElementVNode:_createElementVNode$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,createElementBlock:_createElementBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "zt-missing" };
const _hoisted_2$1 = { class: "zt-status-line text-body-2 mb-3" };
const _hoisted_3$1 = { class: "mr-5" };
const _hoisted_4$1 = { class: "mr-5" };
const _hoisted_5$1 = {
  key: 1,
  class: "zt-uploads pa-3"
};
const _hoisted_6$1 = { class: "d-flex flex-wrap gap-2" };
const _hoisted_7$1 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_8$1 = {
  key: 2,
  class: "zt-list-body"
};
const _hoisted_9$1 = {
  key: 0,
  class: "text-center pa-2"
};
const _hoisted_10$1 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_11 = {
  key: 2,
  class: "zt-list-body"
};
const _hoisted_12 = {
  key: 0,
  class: "text-center pa-2"
};

const {onMounted: onMounted$1,onUnmounted,ref: ref$1} = await importShared('vue');

const PREVIEW_N = 5;


const _sfc_main$1 = {
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

const summary = ref$1({ check: [], subset: [], lib_dir: '', binary_ok: false });
const uploads = ref$1([]);
const loading = ref$1(false);
const expanded = ref$1({ check: false, subset: false });

const uploadRef = ref$1(null);
const uploading = ref$1(false);
const classifying = ref$1(false);
const clearing = ref$1(false);

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

// 上传字体（左右两栏共用；不校验匹配，归类时统一入库）
async function handleUpload(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 3 个
  const BATCH = 3;
  let total = 0;
  uploading.value = true;
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const form = new FormData();
      for (const file of chunk) form.append('file', file);
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
        total += (body?.data?.count ?? chunk.length);
      }
    }
    emit('notify', `已上传 ${total} 个字体，点击「归类」入库并刷新索引`, 'success');
    await loadUploads();
    await loadSummary();
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
    emit('notify', res?.index_ok ? '已入库并刷新索引，请回到「子集化」页重新运行' : (res?.message || '已入库'), 'success');
    await loadUploads();
    await loadSummary();
    emit('action', { type: 'missing_classified' });
  } catch (e) {
    emit('notify', e.message || '归类失败');
  } finally {
    classifying.value = false;
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

onMounted$1(() => {
  loadSummary();
  loadUploads();
  startPolling();
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
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_card_title = _resolveComponent$1("v-card-title");
  const _component_v_alert = _resolveComponent$1("v-alert");
  const _component_v_chip = _resolveComponent$1("v-chip");
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_divider = _resolveComponent$1("v-divider");
  const _component_v_progress_linear = _resolveComponent$1("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$1("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$1("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$1("v-list-item");
  const _component_v_list = _resolveComponent$1("v-list");
  const _component_v_col = _resolveComponent$1("v-col");
  const _component_v_row = _resolveComponent$1("v-row");

  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createVNode$1(_component_v_card, { class: "zt-card-bg mb-4" }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "zt-card-title" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, {
              start: "",
              size: "18"
            }, {
              default: _withCtx$1(() => [...(_cache[3] || (_cache[3] = [
                _createTextVNode$1("mdi-alert-circle-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[4] || (_cache[4] = _createTextVNode$1(" 缺失字体统一管理 ", -1))
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, { class: "pt-0" }, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", _hoisted_2$1, [
              _createElementVNode$1("span", _hoisted_3$1, [
                _createVNode$1(_component_v_icon, {
                  size: 16,
                  color: summary.value.binary_ok ? 'success' : 'error',
                  class: "mr-1"
                }, {
                  default: _withCtx$1(() => [
                    _createTextVNode$1(_toDisplayString$1(summary.value.binary_ok ? 'mdi-check-circle' : 'mdi-close-circle'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]),
                _createTextVNode$1(" assfonts：" + _toDisplayString$1(summary.value.binary_ok ? '就绪' : '未就绪'), 1)
              ]),
              _createElementVNode$1("span", _hoisted_4$1, [
                _createVNode$1(_component_v_icon, {
                  size: 16,
                  color: summary.value.lib_dir ? 'success' : 'warning',
                  class: "mr-1"
                }, {
                  default: _withCtx$1(() => [
                    _createTextVNode$1(_toDisplayString$1(summary.value.lib_dir ? 'mdi-folder-check' : 'mdi-folder-alert'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]),
                _createTextVNode$1(" 字体库：" + _toDisplayString$1(summary.value.lib_dir || '未配置'), 1)
              ]),
              _createElementVNode$1("span", null, [
                _createVNode$1(_component_v_icon, {
                  size: 16,
                  class: "mr-1"
                }, {
                  default: _withCtx$1(() => [...(_cache[5] || (_cache[5] = [
                    _createTextVNode$1("mdi-tray-arrow-up", -1)
                  ]))]),
                  _: 1
                }),
                _createTextVNode$1(" 已上传待归类：" + _toDisplayString$1(uploads.value.length) + " 个 ", 1)
              ])
            ]),
            (uploads.value.length)
              ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                  key: 0,
                  type: "info",
                  density: "compact",
                  class: "mb-3"
                }, {
                  default: _withCtx$1(() => [...(_cache[6] || (_cache[6] = [
                    _createTextVNode$1(" 已上传字体将在「归类」时统一归档到字体库并自动刷新 assfonts 索引；库中已有同名字体自动跳过不覆盖。 ", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode$1("", true),
            (uploads.value.length)
              ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_5$1, [
                  (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(uploads.value, (u) => {
                    return (_openBlock$1(), _createBlock$1(_component_v_chip, {
                      key: u.path,
                      size: "small",
                      variant: "tonal",
                      color: "primary",
                      class: "mr-2 mb-2",
                      close: "",
                      title: u.file_name,
                      "onClick:close": $event => (removeUpload(u.path))
                    }, {
                      default: _withCtx$1(() => [
                        _createTextVNode$1(_toDisplayString$1(u.file_name), 1)
                      ]),
                      _: 2
                    }, 1032, ["title", "onClick:close"]))
                  }), 128))
                ]))
              : _createCommentVNode$1("", true),
            _createElementVNode$1("div", _hoisted_6$1, [
              _createVNode$1(_component_v_btn, {
                color: "primary",
                variant: "tonal",
                disabled: !__props.enabled || uploading.value || classifying.value,
                loading: uploading.value,
                onClick: _cache[0] || (_cache[0] = $event => (uploadRef.value?.click()))
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$1(() => [...(_cache[7] || (_cache[7] = [
                      _createTextVNode$1("mdi-upload", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[8] || (_cache[8] = _createTextVNode$1(" 上传字体 ", -1))
                ]),
                _: 1
              }, 8, ["disabled", "loading"]),
              _createElementVNode$1("input", {
                ref_key: "uploadRef",
                ref: uploadRef,
                type: "file",
                accept: ".ttf,.otf,.ttc,.woff,.woff2",
                multiple: "",
                style: {"display":"none"},
                onChange: handleUpload
              }, null, 544),
              _createVNode$1(_component_v_btn, {
                color: "success",
                variant: "tonal",
                disabled: !__props.enabled || classifying.value || !uploads.value.length,
                loading: classifying.value,
                title: "全部上传字体入库 + 重建索引（运行中不可重复点击）",
                onClick: classify
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$1(() => [...(_cache[9] || (_cache[9] = [
                      _createTextVNode$1("mdi-database-import", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[10] || (_cache[10] = _createTextVNode$1(" 归类 ", -1))
                ]),
                _: 1
              }, 8, ["disabled", "loading"]),
              _createVNode$1(_component_v_btn, {
                variant: "tonal",
                color: "error",
                disabled: !__props.enabled || clearing.value || !uploads.value.length,
                loading: clearing.value,
                title: "清除已上传的字体",
                onClick: clearUploads
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_v_icon, {
                    start: "",
                    size: "18"
                  }, {
                    default: _withCtx$1(() => [...(_cache[11] || (_cache[11] = [
                      _createTextVNode$1("mdi-trash-can-outline", -1)
                    ]))]),
                    _: 1
                  }),
                  _cache[12] || (_cache[12] = _createTextVNode$1(" 清除全部 ", -1))
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
    _createVNode$1(_component_v_row, {
      "no-gutters": "",
      class: "zt-missing-row"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, { class: "zt-card-bg zt-missing-col" }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_icon, {
                      start: "",
                      size: "18",
                      color: "warning"
                    }, {
                      default: _withCtx$1(() => [...(_cache[13] || (_cache[13] = [
                        _createTextVNode$1("mdi-file-document-alert-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$1(" 检查缺失（" + _toDisplayString$1(summary.value.check?.length ?? 0) + "） ", 1)
                  ]),
                  _: 1
                }),
                _createVNode$1(_component_v_divider),
                (loading.value)
                  ? (_openBlock$1(), _createBlock$1(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$1("", true),
                (!loading.value && !(summary.value.check || []).length)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_7$1, " 检查页无缺失字体 "))
                  : (_openBlock$1(), _createElementBlock$1("div", _hoisted_8$1, [
                      _createVNode$1(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$1(() => [
                          (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(shownItems('check'), (f) => {
                            return (_openBlock$1(), _createBlock$1(_component_v_list_item, {
                              key: f.name,
                              lines: "two"
                            }, {
                              prepend: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  color: "warning",
                                  size: "18"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[14] || (_cache[14] = [
                                    _createTextVNode$1("mdi-alert", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$1(() => [
                                    _createTextVNode$1(_toDisplayString$1(f.name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$1(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$1(() => [
                                    _createTextVNode$1(_toDisplayString$1(f.count) + " 个字幕缺失", 1)
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
                        ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_9$1, [
                            _createVNode$1(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              onClick: _cache[1] || (_cache[1] = $event => (toggleExpand('check')))
                            }, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString$1(expanded.value.check ? '收起' : `展开全部（${summary.value.check.length}）`), 1)
                              ]),
                              _: 1
                            })
                          ]))
                        : _createCommentVNode$1("", true)
                    ]))
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, { class: "zt-card-bg zt-missing-col" }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_icon, {
                      start: "",
                      size: "18",
                      color: "error"
                    }, {
                      default: _withCtx$1(() => [...(_cache[15] || (_cache[15] = [
                        _createTextVNode$1("mdi-subtitles-alert-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _createTextVNode$1(" 子集化缺失（" + _toDisplayString$1(summary.value.subset?.length ?? 0) + "） ", 1)
                  ]),
                  _: 1
                }),
                _createVNode$1(_component_v_divider),
                (loading.value)
                  ? (_openBlock$1(), _createBlock$1(_component_v_progress_linear, {
                      key: 0,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode$1("", true),
                (!loading.value && !(summary.value.subset || []).length)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_10$1, " 子集化无缺失字体 "))
                  : (_openBlock$1(), _createElementBlock$1("div", _hoisted_11, [
                      _createVNode$1(_component_v_list, {
                        density: "compact",
                        class: "pa-0"
                      }, {
                        default: _withCtx$1(() => [
                          (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(shownItems('subset'), (f) => {
                            return (_openBlock$1(), _createBlock$1(_component_v_list_item, {
                              key: f.name,
                              lines: "two"
                            }, {
                              prepend: _withCtx$1(() => [
                                _createVNode$1(_component_v_icon, {
                                  color: "error",
                                  size: "18"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[16] || (_cache[16] = [
                                    _createTextVNode$1("mdi-close-octagon-outline", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_v_list_item_title, { class: "zt-font-name" }, {
                                  default: _withCtx$1(() => [
                                    _createTextVNode$1(_toDisplayString$1(f.name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode$1(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                  default: _withCtx$1(() => [
                                    _createTextVNode$1(_toDisplayString$1(f.count) + " 个字幕子集化时缺此字体", 1)
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
                        ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_12, [
                            _createVNode$1(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              onClick: _cache[2] || (_cache[2] = $event => (toggleExpand('subset')))
                            }, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString$1(expanded.value.subset ? '收起' : `展开全部（${summary.value.subset.length}）`), 1)
                              ]),
                              _: 1
                            })
                          ]))
                        : _createCommentVNode$1("", true)
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
    _cache[17] || (_cache[17] = _createElementVNode$1("div", { class: "zt-tip mt-3 text-body-2" }, " 提示：上传字体 → 点「归类」入库并自动刷新索引 → 回到「子集化」页重新运行即可。 ", -1))
  ]))
}
}

};
const MissingFonts = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-1b5e831d"]]);

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

const {computed,inject,onActivated,onMounted,ref,watch,getCurrentInstance} = await importShared('vue');

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
  scan_mode: 'internal',
  archive_mode: 'copy',
  auto_monitor: false,
  auto_check: false,
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

// 内部 Tab 切到哪个视图都递推一次刷新键：即使宿主 keep-alive 不传播 onActivated，
// keep-alive 缓存中的仪表盘/字体库也会通过 watch(refreshKey) 拿最新数据
watch(() => active.value, () => {
  refreshKey.value++;
});

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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-c271debd"]]);

export { Page as default };
