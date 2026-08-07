"""
EmbyPeopleLocalize - API 路由

提供 Vue 前端所需的数据接口：
- GET  /stats       - 统计数据
- GET  /history     - 分页翻译历史（支持搜索/筛选）
- GET  /libraries   - 可用的媒体库列表
- GET  /item_image  - 获取 Emby 条目的海报图片 URL
"""

from typing import Any, Dict, List, Optional

from fastapi import Request, Query
from app.log import logger


def build_api_routes(plugin_instance) -> List[Dict[str, Any]]:
    """构建 API 路由列表，由 __init__.py 的 get_api() 调用"""

    async def api_stats(request: Request) -> Dict[str, Any]:
        """GET /stats - 返回统计数据"""
        try:
            history = list(plugin_instance._history or [])
            return {
                "titles": len(history),
                "fields": sum(int(h.get("n_trans") or 0) for h in history),
                "history_count": len(history),
                "cached": len(plugin_instance._name_cache or {}),
            }
        except Exception as e:
            logger.error(f"API /stats 异常: {e}")
            return {"titles": 0, "fields": 0, "history_count": 0, "cached": 0}

    async def api_history(
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        search: Optional[str] = Query(None),
        lib: Optional[str] = Query(None),
    ) -> Dict[str, Any]:
        """GET /history - 返回分页翻译历史，支持搜索和按库筛选"""
        try:
            history = list(plugin_instance._history or [])
            # 搜索过滤
            if search:
                s = search.strip().lower()
                history = [h for h in history if s in str(h.get("title", "")).lower()]

            # 按库筛选
            if lib:
                l = lib.strip()
                history = [h for h in history if str(h.get("lib", "")) == l]

            total = len(history)
            start = (page - 1) * limit
            end = start + limit
            items = history[start:end]

            # 为每个条目尝试获取海报 URL
            result_items = []
            for h in items:
                item = dict(h)
                item_id = item.get("item_id", "")
                server = item.get("server", "")
                poster_url = None
                if item_id and server:
                    try:
                        poster_url = _get_poster_url(plugin_instance, server, item_id)
                    except Exception:
                        poster_url = None
                item["poster_url"] = poster_url
                result_items.append(item)

            return {
                "items": result_items,
                "total": total,
                "page": page,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"API /history 异常: {e}")
            return {"items": [], "total": 0, "page": page, "limit": limit}

    async def api_libraries(request: Request) -> List[str]:
        """GET /libraries - 返回所有可用的媒体库名称"""
        try:
            history = list(plugin_instance._history or [])
            libs = list(dict.fromkeys(
                str(h.get("lib", "")).strip()
                for h in history
                if str(h.get("lib", "")).strip()
            ))
            return sorted(libs)
        except Exception as e:
            logger.error(f"API /libraries 异常: {e}")
            return []

    async def api_item_image(
        request: Request,
        server: str = Query(""),
        item_id: str = Query(""),
    ) -> Dict[str, Any]:
        """GET /item_image - 返回 Emby 条目的海报图片 URL（302 重定向到 Emby）"""
        try:
            url = _get_poster_url(plugin_instance, server, item_id)
            return {"url": url or ""}
        except Exception as e:
            logger.error(f"API /item_image 异常: {e}")
            return {"url": ""}

    return [
        {"path": "/stats", "endpoint": api_stats, "methods": ["GET"]},
        {"path": "/history", "endpoint": api_history, "methods": ["GET"]},
        {"path": "/libraries", "endpoint": api_libraries, "methods": ["GET"]},
        {"path": "/item_image", "endpoint": api_item_image, "methods": ["GET"]},
    ]


def _get_poster_url(plugin_instance, server_name: str, item_id: str) -> Optional[str]:
    """获取 Emby 条目的 Primary 图片 URL"""
    if not server_name or not item_id:
        return None
    try:
        from app.helper.mediaserver import MediaServerHelper
        helper = MediaServerHelper()
        services = helper.get_services(type_filter="emby", name_filters=[server_name]) or {}
        service = services.get(server_name)
        if not service:
            return None
        host, api_key = plugin_instance._get_emby_info(service)
        if not host or not api_key:
            return None
        return f"{host}/Items/{item_id}/Images/Primary?api_key={api_key}&maxWidth=120&maxHeight=168&quality=80"
    except Exception:
        return None
