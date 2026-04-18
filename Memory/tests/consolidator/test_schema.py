"""巩固层Schema迁移测试。

测试 experiences 表 consolidated 字段的迁移逻辑。
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from Memory.storage.database import DatabaseManager
from Memory.storage.schema import (
    create_all_tables,
    get_current_schema_version,
    migrate_add_consolidated_field,
)


class TestConsolidatedFieldMigration:
    """测试 consolidated 字段的迁移。"""

    def test_consolidated_field_exists_in_new_db(self):
        """测试新创建的数据库包含 consolidated 字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))

            # 创建所有表
            create_all_tables(db_manager)

            # 检查字段是否存在
            with db_manager.transaction() as cursor:
                cursor.execute("PRAGMA table_info(experiences)")
                columns = {row["name"]: row for row in cursor.fetchall()}

                assert "consolidated" in columns
                assert columns["consolidated"]["type"] == "INTEGER"
                # 检查默认值（SQLite的PRAGMA不直接显示默认值，但可以通过CREATE TABLE语句验证）

    def test_consolidated_field_default_value(self):
        """测试 consolidated 字段默认值为 0。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))

            # 创建所有表
            create_all_tables(db_manager)

            # 插入一条记录（不指定consolidated字段）
            with db_manager.transaction() as cursor:
                cursor.execute("""
                    INSERT INTO experiences (id, L3_raw, created_at)
                    VALUES ('test_id', 'test content', '2026-01-01T00:00:00')
                """)
                cursor.execute("SELECT consolidated FROM experiences WHERE id = 'test_id'")
                row = cursor.fetchone()
                assert row["consolidated"] == 0

    def test_schema_version_is_v2(self):
        """测试 schema_version 记录为 v2。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))

            # 创建所有表
            create_all_tables(db_manager)

            # 检查版本
            version = get_current_schema_version(db_manager)
            assert version == "v2"

    def test_migration_adds_consolidated_to_v1_database(self):
        """测试迁移函数可以给 v1 数据库添加 consolidated 字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))

            # 手动创建 v1 数据库（不含 consolidated 字段）
            with db_manager.transaction() as cursor:
                # 创建 experiences 表（v1版本）
                cursor.execute("""
                    CREATE TABLE experiences (
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
                        created_at TEXT NOT NULL
                    )
                """)

                # 创建 schema_version 表
                cursor.execute("""
                    CREATE TABLE schema_version (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        version TEXT NOT NULL,
                        updated_at TEXT,
                        sql_script TEXT
                    )
                """)

                # 记录 v1 版本
                cursor.execute("""
                    INSERT INTO schema_version (id, version, updated_at)
                    VALUES (1, 'v1', '2026-01-01T00:00:00')
                """)

                # 插入测试数据
                cursor.execute("""
                    INSERT INTO experiences (id, L3_raw, created_at)
                    VALUES ('test_id', 'test content', '2026-01-01T00:00:00')
                """)

            # 验证 v1 数据库没有 consolidated 字段
            with db_manager.transaction() as cursor:
                cursor.execute("PRAGMA table_info(experiences)")
                columns = [row["name"] for row in cursor.fetchall()]
                assert "consolidated" not in columns

            # 执行迁移
            success = migrate_add_consolidated_field(db_manager)
            assert success is True

            # 验证字段已添加
            with db_manager.transaction() as cursor:
                cursor.execute("PRAGMA table_info(experiences)")
                columns = [row["name"] for row in cursor.fetchall()]
                assert "consolidated" in columns

                # 验证现有记录的 consolidated 默认值为 0
                cursor.execute("SELECT consolidated FROM experiences WHERE id = 'test_id'")
                row = cursor.fetchone()
                assert row["consolidated"] == 0

                # 验证新记录默认值为 0
                cursor.execute("""
                    INSERT INTO experiences (id, L3_raw, created_at)
                    VALUES ('test_id_2', 'test content 2', '2026-01-01T00:00:00')
                """)
                cursor.execute("SELECT consolidated FROM experiences WHERE id = 'test_id_2'")
                row = cursor.fetchone()
                assert row["consolidated"] == 0

    def test_migration_idempotent(self):
        """测试迁移函数是幂等的（多次调用不会失败）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_manager = DatabaseManager(db_path=str(db_path))

            # 创建 v1 数据库
            with db_manager.transaction() as cursor:
                cursor.execute("""
                    CREATE TABLE experiences (
                        id TEXT PRIMARY KEY,
                        L3_raw TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE schema_version (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        version TEXT NOT NULL,
                        updated_at TEXT
                    )
                """)
                cursor.execute("INSERT INTO schema_version (id, version) VALUES (1, 'v1')")

            # 第一次迁移
            success1 = migrate_add_consolidated_field(db_manager)
            assert success1 is True

            # 第二次迁移（应该成功，不报错）
            success2 = migrate_add_consolidated_field(db_manager)
            assert success2 is True

            # 验证字段只存在一次
            with db_manager.transaction() as cursor:
                cursor.execute("PRAGMA table_info(experiences)")
                columns = [row["name"] for row in cursor.fetchall()]
                # 统计 consolidated 字段出现次数（应该是1）
                consolidated_count = columns.count("consolidated")
                assert consolidated_count == 1
