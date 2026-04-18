"""隐性边发现任务测试模块。

测试隐性边发现任务的各项功能：
- upsert_batch()方法的UPSERT语义
- 隐性边发现的相似度计算
- LLM评估和边创建
"""

import pytest
import numpy as np
from datetime import datetime
from pathlib import Path

from Memory.storage.database import db_manager
from Memory.storage.experience_store import Experience, ExperienceStore
from Memory.storage.experience_edge_store import ExperienceEdge, ExperienceEdgeStore
from Memory.storage.schema import create_all_tables


@pytest.fixture(scope="function")
def fresh_db(tmp_path):
    """创建临时数据库用于测试。

    Args:
        tmp_path: pytest提供的临时路径

    Returns:
        DatabaseManager实例
    """
    from Memory.storage.database import DatabaseManager

    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path=str(db_path))
    create_all_tables(db)
    return db


@pytest.fixture(scope="function")
def experience_edge_store(fresh_db):
    """创建ExperienceEdgeStore测试实例。

    Args:
        fresh_db: 临时数据库实例

    Returns:
        ExperienceEdgeStore实例
    """
    return ExperienceEdgeStore(db_manager=fresh_db)


@pytest.fixture(scope="function")
def experience_store(fresh_db):
    """创建ExperienceStore测试实例。

    Args:
        fresh_db: 临时数据库实例

    Returns:
        ExperienceStore实例
    """
    return ExperienceStore(db_manager=fresh_db)


# ========== Task 1: upsert_batch()测试 ==========


class TestUpsertBatch:
    """测试upsert_batch()方法的UPSERT语义。"""

    def test_new_edges_created(self, experience_edge_store):
        """测试1: 新边成功创建。"""
        # 准备测试数据
        edges = [
            ExperienceEdge(
                from_id="exp_001", to_id="exp_002", type="related", weight=0.8, decayed_weight=0.8
            ),
            ExperienceEdge(
                from_id="exp_002", to_id="exp_003", type="temporal", weight=0.6, decayed_weight=0.6
            ),
        ]

        # 执行upsert
        result = experience_edge_store.upsert_batch(edges)

        # 验证结果
        assert result["created"] == 2
        assert result["updated"] == 0

        # 验证边已创建
        edge1 = experience_edge_store.get_by_from("exp_001")
        assert len(edge1) == 1
        assert edge1[0].to_id == "exp_002"
        assert edge1[0].type == "related"
        assert edge1[0].weight == 0.8

    def test_existing_edges_updated(self, experience_edge_store):
        """测试2: 已存在的边更新weight和decayed_weight。"""
        # 先创建一条边
        edge = ExperienceEdge(
            from_id="exp_001", to_id="exp_002", type="related", weight=0.5, decayed_weight=0.5
        )
        experience_edge_store.create(edge)

        # 准备更新数据（相同from_id, to_id, type）
        updated_edges = [
            ExperienceEdge(
                from_id="exp_001",
                to_id="exp_002",
                type="related",
                weight=0.9,  # 更新权重
                decayed_weight=0.85,
                emotion_driver="updated driver",
            )
        ]

        # 执行upsert
        result = experience_edge_store.upsert_batch(updated_edges)

        # 验证结果
        assert result["created"] == 0
        assert result["updated"] == 1

        # 验证边已更新
        edges = experience_edge_store.get_by_from("exp_001")
        assert len(edges) == 1
        assert edges[0].weight == 0.9
        assert edges[0].decayed_weight == 0.85
        assert edges[0].emotion_driver == "updated driver"

    def test_duplicate_edges_not_created(self, experience_edge_store):
        """测试3: 重复边不重复创建（UPSERT语义）。"""
        # 创建边
        edge = ExperienceEdge(from_id="exp_001", to_id="exp_002", type="related", weight=0.7)
        experience_edge_store.create(edge)

        # 统计初始边数
        initial_count = experience_edge_store.count()

        # 尝试创建相同边（UPSERT应该更新而不是创建新边）
        duplicate_edges = [
            ExperienceEdge(from_id="exp_001", to_id="exp_002", type="related", weight=0.8)
        ]
        result = experience_edge_store.upsert_batch(duplicate_edges)

        # 验证没有创建新边
        assert result["created"] == 0
        assert result["updated"] == 1
        assert experience_edge_store.count() == initial_count

    def test_batch_transaction_correctness(self, experience_edge_store):
        """测试4: 批量操作事务正确。"""
        # 准备测试数据（包含新边和已存在的边）
        existing_edge = ExperienceEdge(
            from_id="exp_001", to_id="exp_002", type="related", weight=0.5
        )
        experience_edge_store.create(existing_edge)

        new_edges = [
            # 已存在的边（应该更新）
            ExperienceEdge(from_id="exp_001", to_id="exp_002", type="related", weight=0.9),
            # 新边（应该创建）
            ExperienceEdge(from_id="exp_002", to_id="exp_003", type="temporal", weight=0.7),
            ExperienceEdge(from_id="exp_003", to_id="exp_004", type="causal", weight=0.6),
        ]

        # 执行upsert
        result = experience_edge_store.upsert_batch(new_edges)

        # 验证统计正确
        assert result["created"] == 2  # 两条新边
        assert result["updated"] == 1  # 一条更新

        # 验证所有边都存在
        assert experience_edge_store.count() == 3  # 总共3条不同的边


# ========== Task 2: 隐性边发现测试 ==========


class TestDiscoverImplicitEdges:
    """测试隐性边发现功能。"""

    def test_embedding_similarity_prefilter(
        self, experience_store, experience_edge_store, fresh_db
    ):
        """测试5: 使用embedding相似度预筛top50对。"""
        # 准备测试数据：创建有embedding的体验
        experiences = []
        for i in range(10):
            exp = Experience(
                id=f"exp_{i:03d}",
                L0_text=f"测试体验{i}",
                L1_text=f"第一层{i}",
                L2_text=f"第二层{i}",
                L3_raw=f"原始记录{i}" * 20,
                importance=0.5,
                consolidated=0,
                created_at=datetime.now().isoformat(),
            )
            # 生成fake embedding
            exp.L0_embedding = np.random.rand(384).astype(np.float32)
            experiences.append(exp)

        # 存储到数据库
        for exp in experiences:
            experience_store.create(exp)

        # 这里应该调用discover_implicit_edges函数
        # 由于需要LLM客户端，我们在Task 2实现后补充完整测试
        # 现在只验证数据准备正确
        assert len(experiences) == 10
        assert all(exp.L0_embedding is not None for exp in experiences)

    def test_skip_duplicate_pairs(self, experience_store):
        """测试10: 跳过已存在的边对（避免重复处理）。"""
        # 这个测试在Task 2实现后补充
        pass
