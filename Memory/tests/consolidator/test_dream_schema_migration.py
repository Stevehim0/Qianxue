"""
测试Schema v4迁移：添加distorted字段到experiences表

Tests:
- migrate_to_v4() creates distorted field in experiences table
- migrate_to_v4() is idempotent (can run multiple times without error)
- distorted field is TEXT type (stores JSON)
- Schema version upgrades from v3 to v4
- Existing data in experiences table is preserved after migration
- get_schema_version() returns 4 after migration
"""

import pytest
import sqlite3
from Memory.storage.schema import create_all_tables, get_current_schema_version, migrate_to_v4


def test_migrate_to_v4_creates_distorted_field(memory_db):
    """验证migrate_to_v4()在experiences表中创建distorted字段"""
    # Start with v3 schema
    assert get_current_schema_version(memory_db) == "v3"

    # Run migration
    success = migrate_to_v4(memory_db)
    assert success is True

    # Verify distorted field exists
    cursor = memory_db.execute_query("PRAGMA table_info(experiences)")
    columns = [row["name"] for row in cursor.fetchall()]
    assert "distorted" in columns


def test_migrate_to_v4_is_idempotent(memory_db):
    """验证migrate_to_v4()是幂等的（多次运行不报错）"""
    # First migration
    success1 = migrate_to_v4(memory_db)
    assert success1 is True

    # Second migration should also succeed
    success2 = migrate_to_v4(memory_db)
    assert success2 is True

    # Schema version should still be v4
    assert get_current_schema_version(memory_db) == "v4"


def test_distorted_field_is_text_type(memory_db):
    """验证distorted字段是TEXT类型（存储JSON）"""
    # Run migration
    migrate_to_v4(memory_db)

    # Check field type
    cursor = memory_db.execute_query("PRAGMA table_info(experiences)")
    columns_info = {row["name"]: row["type"] for row in cursor.fetchall()}
    assert columns_info["distorted"] == "TEXT"


def test_schema_version_upgrades_to_v4(memory_db):
    """验证schema版本从v3升级到v4"""
    # Start at v3
    assert get_current_schema_version(memory_db) == "v3"

    # Migrate to v4
    migrate_to_v4(memory_db)

    # Check version
    version = get_current_schema_version(memory_db)
    assert version == "v4"


def test_existing_data_preserved_after_migration(memory_db, test_data):
    """验证迁移后现有数据保持不变"""
    from Memory.storage.experience_store import ExperienceStore, Experience

    # Insert test data before migration
    store = ExperienceStore(db_manager=memory_db)
    exp = Experience(
        id="test_exp_001", L3_raw="Test content", L0_text="Test summary", importance=0.6
    )
    store.create(exp)

    # Migrate to v4
    migrate_to_v4(memory_db)

    # Verify data still exists
    retrieved = store.get("test_exp_001")
    assert retrieved is not None
    assert retrieved.L3_raw == "Test content"
    assert retrieved.L0_text == "Test summary"
    assert retrieved.importance == 0.6


def test_get_schema_version_returns_4_after_migration(memory_db):
    """验证get_schema_version()在迁移后返回4"""
    # Before migration
    assert get_current_schema_version(memory_db) == "v3"

    # Migrate
    migrate_to_v4(memory_db)

    # After migration
    version = get_current_schema_version(memory_db)
    assert version == "v4"
