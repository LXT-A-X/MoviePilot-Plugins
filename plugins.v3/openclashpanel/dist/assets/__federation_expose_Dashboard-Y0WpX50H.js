import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { c as createApi } from './api-BhchXaeF.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,resolveComponent:_resolveComponent,createVNode:_createVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createTextVNode:_createTextVNode,createCommentVNode:_createCommentVNode,withCtx:_withCtx,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "ocp-dash__head" };
const _hoisted_2 = { class: "text-caption" };
const _hoisted_3 = { class: "ocp-dash__tag" };
const _hoisted_4 = { class: "text-caption" };
const _hoisted_5 = { class: "text-caption" };
const _hoisted_6 = { class: "ocp-dash__net" };
const _hoisted_7 = { class: "text-caption ocp-dash__label" };
const _hoisted_8 = {
  key: 0,
  class: "text-caption"
};
const _hoisted_9 = { class: "ocp-dash__groups" };
const _hoisted_10 = { class: "text-caption ocp-dash__label" };
const _hoisted_11 = { class: "ocp-dash__now" };
const _hoisted_12 = {
  key: 0,
  class: "text-caption"
};
const _hoisted_13 = {
  key: 0,
  class: "ocp-dash__nodes"
};
const _hoisted_14 = { class: "text-caption ocp-dash__label" };
const _hoisted_15 = {
  key: 0,
  class: "text-caption"
};

