"""数据库连接管理和初始化模块。

本模块提供全局SQLite数据库连接管理，包括：
- 单连接模式（全局共享一个连接）
- 上下文管理器自动管理事务
- 自动初始化数据库表结构
- 懒加载模式（失败时记录警告但不阻止启动）
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """全局数据库连接管理器。

    使用单连接模式，所有Store模块共享同一个数据库连接。
    提供事务上下文管理器，自动提交或回滚。
    """

    def __init__(self, db_path: Optional[Path] = None):
        """初始化数据库管理器。

        Args:
            db_path: 数据库文件路径，默认使用settings中的配置
        """
        # 确保 db_path 是 Path 对象，支持传入字符串或 Path 对象
        if db_path is None:
            self.db_path = settings.database.db_path
        else:
            self.db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    @property
    def conn(self) -> sqlite3.Connection:
        """延迟创建数据库连接。

        Returns:
            SQLite连接对象

        Raises:
            sqlite3.DatabaseError: 连接失败时抛出异常
        """
        if self._conn is None:
            try:
                # 确保父目录存在
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

                # 创建连接，设置row_factory返回字典式行
                self._conn = sqlite3.connect(
                    self.db_path, check_same_thread=False  # 允许跨线程使用（单线程应用）
                )
                self._conn.row_factory = sqlite3.Row
                logger.info(f"Database connected: {self.db_path}")
            except sqlite3.Error as e:
                logger.error(f"Failed to connect to database: {e}")
                raise sqlite3.DatabaseError(f"Database connection failed: {e}") from e

        return self._conn

    @contextmanager
    def transaction(self):
        """事务上下文管理器，自动提交或回滚。

        Yields:
            cursor: 数据库游标对象

        Example:
            >>> with db_manager.transaction() as cursor:
            ...     cursor.execute("INSERT INTO ...")
            ...     # 成功时自动提交，异常时自动回滚
        """
        cursor = self.conn.cursor()
        try:
            yield cursor
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back due to error: {e}")
            raise e

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    def is_initialized(self) -> bool:
        """检查数据库是否已初始化。

        Returns:
            True如果schema_version表存在，False否则
        """
        try:
            with self.transaction() as cursor:
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='schema_version'
                """)
                return cursor.fetchone() is not None
        except Exception as e:
            logger.warning(f"Failed to check initialization status: {e}")
            return False

    def initialize(self, db_path: Optional[Path] = None) -> bool:
        """初始化数据库表结构。

        如果数据库未初始化，执行建表SQL。
        懒加载模式：失败时记录警告但继续。

        Args:
            db_path: 可选的数据库路径，用于重新初始化不同的数据库

        Returns:
            True如果初始化成功或已初始化，False如果失败
        """
        # 如果提供了新的 db_path，更新数据库路径并关闭现有连接
        if db_path is not None:
            # 关闭现有连接
            if self._conn is not None:
                self.close()
            # 更新路径（确保是 Path 对象）
            self.db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
            # 重置初始化状态
            self._initialized = False

        if self.is_initialized():
            logger.info("Database already initialized")
            return True

        try:
            # 导入并执行schema初始化
            from Memory.storage.schema import create_all_tables

            create_all_tables(self)
            self._initialized = True
            logger.info("Database initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"Database initialization failed (continuing anyway): {e}")
            return False


# 全局数据库管理器实例
db_manager = DatabaseManager()
