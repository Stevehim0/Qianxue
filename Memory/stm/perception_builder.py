"""感知构建器 — 将 STM 事件格式化为 LLM 可理解的文本。"""

import logging
from typing import List

from Memory.storage.stm_store import StmEvent, StmCompressed

logger = logging.getLogger(__name__)


# 事件类型的中文映射
EVENT_TYPE_LABELS = {
    "ai_reply": "你回复了",
    "tool_call": "你调用了",
    "user_mention": "",
    "significant_msg": "",
}


class PerceptionBuilder:
    """将事件列表格式化为 LLM 可理解的感知文本块。"""

    def build_perception(
        self,
        events: List[StmEvent],
        compressed: List[StmCompressed],
    ) -> str:
        """构建完整的感知文本。

        Args:
            events: 最近的事件列表（按时间倒序）
            compressed: 压缩摘要列表（按时间倒序）

        Returns:
            格式化的感知文本，如果没有事件则返回空字符串
        """
        if not events and not compressed:
            return ""

        parts = ["--- 短期记忆（跨会话感知）---"]

        # 压缩摘要（较早的）
        for c in reversed(compressed):  # 按时间正序显示
            time_start = self._extract_time(c.time_range_start)
            time_end = self._extract_time(c.time_range_end)
            parts.append(f"[摘要 {time_start}~{time_end}] {c.summary}")

        # 原始事件（按时间正序显示，更自然的阅读顺序）
        for event in reversed(events):
            time_str = self._extract_time(event.created_at)
            source_label = self._source_label(event.source_type, event.group_id)
            parts.append(f"[{time_str}] ({source_label}) {event.summary}")

        parts.append("--- 以上是近期跨会话感知 ---")

        return "\n".join(parts)

    def _extract_time(self, iso_str: str) -> str:
        """从 ISO 时间戳生成带相对时间标注的显示字符串。"""
        try:
            from Memory.utils.time_utils import format_relative_time_for_display
            return format_relative_time_for_display(iso_str)
        except Exception:
            # 回退到简单 HH:MM
            try:
                return iso_str[11:16]
            except (IndexError, TypeError):
                return "???"

    def _source_label(self, source_type: str, group_id: str) -> str:
        """生成来源标签。"""
        if source_type == "qq_private" or group_id.startswith("private_"):
            return "私聊"
        # 群聊只显示后4位（避免泄露完整群号）
        if len(group_id) > 4:
            return f"群{group_id[-4:]}"
        return f"群{group_id}"
