import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { c as createApi } from './api-BhchXaeF.js';

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,createVNode:_createVNode,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const {getCurrentInstance,inject,onMounted,ref} = await importShared('vue');

const DEFAULT_SITES_TEXT =
  '百度搜索|https://www.baidu.com/|direct\n' +
  '网易云音乐|https://music.163.com/|direct\n' +
  'GitHub|https://github.com/|proxy\n' +
  'YouTube|https://www.youtube.com/|proxy';


const _sfc_main = {
  __name: 'Config',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'OpenClashPanel' },
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const toast = inject('moviepilot:toast', null);
const instance = getCurrentInstance();
const api = createApi(props);

const DEFAULTS = {
  enabled: true,
  api_url: 'http://192.168.1.1:9090',
  secret: '',
  timeout: 8,
  delay_test_url: 'https://www.gstatic.com/generate_204',
  delay_test_timeout: 5000,
  auto_refresh: 10,
  max_delay_concurrency: 8,
  show_dashboard: true,
  dashboard_url: 'http://192.168.1.1:9090/ui/zashboard/',
  log_level: 'info',
  netcheck_mode: 'kernel',
  netcheck_interval: 30,
  netcheck_timeout: 6,
  netcheck_sites: [
    { name: '百度搜索', url: 'https://www.baidu.com/', via: 'direct' },
    { name: '网易云音乐', url: 'https://music.163.com/', via: 'direct' },
    { name: 'GitHub', url: 'https://github.com/', via: 'proxy' },
    { name: 'YouTube', url: 'https://www.youtube.com/', via: 'proxy' },
  ],
  allow_commands: true,
  openwrt_enabled: false,
  openwrt_host: '192.168.1.1',
  openwrt_scheme: 'http',
  openwrt_username: 'root',
  openwrt_password: '',
};

const cfg = ref({ ...DEFAULTS, ...(props.initialConfig || {}) });
const sitesText = ref(DEFAULT_SITES_TEXT);
const saving = ref(false);
const loading = ref(true);

function sitesToText(sites) {
  if (!Array.isArray(sites) || !sites.length) return DEFAULT_SITES_TEXT
  return sites
    .map((site) => `${site.name || ''}|${site.url || ''}|${site.via === 'proxy' ? 'proxy' : 'direct'}`)
    .join('\n')
}

function textToSites(text) {
  return String(text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
    .map((line) => {
      const parts = line.split('|').map((part) => part.trim());
      if (parts.length < 2) return null
      let url = parts[1];
      if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
      const via = (parts[2] || 'direct').toLowerCase() === 'proxy' ? 'proxy' : 'direct';
      return { name: parts[0], url, via }
    })
    .filter(Boolean)
}

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message);
}

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '68rem' });
  try {
    const cur = await api.get('/config');
    cfg.value = { ...DEFAULTS, ...(props.initialConfig || {}), ...(cur || {}) };
    sitesText.value = sitesToText(cfg.value.netcheck_sites);
  } catch (e) {
    toastMsg('error', '加载配置失败：' + e.message);
  } finally {
    loading.value = false;
  }
});

// 保存契约：把配置作为事件参数交给宿主（MP 3.2.1 的配置弹窗会把该参数 PUT 到 /plugin/{id}），
// 不要再自己 POST，否则宿主收到 undefined 会报“参数不正确”。
function save() {
  saving.value = true;
  try {
    emit('save', { ...cfg.value, netcheck_sites: textToSites(sitesText.value) });
  } finally {
    saving.value = false;
  }
}

