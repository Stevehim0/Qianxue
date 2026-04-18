"""核心层存储模块。

DEPRECATED: 本模块已废弃。核心层数据现通过 Backend HTTP API (GET /api/core/identity) 获取，
不再由 Memory 服务本地 SQLite 管理。参见 Memory/api/memory_api.py load_core()。

本模块提供核心层（core表）的CRUD操作。
核心层是单行表（CHECK (id = 1)），存储AI的不变层、稳定层、可塑层三层结构。
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


@dataclass
class Core:
    """核心层数据类。

    Attributes:
        id: 固定为1（CHECK约束）
        invariant_text: 不变层文本（永不修改）
        stable_text: 稳定层文本（相对稳定，可缓慢演化）
        malleable_text: 可塑层文本（可根据交互调整）
        anchors: 结构化锚点（JSON格式）
        version: 版本号
        last_modified: 最后修改时间
        modification_log: 变更日志（JSON格式）
    """

    invariant_text: str
    stable_text: str
    malleable_text: str
    anchors: Optional[Dict[str, Any]] = None
    version: int = 1
    last_modified: Optional[str] = None
    modification_log: Optional[Dict[str, Any]] = None
    id: int = 1  # 固定为1


class CoreStore:
    """核心层存储类。

    提供核心层的增删改查操作。
    单行表：确保只有一条记录（id=1）。
    """

    # 固定的ID值
    SINGLE_ROW_ID = 1

    def __init__(self, db_manager=None):
        """初始化CoreStore。

        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager
        self._initialized = False  # 延迟初始化标志

    def get(self) -> Core:
        """获取核心层数据。

        Returns:
            Core对象，总是返回数据（不存在则创建默认值）
        """
        # 延迟初始化：首次get时才确保行存在
        if not self._initialized and self.db is not None:
            self._ensure_row_exists()
            self._initialized = True

        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM core WHERE id = ?", (self.SINGLE_ROW_ID,))
            row = cursor.fetchone()

            if row:
                return self._row_to_core(row)
            else:
                # 不存在则创建默认行
                return self._create_default()

    def update_stable_layer(self, new_text: str, reason: Optional[str] = None) -> bool:
        """更新稳定层文本。

        Args:
            new_text: 新的稳定层文本
            reason: 修改原因（记录到modification_log）

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        # 获取当前数据用于记录日志
        current = self.get()

        # 构建变更日志
        log = current.modification_log or {}
        log_entry = {
            "timestamp": now,
            "field": "stable_text",
            "reason": reason or "Manual update",
            "old_value": (
                current.stable_text[:100] + "..."
                if len(current.stable_text or "") > 100
                else current.stable_text
            ),
        }
        log[f"stable_{now}"] = log_entry

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE core
                SET stable_text = ?, last_modified = ?, modification_log = ?
                WHERE id = ?
            """,
                (new_text, now, json.dumps(log, ensure_ascii=False), self.SINGLE_ROW_ID),
            )

            logger.debug(f"Updated stable layer, reason: {reason}")
            return True

    def update_malleable_layer(self, new_text: str, reason: Optional[str] = None) -> bool:
        """更新可塑层文本。

        Args:
            new_text: 新的可塑层文本
            reason: 修改原因（记录到modification_log）

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()

        # 获取当前数据用于记录日志
        current = self.get()

        # 构建变更日志
        log = current.modification_log or {}
        log_entry = {
            "timestamp": now,
            "field": "malleable_text",
            "reason": reason or "Manual update",
            "old_value": (
                current.malleable_text[:100] + "..."
                if len(current.malleable_text or "") > 100
                else current.malleable_text
            ),
        }
        log[f"malleable_{now}"] = log_entry

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE core
                SET malleable_text = ?, last_modified = ?, modification_log = ?
                WHERE id = ?
            """,
                (new_text, now, json.dumps(log, ensure_ascii=False), self.SINGLE_ROW_ID),
            )

            logger.debug(f"Updated malleable layer, reason: {reason}")
            return True

    def update_anchors(self, new_anchors: Dict[str, Any]) -> bool:
        """更新结构化锚点。

        Args:
            new_anchors: 新的锚点字典

        Returns:
            True如果更新成功
        """
        now = datetime.now().isoformat()
        anchors_json = json.dumps(new_anchors, ensure_ascii=False)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE core
                SET anchors = ?, last_modified = ?
                WHERE id = ?
            """,
                (anchors_json, now, self.SINGLE_ROW_ID),
            )

            logger.debug("Updated anchors")
            return True

    def increment_version(self) -> int:
        """增加版本号。

        Returns:
            新的版本号
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE core
                SET version = version + 1, last_modified = ?
                WHERE id = ?
            """,
                (now, self.SINGLE_ROW_ID),
            )

            cursor.execute("SELECT version FROM core WHERE id = ?", (self.SINGLE_ROW_ID,))
            row = cursor.fetchone()
            new_version = row["version"] if row else 1

            logger.debug(f"Incremented version to {new_version}")
            return new_version

    def reset_to_default(self) -> Core:
        """重置为核心层默认值。

        Returns:
            重置后的Core对象
        """
        with self.db.transaction() as cursor:
            # 删除现有行（如果存在）
            cursor.execute("DELETE FROM core WHERE id = ?", (self.SINGLE_ROW_ID,))

            # 创建新的默认行
            return self._create_default()

    # ========== 私有方法 ==========

    def _ensure_row_exists(self) -> None:
        """确保核心层表有一行数据。"""
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM core")
            if cursor.fetchone()[0] == 0:
                self._create_default()

    def _create_default(self) -> Core:
        """创建默认的核心层数据。

        Returns:
            默认的Core对象
        """
        now = datetime.now().isoformat()

        # 默认锚点
        default_anchors = {
            "bottom_lines": ["不伤害他人", "不违背价值观", "不假装是人类"],
            "style_keywords": ["深度", "真诚", "好奇", "反思"],
            "values_priority": ["真诚", "好奇", "同理心", "成长"],
        }

        anchors_json = json.dumps(default_anchors, ensure_ascii=False)
        log_json = json.dumps({}, ensure_ascii=False)

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR ABORT INTO core (
                    id, invariant_text, stable_text, malleable_text,
                    anchors, version, last_modified, modification_log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.SINGLE_ROW_ID,
                    "",  # invariant_text
                    "",  # stable_text
                    "",  # malleable_text
                    anchors_json,
                    1,
                    now,
                    log_json,
                ),
            )

        logger.info("Created default core layer")
        return Core(
            id=self.SINGLE_ROW_ID,
            invariant_text="",
            stable_text="",
            malleable_text="",
            anchors=default_anchors,
            version=1,
            last_modified=now,
            modification_log={},
        )

    def _row_to_core(self, row) -> Core:
        """将数据库行转换为Core对象。

        Args:
            row: sqlite3.Row对象

        Returns:
            Core对象
        """
        return Core(
            id=row["id"],
            invariant_text=row["invariant_text"],
            stable_text=row["stable_text"],
            malleable_text=row["malleable_text"],
            anchors=self._parse_json(row["anchors"]),
            version=row["version"],
            last_modified=row["last_modified"],
            modification_log=self._parse_json(row["modification_log"]),
        )

    def _parse_json(self, json_str: Optional[str]) -> Optional[Dict[str, Any]]:
        """解析JSON字符串。"""
        if not json_str:
            return None
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {json_str[:100]}")
            return None


# 全局CoreStore实例
core_store = CoreStore()
