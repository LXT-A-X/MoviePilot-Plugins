/**
 * 上传文件选择器的 accept 配置。
 *
 * 背景：只写扩展名（.rar/.7z 等）时，手机系统文件选择器会按 MIME 过滤——
 * 压缩包常被识别成 application/x-rar-compressed / application/vnd.rar /
 * application/octet-stream 等，不在 accept 里就会「能看到文件但灰色点不动」，
 * 用户反馈的「手机压缩包无法上传」正是这个原因。
 *
 * 处理方式：桌面保留扩展名过滤（方便选文件）；手机/平板直接不设 accept，
 * 文件选择器不再按 MIME 过滤，任何格式都能选中。后端会校验后缀并给出明确提示。
 */
const DESKTOP_ACCEPT_FONT = '.ttf,.otf,.ttc,.otc,.woff,.woff2,.zip,.7z,.rar'
const DESKTOP_ACCEPT_ASS = '.ass,.ASS,.zip,.7z,.rar'

export { DESKTOP_ACCEPT_FONT, DESKTOP_ACCEPT_ASS }

/** 是否是手机/平板浏览器（安卓、iOS、鸿蒙等）。 */
export function isMobileUploadDevice() {
  if (typeof navigator === 'undefined') return false
  return /Android|iPhone|iPad|iPod|HarmonyOS|Mobile/i.test(navigator.userAgent || '')
}

/** 手机不设 accept（避免 MIME 过滤导致压缩包灰色不可选）；桌面保留类型过滤。 */
export function uploadAcceptFor(desktopAccept) {
  return isMobileUploadDevice() ? undefined : desktopAccept
}

/** 把后端返回的 notes（压缩包跳过/解压失败原因）转成一条可读提示；没有则返回空串。 */
export function formatNotes(notes, max = 3) {
  if (!Array.isArray(notes) || !notes.length) return ''
  const shown = notes.slice(0, max)
  const tail = notes.length > max ? `；等 ${notes.length} 条` : ''
  return shown.join('；') + tail
}