return (_ctx, _cache) => {
  const _component_v_skeleton_loader = _resolveComponent("v-skeleton-loader");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, {
    variant: "tonal",
    class: "pa-4"
  }, {
    default: _withCtx(() => [
      (loading.value)
        ? (_openBlock(), _createBlock(_component_v_skeleton_loader, {
            key: 0,
            type: "list-item@6"
          }))
        : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
            _createVNode(_component_v_alert, {
              type: "info",
              variant: "tonal",
              density: "compact",
              class: "mb-3"
            }, {
              default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                _createTextVNode(" API 地址只填 ", -1),
                _createElementVNode("code", null, "http://路由器IP:9090", -1),
                _createTextVNode("，不要带 ", -1),
                _createElementVNode("code", null, "/ui/...", -1),
                _createTextVNode("（误填会自动纠正）。 ", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_row, { dense: "" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: cfg.value.enabled,
                      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((cfg.value.enabled) = $event)),
                      label: "启用插件",
                      hint: "关闭后侧栏入口、日志采集与接口都不再工作",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.api_url,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((cfg.value.api_url) = $event)),
                      label: "OpenClash API 地址",
                      placeholder: "http://192.168.1.1:9090",
                      hint: "external-controller 根地址（默认 9090），不要填 zashboard 的 /ui 地址",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.secret,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((cfg.value.secret) = $event)),
                      label: "Dashboard 密码",
                      type: "password",
                      hint: "OpenClash → 插件设置 → Dashboard 密码",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.timeout,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.value.timeout) = $event)),
                      modelModifiers: { number: true },
                      label: "请求超时（秒）",
                      type: "number",
                      min: "2",
                      hint: "默认 8 秒",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.auto_refresh,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.value.auto_refresh) = $event)),
                      modelModifiers: { number: true },
                      label: "自动刷新间隔（秒）",
                      type: "number",
                      min: "0",
                      hint: "0 表示关闭自动刷新，默认 10 秒",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: cfg.value.log_level,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.value.log_level) = $event)),
                      items: ['debug', 'info', 'warning', 'error'],
                      label: "日志采集级别",
                      hint: "Clash /logs 的 level 参数",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: cfg.value.netcheck_mode,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.value.netcheck_mode) = $event)),
                      items: [{ title: '内核（与官方一致）', value: 'kernel' }, { title: 'MP 网络', value: 'mp' }, { title: 'OpenClash 代理', value: 'clash' }],
                      label: "访问检查视角",
                      hint: "内核：由 OpenClash 内核测速（官方同款，数字最低）；MP 网络/OpenClash：由 MP 容器测速",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.netcheck_interval,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.value.netcheck_interval) = $event)),
                      modelModifiers: { number: true },
                      label: "访问检查间隔（秒）",
                      type: "number",
                      min: "0",
                      hint: "默认 60，0 表示只手动检查",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.netcheck_timeout,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.value.netcheck_timeout) = $event)),
                      modelModifiers: { number: true },
                      label: "访问检查超时（秒）",
                      type: "number",
                      min: "2",
                      hint: "默认 6",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_textarea, {
                      modelValue: sitesText.value,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((sitesText).value = $event)),
                      label: "访问检查站点",
                      rows: "4",
                      "auto-grow": "",
                      hint: "每行一个：名称|URL|direct/proxy；direct=直连，proxy=国外站点走所选通道",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: cfg.value.allow_commands,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.value.allow_commands) = $event)),
                      label: "允许远程操作命令",
                      hint: "关闭后 /oc_node、/oc_mode、/oc_refresh 只返回提示；查询命令不受影响",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: cfg.value.openwrt_enabled,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.value.openwrt_enabled) = $event)),
                      label: "启用 OpenWrt 管理（需填写下面地址/用户名/密码）",
                      hint: "用于启动/停止/重启 OpenClash、切换运行模式、切换配置文件、更新订阅、清缓存、快捷设置",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.openwrt_host,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.value.openwrt_host) = $event)),
                      label: "OpenWrt 地址",
                      placeholder: "192.168.1.1",
                      hint: "路由器 IP 或域名（不含 http://）",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "6",
                  md: "2"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: cfg.value.openwrt_scheme,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.value.openwrt_scheme) = $event)),
                      items: ['http', 'https'],
                      label: "协议",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "6",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.openwrt_username,
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((cfg.value.openwrt_username) = $event)),
                      label: "LuCI 用户名",
                      placeholder: "root",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.openwrt_password,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((cfg.value.openwrt_password) = $event)),
                      type: "password",
                      label: "LuCI 密码",
                      hint: "仅用于登录路由器，不会写日志",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.delay_test_url,
                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((cfg.value.delay_test_url) = $event)),
                      label: "测速地址",
                      hint: "默认 https://www.gstatic.com/generate_204",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.delay_test_timeout,
                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((cfg.value.delay_test_timeout) = $event)),
                      modelModifiers: { number: true },
                      label: "测速超时（毫秒）",
                      type: "number",
                      min: "1000",
                      hint: "默认 5000",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.max_delay_concurrency,
                      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((cfg.value.max_delay_concurrency) = $event)),
                      modelModifiers: { number: true },
                      label: "测速并发数",
                      type: "number",
                      min: "1",
                      max: "32",
                      hint: "默认 8",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.value.dashboard_url,
                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((cfg.value.dashboard_url) = $event)),
                      label: "完整面板地址（zashboard）",
                      placeholder: "http://192.168.1.1:9090/ui/zashboard/",
                      hint: "“完整面板”按钮打开的地址",
                      "persistent-hint": "",
                      density: "comfortable"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4",
                  class: "d-flex align-center"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: cfg.value.show_dashboard,
                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((cfg.value.show_dashboard) = $event)),
                      label: "显示完整面板按钮",
                      hint: "在新窗口打开 zashboard",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_row, {
              class: "justify-end mt-2",
              "no-gutters": ""
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  color: "primary",
                  loading: saving.value,
                  onClick: save
                }, {
                  default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                    _createTextVNode("保存配置", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ], 64))
    ]),
    _: 1
  }))
}
}

};

export { _sfc_main as default };
