"""体验层边存储模块。

本模块提供体验层边（experience_edges表）的CRUD操作。
体验层边连接两个体验节点，表示时序/主题/因果/联想关系。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class ExperienceEdge:
    """体验层边数据类。

    Attributes:
        id: 边ID（自增）
        from_id: 源体验节点ID
        to_id: 目标体验节点ID
        type: 边类型（temporal/thematic/causal/associative）
        weight: 原始权重
        decayed_weight: 衰减后权重
        emotion_driver: 情感驱动（可选）
        access_count: 被召回次数
        dormant: 休眠标记（0=活跃，1=休眠）
        created_at: 创建时间
    """

    from_id: str
    to_id: str
    type: str
    weight: float = 1.0
    decayed_weight: float = 1.0
    emotion_driver: Optional[str] = None
    access_count: int = 0
    dormant: int = 0
    created_at: Optional[str] = None
    id: Optional[int] = None  # 创建后由数据库填充


class ExperienceEdgeStore:
    """体验层边存储类。

    提供体验层边的增删改查操作。
    """

    def __init__(self, db_manager=None):
        """初始化ExperienceEdgeStore。

        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager

    def create(self, edge: ExperienceEdge) -> int:
        """创建新的体验层边（已去重）。

        如果 (from_id, to_id) 或 (to_id, from_id) 已存在，
        则更新已有边的权重而不是创建重复边。

        Args:
            edge: ExperienceEdge对象

        Returns:
            创建的边ID（自增ID），如已存在则返回已有边ID

        Raises:
            sqlite3.IntegrityError: from_id或to_id不存在时抛出异常
        """
        created_at = edge.created_at or datetime.now().isoformat()

        with self.db.transaction() as cursor:
            # 查重：检查正向边
            cursor.execute(
                """
                SELECT id, weight FROM experience_edges
                WHERE from_id = ? AND to_id = ?
            """,
                (edge.from_id, edge.to_id),
            )
            existing = cursor.fetchone()

            if not existing:
                # 也检查反向边
                cursor.execute(
                    """
                    SELECT id, weight FROM experience_edges
                    WHERE from_id = ? AND to_id = ?
                """,
                    (edge.to_id, edge.from_id),
                )
                existing = cursor.fetchone()

            if existing:
                # 已存在，更新权重
                existing_id = existing["id"]
                new_weight = max(existing["weight"], edge.weight)
                cursor.execute(
                    """
                    UPDATE experience_edges SET weight = ?, decayed_weight = ?
                    WHERE id = ?
                """,
                    (new_weight, edge.decayed_weight, existing_id),
                )
                logger.debug(f"Edge already exists, updated: {existing_id} ({edge.from_id} -> {edge.to_id})")
                return existing_id

            # 不存在，创建新边（OR REPLACE 防并发竞态）
            cursor.execute(
                """
                INSERT OR REPLACE INTO experience_edges (
                    from_id, to_id, type, weight, decayed_weight,
                    emotion_driver, access_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    edge.from_id,
                    edge.to_id,
                    edge.type,
                    edge.weight,
                    edge.decayed_weight,
                    edge.emotion_driver,
                    edge.access_count,
                    created_at,
                ),
            )

            edge_id = cursor.lastrowid
            logger.debug(f"Created experience edge: {edge_id} ({edge.from_id} -> {edge.to_id})")
            return edge_id

    def get(self, edge_id: int) -> Optional[ExperienceEdge]:
        """获取体验层边。

        Args:
            edge_id: 边ID

        Returns:
            ExperienceEdge对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM experience_edges WHERE id = ?", (edge_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_edge(row)
            return None

    def get_by_from(self, from_id: str) -> List[ExperienceEdge]:
        """获取从指定体验节点出发的所有边。

        Args:
            from_id: 源体验节点ID

        Returns:
            ExperienceEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM experience_edges
                WHERE from_id = ?
                ORDER BY created_at DESC
            """,
                (from_id,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_by_to(self, to_id: str) -> List[ExperienceEdge]:
        """获取指向指定体验节点的所有边。

        Args:
            to_id: 目标体验节点ID

        Returns:
            ExperienceEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM experience_edges
                WHERE to_id = ?
                ORDER BY created_at DESC
            """,
                (to_id,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_by_type(self, edge_type: str) -> List[ExperienceEdge]:
        """获取指定类型的所有边。

        Args:
            edge_type: 边类型（temporal/thematic/causal/associative）

        Returns:
            ExperienceEdge列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM experience_edges
                WHERE type = ?
                ORDER BY created_at DESC
            """,
                (edge_type,),
            )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def get_all(self, limit: Optional[int] = None) -> List[ExperienceEdge]:
        """获取所有边。

        Args:
            limit: 限制返回数量，None表示全部

        Returns:
            ExperienceEdge列表
        """
        with self.db.transaction() as cursor:
            if limit:
                cursor.execute(
                    """
                    SELECT * FROM experience_edges
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM experience_edges
                    ORDER BY created_at DESC
                """
                )

            return [self._row_to_edge(row) for row in cursor.fetchall()]

    def update(self, edge: ExperienceEdge) -> bool:
        """更新体验层边。

        Args:
            edge: ExperienceEdge对象（必须包含id）

        Returns:
            True如果更新成功，False如果边不存在
        """
        if edge.id is None:
            raise ValueError("Cannot update edge without id")

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experience_edges SET
                    type = ?, weight = ?, decayed_weight = ?,
                    emotion_driver = ?, access_count = ?, dormant = ?
                WHERE id = ?
            """,
                (
                    edge.type,
                    edge.weight,
                    edge.decayed_weight,
                    edge.emotion_driver,
                    edge.access_count,
                    edge.dormant,
                    edge.id,
                ),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated experience edge: {edge.id}")
            return success

    def increment_access_count(self, edge_id: int) -> bool:
        """增加边的召回次数。

        Args:
            edge_id: 边ID

        Returns:
            True如果更新成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experience_edges
                SET access_count = access_count + 1
                WHERE id = ?
            """,
                (edge_id,),
            )

            return cursor.rowcount > 0

    def delete(self, edge_id: int) -> bool:
        """删除体验层边。

        Args:
            edge_id: 边ID

        Returns:
            True如果删除成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM experience_edges WHERE id = ?", (edge_id,))
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted experience edge: {edge_id}")
            return success

    def count(self) -> int:
        """统计体验层边总数。

        Returns:
            边总数
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM experience_edges")
            return cursor.fetchone()[0]

    def upsert_batch(self, edges: List[ExperienceEdge]) -> dict:
        """批量创建或更新边（UPSERT语义）。

        如果边已存在（from_id + to_id + type相同），
        则更新weight/decayed_weight/emotion_driver；
        否则创建新边。

        使用SQLite的INSERT OR REPLACE语法。

        Args:
            edges: 边列表

        Returns:
            操作统计 {
                'created': 新建数量,
                'updated': 更新数量
            }
        """
        created_count = 0
        updated_count = 0

        with self.db.transaction() as cursor:
            for edge in edges:
                created_at = edge.created_at or datetime.now().isoformat()

                # 先检查是否存在（按 from_id + to_id 查，不管 type）
                cursor.execute(
                    """
                    SELECT id, weight FROM experience_edges
                    WHERE from_id = ? AND to_id = ?
                """,
                    (edge.from_id, edge.to_id),
                )

                row = cursor.fetchone()

                if row:
                    # 已存在，更新
                    existing_id = row["id"]
                    cursor.execute(
                        """
                        UPDATE experience_edges SET
                            weight = ?,
                            decayed_weight = ?,
                            emotion_driver = ?,
                            access_count = access_count + 1
                        WHERE id = ?
                    """,
                        (edge.weight, edge.decayed_weight, edge.emotion_driver, existing_id),
                    )
                    updated_count += 1
                    logger.debug(f"Updated edge: {existing_id} ({edge.from_id} -> {edge.to_id})")
                else:
                    # 不存在，创建（OR REPLACE 防并发竞态）
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO experience_edges (
                            from_id, to_id, type, weight, decayed_weight,
                            emotion_driver, access_count, dormant, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            edge.from_id,
                            edge.to_id,
                            edge.type,
                            edge.weight,
                            edge.decayed_weight,
                            edge.emotion_driver,
                            edge.access_count,
                            edge.dormant,
                            created_at,
                        ),
                    )
                    created_count += 1
                    logger.debug(f"Created edge: {edge.from_id} -> {edge.to_id} (type={edge.type})")

        return {"created": created_count, "updated": updated_count}

    def update_decayed_weight(self, edge_id: int, decayed_weight: float) -> bool:
        """更新边的衰减权重。

        Args:
            edge_id: 边ID
            decayed_weight: 衰减后权重

        Returns:
            True如果更新成功，False如果边不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experience_edges
                SET decayed_weight = ?
                WHERE id = ?
            """,
                (decayed_weight, edge_id),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated decayed_weight for edge: {edge_id}")
            return success

    def set_dormant(self, edge_id: int, dormant: bool) -> bool:
        """设置边的休眠状态。

        Args:
            edge_id: 边ID
            dormant: 休眠状态（True=休眠，False=活跃）

        Returns:
            True如果更新成功，False如果边不存在
        """
        dormant_value = 1 if dormant else 0

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE experience_edges
                SET dormant = ?
                WHERE id = ?
            """,
                (dormant_value, edge_id),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Set dormant={dormant} for edge: {edge_id}")
            return success

    # ========== 辅助方法 ==========

    def _row_to_edge(self, row) -> ExperienceEdge:
        """将数据库行转换为ExperienceEdge对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            ExperienceEdge对象
        """
        return ExperienceEdge(
            id=row["id"],
            from_id=row["from_id"],
            to_id=row["to_id"],
            type=row["type"],
            weight=row["weight"],
            decayed_weight=row["decayed_weight"],
            emotion_driver=row["emotion_driver"],
            access_count=row["access_count"],
            dormant=row["dormant"] if "dormant" in row.keys() else 0,
            created_at=row["created_at"],
        )


# 全局ExperienceEdgeStore实例
experience_edge_store = ExperienceEdgeStore()  # 使用默认db_manager
