"""个人档案存储模块。

本模块提供个人档案（person_profiles表）的CRUD操作。
个人档案存储关于特定人物的交互风格、偏好等信息。
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class PersonProfile:
    """个人档案数据类。

    Attributes:
        id: 档案ID（profile_姓名格式）
        memory_index: 指向记忆系统中的实体ID（可选）
        basic: 基本信息字典（JSON格式）
        interaction_style: 相处方式参数（JSON格式）
        preferences: 沟通偏好（JSON格式）
        last_updated: 最后更新时间
        updated_by: 更新者（默认为dream_ai）
    """

    id: str
    basic: Optional[Dict[str, Any]] = None
    interaction_style: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    memory_index: Optional[str] = None
    last_updated: Optional[str] = None
    updated_by: str = "dream_ai"


class ProfileStore:
    """个人档案存储类。

    提供个人档案的增删改查操作。
    正确处理JSON字段的序列化。
    """

    def __init__(self, db_manager=None):
        """初始化ProfileStore。
        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager

    def create(self, profile: PersonProfile) -> str:
        """创建新的个人档案。

        Args:
            profile: PersonProfile对象

        Returns:
            创建的档案ID

        Raises:
            sqlite3.IntegrityError: ID重复时抛出异常
        """
        now = datetime.now().isoformat()
        last_updated = profile.last_updated or now

        # 序列化JSON字段
        basic_json = self._serialize_json(profile.basic)
        interaction_style_json = self._serialize_json(profile.interaction_style)
        preferences_json = self._serialize_json(profile.preferences)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO person_profiles (
                    id, memory_index, basic, interaction_style,
                    preferences, last_updated, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    profile.id,
                    profile.memory_index,
                    basic_json,
                    interaction_style_json,
                    preferences_json,
                    last_updated,
                    profile.updated_by,
                ),
            )

        logger.debug(f"Created person profile: {profile.id}")
        return profile.id

    def get(self, profile_id: str) -> Optional[PersonProfile]:
        """获取个人档案。

        Args:
            profile_id: 档案ID

        Returns:
            PersonProfile对象，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM person_profiles WHERE id = ?", (profile_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_profile(row)
            return None

    def get_by_name(self, name: str) -> Optional[PersonProfile]:
        """根据人名获取个人档案。

        Args:
            name: 人名

        Returns:
            PersonProfile对象，不存在返回None
        """
        profile_id = f"profile_{name}"
        return self.get(profile_id)

    def get_all(self) -> List[PersonProfile]:
        """获取所有个人档案。

        Returns:
            PersonProfile列表
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM person_profiles ORDER BY last_updated DESC")
            return [self._row_to_profile(row) for row in cursor.fetchall()]

    def list_all(self) -> List[PersonProfile]:
        """获取所有个人档案（get_all 的别名）。

        Returns:
            PersonProfile列表
        """
        return self.get_all()

    def update(self, profile: PersonProfile) -> bool:
        """更新个人档案。

        Args:
            profile: PersonProfile对象

        Returns:
            True如果更新成功，False如果档案不存在
        """
        now = datetime.now().isoformat()

        # 序列化JSON字段
        basic_json = self._serialize_json(profile.basic)
        interaction_style_json = self._serialize_json(profile.interaction_style)
        preferences_json = self._serialize_json(profile.preferences)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE person_profiles SET
                    memory_index = ?, basic = ?, interaction_style = ?,
                    preferences = ?, last_updated = ?, updated_by = ?
                WHERE id = ?
            """,
                (
                    profile.memory_index,
                    basic_json,
                    interaction_style_json,
                    preferences_json,
                    now,
                    profile.updated_by,
                    profile.id,
                ),
            )

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated person profile: {profile.id}")
            return success

    def update_interaction_style(
        self, profile_id: str, interaction_style: Dict[str, Any], updated_by: str = "dream_ai"
    ) -> bool:
        """更新相处方式。

        Args:
            profile_id: 档案ID
            interaction_style: 新的相处方式字典
            updated_by: 更新者

        Returns:
            True如果更新成功，False如果档案不存在
        """
        now = datetime.now().isoformat()
        style_json = json.dumps(interaction_style, ensure_ascii=False)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE person_profiles
                SET interaction_style = ?, last_updated = ?, updated_by = ?
                WHERE id = ?
            """,
                (style_json, now, updated_by, profile_id),
            )

            return cursor.rowcount > 0

    def delete(self, profile_id: str) -> bool:
        """删除个人档案。

        Args:
            profile_id: 档案ID

        Returns:
            True如果删除成功，False如果档案不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("DELETE FROM person_profiles WHERE id = ?", (profile_id,))
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted person profile: {profile_id}")
            return success

    def exists(self, profile_id: str) -> bool:
        """检查档案是否存在。

        Args:
            profile_id: 档案ID

        Returns:
            True如果存在，False否则
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM person_profiles WHERE id = ?", (profile_id,))
            return cursor.fetchone()[0] > 0

    def exists_by_name(self, name: str) -> bool:
        """检查指定人名的档案是否存在。

        Args:
            name: 人名

        Returns:
            True如果存在，False否则
        """
        profile_id = f"profile_{name}"
        return self.exists(profile_id)

    def count(self) -> int:
        """统计个人档案总数。

        Returns:
            档案总数
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM person_profiles")
            return cursor.fetchone()[0]

    # ========== 辅助方法 ==========

    def _serialize_json(self, data: Optional[Dict[str, Any]]) -> Optional[str]:
        """将字典序列化为JSON字符串。"""
        if data is None:
            return None
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_json(self, json_str: Optional[str]) -> Optional[Dict[str, Any]]:
        """将JSON字符串反序列化为字典。"""
        if not json_str:
            return None
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {json_str[:100]}")
            return None

    def _row_to_profile(self, row) -> PersonProfile:
        """将数据库行转换为PersonProfile对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            PersonProfile对象
        """
        return PersonProfile(
            id=row["id"],
            memory_index=row["memory_index"],
            basic=self._deserialize_json(row["basic"]),
            interaction_style=self._deserialize_json(row["interaction_style"]),
            preferences=self._deserialize_json(row["preferences"]),
            last_updated=row["last_updated"],
            updated_by=row["updated_by"],
        )


# 全局ProfileStore实例
profile_store = ProfileStore()
