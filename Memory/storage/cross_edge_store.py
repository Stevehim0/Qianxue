"""跨层边存储模块。

本模块提供跨层边（cross_edges表）的CRUD操作。
跨层边连接体验层和信息层，表示体验与实体的关联。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class CrossEdge:
    """跨层边数据类。

    Attributes:
        id: 边ID（自增）
        from_id: 源体验节点ID
        to_id: 目标实体ID
        context: 关联原因/上下文
        weight: 权重
        created_at: 创建时间
    """

    from_id: str
    to_id: str
    context: Optional[str] = None
    weight: float = 1.0
    created_at: Optional[str] = None
    id: Optional[int] = None


class CrossEdgeStore:
    """跨层边存储类。

    提供跨层边的增删改查操作。
    """

    def __init__(self, db_manager=None):
        """初始化CrossEdgeStore。
        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager

    def create(self, edge: CrossEdge) -> int:
        """创建新的跨层边（已去重）。

        如果 (from_id, to_id) 已存在，则更新权重而不是创建重复边。

        Args:
            edge: CrossEdge对象

        Returns:
            创建的边ID（自增ID），如已存在则返回已有边ID

        Raises:
            sqlite3.IntegrityError: from_id或to_id不存在时抛出异常
        """
        created_at = edge.created_at or datetime.now().isoformat()

        with self.db.transaction() as cursor:
            # 查重：检查是否已存在
            cursor.execute(
                """
                SELECT id, weight FROM cross_edges
                WHERE from_id = ? AND to_id = ?
            """,
                (edge.from_id, edge.to_id),
            )
            existing = cursor.fetchone()

            if existing:
                # 已存在，更新权重
                existing_id = existing["id"]
                new_weight = max(existing["weight"], edge.weight)
                cursor.execute(
                    """
                    UPDATE cross_edges SET weight = ? WHERE id = ?
                """,
                    (new_weight, existing_id),
                )
                logger.debug(f"Cross edge already exists, updated: {existing_id} ({edge.from_id} -> {edge.to_id})")
                return existing_id

            # 不存在，创建新边
            cursor.execute(
                """
                INSERT OR REPLACE INTO cross_edges (from_id, to_id, context, weight, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (edge.from_id, edge.to_id, edge.context, edge.weight, created_at),
            )

            edge_id = cursor.lastrowid
            logger.debug(f"Created cross edge: {edge_id} ({edge.from_id} -> {edge.to_id})")
            return edge_id

    def get(self, edge_id: int) -> Optional[CrossEdge]:
        """获取跨层边。

        Args:
            edge_id: 边ID

        Returns:
            CrossEdge对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM cross_edges WHERE id = ?", (edge_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_edge(row)
            return None

    def get_by_experience(self, exp_id: str) -> List[CrossEdge]:
        """获取从指定体验节点出发的所有跨层边。

        Args:
            exp_id: 体验节点ID

        Returns:
            CrossEdge列表（体验关联的实体）
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM cross_edges
                WHERE from_id = ?
                ORDER BY weight DESC, created_at DESC
            """,
                (exp_id,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_by_entity(self, entity_id: str) -> List[CrossEdge]:
        """获取指向指定实体的所有跨层边。

        Args:
            entity_id: 实体ID

        Returns:
            CrossEdge列表（关联该实体的体验）
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM cross_edges
                WHERE to_id = ?
                ORDER BY weight DESC, created_at DESC
            """,
                (entity_id,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def update(self, edge: CrossEdge) -> bool:
        """更新跨层边。

        Args:
            edge: CrossEdge对象（必须包含id）

        Returns:
            True如果更新成功，False如果边不存在
        """
        if edge.id is None:
            raise ValueError("Cannot update edge without id")

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE cross_edges SET
                    context = ?, weight = ?
                WHERE id = ?
            """,
                (edge.context, edge.weight, edge.id),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated cross edge: {edge.id}")
            return success

    def update_weight(self, edge_id: int, weight: float) -> bool:
        """更新跨层边的权重。

        Args:
            edge_id: 边ID
            weight: 新的权重

        Returns:
            True如果更新成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE cross_edges
                SET weight = ?
                WHERE id = ?
            """,
                (weight, edge_id),
            )

            return cursor.rowcount > 0

    def delete(self, edge_id: int) -> bool:
        """删除跨层边。

        Args:
            edge_id: 边ID

        Returns:
            True如果删除成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM cross_edges WHERE id = ?", (edge_id,))
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted cross edge: {edge_id}")
            return success

    def delete_by_experience(self, exp_id: str) -> int:
        """删除指定体验节点的所有跨层边。

        Args:
            exp_id: 体验节点ID

        Returns:
            删除的边数量
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM cross_edges WHERE from_id = ?", (exp_id,))
            count = cursor.rowcount
            if count > 0:
                logger.debug(f"Deleted {count} cross edges for experience: {exp_id}")
            return count

    def count(self) -> int:
        """统计跨层边总数。

        Returns:
            边总数
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM cross_edges")
            return cursor.fetchone()[0]

    def get_recent_edges(self, days: int = 30, from_type: str = None) -> List[CrossEdge]:
        """查询最近的跨层边。

        Args:
            days: 查询最近N天
            from_type: 来源实体类型（可选）

        Returns:
            CrossEdge列表
        """
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self.db.transaction() as cursor:
            if from_type:
                # 需要JOIN entities表获取type
                cursor.execute(
                    """
                    SELECT ce.* FROM cross_edges ce
                    INNER JOIN entities e ON ce.from_id = e.id
                    WHERE ce.created_at >= ? AND e.type = ?
                    ORDER BY ce.created_at DESC
                """,
                    (cutoff, from_type),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM cross_edges
                    WHERE created_at >= ?
                    ORDER BY created_at DESC
                """,
                    (cutoff,),
                )

            rows = cursor.fetchall()
            return [self._row_to_edge(row) for row in rows]

    def get_by_from(self, from_id: str, days: int = None) -> List[CrossEdge]:
        """获取从指定实体出发的所有跨层边。

        Args:
            from_id: 源实体ID
            days: 查询最近N天（可选）

        Returns:
            CrossEdge列表
        """
        with self.db.transaction() as cursor:
            if days:
                from datetime import datetime, timedelta

                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                cursor.execute(
                    """
                    SELECT * FROM cross_edges
                    WHERE from_id = ? AND created_at >= ?
                    ORDER BY created_at DESC
                """,
                    (from_id, cutoff),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM cross_edges
                    WHERE from_id = ?
                    ORDER BY created_at DESC
                """,
                    (from_id,),
                )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    # ========== 辅助方法 ==========

    def _row_to_edge(self, row) -> CrossEdge:
        """将数据库行转换为CrossEdge对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            CrossEdge对象
        """
        return CrossEdge(
            id=row["id"],
            from_id=row["from_id"],
            to_id=row["to_id"],
            context=row["context"],
            weight=row["weight"],
            created_at=row["created_at"],
        )


# 全局CrossEdgeStore实例
cross_edge_store = CrossEdgeStore()
