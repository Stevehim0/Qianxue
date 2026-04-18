"""数据库Schema定义和初始化模块。

本模块包含所有表的CREATE TABLE语句和初始化逻辑。
参考：Memory/技术选型文档.md §二 SQLite表结构设计
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def create_all_tables(db_manager) -> None:
    """创建所有数据库表。

    Args:
        db_manager: DatabaseManager实例

    Raises:
        sqlite3.Error: 建表失败时抛出异常
    """
    with db_manager.transaction() as cursor:
        # 1. 体验节点表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id TEXT PRIMARY KEY,
                L0_text TEXT,
                L0_embedding BLOB,
                L1_text TEXT,
                L2_text TEXT,
                L3_raw TEXT NOT NULL,
                emotion_category TEXT,
                emotion_intensity REAL,
                emotion_valence REAL,
                emotion_arousal REAL,
                emotion_target TEXT,
                context_focus TEXT,
                context_mood TEXT,
                context_time_of_day TEXT,
                context_silence_before TEXT,
                context_task TEXT,
                context_extra TEXT,
                importance REAL DEFAULT 0.5,
                twist_level TEXT DEFAULT 'none',
                consolidated INTEGER DEFAULT 0,
                L0_decayed REAL DEFAULT 1.0,
                L1_decayed REAL DEFAULT 1.0,
                L2_decayed REAL DEFAULT 1.0,
                L3_decayed REAL DEFAULT 1.0,
                distorted TEXT,
                source_type TEXT DEFAULT 'direct',
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL
            )
        """)
        _create_index(cursor, "experiences", "created_at", desc=True)
        _create_index(cursor, "experiences", "consolidated")
        # Performance optimization indexes (v6)
        _create_index(cursor, "experiences", "importance", desc=True)
        _create_index(cursor, "experiences", "source_type")

        # 2. 体验层边表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experience_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                decayed_weight REAL DEFAULT 1.0,
                emotion_driver TEXT,
                access_count INTEGER DEFAULT 0,
                dormant INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(from_id, to_id),
                FOREIGN KEY (from_id) REFERENCES experiences(id) ON DELETE CASCADE,
                FOREIGN KEY (to_id) REFERENCES experiences(id) ON DELETE CASCADE
            )
        """)
        _create_index(cursor, "experience_edges", "from_id")
        _create_index(cursor, "experience_edges", "to_id")
        _create_index(cursor, "experience_edges", "type")
        # Performance optimization indexes (v6)
        _create_index(cursor, "experience_edges", "decayed_weight", desc=True)

        # 3. 信息层实体表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                properties TEXT,
                embedding BLOB,
                emotion_timeline TEXT,
                emotion_current TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        _create_index(cursor, "entities", "name")
        _create_index(cursor, "entities", "type")

        # 4. 信息层关系边表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                embedding BLOB,
                confidence REAL DEFAULT 0.5,
                source TEXT,
                source_type TEXT,
                verified_at TEXT,
                verify_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(from_id, to_id),
                FOREIGN KEY (from_id) REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY (to_id) REFERENCES entities(id) ON DELETE CASCADE
            )
        """)
        _create_index(cursor, "entity_edges", "from_id")
        _create_index(cursor, "entity_edges", "to_id")
        _create_index(cursor, "entity_edges", "source_type")
        _create_index(cursor, "entity_edges", "confidence")

        # 5. 跨层边表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cross_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                context TEXT,
                weight REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                UNIQUE(from_id, to_id),
                FOREIGN KEY (from_id) REFERENCES experiences(id) ON DELETE CASCADE,
                FOREIGN KEY (to_id) REFERENCES entities(id) ON DELETE CASCADE
            )
        """)
        _create_index(cursor, "cross_edges", "from_id")
        _create_index(cursor, "cross_edges", "to_id")

        # 6. 核心层表（单行表）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS core (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                invariant_text TEXT NOT NULL DEFAULT '',
                stable_text TEXT NOT NULL DEFAULT '',
                malleable_text TEXT NOT NULL DEFAULT '',
                anchors TEXT,
                version INTEGER DEFAULT 1,
                last_modified TEXT,
                modification_log TEXT
            )
        """)

        # 7. 状态层表（单行表）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                mood_valence REAL DEFAULT 0.0,
                mood_arousal REAL DEFAULT 0.3,
                mood_label TEXT DEFAULT '平静',
                energy_value REAL DEFAULT 0.7,
                energy_label TEXT DEFAULT '正常',
                focus TEXT,
                confidence_value REAL DEFAULT 0.7,
                confidence_label TEXT DEFAULT '正常',
                updated_at TEXT
            )
        """)

        # 8. 个人档案表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS person_profiles (
                id TEXT PRIMARY KEY,
                memory_index TEXT,
                basic TEXT,
                interaction_style TEXT,
                preferences TEXT,
                last_updated TEXT,
                updated_by TEXT DEFAULT 'dream_ai',
                FOREIGN KEY (memory_index) REFERENCES entities(id) ON DELETE SET NULL
            )
        """)
        _create_index(cursor, "person_profiles", "memory_index")

        # 9. Schema版本表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version TEXT NOT NULL,
                updated_at TEXT,
                sql_script TEXT
            )
        """)

        # 10. 衰减配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decay_config (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                description TEXT,
                updated_at TEXT
            )
        """)

        # 记录初始版本（v3 - 包含decay_config表）
        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT OR ABORT INTO schema_version (id, version, updated_at)
            VALUES (1, 'v3', ?)
        """,
            (now,),
        )

        logger.info("All database tables created successfully")

    # 执行schema迁移（v3 -> v4 -> v5 -> v6 -> v7 -> v8 -> v9）
    migrate_to_v7(db_manager)
    migrate_to_v8(db_manager)
    migrate_to_v9(db_manager)
    migrate_to_v10(db_manager)
    migrate_to_v11(db_manager)


def _create_index(cursor, table: str, column: str, desc: bool = False) -> None:
    """创建索引（辅助函数）。

    Args:
        cursor: 数据库游标
        table: 表名
        column: 列名
        desc: 是否降序索引（用于ORDER BY ... DESC查询优化）
    """
    index_name = f"idx_{table}_{column}"
    order = "DESC" if desc else ""
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {table}({column} {order})
    """)


