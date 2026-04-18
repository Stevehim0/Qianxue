"""状态层存储模块。

本模块提供状态层（state表）的CRUD操作。
状态层是单行表（CHECK (id = 1)），存储AI的当前状态变量。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class State:
    """状态层数据类。

    Attributes:
        id: 固定为1（CHECK约束）
        mood_valence: 效价（-1到1，负负面正正面）
        mood_arousal: 唤醒度（0-1，低平静高激动）
        mood_label: 自然语言标签
        energy_value: 精力值（0-1）
        energy_label: 精力标签
        focus: 注意力（字符串或null）
        confidence_value: 信心值（0-1）
        confidence_label: 信心标签
        updated_at: 更新时间
    """

    mood_valence: float = 0.0
    mood_arousal: float = 0.3
    mood_label: str = "平静"
    energy_value: float = 0.7
    energy_label: str = "正常"
    focus: Optional[str] = None
    confidence_value: float = 0.7
    confidence_label: str = "正常"
    updated_at: Optional[str] = None
    id: int = 1  # 固定为1


class StateStore:
    """状态层存储类。

    提供状态层的增删改查操作。
    单行表：确保只有一条记录（id=1）。
    状态永久持续，初始化时从数据库读取。
    """

    # 固定的ID值
    SINGLE_ROW_ID = 1

    # 默认值常量
    DEFAULT_MOOD_VALENCE = 0.0
    DEFAULT_MOOD_AROUSAL = 0.3
    DEFAULT_MOOD_LABEL = "平静"
    DEFAULT_ENERGY_VALUE = 0.7
    DEFAULT_ENERGY_LABEL = "正常"
    DEFAULT_CONFIDENCE_VALUE = 0.7
    DEFAULT_CONFIDENCE_LABEL = "正常"

    def __init__(self, db_manager=None):
        """初始化StateStore。

        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager
        self._initialized = False  # 延迟初始化标志

    def get(self) -> State:
        """获取状态层数据。

        Returns:
            State对象，总是返回数据（不存在则创建默认值）
        """
        # 延迟初始化：首次get时才确保行存在
        if not self._initialized and self.db is not None:
            self._ensure_row_exists()
            self._initialized = True

        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM state WHERE id = ?", (self.SINGLE_ROW_ID,))
            row = cursor.fetchone()

            if row:
                return self._row_to_state(row)
            else:
                # 不存在则创建默认行
                return self._create_default()

    def update_mood(self, valence: float, arousal: float, label: Optional[str] = None) -> bool:
        """更新情感状态。

        Args:
            valence: 效价（-1到1）
            arousal: 唤醒度（0到1）
            label: 自然语言标签（可选，自动生成）

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        # 自动生成标签
        if label is None:
            label = self._generate_mood_label(valence, arousal)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE state
                SET mood_valence = ?, mood_arousal = ?, mood_label = ?, updated_at = ?
                WHERE id = ?
            """,
                (valence, arousal, label, now, self.SINGLE_ROW_ID),
            )

            logger.debug(f"Updated mood: valence={valence}, arousal={arousal}")
            return True

    def update_energy(self, value: float, label: Optional[str] = None) -> bool:
        """更新精力状态。

        Args:
            value: 精力值（0-1）
            label: 精力标签（可选，自动生成）

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        # 自动生成标签
        if label is None:
            label = self._generate_energy_label(value)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE state
                SET energy_value = ?, energy_label = ?, updated_at = ?
                WHERE id = ?
            """,
                (value, label, now, self.SINGLE_ROW_ID),
            )

            logger.debug(f"Updated energy: value={value}")
            return True

    def update_focus(self, focus: Optional[str]) -> bool:
        """更新当前专注点。

        Args:
            focus: 专注点描述（null表示无焦点）

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE state
                SET focus = ?, updated_at = ?
                WHERE id = ?
            """,
                (focus, now, self.SINGLE_ROW_ID),
            )

            logger.debug(f"Updated focus: {focus}")
            return True

    def update_confidence(self, value: float, label: Optional[str] = None) -> bool:
        """更新自信度。

        Args:
            value: 自信度（0到1）
            label: 自信标签（可选，自动生成）

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        # 自动生成标签
        if label is None:
            label = self._generate_confidence_label(value)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE state
                SET confidence_value = ?, confidence_label = ?, updated_at = ?
                WHERE id = ?
            """,
                (value, label, now, self.SINGLE_ROW_ID),
            )

            logger.debug(f"Updated confidence: {label} (value={value})")
            return True

    def update_all(self, state: State) -> bool:
        """更新所有状态字段。

        Args:
            state: State对象

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE state
                SET mood_valence = ?, mood_arousal = ?, mood_label = ?,
                    energy_value = ?, energy_label = ?, focus = ?,
                    confidence_value = ?, confidence_label = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    state.mood_valence,
                    state.mood_arousal,
                    state.mood_label,
                    state.energy_value,
                    state.energy_label,
                    state.focus,
                    state.confidence_value,
                    state.confidence_label,
                    now,
                    self.SINGLE_ROW_ID,
                ),
            )

            logger.debug("Updated all state fields")
            return True

    def get_updated_at(self) -> Optional[str]:
        """获取状态最后更新时间。

        Returns:
            ISO格式时间戳，None如果不存在
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT updated_at FROM state WHERE id = ?", (self.SINGLE_ROW_ID,))
            row = cursor.fetchone()
            return row["updated_at"] if row else None

    def reset_to_default(self) -> State:
        """重置为状态层默认值。

        Returns:
            重置后的State对象
        """
        with self.db.transaction() as cursor:
            # 删除现有行（如果存在）
            cursor.execute("DELETE FROM state WHERE id = ?", (self.SINGLE_ROW_ID,))

            # 创建新的默认行
            return self._create_default()

    # ========== 私有方法 ==========

    def _ensure_row_exists(self) -> None:
        """确保状态层表有一行数据。"""
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM state")
            if cursor.fetchone()[0] == 0:
                self._create_default()

    def _create_default(self) -> State:
        """创建默认的状态数据。

        Returns:
            默认的State对象
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR ABORT INTO state (
                    id, mood_valence, mood_arousal, mood_label,
                    energy_value, energy_label, focus,
                    confidence_value, confidence_label, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.SINGLE_ROW_ID,
                    self.DEFAULT_MOOD_VALENCE,
                    self.DEFAULT_MOOD_AROUSAL,
                    self.DEFAULT_MOOD_LABEL,
                    self.DEFAULT_ENERGY_VALUE,
                    self.DEFAULT_ENERGY_LABEL,
                    None,  # focus
                    self.DEFAULT_CONFIDENCE_VALUE,
                    self.DEFAULT_CONFIDENCE_LABEL,
                    now,
                ),
            )

        logger.info("Created default state")
        return State(
            id=self.SINGLE_ROW_ID,
            mood_valence=self.DEFAULT_MOOD_VALENCE,
            mood_arousal=self.DEFAULT_MOOD_AROUSAL,
            mood_label=self.DEFAULT_MOOD_LABEL,
            energy_value=self.DEFAULT_ENERGY_VALUE,
            energy_label=self.DEFAULT_ENERGY_LABEL,
            focus=None,
            confidence_value=self.DEFAULT_CONFIDENCE_VALUE,
            confidence_label=self.DEFAULT_CONFIDENCE_LABEL,
            updated_at=now,
        )

    def _generate_mood_label(self, valence: float, arousal: float) -> str:
        """根据效价和唤醒度生成情感标签。

        Args:
            valence: 效价（-1到1）
            arousal: 唤醒度（0到1）

        Returns:
            自然语言标签
        """
        if arousal < 0.3:
            return "平静"
        elif valence > 0.3:
            return "兴奋" if arousal > 0.7 else "愉快"
        elif valence < -0.3:
            return "愤怒" if arousal > 0.7 else "低落"
        else:
            return "好奇"

    def _generate_energy_label(self, value: float) -> str:
        """根据精力值生成标签。

        Args:
            value: 精力值（0-1）

        Returns:
            精力标签
        """
        if value > 0.8:
            return "充沛"
        elif value > 0.5:
            return "正常"
        elif value > 0.3:
            return "疲惫"
        else:
            return "耗尽"

    def _generate_confidence_label(self, value: float) -> str:
        """根据信心值生成标签。

        Args:
            value: 信心值（0-1）

        Returns:
            信心标签
        """
        if value > 0.8:
            return "自信"
        elif value > 0.5:
            return "正常"
        elif value > 0.3:
            return "犹豫"
        else:
            return "迷茫"

    def _row_to_state(self, row) -> State:
        """将数据库行转换为State对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            State对象
        """
        return State(
            id=row["id"],
            mood_valence=row["mood_valence"],
            mood_arousal=row["mood_arousal"],
            mood_label=row["mood_label"],
            energy_value=row["energy_value"],
            energy_label=row["energy_label"],
            focus=row["focus"],
            confidence_value=row["confidence_value"],
            confidence_label=row["confidence_label"],
            updated_at=row["updated_at"],
        )


# 全局StateStore实例
state_store = StateStore()
