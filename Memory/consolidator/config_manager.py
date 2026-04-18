"""衰减参数配置管理器模块。

提供运行时动态调整衰减参数的接口，支持参数的读取、设置和验证。
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from Memory.storage.database import db_manager as global_db_manager

logger = logging.getLogger(__name__)


# 默认衰减参数（与schema.py migrate_to_v3中的值一致）
DEFAULT_DECAY_PARAMS = {
    "lambda_L0": (0.01, "L0摘要衰减率"),
    "lambda_L1": (0.02, "L1要点衰减率"),
    "lambda_L2": (0.03, "L2细节衰减率"),
    "lambda_L3": (0.05, "L3原始记录衰减率"),
    "lambda_temporal": (0.02, "时序边衰减率"),
    "lambda_thematic": (0.015, "主题边衰减率"),
    "lambda_causal": (0.01, "因果边衰减率"),
    "lambda_associative": (0.025, "联想边衰减率"),
    "alpha": (0.05, "强化系数（每被召回一次权重增加5%）"),
    "beta": (0.5, "情感保护系数"),
    "dormancy_threshold": (0.05, "休眠阈值（边权重低于此值标记休眠）"),
}


class DecayConfigManager:
    """衰减参数配置管理器。

    提供参数的读取、设置和列表功能，支持运行时动态调整衰减参数。
    """

    def __init__(self, db_manager=None):
        """初始化DecayConfigManager。

        Args:
            db_manager: DatabaseManager实例，默认使用全局db_manager
        """
        self.db = db_manager if db_manager is not None else global_db_manager
        self._init_default_config()

    def _init_default_config(self):
        """初始化默认参数（如果decay_config表为空）。"""
        with self.db.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM decay_config")
            row = cursor.fetchone()

            if row["count"] == 0:
                logger.info("Initializing default decay parameters")
                now = datetime.now().isoformat()

                for key, (value, description) in DEFAULT_DECAY_PARAMS.items():
                    cursor.execute(
                        """
                        INSERT INTO decay_config (key, value, description, updated_at)
                        VALUES (?, ?, ?, ?)
                    """,
                        (key, value, description, now),
                    )

                logger.info(f"Initialized {len(DEFAULT_DECAY_PARAMS)} decay parameters")

    def get(self, key: str) -> Optional[float]:
        """获取参数值。

        Args:
            key: 参数名（如'lambda_L0'）

        Returns:
            参数值，不存在返回None
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT value FROM decay_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def set(self, key: str, value: float, description: Optional[str] = None) -> bool:
        """设置参数值。

        Args:
            key: 参数名
            value: 参数值
            description: 参数描述（可选，更新时覆盖）

        Returns:
            True如果设置成功

        Raises:
            ValueError: 参数验证失败
        """
        # 参数验证
        self._validate_parameter(key, value)

        now = datetime.now().isoformat()

        with self.db.transaction() as cursor:
            if description:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO decay_config (key, value, description, updated_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (key, value, description, now),
                )
            else:
                cursor.execute(
                    """
                    UPDATE decay_config
                    SET value = ?, updated_at = ?
                    WHERE key = ?
                """,
                    (value, now, key),
                )

            logger.info(f"Updated decay parameter: {key} = {value}")

        return True

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """列出所有参数。

        Returns:
            参数字典 {
                key: {
                    'value': float,
                    'description': str
                }
            }
        """
        with self.db.transaction() as cursor:
            cursor.execute("SELECT key, value, description FROM decay_config ORDER BY key")
            rows = cursor.fetchall()

            return {
                row["key"]: {"value": row["value"], "description": row["description"]}
                for row in rows
            }

    def _validate_parameter(self, key: str, value: float):
        """验证参数值。

        Args:
            key: 参数名
            value: 参数值

        Raises:
            ValueError: 参数验证失败
        """
        # 所有λ值必须大于0
        if key.startswith("lambda_"):
            if value <= 0:
                raise ValueError(f"lambda parameter must be > 0, got {value}")

        # alpha必须在[0, 1]范围
        elif key == "alpha":
            if not 0 <= value <= 1:
                raise ValueError(f"alpha must be between 0 and 1, got {value}")

        # beta必须在[0, 1]范围
        elif key == "beta":
            if not 0 <= value <= 1:
                raise ValueError(f"beta must be between 0 and 1, got {value}")

        # dormancy_threshold必须在[0, 1]范围
        elif key == "dormancy_threshold":
            if not 0 <= value <= 1:
                raise ValueError(f"dormancy_threshold must be between 0 and 1, got {value}")
