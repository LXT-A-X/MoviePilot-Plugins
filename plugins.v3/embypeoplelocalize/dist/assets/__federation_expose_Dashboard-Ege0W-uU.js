import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { a as api } from './client-Dg9zA7Bo.js';

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,createVNode:_createVNode,Fragment:_Fragment,createElementBlock:_createElementBlock,vShow:_vShow,withDirectives:_withDirectives,mergeProps:_mergeProps} = await importShared('vue');


const _hoisted_1 = { class: "text-h5" };
const _hoisted_2 = { class: "text-caption mt-1" };
const _hoisted_3 = { class: "absolute right-5 top-5" };

const {inject,onMounted,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Dashboard',
  props: {
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'EmbyPeopleLocalize' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
},
  emits: ['action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const loading = ref(true);
const db = ref(null);

async function load() {
  loading.value = true;
  try { db.value = await api.get(props.api, '/db/stats'); }
  catch (e) { db.value = null; }
  loading.value = false;
}
onMounted(load);

return (_ctx, _cache) => {
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_hover = _resolveComponent("v-hover");

  return (_openBlock(), _createBlock(_component_v_hover, null, {
    default: _withCtx(({ isHovering, props: hoverProps }) => [
      _createVNode(_component_v_card, _mergeProps(hoverProps, { class: "w-100" }), {
        default: _withCtx(() => [
          _createVNode(_component_v_card_text, { class: "text-center pa-4" }, {
            default: _withCtx(() => [
              (loading.value)
                ? (_openBlock(), _createBlock(_component_v_progress_circular, {
                    key: 0,
                    indeterminate: "",
                    size: "32",
                    color: "primary"
                  }))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createElementVNode("div", _hoisted_1, _toDisplayString(db.value?.item_count ?? 0), 1),
                    _cache[1] || (_cache[1] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "翻译条目", -1)),
                    _createElementVNode("div", _hoisted_2, _toDisplayString(db.value?.person_count ?? 0) + " 个演员 / 已译 " + _toDisplayString(db.value?.translated_people ?? 0), 1),
                    (__props.allowRefresh)
                      ? (_openBlock(), _createBlock(_component_v_btn, {
                          key: 0,
                          size: "x-small",
                          variant: "text",
                          class: "mt-1",
                          onClick: load
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_icon, { size: "16" }, {
                              default: _withCtx(() => [...(_cache[0] || (_cache[0] = [
                                _createTextVNode("mdi-refresh", -1)
                              ]))]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true)
                  ], 64))
            ]),
            _: 1
          }),
          _withDirectives(_createElementVNode("div", _hoisted_3, [
            _createVNode(_component_v_icon, { class: "cursor-move" }, {
              default: _withCtx(() => [...(_cache[2] || (_cache[2] = [
                _createTextVNode("mdi-drag", -1)
              ]))]),
              _: 1
            })
          ], 512), [
            [_vShow, isHovering]
          ])
        ]),
        _: 2
      }, 1040)
    ]),
    _: 1
  }))
}
}

};

export { _sfc_main as default };
