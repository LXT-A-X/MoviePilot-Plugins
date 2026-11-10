/**
 * MkvToolkit - 宿主 API 封装
 * 通过宿主注入的 api 模块调用后端接口：/api/v1/plugin/MkvToolkit/xxx
 * 后端统一返回 { success, message, data }
 */
const PLUGIN_ID = 'MkvToolkit'

/**
 * 统一解包后端响应：
 * - {success:false} 抛错（message 可直接展示给用户）
 * - {success:true,data} 返回 data
 * - 直接返回业务数据时原样返回
 */
function unwrap(response) {
  const body = response && Object.prototype.hasOwnProperty.call(response, 'success')
    ? response
    : (response?.data ?? response)
  if (body?.success === false) {
    const err = new Error(body.message || '请求失败')
    err.code = body.code
    // 上传超限等场景后端会带 data（size / limit），保留给调用方
    err.data = body.data
    throw err
  }
  return body?.data ?? body ?? {}
}

export function createApi(props) {
  const pluginId = props?.pluginId || PLUGIN_ID
  const client = props?.api || {}
  const withPlugin = (path) => `plugin/${pluginId}${path}`

  return {
    async get(path, params = {}) {
      const res = await client.get(withPlugin(path), { params })
      return unwrap(res)
    },
    async post(path, data = {}) {
      const res = await client.post(withPlugin(path), data)
      return unwrap(res)
    },
    async put(path, data = {}) {
      const res = await client.put(withPlugin(path), data)
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
      })
      return unwrap(res)
    },
  }
}

export default { createApi }
