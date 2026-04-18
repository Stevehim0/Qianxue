"""信息层关系边存储模块。

本模块提供信息层关系边（entity_edges表）的CRUD操作。
关系边连接两个实体，表示它们之间的关系。
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

import numpy as np

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class EntityEdge:
    """信息层关系边数据类。

    Attributes:
        id: 边ID（自增）
        from_id: 源实体ID
        to_id: 目标实体ID
        relation: 关系描述（自由文本）
        embedding: relation文本的语义向量（768维numpy数组）
        confidence: 置信度（0-1）
        source: 来源体验节点ID
        source_type: 来源类型（direct/external/inferred/hearsay/unverified）
        verified_at: 验证时间
        verify_count: 验证次数
        created_at: 创建时间
    """

    from_id: str
    to_id: str
    relation: str
    confidence: float = 0.5
    source: Optional[str] = None
    source_type: str = "direct"
    embedding: Optional[np.ndarray] = None
    verified_at: Optional[str] = None
    verify_count: int = 0
    created_at: Optional[str] = None
    id: Optional[int] = None


class EntityEdgeStore:
    """信息层关系边存储类。

    提供信息层关系边的增删改查操作。
    正确处理embedding字段的BLOB存储。
    """

    def __init__(self, db_manager=None):
        """初始化EntityEdgeStore。
        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager

    def create(self, edge: EntityEdge) -> int:
        """创建新的关系边（已去重）。

        如果 (from_id, to_id, relation) 或 (to_id, from_id, relation) 已存在，
        则更新已有边的置信度而不是创建重复边。

        Args:
            edge: EntityEdge对象

        Returns:
            创建的边ID（自增ID），如已存在则返回已有边ID

        Raises:
            sqlite3.IntegrityError: from_id或to_id不存在时抛出异常
        """
        created_at = edge.created_at or datetime.now().isoformat()

        # 序列化embedding
        embedding_blob = self._serialize_embedding(edge.embedding)

        with self.db.transaction() as cursor:
            # 查重：检查正向和反向边是否已存在
            cursor.execute(
                """
                SELECT id, confidence FROM entity_edges
                WHERE from_id = ? AND to_id = ? AND relation = ?
            """,
                (edge.from_id, edge.to_id, edge.relation),
            )
            existing = cursor.fetchone()

            if not existing:
                # 也检查反向边
                cursor.execute(
                    """
                    SELECT id, confidence FROM entity_edges
                    WHERE from_id = ? AND to_id = ? AND relation = ?
                """,
                    (edge.to_id, edge.from_id, edge.relation),
                )
                existing = cursor.fetchone()

            if existing:
                # 已存在，取更高置信度
                existing_id = existing["id"]
                new_confidence = max(existing["confidence"], edge.confidence)
                cursor.execute(
                    """
                    UPDATE entity_edges SET confidence = ? WHERE id = ?
                """,
                    (new_confidence, existing_id),
                )
                logger.debug(f"Entity edge already exists, updated confidence: {existing_id}")
                return existing_id

            # 不存在，创建新边（OR REPLACE 防并发竞态）
            cursor.execute(
                """
                INSERT OR REPLACE INTO entity_edges (
                    from_id, to_id, relation, embedding, confidence,
                    source, source_type, verified_at, verify_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    edge.from_id,
                    edge.to_id,
                    edge.relation,
                    embedding_blob,
                    edge.confidence,
                    edge.source,
                    edge.source_type,
                    edge.verified_at,
                    edge.verify_count,
                    created_at,
                ),
            )

            edge_id = cursor.lastrowid
            logger.debug(f"Created entity edge: {edge_id} ({edge.from_id} -> {edge.to_id})")
            return edge_id

    def get(self, edge_id: int) -> Optional[EntityEdge]:
        """获取关系边。

        Args:
            edge_id: 边ID

        Returns:
            EntityEdge对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM entity_edges WHERE id = ?", (edge_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_edge(row)
            return None

    def get_by_from(self, from_id: str) -> List[EntityEdge]:
        """获取从指定实体出发的所有关系边。

        Args:
            from_id: 源实体ID

        Returns:
            EntityEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM entity_edges
                WHERE from_id = ?
                ORDER BY confidence DESC, created_at DESC
            """,
                (from_id,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_by_to(self, to_id: str) -> List[EntityEdge]:
        """获取指向指定实体的所有关系边。

        Args:
            to_id: 目标实体ID

        Returns:
            EntityEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM entity_edges
                WHERE to_id = ?
                ORDER BY confidence DESC, created_at DESC
            """,
                (to_id,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_by_source_type(self, source_type: str) -> List[EntityEdge]:
        """获取指定来源类型的所有关系边。

        Args:
            source_type: 来源类型（direct/external/inferred等）

        Returns:
            EntityEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM entity_edges
                WHERE source_type = ?
                ORDER BY created_at DESC
            """,
                (source_type,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_low_confidence(
        self, threshold: float = 0.5, verify_count: int = 0, limit: int = 20
    ) -> List[EntityEdge]:
        """查询低置信度且未验证的边。

        用于信息验证任务，找出需要重新评估的边。

        Args:
            threshold: 置信度阈值（默认0.5），查询confidence < threshold
            verify_count: 验证次数（默认0），查询verify_count <= verify_count
            limit: 最多返回边数（默认20）

        Returns:
            按confidence升序排序的EntityEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM entity_edges
                WHERE confidence < ? AND verify_count <= ?
                ORDER BY confidence ASC, created_at DESC
                LIMIT ?
            """,
                (threshold, verify_count, limit),
            )

            rows = cursor.fetchall()
            return [self._row_to_edge(row) for row in rows]

    def update(self, edge: EntityEdge) -> bool:
        """更新关系边。

        Args:
            edge: EntityEdge对象（必须包含id）

        Returns:
            True如果更新成功，False如果边不存在
        """
        if edge.id is None:
            raise ValueError("Cannot update edge without id")

        embedding_blob = self._serialize_embedding(edge.embedding)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE entity_edges SET
                    relation = ?, embedding = ?, confidence = ?,
                    source_type = ?, verified_at = ?, verify_count = ?
                WHERE id = ?
            """,
                (
                    edge.relation,
                    embedding_blob,
                    edge.confidence,
                    edge.source_type,
                    edge.verified_at,
                    edge.verify_count,
                    edge.id,
                ),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated entity edge: {edge.id}")
            return success

    def update_confidence(self, edge_id: int, confidence: float) -> bool:
        """更新关系边的置信度。

        Args:
            edge_id: 边ID
            confidence: 新的置信度（0-1）

        Returns:
            True如果更新成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE entity_edges
                SET confidence = ?
                WHERE id = ?
            """,
                (confidence, edge_id),
            )

            return cursor.rowcount > 0

    def increment_verify_count(self, edge_id: int) -> bool:
        """增加关系边的验证次数。

        Args:
            edge_id: 边ID

        Returns:
            True如果更新成功，False如果边不存在
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE entity_edges
                SET verify_count = verify_count + 1, verified_at = ?
                WHERE id = ?
            """,
                (now, edge_id),
            )

            return cursor.rowcount > 0

    def delete(self, edge_id: int) -> bool:
        """删除关系边。

        Args:
            edge_id: 边ID

        Returns:
            True如果删除成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM entity_edges WHERE id = ?", (edge_id,))
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted entity edge: {edge_id}")
            return success

    def get_all(self) -> List[EntityEdge]:
        """获取所有关系边。

        Returns:
            所有EntityEdge对象列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM entity_edges
                ORDER BY created_at DESC
                """
            )
            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """统计关系边总数。

        Returns:
            边总数
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM entity_edges")
            return cursor.fetchone()[0]

    # ========== 辅助方法 ==========

    def _serialize_embedding(self, embedding: Optional[np.ndarray]) -> Optional[bytes]:
        """将numpy数组序列化为BLOB。"""
        if embedding is None:
            return None
        if embedding.dtype != np.float32:
            embedding = embedding.astype(np.float32)
        return embedding.tobytes()

    def _deserialize_embedding(self, blob: Optional[bytes]) -> Optional[np.ndarray]:
        """将BLOB反序列化为numpy数组。"""
        if blob is None:
            return None
        return np.frombuffer(blob, dtype=np.float32)

    def _row_to_edge(self, row) -> EntityEdge:
        """将数据库行转换为EntityEdge对象。"""
        return EntityEdge(
            id=row["id"],
            from_id=row["from_id"],
            to_id=row["to_id"],
            relation=row["relation"],
            embedding=self._deserialize_embedding(row["embedding"]),
            confidence=row["confidence"],
            source=row["source"],
            source_type=row["source_type"],
            verified_at=row["verified_at"],
            verify_count=row["verify_count"],
            created_at=row["created_at"],
        )


# 全局EntityEdgeStore实例
entity_edge_store = EntityEdgeStore()
