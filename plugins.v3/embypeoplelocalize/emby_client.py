"""
emby_client.py - Emby 服务器 API 封装
API 在线写回模式下线，仅保留 Webhook/NFO 流水线共用的只读接口
（__init__/_get/_post/_get_user_id/_get_admin_user_id/fetch_item）；
写回类接口（update_people/lock_cast 等）已随 API 模式下线。
"""
import base64
from typing import Any, Dict, List, Optional

import requests
from app.sdk.logging import logger
from app.schemas import ServiceInfo


# v4.6.98（P1-01）：条目存在性**三态** —— 查询失败绝不等于「条目不存在」。
# 删除事件必须能区分「Emby 明确说没有」与「暂时问不到」：
#   FOUND       查询成功，条目存在
#   NOT_FOUND   请求成功到达 Emby，服务器明确回答 404 / 不存在
#   UNAVAILABLE 超时 / 连接失败 / 401 / 403 / 500 / 响应非法 / 无 user_id / 客户端不可用
# 只有 NOT_FOUND 才能作为「容器已删除」的依据；UNAVAILABLE 一律按「状态未知」处理。
ITEM_FOUND = "found"
ITEM_NOT_FOUND = "not_found"
ITEM_UNAVAILABLE = "unavailable"


class EmbyClient:
    """Emby API 客户端"""

    def __init__(self, base_url: str, api_key: str, service: Optional[ServiceInfo] = None,
                 user_id: Optional[str] = None,
                 timeout: tuple = (10, 60),
                 use_proxy: bool = False):
        """timeout 提升到 (10, 60)
        - 连接超时 10s
        - 读取超时 60s
        大型 NAS / 2000+ 媒体库时 10s 读取往往不够，60s 更稳定

        use_proxy 参数 - 控制是否信任系统代理环境变量
        - 默认 False: 内网/直连 Emby，不读 HTTP_PROXY/HTTPS_PROXY
        - True: 公网 Emby 必须走代理的场景
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.service = service
        self._user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "X-Emby-Token": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.session.trust_env = use_proxy
        self.timeout = timeout

    def _get_status(self, path: str, params: Optional[dict] = None) -> tuple:
        """GET 请求（v4.6.98 · P1-01）—— 返回 `(status, data)`，区分「明确不存在」与「查询失败」。

        绝不能把「超时 / 401 / 500 / 客户端不可用」当成「条目不存在」——
        删除事件一旦据此判定「容器已删除」，就会把整部剧/整季误标进观察期。
        """
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except Exception as e:
            logger.warning(f"[EmbyClient] GET {url} 请求失败（服务器不可用，非「不存在」）: {e}")
            return ITEM_UNAVAILABLE, None
        try:
            _code = int(getattr(resp, "status_code", 0) or 0)
        except Exception:
            _code = 0
        if _code == 404:
            logger.debug(f"[EmbyClient] GET {url} → HTTP 404（条目明确不存在）")
            return ITEM_NOT_FOUND, None
        if _code < 200 or _code >= 300:
            logger.warning(f"[EmbyClient] GET {url} 返回 HTTP {_code}（查询失败，按「状态未知」处理）")
            return ITEM_UNAVAILABLE, None
        try:
            _json = resp.json()
        except Exception as e:
            logger.warning(f"[EmbyClient] GET {url} 响应不是合法 JSON（按「状态未知」处理）: {e}")
            return ITEM_UNAVAILABLE, None
        return ITEM_FOUND, _json

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET 请求（兼容旧调用：拿不到就 None —— 不区分原因）。

        ⚠️ 需要区分「不存在 / 查询失败」时请用 `_get_status()` / `fetch_item_status()`。
        """
        try:
            _st, _d = self._get_status(path, params)
        except Exception as e:
            logger.error(f"[EmbyClient] GET {self.base_url}{path} 失败: {e}")
            return None
        return _d if _st == ITEM_FOUND else None

    def get_server_id(self) -> str:
        """缺陷 Q —— 获取 Emby 服务器真实 ServerId（/emby/System/Info 的
        Id 字段，即 Webhook 报文里的 ServerId GUID）。
        用于多 Emby 服务器精确路由（skey「名_主机_端口」与 GUID 是两个命名空间）。"""
        try:
            r = self._get("/emby/System/Info")
            if r and r.get("Id"):
                return str(r.get("Id"))
        except Exception:
            pass
        return ""

    def _post(self, path: str, data: Optional[dict] = None) -> bool:
        """POST 请求"""
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.post(url, json=data, timeout=self.timeout)
            if resp.status_code in (200, 204):
                return True
            logger.warning(f"[EmbyClient] POST {url} 返回 {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"[EmbyClient] POST {url} 失败: {e}")
            return False

    def search_item_by_provider(self, provider: str, value: str,
                                include_types: Optional[list] = None) -> Optional[str]:
        """E —— 按外部 ID（tmdb.{id} 等）搜索 Emby 条目，返回首个匹配的 itemId。
        NFO 条目只有 tmdbid，需先反查 Emby itemId 才能拉海报/LOGO。"""
        try:
            uid = self._get_user_id()
            params = {
                "AnyProviderIdEquals": f"{provider}.{value}",
                "Recursive": "true",
                "Limit": 1,
                "Fields": "Path",
            }
            if include_types:
                params["IncludeItemTypes"] = ",".join(include_types)
            path = f"/Users/{uid}/Items" if uid else "/Items"
            r = self._get(path, params)
            items = (r or {}).get("Items") or []
            if items and items[0].get("Id"):
                return str(items[0]["Id"])
        except Exception as e:
            logger.debug(f"[EmbyClient] 按外部 ID 搜索失败 {provider}.{value}: {e}")
        return None

    def get_image_bytes(self, path: str, params: Optional[dict] = None) -> Optional[bytes]:
        """E —— 拉取图片原始字节（Emby Items/{id}/Images/Primary|Logo）。
        供插件端直连 Emby 转 data URL（海报/LOGO 显示），失败返回 None。"""
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=(10, 30))
            if resp.status_code == 200 and resp.content:
                return resp.content
            logger.warning(f"[EmbyClient] 图片拉取失败 {url} 返回 {resp.status_code}")
            return None
        except Exception as e:
            logger.debug(f"[EmbyClient] 图片拉取异常 {url}: {e}")
            return None

    def get_series_episodes_status(self, series_id: str, limit: int = 200) -> tuple:
        """拉取整剧单集 + **枚举完整性三态**（v4.6.99 · P1-01）→ `(status, items, reason)`。

        · `ITEM_FOUND`       请求成功且**分页完整**（items 可信，可能为空列表）
        · `ITEM_NOT_FOUND`   Emby 明确 404（剧不存在）
        · `ITEM_UNAVAILABLE` 超时 / 401 / 403 / 500 / 无 user_id / 响应非法 / **分页不完整**

        「请求失败返回空列表」绝不等于「整季/整剧没有剧集」——删除处理据此避免把
        仍然存在的季/剧误判为「全部消失」而批量标记观察期。
        """
        _sid = str(series_id or "").strip()
        if not _sid:
            return ITEM_UNAVAILABLE, [], "empty_series_id"
        try:
            uid = self._get_user_id()
        except Exception:
            uid = None
        if not uid:
            logger.warning("[EmbyClient] 无 user_id → 无法枚举剧集（按 UNAVAILABLE 处理，不当作空剧）")
            return ITEM_UNAVAILABLE, [], "no_user_id"
        page = max(1, int(limit or 200))
        out: List[dict] = []
        start = 0
        try:
            while True:
                params = {
                    "Fields": "Path,SeriesName,SeriesId,SeasonId,ParentIndexNumber,IndexNumber,Type,DateCreated",
                    "IncludeItemTypes": "Episode",
                    "StartIndex": start,
                    "Limit": page,
                }
                _st, _r = self._get_status(f"/Shows/{_sid}/Episodes", params)
                if _st == ITEM_NOT_FOUND:
                    return ITEM_NOT_FOUND, [], "http_404"
                if _st != ITEM_FOUND:
                    return ITEM_UNAVAILABLE, out, f"http_error_at_{start}"
                _r = _r or {}
                items = _r.get("Items") or []
                try:
                    total = int(_r.get("TotalRecordCount") or 0)
                except Exception:
                    total = 0
                if not items:
                    # 本页为空：只有「已到末尾」才算完整；服务器声称还有 = 分页异常
                    if start >= total:
                        return ITEM_FOUND, out, ""
                    return ITEM_UNAVAILABLE, out, f"empty_page_but_total_{total}_at_{start}"
                out.extend(items)
                start += len(items)
                if len(items) < page:
                    if total and start < total:
                        return ITEM_UNAVAILABLE, out, f"short_page_{start}/{total}"
                    return ITEM_FOUND, out, ""
                if total and start >= total:
                    return ITEM_FOUND, out, ""
        except Exception as e:
            logger.warning(f"[EmbyClient] 拉取剧集单集异常 {series_id}: {e}")
            return ITEM_UNAVAILABLE, out, "exception"

    def get_series_episodes(self, series_id: str, limit: int = 200) -> List[dict]:
        """拉取某剧的全部单集 —— 整批入库时 Emby 只发一条 Series 级事件
        （Path 为目录），不会为每集发 Episode 事件；需展开为单集任务逐集处理。
        支持 StartIndex/Limit/TotalRecordCount 分页 —— 此前固定 Limit=200，
        超过 200 集的长剧后面的 Episode 根本不进流程。现在循环翻页直到翻完
        （每页 100~200，直到 StartIndex >= TotalRecordCount）。失败返回空列表。

        ⚠️ v4.6.99：需要区分「查询失败」与「真空结果」时请用
        `get_series_episodes_status()`（本方法为兼容包装）。
        """
        try:
            _st, _items, _ = self.get_series_episodes_status(series_id, limit=limit)
        except Exception:
            return []
        return _items if _st == ITEM_FOUND else []

    def query_items_status(self, params: Optional[dict] = None) -> tuple:
        """通用条目查询 + 三态（v4.6.99 · P1-01）→ `(status, data, reason)`。

        data 恒为 `{"Items": [...], "TotalRecordCount": n}`（失败时为空结构）。
        供「季容器集列表枚举」等需要判断枚举是否可信的场景使用。
        """
        _empty = {"Items": [], "TotalRecordCount": 0}
        try:
            uid = self._get_user_id()
        except Exception:
            uid = None
        if not uid:
            return ITEM_UNAVAILABLE, dict(_empty), "no_user_id"
        _st, _r = self._get_status(f"/Users/{uid}/Items", params or {})
        if _st == ITEM_NOT_FOUND:
            return ITEM_NOT_FOUND, dict(_empty), "http_404"
        if _st != ITEM_FOUND:
            return ITEM_UNAVAILABLE, dict(_empty), "http_error"
        _r = _r or {}
        try:
            _total = int(_r.get("TotalRecordCount") or 0)
        except Exception:
            _total = 0
        return ITEM_FOUND, {"Items": _r.get("Items") or [], "TotalRecordCount": _total}, ""

    def query_items(self, params: Optional[dict] = None) -> Dict[str, Any]:
        """通用条目查询（探测入库用）—— 支持 ParentId/IncludeItemTypes/Fields/
        StartIndex/Limit 等，返回 {"Items": [...], "TotalRecordCount": n}。
        Limit=1 时可只取 TotalRecordCount（轻查计数，极小响应）。失败返回空。"""
        try:
            uid = self._get_user_id()
            path = f"/Users/{uid}/Items" if uid else "/Items"
            r = self._get(path, params or {})
            r = r or {}
            return {"Items": r.get("Items") or [],
                    "TotalRecordCount": int(r.get("TotalRecordCount") or 0)}
        except Exception as e:
            logger.warning(f"[EmbyClient] 条目查询失败: {e}")
            return {"Items": [], "TotalRecordCount": 0}

    def list_all_persons(self, limit: int = 500, start_index: int = 0) -> Dict[str, Any]:
        """分页拉取 Emby 全部 Person（人名池「全库 Person」拉取用，文档 §2.3）。
        返回 {"Items": [{"Id","Name","ProviderIds"}...], "TotalRecordCount": n}；失败返回空。"""
        try:
            params = {
                "Recursive": "true",
                "Fields": "ProviderIds",
                "StartIndex": max(0, int(start_index or 0)),
                "Limit": max(1, int(limit or 500)),
            }
            r = self._get("/Persons", params) or {}
            return {"Items": r.get("Items") or [],
                    "TotalRecordCount": int(r.get("TotalRecordCount") or 0)}
        except Exception as e:
            logger.warning(f"[EmbyClient] 拉取 Person 列表失败: {e}")
            return {"Items": [], "TotalRecordCount": 0}

    def find_person_by_name(self, name: str, tmdbid: str = "") -> Optional[dict]:
        """在 Emby 中查找 Person 实体（先按 tmdbid 精确匹配，再按原名完全相同兜底）。
        返回 {Id, Name, ProviderIds}；找不到返回 None。
        背景：Emby 的演员名以 Person 实体为准，nfo 的 <name> 会被它覆盖，
        所以「翻译人名」最终必须落到 Person 实体改名上。"""
        nm = str(name or "").strip()
        if not nm:
            return None
        try:
            r = self._get("/Persons", {"SearchTerm": nm, "Limit": 30, "Recursive": "true"})
            items = (r or {}).get("Items") or []
            _want_tmdb = str(tmdbid or "").strip()
            if _want_tmdb:
                for it in items:
                    prov = it.get("ProviderIds") or {}
                    _pt = str(prov.get("tmdb") or prov.get("Tmdb") or "").strip()
                    if _pt and _pt == _want_tmdb:
                        return {"Id": str(it.get("Id") or ""), "Name": str(it.get("Name") or ""),
                                "ProviderIds": prov}
            for it in items:
                if str(it.get("Name") or "").strip() == nm:
                    return {"Id": str(it.get("Id") or ""), "Name": str(it.get("Name") or ""),
                            "ProviderIds": it.get("ProviderIds") or {}}
        except Exception as e:
            logger.warning(f"[EmbyClient] 查找 Person 失败 {nm}: {e}")
        return None

    def find_persons_by_name(self, name: str, limit: int = 30) -> List[dict]:
        """返回所有「名称完全相同」的 Person —— 用于检测同名多候选。
        只有唯一候选才允许按名字回退改名；多个候选必须失败（不自动猜）。
        返回 [{"Id","Name","ProviderIds"}...]；失败/无匹配返回 []。"""
        nm = str(name or "").strip()
        if not nm:
            return []
        try:
            r = self._get("/Persons", {"SearchTerm": nm, "Limit": max(1, int(limit or 30)),
                                       "Recursive": "true", "Fields": "ProviderIds"})
            items = (r or {}).get("Items") or []
            return [{"Id": str(it.get("Id") or ""), "Name": str(it.get("Name") or ""),
                     "ProviderIds": it.get("ProviderIds") or {}}
                    for it in items if str(it.get("Name") or "").strip() == nm]
        except Exception as e:
            logger.warning(f"[EmbyClient] 查找同名 Person 失败 {nm}: {e}")
            return []

    def get_person_by_id(self, person_id: str) -> Optional[dict]:
        """按 Person ID 查询实体 —— 判定「ID 是否仍有效」。
        ID 仍能取到 → rename 失败应记失败、禁止按名字回退（防误改同名人物）；
        取不到（已删除/失效）才允许回退。返回 {Id,Name,ProviderIds} 或 None。"""
        pid = str(person_id or "").strip()
        if not pid:
            return None
        try:
            uid = self._get_user_id()
            path = f"/Users/{uid}/Items/{pid}" if uid else f"/emby/Items/{pid}"
            it = self._get(path, {"Fields": "ProviderIds"})
            it = it or {}
            if str(it.get("Id") or "").strip():
                return {"Id": str(it.get("Id") or ""), "Name": str(it.get("Name") or ""),
                        "ProviderIds": it.get("ProviderIds") or {}}
        except Exception as e:
            logger.debug(f"[EmbyClient] 按 ID 查 Person 失败 {pid}: {e}")
        return None

    def rename_person(self, person_id: str, new_name: str,
                      provider_ids: Optional[dict] = None) -> bool:
        """重命名 Emby Person 实体（改完 Emby 界面/条目立即生效，
        且 Emby 会把 nfo 的 <name> 自动回写成新名字，形成闭环）。

        Emby POST /Items/{id} 按「整份对象」覆盖式保存：只提交稀疏 DTO
        （Id/Name/Type/ProviderIds）会清空 Overview / LockedFields / 图片 /
        其它 ProviderIds 等属性。因此必须先 GET 完整 Person DTO，仅覆盖 Name
        后整份回写；provider_ids 仅作取不到完整 DTO 时的兜底。"""
        pid = str(person_id or "").strip()
        nn = str(new_name or "").strip()
        if not pid or not nn:
            return False
        try:
            detail = self.get_person_detail(pid)
            if isinstance(detail, dict) and detail:
                detail["Name"] = nn
                if self._post(f"/emby/Items/{pid}", detail):
                    return True
            # 兜底：完整 DTO 取不到（或整份回写失败）时退化为最小 DTO（含 provider_ids）
            body = {"Id": pid, "Name": nn, "Type": "Person",
                    "ProviderIds": provider_ids or {}}
            if self._post(f"/emby/Items/{pid}", body):
                return True
            # 个别版本对 ProviderIds 校验严格 → 去掉再试一次
            return bool(self._post(f"/emby/Items/{pid}", {"Id": pid, "Name": nn, "Type": "Person"}))
        except Exception as e:
            logger.warning(f"[EmbyClient] 重命名 Person 失败 {pid}: {e}")
            return False

    def get_person_detail(self, person_id: str) -> Optional[dict]:
        """取 Person 完整详情（TMDB 补译用）—— 写回前必须先取全量 DTO：
        Emby POST /Items/{id} 按整份对象覆盖，只提交部分字段会清空其它属性。
        对齐 personmeta get_iteminfo（Emby 分支：Fields=ChannelMappingInfo）。"""
        pid = str(person_id or "").strip()
        if not pid:
            return None
        try:
            uid = self._get_user_id()
            path = f"/Users/{uid}/Items/{pid}" if uid else f"/emby/Items/{pid}"
            it = self._get(path, {"Fields": "ChannelMappingInfo"})
            if it and str(it.get("Id") or "").strip():
                return it
        except Exception as e:
            logger.debug(f"[EmbyClient] 取 Person 详情失败 {pid}: {e}")
        return None

    def update_person_info(self, person_id: str, iteminfo: dict) -> bool:
        """写回 Person 详情（整份 DTO，含 LockedFields）——
        对齐 personmeta set_iteminfo（Emby 分支：POST /emby/Items/{id}，application/json）。"""
        pid = str(person_id or "").strip()
        if not pid or not isinstance(iteminfo, dict) or not iteminfo:
            return False
        try:
            return bool(self._post(f"/emby/Items/{pid}", iteminfo))
        except Exception as e:
            logger.warning(f"[EmbyClient] 写回 Person 详情失败 {pid}: {e}")
            return False

    def set_person_primary_image(self, person_id: str, image_bytes: bytes) -> bool:
        """上传 Person 头像（Primary）—— 对齐 personmeta set_item_image（Emby 分支）：
        body 为图片字节的 base64 字符串（非 JSON），Content-Type: image/png。"""
        pid = str(person_id or "").strip()
        if not pid or not image_bytes:
            return False
        url = f"{self.base_url}/emby/Items/{pid}/Images/Primary"
        try:
            b64 = base64.b64encode(image_bytes).decode()
            resp = self.session.post(url, data=b64, headers={"Content-Type": "image/png"},
                                     timeout=self.timeout)
            if resp.status_code in (200, 204):
                return True
            logger.warning(f"[EmbyClient] 上传 Person 头像失败 {pid} 返回 {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.warning(f"[EmbyClient] 上传 Person 头像异常 {pid}: {e}")
            return False

    def _get_user_id(self) -> Optional[str]:
        """获取用户 ID"""
        if self._user_id:
            return self._user_id
        if self.service and self.service.instance:
            uid = getattr(self.service.instance, 'user', None)
            if uid:
                return uid
        if self.service:
            uid = getattr(self.service, 'user_id', None)
            if uid:
                return uid
        return self._get_admin_user_id()

    def _get_admin_user_id(self) -> Optional[str]:
        """获取管理员用户 ID"""
        try:
            data = self._get("/Users") or []
            for u in data:
                policy = u.get("Policy", {})
                if policy.get("IsAdministrator"):
                    return u.get("Id")
            return data[0].get("Id") if data else None
        except Exception:
            return None

    def get_libraries(self) -> List[Dict[str, Any]]:
        """获取所有媒体库（Id/Name/Path），只读、无任何写回。

        只取真实库路径：/Library/VirtualFolders 的 Locations（即 Emby 界面里
        展示的库路径，如 /media/示例库/动画电影）。不再使用 /Library/MediaFolders
        的虚拟 Path（旧库路径易失真）。供「媒体库选择」映射扫描根目录。
        """
        result = []
        try:
            data = self._get("/Library/VirtualFolders")
            items = data if isinstance(data, list) else (data or {}).get("Items", []) or []
            for item in items:
                locs = item.get("Locations") or []
                path = next((str(x).strip() for x in locs if str(x or "").strip()), "")
                lib_id = str(item.get("ItemId") or item.get("Id") or "")
                name = item.get("Name") or ""
                if not lib_id:
                    continue
                result.append({
                    "Id": lib_id,
                    "Name": name,
                    "Type": item.get("CollectionType", "") or "unknown",
                    "Path": path,
                })
        except Exception as e:
            logger.warning(f"[Libraries] VirtualFolders 获取库列表失败: {e}")
        return result

    _ITEM_FIELDS = ("People,LockedFields,Id,Name,ProductionYear,PremiereDate,Type,MediaType,Path,"
                    "SeriesName,ParentIndexNumber,IndexNumber,SeasonNumber,EpisodeNumber")

    def fetch_item_status(self, item_id: str) -> tuple:
        """获取条目详情 + **存在性三态**（v4.6.98 · P1-01）—— 返回 `(status, data)`。

        - `(ITEM_FOUND, {...})`      条目存在；
        - `(ITEM_NOT_FOUND, None)`   Emby 明确回答不存在（404）—— 唯一可作「已删除」依据；
        - `(ITEM_UNAVAILABLE, None)` 无 user_id / 超时 / 401 / 500 / 响应非法 / 客户端不可用
                                    → **状态未知**，调用方不得据此判定容器已删除。
        """
        _iid = str(item_id or "").strip()
        if not _iid:
            return ITEM_UNAVAILABLE, None
        try:
            user_id = self._get_user_id()
        except Exception:
            user_id = None
        if not user_id:
            logger.warning("[EmbyClient] 无 user_id → 条目存在性未知（按 UNAVAILABLE 处理，不当作已删除）")
            return ITEM_UNAVAILABLE, None
        return self._get_status(f"/Users/{user_id}/Items/{_iid}",
                                params={"Fields": self._ITEM_FIELDS})

    def fetch_item(self, item_id: str) -> Optional[dict]:
        """获取条目完整详情（包含 Emby 实际的季集字段 ParentIndexNumber/IndexNumber）。

        兼容旧调用：拿不到就返回 None（不区分「不存在」与「查询失败」）。
        ⚠️ 删除事件等需要区分原因的场景，请改用 `fetch_item_status()`。
        """
        try:
            _st, _d = self.fetch_item_status(item_id)
        except Exception:
            return None
        return _d if _st == ITEM_FOUND else None

    def close(self) -> None:
        """释放底层 requests 会话（连接池）—— 批量任务一次性创建的
        客户端在任务结束时统一 close()，避免长连接/套接字滞留。幂等，可重复调用。"""
        try:
            self.session.close()
        except Exception:
            pass

