import { importShared } from './__federation_fn_import-JrT3xvdd.js';

/**
 * 字体分类管家 - API 封装
 * 通过宿主注入的 api 模块调用后端接口（/api/v1/plugin/Zitifenlei/xxx）
 */
const PLUGIN_ID = 'Zitifenlei';

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

/**
 * GET 请求
 */
async function get(api, path, params = {}) {
  try {
    const res = await api.get(`plugin/${PLUGIN_ID}${path}`, { params });
    return unwrap(res)
  } catch (e) {
    throw e
  }
}

/**
 * POST 请求（JSON body）
 */
async function post(api, path, data = {}) {
  try {
    const res = await api.post(`plugin/${PLUGIN_ID}${path}`, data);
    return unwrap(res)
  } catch (e) {
    throw e
  }
}

/**
 * PUT 请求
 */
async function put(api, path, data = {}) {
  try {
    const res = await api.put(`plugin/${PLUGIN_ID}${path}`, data);
    return unwrap(res)
  } catch (e) {
    throw e
  }
}

/**
 * DELETE 请求
 */
async function del(api, path, params = {}) {
  try {
    const res = await api.delete(`plugin/${PLUGIN_ID}${path}`, { params });
    return unwrap(res)
  } catch (e) {
    throw e
  }
}

const apiModule = {
  get,
  post,
  put,
  del,
};

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {toDisplayString:_toDisplayString$3,createTextVNode:_createTextVNode$3,resolveComponent:_resolveComponent$3,withCtx:_withCtx$3,createVNode:_createVNode$3,createElementVNode:_createElementVNode$3,normalizeClass:_normalizeClass$2,openBlock:_openBlock$3,createElementBlock:_createElementBlock$3,createCommentVNode:_createCommentVNode$3,renderList:_renderList$3,Fragment:_Fragment$3,createBlock:_createBlock$3,normalizeStyle:_normalizeStyle$1} = await importShared('vue');


const _hoisted_1$3 = { class: "zt-dashboard" };
const _hoisted_2$3 = { class: "d-flex align-center flex-wrap" };
const _hoisted_3$3 = { class: "mr-6" };
const _hoisted_4$3 = { class: "mr-6" };
const _hoisted_5$3 = {
  key: 0,
  class: "zt-empty pa-4"
};
const _hoisted_6$3 = { class: "zt-stat-value text-primary" };
const _hoisted_7$3 = { class: "zt-stat-value text-warning" };
const _hoisted_8$3 = { class: "zt-stat-value text-success" };
const _hoisted_9$3 = { class: "zt-stat-value text-error" };
const _hoisted_10$3 = {
  key: 0,
  class: "zt-vendor-total"
};
const _hoisted_11$3 = {
  key: 0,
  class: "zt-empty mt-2"
};
const _hoisted_12$3 = {
  key: 1,
  class: "zt-vendor-container"
};
const _hoisted_13$3 = { class: "zt-vendor-head" };
const _hoisted_14$3 = ["title"];
const _hoisted_15$3 = { class: "zt-vendor-count" };
const _hoisted_16$3 = { class: "zt-vendor-bar-bg" };
const _hoisted_17$3 = { class: "zt-vendor-percent" };
const _hoisted_18$3 = {
  key: 0,
  class: "zt-empty mt-2"
};
const _hoisted_19$3 = { class: "flex-grow-1" };
const _hoisted_20$1 = { class: "zt-dir-label" };
const _hoisted_21$1 = { class: "zt-dir-path text-body-2" };
const _hoisted_22$1 = {
  key: 0,
  class: "zt-empty"
};
const _hoisted_23$1 = { class: "zt-log-time" };
const _hoisted_24$1 = { class: "zt-log-message" };

const {computed: computed$2,onActivated: onActivated$1,onMounted: onMounted$3,onUnmounted: onUnmounted$2,ref: ref$3,watch: watch$3} = await importShared('vue');


