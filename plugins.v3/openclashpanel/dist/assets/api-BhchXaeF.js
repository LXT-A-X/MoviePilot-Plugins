/**
 * OpenClashPanel - 宿主 API 封装
 * 通过宿主注入的 api 模块调用后端接口：/api/v1/plugin/<pluginId>/xxx
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

function createApi(props) {
  const pluginId = props?.pluginId || 'OpenClashPanel';
  const client = props?.api || {};

  return {
    async get(path, params = {}) {
      const res = await client.get(`plugin/${pluginId}${path}`, { params });
      return unwrap(res)
    },
    async post(path, data = {}) {
      const res = await client.post(`plugin/${pluginId}${path}`, data);
      return unwrap(res)
    },
    async put(path, data = {}) {
      const res = await client.put(`plugin/${pluginId}${path}`, data);
      return unwrap(res)
    },
  }
}

export { createApi as c };
