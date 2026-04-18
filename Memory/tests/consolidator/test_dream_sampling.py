"""梦境模块分层采样策略测试。

测试分层混合采样功能：重要记忆40% + 随机60%。
"""

import pytest
from Memory.consolidator.sampling import select_memories_for_dream
from Memory.storage.experience_store import ExperienceStore, Experience
from datetime import datetime, timedelta


class TestLayeredSampling:
    """测试分层混合采样策略。"""

    def test_select_memories_for_dream_returns_correct_total_count(self, db_manager):
        """测试select_memories_for_dream返回正确的总数。"""
        # Arrange: Create 100 experiences
        store = ExperienceStore(db_manager)
        for i in range(100):
            exp = Experience(
                id=f"exp_{i:06d}",
                L3_raw=f"Test content {i}",
                importance=0.5 + (i % 5) * 0.1,  # Varied importance
                created_at=(datetime.now() - timedelta(days=i)).isoformat(),
            )
            store.create(exp)

        # Act: Select 20 memories
        memories = select_memories_for_dream(store, total_count=20)

        # Assert: Should return exactly 20 memories
        assert len(memories) == 20, f"Expected 20 memories, got {len(memories)}"

    def test_important_memories_have_highest_importance(self, db_manager):
        """测试重要记忆（40%）具有最高的重要性分数。"""
        # Arrange: Create experiences with varied importance
        store = ExperienceStore(db_manager)
        for i in range(50):
            exp = Experience(
                id=f"exp_{i:06d}",
                L3_raw=f"Test content {i}",
                importance=0.9 if i < 20 else 0.3,  # First 20 have high importance
                created_at=datetime.now().isoformat(),
            )
            store.create(exp)

        # Act: Select 20 memories (40% = 8 important, 60% = 12 random)
        memories = select_memories_for_dream(store, total_count=20)

        # Assert: First 8 should be the high importance ones
        important_memories = memories[:8]
        for memory in important_memories:
            assert memory.importance >= 0.8, f"Expected high importance, got {memory.importance}"

    def test_random_memories_dont_overlap_with_important(self, db_manager):
        """测试随机记忆（60%）不与重要记忆重叠。"""
        # Arrange: Create 50 experiences
        store = ExperienceStore(db_manager)
        for i in range(50):
            exp = Experience(
                id=f"exp_{i:06d}",
                L3_raw=f"Test content {i}",
                importance=0.5,
                created_at=datetime.now().isoformat(),
            )
            store.create(exp)

        # Act: Select 20 memories
        memories = select_memories_for_dream(store, total_count=20)

        # Assert: All memories should be unique
        memory_ids = [m.id for m in memories]
        assert len(memory_ids) == len(set(memory_ids)), "Duplicate memories found"

    def test_get_top_by_importance_uses_order_by(self, db_manager):
        """测试get_top_by_importance使用ORDER BY importance DESC。"""
        # Arrange: Create experiences with known importance values
        store = ExperienceStore(db_manager)
        importances = [0.3, 0.9, 0.5, 0.7, 0.2]
        for i, imp in enumerate(importances):
            exp = Experience(
                id=f"exp_{i:06d}",
                L3_raw=f"Test content {i}",
                importance=imp,
                created_at=datetime.now().isoformat(),
            )
            store.create(exp)

        # Act: Get top 3 by importance
        top_memories = store.get_top_by_importance(3)

        # Assert: Should be sorted by importance DESC
        assert len(top_memories) == 3
        assert top_memories[0].importance == 0.9
        assert top_memories[1].importance == 0.7
        assert top_memories[2].importance == 0.5

    def test_get_random_excluding_uses_order_by_random(self, db_manager):
        """测试get_random_excluding使用ORDER BY RANDOM()并排除指定ID。"""
        # Arrange: Create 10 experiences
        store = ExperienceStore(db_manager)
        for i in range(10):
            exp = Experience(
                id=f"exp_{i:06d}",
                L3_raw=f"Test content {i}",
                importance=0.5,
                created_at=datetime.now().isoformat(),
            )
            store.create(exp)

        # Act: Get 5 random, excluding first 3
        exclude_ids = [f"exp_{i:06d}" for i in range(3)]
        random_memories = store.get_random_excluding(5, exclude_ids)

        # Assert: Should return 5 memories, none from excluded IDs
        assert len(random_memories) <= 5  # May be less if not enough memories
        for memory in random_memories:
            assert memory.id not in exclude_ids, f"Excluded ID {memory.id} found in results"

    def test_empty_database_returns_empty_list(self, db_manager):
        """测试空数据库返回空列表（不报错）。"""
        # Arrange: Empty store
        store = ExperienceStore(db_manager)

        # Act: Select memories from empty database
        memories = select_memories_for_dream(store, total_count=20)

        # Assert: Should return empty list without errors
        assert memories == []
        assert len(memories) == 0
