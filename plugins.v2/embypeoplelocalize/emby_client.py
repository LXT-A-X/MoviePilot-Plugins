"""
emby_client.py - Emby 服务器 API 封装
v0.9.0 重构版 - 简化代码，添加写回验证
"""
import json
import time
from typing import Any, Dict, List, Optional

import requests
from app.log import logger
from app.schemas import ServiceInfo

from . import constants


def clean_emby_payload(payload: Dict[str, Any],
                       preserve: Optional[List[str]] = None) -> Dict[str, Any]:
    """v1.3.1: 统一清理 Emby 写回 payload

    Emby API 对部分字段敏感，写回前必须强制清理：
    1. 移除 EMBY_STRIP_FIELDS 中定义的只读/敏感字段
    2. 移除值为 None 的字段

    :param payload: 原始 payload
    :param preserve: 必须保留的字段（默认 Id/People/LockedFields）
    :return: 清理后的 payload 副本
    """
    preserve = set(preserve or ["Id", "People", "LockedFields"])
    cleaned = dict(payload)
    # 1. 清理敏感字段
    for field in constants.EMBY_STRIP_FIELDS:
        if field in cleaned and field not in preserve:
            del cleaned[field]
    # 2. 清理 None 值
    for k in list(cleaned.keys()):
        if cleaned[k] is None:
            del cleaned[k]
    return cleaned


class EmbyClient:
    """Emby API 客户端"""

    def __init__(self, base_url: str, api_key: str, service: Optional[ServiceInfo] = None,
                 user_id: Optional[str] = None,
                 timeout: tuple = (10, 60),
                 use_proxy: bool = False):
        """v1.2.8: timeout 提升到 (10, 60)
        - 连接超时 10s
        - 读取超时 60s
        大型 NAS / 2000+ 媒体库时 10s 读取往往不够，60s 更稳定

        v1.3.1: use_proxy 参数 - 控制是否信任系统代理环境变量
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
        # v1.3.1: 代理可配置 - 默认不读系统代理，避免污染
        self.session.trust_env = use_proxy
        # v1.2.8: 超时从 (5, 10) 提升到 (10, 60) - 解决 NAS/大型库响应慢导致的请求失败
        self.timeout = timeout

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET 请求"""
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[EmbyClient] GET {url} 失败: {e}")
            return None

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
        """获取所有媒体库
        v1.2.6: 不再根据 CollectionType 过滤，
        避免自定义类型/混合库被误过滤
        """
        data = self._get("/Library/MediaFolders")
        items = (data or {}).get("Items", []) or []
        result = []
        for item in items:
            # 不再过滤 CollectionType，统一返回所有媒体库
            result.append({
                "Id": str(item.get("Id", "")),
                "Name": item.get("Name", ""),
                "Type": item.get("CollectionType", "") or "unknown",
            })
        return result

    def fetch_item(self, item_id: str) -> Optional[dict]:
        """获取条目完整详情
        v1.2.4: 包含 Emby 实际的季集字段 ParentIndexNumber/IndexNumber
        """
        params = {
            "Fields": "People,LockedFields,Id,Name,ProductionYear,PremiereDate,Type,MediaType,Path,"
                      "SeriesName,ParentIndexNumber,IndexNumber,SeasonNumber,EpisodeNumber"
        }
        user_id = self._get_user_id()
        if not user_id:
            return None
        return self._get(f"/Users/{user_id}/Items/{item_id}", params=params)

    def fetch_items_page(self, library_id: str,
                         limit: int = 50, start_index: int = 0,
                         include_people: bool = False,
                         recursive: bool = True) -> Optional[dict]:
        """分页获取媒体库条目
        v1.2.6: 优化性能 - 列表查询默认不包含 People 字段
        People 字段会显著增加响应体积（一项可能几十个演员），
        改为按需在 _process_item 中单独 fetch_item 获取
        """
        # v1.2.6: 字段精简 - 列表只获取基础字段
        # People 通过 fetch_item 单独获取（更高效，因为已处理的 item 会跳过）
        fields = "Id,Name,ProductionYear,PremiereDate,Type,SeriesName,ParentIndexNumber,IndexNumber"
        if include_people:
            fields += ",People"
        params = {
            "ParentId": library_id,
            "Limit": limit,
            "StartIndex": start_index,
            "Recursive": "true" if recursive else "false",
            "Fields": fields,
        }
        user_id = self._get_user_id()
        if not user_id:
            return None
        return self._get(f"/Users/{user_id}/Items", params=params)

    def update_people(self, item_id: str, new_people: List[dict],
                      lock_cast: bool = False) -> int:
        """更新条目演职人员列表"""
        if not new_people:
            return 0

        full_item = self.fetch_item(item_id)
        if not full_item:
            logger.warning(f"[EmbyClient] [{item_id}] 无法获取完整条目，跳过更新")
            return 0

        payload = dict(full_item)
        payload["Id"] = item_id
        payload["People"] = new_people

        if lock_cast:
            locked_fields = list(full_item.get("LockedFields") or [])
            if "Cast" not in locked_fields:
                locked_fields.append("Cast")
                logger.info(f"[EmbyClient] [{item_id}] LockedFields 追加 Cast: {locked_fields}")
            payload["LockedFields"] = locked_fields

        # v1.3.1: 强制 clean payload - 不依赖调用方，Emby API 对部分字段敏感
        payload = clean_emby_payload(payload)

        if self._post(f"/Items/{item_id}", payload):
            changes = sum(1 for p in new_people if p.get("Name"))
            logger.info(f"[EmbyClient] [{item_id}] 写入成功: {changes} 个 (锁定={lock_cast})")
            return changes

        logger.error(f"[EmbyClient] [{item_id}] 写入失败")
        return 0

    def verify_write(self, item_id: str, expected_names: List[str] = None) -> bool:
        """验证写回是否成功
        v1.2.7: 内容验证 - 检查目标名字是否真的写入了
        expected_names: 期望在 People 中存在的名字列表（翻译后的中文名）
        """
        time.sleep(0.5)
        item = self.fetch_item(item_id)
        if not item:
            return False
        people = item.get("People", []) or []
        if not people:
            return False
        # v1.2.7: 内容验证 - 如果提供了期望名字，必须至少找到一个
        if expected_names:
            current_names = {p.get("Name", "").strip() for p in people if p.get("Name")}
            for name in expected_names:
                if name and name.strip() in current_names:
                    return True
            return False
        return True  # 兼容旧调用：只要 People 非空就算成功

    def is_cast_locked(self, item_id: str) -> bool:
        """判断 Cast 是否已锁定"""
        item = self.fetch_item(item_id)
        if not item:
            return False
        return "Cast" in (item.get("LockedFields") or [])

    def lock_cast_for_item(self, item_id: str) -> bool:
        """对单个条目追加 Cast 到 LockedFields"""
        item = self.fetch_item(item_id)
        if not item:
            return False
        lf = list(item.get("LockedFields") or [])
        if "Cast" in lf:
            return True
        lf.append("Cast")
        payload = dict(item)
        payload["Id"] = item_id
        payload["LockedFields"] = lf
        # v1.3.1: 统一使用 clean_emby_payload
        payload = clean_emby_payload(payload)
        return self._post(f"/Items/{item_id}", payload)

    def refresh_item(self, item_id: str):
        """触发条目元数据刷新"""
        params = {
            "Recursive": "false",
            "MetadataRefreshMode": "FullRefresh",
            "ImageRefreshMode": "FullRefresh",
        }
        user_id = self._get_user_id()
        if not user_id:
            return
        self._post(f"/Users/{user_id}/Items/{item_id}/Refresh", data=params)
