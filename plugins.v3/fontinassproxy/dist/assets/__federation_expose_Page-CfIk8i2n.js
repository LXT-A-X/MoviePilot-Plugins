import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import _sfc_main$2, { a as apiModule } from './__federation_expose_Config-bMq6QQt6.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,toDisplayString:_toDisplayString$1,normalizeClass:_normalizeClass,renderList:_renderList$1,Fragment:_Fragment$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1} = await importShared('vue');


const _hoisted_1$1 = { class: "text-subtitle-2 text-medium-emphasis d-flex align-center" };
const _hoisted_2$1 = { class: "text-caption text-medium-emphasis" };
const _hoisted_3$1 = { class: "text-subtitle-2 text-medium-emphasis d-flex align-center" };
const _hoisted_4$1 = { class: "text-caption text-medium-emphasis text-truncate" };
const _hoisted_5$1 = { class: "text-subtitle-2 text-medium-emphasis d-flex align-center" };
const _hoisted_6$1 = { class: "text-caption text-medium-emphasis" };
const _hoisted_7$1 = { class: "text-subtitle-2 text-medium-emphasis d-flex align-center" };
const _hoisted_8$1 = { class: "text-caption text-medium-emphasis" };
const _hoisted_9$1 = { class: "text-center" };
const _hoisted_10$1 = { class: "text-center" };
const _hoisted_11 = {
  key: 0,
  class: "fia-empty"
};
const _hoisted_12 = { class: "fia-log-time" };
const _hoisted_13 = { class: "fia-log-message" };

