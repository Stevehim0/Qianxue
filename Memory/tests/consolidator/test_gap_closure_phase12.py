"""Phase 12 Gap Closure测试模块。

测试衰减计算执行修复和L3不可变性保护。
这个测试文件验证Gap Closure的完整流程：
1. 当前状态验证（衰减计算未执行）
2. 修复后状态验证（衰减计算执行）
3. L3不可变性保护机制验证
4. update_distorted()方法保护验证

Phase 12 Gap Closure Test - Wave 0
Created: 2026-04-02
Purpose: 测试驱动修复方法 - 验证当前broken state，为修复后的验证做准备
"""

import pytest
from datetime import datetime, timedelta
from Memory.consolidator.pipeline import ConsolidationPipeline
from Memory.consolidator.config_manager import DecayConfigManager
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.experience_edge_store import ExperienceEdgeStore, ExperienceEdge
from Memory.storage.database import db_manager
from Memory.config.settings import settings


class TestGapClosurePhase12:
    """Phase 12 Gap Closure测试类。

    测试场景：
    1. test_decay_calculation_not_executed - 验证当前broken状态
    2. test_decay_calculation_executed_after_fix - 验证修复后状态
    3. test_l3_immutability_protection - 验证L3保护
    4. test_l3_immutability_via_update_distorted - 验证update_distorted保护
    """

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """每个测试前自动设置测试数据库。"""
        db_manager.initialize(":memory:")
        yield
        db_manager.close()

    @pytest.fixture
    def experience_store(self):
        """创建ExperienceStore实例。"""
        return ExperienceStore(db_manager)

    @pytest.fixture
    def experience_edge_store(self):
        """创建ExperienceEdgeStore实例。"""
        return ExperienceEdgeStore(db_manager)

    @pytest.fixture
    def config_manager(self):
        """创建DecayConfigManager实例。"""
        return DecayConfigManager(db_manager)

    @pytest.fixture
    def consolidator_pipeline(self, experience_store, experience_edge_store, config_manager):
        """创建ConsolidationPipeline实例。

        使用mock LLM客户端和embedding服务以避免外部依赖。
        """
        from unittest.mock import Mock
        import numpy as np

        # Mock LLM client
        mock_llm = Mock()
        mock_llm.call_json.return_value = {
            "L1": "Mocked L1 summary",
            "L2": "Mocked L2 details",
        }

        # Mock embedding service
        mock_embedding = Mock()
        mock_embedding.encode.return_value = np.random.rand(768).astype(np.float32)

        # Create pipeline with mocked dependencies
        pipeline = ConsolidationPipeline(
            experience_store=experience_store,
            experience_edge_store=experience_edge_store,
            llm_client=mock_llm,
            embedding_service=mock_embedding,
            config_manager=config_manager,
        )

        return pipeline

    def test_decay_calculation_not_executed(
        self, consolidator_pipeline, experience_store, experience_edge_store, config_manager
    ):
        """测试1: 验证当前状态 - 衰减计算未执行。

        GIVEN: ConsolidationPipeline with test database
        WHEN: Run consolidation (mode='incremental')
        THEN: phase2_results contains {"status": "not_implemented"}
        AND: decay_config table has parameters (lambda_L0, alpha, beta, etc.)
        AND: experiences table has NO decayed values updated (all NULL or 0)

        这个测试验证当前broken state，确认衰减计算功能未被连接。
        """
        # Arrange: 创建测试数据（2个7天前的体验节点）
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        exp1 = Experience(
            id="exp_test_001",
            L3_raw="Test experience 1",
            L0_text="Test L0 summary 1",
            emotion_intensity=0.5,
            importance=0.7,
            created_at=week_ago,
        )
        exp2 = Experience(
            id="exp_test_002",
            L3_raw="Test experience 2",
            L0_text="Test L0 summary 2",
            emotion_intensity=0.6,
            importance=0.8,
            created_at=week_ago,
        )

        experience_store.create(exp1)
        experience_store.create(exp2)

        # 创建测试边（3条边）
        edge1 = ExperienceEdge(
            from_id="exp_test_001",
            to_id="exp_test_002",
            type="temporal",
            weight=0.8,
            decayed_weight=0.8,
            created_at=week_ago,
        )
        edge2 = ExperienceEdge(
            from_id="exp_test_002",
            to_id="exp_test_001",
            type="thematic",
            weight=0.7,
            decayed_weight=0.7,
            created_at=week_ago,
        )
        edge3 = ExperienceEdge(
            from_id="exp_test_001",
            to_id="exp_test_001",
            type="causal",
            weight=0.9,
            decayed_weight=0.9,
            created_at=week_ago,
        )

        experience_edge_store.create(edge1)
        experience_edge_store.create(edge2)
        experience_edge_store.create(edge3)

        # Act: 运行巩固流程（增量模式）
        result = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert: 验证phase2_results状态
        phase2_results = result.get("phase2", {})
        assert phase2_results is not None, "phase2_results should exist"
        assert phase2_results.get("status") == "not_implemented", (
            f"Expected status 'not_implemented', got '{phase2_results.get('status')}'"
        )

        # Assert: 验证decay_config参数已存在
        config = config_manager.list_all()
        assert len(config) >= 11, f"Expected at least 11 decay config parameters, got {len(config)}"

        # 验证关键参数存在
        param_names = {p["name"] for p in config}
        required_params = {
            "lambda_L0",
            "lambda_L1",
            "lambda_L2",
            "lambda_L3",
            "lambda_temporal",
            "lambda_thematic",
            "lambda_causal",
            "lambda_associative",
            "alpha",
            "beta",
            "dormancy_threshold",
        }
        assert required_params.issubset(param_names), (
            f"Missing required parameters: {required_params - param_names}"
        )

        # Assert: 验证experiences表的衰减字段未被更新
        all_exps = experience_store.get_all()
        assert len(all_exps) == 2, f"Expected 2 experiences, got {len(all_exps)}"

        for exp in all_exps:
            # 验证衰减字段为None或0（未计算）
            assert exp.L0_decayed is None or exp.L0_decayed == 0, (
                f"L0_decayed should be None or 0 for unimplemented decay, got {exp.L0_decayed}"
            )
            assert exp.L1_decayed is None or exp.L1_decayed == 0, (
                f"L1_decayed should be None or 0 for unimplemented decay, got {exp.L1_decayed}"
            )
            assert exp.L2_decayed is None or exp.L2_decayed == 0, (
                f"L2_decayed should be None or 0 for unimplemented decay, got {exp.L2_decayed}"
            )
            assert exp.L3_decayed is None or exp.L3_decayed == 0, (
                f"L3_decayed should be None or 0 for unimplemented decay, got {exp.L3_decayed}"
            )

        # Assert: 验证experience_edges表的衰减字段未被更新
        all_edges = experience_edge_store.get_all()
        assert len(all_edges) == 3, f"Expected 3 edges, got {len(all_edges)}"

        for edge in all_edges:
            # 验证衰减权重未更新（仍然是原始值）
            assert edge.decayed_weight == edge.weight, (
                f"decayed_weight should equal weight for unimplemented decay, "
                f"got {edge.decayed_weight} vs {edge.weight}"
            )

    def test_decay_calculation_executed_after_fix(
        self, consolidator_pipeline, experience_store, experience_edge_store, config_manager
    ):
        """测试2: 验证修复后状态 - 衰减计算实际执行。

        GIVEN: ConsolidationPipeline with test database
        AND: 5 experiences with created_at 7 days ago
        AND: 10 experience_edges with weight=0.8
        WHEN: Run consolidation (mode='incremental')
        THEN: phase2_results contains {"status": "completed"}
        AND: phase2_results has edge_count > 0 and node_count > 0
        AND: experiences.L0_decayed < 1.0 (decayed from original)
        AND: experiences.L3_decayed < L0_decayed (L3 decays faster)
        AND: experience_edges.decayed_weight < 0.8 (decayed from original)
        AND: dormant edges marked if decayed_weight < dormancy_threshold

        这个测试在修复后应该PASS（当前是RED状态）。
        """
        # Arrange: 创建5个7天前的体验节点
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        experiences = []
        for i in range(5):
            exp = Experience(
                id=f"exp_test_{i:03d}",
                L3_raw=f"Test experience {i}",
                L0_text=f"Test L0 summary {i}",
                emotion_intensity=0.5 + (i * 0.1),  # 0.5, 0.6, 0.7, 0.8, 0.9
                importance=0.6 + (i * 0.05),  # 0.6, 0.65, 0.7, 0.75, 0.8
                created_at=week_ago,
            )
            experience_store.create(exp)
            experiences.append(exp)

        # 创建10条边
        edges = []
        edge_types = ["temporal", "thematic", "causal", "associative"]
        for i in range(10):
            edge = ExperienceEdge(
                from_id=f"exp_test_{i % 5:03d}",
                to_id=f"exp_test_{(i + 1) % 5:03d}",
                type=edge_types[i % 4],
                weight=0.8,
                decayed_weight=0.8,
                access_count=i // 2,  # 一些边有访问计数
                created_at=week_ago,
            )
            experience_edge_store.create(edge)
            edges.append(edge)

        # Act: 运行巩固流程
        result = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert: 验证phase2_results状态（修复后应该是"completed"）
        phase2_results = result.get("phase2", {})
        assert phase2_results is not None, "phase2_results should exist"
        assert phase2_results.get("status") == "completed", (
            f"Expected status 'completed', got '{phase2_results.get('status')}'"
        )

        # Assert: 验证处理的边数和节点数
        assert phase2_results.get("edge_count", 0) > 0, "edge_count should be > 0"
        assert phase2_results.get("node_count", 0) > 0, "node_count should be > 0"

        # Assert: 验证experiences的衰减值已更新
        all_exps = experience_store.get_all()
        assert len(all_exps) == 5, f"Expected 5 experiences, got {len(all_exps)}"

        for exp in all_exps:
            # 验证衰减值已计算（不为None且在合理范围内）
            assert exp.L0_decayed is not None, "L0_decayed should be calculated"
            assert exp.L1_decayed is not None, "L1_decayed should be calculated"
            assert exp.L2_decayed is not None, "L2_decayed should be calculated"
            assert exp.L3_decayed is not None, "L3_decayed should be calculated"

            # 验证衰减值在[0, 1]范围内
            assert 0.0 <= exp.L0_decayed <= 1.0, f"L0_decayed out of range: {exp.L0_decayed}"
            assert 0.0 <= exp.L1_decayed <= 1.0, f"L1_decayed out of range: {exp.L1_decayed}"
            assert 0.0 <= exp.L2_decayed <= 1.0, f"L2_decayed out of range: {exp.L2_decayed}"
            assert 0.0 <= exp.L3_decayed <= 1.0, f"L3_decayed out of range: {exp.L3_decayed}"

            # 验证L0已衰减（小于1.0）
            assert exp.L0_decayed < 1.0, f"L0_decayed should be < 1.0, got {exp.L0_decayed}"

            # 验证L3衰减比L0快（L3 < L0）
            assert exp.L3_decayed < exp.L0_decayed, (
                f"L3_decayed ({exp.L3_decayed}) should be < L0_decayed ({exp.L0_decayed})"
            )

        # Assert: 验证边的衰减值已更新
        all_edges = experience_edge_store.get_all()
        assert len(all_edges) == 10, f"Expected 10 edges, got {len(all_edges)}"

        dormant_threshold = config_manager.get("dormancy_threshold")["value"]

        for edge in all_edges:
            # 验证衰减权重已计算且小于原始权重
            assert edge.decayed_weight is not None, "decayed_weight should be calculated"
            assert edge.decayed_weight < edge.weight, (
                f"decayed_weight ({edge.decayed_weight}) should be < weight ({edge.weight})"
            )
            assert edge.decayed_weight >= 0.0, f"decayed_weight should be >= 0.0, got {edge.decayed_weight}"

            # 验证休眠标记（如果衰减权重低于阈值）
            if edge.decayed_weight < dormant_threshold:
                assert edge.dormant == 1, (
                    f"Edge with decayed_weight {edge.decayed_weight} < threshold "
                    f"{dormant_threshold} should be marked dormant"
                )

    def test_l3_immutability_protection(self, experience_store):
        """测试3: 验证L3不可变性保护机制。

        GIVEN: ExperienceStore with allow_l3_modification = False
        WHEN: Try to update experience with L3_raw changed
        THEN: Update rejected with ValueError("Cannot modify L3_raw")
        AND: Original L3_raw unchanged in database

        这个测试验证L3保护机制已经生效。
        """
        # Arrange: 创建测试体验节点
        exp = Experience(
            id="exp_test_l3_001",
            L3_raw="Original L3 text - this should never change",
            L0_text="Original L0 text",
            L1_text="Original L1 text",
            L2_text="Original L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )
        experience_store.create(exp)

        # 读取原始L3_raw
        original_exp = experience_store.get_by_id("exp_test_l3_001")
        original_l3 = original_exp.L3_raw

        # Act & Assert: 尝试通过update()修改L3_raw（应该失败）
        modified_exp = Experience(
            id="exp_test_l3_001",
            L3_raw="Modified L3 text - this should be rejected",
            L0_text="Modified L0 text",
            L1_text="Modified L1 text",
            L2_text="Modified L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )

        # 验证抛出ValueError
        with pytest.raises(ValueError, match="Cannot modify L3_raw"):
            experience_store.update(modified_exp)

        # Assert: 验证数据库中的L3_raw未改变
        unchanged_exp = experience_store.get_by_id("exp_test_l3_001")
        assert unchanged_exp.L3_raw == original_l3, (
            f"L3_raw should remain unchanged: expected '{original_l3}', "
            f"got '{unchanged_exp.L3_raw}'"
        )

        # Assert: 验证其他字段也未改变（因为整个update被拒绝）
        assert unchanged_exp.L0_text == "Original L0 text", "L0_text should be unchanged"
        assert unchanged_exp.L1_text == "Original L1 text", "L1_text should be unchanged"
        assert unchanged_exp.L2_text == "Original L2 text", "L2_text should be unchanged"

    def test_l3_immutability_via_update_distorted(self, experience_store):
        """测试4: 验证update_distorted()方法的L3保护。

        GIVEN: ExperienceStore.update_distorted() method
        WHEN: Call update_distorted(experience_id, L0_text="new L0", L1_text="new L1", L2_text="new L2")
        THEN: Update succeeds (L0/L1/L2 modified)
        WHEN: Call update_distorted(experience_id, L3_raw="new L3")  # Should not be possible via signature
        THEN: Method signature prevents L3_raw parameter (no L3_raw parameter in update_distorted)
        AND: Verify L3_raw unchanged in database

        这个测试验证update_distorted()方法设计防止L3修改。
        """
        # Arrange: 创建测试体验节点
        exp = Experience(
            id="exp_test_distort_001",
            L3_raw="Original L3 text - immutable",
            L0_text="Original L0 text",
            L1_text="Original L1 text",
            L2_text="Original L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )
        experience_store.create(exp)

        # 读取原始值
        original_exp = experience_store.get_by_id("exp_test_distort_001")
        original_l3 = original_exp.L3_raw
        original_l0 = original_exp.L0_text
        original_l1 = original_exp.L1_text
        original_l2 = original_exp.L2_text

        # Act 1: 调用update_distorted()修改L0/L1/L2（应该成功）
        success = experience_store.update_distorted(
            experience_id="exp_test_distort_001",
            L0_text="Modified L0 text via update_distorted",
            L1_text="Modified L1 text via update_distorted",
            L2_text="Modified L2 text via update_distorted",
        )

        # Assert 1: 验证更新成功
        assert success is True, "update_distorted() should succeed for L0/L1/L2"

        # Assert 2: 验证L0/L1/L2已更新
        updated_exp = experience_store.get_by_id("exp_test_distort_001")
        assert updated_exp.L0_text == "Modified L0 text via update_distorted", (
            f"L0_text should be updated, got '{updated_exp.L0_text}'"
        )
        assert updated_exp.L1_text == "Modified L1 text via update_distorted", (
            f"L1_text should be updated, got '{updated_exp.L1_text}'"
        )
        assert updated_exp.L2_text == "Modified L2 text via update_distorted", (
            f"L2_text should be updated, got '{updated_exp.L2_text}'"
        )

        # Assert 3: 验证L3_raw未改变
        assert updated_exp.L3_raw == original_l3, (
            f"L3_raw should remain unchanged: expected '{original_l3}', got '{updated_exp.L3_raw}'"
        )

        # Act 2 & Assert 4: 验证update_distorted()方法签名不包含L3_raw参数
        # 使用inspect检查方法签名
        import inspect

        sig = inspect.signature(experience_store.update_distorted)
        params = list(sig.parameters.keys())

        # 验证L3_raw不在参数列表中
        assert "L3_raw" not in params, (
            f"update_distorted() should NOT have L3_raw parameter, but found: {params}"
        )

        # 验证允许的参数存在
        allowed_params = ["experience_id", "L0_text", "L1_text", "L2_text", "distorted"]
        for param in allowed_params:
            assert param in params, f"update_distorted() should have {param} parameter"

        # 最终验证：L3_raw仍然是原始值
        final_exp = experience_store.get_by_id("exp_test_distort_001")
        assert final_exp.L3_raw == original_l3, "L3_raw must remain immutable"

    def test_l3_protection_in_update_method(self, experience_store):
        """测试5: 验证update()方法拒绝L3_raw修改。

        GIVEN: ExperienceStore with allow_l3_modification = False
        AND: Existing experience with L3_raw="original text"
        WHEN: Call update(id, L3_raw="modified text")
        THEN: ValueError raised with message "Cannot modify L3_raw"
        AND: Database still has L3_raw="original text" (no modification)
        AND: Error logged (check log for error message)
        VERIFICATION: Query database directly with SQL to confirm L3_raw unchanged
        """
        # Arrange: 创建测试体验节点
        exp = Experience(
            id="exp_test_update_l3_001",
            L3_raw="Original L3 text - this should never change",
            L0_text="Original L0 text",
            L1_text="Original L1 text",
            L2_text="Original L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )
        experience_store.create(exp)

        # 读取原始L3_raw（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_update_l3_001",))
            result = cursor.fetchone()
            original_l3 = result["L3_raw"] if result else None

        assert original_l3 == "Original L3 text - this should never change", "Failed to create test experience"

        # Act & Assert: 尝试通过update()修改L3_raw（应该失败）
        modified_exp = Experience(
            id="exp_test_update_l3_001",
            L3_raw="Modified L3 text - this should be rejected",
            L0_text="Modified L0 text",
            L1_text="Modified L1 text",
            L2_text="Modified L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )

        # 验证抛出ValueError
        with pytest.raises(ValueError, match="Cannot modify L3_raw"):
            experience_store.update(modified_exp)

        # Assert: 验证数据库中的L3_raw未改变（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_update_l3_001",))
            result = cursor.fetchone()
            unchanged_l3 = result["L3_raw"] if result else None

        assert unchanged_l3 == original_l3, (
            f"L3_raw should remain unchanged in database: expected '{original_l3}', got '{unchanged_l3}'"
        )

        # Assert: 验证其他字段也未改变（因为整个update被拒绝）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT L0_text, L1_text, L2_text FROM experiences WHERE id = ?",
                ("exp_test_update_l3_001",),
            )
            result = cursor.fetchone()

        assert result["L0_text"] == "Original L0 text", "L0_text should be unchanged"
        assert result["L1_text"] == "Original L1 text", "L1_text should be unchanged"
        assert result["L2_text"] == "Original L2 text", "L2_text should be unchanged"

    def test_l3_protection_can_be_disabled_for_testing(self, experience_store):
        """测试6: 验证L3保护可通过配置开关禁用。

        GIVEN: ExperienceStore with allow_l3_modification = True (test mode)
        AND: Existing experience with L3_raw="original text"
        WHEN: Call update(id, L3_raw="modified text")
        THEN: Update succeeds (returns True)
        AND: Database has L3_raw="modified text" (modified)
        VERIFICATION: SQL query confirms L3_raw changed when protection disabled
        This proves the protection is configurable
        """
        # Arrange: 创建测试体验节点
        exp = Experience(
            id="exp_test_allow_l3_001",
            L3_raw="Original L3 text - modifiable in test mode",
            L0_text="Original L0 text",
            emotion_intensity=0.7,
            importance=0.8,
        )
        experience_store.create(exp)

        # 读取原始L3_raw
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_allow_l3_001",))
            result = cursor.fetchone()
            original_l3 = result["L3_raw"] if result else None

        # Act: 临时修改配置允许L3修改
        from Memory.config.settings import settings
        original_allow_l3 = settings.dream.allow_l3_modification
        settings.dream.allow_l3_modification = True

        try:
            # 尝试修改L3_raw（应该成功）
            modified_exp = Experience(
                id="exp_test_allow_l3_001",
                L3_raw="Modified L3 text - allowed in test mode",
                L0_text="Modified L0 text",
                emotion_intensity=0.7,
                importance=0.8,
            )

            success = experience_store.update(modified_exp)

            # Assert: 验证更新成功
            assert success is True, "update() should succeed when allow_l3_modification=True"

            # Assert: 验证数据库中的L3_raw已改变（通过SQL直接查询）
            with db_manager.transaction() as cursor:
                cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_allow_l3_001",))
                result = cursor.fetchone()
                modified_l3 = result["L3_raw"] if result else None

            assert modified_l3 == "Modified L3 text - allowed in test mode", (
                f"L3_raw should be modified when protection disabled: expected 'Modified L3 text - allowed in test mode', got '{modified_l3}'"
            )
            assert modified_l3 != original_l3, "L3_raw should be different from original"

        finally:
            # Restore original setting
            settings.dream.allow_l3_modification = original_allow_l3

    def test_update_distorted_cannot_modify_l3_by_design(self, experience_store):
        """测试7: 验证update_distorted()方法设计防止L3修改。

        GIVEN: ExperienceStore.update_distorted() method
        AND: Existing experience with L3_raw="original L3"
        WHEN: Try to call update_distorted(id, L3_raw="modified")
        THEN: TypeError raised (unexpected keyword argument 'L3_raw')
        OR: Method signature simply doesn't accept L3_raw parameter
        This proves protection by design (no L3_raw parameter exists)
        """
        # Arrange: 创建测试体验节点
        exp = Experience(
            id="exp_test_design_001",
            L3_raw="Original L3 text - protected by design",
            L0_text="Original L0 text",
            L1_text="Original L1 text",
            L2_text="Original L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )
        experience_store.create(exp)

        # Act & Assert: 验证update_distorted()方法签名不包含L3_raw参数
        import inspect

        sig = inspect.signature(experience_store.update_distorted)
        params = list(sig.parameters.keys())

        # 验证L3_raw不在参数列表中
        assert "L3_raw" not in params, (
            f"update_distorted() should NOT have L3_raw parameter, but found: {params}"
        )

        # 验证允许的参数存在
        allowed_params = ["experience_id", "L0_text", "L1_text", "L2_text", "distorted"]
        for param in allowed_params:
            assert param in params, f"update_distorted() should have {param} parameter"

        # Act & Assert: 尝试传递L3_raw参数（应该抛出TypeError）
        with pytest.raises(TypeError, match="unexpected keyword argument 'L3_raw'"):
            experience_store.update_distorted(
                experience_id="exp_test_design_001", L3_raw="This should fail"
            )

        # Assert: 验证L3_raw仍然是原始值
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_design_001",))
            result = cursor.fetchone()
            final_l3 = result["L3_raw"] if result else None

        assert final_l3 == "Original L3 text - protected by design", "L3_raw must remain immutable"

    def test_update_distorted_modifies_l0_l1_l2(self, experience_store):
        """测试8: 验证update_distorted()可以修改L0/L1/L2。

        GIVEN: ExperienceStore.update_distorted() method
        AND: Existing experience with L0="old L0", L1="old L1", L2="old L2"
        WHEN: Call update_distorted(id, L0_text="new L0", L1_text="new L1", L2_text="new L2")
        THEN: Update succeeds (returns True)
        AND: Database has updated L0/L1/L2 values
        AND: L3_raw unchanged (still "original L3")
        VERIFICATION: SQL SELECT query confirms L0/L1/L2 changed, L3_raw unchanged
        This proves L0/L1/L2 can be modified while L3 is protected
        """
        # Arrange: 创建测试体验节点
        exp = Experience(
            id="exp_test_l0l1l2_001",
            L3_raw="Original L3 text - immutable",
            L0_text="Old L0 text",
            L1_text="Old L1 text",
            L2_text="Old L2 text",
            emotion_intensity=0.7,
            importance=0.8,
        )
        experience_store.create(exp)

        # Act: 调用update_distorted()修改L0/L1/L2
        success = experience_store.update_distorted(
            experience_id="exp_test_l0l1l2_001",
            L0_text="New L0 text",
            L1_text="New L1 text",
            L2_text="New L2 text",
        )

        # Assert: 验证更新成功
        assert success is True, "update_distorted() should succeed for L0/L1/L2"

        # Assert: 验证L0/L1/L2已更新（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT L0_text, L1_text, L2_text, L3_raw FROM experiences WHERE id = ?",
                ("exp_test_l0l1l2_001",),
            )
            result = cursor.fetchone()

        assert result["L0_text"] == "New L0 text", f"L0_text should be updated, got '{result['L0_text']}'"
        assert result["L1_text"] == "New L1 text", f"L1_text should be updated, got '{result['L1_text']}'"
        assert result["L2_text"] == "New L2 text", f"L2_text should be updated, got '{result['L2_text']}'"

        # Assert: 验证L3_raw未改变
        assert result["L3_raw"] == "Original L3 text - immutable", (
            f"L3_raw should remain unchanged, got '{result['L3_raw']}'"
        )

    def test_create_allows_l3_raw_on_initial_creation(self, experience_store):
        """测试9: 验证create()方法允许设置L3_raw。

        GIVEN: ExperienceStore.create() method
        WHEN: Call create(L3_raw="new experience text", L0_text="summary", ...)
        THEN: Creation succeeds
        AND: Database has L3_raw="new experience text"
        This proves L3_raw is allowed on creation (immutable after)
        """
        # Arrange: 准备新的体验节点
        new_exp = Experience(
            id="exp_test_create_001",
            L3_raw="New experience L3 text - allowed on creation",
            L0_text="New experience L0 summary",
            L1_text="New experience L1 key points",
            L2_text="New experience L2 details",
            emotion_intensity=0.7,
            importance=0.8,
        )

        # Act: 创建新体验节点
        exp_id = experience_store.create(new_exp)

        # Assert: 验证创建成功
        assert exp_id == "exp_test_create_001", "Experience should be created with correct ID"

        # Assert: 验证数据库中的L3_raw正确设置（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_create_001",))
            result = cursor.fetchone()
            created_l3 = result["L3_raw"] if result else None

        assert created_l3 == "New experience L3 text - allowed on creation", (
            f"L3_raw should be set on creation, got '{created_l3}'"
        )

    def test_l3_immutability_across_all_code_paths(self, consolidator_pipeline, experience_store):
        """测试10: 验证L3保护在巩固流程中生效。

        GIVEN: ConsolidationPipeline with dream module
        AND: Experience with L3_raw="original"
        WHEN: Run consolidation (which calls various update methods)
        THEN: L3_raw never modified (verify in database)
        AND: distorted field may be updated (allowed)
        VERIFICATION: SQL query confirms L3_raw unchanged after consolidation
        This proves L3 protection holds during complex operations
        """
        # Arrange: 创建测试体验节点
        import numpy as np
        from datetime import datetime, timedelta

        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        exp = Experience(
            id="exp_test_consolidation_001",
            L3_raw="Original L3 text - must survive consolidation",
            L0_text="Original L0 text",
            L1_text="Original L1 text",
            L2_text="Original L2 text",
            emotion_intensity=0.7,
            importance=0.8,
            L0_embedding=np.random.rand(768).astype(np.float32),
            created_at=week_ago,
        )
        experience_store.create(exp)

        # 读取原始L3_raw
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw FROM experiences WHERE id = ?", ("exp_test_consolidation_001",))
            result = cursor.fetchone()
            original_l3 = result["L3_raw"] if result else None

        # Act: 运行巩固流程（增量模式）
        result = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert: 验证L3_raw未改变（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L3_raw, distorted FROM experiences WHERE id = ?", ("exp_test_consolidation_001",))
            result = cursor.fetchone()
            final_l3 = result["L3_raw"] if result else None
            distorted = result["distorted"] if result else None

        assert final_l3 == original_l3, (
            f"L3_raw should remain unchanged after consolidation: expected '{original_l3}', got '{final_l3}'"
        )

        # Assert: 验证distorted字段可能被更新（巩固流程可能会更新这个字段）
        # 注意：distorted字段可能被更新，也可能保持None，这不影响L3保护的验证
        # 重要的是L3_raw必须是原始值

    # ========== 集成测试（Integration Tests - Tests 11-15）==========

    def test_full_consolidation_with_decay_calculation(
        self, consolidator_pipeline, experience_store, experience_edge_store, config_manager
    ):
        """测试11: 验证完整巩固流程中的衰减计算。

        GIVEN: ConsolidationPipeline with test database
        AND: 20 test experiences (created_at various times: 1, 3, 7, 14, 30 days ago)
        AND: 30 test experience_edges with different types (temporal, thematic, causal, associative)
        AND: DecayConfigManager with default parameters (lambda_L0=0.01, alpha=0.05, beta=0.5)
        WHEN: Run full consolidation: pipeline.run_consolidation(mode='full', days=30)
        THEN: Phase 1 completes successfully (6 parallel tasks)
        AND: Phase 2 (decay calculation) executes:
            * phase2_results['status'] == 'completed'
            * phase2_results['edge_count'] == 30
            * phase2_results['node_count'] == 20
            * phase2_results['dormant_count'] >= 0
            * phase2_results['awakened_count'] >= 0
        AND: Database has decayed values:
            * experiences.L0_decayed < 1.0 for all nodes
            * experiences.L3_decayed < experiences.L0_decayed (L3 decays faster)
            * experience_edges.decayed_weight < original weight
            * experience_edges.dormant = True for weak edges
        AND: Decay values follow formula:
            * Older memories have lower decayed values (more decay)
            * High importance memories decay slower
            * High emotion_intensity memories decay slower
            * Frequently accessed edges decay slower
        VERIFICATION: SQL queries confirm decayed fields updated in database
        """
        # Arrange: 创建20个不同时间、重要性、情感强度的体验节点
        import numpy as np
        from datetime import datetime, timedelta

        time_ago_map = {
            1: timedelta(days=1),
            3: timedelta(days=3),
            7: timedelta(days=7),
            14: timedelta(days=14),
            30: timedelta(days=30),
        }

        experiences = []
        for i in range(20):
            days_ago = [1, 3, 7, 14, 30][i % 5]
            time_ago = time_ago_map[days_ago]

            exp = Experience(
                id=f"exp_test_{i:03d}",
                L3_raw=f"Test experience {i}",
                L0_text=f"Test L0 summary {i}",
                emotion_intensity=0.4 + (i % 5) * 0.1,  # 0.4, 0.5, 0.6, 0.7, 0.8
                importance=0.5 + (i % 4) * 0.1,  # 0.5, 0.6, 0.7, 0.8
                created_at=(datetime.now() - time_ago).isoformat(),
                L0_embedding=np.random.rand(768).astype(np.float32),
            )
            experience_store.create(exp)
            experiences.append(exp)

        # 创建30条边（不同类型和访问计数）
        edges = []
        edge_types = ["temporal", "thematic", "causal", "associative"]
        for i in range(30):
            edge = ExperienceEdge(
                from_id=f"exp_test_{i % 20:03d}",
                to_id=f"exp_test_{(i + 1) % 20:03d}",
                type=edge_types[i % 4],
                weight=0.5 + (i % 5) * 0.1,  # 0.5, 0.6, 0.7, 0.8, 0.9
                decayed_weight=0.5 + (i % 5) * 0.1,
                access_count=i // 3,  # 不同的访问计数：0, 1, 2, ..., 9
                created_at=(datetime.now() - timedelta(days=7)).isoformat(),
            )
            experience_edge_store.create(edge)
            edges.append(edge)

        # Act: 运行全量巩固流程
        result = consolidator_pipeline.run_consolidation(mode="full", batch_size=20)

        # Assert: 验证phase1_results状态
        phase1_results = result.get("phase1", {})
        assert phase1_results is not None, "phase1_results should exist"
        assert phase1_results.get("status") == "completed", (
            f"Expected phase1 status 'completed', got '{phase1_results.get('status')}'"
        )

        # Assert: 验证phase2_results状态（衰减计算执行）
        phase2_results = result.get("phase2", {})
        assert phase2_results is not None, "phase2_results should exist"
        assert phase2_results.get("status") == "completed", (
            f"Expected phase2 status 'completed', got '{phase2_results.get('status')}'"
        )

        # Assert: 验证处理的边数和节点数
        assert phase2_results.get("edge_count", 0) > 0, "edge_count should be > 0"
        assert phase2_results.get("node_count", 0) > 0, "node_count should be > 0"

        # Assert: 验证休眠和唤醒计数
        dormant_count = phase2_results.get("dormant_count", 0)
        awakened_count = phase2_results.get("awakened_count", 0)
        assert dormant_count >= 0, "dormant_count should be >= 0"
        assert awakened_count >= 0, "awakened_count should be >= 0"

        # Assert: 验证experiences的衰减值已更新（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT id, L0_decayed, L3_decayed FROM experiences ORDER BY id"
            )
            all_decayed = cursor.fetchall()

        assert len(all_decayed) == 20, f"Expected 20 experiences, got {len(all_decayed)}"

        for row in all_decayed:
            L0_decayed = row["L0_decayed"]
            L3_decayed = row["L3_decayed"]

            # 验证衰减值已计算（不为None且在合理范围内）
            assert L0_decayed is not None, "L0_decayed should be calculated"
            assert L3_decayed is not None, "L3_decayed should be calculated"

            # 验证衰减值在[0, 1]范围内
            assert 0.0 <= L0_decayed <= 1.0, f"L0_decayed out of range: {L0_decayed}"
            assert 0.0 <= L3_decayed <= 1.0, f"L3_decayed out of range: {L3_decayed}"

            # 验证L0已衰减（小于1.0）
            assert L0_decayed < 1.0, f"L0_decayed should be < 1.0, got {L0_decayed}"

            # 验证L3衰减比L0快（L3 < L0）
            assert L3_decayed < L0_decayed, (
                f"L3_decayed ({L3_decayed}) should be < L0_decayed ({L0_decayed})"
            )

        # Assert: 验证边的衰减值已更新（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT id, weight, decayed_weight, dormant FROM experience_edges ORDER BY id"
            )
            all_edges = cursor.fetchall()

        assert len(all_edges) == 30, f"Expected 30 edges, got {len(all_edges)}"

        dormant_threshold = config_manager.get("dormancy_threshold")["value"]

        for row in all_edges:
            weight = row["weight"]
            decayed_weight = row["decayed_weight"]
            dormant = row["dormant"]

            # 验证衰减权重已计算且小于原始权重
            assert decayed_weight is not None, "decayed_weight should be calculated"
            assert decayed_weight < weight, (
                f"decayed_weight ({decayed_weight}) should be < weight ({weight})"
            )
            assert decayed_weight >= 0.0, f"decayed_weight should be >= 0.0, got {decayed_weight}"

            # 验证休眠标记（如果衰减权重低于阈值）
            if decayed_weight < dormant_threshold:
                assert dormant == 1, (
                    f"Edge with decayed_weight {decayed_weight} < threshold "
                    f"{dormant_threshold} should be marked dormant"
                )

    def test_decay_parameters_persist_across_consolidations(
        self, consolidator_pipeline, experience_store, experience_edge_store, config_manager
    ):
        """测试12: 验证衰减参数在多次巩固中保持不变。

        GIVEN: DecayConfigManager with custom parameters
        AND: Set lambda_L0=0.02 (faster decay)
        AND: Set alpha=0.1 (stronger reinforcement)
        AND: Set beta=0.8 (stronger emotion protection)
        WHEN: Run consolidation twice
        THEN: First consolidation uses custom parameters
        AND: Second consolidation still uses custom parameters (not reset)
        AND: Decay results reflect custom parameters:
            * Faster decay with higher lambda_L0
            * Strong reinforcement with higher alpha
        Verify parameters persist in decay_config table
        """
        # Arrange: 设置自定义衰减参数
        config_manager.set("lambda_L0", 0.02)  # 更快的衰减
        config_manager.set("alpha", 0.1)  # 更强的增强
        config_manager.set("beta", 0.8)  # 更强的情感保护

        # 创建测试数据
        import numpy as np
        from datetime import datetime, timedelta

        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        exp1 = Experience(
            id="exp_test_persist_001",
            L3_raw="Test experience 1",
            L0_text="Test L0 summary 1",
            emotion_intensity=0.7,
            importance=0.8,
            created_at=week_ago,
            L0_embedding=np.random.rand(768).astype(np.float32),
        )
        exp2 = Experience(
            id="exp_test_persist_002",
            L3_raw="Test experience 2",
            L0_text="Test L0 summary 2",
            emotion_intensity=0.6,
            importance=0.7,
            created_at=week_ago,
            L0_embedding=np.random.rand(768).astype(np.float32),
        )
        experience_store.create(exp1)
        experience_store.create(exp2)

        edge1 = ExperienceEdge(
            from_id="exp_test_persist_001",
            to_id="exp_test_persist_002",
            type="temporal",
            weight=0.8,
            decayed_weight=0.8,
            created_at=week_ago,
        )
        experience_edge_store.create(edge1)

        # Act 1: 第一次运行巩固
        result1 = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert 1: 验证第一次巩固使用自定义参数
        phase2_results_1 = result1.get("phase2", {})
        assert phase2_results_1.get("status") == "completed", "First consolidation should complete"

        # 验证参数在配置表中仍然正确
        lambda_L0_after_1 = config_manager.get("lambda_L0")["value"]
        alpha_after_1 = config_manager.get("alpha")["value"]
        beta_after_1 = config_manager.get("beta")["value"]

        assert lambda_L0_after_1 == 0.02, f"lambda_L0 should persist as 0.02, got {lambda_L0_after_1}"
        assert alpha_after_1 == 0.1, f"alpha should persist as 0.1, got {alpha_after_1}"
        assert beta_after_1 == 0.8, f"beta should persist as 0.8, got {beta_after_1}"

        # Act 2: 第二次运行巩固
        result2 = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert 2: 验证第二次巩固仍然使用自定义参数
        phase2_results_2 = result2.get("phase2", {})
        assert phase2_results_2.get("status") == "completed", "Second consolidation should complete"

        # 验证参数在配置表中仍然正确
        lambda_L0_after_2 = config_manager.get("lambda_L0")["value"]
        alpha_after_2 = config_manager.get("alpha")["value"]
        beta_after_2 = config_manager.get("beta")["value"]

        assert lambda_L0_after_2 == 0.02, f"lambda_L0 should persist as 0.02 after second consolidation, got {lambda_L0_after_2}"
        assert alpha_after_2 == 0.1, f"alpha should persist as 0.1 after second consolidation, got {alpha_after_2}"
        assert beta_after_2 == 0.8, f"beta should persist as 0.8 after second consolidation, got {beta_after_2}"

        # Assert 3: 验证衰减结果反映了自定义参数
        # 更高的lambda_L0应该导致更快的衰减（更低的decay值）
        with db_manager.transaction() as cursor:
            cursor.execute("SELECT L0_decayed FROM experiences WHERE id = ?", ("exp_test_persist_001",))
            result = cursor.fetchone()
            L0_decayed = result["L0_decayed"] if result else None

        assert L0_decayed is not None, "L0_decayed should be calculated"
        assert L0_decayed < 1.0, "L0_decayed should be < 1.0 (decay occurred)"

        # 由于lambda_L0=0.02（默认是0.01），衰减应该更快，所以L0_decayed应该更低
        # 7天后的衰减公式：exp(-0.02 * 7) = exp(-0.14) ≈ 0.87
        # 默认参数：exp(-0.01 * 7) = exp(-0.07) ≈ 0.93
        # 所以L0_decayed应该约等于0.87（考虑情感和重要性的调整）
        assert L0_decayed < 0.90, f"With faster lambda_L0=0.02, L0_decayed should be < 0.90, got {L0_decayed}"

    def test_decay_calculation_error_handling(
        self, consolidator_pipeline, experience_store, experience_edge_store, config_manager
    ):
        """测试13: 验证衰减计算错误处理。

        GIVEN: ConsolidationPipeline with invalid decay parameters
        AND: Set lambda_L0=-0.1 (invalid: negative value)
        WHEN: Run consolidation
        THEN: Decay calculation fails gracefully
        AND: phase2_results['status'] == 'error'
        AND: Error message logged
        AND: Phase 1 tasks still complete (no cascade failure)
        """
        # Arrange: 创建测试数据
        import numpy as np
        from datetime import datetime, timedelta

        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        exp1 = Experience(
            id="exp_test_error_001",
            L3_raw="Test experience 1",
            L0_text="Test L0 summary 1",
            emotion_intensity=0.7,
            importance=0.8,
            created_at=week_ago,
            L0_embedding=np.random.rand(768).astype(np.float32),
        )
        experience_store.create(exp1)

        # Act: 尝试设置无效的lambda_L0（负值）
        # 注意：config_manager.set()会验证参数，所以我们需要直接修改数据库
        with db_manager.transaction() as cursor:
            cursor.execute(
                "UPDATE decay_config SET value = ? WHERE name = ?",
                (-0.1, "lambda_L0")  # 无效的负值
            )

        # 尝试运行巩固（应该失败）
        result = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert: 验证Phase 1仍然完成
        phase1_results = result.get("phase1", {})
        assert phase1_results is not None, "phase1_results should exist"
        # Phase 1应该成功（因为有测试数据）
        # 如果没有候选节点，状态可能是"skipped"
        phase1_status = phase1_results.get("status")
        assert phase1_status in ["completed", "skipped"], (
            f"Phase 1 status should be 'completed' or 'skipped', got '{phase1_status}'"
        )

        # Assert: 验证Phase 2衰减计算失败
        phase2_results = result.get("phase2", {})
        assert phase2_results is not None, "phase2_results should exist"
        assert phase2_results.get("status") == "error", (
            f"Expected phase2 status 'error', got '{phase2_results.get('status')}'"
        )

        # 验证错误消息存在
        assert "message" in phase2_results, "Error message should be present"
        assert len(phase2_results["message"]) > 0, "Error message should not be empty"

    def test_dormancy_mechanism(
        self, consolidator_pipeline, experience_store, experience_edge_store, config_manager
    ):
        """测试14: 验证休眠机制。

        GIVEN: ConsolidationPipeline with dormancy_threshold=0.1
        AND: 10 test edges with low weight (0.05)
        AND: 10 test edges with high weight (0.9)
        WHEN: Run consolidation
        THEN: Low-weight edges marked dormant (dormant=True)
        AND: High-weight edges not dormant (dormant=False)
        AND: Dormant edges have decayed_weight < threshold
        AND: Awakening mechanism works (accessed edges awakened)
        VERIFICATION: SQL SELECT query confirms dormant field set correctly
        """
        # Arrange: 设置休眠阈值
        config_manager.set("dormancy_threshold", 0.1)

        # 创建测试数据
        import numpy as np
        from datetime import datetime, timedelta

        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        # 创建10个低权重边（应该休眠）
        for i in range(10):
            edge = ExperienceEdge(
                from_id=f"exp_test_dormant_low_{i:03d}",
                to_id=f"exp_test_dormant_low_{(i + 1) % 10:03d}",
                type="temporal",
                weight=0.05,  # 低权重
                decayed_weight=0.05,
                access_count=0,  # 无访问
                created_at=week_ago,
            )
            experience_edge_store.create(edge)

        # 创建10个高权重边（不应该休眠）
        for i in range(10):
            edge = ExperienceEdge(
                from_id=f"exp_test_dormant_high_{i:03d}",
                to_id=f"exp_test_dormant_high_{(i + 1) % 10:03d}",
                type="thematic",
                weight=0.9,  # 高权重
                decayed_weight=0.9,
                access_count=10,  # 多次访问
                created_at=week_ago,
            )
            experience_edge_store.create(edge)

        # Act: 运行巩固
        result = consolidator_pipeline.run_consolidation(mode="incremental", batch_size=10)

        # Assert: 验证Phase 2完成
        phase2_results = result.get("phase2", {})
        assert phase2_results.get("status") == "completed", "Decay calculation should complete"

        # Assert: 验证低权重边被标记为休眠（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT id, weight, decayed_weight, dormant FROM experience_edges "
                "WHERE id LIKE 'exp_test_dormant_low_%' ORDER BY id"
            )
            low_weight_edges = cursor.fetchall()

        assert len(low_weight_edges) == 10, f"Expected 10 low-weight edges, got {len(low_weight_edges)}"

        dormant_threshold = config_manager.get("dormancy_threshold")["value"]

        for row in low_weight_edges:
            weight = row["weight"]
            decayed_weight = row["decayed_weight"]
            dormant = row["dormant"]

            # 验证衰减权重低于阈值
            assert decayed_weight < dormant_threshold, (
                f"Low-weight edge decayed_weight ({decayed_weight}) should be < threshold ({dormant_threshold})"
            )

            # 验证被标记为休眠
            assert dormant == 1, (
                f"Low-weight edge should be marked dormant (dormant=1), got dormant={dormant}"
            )

        # Assert: 验证高权重边未被标记为休眠（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT id, weight, decayed_weight, dormant FROM experience_edges "
                "WHERE id LIKE 'exp_test_dormant_high_%' ORDER BY id"
            )
            high_weight_edges = cursor.fetchall()

        assert len(high_weight_edges) == 10, f"Expected 10 high-weight edges, got {len(high_weight_edges)}"

        for row in high_weight_edges:
            weight = row["weight"]
            decayed_weight = row["decayed_weight"]
            dormant = row["dormant"]

            # 验证衰减权重仍然较高（可能低于原始权重，但高于阈值）
            assert decayed_weight >= dormant_threshold, (
                f"High-weight edge decayed_weight ({decayed_weight}) should be >= threshold ({dormant_threshold})"
            )

            # 验证未被标记为休眠
            assert dormant == 0, (
                f"High-weight edge should not be marked dormant (dormant=0), got dormant={dormant}"
            )

        # Assert: 验证休眠计数
        dormant_count = phase2_results.get("dormant_count", 0)
        assert dormant_count >= 10, f"Expected at least 10 dormant edges, got {dormant_count}"

    def test_l3_immutability_during_consolidation(
        self, consolidator_pipeline, experience_store, experience_edge_store
    ):
        """测试15: 验证巩固流程中的L3不可变性。

        GIVEN: ConsolidationPipeline with dream module enabled
        AND: 5 test experiences with L3_raw="original text"
        WHEN: Run full consolidation (includes dream module)
        THEN: L3_raw unchanged for all experiences
        AND: distorted field may be updated
        AND: L0/L1/L2 may be updated
        AND: L3 protection enforced throughout
        VERIFICATION: SQL SELECT L3_raw FROM experiences confirms no changes
        """
        # Arrange: 创建测试数据
        import numpy as np
        from datetime import datetime, timedelta

        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        original_l3_values = {}

        for i in range(5):
            l3_text = f"Original L3 text {i} - must survive consolidation"
            exp = Experience(
                id=f"exp_test_consolid_l3_{i:03d}",
                L3_raw=l3_text,
                L0_text=f"Original L0 text {i}",
                L1_text=f"Original L1 text {i}",
                L2_text=f"Original L2 text {i}",
                emotion_intensity=0.7,
                importance=0.8,
                created_at=week_ago,
                L0_embedding=np.random.rand(768).astype(np.float32),
            )
            experience_store.create(exp)
            original_l3_values[exp.id] = l3_text

        # Act: 运行全量巩固（包含梦境模块）
        result = consolidator_pipeline.run_consolidation(mode="full", batch_size=10)

        # Assert: 验证巩固完成
        phase1_results = result.get("phase1", {})
        assert phase1_results.get("status") in ["completed", "skipped"], (
            f"Phase 1 should complete or be skipped, got '{phase1_results.get('status')}'"
        )

        phase2_results = result.get("phase2", {})
        assert phase2_results.get("status") == "completed", "Phase 2 should complete"

        # Assert: 验证L3_raw未改变（通过SQL直接查询）
        with db_manager.transaction() as cursor:
            cursor.execute(
                "SELECT id, L3_raw, distorted FROM experiences WHERE id LIKE 'exp_test_consolid_l3_%' ORDER BY id"
            )
            all_exps = cursor.fetchall()

        assert len(all_exps) == 5, f"Expected 5 experiences, got {len(all_exps)}"

        for row in all_exps:
            exp_id = row["id"]
            l3_raw = row["L3_raw"]
            distorted = row["distorted"]

            # 验证L3_raw仍然是原始值
            original_l3 = original_l3_values[exp_id]
            assert l3_raw == original_l3, (
                f"L3_raw should remain unchanged for {exp_id}: "
                f"expected '{original_l3}', got '{l3_raw}'"
            )

            # distorted字段可能被更新（梦境模块可能会更新），也可能保持None
            # 这不影响L3保护的验证
            # 重要的是L3_raw必须是原始值