def get_current_schema_version(db_manager) -> str:
    """获取当前schema版本。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        版本字符串，如'v1'，未初始化返回'unknown'
    """
    try:
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version WHERE id = 1")
            row = cursor.fetchone()
            return row["version"] if row else "unknown"
    except Exception:
        return "unknown"


def migrate_add_consolidated_field(db_manager) -> bool:
    """迁移：添加consolidated字段到experiences表（v1 -> v2）。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或字段已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 检查字段是否已存在
            cursor.execute("PRAGMA table_info(experiences)")
            columns = [row["name"] for row in cursor.fetchall()]

            if "consolidated" in columns:
                logger.info("Field 'consolidated' already exists in experiences table")
                # 更新schema版本到v2（如果还不是）
                cursor.execute("UPDATE schema_version SET version = 'v2' WHERE id = 1")
                return True

            # 添加consolidated字段
            cursor.execute("""
                ALTER TABLE experiences
                ADD COLUMN consolidated INTEGER DEFAULT 0
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_experiences_consolidated
                ON experiences(consolidated)
            """)

            # 更新schema版本到v2
            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE schema_version
                SET version = 'v2', updated_at = ?
                WHERE id = 1
            """,
                (now,),
            )

            logger.info("Successfully migrated schema from v1 to v2 (added consolidated field)")
            return True

    except Exception as e:
        logger.error(f"Failed to migrate schema to v2: {e}")
        return False


