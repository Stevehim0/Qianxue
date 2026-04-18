"""
测试ExperienceStore对distorted字段的支持

Tests:
- Experience dataclass has distorted field (Optional[str])
- create() method accepts and stores distorted parameter
- _row_to_experience() parses distorted field from database
- update_distorted() method updates L0/L1/L2 and distorted atomically
- update_distorted() rejects attempts to modify L3_raw (raises ValueError)
- Backward compatibility - reading experiences without distorted field works (returns None)
"""

import pytest
import json
from Memory.storage.experience_store import ExperienceStore, Experience


def test_experience_dataclass_has_distorted_field():
    """验证Experience数据类包含distorted字段"""
    exp = Experience(id="test_001", L3_raw="Test content")

    # distorted field should exist and default to None
    assert hasattr(exp, "distorted")
    assert exp.distorted is None


def test_create_stores_distorted_parameter(memory_db):
    """验证create()方法接受并存储distorted参数"""
    store = ExperienceStore(db_manager=memory_db)

    # Create experience with distorted field
    distorted_json = json.dumps(
        {"type": "dream_distortion", "timestamp": "2026-04-02T00:00:00Z"}, ensure_ascii=False
    )

    exp = Experience(id="test_001", L3_raw="Test content", distorted=distorted_json)

    store.create(exp)

    # Retrieve and verify
    retrieved = store.get("test_001")
    assert retrieved is not None
    assert retrieved.distorted == distorted_json


def test_row_to_experience_parses_distorted_field(memory_db):
    """验证_row_to_experience()从数据库解析distorted字段"""
    store = ExperienceStore(db_manager=memory_db)

    # Create experience with distorted field
    distorted_data = {
        "type": "dream_distortion",
        "timestamp": "2026-04-02T00:00:00Z",
        "original_values": {"L0_text": "Original summary"},
        "distorted_values": {"L0_text": "Distorted summary"},
    }
    distorted_json = json.dumps(distorted_data, ensure_ascii=False)

    exp = Experience(id="test_002", L3_raw="Test content", distorted=distorted_json)
    store.create(exp)

    # Parse back from database
    retrieved = store.get("test_002")
    assert retrieved.distorted is not None

    # Verify JSON is valid
    parsed = json.loads(retrieved.distorted)
    assert parsed["type"] == "dream_distortion"
    assert parsed["original_values"]["L0_text"] == "Original summary"


def test_update_distorted_method_exists(memory_db):
    """验证update_distorted()方法存在"""
    store = ExperienceStore(db_manager=memory_db)

    # Check method exists
    assert hasattr(store, "update_distorted")
    assert callable(store.update_distorted)


def test_update_distorted_updates_L0_L1_L2_and_distorted(memory_db):
    """验证update_distorted()方法更新L0/L1/L2和distorted字段"""
    store = ExperienceStore(db_manager=memory_db)

    # Create initial experience
    exp = Experience(
        id="test_003",
        L3_raw="Original L3",
        L0_text="Original L0",
        L1_text="Original L1",
        L2_text="Original L2",
    )
    store.create(exp)

    # Update with distorted values
    distorted_json = json.dumps(
        {
            "type": "dream_distortion",
            "timestamp": "2026-04-02T00:00:00Z",
            "original_values": {
                "L0_text": "Original L0",
                "L1_text": "Original L1",
                "L2_text": "Original L2",
            },
            "distorted_values": {
                "L0_text": "Distorted L0",
                "L1_text": "Distorted L1",
                "L2_text": "Distorted L2",
            },
        },
        ensure_ascii=False,
    )

    success = store.update_distorted(
        "test_003",
        L0_text="Distorted L0",
        L1_text="Distorted L1",
        L2_text="Distorted L2",
        distorted=distorted_json,
    )

    assert success is True

    # Verify updates
    retrieved = store.get("test_003")
    assert retrieved.L0_text == "Distorted L0"
    assert retrieved.L1_text == "Distorted L1"
    assert retrieved.L2_text == "Distorted L2"
    assert retrieved.L3_raw == "Original L3"  # L3 unchanged
    assert retrieved.distorted == distorted_json


def test_update_distorted_rejects_L3_modification(memory_db):
    """验证update_distorted()拒绝修改L3_raw（抛出ValueError）"""
    store = ExperienceStore(db_manager=memory_db)

    # Create initial experience
    exp = Experience(id="test_004", L3_raw="Original L3", L0_text="Original L0")
    store.create(exp)

    # Try to modify L3 - should raise ValueError
    with pytest.raises(ValueError, match="Cannot modify L3_raw"):
        store.update_distorted(
            "test_004", L3_raw="Modified L3", L0_text="Modified L0"  # This should be rejected
        )


def test_backward_compatibility_reading_without_distorted(memory_db):
    """验证向后兼容性 - 读取没有distorted字段的经验数据返回None"""
    store = ExperienceStore(db_manager=memory_db)

    # Manually insert a row without distorted field (simulate old data)
    with memory_db.transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO experiences (id, L3_raw, L0_text, created_at)
            VALUES (?, ?, ?, ?)
        """,
            ("old_001", "Old L3", "Old L0", "2026-04-01T00:00:00Z"),
        )

    # Read back - distorted should be None
    retrieved = store.get("old_001")
    assert retrieved is not None
    assert retrieved.distorted is None
    assert retrieved.L0_text == "Old L0"
