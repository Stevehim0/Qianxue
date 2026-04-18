"""STM 事件压缩器 — 使用 LLM 将大量事件压缩为简洁摘要。"""

import logging
from datetime import datetime
from typing import List, Optional

from Memory.storage.stm_store import StmEvent, stm_store
from Memory.config.settings import settings

logger = logging.getLogger(__name__)

# 压缩用 prompt
_COMPRESSION_PROMPT = """\
请将以下AI行为记录压缩为简洁的事件摘要（2-3句话），保留关键信息（谁、在哪、做了什么）：

{events_text}

直接输出摘要文本，不要用JSON格式。"""


class StmCompressor:
    """使用 LLM 将累积的 STM 事件压缩为简洁摘要。"""

    def should_compress(self, active_count: int) -> bool:
        """判断是否需要触发压缩。"""
        return active_count >= settings.stm.compression_threshold

    def compress(self, llm_client) -> Optional[str]:
        """执行一次压缩。

        从 stm_events 中取出一批旧事件，用 LLM 生成摘要，
        存入 stm_compressed，然后删除原始事件。

        Args:
            llm_client: LLM 客户端实例（BaseLLMClient 子类）

        Returns:
            生成的摘要文本，如果失败返回 None
        """
        events = stm_store.get_events_for_compression()
        if not events:
            logger.debug("No events to compress")
            return None

        # 构建事件文本
        events_text = self._format_events_for_compression(events)

        try:
            # 调用 LLM 生成压缩摘要
            summary = llm_client.call(
                prompt=_COMPRESSION_PROMPT.format(events_text=events_text),
                system_prompt="你是一个简洁的事件摘要助手。",
                temperature=0.3,
                max_tokens=300,
                response_format="text",
            )

            if not summary or not summary.strip():
                logger.warning("LLM returned empty compression summary")
                return None

            summary = summary.strip()

            # 存储压缩摘要
            event_ids = [e.id for e in events if e.id is not None]
            time_start = events[0].created_at
            time_end = events[-1].created_at

            stm_store.store_compressed(
                summary=summary,
                event_count=len(events),
                time_range_start=time_start,
                time_range_end=time_end,
            )

            # 删除已压缩的原始事件
            stm_store.delete_events(event_ids)

            logger.info(
                f"STM compression: {len(events)} events -> \"{summary[:80]}\""
            )
            return summary

        except Exception as e:
            logger.error(f"STM compression failed: {e}")
            return None

    def _format_events_for_compression(self, events: List[StmEvent]) -> str:
        """将事件列表格式化为 LLM 输入文本。"""
        lines = []
        for event in events:
            time_str = event.created_at[11:16] if event.created_at else "???"
            source = "私聊" if event.source_type == "qq_private" else f"群{event.group_id[-4:]}"
            lines.append(f"[{time_str}] ({source}) {event.summary}")
        return "\n".join(lines)
