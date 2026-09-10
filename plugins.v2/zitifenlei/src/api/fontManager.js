/**
 * 字体分类管家 - API 封装
 * 通过宿主注入的 api 模块调用后端接口（/api/v1/plugin/Zitifenlei/xxx）
 */
const PLUGIN_ID = 'Zitifenlei'

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

/**
 * GET 请求
 */
async function get(api, path, params = {}) {
  try {
    const res = await api.get(`plugin/${PLUGIN_ID}${path}`, { params })
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
    const res = await api.post(`plugin/${PLUGIN_ID}${path}`, data)
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
    const res = await api.put(`plugin/${PLUGIN_ID}${path}`, data)
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
    const res = await api.delete(`plugin/${PLUGIN_ID}${path}`, { params })
    return unwrap(res)
  } catch (e) {
    throw e
  }
}

export default {
  get,
  post,
  put,
  del,
}