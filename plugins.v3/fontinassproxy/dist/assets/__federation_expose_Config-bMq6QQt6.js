import { importShared } from './__federation_fn_import-JrT3xvdd.js';

/**
 * 字幕字体代理 - API 封装
 * 通过宿主注入的 api 模块调用后端接口（/api/v1/plugin/FontInAssProxy/xxx）
 */
const PLUGIN_ID = 'FontInAssProxy';

/**
 * 统一解包后端响应
 * 后端接口可能直接返回 {success, message, data}，也可能直接返回业务数据
 */
function unwrap(response) {
  const body = response && Object.prototype.hasOwnProperty.call(response, 'success')
    ? response
    : (response?.data ?? response);
  if (body?.success === false) {
    const err = new Error(body.message || '请求失败');
    err.code = body.code;
    throw err
  }
  return body?.data ?? body ?? {}
}

async function get(api, path, params = {}) {
  const res = await api.get(`plugin/${PLUGIN_ID}${path}`, { params });
  return unwrap(res)
}

async function post(api, path, data = {}) {
  const res = await api.post(`plugin/${PLUGIN_ID}${path}`, data);
  return unwrap(res)
}

const apiModule = { get, post };

const {resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');


const {inject,onMounted,ref,getCurrentInstance} = await importShared('vue');


const _sfc_main = {
  __name: 'Settings',
  props: {
  api: { type: Object, default: () => ({}) },
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['save'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject('moviepilot:toast', null);
const instance = getCurrentInstance();

const DEFAULTS = {
  enabled: true,
  emby_url: '',
  emby_api_key: '',
  font_dirs: '',
  srt_default_font: '思源黑体 CN',
  srt_font_size: 20,
  srt_primary_colour: '&H00FFFFFF',
  cache_enabled: true,
  cache_ttl_hours: 24,
  max_concurrent_subset: 4,
  passthrough_on_error: true,
  internal_proxy_enabled: false,
  internal_proxy_port: 8097,
  notify_enabled: true,
};

const cfg = ref({ ...DEFAULTS });
const saving = ref(false);

function toastMsg(type, message) {
  if (toast && typeof toast[type] === 'function') toast[type](message);
}

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '68rem' });
  try {
    const cur = await apiModule.get(props.api, '/config');
    cfg.value = { ...DEFAULTS, ...(props.initialConfig || {}), ...(cur || {}) };
  } catch (e) {
    toastMsg('error', '加载配置失败: ' + e.message);
  }
});

async function save() {
  saving.value = true;
  try {
    await apiModule.post(props.api, '/config', cfg.value);
    emit('save');
    toastMsg('success', '配置已保存并生效');
  } catch (e) {
    toastMsg('error', '保存失败: ' + e.message);
  } finally {
    saving.value = false;
  }
}

return (_ctx, _cache) => {
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, {
    variant: "tonal",
    class: "pa-4"
  }, {
    default: _withCtx(() => [
      _createVNode(_component_v_row, { dense: "" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_col, { cols: "12" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_switch, {
                modelValue: cfg.value.enabled,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((cfg.value.enabled) = $event)),
                label: "启用插件",
                hint: "关闭时字幕请求原样透传（返回 502）",
                "persistent-hint": ""
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_text_field, {
                modelValue: cfg.value.emby_url,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((cfg.value.emby_url) = $event)),
                label: "Emby/Jellyfin 地址",
                hint: "如 http://192.168.1.10:8096，需 MoviePilot 容器可访问",
                "persistent-hint": "",
                density: "comfortable"
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_text_field, {
                modelValue: cfg.value.emby_api_key,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((cfg.value.emby_api_key) = $event)),
                label: "回源 API Key",
                hint: "留空则转发客户端原始 api_key",
                "persistent-hint": "",
                density: "comfortable"
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, { cols: "12" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_textarea, {
                modelValue: cfg.value.font_dirs,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.value.font_dirs) = $event)),
                label: "字体目录",
                rows: "2",
                "auto-grow": "",
                hint: "多个用 ; 分隔，递归扫描；目录必须挂载进 MoviePilot 容器",
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
                modelValue: cfg.value.srt_default_font,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.value.srt_default_font) = $event)),
                label: "SRT 兜底字体",
                hint: "SRT / 无明确字体名 / 字体缺失时兜底",
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
                modelValue: cfg.value.srt_font_size,
                "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.value.srt_font_size) = $event)),
                label: "SRT 转 ASS 字号",
                type: "number",
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
                modelValue: cfg.value.srt_primary_colour,
                "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.value.srt_primary_colour) = $event)),
                label: "SRT 转 ASS 主色（BGR）",
                hint: "十六进制，如 &H00FFFFFF",
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
              _createVNode(_component_v_switch, {
                modelValue: cfg.value.cache_enabled,
                "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.value.cache_enabled) = $event)),
                label: "处理结果缓存",
                hint: "内存 + 磁盘双层",
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
                modelValue: cfg.value.cache_ttl_hours,
                "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.value.cache_ttl_hours) = $event)),
                label: "缓存有效期（小时）",
                type: "number",
                hint: "磁盘缓存保留时长，默认 24（1 天）；每 4 小时清理一次",
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
                modelValue: cfg.value.max_concurrent_subset,
                "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.value.max_concurrent_subset) = $event)),
                label: "子集化并发上限",
                type: "number",
                hint: "保护 MP 主进程，超限请求降级透传",
                "persistent-hint": "",
                density: "comfortable"
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, { cols: "12" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_switch, {
                modelValue: cfg.value.passthrough_on_error,
                "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.value.passthrough_on_error) = $event)),
                label: "处理失败时返回原始字幕",
                hint: "关闭时失败返回 500",
                "persistent-hint": ""
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_switch, {
                modelValue: cfg.value.internal_proxy_enabled,
                "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.value.internal_proxy_enabled) = $event)),
                label: "启用内置反代端口",
                hint: "不依赖 nginx，客户端直接访问本端口；需要在 MP 容器映射该端口",
                "persistent-hint": ""
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_text_field, {
                modelValue: cfg.value.internal_proxy_port,
                "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.value.internal_proxy_port) = $event)),
                label: "内置反代端口",
                type: "number",
                hint: "如 8097，MP 容器需映射（ports 加 8097:8097）",
                "persistent-hint": "",
                density: "comfortable"
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_col, { cols: "12" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_switch, {
                modelValue: cfg.value.notify_enabled,
                "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.value.notify_enabled) = $event)),
                label: "启用通知",
                hint: "新字体入库 / 缺失字体 / 处理错误时发送消息通知（默认开启，关闭则静默）",
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
            default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
              _createTextVNode("保存配置", -1)
            ]))]),
            _: 1
          }, 8, ["loading"])
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};

export { apiModule as a, _sfc_main as default };
