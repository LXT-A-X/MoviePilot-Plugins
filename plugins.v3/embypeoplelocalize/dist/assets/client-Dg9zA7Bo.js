/**
 * Emby 演职人员中文化 - API 封装
 * 通过宿主注入的 api 模块调用后端接口（/api/v1/plugin/EmbyPeopleLocalize/xxx）
 */
const PLUGIN_ID = 'EmbyPeopleLocalize';

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

async function get(api, path, params = {}) {
  return unwrap(await api.get(`plugin/${PLUGIN_ID}${path}`, { params }))
}

async function post(api, path, data = {}) {
  return unwrap(await api.post(`plugin/${PLUGIN_ID}${path}`, data))
}

const api = { get, post };

export { api as a };