def migrate_to_v2(db_manager) -> bool:
    """迁移数据库schema到v2版本。

    v2版本添加了consolidated字段到experiences表，用于跟踪巩固状态。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v2版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v2":
        logger.info("Schema already at v2, no migration needed")
        return True

    # 执行v1到v2的迁移
    return migrate_add_consolidated_field(db_manager)


def migrate_add_decay_config_table(db_manager) -> bool:
    """迁移：添加decay_config表（v2 -> v3）。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或表已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 检查表是否已存在
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='decay_config'
            """)
            table_exists = cursor.fetchone()

            if table_exists:
                logger.info("Table 'decay_config' already exists")
                # 更新schema版本到v3（如果还不是）
                cursor.execute("UPDATE schema_version SET version = 'v3' WHERE id = 1")
                return True

            # 创建decay_config表
            cursor.execute("""
                CREATE TABLE decay_config (
                    key TEXT PRIMARY KEY,
                    value REAL NOT NULL,
                    description TEXT,
                    updated_at TEXT
                )
            """)

            # 更新schema版本到v3
            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE schema_version
                SET version = 'v3', updated_at = ?
                WHERE id = 1
            """,
                (now,),
            )

            logger.info("Successfully migrated schema from v2 to v3 (added decay_config table)")
            return True

    except Exception as e:
        logger.error(f"Failed to migrate schema to v3: {e}")
        return False


def migrate_to_v3(db_manager) -> bool:
    """迁移数据库schema到v3版本。

    v3版本添加了decay_config表，用于存储衰减参数配置。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v3版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v3":
        logger.info("Schema already at v3, no migration needed")
        return True

    # 先确保是v2版本
    if current_version != "v2":
        migrate_to_v2(db_manager)

    # 执行v2到v3的迁移
    return migrate_add_decay_config_table(db_manager)


def migrate_add_distorted_field(db_manager) -> bool:
    """迁移：添加distorted字段到experiences表（v3 -> v4）。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或字段已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 检查字段是否已存在
            cursor.execute("PRAGMA table_info(experiences)")
            columns = [row["name"] for row in cursor.fetchall()]

            if "distorted" in columns:
                logger.info("Field 'distorted' already exists in experiences table")
                # 更新schema版本到v4（如果还不是）
                cursor.execute("UPDATE schema_version SET version = 'v4' WHERE id = 1")
                return True

            # 添加distorted字段
            cursor.execute("""
                ALTER TABLE experiences
                ADD COLUMN distorted TEXT
            """)

            # 更新schema版本到v4
            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE schema_version
                SET version = 'v4', updated_at = ?
                WHERE id = 1
            """,
                (now,),
            )

            logger.info("Successfully migrated schema from v3 to v4 (added distorted field)")
            return True

    except Exception as e:
        logger.error(f"Failed to migrate schema to v4: {e}")
        return False


def migrate_to_v4(db_manager) -> bool:
    """迁移数据库schema到v4版本。

    v4版本添加了distorted字段到experiences表，用于记录梦境扭曲审计追踪。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v4版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v4":
        logger.info("Schema already at v4, no migration needed")
        return True

    # 先确保是v3版本
    if current_version != "v3":
        migrate_to_v3(db_manager)

    # 执行v3到v4的迁移
    return migrate_add_distorted_field(db_manager)


