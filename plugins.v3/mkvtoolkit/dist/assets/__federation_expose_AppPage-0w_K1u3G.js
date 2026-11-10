import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import Config, { _ as _export_sfc, f as fmtBytes, S as SUBTITLE_ENCODINGS, c as codecLabel, a as fmtChannels, L as LANGUAGE_ITEMS, b as baseName, A as ARCHIVE_EXTENSIONS, F as FONT_EXTENSIONS, d as AUDIO_EXTENSIONS, e as SUBTITLE_EXTENSIONS, i as isArchiveName, g as fmtDateTime, h as fmtDuration, j as createApi, k as extName, s as stripExt } from './__federation_expose_Config-DbJZ4ehJ.js';

const logoUrl = "/assets/icon-DyyW1sja.png";

const {resolveComponent:_resolveComponent$a,openBlock:_openBlock$a,createBlock:_createBlock$a,createCommentVNode:_createCommentVNode$a,createElementVNode:_createElementVNode$a,toDisplayString:_toDisplayString$a,normalizeClass:_normalizeClass$9,createElementBlock:_createElementBlock$a,unref:_unref$7,normalizeStyle:_normalizeStyle$1,renderList:_renderList$8,Fragment:_Fragment$9} = await importShared('vue');


const _hoisted_1$a = { class: "tree-node" };
const _hoisted_2$a = ["title"];
const _hoisted_3$a = { class: "tree-ic" };
const _hoisted_4$a = { class: "tree-name" };
const _hoisted_5$a = { class: "tree-mini" };
const _hoisted_6$a = { key: 0 };
const _hoisted_7$9 = { key: 1 };

const {computed: computed$9,inject: inject$1} = await importShared('vue');


const _sfc_main$a = {
  __name: 'TreeNode',
  props: {
  node: { type: Object, required: true },
  api: { type: Object, required: true },
  root: { type: String, default: '' },
  kind: { type: String, default: 'video' },
  current: { type: String, default: '' },
  // 文件路径 -> /file-statuses 条目
  statuses: { type: Object, default: () => ({}) },
  depth: { type: Number, default: 0 },
},
  emits: ['select'],
  setup(__props, { emit: __emit }) {

/**
 * 目录树节点（递归）
 * 懒加载：首次展开目录时才请求 /fs/list；目录节点带 file_count 时显示数量
 */
const props = __props;

const emit = __emit;
const toast = inject$1('moviepilot:toast', null);

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message);
}

async function loadChildren() {
  const node = props.node;
  if (!node.dir || node.loaded || node.loading) return
  node.loading = true;
  try {
    const data = await props.api.post('/fs/list', {
      root: props.root,
      path: node.path,
      kind: props.kind,
    });
    const dirs = (data?.dirs || []).map((item) => ({
      name: item.name,
      path: item.path,
      dir: true,
      expanded: false,
      loaded: false,
      loading: false,
      children: [],
      fileCount: item.file_count ?? null,
    }));
    const files = (data?.files || []).map((item) => ({
      name: item.name,
      path: item.path,
      dir: false,
      size: item.size ?? null,
      ext: item.ext || '',
    }));
    node.children = dirs.concat(files);
    node.loaded = true;
  } catch (err) {
    node.loaded = true;
    node.children = [];
    toastMsg('error', `读取目录失败：${err.message}`);
  } finally {
    node.loading = false;
  }
}

async function onClick() {
  if (props.node.dir) {
    await loadChildren();
    props.node.expanded = !props.node.expanded;
  } else {
    emit('select', props.node.path);
  }
}

function indent() {
  return `${props.depth * 14 + 8}px`
}

// 文件行状态徽标：pending/running/success/failed/cancelled
const STATUS_BADGE = {
  pending: { text: '待开始', cls: 'pending' },
  running: { text: '运行中', cls: 'running' },
  success: { text: '已完成', cls: 'success' },
  failed: { text: '失败', cls: 'failed' },
  cancelled: { text: '已取消', cls: 'cancelled' },
};

const badge = computed$9(() => {
  if (props.node.dir) return null
  const info = props.statuses?.[props.node.path];
  if (!info) return null
  const found = STATUS_BADGE[info.state];
  if (!found) return null
  // 队列 pending 且阶段为「等待中」时显示等待中
  if (info.state === 'pending' && String(info.stage || '').includes('等待')) {
    return { text: '等待中', cls: 'pending' }
  }
  return found
});

return (_ctx, _cache) => {
  const _component_v_progress_circular = _resolveComponent$a("v-progress-circular");
  const _component_v_icon = _resolveComponent$a("v-icon");
  const _component_TreeNode = _resolveComponent$a("TreeNode", true);

  return (_openBlock$a(), _createElementBlock$a("div", _hoisted_1$a, [
    _createElementVNode$a("div", {
      class: _normalizeClass$9(["tree-row", { 'tree-row--file': !__props.node.dir, 'tree-row--active': !__props.node.dir && __props.node.path === __props.current }]),
      style: _normalizeStyle$1({ paddingLeft: indent() }),
      title: __props.node.path,
      onClick: onClick
    }, [
      _createElementVNode$a("span", _hoisted_3$a, [
        (__props.node.loading)
          ? (_openBlock$a(), _createBlock$a(_component_v_progress_circular, {
              key: 0,
              indeterminate: "",
              size: "12",
              width: "2"
            }))
          : (__props.node.dir)
            ? (_openBlock$a(), _createBlock$a(_component_v_icon, {
                key: 1,
                size: "15",
                icon: __props.node.expanded ? 'mdi-chevron-down' : 'mdi-chevron-right'
              }, null, 8, ["icon"]))
            : (_openBlock$a(), _createBlock$a(_component_v_icon, {
                key: 2,
                size: "15",
                icon: "mdi-filmstrip"
              }))
      ]),
      _createElementVNode$a("span", _hoisted_4$a, _toDisplayString$a(__props.node.name), 1),
      (badge.value)
        ? (_openBlock$a(), _createElementBlock$a("span", {
            key: 0,
            class: _normalizeClass$9(["tree-badge", `tree-badge--${badge.value.cls}`])
          }, _toDisplayString$a(badge.value.text), 3))
        : _createCommentVNode$a("", true),
      _createElementVNode$a("span", _hoisted_5$a, [
        (__props.node.dir && __props.node.fileCount)
          ? (_openBlock$a(), _createElementBlock$a("span", _hoisted_6$a, _toDisplayString$a(__props.node.fileCount), 1))
          : (!__props.node.dir)
            ? (_openBlock$a(), _createElementBlock$a("span", _hoisted_7$9, _toDisplayString$a(_unref$7(fmtBytes)(__props.node.size, 0)), 1))
            : _createCommentVNode$a("", true)
      ])
    ], 14, _hoisted_2$a),
    (__props.node.dir && __props.node.expanded && __props.node.children && __props.node.children.length)
      ? (_openBlock$a(true), _createElementBlock$a(_Fragment$9, { key: 0 }, _renderList$8(__props.node.children, (child) => {
          return (_openBlock$a(), _createBlock$a(_component_TreeNode, {
            key: child.path,
            node: child,
            api: __props.api,
            root: __props.root,
            kind: __props.kind,
            current: __props.current,
            statuses: __props.statuses,
            depth: __props.depth + 1,
            onSelect: _cache[0] || (_cache[0] = $event => (emit('select', $event)))
          }, null, 8, ["node", "api", "root", "kind", "current", "statuses", "depth"]))
        }), 128))
      : (__props.node.dir && __props.node.expanded && __props.node.loaded)
        ? (_openBlock$a(), _createElementBlock$a("div", {
            key: 1,
            class: "tree-empty",
            style: _normalizeStyle$1({ paddingLeft: `${__props.depth * 14 + 26}px` })
          }, " （空目录） ", 4))
        : _createCommentVNode$a("", true)
  ]))
}
}

};
const TreeNode = /*#__PURE__*/_export_sfc(_sfc_main$a, [['__scopeId',"data-v-d984090f"]]);

const {resolveComponent:_resolveComponent$9,createVNode:_createVNode$9,createElementVNode:_createElementVNode$9,renderList:_renderList$7,Fragment:_Fragment$8,openBlock:_openBlock$9,createElementBlock:_createElementBlock$9,toDisplayString:_toDisplayString$9,normalizeClass:_normalizeClass$8,createCommentVNode:_createCommentVNode$9,createBlock:_createBlock$9,createTextVNode:_createTextVNode$9,withCtx:_withCtx$9} = await importShared('vue');


const _hoisted_1$9 = { class: "file-tree" };
const _hoisted_2$9 = { class: "file-tree-head" };
const _hoisted_3$9 = { class: "file-tree-search-row" };
const _hoisted_4$9 = {
  key: 0,
  class: "file-tree-roots"
};
const _hoisted_5$9 = ["title", "onClick"];
const _hoisted_6$9 = { class: "file-tree-body" };
const _hoisted_7$8 = {
  key: 0,
  class: "file-tree-tip"
};
const _hoisted_8$7 = {
  key: 2,
  class: "file-tree-tip file-tree-tip--error"
};
const _hoisted_9$7 = {
  key: 0,
  class: "file-tree-list"
};
const _hoisted_10$7 = {
  key: 1,
  class: "file-tree-tip"
};
const _hoisted_11$7 = {
  key: 4,
  class: "file-tree-list"
};
const _hoisted_12$7 = {
  key: 5,
  class: "file-tree-tip"
};

const {computed: computed$8,onMounted: onMounted$1,ref: ref$5,watch: watch$3} = await importShared('vue');


const _sfc_main$9 = {
  __name: 'FileTree',
  props: {
  api: { type: Object, required: true },
  roots: { type: Array, default: () => [] },
  current: { type: String, default: '' },
  kind: { type: String, default: 'video' },
  // 由 AppPage 递增，打开文件/切换页签时触发任务状态刷新
  refreshTick: { type: Number, default: 0 },
},
  emits: ['select'],
  setup(__props, { emit: __emit }) {

/**
 * 左侧媒体目录树：根目录切换 + 懒加载 + 客户端搜索（只列 .mkv）
 */
const props = __props;

const emit = __emit;

const activeRoot = ref$5('');
const keyword = ref$5('');
const nodes = ref$5([]);
const loading = ref$5(false);
const error = ref$5('');
// 文件路径 -> /file-statuses 条目
const statuses = ref$5({});
const statusLoading = ref$5(false);

const rootList = computed$8(() => (Array.isArray(props.roots) ? props.roots.filter(Boolean) : []));

// 把已加载的树拍平成文件列表，供搜索使用
function walk(list, out) {
  for (const node of list) {
    if (node.dir) {
      if (node.children?.length) walk(node.children, out);
    } else {
      out.push(node);
    }
  }
  return out
}

const allFiles = computed$8(() => walk(nodes.value, []));
const searchResults = computed$8(() => {
  const query = keyword.value.trim().toLowerCase();
  if (!query) return []
  return allFiles.value.filter((node) => node.name.toLowerCase().includes(query))
});

async function loadRoot(root) {
  if (!root) {
    nodes.value = [];
    return
  }
  loading.value = true;
  error.value = '';
  try {
    const data = await props.api.post('/fs/list', { root, path: root, kind: props.kind });
    const dirs = (data?.dirs || []).map((item) => ({
      name: item.name,
      path: item.path,
      dir: true,
      expanded: false,
      loaded: false,
      loading: false,
      children: [],
      fileCount: item.file_count ?? null,
    }));
    const files = (data?.files || []).map((item) => ({
      name: item.name,
      path: item.path,
      dir: false,
      size: item.size ?? null,
      ext: item.ext || '',
    }));
    nodes.value = dirs.concat(files);
  } catch (err) {
    nodes.value = [];
    error.value = err.message || '读取目录失败';
  } finally {
    loading.value = false;
  }
}

function chooseRoot(root) {
  if (!root || root === activeRoot.value) return
  activeRoot.value = root;
  keyword.value = '';
  loadRoot(root);
}

function onSelect(path) {
  emit('select', path);
}

/** 拉取文件任务状态（队列优先于历史，后端已按路径去重）。 */
async function loadStatuses() {
  if (statusLoading.value) return
  statusLoading.value = true;
  try {
    const data = await props.api.get('/file-statuses');
    const map = {};
    for (const item of data?.items || []) {
      if (item?.path) map[item.path] = item;
    }
    statuses.value = map;
  } catch (err) {
    // 状态读取失败不影响目录浏览
  } finally {
    statusLoading.value = false;
  }
}

onMounted$1(() => {
  loadStatuses();
  if (rootList.value.length) {
    activeRoot.value = rootList.value[0];
    loadRoot(activeRoot.value);
  }
});

// 打开文件 / 切换页签时刷新任务状态
watch$3(
  () => props.refreshTick,
  () => loadStatuses(),
);
watch$3(
  () => props.current,
  () => loadStatuses(),
);

watch$3(
  rootList,
  (list) => {
    if (!list.length) {
      activeRoot.value = '';
      nodes.value = [];
      return
    }
    if (!list.includes(activeRoot.value)) {
      activeRoot.value = list[0];
      loadRoot(activeRoot.value);
    }
  },
  { deep: true },
);

return (_ctx, _cache) => {
  const _component_v_text_field = _resolveComponent$9("v-text-field");
  const _component_v_btn = _resolveComponent$9("v-btn");
  const _component_v_skeleton_loader = _resolveComponent$9("v-skeleton-loader");

  return (_openBlock$9(), _createElementBlock$9("div", _hoisted_1$9, [
    _createElementVNode$9("div", _hoisted_2$9, [
      _createElementVNode$9("div", _hoisted_3$9, [
        _createVNode$9(_component_v_text_field, {
          modelValue: keyword.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((keyword).value = $event)),
          density: "compact",
          variant: "solo-filled",
          flat: "",
          "hide-details": "",
          placeholder: "搜索片名 / 文件名…",
          "prepend-inner-icon": "mdi-magnify",
          clearable: ""
        }, null, 8, ["modelValue"]),
        _createVNode$9(_component_v_btn, {
          size: "x-small",
          variant: "text",
          icon: "mdi-refresh",
          title: "刷新任务状态",
          loading: statusLoading.value,
          class: "file-tree-refresh",
          onClick: loadStatuses
        }, null, 8, ["loading"])
      ]),
      (rootList.value.length)
        ? (_openBlock$9(), _createElementBlock$9("div", _hoisted_4$9, [
            (_openBlock$9(true), _createElementBlock$9(_Fragment$8, null, _renderList$7(rootList.value, (root) => {
              return (_openBlock$9(), _createElementBlock$9("button", {
                key: root,
                class: _normalizeClass$8(["root-chip", { 'root-chip--active': root === activeRoot.value }]),
                title: root,
                type: "button",
                onClick: $event => (chooseRoot(root))
              }, _toDisplayString$9(root), 11, _hoisted_5$9))
            }), 128))
          ]))
        : _createCommentVNode$9("", true)
    ]),
    _createElementVNode$9("div", _hoisted_6$9, [
      (!rootList.value.length)
        ? (_openBlock$9(), _createElementBlock$9("div", _hoisted_7$8, " 还没有配置媒体根目录，请先到「设置 → 目录」添加。 "))
        : (loading.value)
          ? (_openBlock$9(), _createBlock$9(_component_v_skeleton_loader, {
              key: 1,
              type: "list-item@6"
            }))
          : (error.value)
            ? (_openBlock$9(), _createElementBlock$9("div", _hoisted_8$7, [
                _createTextVNode$9(_toDisplayString$9(error.value) + " ", 1),
                _createVNode$9(_component_v_btn, {
                  size: "small",
                  variant: "text",
                  onClick: _cache[1] || (_cache[1] = $event => (loadRoot(activeRoot.value)))
                }, {
                  default: _withCtx$9(() => [...(_cache[2] || (_cache[2] = [
                    _createTextVNode$9("重试", -1)
                  ]))]),
                  _: 1
                })
              ]))
            : (keyword.value.trim())
              ? (_openBlock$9(), _createElementBlock$9(_Fragment$8, { key: 3 }, [
                  (searchResults.value.length)
                    ? (_openBlock$9(), _createElementBlock$9("div", _hoisted_9$7, [
                        (_openBlock$9(true), _createElementBlock$9(_Fragment$8, null, _renderList$7(searchResults.value, (node) => {
                          return (_openBlock$9(), _createBlock$9(TreeNode, {
                            key: node.path,
                            node: node,
                            api: __props.api,
                            root: activeRoot.value,
                            kind: __props.kind,
                            current: __props.current,
                            statuses: statuses.value,
                            depth: 0,
                            onSelect: onSelect
                          }, null, 8, ["node", "api", "root", "kind", "current", "statuses"]))
                        }), 128))
                      ]))
                    : (_openBlock$9(), _createElementBlock$9("div", _hoisted_10$7, "没有匹配的文件（只搜索已展开的目录）"))
                ], 64))
              : (nodes.value.length)
                ? (_openBlock$9(), _createElementBlock$9("div", _hoisted_11$7, [
                    (_openBlock$9(true), _createElementBlock$9(_Fragment$8, null, _renderList$7(nodes.value, (node) => {
                      return (_openBlock$9(), _createBlock$9(TreeNode, {
                        key: node.path,
                        node: node,
                        api: __props.api,
                        root: activeRoot.value,
                        kind: __props.kind,
                        current: __props.current,
                        statuses: statuses.value,
                        depth: 0,
                        onSelect: onSelect
                      }, null, 8, ["node", "api", "root", "kind", "current", "statuses"]))
                    }), 128))
                  ]))
                : (_openBlock$9(), _createElementBlock$9("div", _hoisted_12$7, "当前根目录下没有子目录或 .mkv 文件"))
    ])
  ]))
}
}

};
const FileTree = /*#__PURE__*/_export_sfc(_sfc_main$9, [['__scopeId',"data-v-839128ab"]]);

const {toDisplayString:_toDisplayString$8,createElementVNode:_createElementVNode$8,createTextVNode:_createTextVNode$8,openBlock:_openBlock$8,createElementBlock:_createElementBlock$8,createCommentVNode:_createCommentVNode$8,renderList:_renderList$6,Fragment:_Fragment$7,resolveComponent:_resolveComponent$8,createVNode:_createVNode$8,unref:_unref$6,withCtx:_withCtx$8,createBlock:_createBlock$8,normalizeClass:_normalizeClass$7,withKeys:_withKeys$2} = await importShared('vue');


const _hoisted_1$8 = { class: "track-card-title" };
const _hoisted_2$8 = { class: "track-card-hint" };
const _hoisted_3$8 = {
  key: 0,
  class: "track-empty"
};
const _hoisted_4$8 = {
  key: 1,
  class: "track-table"
};
const _hoisted_5$8 = {
  key: 0,
  class: "col-channels"
};
const _hoisted_6$8 = { class: "col-no" };
const _hoisted_7$7 = { class: "col-keep" };
const _hoisted_8$6 = { class: "cell-center" };
const _hoisted_9$6 = { class: "track-source" };
const _hoisted_10$6 = { class: "track-codec" };
const _hoisted_11$6 = {
  key: 0,
  class: "track-embedded"
};
const _hoisted_12$6 = { class: "added-source" };
const _hoisted_13$6 = ["title"];
const _hoisted_14$5 = { class: "added-extra" };
const _hoisted_15$5 = {
  key: 0,
  class: "col-channels"
};
const _hoisted_16$5 = { class: "col-lang" };
const _hoisted_17$5 = { class: "col-name" };
const _hoisted_18$5 = { class: "col-switch" };
const _hoisted_19$5 = { class: "cell-center" };
const _hoisted_20$4 = { class: "col-switch" };
const _hoisted_21$4 = { class: "cell-center" };
const _hoisted_22$4 = { class: "col-ops" };
const _hoisted_23$4 = { class: "track-ops" };
const _hoisted_24$4 = {
  key: 2,
  class: "track-cards"
};
const _hoisted_25$4 = { class: "m-track-main" };
const _hoisted_26$3 = { class: "m-track-title" };
const _hoisted_27$3 = { class: "m-track-no" };
const _hoisted_28$3 = {
  key: 0,
  class: "m-track-sub"
};
const _hoisted_29$2 = {
  key: 1,
  class: "m-track-tag"
};
const _hoisted_30$1 = ["title"];
const _hoisted_31$1 = { class: "m-track-fields" };
const _hoisted_32$1 = { class: "m-field-wrap m-field-lang" };
const _hoisted_33$1 = { class: "m-field-wrap m-field-name" };
const _hoisted_34$1 = {
  key: 1,
  class: "m-track-fields"
};
const _hoisted_35$1 = {
  key: 0,
  class: "m-field-wrap m-field-lang"
};
const _hoisted_36$1 = { class: "m-field-wrap m-field-lang" };
const _hoisted_37$1 = { class: "m-track-controls" };
const _hoisted_38$1 = { class: "m-ops" };
const _hoisted_39$1 = { class: "track-add-row" };
const _hoisted_40$1 = { class: "track-hint" };
const _hoisted_41$1 = { class: "custom-lang-body" };
const _hoisted_42$1 = { class: "custom-lang-foot" };

const {computed: computed$7,ref: ref$4} = await importShared('vue');

// 轨道编辑里的编码选项用紧凑文案，避免手机卡片宽度不足被截断
const CUSTOM_LANG = '__custom_lang__';

