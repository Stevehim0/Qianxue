"""体验节点存储模块。

本模块提供体验节点（experiences表）的CRUD操作。
关键功能：
- L0_embedding字段的BLOB存储和读取
- numpy数组的正确转换（tobytes/frombuffer）
- 参数化查询防止SQL注入
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """体验节点数据类。

    Attributes:
        id: 体验节点ID（exp_YYYYMMDD_HHmmss格式）
        L0_text: L0摘要文本
        L0_embedding: L0摘要的向量（768维numpy数组）
        L1_text: L1关键要点
        L2_text: L2具体细节
        L3_raw: L3完整原文（永不修改）
        emotion_category: 情感类别
        emotion_intensity: 情感强度（0-1）
        emotion_valence: 效价（-1到1）
        emotion_arousal: 唤醒度（0-1）
        emotion_target: 情感指向的实体ID
        context_focus: 上下文：状态层focus
        context_mood: 上下文：状态层mood
        context_time_of_day: 上下文：时间推导
        context_silence_before: 上下文：距上一体验的时间差
        context_task: 上下文：外部任务
        context_extra: 上下文：扩展字段（JSON）
        importance: 重要度评分
        twist_level: 扭曲程度标记
        consolidated: 巩固标记（0=未巩固，1=已巩固）
        L0_decayed: L0层衰减权重
        L1_decayed: L1层衰减权重
        L2_decayed: L2层衰减权重
        L3_decayed: L3层衰减权重
        distorted: 梦境扭曲审计追踪（JSON字符串）
        created_at: 创建时间
    """

    id: str
    L3_raw: str
    L0_text: Optional[str] = None
    L0_embedding: Optional[np.ndarray] = None
    L1_text: Optional[str] = None
    L2_text: Optional[str] = None
    emotion_category: Optional[str] = None
    emotion_intensity: Optional[float] = None
    emotion_valence: Optional[float] = None
    emotion_arousal: Optional[float] = None
    emotion_target: Optional[str] = None
    context_focus: Optional[str] = None
    context_mood: Optional[str] = None
    context_time_of_day: Optional[str] = None
    context_silence_before: Optional[str] = None
    context_task: Optional[str] = None
    context_extra: Optional[str] = None
    importance: float = 0.5
    twist_level: str = "none"
    consolidated: int = 0
    L0_decayed: float = 1.0
    L1_decayed: float = 1.0
    L2_decayed: float = 1.0
    L3_decayed: float = 1.0
    distorted: Optional[str] = None
    source_type: str = "direct"  # direct, dream, etc.
    confidence: float = 1.0  # 置信度
    created_at: Optional[str] = None


class ExperienceStore:
    """体验节点存储类。

    提供体验节点的增删改查操作。
    正确处理embedding字段的BLOB存储。
    """

    def __init__(self, db_manager=None):
        """初始化ExperienceStore。

        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager

    def create(self, exp: Experience) -> str:
        """创建新的体验节点。

        Args:
            exp: Experience对象

        Returns:
            创建的体验节点ID

        Raises:
            sqlite3.IntegrityError: ID重复时抛出异常
        """
        created_at = exp.created_at or datetime.now().isoformat()

        # 将numpy数组转换为BLOB
        embedding_blob = self._serialize_embedding(exp.L0_embedding)

        with self.db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO experiences ("
                "id, L0_text, L0_embedding, L1_text, L2_text, L3_raw, "
                "emotion_category, emotion_intensity, emotion_valence, emotion_arousal, emotion_target, "
                "context_focus, context_mood, context_time_of_day, context_silence_before, "
                "context_task, context_extra, importance, twist_level, consolidated, "
                "L0_decayed, L1_decayed, L2_decayed, L3_decayed, distorted, "
                "source_type, confidence, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    exp.id,
                    exp.L0_text,
                    embedding_blob,
                    exp.L1_text,
                    exp.L2_text,
                    exp.L3_raw,
                    exp.emotion_category,
                    exp.emotion_intensity,
                    exp.emotion_valence,
                    exp.emotion_arousal,
                    exp.emotion_target,
                    exp.context_focus,
                    exp.context_mood,
                    exp.context_time_of_day,
                    exp.context_silence_before,
                    exp.context_task,
                    exp.context_extra,
                    exp.importance,
                    exp.twist_level,
                    exp.consolidated,
                    exp.L0_decayed,
                    exp.L1_decayed,
                    exp.L2_decayed,
                    exp.L3_decayed,
                    exp.distorted,
                    exp.source_type,
                    exp.confidence,
                    created_at,
                ),
            )

        logger.debug(f"Created experience: {exp.id}")
        return exp.id

    def get(self, exp_id: str) -> Optional[Experience]:
        """获取体验节点。

        Args:
            exp_id: 体验节点ID

        Returns:
            Experience对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_experience(row)
            return None

    def get_since(self, since_iso: str) -> List[Experience]:
        """获取指定时间之后创建的体验节点。

        Args:
            since_iso: ISO格式时间戳字符串

        Returns:
            符合条件的Experience列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                "SELECT * FROM experiences WHERE created_at >= ? ORDER BY created_at ASC",
                (since_iso,),
            )
            return [self._row_to_experience(row) for row in cursor.fetchall()]

    def get_all(self, limit: Optional[int] = None) -> List[Experience]:
        """获取所有体验节点。

        Args:
            limit: 限制返回数量，None表示全部

        Returns:
            Experience列表
        """
        with self.db.transaction() as cursor:
            if limit:
                cursor.execute(
                    "SELECT * FROM experiences ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            else:
                cursor.execute("SELECT * FROM experiences ORDER BY created_at DESC")

            return [self._row_to_experience(row) for row in cursor.fetchall()]

    def get_entity_stats(self, entity_name: str) -> Dict[str, int]:
        """获取指定实体在 experiences 中的出现统计。

        通过 cross_edges 关联和文本搜索统计实体出现次数和跨天数。
        用于 ProfileManager 判断是否触发档案自动创建（>=3次且>=3天）。

        Args:
            entity_name: 实体名称

        Returns:
            {"count": 总出现次数, "unique_days": 跨天数}
        """
        try:
            with self.db.transaction() as cursor:
                # 通过 L3_raw / L0_text 文本搜索统计出现次数和跨天数
                cursor.execute(
                    """
                    SELECT COUNT(*) as count, COUNT(DISTINCT DATE(created_at)) as unique_days
                    FROM experiences
                    WHERE L3_raw LIKE ? OR L0_text LIKE ?
                    """,
                    (f"%{entity_name}%", f"%{entity_name}%"),
                )
                row = cursor.fetchone()
                return {
                    "count": row["count"] if row else 0,
                    "unique_days": row["unique_days"] if row else 0,
                }
        except Exception as e:
            logger.error(f"Failed to get entity stats for {entity_name}: {e}")
            return {"count": 0, "unique_days": 0}

    def update(self, exp: Experience) -> bool:
        """更新体验节点。

        注意：L3_raw字段永远不能修改（铁律）

        Args:
            exp: Experience对象

        Returns:
            True如果更新成功，False如果节点不存在

        Raises:
            ValueError: 如果尝试修改L3_raw字段（除非allow_l3_modification=True）
        """
        # CRITICAL: L3 immutability enforcement (D-15, D-07, D-08)
        # Check if caller is trying to modify L3_raw field
        original_exp = self.get(exp.id)
        if original_exp and original_exp.L3_raw != exp.L3_raw:
            # L3_raw modification attempted
            from Memory.config.settings import settings
            if not settings.dream.allow_l3_modification:
                logger.error(
                    f"Attempted to modify L3_raw field for experience {exp.id}. "
                    f"L3 is immutable per design principle (D-15). "
                    f"Original: '{original_exp.L3_raw[:50]}...', "
                    f"Attempted: '{exp.L3_raw[:50]}...'. "
                    f"Set allow_l3_modification=True to override (testing only)."
                )
                raise ValueError(
                    "Cannot modify L3_raw: L3 (original text) is immutable. "
                    "This is a core design principle to preserve memory authenticity. "
                    "See Phase 08 CONTEXT.md D-15, Phase 12 CONTEXT.md D-07/D-08."
                )
            else:
                logger.warning(
                    f"L3_raw modification allowed for experience {exp.id} "
                    f"(allow_l3_modification=True - testing mode)"
                )

        embedding_blob = self._serialize_embedding(exp.L0_embedding)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experiences SET
                    L0_text = ?, L0_embedding = ?, L1_text = ?, L2_text = ?,
                    emotion_category = ?, emotion_intensity = ?, emotion_valence = ?,
                    emotion_arousal = ?, emotion_target = ?,
                    context_focus = ?, context_mood = ?, context_time_of_day = ?,
                    context_silence_before = ?, context_task = ?, context_extra = ?,
                    importance = ?, twist_level = ?, consolidated = ?,
                    L0_decayed = ?, L1_decayed = ?, L2_decayed = ?, L3_decayed = ?
                WHERE id = ?
            """,
                (
                    exp.L0_text,
                    embedding_blob,
                    exp.L1_text,
                    exp.L2_text,
                    exp.emotion_category,
                    exp.emotion_intensity,
                    exp.emotion_valence,
                    exp.emotion_arousal,
                    exp.emotion_target,
                    exp.context_focus,
                    exp.context_mood,
                    exp.context_time_of_day,
                    exp.context_silence_before,
                    exp.context_task,
                    exp.context_extra,
                    exp.importance,
                    exp.twist_level,
                    exp.consolidated,
                    exp.L0_decayed,
                    exp.L1_decayed,
                    exp.L2_decayed,
                    exp.L3_decayed,
                    exp.id,
                ),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated experience: {exp.id}")
            return success

    def delete(self, exp_id: str) -> bool:
        """删除体验节点。

        警告：此操作会同时删除关联的边（外键CASCADE）

        Args:
            exp_id: 体验节点ID

        Returns:
            True如果删除成功，False如果节点不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted experience: {exp_id}")
            return success

    def get_by_time_range(self, start_time: str, end_time: str) -> List[Experience]:
        """获取指定时间范围内的体验节点。

        Args:
            start_time: 开始时间（ISO格式）
            end_time: 结束时间（ISO格式）

        Returns:
            Experience列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM experiences
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at DESC
            """,
                (start_time, end_time),
            )

            return [self._row_to_experience(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """统计体验节点总数。

        Returns:
            节点总数
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM experiences")
            return cursor.fetchone()[0]

    def get_consolidation_candidates(
        self, batch_size: int, mode: str = "incremental", days: int = 7
    ) -> List[Experience]:
        """获取待巩固的体验节点。

        Args:
            batch_size: 最多返回节点数
            mode: 'incremental'（增量）或 'full'（全量最近N天）
            days: 全量模式下查询最近N天（默认7天）

        Returns:
            按created_at排序的体验节点列表
        """
        with self.db.transaction() as cursor:
            if mode == "incremental":
                # 增量模式：查询consolidated=0的节点
                cursor.execute(
                    """
                    SELECT * FROM experiences
                    WHERE consolidated = 0
                    ORDER BY created_at ASC
                    LIMIT ?
                """,
                    (batch_size,),
                )
            else:
                # 全量模式：查询最近N天的所有节点
                from datetime import datetime, timedelta

                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                cursor.execute(
                    """
                    SELECT * FROM experiences
                    WHERE created_at >= ?
                    ORDER BY created_at ASC
                    LIMIT ?
                """,
                    (cutoff, batch_size),
                )

            return [self._row_to_experience(row) for row in cursor.fetchall()]

    def update_consolidated_batch(self, experience_ids: List[str], consolidated: bool) -> int:
        """批量更新体验节点的巩固标记。

        Args:
            experience_ids: 体验节点ID列表
            consolidated: 巩固标记

        Returns:
            更新的节点数量
        """
        consolidated_value = 1 if consolidated else 0

        with self.db.transaction() as cursor:
            placeholders = ",".join("?" * len(experience_ids))
            cursor.execute(
                f"""
                UPDATE experiences
                SET consolidated = ?
                WHERE id IN ({placeholders})
            """,
                [consolidated_value] + experience_ids,
            )

            updated_count = cursor.rowcount
            logger.debug(f"Updated consolidated={consolidated} for {updated_count} experiences")
            return updated_count

    def update_l1l2(
        self, experience_id: str, l1_text: Optional[str] = None, l2_text: Optional[str] = None
    ) -> bool:
        """更新体验节点的L1/L2摘要。

        Args:
            experience_id: 体验节点ID
            l1_text: L1关键要点（可选）
            l2_text: L2具体细节（可选）

        Returns:
            True如果更新成功，False如果节点不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experiences
                SET L1_text = ?, L2_text = ?
                WHERE id = ?
            """,
                (l1_text, l2_text, experience_id),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated L1/L2 for experience: {experience_id}")
            return success

    def update_importance(self, experience_id: str, importance: float) -> bool:
        """更新体验节点的重要度评分。

        Args:
            experience_id: 体验节点ID
            importance: 重要度评分（0-1）

        Returns:
            True如果更新成功，False如果节点不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experiences
                SET importance = ?
                WHERE id = ?
            """,
                (importance, experience_id),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated importance for experience: {experience_id}")
            return success

    def update_decayed_fields(self, exp: Experience) -> bool:
        """更新体验节点的衰减字段。

        Args:
            exp: Experience对象（必须包含id和衰减字段）

        Returns:
            True如果更新成功，False如果节点不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experiences
                SET L0_decayed = ?, L1_decayed = ?, L2_decayed = ?, L3_decayed = ?
                WHERE id = ?
            """,
                (exp.L0_decayed, exp.L1_decayed, exp.L2_decayed, exp.L3_decayed, exp.id),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated decayed fields for experience: {exp.id}")
            return success

    def get_top_by_importance(self, limit: int) -> List[Experience]:
        """按重要性分数获取前N个体验节点。

        使用SQL ORDER BY importance DESC提高效率。

        Args:
            limit: 最多返回的体验节点数

        Returns:
            按重要性降序排序的体验节点列表
        """
        with self.db.transaction() as cursor:
            query = """
                SELECT * FROM experiences
                ORDER BY importance DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            return [self._row_to_experience(row) for row in rows]

    def get_random_excluding(self, limit: int, exclude_ids: List[str]) -> List[Experience]:
        """获取N个随机体验节点，排除指定ID。

        使用SQL ORDER BY RANDOM()实现真正的随机性。
        使用WHERE id NOT IN (...)高效排除指定ID。

        Args:
            limit: 最多返回的体验节点数
            exclude_ids: 要排除的体验节点ID列表

        Returns:
            随机体验节点列表
        """
        with self.db.transaction() as cursor:
            if not exclude_ids:
                # No exclusions, simple random query
                query = "SELECT * FROM experiences ORDER BY RANDOM() LIMIT ?"
                cursor.execute(query, (limit,))
            else:
                # Exclude specific IDs
                placeholders = ",".join(["?" for _ in exclude_ids])
                query = f"""
                    SELECT * FROM experiences
                    WHERE id NOT IN ({placeholders})
                    ORDER BY RANDOM()
                    LIMIT ?
                """
                cursor.execute(query, exclude_ids + [limit])

            rows = cursor.fetchall()
            return [self._row_to_experience(row) for row in rows]

    def update_distorted(
        self,
        experience_id: str,
        L0_text: Optional[str] = None,
        L1_text: Optional[str] = None,
        L2_text: Optional[str] = None,
        distorted: Optional[str] = None,
    ) -> bool:
        """更新体验节点的L0/L1/L2字段和distorted审计追踪。

        CRITICAL: L3_raw字段不能修改 - 如果尝试修改会抛出ValueError
        这强制执行D-15: L0可改，L1可微调，L2可模糊细节，L3绝对不改

        Args:
            experience_id: 体验节点ID
            L0_text: 新的L0摘要（可选）
            L1_text: 新的L1关键要点（可选）
            L2_text: 新的L2具体细节（可选）
            distorted: JSON字符串记录扭曲历史（可选）

        Returns:
            True如果更新成功，False如果节点不存在

        Raises:
            ValueError: 如果尝试修改L3_raw字段
        """
        # Build UPDATE dynamically based on provided fields
        update_fields = []
        values = []

        if L0_text is not None:
            update_fields.append("L0_text = ?")
            values.append(L0_text)

        if L1_text is not None:
            update_fields.append("L1_text = ?")
            values.append(L1_text)

        if L2_text is not None:
            update_fields.append("L2_text = ?")
            values.append(L2_text)

        if distorted is not None:
            update_fields.append("distorted = ?")
            values.append(distorted)

        if not update_fields:
            logger.warning(f"No fields to update for experience: {experience_id}")
            return False

        # Add experience_id to values
        values.append(experience_id)

        # Execute UPDATE
        with self.db.transaction() as cursor:
            sql = f"UPDATE experiences SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(sql, values)

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated distorted fields for experience: {experience_id}")
            return success

    # ========== 辅助方法 ==========

    def _serialize_embedding(self, embedding: Optional[np.ndarray]) -> Optional[bytes]:
        """将numpy数组序列化为BLOB。

        Args:
            embedding: numpy数组（768维，float32）

        Returns:
            BLOB数据，None如果输入为None
        """
        if embedding is None:
            return None

        # 确保是float32类型
        if embedding.dtype != np.float32:
            embedding = embedding.astype(np.float32)

        return embedding.tobytes()

    def _deserialize_embedding(self, blob: Optional[bytes]) -> Optional[np.ndarray]:
        """将BLOB反序列化为numpy数组。

        Args:
            blob: BLOB数据

        Returns:
            numpy数组（768维，float32），None如果输入为None
        """
        if blob is None:
            return None

        return np.frombuffer(blob, dtype=np.float32)

    def _row_to_experience(self, row) -> Experience:
        """将数据库行转换为Experience对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            Experience对象
        """
        return Experience(
            id=row["id"],
            L0_text=row["L0_text"],
            L0_embedding=self._deserialize_embedding(row["L0_embedding"]),
            L1_text=row["L1_text"],
            L2_text=row["L2_text"],
            L3_raw=row["L3_raw"],
            emotion_category=row["emotion_category"],
            emotion_intensity=row["emotion_intensity"],
            emotion_valence=row["emotion_valence"],
            emotion_arousal=row["emotion_arousal"],
            emotion_target=row["emotion_target"],
            context_focus=row["context_focus"],
            context_mood=row["context_mood"],
            context_time_of_day=row["context_time_of_day"],
            context_silence_before=row["context_silence_before"],
            context_task=row["context_task"],
            context_extra=row["context_extra"],
            importance=row["importance"],
            twist_level=row["twist_level"],
            consolidated=row["consolidated"] if "consolidated" in row.keys() else 0,
            L0_decayed=row["L0_decayed"] if "L0_decayed" in row.keys() else 1.0,
            L1_decayed=row["L1_decayed"] if "L1_decayed" in row.keys() else 1.0,
            L2_decayed=row["L2_decayed"] if "L2_decayed" in row.keys() else 1.0,
            L3_decayed=row["L3_decayed"] if "L3_decayed" in row.keys() else 1.0,
            distorted=row["distorted"] if "distorted" in row.keys() else None,
            source_type=row["source_type"] if "source_type" in row.keys() else "direct",
            confidence=row["confidence"] if "confidence" in row.keys() else 1.0,
            created_at=row["created_at"],
        )


# 全局ExperienceStore实例（使用默认db_manager）
experience_store = ExperienceStore()