const _sfc_main$3 = {
  __name: 'Dashboard',
  props: {
  api: { type: Object, default: () => ({}) },
  // 插件总开关（声明用于避免 attrs 落到根元素）
  enabled: { type: Boolean, default: true },
  // 数据变更信号（Page 递推）：字体库删除字体等操作后，本页重拉统计/厂商分布
  refreshKey: { type: Number, default: 0 },
},
  emits: ['notify', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

ref$3(true);
const stats = ref$3({ total: 0, pending: 0, archived: 0, error: 0, db_ok: true, last_scan: '' });
const vendors = ref$3([]);
const dirs = ref$3([]);
const logs = ref$3([]);
// 运行依赖检测：fontTools / watchdog / SQLite
const deps = ref$3({ items: [], ok_count: 0, total: 0 });
const depsDialog = ref$3(false);
const depsLoading = ref$3(false);

let refreshTimer = null;

async function loadDeps() {
  depsLoading.value = true;
  try {
    const data = await apiModule.get(props.api, '/deps/check');
    deps.value = data && data.items ? data : { items: [], ok_count: 0, total: 0 };
  } catch (e) {
    // 接口异常不打扰
  } finally {
    depsLoading.value = false;
  }
}

const depsOk = computed$2(() => deps.value.total > 0 && deps.value.ok_count === deps.value.total);

async function loadStats() {
  try {
    stats.value = await apiModule.get(props.api, '/stats');
  } catch (e) {
    emit('notify', e.message || '加载统计失败');
  }
}

async function loadVendors() {
  try {
    vendors.value = await apiModule.get(props.api, '/vendors');
  } catch (e) {
    // 忽略
  }
}

async function loadConfig() {
  try {
    const cfg = await apiModule.get(props.api, '/config');
    dirs.value = cfg.dirs || [];
  } catch (e) {
    // 忽略
  }
}

async function loadLogs() {
  try {
    logs.value = await apiModule.get(props.api, '/logs', { limit: 10 });
  } catch (e) {
    // 忽略
  }
}

onMounted$3(() => {
  loadStats();
  loadVendors();
  loadConfig();
  loadLogs();
  loadDeps();
  refreshTimer = setInterval(loadLogs, 30000);
});

// 从其他 Tab 直接切回仪表盘（keep-alive 缓存场景）时重拉统计/厂商分布/日志：
// 切 Tab 本身不会推进 refreshKey，必须有 onActivated 兜底才能拿到最新分布
onActivated$1(() => {
  loadStats();
  loadVendors();
  loadConfig();
  loadLogs();
  loadDeps();
});

onUnmounted$2(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});

// 兄弟页完成数据变更（如字体库删除字体→ Page 递推 refreshKey）：重拉统计与厂商分布
watch$3(() => props.refreshKey, () => {
  loadStats();
  loadVendors();
  loadConfig();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$3("v-icon");
  const _component_v_alert = _resolveComponent$3("v-alert");
  const _component_v_spacer = _resolveComponent$3("v-spacer");
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_card_title = _resolveComponent$3("v-card-title");
  const _component_v_chip = _resolveComponent$3("v-chip");
  const _component_v_list_item_title = _resolveComponent$3("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent$3("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$3("v-list-item");
  const _component_v_list = _resolveComponent$3("v-list");
  const _component_v_card_text = _resolveComponent$3("v-card-text");
  const _component_v_card = _resolveComponent$3("v-card");
  const _component_v_dialog = _resolveComponent$3("v-dialog");
  const _component_v_col = _resolveComponent$3("v-col");
  const _component_v_row = _resolveComponent$3("v-row");
  const _component_v_table = _resolveComponent$3("v-table");

  return (_openBlock$3(), _createElementBlock$3("div", _hoisted_1$3, [
    _createVNode$3(_component_v_alert, {
      type: !__props.enabled ? 'warning' : (stats.value.db_ok ? 'success' : 'error'),
      variant: "tonal",
      class: "mb-4 zt-status-bar",
      density: "compact"
    }, {
      default: _withCtx$3(() => [
        _createElementVNode$3("div", _hoisted_2$3, [
          _createElementVNode$3("span", _hoisted_3$3, [
            _createVNode$3(_component_v_icon, { size: 16 }, {
              default: _withCtx$3(() => [
                _createTextVNode$3(_toDisplayString$3(__props.enabled ? 'mdi-server' : 'mdi-power-off'), 1)
              ]),
              _: 1
            }),
            _cache[2] || (_cache[2] = _createTextVNode$3(" 服务状态： ", -1)),
            _createElementVNode$3("b", null, _toDisplayString$3(!__props.enabled ? '已停用' : (stats.value.db_ok ? '运行中' : '异常')), 1)
          ]),
          _createElementVNode$3("span", _hoisted_4$3, [
            _createVNode$3(_component_v_icon, { size: 16 }, {
              default: _withCtx$3(() => [...(_cache[3] || (_cache[3] = [
                _createTextVNode$3("mdi-clock-outline", -1)
              ]))]),
              _: 1
            }),
            _createTextVNode$3(" 上次全量检查：" + _toDisplayString$3(stats.value.last_scan || '从未'), 1)
          ]),
          _createElementVNode$3("span", null, [
            _createVNode$3(_component_v_icon, { size: 16 }, {
              default: _withCtx$3(() => [...(_cache[4] || (_cache[4] = [
                _createTextVNode$3("mdi-database-check", -1)
              ]))]),
              _: 1
            }),
            _cache[5] || (_cache[5] = _createTextVNode$3(" 数据库： ", -1)),
            _createElementVNode$3("b", {
              class: _normalizeClass$2(stats.value.db_ok ? 'text-success' : 'text-error')
            }, _toDisplayString$3(stats.value.db_ok ? '正常' : '错误'), 3)
          ]),
          _createElementVNode$3("span", {
            class: _normalizeClass$2(["zt-deps-tag", !depsLoading.value && !depsOk.value ? 'text-error' : 'text-success']),
            title: "点击查看依赖明细",
            onClick: _cache[0] || (_cache[0] = $event => (depsDialog.value = true))
          }, [
            _createVNode$3(_component_v_icon, { size: 16 }, {
              default: _withCtx$3(() => [
                _createTextVNode$3(_toDisplayString$3(depsLoading.value ? 'mdi-loading mdi-spin' : (depsOk.value ? 'mdi-check-circle' : 'mdi-alert-circle')), 1)
              ]),
              _: 1
            }),
            _cache[6] || (_cache[6] = _createTextVNode$3(" 依赖： ", -1)),
            _createElementVNode$3("b", null, _toDisplayString$3(depsLoading.value ? '检测中…' : (depsOk.value ? '正常' : '异常')), 1)
          ], 2)
        ])
      ]),
      _: 1
    }, 8, ["type"]),
    _createVNode$3(_component_v_dialog, {
      modelValue: depsDialog.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((depsDialog).value = $event)),
      "max-width": "440"
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card_title, { class: "zt-card-title" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$3(() => [...(_cache[7] || (_cache[7] = [
                    _createTextVNode$3("mdi-package-variant-closed", -1)
                  ]))]),
                  _: 1
                }),
                _cache[10] || (_cache[10] = _createTextVNode$3(" 运行依赖 ", -1)),
                _createVNode$3(_component_v_spacer),
                _createVNode$3(_component_v_btn, {
                  size: "small",
                  variant: "tonal",
                  loading: depsLoading.value,
                  onClick: loadDeps
                }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, {
                      start: "",
                      size: "14"
                    }, {
                      default: _withCtx$3(() => [...(_cache[8] || (_cache[8] = [
                        _createTextVNode$3("mdi-refresh", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[9] || (_cache[9] = _createTextVNode$3(" 重新检测 ", -1))
                  ]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            }),
            _createVNode$3(_component_v_card_text, { class: "pt-0" }, {
              default: _withCtx$3(() => [
                (!deps.value.value.items.length)
                  ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_5$3, "暂未检测"))
                  : (_openBlock$3(), _createBlock$3(_component_v_list, {
                      key: 1,
                      density: "compact",
                      lines: "two",
                      class: "pa-0"
                    }, {
                      default: _withCtx$3(() => [
                        (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(deps.value.value.items, (d) => {
                          return (_openBlock$3(), _createBlock$3(_component_v_list_item, {
                            key: d.key
                          }, {
                            prepend: _withCtx$3(() => [
                              _createVNode$3(_component_v_icon, {
                                color: d.ok ? 'success' : 'error',
                                size: "20"
                              }, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3(_toDisplayString$3(d.ok ? 'mdi-check-circle' : 'mdi-close-circle'), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"])
                            ]),
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_v_list_item_title, null, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3(_toDisplayString$3(d.name) + " ", 1),
                                  _createVNode$3(_component_v_chip, {
                                    color: d.ok ? 'success' : 'error',
                                    size: "x-small",
                                    variant: "tonal",
                                    class: "ml-1"
                                  }, {
                                    default: _withCtx$3(() => [
                                      _createTextVNode$3(_toDisplayString$3(d.ok ? '正常' : '未安装'), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"])
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode$3(_component_v_list_item_subtitle, null, {
                                default: _withCtx$3(() => [
                                  _createTextVNode$3(_toDisplayString$3(d.ok ? d.detail : d.detail + '（' + d.impact + '）'), 1)
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
                _cache[11] || (_cache[11] = _createElementVNode$3("div", { class: "zt-deps-hint text-body-2" }, " 依赖由 MoviePilot 安装插件时按 requirements.txt 自动安装；缺失时功能降级（见各项说明）。 ", -1))
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$3(_component_v_row, null, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_col, {
          cols: "6",
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-stat-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_text, { class: "text-center pa-4" }, {
                  default: _withCtx$3(() => [
                    _createElementVNode$3("div", _hoisted_6$3, _toDisplayString$3(stats.value.total), 1),
                    _cache[12] || (_cache[12] = _createElementVNode$3("div", { class: "zt-stat-label" }, "字体总数", -1))
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
          cols: "6",
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-stat-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_text, { class: "text-center pa-4" }, {
                  default: _withCtx$3(() => [
                    _createElementVNode$3("div", _hoisted_7$3, _toDisplayString$3(stats.value.pending), 1),
                    _cache[13] || (_cache[13] = _createElementVNode$3("div", { class: "zt-stat-label" }, "待整理", -1))
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
          cols: "6",
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-stat-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_text, { class: "text-center pa-4" }, {
                  default: _withCtx$3(() => [
                    _createElementVNode$3("div", _hoisted_8$3, _toDisplayString$3(stats.value.subset ?? stats.value.archived), 1),
                    _cache[14] || (_cache[14] = _createElementVNode$3("div", { class: "zt-stat-label" }, "最近子集化数量", -1))
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
          cols: "6",
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-stat-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_text, { class: "text-center pa-4" }, {
                  default: _withCtx$3(() => [
                    _createElementVNode$3("div", _hoisted_9$3, _toDisplayString$3(stats.value.error), 1),
                    _cache[15] || (_cache[15] = _createElementVNode$3("div", { class: "zt-stat-label" }, "缺失字体", -1))
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
    _createVNode$3(_component_v_row, { class: "mt-2" }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-mid-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$3(() => [...(_cache[16] || (_cache[16] = [
                        _createTextVNode$3("mdi-chart-bar", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[17] || (_cache[17] = _createTextVNode$3(" 厂商分布 ", -1)),
                    (vendors.value.length)
                      ? (_openBlock$3(), _createElementBlock$3("span", _hoisted_10$3, _toDisplayString$3(vendors.value.length) + " 家", 1))
                      : _createCommentVNode$3("", true)
                  ]),
                  _: 1
                }),
                _createVNode$3(_component_v_card_text, { class: "zt-scroll-body" }, {
                  default: _withCtx$3(() => [
                    (!vendors.value.length)
                      ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_11$3, "暂无数据"))
                      : (_openBlock$3(), _createElementBlock$3("div", _hoisted_12$3, [
                          (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(vendors.value, (item) => {
                            return (_openBlock$3(), _createElementBlock$3("div", {
                              key: item.vendor,
                              class: "zt-vendor-row"
                            }, [
                              _createElementVNode$3("div", _hoisted_13$3, [
                                _createElementVNode$3("span", {
                                  class: "zt-vendor-name",
                                  title: item.vendor
                                }, _toDisplayString$3(item.vendor), 9, _hoisted_14$3),
                                _createElementVNode$3("span", _hoisted_15$3, _toDisplayString$3(item.count), 1)
                              ]),
                              _createElementVNode$3("div", _hoisted_16$3, [
                                _createElementVNode$3("div", {
                                  class: "zt-vendor-bar",
                                  style: _normalizeStyle$1({ width: item.percent + '%' })
                                }, null, 4)
                              ]),
                              _createElementVNode$3("div", _hoisted_17$3, _toDisplayString$3(item.percent) + "%", 1)
                            ]))
                          }), 128))
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
        _createVNode$3(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_card, { class: "zt-card-bg zt-mid-card" }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_card_title, { class: "zt-card-title" }, {
                  default: _withCtx$3(() => [
                    _createVNode$3(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$3(() => [...(_cache[18] || (_cache[18] = [
                        _createTextVNode$3("mdi-folder-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[19] || (_cache[19] = _createTextVNode$3(" 目录健康度 ", -1))
                  ]),
                  _: 1
                }),
                _createVNode$3(_component_v_card_text, { class: "zt-scroll-body zt-dir-list" }, {
                  default: _withCtx$3(() => [
                    (!dirs.value.length)
                      ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_18$3, " 尚未在设置中配置目录 "))
                      : _createCommentVNode$3("", true),
                    (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(dirs.value, (dir) => {
                      return (_openBlock$3(), _createElementBlock$3("div", {
                        key: dir.path,
                        class: "zt-dir-item"
                      }, [
                        _createVNode$3(_component_v_icon, {
                          size: 16,
                          class: _normalizeClass$2([dir.exists ? 'text-success' : 'text-error', "mr-2"])
                        }, {
                          default: _withCtx$3(() => [
                            _createTextVNode$3(_toDisplayString$3(dir.exists ? 'mdi-check-circle' : 'mdi-alert-circle'), 1)
                          ]),
                          _: 2
                        }, 1032, ["class"]),
                        _createElementVNode$3("div", _hoisted_19$3, [
                          _createElementVNode$3("div", _hoisted_20$1, _toDisplayString$3(dir.label), 1),
                          _createElementVNode$3("div", _hoisted_21$1, _toDisplayString$3(dir.path || '(未配置)'), 1)
                        ])
                      ]))
                    }), 128))
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
    _createVNode$3(_component_v_card, { class: "zt-card-bg mt-4 zt-log-card" }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_card_title, { class: "zt-card-title" }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_icon, {
              start: "",
              size: "18"
            }, {
              default: _withCtx$3(() => [...(_cache[20] || (_cache[20] = [
                _createTextVNode$3("mdi-text-box-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[21] || (_cache[21] = _createTextVNode$3(" 最近操作日志 ", -1))
          ]),
          _: 1
        }),
        _createVNode$3(_component_v_card_text, { class: "pt-0 zt-scroll-body" }, {
          default: _withCtx$3(() => [
            (!logs.value.length)
              ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_22$1, "暂无日志"))
              : _createCommentVNode$3("", true),
            _createVNode$3(_component_v_table, { density: "compact" }, {
              default: _withCtx$3(() => [
                _createElementVNode$3("tbody", null, [
                  (_openBlock$3(true), _createElementBlock$3(_Fragment$3, null, _renderList$3(logs.value, (log) => {
                    return (_openBlock$3(), _createElementBlock$3("tr", {
                      key: log.id
                    }, [
                      _createElementVNode$3("td", _hoisted_23$1, _toDisplayString$3(log.time), 1),
                      _createElementVNode$3("td", null, [
                        _createVNode$3(_component_v_chip, {
                          size: "x-small",
                          color: log.level === 'error' ? 'error' : log.level === 'warning' ? 'warning' : 'info',
                          variant: "tonal",
                          class: "mr-2 zt-log-level"
                        }, {
                          default: _withCtx$3(() => [
                            _createTextVNode$3(_toDisplayString$3(log.level.toUpperCase()), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"]),
                        _createElementVNode$3("span", _hoisted_24$1, _toDisplayString$3(log.message), 1)
                      ])
                    ]))
                  }), 128))
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
  ]))
}
}

};
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-777d66ee"]]);

const {createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,openBlock:_openBlock$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,createElementBlock:_createElementBlock$2,renderList:_renderList$2,Fragment:_Fragment$2,normalizeStyle:_normalizeStyle,withModifiers:_withModifiers$1} = await importShared('vue');


const _hoisted_1$2 = { class: "zt-font-library" };
const _hoisted_2$2 = { class: "zt-topbar" };
const _hoisted_3$2 = { class: "zt-total text-body-2" };
const _hoisted_4$2 = { class: "pa-3 pb-2" };
const _hoisted_5$2 = { class: "zt-dir-count" };
const _hoisted_6$2 = {
  key: 0,
  class: "zt-empty pa-6"
};
const _hoisted_7$2 = {
  key: 1,
  class: "pa-4"
};
const _hoisted_8$2 = { class: "d-flex align-center mb-3" };
const _hoisted_9$2 = { class: "flex-grow-1" };
const _hoisted_10$2 = { class: "zt-detail-title zt-font-name" };
const _hoisted_11$2 = { class: "zt-detail-meta" };
const _hoisted_12$2 = { class: "zt-meta-grid mb-3" };
const _hoisted_13$2 = { class: "zt-meta-item" };
const _hoisted_14$2 = { class: "zt-meta-value" };
const _hoisted_15$2 = { class: "zt-meta-item" };
const _hoisted_16$2 = { class: "zt-meta-value" };
const _hoisted_17$2 = { class: "zt-meta-item" };
const _hoisted_18$2 = { class: "zt-meta-value" };
const _hoisted_19$2 = { class: "zt-meta-item" };
const _hoisted_20 = { class: "zt-meta-value" };
const _hoisted_21 = { class: "zt-section-label mb-2" };
const _hoisted_22 = { class: "zt-preview-sample" };
const _hoisted_23 = {
  key: 1,
  class: "zt-empty pa-4"
};
const _hoisted_24 = { class: "d-flex pa-3 flex-wrap" };
const _hoisted_25 = {
  key: 1,
  class: "zt-empty"
};
const _hoisted_26 = {
  key: 2,
  class: "zt-preview-body"
};
const _hoisted_27 = { class: "zt-preview-name mb-2" };
const _hoisted_28 = { class: "zt-preview-family mb-3" };

const {computed: computed$1,watch: watch$2,onActivated,onMounted: onMounted$2,onUnmounted: onUnmounted$1,ref: ref$2} = await importShared('vue');

const FONT_BATCH_SIZE = 200;
const PREVIEW_FONT_FAMILY = 'zt-preview-font';


const _sfc_main$2 = {
  __name: 'FontLibrary',
  props: {
  api: { type: Object, default: () => ({}) },
  // 插件总开关：停用时操作按钮置灰禁用
  enabled: { type: Boolean, default: true },
  // 数据变更信号（Page 递推）：其他页完成重新识别厂商等操作后，本页重拉最新数据
  refreshKey: { type: Number, default: 0 },
},
  emits: ['notify', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

// ===== 查询状态（本地全量，前端构建目录树） =====
const search = ref$2('');
const vendorFilter = ref$2('');
const allFonts = ref$2([]);       // 全量字体（来自 /fonts/tree）
const libDir = ref$2('');         // 字体库根目录
const loadingList = ref$2(false);
const loaded = ref$2(false);

// ===== 选中字体（右栏详情） =====
const selectedId = ref$2(null);
const selectedFont = computed$1(() => allFonts.value.find(f => f.id === selectedId.value) || null);

// ===== 「目录自动收集」开关联动 =====
// 开：监控字体自动归档进字体库，刷新时失效选中自动清理（现状）；
// 关：监控字体进「待确认」不归档，用户在整理时保留选中不被刷新打断
const autoCollect = ref$2(true);
async function refreshCollectFlag() {
  try {
    const data = await apiModule.get(props.api, '/config');
    autoCollect.value = data?.auto_collect !== false;
  } catch (e) {
    /* 拉取失败保持默认（开） */
  }
}

// ===== 目录树 =====
const expandedDirs = ref$2(new Set());
// 展开目录下的字体按需渲染：初始渲染前 FONT_BATCH_SIZE 个，滚动到底自动追加，避免上万字体一次性渲染卡死手机端
const renderedFonts = ref$2(FONT_BATCH_SIZE);
function resetRenderedFonts() {
  renderedFonts.value = FONT_BATCH_SIZE;
}
// 可见节点：目录节点永远全部渲染（保证子树可导航），字体节点受 renderedFonts 数量限制
const visibleNodes = computed$1(() => {
  let remain = renderedFonts.value;
  const out = [];
  for (const node of flatNodes.value) {
    if (node.type === 'dir') out.push(node);
    else if (remain > 0) {
      out.push(node);
      remain--;
    }
  }
  return out
});
// 左侧列表容器滚动接近底部时追加一屏字体
const listCardRef = ref$2(null);
function onListScroll() {
  const el = listCardRef.value;
  if (!el) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 120) {
    renderedFonts.value += FONT_BATCH_SIZE;
  }
}

// ===== 删除字体（记录+本地文件，二次确认） =====
const deleteDialog = ref$2(false);
const deleteTarget = ref$2(null);
const deleting = ref$2(false);

// ===== 待确认上传 =====
const pendingFonts = ref$2([]);
const loadingPending = ref$2(false);
const uploadRef = ref$2(null);
const uploading = ref$2(false);
const confirming = ref$2(false);
const discarding = ref$2(false);
// 全量检查运行中：按钮转圈禁用，结束才恢复（防重复点击）
const scanning = ref$2(false);

// ===== 数据库备份/恢复 =====
const dbImportRef = ref$2(null);
const dbBusy = ref$2(false);
const clearDialog = ref$2(false);

// ===== 预览 =====
const previewOpen = ref$2(false);
const previewLoading = ref$2(false);
const previewError = ref$2('');
const previewName = ref$2('');
const previewFamily = ref$2('');
const previewFont = ref$2(null);
const faceLoading = ref$2(false);
const faceError = ref$2('');
function disposePreviewFont() {
  if (previewFont.value && document.fonts) {
    try {
      document.fonts.delete(previewFont.value);
    } catch (e) {
      // 忽略
    }
  }
  previewFont.value = null;
}

// base64 -> ArrayBuffer（绕过 data URL 网络管线，根治 "A network error occurred"）
function base64ToArrayBuffer(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer
}

// 用 ArrayBuffer 创建并加载 FontFace，避免 data: URL 被浏览器当作网络资源
async function loadPreviewFace(data) {
  const face = new FontFace(PREVIEW_FONT_FAMILY, base64ToArrayBuffer(data));
  await face.load();
  if (document.fonts) document.fonts.add(face);
  return face
}

// 把浏览器裸错误转成用户可读的中文提示
function friendlyPreviewError(e) {
  const msg = (e && e.message) || '';
  if (/Invalid font data|Unexpected end|Not a valid|Failed to decode|Couldn't parse/i.test(msg)) {
    return '该字体文件无法解析（可能是被截断、损坏，或为 TTC 集合等浏览器不支持的格式）'
  }
  return msg || '预览失败'
}

const previewStyle = computed$1(() => {
  if (!previewFont.value) return {}
  return { fontFamily: `'${PREVIEW_FONT_FAMILY}', sans-serif` }
});

// 厂商列表（来自 vendors 接口 + 当前列表聚合）
const vendorOptions = ref$2([]);

// ===== 目录计算：file_path 相对 lib_dir 的所在目录 =====
function relDirOf(filePath) {
  if (!filePath) return ''
  let p = String(filePath).replace(/\\/g, '/');
  let base = libDir.value ? String(libDir.value).replace(/\\/g, '/').replace(/\/+$/, '') : '';
  if (base && p.startsWith(base + '/')) {
    p = p.slice(base.length + 1);
  }
  const idx = p.lastIndexOf('/');
  return idx >= 0 ? p.slice(0, idx) : ''
}

// ===== 构建扁平目录树节点 =====
const flatNodes = computed$1(() => {
  const dirMap = new Map(); // relDir -> { path, label, depth, fonts: [] }
  const getDir = (relDir) => {
    if (!relDir) {
      const key = '__root__';
      if (!dirMap.has(key)) dirMap.set(key, { key, path: '', label: '未分类', depth: 0, fonts: [] });
      return dirMap.get(key)
    }
    const segs = relDir.split('/').filter(Boolean);
    const path = segs.join('/');
    if (dirMap.has(path)) return dirMap.get(path)
    const node = {
      key: 'dir:' + path,
      path,
      label: segs[segs.length - 1],
      depth: segs.length,
      fonts: [],
    };
    dirMap.set(path, node);
    return node
  };
  // 确保父目录节点存在
  const ensureParents = (dirNode) => {
    if (!dirNode || dirNode.depth <= 0 || dirNode.path.indexOf('/') < 0) return
    const parentPath = dirNode.path.slice(0, dirNode.path.lastIndexOf('/'));
    const parent = getDir(parentPath);
    ensureParents(parent);
  };

  let list = allFonts.value;
  // 厂商过滤
  if (vendorFilter.value) {
    list = list.filter(f => f.vendor === vendorFilter.value);
  }
  // 关键字过滤：匹配时也保留目录
  const kw = (search.value || '').trim().toLowerCase();
  if (kw) {
    list = list.filter(f =>
      [f.name, f.family, f.vendor, f.designer, f.file_name].some(v => v && String(v).toLowerCase().includes(kw))
    );
  }
  for (const f of list) {
    const relDir = relDirOf(f.file_path);
    const dirNode = getDir(relDir);
    ensureParents(dirNode);
    dirNode.fonts.push(f);
  }
  // 递归统计：每个目录节点 = 自身直接字体 + 全部子目录（含嵌套）字体数，
  // 保证按格式分子文件夹后「厂商」层显示的是该厂商全部字体（如 方正/ttf/…ttf 归到方正 47）
  const dirKeys = [...dirMap.keys()].filter(k => k !== '__root__').sort((a, b) => b.split('/').length - a.split('/').length);
  for (const k of dirKeys) {
    const d = dirMap.get(k);
    d.total_fonts = d.total_fonts || d.fonts.length;
    const parentPath = k.includes('/') ? k.slice(0, k.lastIndexOf('/')) : '';
    const parent = dirMap.get(parentPath);
    if (parent) parent.total_fonts = (parent.total_fonts || parent.fonts.length) + d.total_fonts;
  }
  // 剔除空目录（关键字过滤后可能没有字体）
  const nodes = [];
  const walk = (dirNode) => {
    if (!dirNode.fonts.length && dirNode.path !== '' && ![...dirMap.values()].some(d => d.path.startsWith(dirNode.path + '/'))) {
      return false // 空目录，不输出子节点
    }
    const dirChildren = [...dirMap.values()]
      .filter(d => d.depth === dirNode.depth + 1 && (d.path.startsWith(dirNode.path + '/') || (dirNode.path === '' && d.path.indexOf('/') < 0)))
      .sort((a, b) => {
        // 厂商层（一级目录）按字体数量从多到少，数量相同按名称；格式等子层保持名称排序
        if (dirNode.depth === 0) {
          return (b.total_fonts || 0) - (a.total_fonts || 0) || (a.label < b.label ? -1 : 1)
        }
        return a.label < b.label ? -1 : 1
      });
    const hasVisible = dirNode.fonts.length > 0 || dirChildren.length > 0;
    if (hasVisible) {
      nodes.push({ key: 'dir:' + dirNode.path, type: 'dir', dir: dirNode, depth: dirNode.depth });
    }
    const isExpanded = kw ? true : expandedDirs.value.has(dirNode.path) || expandedDirs.value.has('__root__');
    if (isExpanded) {
      for (const child of dirChildren) walk(child);
      for (const f of [...dirNode.fonts].sort((a, b) => (a.id > b.id ? -1 : 1))) {
        nodes.push({ key: 'font:' + f.id, type: 'font', font: f, fontDir: dirNode, depth: dirNode.depth + 1 });
      }
    }
  };
  // 根目录下直接文件（厂商层：按字体数量从多到少，数量相同按名称）
  const rootChildren = [...dirMap.values()]
    .filter(d => d.depth === 1)
    .sort((a, b) => (b.total_fonts || 0) - (a.total_fonts || 0) || (a.label < b.label ? -1 : 1));
  const hasRoot = dirMap.has('__root__');
  const rootDir = dirMap.get('__root__');
  if (hasRoot && rootDir.fonts.length) {
    nodes.push({ key: 'dir:__root__', type: 'dir', dir: rootDir, depth: 0 });
    if (expandedDirs.value.has('__root__') || kw) {
      for (const f of [...rootDir.fonts].sort((a, b) => (a.id > b.id ? -1 : 1))) {
        nodes.push({ key: 'font:' + f.id, type: 'font', font: f, fontDir: rootDir, depth: 1 });
      }
    }
  }
  for (const child of rootChildren) walk(child);
  return nodes
});

function toggleDir(dir) {
  const set = new Set(expandedDirs.value);
  const key = dir.path || '__root__';
  if (set.has(key)) set.delete(key);
  else set.add(key);
  expandedDirs.value = set;
  resetRenderedFonts();
}

// 搜索/厂商筛选变化时重置按需渲染计数
watch$2([search, vendorFilter], () => resetRenderedFonts());

// ===== 数据加载 =====
async function loadFonts() {
  loadingList.value = true;
  try {
    const data = await apiModule.get(props.api, '/fonts/tree');
    allFonts.value = data.list || [];
    libDir.value = data.lib_dir || '';
    loaded.value = true;
    resetRenderedFonts();
    // 若当前选中字体已不存在则清除：
    // 目录自动收集开启时监控自动入库、删除后选中失效应自动清理；
    // 关闭时（监控字体在待确认、用户正在整理）保留选中，不做自动清理
    if (
      selectedId.value &&
      !allFonts.value.some(f => f.id === selectedId.value) &&
      autoCollect.value
    ) {
      selectedId.value = null;
    }
  } catch (e) {
    emit('notify', e.message || '加载字体库失败');
  } finally {
    loadingList.value = false;
  }
}

async function loadPending() {
  loadingPending.value = true;
  try {
    pendingFonts.value = await apiModule.get(props.api, '/fonts/pending');
  } catch (e) {
    emit('notify', e.message || '加载待确认列表失败');
  } finally {
    loadingPending.value = false;
  }
}

async function loadVendors() {
  try {
    vendorOptions.value = await apiModule.get(props.api, '/vendors');
  } catch (e) {
    // 忽略
  }
}

// ===== 交互（纯前端过滤，computed 自动响应） =====

// 点击左侧列表的「空白」区域取消选中（停止对焦）
function onListClick(e) {
  const el = e.target;
  if (!el || !el.closest) return
  if (el.closest('.zt-font-item, .zt-dir-item, .zt-fav-icon, .v-chip, .v-btn')) return
  selectedId.value = null;
}

// ===== 右栏详情：选中 + 加载真实字体大样 =====
async function selectFont(font) {
  if (!font) return
  selectedId.value = font.id;
  disposePreviewFont();
  previewFont.value = null;
  faceLoading.value = true;
  faceError.value = '';
  try {
    const res = await apiModule.get(props.api, '/fonts/preview', { id: font.id });
    const data = res?.data || '';
    if (!data) {
      faceError.value = '该字体文件不存在或无法读取';
      return
    }
    const face = await loadPreviewFace(data);
    previewFont.value = face;
  } catch (e) {
    faceError.value = friendlyPreviewError(e);
  } finally {
    faceLoading.value = false;
  }
}

// ===== 删除字体（❌）：记录 + 本地文件 =====
function askDelete(font) {
  deleteTarget.value = font;
  deleteDialog.value = true;
}

async function confirmDelete() {
  const font = deleteTarget.value;
  if (!font) return
  deleting.value = true;
  try {
    const res = await apiModule.del(props.api, '/fonts/delete', { id: font.id });
    emit('notify', res?.file_deleted ? '字体及本地文件已删除' : '字体记录已删除', 'success');
    allFonts.value = allFonts.value.filter(f => f.id !== font.id);
    if (selectedId.value === font.id) selectedId.value = null;
    loadPending();
    // 通知 Page 递推 refreshKey：仪表盘统计/厂商分布同步刷新
    emit('action', { type: 'font_deleted' });
  } catch (e) {
    emit('notify', e.message || '删除失败');
  } finally {
    deleting.value = false;
    deleteDialog.value = false;
    deleteTarget.value = null;
  }
}

async function toggleFavorite(font) {
  try {
    await apiModule.post(props.api, '/fonts/toggle_favorite', { id: font.id });
    font.favorite = font.favorite ? 0 : 1;
  } catch (e) {
    emit('notify', e.message || '收藏操作失败');
  }
}

async function handleUpload(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），改为分批顺序上传，每批 3 个
  const BATCH = 3;
  let total = 0;
  uploading.value = true;
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const form = new FormData();
      for (const file of chunk) form.append('file', file);
      const res = await props.api.post(
        `plugin/Zitifenlei/fonts/upload_preview`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      const body = res?.data ?? res;
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '上传失败'}`);
        break
      } else {
        const item = body?.data ?? body;
        total += (item?.count ?? chunk.length);
      }
    }
    emit('notify', `已加入待确认列表 ${total} 个字体`, 'success');
    loadPending();
  } catch (e) {
    emit('notify', e.message || '上传失败');
  } finally {
    uploading.value = false;
  }
}

async function confirmUpload() {
  if (!pendingFonts.value.length) {
    emit('notify', '没有待确认的字体', 'warning');
    return
  }
  confirming.value = true;
  try {
    const res = await apiModule.post(props.api, '/fonts/confirm_upload');
    const done = res?.processed ?? pendingFonts.value.length;
    emit('notify', `已归档 ${done} 个字体`, 'success');
    pendingFonts.value = [];
    loadFonts();
    loadPending();
    emit('action', { type: 'fonts_archived' });
  } catch (e) {
    emit('notify', e.message || '整理失败');
  } finally {
    confirming.value = false;
  }
}

async function discardUpload() {
  if (!pendingFonts.value.length) return
  discarding.value = true;
  try {
    await apiModule.post(props.api, '/fonts/discard_upload');
    emit('notify', '已全部丢弃', 'success');
    pendingFonts.value = [];
  } catch (e) {
    emit('notify', e.message || '丢弃失败');
  } finally {
    discarding.value = false;
  }
}

async function deletePending(id) {
  try {
    await apiModule.post(props.api, `/fonts/pending_delete/${id}`);
    pendingFonts.value = pendingFonts.value.filter(p => p.id !== id);
    if (!pendingFonts.value.length) {
      loadFonts();
    }
  } catch (e) {
    emit('notify', e.message || '删除失败');
  }
}

async function scanArchive() {
  if (scanning.value) return
  scanning.value = true;
  try {
    const res = await apiModule.post(props.api, '/fonts/scan');
    const n = res?.added ?? 0;
    if (n) {
      // 「目录自动收集」开启 → 直接入库；关闭 → 加入待确认
      emit('notify', autoCollect.value ? `全量检查完成，已归档 ${n} 个字体` : `全量检查完成，新增 ${n} 个待确认字体`, 'success');
      if (autoCollect.value) {
        loadFonts();
        loadVendors();
        emit('action', { type: 'fonts_archived' });
      }
    } else {
      emit('notify', '全量检查完成，无新增字体（已入库或已在待确认）', 'info');
    }
    loadPending();
  } catch (e) {
    emit('notify', e.message || '全量检查失败');
  } finally {
    scanning.value = false;
  }
}

// ===== 数据库备份 / 恢复 / 清空 =====
async function exportDatabase() {
  dbBusy.value = true;
  try {
    const data = await apiModule.get(props.api, '/db/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    a.download = `字体库备份_${ts}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    emit('notify', '数据库备份已导出', 'success');
  } catch (e) {
    emit('notify', e.message || '导出数据库失败');
  } finally {
    dbBusy.value = false;
  }
}

async function handleDbImport(event) {
  const file = event.target.files?.[0];
  if (!file) return
  dbBusy.value = true;
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    await apiModule.post(props.api, '/db/import', payload);
    emit('notify', '数据库已恢复，列表已刷新', 'success');
    await loadFonts();
    await loadPending();
    loadVendors();
  } catch (e) {
    emit('notify', e.message.includes('Unexpected token') ? '导入失败：备份文件格式不正确' : (e.message || '导入数据库失败'));
  } finally {
    dbBusy.value = false;
    event.target.value = '';
  }
}

async function clearDatabase() {
  clearDialog.value = false;
  dbBusy.value = true;
  try {
    await apiModule.del(props.api, '/db/clear');
    emit('notify', '数据库已清空', 'success');
    selectedId.value = null;
    allFonts.value = [];
    await loadFonts();
    await loadPending();
    emit('action', { type: 'db_cleared' });
  } catch (e) {
    emit('notify', e.message || '清空数据库失败');
  } finally {
    dbBusy.value = false;
  }
}

// ===== 预览对话框（放大） =====
async function openPreview(font) {
  disposePreviewFont();
  previewOpen.value = true;
  previewLoading.value = true;
  previewError.value = '';
  previewName.value = font.name || '';
  previewFamily.value = font.family || '';
  try {
    const res = await apiModule.get(props.api, '/fonts/preview', { id: font.id });
    previewName.value = res?.name || font.name || '';
    previewFamily.value = res?.family || font.family || '';
    const data = res?.data || '';
    if (!data) {
      previewError.value = '该字体文件不存在或无法读取';
      return
    }
    const face = await loadPreviewFace(data);
    previewFont.value = face;
  } catch (e) {
    previewError.value = friendlyPreviewError(e);
  } finally {
    previewLoading.value = false;
  }
}

// 统一数据刷新：全量拉目录树 + 待确认 + 厂商分布（保持选中/展开状态，不重置界面）
function refreshData() {
  loadFonts();
  loadPending();
  loadVendors();
}

// 30 秒轮询兜底：目录监控/入库自动归档写入新字体后，页面停留不动也能自动显示
let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(refreshData, 30000);
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted$2(async () => {
  refreshCollectFlag();
  await loadFonts();
  loadPending();
  loadVendors();
  startPolling();
});

// 宿主详情页以 keep-alive 缓存子视图：每次进入字体库页时重新拉取，
// 确保「重新识别厂商」等操作在其他页完成后，左侧列表/厂商带到最新数据
onActivated(async () => {
  refreshCollectFlag();
  await loadFonts();
  loadPending();
  loadVendors();
});

// 兄弟页完成数据变更（如仪表盘「重新识别厂商」→ Page 递推 refreshKey）：
// 即使本页处于 keep-alive 缓存、未切换 Tab，也立即重拉，杜绝旧数据残留
watch$2(() => props.refreshKey, () => {
  refreshData();
});

onUnmounted$1(() => {
  stopPolling();
  disposePreviewFont();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_spacer = _resolveComponent$2("v-spacer");
  const _component_v_text_field = _resolveComponent$2("v-text-field");
  const _component_v_select = _resolveComponent$2("v-select");
  const _component_v_divider = _resolveComponent$2("v-divider");
  const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$2("v-list-item-title");
  const _component_v_list_item = _resolveComponent$2("v-list-item");
  const _component_v_chip = _resolveComponent$2("v-chip");
  const _component_v_list_item_subtitle = _resolveComponent$2("v-list-item-subtitle");
  const _component_v_list = _resolveComponent$2("v-list");
  const _component_v_card_text = _resolveComponent$2("v-card-text");
  const _component_v_card = _resolveComponent$2("v-card");
  const _component_v_col = _resolveComponent$2("v-col");
  const _component_v_progress_circular = _resolveComponent$2("v-progress-circular");
  const _component_v_row = _resolveComponent$2("v-row");
  const _component_v_card_title = _resolveComponent$2("v-card-title");
  const _component_v_card_actions = _resolveComponent$2("v-card-actions");
  const _component_v_dialog = _resolveComponent$2("v-dialog");

  return (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
    _createElementVNode$2("div", _hoisted_2$2, [
      _createVNode$2(_component_v_btn, {
        variant: "tonal",
        color: "primary",
        disabled: !__props.enabled,
        loading: uploading.value,
        onClick: _cache[0] || (_cache[0] = $event => (uploadRef.value?.click()))
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[13] || (_cache[13] = [
              _createTextVNode$2("mdi-upload", -1)
            ]))]),
            _: 1
          }),
          _cache[14] || (_cache[14] = _createTextVNode$2(" 上传字体 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createElementVNode$2("input", {
        ref_key: "uploadRef",
        ref: uploadRef,
        type: "file",
        accept: ".ttf,.otf,.TTF,.OTF",
        multiple: "",
        style: {"display":"none"},
        onChange: handleUpload
      }, null, 544),
      _createVNode$2(_component_v_btn, {
        variant: "tonal",
        disabled: !__props.enabled || scanning.value,
        loading: scanning.value,
        title: "全量检查：扫描字体监控目录中的字体（目录自动收集开启时直接入库，关闭时加入待确认区；运行中不可重复点击）",
        onClick: scanArchive
      }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$2(() => [...(_cache[15] || (_cache[15] = [
              _createTextVNode$2("mdi-magnify-scan", -1)
            ]))]),
            _: 1
          }),
          _cache[16] || (_cache[16] = _createTextVNode$2(" 全量检查 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createVNode$2(_component_v_spacer),
      _createElementVNode$2("span", _hoisted_3$2, "共 " + _toDisplayString$2(allFonts.value.length) + " 个字体", 1)
    ]),
    _createVNode$2(_component_v_row, {
      "no-gutters": "",
      class: "zt-font-row"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_col, {
          cols: "12",
          md: "5"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, {
              class: "zt-card-bg zt-list-card",
              ref_key: "listCardRef",
              ref: listCardRef,
              onScroll: onListScroll
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_text, { class: "pa-0" }, {
                  default: _withCtx$2(() => [
                    _createElementVNode$2("div", _hoisted_4$2, [
                      _createVNode$2(_component_v_text_field, {
                        modelValue: search.value,
                        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((search).value = $event)),
                        placeholder: "搜索字体名称、厂商、设计师...",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        clearable: "",
                        "prepend-inner-icon": "mdi-magnify"
                      }, null, 8, ["modelValue"]),
                      _createVNode$2(_component_v_select, {
                        modelValue: vendorFilter.value,
                        "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((vendorFilter).value = $event)),
                        items: vendorOptions.value,
                        "item-title": "vendor",
                        "item-value": "vendor",
                        label: "厂商筛选",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        clearable: "",
                        class: "mt-2"
                      }, null, 8, ["modelValue", "items"])
                    ]),
                    _createVNode$2(_component_v_divider),
                    (loadingList.value)
                      ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
                          key: 0,
                          indeterminate: "",
                          color: "primary"
                        }))
                      : _createCommentVNode$2("", true),
                    (!loadingList.value && loaded.value && !flatNodes.value.length)
                      ? (_openBlock$2(), _createElementBlock$2("div", {
                          key: 1,
                          class: "zt-empty pa-6",
                          onClick: _cache[3] || (_cache[3] = $event => (selectedId.value = null))
                        }, " 暂无字体，点击「上传字体」或「全量检查」添加 "))
                      : (_openBlock$2(), _createElementBlock$2("div", {
                          key: 2,
                          class: "zt-list-body",
                          onClick: onListClick
                        }, [
                          _createVNode$2(_component_v_list, {
                            density: "compact",
                            class: "pa-0",
                            nav: ""
                          }, {
                            default: _withCtx$2(() => [
                              (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(visibleNodes.value, (node) => {
                                return (_openBlock$2(), _createElementBlock$2(_Fragment$2, {
                                  key: node.key
                                }, [
                                  (node.type === 'dir')
                                    ? (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                                        key: 0,
                                        class: "zt-dir-item",
                                        style: _normalizeStyle({ paddingLeft: (node.depth * 10) + 'px' }),
                                        onClick: $event => (toggleDir(node.dir))
                                      }, {
                                        prepend: _withCtx$2(() => [
                                          _createVNode$2(_component_v_icon, {
                                            size: "18",
                                            class: "mr-1"
                                          }, {
                                            default: _withCtx$2(() => [
                                              _createTextVNode$2(_toDisplayString$2(expandedDirs.value.has(node.dir.path || '__root__') ? 'mdi-chevron-down' : 'mdi-chevron-right'), 1)
                                            ]),
                                            _: 2
                                          }, 1024),
                                          _createVNode$2(_component_v_icon, {
                                            size: "16",
                                            color: "info",
                                            class: "mr-1"
                                          }, {
                                            default: _withCtx$2(() => [
                                              _createTextVNode$2(_toDisplayString$2(expandedDirs.value.has(node.dir.path || '__root__') ? 'mdi-folder-open' : 'mdi-folder'), 1)
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ]),
                                        append: _withCtx$2(() => [
                                          _createElementVNode$2("span", _hoisted_5$2, _toDisplayString$2(node.dir.total_fonts ?? node.dir.fonts.length), 1)
                                        ]),
                                        default: _withCtx$2(() => [
                                          _createVNode$2(_component_v_list_item_title, { class: "zt-dir-name" }, {
                                            default: _withCtx$2(() => [
                                              _createTextVNode$2(_toDisplayString$2(node.dir.label), 1)
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ]),
                                        _: 2
                                      }, 1032, ["style", "onClick"]))
                                    : (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                                        key: 1,
                                        active: selectedId.value === node.font.id,
                                        class: "zt-font-item",
                                        style: _normalizeStyle({ paddingLeft: (node.depth * 6 + (node.fontDir.path ? 10 : 30)) + 'px' }),
                                        onClick: $event => (selectFont(node.font))
                                      }, {
                                        append: _withCtx$2(() => [
                                          _createVNode$2(_component_v_btn, {
                                            size: "x-small",
                                            variant: "text",
                                            icon: "",
                                            class: "zt-fav-icon",
                                            disabled: !__props.enabled,
                                            title: "删除字体（含本地文件）",
                                            onClick: _withModifiers$1($event => (askDelete(node.font)), ["stop"])
                                          }, {
                                            default: _withCtx$2(() => [
                                              _createVNode$2(_component_v_icon, {
                                                size: "16",
                                                color: "error"
                                              }, {
                                                default: _withCtx$2(() => [...(_cache[17] || (_cache[17] = [
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
                                              _createTextVNode$2(_toDisplayString$2(node.font.name || node.font.family || node.font.file_name), 1)
                                            ]),
                                            _: 2
                                          }, 1024),
                                          _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                                            default: _withCtx$2(() => [
                                              _createTextVNode$2(_toDisplayString$2(node.font.vendor || '未知厂商') + " ", 1),
                                              _createVNode$2(_component_v_chip, {
                                                color: node.font.source === 'manual' ? 'primary' : 'success',
                                                size: "x-small",
                                                variant: "tonal",
                                                class: "ml-1"
                                              }, {
                                                default: _withCtx$2(() => [
                                                  _createTextVNode$2(_toDisplayString$2(node.font.source === 'manual' ? '手动' : '自动'), 1)
                                                ]),
                                                _: 2
                                              }, 1032, ["color"])
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ]),
                                        _: 2
                                      }, 1032, ["active", "style", "onClick"]))
                                ], 64))
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
            }, 512)
          ]),
          _: 1
        }),
        _createVNode$2(_component_v_col, {
          cols: "12",
          md: "7"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, { class: "zt-card-bg zt-detail-card" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_text, { class: "pa-0" }, {
                  default: _withCtx$2(() => [
                    (!selectedFont.value)
                      ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_6$2, " 点击左侧字体查看详情与预览 "))
                      : (_openBlock$2(), _createElementBlock$2("div", _hoisted_7$2, [
                          _createElementVNode$2("div", _hoisted_8$2, [
                            _createElementVNode$2("div", _hoisted_9$2, [
                              _createElementVNode$2("div", _hoisted_10$2, _toDisplayString$2(selectedFont.value.name || selectedFont.value.family || selectedFont.value.file_name), 1),
                              _createElementVNode$2("div", _hoisted_11$2, [
                                _createTextVNode$2(_toDisplayString$2(selectedFont.value.family || '未知字族') + " ", 1),
                                _createVNode$2(_component_v_chip, {
                                  color: selectedFont.value.source === 'manual' ? 'primary' : 'success',
                                  size: "x-small",
                                  variant: "tonal",
                                  class: "ml-2"
                                }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(selectedFont.value.source === 'manual' ? '手动' : '自动'), 1)
                                  ]),
                                  _: 1
                                }, 8, ["color"]),
                                (selectedFont.value.status === '待整理')
                                  ? (_openBlock$2(), _createBlock$2(_component_v_chip, {
                                      key: 0,
                                      size: "x-small",
                                      variant: "tonal",
                                      class: "ml-1"
                                    }, {
                                      default: _withCtx$2(() => [
                                        _createVNode$2(_component_v_icon, {
                                          size: "14",
                                          class: "mr-1"
                                        }, {
                                          default: _withCtx$2(() => [...(_cache[18] || (_cache[18] = [
                                            _createTextVNode$2("mdi-clock-outline", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _cache[19] || (_cache[19] = _createTextVNode$2("待整理 ", -1))
                                      ]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$2("", true)
                              ])
                            ]),
                            _createVNode$2(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              color: selectedFont.value.favorite ? 'warning' : '',
                              class: "mr-2",
                              disabled: !__props.enabled,
                              onClick: _cache[4] || (_cache[4] = $event => (toggleFavorite(selectedFont.value)))
                            }, {
                              default: _withCtx$2(() => [
                                _createVNode$2(_component_v_icon, { size: "16" }, {
                                  default: _withCtx$2(() => [
                                    _createTextVNode$2(_toDisplayString$2(selectedFont.value.favorite ? 'mdi-star' : 'mdi-star-outline'), 1)
                                  ]),
                                  _: 1
                                }),
                                _cache[20] || (_cache[20] = _createTextVNode$2(" 收藏 ", -1))
                              ]),
                              _: 1
                            }, 8, ["color", "disabled"]),
                            _createVNode$2(_component_v_btn, {
                              size: "small",
                              variant: "tonal",
                              onClick: _cache[5] || (_cache[5] = $event => (openPreview(selectedFont.value)))
                            }, {
                              default: _withCtx$2(() => [
                                _createVNode$2(_component_v_icon, { size: "16" }, {
                                  default: _withCtx$2(() => [...(_cache[21] || (_cache[21] = [
                                    _createTextVNode$2("mdi-arrow-expand", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _cache[22] || (_cache[22] = _createTextVNode$2(" 放大 ", -1))
                              ]),
                              _: 1
                            })
                          ]),
                          _createVNode$2(_component_v_divider, { class: "mb-3" }),
                          _createElementVNode$2("div", _hoisted_12$2, [
                            _createElementVNode$2("div", _hoisted_13$2, [
                              _cache[23] || (_cache[23] = _createElementVNode$2("div", { class: "zt-meta-label" }, "厂商", -1)),
                              _createElementVNode$2("div", _hoisted_14$2, _toDisplayString$2(selectedFont.value.vendor || '未知厂商'), 1)
                            ]),
                            _createElementVNode$2("div", _hoisted_15$2, [
                              _cache[24] || (_cache[24] = _createElementVNode$2("div", { class: "zt-meta-label" }, "设计师", -1)),
                              _createElementVNode$2("div", _hoisted_16$2, _toDisplayString$2(selectedFont.value.designer || '未知设计师'), 1)
                            ]),
                            _createElementVNode$2("div", _hoisted_17$2, [
                              _cache[25] || (_cache[25] = _createElementVNode$2("div", { class: "zt-meta-label" }, "文件名", -1)),
                              _createElementVNode$2("div", _hoisted_18$2, _toDisplayString$2(selectedFont.value.file_name), 1)
                            ]),
                            _createElementVNode$2("div", _hoisted_19$2, [
                              _cache[26] || (_cache[26] = _createElementVNode$2("div", { class: "zt-meta-label" }, "大小", -1)),
                              _createElementVNode$2("div", _hoisted_20, _toDisplayString$2(selectedFont.value.file_size ? (selectedFont.value.file_size / 1024).toFixed(0) + ' KB' : '-'), 1)
                            ])
                          ]),
                          _createElementVNode$2("div", _hoisted_21, [
                            _createVNode$2(_component_v_icon, {
                              start: "",
                              size: "16"
                            }, {
                              default: _withCtx$2(() => [...(_cache[27] || (_cache[27] = [
                                _createTextVNode$2("mdi-format-font", -1)
                              ]))]),
                              _: 1
                            }),
                            _cache[28] || (_cache[28] = _createTextVNode$2(" 字体预览 ", -1))
                          ]),
                          _createElementVNode$2("div", _hoisted_22, [
                            (faceLoading.value)
                              ? (_openBlock$2(), _createBlock$2(_component_v_progress_circular, {
                                  key: 0,
                                  indeterminate: "",
                                  size: "28",
                                  class: "ma-4"
                                }))
                              : (faceError.value)
                                ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_23, _toDisplayString$2(faceError.value), 1))
                                : (_openBlock$2(), _createElementBlock$2("div", {
                                    key: 2,
                                    style: _normalizeStyle(previewStyle.value)
                                  }, [...(_cache[29] || (_cache[29] = [
                                    _createElementVNode$2("div", { style: {"font-size":"42px","font-weight":"700"} }, "观沧海", -1),
                                    _createElementVNode$2("div", { style: {"font-size":"16px","margin-top":"8px"} }, " ABCDEFGHIJKLM · abcdefghijklm · 0123456789 ", -1)
                                  ]))], 4))
                          ])
                        ]))
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
    (pendingFonts.value.length)
      ? (_openBlock$2(), _createBlock$2(_component_v_card, {
          key: 0,
          class: "zt-card-bg mt-4 zt-pending"
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18",
                  color: "warning"
                }, {
                  default: _withCtx$2(() => [...(_cache[30] || (_cache[30] = [
                    _createTextVNode$2("mdi-alert-circle-outline", -1)
                  ]))]),
                  _: 1
                }),
                _createTextVNode$2(" 待确认上传（" + _toDisplayString$2(pendingFonts.value.length) + "） ", 1)
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_text, { class: "pa-0" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_list, {
                  lines: "one",
                  density: "compact",
                  class: "pa-0"
                }, {
                  default: _withCtx$2(() => [
                    (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(pendingFonts.value, (p) => {
                      return (_openBlock$2(), _createBlock$2(_component_v_list_item, {
                        key: p.id
                      }, {
                        prepend: _withCtx$2(() => [
                          _createVNode$2(_component_v_icon, {
                            color: "warning",
                            size: "18"
                          }, {
                            default: _withCtx$2(() => [...(_cache[31] || (_cache[31] = [
                              _createTextVNode$2("mdi-alert", -1)
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
                            title: "删除该项",
                            onClick: $event => (deletePending(p.id))
                          }, {
                            default: _withCtx$2(() => [
                              _createVNode$2(_component_v_icon, { size: "16" }, {
                                default: _withCtx$2(() => [...(_cache[32] || (_cache[32] = [
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
                              _createTextVNode$2(_toDisplayString$2(p.name || p.file_name), 1)
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$2(_component_v_list_item_subtitle, { class: "zt-font-meta" }, {
                            default: _withCtx$2(() => [
                              _createTextVNode$2(_toDisplayString$2(p.vendor || '未知厂商') + " · " + _toDisplayString$2(p.file_size ? (p.file_size / 1024).toFixed(0) + 'KB' : ''), 1)
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
                _createElementVNode$2("div", _hoisted_24, [
                  _createVNode$2(_component_v_btn, {
                    color: "success",
                    variant: "tonal",
                    class: "mr-2",
                    disabled: !__props.enabled,
                    loading: confirming.value,
                    onClick: confirmUpload
                  }, {
                    default: _withCtx$2(() => [
                      _createVNode$2(_component_v_icon, {
                        start: "",
                        size: "18"
                      }, {
                        default: _withCtx$2(() => [...(_cache[33] || (_cache[33] = [
                          _createTextVNode$2("mdi-check-all", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[34] || (_cache[34] = _createTextVNode$2(" 一键整理 ", -1))
                    ]),
                    _: 1
                  }, 8, ["disabled", "loading"]),
                  _createVNode$2(_component_v_btn, {
                    color: "error",
                    variant: "tonal",
                    disabled: !__props.enabled,
                    loading: discarding.value,
                    onClick: discardUpload
                  }, {
                    default: _withCtx$2(() => [
                      _createVNode$2(_component_v_icon, {
                        start: "",
                        size: "18"
                      }, {
                        default: _withCtx$2(() => [...(_cache[35] || (_cache[35] = [
                          _createTextVNode$2("mdi-trash-can-outline", -1)
                        ]))]),
                        _: 1
                      }),
                      _cache[36] || (_cache[36] = _createTextVNode$2(" 全部丢弃 ", -1))
                    ]),
                    _: 1
                  }, 8, ["disabled", "loading"])
                ])
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
      : _createCommentVNode$2("", true),
    _createVNode$2(_component_v_card, { class: "zt-card-bg mt-4 zt-db-block" }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_icon, {
              start: "",
              size: "18"
            }, {
              default: _withCtx$2(() => [...(_cache[37] || (_cache[37] = [
                _createTextVNode$2("mdi-database-cog-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[38] || (_cache[38] = _createTextVNode$2(" 数据库管理 ", -1))
          ]),
          _: 1
        }),
        _createVNode$2(_component_v_card_text, { class: "d-flex align-center flex-wrap pa-3" }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_btn, {
              variant: "tonal",
              color: "primary",
              size: "small",
              class: "mr-2 mb-2",
              disabled: !__props.enabled,
              loading: dbBusy.value,
              onClick: exportDatabase
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$2(() => [...(_cache[39] || (_cache[39] = [
                    _createTextVNode$2("mdi-database-export-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[40] || (_cache[40] = _createTextVNode$2(" 导出数据库 ", -1))
              ]),
              _: 1
            }, 8, ["disabled", "loading"]),
            _createVNode$2(_component_v_btn, {
              variant: "tonal",
              size: "small",
              class: "mr-2 mb-2",
              disabled: !__props.enabled,
              loading: dbBusy.value,
              onClick: _cache[6] || (_cache[6] = $event => (dbImportRef.value?.click()))
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$2(() => [...(_cache[41] || (_cache[41] = [
                    _createTextVNode$2("mdi-database-import-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[42] || (_cache[42] = _createTextVNode$2(" 导入数据库 ", -1))
              ]),
              _: 1
            }, 8, ["disabled", "loading"]),
            _createElementVNode$2("input", {
              ref_key: "dbImportRef",
              ref: dbImportRef,
              type: "file",
              accept: ".json,application/json",
              style: {"display":"none"},
              onChange: handleDbImport
            }, null, 544),
            _createVNode$2(_component_v_btn, {
              variant: "tonal",
              color: "error",
              size: "small",
              class: "mb-2",
              disabled: !__props.enabled,
              onClick: _cache[7] || (_cache[7] = $event => (clearDialog.value = true))
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18"
                }, {
                  default: _withCtx$2(() => [...(_cache[43] || (_cache[43] = [
                    _createTextVNode$2("mdi-database-remove-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[44] || (_cache[44] = _createTextVNode$2(" 清空数据库 ", -1))
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$2(_component_v_dialog, {
      modelValue: deleteDialog.value,
      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((deleteDialog).value = $event)),
      "max-width": "420"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18",
                  color: "error"
                }, {
                  default: _withCtx$2(() => [...(_cache[45] || (_cache[45] = [
                    _createTextVNode$2("mdi-alert-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[46] || (_cache[46] = _createTextVNode$2(" 删除字体 ", -1))
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_text, null, {
              default: _withCtx$2(() => [
                _createTextVNode$2(" 将删除字体「" + _toDisplayString$2(deleteTarget.value?.name || deleteTarget.value?.file_name) + "」的数据库记录， 并", 1),
                _cache[47] || (_cache[47] = _createElementVNode$2("strong", null, "同时删除本地字体文件", -1)),
                _cache[48] || (_cache[48] = _createTextVNode$2("。此操作不可恢复，是否继续？ ", -1))
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_actions, null, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_spacer),
                _createVNode$2(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[8] || (_cache[8] = $event => (deleteDialog.value = false))
                }, {
                  default: _withCtx$2(() => [...(_cache[49] || (_cache[49] = [
                    _createTextVNode$2("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$2(_component_v_btn, {
                  color: "error",
                  variant: "tonal",
                  loading: deleting.value,
                  onClick: confirmDelete
                }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$2(() => [...(_cache[50] || (_cache[50] = [
                        _createTextVNode$2("mdi-delete-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[51] || (_cache[51] = _createTextVNode$2(" 确认删除 ", -1))
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
    _createVNode$2(_component_v_dialog, {
      modelValue: clearDialog.value,
      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((clearDialog).value = $event)),
      "max-width": "420"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card_title, { class: "zt-card-title" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_icon, {
                  start: "",
                  size: "18",
                  color: "error"
                }, {
                  default: _withCtx$2(() => [...(_cache[52] || (_cache[52] = [
                    _createTextVNode$2("mdi-alert-outline", -1)
                  ]))]),
                  _: 1
                }),
                _cache[53] || (_cache[53] = _createTextVNode$2(" 清空数据库 ", -1))
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_text, null, {
              default: _withCtx$2(() => [...(_cache[54] || (_cache[54] = [
                _createTextVNode$2(" 将删除所有字体、待确认与 ASS 检查记录。此操作不可恢复，建议先「导出数据库」备份。 是否继续？ ", -1)
              ]))]),
              _: 1
            }),
            _createVNode$2(_component_v_card_actions, null, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_spacer),
                _createVNode$2(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[10] || (_cache[10] = $event => (clearDialog.value = false))
                }, {
                  default: _withCtx$2(() => [...(_cache[55] || (_cache[55] = [
                    _createTextVNode$2("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode$2(_component_v_btn, {
                  color: "error",
                  variant: "tonal",
                  loading: dbBusy.value,
                  onClick: clearDatabase
                }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_icon, {
                      start: "",
                      size: "18"
                    }, {
                      default: _withCtx$2(() => [...(_cache[56] || (_cache[56] = [
                        _createTextVNode$2("mdi-database-remove-outline", -1)
                      ]))]),
                      _: 1
                    }),
                    _cache[57] || (_cache[57] = _createTextVNode$2(" 确定清空 ", -1))
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
    _createVNode$2(_component_v_dialog, {
      modelValue: previewOpen.value,
      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((previewOpen).value = $event)),
      "max-width": "420"
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
                  default: _withCtx$2(() => [...(_cache[58] || (_cache[58] = [
                    _createTextVNode$2("mdi-format-font", -1)
                  ]))]),
                  _: 1
                }),
                _cache[59] || (_cache[59] = _createTextVNode$2(" 字体预览 ", -1))
              ]),
              _: 1
            }),
            _createVNode$2(_component_v_card_text, null, {
              default: _withCtx$2(() => [
                (previewLoading.value)
                  ? (_openBlock$2(), _createBlock$2(_component_v_progress_circular, {
                      key: 0,
                      indeterminate: "",
                      class: "zt-preview-loading"
                    }))
                  : (previewError.value)
                    ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_25, _toDisplayString$2(previewError.value), 1))
                    : (_openBlock$2(), _createElementBlock$2("div", _hoisted_26, [
                        _createElementVNode$2("div", _hoisted_27, _toDisplayString$2(previewName.value), 1),
                        _createElementVNode$2("div", _hoisted_28, _toDisplayString$2(previewFamily.value), 1),
                        _createElementVNode$2("div", {
                          class: "zt-preview-sample",
                          style: _normalizeStyle(previewStyle.value)
                        }, [...(_cache[60] || (_cache[60] = [
                          _createElementVNode$2("span", { style: {"font-size":"42px","font-weight":"700"} }, "观沧海", -1),
                          _createElementVNode$2("span", { style: {"font-size":"16px","display":"block","margin-top":"8px"} }, " ABCDEFGHIJKLM abcdefghijklm 0123456789 ", -1)
                        ]))], 4)
                      ]))
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
const FontLibrary = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-77535287"]]);

const {createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,toDisplayString:_toDisplayString$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1,createBlock:_createBlock$1,renderList:_renderList$1,Fragment:_Fragment$1,withModifiers:_withModifiers,normalizeClass:_normalizeClass$1} = await importShared('vue');


const _hoisted_1$1 = { class: "zt-check" };
const _hoisted_2$1 = { class: "d-flex align-center flex-wrap mb-4" };
const _hoisted_3$1 = { class: "text-body-2 zt-total" };
const _hoisted_4$1 = {
  key: 0,
  class: "zt-match-source mb-2"
};
const _hoisted_5$1 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_6$1 = {
  key: 3,
  class: "zt-clear-row pa-3 d-flex justify-end"
};
const _hoisted_7$1 = {
  key: 1,
  class: "zt-empty pa-6"
};
const _hoisted_8$1 = {
  key: 2,
  class: "pa-4"
};
const _hoisted_9$1 = { class: "d-flex align-center mb-3 flex-wrap" };
const _hoisted_10$1 = { class: "flex-grow-1" };
const _hoisted_11$1 = { class: "zt-detail-title text-subtitle-1" };
const _hoisted_12$1 = { class: "zt-detail-meta text-body-2" };
const _hoisted_13$1 = {
  key: 0,
  class: "mb-4 zt-inline-ok"
};
const _hoisted_14$1 = { class: "mb-2" };
const _hoisted_15$1 = { class: "zt-section-label" };
const _hoisted_16$1 = { class: "zt-missing-list mb-4" };
const _hoisted_17$1 = {
  key: 0,
  class: "zt-empty2"
};
const _hoisted_18$1 = { class: "zt-section-label" };
const _hoisted_19$1 = { class: "zt-all-list" };

const {computed,onMounted: onMounted$1,onUnmounted,ref: ref$1,watch: watch$1} = await importShared('vue');

const limit = 20;

const _sfc_main$1 = {
  __name: 'Check',
  props: {
  api: { type: Object, default: () => ({}) },
  // 插件总开关：停用时操作按钮置灰禁用
  enabled: { type: Boolean, default: true },
  // 数据变更信号（Page 递推）：字体库删除/新增字体后，本页缺失标记/缺失窗口实时刷新
  refreshKey: { type: Number, default: 0 },
},
  emits: ['notify', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const records = ref$1([]);
const total = ref$1(0);
const page = ref$1(1);
const search = ref$1('');
const loadingList = ref$1(false);
const reachedEnd = ref$1(false);

const selectedId = ref$1(null);
const detail = ref$1(null);
const detailLoading = ref$1(false);
const detailOpen = ref$1(false);

const uploadRef = ref$1(null);
const uploading = ref$1(false);
const deletingId = ref$1(null);
const clearing = ref$1(false);
const checkingId = ref$1(null);
// 全量扫描（字体监控目录字体直接入库）
const scanning = ref$1(false);

computed(() =>
  records.value.find(r => r.id === selectedId.value) || null
);

// 检查「匹配基准」：index=assfonts 子集索引（与子集化同一口径，多键匹配更准）；
// db=字体库记录（索引未构建/不可用时的回退口径，可能误报缺失）
// 由 /ass/list 响应顶层 match_source 决定（列表为空时也显示）
const matchSource = ref$1('');
const matchSourceText = computed(() => {
  const s = matchSource.value || records.value[0]?.match_source || '';
  if (s === 'index') return '子集索引（assfonts fonts.json），与子集化同一口径'
  if (s === 'db') return '字体库记录（索引未构建，去「子集化」页点右上角「重建索引」后可切换为子集索引口径）'
  return ''
});

async function loadRecords(reset = false) {
  if (loadingList.value) return
  if (reset) {
    page.value = 1;
    reachedEnd.value = false;
    selectedId.value = null;
  }
  if (reachedEnd.value) return
  loadingList.value = true;
  try {
    const data = await apiModule.get(props.api, '/ass/list', {
      page: page.value,
      limit,
      search: search.value,
    });
    const list = data.list || [];
    total.value = data.total || 0;
    matchSource.value = data.match_source || list[0]?.match_source || matchSource.value;
    records.value = reset ? list : [...records.value, ...list];
    if (!list.length || records.value.length >= total.value) {
      reachedEnd.value = true;
    }
    // 注意：不自动选中/不自动加载第一条——右侧只在点击左侧记录时显示
  } catch (e) {
    emit('notify', e.message || '加载检查记录失败');
  } finally {
    loadingList.value = false;
  }
}

async function loadDetail(id) {
  selectedId.value = id;
  detailLoading.value = true;
  detailOpen.value = true;
  try {
    detail.value = await apiModule.get(props.api, '/ass/detail', { id });
  } catch (e) {
    emit('notify', e.message || '加载详情失败');
  } finally {
    detailLoading.value = false;
  }
}

let searchTimer = null;
watch$1(search, () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadRecords(true), 300);
});

function loadMore() {
  page.value += 1;
  loadRecords();
}

async function handleUpload(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 5 个
  const BATCH = 5;
  let total = 0;
  uploading.value = true;
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const form = new FormData();
      for (const file of chunk) form.append('file', file);
      const res = await props.api.post(
        'plugin/Zitifenlei/ass/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      const body = res?.data ?? res;
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '字幕上传失败'}`);
        break
      } else {
        total += (body?.data?.count ?? chunk.length);
      }
    }
    emit('notify', `已上传 ${total} 个字幕，点击上方「检查」对比字体库`, 'success');
    // 不自动选中任何记录：右侧保持空，等待点击左侧
    await loadRecords(true);
  } catch (e) {
    emit('notify', e.message || '字幕上传失败');
  } finally {
    uploading.value = false;
  }
}

async function checkRecord(id) {
  if (!id || checkingId.value) return null
  checkingId.value = id;
  try {
    const data = await apiModule.post(props.api, '/ass/check', { id });
    // 正在查看该条时刷新右侧显示，否则右侧保持原样（不自动选中）
    if (detail.value && detail.value.id === id) {
      await loadDetail(id);
    }
    await loadRecords(true);
    return data
  } catch (e) {
    emit('notify', e.message || '检查失败');
    return null
  } finally {
    checkingId.value = null;
  }
}

// 顶部「检查」：批量检查左侧全部「待检查」字幕，结果同步更新左侧列表与底部缺失窗口
async function checkAllPending() {
  if (checkingId.value) return
  const pending = records.value.filter(r => r.status === 'pending');
  if (!pending.length) {
    emit('notify', records.value.length ? '没有待检查的字幕' : '请先上传 ASS 字幕', 'warning');
    return
  }
  let ok = 0;
  for (const rec of pending) {
    const data = await checkRecord(rec.id);
    if (data) ok++;
  }
  emit('notify', `检查完成：${ok}/${pending.length} 条`, ok === pending.length ? 'success' : 'warning');
}

// 全量检查：递归扫描 ASS 字幕目录中的全部字幕并检查（存量字幕一键全查，按 file_path upsert 幂等）
async function scanAssAll() {
  if (scanning.value) return
  scanning.value = true;
  try {
    const res = await apiModule.post(props.api, '/ass/scan_all');
    emit('notify', res?.message || '全量检查完成', 'success');
    await loadRecords(true);
  } catch (e) {
    emit('notify', e.message || '全量检查失败');
  } finally {
    scanning.value = false;
  }
}

async function deleteRecord(id) {
  deletingId.value = id;
  try {
    await apiModule.del(props.api, '/ass/delete', { id });
    emit('notify', '已删除记录', 'success');
    // 删除的是当前正在查看的记录时，清空右侧显示
    if (detail.value && detail.value.id === id) {
      detail.value = null;
      detailOpen.value = false;
      selectedId.value = null;
    }
    await loadRecords(true);
  } catch (e) {
    emit('notify', e.message || '删除失败');
  } finally {
    deletingId.value = null;
  }
}

async function clearAll() {
  clearing.value = true;
  try {
    await apiModule.del(props.api, '/ass/clear_all');
    emit('notify', '已清空全部记录', 'success');
    detail.value = null;
    detailOpen.value = false;
    await loadRecords(true);
  } catch (e) {
    emit('notify', e.message || '清空失败');
  } finally {
    clearing.value = false;
  }
}

function goFontSearch(name) {
  // 跳转到字体库搜索该字体名：通过宿主路由 or 菜单；这里直接提示
  emit('notify', `可在字体库搜索：${name}`, 'info');
}

// 软刷新左侧记录列表 + 缺失窗口（保留当前选中，不重置界面）：
// 切 Tab 回来 / refreshKey 触发 / 30 秒轮询兜底 共用——监控新字幕按 id 倒序出现在列表顶部
async function refreshRecordsSoft() {
  page.value = 1;
  reachedEnd.value = false;
  loadingList.value = true;
  try {
    const data = await apiModule.get(props.api, '/ass/list', {
      page: 1,
      limit,
      search: search.value,
    });
    const list = data.list || [];
    total.value = data.total || 0;
    matchSource.value = data.match_source || list[0]?.match_source || matchSource.value;
    records.value = list;
    reachedEnd.value = !list.length || records.value.length >= total.value;
    if (selectedId.value && list.some(r => r.id === selectedId.value)) {
      if (detail.value) loadDetail(selectedId.value);
    } else if (selectedId.value) {
      selectedId.value = null;
      detail.value = null;
      detailOpen.value = false;
    }
  } catch (e) {
    emit('notify', e.message || '刷新检查记录失败');
  } finally {
    loadingList.value = false;
  }
}

// 30 秒轮询兜底：目录监控/入库扫描写入新字幕记录后，页面停留不动也能自动显示
let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(refreshRecordsSoft, 30000);
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// 兄弟页完成数据变更（字体库删除字体等 → Page 递推 refreshKey）：
// ① 当前打开的详情缺失标记 + 底部缺失窗口实时重算；
// ② 软刷新左侧记录列表——切 Tab 回来时监控新写入的字幕直接出现在列表顶部（id 倒序），
//    不再需要退出插件重进
watch$1(() => props.refreshKey, () => {
  refreshRecordsSoft();
});

onMounted$1(async () => {
  await loadRecords(true);
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_spacer = _resolveComponent$1("v-spacer");
  const _component_v_text_field = _resolveComponent$1("v-text-field");
  const _component_v_progress_linear = _resolveComponent$1("v-progress-linear");
  const _component_v_list_item_title = _resolveComponent$1("v-list-item-title");
  const _component_v_chip = _resolveComponent$1("v-chip");
  const _component_v_list_item_subtitle = _resolveComponent$1("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent$1("v-list-item");
  const _component_v_list = _resolveComponent$1("v-list");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_col = _resolveComponent$1("v-col");
  const _component_v_progress_circular = _resolveComponent$1("v-progress-circular");
  const _component_v_alert = _resolveComponent$1("v-alert");
  const _component_v_divider = _resolveComponent$1("v-divider");
  const _component_v_row = _resolveComponent$1("v-row");

  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createElementVNode$1("div", _hoisted_2$1, [
      _createVNode$1(_component_v_btn, {
        color: "primary",
        variant: "tonal",
        disabled: !__props.enabled,
        loading: uploading.value,
        onClick: _cache[0] || (_cache[0] = $event => (uploadRef.value?.click()))
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$1(() => [...(_cache[2] || (_cache[2] = [
              _createTextVNode$1("mdi-upload", -1)
            ]))]),
            _: 1
          }),
          _cache[3] || (_cache[3] = _createTextVNode$1(" 上传 ASS 字幕 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createElementVNode$1("input", {
        ref_key: "uploadRef",
        ref: uploadRef,
        type: "file",
        accept: ".ass,.ASS",
        multiple: "",
        style: {"display":"none"},
        onChange: handleUpload
      }, null, 544),
      _createVNode$1(_component_v_btn, {
        color: "success",
        variant: "tonal",
        class: "ml-2",
        disabled: !__props.enabled || !records.value.length,
        loading: !!checkingId.value,
        onClick: checkAllPending
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$1(() => [...(_cache[4] || (_cache[4] = [
              _createTextVNode$1("mdi-magnify-scan", -1)
            ]))]),
            _: 1
          }),
          _cache[5] || (_cache[5] = _createTextVNode$1(" 检查 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createVNode$1(_component_v_spacer),
      _createVNode$1(_component_v_btn, {
        color: "info",
        variant: "tonal",
        class: "mr-2",
        disabled: !__props.enabled,
        loading: scanning.value,
        title: "全量检查：递归扫描 ASS 字幕目录中的全部字幕并检查（存量字幕一键全查）",
        onClick: scanAssAll
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx$1(() => [...(_cache[6] || (_cache[6] = [
              _createTextVNode$1("mdi-magnify-scan", -1)
            ]))]),
            _: 1
          }),
          _cache[7] || (_cache[7] = _createTextVNode$1(" 全量检查 ", -1))
        ]),
        _: 1
      }, 8, ["disabled", "loading"]),
      _createElementVNode$1("span", _hoisted_3$1, "共 " + _toDisplayString$1(total.value) + " 条记录", 1)
    ]),
    _cache[27] || (_cache[27] = _createElementVNode$1("div", { class: "zt-tip text-body-2 mb-2" }, " 上传字幕仅登记为「待检查」；点右侧「检查」对比字体库，缺字体的补字/入库请到「缺失字体」页 ", -1)),
    _createVNode$1(_component_v_text_field, {
      modelValue: search.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((search).value = $event)),
      placeholder: "搜索字幕文件名...",
      density: "compact",
      variant: "outlined",
      "hide-details": "",
      clearable: "",
      class: "mb-3 zt-search",
      "prepend-inner-icon": "mdi-magnify"
    }, null, 8, ["modelValue"]),
    (matchSourceText.value)
      ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_4$1, " 匹配基准：" + _toDisplayString$1(matchSourceText.value), 1))
      : _createCommentVNode$1("", true),
    _createVNode$1(_component_v_row, { "no-gutters": "" }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_col, {
          cols: "12",
          md: "5"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, { class: "zt-card-bg zt-list-card" }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, { class: "pa-0" }, {
                  default: _withCtx$1(() => [
                    (loadingList.value)
                      ? (_openBlock$1(), _createBlock$1(_component_v_progress_linear, {
                          key: 0,
                          indeterminate: "",
                          color: "primary"
                        }))
                      : _createCommentVNode$1("", true),
                    (!loadingList.value && !records.value.length)
                      ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_5$1, " 暂无检查记录，上传 ASS 字幕后点击「检查」对比字体库 "))
                      : (_openBlock$1(), _createBlock$1(_component_v_list, {
                          key: 2,
                          density: "compact",
                          class: "pa-0"
                        }, {
                          default: _withCtx$1(() => [
                            (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(records.value, (rec) => {
                              return (_openBlock$1(), _createBlock$1(_component_v_list_item, {
                                key: rec.id,
                                active: selectedId.value === rec.id,
                                class: "zt-record-item",
                                onClick: $event => (loadDetail(rec.id))
                              }, {
                                prepend: _withCtx$1(() => [
                                  _createVNode$1(_component_v_icon, {
                                    color: rec.status === 'ok' ? 'success' : 'error',
                                    size: "18"
                                  }, {
                                    default: _withCtx$1(() => [
                                      _createTextVNode$1(_toDisplayString$1(rec.status === 'ok' ? 'mdi-check-circle' : 'mdi-alert-circle'), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"])
                                ]),
                                append: _withCtx$1(() => [
                                  _createVNode$1(_component_v_btn, {
                                    size: "x-small",
                                    variant: "text",
                                    icon: "",
                                    color: "error",
                                    disabled: !__props.enabled,
                                    loading: deletingId.value === rec.id,
                                    title: "删除该字幕（避免误传）",
                                    onClick: _withModifiers($event => (deleteRecord(rec.id)), ["stop"])
                                  }, {
                                    default: _withCtx$1(() => [
                                      _createVNode$1(_component_v_icon, { size: "16" }, {
                                        default: _withCtx$1(() => [...(_cache[11] || (_cache[11] = [
                                          _createTextVNode$1("mdi-close", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  }, 8, ["disabled", "loading", "onClick"])
                                ]),
                                default: _withCtx$1(() => [
                                  _createVNode$1(_component_v_list_item_title, { class: "zt-record-name text-body-2" }, {
                                    default: _withCtx$1(() => [
                                      _createTextVNode$1(_toDisplayString$1(rec.file_name), 1)
                                    ]),
                                    _: 2
                                  }, 1024),
                                  _createVNode$1(_component_v_list_item_subtitle, { class: "zt-record-meta" }, {
                                    default: _withCtx$1(() => [
                                      _createTextVNode$1(_toDisplayString$1(rec.check_time) + " ", 1),
                                      (rec.status === 'pending')
                                        ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                            key: 0,
                                            size: "x-small",
                                            color: "warning",
                                            variant: "tonal",
                                            class: "ml-1",
                                            onClick: _withModifiers($event => (checkRecord(rec.id)), ["stop"])
                                          }, {
                                            default: _withCtx$1(() => [...(_cache[8] || (_cache[8] = [
                                              _createTextVNode$1(" 待检查 ", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["onClick"]))
                                        : (rec.missing_count > 0)
                                          ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                              key: 1,
                                              size: "x-small",
                                              color: "error",
                                              variant: "tonal",
                                              class: "ml-1"
                                            }, {
                                              default: _withCtx$1(() => [
                                                _createTextVNode$1(" 缺 " + _toDisplayString$1(rec.missing_count) + " 个 ", 1)
                                              ]),
                                              _: 2
                                            }, 1024))
                                          : (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                              key: 2,
                                              size: "x-small",
                                              color: "success",
                                              variant: "tonal",
                                              class: "ml-1"
                                            }, {
                                              default: _withCtx$1(() => [...(_cache[9] || (_cache[9] = [
                                                _createTextVNode$1(" 完整 ", -1)
                                              ]))]),
                                              _: 1
                                            })),
                                      (rec.subsetted)
                                        ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                            key: 3,
                                            size: "x-small",
                                            color: "info",
                                            variant: "tonal",
                                            class: "ml-1"
                                          }, {
                                            default: _withCtx$1(() => [...(_cache[10] || (_cache[10] = [
                                              _createTextVNode$1(" 已内嵌字体 ", -1)
                                            ]))]),
                                            _: 1
                                          }))
                                        : _createCommentVNode$1("", true)
                                    ]),
                                    _: 2
                                  }, 1024)
                                ]),
                                _: 2
                              }, 1032, ["active", "onClick"]))
                            }), 128)),
                            (!reachedEnd.value && records.value.length)
                              ? (_openBlock$1(), _createBlock$1(_component_v_list_item, {
                                  key: 0,
                                  class: "text-center"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_v_btn, {
                                      variant: "text",
                                      loading: loadingList.value,
                                      onClick: loadMore
                                    }, {
                                      default: _withCtx$1(() => [...(_cache[12] || (_cache[12] = [
                                        _createTextVNode$1(" 加载更多... ", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["loading"])
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode$1("", true)
                          ]),
                          _: 1
                        })),
                    (records.value.length)
                      ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_6$1, [
                          _createVNode$1(_component_v_btn, {
                            color: "error",
                            variant: "tonal",
                            size: "small",
                            disabled: !__props.enabled,
                            loading: clearing.value,
                            onClick: clearAll
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_v_icon, {
                                start: "",
                                size: "16"
                              }, {
                                default: _withCtx$1(() => [...(_cache[13] || (_cache[13] = [
                                  _createTextVNode$1("mdi-trash-can-outline", -1)
                                ]))]),
                                _: 1
                              }),
                              _cache[14] || (_cache[14] = _createTextVNode$1(" 清空全部 ", -1))
                            ]),
                            _: 1
                          }, 8, ["disabled", "loading"])
                        ]))
                      : _createCommentVNode$1("", true)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_col, {
          cols: "12",
          md: "7"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, { class: "zt-card-bg zt-detail-card" }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, { class: "pa-0" }, {
                  default: _withCtx$1(() => [
                    (detailLoading.value)
                      ? (_openBlock$1(), _createBlock$1(_component_v_progress_circular, {
                          key: 0,
                          indeterminate: "",
                          class: "zt-detail-loading"
                        }))
                      : (!detail.value)
                        ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_7$1, " 点击左侧记录查看详情 "))
                        : (_openBlock$1(), _createElementBlock$1("div", _hoisted_8$1, [
                            _createElementVNode$1("div", _hoisted_9$1, [
                              _createElementVNode$1("div", _hoisted_10$1, [
                                _createElementVNode$1("div", _hoisted_11$1, _toDisplayString$1(detail.value.file_name), 1),
                                _createElementVNode$1("div", _hoisted_12$1, [
                                  _createTextVNode$1(" 检查时间：" + _toDisplayString$1(detail.value.check_time) + " ", 1),
                                  _createVNode$1(_component_v_chip, {
                                    size: "x-small",
                                    variant: "tonal",
                                    color: detail.value.status === 'ok' ? 'success' : (detail.value.status === 'pending' ? 'warning' : 'error'),
                                    class: "ml-2"
                                  }, {
                                    default: _withCtx$1(() => [
                                      _createTextVNode$1(_toDisplayString$1(detail.value.status === 'ok' ? '字体完整' : (detail.value.status === 'pending' ? '待检查' : `缺 ${detail.value.missing_count} 个字体`)), 1)
                                    ]),
                                    _: 1
                                  }, 8, ["color"]),
                                  (detail.value.subsetted)
                                    ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                        key: 0,
                                        size: "x-small",
                                        color: "info",
                                        variant: "tonal",
                                        class: "ml-1"
                                      }, {
                                        default: _withCtx$1(() => [...(_cache[15] || (_cache[15] = [
                                          _createTextVNode$1(" 已内嵌字体 ", -1)
                                        ]))]),
                                        _: 1
                                      }))
                                    : _createCommentVNode$1("", true)
                                ])
                              ])
                            ]),
                            (detail.value.status === 'pending')
                              ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                                  key: 0,
                                  type: "warning",
                                  density: "compact",
                                  class: "mb-3"
                                }, {
                                  default: _withCtx$1(() => [...(_cache[16] || (_cache[16] = [
                                    _createTextVNode$1(" 该字幕尚未检查，点击「检查」按钮对比字体库。 ", -1)
                                  ]))]),
                                  _: 1
                                }))
                              : _createCommentVNode$1("", true),
                            (detail.value.subsetted)
                              ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                                  key: 1,
                                  type: "success",
                                  variant: "tonal",
                                  density: "compact",
                                  class: "mb-3"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_v_icon, {
                                      size: "16",
                                      class: "mr-1"
                                    }, {
                                      default: _withCtx$1(() => [...(_cache[17] || (_cache[17] = [
                                        _createTextVNode$1("mdi-sticker-check-outline", -1)
                                      ]))]),
                                      _: 1
                                    }),
                                    _cache[18] || (_cache[18] = _createTextVNode$1(" 该字幕已内嵌（子集化）字体，播放时无需另行安装字体 ", -1))
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode$1("", true),
                            _createVNode$1(_component_v_divider, { class: "mb-3" }),
                            (detail.value.status !== 'pending')
                              ? (_openBlock$1(), _createElementBlock$1(_Fragment$1, { key: 2 }, [
                                  (detail.value.subsetted)
                                    ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_13$1, [
                                        _createVNode$1(_component_v_icon, {
                                          start: "",
                                          size: "16",
                                          color: "success"
                                        }, {
                                          default: _withCtx$1(() => [...(_cache[19] || (_cache[19] = [
                                            _createTextVNode$1("mdi-sticker-check-outline", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _cache[20] || (_cache[20] = _createElementVNode$1("span", { class: "zt-section-label" }, "该字幕已内嵌（子集化）字体，无需检查缺失字体", -1))
                                      ]))
                                    : (_openBlock$1(), _createElementBlock$1(_Fragment$1, { key: 1 }, [
                                        _createElementVNode$1("div", _hoisted_14$1, [
                                          _createVNode$1(_component_v_icon, {
                                            start: "",
                                            size: "16",
                                            color: "error"
                                          }, {
                                            default: _withCtx$1(() => [...(_cache[21] || (_cache[21] = [
                                              _createTextVNode$1("mdi-alert-decagram-outline", -1)
                                            ]))]),
                                            _: 1
                                          }),
                                          _createElementVNode$1("span", _hoisted_15$1, "缺失字体（" + _toDisplayString$1(detail.value.missing_fonts?.length || 0) + "）", 1)
                                        ]),
                                        _createElementVNode$1("div", _hoisted_16$1, [
                                          (!(detail.value.missing_fonts?.length))
                                            ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_17$1, [
                                                _createVNode$1(_component_v_icon, {
                                                  color: "success",
                                                  size: "16",
                                                  class: "mr-1"
                                                }, {
                                                  default: _withCtx$1(() => [...(_cache[22] || (_cache[22] = [
                                                    _createTextVNode$1("mdi-check-circle", -1)
                                                  ]))]),
                                                  _: 1
                                                }),
                                                _cache[23] || (_cache[23] = _createTextVNode$1(" 没有缺失字体 ", -1))
                                              ]))
                                            : _createCommentVNode$1("", true),
                                          (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(detail.value.missing_fonts || [], (f) => {
                                            return (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                              key: f,
                                              size: "small",
                                              color: "error",
                                              variant: "tonal",
                                              class: "ma-1 zt-missing-chip"
                                            }, {
                                              default: _withCtx$1(() => [
                                                _createTextVNode$1(_toDisplayString$1(f) + " ", 1),
                                                _createVNode$1(_component_v_icon, {
                                                  size: "14",
                                                  class: "ml-1 zt-search-icon",
                                                  onClick: $event => (goFontSearch(f))
                                                }, {
                                                  default: _withCtx$1(() => [...(_cache[24] || (_cache[24] = [
                                                    _createTextVNode$1(" mdi-magnify ", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["onClick"])
                                              ]),
                                              _: 2
                                            }, 1024))
                                          }), 128))
                                        ])
                                      ], 64)),
                                  _createElementVNode$1("div", null, [
                                    _createVNode$1(_component_v_icon, {
                                      start: "",
                                      size: "16"
                                    }, {
                                      default: _withCtx$1(() => [...(_cache[25] || (_cache[25] = [
                                        _createTextVNode$1("mdi-format-font", -1)
                                      ]))]),
                                      _: 1
                                    }),
                                    _createElementVNode$1("span", _hoisted_18$1, "使用的全部字体（" + _toDisplayString$1(detail.value.all_fonts?.length || 0) + "）", 1)
                                  ]),
                                  _createElementVNode$1("div", _hoisted_19$1, [
                                    (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(detail.value.all_fonts || [], (f) => {
                                      return (_openBlock$1(), _createBlock$1(_component_v_chip, {
                                        key: f.name || f,
                                        size: "small",
                                        variant: "tonal",
                                        class: _normalizeClass$1(["ma-1", { 'zt-in-lib': f.in_lib }])
                                      }, {
                                        default: _withCtx$1(() => [
                                          (f.in_lib)
                                            ? (_openBlock$1(), _createBlock$1(_component_v_icon, {
                                                key: 0,
                                                size: "14",
                                                class: "mr-1 text-success"
                                              }, {
                                                default: _withCtx$1(() => [...(_cache[26] || (_cache[26] = [
                                                  _createTextVNode$1("mdi-check-circle", -1)
                                                ]))]),
                                                _: 1
                                              }))
                                            : _createCommentVNode$1("", true),
                                          _createTextVNode$1(" " + _toDisplayString$1(f.name || f), 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["class"]))
                                    }), 128))
                                  ])
                                ], 64))
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
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const Check = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-b0279a64"]]);

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass} = await importShared('vue');


const _hoisted_1 = {
  class: "zt-settings",
  style: {"max-width":"720px"}
};
const _hoisted_2 = { class: "zt-switch-row" };
const _hoisted_3 = { class: "zt-radio-title" };
const _hoisted_4 = { class: "zt-radio-desc" };
const _hoisted_5 = { class: "zt-radio-title" };
const _hoisted_6 = { class: "zt-radio-desc" };
const _hoisted_7 = { class: "zt-switch-row mt-2" };
const _hoisted_8 = { class: "zt-switch-row mt-2" };
const _hoisted_9 = { class: "zt-switch-row" };
const _hoisted_10 = { class: "zt-switch-row" };
const _hoisted_11 = { class: "zt-switch-row" };
const _hoisted_12 = { class: "zt-switch-row" };
const _hoisted_13 = { class: "zt-switch-row" };
const _hoisted_14 = { class: "zt-switch-row" };
const _hoisted_15 = { class: "zt-radio-title" };
const _hoisted_16 = { class: "zt-radio-desc" };
const _hoisted_17 = { class: "zt-switch-row" };
const _hoisted_18 = { class: "zt-switch-row" };
const _hoisted_19 = { class: "d-flex justify-end mt-4" };

const {onMounted,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Settings',
  props: {
  api: { type: Object, default: () => ({}) },
  // 宿主在打开配置弹窗时通过 GET /plugin/form/{id} 拉取的合并 model（默认值+已存配置）
  initialConfig: { type: Object, default: () => ({}) },
  // 插件总开关（数据页传入，与 config.enabled 同源；声明用于避免 attrs 落到根元素）
  enabled: { type: Boolean, default: true },
},
  emits: ['notify', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const DEFAULT_CONFIG = {
  enabled: true,
  input_dir: '',
  lib_dir: '',
  ass_dir: '',
  subset_dir: '',
  scan_mode: 'internal',
  archive_mode: 'copy',
  // 移动归档时删除判重跳过的残留源文件（只作用于「移动原文件」模式）
  move_delete_duplicate: true,
  // 是否利用字体内部名称命名（开：用字体内部 PostScript 名；关：保持原文件名）
  font_name_internal: false,
  // 是否启用监控（总开关）：统一控制字体监控目录 / ASS字幕目录监控 / ASS目录监控子集
  monitor_enabled: false,
  auto_inbound: true,
  auto_collect: true,
  notify_enabled: false,
  auto_subset: false,
  subset_overwrite: false,
  subset_out_dir: '',
  subset_out_mode: 'copy',
  subset_sync_subdir: false,
  hdr_brightness: false,
  hdr_brightness_level: '',
};

// 数据源：宿主 initial-config（默认值+已存配置）；进入页面后立即用后端权威配置回填，
// 避免详情页（Page 场景）拿不到 initialConfig 时表单显示默认空值、一保存就覆盖真实配置。
const config = ref({ ...DEFAULT_CONFIG, ...(props.initialConfig || {}) });
const saving = ref(false);

const scanModes = [
  { title: '内部扫描(推荐)', value: 'internal', description: '扫描字体文件内部元数据（需 fontTools）' },
  { title: '文件名解析', value: 'filename', description: '直接从文件名提取信息，速度更快' },
];
const archiveModes = [
  { title: '复制保留原文件', value: 'copy', description: '归档时复制字体到字体库目录' },
  { title: '移动原文件', value: 'move', description: '归档时移动字体到字体库目录' },
];
const subsetOutModes = [
  { title: '复制到输出目录', value: 'copy', description: '把新的字幕（成品）复制到输出目录，旧的源字幕还在原处' },
  { title: '移动到输出目录', value: 'move', description: '把字幕（成品）移动到输出目录，原处不再保留' },
];
// 同步子集字体夹（*_subsetted）：字体已内嵌进成品字幕，夹子仅是 assfonts 的备份，默认不保留
// HDR 字幕亮度档位（关/档位选择，对应 ASS 色码压暗比例）
const hdrLevels = [
  { title: '关（不调整亮度）', value: '' },
  { title: '100% 纯白（&H00FFFFFF）· 仅 SDR 片源', value: '100' },
  { title: '85%（&H00D9D9D9）· 折中保守档', value: '85' },
  { title: '80%（&H00CCCCCC）· HDR 主流推荐 ⭐', value: '80' },
  { title: '75%（&H00BFBFBF）· 暗场多的片子', value: '75' },
  { title: '70%（&H00B2B2B2）· OLED/MiniLED 暗室', value: '70' },
  { title: '63%（&H00A1A1A1）· 模拟 SDR 白观感', value: '63' },
  { title: '50% 中灰（&H00808080）· 极端场景', value: '50' },
];

// 拉取后端权威配置回填表单（详情页/配置弹窗统一入口）
// 对齐 subscribeplus：数据页复用配置 UI 时先 GET /config 取当前值，
// 避免表单显示默认值导致一保存就把真实配置覆盖成空。
async function loadConfig() {
  if (typeof props.api?.get !== 'function') return
  try {
    const data = await apiModule.get(props.api, '/config');
    if (data && typeof data === 'object') {
      const { dirs, ...cfg } = data;
      config.value = { ...DEFAULT_CONFIG, ...cfg };
    }
  } catch (e) {
    // 读取失败保持初始配置（弹窗场景 initialConfig 已经够用）
  }
}

// 保存（对齐 subscribeplus_v0.23 单通道范式，杜绝双保存冲突）：
// 1) POST /config 由后端 update_config 写入宿主原生配置并热生效；
// 2) GET /config 校验回填权威值（enabled 以运行时为准），开关不再回跳；
// 3) emit('save') 仅用于父组件本地状态同步（停用遮罩即时生效），不请求宿主再 PUT。
async function save() {
  saving.value = true;
  try {
    // HDR 开关开启但档位为空 → 给默认推荐档 80%
    if (config.value.hdr_brightness && !config.value.hdr_brightness_level) {
      config.value.hdr_brightness_level = '80';
    }
    if (!config.value.hdr_brightness) {
      config.value.hdr_brightness_level = '';
    }
    if (typeof props.api?.post === 'function') {
      await apiModule.post(props.api, '/config', { ...config.value });
      try {
        const data = await apiModule.get(props.api, '/config');
        if (data && typeof data === 'object') {
          const { dirs, ...cfg } = data;
          config.value = { ...DEFAULT_CONFIG, ...cfg };
        }
      } catch (e) {
        // 校验回填失败忽略，保留本地已存配置
      }
      emit('save', { ...config.value });
      emit('notify', '配置已保存并生效；插件列表状态将在刷新后更新', 'success');
    } else {
      // 兜底：无 API 通道时交由宿主原生保存
      emit('save', { ...config.value });
      emit('notify', '配置已保存', 'success');
    }
  } catch (e) {
    emit('notify', e.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

onMounted(loadConfig);

// 「插件总开关」拨向关闭时拦截：后台有任务（全量检查/扫描/子集化运行中）则弹提示并取消关闭，
// 保住 v1.2.13 优雅停止的前提——先不触发 stop_service，任务跑完再关，不留任何半截状态
const busyDialog = ref(false);
const checkingBusy = ref(false);
async function onEnabledToggle(val) {
  if (val === config.value.enabled) return
  if (val === false) {
    checkingBusy.value = true;
    try {
      const st = await apiModule.get(props.api, '/task/status');
      if (st && st.busy) {
        busyDialog.value = true;
        return // 有任务运行：不切换，弹提示
      }
    } catch (e) {
      // 接口异常时不拦截，放行（避免查询失败把开关卡死）
    } finally {
      checkingBusy.value = false;
    }
  }
  config.value.enabled = val;
}

// 「入库自动检查字幕」与「入库后自动子集化」互斥：同一批入库字幕只走一种处理，
// 一次只允许开一个——开检查自动关子集化，开子集化自动关检查，避免用户两开打架。
watch(() => config.value.auto_inbound, (v) => {
  if (v) config.value.auto_subset = false;
});
watch(() => config.value.auto_subset, (v) => {
  if (v) config.value.auto_inbound = false;
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_radio = _resolveComponent("v-radio");
  const _component_v_radio_group = _resolveComponent("v-radio-group");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_dialog = _resolveComponent("v-dialog");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, { class: "zt-card-bg" }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, { class: "zt-card-title" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              start: "",
              size: "18",
              color: config.value.enabled ? 'success' : 'error'
            }, {
              default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                _createTextVNode("mdi-power", -1)
              ]))]),
              _: 1
            }, 8, ["color"]),
            _cache[23] || (_cache[23] = _createTextVNode(" 插件总开关 ", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_2, [
              _cache[24] || (_cache[24] = _createElementVNode("div", { class: "flex-grow-1" }, [
                _createElementVNode("div", { class: "zt-switch-title" }, "启用字体分类管家"),
                _createElementVNode("div", { class: "zt-switch-desc" }, "关闭后插件所有功能不可用、后台定时任务停止，保存配置后生效")
              ], -1)),
              _createVNode(_component_v_switch, {
                "model-value": config.value.enabled,
                color: "success",
                "hide-details": "",
                loading: checkingBusy.value,
                "onUpdate:modelValue": onEnabledToggle
              }, null, 8, ["model-value", "loading"])
            ]),
            (!config.value.enabled)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "warning",
                  density: "compact",
                  class: "mt-2"
                }, {
                  default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
                    _createTextVNode(" 插件已停用：其他页面将不可操作，仅可在本页重新开启。 ", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode("", true)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createElementVNode("div", {
      class: _normalizeClass(["zt-disabled-zone", { 'is-off': !config.value.enabled }])
    }, [
      _createVNode(_component_v_card, { class: "zt-card-bg mt-4" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_title, { class: "zt-card-title" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                size: "18"
              }, {
                default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                  _createTextVNode("mdi-folder-cog-outline", -1)
                ]))]),
                _: 1
              }),
              _cache[27] || (_cache[27] = _createTextVNode(" 目录配置 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_text_field, {
                modelValue: config.value.input_dir,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.value.input_dir) = $event)),
                label: "字体监控目录",
                placeholder: "/media/fonts/incoming",
                density: "compact",
                variant: "outlined",
                class: "mb-3"
              }, null, 8, ["modelValue"]),
              _createVNode(_component_v_text_field, {
                modelValue: config.value.lib_dir,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.lib_dir) = $event)),
                label: "字体库目录",
                placeholder: "/media/fonts/library",
                density: "compact",
                variant: "outlined",
                class: "mb-3"
              }, null, 8, ["modelValue"]),
              _createVNode(_component_v_text_field, {
                modelValue: config.value.ass_dir,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.ass_dir) = $event)),
                label: "ASS字幕目录监控",
                placeholder: "/media/subtitles",
                density: "compact",
                variant: "outlined",
                class: "mb-3"
              }, null, 8, ["modelValue"]),
              _createVNode(_component_v_text_field, {
                modelValue: config.value.subset_dir,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.subset_dir) = $event)),
                label: "ASS目录监控子集",
                placeholder: "/media/subtitles/subset",
                density: "compact",
                variant: "outlined",
                class: "mb-3"
              }, null, 8, ["modelValue"]),
              _createVNode(_component_v_text_field, {
                modelValue: config.value.subset_out_dir,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.subset_out_dir) = $event)),
                label: "子集化输出目录",
                placeholder: "/media/subtitles/subset-out",
                density: "compact",
                variant: "outlined",
                hint: "目录监控（ASS目录监控子集）子集化成品（字幕与子集字体夹）的落点，按剧名分到子文件夹；手动上传字幕的子集结果留在插件临时文件夹，不受此设置影响",
                "persistent-hint": ""
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_card, { class: "zt-card-bg mt-4" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_title, { class: "zt-card-title" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                size: "18"
              }, {
                default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                  _createTextVNode("mdi-tune-variant", -1)
                ]))]),
                _: 1
              }),
              _cache[29] || (_cache[29] = _createTextVNode(" 扫描与归档模式 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _cache[32] || (_cache[32] = _createElementVNode("div", { class: "zt-option-label mb-1" }, "扫描模式", -1)),
              _createVNode(_component_v_radio_group, {
                modelValue: config.value.scan_mode,
                "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.scan_mode) = $event)),
                density: "compact"
              }, {
                default: _withCtx(() => [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(scanModes, (mode) => {
                    return _createVNode(_component_v_radio, {
                      key: mode.value,
                      label: mode.title,
                      value: mode.value
                    }, {
                      label: _withCtx(() => [
                        _createElementVNode("div", null, [
                          _createElementVNode("div", _hoisted_3, _toDisplayString(mode.title), 1),
                          _createElementVNode("div", _hoisted_4, _toDisplayString(mode.description), 1)
                        ])
                      ]),
                      _: 2
                    }, 1032, ["label", "value"])
                  }), 64))
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _cache[33] || (_cache[33] = _createElementVNode("div", { class: "zt-option-label mb-1 mt-2" }, "归档模式", -1)),
              _createVNode(_component_v_radio_group, {
                modelValue: config.value.archive_mode,
                "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.archive_mode) = $event)),
                density: "compact"
              }, {
                default: _withCtx(() => [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(archiveModes, (mode) => {
                    return _createVNode(_component_v_radio, {
                      key: mode.value,
                      label: mode.title,
                      value: mode.value
                    }, {
                      label: _withCtx(() => [
                        _createElementVNode("div", null, [
                          _createElementVNode("div", _hoisted_5, _toDisplayString(mode.title), 1),
                          _createElementVNode("div", _hoisted_6, _toDisplayString(mode.description), 1)
                        ])
                      ]),
                      _: 2
                    }, 1032, ["label", "value"])
                  }), 64))
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _createElementVNode("div", _hoisted_7, [
                _cache[30] || (_cache[30] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "移动归档时删除重复源文件"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "仅作用于「移动原文件」模式：字体库已有同名字体、判重跳过时，自动删除监控目录里残留的重复源文件；复制模式不受影响（源文件本就保留）")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.move_delete_duplicate,
                  "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.move_delete_duplicate) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode("div", _hoisted_8, [
                _cache[31] || (_cache[31] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "利用字体内部名称命名"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "开：归档时用字体内部的 PostScript 名命名（如 SourceHanSansCN-Bold）；关：保持原名（文件名）不变")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.font_name_internal,
                  "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.font_name_internal) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_card, { class: "zt-card-bg mt-4" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_title, { class: "zt-card-title" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                size: "18"
              }, {
                default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
                  _createTextVNode("mdi-cog-refresh-outline", -1)
                ]))]),
                _: 1
              }),
              _cache[35] || (_cache[35] = _createTextVNode(" 自动化设置 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createElementVNode("div", _hoisted_9, [
                _cache[36] || (_cache[36] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "是否启用监控"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "总开关：统一控制「字体监控目录」「ASS字幕目录监控」「ASS目录监控子集」三个目录的监控启停；关闭则三个目录都不监控")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.monitor_enabled,
                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.monitor_enabled) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode("div", _hoisted_10, [
                _cache[37] || (_cache[37] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "是否自动执行监控结果"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "开：监控到新东西直接执行——字体直接归档、字幕直接检查、子集化直接运行；关：待定——字体进待确认、检查进待检查、子集化进待处理，等手动处理")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.auto_collect,
                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.auto_collect) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode("div", _hoisted_11, [
                _cache[38] || (_cache[38] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "入库自动检查字幕"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "MP 转存完成（整理入库）时自动扫描该剧 ASS 字幕并检查字体，汇总通知（与「入库后自动子集化」互斥，同时只能开一个）")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.auto_inbound,
                  "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.auto_inbound) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode("div", _hoisted_12, [
                _cache[39] || (_cache[39] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "发送通知"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "归档/检查完成时通过系统通知发送结果")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.notify_enabled,
                  "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.notify_enabled) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_card, { class: "zt-card-bg mt-4" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_title, { class: "zt-card-title" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                size: "18"
              }, {
                default: _withCtx(() => [...(_cache[40] || (_cache[40] = [
                  _createTextVNode("mdi-subtitles-outline", -1)
                ]))]),
                _: 1
              }),
              _cache[41] || (_cache[41] = _createTextVNode(" 子集化设置 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createElementVNode("div", _hoisted_13, [
                _cache[42] || (_cache[42] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "入库后自动子集化"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "MP 转存完成时，对新增字幕调用 assfonts 子集化并内嵌字体（结果可在「子集化」页查看；与「入库自动检查字幕」互斥，同时只能开一个）")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.auto_subset,
                  "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.auto_subset) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createElementVNode("div", _hoisted_14, [
                _cache[43] || (_cache[43] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "输出覆盖原文件"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "开：子集化结果直接替换原字幕文件（文件名不变，媒体库只保留一份）；关：保留原字幕，另生成 xx.assfonts.ass 成品文件")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.subset_overwrite,
                  "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.subset_overwrite) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _cache[46] || (_cache[46] = _createElementVNode("div", { class: "zt-option-label mb-1 mt-2" }, "监控目录输出方式", -1)),
              _createVNode(_component_v_radio_group, {
                modelValue: config.value.subset_out_mode,
                "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.value.subset_out_mode) = $event)),
                density: "compact"
              }, {
                default: _withCtx(() => [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(subsetOutModes, (mode) => {
                    return _createVNode(_component_v_radio, {
                      key: mode.value,
                      label: mode.title,
                      value: mode.value
                    }, {
                      label: _withCtx(() => [
                        _createElementVNode("div", null, [
                          _createElementVNode("div", _hoisted_15, _toDisplayString(mode.title), 1),
                          _createElementVNode("div", _hoisted_16, _toDisplayString(mode.description), 1)
                        ])
                      ]),
                      _: 2
                    }, 1032, ["label", "value"])
                  }), 64))
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _cache[47] || (_cache[47] = _createElementVNode("div", { class: "zt-hint" }, "目录监控（ASS目录监控子集）的字幕成品按「输出目录/剧名/」子文件夹分类输出（如「你的名字.ass」→「你的名字」文件夹），多剧字幕互不混淆；手动上传的字幕子集结果留在插件临时文件夹，不受此设置影响", -1)),
              _createElementVNode("div", _hoisted_17, [
                _cache[44] || (_cache[44] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "是否在输出端保留子集化字体文件夹"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "管 MP 入库与监控目录子集化：开＝在输出端产生 *_subsetted 字体文件夹；关＝不产生，源字幕目录里的也自动清理。手动上传的字幕子集不受此开关支配（始终不产生）")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.subset_sync_subdir,
                  "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.value.subset_sync_subdir) = $event)),
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _cache[48] || (_cache[48] = _createElementVNode("div", { class: "zt-option-label mb-1 mt-2" }, "HDR 字幕亮度", -1)),
              _createElementVNode("div", _hoisted_18, [
                _cache[45] || (_cache[45] = _createElementVNode("div", { class: "flex-grow-1" }, [
                  _createElementVNode("div", { class: "zt-switch-title" }, "启用 HDR 亮度压暗"),
                  _createElementVNode("div", { class: "zt-switch-desc" }, "子集化/上传处理的字幕成品按所选档位压暗主色/描边/阴影，避免 HDR 片源下纯白字幕刺眼")
                ], -1)),
                _createVNode(_component_v_switch, {
                  modelValue: config.value.hdr_brightness,
                  "onUpdate:modelValue": [
                    _cache[17] || (_cache[17] = $event => ((config.value.hdr_brightness) = $event)),
                    _cache[18] || (_cache[18] = v => { if (!v) config.value.hdr_brightness_level = ''; })
                  ],
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _createVNode(_component_v_select, {
                modelValue: config.value.hdr_brightness_level,
                "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((config.value.hdr_brightness_level) = $event)),
                items: hdrLevels,
                "item-title": "title",
                "item-value": "value",
                label: "亮度档位",
                density: "compact",
                variant: "outlined",
                class: "mt-1",
                disabled: !config.value.hdr_brightness,
                hint: "档位即纯白亮度百分比（80% ⭐ HDR 主流推荐）；选择「关」或留空则不调整",
                "persistent-hint": ""
              }, null, 8, ["modelValue", "disabled"]),
              _cache[49] || (_cache[49] = _createElementVNode("div", { class: "zt-hint" }, "应用范围：全量子集化、目录监控自动子集化、入库子集化处理后生成的成品字幕（原始字幕不受影响）", -1)),
              _cache[50] || (_cache[50] = _createElementVNode("div", { class: "zt-hint" }, "assfonts 可执行文件随插件分发（bin/assfonts），字体来源为「字体库目录」；新字体入库后在「子集化」页点击「重建索引」即可生效", -1))
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ], 2),
    _createElementVNode("div", _hoisted_19, [
      _createVNode(_component_v_btn, {
        color: "primary",
        variant: "tonal",
        loading: saving.value,
        onClick: save
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_icon, {
            start: "",
            size: "18"
          }, {
            default: _withCtx(() => [...(_cache[51] || (_cache[51] = [
              _createTextVNode("mdi-content-save-outline", -1)
            ]))]),
            _: 1
          }),
          _cache[52] || (_cache[52] = _createTextVNode(" 保存配置 ", -1))
        ]),
        _: 1
      }, 8, ["loading"])
    ]),
    _createVNode(_component_v_dialog, {
      modelValue: busyDialog.value,
      "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((busyDialog).value = $event)),
      "max-width": "480px"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { class: "zt-card-bg" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  start: "",
                  size: "20",
                  color: "warning"
                }, {
                  default: _withCtx(() => [...(_cache[53] || (_cache[53] = [
                    _createTextVNode("mdi-progress-clock", -1)
                  ]))]),
                  _: 1
                }),
                _cache[54] || (_cache[54] = _createTextVNode(" 后台有任务运行 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_text, { class: "pt-2" }, {
              default: _withCtx(() => [...(_cache[55] || (_cache[55] = [
                _createTextVNode(" 当前有全量检查 / 扫描 / 子集化任务正在后台运行，暂时无法关闭插件。", -1),
                _createElementVNode("br", null, null, -1),
                _createElementVNode("br", null, null, -1),
                _createTextVNode(" 请等待任务完成后再关闭插件，直接关闭可能导致文件入库但记录缺失。 ", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  color: "primary",
                  variant: "tonal",
                  onClick: _cache[20] || (_cache[20] = $event => (busyDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[56] || (_cache[56] = [
                    _createTextVNode("我知道了", -1)
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
    }, 8, ["modelValue"])
  ]))
}
}

};
const Settings = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-17fb2099"]]);

export { Check as C, Dashboard as D, FontLibrary as F, Settings as S, _export_sfc as _, apiModule as a };