const _sfc_main$8 = {
  __name: 'TrackEditor',
  props: {
  kind: { type: String, required: true }, // audio | subtitle
  tracks: { type: Array, default: () => [] },
  // narrow: 卡片；medium: 紧凑表格；wide: 普通表格
  layout: { type: String, default: 'wide' },
},
  emits: ['pick', 'upload', 'move', 'remove', 'estimate'],
  setup(__props, { emit: __emit }) {

/**
 * 音频/字幕轨道编辑器：桌面表格 + 手机卡片
 * - 保留勾选（取消 = 删除），新增轨道删除 = 直接移除
 * - ↑↓ 调整顺序（不做拖拽）
 * - 语言 / 轨道名 / 默认 / 强制
 */
const TRACK_ENCODINGS = SUBTITLE_ENCODINGS.map((item) =>
  item.value === 'auto' ? { ...item, title: '自动' } : item,
);

const props = __props;

const emit = __emit;

const narrow = computed$7(() => props.layout === 'narrow');
const medium = computed$7(() => props.layout === 'medium');
const isAudio = computed$7(() => props.kind === 'audio');
const kindLabel = computed$7(() => (isAudio.value ? '音频' : '字幕'));

// 同一类轨道（同页签）内可自由移动，不区分原有/新增
function canMove(track, delta) {
  const list = props.tracks;
  const index = list.findIndex((item) => item === track);
  const target = index + delta;
  return index >= 0 && target >= 0 && target < list.length
}

function move(track, delta) {
  if (!canMove(track, delta)) return
  emit('move', track, delta);
}

function remove(track) {
  emit('remove', track);
}

function toggleKeep(track) {
  // 原有轨道：取消勾选 → 标记删除；新增轨道：取消勾选 → 本次不添加
  track.keep = !track.keep;
}

function addTrack() {
  emit('pick', props.kind);
}

function uploadTrack() {
  emit('upload', props.kind);
}

// 由 AppPage 调 /analyze/offset 并把结果写回 track.sync_ms
function estimate(track) {
  emit('estimate', track);
}

function numberLabel(index) {
  return String(index + 1)
}

function sourceLabel(track) {
  if (!track.added) {
    // 原有字幕轨来自容器内部，标注「内嵌」；原有音频轨只显示编码
    const label = codecLabel(track);
    return props.kind === 'subtitle' ? `${label} · 内嵌` : label
  }
  const name = track.file?.name || track.file?.path || '';
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : '外部文件'
}

// 旧文件的 ISO 代码 / 其它 BCP47 变体统一映射到简体/繁体下拉项
function normalizeLang(value) {
  const code = String(value || 'und').trim();
  const lower = code.toLowerCase();
  if (['chi', 'zho', 'cmn', 'zh', 'zh-cn', 'zh-sg', 'zh-hans'].includes(lower)) return 'zh-Hans'
  if (['zh-tw', 'zh-hk', 'zh-mo', 'zh-hant'].includes(lower)) return 'zh-Hant'
  return code || 'und'
}

function displayLang(track) {
  return normalizeLang(track.language)
}

// 语言下拉：ISO 639-2 / BCP47 代码 + 中文名，支持「自定义…」手动输入
const customLang = ref$4({ open: false, value: '', track: null });

function languageItemsFor(track) {
  const code = normalizeLang(track.language);
  const known = LANGUAGE_ITEMS.some((item) => item.value === code);
  const base = known ? [...LANGUAGE_ITEMS] : [...LANGUAGE_ITEMS, { title: `${code}（自定义）`, value: code }];
  return [...base, { title: '自定义…', value: CUSTOM_LANG }]
}

function onLanguageChange(track, value) {
  if (value === CUSTOM_LANG) {
    customLang.value = { open: true, value: String(track.language || ''), track };
    return
  }
  // 保留 BCP47 大小写（zh-Hant），不要强转小写
  track.language = String(value || '').trim() || 'und';
}

function cancelCustomLang() {
  customLang.value = { open: false, value: '', track: null };
}

function confirmCustomLang() {
  const track = customLang.value.track;
  if (track) track.language = String(customLang.value.value || '').trim() || 'und';
  cancelCustomLang();
}

return (_ctx, _cache) => {
  const _component_v_checkbox_btn = _resolveComponent$8("v-checkbox-btn");
  const _component_v_chip = _resolveComponent$8("v-chip");
  const _component_v_select = _resolveComponent$8("v-select");
  const _component_v_text_field = _resolveComponent$8("v-text-field");
  const _component_v_btn = _resolveComponent$8("v-btn");
  const _component_v_switch = _resolveComponent$8("v-switch");
  const _component_v_spacer = _resolveComponent$8("v-spacer");
  const _component_v_card = _resolveComponent$8("v-card");
  const _component_v_dialog = _resolveComponent$8("v-dialog");

  return (_openBlock$8(), _createBlock$8(_component_v_card, {
    variant: "flat",
    class: _normalizeClass$7(["track-card", { 'track-card--medium': medium.value }])
  }, {
    default: _withCtx$8(() => [
      _createElementVNode$8("div", _hoisted_1$8, [
        _createTextVNode$8(_toDisplayString$8(kindLabel.value) + "轨 ", 1),
        _createElementVNode$8("span", _hoisted_2$8, _toDisplayString$8(isAudio.value ? '取消勾选 = 删除；顺序影响播放器列表' : '取消勾选 = 删除；新增字幕来自同级文件或上传'), 1)
      ]),
      (!__props.tracks.length)
        ? (_openBlock$8(), _createElementBlock$8("div", _hoisted_3$8, " 暂无" + _toDisplayString$8(kindLabel.value) + "轨。" + _toDisplayString$8(isAudio.value ? '可管理已有轨道，或从目录/上传音频文件新增。' : '可从目录选择或上传字幕文件新增。'), 1))
        : (!narrow.value)
          ? (_openBlock$8(), _createElementBlock$8("table", _hoisted_4$8, [
              _createElementVNode$8("thead", null, [
                _createElementVNode$8("tr", null, [
                  _cache[2] || (_cache[2] = _createElementVNode$8("th", { class: "col-no" }, "#", -1)),
                  _cache[3] || (_cache[3] = _createElementVNode$8("th", { class: "col-keep" }, "保留", -1)),
                  _createElementVNode$8("th", null, _toDisplayString$8(isAudio.value ? '编码 / 来源' : '格式 / 来源'), 1),
                  (isAudio.value)
                    ? (_openBlock$8(), _createElementBlock$8("th", _hoisted_5$8, "声道"))
                    : _createCommentVNode$8("", true),
                  _cache[4] || (_cache[4] = _createElementVNode$8("th", { class: "col-lang" }, "语言", -1)),
                  _cache[5] || (_cache[5] = _createElementVNode$8("th", { class: "col-name" }, "轨道名", -1)),
                  _cache[6] || (_cache[6] = _createElementVNode$8("th", { class: "col-switch" }, "默认", -1)),
                  _cache[7] || (_cache[7] = _createElementVNode$8("th", { class: "col-switch" }, "强制", -1)),
                  _cache[8] || (_cache[8] = _createElementVNode$8("th", { class: "col-ops" }, null, -1))
                ])
              ]),
              _createElementVNode$8("tbody", null, [
                (_openBlock$8(true), _createElementBlock$8(_Fragment$7, null, _renderList$6(__props.tracks, (track, index) => {
                  return (_openBlock$8(), _createElementBlock$8("tr", {
                    key: track.id,
                    class: _normalizeClass$7({ dropping: !track.keep })
                  }, [
                    _createElementVNode$8("td", _hoisted_6$8, _toDisplayString$8(numberLabel(index)), 1),
                    _createElementVNode$8("td", _hoisted_7$7, [
                      _createElementVNode$8("div", _hoisted_8$6, [
                        _createVNode$8(_component_v_checkbox_btn, {
                          "model-value": track.keep,
                          density: "compact",
                          color: "primary",
                          "hide-details": "",
                          "aria-label": `保留${kindLabel.value}轨 ${numberLabel(index)}`,
                          "onUpdate:modelValue": $event => (toggleKeep(track))
                        }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"])
                      ])
                    ]),
                    _createElementVNode$8("td", _hoisted_9$6, [
                      (!track.added)
                        ? (_openBlock$8(), _createElementBlock$8(_Fragment$7, { key: 0 }, [
                            _createElementVNode$8("span", _hoisted_10$6, _toDisplayString$8(_unref$6(codecLabel)(track)), 1),
                            (__props.kind === 'subtitle')
                              ? (_openBlock$8(), _createElementBlock$8("span", _hoisted_11$6, "· 内嵌"))
                              : _createCommentVNode$8("", true)
                          ], 64))
                        : (_openBlock$8(), _createElementBlock$8(_Fragment$7, { key: 1 }, [
                            _createElementVNode$8("div", _hoisted_12$6, [
                              _createVNode$8(_component_v_chip, {
                                size: "x-small",
                                variant: "tonal",
                                color: "primary",
                                class: "added-tag"
                              }, {
                                default: _withCtx$8(() => [...(_cache[9] || (_cache[9] = [
                                  _createTextVNode$8("新增", -1)
                                ]))]),
                                _: 1
                              }),
                              _createElementVNode$8("span", {
                                class: "added-file",
                                title: track.file?.path
                              }, _toDisplayString$8(sourceLabel(track)) + " · " + _toDisplayString$8(track.file?.name), 9, _hoisted_13$6)
                            ]),
                            _createElementVNode$8("div", _hoisted_14$5, [
                              (!isAudio.value)
                                ? (_openBlock$8(), _createBlock$8(_component_v_select, {
                                    key: 0,
                                    modelValue: track.encoding,
                                    "onUpdate:modelValue": $event => ((track.encoding) = $event),
                                    items: _unref$6(TRACK_ENCODINGS),
                                    density: "compact",
                                    variant: "outlined",
                                    "hide-details": "",
                                    class: "encoding-select",
                                    title: "字幕文件编码"
                                  }, null, 8, ["modelValue", "onUpdate:modelValue", "items"]))
                                : _createCommentVNode$8("", true),
                              _createVNode$8(_component_v_text_field, {
                                modelValue: track.sync_ms,
                                "onUpdate:modelValue": $event => ((track.sync_ms) = $event),
                                modelModifiers: { number: true },
                                type: "number",
                                density: "compact",
                                variant: "outlined",
                                "hide-details": "",
                                placeholder: "0",
                                suffix: "ms",
                                class: "sync-input",
                                title: isAudio.value ? '音轨延迟校正（毫秒，正数=延后）' : '字幕延迟校正（毫秒，正数=延后）'
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "title"]),
                              _createVNode$8(_component_v_btn, {
                                size: "x-small",
                                variant: "tonal",
                                "prepend-icon": "mdi-timer-sync-outline",
                                class: "estimate-btn",
                                loading: Boolean(track._estimating),
                                disabled: Boolean(track._estimating) || !track.file?.path,
                                title: track._offsetHint || '用 ffmpeg 估计与视频的偏移（实验功能，结果需自行确认）',
                                onClick: $event => (estimate(track))
                              }, {
                                default: _withCtx$8(() => [...(_cache[10] || (_cache[10] = [
                                  _createTextVNode$8(" 估偏移 ", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading", "disabled", "title", "onClick"])
                            ])
                          ], 64))
                    ]),
                    (isAudio.value)
                      ? (_openBlock$8(), _createElementBlock$8("td", _hoisted_15$5, _toDisplayString$8(track.added ? '—' : _unref$6(fmtChannels)(track)), 1))
                      : _createCommentVNode$8("", true),
                    _createElementVNode$8("td", _hoisted_16$5, [
                      _createVNode$8(_component_v_select, {
                        "model-value": displayLang(track),
                        items: languageItemsFor(track),
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        class: "lang-input lang-select",
                        placeholder: "und",
                        "aria-label": `${kindLabel.value}轨 ${numberLabel(index)} 语言`,
                        "onUpdate:modelValue": $event => (onLanguageChange(track, $event))
                      }, null, 8, ["model-value", "items", "aria-label", "onUpdate:modelValue"])
                    ]),
                    _createElementVNode$8("td", _hoisted_17$5, [
                      _createVNode$8(_component_v_text_field, {
                        modelValue: track.name,
                        "onUpdate:modelValue": $event => ((track.name) = $event),
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        placeholder: "轨道名",
                        "aria-label": `${kindLabel.value}轨 ${numberLabel(index)} 名称`
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "aria-label"])
                    ]),
                    _createElementVNode$8("td", _hoisted_18$5, [
                      _createElementVNode$8("div", _hoisted_19$5, [
                        _createVNode$8(_component_v_switch, {
                          modelValue: track.default,
                          "onUpdate:modelValue": $event => ((track.default) = $event),
                          density: "compact",
                          color: "primary",
                          "hide-details": "",
                          "aria-label": `${kindLabel.value}轨 ${numberLabel(index)} 默认`
                        }, null, 8, ["modelValue", "onUpdate:modelValue", "aria-label"])
                      ])
                    ]),
                    _createElementVNode$8("td", _hoisted_20$4, [
                      _createElementVNode$8("div", _hoisted_21$4, [
                        _createVNode$8(_component_v_switch, {
                          modelValue: track.forced,
                          "onUpdate:modelValue": $event => ((track.forced) = $event),
                          density: "compact",
                          color: "primary",
                          "hide-details": "",
                          "aria-label": `${kindLabel.value}轨 ${numberLabel(index)} 强制`
                        }, null, 8, ["modelValue", "onUpdate:modelValue", "aria-label"])
                      ])
                    ]),
                    _createElementVNode$8("td", _hoisted_22$4, [
                      _createElementVNode$8("div", _hoisted_23$4, [
                        _createVNode$8(_component_v_btn, {
                          size: "x-small",
                          variant: "tonal",
                          icon: "mdi-arrow-up",
                          disabled: !canMove(track, -1),
                          title: "上移",
                          onClick: $event => (move(track, -1))
                        }, null, 8, ["disabled", "onClick"]),
                        _createVNode$8(_component_v_btn, {
                          size: "x-small",
                          variant: "tonal",
                          icon: "mdi-arrow-down",
                          disabled: !canMove(track, 1),
                          title: "下移",
                          onClick: $event => (move(track, 1))
                        }, null, 8, ["disabled", "onClick"]),
                        _createVNode$8(_component_v_btn, {
                          size: "x-small",
                          variant: "tonal",
                          icon: !track.added && !track.keep ? 'mdi-restore' : 'mdi-close',
                          title: !track.added && !track.keep ? '恢复该轨道' : (track.added ? '移除新增' : '标记删除'),
                          onClick: $event => (remove(track))
                        }, null, 8, ["icon", "title", "onClick"])
                      ])
                    ])
                  ], 2))
                }), 128))
              ])
            ]))
          : (_openBlock$8(), _createElementBlock$8("div", _hoisted_24$4, [
              (_openBlock$8(true), _createElementBlock$8(_Fragment$7, null, _renderList$6(__props.tracks, (track, index) => {
                return (_openBlock$8(), _createElementBlock$8("div", {
                  key: track.id,
                  class: _normalizeClass$7(["m-track", { dropping: !track.keep }])
                }, [
                  _createVNode$8(_component_v_checkbox_btn, {
                    "model-value": track.keep,
                    density: "compact",
                    color: "primary",
                    "hide-details": "",
                    class: "m-track-check",
                    "onUpdate:modelValue": $event => (toggleKeep(track))
                  }, null, 8, ["model-value", "onUpdate:modelValue"]),
                  _createElementVNode$8("div", _hoisted_25$4, [
                    _createElementVNode$8("div", _hoisted_26$3, [
                      _createElementVNode$8("span", _hoisted_27$3, _toDisplayString$8(numberLabel(index)), 1),
                      _createElementVNode$8("span", null, _toDisplayString$8(sourceLabel(track)), 1),
                      (isAudio.value && !track.added)
                        ? (_openBlock$8(), _createElementBlock$8("span", _hoisted_28$3, _toDisplayString$8(_unref$6(fmtChannels)(track)), 1))
                        : _createCommentVNode$8("", true),
                      (track.added)
                        ? (_openBlock$8(), _createElementBlock$8("span", _hoisted_29$2, "新增"))
                        : _createCommentVNode$8("", true)
                    ]),
                    (track.added)
                      ? (_openBlock$8(), _createElementBlock$8("div", {
                          key: 0,
                          class: "m-track-file",
                          title: track.file?.path
                        }, _toDisplayString$8(track.file?.name), 9, _hoisted_30$1))
                      : _createCommentVNode$8("", true),
                    _createElementVNode$8("div", _hoisted_31$1, [
                      _createElementVNode$8("div", _hoisted_32$1, [
                        _cache[11] || (_cache[11] = _createElementVNode$8("span", { class: "m-field-cap" }, "语言", -1)),
                        _createVNode$8(_component_v_select, {
                          "model-value": displayLang(track),
                          items: languageItemsFor(track),
                          placeholder: "und",
                          density: "compact",
                          variant: "outlined",
                          "hide-details": "",
                          class: "m-lang-select",
                          "onUpdate:modelValue": $event => (onLanguageChange(track, $event))
                        }, null, 8, ["model-value", "items", "onUpdate:modelValue"])
                      ]),
                      _createElementVNode$8("div", _hoisted_33$1, [
                        _cache[12] || (_cache[12] = _createElementVNode$8("span", { class: "m-field-cap" }, "轨道名", -1)),
                        _createVNode$8(_component_v_text_field, {
                          modelValue: track.name,
                          "onUpdate:modelValue": $event => ((track.name) = $event),
                          placeholder: "轨道名",
                          density: "compact",
                          variant: "outlined",
                          "hide-details": ""
                        }, null, 8, ["modelValue", "onUpdate:modelValue"])
                      ])
                    ]),
                    (track.added)
                      ? (_openBlock$8(), _createElementBlock$8("div", _hoisted_34$1, [
                          (!isAudio.value)
                            ? (_openBlock$8(), _createElementBlock$8("div", _hoisted_35$1, [
                                _cache[13] || (_cache[13] = _createElementVNode$8("span", { class: "m-field-cap" }, "字幕编码", -1)),
                                _createVNode$8(_component_v_select, {
                                  modelValue: track.encoding,
                                  "onUpdate:modelValue": $event => ((track.encoding) = $event),
                                  items: _unref$6(TRACK_ENCODINGS),
                                  density: "compact",
                                  variant: "outlined",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue", "items"])
                              ]))
                            : _createCommentVNode$8("", true),
                          _createElementVNode$8("div", _hoisted_36$1, [
                            _cache[14] || (_cache[14] = _createElementVNode$8("span", { class: "m-field-cap" }, "延迟（ms）", -1)),
                            _createVNode$8(_component_v_text_field, {
                              modelValue: track.sync_ms,
                              "onUpdate:modelValue": $event => ((track.sync_ms) = $event),
                              modelModifiers: { number: true },
                              type: "number",
                              placeholder: "0",
                              density: "compact",
                              variant: "outlined",
                              "hide-details": ""
                            }, null, 8, ["modelValue", "onUpdate:modelValue"])
                          ]),
                          _createVNode$8(_component_v_btn, {
                            class: "m-estimate",
                            size: "small",
                            variant: "tonal",
                            "prepend-icon": "mdi-timer-sync-outline",
                            loading: Boolean(track._estimating),
                            disabled: Boolean(track._estimating) || !track.file?.path,
                            title: track._offsetHint || '用 ffmpeg 估计与视频的偏移（实验功能，结果需自行确认）',
                            onClick: $event => (estimate(track))
                          }, {
                            default: _withCtx$8(() => [...(_cache[15] || (_cache[15] = [
                              _createTextVNode$8(" 估偏移 ", -1)
                            ]))]),
                            _: 1
                          }, 8, ["loading", "disabled", "title", "onClick"])
                        ]))
                      : _createCommentVNode$8("", true),
                    _createElementVNode$8("div", _hoisted_37$1, [
                      _createVNode$8(_component_v_switch, {
                        modelValue: track.default,
                        "onUpdate:modelValue": $event => ((track.default) = $event),
                        label: "默认",
                        density: "compact",
                        color: "primary",
                        "hide-details": "",
                        class: "m-switch"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                      _createVNode$8(_component_v_switch, {
                        modelValue: track.forced,
                        "onUpdate:modelValue": $event => ((track.forced) = $event),
                        label: "强制",
                        density: "compact",
                        color: "primary",
                        "hide-details": "",
                        class: "m-switch"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                      _createVNode$8(_component_v_spacer),
                      _createElementVNode$8("div", _hoisted_38$1, [
                        _createVNode$8(_component_v_btn, {
                          size: "small",
                          variant: "tonal",
                          icon: "mdi-arrow-up",
                          disabled: !canMove(track, -1),
                          onClick: $event => (move(track, -1))
                        }, null, 8, ["disabled", "onClick"]),
                        _createVNode$8(_component_v_btn, {
                          size: "small",
                          variant: "tonal",
                          icon: "mdi-arrow-down",
                          disabled: !canMove(track, 1),
                          onClick: $event => (move(track, 1))
                        }, null, 8, ["disabled", "onClick"]),
                        _createVNode$8(_component_v_btn, {
                          size: "small",
                          variant: "tonal",
                          icon: !track.added && !track.keep ? 'mdi-restore' : 'mdi-close',
                          onClick: $event => (remove(track))
                        }, null, 8, ["icon", "onClick"])
                      ])
                    ])
                  ])
                ], 2))
              }), 128))
            ])),
      _createElementVNode$8("div", _hoisted_39$1, [
        _createVNode$8(_component_v_btn, {
          size: "small",
          variant: "tonal",
          "prepend-icon": "mdi-folder-open-outline",
          onClick: addTrack
        }, {
          default: _withCtx$8(() => [
            _createTextVNode$8(" 从目录选择" + _toDisplayString$8(kindLabel.value), 1)
          ]),
          _: 1
        }),
        _createVNode$8(_component_v_btn, {
          size: "small",
          variant: "text",
          "prepend-icon": "mdi-upload-outline",
          onClick: uploadTrack
        }, {
          default: _withCtx$8(() => [
            _createTextVNode$8(" 上传" + _toDisplayString$8(kindLabel.value), 1)
          ]),
          _: 1
        })
      ]),
      _createElementVNode$8("div", _hoisted_40$1, [
        (isAudio.value)
          ? (_openBlock$8(), _createElementBlock$8(_Fragment$7, { key: 0 }, [
              _createTextVNode$8(" 支持 aac / flac / mka / ac3 / dts / mp3 / m4a；音频文件通常超过上传上限，建议用目录选择 ")
            ], 64))
          : (_openBlock$8(), _createElementBlock$8(_Fragment$7, { key: 1 }, [
              _createTextVNode$8(" 内封 srt / ass / ssa / vtt；编码可自动探测或强制 GBK / BIG5 ")
            ], 64))
      ]),
      _createVNode$8(_component_v_dialog, {
        modelValue: customLang.value.open,
        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((customLang.value.open) = $event)),
        "max-width": "440"
      }, {
        default: _withCtx$8(() => [
          _createVNode$8(_component_v_card, { class: "custom-lang-dialog" }, {
            default: _withCtx$8(() => [
              _cache[19] || (_cache[19] = _createElementVNode$8("div", { class: "custom-lang-title" }, "自定义语言代码", -1)),
              _createElementVNode$8("div", _hoisted_41$1, [
                _createVNode$8(_component_v_text_field, {
                  modelValue: customLang.value.value,
                  "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((customLang.value.value) = $event)),
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  placeholder: "chi / jpn / zh-CN",
                  autofocus: "",
                  onKeyup: _withKeys$2(confirmCustomLang, ["enter"])
                }, null, 8, ["modelValue"]),
                _cache[16] || (_cache[16] = _createElementVNode$8("div", { class: "custom-lang-hint" }, "需 ISO 639-2 / BCP 47 代码，如 chi、jpn、zh-CN；留空则使用 und", -1))
              ]),
              _createElementVNode$8("div", _hoisted_42$1, [
                _createVNode$8(_component_v_btn, {
                  variant: "text",
                  onClick: cancelCustomLang
                }, {
                  default: _withCtx$8(() => [...(_cache[17] || (_cache[17] = [
                    _createTextVNode$8("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$8(_component_v_btn, {
                  color: "primary",
                  variant: "flat",
                  onClick: confirmCustomLang
                }, {
                  default: _withCtx$8(() => [...(_cache[18] || (_cache[18] = [
                    _createTextVNode$8("确定", -1)
                  ]))]),
                  _: 1
                })
              ])
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"])
    ]),
    _: 1
  }, 8, ["class"]))
}
}

};
const TrackEditor = /*#__PURE__*/_export_sfc(_sfc_main$8, [['__scopeId',"data-v-e9ba9172"]]);

const {toDisplayString:_toDisplayString$7,createElementVNode:_createElementVNode$7,resolveComponent:_resolveComponent$7,createVNode:_createVNode$7,createTextVNode:_createTextVNode$7,withCtx:_withCtx$7,openBlock:_openBlock$7,createElementBlock:_createElementBlock$7,createCommentVNode:_createCommentVNode$7,renderList:_renderList$5,Fragment:_Fragment$6,normalizeClass:_normalizeClass$6,createBlock:_createBlock$7} = await importShared('vue');


const _hoisted_1$7 = { class: "sibling-title" };
const _hoisted_2$7 = { class: "sibling-hint" };
const _hoisted_3$7 = {
  key: 0,
  class: "sibling-empty"
};
const _hoisted_4$7 = {
  key: 1,
  class: "sibling-grid"
};
const _hoisted_5$7 = { class: "sib-check" };
const _hoisted_6$7 = ["title"];
const _hoisted_7$6 = { class: "sibling-tag" };

const {computed: computed$6} = await importShared('vue');



const _sfc_main$7 = {
  __name: 'SiblingPanel',
  props: {
  // 全部候选（AppPage 已按 kind 分组好的扁平列表）
  items: { type: Array, default: () => [] },
  // narrow 单列；medium/wide 两列
  layout: { type: String, default: 'wide' },
  // 当前页签类型：subtitle | audio | font
  kind: { type: String, default: 'subtitle' },
  // 当前类型候选是否都已由自动导入/挂载按钮挂载
  mounted: { type: Boolean, default: false },
},
  emits: ['toggle', 'mount-toggle'],
  setup(__props, { emit: __emit }) {

/**
 * 同级自动发现（按页签分类型显示）：
 * 字幕页只看同名字幕、音频页只看同名音频、附件页只看同目录字体；
 * 勾选 = 作为新增轨道 / 附件写入，不复制、不移动原文件
 */
const props = __props;

const narrow = computed$6(() => props.layout === 'narrow');
const emit = __emit;

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
};
const meta = computed$6(() => KIND_META[props.kind] || KIND_META.subtitle);

// 只渲染当前页签对应类型
const kindItems = computed$6(() => props.items.filter((item) => item.kind === props.kind));
// 字幕/音频只挂载前缀匹配项；字体全部可挂载
const matchedCount = computed$6(() =>
  props.kind === 'font' ? kindItems.value.length : kindItems.value.filter((item) => item.matched).length,
);

function tagText(item) {
  const lang = item.language || '';
  const ext = String(item.ext || '').replace('.', '').toUpperCase();
  return [lang, ext].filter(Boolean).join(' · ')
}

function confirmToggle(item, value) {
  emit('toggle', item, value);
}

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent$7("v-spacer");
  const _component_v_btn = _resolveComponent$7("v-btn");
  const _component_v_checkbox_btn = _resolveComponent$7("v-checkbox-btn");
  const _component_v_card = _resolveComponent$7("v-card");

  return (_openBlock$7(), _createBlock$7(_component_v_card, {
    variant: "flat",
    class: _normalizeClass$6(["sibling-card", { 'sibling-card--narrow': narrow.value }])
  }, {
    default: _withCtx$7(() => [
      _createElementVNode$7("div", _hoisted_1$7, [
        _createTextVNode$7(" 同级自动发现 · " + _toDisplayString$7(meta.value.label) + " ", 1),
        _createElementVNode$7("span", _hoisted_2$7, _toDisplayString$7(meta.value.hint), 1),
        _createVNode$7(_component_v_spacer),
        _createVNode$7(_component_v_btn, {
          size: "small",
          variant: __props.mounted ? 'flat' : 'tonal',
          color: __props.mounted ? 'success' : undefined,
          "prepend-icon": __props.mounted ? 'mdi-check-circle-outline' : 'mdi-auto-fix',
          disabled: !__props.mounted && !matchedCount.value,
          title: __props.mounted ? '收回由自动导入/挂载加入的条目（手动添加的不会被删除）' : meta.value.mountTip,
          onClick: _cache[0] || (_cache[0] = $event => (emit('mount-toggle')))
        }, {
          default: _withCtx$7(() => [
            _createTextVNode$7(_toDisplayString$7(__props.mounted ? '已挂载 · 点击收回' : '挂载'), 1)
          ]),
          _: 1
        }, 8, ["variant", "color", "prepend-icon", "disabled", "title"])
      ]),
      (!kindItems.value.length)
        ? (_openBlock$7(), _createElementBlock$7("div", _hoisted_3$7, _toDisplayString$7(meta.value.empty), 1))
        : (_openBlock$7(), _createElementBlock$7("div", _hoisted_4$7, [
            (_openBlock$7(true), _createElementBlock$7(_Fragment$6, null, _renderList$5(kindItems.value, (item) => {
              return (_openBlock$7(), _createElementBlock$7("label", {
                key: item.key,
                class: "sibling-row"
              }, [
                _createElementVNode$7("span", _hoisted_5$7, [
                  _createVNode$7(_component_v_checkbox_btn, {
                    "model-value": item.checked,
                    density: "compact",
                    color: "primary",
                    "hide-details": "",
                    "onUpdate:modelValue": $event => (confirmToggle(item, $event))
                  }, null, 8, ["model-value", "onUpdate:modelValue"])
                ]),
                _createElementVNode$7("span", {
                  class: "sibling-name",
                  title: item.path
                }, _toDisplayString$7(item.name), 9, _hoisted_6$7),
                _createElementVNode$7("span", _hoisted_7$6, _toDisplayString$7(tagText(item)), 1)
              ]))
            }), 128))
          ]))
    ]),
    _: 1
  }, 8, ["class"]))
}
}

};
const SiblingPanel = /*#__PURE__*/_export_sfc(_sfc_main$7, [['__scopeId',"data-v-2b70ade4"]]);

const {toDisplayString:_toDisplayString$6,createElementVNode:_createElementVNode$6,resolveComponent:_resolveComponent$6,createVNode:_createVNode$6,openBlock:_openBlock$6,createBlock:_createBlock$6,createCommentVNode:_createCommentVNode$6,createTextVNode:_createTextVNode$6,createElementBlock:_createElementBlock$6,unref:_unref$5,renderList:_renderList$4,Fragment:_Fragment$5,withCtx:_withCtx$6,normalizeClass:_normalizeClass$5} = await importShared('vue');


const _hoisted_1$6 = { class: "preview-head" };
const _hoisted_2$6 = { class: "preview-title" };
const _hoisted_3$6 = { class: "preview-body" };
const _hoisted_4$6 = { class: "preview-path" };
const _hoisted_5$6 = { class: "preview-summary" };
const _hoisted_6$6 = { class: "sum-item" };
const _hoisted_7$5 = { class: "sum-item" };
const _hoisted_8$5 = {
  key: 0,
  class: "sum-item sum-add"
};
const _hoisted_9$5 = { class: "sum-note" };
const _hoisted_10$5 = {
  key: 1,
  class: "sum-item sum-add"
};
const _hoisted_11$5 = { class: "sum-note" };
const _hoisted_12$5 = {
  key: 2,
  class: "sum-item sum-add"
};
const _hoisted_13$5 = { class: "sum-note" };
const _hoisted_14$4 = { class: "sum-k" };
const _hoisted_15$4 = { class: "sum-note" };
const _hoisted_16$4 = { class: "sum-item" };
const _hoisted_17$4 = { class: "sum-item" };
const _hoisted_18$4 = { class: "preview-out" };
const _hoisted_19$4 = {
  key: 0,
  class: "preview-nobackup"
};
const _hoisted_20$3 = {
  key: 0,
  class: "preview-backup-path"
};
const _hoisted_21$3 = { key: 2 };
const _hoisted_22$3 = {
  key: 0,
  class: "warnbox warnbox--red"
};
const _hoisted_23$3 = {
  key: 1,
  class: "duration-confirm"
};
const _hoisted_24$3 = {
  key: 2,
  class: "preview-cmd"
};
const _hoisted_25$3 = {
  key: 3,
  class: "preview-empty-cmd"
};
const _hoisted_26$2 = { class: "preview-foot" };
const _hoisted_27$2 = { class: "preview-foot-note" };
const _hoisted_28$2 = { class: "preview-foot-btns" };

const {computed: computed$5} = await importShared('vue');

const {useDisplay: useDisplay$3} = await importShared('vuetify');


const _sfc_main$6 = {
  __name: 'PreviewDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  path: { type: String, default: '' },
  result: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
  engineReady: { type: Boolean, default: true },
  title: { type: String, default: '确认执行' },
  confirmText: { type: String, default: '确认执行' },
  // duration_mismatch 警告强制勾选状态由父级持有（确认后随 plan 提交）
  confirmed: { type: Boolean, default: false },
  // 布局三档：narrow 全屏；medium/wide 窗口弹窗（不传则按视口回退）
  layout: { type: String, default: '' },
},
  emits: ['update:modelValue', 'update:confirmed', 'confirm'],
  setup(__props, { emit: __emit }) {

/**
 * 预览确认弹窗：展示 /plan 的执行引擎、变更摘要、输出/空间、warnings 与 blockers，
 * blockers 非空时禁止提交；命令详情可展开。
 */
const props = __props;

const emit = __emit;
const display = useDisplay$3();
const effectiveLayout = computed$5(() => props.layout || (display.mdAndUp.value ? 'wide' : 'narrow'));
const mobile = computed$5(() => effectiveLayout.value === 'narrow');

const CHANGES_MAP = { keep: '保留', clear: '清空', import: '导入', none: '不写入' };
const ENGINE_MAP = { mkvmerge: 'mkvmerge（重封装）', ffmpeg: 'ffmpeg（降级执行）', none: '未检测到引擎' };

const changes = computed$5(() => props.result?.changes || {});
const warnings = computed$5(() => (Array.isArray(props.result?.warnings) ? props.result.warnings : []));
const blockers = computed$5(() => (Array.isArray(props.result?.blockers) ? props.result.blockers : []));

const addedTracks = computed$5(() => (Array.isArray(changes.value.add) ? changes.value.add : []));
const addedSubtitles = computed$5(() => addedTracks.value.filter((item) => item.kind === 'subtitle'));
const addedAudios = computed$5(() => addedTracks.value.filter((item) => item.kind === 'audio'));
const dropped = computed$5(() => (Array.isArray(changes.value.drop) ? changes.value.drop : []));
const edits = computed$5(() => (Array.isArray(changes.value.edit) ? changes.value.edit : []));
const attachmentsAdd = computed$5(() =>
  Array.isArray(changes.value.attachments_add) ? changes.value.attachments_add : [],
);
const attachmentsDrop = computed$5(() =>
  Array.isArray(changes.value.attachments_drop) ? changes.value.attachments_drop : [],
);
const commands = computed$5(() => (Array.isArray(props.result?.commands) ? props.result.commands : []));
// 时长不一致警告：必须显式勾选后才能确认（后端 code 固定为 duration_mismatch）
const durationWarnings = computed$5(() =>
  warnings.value.filter((item) => (item?.code || '') === 'duration_mismatch'),
);
const hasDurationMismatch = computed$5(() => durationWarnings.value.length > 0);
const canSubmit = computed$5(
  () =>
    props.engineReady &&
    !blockers.value.length &&
    !props.loading &&
    !props.submitting &&
    (!hasDurationMismatch.value || props.confirmed),
);

const engineText = computed$5(() => ENGINE_MAP[props.result?.engine] || props.result?.engine || '—');
const chaptersText = computed$5(() => {
  const raw = changes.value.chapters;
  if (raw == null) return '—'
  if (typeof raw === 'object') {
    return CHANGES_MAP[raw.mode] || raw.mode || '—'
  }
  return CHANGES_MAP[raw] || String(raw)
});
const spaceText = computed$5(() => {
  const space = props.result?.space;
  if (!space) return ''
  const need = fmtBytes(space.need);
  const free = fmtBytes(space.free);
  const enough = Number(space.free) >= Number(space.need);
  return `需要空间：约 ${need}（剩余 ${free} ${enough ? '✓' : '✗'}）`
});
const titleText = computed$5(() => changes.value.title || '—');
const fileLabel = computed$5(() => baseName(props.path || props.result?.output_path || ''));

function commandText(command) {
  if (typeof command === 'string') return command
  if (command.display) return command.display
  if (command.tool && Array.isArray(command.args)) return `${command.tool} ${command.args.join(' ')}`
  return JSON.stringify(command)
}

function close() {
  emit('update:modelValue', false);
}

function confirm() {
  if (!canSubmit.value) return
  emit('confirm');
}

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent$6("v-spacer");
  const _component_v_btn = _resolveComponent$6("v-btn");
  const _component_v_skeleton_loader = _resolveComponent$6("v-skeleton-loader");
  const _component_v_checkbox = _resolveComponent$6("v-checkbox");
  const _component_v_alert = _resolveComponent$6("v-alert");
  const _component_v_card = _resolveComponent$6("v-card");
  const _component_v_dialog = _resolveComponent$6("v-dialog");

  return (_openBlock$6(), _createBlock$6(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": mobile.value ? undefined : 820,
    fullscreen: mobile.value,
    scrollable: "",
    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => (emit('update:modelValue', $event)))
  }, {
    default: _withCtx$6(() => [
      _createVNode$6(_component_v_card, {
        class: _normalizeClass$5(["preview-dialog", { 'dialog-compact': mobile.value, 'dialog-medium': effectiveLayout.value === 'medium' }])
      }, {
        default: _withCtx$6(() => [
          _createElementVNode$6("div", _hoisted_1$6, [
            _createElementVNode$6("span", _hoisted_2$6, _toDisplayString$6(__props.title || '确认执行'), 1),
            _createVNode$6(_component_v_spacer),
            _createVNode$6(_component_v_btn, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              "aria-label": "关闭",
              onClick: close
            })
          ]),
          _createElementVNode$6("div", _hoisted_3$6, [
            _createElementVNode$6("div", _hoisted_4$6, _toDisplayString$6(__props.path), 1),
            (__props.loading && !__props.result)
              ? (_openBlock$6(), _createBlock$6(_component_v_skeleton_loader, {
                  key: 0,
                  type: "list-item-three-line, list-item@3"
                }))
              : (__props.result)
                ? (_openBlock$6(), _createElementBlock$6(_Fragment$5, { key: 1 }, [
                    _createElementVNode$6("div", _hoisted_5$6, [
                      _createElementVNode$6("div", _hoisted_6$6, [
                        _cache[2] || (_cache[2] = _createElementVNode$6("span", { class: "sum-k" }, "执行引擎：", -1)),
                        _createTextVNode$6(_toDisplayString$6(engineText.value), 1)
                      ]),
                      _createElementVNode$6("div", _hoisted_7$5, [
                        _cache[3] || (_cache[3] = _createElementVNode$6("span", { class: "sum-k" }, "保留轨道：", -1)),
                        _createTextVNode$6(_toDisplayString$6(changes.value.keep ?? '—') + " 条", 1)
                      ]),
                      (addedSubtitles.value.length)
                        ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_8$5, [
                            _createTextVNode$6(" ＋ 新增字幕 " + _toDisplayString$6(addedSubtitles.value.length) + " 条 ", 1),
                            _createElementVNode$6("span", _hoisted_9$5, _toDisplayString$6(addedSubtitles.value.map((item) => item.name || item.file).join('、')), 1)
                          ]))
                        : _createCommentVNode$6("", true),
                      (addedAudios.value.length)
                        ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_10$5, [
                            _createTextVNode$6(" ＋ 新增音轨 " + _toDisplayString$6(addedAudios.value.length) + " 条 ", 1),
                            _createElementVNode$6("span", _hoisted_11$5, _toDisplayString$6(addedAudios.value.map((item) => item.name || item.file).join('、')), 1)
                          ]))
                        : _createCommentVNode$6("", true),
                      (attachmentsAdd.value.length)
                        ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_12$5, [
                            _createTextVNode$6(" ＋ 字体附件 " + _toDisplayString$6(attachmentsAdd.value.length) + " 个 ", 1),
                            _createElementVNode$6("span", _hoisted_13$5, _toDisplayString$6(attachmentsAdd.value.map((item) => _unref$5(baseName)(item)).join('、')), 1)
                          ]))
                        : _createCommentVNode$6("", true),
                      (_openBlock$6(true), _createElementBlock$6(_Fragment$5, null, _renderList$4(dropped.value, (item) => {
                        return (_openBlock$6(), _createElementBlock$6("div", {
                          key: `drop-${item.id}`,
                          class: "sum-item sum-del"
                        }, " ✕ 删除" + _toDisplayString$6(item.type === 'audio' ? '音轨' : item.type === 'subtitle' ? '字幕' : item.type || '轨道') + " " + _toDisplayString$6(item.name || `#${item.id}`), 1))
                      }), 128)),
                      (_openBlock$6(true), _createElementBlock$6(_Fragment$5, null, _renderList$4(attachmentsDrop.value, (item) => {
                        return (_openBlock$6(), _createElementBlock$6("div", {
                          key: `ad-${item}`,
                          class: "sum-item sum-del"
                        }, " ✕ 删除字体附件 " + _toDisplayString$6(item), 1))
                      }), 128)),
                      (_openBlock$6(true), _createElementBlock$6(_Fragment$5, null, _renderList$4(edits.value, (item) => {
                        return (_openBlock$6(), _createElementBlock$6("div", {
                          key: `edit-${item.id}-${item.field}`,
                          class: "sum-item"
                        }, [
                          _createElementVNode$6("span", _hoisted_14$4, "修改 " + _toDisplayString$6(item.field) + "：", 1),
                          _createElementVNode$6("span", _hoisted_15$4, "#" + _toDisplayString$6(item.id) + " " + _toDisplayString$6(item.from) + " → " + _toDisplayString$6(item.to), 1)
                        ]))
                      }), 128)),
                      _createElementVNode$6("div", _hoisted_16$4, [
                        _cache[4] || (_cache[4] = _createElementVNode$6("span", { class: "sum-k" }, "章节：", -1)),
                        _createTextVNode$6(_toDisplayString$6(chaptersText.value), 1)
                      ]),
                      _createElementVNode$6("div", _hoisted_17$4, [
                        _cache[5] || (_cache[5] = _createElementVNode$6("span", { class: "sum-k" }, "容器标题：", -1)),
                        _createTextVNode$6(_toDisplayString$6(titleText.value), 1)
                      ])
                    ]),
                    _createElementVNode$6("div", _hoisted_18$4, [
                      _createElementVNode$6("div", null, "输出：" + _toDisplayString$6(__props.result.output_path || '—'), 1),
                      (__props.result.no_backup)
                        ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_19$4, " 不做临时备份，失败时无恢复副本 "))
                        : (__props.result.output_mode === 'replace')
                          ? (_openBlock$6(), _createElementBlock$6(_Fragment$5, { key: 1 }, [
                              _cache[6] || (_cache[6] = _createElementVNode$6("div", { class: "preview-backup" }, "临时备份：成功后删除，失败保留", -1)),
                              (__props.result.backup_path)
                                ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_20$3, "备份：" + _toDisplayString$6(__props.result.backup_path), 1))
                                : _createCommentVNode$6("", true)
                            ], 64))
                          : _createCommentVNode$6("", true),
                      (spaceText.value)
                        ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_21$3, _toDisplayString$6(spaceText.value), 1))
                        : _createCommentVNode$6("", true)
                    ]),
                    (_openBlock$6(true), _createElementBlock$6(_Fragment$5, null, _renderList$4(blockers.value, (item, index) => {
                      return (_openBlock$6(), _createElementBlock$6("div", {
                        key: `blk-${index}`,
                        class: "warnbox warnbox--red"
                      }, " ⚠ " + _toDisplayString$6(item.message || item.code), 1))
                    }), 128)),
                    (_openBlock$6(true), _createElementBlock$6(_Fragment$5, null, _renderList$4(warnings.value, (item, index) => {
                      return (_openBlock$6(), _createElementBlock$6("div", {
                        key: `warn-${index}`,
                        class: "warnbox warnbox--warn"
                      }, " ⚠ " + _toDisplayString$6(item.message || item.code), 1))
                    }), 128)),
                    (!__props.engineReady)
                      ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_22$3, " ⚠ 未检测到 MKVToolNix，无法执行，请先在设置里安装或指定引擎路径 "))
                      : _createCommentVNode$6("", true),
                    (hasDurationMismatch.value)
                      ? (_openBlock$6(), _createElementBlock$6("div", _hoisted_23$3, [
                          _createVNode$6(_component_v_checkbox, {
                            "model-value": __props.confirmed,
                            density: "compact",
                            color: "warning",
                            "hide-details": "",
                            label: "我已知晓时长不一致，仍要执行",
                            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (emit('update:confirmed', $event)))
                          }, null, 8, ["model-value"]),
                          _cache[7] || (_cache[7] = _createElementVNode$6("div", { class: "duration-confirm-hint" }, " 音轨 / 字幕与视频时长不一致（可能不是同一版本），执行后可能出现时间轴错位；建议先用「估偏移」校正 sync。 ", -1))
                        ]))
                      : _createCommentVNode$6("", true),
                    (commands.value.length)
                      ? (_openBlock$6(), _createElementBlock$6("details", _hoisted_24$3, [
                          _createElementVNode$6("summary", null, "命令详情（" + _toDisplayString$6(commands.value.length) + " 条）", 1),
                          (_openBlock$6(true), _createElementBlock$6(_Fragment$5, null, _renderList$4(commands.value, (command, index) => {
                            return (_openBlock$6(), _createElementBlock$6("pre", {
                              key: `cmd-${index}`,
                              class: "preview-code"
                            }, _toDisplayString$6(commandText(command)), 1))
                          }), 128))
                        ]))
                      : (_openBlock$6(), _createElementBlock$6("div", _hoisted_25$3, "后端未返回命令（无实际写操作时可以忽略）"))
                  ], 64))
                : (_openBlock$6(), _createBlock$6(_component_v_alert, {
                    key: 2,
                    type: "error",
                    variant: "tonal",
                    density: "compact"
                  }, {
                    default: _withCtx$6(() => [...(_cache[8] || (_cache[8] = [
                      _createTextVNode$6(" 预览生成失败，请检查文件路径与引擎状态后重试 ", -1)
                    ]))]),
                    _: 1
                  }))
          ]),
          _createElementVNode$6("div", _hoisted_26$2, [
            _createElementVNode$6("span", _hoisted_27$2, _toDisplayString$6(fileLabel.value), 1),
            _createVNode$6(_component_v_spacer),
            _createElementVNode$6("div", _hoisted_28$2, [
              _createVNode$6(_component_v_btn, {
                variant: "text",
                disabled: __props.submitting,
                onClick: close
              }, {
                default: _withCtx$6(() => [...(_cache[9] || (_cache[9] = [
                  _createTextVNode$6("取消", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$6(_component_v_btn, {
                color: "primary",
                variant: "flat",
                loading: __props.submitting,
                disabled: !canSubmit.value,
                onClick: confirm
              }, {
                default: _withCtx$6(() => [
                  _createTextVNode$6(_toDisplayString$6(__props.confirmText || '确认执行'), 1)
                ]),
                _: 1
              }, 8, ["loading", "disabled"])
            ])
          ])
        ]),
        _: 1
      }, 8, ["class"])
    ]),
    _: 1
  }, 8, ["model-value", "max-width", "fullscreen"]))
}
}

};
const PreviewDialog = /*#__PURE__*/_export_sfc(_sfc_main$6, [['__scopeId',"data-v-55b51128"]]);

const {toDisplayString:_toDisplayString$5,createElementVNode:_createElementVNode$5,resolveComponent:_resolveComponent$5,createVNode:_createVNode$5,renderList:_renderList$3,Fragment:_Fragment$4,openBlock:_openBlock$5,createElementBlock:_createElementBlock$5,normalizeClass:_normalizeClass$4,createTextVNode:_createTextVNode$5,withCtx:_withCtx$5,withKeys:_withKeys$1,createCommentVNode:_createCommentVNode$5,createBlock:_createBlock$5,unref:_unref$4} = await importShared('vue');


const _hoisted_1$5 = { class: "picker-head" };
const _hoisted_2$5 = { class: "picker-title" };
const _hoisted_3$5 = { class: "picker-body" };
const _hoisted_4$5 = { class: "picker-toolbar" };
const _hoisted_5$5 = { class: "picker-roots" };
const _hoisted_6$5 = ["onClick"];
const _hoisted_7$4 = ["title"];
const _hoisted_8$4 = {
  key: 0,
  class: "archive-manual"
};
const _hoisted_9$4 = { class: "picker-list" };
const _hoisted_10$4 = {
  key: 0,
  class: "picker-empty picker-empty--error"
};
const _hoisted_11$4 = ["onClick"];
const _hoisted_12$4 = { class: "picker-name" };
const _hoisted_13$4 = {
  key: 0,
  class: "picker-size"
};
const _hoisted_14$3 = ["onClick", "onDblclick"];
const _hoisted_15$3 = { class: "picker-name" };
const _hoisted_16$3 = { class: "picker-size" };
const _hoisted_17$3 = {
  key: 0,
  class: "picker-empty"
};
const _hoisted_18$3 = { class: "picker-foot" };
const _hoisted_19$3 = { class: "picker-foot-btns" };

const {computed: computed$4,ref: ref$3,watch: watch$2} = await importShared('vue');

const {useDisplay: useDisplay$2} = await importShared('vuetify');


const _sfc_main$5 = {
  __name: 'FilePickerDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  api: { type: Object, required: true },
  kind: { type: String, default: 'subtitle' },
  title: { type: String, default: '' },
  roots: { type: Array, default: () => [] },
  initialPath: { type: String, default: '' },
  exts: { type: Array, default: () => [] },
  // 布局三档：narrow 全屏；medium 半屏窗口（min(620px,55vw)）；wide 680px
  layout: { type: String, default: '' },
},
  emits: ['update:modelValue', 'select'],
  setup(__props, { emit: __emit }) {

/**
 * 从目录选择素材：调用 /fs/list，按 kind 过滤，选中后返回服务器路径
 */
const props = __props;

const emit = __emit;
const display = useDisplay$2();
const effectiveLayout = computed$4(() => props.layout || (display.mdAndUp.value ? 'wide' : 'narrow'));
const mobile = computed$4(() => effectiveLayout.value === 'narrow');
const dialogMaxWidth = computed$4(() => {
  if (mobile.value) return undefined
  return effectiveLayout.value === 'medium' ? 'min(620px, 55vw)' : 680
});

const KIND_TITLE = { subtitle: '选择字幕文件', audio: '选择音频文件', font: '选择字体文件', chapter: '选择章节文件', archive: '选择字体压缩包' };
const KIND_EXT = {
  subtitle: SUBTITLE_EXTENSIONS,
  audio: AUDIO_EXTENSIONS,
  font: FONT_EXTENSIONS,
  chapter: ['.xml', '.txt', '.ogm'],
  archive: ARCHIVE_EXTENSIONS,
};

const activeRoot = ref$3('');
const currentPath = ref$3('');
const parentPath = ref$3('');
const dirs = ref$3([]);
const files = ref$3([]);
const selected = ref$3(null);
const loading = ref$3(false);
const error = ref$3('');

const dialogTitle = computed$4(() => props.title || KIND_TITLE[props.kind] || '选择文件');
const allowedExts = computed$4(() => (props.exts?.length ? props.exts : KIND_EXT[props.kind] || []));
// 压缩包由后端 /fs/list 的 archive kind 直接过滤
const listKind = computed$4(() => (props.kind === 'chapter' ? 'all' : props.kind));
const rootList = computed$4(() => (Array.isArray(props.roots) ? props.roots.filter(Boolean) : []));
const manualPath = ref$3('');

function isFileLike(path) {
  const last = String(path || '').split('/').pop() || '';
  return last.includes('.')
}

function dirName(path) {
  const normalized = String(path || '').replace(/\/+$/, '');
  const index = normalized.lastIndexOf('/');
  return index > 0 ? normalized.slice(0, index) : '/'
}

function resolveRoot(path) {
  for (const root of rootList.value) {
    const clean = String(root).replace(/\/+$/, '');
    if (path === clean || path === root || String(path).startsWith(`${clean}/`)) return root
  }
  return rootList.value[0] || ''
}

function matchesExt(name) {
  if (!allowedExts.value.length) return true
  const lower = String(name || '').toLowerCase();
  return allowedExts.value.some((ext) => lower.endsWith(ext))
}

async function load(path) {
  const target = path || activeRoot.value;
  loading.value = true;
  error.value = '';
  selected.value = null;
  try {
    const data = await props.api.post('/fs/list', {
      root: activeRoot.value,
      path: target,
      kind: listKind.value,
    });
    currentPath.value = data?.path || target;
    parentPath.value = data?.parent || '';
    dirs.value = (data?.dirs || []).map((item) => ({
      name: item.name,
      path: item.path,
      fileCount: item.file_count ?? null,
    }));
    files.value = (data?.files || [])
      .filter((item) => matchesExt(item.name))
      .map((item) => ({
        name: item.name,
        path: item.path,
        size: item.size ?? null,
        ext: item.ext || '',
      }));
  } catch (err) {
    error.value = err.message || '读取目录失败';
    dirs.value = [];
    files.value = [];
  } finally {
    loading.value = false;
  }
}

function init() {
  selected.value = null;
  manualPath.value = '';
  error.value = '';
  if (!rootList.value.length) {
    error.value = '还没有配置媒体根目录，请先到设置里添加';
    return
  }
  let start = props.initialPath || '';
  if (start && isFileLike(start)) start = dirName(start);
  activeRoot.value = resolveRoot(start || rootList.value[0]);
  const root = activeRoot.value;
  if (!start || (start !== root && !String(start).startsWith(`${String(root).replace(/\/+$/, '')}/`))) {
    start = root;
  }
  load(start || root);
}

function chooseRoot(root) {
  if (!root) return
  activeRoot.value = root;
  load(root);
}

function enterDir(dir) {
  load(dir.path);
}

function goParent() {
  if (!parentPath.value) return
  load(parentPath.value);
}

function pick(file) {
  selected.value = file;
}

function archiveExt(name) {
  const lower = String(name || '').toLowerCase();
  return ARCHIVE_EXTENSIONS.find((ext) => lower.endsWith(ext)) || ''
}

/** 压缩包选择兜底：后端 /fs/list 可能不列压缩包，允许直接输入完整路径。 */
function confirmManualArchive() {
  const path = manualPath.value.trim();
  if (!path) return
  const name = path.split('/').pop() || path;
  const ext = archiveExt(name);
  if (!ext) {
    error.value = '请输入支持的压缩包路径（zip / 7z / rar / tar）';
    return
  }
  emit('select', { name, path, size: null, ext, kind: 'archive' });
  emit('update:modelValue', false);
}

function pickAndConfirm(file) {
  pick(file);
  confirmPick();
}

function confirmPick() {
  if (!selected.value) return
  emit('select', { ...selected.value, kind: props.kind });
  emit('update:modelValue', false);
}

watch$2(
  () => props.modelValue,
  (value) => {
    if (value) init();
  },
);

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent$5("v-spacer");
  const _component_v_btn = _resolveComponent$5("v-btn");
  const _component_v_text_field = _resolveComponent$5("v-text-field");
  const _component_v_progress_linear = _resolveComponent$5("v-progress-linear");
  const _component_v_icon = _resolveComponent$5("v-icon");
  const _component_v_card = _resolveComponent$5("v-card");
  const _component_v_dialog = _resolveComponent$5("v-dialog");

  return (_openBlock$5(), _createBlock$5(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": dialogMaxWidth.value,
    fullscreen: mobile.value,
    scrollable: "",
    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => (emit('update:modelValue', $event)))
  }, {
    default: _withCtx$5(() => [
      _createVNode$5(_component_v_card, {
        class: _normalizeClass$4(["picker-dialog", { 'dialog-compact': mobile.value, 'dialog-medium': effectiveLayout.value === 'medium' }])
      }, {
        default: _withCtx$5(() => [
          _createElementVNode$5("div", _hoisted_1$5, [
            _createElementVNode$5("span", _hoisted_2$5, _toDisplayString$5(dialogTitle.value), 1),
            _createVNode$5(_component_v_spacer),
            _createVNode$5(_component_v_btn, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              "aria-label": "关闭",
              onClick: _cache[0] || (_cache[0] = $event => (emit('update:modelValue', false)))
            })
          ]),
          _createElementVNode$5("div", _hoisted_3$5, [
            _createElementVNode$5("div", _hoisted_4$5, [
              _createElementVNode$5("div", _hoisted_5$5, [
                (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$3(rootList.value, (root) => {
                  return (_openBlock$5(), _createElementBlock$5("button", {
                    key: root,
                    type: "button",
                    class: _normalizeClass$4(["root-chip", { 'root-chip--active': root === activeRoot.value }]),
                    onClick: $event => (chooseRoot(root))
                  }, _toDisplayString$5(root), 11, _hoisted_6$5))
                }), 128))
              ]),
              _createVNode$5(_component_v_btn, {
                size: "x-small",
                variant: "text",
                "prepend-icon": "mdi-arrow-up",
                disabled: !parentPath.value || loading.value,
                onClick: goParent
              }, {
                default: _withCtx$5(() => [...(_cache[4] || (_cache[4] = [
                  _createTextVNode$5(" 上级 ", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"])
            ]),
            _createElementVNode$5("div", {
              class: "picker-path",
              title: currentPath.value
            }, _toDisplayString$5(currentPath.value || '—'), 9, _hoisted_7$4),
            (__props.kind === 'archive')
              ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_8$4, [
                  _createVNode$5(_component_v_text_field, {
                    modelValue: manualPath.value,
                    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((manualPath).value = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    placeholder: "也可直接输入压缩包完整路径，如 /media/fonts.zip",
                    class: "archive-manual-input mono",
                    onKeyup: _withKeys$1(confirmManualArchive, ["enter"])
                  }, null, 8, ["modelValue"]),
                  _createVNode$5(_component_v_btn, {
                    size: "small",
                    variant: "tonal",
                    disabled: !manualPath.value.trim(),
                    onClick: confirmManualArchive
                  }, {
                    default: _withCtx$5(() => [...(_cache[5] || (_cache[5] = [
                      _createTextVNode$5(" 使用此压缩包 ", -1)
                    ]))]),
                    _: 1
                  }, 8, ["disabled"])
                ]))
              : _createCommentVNode$5("", true),
            _createElementVNode$5("div", _hoisted_9$4, [
              (loading.value)
                ? (_openBlock$5(), _createBlock$5(_component_v_progress_linear, {
                    key: 0,
                    indeterminate: "",
                    color: "primary",
                    class: "picker-loading"
                  }))
                : _createCommentVNode$5("", true),
              (!loading.value)
                ? (_openBlock$5(), _createElementBlock$5(_Fragment$4, { key: 1 }, [
                    (error.value)
                      ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_10$4, _toDisplayString$5(error.value), 1))
                      : (_openBlock$5(), _createElementBlock$5(_Fragment$4, { key: 1 }, [
                          (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$3(dirs.value, (dir) => {
                            return (_openBlock$5(), _createElementBlock$5("div", {
                              key: `dir-${dir.path}`,
                              class: "picker-row picker-row--dir",
                              onClick: $event => (enterDir(dir))
                            }, [
                              _createVNode$5(_component_v_icon, {
                                size: "17",
                                icon: "mdi-folder-outline"
                              }),
                              _createElementVNode$5("span", _hoisted_12$4, _toDisplayString$5(dir.name), 1),
                              (dir.fileCount)
                                ? (_openBlock$5(), _createElementBlock$5("span", _hoisted_13$4, _toDisplayString$5(dir.fileCount) + " 项", 1))
                                : _createCommentVNode$5("", true),
                              _createVNode$5(_component_v_icon, {
                                size: "15",
                                icon: "mdi-chevron-right",
                                class: "picker-arrow"
                              })
                            ], 8, _hoisted_11$4))
                          }), 128)),
                          (_openBlock$5(true), _createElementBlock$5(_Fragment$4, null, _renderList$3(files.value, (file) => {
                            return (_openBlock$5(), _createElementBlock$5("div", {
                              key: `file-${file.path}`,
                              class: _normalizeClass$4(["picker-row", { 'picker-row--sel': selected.value && selected.value.path === file.path }]),
                              onClick: $event => (pick(file)),
                              onDblclick: $event => (pickAndConfirm(file))
                            }, [
                              _createVNode$5(_component_v_icon, {
                                size: "17",
                                icon: "mdi-file-outline"
                              }),
                              _createElementVNode$5("span", _hoisted_15$3, _toDisplayString$5(file.name), 1),
                              _createElementVNode$5("span", _hoisted_16$3, _toDisplayString$5(_unref$4(fmtBytes)(file.size)), 1)
                            ], 42, _hoisted_14$3))
                          }), 128)),
                          (!dirs.value.length && !files.value.length)
                            ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_17$3, " 当前目录没有可选的" + _toDisplayString$5(__props.kind === 'chapter' ? '章节文件' : '文件'), 1))
                            : _createCommentVNode$5("", true)
                        ], 64))
                  ], 64))
                : _createCommentVNode$5("", true)
            ]),
            _cache[6] || (_cache[6] = _createElementVNode$5("div", { class: "picker-note" }, " 只列出当前类型允许的扩展名；选中后作为轨道 / 附件来源写入 MKV，不会复制或移动原文件。 ", -1))
          ]),
          _createElementVNode$5("div", _hoisted_18$3, [
            _createVNode$5(_component_v_spacer),
            _createElementVNode$5("div", _hoisted_19$3, [
              _createVNode$5(_component_v_btn, {
                variant: "text",
                onClick: _cache[2] || (_cache[2] = $event => (emit('update:modelValue', false)))
              }, {
                default: _withCtx$5(() => [...(_cache[7] || (_cache[7] = [
                  _createTextVNode$5("取消", -1)
                ]))]),
                _: 1
              }),
              _createVNode$5(_component_v_btn, {
                color: "primary",
                variant: "flat",
                disabled: !selected.value,
                onClick: confirmPick
              }, {
                default: _withCtx$5(() => [...(_cache[8] || (_cache[8] = [
                  _createTextVNode$5("选择此文件", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"])
            ])
          ])
        ]),
        _: 1
      }, 8, ["class"])
    ]),
    _: 1
  }, 8, ["model-value", "max-width", "fullscreen"]))
}
}

};
const FilePickerDialog = /*#__PURE__*/_export_sfc(_sfc_main$5, [['__scopeId',"data-v-2bf1b2e2"]]);

const {toDisplayString:_toDisplayString$4,createElementVNode:_createElementVNode$4,resolveComponent:_resolveComponent$4,createVNode:_createVNode$4,withModifiers:_withModifiers,withKeys:_withKeys,normalizeClass:_normalizeClass$3,unref:_unref$3,createTextVNode:_createTextVNode$4,withCtx:_withCtx$4,openBlock:_openBlock$4,createElementBlock:_createElementBlock$4,createCommentVNode:_createCommentVNode$4,Fragment:_Fragment$3,createBlock:_createBlock$4} = await importShared('vue');


const _hoisted_1$4 = { class: "upload-head" };
const _hoisted_2$4 = { class: "upload-title" };
const _hoisted_3$4 = { class: "upload-body" };
const _hoisted_4$4 = ["accept"];
const _hoisted_5$4 = ["onKeydown"];
const _hoisted_6$4 = { class: "upload-sub" };
const _hoisted_7$3 = {
  key: 0,
  class: "upload-selected"
};
const _hoisted_8$3 = ["title"];
const _hoisted_9$3 = { class: "upload-fsize" };
const _hoisted_10$3 = {
  key: 1,
  class: "upload-error"
};
const _hoisted_11$3 = { class: "upload-warn" };
const _hoisted_12$3 = { class: "upload-foot" };
const _hoisted_13$3 = { class: "upload-foot-btns" };

const {computed: computed$3,ref: ref$2,watch: watch$1} = await importShared('vue');

const {useDisplay: useDisplay$1} = await importShared('vuetify');

const archiveLimitBytes = 512 * 1024 * 1024;

const _sfc_main$4 = {
  __name: 'UploadDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  api: { type: Object, required: true },
  kind: { type: String, default: 'subtitle' },
  maxMb: { type: Number, default: 50 },
  title: { type: String, default: '' },
  // 布局三档：narrow 全屏；medium 520px；wide 540px
  layout: { type: String, default: '' },
},
  emits: ['update:modelValue', 'uploaded'],
  setup(__props, { emit: __emit }) {

/**
 * 上传小文件（字幕 / 音频 / 字体）
 * 前端先用 file.size 校验 upload_max_mb，超限直接拒绝并提示改用「从目录选择」；
 * 后端返回超限错误时同样提示。
 */
const props = __props;

const emit = __emit;
const display = useDisplay$1();
const effectiveLayout = computed$3(() => props.layout || (display.mdAndUp.value ? 'wide' : 'narrow'));
const mobile = computed$3(() => effectiveLayout.value === 'narrow');
const dialogMaxWidth = computed$3(() => {
  if (mobile.value) return undefined
  return effectiveLayout.value === 'medium' ? 520 : 540
});

const KIND_TITLE = { subtitle: '上传字幕', audio: '上传音频', font: '上传字体' };
const KIND_ACCEPT = {
  subtitle: SUBTITLE_EXTENSIONS.join(','),
  audio: AUDIO_EXTENSIONS.join(','),
  // 字体页同时允许直接上传字体压缩包（走 /archive/upload 解压）
  font: [...FONT_EXTENSIONS, ...ARCHIVE_EXTENSIONS].join(','),
};

const fileInput = ref$2(null);
const file = ref$2(null);
const uploading = ref$2(false);
const error = ref$2('');
const dragging = ref$2(false);

const dialogTitle = computed$3(() => props.title || KIND_TITLE[props.kind] || '上传文件');
const limitMb = computed$3(() => (Number(props.maxMb) > 0 ? Number(props.maxMb) : 50));
const limitBytes = computed$3(() => limitMb.value * 1024 * 1024);
const accept = computed$3(() => KIND_ACCEPT[props.kind] || '');
// 字体页选中压缩包时改走 /archive/upload，上限 512MB
const fileIsArchive = computed$3(() => props.kind === 'font' && isArchiveName(file.value?.name || ''));
computed$3(() => (fileIsArchive.value ? archiveLimitBytes : limitBytes.value));
const uploadHint = computed$3(() =>
  fileIsArchive.value ? '压缩包最大 512MB，上传后自动解压出字体' : `上传上限 ${limitMb.value}MB，超过请改用「从目录选择」`,
);

function reset() {
  file.value = null;
  error.value = '';
  uploading.value = false;
  dragging.value = false;
  if (fileInput.value) fileInput.value.value = '';
}

function pickFile() {
  if (uploading.value) return
  fileInput.value?.click();
}

function validate(f) {
  if (!f) return false
  const isArchive = props.kind === 'font' && isArchiveName(f.name);
  const limit = isArchive ? archiveLimitBytes : limitBytes.value;
  if (f.size > limit) {
    file.value = null;
    error.value = isArchive
      ? `压缩包 ${fmtBytes(f.size)} 超过 512MB 上限`
      : `文件 ${fmtBytes(f.size)} 超过 ${limitMb.value}MB 上限，请改用「从目录选择」`;
    return false
  }
  return true
}

function onFileChange(event) {
  const f = event.target.files?.[0];
  error.value = '';
  if (!validate(f)) {
    file.value = null;
    return
  }
  file.value = f;
}

function onDrop(event) {
  dragging.value = false;
  if (uploading.value) return
  const f = event.dataTransfer?.files?.[0];
  error.value = '';
  if (!validate(f)) {
    file.value = null;
    return
  }
  file.value = f;
}

async function upload() {
  if (!file.value || uploading.value) return
  // 双保险：上传前再校验一次
  if (!validate(file.value)) return
  uploading.value = true;
  error.value = '';
  try {
    const form = new FormData();
    form.append('file', file.value);
    if (props.kind === 'font' && isArchiveName(file.value.name)) {
      // 压缩包：后端上传后直接解压字体
      const data = await props.api.upload('/archive/upload', form);
      emit('uploaded', { ...(data || {}), kind: 'font', archiveUpload: true });
    } else {
      const data = await props.api.upload('/upload', form, { kind: props.kind });
      emit('uploaded', { ...(data || {}), kind: props.kind });
    }
    emit('update:modelValue', false);
    reset();
  } catch (err) {
    // 后端超限文案已明确（含「请改用从目录选择」），直接展示
    error.value = err.message || '上传失败';
  } finally {
    uploading.value = false;
  }
}

watch$1(
  () => props.modelValue,
  (value) => {
    if (value) reset();
  },
);

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent$4("v-spacer");
  const _component_v_btn = _resolveComponent$4("v-btn");
  const _component_v_icon = _resolveComponent$4("v-icon");
  const _component_v_card = _resolveComponent$4("v-card");
  const _component_v_dialog = _resolveComponent$4("v-dialog");

  return (_openBlock$4(), _createBlock$4(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": dialogMaxWidth.value,
    fullscreen: mobile.value,
    "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => (emit('update:modelValue', $event)))
  }, {
    default: _withCtx$4(() => [
      _createVNode$4(_component_v_card, {
        class: _normalizeClass$3(["upload-dialog", { 'dialog-compact': mobile.value }])
      }, {
        default: _withCtx$4(() => [
          _createElementVNode$4("div", _hoisted_1$4, [
            _createElementVNode$4("span", _hoisted_2$4, _toDisplayString$4(dialogTitle.value), 1),
            _createVNode$4(_component_v_spacer),
            _createVNode$4(_component_v_btn, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              "aria-label": "关闭",
              onClick: _cache[0] || (_cache[0] = $event => (emit('update:modelValue', false)))
            })
          ]),
          _createElementVNode$4("div", _hoisted_3$4, [
            _createElementVNode$4("input", {
              ref_key: "fileInput",
              ref: fileInput,
              type: "file",
              class: "upload-input",
              accept: accept.value,
              onChange: onFileChange
            }, null, 40, _hoisted_4$4),
            _createElementVNode$4("div", {
              class: _normalizeClass$3(["upload-drop", { 'upload-drop--drag': dragging.value }]),
              role: "button",
              tabindex: "0",
              onClick: pickFile,
              onKeydown: [
                _withKeys(_withModifiers(pickFile, ["prevent"]), ["enter"]),
                _withKeys(_withModifiers(pickFile, ["prevent"]), ["space"])
              ],
              onDragover: _cache[1] || (_cache[1] = _withModifiers($event => (dragging.value = true), ["prevent"])),
              onDragleave: _cache[2] || (_cache[2] = _withModifiers($event => (dragging.value = false), ["prevent"])),
              onDrop: _withModifiers(onDrop, ["prevent"])
            }, [
              _createVNode$4(_component_v_icon, {
                size: "30",
                icon: "mdi-upload-outline",
                class: "upload-big"
              }),
              _cache[6] || (_cache[6] = _createElementVNode$4("div", { class: "upload-main" }, "点击选择文件，或拖到这里", -1)),
              _createElementVNode$4("div", _hoisted_6$4, _toDisplayString$4(uploadHint.value), 1)
            ], 42, _hoisted_5$4),
            (file.value)
              ? (_openBlock$4(), _createElementBlock$4("div", _hoisted_7$3, [
                  _createVNode$4(_component_v_icon, {
                    size: "16",
                    icon: "mdi-file-outline"
                  }),
                  _createElementVNode$4("span", {
                    class: "upload-fname",
                    title: file.value.name
                  }, _toDisplayString$4(file.value.name), 9, _hoisted_8$3),
                  _createElementVNode$4("span", _hoisted_9$3, _toDisplayString$4(_unref$3(fmtBytes)(file.value.size)), 1),
                  _createVNode$4(_component_v_btn, {
                    size: "x-small",
                    variant: "text",
                    disabled: uploading.value,
                    onClick: _cache[3] || (_cache[3] = $event => (file.value = null))
                  }, {
                    default: _withCtx$4(() => [...(_cache[7] || (_cache[7] = [
                      _createTextVNode$4("移除", -1)
                    ]))]),
                    _: 1
                  }, 8, ["disabled"])
                ]))
              : _createCommentVNode$4("", true),
            (error.value)
              ? (_openBlock$4(), _createElementBlock$4("div", _hoisted_10$3, _toDisplayString$4(error.value), 1))
              : _createCommentVNode$4("", true),
            _createElementVNode$4("div", _hoisted_11$3, [
              _cache[8] || (_cache[8] = _createTextVNode$4(" 宿主 nginx 默认请求体上限 50MB，超过会直接失败；音频 / 大字体请用「从目录选择」。 ", -1)),
              (__props.kind === 'font')
                ? (_openBlock$4(), _createElementBlock$4(_Fragment$3, { key: 0 }, [
                    _createTextVNode$4("字体压缩包（zip/7z/rar/tar）最大 512MB，上传后自动解压出字体；超过 50MB 的压缩包请放到媒体目录用「从目录批量解压」。")
                  ], 64))
                : _createCommentVNode$4("", true)
            ]),
            _cache[9] || (_cache[9] = _createElementVNode$4("div", { class: "upload-note" }, "上传的文件存放到插件数据目录，处理完成后不会留在媒体库。", -1))
          ]),
          _createElementVNode$4("div", _hoisted_12$3, [
            _createVNode$4(_component_v_spacer),
            _createElementVNode$4("div", _hoisted_13$3, [
              _createVNode$4(_component_v_btn, {
                variant: "text",
                disabled: uploading.value,
                onClick: _cache[4] || (_cache[4] = $event => (emit('update:modelValue', false)))
              }, {
                default: _withCtx$4(() => [...(_cache[10] || (_cache[10] = [
                  _createTextVNode$4("取消", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$4(_component_v_btn, {
                color: "primary",
                variant: "flat",
                loading: uploading.value,
                disabled: !file.value,
                onClick: upload
              }, {
                default: _withCtx$4(() => [...(_cache[11] || (_cache[11] = [
                  _createTextVNode$4("上传", -1)
                ]))]),
                _: 1
              }, 8, ["loading", "disabled"])
            ])
          ])
        ]),
        _: 1
      }, 8, ["class"])
    ]),
    _: 1
  }, 8, ["model-value", "max-width", "fullscreen"]))
}
}

};
const UploadDialog = /*#__PURE__*/_export_sfc(_sfc_main$4, [['__scopeId',"data-v-d6e031fc"]]);

const {createElementVNode:_createElementVNode$3,toDisplayString:_toDisplayString$3,openBlock:_openBlock$3,createElementBlock:_createElementBlock$3,createCommentVNode:_createCommentVNode$3,createTextVNode:_createTextVNode$3,resolveComponent:_resolveComponent$3,withCtx:_withCtx$3,createVNode:_createVNode$3,createBlock:_createBlock$3,renderList:_renderList$2,Fragment:_Fragment$2,normalizeClass:_normalizeClass$2,unref:_unref$2} = await importShared('vue');


const _hoisted_1$3 = { class: "page-head" };
const _hoisted_2$3 = { class: "page-count" };
const _hoisted_3$3 = {
  key: 0,
  class: "page-held"
};
const _hoisted_4$3 = {
  key: 1,
  class: "page-paused"
};
const _hoisted_5$3 = { class: "page-actions" };
const _hoisted_6$3 = { class: "queue-concurrency" };
const _hoisted_7$2 = {
  key: 1,
  class: "page-empty"
};
const _hoisted_8$2 = { class: "queue-table" };
const _hoisted_9$2 = { class: "col-no" };
const _hoisted_10$2 = { class: "col-status" };
const _hoisted_11$2 = {
  key: 0,
  class: "badge-dot"
};
const _hoisted_12$2 = { class: "name-cell" };
const _hoisted_13$2 = ["title"];
const _hoisted_14$2 = { class: "file-sub" };
const _hoisted_15$2 = { key: 0 };
const _hoisted_16$2 = { class: "summary-cell" };
const _hoisted_17$2 = { class: "progress-cell" };
const _hoisted_18$2 = { class: "progress-text" };
const _hoisted_19$2 = {
  key: 1,
  class: "progress-idle"
};
const _hoisted_20$2 = { class: "ops-cell" };
const _hoisted_21$2 = { class: "row-ops" };
const _hoisted_22$2 = {
  key: 1,
  class: "queue-cards"
};
const _hoisted_23$2 = { class: "m-card-head" };
const _hoisted_24$2 = {
  key: 0,
  class: "badge-dot"
};
const _hoisted_25$2 = ["title"];
const _hoisted_26$1 = { class: "m-ops-sum" };
const _hoisted_27$1 = { class: "m-card-foot" };
const _hoisted_28$1 = {
  key: 1,
  class: "m-card-foot"
};
const _hoisted_29$1 = { class: "m-time" };

const {computed: computed$2} = await importShared('vue');


const _sfc_main$3 = {
  __name: 'QueuePage',
  props: {
  jobs: { type: Array, default: () => [] },
  paused: { type: Boolean, default: false },
  concurrency: { type: Number, default: 1 },
  held: { type: Number, default: 0 },
  editingId: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  // narrow: 卡片；medium: 紧凑表格；wide: 普通表格
  layout: { type: String, default: 'wide' },
},
  emits: ['refresh', 'cancel', 'move', 'pause', 'clear', 'start', 'start-all', 'edit', 'set-concurrency'],
  setup(__props, { emit: __emit }) {

/**
 * 队列页：运行中 / 等待中 / 待启动，进度、取消、置顶/上移/下移、开始、全部开始、暂停、清空等待；
 * 待启动或暂停中的等待任务支持「编辑」（回填编辑器后重新提交更新）。
 */
const props = __props;

const emit = __emit;

const narrow = computed$2(() => props.layout === 'narrow');
const medium = computed$2(() => props.layout === 'medium');

const running = computed$2(() => props.jobs.filter((job) => job.status === 'running'));
const pending = computed$2(() => props.jobs.filter((job) => job.status === 'pending'));
const rows = computed$2(() => running.value.concat(pending.value));
const heldJobs = computed$2(() => pending.value.filter((job) => Boolean(job.hold)));
// 以任务列表为准，status.queue.held 作为兜底（列表还没刷到时的页头数量）
const heldCount = computed$2(() => Math.max(Number(props.held) || 0, heldJobs.value.length));

const concurrencyItems = [1, 2, 3];

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
  const value = Number(job.progress);
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}

function etaText(job) {
  if (job.status !== 'running') return ''
  const progress = progressOf(job);
  if (progress <= 0) return ''
  const elapsed = Number(job.duration) > 0 ? Number(job.duration) : 0;
  if (!elapsed) return ''
  const remaining = (elapsed / progress) * (100 - progress);
  if (!Number.isFinite(remaining) || remaining <= 0) return ''
  return `${fmtDuration(remaining)} 剩余`
}

function progressText(job) {
  const progress = progressOf(job);
  if (job.status !== 'running') return ''
  const eta = etaText(job);
  return eta ? `${progress}% · 约 ${eta}` : `${progress}%`
}

function moveTo(job, to) {
  emit('move', job, to);
}

function cancel(job) {
  emit('cancel', job);
}

function togglePause() {
  emit('pause', !props.paused);
}

function changeConcurrency(value) {
  const num = Number(value);
  if (!num || num === props.concurrency) return
  emit('set-concurrency', num);
}

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_select = _resolveComponent$3("v-select");
  const _component_v_skeleton_loader = _resolveComponent$3("v-skeleton-loader");
  const _component_v_chip = _resolveComponent$3("v-chip");
  const _component_v_progress_linear = _resolveComponent$3("v-progress-linear");
  const _component_v_card = _resolveComponent$3("v-card");
  const _component_v_spacer = _resolveComponent$3("v-spacer");

  return (_openBlock$3(), _createElementBlock$3("div", {
    class: _normalizeClass$2(["queue-page", { 'queue-page--medium': medium.value }])
  }, [
    _createElementVNode$3("div", _hoisted_1$3, [
      _cache[6] || (_cache[6] = _createElementVNode$3("h2", { class: "page-title" }, "队列", -1)),
      _createElementVNode$3("span", _hoisted_2$3, [
        _createTextVNode$3(_toDisplayString$3(running.value.length) + " 运行中 · " + _toDisplayString$3(pending.value.length) + " 等待中 ", 1),
        (heldCount.value)
          ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_3$3, "· " + _toDisplayString$3(heldCount.value) + " 个待启动", 1))
          : _createCommentVNode$3("", true),
        (__props.paused)
          ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_4$3, "（已暂停）"))
          : _createCommentVNode$3("", true)
      ]),
      _createElementVNode$3("div", _hoisted_5$3, [
        _createVNode$3(_component_v_btn, {
          size: "small",
          color: "primary",
          variant: "flat",
          "prepend-icon": "mdi-play-circle-outline",
          disabled: !heldCount.value,
          onClick: _cache[0] || (_cache[0] = $event => (emit('start-all')))
        }, {
          default: _withCtx$3(() => [...(_cache[3] || (_cache[3] = [
            _createTextVNode$3(" 全部开始 ", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createElementVNode$3("label", _hoisted_6$3, [
          _cache[4] || (_cache[4] = _createTextVNode$3(" 并发 ", -1)),
          _createVNode$3(_component_v_select, {
            "model-value": __props.concurrency,
            items: concurrencyItems,
            density: "compact",
            variant: "outlined",
            "hide-details": "",
            class: "concurrency-select",
            "onUpdate:modelValue": changeConcurrency
          }, null, 8, ["model-value"])
        ]),
        _createVNode$3(_component_v_btn, {
          size: "small",
          variant: "tonal",
          "prepend-icon": __props.paused ? 'mdi-play' : 'mdi-pause',
          onClick: togglePause
        }, {
          default: _withCtx$3(() => [
            _createTextVNode$3(_toDisplayString$3(__props.paused ? '继续队列' : '暂停队列'), 1)
          ]),
          _: 1
        }, 8, ["prepend-icon"]),
        _createVNode$3(_component_v_btn, {
          size: "small",
          variant: "text",
          disabled: !pending.value.length,
          onClick: _cache[1] || (_cache[1] = $event => (emit('clear')))
        }, {
          default: _withCtx$3(() => [...(_cache[5] || (_cache[5] = [
            _createTextVNode$3("清空等待", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createVNode$3(_component_v_btn, {
          size: "small",
          variant: "text",
          icon: "mdi-refresh",
          loading: __props.loading,
          title: "刷新",
          onClick: _cache[2] || (_cache[2] = $event => (emit('refresh')))
        }, null, 8, ["loading"])
      ])
    ]),
    (__props.loading && !rows.value.length)
      ? (_openBlock$3(), _createBlock$3(_component_v_skeleton_loader, {
          key: 0,
          type: "list-item@4"
        }))
      : (!rows.value.length)
        ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_7$2, " 队列为空。去「编辑」页选择文件，预览确认后会加入队列。 "))
        : (_openBlock$3(), _createElementBlock$3(_Fragment$2, { key: 2 }, [
            (!narrow.value)
              ? (_openBlock$3(), _createBlock$3(_component_v_card, {
                  key: 0,
                  variant: "flat",
                  class: "queue-table-card"
                }, {
                  default: _withCtx$3(() => [
                    _createElementVNode$3("table", _hoisted_8$2, [
                      _cache[12] || (_cache[12] = _createElementVNode$3("thead", null, [
                        _createElementVNode$3("tr", null, [
                          _createElementVNode$3("th", { class: "col-no" }),
                          _createElementVNode$3("th", { class: "col-status" }, "状态"),
                          _createElementVNode$3("th", null, "文件"),
                          _createElementVNode$3("th", { class: "col-summary" }, "操作摘要"),
                          _createElementVNode$3("th", { class: "col-progress" }, "进度"),
                          _createElementVNode$3("th", { class: "col-ops" })
                        ])
                      ], -1)),
                      _createElementVNode$3("tbody", null, [
                        (_openBlock$3(true), _createElementBlock$3(_Fragment$2, null, _renderList$2(rows.value, (job, index) => {
                          return (_openBlock$3(), _createElementBlock$3("tr", {
                            key: job.id,
                            class: "queue-row"
                          }, [
                            _createElementVNode$3("td", _hoisted_9$2, _toDisplayString$3(index + 1), 1),
                            _createElementVNode$3("td", _hoisted_10$2, [
                              _createElementVNode$3("span", {
                                class: _normalizeClass$2(["badge-state", stateClass(job)])
                              }, [
                                (job.status === 'running')
                                  ? (_openBlock$3(), _createElementBlock$3("i", _hoisted_11$2))
                                  : _createCommentVNode$3("", true),
                                _createTextVNode$3(" " + _toDisplayString$3(statusLabel(job)), 1)
                              ], 2)
                            ]),
                            _createElementVNode$3("td", _hoisted_12$2, [
                              _createElementVNode$3("div", {
                                class: "file-name",
                                title: job.path
                              }, [
                                _createTextVNode$3(_toDisplayString$3(job.name || job.path) + " ", 1),
                                (__props.editingId === job.id)
                                  ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                                      key: 0,
                                      size: "x-small",
                                      color: "info",
                                      variant: "tonal",
                                      class: "editing-tag"
                                    }, {
                                      default: _withCtx$3(() => [...(_cache[7] || (_cache[7] = [
                                        _createTextVNode$3(" 编辑中 ", -1)
                                      ]))]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$3("", true)
                              ], 8, _hoisted_13$2),
                              _createElementVNode$3("div", _hoisted_14$2, [
                                _createTextVNode$3(_toDisplayString$3(job.engine || ''), 1),
                                (job.error)
                                  ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_15$2, " · " + _toDisplayString$3(job.error), 1))
                                  : _createCommentVNode$3("", true)
                              ])
                            ]),
                            _createElementVNode$3("td", _hoisted_16$2, _toDisplayString$3(job.summary || '—'), 1),
                            _createElementVNode$3("td", _hoisted_17$2, [
                              (job.status === 'running')
                                ? (_openBlock$3(), _createElementBlock$3(_Fragment$2, { key: 0 }, [
                                    _createVNode$3(_component_v_progress_linear, {
                                      "model-value": progressOf(job),
                                      height: "6",
                                      rounded: "",
                                      color: "primary"
                                    }, null, 8, ["model-value"]),
                                    _createElementVNode$3("div", _hoisted_18$2, _toDisplayString$3(progressText(job)), 1)
                                  ], 64))
                                : (_openBlock$3(), _createElementBlock$3("span", _hoisted_19$2, "—"))
                            ]),
                            _createElementVNode$3("td", _hoisted_20$2, [
                              _createElementVNode$3("div", _hoisted_21$2, [
                                (job.status === 'running')
                                  ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                      key: 0,
                                      size: "x-small",
                                      variant: "tonal",
                                      onClick: $event => (cancel(job))
                                    }, {
                                      default: _withCtx$3(() => [...(_cache[8] || (_cache[8] = [
                                        _createTextVNode$3("取消", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["onClick"]))
                                  : (_openBlock$3(), _createElementBlock$3(_Fragment$2, { key: 1 }, [
                                      (canEdit(job))
                                        ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                            key: 0,
                                            size: "x-small",
                                            variant: "tonal",
                                            "prepend-icon": "mdi-pencil",
                                            onClick: $event => (emit('edit', job))
                                          }, {
                                            default: _withCtx$3(() => [...(_cache[9] || (_cache[9] = [
                                              _createTextVNode$3(" 编辑 ", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["onClick"]))
                                        : _createCommentVNode$3("", true),
                                      (isHeld(job))
                                        ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                            key: 1,
                                            size: "x-small",
                                            color: "primary",
                                            variant: "flat",
                                            "prepend-icon": "mdi-play",
                                            onClick: $event => (emit('start', job))
                                          }, {
                                            default: _withCtx$3(() => [...(_cache[10] || (_cache[10] = [
                                              _createTextVNode$3(" 开始 ", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["onClick"]))
                                        : _createCommentVNode$3("", true),
                                      _createVNode$3(_component_v_btn, {
                                        size: "x-small",
                                        variant: "tonal",
                                        disabled: index <= running.value.length,
                                        onClick: $event => (moveTo(job, 'top'))
                                      }, {
                                        default: _withCtx$3(() => [...(_cache[11] || (_cache[11] = [
                                          _createTextVNode$3("置顶", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["disabled", "onClick"]),
                                      _createVNode$3(_component_v_btn, {
                                        size: "x-small",
                                        variant: "tonal",
                                        icon: "mdi-arrow-up",
                                        title: "上移",
                                        onClick: $event => (moveTo(job, 'up'))
                                      }, null, 8, ["onClick"]),
                                      _createVNode$3(_component_v_btn, {
                                        size: "x-small",
                                        variant: "tonal",
                                        icon: "mdi-arrow-down",
                                        title: "下移",
                                        onClick: $event => (moveTo(job, 'down'))
                                      }, null, 8, ["onClick"]),
                                      _createVNode$3(_component_v_btn, {
                                        size: "x-small",
                                        variant: "tonal",
                                        icon: "mdi-close",
                                        title: "取消排队",
                                        onClick: $event => (cancel(job))
                                      }, null, 8, ["onClick"])
                                    ], 64))
                              ])
                            ])
                          ]))
                        }), 128))
                      ])
                    ])
                  ]),
                  _: 1
                }))
              : (_openBlock$3(), _createElementBlock$3("div", _hoisted_22$2, [
                  (_openBlock$3(true), _createElementBlock$3(_Fragment$2, null, _renderList$2(rows.value, (job) => {
                    return (_openBlock$3(), _createElementBlock$3("div", {
                      key: job.id,
                      class: "m-card"
                    }, [
                      _createElementVNode$3("div", _hoisted_23$2, [
                        _createElementVNode$3("span", {
                          class: _normalizeClass$2(["badge-state", stateClass(job)])
                        }, [
                          (job.status === 'running')
                            ? (_openBlock$3(), _createElementBlock$3("i", _hoisted_24$2))
                            : _createCommentVNode$3("", true),
                          _createTextVNode$3(" " + _toDisplayString$3(statusLabel(job)), 1)
                        ], 2),
                        _createElementVNode$3("span", {
                          class: "m-name",
                          title: job.path
                        }, _toDisplayString$3(job.name || job.path), 9, _hoisted_25$2),
                        (__props.editingId === job.id)
                          ? (_openBlock$3(), _createBlock$3(_component_v_chip, {
                              key: 0,
                              size: "x-small",
                              color: "info",
                              variant: "tonal",
                              class: "editing-tag"
                            }, {
                              default: _withCtx$3(() => [...(_cache[13] || (_cache[13] = [
                                _createTextVNode$3(" 编辑中 ", -1)
                              ]))]),
                              _: 1
                            }))
                          : _createCommentVNode$3("", true)
                      ]),
                      _createElementVNode$3("div", _hoisted_26$1, _toDisplayString$3(job.summary || '—'), 1),
                      (job.status === 'running')
                        ? (_openBlock$3(), _createElementBlock$3(_Fragment$2, { key: 0 }, [
                            _createVNode$3(_component_v_progress_linear, {
                              "model-value": progressOf(job),
                              height: "6",
                              rounded: "",
                              color: "primary",
                              class: "mt-2"
                            }, null, 8, ["model-value"]),
                            _createElementVNode$3("div", _hoisted_27$1, [
                              _createElementVNode$3("span", null, _toDisplayString$3(progressText(job)), 1),
                              _createVNode$3(_component_v_spacer),
                              _createVNode$3(_component_v_btn, {
                                size: "small",
                                variant: "tonal",
                                onClick: $event => (cancel(job))
                              }, {
                                default: _withCtx$3(() => [...(_cache[14] || (_cache[14] = [
                                  _createTextVNode$3("取消", -1)
                                ]))]),
                                _: 1
                              }, 8, ["onClick"])
                            ])
                          ], 64))
                        : (_openBlock$3(), _createElementBlock$3("div", _hoisted_28$1, [
                            _createElementVNode$3("span", _hoisted_29$1, _toDisplayString$3(_unref$2(fmtDateTime)(job.created_at, true)), 1),
                            _createVNode$3(_component_v_spacer),
                            (canEdit(job))
                              ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                  key: 0,
                                  size: "small",
                                  variant: "tonal",
                                  "prepend-icon": "mdi-pencil",
                                  onClick: $event => (emit('edit', job))
                                }, {
                                  default: _withCtx$3(() => [...(_cache[15] || (_cache[15] = [
                                    _createTextVNode$3(" 编辑 ", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["onClick"]))
                              : _createCommentVNode$3("", true),
                            (isHeld(job))
                              ? (_openBlock$3(), _createBlock$3(_component_v_btn, {
                                  key: 1,
                                  size: "small",
                                  color: "primary",
                                  variant: "flat",
                                  "prepend-icon": "mdi-play",
                                  onClick: $event => (emit('start', job))
                                }, {
                                  default: _withCtx$3(() => [...(_cache[16] || (_cache[16] = [
                                    _createTextVNode$3(" 开始 ", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["onClick"]))
                              : _createCommentVNode$3("", true),
                            _createVNode$3(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              onClick: $event => (moveTo(job, 'top'))
                            }, {
                              default: _withCtx$3(() => [...(_cache[17] || (_cache[17] = [
                                _createTextVNode$3("置顶", -1)
                              ]))]),
                              _: 1
                            }, 8, ["onClick"]),
                            _createVNode$3(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              icon: "mdi-arrow-up",
                              title: "上移",
                              onClick: $event => (moveTo(job, 'up'))
                            }, null, 8, ["onClick"]),
                            _createVNode$3(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              icon: "mdi-arrow-down",
                              title: "下移",
                              onClick: $event => (moveTo(job, 'down'))
                            }, null, 8, ["onClick"]),
                            _createVNode$3(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              icon: "mdi-close",
                              title: "取消排队",
                              onClick: $event => (cancel(job))
                            }, null, 8, ["onClick"])
                          ]))
                    ]))
                  }), 128))
                ])),
            _cache[18] || (_cache[18] = _createElementVNode$3("div", { class: "page-tip" }, " 「待启动」任务只进队列、不会被调度，点行内「开始」或页头「全部开始」后才会执行。 待启动任务、以及队列暂停时的等待任务可以「编辑」，提交后会直接更新该任务（不会新建）。 排序用「置顶 / 上移 / 下移」，不做拖拽；正在运行的任务只能取消，不能调序。 插件重载后等待任务自动恢复，运行中的任务会标记为中断。 ", -1))
          ], 64))
  ], 2))
}
}

};
const QueuePage = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-019cf7c8"]]);

const {createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,createTextVNode:_createTextVNode$2,withCtx:_withCtx$2,openBlock:_openBlock$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,createElementBlock:_createElementBlock$2,renderList:_renderList$1,Fragment:_Fragment$1,unref:_unref$1,normalizeClass:_normalizeClass$1} = await importShared('vue');


const _hoisted_1$2 = { class: "page-head" };
const _hoisted_2$2 = { class: "page-count" };
const _hoisted_3$2 = { class: "page-actions" };
const _hoisted_4$2 = {
  key: 1,
  class: "page-empty"
};
const _hoisted_5$2 = { class: "history-table" };
const _hoisted_6$2 = { class: "col-time mono" };
const _hoisted_7$1 = { class: "name-cell" };
const _hoisted_8$1 = ["title"];
const _hoisted_9$1 = ["title"];
const _hoisted_10$1 = {
  key: 0,
  class: "file-sub"
};
const _hoisted_11$1 = ["title"];
const _hoisted_12$1 = { class: "summary-cell" };
const _hoisted_13$1 = { class: "col-result" };
const _hoisted_14$1 = { class: "col-duration" };
const _hoisted_15$1 = { class: "ops-cell" };
const _hoisted_16$1 = { class: "row-ops" };
const _hoisted_17$1 = ["title"];
const _hoisted_18$1 = {
  key: 1,
  class: "history-cards"
};
const _hoisted_19$1 = { class: "m-card-head" };
const _hoisted_20$1 = ["title"];
const _hoisted_21$1 = ["title"];
const _hoisted_22$1 = { class: "m-ops-sum" };
const _hoisted_23$1 = ["title"];
const _hoisted_24$1 = ["title"];
const _hoisted_25$1 = { class: "m-card-foot" };

const {computed: computed$1,ref: ref$1} = await importShared('vue');


const _sfc_main$2 = {
  __name: 'HistoryPage',
  props: {
  items: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  keep: { type: Number, default: 200 },
  loading: { type: Boolean, default: false },
  // narrow: 卡片；medium: 紧凑表格；wide: 普通表格
  layout: { type: String, default: 'wide' },
},
  emits: ['refresh', 'rollback', 'reopen', 'delete', 'clear'],
  setup(__props, { emit: __emit }) {

/**
 * 历史页：结果、耗时、回滚（有备份才显示）、重新打开（回填编辑器）、删除记录
 */
const props = __props;

const emit = __emit;

const narrow = computed$1(() => props.layout === 'narrow');
const medium = computed$1(() => props.layout === 'medium');

const filter = ref$1('all');
const filterItems = [
  { title: '全部', value: 'all' },
  { title: '成功', value: 'success' },
  { title: '失败', value: 'failed' },
  { title: '取消', value: 'cancelled' },
];

const filtered = computed$1(() => {
  if (filter.value === 'all') return props.items
  return props.items.filter((item) => item.status === filter.value)
});

const STATUS_MAP = {
  success: { text: '成功', cls: 'ok' },
  failed: { text: '失败', cls: 'fail' },
  cancelled: { text: '取消', cls: 'cancel' },
  interrupted: { text: '中断', cls: 'cancel' },
  running: { text: '运行中', cls: 'run' },
};

function statusOf(item) {
  const found = STATUS_MAP[item.status];
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
  emit('reopen', item);
}

function rollback(item) {
  if (!canRollback(item)) return
  emit('rollback', item);
}

return (_ctx, _cache) => {
  const _component_v_select = _resolveComponent$2("v-select");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_skeleton_loader = _resolveComponent$2("v-skeleton-loader");
  const _component_v_card = _resolveComponent$2("v-card");
  const _component_v_spacer = _resolveComponent$2("v-spacer");

  return (_openBlock$2(), _createElementBlock$2("div", {
    class: _normalizeClass$1(["history-page", { 'history-page--medium': medium.value }])
  }, [
    _createElementVNode$2("div", _hoisted_1$2, [
      _cache[4] || (_cache[4] = _createElementVNode$2("h2", { class: "page-title" }, "历史", -1)),
      _createElementVNode$2("span", _hoisted_2$2, "共 " + _toDisplayString$2(__props.total || __props.items.length) + " 条 · 保留最近 " + _toDisplayString$2(__props.keep) + " 条", 1),
      _createElementVNode$2("div", _hoisted_3$2, [
        _createVNode$2(_component_v_select, {
          modelValue: filter.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((filter).value = $event)),
          items: filterItems,
          density: "compact",
          variant: "outlined",
          "hide-details": "",
          class: "filter-select"
        }, null, 8, ["modelValue"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "text",
          color: "error",
          "prepend-icon": "mdi-delete-sweep-outline",
          disabled: !__props.items.length,
          onClick: _cache[1] || (_cache[1] = $event => (emit('clear')))
        }, {
          default: _withCtx$2(() => [...(_cache[3] || (_cache[3] = [
            _createTextVNode$2(" 清空历史 ", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createVNode$2(_component_v_btn, {
          size: "small",
          variant: "text",
          icon: "mdi-refresh",
          loading: __props.loading,
          title: "刷新",
          onClick: _cache[2] || (_cache[2] = $event => (emit('refresh')))
        }, null, 8, ["loading"])
      ])
    ]),
    (__props.loading && !__props.items.length)
      ? (_openBlock$2(), _createBlock$2(_component_v_skeleton_loader, {
          key: 0,
          type: "list-item@4"
        }))
      : (!filtered.value.length)
        ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_4$2, _toDisplayString$2(__props.items.length ? '没有符合筛选条件的记录' : '还没有处理记录。完成一次任务后会出现在这里。'), 1))
        : (_openBlock$2(), _createElementBlock$2(_Fragment$1, { key: 2 }, [
            (!narrow.value)
              ? (_openBlock$2(), _createBlock$2(_component_v_card, {
                  key: 0,
                  variant: "flat",
                  class: "history-table-card"
                }, {
                  default: _withCtx$2(() => [
                    _createElementVNode$2("table", _hoisted_5$2, [
                      _cache[8] || (_cache[8] = _createElementVNode$2("thead", null, [
                        _createElementVNode$2("tr", null, [
                          _createElementVNode$2("th", { class: "col-time" }, "时间"),
                          _createElementVNode$2("th", null, "文件"),
                          _createElementVNode$2("th", { class: "col-output" }, "输出位置"),
                          _createElementVNode$2("th", { class: "col-summary" }, "操作摘要"),
                          _createElementVNode$2("th", { class: "col-result" }, "结果"),
                          _createElementVNode$2("th", { class: "col-duration" }, "耗时"),
                          _createElementVNode$2("th", { class: "col-ops" })
                        ])
                      ], -1)),
                      _createElementVNode$2("tbody", null, [
                        (_openBlock$2(true), _createElementBlock$2(_Fragment$1, null, _renderList$1(filtered.value, (item) => {
                          return (_openBlock$2(), _createElementBlock$2("tr", {
                            key: item.id
                          }, [
                            _createElementVNode$2("td", _hoisted_6$2, _toDisplayString$2(_unref$1(fmtDateTime)(item.created_at, true)), 1),
                            _createElementVNode$2("td", _hoisted_7$1, [
                              _createElementVNode$2("div", {
                                class: "file-name",
                                title: item.path
                              }, [
                                _createTextVNode$2(_toDisplayString$2(item.name || item.path) + " ", 1),
                                (warningList(item).length)
                                  ? (_openBlock$2(), _createElementBlock$2("span", {
                                      key: 0,
                                      class: "warn-flag",
                                      title: warningText(item)
                                    }, "⚠", 8, _hoisted_9$1))
                                  : _createCommentVNode$2("", true)
                              ], 8, _hoisted_8$1),
                              (item.engine)
                                ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_10$1, _toDisplayString$2(item.engine), 1))
                                : _createCommentVNode$2("", true)
                            ]),
                            _createElementVNode$2("td", {
                              class: "output-cell mono",
                              title: item.output_path || '—'
                            }, _toDisplayString$2(item.output_path || '—'), 9, _hoisted_11$1),
                            _createElementVNode$2("td", _hoisted_12$1, _toDisplayString$2(summaryText(item)), 1),
                            _createElementVNode$2("td", _hoisted_13$1, [
                              _createElementVNode$2("span", {
                                class: _normalizeClass$1(["badge-state", `badge-state--${statusOf(item).cls}`])
                              }, _toDisplayString$2(statusOf(item).text), 3)
                            ]),
                            _createElementVNode$2("td", _hoisted_14$1, _toDisplayString$2(_unref$1(fmtDuration)(item.duration)), 1),
                            _createElementVNode$2("td", _hoisted_15$1, [
                              _createElementVNode$2("div", _hoisted_16$1, [
                                (backupState(item))
                                  ? (_openBlock$2(), _createElementBlock$2("span", {
                                      key: 0,
                                      class: _normalizeClass$1(["backup-state", `backup-state--${backupState(item).cls}`]),
                                      title: backupState(item).text
                                    }, _toDisplayString$2(backupState(item).text), 11, _hoisted_17$1))
                                  : _createCommentVNode$2("", true),
                                (canRollback(item))
                                  ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                                      key: 1,
                                      size: "x-small",
                                      variant: "tonal",
                                      onClick: $event => (rollback(item))
                                    }, {
                                      default: _withCtx$2(() => [...(_cache[5] || (_cache[5] = [
                                        _createTextVNode$2("回滚", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["onClick"]))
                                  : _createCommentVNode$2("", true),
                                _createVNode$2(_component_v_btn, {
                                  size: "x-small",
                                  variant: "tonal",
                                  title: item.plan ? '按记录里的编辑配置回填编辑器' : '该记录没有配置，只打开文件',
                                  onClick: $event => (reopen(item))
                                }, {
                                  default: _withCtx$2(() => [...(_cache[6] || (_cache[6] = [
                                    _createTextVNode$2(" 重新打开 ", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["title", "onClick"]),
                                _createVNode$2(_component_v_btn, {
                                  size: "x-small",
                                  variant: "tonal",
                                  color: "error",
                                  title: "删除这条历史记录（不影响备份文件）",
                                  onClick: $event => (emit('delete', item))
                                }, {
                                  default: _withCtx$2(() => [...(_cache[7] || (_cache[7] = [
                                    _createTextVNode$2(" 删除 ", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["onClick"])
                              ])
                            ])
                          ]))
                        }), 128))
                      ])
                    ])
                  ]),
                  _: 1
                }))
              : (_openBlock$2(), _createElementBlock$2("div", _hoisted_18$1, [
                  (_openBlock$2(true), _createElementBlock$2(_Fragment$1, null, _renderList$1(filtered.value, (item) => {
                    return (_openBlock$2(), _createElementBlock$2("div", {
                      key: item.id,
                      class: "m-card"
                    }, [
                      _createElementVNode$2("div", _hoisted_19$1, [
                        _createElementVNode$2("span", {
                          class: _normalizeClass$1(["badge-state", `badge-state--${statusOf(item).cls}`])
                        }, _toDisplayString$2(statusOf(item).text), 3),
                        _createElementVNode$2("span", {
                          class: "m-name",
                          title: item.path
                        }, _toDisplayString$2(item.name || item.path), 9, _hoisted_20$1),
                        (warningList(item).length)
                          ? (_openBlock$2(), _createElementBlock$2("span", {
                              key: 0,
                              class: "warn-flag",
                              title: warningText(item)
                            }, "⚠", 8, _hoisted_21$1))
                          : _createCommentVNode$2("", true)
                      ]),
                      _createElementVNode$2("div", _hoisted_22$1, [
                        _createTextVNode$2(_toDisplayString$2(summaryText(item)) + " ", 1),
                        (backupState(item))
                          ? (_openBlock$2(), _createElementBlock$2("span", {
                              key: 0,
                              class: _normalizeClass$1(["backup-state", `backup-state--${backupState(item).cls}`]),
                              title: backupState(item).text
                            }, " · " + _toDisplayString$2(backupState(item).text), 11, _hoisted_23$1))
                          : _createCommentVNode$2("", true)
                      ]),
                      _createElementVNode$2("div", {
                        class: "m-output mono",
                        title: item.output_path || '—'
                      }, "输出：" + _toDisplayString$2(item.output_path || '—'), 9, _hoisted_24$1),
                      _createElementVNode$2("div", _hoisted_25$1, [
                        _createElementVNode$2("span", null, _toDisplayString$2(_unref$1(fmtDateTime)(item.created_at, true)) + " · " + _toDisplayString$2(_unref$1(fmtDuration)(item.duration)), 1),
                        _createVNode$2(_component_v_spacer),
                        (canRollback(item))
                          ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                              key: 0,
                              size: "small",
                              variant: "tonal",
                              onClick: $event => (rollback(item))
                            }, {
                              default: _withCtx$2(() => [...(_cache[9] || (_cache[9] = [
                                _createTextVNode$2("回滚", -1)
                              ]))]),
                              _: 1
                            }, 8, ["onClick"]))
                          : _createCommentVNode$2("", true),
                        _createVNode$2(_component_v_btn, {
                          size: "small",
                          variant: "tonal",
                          title: item.plan ? '按记录里的编辑配置回填编辑器' : '该记录没有配置，只打开文件',
                          onClick: $event => (reopen(item))
                        }, {
                          default: _withCtx$2(() => [...(_cache[10] || (_cache[10] = [
                            _createTextVNode$2(" 重新打开 ", -1)
                          ]))]),
                          _: 1
                        }, 8, ["title", "onClick"]),
                        _createVNode$2(_component_v_btn, {
                          size: "small",
                          variant: "tonal",
                          color: "error",
                          onClick: $event => (emit('delete', item))
                        }, {
                          default: _withCtx$2(() => [...(_cache[11] || (_cache[11] = [
                            _createTextVNode$2("删除", -1)
                          ]))]),
                          _: 1
                        }, 8, ["onClick"])
                      ])
                    ]))
                  }), 128))
                ])),
            _cache[12] || (_cache[12] = _createElementVNode$2("div", { class: "page-tip" }, "临时备份策略：原地替换成功后会删除临时备份（不可回滚）；失败时保留备份并可回滚；未做临时备份的记录无恢复副本。「重新打开」会按记录里的配置回填轨道 / 附件 / 章节 / 输出（旧记录没有配置时只打开文件）；删除历史只移除记录，不会删除备份文件。⚠ 标记表示该记录带有时长/轨道等告警。", -1))
          ], 64))
  ], 2))
}
}

};
const HistoryPage = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-03b6e9c8"]]);

const {toDisplayString:_toDisplayString$1,createElementVNode:_createElementVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1,renderSlot:_renderSlot,createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,createBlock:_createBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "confirm-head" };
const _hoisted_2$1 = { class: "confirm-title" };
const _hoisted_3$1 = { class: "confirm-body" };
const _hoisted_4$1 = {
  key: 0,
  class: "confirm-text"
};
const _hoisted_5$1 = {
  key: 1,
  class: "confirm-detail"
};
const _hoisted_6$1 = { class: "confirm-foot" };


const _sfc_main$1 = {
  __name: 'ConfirmDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '确认操作' },
  text: { type: String, default: '' },
  detail: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  color: { type: String, default: 'primary' },
  loading: { type: Boolean, default: false },
},
  emits: ['update:modelValue', 'confirm'],
  setup(__props, { emit: __emit }) {

/**
 * 通用二次确认弹窗
 */
const props = __props;

const emit = __emit;

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createBlock$1(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "480",
    "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => (emit('update:modelValue', $event)))
  }, {
    default: _withCtx$1(() => [
      _createVNode$1(_component_v_card, { class: "confirm-card" }, {
        default: _withCtx$1(() => [
          _createElementVNode$1("div", _hoisted_1$1, [
            _createElementVNode$1("span", _hoisted_2$1, _toDisplayString$1(__props.title), 1)
          ]),
          _createElementVNode$1("div", _hoisted_3$1, [
            (__props.text)
              ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_4$1, _toDisplayString$1(__props.text), 1))
              : _createCommentVNode$1("", true),
            (__props.detail)
              ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_5$1, _toDisplayString$1(__props.detail), 1))
              : _createCommentVNode$1("", true),
            _renderSlot(_ctx.$slots, "default", {}, undefined, true)
          ]),
          _createElementVNode$1("div", _hoisted_6$1, [
            _createVNode$1(_component_v_btn, {
              variant: "text",
              disabled: __props.loading,
              onClick: _cache[0] || (_cache[0] = $event => (emit('update:modelValue', false)))
            }, {
              default: _withCtx$1(() => [...(_cache[3] || (_cache[3] = [
                _createTextVNode$1("取消", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$1(_component_v_btn, {
              color: props.color,
              variant: "flat",
              loading: __props.loading,
              onClick: _cache[1] || (_cache[1] = $event => (emit('confirm')))
            }, {
              default: _withCtx$1(() => [
                _createTextVNode$1(_toDisplayString$1(__props.confirmText), 1)
              ]),
              _: 1
            }, 8, ["color", "loading"])
          ])
        ]),
        _: 3
      })
    ]),
    _: 3
  }, 8, ["model-value"]))
}
}

};
const ConfirmDialog = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-f724bb26"]]);

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,unref:_unref,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass,renderList:_renderList,Fragment:_Fragment,createBlock:_createBlock,normalizeStyle:_normalizeStyle} = await importShared('vue');


const _hoisted_1 = {
  key: 0,
  class: "mkv-disabled-mask"
};
const _hoisted_2 = { class: "mkv-disabled-card" };
const _hoisted_3 = { class: "mkv-disabled-actions" };
const _hoisted_4 = { class: "mkv-header" };
const _hoisted_5 = { class: "mkv-brand" };
const _hoisted_6 = ["src"];
const _hoisted_7 = {
  key: 0,
  class: "mkv-brand-text"
};
const _hoisted_8 = {
  key: 1,
  class: "mkv-ver"
};
const _hoisted_9 = {
  key: 2,
  class: "mkv-ver mkv-ver--ui"
};
const _hoisted_10 = {
  key: 0,
  class: "mkv-engine-chips"
};
const _hoisted_11 = ["title"];
const _hoisted_12 = { class: "mkv-nav" };
const _hoisted_13 = ["onClick"];
const _hoisted_14 = {
  key: 0,
  class: "mkv-nav-badge"
};
const _hoisted_15 = ["title"];
const _hoisted_16 = {
  key: 1,
  class: "mkv-banner"
};
const _hoisted_17 = { class: "mkv-body" };
const _hoisted_18 = {
  key: 0,
  class: "mkv-edit"
};
const _hoisted_19 = {
  key: 0,
  class: "mkv-tree-panel"
};
const _hoisted_20 = { class: "mkv-editor" };
const _hoisted_21 = {
  key: 0,
  class: "mkv-mobile-bar"
};
const _hoisted_22 = ["title"];
const _hoisted_23 = {
  key: 2,
  class: "editing-banner"
};
const _hoisted_24 = { class: "editing-banner-text" };
const _hoisted_25 = {
  key: 4,
  class: "mkv-empty-editor"
};
const _hoisted_26 = { class: "mkv-empty-title" };
const _hoisted_27 = { class: "file-head" };
const _hoisted_28 = { class: "file-head-main" };
const _hoisted_29 = { class: "file-title-row" };
const _hoisted_30 = ["title"];
const _hoisted_31 = ["title"];
const _hoisted_32 = { class: "file-actions" };
const _hoisted_33 = { class: "submit-status-text" };
const _hoisted_34 = { class: "info-strip" };
const _hoisted_35 = { class: "info-chip" };
const _hoisted_36 = { class: "info-chip" };
const _hoisted_37 = { class: "info-chip" };
const _hoisted_38 = { class: "info-chip" };
const _hoisted_39 = { class: "info-chip" };
const _hoisted_40 = { class: "info-chip" };
const _hoisted_41 = { class: "mkv-editor-tabs" };
const _hoisted_42 = ["onClick"];
const _hoisted_43 = {
  key: 1,
  class: "mkv-panel"
};
const _hoisted_44 = {
  key: 0,
  class: "kv-grid"
};
const _hoisted_45 = { class: "kv-item" };
const _hoisted_46 = { class: "kv-item" };
const _hoisted_47 = { class: "kv-item" };
const _hoisted_48 = { class: "kv-item" };
const _hoisted_49 = { class: "kv-item" };
const _hoisted_50 = { class: "kv-item" };
const _hoisted_51 = { class: "kv-item" };
const _hoisted_52 = { class: "kv-item" };
const _hoisted_53 = {
  key: 1,
  class: "mkv-empty-tip"
};
const _hoisted_54 = {
  key: 2,
  class: "mkv-panel"
};
const _hoisted_55 = {
  key: 3,
  class: "mkv-panel"
};
const _hoisted_56 = {
  key: 4,
  class: "mkv-panel"
};
const _hoisted_57 = {
  key: 0,
  class: "mkv-empty-tip"
};
const _hoisted_58 = {
  key: 1,
  class: "attach-table"
};
const _hoisted_59 = ["title"];
const _hoisted_60 = {
  key: 0,
  class: "attach-tag"
};
const _hoisted_61 = { class: "col-mime" };
const _hoisted_62 = { class: "col-size" };
const _hoisted_63 = { class: "col-ops" };
const _hoisted_64 = { class: "attach-ops" };
const _hoisted_65 = {
  key: 2,
  class: "attach-cards"
};
const _hoisted_66 = { class: "attach-card-main" };
const _hoisted_67 = ["title"];
const _hoisted_68 = { class: "attach-sub" };
const _hoisted_69 = {
  key: 0,
  class: "attach-tag"
};
const _hoisted_70 = { class: "mkv-add-row" };
const _hoisted_71 = { class: "archive-hint" };
const _hoisted_72 = {
  key: 5,
  class: "mkv-panel"
};
const _hoisted_73 = { class: "mkv-form-row" };
const _hoisted_74 = { class: "mkv-form-value" };
const _hoisted_75 = ["title"];
const _hoisted_76 = { class: "mkv-form-row" };
const _hoisted_77 = { class: "mkv-form-value" };
const _hoisted_78 = { class: "mkv-sec-title" };
const _hoisted_79 = {
  key: 0,
  class: "chapter-table"
};
const _hoisted_80 = { class: "chapter-time" };
const _hoisted_81 = {
  key: 1,
  class: "mkv-empty-tip"
};
const _hoisted_82 = {
  key: 6,
  class: "mkv-panel"
};
const _hoisted_83 = { class: "extra-args-actions" };
const _hoisted_84 = {
  key: 0,
  class: "extra-args-msg extra-args-msg--error"
};
const _hoisted_85 = {
  key: 1,
  class: "extra-args-msg extra-args-msg--ok"
};
const _hoisted_86 = { class: "output-box" };
const _hoisted_87 = { class: "radio" };
const _hoisted_88 = ["checked"];
const _hoisted_89 = {
  key: 1,
  class: "output-tag output-tag--warn"
};
const _hoisted_90 = {
  key: 2,
  class: "output-tag"
};
const _hoisted_91 = ["checked", "disabled"];
const _hoisted_92 = {
  key: 8,
  class: "output-hint output-hint--warn"
};
const _hoisted_93 = { key: 0 };
const _hoisted_94 = { key: 1 };
const _hoisted_95 = ["title"];
const _hoisted_96 = {
  key: 10,
  class: "no-backup-row"
};
const _hoisted_97 = { class: "execute-row" };
const _hoisted_98 = { class: "execute-btns" };
const _hoisted_99 = {
  key: 3,
  class: "mkv-settings-wrap"
};
const _hoisted_100 = { class: "mkv-settings-bar" };
const _hoisted_101 = { class: "mkv-settings-body" };
const _hoisted_102 = {
  key: 2,
  class: "mkv-bottombar"
};
const _hoisted_103 = {
  key: 0,
  class: "bottom-text"
};
const _hoisted_104 = {
  key: 1,
  class: "bottom-text"
};
const _hoisted_105 = {
  key: 2,
  class: "bottom-progress"
};
const _hoisted_106 = {
  key: 3,
  class: "bottom-extra"
};
const _hoisted_107 = {
  key: 4,
  class: "bottom-text"
};
const _hoisted_108 = { class: "mkv-tree-dialog-head" };
const _hoisted_109 = { class: "mkv-tree-dialog-body" };
const _hoisted_110 = { class: "duplicate-head" };
const _hoisted_111 = { class: "duplicate-title" };
const _hoisted_112 = { class: "duplicate-body" };
const _hoisted_113 = { key: 0 };
const _hoisted_114 = { key: 1 };
const _hoisted_115 = { class: "duplicate-foot" };
const _hoisted_116 = { class: "archive-head" };
const _hoisted_117 = { class: "archive-body" };
const _hoisted_118 = { class: "archive-recursive" };
const _hoisted_119 = { class: "archive-support" };
const _hoisted_120 = { class: "archive-foot" };

const {computed,getCurrentInstance,inject,onBeforeUnmount,onMounted,ref,watch} = await importShared('vue');

const {useDisplay} = await importShared('vuetify');

const UI_BUILD = '0.1.50';

const _sfc_main = {
  __name: 'AppPage',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MkvToolkit' },
  navKey: { type: String, default: 'main' },
  initialConfig: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  showClose: { type: Boolean, default: false },
},
  emits: ['action', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

/**
 * MKV 工具箱 · 主页面
 * 顶栏（品牌 / 引擎状态 / 三 Tab / 设置 / 退出）+ 编辑页（目录树 + 编辑器）+ 队列 + 历史 + 设置
 * 编辑页只维护“期望状态”，执行必须走 /plan 预览确认后再入队
 */
const props = __props;

const emit = __emit;
const display = useDisplay();
const mobile = computed(() => !display.mdAndUp.value);
// 按插件根容器自身宽度分三档（PC 模式下视口宽但容器窄，不能只用视口断点）：
// narrow: 真手机竖屏 / 容器 < 720；medium: 720~1100；wide: >= 1100
const rootRef = ref(null);
// 是否运行在宿主「插件卡片弹窗」（PluginDataDialog 的 VDialog）里
const inHostDialog = ref(false);
const containerWidth = ref(0);
const narrow = computed(() => mobile.value || (containerWidth.value > 0 && containerWidth.value < 720));
const medium = computed(() => !narrow.value && containerWidth.value > 0 && containerWidth.value < 1100);
const wide = computed(() => !narrow.value && !medium.value);
const layoutMode = computed(() => (narrow.value ? 'narrow' : medium.value ? 'medium' : 'wide'));
let resizeObserver = null;
const toast = inject('moviepilot:toast', null);
const instance = getCurrentInstance();
const api = createApi(props);

// ---------------------------------------------------------------- 基础状态
const navItems = [
  { key: 'edit', label: '编辑' },
  { key: 'queue', label: '队列' },
  { key: 'history', label: '历史' },
];
const editorTabs = [
  { key: 'video', label: '视频' },
  { key: 'audio', label: '音频' },
  { key: 'subtitle', label: '字幕' },
  { key: 'attach', label: '附件' },
  { key: 'chapter', label: '章节' },
  { key: 'advanced', label: '高级' },
];

const tab = ref('edit');
const status = ref({});
const statusLoaded = ref(false);
const pluginDisabled = computed(() => status.value?.enabled === false);
// 停用遮罩延迟显示：避免弹窗打开瞬间用旧的/未就绪状态闪一下「插件已停用」
const showDisabledMask = ref(false);
let disabledMaskTimer = null;
watch(pluginDisabled, (value) => {
  if (disabledMaskTimer) {
    clearTimeout(disabledMaskTimer);
    disabledMaskTimer = null;
  }
  if (value) {
    disabledMaskTimer = setTimeout(() => {
      if (pluginDisabled.value) showDisabledMask.value = true;
    }, 400);
  } else {
    showDisabledMask.value = false;
  }
}, { immediate: true });
function reloadPage() {
  window.location.reload();
}

/** 停用状态下直接打开本插件设置页（可在「启用插件」开关里重新启用并保存）。 */
function openSettingsFromDisabled() {
  showDisabledMask.value = false;
  switchTab('settings');
}
// 前端构建版本（与后端版本独立，便于确认浏览器加载的是新 bundle）
const config = ref({ ...(props.initialConfig || {}) });
const error = ref('');
const treeDialog = ref(false);
// 递增后 FileTree 重新拉取 /file-statuses（打开文件 / 切换页签时）
const fileStatusTick = ref(0);
// 当前文件的队列/历史状态（提交后状态条 + 标题徽标）
const fileStatusMap = ref({});
const currentFileStatus = ref(null);
const statusDismissed = ref(false);
// 重复提交保护：检测到同 path 的 pending/running 任务时弹出三选一
const duplicateState = ref({ open: false, action: '', conflict: null });
let statusPollTimer = null;
const snackbar = ref({ show: false, text: '', color: 'success' });

// 探测与编辑状态
const currentPath = ref('');
const probe = ref(null);
const probeLoading = ref(false);
const editorTab = ref('video');
const trackViews = ref([]);
const attachments = ref([]);
const siblings = ref([]);
// 自动导入默认值（设置页开关控制打开文件时是否自动挂载）
const autoSubtitle = computed(() => Boolean(config.value.auto_subtitle));
const autoAudio = computed(() => Boolean(config.value.auto_audio));
const autoFonts = computed(() => Boolean(config.value.auto_fonts));
// 由「自动导入 / 挂载按钮」加入的条目路径（用于双向挂载按钮只收回自己加的条目）
const autoMountedPaths = ref({ subtitle: [], audio: [], font: [] });
// 未保存修改基线（关闭文件时用来判断是否需要确认）
const editorBaseline = ref('');
const title = ref('');
const chapterMode = ref('keep');
const chapterFile = ref('');
const extraArgsText = ref('');
// 附加参数「验证并应用」状态
const extraArgsChecking = ref(false);
const extraArgsError = ref('');
const extraArgsOk = ref('');
const outputMode = ref('dir');
const outputDir = ref('');
// 原地替换时不保存备份（不可回滚），仅在 mode=replace 时生效
const noBackup = ref(false);
const savingPlan = ref(false);
const holdSubmitting = ref(false);
// 队列内编辑：非空时两个提交按钮都改为更新该排队任务
const editingJobId = ref('');
const editingJobName = ref('');

// 预览
const previewOpen = ref(false);
const previewLoading = ref(false);
const previewSubmitting = ref(false);
const planResult = ref(null);
// /plan warnings 出现 duration_mismatch 时必须显式勾选「我已知晓」才能提交
const durationMismatchConfirmed = ref(false);
const hasDurationMismatch = computed(() =>
  (planResult.value?.warnings || []).some((item) => (item?.code || '') === 'duration_mismatch'),
);

// 选择器 / 上传
const picker = ref({ open: false, kind: 'subtitle', title: '', initialPath: '', exts: [] });
const uploadDialog = ref({ open: false, kind: 'subtitle' });
// 压缩包解压（字体）
const archiveTools = ref({ tools: {}, extensions: [] });
const archiveLoading = ref(false);
const archiveDialog = ref({ open: false, path: '', recursive: false, loading: false });

// 确认弹窗
const confirmState = ref({
  open: false,
  title: '',
  text: '',
  detail: '',
  confirmText: '确定',
  color: 'primary',
  loading: false,
  action: null,
});

// 队列 / 历史
const queueJobs = ref([]);
const queuePaused = ref(false);
const queueLoading = ref(false);
const historyItems = ref([]);
const historyTotal = ref(0);
const historyLoading = ref(false);

// 安装
const installStarting = ref(false);

let statusTimer = null;
let queueTimer = null;
let installTimer = null;

// ---------------------------------------------------------------- 计算属性
const engine = computed(() => status.value?.engine || {});
computed(() => status.value?.engine_install || {});
const engineReady = computed(() => {
  if (engine.value.mode === 'none') return false
  if (engine.value.mkvmerge?.ok) return true
  return Boolean(config.value.allow_ffmpeg_fallback && engine.value.ffmpeg?.ok)
});
const mkvmergeChip = computed(() => {
  const info = engine.value.mkvmerge || {};
  if (info.ok) return `mkvmerge${info.version ? ` v${info.version}` : ''}`
  return 'mkvmerge 未安装'
});
const ffmpegChip = computed(() => {
  const info = engine.value.ffmpeg || {};
  if (info.ok) return `ffmpeg${info.version ? ` ${info.version}` : ''}`
  return 'ffmpeg 未检测到'
});
const runningJob = computed(() => queueJobs.value.find((job) => job.status === 'running') || null);
// 宿主卡片弹窗里：空状态固定 900 上限；有内容按内容撑高，最高 1000
const hasContent = computed(() => Boolean(
  probe.value
  || currentPath.value
  || runningJob.value
  || queueJobs.value.length
  || historyItems.value.length,
));
const pendingJobs = computed(() => queueJobs.value.filter((job) => job.status === 'pending'));
const queueCount = computed(() => {
  const fromStatus = Number(status.value?.queue?.pending);
  if (Number.isFinite(fromStatus) && fromStatus >= 0) return fromStatus
  return pendingJobs.value.length
});
const queueBadge = computed(() => (queueCount.value > 0 ? queueCount.value : 0));
const hasActiveJobs = computed(() => {
  if (runningJob.value || pendingJobs.value.length) return true
  const queue = status.value?.queue || {};
  return Number(queue.running) > 0 || Number(queue.pending) > 0
});
const bottomBarVisible = computed(() => Boolean(runningJob.value || queueCount.value > 0));

const container = computed(() => probe.value?.container || {});
const videoTrack = computed(() => (probe.value?.tracks || []).find((track) => track.type === 'video') || null);
const chapters = computed(() => probe.value?.chapters || []);
const audioTracks = computed(() => trackViews.value.filter((track) => track.type === 'audio'));
const subtitleTracks = computed(() => trackViews.value.filter((track) => track.type === 'subtitle'));
const mediaTitle = computed(() => (probe.value?.name ? String(probe.value.name) : '未选择文件'));
const sourceExt = computed(() => extName(currentPath.value || '').toLowerCase());
// m2ts/ts 源必须重封装成 MKV：不能原地替换，输出名自动改为 .mkv
const isNonMkvSource = computed(() => Boolean(currentPath.value) && sourceExt.value !== '.mkv');
// 备份目录/保留份数：后端 GET /config 已补默认值，这里再做兜底
const backupDir = computed(() => String(config.value.backup_dir || '/config/plugins/MkvToolkit/backup'));
computed(() => (Number(config.value.backup_keep) > 0 ? Number(config.value.backup_keep) : 3));
const uploadMaxMb = computed(() => (Number(config.value.upload_max_mb) > 0 ? Number(config.value.upload_max_mb) : 50));
// 压缩包支持提示：7z/unrar 都不可用时提示需容器安装
const archiveHint = computed(() => {
  const tools = archiveTools.value?.tools || {};
  if (!tools['7z'] && !tools.unrar) {
    return 'zip/tar 可直接解压；7z/rar 需在容器安装 7z 或 unrar'
  }
  const names = [];
  if (tools['7z'] || tools.unrar) names.push('7z/rar');
  return `支持 zip/tar${names.length ? '、7z/rar' : ''}；解压出的字体自动加入附件`
});
const archiveExtensions = computed(() =>
  Array.isArray(archiveTools.value?.extensions) && archiveTools.value.extensions.length
    ? archiveTools.value.extensions
    : ARCHIVE_EXTENSIONS,
);
// 顶部引擎区的压缩包依赖状态：zip/tar 内置，7z/rar 取决于系统工具
const archiveChipOk = computed(() => {
  const tools = archiveTools.value?.tools || {};
  return Boolean(tools['7z'] || tools.unrar)
});
const archiveChip = computed(() => (archiveChipOk.value ? '压缩包 zip/tar/7z/rar' : '压缩包 zip/tar'));

const runningProgress = computed(() => {
  const value = Number(runningJob.value?.progress);
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
});

// 当前文件状态徽标/状态条文案（pending 阶段为「等待中」时优先显示等待中）
const statusMeta = computed(() => {
  const status = currentFileStatus.value;
  if (!status?.state) return null
  const labels = { pending: '待开始', running: '运行中', success: '已完成', failed: '失败', cancelled: '已取消' };
  let label = labels[status.state] || status.state;
  if (status.state === 'pending' && String(status.stage || '').includes('等待')) label = '等待中';
  return { label, state: status.state, id: status.job_id || '' }
});
const statusBannerVisible = computed(() => Boolean(statusMeta.value) && !statusDismissed.value);

function statusIcon(state) {
  return (
    {
      pending: 'mdi-clock-outline',
      running: 'mdi-progress-clock',
      success: 'mdi-check-circle-outline',
      failed: 'mdi-alert-circle-outline',
      cancelled: 'mdi-cancel',
    }[state] || 'mdi-information-outline'
  )
}

const siblingItems = computed(() => {
  const data = probe.value?.siblings;
  if (!data) return []
  const list = [];
  for (const kind of ['subtitle', 'audio', 'font']) {
    const key = kind === 'subtitle' ? 'subtitles' : kind === 'audio' ? 'audios' : 'fonts';
    for (const item of data[key] || []) {
      list.push({
        key: `${kind}:${item.path}`,
        kind,
        name: item.name,
        path: item.path,
        size: item.size,
        ext: item.ext || extName(item.name),
        language: item.language || '',
        matched: Boolean(item.matched),
        checked: isAddedSource(kind, item.path),
      });
    }
  }
  return list
});

// 同级自动发现面板按页签分类型：字幕/音频/附件各看各的，视频/章节/高级不显示
const siblingKind = computed(() => (editorTab.value === 'audio' ? 'audio' : editorTab.value === 'attach' ? 'font' : 'subtitle'));
const showSiblings = computed(() => ['subtitle', 'audio', 'attach'].includes(editorTab.value));

/** 当前页签可挂载的候选：字幕/音频为前缀匹配项，字体为同目录全部字体。 */
function siblingCandidates(kind) {
  const sib = probe.value?.siblings || {};
  if (kind === 'font') return sib.fonts || []
  return (kind === 'audio' ? sib.audios : sib.subtitles) || []
}

function autoList(kind) {
  return autoMountedPaths.value[kind] || []
}

function isAutoMounted(kind, path) {
  return autoList(kind).includes(path)
}

function markAutoMounted(kind, path) {
  if (!path || isAutoMounted(kind, path)) return
  autoMountedPaths.value = { ...autoMountedPaths.value, [kind]: [...autoList(kind), path] };
}

function forgetAutoMounted(kind, path) {
  if (!path || !isAutoMounted(kind, path)) return
  autoMountedPaths.value = { ...autoMountedPaths.value, [kind]: autoList(kind).filter((item) => item !== path) };
}

function clearAutoMounted() {
  autoMountedPaths.value = { subtitle: [], audio: [], font: [] };
}

// 当前类型可挂载候选是否都已挂载（状态看实际存在，收回只看自动加入的路径集合）
const siblingMounted = computed(() => {
  const kind = siblingKind.value;
  const candidates = siblingCandidates(kind);
  if (!candidates.length) return false
  return candidates.every((item) => isCandidatePresent(kind, item.path))
});

/** 候选是否已存在于编辑器（新增轨道/新增附件）。 */
function isCandidatePresent(kind, path) {
  if (kind === 'font') return attachments.value.some((item) => item.added && item.file?.path === path)
  return trackViews.value.some((track) => track.added && track.file?.path === path)
}

// ---------------------------------------------------------------- 提示
function toastMsg(kind, message) {
  const text = String(message || '');
  if (toast && typeof toast[kind] === 'function') {
    toast[kind](text);
    return
  }
  snackbar.value = {
    show: true,
    text,
    color: kind === 'error' ? 'error' : kind === 'warning' ? 'warning' : kind === 'info' ? 'info' : 'success',
  };
}

// ---------------------------------------------------------------- 配置 / 状态
async function loadConfig() {
  try {
    const data = await api.get('/config');
    config.value = { ...config.value, ...(data || {}) };
  } catch (err) {
    // 配置读取失败时用宿主注入的 initialConfig 兜底
  }
  if (!currentPath.value) {
    outputMode.value = config.value.output_mode || 'dir';
    outputDir.value = config.value.output_dir || '';
  }
}

async function loadStatus() {
  try {
    status.value = await api.get('/status') || {};
    // 诊断用：记录每次 /status 的 enabled，复现“闪现停用页”时可在控制台导出
    if (typeof window !== 'undefined') {
      window.__mkvToolkitStatus = window.__mkvToolkitStatus || [];
      window.__mkvToolkitStatus.push({
        t: new Date().toISOString(),
        enabled: status.value?.enabled,
        version: status.value?.version,
      });
      if (window.__mkvToolkitStatus.length > 300) window.__mkvToolkitStatus.shift();
    }
    if (status.value?.enabled === false) {
      console.warn('[MkvToolkit] /status 返回 enabled=false', status.value?.version);
    }
    if (status.value?.engine_install?.running && !installTimer) {
      installStarting.value = true;
      pollEngineInstall();
    }
  } catch (err) {
    // 轮询失败静默
  }
}

// ---------------------------------------------------------------- 文件状态条 / 轮询
function stopStatusPoll() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
}

/** 拉取 /file-statuses，按当前 path 更新状态条与标题徽标。 */
async function refreshFileStatuses() {
  try {
    const data = await api.get('/file-statuses');
    const map = {};
    for (const item of data?.items || []) {
      if (item?.path) map[item.path] = item;
    }
    fileStatusMap.value = map;
    currentFileStatus.value = currentPath.value ? (map[currentPath.value] || null) : null;
  } catch (err) {
    // 状态读取失败静默，不影响编辑
  }
  ensureStatusPoll();
}

/** 提交/更新成功后立即用返回的 job 填充状态条（无需等下一轮 /file-statuses）。 */
function seedSubmittedJob(job, fallbackPath) {
  const path = job?.path || fallbackPath || currentPath.value;
  if (!path) return
  const entry = {
    path,
    name: baseName(path),
    state: job?.status || 'pending',
    stage: job?.stage || '等待中',
    job_id: job?.id || job?.job_id || '',
    updated_at: '',
  };
  fileStatusMap.value = { ...fileStatusMap.value, [path]: entry };
  if (!currentPath.value || path === currentPath.value) {
    currentFileStatus.value = entry;
    statusDismissed.value = false;
  }
  fileStatusTick.value += 1;
  ensureStatusPoll();
}

/** pending/running 状态下每 5 秒轮询；离开编辑页/关闭文件/终态停止。 */
function ensureStatusPoll() {
  const shouldPoll =
    tab.value === 'edit' &&
    Boolean(currentPath.value) &&
    ['pending', 'running'].includes(currentFileStatus.value?.state);
  if (!shouldPoll) {
    stopStatusPoll();
    return
  }
  if (statusPollTimer) return
  statusPollTimer = setInterval(() => {
    refreshFileStatuses();
  }, 5000);
}

// ---------------------------------------------------------------- 重复提交保护
/** 再请求一次 /file-statuses，判断当前 path 是否已有 pending/running 任务。 */
async function findActiveJobForCurrentPath() {
  if (!currentPath.value) return null
  try {
    const data = await api.get('/file-statuses');
    const map = {};
    for (const item of data?.items || []) {
      if (item?.path) map[item.path] = item;
    }
    fileStatusMap.value = map;
    const hit = map[currentPath.value];
    if (hit) currentFileStatus.value = hit;
    return hit && ['pending', 'running'].includes(hit.state) ? hit : null
  } catch (err) {
    const hit = fileStatusMap.value[currentPath.value];
    return hit && ['pending', 'running'].includes(hit.state) ? hit : null
  }
}

/** 返回 true 表示可继续提交；false 表示已弹出三选一对话框。 */
async function guardDuplicateSubmission(action) {
  // 队列内编辑态：直接走 update，跳过重复保护
  if (editingJobId.value) return true
  const conflict = await findActiveJobForCurrentPath();
  if (!conflict) return true
  duplicateState.value = { open: true, action, conflict };
  return false
}

/** 三选一：更新现有队列任务（只调用 update，不新建）。 */
async function updateExistingJobFromConflict(conflict) {
  const jobId = conflict?.job_id;
  if (!jobId) return
  try {
    const data = await api.post(`/jobs/${encodeURIComponent(jobId)}/update`, { plan: buildPlan() });
    toastMsg('success', '已更新队列任务');
    seedSubmittedJob(data || { id: jobId, status: 'pending', path: currentPath.value });
    await loadQueue(true);
    await loadStatus();
  } catch (err) {
    toastMsg('error', `更新队列任务失败：${err.message}`);
    await refreshFileStatuses();
  }
}

async function chooseDuplicate(choice) {
  const action = duplicateState.value.action;
  const conflict = duplicateState.value.conflict;
  duplicateState.value = { open: false, action: '', conflict: null };
  if (choice === 'cancel') return
  if (choice === 'update') {
    await updateExistingJobFromConflict(conflict);
    return
  }
  // 再提交一个新任务：继续原提交流程
  if (action === 'preview') await openPreview(true);
  else await enqueueHold(true);
}

async function loadQueue(silent = true) {
  if (!silent) queueLoading.value = true;
  try {
    const data = await api.get('/jobs', { status: 'all' });
    queueJobs.value = data?.jobs || [];
    queuePaused.value = Boolean(data?.paused);
  } catch (err) {
    if (!silent) toastMsg('error', `读取队列失败：${err.message}`);
  } finally {
    queueLoading.value = false;
  }
}

async function loadHistory(silent = true) {
  if (!silent) historyLoading.value = true;
  try {
    const data = await api.get('/history', { limit: 50, offset: 0 });
    historyItems.value = data?.items || [];
    historyTotal.value = Number(data?.total) || historyItems.value.length;
  } catch (err) {
    if (!silent) toastMsg('error', `读取历史失败：${err.message}`);
  } finally {
    historyLoading.value = false;
  }
}

// ---------------------------------------------------------------- 文件选择与探测
function dirOf(path) {
  const normalized = String(path || '').replace(/\/+$/, '');
  const index = normalized.lastIndexOf('/');
  return index > 0 ? normalized.slice(0, index) : normalized
}

function applyProbe(data, keepTab = false) {
  probe.value = data || null;
  if (!data) return
  error.value = '';
  if (!keepTab) editorTab.value = 'video';
  title.value = data.container?.title || stripExt(data.name || baseName(data.path));
  trackViews.value = (data.tracks || [])
    .filter((track) => ['video', 'audio', 'subtitle'].includes(track.type))
    .map((track) => ({
      id: track.id,
      type: track.type,
      codec: track.codec,
      codec_detail: track.codec_detail,
      channels: track.channels,
      sample_rate: track.sample_rate,
      width: track.width,
      height: track.height,
      fps: track.fps,
      hdr: track.hdr,
      bitrate: track.bitrate,
      bitrate_estimated: Boolean(track.bitrate_estimated),
      duration: track.duration,
      language: track.language || 'und',
      name: track.name || '',
      default: Boolean(track.default),
      forced: Boolean(track.forced),
      keep: true,
      added: false,
      readonly: track.type === 'video',
      _orig: {
        language: track.language || 'und',
        name: track.name || '',
        default: Boolean(track.default),
        forced: Boolean(track.forced),
      },
    }));
  attachments.value = (data.attachments || []).map((item, index) => ({
    id: item.id ?? index,
    name: item.name,
    mime: item.mime || '',
    size: item.size ?? null,
    keep: true,
    added: false,
  }));
  // 同级自动发现：仅前缀匹配的字幕默认勾选（音频/字体需手动确认）
  siblings.value = [];
  clearAutoMounted();
  const sib = data.siblings || {};
  for (const item of sib.subtitles || []) {
    siblings.value.push({ kind: 'subtitle', ...item, checked: Boolean(item.matched) });
  }
  for (const item of sib.audios || []) {
    siblings.value.push({ kind: 'audio', ...item, checked: false });
  }
  for (const item of sib.fonts || []) {
    siblings.value.push({ kind: 'font', ...item, checked: false });
  }
  chapterMode.value = 'keep';
  chapterFile.value = '';
  extraArgsText.value = '';
  // m2ts/ts 源不能原地替换，强制输出到目录（后端会重封装为 .mkv）
  const nonMkv = extName(data.path || '').toLowerCase() !== '.mkv';
  outputMode.value = nonMkv ? 'dir' : (config.value.output_mode || 'dir');
  outputDir.value = config.value.output_dir || '';
  noBackup.value = false;
  // 打开文件时按当前开关自动导入同级素材（前缀匹配的字幕/音频、同目录字体）
  applyAutoImport();
  editorBaseline.value = editorSnapshot();
}

// ---------------------------------------------------------------- 关闭文件 / 未保存修改
/** 当前编辑状态的稳定快照（用于判断是否有未提交修改）。 */
function editorSnapshot() {
  if (!probe.value) return ''
  return JSON.stringify({
    path: currentPath.value,
    title: title.value,
    chapterMode: chapterMode.value,
    chapterFile: chapterFile.value,
    extraArgsText: extraArgsText.value,
    outputMode: outputMode.value,
    outputDir: outputDir.value,
    noBackup: noBackup.value,
    tracks: trackViews.value.map((track) => ({
      id: track.id,
      keep: track.keep,
      added: track.added,
      language: track.language,
      name: track.name,
      default: Boolean(track.default),
      forced: Boolean(track.forced),
      encoding: track.encoding,
      sync_ms: track.sync_ms,
      file: track.file?.path || '',
    })),
    attachments: attachments.value.map((item) => ({
      id: item.id,
      keep: item.keep,
      added: item.added,
      name: item.name,
      file: item.file?.path || '',
    })),
  })
}

const editorDirty = computed(() => Boolean(probe.value) && editorSnapshot() !== editorBaseline.value);

function doClearFile() {
  currentPath.value = '';
  probe.value = null;
  trackViews.value = [];
  attachments.value = [];
  siblings.value = [];
  title.value = '';
  chapterMode.value = 'keep';
  chapterFile.value = '';
  extraArgsText.value = '';
  outputMode.value = config.value.output_mode || 'dir';
  outputDir.value = config.value.output_dir || '';
  noBackup.value = false;
  error.value = '';
  editingJobId.value = '';
  editingJobName.value = '';
  editorBaseline.value = '';
  currentFileStatus.value = null;
  statusDismissed.value = false;
  stopStatusPoll();
  clearAutoMounted();
}

function clearFile() {
  if (!probe.value) return
  if (!editorDirty.value) {
    doClearFile();
    return
  }
  askConfirm({
    title: '关闭文件',
    text: '当前编辑有未保存的修改，关闭后会丢弃这些修改。',
    confirmText: '丢弃并关闭',
    color: 'warning',
    action: doClearFile,
  });
}

async function loadProbe(path, keepTab = false) {
  if (!path) return false
  probeLoading.value = true;
  error.value = '';
  try {
    const data = await api.post('/probe', { path });
    currentPath.value = path;
    applyProbe(data, keepTab);
    return true
  } catch (err) {
    error.value = err.message;
    toastMsg('error', `探测失败：${err.message}`);
    return false
  } finally {
    probeLoading.value = false;
    // 打开/重新探测文件后刷新状态条
    refreshFileStatuses();
  }
}

function onSelectFile(path) {
  treeDialog.value = false;
  // 编辑队列任务时切换文件，视为放弃本次编辑
  if (editingJobId.value && path !== currentPath.value) {
    editingJobId.value = '';
    editingJobName.value = '';
    toastMsg('info', '已取消队列任务编辑');
  }
  loadProbe(path).finally(() => {
    // 打开文件后刷新文件树的队列/历史状态徽标
    fileStatusTick.value += 1;
  });
}

function reprobe() {
  if (!currentPath.value) return
  loadProbe(currentPath.value, true).finally(() => {
    fileStatusTick.value += 1;
  });
}

/** 复制文本：优先 Clipboard API；http 页面（非安全上下文）回退 execCommand。 */
async function copyToClipboard(text) {
  if (!text) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true
    }
  } catch (err) {
    // 继续尝试回退方案
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, text.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok
  } catch (err) {
    return false
  }
}

async function copyPath() {
  if (!currentPath.value) return
  const ok = await copyToClipboard(currentPath.value);
  if (ok) toastMsg('success', '路径已复制');
  else toastMsg('warning', '复制失败：当前页面不是 https，浏览器禁止剪贴板；请手动选择路径文本');
}

// ---------------------------------------------------------------- 新增轨道 / 附件
function inferLanguage(name) {
  const lower = String(name || '').toLowerCase();
  const map = config.value.language_map || {};
  const entries = Object.entries(map).sort((a, b) => String(b[0]).length - String(a[0]).length);
  for (const [suffix, language] of entries) {
    if (suffix && lower.includes(String(suffix).toLowerCase())) return language
  }
  return 'und'
}

function addTrackFromFile(kind, file, withToast = true) {
  const path = file.path;
  if (trackViews.value.some((track) => track.added && track.file?.path === path)) return false
  const language = file.language || inferLanguage(file.name || path);
  trackViews.value = [
    ...trackViews.value,
    {
      id: `add-${kind}-${path}`,
      type: kind,
      kind,
      added: true,
      keep: true,
      language,
      name: '',
      default: false,
      forced: false,
      encoding: 'auto',
      sync_ms: 0,
      file: {
        name: file.name || baseName(path),
        path,
        size: file.size ?? null,
        ext: file.ext || extName(file.name || path),
      },
    },
  ];
  if (withToast) toastMsg('success', `已添加${kind === 'audio' ? '音频' : '字幕'}：${baseName(path)}`);
  return true
}

function addFontFromFile(file) {
  const path = file.path;
  const name = String(file.name || baseName(path) || '').trim().toLowerCase();
  // 同一路径或同名（忽略大小写）都视为重复：解压出来的同名字体不再重复加入
  const exists = attachments.value.some((item) => {
    const itemPath = item.added ? item.file?.path : item.path;
    const itemName = String(item.name || item.file?.name || '').trim().toLowerCase();
    return (itemPath && itemPath === path) || (name && itemName === name)
  });
  if (exists) return false
  attachments.value = [
    ...attachments.value,
    {
      id: `add-font-${path}`,
      name: file.name || baseName(path),
      mime: '',
      size: file.size ?? null,
      keep: true,
      added: true,
      file: { name: file.name || baseName(path), path, size: file.size ?? null },
    },
  ];
  return true
}

function isAddedSource(kind, path) {
  if (kind === 'font') {
    return attachments.value.some((item) => item.added && item.file?.path === path)
  }
  return trackViews.value.some((track) => track.added && track.file?.path === path)
}

function toggleSibling(item, value) {
  if (item.kind === 'font') {
    if (value) addFontFromFile(item);
    else {
      attachments.value = attachments.value.filter((entry) => !(entry.added && entry.file?.path === item.path));
      forgetAutoMounted('font', item.path);
    }
    return
  }
  if (value) {
    addTrackFromFile(item.kind, item);
  } else {
    trackViews.value = trackViews.value.filter((track) => !(track.added && track.file?.path === item.path));
    forgetAutoMounted(item.kind, item.path);
  }
}

// ---------------------------------------------------------------- 自动导入 / 挂载（打开文件时 + 双向挂载按钮）
/** 按设置默认值自动导入：字幕/音频只取前缀匹配（matched），字体取同目录（含 fonts/ 子目录）全部，并记录路径。 */
function applyAutoImport() {
  const sib = probe.value?.siblings || {};
  if (autoSubtitle.value) {
    for (const item of sib.subtitles || []) {
      if (item.matched && addTrackFromFile('subtitle', item, false)) markAutoMounted('subtitle', item.path);
    }
  }
  if (autoAudio.value) {
    for (const item of sib.audios || []) {
      if (item.matched && addTrackFromFile('audio', item, false)) markAutoMounted('audio', item.path);
    }
  }
  if (autoFonts.value) {
    for (const item of sib.fonts || []) {
      if (addFontFromFile(item)) markAutoMounted('font', item.path);
    }
  }
}

const KIND_LABEL_TEXT = { subtitle: '同名字幕', audio: '同名音频', font: '同目录字体' };

/** 挂载当前页签类型的所有候选，并记录路径。 */
function mountSiblings(kind = 'subtitle') {
  const candidates = siblingCandidates(kind);
  let count = 0;
  for (const item of candidates) {
    const ok = kind === 'font' ? addFontFromFile(item) : addTrackFromFile(kind, item, false);
    if (ok) {
      count += 1;
      // 只记录由挂载按钮/自动导入加入的路径，收回时也只删这些
      markAutoMounted(kind, item.path);
    }
  }
  const label = KIND_LABEL_TEXT[kind] || '候选';
  if (count) toastMsg('success', `已挂载 ${count} 个${label}`);
  else if (candidates.length) toastMsg('info', `${label}都已在列表中`);
  else toastMsg('info', `没有可挂载的${label}`);
}

/** 收回当前页签由自动导入/挂载按钮加入的条目（用户手动加的不动）。 */
function unmountSiblings(kind = 'subtitle') {
  const paths = new Set(autoList(kind));
  let count = 0;
  if (kind === 'font') {
    const before = attachments.value.length;
    attachments.value = attachments.value.filter((item) => !(item.added && paths.has(item.file?.path)));
    count = before - attachments.value.length;
  } else {
    const before = trackViews.value.length;
    trackViews.value = trackViews.value.filter((track) => !(track.added && paths.has(track.file?.path)));
    count = before - trackViews.value.length;
  }
  autoMountedPaths.value = { ...autoMountedPaths.value, [kind]: [] };
  const label = KIND_LABEL_TEXT[kind] || '候选';
  if (count) toastMsg('success', `已收回 ${count} 个${label}`);
  else toastMsg('info', `没有可收回的${label}`);
}

function toggleSiblingMount() {
  const kind = siblingKind.value;
  if (siblingMounted.value) unmountSiblings(kind);
  else mountSiblings(kind);
}

/** 附件区：扫描同目录字体（含 fonts/ 子目录）并全部加入附件（按路径去重）。 */
function scanSiblingFonts() {
  const fonts = probe.value?.siblings?.fonts || [];
  let count = 0;
  for (const item of fonts) {
    const before = attachments.value.length;
    addFontFromFile(item);
    if (attachments.value.length > before) count += 1;
  }
  if (count) toastMsg('success', `已扫描并挂载 ${count} 个同目录字体`);
  else if (fonts.length) toastMsg('info', '同目录字体都已在附件列表中');
  else toastMsg('info', '同目录（含 fonts/ 子目录）没有发现字体文件');
}

function moveTrack(track, delta) {
  // 同类轨道内自由移动（不区分原有 / 新增），其它类型轨道位置保持不变
  const sameType = trackViews.value.filter((item) => item.type === track.type);
  const index = sameType.findIndex((item) => item.id === track.id);
  const neighbor = sameType[index + delta];
  if (!neighbor) return
  const list = [...trackViews.value];
  const from = list.findIndex((item) => item.id === track.id);
  const to = list.findIndex((item) => item.id === neighbor.id);
  if (from < 0 || to < 0) return
  list.splice(from, 1);
  list.splice(to, 0, track);
  trackViews.value = list;
}

function removeTrack(track) {
  if (track.added) {
    trackViews.value = trackViews.value.filter((item) => item.id !== track.id);
    forgetAutoMounted(track.type === 'audio' ? 'audio' : 'subtitle', track.file?.path);
    return
  }
  if (track.readonly) return
  track.keep = !track.keep;
}

// 估偏移：调用 /analyze/offset，把 offset_ms 写回新增轨的 sync_ms（实验能力，需用户确认）
async function estimateTrackOffset(track) {
  if (!track || !track.added || !track.file?.path || !currentPath.value || track._estimating) return
  track._estimating = true;
  try {
    const data = await api.post('/analyze/offset', {
      path: currentPath.value,
      file: track.file.path,
      kind: track.kind || (track.type === 'subtitle' ? 'subtitle' : 'audio'),
    });
    const offset = Math.round(Number(data?.offset_ms) || 0);
    track.sync_ms = offset;
    // 后端 confidence 已是 0~100 的整数百分比，不要再乘 100
    const confidence = Math.max(0, Math.min(100, Math.round(Number(data?.confidence) || 0)));
    const reliable = data?.reliable !== false;
    const hint = String(data?.hint || '').trim();
    track._offsetHint = [hint, `置信度 ${confidence}%`, data?.margin != null ? `margin ${data.margin}` : '']
      .filter(Boolean)
      .join('；');
    if (offset === 0) {
      // 原本就对齐：不写 sync，提示无需调整
      toastMsg('success', `已对齐，无需调整（置信度 ${confidence}%）`);
    } else if (reliable) {
      toastMsg('success', `估计偏移 ${offset >= 0 ? '+' : ''}${offset}ms（置信度 ${confidence}%）`);
    } else {
      toastMsg('warning', '估计不可靠（可能不是同一版本），请确认后再用');
    }
  } catch (err) {
    toastMsg('error', `估计偏移失败：${err.message}`);
  } finally {
    track._estimating = false;
  }
}

function toggleAttachment(item) {
  if (item.added) {
    attachments.value = attachments.value.filter((entry) => entry.id !== item.id);
    forgetAutoMounted('font', item.file?.path);
    return
  }
  item.keep = !item.keep;
}

// 附件 MIME → 可读类型
function attachmentType(item) {
  const mime = String(item?.mime || '').toLowerCase();
  const ext = extName(item?.name || '');
  if (mime.includes('truetype') || ext === '.ttf') return 'TrueType'
  if (mime.includes('opentype') || ext === '.otf') return 'OpenType'
  if (mime.includes('collection') || ext === '.ttc') return 'TrueType Collection'
  return '字体'
}

function resetEditor() {
  if (probe.value) {
    applyProbe(probe.value, true);
    toastMsg('info', '已重置本次编辑');
  }
}

// ---------------------------------------------------------------- 压缩包解压（字体）
async function loadArchiveTools() {
  try {
    const data = await api.get('/archive/tools');
    archiveTools.value = {
      tools: data?.tools || {},
      extensions: Array.isArray(data?.extensions) ? data.extensions : [],
    };
  } catch (err) {
    // 能力读取失败时用前端默认扩展名兜底
  }
}

/** 把 /archive/extract 返回的字体加入附件：同名/同路径跳过，返回 {added, skipped}。 */
function addArchiveFonts(data) {
  let added = 0;
  let skipped = 0;
  const seen = new Set();
  for (const item of data?.items || []) {
    if (!item?.path) continue
    const name = String(item.name || baseName(item.path) || '').trim().toLowerCase();
    if (name && seen.has(name)) {
      skipped += 1;
      continue
    }
    if (name) seen.add(name);
    if (addFontFromFile({
      name: item.name || baseName(item.path),
      path: item.path,
      size: item.size ?? null,
      ext: item.ext || extName(item.name || item.path),
    })) {
      added += 1;
    } else {
      skipped += 1;
    }
  }
  const errors = (data?.archives || []).filter((item) => item?.error);
  if (errors.length) toastMsg('warning', errors[0].error);
  return { added, skipped }
}

/** 生成解压结果的提示文案。 */
function archiveToast(prefix, result) {
  const parts = [`${prefix} ${result.added} 个字体`];
  if (result.skipped) parts.push(`跳过 ${result.skipped} 个重复/已在列表`);
  return parts.join('，')
}

/** 单个压缩包：从目录选择后立即解压。 */
async function extractArchiveFile(path) {
  if (!path || archiveLoading.value) return
  archiveLoading.value = true;
  try {
    const data = await api.post('/archive/extract', { path });
    const result = addArchiveFonts(data);
    if (result.added) toastMsg('success', archiveToast('已解压', result));
    else if (result.skipped) toastMsg('info', `字体都已在附件列表中（跳过 ${result.skipped} 个重复）`);
    else if (!(data?.archives || []).some((item) => item?.error)) toastMsg('info', '压缩包里没有字体文件');
  } catch (err) {
    toastMsg('error', `解压失败：${err.message}`);
  } finally {
    archiveLoading.value = false;
  }
}

function openArchivePicker() {
  const base = currentPath.value || probe.value?.path || '';
  picker.value = {
    open: true,
    kind: 'archive',
    title: '选择字体压缩包',
    initialPath: base ? dirOf(base) : (config.value.roots?.[0] || ''),
    exts: archiveExtensions.value.length ? archiveExtensions.value : ARCHIVE_EXTENSIONS,
  };
}

function openArchiveBatch() {
  const base = currentPath.value || probe.value?.path || '';
  archiveDialog.value = {
    open: true,
    path: base ? dirOf(base) : (config.value.roots?.[0] || ''),
    recursive: false,
    loading: false,
  };
}

/** 目录批量解压：可包含子目录，扫描目录下压缩包并解出字体。 */
async function runArchiveBatch() {
  const dialog = archiveDialog.value;
  if (dialog.loading) return
  if (!String(dialog.path || '').trim()) {
    toastMsg('warning', '请输入要扫描的目录路径');
    return
  }
  dialog.loading = true;
  try {
    const data = await api.post('/archive/extract', {
      path: String(dialog.path).trim(),
      recursive: Boolean(dialog.recursive),
    });
    const result = addArchiveFonts(data);
    const scanned = Array.isArray(data?.archives) ? data.archives.length : 0;
    if (result.added) {
      toastMsg('success', `扫描 ${scanned} 个压缩包，${archiveToast('解压', result)}`);
    } else if (result.skipped) {
      toastMsg('info', `扫描 ${scanned} 个压缩包，字体都已在附件列表中（跳过 ${result.skipped} 个重复）`);
    } else {
      toastMsg('info', `扫描 ${scanned} 个压缩包，没有找到可加入的字体`);
    }
    dialog.open = false;
  } catch (err) {
    toastMsg('error', `解压失败：${err.message}`);
  } finally {
    dialog.loading = false;
  }
}

// ---------------------------------------------------------------- 选择器 / 上传
function openPicker(kind) {
  const titles = { subtitle: '选择字幕文件', audio: '选择音频文件', font: '选择字体文件', chapter: '选择章节文件' };
  picker.value = {
    open: true,
    kind,
    title: titles[kind] || '选择文件',
    initialPath: currentPath.value ? dirOf(currentPath.value) : (config.value.roots?.[0] || ''),
    exts: kind === 'chapter' ? ['.xml', '.txt', '.ogm'] : [],
  };
}

function onPicked(file) {
  if (!file) return
  if (file.kind === 'archive') {
    extractArchiveFile(file.path);
    return
  }
  if (file.kind === 'chapter') {
    chapterFile.value = file.path;
    chapterMode.value = 'import';
    toastMsg('success', `已选择章节文件：${baseName(file.path)}`);
    return
  }
  if (file.kind === 'font') {
    addFontFromFile(file);
    toastMsg('success', `已添加字体：${file.name || baseName(file.path)}`);
    return
  }
  addTrackFromFile(file.kind, file);
}

function openUpload(kind) {
  uploadDialog.value = { open: true, kind };
}

function onUploaded(data) {
  // 压缩包上传：后端直接解压并返回 items，全部加入附件
  if (Array.isArray(data?.items)) {
    const result = addArchiveFonts(data);
    if (result.added) toastMsg('success', archiveToast('已上传并解压', result));
    else if (result.skipped) toastMsg('info', `字体都已在附件列表中（跳过 ${result.skipped} 个重复）`);
    return
  }
  if (!data?.path) return
  const kind = data.kind || uploadDialog.value.kind;
  const file = { name: data.name, path: data.path, size: data.size, ext: extName(data.name) };
  if (kind === 'font') addFontFromFile(file);
  else addTrackFromFile(kind, file, false);
  toastMsg('success', `已上传：${data.name || baseName(data.path)}`);
}

// ---------------------------------------------------------------- 期望状态 → plan
function buildPlan() {
  const originals = trackViews.value.filter((track) => !track.added);
  const added = trackViews.value.filter((track) => track.added);
  // 视频轨恒保留，也要参与 order（后端按 order 决定轨道排列）
  originals.filter((track) => track.keep);
  const edits = {};
  for (const track of originals) {
    if (track.readonly) continue
    const orig = track._orig || {};
    const changed =
      track.language !== orig.language ||
      track.name !== orig.name ||
      Boolean(track.default) !== Boolean(orig.default) ||
      Boolean(track.forced) !== Boolean(orig.forced);
    if (changed) {
      edits[String(track.id)] = {
        language: track.language || 'und',
        name: track.name || '',
        default: Boolean(track.default),
        forced: Boolean(track.forced),
      };
    }
  }
  // 新增轨道条目（供 order 里用 add:<文件路径> 表示插入位置）
  const addedEntries = added
    .filter((track) => track.keep)
    .map((track) => {
      const base = {
        kind: track.kind,
        file: track.file.path,
        language: track.language || 'und',
        name: track.name || '',
        default: Boolean(track.default),
        forced: Boolean(track.forced),
      };
      return track.kind === 'audio'
        ? { ...base, sync_ms: Number(track.sync_ms) || 0 }
        : { ...base, encoding: track.encoding || 'auto', sync_ms: Number(track.sync_ms) || 0 }
    });
  // 混合顺序：数字 = 原有轨道 ID，add:<路径> = 新增轨道，按当前列表顺序输出
  const order = [];
  for (const track of trackViews.value) {
    if (track.added) {
      if (track.keep) order.push(`add:${track.file.path}`);
    } else if (track.keep) {
      order.push(track.id);
    }
  }
  return {
    path: currentPath.value,
    title: title.value,
    chapters: {
      mode: chapterMode.value,
      file: chapterMode.value === 'import' ? chapterFile.value : null,
    },
    tracks: {
      order,
      drop: originals.filter((track) => !track.keep && !track.readonly).map((track) => track.id),
      edits,
      add: addedEntries,
      attachments_add: attachments.value.filter((item) => item.added && item.keep).map((item) => item.file.path),
      attachments_drop: attachments.value.filter((item) => !item.added && !item.keep).map((item) => item.name),
    },
    output: {
      mode: outputMode.value,
      dir: outputDir.value,
      // no_backup 只在原地替换时有意义
      no_backup: outputMode.value === 'replace' ? Boolean(noBackup.value) : false,
    },
    extra_args: extraArgsText.value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean),
    // 时长不一致警告需要用户在预览弹窗显式确认，确认后才随 plan 提交
    ...(durationMismatchConfirmed.value ? { confirmed_duration_mismatch: true } : {}),
  }
}

async function openPreview(skipGuard = false) {
  if (!currentPath.value) return
  // 重复提交保护：pending/running 时先让用户选择更新/新建/取消
  if (!skipGuard && !(await guardDuplicateSubmission('preview'))) return
  durationMismatchConfirmed.value = false;
  previewOpen.value = true;
  previewLoading.value = true;
  planResult.value = null;
  try {
    planResult.value = await api.post('/plan', buildPlan());
  } catch (err) {
    previewOpen.value = false;
    toastMsg('error', `预览失败：${err.message}`);
  } finally {
    previewLoading.value = false;
  }
}

async function applyExtraArgs() {
  if (!currentPath.value) {
    toastMsg('warning', '请先选择文件');
    return
  }
  extraArgsChecking.value = true;
  extraArgsError.value = '';
  extraArgsOk.value = '';
  try {
    const result = await api.post('/plan', buildPlan());
    planResult.value = result;
    const blockers = result.blockers || [];
    const argBlocker = blockers.find((item) => ['extra_args', 'extra_args_engine'].includes(item.code));
    if (argBlocker) {
      extraArgsError.value = argBlocker.message;
      toastMsg('error', argBlocker.message);
      return
    }
    extraArgsOk.value = '已应用：预览里的命令已包含这些参数';
    previewOpen.value = true;
    if (blockers.length) {
      toastMsg('warning', `附加参数已应用，但计划还有 ${blockers.length} 项阻塞，请先处理`);
    } else {
      toastMsg('success', '附加参数已应用');
    }
  } catch (err) {
    extraArgsError.value = err.message;
    toastMsg('error', `验证失败：${err.message}`);
  } finally {
    extraArgsChecking.value = false;
  }
}

watch(extraArgsText, () => {
  extraArgsError.value = '';
  extraArgsOk.value = '';
});

async function confirmRun() {
  if (!planResult.value || previewSubmitting.value) return
  if ((planResult.value.blockers || []).length) return
  // 有 duration_mismatch 警告时必须先勾选「我已知晓」
  if (hasDurationMismatch.value && !durationMismatchConfirmed.value) {
    toastMsg('warning', '请先勾选「我已知晓时长不一致，仍要执行」再确认');
    return
  }
  previewSubmitting.value = true;
  savingPlan.value = true;
  try {
    // 编辑队列任务：确认后走 update，不再创建新任务
    if (editingJobId.value) {
      await submitJobUpdate();
      return
    }
    const data = await api.post('/jobs', { plan: buildPlan() });
    previewOpen.value = false;
    const jobId = data?.id || data?.job_id;
    toastMsg('success', `已加入队列${jobId ? `（${jobId}）` : ''}`);
    seedSubmittedJob(data, currentPath.value);
    await loadQueue(false);
    await loadStatus();
    await refreshFileStatuses();
  } catch (err) {
    toastMsg('error', `入队失败：${err.message}`);
  } finally {
    previewSubmitting.value = false;
    savingPlan.value = false;
  }
}

// 仅加入队列：先 /plan 校验（blockers 提示，不入队），再以 hold=true 入队，等队列页统一开始
// 编辑队列任务时语义改为「更新且保持原有 hold 状态」
async function enqueueHold(skipGuard = false) {
  if (!currentPath.value || holdSubmitting.value) return
  // 重复提交保护：pending/running 时先让用户选择更新/新建/取消
  if (!skipGuard && !(await guardDuplicateSubmission('enqueue'))) return
  holdSubmitting.value = true;
  try {
    const preview = await api.post('/plan', buildPlan());
    if ((preview?.blockers || []).length) {
      const messages = (preview.blockers || [])
        .map((item) => item.message || item.code)
        .filter(Boolean)
        .slice(0, 2);
      toastMsg('error', messages.length ? messages.join('；') : '计划存在阻塞项，无法加入队列');
      return
    }
    // 时长不一致需要显式勾选确认，仅支持走「预览并确认/预览并更新」流程
    if ((preview?.warnings || []).some((item) => (item?.code || '') === 'duration_mismatch')) {
      toastMsg('warning', '计划存在时长不一致警告，请用「预览并确认」勾选确认后再执行');
      return
    }
    if (editingJobId.value) {
      await submitJobUpdate();
      return
    }
    const data = await api.post('/jobs', { plan: buildPlan(), hold: true });
    const jobId = data?.id || data?.job_id;
    toastMsg('success', `已加入队列（待启动）${jobId ? `：${jobId}` : ''}，到队列页统一开始`);
    seedSubmittedJob(data, currentPath.value);
    await loadQueue(true);
    await loadStatus();
    await refreshFileStatuses();
  } catch (err) {
    toastMsg('error', `加入队列失败：${err.message}`);
  } finally {
    holdSubmitting.value = false;
  }
}

// 更新正在编辑的队列任务（hold 状态由后端保留）
async function submitJobUpdate() {
  const jobId = editingJobId.value;
  if (!jobId) return false
  try {
    const data = await api.post(`/jobs/${encodeURIComponent(jobId)}/update`, { plan: buildPlan() });
    editingJobId.value = '';
    editingJobName.value = '';
    previewOpen.value = false;
    toastMsg('success', '队列任务已更新');
    seedSubmittedJob(data || { id: jobId, status: 'pending', path: currentPath.value });
    await loadQueue(false);
    await loadStatus();
    await refreshFileStatuses();
    return true
  } catch (err) {
    // 任务已被取消/开始、或新计划出现 blockers 时后端会返回 message：清空编辑态并刷新
    editingJobId.value = '';
    editingJobName.value = '';
    previewOpen.value = false;
    toastMsg('error', `队列任务更新失败：${err.message}`);
    await loadQueue(false);
    await loadStatus();
    await refreshFileStatuses();
    return false
  }
}

// 从队列进入编辑：用任务里的原始 plan 回填编辑器
async function startEditJob(job) {
  if (!job?.plan || typeof job.plan !== 'object') {
    toastMsg('warning', '该任务没有可编辑的计划，请取消后重新加入');
    return
  }
  editingJobId.value = job.id;
  editingJobName.value = job.name || job.path || job.id;
  switchTab('edit');
  currentPath.value = job.path || '';
  const loaded = await loadProbe(job.path);
  if (!loaded) {
    editingJobId.value = '';
    editingJobName.value = '';
    toastMsg('error', '任务文件已失效，无法编辑');
    return
  }
  applyPlanToEditor(job.plan);
  editorTab.value = 'video';
  toastMsg('success', '已载入队列任务，提交后将更新该任务');
}

function cancelEditing() {
  if (!editingJobId.value) return
  editingJobId.value = '';
  editingJobName.value = '';
  toastMsg('info', '已取消队列任务编辑');
}

// ---------------------------------------------------------------- 队列操作
async function cancelJob(job) {
  askConfirm({
    title: '取消任务',
    text: `确定取消「${job.name || job.path}」？运行中的任务会终止并清理临时文件。`,
    confirmText: '取消任务',
    color: 'error',
    action: async () => {
      await api.post(`/jobs/${encodeURIComponent(job.id)}/cancel`);
      toastMsg('success', '已请求取消');
      await loadQueue(false);
      await loadStatus();
    },
  });
}

async function moveJob(job, to) {
  try {
    await api.post(`/jobs/${encodeURIComponent(job.id)}/move`, { to });
    await loadQueue(true);
  } catch (err) {
    toastMsg('error', `调整顺序失败：${err.message}`);
  }
}

async function togglePause(paused) {
  try {
    await api.post('/jobs/pause', { paused });
    queuePaused.value = paused;
    toastMsg('success', paused ? '队列已暂停，当前任务结束后不再开始新任务' : '队列已恢复');
    await loadQueue(true);
  } catch (err) {
    toastMsg('error', `操作失败：${err.message}`);
  }
}

function clearPending() {
  askConfirm({
    title: '清空等待队列',
    text: `确定清空 ${pendingJobs.value.length} 个等待中的任务？正在运行的任务不受影响。`,
    confirmText: '清空等待',
    color: 'warning',
    action: async () => {
      await api.post('/jobs/clear');
      toastMsg('success', '已清空等待队列');
      await loadQueue(false);
      await loadStatus();
    },
  });
}

// 启动单个「待启动」任务
async function startJob(job) {
  try {
    await api.post(`/jobs/${encodeURIComponent(job.id)}/start`);
    toastMsg('success', `已开始：${job.name || job.path}`);
    await loadQueue(false);
    await loadStatus();
  } catch (err) {
    toastMsg('error', `启动失败：${err.message}`);
  }
}

// 全部开始：解除所有待启动任务并恢复队列
async function startAllJobs() {
  try {
    const data = await api.post('/jobs/start');
    const started = Number(data?.started) || 0;
    toastMsg('success', started ? `已开始 ${started} 个待启动任务` : '没有待启动任务');
    queuePaused.value = Boolean(data?.paused);
    await loadQueue(false);
    await loadStatus();
  } catch (err) {
    toastMsg('error', `全部开始失败：${err.message}`);
  }
}

async function setConcurrency(value) {
  const previous = config.value.concurrency;
  config.value = { ...config.value, concurrency: value };
  try {
    const saved = await api.post('/config', { ...config.value });
    config.value = { ...config.value, ...(saved || {}) };
    toastMsg('success', `并发数已设为 ${value}`);
  } catch (err) {
    config.value = { ...config.value, concurrency: previous };
    toastMsg('error', `保存并发数失败：${err.message}`);
  }
}

// ---------------------------------------------------------------- 历史操作
function rollbackHistory(item) {
  askConfirm({
    title: '回滚到备份',
    text: `确定用备份恢复「${item.name || item.path}」？当前文件会被备份版本覆盖。`,
    detail: item.backup_path || '',
    confirmText: '回滚',
    color: 'warning',
    action: async () => {
      await api.post(`/history/${encodeURIComponent(item.id)}/rollback`);
      toastMsg('success', '已从备份回滚');
      await loadHistory(false);
      await loadStatus();
    },
  });
}

// 删除单条历史记录（不会删除备份文件）
function deleteHistory(item) {
  askConfirm({
    title: '删除历史记录',
    text: `确定删除「${item.name || item.path}」这条历史记录？`,
    detail: '只删除记录，不会删除备份文件。',
    confirmText: '删除',
    color: 'error',
    action: async () => {
      const data = await api.post(`/history/${encodeURIComponent(item.id)}/delete`);
      if (data?.deleted) {
        toastMsg('success', '历史记录已删除');
      } else {
        toastMsg('warning', '记录不存在或已删除');
      }
      await loadHistory(false);
    },
  });
}

// 清空全部历史记录（不会删除备份文件）
function clearHistory() {
  askConfirm({
    title: '清空历史记录',
    text: '确定清空全部历史记录？此操作不可撤销。',
    detail: '只删除记录，不会删除备份文件。',
    confirmText: '清空',
    color: 'error',
    action: async () => {
      const data = await api.post('/history/clear');
      const count = Number(data?.deleted) || 0;
      toastMsg('success', count ? `已清空 ${count} 条历史记录` : '没有可清空的历史记录');
      await loadHistory(false);
    },
  });
}

/**
 * 把历史记录里的完整 plan 回填到编辑器（先探测、再叠加 plan）
 * 字段与 /plan 请求体一致：tracks.order/drop/edits/add、attachments、chapters、title、output、extra_args
 */
function applyPlanToEditor(plan) {
  if (!plan || typeof plan !== 'object') return false
  // 探测时会自动预勾选匹配的字幕；历史 plan 才是最终状态，先清空所有新增轨道
  const baseOriginals = trackViews.value.filter((track) => !track.added);
  trackViews.value = baseOriginals;
  attachments.value = attachments.value.filter((item) => !item.added);

  const trackPlan = plan.tracks && typeof plan.tracks === 'object' ? plan.tracks : {};
  const byId = new Map(baseOriginals.map((track) => [Number(track.id), track]));

  // 1) 轨道顺序：order 里有的按 order，其余（已删除的）追加到末尾保留展示
  const ordered = [];
  const seen = new Set();
  for (const rawId of Array.isArray(trackPlan.order) ? trackPlan.order : []) {
    const track = byId.get(Number(rawId));
    if (track && !seen.has(track)) {
      ordered.push(track);
      seen.add(track);
    }
  }
  for (const track of baseOriginals) {
    if (!seen.has(track)) ordered.push(track);
  }

  // 2) 删除标记
  const dropIds = new Set(
    (Array.isArray(trackPlan.drop) ? trackPlan.drop : []).map((id) => Number(id)),
  );
  for (const track of ordered) {
    if (track.readonly) continue
    track.keep = !dropIds.has(Number(track.id));
  }

  // 3) 轨道编辑（语言 / 名称 / 默认 / 强制）
  const edits = trackPlan.edits && typeof trackPlan.edits === 'object' ? trackPlan.edits : {};
  for (const [key, patch] of Object.entries(edits)) {
    const track = byId.get(Number(key));
    if (!track || track.readonly || !patch || typeof patch !== 'object') continue
    if (patch.language != null) track.language = String(patch.language);
    if (patch.name != null) track.name = String(patch.name);
    if (patch.default != null) track.default = Boolean(patch.default);
    if (patch.forced != null) track.forced = Boolean(patch.forced);
  }

  // 4) 新增轨道（字幕 / 音频）
  const addedPaths = new Set();
  for (const item of Array.isArray(trackPlan.add) ? trackPlan.add : []) {
    if (!item || typeof item !== 'object' || !item.file) continue
    const filePath = String(item.file);
    if (!filePath || addedPaths.has(filePath)) continue
    addedPaths.add(filePath);
    const kind = item.kind === 'audio' ? 'audio' : 'subtitle';
    ordered.push({
      id: `add-${kind}-${filePath}`,
      type: kind,
      kind,
      added: true,
      keep: true,
      language: item.language || inferLanguage(baseName(filePath)),
      name: item.name || '',
      default: Boolean(item.default),
      forced: Boolean(item.forced),
      encoding: item.encoding || 'auto',
      sync_ms: Number(item.sync_ms) || 0,
      file: { name: baseName(filePath), path: filePath, size: null, ext: extName(filePath) },
    });
  }
  // 4.5) 混合顺序：order 中 `add:<路径>` 表示新增轨道的插入位置，按 order 重排
  const rawOrder = Array.isArray(trackPlan.order) ? trackPlan.order : [];
  if (rawOrder.some((token) => typeof token === 'string' && token.startsWith('add:'))) {
    const originalById = new Map(ordered.filter((track) => !track.added).map((track) => [Number(track.id), track]));
    const addedByPath = new Map(ordered.filter((track) => track.added).map((track) => [track.file?.path, track]));
    const finalOrder = [];
    const seenTracks = new Set();
    for (const token of rawOrder) {
      let target = null;
      if (typeof token === 'string' && token.startsWith('add:')) {
        target = addedByPath.get(token.slice(4)) || null;
      } else {
        const numeric = Number(token);
        if (Number.isFinite(numeric)) target = originalById.get(numeric) || null;
      }
      if (target && !seenTracks.has(target)) {
        finalOrder.push(target);
        seenTracks.add(target);
      }
    }
    for (const track of ordered) {
      if (!seenTracks.has(track)) finalOrder.push(track);
    }
    ordered.length = 0;
    ordered.push(...finalOrder);
  }
  trackViews.value = ordered;

  // 5) 附件：attachments_add 追加为新增字体，attachments_drop 标记删除
  const attachmentByName = new Map(attachments.value.map((item) => [item.name, item]));
  for (const name of Array.isArray(trackPlan.attachments_drop) ? trackPlan.attachments_drop : []) {
    const item = attachmentByName.get(String(name));
    if (item) item.keep = false;
  }
  const attachmentPaths = new Set(attachments.value.filter((item) => item.added).map((item) => item.file?.path));
  for (const rawPath of Array.isArray(trackPlan.attachments_add) ? trackPlan.attachments_add : []) {
    const path = String(rawPath || '');
    if (!path || attachmentPaths.has(path)) continue
    attachmentPaths.add(path);
    attachments.value = [
      ...attachments.value,
      {
        id: `add-font-${path}`,
        name: baseName(path),
        mime: '',
        size: null,
        keep: true,
        added: true,
        file: { name: baseName(path), path, size: null },
      },
    ];
  }

  // 6) 章节 / 容器标题
  const chapterPlan = plan.chapters && typeof plan.chapters === 'object' ? plan.chapters : {};
  chapterMode.value = ['keep', 'clear', 'import'].includes(chapterPlan.mode) ? chapterPlan.mode : 'keep';
  chapterFile.value = chapterMode.value === 'import' ? String(chapterPlan.file || '') : '';
  if (plan.title != null) title.value = String(plan.title);

  // 7) 输出
  const outputPlan = plan.output && typeof plan.output === 'object' ? plan.output : {};
  outputMode.value = outputPlan.mode === 'replace' ? 'replace' : 'dir';
  outputDir.value = outputPlan.dir ? String(outputPlan.dir) : (config.value.output_dir || '');
  noBackup.value = outputMode.value === 'replace' && Boolean(outputPlan.no_backup);

  // 8) 附加参数（每行一条）
  const extraArgs = Array.isArray(plan.extra_args) ? plan.extra_args : [];
  extraArgsText.value = extraArgs.map((line) => String(line)).join('\n');
  return true
}

async function reopenHistory(item) {
  if (!item?.path) {
    toastMsg('error', '该记录没有可打开的文件路径');
    return
  }
  switchTab('edit');
  currentPath.value = item.path;
  const loaded = await loadProbe(item.path);
  if (!loaded) {
    toastMsg('error', '该记录的文件已失效，无法回填');
    return
  }
  const planData = item.plan && typeof item.plan === 'object' ? item.plan : null;
  if (!planData) {
    toastMsg('warning', '该记录没有可回填的配置，已只打开文件');
    return
  }
  try {
    applyPlanToEditor(planData);
    editorTab.value = 'video';
    toastMsg('success', '已回填历史记录的编辑配置');
  } catch (err) {
    toastMsg('error', `回填失败：${err.message}`);
  }
}

// ---------------------------------------------------------------- 引擎安装
function askInstallEngine() {
  askConfirm({
    title: '安装 MKVToolNix',
    text: '将从 Debian 源执行 apt 安装 mkvtoolnix（约几十 MB），安装过程在后台进行，可在设置页查看日志。',
    confirmText: '开始安装',
    action: async () => {
      await api.post('/engine/install', { method: 'apt' });
      installStarting.value = true;
      toastMsg('info', '已开始安装，完成后引擎状态会自动刷新');
      pollEngineInstall();
    },
  });
}

async function pollEngineInstall() {
  if (installTimer) clearTimeout(installTimer);
  installTimer = setTimeout(async () => {
    try {
      const data = await api.get('/status');
      status.value = data || {};
      if (data?.engine_install?.running) {
        pollEngineInstall();
        return
      }
      installTimer = null;
      installStarting.value = false;
      if (data?.engine_install?.ok === false) {
        toastMsg('error', '引擎安装失败，请到设置页查看日志');
      } else {
        toastMsg('success', '引擎安装完成');
        await loadStatus();
      }
    } catch (err) {
      installTimer = null;
      installStarting.value = false;
    }
  }, 1000);
}

// ---------------------------------------------------------------- 确认弹窗
function askConfirm(options) {
  confirmState.value = {
    open: true,
    title: options.title || '确认操作',
    text: options.text || '',
    detail: options.detail || '',
    confirmText: options.confirmText || '确定',
    color: options.color || 'primary',
    loading: false,
    action: options.action || null,
  };
}

async function runConfirm() {
  const action = confirmState.value.action;
  confirmState.value = { ...confirmState.value, open: false };
  if (!action) return
  try {
    await action();
  } catch (err) {
    toastMsg('error', err.message || '操作失败');
  }
}

// ---------------------------------------------------------------- Tab / 配置保存
const lastNonSettingsTab = ref('edit');

function switchTab(key) {
  if (key === 'settings' && tab.value !== 'settings') {
    lastNonSettingsTab.value = tab.value;
  }
  tab.value = key;
  // 切换页签时刷新文件树的队列/历史状态徽标
  fileStatusTick.value += 1;
  if (key === 'queue') loadQueue(false);
  if (key === 'history') loadHistory(false);
}

/** 从设置页返回上一次停留的主页面（编辑/队列/历史）。 */
function backFromSettings() {
  switchTab(lastNonSettingsTab.value || 'edit');
}

function onConfigSaved(saved) {
  config.value = { ...config.value, ...(saved || {}) };
}

function exitPanel() {
  if (props.showClose) {
    emit('close');
    return
  }
  window.location.href = `${window.location.origin}/#/plugins?tab=installed`;
}

// ---------------------------------------------------------------- 定时器
function ensureQueueTimer() {
  if (hasActiveJobs.value && !queueTimer) {
    queueTimer = setInterval(async () => {
      await loadQueue(true);
    }, 1000);
  } else if (!hasActiveJobs.value && queueTimer) {
    clearInterval(queueTimer);
    queueTimer = null;
  }
}

watch(hasActiveJobs, ensureQueueTimer);
// 切换文件：重置状态条并按新 path 拉取状态；关闭文件时停止轮询
watch(currentPath, (path) => {
  statusDismissed.value = false;
  if (!path) {
    currentFileStatus.value = null;
    stopStatusPoll();
    return
  }
  refreshFileStatuses();
});
// 离开编辑页停止轮询，回到编辑页重新拉取
watch(tab, (value) => {
  if (value === 'edit' && currentPath.value) refreshFileStatuses();
  else stopStatusPoll();
});
// 预览弹窗关闭后清空「时长不一致已确认」，避免下次提交误带 confirmed_duration_mismatch
watch(previewOpen, (open) => {
  if (!open) durationMismatchConfirmed.value = false;
});

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '100rem' });
  // 监听插件根容器宽度（不依赖视口断点），PC 模式下容器窄时也能切紧凑布局
  if (rootRef.value) {
    // 宿主卡片弹窗（VDialog）内：布局要尽量撑满弹窗，减少上下留白
    inHostDialog.value = Boolean(rootRef.value.closest('.v-dialog'));
    containerWidth.value = rootRef.value.clientWidth || 0;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0];
        const width = entry?.contentRect?.width || entry?.target?.clientWidth || 0;
        if (width) containerWidth.value = width;
      });
      resizeObserver.observe(rootRef.value);
    }
  }
  await loadConfig();
  await Promise.all([loadStatus(), loadQueue(true), loadHistory(true), loadArchiveTools()]);
  statusLoaded.value = true;
  await refreshFileStatuses();
  statusTimer = setInterval(async () => {
    await loadStatus();
    if (tab.value === 'queue') await loadQueue(true);
  }, 5000);
  ensureQueueTimer();
});

onBeforeUnmount(() => {
  if (resizeObserver) resizeObserver.disconnect();
  if (disabledMaskTimer) clearTimeout(disabledMaskTimer);
  resizeObserver = null;
  stopStatusPoll();
  if (statusTimer) clearInterval(statusTimer);
  if (queueTimer) clearInterval(queueTimer);
  if (installTimer) clearTimeout(installTimer);
  statusTimer = null;
  queueTimer = null;
  installTimer = null;
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_skeleton_loader = _resolveComponent("v-skeleton-loader");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_checkbox = _resolveComponent("v-checkbox");
  const _component_v_dialog = _resolveComponent("v-dialog");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", {
    ref_key: "rootRef",
    ref: rootRef,
    class: _normalizeClass(["mkv-page", { 'mkv-narrow': narrow.value, 'mkv-medium': medium.value, 'mkv-wide': wide.value, 'mkv-host-dialog': inHostDialog.value, 'mkv-has-content': hasContent.value }])
  }, [
    (statusLoaded.value && showDisabledMask.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_1, [
          _createElementVNode("div", _hoisted_2, [
            _createVNode(_component_v_icon, {
              size: "46",
              color: "grey",
              icon: "mdi-power-off",
              class: "mb-2"
            }),
            _cache[43] || (_cache[43] = _createElementVNode("div", { class: "mkv-disabled-title" }, "插件已停用", -1)),
            _cache[44] || (_cache[44] = _createElementVNode("div", { class: "mkv-disabled-desc" }, [
              _createTextVNode(" 请到 MoviePilot 的「设置 → 插件」页面找到「MKV 工具箱」："),
              _createElementVNode("br"),
              _createTextVNode(" 1. 点击「启用 / 启动」"),
              _createElementVNode("br"),
              _createTextVNode(" 2. 点击「应用保存」"),
              _createElementVNode("br"),
              _createTextVNode(" 3. 回到本页刷新 ")
            ], -1)),
            _createElementVNode("div", _hoisted_3, [
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-cog-outline",
                onClick: openSettingsFromDisabled
              }, {
                default: _withCtx(() => [...(_cache[41] || (_cache[41] = [
                  _createTextVNode(" 前往设置启用 ", -1)
                ]))]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                variant: "tonal",
                "prepend-icon": "mdi-refresh",
                onClick: reloadPage
              }, {
                default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                  _createTextVNode(" 刷新页面 ", -1)
                ]))]),
                _: 1
              })
            ])
          ])
        ]))
      : _createCommentVNode("", true),
    _createElementVNode("header", _hoisted_4, [
      _createElementVNode("div", _hoisted_5, [
        _createElementVNode("img", {
          class: "mkv-logo mkv-logo--img",
          src: _unref(logoUrl),
          alt: "MKV 工具箱"
        }, null, 8, _hoisted_6),
        (!medium.value)
          ? (_openBlock(), _createElementBlock("span", _hoisted_7, _toDisplayString(narrow.value ? '工具箱' : 'MKV 工具箱'), 1))
          : _createCommentVNode("", true),
        (wide.value)
          ? (_openBlock(), _createElementBlock("span", _hoisted_8, "v" + _toDisplayString(status.value.version || '0.1.50'), 1))
          : _createCommentVNode("", true),
        (wide.value)
          ? (_openBlock(), _createElementBlock("span", _hoisted_9, "UI " + _toDisplayString(UI_BUILD)))
          : _createCommentVNode("", true)
      ]),
      (wide.value)
        ? (_openBlock(), _createElementBlock("div", _hoisted_10, [
            _createElementVNode("span", {
              class: _normalizeClass(["engine-chip", engine.value.mkvmerge?.ok ? 'ok' : 'warn'])
            }, [
              _cache[45] || (_cache[45] = _createElementVNode("i", { class: "dot" }, null, -1)),
              _createTextVNode(_toDisplayString(mkvmergeChip.value), 1)
            ], 2),
            _createElementVNode("span", {
              class: _normalizeClass(["engine-chip", engine.value.ffmpeg?.ok ? 'ok' : 'bad'])
            }, [
              _cache[46] || (_cache[46] = _createElementVNode("i", { class: "dot" }, null, -1)),
              _createTextVNode(_toDisplayString(ffmpegChip.value), 1)
            ], 2),
            _createElementVNode("span", {
              class: _normalizeClass(["engine-chip", [archiveChipOk.value ? 'ok' : 'warn', { 'engine-chip--click': !archiveChipOk.value }]]),
              title: archiveChipOk.value ? archiveHint.value : `${archiveHint.value}（点击去设置安装）`,
              onClick: _cache[0] || (_cache[0] = $event => (!archiveChipOk.value && switchTab('settings')))
            }, [
              _cache[47] || (_cache[47] = _createElementVNode("i", { class: "dot" }, null, -1)),
              _createTextVNode(_toDisplayString(archiveChip.value), 1)
            ], 10, _hoisted_11)
          ]))
        : _createCommentVNode("", true),
      _cache[50] || (_cache[50] = _createElementVNode("span", { class: "mkv-spacer" }, null, -1)),
      _createElementVNode("nav", _hoisted_12, [
        (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
          return _createElementVNode("button", {
            key: item.key,
            type: "button",
            class: _normalizeClass(["mkv-nav-btn", { active: tab.value === item.key }]),
            onClick: $event => (switchTab(item.key))
          }, [
            _createTextVNode(_toDisplayString(item.label) + " ", 1),
            (item.key === 'queue' && queueBadge.value)
              ? (_openBlock(), _createElementBlock("span", _hoisted_14, _toDisplayString(queueBadge.value), 1))
              : _createCommentVNode("", true)
          ], 10, _hoisted_13)
        }), 64))
      ]),
      _createElementVNode("button", {
        type: "button",
        class: "mkv-icon-btn",
        title: tab.value === 'settings' ? '返回主页面' : '设置',
        onClick: _cache[1] || (_cache[1] = $event => (tab.value === 'settings' ? backFromSettings() : switchTab('settings')))
      }, [
        _createVNode(_component_v_icon, {
          size: "18",
          icon: tab.value === 'settings' ? 'mdi-arrow-left' : 'mdi-cog-outline'
        }, null, 8, ["icon"])
      ], 8, _hoisted_15),
      (wide.value)
        ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
            _cache[49] || (_cache[49] = _createElementVNode("span", { class: "mkv-divider" }, null, -1)),
            _createElementVNode("button", {
              type: "button",
              class: "mkv-exit-btn",
              title: "退出插件（返回插件管理页）",
              onClick: exitPanel
            }, [
              _createVNode(_component_v_icon, {
                size: "14",
                icon: "mdi-close"
              }),
              _cache[48] || (_cache[48] = _createElementVNode("span", null, "退出", -1))
            ])
          ], 64))
        : (_openBlock(), _createElementBlock("button", {
            key: 2,
            type: "button",
            class: "mkv-icon-btn",
            title: "退出",
            onClick: exitPanel
          }, [
            _createVNode(_component_v_icon, {
              size: "18",
              icon: "mdi-close"
            })
          ]))
    ]),
    (!engineReady.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_16, [
          _createVNode(_component_v_icon, {
            size: "16",
            icon: "mdi-alert-outline"
          }),
          _cache[53] || (_cache[53] = _createElementVNode("span", null, "未检测到 MKVToolNix，当前只能预览不能执行", -1)),
          _cache[54] || (_cache[54] = _createElementVNode("span", { class: "mkv-spacer" }, null, -1)),
          _createVNode(_component_v_btn, {
            size: "small",
            color: "primary",
            variant: "flat",
            loading: installStarting.value,
            onClick: askInstallEngine
          }, {
            default: _withCtx(() => [...(_cache[51] || (_cache[51] = [
              _createTextVNode(" 立即安装 ", -1)
            ]))]),
            _: 1
          }, 8, ["loading"]),
          _createVNode(_component_v_btn, {
            size: "small",
            variant: "text",
            onClick: _cache[2] || (_cache[2] = $event => (switchTab('settings')))
          }, {
            default: _withCtx(() => [...(_cache[52] || (_cache[52] = [
              _createTextVNode("去设置", -1)
            ]))]),
            _: 1
          })
        ]))
      : _createCommentVNode("", true),
    _createElementVNode("main", _hoisted_17, [
      (tab.value === 'edit')
        ? (_openBlock(), _createElementBlock("section", _hoisted_18, [
            (wide.value)
              ? (_openBlock(), _createElementBlock("aside", _hoisted_19, [
                  _createVNode(FileTree, {
                    api: _unref(api),
                    roots: config.value.roots || [],
                    current: currentPath.value,
                    "refresh-tick": fileStatusTick.value,
                    onSelect: onSelectFile
                  }, null, 8, ["api", "roots", "current", "refresh-tick"])
                ]))
              : _createCommentVNode("", true),
            _createElementVNode("section", _hoisted_20, [
              (!wide.value)
                ? (_openBlock(), _createElementBlock("div", _hoisted_21, [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "tonal",
                      "prepend-icon": "mdi-menu",
                      onClick: _cache[3] || (_cache[3] = $event => (treeDialog.value = true))
                    }, {
                      default: _withCtx(() => [...(_cache[55] || (_cache[55] = [
                        _createTextVNode("文件", -1)
                      ]))]),
                      _: 1
                    }),
                    _createElementVNode("span", {
                      class: "mkv-mobile-file",
                      title: currentPath.value
                    }, _toDisplayString(currentPath.value ? _unref(baseName)(currentPath.value) : '未选择文件'), 9, _hoisted_22),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "text",
                      icon: "mdi-refresh",
                      disabled: !currentPath.value,
                      title: "重新探测",
                      onClick: reprobe
                    }, null, 8, ["disabled"])
                  ]))
                : _createCommentVNode("", true),
              (error.value)
                ? (_openBlock(), _createBlock(_component_v_alert, {
                    key: 1,
                    type: "error",
                    variant: "tonal",
                    density: "compact",
                    closable: "",
                    class: "mb-2",
                    "onClick:close": _cache[4] || (_cache[4] = $event => (error.value = ''))
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(error.value), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode("", true),
              (editingJobId.value)
                ? (_openBlock(), _createElementBlock("div", _hoisted_23, [
                    _createVNode(_component_v_icon, {
                      size: "16",
                      icon: "mdi-pencil-box-outline"
                    }),
                    _createElementVNode("span", _hoisted_24, [
                      _cache[56] || (_cache[56] = _createTextVNode(" 正在编辑队列任务：", -1)),
                      _createElementVNode("b", null, _toDisplayString(editingJobName.value), 1),
                      _cache[57] || (_cache[57] = _createTextVNode("，提交后会更新该任务 ", -1))
                    ]),
                    _createVNode(_component_v_btn, {
                      size: "x-small",
                      variant: "text",
                      "append-icon": "mdi-close",
                      onClick: cancelEditing
                    }, {
                      default: _withCtx(() => [...(_cache[58] || (_cache[58] = [
                        _createTextVNode("取消编辑", -1)
                      ]))]),
                      _: 1
                    })
                  ]))
                : _createCommentVNode("", true),
              (probeLoading.value)
                ? (_openBlock(), _createBlock(_component_v_skeleton_loader, {
                    key: 3,
                    type: "article, list-item@6"
                  }))
                : (!probe.value)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_25, [
                      _createVNode(_component_v_icon, {
                        size: "42",
                        icon: "mdi-filmstrip-box-multiple",
                        class: "mkv-empty-icon"
                      }),
                      _createElementVNode("div", _hoisted_26, "从" + _toDisplayString(!wide.value ? '「文件」' : '左侧目录') + "选择 .mkv / .m2ts 文件开始编辑", 1),
                      _cache[59] || (_cache[59] = _createElementVNode("div", { class: "mkv-empty-hint" }, "只做容器层调整：内封/删除字幕、管理音轨、加字体附件、改标题与章节，不转码、不剪片", -1))
                    ]))
                  : (_openBlock(), _createElementBlock(_Fragment, { key: 5 }, [
                      _createElementVNode("div", _hoisted_27, [
                        _createElementVNode("div", _hoisted_28, [
                          _createElementVNode("div", _hoisted_29, [
                            _createElementVNode("div", {
                              class: "file-title",
                              title: mediaTitle.value
                            }, _toDisplayString(mediaTitle.value), 9, _hoisted_30),
                            (statusMeta.value)
                              ? (_openBlock(), _createElementBlock("span", {
                                  key: 0,
                                  class: _normalizeClass(["file-status-chip", `file-status-chip--${statusMeta.value.state}`])
                                }, _toDisplayString(statusMeta.value.label), 3))
                              : _createCommentVNode("", true)
                          ]),
                          _createElementVNode("div", {
                            class: "file-path",
                            title: probe.value.path
                          }, _toDisplayString(probe.value.path), 9, _hoisted_31)
                        ]),
                        _createElementVNode("div", _hoisted_32, [
                          (wide.value)
                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                _createVNode(_component_v_btn, {
                                  size: "small",
                                  variant: "tonal",
                                  onClick: reprobe
                                }, {
                                  default: _withCtx(() => [...(_cache[60] || (_cache[60] = [
                                    _createTextVNode("重新探测", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _createVNode(_component_v_btn, {
                                  size: "small",
                                  variant: "text",
                                  onClick: copyPath
                                }, {
                                  default: _withCtx(() => [...(_cache[61] || (_cache[61] = [
                                    _createTextVNode("复制路径", -1)
                                  ]))]),
                                  _: 1
                                })
                              ], 64))
                            : _createCommentVNode("", true),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            variant: "text",
                            icon: "mdi-close",
                            title: "关闭文件（回到未选择文件）",
                            "aria-label": "关闭文件",
                            class: "file-close-btn",
                            onClick: clearFile
                          })
                        ])
                      ]),
                      (statusBannerVisible.value)
                        ? (_openBlock(), _createElementBlock("div", {
                            key: 0,
                            class: _normalizeClass(["submit-status-banner", `submit-status-banner--${statusMeta.value.state}`])
                          }, [
                            _createVNode(_component_v_icon, {
                              size: "15",
                              icon: statusIcon(statusMeta.value.state)
                            }, null, 8, ["icon"]),
                            _createElementVNode("span", _hoisted_33, [
                              _cache[62] || (_cache[62] = _createTextVNode(" 已加入队列", -1)),
                              (statusMeta.value.id)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                    _createTextVNode(" · #" + _toDisplayString(statusMeta.value.id), 1)
                                  ], 64))
                                : _createCommentVNode("", true),
                              _createTextVNode(" · " + _toDisplayString(statusMeta.value.label), 1)
                            ]),
                            _createVNode(_component_v_spacer),
                            _createVNode(_component_v_btn, {
                              size: "x-small",
                              variant: "tonal",
                              onClick: _cache[5] || (_cache[5] = $event => (switchTab('queue')))
                            }, {
                              default: _withCtx(() => [...(_cache[63] || (_cache[63] = [
                                _createTextVNode("去队列编辑", -1)
                              ]))]),
                              _: 1
                            }),
                            _createVNode(_component_v_btn, {
                              size: "x-small",
                              variant: "text",
                              onClick: _cache[6] || (_cache[6] = $event => (statusDismissed.value = true))
                            }, {
                              default: _withCtx(() => [...(_cache[64] || (_cache[64] = [
                                _createTextVNode("关闭提示", -1)
                              ]))]),
                              _: 1
                            })
                          ], 2))
                        : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_34, [
                        _createElementVNode("span", _hoisted_35, _toDisplayString(container.value.format || 'MKV'), 1),
                        _createElementVNode("span", _hoisted_36, _toDisplayString(_unref(fmtBytes)(probe.value.size)), 1),
                        _createElementVNode("span", _hoisted_37, "时长 " + _toDisplayString(_unref(fmtDuration)(container.value.duration)), 1),
                        _createElementVNode("span", _hoisted_38, _toDisplayString(probe.value.tracks?.length || 0) + " 条轨道", 1),
                        _createElementVNode("span", _hoisted_39, _toDisplayString(chapters.value.length) + " 章节", 1),
                        _createElementVNode("span", _hoisted_40, _toDisplayString(attachments.value.length) + " 附件", 1)
                      ]),
                      _createElementVNode("nav", _hoisted_41, [
                        (_openBlock(), _createElementBlock(_Fragment, null, _renderList(editorTabs, (item) => {
                          return _createElementVNode("button", {
                            key: item.key,
                            type: "button",
                            class: _normalizeClass(["mkv-tab-btn", { active: editorTab.value === item.key }]),
                            onClick: $event => (editorTab.value = item.key)
                          }, _toDisplayString(item.label), 11, _hoisted_42)
                        }), 64))
                      ]),
                      (editorTab.value === 'video')
                        ? (_openBlock(), _createElementBlock("div", _hoisted_43, [
                            _createVNode(_component_v_card, {
                              variant: "flat",
                              class: "mkv-card"
                            }, {
                              default: _withCtx(() => [
                                _cache[73] || (_cache[73] = _createElementVNode("div", { class: "mkv-card-title" }, [
                                  _createTextVNode(" 视频轨 "),
                                  _createElementVNode("span", { class: "mkv-card-hint" }, "视频轨不可删除，只读")
                                ], -1)),
                                (videoTrack.value)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_44, [
                                      _createElementVNode("div", _hoisted_45, [
                                        _cache[65] || (_cache[65] = _createElementVNode("span", null, "编码", -1)),
                                        _createElementVNode("b", null, _toDisplayString(_unref(codecLabel)(videoTrack.value)), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_46, [
                                        _cache[66] || (_cache[66] = _createElementVNode("span", null, "分辨率", -1)),
                                        _createElementVNode("b", null, _toDisplayString(videoTrack.value.width && videoTrack.value.height ? `${videoTrack.value.width} × ${videoTrack.value.height}` : '—'), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_47, [
                                        _cache[67] || (_cache[67] = _createElementVNode("span", null, "动态范围", -1)),
                                        _createElementVNode("b", null, _toDisplayString(videoTrack.value.hdr || 'SDR'), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_48, [
                                        _cache[68] || (_cache[68] = _createElementVNode("span", null, "码率", -1)),
                                        _createElementVNode("b", null, [
                                          (videoTrack.value.bitrate)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createTextVNode(_toDisplayString(videoTrack.value.bitrate_estimated ? '≈ ' : '') + _toDisplayString((Number(videoTrack.value.bitrate) / 1000000).toFixed(1)) + " Mbps" + _toDisplayString(videoTrack.value.bitrate_estimated ? '（估算）' : ''), 1)
                                              ], 64))
                                            : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                _createTextVNode("—")
                                              ], 64))
                                        ])
                                      ]),
                                      _createElementVNode("div", _hoisted_49, [
                                        _cache[69] || (_cache[69] = _createElementVNode("span", null, "帧率", -1)),
                                        _createElementVNode("b", null, _toDisplayString(videoTrack.value.fps ? `${Number(videoTrack.value.fps).toFixed(3)} fps` : '—'), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_50, [
                                        _cache[70] || (_cache[70] = _createElementVNode("span", null, "时长", -1)),
                                        _createElementVNode("b", null, _toDisplayString(_unref(fmtDuration)(videoTrack.value.duration || container.value.duration, true)), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_51, [
                                        _cache[71] || (_cache[71] = _createElementVNode("span", null, "轨道数", -1)),
                                        _createElementVNode("b", null, _toDisplayString(probe.value.tracks?.length || 0), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_52, [
                                        _cache[72] || (_cache[72] = _createElementVNode("span", null, "容器", -1)),
                                        _createElementVNode("b", null, _toDisplayString(container.value.format || 'Matroska'), 1)
                                      ])
                                    ]))
                                  : (_openBlock(), _createElementBlock("div", _hoisted_53, "探测结果里没有视频轨（可能是纯音频文件）"))
                              ]),
                              _: 1
                            })
                          ]))
                        : (editorTab.value === 'audio')
                          ? (_openBlock(), _createElementBlock("div", _hoisted_54, [
                              _createVNode(TrackEditor, {
                                kind: "audio",
                                tracks: audioTracks.value,
                                layout: layoutMode.value,
                                onPick: openPicker,
                                onUpload: openUpload,
                                onMove: moveTrack,
                                onRemove: removeTrack,
                                onEstimate: estimateTrackOffset
                              }, null, 8, ["tracks", "layout"])
                            ]))
                          : (editorTab.value === 'subtitle')
                            ? (_openBlock(), _createElementBlock("div", _hoisted_55, [
                                _createVNode(TrackEditor, {
                                  kind: "subtitle",
                                  tracks: subtitleTracks.value,
                                  layout: layoutMode.value,
                                  onPick: openPicker,
                                  onUpload: openUpload,
                                  onMove: moveTrack,
                                  onRemove: removeTrack,
                                  onEstimate: estimateTrackOffset
                                }, null, 8, ["tracks", "layout"])
                              ]))
                            : (editorTab.value === 'attach')
                              ? (_openBlock(), _createElementBlock("div", _hoisted_56, [
                                  _createVNode(_component_v_card, {
                                    variant: "flat",
                                    class: "mkv-card"
                                  }, {
                                    default: _withCtx(() => [
                                      _cache[80] || (_cache[80] = _createElementVNode("div", { class: "mkv-card-title" }, "附件（仅字体）", -1)),
                                      (!attachments.value.length)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_57, "暂无附件，可从目录选择或上传字体文件"))
                                        : (!narrow.value)
                                          ? (_openBlock(), _createElementBlock("table", _hoisted_58, [
                                              _cache[74] || (_cache[74] = _createElementVNode("thead", null, [
                                                _createElementVNode("tr", null, [
                                                  _createElementVNode("th", null, "文件名"),
                                                  _createElementVNode("th", { class: "col-mime" }, "类型"),
                                                  _createElementVNode("th", { class: "col-size" }, "大小"),
                                                  _createElementVNode("th", { class: "col-ops" })
                                                ])
                                              ], -1)),
                                              _createElementVNode("tbody", null, [
                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(attachments.value, (item) => {
                                                  return (_openBlock(), _createElementBlock("tr", {
                                                    key: item.id,
                                                    class: _normalizeClass({ dropping: !item.keep })
                                                  }, [
                                                    _createElementVNode("td", null, [
                                                      _createElementVNode("span", {
                                                        class: "attach-name",
                                                        title: item.file?.path || item.name
                                                      }, _toDisplayString(item.name), 9, _hoisted_59),
                                                      (item.added)
                                                        ? (_openBlock(), _createElementBlock("span", _hoisted_60, "新增"))
                                                        : _createCommentVNode("", true)
                                                    ]),
                                                    _createElementVNode("td", _hoisted_61, _toDisplayString(attachmentType(item)), 1),
                                                    _createElementVNode("td", _hoisted_62, _toDisplayString(_unref(fmtBytes)(item.size)), 1),
                                                    _createElementVNode("td", _hoisted_63, [
                                                      _createElementVNode("div", _hoisted_64, [
                                                        _createVNode(_component_v_btn, {
                                                          size: "x-small",
                                                          variant: "tonal",
                                                          icon: !item.added && !item.keep ? 'mdi-restore' : 'mdi-close',
                                                          title: !item.added && !item.keep ? '恢复该附件' : (item.added ? '移除新增' : '标记删除'),
                                                          onClick: $event => (toggleAttachment(item))
                                                        }, null, 8, ["icon", "title", "onClick"])
                                                      ])
                                                    ])
                                                  ], 2))
                                                }), 128))
                                              ])
                                            ]))
                                          : (_openBlock(), _createElementBlock("div", _hoisted_65, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(attachments.value, (item) => {
                                                return (_openBlock(), _createElementBlock("div", {
                                                  key: item.id,
                                                  class: _normalizeClass(["attach-card", { dropping: !item.keep }])
                                                }, [
                                                  _createElementVNode("div", _hoisted_66, [
                                                    _createElementVNode("div", {
                                                      class: "attach-name",
                                                      title: item.file?.path || item.name
                                                    }, _toDisplayString(item.name), 9, _hoisted_67),
                                                    _createElementVNode("div", _hoisted_68, _toDisplayString(attachmentType(item)) + " · " + _toDisplayString(_unref(fmtBytes)(item.size)), 1)
                                                  ]),
                                                  (item.added)
                                                    ? (_openBlock(), _createElementBlock("span", _hoisted_69, "新增"))
                                                    : _createCommentVNode("", true),
                                                  _createVNode(_component_v_btn, {
                                                    size: "small",
                                                    variant: "tonal",
                                                    icon: !item.added && !item.keep ? 'mdi-restore' : 'mdi-close',
                                                    onClick: $event => (toggleAttachment(item))
                                                  }, null, 8, ["icon", "onClick"])
                                                ], 2))
                                              }), 128))
                                            ])),
                                      _createElementVNode("div", _hoisted_70, [
                                        _createVNode(_component_v_btn, {
                                          size: "small",
                                          variant: "tonal",
                                          "prepend-icon": "mdi-folder-open-outline",
                                          onClick: _cache[7] || (_cache[7] = $event => (openPicker('font')))
                                        }, {
                                          default: _withCtx(() => [...(_cache[75] || (_cache[75] = [
                                            _createTextVNode(" 从目录选择字体 ", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _createVNode(_component_v_btn, {
                                          size: "small",
                                          variant: "text",
                                          "prepend-icon": "mdi-upload-outline",
                                          onClick: _cache[8] || (_cache[8] = $event => (openUpload('font')))
                                        }, {
                                          default: _withCtx(() => [...(_cache[76] || (_cache[76] = [
                                            _createTextVNode(" 上传字体 ", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _createVNode(_component_v_btn, {
                                          size: "small",
                                          variant: "text",
                                          "prepend-icon": "mdi-folder-zip-outline",
                                          loading: archiveLoading.value,
                                          onClick: openArchivePicker
                                        }, {
                                          default: _withCtx(() => [...(_cache[77] || (_cache[77] = [
                                            _createTextVNode(" 解压字体压缩包 ", -1)
                                          ]))]),
                                          _: 1
                                        }, 8, ["loading"]),
                                        _createVNode(_component_v_btn, {
                                          size: "small",
                                          variant: "text",
                                          "prepend-icon": "mdi-zip-box-open-outline",
                                          onClick: openArchiveBatch
                                        }, {
                                          default: _withCtx(() => [...(_cache[78] || (_cache[78] = [
                                            _createTextVNode(" 从目录批量解压 ", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _createVNode(_component_v_btn, {
                                          size: "small",
                                          variant: "text",
                                          "prepend-icon": "mdi-folder-search-outline",
                                          class: "scan-fonts-btn",
                                          onClick: scanSiblingFonts
                                        }, {
                                          default: _withCtx(() => [...(_cache[79] || (_cache[79] = [
                                            _createTextVNode(" 扫描同目录字体 ", -1)
                                          ]))]),
                                          _: 1
                                        })
                                      ]),
                                      _createElementVNode("div", _hoisted_71, _toDisplayString(archiveHint.value), 1),
                                      _cache[81] || (_cache[81] = _createElementVNode("div", {
                                        class: "mkv-empty-tip",
                                        style: {"margin-top":"8px"}
                                      }, "只允许 ttf / otf / ttc；字体文件通常超过上传上限，建议用目录选择", -1))
                                    ]),
                                    _: 1
                                  })
                                ]))
                              : (editorTab.value === 'chapter')
                                ? (_openBlock(), _createElementBlock("div", _hoisted_72, [
                                    _createVNode(_component_v_card, {
                                      variant: "flat",
                                      class: "mkv-card"
                                    }, {
                                      default: _withCtx(() => [
                                        _cache[89] || (_cache[89] = _createElementVNode("div", { class: "mkv-card-title" }, [
                                          _createTextVNode(" 章节 "),
                                          _createElementVNode("span", { class: "mkv-card-hint" }, "支持 OGM XML 与 ffmetadata 导入（ffmetadata 由后端先转 OGM）")
                                        ], -1)),
                                        _createElementVNode("div", _hoisted_73, [
                                          _cache[86] || (_cache[86] = _createElementVNode("label", null, "处理方式", -1)),
                                          _createElementVNode("div", _hoisted_74, [
                                            _createVNode(_component_v_btn_toggle, {
                                              "model-value": chapterMode.value,
                                              mandatory: "",
                                              density: "compact",
                                              variant: "outlined",
                                              divided: "",
                                              "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => (chapterMode.value = $event))
                                            }, {
                                              default: _withCtx(() => [
                                                _createVNode(_component_v_btn, {
                                                  value: "keep",
                                                  size: "small"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[82] || (_cache[82] = [
                                                    _createTextVNode("保留", -1)
                                                  ]))]),
                                                  _: 1
                                                }),
                                                _createVNode(_component_v_btn, {
                                                  value: "clear",
                                                  size: "small"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[83] || (_cache[83] = [
                                                    _createTextVNode("清空", -1)
                                                  ]))]),
                                                  _: 1
                                                }),
                                                _createVNode(_component_v_btn, {
                                                  value: "import",
                                                  size: "small"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[84] || (_cache[84] = [
                                                    _createTextVNode("导入 XML", -1)
                                                  ]))]),
                                                  _: 1
                                                })
                                              ]),
                                              _: 1
                                            }, 8, ["model-value"]),
                                            _createVNode(_component_v_btn, {
                                              size: "small",
                                              variant: "text",
                                              "prepend-icon": "mdi-folder-open-outline",
                                              onClick: _cache[10] || (_cache[10] = $event => (openPicker('chapter')))
                                            }, {
                                              default: _withCtx(() => [...(_cache[85] || (_cache[85] = [
                                                _createTextVNode(" 选择文件… ", -1)
                                              ]))]),
                                              _: 1
                                            }),
                                            (chapterFile.value)
                                              ? (_openBlock(), _createElementBlock("span", {
                                                  key: 0,
                                                  class: "mono sub ellipsis",
                                                  title: chapterFile.value
                                                }, _toDisplayString(_unref(baseName)(chapterFile.value)), 9, _hoisted_75))
                                              : _createCommentVNode("", true)
                                          ])
                                        ]),
                                        _createElementVNode("div", _hoisted_76, [
                                          _cache[87] || (_cache[87] = _createElementVNode("label", null, "容器标题", -1)),
                                          _createElementVNode("div", _hoisted_77, [
                                            _createVNode(_component_v_text_field, {
                                              modelValue: title.value,
                                              "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((title).value = $event)),
                                              density: "compact",
                                              variant: "outlined",
                                              "hide-details": "",
                                              placeholder: "留空 = 不修改",
                                              class: "title-input"
                                            }, null, 8, ["modelValue"])
                                          ])
                                        ]),
                                        _createElementVNode("div", _hoisted_78, [
                                          _createTextVNode(" 现有章节（" + _toDisplayString(chapters.value.length) + " 个", 1),
                                          (chapters.value.length > 3)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createTextVNode("，预览前 3 个")
                                              ], 64))
                                            : _createCommentVNode("", true),
                                          _cache[88] || (_cache[88] = _createTextVNode("） ", -1))
                                        ]),
                                        (chapters.value.length)
                                          ? (_openBlock(), _createElementBlock("table", _hoisted_79, [
                                              _createElementVNode("tbody", null, [
                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(chapters.value.slice(0, 3), (chapter, index) => {
                                                  return (_openBlock(), _createElementBlock("tr", { key: index }, [
                                                    _createElementVNode("td", _hoisted_80, _toDisplayString(_unref(fmtDuration)(chapter.start)), 1),
                                                    _createElementVNode("td", null, _toDisplayString(chapter.title || `章节 ${index + 1}`), 1)
                                                  ]))
                                                }), 128))
                                              ])
                                            ]))
                                          : (_openBlock(), _createElementBlock("div", _hoisted_81, "原文件没有章节"))
                                      ]),
                                      _: 1
                                    })
                                  ]))
                                : (editorTab.value === 'advanced')
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_82, [
                                      _createVNode(_component_v_card, {
                                        variant: "flat",
                                        class: "mkv-card"
                                      }, {
                                        default: _withCtx(() => [
                                          _cache[91] || (_cache[91] = _createElementVNode("div", { class: "mkv-card-title" }, [
                                            _createTextVNode(" 附加参数 "),
                                            _createElementVNode("span", { class: "mkv-card-hint" }, "追加到自动生成的 mkvmerge 命令行（仅 mkvmerge 生效）")
                                          ], -1)),
                                          _createVNode(_component_v_textarea, {
                                            modelValue: extraArgsText.value,
                                            "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((extraArgsText).value = $event)),
                                            rows: "4",
                                            density: "compact",
                                            variant: "outlined",
                                            "hide-details": "",
                                            class: "mono extra-args",
                                            placeholder: "--sync 1:-250\n--track-name 2:国配"
                                          }, null, 8, ["modelValue"]),
                                          _createElementVNode("div", _hoisted_83, [
                                            _createVNode(_component_v_btn, {
                                              size: "small",
                                              color: "primary",
                                              variant: "tonal",
                                              "prepend-icon": "mdi-check-decagram-outline",
                                              loading: extraArgsChecking.value,
                                              onClick: applyExtraArgs
                                            }, {
                                              default: _withCtx(() => [...(_cache[90] || (_cache[90] = [
                                                _createTextVNode(" 验证并应用 ", -1)
                                              ]))]),
                                              _: 1
                                            }, 8, ["loading"]),
                                            (extraArgsError.value)
                                              ? (_openBlock(), _createElementBlock("span", _hoisted_84, _toDisplayString(extraArgsError.value), 1))
                                              : (extraArgsOk.value)
                                                ? (_openBlock(), _createElementBlock("span", _hoisted_85, _toDisplayString(extraArgsOk.value), 1))
                                                : _createCommentVNode("", true)
                                          ]),
                                          _cache[92] || (_cache[92] = _createElementVNode("div", { class: "warnbox warnbox--red" }, [
                                            _createTextVNode(" 禁止参数："),
                                            _createElementVNode("span", { class: "mono" }, "-o / --output"),
                                            _createTextVNode("（输出路径由插件控制）、输入文件。出现被禁参数会直接拒绝执行。 ")
                                          ], -1)),
                                          _cache[93] || (_cache[93] = _createElementVNode("div", { class: "mkv-empty-tip" }, [
                                            _createTextVNode(" 常用示例 "),
                                            _createElementVNode("span", { class: "mono" }, "--default-track-flag 2:1"),
                                            _createTextVNode("、"),
                                            _createElementVNode("span", { class: "mono" }, "--language 2:chi"),
                                            _createTextVNode("、"),
                                            _createElementVNode("span", { class: "mono" }, "--no-audio"),
                                            _createTextVNode("；只填附加参数也会触发一次 mkvmerge 重封装。 ")
                                          ], -1))
                                        ]),
                                        _: 1
                                      })
                                    ]))
                                  : _createCommentVNode("", true),
                      (showSiblings.value)
                        ? (_openBlock(), _createBlock(SiblingPanel, {
                            key: 7,
                            items: siblingItems.value,
                            layout: layoutMode.value,
                            kind: siblingKind.value,
                            mounted: siblingMounted.value,
                            onToggle: toggleSibling,
                            onMountToggle: toggleSiblingMount
                          }, null, 8, ["items", "layout", "kind", "mounted"]))
                        : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_86, [
                        _createElementVNode("label", _hoisted_87, [
                          _createElementVNode("input", {
                            type: "radio",
                            name: "mkv-output-mode",
                            checked: outputMode.value === 'dir',
                            onChange: _cache[13] || (_cache[13] = $event => (outputMode.value = 'dir'))
                          }, null, 40, _hoisted_88),
                          _cache[94] || (_cache[94] = _createElementVNode("span", null, "输出到目录", -1))
                        ]),
                        (outputMode.value === 'dir')
                          ? (_openBlock(), _createBlock(_component_v_text_field, {
                              key: 0,
                              modelValue: outputDir.value,
                              "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((outputDir).value = $event)),
                              density: "compact",
                              variant: "outlined",
                              "hide-details": "",
                              class: "output-path mono",
                              placeholder: "/config/plugins/MkvToolkit/output"
                            }, null, 8, ["modelValue"]))
                          : _createCommentVNode("", true),
                        (isNonMkvSource.value)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_89, "输出文件名自动改为 .mkv"))
                          : (_openBlock(), _createElementBlock("span", _hoisted_90, "文件名自动＝原名")),
                        _createElementVNode("label", {
                          class: _normalizeClass(["radio output-replace", { 'output-replace--disabled': isNonMkvSource.value }])
                        }, [
                          _createElementVNode("input", {
                            type: "radio",
                            name: "mkv-output-mode",
                            checked: outputMode.value === 'replace',
                            disabled: isNonMkvSource.value,
                            onChange: _cache[15] || (_cache[15] = $event => (!isNonMkvSource.value && (outputMode.value = 'replace')))
                          }, null, 40, _hoisted_91),
                          _cache[95] || (_cache[95] = _createElementVNode("span", null, "原地替换", -1))
                        ], 2)
                      ]),
                      (isNonMkvSource.value)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_92, " m2ts 需重封装为 MKV，不能原地替换；已自动改为「输出到目录」，输出文件名后缀为 .mkv "))
                        : _createCommentVNode("", true),
                      (outputMode.value === 'replace')
                        ? (_openBlock(), _createElementBlock("div", {
                            key: 9,
                            class: _normalizeClass(["backup-info", { 'backup-info--danger': noBackup.value }])
                          }, [
                            _createVNode(_component_v_icon, {
                              size: "14",
                              icon: noBackup.value ? 'mdi-alert-outline' : 'mdi-shield-check-outline'
                            }, null, 8, ["icon"]),
                            (noBackup.value)
                              ? (_openBlock(), _createElementBlock("span", _hoisted_93, "备份：不做临时备份（替换失败时无恢复副本）"))
                              : (_openBlock(), _createElementBlock("span", _hoisted_94, [
                                  _cache[96] || (_cache[96] = _createTextVNode(" 备份：临时备份到 ", -1)),
                                  _createElementVNode("span", {
                                    class: "backup-dir mono",
                                    title: backupDir.value
                                  }, _toDisplayString(backupDir.value), 9, _hoisted_95),
                                  _cache[97] || (_cache[97] = _createTextVNode(" （任务成功后删除；失败保留并尝试还原源文件） ", -1))
                                ]))
                          ], 2))
                        : _createCommentVNode("", true),
                      (outputMode.value === 'replace')
                        ? (_openBlock(), _createElementBlock("div", _hoisted_96, [
                            _createVNode(_component_v_checkbox, {
                              modelValue: noBackup.value,
                              "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((noBackup).value = $event)),
                              density: "compact",
                              color: "warning",
                              "hide-details": "",
                              label: "不保存临时备份",
                              class: "no-backup-check"
                            }, null, 8, ["modelValue"])
                          ]))
                        : _createCommentVNode("", true),
                      _cache[101] || (_cache[101] = _createElementVNode("div", { class: "output-hint" }, " 输出目录是容器内路径（如 /media、/downloads），不是 Windows 盘符路径；对应宿主机映射目录 ", -1)),
                      _createElementVNode("div", _hoisted_97, [
                        _cache[99] || (_cache[99] = _createElementVNode("span", { class: "execute-tip" }, "执行前会先弹出预览确认，不会直接写文件", -1)),
                        _cache[100] || (_cache[100] = _createElementVNode("span", { class: "mkv-spacer" }, null, -1)),
                        _createElementVNode("div", _hoisted_98, [
                          _createVNode(_component_v_btn, {
                            variant: "text",
                            onClick: resetEditor
                          }, {
                            default: _withCtx(() => [...(_cache[98] || (_cache[98] = [
                              _createTextVNode("重置", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            variant: "tonal",
                            disabled: !currentPath.value || !engineReady.value,
                            loading: holdSubmitting.value,
                            onClick: _cache[17] || (_cache[17] = $event => (enqueueHold()))
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(editingJobId.value ? '更新任务' : '仅加入队列'), 1)
                            ]),
                            _: 1
                          }, 8, ["disabled", "loading"]),
                          _createVNode(_component_v_btn, {
                            color: "primary",
                            variant: "flat",
                            disabled: !currentPath.value || !engineReady.value,
                            onClick: _cache[18] || (_cache[18] = $event => (openPreview()))
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(engineReady.value ? (editingJobId.value ? '预览并更新' : '预览并确认') : '需安装 MKVToolNix'), 1)
                            ]),
                            _: 1
                          }, 8, ["disabled"])
                        ])
                      ])
                    ], 64))
            ])
          ]))
        : (tab.value === 'queue')
          ? (_openBlock(), _createBlock(QueuePage, {
              key: 1,
              jobs: queueJobs.value,
              paused: queuePaused.value,
              concurrency: Number(config.value.concurrency) || 1,
              held: Number(status.value.queue?.held) || 0,
              "editing-id": editingJobId.value,
              loading: queueLoading.value,
              layout: layoutMode.value,
              onRefresh: _cache[19] || (_cache[19] = $event => (loadQueue(false))),
              onCancel: cancelJob,
              onMove: moveJob,
              onPause: togglePause,
              onClear: clearPending,
              onStart: startJob,
              onStartAll: startAllJobs,
              onEdit: startEditJob,
              onSetConcurrency: setConcurrency
            }, null, 8, ["jobs", "paused", "concurrency", "held", "editing-id", "loading", "layout"]))
          : (tab.value === 'history')
            ? (_openBlock(), _createBlock(HistoryPage, {
                key: 2,
                items: historyItems.value,
                total: historyTotal.value,
                keep: Number(config.value.history_keep) || 200,
                loading: historyLoading.value,
                layout: layoutMode.value,
                onRefresh: _cache[20] || (_cache[20] = $event => (loadHistory(false))),
                onRollback: rollbackHistory,
                onReopen: reopenHistory,
                onDelete: deleteHistory,
                onClear: clearHistory
              }, null, 8, ["items", "total", "keep", "loading", "layout"]))
            : (tab.value === 'settings')
              ? (_openBlock(), _createElementBlock("div", _hoisted_99, [
                  _createElementVNode("div", _hoisted_100, [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "tonal",
                      "prepend-icon": "mdi-arrow-left",
                      onClick: _cache[21] || (_cache[21] = $event => (backFromSettings()))
                    }, {
                      default: _withCtx(() => [...(_cache[102] || (_cache[102] = [
                        _createTextVNode(" 返回主页面 ", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[103] || (_cache[103] = _createElementVNode("span", { class: "mkv-settings-title" }, "设置", -1))
                  ]),
                  _createElementVNode("div", _hoisted_101, [
                    _createVNode(Config, {
                      api: props.api,
                      "plugin-id": props.pluginId,
                      "initial-config": config.value,
                      embedded: true,
                      onSave: onConfigSaved
                    }, null, 8, ["api", "plugin-id", "initial-config"])
                  ])
                ]))
              : _createCommentVNode("", true)
    ]),
    (bottomBarVisible.value)
      ? (_openBlock(), _createElementBlock("footer", _hoisted_102, [
          _createElementVNode("span", {
            class: _normalizeClass(["bottom-dot", { paused: queuePaused.value }])
          }, null, 2),
          (runningJob.value)
            ? (_openBlock(), _createElementBlock("span", _hoisted_103, [
                _cache[104] || (_cache[104] = _createTextVNode("运行中 ", -1)),
                _createElementVNode("b", null, _toDisplayString(runningJob.value.name), 1)
              ]))
            : (_openBlock(), _createElementBlock("span", _hoisted_104, "队列等待中")),
          (runningJob.value)
            ? (_openBlock(), _createElementBlock("div", _hoisted_105, [
                _createElementVNode("i", {
                  style: _normalizeStyle({ width: `${runningProgress.value}%` })
                }, null, 4)
              ]))
            : _createCommentVNode("", true),
          (runningJob.value && !narrow.value)
            ? (_openBlock(), _createElementBlock("span", _hoisted_106, _toDisplayString(runningProgress.value) + "%", 1))
            : _createCommentVNode("", true),
          _cache[107] || (_cache[107] = _createElementVNode("span", { class: "mkv-spacer" }, null, -1)),
          (queueCount.value)
            ? (_openBlock(), _createElementBlock("span", _hoisted_107, [
                _cache[105] || (_cache[105] = _createTextVNode("队列 ", -1)),
                _createElementVNode("b", null, _toDisplayString(queueCount.value), 1),
                _cache[106] || (_cache[106] = _createTextVNode(" 个等待", -1))
              ]))
            : _createCommentVNode("", true),
          _createElementVNode("button", {
            type: "button",
            class: "bottom-link",
            onClick: _cache[22] || (_cache[22] = $event => (switchTab('queue')))
          }, "查看队列 →")
        ]))
      : _createCommentVNode("", true),
    (!wide.value)
      ? (_openBlock(), _createBlock(_component_v_dialog, {
          key: 3,
          modelValue: treeDialog.value,
          "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((treeDialog).value = $event)),
          fullscreen: narrow.value,
          "max-width": narrow.value ? undefined : 'min(620px, 55vw)',
          scrollable: "",
          transition: "dialog-bottom-transition"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              class: _normalizeClass(["mkv-tree-dialog", { 'mkv-tree-dialog--window': !narrow.value }])
            }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_108, [
                  _cache[108] || (_cache[108] = _createElementVNode("span", null, "媒体文件", -1)),
                  _createVNode(_component_v_spacer),
                  _createVNode(_component_v_btn, {
                    icon: "mdi-close",
                    variant: "text",
                    size: "small",
                    "aria-label": "关闭",
                    onClick: _cache[23] || (_cache[23] = $event => (treeDialog.value = false))
                  })
                ]),
                _createElementVNode("div", _hoisted_109, [
                  _createVNode(FileTree, {
                    api: _unref(api),
                    roots: config.value.roots || [],
                    current: currentPath.value,
                    "refresh-tick": fileStatusTick.value,
                    onSelect: onSelectFile
                  }, null, 8, ["api", "roots", "current", "refresh-tick"])
                ])
              ]),
              _: 1
            }, 8, ["class"])
          ]),
          _: 1
        }, 8, ["modelValue", "fullscreen", "max-width"]))
      : _createCommentVNode("", true),
    _createVNode(_component_v_dialog, {
      modelValue: duplicateState.value.open,
      "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((duplicateState.value.open) = $event)),
      "max-width": "560",
      persistent: ""
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { class: "duplicate-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_110, [
              _createElementVNode("span", _hoisted_111, _toDisplayString(duplicateState.value.conflict?.state === 'running' ? '当前任务正在运行' : '检测到未完成的队列任务'), 1),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                "aria-label": "关闭",
                onClick: _cache[25] || (_cache[25] = $event => (chooseDuplicate('cancel')))
              })
            ]),
            _createElementVNode("div", _hoisted_112, [
              (duplicateState.value.conflict?.state === 'running')
                ? (_openBlock(), _createElementBlock("p", _hoisted_113, [
                    _cache[109] || (_cache[109] = _createTextVNode(" 当前文件有正在运行的任务", -1)),
                    (duplicateState.value.conflict?.job_id)
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                          _createTextVNode("（#" + _toDisplayString(duplicateState.value.conflict.job_id) + "）", 1)
                        ], 64))
                      : _createCommentVNode("", true),
                    _cache[110] || (_cache[110] = _createTextVNode("，新任务会在其结束后执行。 ", -1))
                  ]))
                : (_openBlock(), _createElementBlock("p", _hoisted_114, [
                    _cache[111] || (_cache[111] = _createTextVNode(" 当前文件已有待开始的队列任务", -1)),
                    (duplicateState.value.conflict?.job_id)
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                          _createTextVNode("（#" + _toDisplayString(duplicateState.value.conflict.job_id) + "）", 1)
                        ], 64))
                      : _createCommentVNode("", true),
                    _cache[112] || (_cache[112] = _createTextVNode("。 可以更新现有任务，或再提交一个新任务。 ", -1))
                  ]))
            ]),
            _createElementVNode("div", _hoisted_115, [
              (duplicateState.value.conflict?.state !== 'running')
                ? (_openBlock(), _createBlock(_component_v_btn, {
                    key: 0,
                    color: "primary",
                    variant: "flat",
                    onClick: _cache[26] || (_cache[26] = $event => (chooseDuplicate('update')))
                  }, {
                    default: _withCtx(() => [...(_cache[113] || (_cache[113] = [
                      _createTextVNode(" 更新现有队列任务 ", -1)
                    ]))]),
                    _: 1
                  }))
                : _createCommentVNode("", true),
              _createVNode(_component_v_btn, {
                color: duplicateState.value.conflict?.state !== 'running' ? undefined : 'primary',
                variant: duplicateState.value.conflict?.state !== 'running' ? 'tonal' : 'flat',
                onClick: _cache[27] || (_cache[27] = $event => (chooseDuplicate('new')))
              }, {
                default: _withCtx(() => [...(_cache[114] || (_cache[114] = [
                  _createTextVNode(" 再提交一个新任务 ", -1)
                ]))]),
                _: 1
              }, 8, ["color", "variant"]),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[28] || (_cache[28] = $event => (chooseDuplicate('cancel')))
              }, {
                default: _withCtx(() => [...(_cache[115] || (_cache[115] = [
                  _createTextVNode("取消", -1)
                ]))]),
                _: 1
              })
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: archiveDialog.value.open,
      "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((archiveDialog.value.open) = $event)),
      "max-width": "540"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { class: "archive-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_116, [
              _cache[116] || (_cache[116] = _createElementVNode("span", { class: "archive-title" }, "从目录批量解压字体", -1)),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                "aria-label": "关闭",
                onClick: _cache[30] || (_cache[30] = $event => (archiveDialog.value.open = false))
              })
            ]),
            _createElementVNode("div", _hoisted_117, [
              _cache[118] || (_cache[118] = _createElementVNode("div", { class: "archive-field-label" }, "目录路径", -1)),
              _createVNode(_component_v_text_field, {
                modelValue: archiveDialog.value.path,
                "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((archiveDialog.value.path) = $event)),
                placeholder: "/media/动画/字体",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                class: "mono"
              }, null, 8, ["modelValue"]),
              _createElementVNode("div", _hoisted_118, [
                _createVNode(_component_v_checkbox, {
                  modelValue: archiveDialog.value.recursive,
                  "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((archiveDialog.value.recursive) = $event)),
                  density: "compact",
                  "hide-details": "",
                  label: "包含子目录"
                }, null, 8, ["modelValue"]),
                _cache[117] || (_cache[117] = _createElementVNode("span", { class: "archive-tip" }, "扫描目录下的 zip / 7z / rar / tar 压缩包，解压字体加入附件", -1))
              ]),
              _createElementVNode("div", _hoisted_119, _toDisplayString(archiveHint.value), 1)
            ]),
            _createElementVNode("div", _hoisted_120, [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                disabled: archiveDialog.value.loading,
                onClick: _cache[33] || (_cache[33] = $event => (archiveDialog.value.open = false))
              }, {
                default: _withCtx(() => [...(_cache[119] || (_cache[119] = [
                  _createTextVNode("取消", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                loading: archiveDialog.value.loading,
                onClick: runArchiveBatch
              }, {
                default: _withCtx(() => [...(_cache[120] || (_cache[120] = [
                  _createTextVNode("解压", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(PreviewDialog, {
      modelValue: previewOpen.value,
      "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((previewOpen).value = $event)),
      confirmed: durationMismatchConfirmed.value,
      "onUpdate:confirmed": _cache[36] || (_cache[36] = $event => ((durationMismatchConfirmed).value = $event)),
      path: currentPath.value,
      result: planResult.value,
      loading: previewLoading.value,
      submitting: previewSubmitting.value,
      "engine-ready": engineReady.value,
      layout: layoutMode.value,
      title: editingJobId.value ? '更新队列任务' : '确认执行',
      "confirm-text": editingJobId.value ? '确认更新' : '确认执行',
      onConfirm: confirmRun
    }, null, 8, ["modelValue", "confirmed", "path", "result", "loading", "submitting", "engine-ready", "layout", "title", "confirm-text"]),
    _createVNode(FilePickerDialog, {
      modelValue: picker.value.open,
      "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((picker.value.open) = $event)),
      api: _unref(api),
      kind: picker.value.kind,
      title: picker.value.title,
      roots: config.value.roots || [],
      "initial-path": picker.value.initialPath,
      exts: picker.value.exts,
      layout: layoutMode.value,
      onSelect: onPicked
    }, null, 8, ["modelValue", "api", "kind", "title", "roots", "initial-path", "exts", "layout"]),
    _createVNode(UploadDialog, {
      modelValue: uploadDialog.value.open,
      "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((uploadDialog.value.open) = $event)),
      api: _unref(api),
      kind: uploadDialog.value.kind,
      "max-mb": uploadMaxMb.value,
      layout: layoutMode.value,
      onUploaded: onUploaded
    }, null, 8, ["modelValue", "api", "kind", "max-mb", "layout"]),
    _createVNode(ConfirmDialog, {
      modelValue: confirmState.value.open,
      "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((confirmState.value.open) = $event)),
      title: confirmState.value.title,
      text: confirmState.value.text,
      detail: confirmState.value.detail,
      "confirm-text": confirmState.value.confirmText,
      color: confirmState.value.color,
      loading: confirmState.value.loading,
      onConfirm: runConfirm
    }, null, 8, ["modelValue", "title", "text", "detail", "confirm-text", "color", "loading"]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.value.show,
      "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((snackbar.value.show) = $event)),
      color: snackbar.value.color,
      timeout: 2200,
      location: "bottom"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(snackbar.value.text), 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ], 2))
}
}

};
const AppPage = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-90ed53f1"]]);

export { AppPage as default };