def migrate_add_source_type_and_confidence(db_manager) -> bool:
    """迁移：添加source_type和confidence字段到experiences表（v4 -> v5）。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或字段已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 检查字段是否已存在
            cursor.execute("PRAGMA table_info(experiences)")
            columns = [row["name"] for row in cursor.fetchall()]

            fields_added = False

            # 添加source_type字段（如果不存在）
            if "source_type" not in columns:
                cursor.execute("""
                    ALTER TABLE experiences
                    ADD COLUMN source_type TEXT DEFAULT 'direct'
                """)
                logger.info("Added source_type field to experiences table")
                fields_added = True
            else:
                logger.info("Field 'source_type' already exists in experiences table")

            # 添加confidence字段（如果不存在）
            if "confidence" not in columns:
                cursor.execute("""
                    ALTER TABLE experiences
                    ADD COLUMN confidence REAL DEFAULT 1.0
                """)
                logger.info("Added confidence field to experiences table")
                fields_added = True
            else:
                logger.info("Field 'confidence' already exists in experiences table")

            # 更新schema版本到v5（如果有字段添加）
            if fields_added:
                now = datetime.now().isoformat()
                cursor.execute(
                    """
                    UPDATE schema_version
                    SET version = 'v5', updated_at = ?
                    WHERE id = 1
                """,
                    (now,),
                )
                logger.info(
                    "Successfully migrated schema from v4 to v5 (added source_type and confidence fields)"
                )
            else:
                # 如果字段已存在，确保版本是v5
                cursor.execute("UPDATE schema_version SET version = 'v5' WHERE id = 1")

            return True

    except Exception as e:
        logger.error(f"Failed to migrate schema to v5: {e}")
        return False


def migrate_to_v5(db_manager) -> bool:
    """迁移数据库schema到v5版本。

    v5版本添加了source_type和confidence字段到experiences表。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v5版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v5":
        logger.info("Schema already at v5, no migration needed")
        return True

    # 先确保是v4版本
    if current_version != "v4":
        migrate_to_v4(db_manager)

    # 执行v4到v5的迁移
    return migrate_add_source_type_and_confidence(db_manager)


def migrate_add_performance_indexes(db_manager) -> bool:
    """迁移：添加性能优化索引（v5 -> v6）。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或索引已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 更新schema版本到v6
            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE schema_version
                SET version = 'v6', updated_at = ?
                WHERE id = 1
            """,
                (now,),
            )

            logger.info("Successfully migrated schema from v5 to v6 (added performance indexes)")
            return True

    except Exception as e:
        logger.error(f"Failed to migrate schema to v6: {e}")
        return False


def migrate_to_v6(db_manager) -> bool:
    """迁移数据库schema到v6版本。

    v6版本添加了性能优化索引，加速常见查询。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v6版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v6":
        logger.info("Schema already at v6, no migration needed")
        return True

    # 先确保是v5版本
    if current_version != "v5":
        migrate_to_v5(db_manager)

    # 执行v5到v6的迁移
    return migrate_add_performance_indexes(db_manager)


def migrate_add_entity_metadata_fields(db_manager) -> bool:
    """迁移：添加source和confidence字段到entities表（v6 -> v7）。

    实现D-02决策（元数据和业务属性分离），将source和confidence从properties
    JSON字段提升到entities表的独立列。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或字段已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 检查字段是否已存在
            cursor.execute("PRAGMA table_info(entities)")
            columns = [row["name"] for row in cursor.fetchall()]

            fields_added = []

            # 添加source字段（如果不存在）
            if "source" not in columns:
                cursor.execute("""
                    ALTER TABLE entities
                    ADD COLUMN source TEXT
                """)
                fields_added.append("source")
                logger.info("Added 'source' field to entities table")
            else:
                logger.info("Field 'source' already exists in entities table")

            # 添加confidence字段（如果不存在）
            if "confidence" not in columns:
                cursor.execute("""
                    ALTER TABLE entities
                    ADD COLUMN confidence REAL DEFAULT 0.5
                """)
                fields_added.append("confidence")
                logger.info("Added 'confidence' field to entities table")
            else:
                logger.info("Field 'confidence' already exists in entities table")

            # 更新schema版本到v7
            if fields_added:
                now = datetime.now().isoformat()
                cursor.execute(
                    """
                    UPDATE schema_version
                    SET version = 'v7', updated_at = ?
                    WHERE id = 1
                """,
                    (now,),
                )
                logger.info(f"Schema migrated to v7, added fields: {', '.join(fields_added)}")
            else:
                # 如果字段都已存在，确保版本是v7
                cursor.execute("UPDATE schema_version SET version = 'v7' WHERE id = 1")
                logger.info("Schema already at v7, no new fields added")

            return True

    except Exception as e:
        logger.error(f"Failed to add entity metadata fields: {e}")
        return False


