"""信息层实体存储模块。

本模块提供信息层实体（entities表）的CRUD操作。
关键功能：
- embedding字段的BLOB存储和读取
- properties、emotion_timeline、emotion_current字段的JSON序列化
- entities表name字段UNIQUE约束（同名即同人）
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
class Entity:
    """信息层实体数据类。

    Attributes:
        id: 实体ID（UUID格式）
        type: 实体类型（person/place/concept/event/skill/other）
        name: 实体名（唯一）
        properties: 属性字典（JSON格式，只包含业务属性）
        source: 信息来源（表字段，元数据）
        confidence: 置信度（表字段，元数据，0-1）
        embedding: name+properties的语义向量（768维numpy数组）
        emotion_timeline: 情感时间线（JSON格式，person类型专用）
        emotion_current: 当前情感（JSON格式，person类型专用）
        created_at: 创建时间
        updated_at: 更新时间
    """

    id: str
    name: str
    type: str
    properties: Optional[Dict[str, Any]] = None
    source: Optional[str] = None  # 新增：元数据字段
    confidence: Optional[float] = None  # 新增：元数据字段
    embedding: Optional[np.ndarray] = None
    emotion_timeline: Optional[Dict[str, Any]] = None
    emotion_current: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class EntityStore:
    """信息层实体存储类。

    提供信息层实体的增删改查操作。
    正确处理embedding字段的BLOB存储和JSON字段的序列化。
    """

    def __init__(self, db_manager=None):
        """初始化EntityStore。
        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager

    def create(self, entity: Entity) -> str:
        """创建新的实体。

        Args:
            entity: Entity对象

        Returns:
            创建的实体ID

        Raises:
            sqlite3.IntegrityError: name重复时抛出异常（UNIQUE约束）
        """
        now = datetime.now().isoformat()
        created_at = entity.created_at or now
        updated_at = entity.updated_at or now

        # 序列化字段
        embedding_blob = self._serialize_embedding(entity.embedding)
        properties_json = self._serialize_json(entity.properties)
        emotion_timeline_json = self._serialize_json(entity.emotion_timeline)
        emotion_current_json = self._serialize_json(entity.emotion_current)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO entities (
                    id, type, name, properties, source, confidence, embedding,
                    emotion_timeline, emotion_current,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entity.id,
                    entity.type,
                    entity.name,
                    properties_json,
                    entity.source,  # 新增：元数据字段
                    entity.confidence,  # 新增：元数据字段
                    embedding_blob,
                    emotion_timeline_json,
                    emotion_current_json,
                    created_at,
                    updated_at,
                ),
            )

        logger.debug(f"Created entity: {entity.id} ({entity.name})")
        return entity.id

    def get(self, entity_id: str) -> Optional[Entity]:
        """获取实体。

        Args:
            entity_id: 实体ID

        Returns:
            Entity对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_entity(row)
            return None

    def get_by_name(self, name: str) -> Optional[Entity]:
        """根据名称获取实体。

        Args:
            name: 实体名

        Returns:
            Entity对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM entities WHERE name = ?", (name,))
            row = cursor.fetchone()

            if row:
                return self._row_to_entity(row)
            return None

    def get_by_type(self, entity_type: str) -> List[Entity]:
        """获取指定类型的所有实体。

        Args:
            entity_type: 实体类型（person/place/concept等）

        Returns:
            Entity列表
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM entities
                WHERE type = ?
                ORDER BY created_at DESC
            """,
                (entity_type,),
            )

            return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_all(self, limit: Optional[int] = None) -> List[Entity]:
        """获取所有实体。

        Args:
            limit: 限制返回数量，None表示全部

        Returns:
            Entity列表
        """
        with self.db.transaction() as cursor:
            if limit:
                cursor.execute("SELECT * FROM entities ORDER BY created_at DESC LIMIT ?", (limit,))
            else:
                cursor.execute("SELECT * FROM entities ORDER BY created_at DESC")

            return [self._row_to_entity(row) for row in cursor.fetchall()]

    def update(self, entity: Entity) -> bool:
        """更新实体。

        注意：name字段不能修改（UNIQUE约束）

        Args:
            entity: Entity对象

        Returns:
            True如果更新成功，False如果实体不存在
        """
        now = datetime.now().isoformat()

        # 序列化字段
        embedding_blob = self._serialize_embedding(entity.embedding)
        properties_json = self._serialize_json(entity.properties)
        emotion_timeline_json = self._serialize_json(entity.emotion_timeline)
        emotion_current_json = self._serialize_json(entity.emotion_current)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE entities SET
                    type = ?, properties = ?, embedding = ?,
                    emotion_timeline = ?, emotion_current = ?,
                    updated_at = ?
                WHERE id = ?
            """,
                (
                    entity.type,
                    properties_json,
                    embedding_blob,
                    emotion_timeline_json,
                    emotion_current_json,
                    now,
                    entity.id,
                ),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated entity: {entity.id}")
            return success

    def update_properties(self, entity_id: str, properties: Dict[str, Any]) -> bool:
        """更新实体的properties字段。

        Args:
            entity_id: 实体ID
            properties: 新的属性字典

        Returns:
            True如果更新成功，False如果实体不存在
        """
        now = datetime.now().isoformat()
        properties_json = json.dumps(properties, ensure_ascii=False)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE entities
                SET properties = ?, updated_at = ?
                WHERE id = ?
            """,
                (properties_json, now, entity_id),
            )

            return cursor.rowcount > 0

    def delete(self, entity_id: str) -> bool:
        """删除实体。

        警告：此操作会同时删除关联的边（外键CASCADE）

        Args:
            entity_id: 实体ID

        Returns:
            True如果删除成功，False如果实体不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted entity: {entity_id}")
            return success

    def exists_by_name(self, name: str) -> bool:
        """检查指定名称的实体是否存在。

        Args:
            name: 实体名

        Returns:
            True如果存在，False否则
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM entities WHERE name = ?", (name,))
            return cursor.fetchone()[0] > 0

    def count(self) -> int:
        """统计实体总数。

        Returns:
            实体总数
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM entities")
            return cursor.fetchone()[0]

    def count_by_type(self) -> Dict[str, int]:
        """统计各类型实体数量。

        Returns:
            字典，键为类型，值为数量
        """
        with self.db.transaction() as cursor:
            cursor.execute("""
                SELECT type, COUNT(*) as count
                FROM entities
                GROUP BY type
            """)

            return {row["type"]: row["count"] for row in cursor.fetchall()}

    def get_shared_properties(
        self, threshold: int = 5, property_names: List[str] = None
    ) -> List[Dict[str, Any]]:
        """查询被多个实体共享的属性。

        扫描entities表的properties字段，统计每个属性值
        被多少实体共享。只返回共享次数>=threshold的属性。

        Args:
            threshold: 最小共享次数（默认5）
            property_names: 要检查的属性名列表（None表示所有）

        Returns:
            共享属性列表，每项包含 {
                'property_name': 属性名,
                'property_value': 属性值,
                'entities': [实体ID列表],
                'count': 共享次数
            }
        """
        # 获取所有实体
        entities = self.get_all()

        # 统计属性值
        property_counter = {}  # {(property_name, value): {entities: [], count: 0}}

        for entity in entities:
            if not entity.properties:
                continue

            for prop_name, prop_value in entity.properties.items():
                # 如果指定了属性名列表，只检查这些
                if property_names and prop_name not in property_names:
                    continue

                # 将值转为可哈希类型
                if isinstance(prop_value, (str, int, float, bool)):
                    key = (prop_name, str(prop_value))
                else:
                    key = (prop_name, json.dumps(prop_value, ensure_ascii=False))

                if key not in property_counter:
                    property_counter[key] = {
                        "property_name": prop_name,
                        "property_value": prop_value,
                        "entities": [],
                        "count": 0,
                    }

                property_counter[key]["entities"].append(entity.id)
                property_counter[key]["count"] += 1

        # 筛选共享次数>=threshold的属性
        shared_properties = [
            prop for prop in property_counter.values() if prop["count"] >= threshold
        ]

        # 按共享次数降序排序
        shared_properties.sort(key=lambda x: x["count"], reverse=True)

        logger.debug(f"找到{len(shared_properties)}个共享属性(>={threshold}次)")

        return shared_properties

    def get_frequent_entities(
        self, entity_type: str = "person", days: int = 30, min_count: int = 3
    ) -> List[Entity]:
        """查询最近N天出现频率最高的实体。

        通过cross_edges统计实体被关联的次数（即出现的体验数）。

        Args:
            entity_type: 实体类型（如'person'）
            days: 查询最近N天（默认30天）
            min_count: 最小出现次数（默认3次）

        Returns:
            实体列表，按出现次数降序排序
        """
        from datetime import datetime, timedelta
        from Memory.storage.cross_edge_store import CrossEdgeStore

        # 获取cross_edge_store实例
        if not hasattr(self, "_cross_edge_store") or self._cross_edge_store is None:
            self._cross_edge_store = CrossEdgeStore(self.db)

        # 获取最近N天的cross_edges
        recent_cross_edges = self._cross_edge_store.get_recent_edges(
            days=days, from_type=entity_type
        )

        # 统计每个实体出现的次数
        entity_count = {}
        for edge in recent_cross_edges:
            entity_id = edge.from_id
            entity_count[entity_id] = entity_count.get(entity_id, 0) + 1

        # 筛选出现次数>=min_count的实体
        frequent_entity_ids = [
            entity_id for entity_id, count in entity_count.items() if count >= min_count
        ]

        if not frequent_entity_ids:
            return []

        # 获取实体详细信息
        frequent_entities = []
        for entity_id in frequent_entity_ids:
            entity = self.get(entity_id)
            if entity:
                # 添加count属性用于排序
                entity._appearance_count = entity_count[entity_id]
                frequent_entities.append(entity)

        # 按出现次数降序排序
        frequent_entities.sort(key=lambda e: getattr(e, "_appearance_count", 0), reverse=True)

        return frequent_entities

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

    def _serialize_json(self, data: Optional[Dict[str, Any]]) -> Optional[str]:
        """将字典序列化为JSON字符串。

        Args:
            data: 字典数据

        Returns:
            JSON字符串，None如果输入为None
        """
        if data is None:
            return None

        return json.dumps(data, ensure_ascii=False)

    def _deserialize_json(self, json_str: Optional[str]) -> Optional[Dict[str, Any]]:
        """将JSON字符串反序列化为字典。

        Args:
            json_str: JSON字符串

        Returns:
            字典数据，None如果输入为None或空字符串
        """
        if not json_str:
            return None

        return json.loads(json_str)

    def _row_to_entity(self, row) -> Entity:
        """将数据库行转换为Entity对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            Entity对象
        """
        return Entity(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            properties=self._deserialize_json(row["properties"]),
            source=row["source"] if "source" in row.keys() else None,  # 新增：元数据字段
            confidence=row["confidence"] if "confidence" in row.keys() else None,  # 新增：元数据字段
            embedding=self._deserialize_embedding(row["embedding"]),
            emotion_timeline=self._deserialize_json(row["emotion_timeline"]),
            emotion_current=self._deserialize_json(row["emotion_current"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# 全局EntityStore实例
entity_store = EntityStore()
