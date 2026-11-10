import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import AppPage from './__federation_expose_AppPage-DCNC-ML9.js';

const {openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

// 宿主注入契约：api / pluginId / navKey / initialConfig / nativeSubscribe

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MkvToolkit' },
  navKey: { type: String, default: 'main' },
  initialConfig: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
},
  emits: ['action', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

return (_ctx, _cache) => {
  return (_openBlock(), _createBlock(AppPage, {
    api: props.api,
    "plugin-id": props.pluginId,
    "nav-key": props.navKey,
    "initial-config": props.initialConfig,
    "native-subscribe": props.nativeSubscribe,
    "show-close": true,
    onAction: _cache[0] || (_cache[0] = $event => (emit('action'))),
    onClose: _cache[1] || (_cache[1] = $event => (emit('close'))),
    onSwitch: _cache[2] || (_cache[2] = $event => (emit('switch')))
  }, null, 8, ["api", "plugin-id", "nav-key", "initial-config", "native-subscribe"]))
}
}

};

export { _sfc_main as default };