def migrate_to_v7(db_manager) -> bool:
    """迁移数据库schema到v7版本。

    v7版本添加了实体元数据字段（source和confidence），实现元数据和业务属性分离。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v7版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v7":
        logger.info("Schema already at v7, no migration needed")
        return True

    # 先确保是v6版本
    if current_version != "v6":
        migrate_to_v6(db_manager)

    # 执行v6到v7的迁移
    return migrate_add_entity_metadata_fields(db_manager)


def migrate_add_stm_tables(db_manager) -> bool:
    """迁移：添加短期记忆（STM）相关表（v7 -> v8）。

    新增 stm_events（事件流）和 stm_compressed（压缩摘要）表，
    用于实现跨会话全局感知。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或表已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            # 检查表是否已存在
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='stm_events'
            """)
            if cursor.fetchone():
                logger.info("Table 'stm_events' already exists")
                cursor.execute("UPDATE schema_version SET version = 'v8' WHERE id = 1")
                return True

            # 创建 stm_events 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stm_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    user_id TEXT,
                    summary TEXT NOT NULL,
                    detail TEXT,
                    importance REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL
                )
            """)
            _create_index(cursor, "stm_events", "created_at", desc=True)
            _create_index(cursor, "stm_events", "group_id")

            # 创建 stm_compressed 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stm_compressed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    time_range_start TEXT NOT NULL,
                    time_range_end TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            _create_index(cursor, "stm_compressed", "created_at", desc=True)

            # 更新 schema 版本
            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE schema_version
                SET version = 'v8', updated_at = ?
                WHERE id = 1
            """,
                (now,),
            )

            logger.info("Successfully migrated schema from v7 to v8 (added STM tables)")
            return True

    except Exception as e:
        logger.error(f"Failed to add STM tables: {e}")
        return False


def migrate_to_v8(db_manager) -> bool:
    """迁移数据库schema到v8版本。

    v8版本添加了短期记忆（STM）相关表，用于跨会话全局感知。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v8版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v8":
        logger.info("Schema already at v8, no migration needed")
        return True

    # 先确保是v7版本
    if current_version != "v7":
        migrate_to_v7(db_manager)

    # 执行v7到v8的迁移
    return migrate_add_stm_tables(db_manager)


def migrate_add_dormant_field(db_manager) -> bool:
    """迁移：添加dormant字段到experience_edges表（v8 -> v9）。

    dormant用于标记边的休眠状态（0=活跃，1=休眠），
    巩固层的隐性边发现等功能依赖此字段。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或字段已存在，False如果失败
    """
    try:
        with db_manager.transaction() as cursor:
            cursor.execute("PRAGMA table_info(experience_edges)")
            columns = [row["name"] for row in cursor.fetchall()]

            if "dormant" in columns:
                logger.info("Field 'dormant' already exists in experience_edges table")
                cursor.execute("UPDATE schema_version SET version = 'v9' WHERE id = 1")
                return True

            cursor.execute("""
                ALTER TABLE experience_edges
                ADD COLUMN dormant INTEGER DEFAULT 0
            """)

            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE schema_version
                SET version = 'v9', updated_at = ?
                WHERE id = 1
            """,
                (now,),
            )

            logger.info("Successfully migrated schema from v8 to v9 (added dormant field to experience_edges)")
            return True

    except Exception as e:
        logger.error(f"Failed to migrate schema to v9: {e}")
        return False


def migrate_to_v9(db_manager) -> bool:
    """迁移数据库schema到v9版本。

    v9版本添加了dormant字段到experience_edges表，用于标记边的休眠状态。

    Args:
        db_manager: DatabaseManager实例

    Returns:
        True如果迁移成功或已经是v9版本，False如果失败
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "unknown":
        logger.warning("Unknown schema version, attempting migration anyway")
    elif current_version == "v9":
        logger.info("Schema already at v9, no migration needed")
        return True

    # 先确保是v8版本
    if current_version != "v8":
        migrate_to_v8(db_manager)

    # 执行v8到v9的迁移
    return migrate_add_dormant_field(db_manager)


