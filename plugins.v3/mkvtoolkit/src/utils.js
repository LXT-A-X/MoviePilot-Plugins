/**
 * MkvToolkit - 通用格式化与常量
 */

export const LANGUAGE_OPTIONS = [
  'zh-Hans', 'zh-Hant', 'yue', 'jpn', 'eng', 'kor', 'fra', 'deu', 'spa',
  'ita', 'rus', 'por', 'tha', 'vie', 'und',
]

// 语言下拉选项：显示「简体中文 (zh-Hans)」，value 使用 ISO 639-2 / BCP47 代码
export const LANGUAGE_ITEMS = [
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
]

export const SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.ssa', '.vtt', '.sup', '.mks']
export const AUDIO_EXTENSIONS = ['.aac', '.flac', '.mka', '.ac3', '.dts', '.mp3', '.m4a', '.eac3', '.truehd']
export const FONT_EXTENSIONS = ['.ttf', '.otf', '.ttc']

// 字体压缩包：zip/tar 内置可解；7z/rar 依赖容器内 7z / unrar
export const ARCHIVE_EXTENSIONS = [
  '.zip', '.7z', '.rar', '.tar', '.tgz', '.tbz2', '.txz',
  '.tar.gz', '.tar.bz2', '.tar.xz',
]

/** 判断文件名是否为支持的压缩包（含 .tar.gz 这类双后缀）。 */
export function isArchiveName(name) {
  const lower = String(name || '').toLowerCase()
  return ARCHIVE_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export const SUBTITLE_ENCODINGS = [
  { title: '自动探测', value: 'auto' },
  { title: 'UTF-8', value: 'utf-8' },
  { title: 'GBK', value: 'gbk' },
  { title: 'BIG5', value: 'big5' },
]

// 字节数格式化：B / KB / MB / GB / TB
export function fmtBytes(value, digits = 1) {
  if (value == null || value === '' || Number.isNaN(Number(value))) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let num = Number(value)
  let index = 0
  while (num >= 1024 && index < units.length - 1) {
    num /= 1024
    index += 1
  }
  return `${num.toFixed(index ? digits : 0)} ${units[index]}`
}

// 秒 → mm:ss / h:mm:ss
export function fmtDuration(seconds, withMs = false) {
  const total = Number(seconds)
  if (!Number.isFinite(total) || total < 0) return '—'
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = Math.floor(total % 60)
  const ms = Math.round((total - Math.floor(total)) * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  const base = hours
    ? `${hours}:${pad(minutes)}:${pad(secs)}`
    : `${pad(minutes)}:${pad(secs)}`
  return withMs ? `${base}.${String(ms).padStart(3, '0')}` : base
}

// 历史/任务里的时间字符串 → 本地可读（兼容 ISO 与 "YYYY-MM-DD HH:mm:ss"）
export function fmtDateTime(value, short = false) {
  if (!value) return '—'
  const text = String(value)
  let date = new Date(text)
  if (Number.isNaN(date.getTime())) date = new Date(text.replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return text
  const pad = (n) => String(n).padStart(2, '0')
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  if (short) return `${month}-${day} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  return `${date.getFullYear()}-${month}-${day} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

// 取文件名（兼容 / 与 \ 分隔）
export function baseName(path) {
  if (!path) return ''
  const normalized = String(path).replaceAll('\\', '/')
  const index = normalized.lastIndexOf('/')
  return index >= 0 ? normalized.slice(index + 1) : normalized
}

// 取扩展名（小写，含点）
export function extName(name) {
  const base = baseName(name)
  const index = base.lastIndexOf('.')
  return index > 0 ? base.slice(index).toLowerCase() : ''
}

// 去掉扩展名
export function stripExt(name) {
  const base = baseName(name)
  const index = base.lastIndexOf('.')
  return index > 0 ? base.slice(0, index) : base
}

// 声道数 → 2.0 / 5.1 这种显示
export function fmtChannels(track) {
  const channels = Number(track?.channels || 0)
  if (!channels) return '—'
  if (channels === 1) return '1.0'
  if (channels === 2) return '2.0'
  if (channels === 6) return '5.1'
  if (channels === 8) return '7.1'
  return `${channels}ch`
}

// 编码名统一大写（hevc → HEVC）
export function codecLabel(track) {
  return String(track?.codec || track?.codec_detail || '').toUpperCase() || '—'
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
