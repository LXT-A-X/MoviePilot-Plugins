/**
 * 字幕字体代理 - API 封装
 * 通过宿主注入的 api 模块调用后端接口（/api/v1/plugin/FontInAssProxy/xxx）
 */
const PLUGIN_ID = 'FontInAssProxy'

/**
 * 统一解包后端响应
 * 后端接口可能直接返回 {success, message, data}，也可能直接返回业务数据
 */
function unwrap(response) {
  const body = response && Object.prototype.hasOwnProperty.call(response, 'success')
    ? response
    : (response?.data ?? response)
  if (body?.success === false) {
    const err = new Error(body.message || '请求失败')
    err.code = body.code
    throw err
  }
  return body?.data ?? body ?? {}
}

async function get(api, path, params = {}) {
  const res = await api.get(`plugin/${PLUGIN_ID}${path}`, { params })
  return unwrap(res)
}

async function post(api, path, data = {}) {
  const res = await api.post(`plugin/${PLUGIN_ID}${path}`, data)
  return unwrap(res)
}

export default { get, post }