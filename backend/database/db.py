"""SQLite database connection and initialization."""

import aiosqlite
import json
from pathlib import Path
from typing import Optional


# 数据库文件路径
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chat.db"


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> aiosqlite.Connection:
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        """建立数据库连接"""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            await self._connection.execute("PRAGMA foreign_keys = ON")
            await self._connection.execute("PRAGMA journal_mode = WAL")
        return self._connection

    async def close(self):
        """关闭数据库连接"""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def initialize_tables(self):
        """初始化数据表"""
        conn = await self.connect()

        # 创建用户信息表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                nickname TEXT,
                user_type TEXT CHECK(user_type IN ('friend', 'group_member', 'robot')),
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0
            )
        """)

        # 创建群聊信息表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                group_name TEXT,
                enabled INTEGER DEFAULT 1,
                auto_reply_enabled INTEGER DEFAULT 1,
                reply_delay_seconds INTEGER DEFAULT 5
            )
        """)

        # 创建对话上下文表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups(group_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_group_user
            ON conversations(group_id, user_id, timestamp)
        """)

        # 创建配置表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS configs (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 插入默认配置
        default_configs = {
            "api_config": '{"current_api": "", "apis": {}}',
            "system_prompt": '{"global_system_prompt": "你是一个友好的AI助手", "group_system_prompts": {}}',
            "context_window": "10"
        }

        for key, value in default_configs.items():
            # 检查是否已存在
            cursor = await conn.execute(
                "SELECT 1 FROM configs WHERE key = ?",
                (key,)
            )
            if not await cursor.fetchone():
                await conn.execute(
                    "INSERT INTO configs (key, value) VALUES (?, ?)",
                    (key, value)
                )

        await conn.commit()

        # 执行数据库迁移
        await self._migrate_database(conn)


    async def _migrate_database(self, conn: aiosqlite.Connection):
        """执行数据库迁移"""
        try:
            # 检查users表的约束
            cursor = await conn.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in await cursor.fetchall()]
            sql_column = next((col for col in columns if col == "user_type"), None)

            # 修改user_type约束，添加robot类型
            if sql_column:
                # SQLite不支持直接修改约束，需要重建表
                # 这里我们使用INSERT OR IGNORE来绕过约束检查
                # 如果约束严格，用户需要手动修改数据库
                # 或者我们创建一个更宽松的约束
                try:
                    # 尝试创建一个没有约束的临时表
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS users_new (
                            user_id TEXT PRIMARY KEY,
                            nickname TEXT,
                            user_type TEXT CHECK(user_type IN ('friend', 'group_member', 'robot')),
                            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            message_count INTEGER DEFAULT 0
                        )
                    """)
                    await conn.commit()
                    print("数据库迁移: 创建了 users_new 表，包含robot类型")
                except Exception as e:
                    print(f"数据库迁移警告（robot类型）: {e}")
                    # 如果创建失败，用户需要手动修改约束

            # 检查conversations表是否已有mentions字段
            cursor = await conn.execute("PRAGMA table_info(conversations)")
            columns = [row[1] for row in await cursor.fetchall()]

            # 添加mentions字段
            if "mentions" not in columns:
                await conn.execute("ALTER TABLE conversations ADD COLUMN mentions TEXT DEFAULT NULL")
                await conn.commit()
                print("数据库迁移: 添加了 conversations.mentions 字段")

            # 添加is_directed_at_bot字段
            if "is_directed_at_bot" not in columns:
                await conn.execute("ALTER TABLE conversations ADD COLUMN is_directed_at_bot INTEGER DEFAULT 0")
                await conn.commit()
                print("数据库迁移: 添加了 conversations.is_directed_at_bot 字段")

            # 添加sender_nickname字段
            if "sender_nickname" not in columns:
                await conn.execute("ALTER TABLE conversations ADD COLUMN sender_nickname TEXT")
                await conn.commit()
                print("数据库迁移: 添加了 conversations.sender_nickname 字段")

            # 添加索引（如果不存在）
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_group_timestamp
                ON conversations(group_id, timestamp DESC)
            """)

            # 统一身份表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS unified_identities (
                    id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS identity_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    platform_id TEXT NOT NULL,
                    platform_nickname TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (identity_id) REFERENCES unified_identities(id),
                    UNIQUE(platform, platform_id)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_aliases_platform
                ON identity_aliases(platform, platform_id)
            """)

            await conn.commit()
        except Exception as e:
            print(f"数据库迁移警告: {e}")
            # 迁移失败不阻止启动，只记录日志


# 全局数据库实例
database = Database()


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接的依赖注入函数"""
    return await database.connect()
