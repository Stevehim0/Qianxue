"""短期记忆（STM）存储模块。

本模块提供跨会话全局感知的事件存储。
记录 AI 近期在所有会话中的行为和关键用户消息，
支持事件压缩和自动过期清理。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from Memory.storage.database import db_manager as global_db_manager
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class StmEvent:
    """短期记忆事件。

    Attributes:
        id: 事件ID
        event_type: 事件类型（ai_reply | tool_call | user_mention | significant_msg）
        source_type: 来源类型（qq_group | qq_private）
        group_id: 会话ID
        user_id: 用户ID（可选）
        summary: 一行人类可读摘要
        detail: 可选的详细信息
        importance: 重要度 0.0-1.0
        created_at: 创建时间（ISO格式）
    """

    id: Optional[int] = None
    event_type: str = ""
    source_type: str = ""
    group_id: str = ""
    user_id: Optional[str] = None
    summary: str = ""
    detail: Optional[str] = None
    importance: float = 0.5
    created_at: str = ""


@dataclass
class StmCompressed:
    """压缩后的事件摘要。

    Attributes:
        id: 摘要ID
        summary: LLM 生成的压缩摘要
        event_count: 被压缩的原始事件数量
        time_range_start: 原始事件的最早时间
        time_range_end: 原始事件的最晚时间
        created_at: 压缩时间
    """

    id: Optional[int] = None
    summary: str = ""
    event_count: int = 0
    time_range_start: str = ""
    time_range_end: str = ""
    created_at: str = ""


class StmStore:
    """短期记忆存储类。

    提供事件的 CRUD、压缩摘要管理和自动清理。
    """

    def __init__(self, db_manager=None):
        self.db = db_manager if db_manager is not None else global_db_manager

    def record_event(
        self,
        event_type: str,
        source_type: str,
        group_id: str,
        user_id: Optional[str] = None,
        summary: str = "",
        detail: Optional[str] = None,
        importance: float = 0.5,
    ) -> int:
        """记录一个新事件。

        Returns:
            新事件的ID
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO stm_events
                    (event_type, source_type, group_id, user_id,
                     summary, detail, importance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (event_type, source_type, group_id, user_id,
                 summary, detail, importance, now),
            )
            event_id = cursor.lastrowid

        logger.debug(f"STM event recorded: [{event_type}] {summary[:50]}")
        return event_id

    def get_recent_events(
        self, hours: Optional[float] = None, limit: Optional[int] = None
    ) -> List[StmEvent]:
        """获取最近的事件。

        Args:
            hours: 回溯小时数，默认使用配置的 retention_hours
            limit: 最大返回数量，默认使用配置的 max_perception_events
        """
        if hours is None:
            hours = settings.stm.retention_hours
        if limit is None:
            limit = settings.stm.max_perception_events

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM stm_events
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (cutoff, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]

    def get_compressed_summaries(self, hours: Optional[float] = None) -> List[StmCompressed]:
        """获取压缩后的摘要。"""
        if hours is None:
            hours = settings.stm.retention_hours

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM stm_compressed
                WHERE created_at >= ?
                ORDER BY time_range_start DESC
            """,
                (cutoff,),
            )
            rows = cursor.fetchall()
            return [self._row_to_compressed(row) for row in rows]

    def get_events_for_compression(self) -> List[StmEvent]:
        """获取可以被压缩的事件（30分钟前的，按时间排序）。"""
        cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM stm_events
                WHERE created_at < ?
                ORDER BY created_at ASC
                LIMIT ?
            """,
                (cutoff, settings.stm.compression_batch_size),
            )
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]

    def delete_events(self, event_ids: List[int]) -> None:
        """删除指定事件（压缩后清理原始事件）。"""
        if not event_ids:
            return

        with self.db.transaction() as cursor:
            placeholders = ",".join("?" * len(event_ids))
            cursor.execute(
                f"DELETE FROM stm_events WHERE id IN ({placeholders})",
                event_ids,
            )

        logger.debug(f"Deleted {len(event_ids)} compressed STM events")

    def store_compressed(
        self,
        summary: str,
        event_count: int,
        time_range_start: str,
        time_range_end: str,
    ) -> int:
        """存储一个压缩摘要。"""
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO stm_compressed
                    (summary, event_count, time_range_start, time_range_end, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (summary, event_count, time_range_start, time_range_end, now),
            )
            return cursor.lastrowid

    def cleanup_expired(self, max_age_hours: Optional[float] = None) -> int:
        """清理过期的事件和压缩摘要。

        Returns:
            删除的总行数
        """
        if max_age_hours is None:
            max_age_hours = settings.stm.retention_hours

        cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        total = 0

        with self.db.transaction() as cursor:
            cursor.execute(
                "DELETE FROM stm_events WHERE created_at < ?",
                (cutoff,),
            )
            total += cursor.rowcount

            cursor.execute(
                "DELETE FROM stm_compressed WHERE created_at < ?",
                (cutoff,),
            )
            total += cursor.rowcount

        if total > 0:
            logger.info(f"STM cleanup: removed {total} expired records")
        return total

    def get_active_count(self) -> int:
        """获取当前活跃事件数量（用于判断是否需要压缩）。"""
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM stm_events")
            return cursor.fetchone()[0]

    def _row_to_event(self, row) -> StmEvent:
        return StmEvent(
            id=row["id"],
            event_type=row["event_type"],
            source_type=row["source_type"],
            group_id=row["group_id"],
            user_id=row["user_id"],
            summary=row["summary"],
            detail=row["detail"],
            importance=row["importance"],
            created_at=row["created_at"],
        )

    def _row_to_compressed(self, row) -> StmCompressed:
        return StmCompressed(
            id=row["id"],
            summary=row["summary"],
            event_count=row["event_count"],
            time_range_start=row["time_range_start"],
            time_range_end=row["time_range_end"],
            created_at=row["created_at"],
        )


# 全局 StmStore 实例
stm_store = StmStore()
