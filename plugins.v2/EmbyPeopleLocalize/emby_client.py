"""
emby_client.py - Emby 服务器 API 封装
支持：获取媒体库、分页拉取条目、更新演职人员、Cast 锁定
"""
import json
import time
from typing import Any, Dict, List, Optional

import requests

from app.schemas import ServiceInfo


class EmbyClient:
    """Emby API 客户端"""

    def __init__(self, base_url: str, api_key: str, service: Optional[ServiceInfo] = None,
                 user_id: Optional[str] = None):
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
        # 内网通信不走代理
        self.session.trust_env = False
        # 超时设置
        self.timeout = (5, 10)  # 连接5秒，读取10秒

    # ──────────────────────────────────────
    # 基础请求
    # ──────────────────────────────────────
    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[EmbyClient] GET {url} 失败: {e}")
            return None

    def _post(self, path: str, data: Optional[dict] = None) -> bool:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.post(url, json=data, timeout=self.timeout)
            if resp.status_code in (200, 204):
                return True
            print(f"[EmbyClient] POST {url} 返回 {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"[EmbyClient] POST {url} 失败: {e}")
            return False

    # ──────────────────────────────────────
    # 媒体库 / 条目读取
    # ──────────────────────────────────────
    def get_libraries(self) -> List[Dict[str, Any]]:
        """获取所有媒体库"""
        data = self._get("/Library/MediaFolders")
        items = (data or {}).get("Items", []) or []
        result = []
        for item in items:
            if item.get("CollectionType"):
                result.append({
                    "Id": str(item.get("Id", "")),
                    "Name": item.get("Name", ""),
                    "Type": item.get("CollectionType", ""),
                })
        return result

    def _get_user_id(self, service: ServiceInfo) -> Optional[str]:
        """根据服务配置获取 Emby UserId，优先使用构造函数传入的 user_id"""
        # 1. 直接使用构造函数传入的 user_id
        if self._user_id:
            return self._user_id
        # 2. 从 service.instance.user 提取
        inst = service.instance
        if inst:
            uid = getattr(inst, 'user', None)
            if uid:
                return uid
        # 3. 从 service 属性
        uid = getattr(service, 'user_id', None)
        if uid:
            return uid
        # 4. 回退到第一个管理员
        return self._get_admin_user_id()

    def fetch_item(self, service: ServiceInfo, item_id: str) -> Optional[dict]:
        """获取条目完整详情（含 People / LockedFields）"""
        params = {
            "Fields": "People,LockedFields,Id,Name,ProductionYear,PremiereDate,Type,MediaType,Path"
        }
        user_id = self._get_user_id(service)
        if not user_id:
            return None
        return self._get(f"/Users/{user_id}/Items/{item_id}", params=params)

    def fetch_items_page(self, service: ServiceInfo, library_id: str,
                         limit: int = 50, start_index: int = 0) -> Optional[dict]:
        """分页获取媒体库条目"""
        params = {
            "ParentId": library_id,
            "Limit": limit,
            "StartIndex": start_index,
            "Recursive": "true",
            "Fields": "Id,Name,ProductionYear,PremiereDate,People,Type,LockedFields",
        }
        user_id = self._get_user_id(service)
        if not user_id:
            return None
        return self._get(f"/Users/{user_id}/Items", params=params)

    def _get_admin_user_id(self) -> Optional[str]:
        try:
            data = self._get("/Users") or []
            for u in data:
                policy = u.get("Policy", {})
                if policy.get("IsAdministrator"):
                    return u.get("Id")
            return data[0].get("Id") if data else None
        except Exception:
            return None

    # ──────────────────────────────────────
    # 写回：更新演职人员
    # ──────────────────────────────────────
    def update_people(self, service: ServiceInfo, item_id: str,
                      new_people: List[dict], item_data: Optional[dict] = None,
                      lock_cast: bool = False) -> int:
        """
        更新条目演职人员列表
        必须拉取完整条目信息后提交，禁止局部更新
        lock_cast=True  → 追加 "Cast" 到 LockedFields
        lock_cast=False → 只更新 People，不动 LockedFields
        返回成功更新的字段数
        """
        if not new_people:
            return 0

        # 总是重新拉取完整条目，避免使用分页/精简数据导致 Emby 报 "source" 为空
        full_item = self.fetch_item(service, item_id)
        if not full_item:
            print(f"[EmbyClient] [{item_id}] 无法获取完整条目，跳过更新")
            return 0

        payload = dict(full_item)
        payload["Id"] = item_id
        payload["People"] = new_people

        if lock_cast:
            locked_fields = list(full_item.get("LockedFields") or [])
            if "Cast" not in locked_fields:
                locked_fields.append("Cast")
                print(f"[EmbyClient] [{item_id}] LockedFields 追加 Cast: {locked_fields}")
            payload["LockedFields"] = locked_fields

        # 剔除只读字段（People 和 LockedFields 不能删！）
        from . import constants
        for field in constants.EMBY_STRIP_FIELDS:
            if field in payload and field not in ("Id", "People", "LockedFields"):
                del payload[field]

        # 删除 None 值
        for k in list(payload.keys()):
            if payload[k] is None:
                del payload[k]

        if self._post(f"/Items/{item_id}", payload):
            changes = sum(1 for p in new_people if p.get("Name"))
            print(f"[EmbyClient] [{item_id}] 写入成功: {changes} 个 (锁定={lock_cast})")
            return changes

        print(f"[EmbyClient] [{item_id}] 写入失败")
        return 0

    # ──────────────────────────────────────
    # Cast 锁定查询 / 操作
    # ──────────────────────────────────────
    def get_locked_fields(self, service: ServiceInfo, item_id: str) -> List[str]:
        """获取条目的 LockedFields 列表"""
        item = self.fetch_item(service, item_id)
        if not item:
            return []
        return list(item.get("LockedFields") or [])

    def is_cast_locked(self, service: ServiceInfo, item_id: str) -> bool:
        """判断 Cast 是否已锁定"""
        return "Cast" in self.get_locked_fields(service, item_id)

    def lock_cast_for_item(self, service: ServiceInfo, item_id: str) -> bool:
        """对单个条目追加 Cast 到 LockedFields（携带完整条目信息提交）"""
        item = self.fetch_item(service, item_id)
        if not item:
            return False
        lf = list(item.get("LockedFields") or [])
        if "Cast" in lf:
            return True  # 已经锁了
        lf.append("Cast")
        payload = dict(item)
        payload["Id"] = item_id
        payload["LockedFields"] = lf
        # 剔除只读字段
        from . import constants
        for field in constants.EMBY_STRIP_FIELDS:
            if field in payload and field not in ("Id", "LockedFields"):
                del payload[field]
        # 删除 None 值
        for k in list(payload.keys()):
            if payload[k] is None:
                del payload[k]
        return self._post(f"/Items/{item_id}", payload)

    # ──────────────────────────────────────
    # 刷新
    # ──────────────────────────────────────
    def refresh_item(self, service: ServiceInfo, item_id: str):
        """触发条目元数据刷新"""
        params = {
            "Recursive": "false",
            "MetadataRefreshMode": "FullRefresh",
            "ImageRefreshMode": "FullRefresh",
        }
        user_id = getattr(service, 'user_id', None) or self._get_admin_user_id()
        if not user_id:
            return
        self._post(f"/Users/{user_id}/Items/{item_id}/Refresh", data=params)
