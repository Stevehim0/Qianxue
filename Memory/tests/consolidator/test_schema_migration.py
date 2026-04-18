"""测试Schema v2到v3的迁移功能。

测试覆盖：
- 幂等性：v3数据库上重复执行不报错
- 字段添加：experiences表添加4个衰减字段
- 字段添加：experience_edges表添加dormant字段
- 表创建：decay_config表创建并插入默认参数
- 版本升级：schema_version表更新到v3
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from Memory.storage.schema import migrate_to_v3, get_current_schema_version, create_all_tables
from Memory.storage.database import DatabaseManager


@pytest.fixture
def temp_db():
    """创建临时数据库实例。"""
    # 创建临时数据库文件
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # 初始化DatabaseManager
    db_manager = DatabaseManager(db_path=db_path)

    yield db_manager

    # 清理
    os.unlink(db_path)


@pytest.fixture
def v2_database(temp_db):
    """创建v2版本的数据库（不含v3字段）。"""
    # 创建v2 schema
    create_all_tables(temp_db)

    # 确保版本是v2
    with temp_db.transaction() as cursor:
        cursor.execute("UPDATE schema_version SET version = 'v2' WHERE id = 1")

    # 验证初始状态
    version = get_current_schema_version(temp_db)
    assert version == "v2"

    return temp_db


@pytest.fixture
def v3_database(v2_database):
    """创建v3版本的数据库（已执行迁移）。"""
    migrate_to_v3(v2_database)
    return v2_database


class TestSchemaMigrationV3:
    """测试Schema v3迁移功能。"""

    def test_migrate_to_v3_idempotent(self, v3_database):
        """测试1: migrate_to_v3在v3数据库上幂等执行（不报错，返回True）。"""
        # 第一次迁移应该成功
        result1 = migrate_to_v3(v3_database)
        assert result1 is True

        # 第二次迁移也应该成功（幂等性）
        result2 = migrate_to_v3(v3_database)
        assert result2 is True

        # 版本应该仍然是v3
        version = get_current_schema_version(v3_database)
        assert version == "v3"

    def test_migrate_to_v3_adds_experience_fields(self, v2_database):
        """测试2: migrate_to_v3在v2数据库上成功添加4个衰减字段。"""
        # 执行迁移
        result = migrate_to_v3(v2_database)
        assert result is True

        # 检查字段是否添加成功
        with v2_database.transaction() as cursor:
            cursor.execute("PRAGMA table_info(experiences)")
            columns = {row["name"] for row in cursor.fetchall()}

            # 验证4个衰减字段存在
            assert "L0_decayed" in columns
            assert "L1_decayed" in columns
            assert "L2_decayed" in columns
            assert "L3_decayed" in columns

            # 验证字段类型和默认值
            cursor.execute(
                "SELECT L0_decayed, L1_decayed, L2_decayed, L3_decayed FROM experiences LIMIT 1"
            )
            # 如果没有数据，插入测试行验证默认值
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO experiences (
                        id, L3_raw, L0_decayed, L1_decayed, L2_decayed, L3_decayed, created_at
                    ) VALUES ('test_001', 'test', DEFAULT, DEFAULT, DEFAULT, DEFAULT, datetime('now'))
                """)
                cursor.execute(
                    "SELECT L0_decayed, L1_decayed, L2_decayed, L3_decayed FROM experiences WHERE id = 'test_001'"
                )
                row = cursor.fetchone()
                assert row["L0_decayed"] == 1.0
                assert row["L1_decayed"] == 1.0
                assert row["L2_decayed"] == 1.0
                assert row["L3_decayed"] == 1.0

    def test_migrate_to_v3_adds_dormant_field(self, v2_database):
        """测试3: migrate_to_v3在experience_edges表添加dormant字段。"""
        # 执行迁移
        result = migrate_to_v3(v2_database)
        assert result is True

        # 检查字段是否添加成功
        with v2_database.transaction() as cursor:
            cursor.execute("PRAGMA table_info(experience_edges)")
            columns = {row["name"] for row in cursor.fetchall()}

            # 验证dormant字段存在
            assert "dormant" in columns

            # 验证默认值
            cursor.execute("SELECT dormant FROM experience_edges LIMIT 1")
            # 如果没有数据，插入测试行验证默认值
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO experience_edges (from_id, to_id, type, dormant, created_at)
                    VALUES ('exp_001', 'exp_002', 'temporal', DEFAULT, datetime('now'))
                """)
                cursor.execute("SELECT dormant FROM experience_edges WHERE from_id = 'exp_001'")
                row = cursor.fetchone()
                assert row["dormant"] == 0

    def test_migrate_to_v3_creates_decay_config_table(self, v2_database):
        """测试4: migrate_to_v3创建decay_config表并插入默认参数。"""
        # 执行迁移
        result = migrate_to_v3(v2_database)
        assert result is True

        # 检查表是否创建成功
        with v2_database.transaction() as cursor:
            # 验证表存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='decay_config'"
            )
            assert cursor.fetchone() is not None

            # 验证表结构
            cursor.execute("PRAGMA table_info(decay_config)")
            columns = {row["name"] for row in cursor.fetchall()}
            assert "key" in columns
            assert "value" in columns
            assert "description" in columns
            assert "updated_at" in columns

            # 验证默认参数插入
            cursor.execute("SELECT COUNT(*) FROM decay_config")
            count = cursor.fetchone()[0]
            assert count == 11  # 应该有11个默认参数

            # 验证关键参数存在
            cursor.execute("SELECT value FROM decay_config WHERE key = 'lambda_L0'")
            assert cursor.fetchone()["value"] == 0.01

            cursor.execute("SELECT value FROM decay_config WHERE key = 'lambda_L1'")
            assert cursor.fetchone()["value"] == 0.02

            cursor.execute("SELECT value FROM decay_config WHERE key = 'lambda_L2'")
            assert cursor.fetchone()["value"] == 0.03

            cursor.execute("SELECT value FROM decay_config WHERE key = 'lambda_L3'")
            assert cursor.fetchone()["value"] == 0.05

            cursor.execute("SELECT value FROM decay_config WHERE key = 'dormancy_threshold'")
            assert cursor.fetchone()["value"] == 0.05

    def test_migrate_to_v3_upgrades_schema_version(self, v2_database):
        """测试5: migrate_to_v3更新schema版本到v3。"""
        # 验证初始版本是v2
        version_before = get_current_schema_version(v2_database)
        assert version_before == "v2"

        # 执行迁移
        result = migrate_to_v3(v2_database)
        assert result is True

        # 验证版本已升级到v3
        version_after = get_current_schema_version(v2_database)
        assert version_after == "v3"

    def test_migrate_to_v3_field_existence_check(self, v3_database):
        """测试6: migrate_to_v3检查字段存在性，避免重复添加。"""
        # 验证字段已存在
        with v3_database.transaction() as cursor:
            cursor.execute("PRAGMA table_info(experiences)")
            columns = {row["name"] for row in cursor.fetchall()}
            assert "L0_decayed" in columns
            assert "L1_decayed" in columns
            assert "L2_decayed" in columns
            assert "L3_decayed" in columns

        # 再次执行迁移（不应该报错）
        result = migrate_to_v3(v3_database)
        assert result is True

        # 验证字段没有重复添加（列数应该保持不变）
        with v3_database.transaction() as cursor:
            cursor.execute("PRAGMA table_info(experiences)")
            columns_after = cursor.fetchall()
            # 确保列数合理（不会因为重复执行而增加）
            assert len(columns_after) < 50  # 防御性检查


class TestSchemaMigrationV3ErrorHandling:
    """测试Schema v3迁移的错误处理。"""

    def test_migrate_to_v3_handles_unknown_version(self, temp_db):
        """测试: migrate_to_v3处理未知版本时仍然尝试迁移。"""
        # 创建一个空的数据库（没有schema_version表）
        # 执行迁移应该返回True或False，但不应该崩溃
        result = migrate_to_v3(temp_db)
        # 结果可能是True（迁移成功）或False（迁移失败），但不应抛出异常
        assert isinstance(result, bool)

    def test_migrate_to_v3_preserves_existing_data(self, v2_database):
        """测试: migrate_to_v3保留现有数据不被破坏。"""
        # 插入测试数据
        with v2_database.transaction() as cursor:
            cursor.execute("""
                INSERT INTO experiences (id, L3_raw, importance, created_at)
                VALUES ('test_preserve', 'original data', 0.8, datetime('now'))
            """)

        # 执行迁移
        result = migrate_to_v3(v2_database)
        assert result is True

        # 验证数据仍然存在
        with v2_database.transaction() as cursor:
            cursor.execute("SELECT L3_raw, importance FROM experiences WHERE id = 'test_preserve'")
            row = cursor.fetchone()
            assert row["L3_raw"] == "original data"
            assert row["importance"] == 0.8
