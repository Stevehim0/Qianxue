"""短期记忆（STM）HTTP 客户端。

通过 HTTP 调用 Memory 服务的 STM API，
记录事件和获取跨会话感知文本。
"""

import logging
from typing import Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


class STMClient:
    """短期记忆 HTTP 客户端。

    使用 httpx.AsyncClient 调用 Memory 服务的 STM 端点。
    所有方法都有降级处理，不会因 Memory 服务不可用而阻塞主流程。
    """

    def __init__(self, base_url: str = ""):
        self.base_url = (base_url or settings.memory.service_url).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=settings.memory.stm_connect_timeout,
                    read=settings.memory.stm_read_timeout,
                    write=settings.memory.stm_write_timeout,
                    pool=settings.memory.stm_pool_timeout,
                ),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def record_event(
        self,
        event_type: str,
        source_type: str,
        group_id: str,
        user_id: Optional[str] = None,
        summary: str = "",
        detail: Optional[str] = None,
        importance: float = 0.5,
    ) -> dict:
        """记录一个 STM 事件（fire-and-forget，失败静默）。

        Returns:
            API 响应字典，失败时返回 {"success": False}
        """
        try:
            client = await self._get_client()
            resp = await client.post("/api/stm/event", json={
                "event_type": event_type,
                "source_type": source_type,
                "group_id": group_id,
                "user_id": user_id,
                "summary": summary,
                "detail": detail,
                "importance": importance,
            })
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.debug(f"STM record_event failed: {resp.status_code}")
                return {"success": False}
        except Exception as e:
            logger.debug(f"STM record_event error: {e}")
            return {"success": False}

    async def get_perception(self, hours: float = 6.0) -> Optional[str]:
        """获取格式化的感知文本。

        Returns:
            感知文本字符串，如果没有事件或调用失败返回 None
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                "/api/stm/perception",
                params={"hours": hours},
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("perception_text", "")
                return text if text else None
            else:
                logger.debug(f"STM get_perception failed: {resp.status_code}")
                return None
        except Exception as e:
            logger.debug(f"STM get_perception error: {e}")
            return None


# 模块级单例
stm_client = STMClient()
