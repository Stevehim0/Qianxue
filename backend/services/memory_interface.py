"""记忆系统抽象接口.

新记忆系统只需:
1. 实现本文件中的 MemoryProvider 类
2. 将全局实例 memory_provider 替换为新实现
"""

import logging
from datetime import datetime
from typing import Optional, List

import httpx

from backend.config import settings
from backend.database.models import UserProfile, RetrievedMemory, UserMemory

logger = logging.getLogger(__name__)


class MemoryProvider:
    """记忆系统抽象接口 - 默认空实现.

    所有方法都有默认的空实现，系统可以在无记忆的情况下正常运行。
    新的记忆系统继承此类并覆盖需要的方法即可。
    """

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户档案."""
        return None

    async def retrieve_relevant(
        self,
        query: str,
        user_id: str,
        group_id: str,
        limit: int = 5
    ) -> List[RetrievedMemory]:
        """检索与查询相关的记忆."""
        return []

    async def retrieve_briefing(
        self,
        query: str,
        context: Optional[dict] = None,
    ) -> Optional[str]:
        """通过关键词召回记忆简报."""
        return None

    async def get_ai_state(self) -> dict:
        """获取 AI 当前状态."""
        return {}

    async def extract_and_store(
        self,
        group_id: str,
        user_id: str,
        content: str,
        role: str = "user",
        speaker: str | None = None,
        source_type: str = "qq_group",
    ) -> None:
        """从消息中提取并存储记忆（后台调用，不阻塞主流程）."""
        pass

    async def update_access_stats(self, memory_id: int) -> None:
        """更新记忆访问统计."""
        pass


class QianxueMemoryProvider(MemoryProvider):
    """记忆系统HTTP客户端实现.

    通过HTTP调用独立的Memory HTTP服务。
    """

    def __init__(self, base_url: str = ""):
        self.base_url = (base_url or settings.memory.service_url).rstrip("/")
        # Use a single httpx client for connection pooling
        self._client: Optional[httpx.AsyncClient] = None
        self._nickname_map: dict[str, str] = {}  # user_id -> nickname cache

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=settings.memory.provider_connect_timeout,
                    read=settings.memory.provider_read_timeout,
                    write=settings.memory.provider_write_timeout,
                    pool=settings.memory.provider_pool_timeout,
                ),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health_check(self) -> bool:
        """检查Memory服务是否可用"""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Memory service health check failed: {e}")
            return False

    async def extract_and_store(
        self,
        group_id: str,
        user_id: str,
        content: str,
        role: str = "user",
        speaker: str | None = None,
        source_type: str = "qq_group",
    ) -> None:
        """从消息中提取并存储记忆.

        将消息发送给Memory服务的缓冲区，由缓冲机制决定何时处理。

        Args:
            group_id: 群聊ID（或 private_{user_id}）
            user_id: 用户ID
            content: 消息内容
            role: 角色 ("user" 或 "assistant")
            speaker: 说话者名称（可选，默认从昵称映射查找）
            source_type: 来源类型 ("qq_group" 或 "qq_private")
        """
        try:
            client = await self._get_client()

            if speaker is None:
                speaker = self._nickname_map.get(user_id, f"用户{user_id[-4:] if len(user_id) > 4 else user_id}")

            message_item = {
                "speaker": speaker,
                "content": content,
                "role": role,
            }

            resp = await client.post("/api/event", json={
                "source_type": source_type,
                "source_id": group_id,
                "messages": [message_item],
            })

            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"Memory event buffered: count={data.get('buffer_count')}")
            else:
                logger.warning(f"Failed to buffer memory event: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"Memory extract_and_store failed: {e}")

    async def retrieve_relevant(
        self,
        query: str,
        user_id: str,
        group_id: str,
        limit: int = 5,
        context: Optional[dict] = None,
    ) -> List[RetrievedMemory]:
        """检索与查询相关的记忆.

        调用Memory服务的recall接口，将结果转换为Backend期望的格式。
        """
        try:
            client = await self._get_client()

            recall_context = context or {
                "recent_history": [],
                "ai_state": await self.get_ai_state(),
                "current_time": datetime.now().isoformat(),
            }

            resp = await client.post("/api/recall", json={
                "query": query,
                "context": recall_context,
            })

            if resp.status_code != 200:
                logger.warning(f"Memory recall failed: {resp.status_code}")
                return []

            data = resp.json()
            results: List[RetrievedMemory] = []

            # Convert experiences to RetrievedMemory format
            for exp in data.get("experiences", [])[:limit]:
                # Build content from L0/L1/recall_hint
                content = exp.get("L1_text") or exp.get("L0_text") or exp.get("recall_hint") or ""

                user_memory = UserMemory(
                    id=hash(exp.get("experience_id", "")) % (10**8),  # Convert string ID to int
                    user_id=user_id,
                    group_id=group_id,
                    memory_type="conversation_summary",
                    title=exp.get("L0_text", "")[:50] if exp.get("L0_text") else None,
                    content=content,
                    importance=min(5, max(1, int(exp.get("importance", 0.5) * 5))),
                    source_context=exp.get("experience_id"),
                )

                results.append(RetrievedMemory(
                    memory=user_memory,
                    similarity_score=exp.get("activation_score", 0.0),
                    retrieval_method=exp.get("source_type", "semantic"),
                ))

            # Also include entity information as memories
            for ent in data.get("entities", []):
                if len(results) >= limit:
                    break

                props = ent.get("properties") or {}
                content_parts = [f"{ent.get('name', '未知')} ({ent.get('type', '实体')})"]
                if props:
                    for k, v in props.items():
                        content_parts.append(f"{k}: {v}")

                user_memory = UserMemory(
                    id=hash(ent.get("entity_id", "")) % (10**8),
                    user_id=user_id,
                    group_id=group_id,
                    memory_type="basic_info",
                    title=ent.get("name"),
                    content=" | ".join(content_parts),
                    importance=3,
                )

                results.append(RetrievedMemory(
                    memory=user_memory,
                    similarity_score=ent.get("activation_score", 0.0),
                    retrieval_method="entity_search",
                ))

            return results

        except Exception as e:
            logger.warning(f"Memory retrieve_relevant failed: {e}")
            return []

    async def retrieve_briefing(
        self,
        query: str,
        context: Optional[dict] = None,
    ) -> Optional[str]:
        """通过关键词召回记忆简报.

        调用 Memory 服务的 /api/recall/keywords 接口，返回 briefing 文本。
        """
        try:
            client = await self._get_client()

            recall_context = context or {
                "recent_history": [],
                "ai_state": await self.get_ai_state(),
                "current_time": datetime.now().isoformat(),
            }

            resp = await client.post("/api/recall/keywords", json={
                "query": query,
                "context": recall_context,
            })

            if resp.status_code != 200:
                logger.warning(f"Memory recall by keywords failed: {resp.status_code}")
                return None

            data = resp.json()
            briefing = data.get("briefing")
            logger.info(f"[Memory] recall result: {briefing}")
            return briefing

        except Exception as e:
            logger.warning(f"Memory retrieve_briefing failed: {e}", exc_info=True)
            return None

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户档案.

        尝试通过昵称查找Memory系统中的实体档案。
        """
        try:
            nickname = self._nickname_map.get(user_id)
            if not nickname:
                return None

            client = await self._get_client()
            resp = await client.get(f"/api/profile/{nickname}")

            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data.get("found") or not data.get("profile"):
                return None

            profile = data["profile"]
            basic = profile.get("basic", {})

            return UserProfile(
                user_id=user_id,
                nickname=basic.get("name"),
                bio=f"实体类型: {basic.get('type', '未知')}",
                created_at=basic.get("first_seen"),
            )

        except Exception as e:
            logger.warning(f"Memory get_user_profile failed: {e}")
            return None

    async def get_ai_state(self) -> dict:
        """从 Memory 服务获取 AI 当前状态。

        Returns:
            ai_state 字典，含 mood/energy/focus/confidence。
            获取失败时返回空字典（降级）。
        """
        try:
            client = await self._get_client()
            resp = await client.get("/api/state")
            if resp.status_code == 200:
                data = resp.json()
                state_prompt = data.get("state_prompt", "")
                return {"state_prompt": state_prompt}
        except Exception as e:
            logger.debug(f"Failed to get AI state: {e}")
        return {}

    async def update_access_stats(self, memory_id: int) -> None:
        """更新记忆访问统计（暂不实现）."""
        pass

    def update_nickname_map(self, user_id: str, nickname: str):
        """更新 user_id -> nickname 映射缓存"""
        if nickname:
            self._nickname_map[user_id] = nickname


# 全局单例 - 默认空实现
# 在 main.py 中根据配置替换为 QianxueMemoryProvider
memory_provider = MemoryProvider()
