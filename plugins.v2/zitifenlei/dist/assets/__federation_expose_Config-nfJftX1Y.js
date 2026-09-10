import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, S as Settings, C as Check, F as FontLibrary, D as Dashboard } from './Settings-BJtwxi_I.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createBlock:_createBlock,createCommentVNode:_createCommentVNode,resolveDynamicComponent:_resolveDynamicComponent,KeepAlive:_KeepAlive} = await importShared('vue');


const _hoisted_1 = { class: "zt-app" };
const _hoisted_2 = { class: "zt-layout" };
const _hoisted_3 = { class: "zt-nav zt-card-bg" };
const _hoisted_4 = { class: "zt-nav-header" };
const _hoisted_5 = { class: "zt-app-title" };
const _hoisted_6 = { class: "zt-content" };
const _hoisted_7 = {
  key: 0,
  class: "zt-disabled-mask"
};
const _hoisted_8 = { class: "zt-disabled-card zt-card-bg" };

const {computed,inject,onMounted,ref,getCurrentInstance} = await importShared('vue');

// 宿主注入的能力

const _sfc_main = {
  __name: 'Config',
  props: {
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'Zitifenlei' },
  // 宿主拉取 GET /plugin/form/{id} 返回的合并 model（默认值+已存配置），作为配置唯一数据源
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['action', 'layout', 'close', 'save'],
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
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
];

const active = ref('dashboard');
const loading = ref(true);

// 全局配置：以宿主 initial-config 为准（原生保存后宿主回传的就是这份数据）
const pluginConfig = ref({
  enabled: true,
  input_dir: '',
  lib_dir: '',
  ass_dir: '',
  scan_mode: 'internal',
  archive_mode: 'copy',
  auto_monitor: false,
  auto_check: false,
  notify_enabled: false,
  ...(props.initialConfig || {}),
});
const pluginEnabled = computed(() => pluginConfig.value.enabled !== false);

// 设置页保存回调：仅更新本地开关状态。
// 持久化由设置页 POST /config 交给后端 update_config 完成（对齐 subscribeplus 单通道），
// 不再 emit('save') 转发宿主 PUT，避免双保存冲突。
function onConfigSave(cfg) {
  if (cfg && typeof cfg === 'object') {
    pluginConfig.value = { ...pluginConfig.value, ...cfg };
  }
}

// 视图：点到哪里，右边显示什么
const views = {
  dashboard: Dashboard,
  fonts: FontLibrary,
  check: Check,
  settings: Settings,
};
const currentView = computed(() => views[active.value] || Dashboard);

onMounted(async () => {
  // 通知宿主：最大需要 68rem 宽度
  instance?.emit('layout', { maxWidth: '68rem' });

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

// 关闭插件页（右上角 X）：先走宿主 close 事件，再退浏览器历史兜底
function closePlugin() {
  try {
    emit('close');
  } catch (e) {
    // 忽略
  }
  try {
    if (window.history.length > 1) {
      window.history.back();
    } else if (window.close) {
      window.close();
    }
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
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("div", _hoisted_4, [
          _createElementVNode("div", _hoisted_5, [
            _createVNode(_component_v_icon, { start: "" }, {
              default: _withCtx(() => [...(_cache[2] || (_cache[2] = [
                _createTextVNode("mdi-format-font", -1)
              ]))]),
              _: 1
            }),
            _cache[3] || (_cache[3] = _createTextVNode(" 字体分类管家 ", -1))
          ]),
          _cache[4] || (_cache[4] = _createElementVNode("div", { class: "zt-app-subtitle" }, "Font Manager", -1))
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
                "initial-config": pluginConfig.value,
                enabled: pluginEnabled.value,
                onNotify: notify,
                onAction: _cache[0] || (_cache[0] = $event => (emit('action'))),
                onSave: onConfigSave
              }, null, 40, ["api", "target", "initial-config", "enabled"]))
            ], 1024))
      ])
    ]),
    _createVNode(_component_v_btn, {
      icon: "mdi-close",
      size: "small",
      variant: "tonal",
      class: "zt-close-btn",
      title: "关闭插件",
      onClick: closePlugin
    }),
    (!pluginEnabled.value && active.value !== 'settings')
      ? (_openBlock(), _createElementBlock("div", _hoisted_7, [
          _createElementVNode("div", _hoisted_8, [
            _createVNode(_component_v_icon, {
              color: "warning",
              size: "44",
              class: "mb-2"
            }, {
              default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
                _createTextVNode("mdi-power-off", -1)
              ]))]),
              _: 1
            }),
            _cache[8] || (_cache[8] = _createElementVNode("div", { class: "zt-disabled-title" }, "插件已停用", -1)),
            _cache[9] || (_cache[9] = _createElementVNode("div", { class: "zt-disabled-desc" }, "插件已被关闭，其他页面暂不可用", -1)),
            _createVNode(_component_v_btn, {
              color: "primary",
              variant: "tonal",
              class: "mt-3",
              onClick: _cache[1] || (_cache[1] = $event => (active.value = 'settings'))
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
                    _createTextVNode("mdi-cog-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[7] || (_cache[7] = _createTextVNode(" 前往设置启用 ", -1))
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
          default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
            _createTextVNode(" 插件当前已停用：其他页面不可操作，请在本页开启「插件总开关」并保存。 ", -1)
          ]))]),
          _: 1
        }))
      : _createCommentVNode("", true)
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-0dc9c564"]]);

export { Config as default };