def _rebuild_table_with_unique(db_manager, table_name: str, create_sql: str, unique_cols: list) -> bool:
    """重建表以添加 UNIQUE 约束，保留数据（去重取最新）。

    SQLite 不支持 ALTER TABLE ADD CONSTRAINT，需要重建表。
    步骤：创建临时表 -> 拷贝去重数据 -> 删旧表 -> 重命名。

    Args:
        db_manager: DatabaseManager实例
        table_name: 表名
        create_sql: 新建表的 CREATE TABLE 语句（含 UNIQUE）
        unique_cols: 用于去重的列名列表

    Returns:
        True如果成功
    """
    tmp_name = f"_tmp_{table_name}"
    unique_expr = ", ".join(unique_cols)

    try:
        with db_manager.transaction() as cursor:
            # 统计旧表数据
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            old_count = cursor.fetchone()[0]

            # 创建临时表（新结构）
            cursor.execute(create_sql.replace(f" {table_name} ", f" {tmp_name} "))

            # 拷贝数据（去重：同 unique key 保留 id 最大的那条）
            cols_sql = ", ".join(
                c[1] for c in cursor.execute(f"PRAGMA table_info({tmp_name})").fetchall()
            )
            cursor.execute(f"""
                INSERT INTO {tmp_name} ({cols_sql})
                SELECT {cols_sql} FROM {table_name}
                WHERE id IN (
                    SELECT MAX(id) FROM {table_name}
                    GROUP BY {unique_expr}
                )
            """)

            cursor.execute(f"SELECT COUNT(*) FROM {tmp_name}")
            new_count = cursor.fetchone()[0]
            deduped = old_count - new_count

            # 替换旧表
            cursor.execute(f"DROP TABLE {table_name}")
            cursor.execute(f"ALTER TABLE {tmp_name} RENAME TO {table_name}")

            logger.info(
                f"Rebuilt {table_name}: {old_count} -> {new_count} rows "
                f"(removed {deduped} duplicates), added UNIQUE({unique_expr})"
            )
        return True

    except Exception as e:
        logger.error(f"Failed to rebuild {table_name}: {e}")
        return False