const {computed: computed$1,inject: inject$1,nextTick,onActivated,onBeforeUnmount,onDeactivated,onMounted: onMounted$1,ref: ref$1} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'Status',
  props: {
  api: { type: Object, default: () => ({}) },
},
  emits: ['action', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;
const toast = inject$1('moviepilot:toast', null);

const status = ref$1(null);
const missing = ref$1([]);
const logs = ref$1([]);
const logBox = ref$1(null);
const followLog = ref$1(true);
const busy = ref$1(false);
const refreshing = ref$1(false);
let timer = null;
let logTimer = null;

// ---- 状态卡计算（正常绿 / 异常红）----
const idxReady = computed$1(() => status.value?.index?.ready === true);
const idxScanning = computed$1(() => status.value?.index?.scanning === true);
const idxHasDirs = computed$1(() => (status.value?.index?.dirs?.length ?? 0) > 0);
const idxFaces = computed$1(() => status.value?.index?.faces ?? 0);
const ftVer = computed$1(() => status.value?.fonttools_version ?? '?');
const hbVer = computed$1(() => status.value?.uharfbuzz_version ?? '?');
const idxSub = computed$1(() => {
  if (idxReady.value) {
    const hbTxt = hbVer.value && hbVer.value !== '?'
      ? ` · uharfbuzz ${hbVer.value}`
      : ' · uharfbuzz 未安装（fontTools 兜底）';
    return '就绪 · fontTools ' + ftVer.value + hbTxt
  }
  if (idxScanning.value) return '扫描中… 已 ' + idxFaces.value + ' 个字体'
  if (idxHasDirs.value) return '等待扫描'
  return '未配置字体目录'
});
const idxColor = computed$1(() => idxReady.value ? 'success' : 'error');
const proxyOn = computed$1(() => status.value?.internal_proxy?.enabled === true);
const proxyPort = computed$1(() => status.value?.internal_proxy?.port ?? null);
const cacheOn = computed$1(() => !!status.value?.cache?.disk_dir);
const cacheTotal = computed$1(() => (status.value?.cache?.mem_items ?? 0) + (status.value?.cache?.disk_files ?? 0));
const missTotal = computed$1(() => status.value?.missing ?? 0);
// 日志有 error 级时视为异常（红），仅 warning 黄色
const logBad = computed$1(() => logs.value.some(l => (l.level || '') === 'error'));
const logWarn = computed$1(() => !logBad.value && logs.value.some(l => (l.level || '') === 'warning'));

function fmtTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function toastMsg(type, message) {
  if (toast && typeof toast[type] === 'function') toast[type](message);
}

async function loadStatus() {
  try {
    status.value = await apiModule.get(props.api, '/status');
  } catch (e) {
    toastMsg('error', '获取状态失败: ' + e.message);
  }
}

async function loadMissing() {
  try {
    missing.value = (await apiModule.get(props.api, '/missing')) || [];
  } catch (e) {
    toastMsg('error', '获取缺失字体失败: ' + e.message);
  }
}

async function loadLogs() {
  try {
    logs.value = (await apiModule.get(props.api, '/logs', { lines: 300 })) || [];
  } catch (e) {
    // 日志读取失败不打扰
  }
  if (followLog.value && logBox.value) {
    await nextTick();
    logBox.value.scrollTop = logBox.value.scrollHeight;
  }
}

function onLogScroll() {
  const el = logBox.value;
  if (!el) return
  followLog.value = (el.scrollHeight - el.scrollTop - el.clientHeight) < 40;
}

async function refresh() {
  refreshing.value = true;
  await Promise.all([loadStatus(), loadMissing(), loadLogs()]);
  refreshing.value = false;
}

async function rebuild() {
  busy.value = true;
  try {
    const res = await apiModule.post(props.api, '/rebuild');
    toastMsg('success', res?.message || '字体索引已重建');
    await refresh();
  } catch (e) {
    toastMsg('error', e.message);
  } finally {
    busy.value = false;
  }
}

async function clearMissing() {
  if (!missing.value.length) return
  busy.value = true;
  try {
    const res = await apiModule.post(props.api, '/missing/clear');
    toastMsg('success', res?.message || '缺失字体记录已清除');
    missing.value = [];
    await loadStatus();
  } catch (e) {
    toastMsg('error', e.message);
  } finally {
    busy.value = false;
  }
}

async function clearLogs() {
  busy.value = true;
  try {
    const res = await apiModule.post(props.api, '/logs/clear');
    toastMsg('success', res?.message || '插件日志已清除');
    logs.value = [];
  } catch (e) {
    toastMsg('error', e.message);
  } finally {
    busy.value = false;
  }
}

async function clearCache() {
  busy.value = true;
  try {
    const res = await apiModule.post(props.api, '/clear_cache');
    toastMsg('success', res?.message || '缓存已清空');
    await refresh();
  } catch (e) {
    toastMsg('error', e.message);
  } finally {
    busy.value = false;
  }
}

onMounted$1(() => {
  refresh();
});
onActivated(() => {
  // 从其他页（设置）切回状态页时：立即拉最新数据并重启定时器，
  // 避免 keep-alive 缓存导致界面停留在旧数据
  refresh();
  if (!timer) timer = setInterval(refresh, 10000);
  if (!logTimer) logTimer = setInterval(loadLogs, 8000);
});
onDeactivated(() => {
  if (timer) { clearInterval(timer); timer = null; }
  if (logTimer) { clearInterval(logTimer); logTimer = null; }
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
  if (logTimer) clearInterval(logTimer);
});

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_spacer = _resolveComponent$1("v-spacer");
  const _component_v_row = _resolveComponent$1("v-row");
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_col = _resolveComponent$1("v-col");
  const _component_v_card_title = _resolveComponent$1("v-card-title");
  const _component_v_table = _resolveComponent$1("v-table");
  const _component_v_alert = _resolveComponent$1("v-alert");
  const _component_v_chip = _resolveComponent$1("v-chip");

  return (_openBlock$1(), _createElementBlock$1("div", null, [
    _createVNode$1(_component_v_row, {
      class: "align-center mb-3",
      "no-gutters": "",
      style: {"padding-right":"48px"}
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_btn, {
          size: "small",
          variant: "flat",
          "prepend-icon": "mdi-refresh",
          loading: refreshing.value,
          onClick: refresh
        }, {
          default: _withCtx$1(() => [...(_cache[0] || (_cache[0] = [
            _createTextVNode$1("刷新", -1)
          ]))]),
          _: 1
        }, 8, ["loading"]),
        _createVNode$1(_component_v_spacer),
        _createVNode$1(_component_v_btn, {
          size: "small",
          color: "error",
          variant: "flat",
          "prepend-icon": "mdi-cached",
          disabled: busy.value,
          class: "mr-2",
          onClick: clearCache
        }, {
          default: _withCtx$1(() => [...(_cache[1] || (_cache[1] = [
            _createTextVNode$1("清空字幕缓存", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createVNode$1(_component_v_btn, {
          size: "small",
          color: "primary",
          variant: "flat",
          "prepend-icon": "mdi-database-sync",
          disabled: busy.value || !status.value?.index?.ready,
          onClick: rebuild
        }, {
          default: _withCtx$1(() => [...(_cache[2] || (_cache[2] = [
            _createTextVNode$1("重建字体索引", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"])
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_row, { dense: "" }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_col, {
          cols: "12",
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, {
              variant: "tonal",
              class: "fill-height"
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, null, {
                  default: _withCtx$1(() => [
                    _createElementVNode$1("div", _hoisted_1$1, [
                      _createVNode$1(_component_v_icon, {
                        size: 16,
                        color: idxColor.value,
                        class: "mr-1"
                      }, {
                        default: _withCtx$1(() => [...(_cache[3] || (_cache[3] = [
                          _createTextVNode$1("mdi-circle", -1)
                        ]))]),
                        _: 1
                      }, 8, ["color"]),
                      _cache[4] || (_cache[4] = _createTextVNode$1(" 字体索引 ", -1))
                    ]),
                    _createElementVNode$1("div", {
                      class: _normalizeClass(["text-h6 mt-1", idxReady.value ? 'text-success' : 'text-error'])
                    }, [
                      _createTextVNode$1(_toDisplayString$1(idxFaces.value) + " ", 1),
                      _cache[5] || (_cache[5] = _createElementVNode$1("span", { class: "text-caption text-medium-emphasis" }, "个字体", -1))
                    ], 2),
                    _createElementVNode$1("div", _hoisted_2$1, _toDisplayString$1(idxSub.value), 1)
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
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, {
              variant: "tonal",
              class: "fill-height"
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, null, {
                  default: _withCtx$1(() => [
                    _createElementVNode$1("div", _hoisted_3$1, [
                      _createVNode$1(_component_v_icon, {
                        size: 16,
                        color: proxyOn.value ? 'success' : 'error',
                        class: "mr-1"
                      }, {
                        default: _withCtx$1(() => [...(_cache[6] || (_cache[6] = [
                          _createTextVNode$1("mdi-circle", -1)
                        ]))]),
                        _: 1
                      }, 8, ["color"]),
                      _cache[7] || (_cache[7] = _createTextVNode$1(" 反代端口 ", -1))
                    ]),
                    _createElementVNode$1("div", {
                      class: _normalizeClass(["text-h6 mt-1", proxyOn.value ? 'text-success' : 'text-error'])
                    }, _toDisplayString$1(proxyOn.value ? proxyPort.value : '未启用'), 3),
                    _createElementVNode$1("div", _hoisted_4$1, _toDisplayString$1(status.value?.emby_url || '未配置回源'), 1)
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
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, {
              variant: "tonal",
              class: "fill-height"
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, null, {
                  default: _withCtx$1(() => [
                    _createElementVNode$1("div", _hoisted_5$1, [
                      _createVNode$1(_component_v_icon, {
                        size: 16,
                        color: cacheOn.value ? 'success' : 'error',
                        class: "mr-1"
                      }, {
                        default: _withCtx$1(() => [...(_cache[8] || (_cache[8] = [
                          _createTextVNode$1("mdi-circle", -1)
                        ]))]),
                        _: 1
                      }, 8, ["color"]),
                      _cache[9] || (_cache[9] = _createTextVNode$1(" 字幕缓存 ", -1))
                    ]),
                    _createElementVNode$1("div", {
                      class: _normalizeClass(["text-h6 mt-1", cacheOn.value ? 'text-success' : 'text-error'])
                    }, [
                      _createTextVNode$1(_toDisplayString$1(cacheTotal.value) + " ", 1),
                      _cache[10] || (_cache[10] = _createElementVNode$1("span", { class: "text-caption text-medium-emphasis" }, "条", -1))
                    ], 2),
                    _createElementVNode$1("div", _hoisted_6$1, "内存 " + _toDisplayString$1(status.value?.cache?.mem_items ?? 0) + " · 磁盘 " + _toDisplayString$1(status.value?.cache?.disk_files ?? 0), 1)
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
          sm: "6",
          md: "3"
        }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_card, {
              variant: "tonal",
              class: "fill-height"
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, null, {
                  default: _withCtx$1(() => [
                    _createElementVNode$1("div", _hoisted_7$1, [
                      _createVNode$1(_component_v_icon, {
                        size: 16,
                        color: missTotal.value === 0 ? 'success' : 'error',
                        class: "mr-1"
                      }, {
                        default: _withCtx$1(() => [...(_cache[11] || (_cache[11] = [
                          _createTextVNode$1("mdi-circle", -1)
                        ]))]),
                        _: 1
                      }, 8, ["color"]),
                      _cache[12] || (_cache[12] = _createTextVNode$1(" 缺失字体 ", -1))
                    ]),
                    _createElementVNode$1("div", {
                      class: _normalizeClass(["text-h6 mt-1", missTotal.value === 0 ? 'text-success' : 'text-error'])
                    }, [
                      _createTextVNode$1(_toDisplayString$1(missTotal.value) + " ", 1),
                      _cache[13] || (_cache[13] = _createElementVNode$1("span", { class: "text-caption text-medium-emphasis" }, "种", -1))
                    ], 2),
                    _createElementVNode$1("div", _hoisted_8$1, "最近 " + _toDisplayString$1(status.value?.miss_count ?? 0) + " 次命中", 1)
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
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mt-4"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center" }, {
          default: _withCtx$1(() => [
            _cache[15] || (_cache[15] = _createTextVNode$1(" 缺失字体记录 ", -1)),
            _createVNode$1(_component_v_spacer),
            _createVNode$1(_component_v_btn, {
              size: "small",
              color: "error",
              variant: "flat",
              density: "comfortable",
              "prepend-icon": "mdi-delete-outline",
              disabled: busy.value || missing.value.length === 0,
              onClick: clearMissing
            }, {
              default: _withCtx$1(() => [...(_cache[14] || (_cache[14] = [
                _createTextVNode$1("清除", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"])
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, { class: "fia-list-wrap" }, {
          default: _withCtx$1(() => [
            (missing.value.length)
              ? (_openBlock$1(), _createBlock$1(_component_v_table, {
                  key: 0,
                  density: "compact"
                }, {
                  default: _withCtx$1(() => [
                    _cache[16] || (_cache[16] = _createElementVNode$1("thead", null, [
                      _createElementVNode$1("tr", null, [
                        _createElementVNode$1("th", null, "字体名"),
                        _createElementVNode$1("th", { class: "text-center" }, "出现次数"),
                        _createElementVNode$1("th", { class: "text-center" }, "最近出现")
                      ])
                    ], -1)),
                    _createElementVNode$1("tbody", null, [
                      (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(missing.value, (m) => {
                        return (_openBlock$1(), _createElementBlock$1("tr", {
                          key: m.font_name
                        }, [
                          _createElementVNode$1("td", null, _toDisplayString$1(m.font_name), 1),
                          _createElementVNode$1("td", _hoisted_9$1, _toDisplayString$1(m.count), 1),
                          _createElementVNode$1("td", _hoisted_10$1, _toDisplayString$1(fmtTime(m.last_seen)), 1)
                        ]))
                      }), 128))
                    ])
                  ]),
                  _: 1
                }))
              : (_openBlock$1(), _createBlock$1(_component_v_alert, {
                  key: 1,
                  type: "info",
                  variant: "tonal",
                  density: "compact",
                  class: "mb-0"
                }, {
                  default: _withCtx$1(() => [...(_cache[17] || (_cache[17] = [
                    _createTextVNode$1("暂无缺失字体记录", -1)
                  ]))]),
                  _: 1
                }))
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode$1(_component_v_card, {
      variant: "tonal",
      class: "mt-4 fia-log-card"
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, {
              size: 14,
              color: logBad.value ? 'error' : logWarn.value ? 'warning' : 'success',
              class: "mr-1"
            }, {
              default: _withCtx$1(() => [...(_cache[18] || (_cache[18] = [
                _createTextVNode$1("mdi-circle", -1)
              ]))]),
              _: 1
            }, 8, ["color"]),
            _cache[20] || (_cache[20] = _createTextVNode$1(" 插件日志 ", -1)),
            _createVNode$1(_component_v_spacer),
            _createVNode$1(_component_v_btn, {
              size: "small",
              color: "error",
              variant: "flat",
              density: "comfortable",
              "prepend-icon": "mdi-delete-outline",
              disabled: busy.value,
              class: "mr-1",
              onClick: clearLogs
            }, {
              default: _withCtx$1(() => [...(_cache[19] || (_cache[19] = [
                _createTextVNode$1("清除", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"])
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_card_text, { class: "pa-0 fia-log-body" }, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", {
              ref_key: "logBox",
              ref: logBox,
              class: "fia-log-box",
              onScroll: onLogScroll
            }, [
              (logs.value.length === 0)
                ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_11, " 暂无插件日志（播放字幕产生 FontInAssProxy 日志后显示） "))
                : (_openBlock$1(), _createBlock$1(_component_v_table, {
                    key: 1,
                    density: "compact",
                    class: "fia-log-table"
                  }, {
                    default: _withCtx$1(() => [
                      _createElementVNode$1("tbody", null, [
                        (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(logs.value, (l) => {
                          return (_openBlock$1(), _createElementBlock$1("tr", {
                            key: l.id
                          }, [
                            _createElementVNode$1("td", _hoisted_12, _toDisplayString$1(l.time), 1),
                            _createElementVNode$1("td", null, [
                              _createVNode$1(_component_v_chip, {
                                size: "x-small",
                                variant: "tonal",
                                class: "mr-2 fia-log-level",
                                color: l.level === 'error' ? 'error' : l.level === 'warning' ? 'warning' : 'info'
                              }, {
                                default: _withCtx$1(() => [
                                  _createTextVNode$1(_toDisplayString$1((l.level || 'info').toUpperCase()), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"]),
                              _createElementVNode$1("span", _hoisted_13, _toDisplayString$1(l.message), 1)
                            ])
                          ]))
                        }), 128))
                      ])
                    ]),
                    _: 1
                  }))
            ], 544)
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
const Status = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-7cca8b46"]]);

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createBlock:_createBlock,createCommentVNode:_createCommentVNode,resolveDynamicComponent:_resolveDynamicComponent,KeepAlive:_KeepAlive,createSlots:_createSlots} = await importShared('vue');


const _hoisted_1 = { class: "ffa-app" };
const _hoisted_2 = { class: "ffa-layout" };
const _hoisted_3 = { class: "ffa-nav ffa-card-bg" };
const _hoisted_4 = { class: "ffa-nav-header" };
const _hoisted_5 = { class: "ffa-app-title" };
const _hoisted_6 = { class: "ffa-content" };
const _hoisted_7 = { class: "ffa-mobile-nav ffa-card-bg" };
const _hoisted_8 = { class: "ffa-sheet-card ffa-card-bg" };
const _hoisted_9 = {
  key: 0,
  class: "ffa-disabled-mask"
};
const _hoisted_10 = { class: "ffa-disabled-card ffa-card-bg" };

const {computed,inject,onMounted,ref,getCurrentInstance} = await importShared('vue');

// 宿主注入的能力（对齐 zitifenlei 契约）

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'FontInAssProxy' },
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['action', 'layout', 'switch', 'close', 'save'],
  setup(__props, { expose: __expose, emit: __emit }) {

const props = __props;
const emit = __emit;
const toast = inject('moviepilot:toast', null);
const instance = getCurrentInstance();

// 导航项：设置页入口放在导航里，不再“看不见”
const navItems = [
  { key: 'status', title: '状态', icon: 'mdi-view-dashboard-outline' },
  { key: 'settings', title: '设置', icon: 'mdi-cog-outline' },
];

const active = ref('status');
const loading = ref(true);
const mobileSheet = ref(false);

// 当前导航项（移动端顶部栏展示）
const currentNavItem = computed(() => navItems.find(item => item.key === active.value) || navItems[0]);

function gotoNav(key) {
  active.value = key;
  mobileSheet.value = false;
}

// 全局配置：以 GET /config 为权威（重启/热生效后重新拉取）
const pluginConfig = ref({
  enabled: true,
  ...(props.initialConfig || {}),
});
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

// 设置页保存回调：更新本地开关状态（停用遮罩即时生效），转发宿主 save
function onConfigSave() {
  emit('save');
  initConfig();
}

// 视图映射：点击导航切换
const views = {
  status: Status,
  settings: _sfc_main$2,
};
const currentView = computed(() => views[active.value] || Status);

onMounted(async () => {
  // 通知宿主：最大需要 68rem 宽度（与字体分类管家一致）
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
  if (toast && typeof toast[type] === 'function') toast[type](message);
}

// 关闭插件页（右上角 X）
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
                _createTextVNode("mdi-subtitles-outline", -1)
              ]))]),
              _: 1
            }),
            _cache[4] || (_cache[4] = _createTextVNode(" 字幕字体代理 ", -1))
          ]),
          _cache[5] || (_cache[5] = _createElementVNode("div", { class: "ffa-app-subtitle" }, "FontInAssProxy", -1))
        ]),
        _createVNode(_component_v_divider, { class: "ffa-divider" }),
        _createVNode(_component_v_list, { class: "ffa-nav-list" }, {
          default: _withCtx(() => [
            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
              return _createVNode(_component_v_list_item, {
                key: item.key,
                active: active.value === item.key,
                class: "ffa-nav-item",
                onClick: $event => (active.value = item.key)
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_list_item_title, { class: "ffa-nav-text" }, {
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
              class: "ffa-loading"
            }))
          : (_openBlock(), _createBlock(_KeepAlive, { key: 1 }, [
              (_openBlock(), _createBlock(_resolveDynamicComponent(currentView.value), {
                api: props.api,
                onSave: onConfigSave
              }, null, 40, ["api"]))
            ], 1024))
      ])
    ]),
    _createElementVNode("div", _hoisted_7, [
      _createElementVNode("button", {
        type: "button",
        class: "ffa-mnav-current",
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
          class: "ffa-mnav-caret"
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
      class: "ffa-sheet"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", _hoisted_8, [
          _cache[8] || (_cache[8] = _createElementVNode("div", { class: "ffa-sheet-title" }, "切换页面", -1)),
          _createVNode(_component_v_divider, { class: "ffa-divider" }),
          _createVNode(_component_v_list, { class: "ffa-sheet-list" }, {
            default: _withCtx(() => [
              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(navItems, (item) => {
                return _createVNode(_component_v_list_item, {
                  key: item.key,
                  active: active.value === item.key,
                  color: "primary",
                  rounded: "lg",
                  class: "ffa-sheet-item",
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
      class: "ffa-close-btn",
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
            _cache[12] || (_cache[12] = _createElementVNode("div", { class: "ffa-disabled-title" }, "插件已停用", -1)),
            _cache[13] || (_cache[13] = _createElementVNode("div", { class: "ffa-disabled-desc" }, "插件已被关闭，代理链路暂停，其他页面暂不可用", -1)),
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
          class: "ffa-disabled-banner"
        }, {
          default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
            _createTextVNode(" 插件当前已停用：字幕请求将原样透传，请在本页开启「启用插件」并保存。 ", -1)
          ]))]),
          _: 1
        }))
      : _createCommentVNode("", true)
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-6adbe0b1"]]);

export { Page as default };
