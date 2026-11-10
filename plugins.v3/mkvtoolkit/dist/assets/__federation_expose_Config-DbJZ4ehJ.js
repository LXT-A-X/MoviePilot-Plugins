import { importShared } from './__federation_fn_import-JrT3xvdd.js';

/**
 * MkvToolkit - 宿主 API 封装
 * 通过宿主注入的 api 模块调用后端接口：/api/v1/plugin/MkvToolkit/xxx
 * 后端统一返回 { success, message, data }
 */
const PLUGIN_ID = 'MkvToolkit';

/**
 * 统一解包后端响应：
 * - {success:false} 抛错（message 可直接展示给用户）
 * - {success:true,data} 返回 data
 * - 直接返回业务数据时原样返回
 */
function unwrap(response) {
  const body = response && Object.prototype.hasOwnProperty.call(response, 'success')
    ? response
    : (response?.data ?? response);
  if (body?.success === false) {
    const err = new Error(body.message || '请求失败');
    err.code = body.code;
    // 上传超限等场景后端会带 data（size / limit），保留给调用方
    err.data = body.data;
    throw err
  }
  return body?.data ?? body ?? {}
}

function createApi(props) {
  const pluginId = props?.pluginId || PLUGIN_ID;
  const client = props?.api || {};
  const withPlugin = (path) => `plugin/${pluginId}${path}`;

  return {
    async get(path, params = {}) {
      const res = await client.get(withPlugin(path), { params });
      return unwrap(res)
    },
    async post(path, data = {}) {
      const res = await client.post(withPlugin(path), data);
      return unwrap(res)
    },
    async put(path, data = {}) {
      const res = await client.put(withPlugin(path), data);
      return unwrap(res)
    },
    /**
     * 上传小文件（multipart/form-data，字段名 file）
     * 超限时后端返回 success=false，错误对象带 message 与 data{size,limit}
     */
    async upload(path, formData, params = {}) {
      const res = await client.post(withPlugin(path), formData, {
        params,
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return unwrap(res)
    },
  }
}

/**
 * MkvToolkit - 通用格式化与常量
 */


// 语言下拉选项：显示「简体中文 (zh-Hans)」，value 使用 ISO 639-2 / BCP47 代码
const LANGUAGE_ITEMS = [
  { title: '未指定 (und)', value: 'und' },
  { title: '简体中文 (zh-Hans)', value: 'zh-Hans' },
  { title: '繁体中文 (zh-Hant)', value: 'zh-Hant' },
  { title: '日语 (jpn)', value: 'jpn' },
  { title: '英语 (eng)', value: 'eng' },
  { title: '韩语 (kor)', value: 'kor' },
  { title: '粤语 (yue)', value: 'yue' },
  { title: '法语 (fra)', value: 'fra' },
  { title: '法语 (fre)', value: 'fre' },
  { title: '德语 (deu)', value: 'deu' },
  { title: '德语 (ger)', value: 'ger' },
  { title: '西班牙语 (spa)', value: 'spa' },
  { title: '俄语 (rus)', value: 'rus' },
  { title: '葡萄牙语 (por)', value: 'por' },
  { title: '意大利语 (ita)', value: 'ita' },
  { title: '泰语 (tha)', value: 'tha' },
  { title: '越南语 (vie)', value: 'vie' },
  { title: '阿拉伯语 (ara)', value: 'ara' },
  { title: '印地语 (hin)', value: 'hin' },
  { title: '马来语 (msa)', value: 'msa' },
  { title: '马来语 (may)', value: 'may' },
  { title: '印尼语 (ind)', value: 'ind' },
  { title: '菲律宾语 (tgl)', value: 'tgl' },
  { title: '土耳其语 (tur)', value: 'tur' },
];

const SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.ssa', '.vtt', '.sup', '.mks'];
const AUDIO_EXTENSIONS = ['.aac', '.flac', '.mka', '.ac3', '.dts', '.mp3', '.m4a', '.eac3', '.truehd'];
const FONT_EXTENSIONS = ['.ttf', '.otf', '.ttc'];

// 字体压缩包：zip/tar 内置可解；7z/rar 依赖容器内 7z / unrar
const ARCHIVE_EXTENSIONS = [
  '.zip', '.7z', '.rar', '.tar', '.tgz', '.tbz2', '.txz',
  '.tar.gz', '.tar.bz2', '.tar.xz',
];

/** 判断文件名是否为支持的压缩包（含 .tar.gz 这类双后缀）。 */
function isArchiveName(name) {
  const lower = String(name || '').toLowerCase();
  return ARCHIVE_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

const SUBTITLE_ENCODINGS = [
  { title: '自动探测', value: 'auto' },
  { title: 'UTF-8', value: 'utf-8' },
  { title: 'GBK', value: 'gbk' },
  { title: 'BIG5', value: 'big5' },
];

// 字节数格式化：B / KB / MB / GB / TB
function fmtBytes(value, digits = 1) {
  if (value == null || value === '' || Number.isNaN(Number(value))) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let num = Number(value);
  let index = 0;
  while (num >= 1024 && index < units.length - 1) {
    num /= 1024;
    index += 1;
  }
  return `${num.toFixed(index ? digits : 0)} ${units[index]}`
}

// 秒 → mm:ss / h:mm:ss
function fmtDuration(seconds, withMs = false) {
  const total = Number(seconds);
  if (!Number.isFinite(total) || total < 0) return '—'
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  const ms = Math.round((total - Math.floor(total)) * 1000);
  const pad = (n) => String(n).padStart(2, '0');
  const base = hours
    ? `${hours}:${pad(minutes)}:${pad(secs)}`
    : `${pad(minutes)}:${pad(secs)}`;
  return withMs ? `${base}.${String(ms).padStart(3, '0')}` : base
}

// 历史/任务里的时间字符串 → 本地可读（兼容 ISO 与 "YYYY-MM-DD HH:mm:ss"）
function fmtDateTime(value, short = false) {
  if (!value) return '—'
  const text = String(value);
  let date = new Date(text);
  if (Number.isNaN(date.getTime())) date = new Date(text.replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return text
  const pad = (n) => String(n).padStart(2, '0');
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  if (short) return `${month}-${day} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  return `${date.getFullYear()}-${month}-${day} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

// 取文件名（兼容 / 与 \ 分隔）
function baseName(path) {
  if (!path) return ''
  const normalized = String(path).replaceAll('\\', '/');
  const index = normalized.lastIndexOf('/');
  return index >= 0 ? normalized.slice(index + 1) : normalized
}

// 取扩展名（小写，含点）
function extName(name) {
  const base = baseName(name);
  const index = base.lastIndexOf('.');
  return index > 0 ? base.slice(index).toLowerCase() : ''
}

// 去掉扩展名
function stripExt(name) {
  const base = baseName(name);
  const index = base.lastIndexOf('.');
  return index > 0 ? base.slice(0, index) : base
}

// 声道数 → 2.0 / 5.1 这种显示
function fmtChannels(track) {
  const channels = Number(track?.channels || 0);
  if (!channels) return '—'
  if (channels === 1) return '1.0'
  if (channels === 2) return '2.0'
  if (channels === 6) return '5.1'
  if (channels === 8) return '7.1'
  return `${channels}ch`
}

// 编码名统一大写（hevc → HEVC）
function codecLabel(track) {
  return String(track?.codec || track?.codec_detail || '').toUpperCase() || '—'
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,createVNode:_createVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,withKeys:_withKeys} = await importShared('vue');


const _hoisted_1 = { class: "config-page" };
const _hoisted_2 = { class: "form-row" };
const _hoisted_3 = { class: "value" };
const _hoisted_4 = { class: "form-row" };
const _hoisted_5 = { class: "value" };
const _hoisted_6 = { class: "value" };
const _hoisted_7 = ["title"];
const _hoisted_8 = {
  key: 1,
  class: "sub"
};
const _hoisted_9 = { class: "form-row" };
const _hoisted_10 = { class: "value" };
const _hoisted_11 = { class: "form-row" };
const _hoisted_12 = { class: "value" };
const _hoisted_13 = { class: "sub" };
const _hoisted_14 = { class: "form-row" };
const _hoisted_15 = { class: "value" };
const _hoisted_16 = {
  key: 0,
  class: "form-row"
};
const _hoisted_17 = { class: "value" };
const _hoisted_18 = { class: "form-row" };
const _hoisted_19 = { class: "value" };
const _hoisted_20 = { class: "form-row" };
const _hoisted_21 = { class: "value" };
const _hoisted_22 = { class: "root-list" };
const _hoisted_23 = ["onClick"];
const _hoisted_24 = {
  key: 0,
  class: "sub"
};
const _hoisted_25 = { class: "form-row" };
const _hoisted_26 = { class: "value" };
const _hoisted_27 = { class: "form-row" };
const _hoisted_28 = { class: "value" };
const _hoisted_29 = { class: "form-row" };
const _hoisted_30 = { class: "value" };
const _hoisted_31 = { class: "form-row" };
const _hoisted_32 = { class: "value" };
const _hoisted_33 = { class: "form-row" };
const _hoisted_34 = { class: "value" };
const _hoisted_35 = { class: "form-row" };
const _hoisted_36 = { class: "value" };
const _hoisted_37 = { class: "form-row" };
const _hoisted_38 = { class: "value" };
const _hoisted_39 = ["title"];
const _hoisted_40 = { class: "sub" };
const _hoisted_41 = { class: "form-row" };
const _hoisted_42 = { class: "value" };
const _hoisted_43 = { class: "form-row" };
const _hoisted_44 = { class: "value" };
const _hoisted_45 = { class: "form-row" };
const _hoisted_46 = { class: "value" };
const _hoisted_47 = { class: "form-row" };
const _hoisted_48 = { class: "value" };
const _hoisted_49 = { class: "form-row" };
const _hoisted_50 = { class: "value" };
const _hoisted_51 = { class: "form-row" };
const _hoisted_52 = { class: "value" };
const _hoisted_53 = { class: "sub" };
const _hoisted_54 = { class: "form-row" };
const _hoisted_55 = { class: "value" };
const _hoisted_56 = { class: "form-row" };
const _hoisted_57 = { class: "value" };
const _hoisted_58 = {
  key: 0,
  class: "diagnose-list"
};
const _hoisted_59 = { class: "diagnose-name" };
const _hoisted_60 = { class: "diagnose-detail" };
const _hoisted_61 = {
  key: 1,
  class: "diagnose-note"
};
const _hoisted_62 = { class: "config-actions" };
const _hoisted_63 = { class: "dialog-head" };
const _hoisted_64 = { class: "dialog-title" };
const _hoisted_65 = { class: "dialog-body" };
const _hoisted_66 = { class: "sub mb-3" };
const _hoisted_67 = {
  key: 1,
  class: "install-error"
};
const _hoisted_68 = { class: "install-state" };
const _hoisted_69 = {
  key: 0,
  class: "install-log"
};
const _hoisted_70 = {
  key: 1,
  class: "install-error"
};
const _hoisted_71 = { class: "dialog-foot" };
const _hoisted_72 = { class: "dialog-head" };
const _hoisted_73 = { class: "dialog-body" };
const _hoisted_74 = { class: "dialog-foot" };
const _hoisted_75 = { class: "dialog-head" };
const _hoisted_76 = { class: "dialog-body" };
const _hoisted_77 = { class: "dialog-foot" };

const {computed,getCurrentInstance,inject,onBeforeUnmount,onMounted,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MkvToolkit' },
  initialConfig: { type: Object, default: () => ({}) },
  // 作为 AppPage 设置 Tab 内嵌时不要再改宿主 layout（AppPage 已按分栏宽度申请）
  embedded: { type: Boolean, default: false },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

/**
 * MkvToolkit 设置页（同时作为 ./Config 联邦暴露）
 * 引擎检测与安装 / 根目录 / 输出与备份 / 字幕与语言 / 执行与校验 / 上传 / 诊断
 * 配置读写统一走 GET /config、POST /config
 */
const props = __props;

const emit = __emit;
const toast = inject('moviepilot:toast', null);
const instance = getCurrentInstance();
const api = createApi(props);

const DEFAULTS = {
  enabled: true,
  roots: [],
  engine_mode: 'auto',
  mkvmerge_path: '',
  mkvpropedit_path: '',
  mkvextract_path: '',
  ffmpeg_path: '',
  output_mode: 'dir',
  output_dir: '/config/plugins/MkvToolkit/output',
  backup_dir: '/config/plugins/MkvToolkit/backup',
  backup_keep: 3,
  subtitle_after: 'keep',
  subtitle_encoding: 'auto',
  language_map: {
    '.zh': 'chi',
    '.chs': 'chi',
    '.cht': 'chi',
    '.jpn': 'jpn',
    '.eng': 'eng',
    '.yue': 'yue',
  },
  concurrency: 1,
  validation_tolerance: 2,
  strict_duration_check: false,
  history_keep: 200,
  upload_max_mb: 50,
  allow_ffmpeg_fallback: false,
  auto_subtitle: false,
  auto_audio: false,
  auto_fonts: false,
};

const ENGINE_KEYS = [
  { key: 'mkvmerge', label: 'mkvmerge', required: true, tip: '封装 / 轨道管理主引擎' },
  { key: 'mkvpropedit', label: 'mkvpropedit', required: false, tip: '只改元数据（标题/语言）时用' },
  { key: 'mkvextract', label: 'mkvextract', required: false, tip: '章节/附件提取用' },
  { key: 'ffprobe', label: 'ffprobe', required: false, tip: '探测兜底' },
  { key: 'ffmpeg', label: 'ffmpeg', required: false, tip: '降级封装（能力减配）' },
];

const OUTPUT_MODES = [
  { title: '输出到目录', value: 'dir' },
  { title: '原地替换', value: 'replace' },
];
const SUBTITLE_AFTER = [
  { title: '保留', value: 'keep' },
  { title: '移到归档目录', value: 'archive' },
  { title: '删除', value: 'delete' },
];
const SUBTITLE_ENCODINGS = [
  { title: '自动探测', value: 'auto' },
  { title: 'UTF-8', value: 'utf-8' },
  { title: 'GBK', value: 'gbk' },
  { title: 'BIG5', value: 'big5' },
];
const ENGINE_MODES = [
  { title: '自动（优先 mkvmerge）', value: 'auto' },
  { title: '仅 mkvmerge', value: 'mkvmerge' },
  { title: '仅 ffmpeg（降级）', value: 'ffmpeg' },
];
const INSTALL_METHODS = [
  { title: 'apt 安装', value: 'apt', desc: '从 Debian 源安装 mkvtoolnix（官方镜像 trixie 源为 92.0）' },
  { title: 'AppImage 解包', value: 'appimage', desc: '下载官方 AppImage 并解包到插件数据目录' },
  { title: '手动指定路径', value: 'path', desc: '已在宿主机放好二进制时，直接指定 mkvmerge 路径' },
];

const cfg = ref({ ...DEFAULTS, ...(props.initialConfig || {}) });
const status = ref({});
const loading = ref(true);
const saving = ref(false);
const error = ref('');

// ---------------- 引擎安装 ----------------
const installOpen = ref(false);
const installMethod = ref('apt');
const installTarget = ref('all');
const installPath = ref('');
const installStarted = ref(false);
const installRunning = ref(false);
const installOk = ref(true);
const installLog = ref('');
const installError = ref('');
let installTimer = null;

// ---------------- 根目录 ----------------
const rootDialog = ref(false);
const newRoot = ref('');

// ---------------- 语言映射 ----------------
const languageDialog = ref(false);
const languageText = ref('');

// ---------------- 诊断 ----------------
const diagnoseLoading = ref(false);
const diagnoseResults = ref([]);
const diagnoseNote = ref('');

const engine = computed(() => status.value?.engine || {});
const engineInstall = computed(() => status.value?.engine_install || {});
// 压缩包解压工具（7z/unrar）状态：zip/tar 内置，7z/rar 依赖系统工具
const archiveTools = computed(() => status.value?.archive?.tools || {});
const archive7z = computed(() => Boolean(archiveTools.value['7z']));
const archiveUnrar = computed(() => Boolean(archiveTools.value.unrar));
// rar 可以用 unrar，也可以直接用 7z 解压
const archiveRar = computed(() => archiveUnrar.value || archive7z.value);
const TARGET_LABELS = {
  all: '全部引擎 + 压缩包工具',
  mkvmerge: 'mkvmerge',
  mkvpropedit: 'mkvpropedit',
  mkvextract: 'mkvextract',
  ffmpeg: 'ffmpeg',
  ffprobe: 'ffprobe',
  '7z': '7z 解压工具',
  unrar: 'unrar 解压工具',
};
const installTargetLabel = computed(() => TARGET_LABELS[installTarget.value] || '引擎');
const engineRows = computed(() =>
  ENGINE_KEYS.map((item) => {
    const info = engine.value[item.key] || {};
    const configured = cfg.value[`${item.key}_path`] || '';
    return {
      ...item,
      ok: Boolean(info.ok),
      version: info.version || '',
      path: info.path || '',
      configured,
    }
  }),
);
const mkvReady = computed(() => {
  const mode = engine.value.mode;
  if (mode === 'none') return false
  return Boolean(engine.value.mkvmerge?.ok) || mode === 'ffmpeg'
});
const languageMapCount = computed(() => Object.keys(cfg.value.language_map || {}).length);

function toastMsg(kind, message) {
  if (toast && typeof toast[kind] === 'function') toast[kind](message);
}

async function loadStatus() {
  try {
    status.value = await api.get('/status');
    const info = status.value?.engine_install || {};
    if (info.running && !installRunning.value) {
      installRunning.value = true;
      installStarted.value = true;
      installLog.value = info.log_tail || '';
      scheduleInstallPoll();
    }
  } catch (err) {
    // 状态读取失败不阻塞设置页
  }
}

async function loadConfig() {
  loading.value = true;
  error.value = '';
  try {
    const data = await api.get('/config');
    cfg.value = { ...DEFAULTS, ...(props.initialConfig || {}), ...(data || {}) };
    cfg.value.roots = Array.isArray(cfg.value.roots) ? cfg.value.roots : [];
    cfg.value.language_map = { ...DEFAULTS.language_map, ...(cfg.value.language_map || {}) };
  } catch (err) {
    error.value = err.message || '读取配置失败';
    toastMsg('error', `读取配置失败：${err.message}`);
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  error.value = '';
  try {
    const payload = {
      ...cfg.value,
      roots: [...(cfg.value.roots || [])],
      language_map: { ...(cfg.value.language_map || {}) },
    };
    const saved = await api.post('/config', payload);
    cfg.value = { ...DEFAULTS, ...cfg.value, ...(saved || {}) };
    emit('save', { ...cfg.value });
    toastMsg('success', '配置已保存');
  } catch (err) {
    error.value = err.message;
    toastMsg('error', `保存失败：${err.message}`);
  } finally {
    saving.value = false;
  }
}

async function checkEngine() {
  try {
    const data = await api.post('/engine/check');
    status.value = { ...status.value, engine: data || {} };
    toastMsg('success', mkvReady.value ? '引擎检测完成' : '未检测到 MKVToolNix');
  } catch (err) {
    toastMsg('error', `检测失败：${err.message}`);
  }
}

function openInstall(method, target = 'all') {
  installTarget.value = target;
  // 7z/unrar 只能通过 apt 安装
  installMethod.value = target === '7z' || target === 'unrar' ? 'apt' : method;
  installPath.value = '';
  installStarted.value = false;
  installRunning.value = false;
  installLog.value = '';
  installError.value = '';
  installOk.value = true;
  installOpen.value = true;
}

function currentMethodDesc() {
  return INSTALL_METHODS.find((item) => item.value === installMethod.value) || INSTALL_METHODS[0]
}

async function startInstall() {
  if (installMethod.value === 'path' && !installPath.value.trim()) {
    installError.value = '请填写 mkvmerge 可执行文件的绝对路径';
    return
  }
  installError.value = '';
  try {
    const payload = { method: installMethod.value, target: installTarget.value };
    if (installMethod.value === 'path') payload.path = installPath.value.trim();
    await api.post('/engine/install', payload);
    installStarted.value = true;
    installRunning.value = true;
    installLog.value = '安装任务已启动，正在等待日志…';
    scheduleInstallPoll();
  } catch (err) {
    installError.value = err.message || '安装启动失败';
  }
}

function scheduleInstallPoll() {
  if (installTimer) clearTimeout(installTimer);
  installTimer = setTimeout(pollInstall, 1000);
}

async function pollInstall() {
  try {
    const data = await api.get('/status');
    status.value = data || {};
    const info = data?.engine_install || {};
    installRunning.value = Boolean(info.running);
    installOk.value = info.ok !== false;
    installLog.value = info.log_tail || installLog.value;
    if (installRunning.value) {
      scheduleInstallPoll();
      return
    }
    // 安装结束：重新检测引擎
    installStarted.value = true;
    if (installOk.value) {
      toastMsg('success', `${installTargetLabel.value} 安装完成`);
      try {
        const checked = await api.post('/engine/check');
        status.value = { ...status.value, engine: checked || {} };
      } catch (err) {
        // 忽略二次检测失败
      }
    } else {
      toastMsg('error', '引擎安装失败，请查看日志');
    }
  } catch (err) {
    installError.value = err.message || '读取安装进度失败';
    installRunning.value = false;
  }
}

function closeInstall() {
  installOpen.value = false;
}

// ---------------- 根目录 ----------------
function addRoot() {
  const value = newRoot.value.trim().replace(/\/+$/, '');
  if (!value) return
  if (!value.startsWith('/')) {
    toastMsg('error', '根目录必须是容器内的绝对路径，例如 /media');
    return
  }
  if ((cfg.value.roots || []).includes(value)) {
    toastMsg('warning', '该根目录已存在');
    return
  }
  cfg.value.roots = [...(cfg.value.roots || []), value];
  newRoot.value = '';
  rootDialog.value = false;
}

function removeRoot(root) {
  cfg.value.roots = (cfg.value.roots || []).filter((item) => item !== root);
}

// ---------------- 语言映射 ----------------
function openLanguage() {
  languageText.value = Object.entries(cfg.value.language_map || {})
    .map(([ext, lang]) => `${ext}=${lang}`)
    .join('\n');
  languageDialog.value = true;
}

function saveLanguage() {
  const next = {};
  for (const line of String(languageText.value || '').split('\n')) {
    const text = line.trim();
    if (!text || text.startsWith('#')) continue
    const index = text.lastIndexOf('=');
    if (index <= 0) continue
    const ext = text.slice(0, index).trim();
    const lang = text.slice(index + 1).trim();
    if (ext && lang) next[ext] = lang;
  }
  cfg.value.language_map = next;
  languageDialog.value = false;
  toastMsg('success', `语言映射已更新（${Object.keys(next).length} 条），保存后生效`);
}

function languageHint() {
  const entries = Object.entries(cfg.value.language_map || {});
  if (!entries.length) return '未配置'
  return entries.map(([ext, lang]) => `${ext} → ${lang}`).join('　')
}

// ---------------- 诊断 ----------------
async function runDiagnose() {
  diagnoseLoading.value = true;
  diagnoseResults.value = [];
  diagnoseNote.value = '';
  const results = [];
  const push = (name, ok, detail) => results.push({ name, ok, detail });
  try {
    // 契约里没有诊断接口，后端若实现 /diagnose 则优先使用
    let remote = null;
    try {
      remote = await api.post('/diagnose');
    } catch (err) {
      remote = null;
    }
    if (remote && Array.isArray(remote.checks) && remote.checks.length) {
      diagnoseResults.value = remote.checks.map((item) => ({
        name: item.name || item.code || '检查项',
        ok: item.ok !== false,
        detail: item.detail || item.message || '',
      }));
      diagnoseNote.value = remote.message || '诊断完成';
      return
    }

    // 后端 /diagnose 的真实结构：engine / mode / is_root / data_dir / roots / upload_max_mb
    if (remote && remote.engine) {
      const eng = remote.engine || {};
      push(
        'mkvmerge',
        Boolean(eng.mkvmerge?.ok),
        eng.mkvmerge?.ok ? `${eng.mkvmerge.version || ''} ${eng.mkvmerge.path || ''}` : '未找到，需在设置里安装',
      );
      push(
        'mkvpropedit',
        Boolean(eng.mkvpropedit?.ok),
        eng.mkvpropedit?.ok ? `${eng.mkvpropedit.version || ''}` : '缺失（只改元数据时会回退重封装）',
      );
      push(
        'mkvextract',
        Boolean(eng.mkvextract?.ok),
        eng.mkvextract?.ok ? `${eng.mkvextract.version || ''}` : '缺失（章节/附件提取可能受限）',
      );
      push('ffmpeg / ffprobe', Boolean(eng.ffmpeg?.ok) && Boolean(eng.ffprobe?.ok), `ffmpeg ${eng.ffmpeg?.version || '未检测到'}`);
      push('执行模式', String(remote.mode || 'none') !== 'none', `当前引擎：${remote.mode || 'none'}`);
      push('运行身份', Boolean(remote.is_root), remote.is_root ? 'root（权限充足）' : '非 root，注意目录权限');
      push('数据目录', Boolean(remote.data_writable), `${remote.data_dir || '—'} ${remote.data_writable ? '可写' : '不可写'}`);
      for (const root of remote.roots || []) {
        push(
          `根目录 ${root.path || '—'}`,
          Boolean(root.exists && root.writable),
          `${root.exists ? '存在' : '不存在'} · ${root.writable ? '可写' : '不可写'} · 剩余 ${fmtBytes(root.free)}`,
        );
      }
      push(
        '上传上限',
        Number(remote.upload_max_mb) > 0 && Number(remote.upload_max_mb) <= 50,
        `当前 ${remote.upload_max_mb}MB（宿主 nginx 默认 50MB）`,
      );
      diagnoseResults.value = results;
      const badRemote = results.filter((item) => !item.ok).length;
      diagnoseNote.value = `诊断完成（${remote.timestamp || '—'}）：${badRemote ? `${badRemote} 项需要注意` : '全部通过'}`;
      return
    }

    const data = await api.get('/status');
    const eng = data?.engine || {};
    push(
      'mkvmerge',
      Boolean(eng.mkvmerge?.ok),
      eng.mkvmerge?.ok ? `${eng.mkvmerge.version || ''} ${eng.mkvmerge.path || ''}` : '未找到，需在设置里安装',
    );
    push(
      'mkvpropedit',
      Boolean(eng.mkvpropedit?.ok),
      eng.mkvpropedit?.ok ? `${eng.mkvpropedit.version || ''}` : '缺失（只改元数据时会回退重封装）',
    );
    push(
      'mkvextract',
      Boolean(eng.mkvextract?.ok),
      eng.mkvextract?.ok ? `${eng.mkvextract.version || ''}` : '缺失（章节/附件提取可能受限）',
    );
    push('ffmpeg / ffprobe', Boolean(eng.ffmpeg?.ok) && Boolean(eng.ffprobe?.ok), `ffmpeg ${eng.ffmpeg?.version || '未检测到'}`);
    push('媒体根目录', (cfg.value.roots || []).length > 0, (cfg.value.roots || []).join('、') || '未配置，目录树不可用');
    push(
      '输出目录',
      cfg.value.output_mode === 'replace' ? true : Boolean(cfg.value.output_dir),
      cfg.value.output_mode === 'replace' ? '原地替换模式，输出目录不生效' : cfg.value.output_dir || '未填写',
    );
    push(
      '备份目录',
      true,
      cfg.value.backup_dir || '默认：/config/plugins/MkvToolkit/backup（留空自动使用插件数据目录）',
    );
    push('上传上限', Number(cfg.value.upload_max_mb) > 0 && Number(cfg.value.upload_max_mb) <= 50, `当前 ${cfg.value.upload_max_mb}MB（宿主 nginx 默认上限 50MB）`);
    push('并发数', Number(cfg.value.concurrency) >= 1 && Number(cfg.value.concurrency) <= 3, `当前 ${cfg.value.concurrency}`);
    push('插件状态', data?.enabled !== false, data?.enabled === false ? '插件已停用' : `版本 ${data?.version || '—'}`);
    diagnoseResults.value = results;
    const bad = results.filter((item) => !item.ok).length;
    diagnoseNote.value = bad ? `诊断完成：${bad} 项需要注意` : '诊断完成：全部通过';
  } catch (err) {
    diagnoseNote.value = `诊断失败：${err.message}`;
  } finally {
    diagnoseLoading.value = false;
  }
}

onMounted(async () => {
  if (!props.embedded) instance?.emit('layout', { maxWidth: '72rem' });
  await loadConfig();
  await loadStatus();
});

onBeforeUnmount(() => {
  if (installTimer) clearTimeout(installTimer);
  installTimer = null;
});

return (_ctx, _cache) => {
  const _component_v_skeleton_loader = _resolveComponent("v-skeleton-loader");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_dialog = _resolveComponent("v-dialog");
  const _component_v_textarea = _resolveComponent("v-textarea");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (loading.value)
      ? (_openBlock(), _createBlock(_component_v_skeleton_loader, {
          key: 0,
          type: "list-item@8"
        }))
      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
          (error.value)
            ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 0,
                type: "error",
                variant: "tonal",
                density: "compact",
                class: "mb-3",
                closable: "",
                "onClick:close": _cache[0] || (_cache[0] = $event => (error.value = ''))
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(error.value), 1)
                ]),
                _: 1
              }))
            : _createCommentVNode("", true),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[52] || (_cache[52] = _createElementVNode("div", { class: "config-card-title" }, "引擎", -1)),
              _createElementVNode("div", _hoisted_2, [
                _cache[36] || (_cache[36] = _createElementVNode("label", null, "启用插件", -1)),
                _createElementVNode("div", _hoisted_3, [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.value.enabled,
                    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((cfg.value.enabled) = $event)),
                    density: "compact",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _cache[35] || (_cache[35] = _createElementVNode("span", { class: "sub" }, "关闭后插件停止后台任务队列与相关接口，页面显示停用提示；侧栏入口保留，重新启用需到插件管理页启用并「应用保存」", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_4, [
                _cache[37] || (_cache[37] = _createElementVNode("label", null, "引擎模式", -1)),
                _createElementVNode("div", _hoisted_5, [
                  _createVNode(_component_v_select, {
                    modelValue: cfg.value.engine_mode,
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((cfg.value.engine_mode) = $event)),
                    items: ENGINE_MODES,
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-260"
                  }, null, 8, ["modelValue"])
                ])
              ]),
              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(engineRows.value, (row) => {
                return (_openBlock(), _createElementBlock("div", {
                  key: row.key,
                  class: "form-row"
                }, [
                  _createElementVNode("label", null, _toDisplayString(row.label), 1),
                  _createElementVNode("div", _hoisted_6, [
                    _createVNode(_component_v_chip, {
                      size: "x-small",
                      variant: "tonal",
                      color: row.ok ? 'success' : (row.required ? 'error' : 'warning')
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(row.ok ? (row.version || '已就绪') : '未检测到'), 1)
                      ]),
                      _: 2
                    }, 1032, ["color"]),
                    (row.path)
                      ? (_openBlock(), _createElementBlock("span", {
                          key: 0,
                          class: "mono sub ellipsis",
                          title: row.path
                        }, _toDisplayString(row.path), 9, _hoisted_7))
                      : (_openBlock(), _createElementBlock("span", _hoisted_8, _toDisplayString(row.tip), 1)),
                    (row.key !== 'ffprobe')
                      ? (_openBlock(), _createBlock(_component_v_text_field, {
                          key: 2,
                          modelValue: cfg.value[`${row.key}_path`],
                          "onUpdate:modelValue": $event => ((cfg.value[`${row.key}_path`]) = $event),
                          density: "compact",
                          variant: "outlined",
                          "hide-details": "",
                          placeholder: `自定义 ${row.label} 路径（留空=自动探测）`,
                          class: "path-input"
                        }, null, 8, ["modelValue", "onUpdate:modelValue", "placeholder"]))
                      : _createCommentVNode("", true),
                    (!row.ok)
                      ? (_openBlock(), _createBlock(_component_v_btn, {
                          key: 3,
                          size: "x-small",
                          variant: "tonal",
                          color: "primary",
                          loading: installRunning.value && installTarget.value === row.key,
                          onClick: $event => (openInstall('apt', row.key))
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(" 安装 " + _toDisplayString(row.label), 1)
                          ]),
                          _: 2
                        }, 1032, ["loading", "onClick"]))
                      : _createCommentVNode("", true)
                  ])
                ]))
              }), 128)),
              _createElementVNode("div", _hoisted_9, [
                _cache[41] || (_cache[41] = _createElementVNode("label", null, "压缩包解压", -1)),
                _createElementVNode("div", _hoisted_10, [
                  _createVNode(_component_v_chip, {
                    size: "x-small",
                    variant: "tonal",
                    color: archive7z.value ? 'success' : 'warning'
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(archive7z.value ? '7z 已就绪' : '7z 未安装'), 1)
                    ]),
                    _: 1
                  }, 8, ["color"]),
                  _createVNode(_component_v_chip, {
                    size: "x-small",
                    variant: "tonal",
                    color: archiveRar.value ? 'success' : 'warning'
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(archiveRar.value ? (archiveUnrar.value ? 'unrar 已就绪' : 'rar 可解压（7z）') : 'rar 未安装'), 1)
                    ]),
                    _: 1
                  }, 8, ["color"]),
                  (!archive7z.value)
                    ? (_openBlock(), _createBlock(_component_v_btn, {
                        key: 0,
                        size: "x-small",
                        variant: "tonal",
                        loading: installRunning.value && installTarget.value === '7z',
                        onClick: _cache[3] || (_cache[3] = $event => (openInstall('apt', '7z')))
                      }, {
                        default: _withCtx(() => [...(_cache[38] || (_cache[38] = [
                          _createTextVNode(" 安装 7z ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading"]))
                    : _createCommentVNode("", true),
                  (!archiveUnrar.value)
                    ? (_openBlock(), _createBlock(_component_v_btn, {
                        key: 1,
                        size: "x-small",
                        variant: "tonal",
                        loading: installRunning.value && installTarget.value === 'unrar',
                        onClick: _cache[4] || (_cache[4] = $event => (openInstall('apt', 'unrar')))
                      }, {
                        default: _withCtx(() => [...(_cache[39] || (_cache[39] = [
                          _createTextVNode(" 安装 unrar ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading"]))
                    : _createCommentVNode("", true),
                  _cache[40] || (_cache[40] = _createElementVNode("span", { class: "sub" }, "zip/tar 内置解压；7z/rar 有 7z 即可，unrar 是可选的备选", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_11, [
                _cache[43] || (_cache[43] = _createElementVNode("label", null, "重新检测", -1)),
                _createElementVNode("div", _hoisted_12, [
                  _createVNode(_component_v_btn, {
                    size: "small",
                    variant: "tonal",
                    "prepend-icon": "mdi-refresh",
                    onClick: checkEngine
                  }, {
                    default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                      _createTextVNode("重新检测", -1)
                    ]))]),
                    _: 1
                  }),
                  _createElementVNode("span", _hoisted_13, _toDisplayString(mkvReady.value ? '引擎可用，可以执行封装' : '缺少 mkvmerge，当前只能预览不能执行'), 1)
                ])
              ]),
              _createElementVNode("div", _hoisted_14, [
                _cache[47] || (_cache[47] = _createElementVNode("label", null, "安装 / 更新", -1)),
                _createElementVNode("div", _hoisted_15, [
                  _createVNode(_component_v_btn, {
                    size: "small",
                    color: "primary",
                    variant: "flat",
                    "prepend-icon": "mdi-download",
                    onClick: _cache[5] || (_cache[5] = $event => (openInstall('apt')))
                  }, {
                    default: _withCtx(() => [...(_cache[44] || (_cache[44] = [
                      _createTextVNode(" 一键安装全部（apt） ", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_v_btn, {
                    size: "small",
                    variant: "tonal",
                    onClick: _cache[6] || (_cache[6] = $event => (openInstall('appimage')))
                  }, {
                    default: _withCtx(() => [...(_cache[45] || (_cache[45] = [
                      _createTextVNode("AppImage 解包", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    onClick: _cache[7] || (_cache[7] = $event => (openInstall('path')))
                  }, {
                    default: _withCtx(() => [...(_cache[46] || (_cache[46] = [
                      _createTextVNode("手动指定路径", -1)
                    ]))]),
                    _: 1
                  })
                ])
              ]),
              (engineInstall.value.running)
                ? (_openBlock(), _createElementBlock("div", _hoisted_16, [
                    _cache[49] || (_cache[49] = _createElementVNode("label", null, "安装进度", -1)),
                    _createElementVNode("div", _hoisted_17, [
                      _createVNode(_component_v_progress_circular, {
                        indeterminate: "",
                        size: "16",
                        width: "2",
                        color: "primary"
                      }),
                      _cache[48] || (_cache[48] = _createElementVNode("span", { class: "sub" }, "安装进行中，可在下方诊断里查看结果", -1))
                    ])
                  ]))
                : _createCommentVNode("", true),
              _createElementVNode("div", _hoisted_18, [
                _cache[51] || (_cache[51] = _createElementVNode("label", null, "降级执行", -1)),
                _createElementVNode("div", _hoisted_19, [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.value.allow_ffmpeg_fallback,
                    "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.value.allow_ffmpeg_fallback) = $event)),
                    density: "compact",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _cache[50] || (_cache[50] = _createElementVNode("span", { class: "sub" }, "缺 mkvmerge 时允许用 ffmpeg 真执行（默认关闭，能力减配）", -1))
                ])
              ])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[55] || (_cache[55] = _createElementVNode("div", { class: "config-card-title" }, "目录", -1)),
              _createElementVNode("div", _hoisted_20, [
                _cache[54] || (_cache[54] = _createElementVNode("label", null, "媒体根目录", -1)),
                _createElementVNode("div", _hoisted_21, [
                  _createElementVNode("div", _hoisted_22, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(cfg.value.roots, (root) => {
                      return (_openBlock(), _createElementBlock("span", {
                        key: root,
                        class: "root-tag"
                      }, [
                        _createTextVNode(_toDisplayString(root) + " ", 1),
                        _createElementVNode("button", {
                          type: "button",
                          class: "root-del",
                          title: "移除",
                          onClick: $event => (removeRoot(root))
                        }, "✕", 8, _hoisted_23)
                      ]))
                    }), 128)),
                    (!cfg.value.roots || !cfg.value.roots.length)
                      ? (_openBlock(), _createElementBlock("span", _hoisted_24, "还没有根目录，插件无法浏览媒体文件"))
                      : _createCommentVNode("", true)
                  ]),
                  _createVNode(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    "prepend-icon": "mdi-plus",
                    onClick: _cache[9] || (_cache[9] = $event => (rootDialog.value = true))
                  }, {
                    default: _withCtx(() => [...(_cache[53] || (_cache[53] = [
                      _createTextVNode("添加", -1)
                    ]))]),
                    _: 1
                  })
                ])
              ]),
              _cache[56] || (_cache[56] = _createElementVNode("div", { class: "form-row" }, [
                _createElementVNode("label", null, "目录树"),
                _createElementVNode("div", { class: "value" }, [
                  _createElementVNode("span", { class: "sub" }, "只显示 .mkv；懒加载；顶部可搜索；文件路径必须落在根目录内")
                ])
              ], -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[63] || (_cache[63] = _createElementVNode("div", { class: "config-card-title" }, "输出与备份", -1)),
              _createElementVNode("div", _hoisted_25, [
                _cache[58] || (_cache[58] = _createElementVNode("label", null, "默认输出", -1)),
                _createElementVNode("div", _hoisted_26, [
                  _createVNode(_component_v_btn_toggle, {
                    "model-value": cfg.value.output_mode,
                    mandatory: "",
                    density: "compact",
                    variant: "outlined",
                    divided: "",
                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => (cfg.value.output_mode = $event))
                  }, {
                    default: _withCtx(() => [
                      (_openBlock(), _createElementBlock(_Fragment, null, _renderList(OUTPUT_MODES, (item) => {
                        return _createVNode(_component_v_btn, {
                          key: item.value,
                          value: item.value,
                          size: "small"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(item.title), 1)
                          ]),
                          _: 2
                        }, 1032, ["value"])
                      }), 64))
                    ]),
                    _: 1
                  }, 8, ["model-value"]),
                  _cache[57] || (_cache[57] = _createElementVNode("span", { class: "sub" }, "原地替换默认会先做临时备份，任务成功后自动删除；失败时保留备份并尝试还原源文件", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_27, [
                _cache[59] || (_cache[59] = _createElementVNode("label", null, "输出目录", -1)),
                _createElementVNode("div", _hoisted_28, [
                  _createVNode(_component_v_text_field, {
                    modelValue: cfg.value.output_dir,
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.value.output_dir) = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "path-input mono"
                  }, null, 8, ["modelValue"])
                ])
              ]),
              _createElementVNode("div", _hoisted_29, [
                _cache[60] || (_cache[60] = _createElementVNode("label", null, "备份目录", -1)),
                _createElementVNode("div", _hoisted_30, [
                  _createVNode(_component_v_text_field, {
                    modelValue: cfg.value.backup_dir,
                    "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.value.backup_dir) = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "path-input mono",
                    placeholder: "留空则默认：/config/plugins/MkvToolkit/backup"
                  }, null, 8, ["modelValue"])
                ])
              ]),
              _createElementVNode("div", _hoisted_31, [
                _cache[62] || (_cache[62] = _createElementVNode("label", null, "失败备份保留份数", -1)),
                _createElementVNode("div", _hoisted_32, [
                  _createVNode(_component_v_select, {
                    modelValue: cfg.value.backup_keep,
                    "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.value.backup_keep) = $event)),
                    modelModifiers: { number: true },
                    items: [1, 3, 5, 10],
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-90"
                  }, null, 8, ["modelValue"]),
                  _cache[61] || (_cache[61] = _createElementVNode("span", { class: "sub" }, "份；仅清理失败任务遗留的备份，成功任务会自动删除临时备份", -1))
                ])
              ]),
              _cache[64] || (_cache[64] = _createElementVNode("div", { class: "form-row" }, [
                _createElementVNode("label"),
                _createElementVNode("div", { class: "value" }, [
                  _createElementVNode("span", { class: "sub" }, "留空时使用插件数据目录下的 backup；可改成媒体盘等大容量路径")
                ])
              ], -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[71] || (_cache[71] = _createElementVNode("div", { class: "config-card-title" }, "字幕与语言", -1)),
              _createElementVNode("div", _hoisted_33, [
                _cache[66] || (_cache[66] = _createElementVNode("label", null, "内封后外挂字幕", -1)),
                _createElementVNode("div", _hoisted_34, [
                  _createVNode(_component_v_btn_toggle, {
                    "model-value": cfg.value.subtitle_after,
                    mandatory: "",
                    density: "compact",
                    variant: "outlined",
                    divided: "",
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => (cfg.value.subtitle_after = $event))
                  }, {
                    default: _withCtx(() => [
                      (_openBlock(), _createElementBlock(_Fragment, null, _renderList(SUBTITLE_AFTER, (item) => {
                        return _createVNode(_component_v_btn, {
                          key: item.value,
                          value: item.value,
                          size: "small"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(item.title), 1)
                          ]),
                          _: 2
                        }, 1032, ["value"])
                      }), 64))
                    ]),
                    _: 1
                  }, 8, ["model-value"]),
                  _cache[65] || (_cache[65] = _createElementVNode("span", { class: "sub" }, "默认保留；仅在原地替换模式下生效，输出到新目录时不会移动源字幕", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_35, [
                _cache[68] || (_cache[68] = _createElementVNode("label", null, "编码兜底", -1)),
                _createElementVNode("div", _hoisted_36, [
                  _createVNode(_component_v_select, {
                    modelValue: cfg.value.subtitle_encoding,
                    "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((cfg.value.subtitle_encoding) = $event)),
                    items: SUBTITLE_ENCODINGS,
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-180"
                  }, null, 8, ["modelValue"]),
                  _cache[67] || (_cache[67] = _createElementVNode("span", { class: "sub" }, "自动探测失败时按此编码处理", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_37, [
                _cache[70] || (_cache[70] = _createElementVNode("label", null, "语言映射", -1)),
                _createElementVNode("div", _hoisted_38, [
                  _createElementVNode("span", {
                    class: "mono sub ellipsis",
                    title: languageHint()
                  }, _toDisplayString(languageHint()), 9, _hoisted_39),
                  _createElementVNode("span", _hoisted_40, "（" + _toDisplayString(languageMapCount.value) + " 条）", 1),
                  _createVNode(_component_v_btn, {
                    size: "small",
                    variant: "text",
                    "prepend-icon": "mdi-pencil",
                    onClick: openLanguage
                  }, {
                    default: _withCtx(() => [...(_cache[69] || (_cache[69] = [
                      _createTextVNode("编辑", -1)
                    ]))]),
                    _: 1
                  })
                ])
              ])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[78] || (_cache[78] = _createElementVNode("div", { class: "config-card-title" }, "自动导入", -1)),
              _createElementVNode("div", _hoisted_41, [
                _cache[73] || (_cache[73] = _createElementVNode("label", null, "自动导入同名字幕", -1)),
                _createElementVNode("div", _hoisted_42, [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.value.auto_subtitle,
                    "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((cfg.value.auto_subtitle) = $event)),
                    density: "compact",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _cache[72] || (_cache[72] = _createElementVNode("span", { class: "sub" }, "打开文件时自动导入同名字幕（前缀匹配的候选）", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_43, [
                _cache[75] || (_cache[75] = _createElementVNode("label", null, "自动导入同名音频", -1)),
                _createElementVNode("div", _hoisted_44, [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.value.auto_audio,
                    "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((cfg.value.auto_audio) = $event)),
                    density: "compact",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _cache[74] || (_cache[74] = _createElementVNode("span", { class: "sub" }, "打开文件时自动导入同名音频（前缀匹配的候选）", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_45, [
                _cache[77] || (_cache[77] = _createElementVNode("label", null, "自动导入同目录字体", -1)),
                _createElementVNode("div", _hoisted_46, [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.value.auto_fonts,
                    "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((cfg.value.auto_fonts) = $event)),
                    density: "compact",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _cache[76] || (_cache[76] = _createElementVNode("span", { class: "sub" }, "打开文件时自动导入同目录（含 fonts/ 子目录）字体为附件", -1))
                ])
              ])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[89] || (_cache[89] = _createElementVNode("div", { class: "config-card-title" }, "执行", -1)),
              _createElementVNode("div", _hoisted_47, [
                _cache[80] || (_cache[80] = _createElementVNode("label", null, "并发数", -1)),
                _createElementVNode("div", _hoisted_48, [
                  _createVNode(_component_v_select, {
                    modelValue: cfg.value.concurrency,
                    "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((cfg.value.concurrency) = $event)),
                    modelModifiers: { number: true },
                    items: [1, 2, 3],
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-90"
                  }, null, 8, ["modelValue"]),
                  _cache[79] || (_cache[79] = _createElementVNode("span", { class: "sub" }, "机械盘建议 1，SSD 可 2~3", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_49, [
                _cache[85] || (_cache[85] = _createElementVNode("label", null, "校验", -1)),
                _createElementVNode("div", _hoisted_50, [
                  _cache[81] || (_cache[81] = _createElementVNode("span", { class: "sub" }, "时长误差 >", -1)),
                  _createVNode(_component_v_text_field, {
                    modelValue: cfg.value.validation_tolerance,
                    "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((cfg.value.validation_tolerance) = $event)),
                    modelModifiers: { number: true },
                    type: "number",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-90"
                  }, null, 8, ["modelValue"]),
                  _cache[82] || (_cache[82] = _createElementVNode("span", { class: "sub" }, "秒视为失败", -1)),
                  _cache[83] || (_cache[83] = _createElementVNode("span", { class: "sub" }, "历史保留", -1)),
                  _createVNode(_component_v_text_field, {
                    modelValue: cfg.value.history_keep,
                    "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((cfg.value.history_keep) = $event)),
                    modelModifiers: { number: true },
                    type: "number",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-90"
                  }, null, 8, ["modelValue"]),
                  _cache[84] || (_cache[84] = _createElementVNode("span", { class: "sub" }, "条", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_51, [
                _cache[86] || (_cache[86] = _createElementVNode("label", null, "严格时长校验", -1)),
                _createElementVNode("div", _hoisted_52, [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.value.strict_duration_check,
                    "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((cfg.value.strict_duration_check) = $event)),
                    density: "compact",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _createElementVNode("span", _hoisted_53, " 关闭时：输出时长与源视频偏差只记警告；开启时：偏差超过上面的阈值（" + _toDisplayString(cfg.value.validation_tolerance) + " 秒）判失败 ", 1)
                ])
              ]),
              _createElementVNode("div", _hoisted_54, [
                _cache[88] || (_cache[88] = _createElementVNode("label", null, "上传上限", -1)),
                _createElementVNode("div", _hoisted_55, [
                  _createVNode(_component_v_text_field, {
                    modelValue: cfg.value.upload_max_mb,
                    "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((cfg.value.upload_max_mb) = $event)),
                    modelModifiers: { number: true },
                    type: "number",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "w-90"
                  }, null, 8, ["modelValue"]),
                  _cache[87] || (_cache[87] = _createElementVNode("span", { class: "sub" }, "MB，前端与后端双重校验；宿主 nginx 默认 50MB", -1))
                ])
              ])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card, {
            variant: "flat",
            class: "config-card"
          }, {
            default: _withCtx(() => [
              _cache[93] || (_cache[93] = _createElementVNode("div", { class: "config-card-title" }, "诊断", -1)),
              _createElementVNode("div", _hoisted_56, [
                _cache[92] || (_cache[92] = _createElementVNode("label", null, "一键诊断", -1)),
                _createElementVNode("div", _hoisted_57, [
                  _createVNode(_component_v_btn, {
                    size: "small",
                    variant: "tonal",
                    "prepend-icon": "mdi-stethoscope",
                    loading: diagnoseLoading.value,
                    onClick: runDiagnose
                  }, {
                    default: _withCtx(() => [...(_cache[90] || (_cache[90] = [
                      _createTextVNode(" 开始诊断 ", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"]),
                  _cache[91] || (_cache[91] = _createElementVNode("span", { class: "sub" }, "检查引擎版本、路径、空间、上传上限、配置一致性", -1))
                ])
              ]),
              (diagnoseResults.value.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_58, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(diagnoseResults.value, (item, index) => {
                      return (_openBlock(), _createElementBlock("div", {
                        key: index,
                        class: "diagnose-row"
                      }, [
                        _createVNode(_component_v_icon, {
                          size: "15",
                          icon: item.ok ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline',
                          color: item.ok ? 'success' : 'warning'
                        }, null, 8, ["icon", "color"]),
                        _createElementVNode("span", _hoisted_59, _toDisplayString(item.name), 1),
                        _createElementVNode("span", _hoisted_60, _toDisplayString(item.detail), 1)
                      ]))
                    }), 128))
                  ]))
                : _createCommentVNode("", true),
              (diagnoseNote.value)
                ? (_openBlock(), _createElementBlock("div", _hoisted_61, _toDisplayString(diagnoseNote.value), 1))
                : _createCommentVNode("", true)
            ]),
            _: 1
          }),
          _createElementVNode("div", _hoisted_62, [
            _createVNode(_component_v_btn, {
              variant: "text",
              "prepend-icon": "mdi-refresh",
              disabled: saving.value,
              onClick: loadConfig
            }, {
              default: _withCtx(() => [...(_cache[94] || (_cache[94] = [
                _createTextVNode("重新加载", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_btn, {
              color: "primary",
              variant: "flat",
              "prepend-icon": "mdi-content-save",
              loading: saving.value,
              onClick: saveConfig
            }, {
              default: _withCtx(() => [...(_cache[95] || (_cache[95] = [
                _createTextVNode(" 保存配置 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
        ], 64)),
    _createVNode(_component_v_dialog, {
      modelValue: installOpen.value,
      "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((installOpen).value = $event)),
      "max-width": "620",
      scrollable: ""
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_63, [
              _createElementVNode("span", _hoisted_64, "安装 " + _toDisplayString(installTargetLabel.value), 1),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                "aria-label": "关闭",
                onClick: closeInstall
              })
            ]),
            _createElementVNode("div", _hoisted_65, [
              (!installStarted.value)
                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                    _createVNode(_component_v_btn_toggle, {
                      modelValue: installMethod.value,
                      "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((installMethod).value = $event)),
                      mandatory: "",
                      density: "compact",
                      variant: "outlined",
                      divided: "",
                      class: "mb-3"
                    }, {
                      default: _withCtx(() => [
                        (_openBlock(), _createElementBlock(_Fragment, null, _renderList(INSTALL_METHODS, (item) => {
                          return _createVNode(_component_v_btn, {
                            key: item.value,
                            value: item.value,
                            size: "small"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(item.title), 1)
                            ]),
                            _: 2
                          }, 1032, ["value"])
                        }), 64))
                      ]),
                      _: 1
                    }, 8, ["modelValue"]),
                    _createElementVNode("div", _hoisted_66, _toDisplayString(currentMethodDesc().desc), 1),
                    (installMethod.value === 'path')
                      ? (_openBlock(), _createBlock(_component_v_text_field, {
                          key: 0,
                          modelValue: installPath.value,
                          "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((installPath).value = $event)),
                          label: "mkvmerge 可执行文件路径",
                          placeholder: "/usr/bin/mkvmerge",
                          density: "compact",
                          variant: "outlined",
                          "hide-details": "",
                          class: "mono"
                        }, null, 8, ["modelValue"]))
                      : _createCommentVNode("", true),
                    (installError.value)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_67, _toDisplayString(installError.value), 1))
                      : _createCommentVNode("", true),
                    _cache[96] || (_cache[96] = _createElementVNode("div", { class: "install-tip" }, "安装过程在后台线程执行，可以关闭此窗口；完成后引擎状态会自动刷新。", -1))
                  ], 64))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createElementVNode("div", _hoisted_68, [
                      (installRunning.value)
                        ? (_openBlock(), _createBlock(_component_v_progress_circular, {
                            key: 0,
                            indeterminate: "",
                            size: "16",
                            width: "2",
                            color: "primary"
                          }))
                        : (_openBlock(), _createBlock(_component_v_icon, {
                            key: 1,
                            icon: installOk.value ? 'mdi-check-circle' : 'mdi-alert-circle',
                            color: installOk.value ? 'success' : 'error',
                            size: "18"
                          }, null, 8, ["icon", "color"])),
                      _createElementVNode("span", null, _toDisplayString(installRunning.value ? '安装中…' : (installOk.value ? '安装完成' : '安装失败')), 1)
                    ]),
                    (installLog.value)
                      ? (_openBlock(), _createElementBlock("pre", _hoisted_69, _toDisplayString(installLog.value), 1))
                      : _createCommentVNode("", true),
                    (installError.value)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_70, _toDisplayString(installError.value), 1))
                      : _createCommentVNode("", true)
                  ], 64))
            ]),
            _createElementVNode("div", _hoisted_71, [
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: closeInstall
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(installStarted.value ? '关闭' : '取消'), 1)
                ]),
                _: 1
              }),
              (!installStarted.value)
                ? (_openBlock(), _createBlock(_component_v_btn, {
                    key: 0,
                    color: "primary",
                    variant: "flat",
                    onClick: startInstall
                  }, {
                    default: _withCtx(() => [...(_cache[97] || (_cache[97] = [
                      _createTextVNode("开始安装", -1)
                    ]))]),
                    _: 1
                  }))
                : _createCommentVNode("", true)
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: rootDialog.value,
      "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((rootDialog).value = $event)),
      "max-width": "480"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_72, [
              _cache[98] || (_cache[98] = _createElementVNode("span", { class: "dialog-title" }, "添加媒体根目录", -1)),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                onClick: _cache[27] || (_cache[27] = $event => (rootDialog.value = false))
              })
            ]),
            _createElementVNode("div", _hoisted_73, [
              _createVNode(_component_v_text_field, {
                modelValue: newRoot.value,
                "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((newRoot).value = $event)),
                label: "容器内绝对路径",
                placeholder: "/media",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                class: "mono",
                onKeyup: _withKeys(addRoot, ["enter"])
              }, null, 8, ["modelValue"]),
              _cache[99] || (_cache[99] = _createElementVNode("div", { class: "install-tip" }, [
                _createTextVNode("路径必须存在于容器内，例如 "),
                _createElementVNode("span", { class: "mono" }, "/media"),
                _createTextVNode("、"),
                _createElementVNode("span", { class: "mono" }, "/downloads"),
                _createTextVNode("。")
              ], -1))
            ]),
            _createElementVNode("div", _hoisted_74, [
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[29] || (_cache[29] = $event => (rootDialog.value = false))
              }, {
                default: _withCtx(() => [...(_cache[100] || (_cache[100] = [
                  _createTextVNode("取消", -1)
                ]))]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: addRoot
              }, {
                default: _withCtx(() => [...(_cache[101] || (_cache[101] = [
                  _createTextVNode("添加", -1)
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
      modelValue: languageDialog.value,
      "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((languageDialog).value = $event)),
      "max-width": "560"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_75, [
              _cache[102] || (_cache[102] = _createElementVNode("span", { class: "dialog-title" }, "编辑语言映射", -1)),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                onClick: _cache[31] || (_cache[31] = $event => (languageDialog.value = false))
              })
            ]),
            _createElementVNode("div", _hoisted_76, [
              _createVNode(_component_v_textarea, {
                modelValue: languageText.value,
                "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((languageText).value = $event)),
                rows: "8",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                class: "mono",
                placeholder: ".zh=chi\n.chs=chi\n.jpn=jpn"
              }, null, 8, ["modelValue"]),
              _cache[103] || (_cache[103] = _createElementVNode("div", { class: "install-tip" }, [
                _createTextVNode("每行一条："),
                _createElementVNode("span", { class: "mono" }, "文件名后缀=ISO639-2 语言码"),
                _createTextVNode("，例如 "),
                _createElementVNode("span", { class: "mono" }, ".zh=chi"),
                _createTextVNode("。")
              ], -1))
            ]),
            _createElementVNode("div", _hoisted_77, [
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[33] || (_cache[33] = $event => (languageDialog.value = false))
              }, {
                default: _withCtx(() => [...(_cache[104] || (_cache[104] = [
                  _createTextVNode("取消", -1)
                ]))]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: saveLanguage
              }, {
                default: _withCtx(() => [...(_cache[105] || (_cache[105] = [
                  _createTextVNode("确定", -1)
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
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e2e828f8"]]);

export { ARCHIVE_EXTENSIONS as A, FONT_EXTENSIONS as F, LANGUAGE_ITEMS as L, SUBTITLE_ENCODINGS as S, _export_sfc as _, fmtChannels as a, baseName as b, codecLabel as c, AUDIO_EXTENSIONS as d, Config as default, SUBTITLE_EXTENSIONS as e, fmtBytes as f, fmtDateTime as g, fmtDuration as h, isArchiveName as i, createApi as j, extName as k, stripExt as s };