def migrate_add_unique_constraints(db_manager) -> bool:
    """迁移：给三张边表加 UNIQUE 约束（v9 -> v10）。

    防止巩固层重复创建相同的边。
    """
    results = []

    # experience_edges: UNIQUE(from_id, to_id)
    results.append(_rebuild_table_with_unique(
        db_manager, "experience_edges",
        """CREATE TABLE experience_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id TEXT NOT NULL,
            to_id TEXT NOT NULL,
            type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            decayed_weight REAL DEFAULT 1.0,
            emotion_driver TEXT,
            access_count INTEGER DEFAULT 0,
            dormant INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(from_id, to_id),
            FOREIGN KEY (from_id) REFERENCES experiences(id) ON DELETE CASCADE,
            FOREIGN KEY (to_id) REFERENCES experiences(id) ON DELETE CASCADE
        )""",
        ["from_id", "to_id"],
    ))

    # 重建索引
    with db_manager.transaction() as cursor:
        _create_index(cursor, "experience_edges", "from_id")
        _create_index(cursor, "experience_edges", "to_id")
        _create_index(cursor, "experience_edges", "type")
        _create_index(cursor, "experience_edges", "decayed_weight", desc=True)

    # entity_edges: UNIQUE(from_id, to_id)
    results.append(_rebuild_table_with_unique(
        db_manager, "entity_edges",
        """CREATE TABLE entity_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id TEXT NOT NULL,
            to_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            embedding BLOB,
            confidence REAL DEFAULT 0.5,
            source TEXT,
            source_type TEXT,
            verified_at TEXT,
            verify_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(from_id, to_id),
            FOREIGN KEY (from_id) REFERENCES entities(id) ON DELETE CASCADE,
            FOREIGN KEY (to_id) REFERENCES entities(id) ON DELETE CASCADE
        )""",
        ["from_id", "to_id"],
    ))

    with db_manager.transaction() as cursor:
        _create_index(cursor, "entity_edges", "from_id")
        _create_index(cursor, "entity_edges", "to_id")
        _create_index(cursor, "entity_edges", "source_type")
        _create_index(cursor, "entity_edges", "confidence")

    # cross_edges: UNIQUE(from_id, to_id)
    results.append(_rebuild_table_with_unique(
        db_manager, "cross_edges",
        """CREATE TABLE cross_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id TEXT NOT NULL,
            to_id TEXT NOT NULL,
            context TEXT,
            weight REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            UNIQUE(from_id, to_id),
            FOREIGN KEY (from_id) REFERENCES experiences(id) ON DELETE CASCADE,
            FOREIGN KEY (to_id) REFERENCES entities(id) ON DELETE CASCADE
        )""",
        ["from_id", "to_id"],
    ))

    with db_manager.transaction() as cursor:
        _create_index(cursor, "cross_edges", "from_id")
        _create_index(cursor, "cross_edges", "to_id")

    if all(results):
        now = datetime.now().isoformat()
        with db_manager.transaction() as cursor:
            cursor.execute(
                "UPDATE schema_version SET version = 'v10', updated_at = ? WHERE id = 1",
                (now,),
            )
        logger.info("Successfully migrated schema from v9 to v10 (UNIQUE constraints on edge tables)")
        return True

    logger.error("Failed to add UNIQUE constraints to some edge tables")
    return False


def migrate_to_v10(db_manager) -> bool:
    """迁移数据库schema到v10版本。

    v10版本给三张边表添加UNIQUE约束，防止巩固层重复创建边。
    """
    current_version = get_current_schema_version(db_manager)

    if current_version == "v10":
        logger.info("Schema already at v10, no migration needed")
        return True

    # 先确保是v9版本
    if current_version != "v9":
        migrate_to_v9(db_manager)

    return migrate_add_unique_constraints(db_manager)


def migrate_add_pending_facts(db_manager) -> bool:
    """迁移：添加 profile_pending_facts 表（v10 -> v11）。"""
    try:
        with db_manager.transaction() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='profile_pending_facts'
            """)
            if cursor.fetchone():
                logger.info("Table 'profile_pending_facts' already exists")
                cursor.execute("UPDATE schema_version SET version = 'v11' WHERE id = 1")
                return True

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profile_pending_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_name TEXT NOT NULL,
                    fact_text TEXT NOT NULL,
                    source_type TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            _create_index(cursor, "profile_pending_facts", "entity_name")
            _create_index(cursor, "profile_pending_facts", "created_at", desc=True)

            now = datetime.now().isoformat()
            cursor.execute(
                "UPDATE schema_version SET version = 'v11', updated_at = ? WHERE id = 1",
                (now,),
            )
            logger.info("Successfully migrated schema from v10 to v11 (added profile_pending_facts)")
            return True
    except Exception as e:
        logger.error(f"Failed to migrate schema to v11: {e}")
        return False


def migrate_to_v11(db_manager) -> bool:
    """迁移数据库schema到v11版本。

    v11版本添加了 profile_pending_facts 表，用于从日常对话中积累人物信息。
    """
    current_version = get_current_schema_version(db_manager)
    if current_version == "v11":
        logger.info("Schema already at v11, no migration needed")
        return True
    if current_version != "v10":
        migrate_to_v10(db_manager)
    return migrate_add_pending_facts(db_manager)