const {computed,onBeforeUnmount,onMounted,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Dashboard',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OpenClashPanel' },
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
  nativeSubscribe: { type: Function, default: null },
},
  setup(__props) {

const props = __props;

const api = createApi(props);
const status = ref({});
const groups = ref([]);
const netResults = ref([]);
const netMode = ref('mp');
const netChecking = ref(false);
const error = ref('');
let timer = null;

const defaultGroup = computed(
  () => groups.value.find((item) => item.name.includes('默认代理')) || groups.value[0] || null,
);

function loadConfigMode() {
  const cfg = props.config || {};
  const saved = cfg.netcheck_mode;
  netMode.value = ['kernel', 'mp', 'clash'].includes(saved) ? saved : 'kernel';
}

async function load() {
  error.value = '';
  try {
    const [s, g] = await Promise.all([api.get('/status'), api.get('/groups')]);
    status.value = s || {};
    groups.value = (g && g.groups) || [];
  } catch (e) {
    error.value = e.message || '加载失败';
  }
  await loadNet(0);
}

async function loadNet(retry) {
  try {
    const res = await api.get('/netcheck', { mode: netMode.value });
    netResults.value = (res && res.results) || [];
    netChecking.value = Boolean(res && res.checking);
    if (netChecking.value && retry < 10) {
      setTimeout(() => loadNet(retry + 1), 1500);
    }
  } catch (e) {
    netChecking.value = false;
  }
}

function fmtNow(group) {
  if (!group) return ''
  if (group.type === 'Smart') return '智能自动选路'
  return group.now || '—'
}

function netColor(item) {
  if (item.delay == null) return 'error'
  if (item.delay < 300) return 'success'
  if (item.delay < 1000) return 'warning'
  return 'error'
}

function netText(item) {
  return item.delay == null ? '失败' : `${item.delay}ms`
}

function openPanel() {
  window.location.hash = `#/plugin-app/${props.pluginId}/main`;
}

function fmtBytes(n) {
  if (n == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i ? 1 : 0)} ${units[i]}`
}

onMounted(() => {
  loadConfigMode();
  load();
  timer = setInterval(load, 30000);
});

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
  timer = null;
});

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, {
    variant: "flat",
    class: "ocp-dash pa-3",
    onClick: openPanel
  }, {
    default: _withCtx(() => [
      _createElementVNode("div", _hoisted_1, [
        _createElementVNode("span", {
          class: _normalizeClass(["ocp-dot", status.value.meta ? 'ocp-dot--ok' : 'ocp-dot--bad'])
        }, null, 2),
        _cache[0] || (_cache[0] = _createElementVNode("span", { class: "ocp-dash__title" }, "OpenClash", -1)),
        _createElementVNode("span", _hoisted_2, _toDisplayString(status.value.version || '—'), 1),
        _createElementVNode("span", _hoisted_3, _toDisplayString(status.value.mode || '—'), 1),
        _createElementVNode("span", _hoisted_4, " 默认代理 → " + _toDisplayString(fmtNow(defaultGroup.value)), 1),
        _createVNode(_component_v_spacer),
        _createElementVNode("span", _hoisted_5, _toDisplayString(status.value.active_connections ?? '—') + " 连接 · " + _toDisplayString(fmtBytes(status.value.download_total)) + " ↓ / " + _toDisplayString(fmtBytes(status.value.upload_total)) + " ↑ ", 1)
      ]),
      _createElementVNode("div", _hoisted_6, [
        _createElementVNode("span", _hoisted_7, _toDisplayString(netMode.value === 'clash' ? 'OpenClash' : netMode.value === 'kernel' ? '内核' : 'MP') + " 访问检查", 1),
        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(netResults.value, (item) => {
          return (_openBlock(), _createElementBlock("span", {
            key: item.name,
            class: "ocp-dash__netitem"
          }, [
            _createElementVNode("span", {
              class: _normalizeClass(["ocp-dot", `ocp-dot--${netColor(item)}`])
            }, null, 2),
            _createTextVNode(" " + _toDisplayString(item.name) + " " + _toDisplayString(netText(item)), 1)
          ]))
        }), 128)),
        (!netResults.value.length)
          ? (_openBlock(), _createElementBlock("span", _hoisted_8, _toDisplayString(netChecking.value ? '检查中…' : (error.value || '暂无结果')), 1))
          : _createCommentVNode("", true)
      ]),
      _createElementVNode("div", _hoisted_9, [
        _createElementVNode("span", _hoisted_10, "策略组（" + _toDisplayString(groups.value.length) + "）", 1),
        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(groups.value.slice(0, 10), (group) => {
          return (_openBlock(), _createBlock(_component_v_chip, {
            key: group.name,
            size: "x-small",
            variant: group.name === defaultGroup.value?.name ? 'flat' : 'outlined',
            color: group.name === defaultGroup.value?.name ? 'primary' : undefined
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(group.name), 1),
              _createElementVNode("span", _hoisted_11, "→ " + _toDisplayString(fmtNow(group)), 1)
            ]),
            _: 2
          }, 1032, ["variant", "color"]))
        }), 128)),
        (groups.value.length > 10)
          ? (_openBlock(), _createElementBlock("span", _hoisted_12, "+" + _toDisplayString(groups.value.length - 10), 1))
          : _createCommentVNode("", true)
      ]),
      (defaultGroup.value)
        ? (_openBlock(), _createElementBlock("div", _hoisted_13, [
            _createElementVNode("span", _hoisted_14, _toDisplayString(defaultGroup.value.name) + " 节点", 1),
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((defaultGroup.value.members || []).slice(0, 10), (member) => {
              return (_openBlock(), _createBlock(_component_v_chip, {
                key: member.name,
                size: "x-small",
                variant: member.selected ? 'flat' : 'outlined',
                color: member.selected ? 'primary' : undefined
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(member.name), 1)
                ]),
                _: 2
              }, 1032, ["variant", "color"]))
            }), 128)),
            ((defaultGroup.value.members || []).length > 10)
              ? (_openBlock(), _createElementBlock("span", _hoisted_15, " +" + _toDisplayString((defaultGroup.value.members || []).length - 10), 1))
              : _createCommentVNode("", true)
          ]))
        : _createCommentVNode("", true)
    ]),
    _: 1
  }))
}
}

};
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-5ece3684"]]);

export { Dashboard as default };
