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
        self.session.trust_env = False
        self.timeout = (5, 10)

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

    def get_libraries(self) -> List[Dict[str, Any]]:
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
        if self._user_id:
            return self._user_id
        inst = service.instance
        if inst:
            uid = getattr(inst, 'user', None)
            if uid:
                return uid
        uid = getattr(service, 'user_id', None)
        if uid:
            return uid
        return self._get_admin_user_id()

    def fetch_item(self, service: ServiceInfo, item_id: str) -> Optional[dict]:
        params = {
            "Fields": "People,LockedFields,Id,Name,ProductionYear,PremiereDate,Type,MediaType,Path"
        }
        user_id = self._get_user_id(service)
        if not user_id:
            return None
        return self._get(f"/Users/{user_id}/Items/{item_id}", params=params)

    def fetch_items_page(self, service: ServiceInfo, library_id: str,
                         limit: int = 50, start_index: int = 0) -> Optional[dict]:
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

    def update_people(self, service: ServiceInfo, item_id: str,
                      new_people: List[dict], item_data: Optional[dict] = None,
                      lock_cast: bool = False) -> int:
        if not new_people:
            return 0
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
        from . import constants
        for field in constants.EMBY_STRIP_FIELDS:
            if field in payload and field not in ("Id", "People", "LockedFields"):
                del payload[field]
        for k in list(payload.keys()):
            if payload[k] is None:
                del payload[k]
        if self._post(f"/Items/{item_id}", payload):
            changes = sum(1 for p in new_people if p.get("Name"))
            print(f"[EmbyClient] [{item_id}] 写入成功: {changes} 个 (锁定={lock_cast})")
            return changes
        print(f"[EmbyClient] [{item_id}] 写入失败")
        return 0

    def get_locked_fields(self, service: ServiceInfo, item_id: str) -> List[str]:
        item = self.fetch_item(service, item_id)
        if not item:
            return []
        return list(item.get("LockedFields") or [])

    def is_cast_locked(self, service: ServiceInfo, item_id: str) -> bool:
        return "Cast" in self.get_locked_fields(service, item_id)

    def lock_cast_for_item(self, service: ServiceInfo, item_id: str) -> bool:
        item = self.fetch_item(service, item_id)
        if not item:
            return False
        lf = list(item.get("LockedFields") or [])
        if "Cast" in lf:
            return True
        lf.append("Cast")
        payload = dict(item)
        payload["Id"] = item_id
        payload["LockedFields"] = lf
        from . import constants
        for field in constants.EMBY_STRIP_FIELDS:
            if field in payload and field not in ("Id", "LockedFields"):
                del payload[field]
        for k in list(payload.keys()):
            if payload[k] is None:
                del payload[k]
        return self._post(f"/Items/{item_id}", payload)

    def refresh_item(self, service: ServiceInfo, item_id: str):
        params = {
            "Recursive": "false",
            "MetadataRefreshMode": "FullRefresh",
            "ImageRefreshMode": "FullRefresh",
        }
        user_id = getattr(service, 'user_id', None) or self._get_admin_user_id()
        if not user_id:
            return
        self._post(f"/Users/{user_id}/Items/{item_id}/Refresh", data=params)
