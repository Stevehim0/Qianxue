"""ProfileManager Gap Closure测试。

测试验证ProfileManager和RecallManager的个人档案系统集成差距。
这是Gap Closure测试的一部分，验证当前broken state。

Gap Coverage:
- Gap 4: PROFILE-04需求未实现（update_profiles占位实现）
- Gap 5: PROFILE-08部分实现（单人加载实现，群聊未实现）
- Gap 6: 群聊场景支持缺失
- Gap 7: 巩固层集成缺失

Reference: .planning/phases/10-召回层/10-VERIFICATION.md
"""

import pytest
from unittest.mock import Mock, MagicMock, call, patch
from datetime import datetime, timedelta

from Memory.recall.profile_manager import ProfileManager
from Memory.recall.manager import RecallManager
from Memory.recall.profile_data import InteractionStyle
from Memory.storage.profile_store import ProfileStore, PersonProfile as StoreProfile
from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.storage.entity_store import EntityStore


def _make_store_profile(name, style_dict, notes=None):
    """辅助函数：创建 profile_store.PersonProfile 对象。"""
    basic = {"name": name, "type": "person"}
    if notes:
        basic["notes"] = notes
    return StoreProfile(
        id=f"profile_{name}",
        basic=basic,
        interaction_style=style_dict,
        preferences={},
    )


def test_update_profiles_calls_dream_ai():
    """验证update_profiles()调用梦境AI分析对话历史（Gap 4修复）。

    测试步骤：
    1. Mock ProfileStore.list_all()返回测试档案（StoreProfile，interaction_style 为 Dict）
    2. Mock ExperienceStore查询对话历史
    3. Mock LLM客户端返回梦境AI响应
    4. 验证LLM被调用且ProfileStore.update_interaction_style()被调用

    Expected: update_profiles()调用梦境AI并更新ProfileStore
    """
    import json

    # 创建Mock stores
    mock_profile_store = Mock(spec=ProfileStore)
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_entity_store = Mock(spec=EntityStore)

    # Mock返回数据（使用 StoreProfile，interaction_style 为 Dict）
    test_profile = _make_store_profile(
        "张三",
        {"warmth": 0.8, "formality": 0.3, "humor": 0.7,
         "proactivity": 0.6, "directness": 0.5, "boundaries": 0.4},
    )

    mock_profile_store.list_all.return_value = [test_profile]

    # Mock LLM客户端
    mock_llm_client = Mock()
    mock_llm_client.call.return_value = json.dumps({
        "entity_name": "张三",
        "analysis": {
            "interaction_pattern": "用户偏好边界感",
            "emotional_trend": "用户在对话中表达了对空间的需求",
            "ai_self_reflection": "应该收敛warmth"
        },
        "new_interaction_style": {
            "warmth": 0.6,
            "formality": 0.5,
            "humor": 0.5,
            "proactivity": 0.5,
            "directness": 0.5,
            "boundaries": 0.7
        },
        "reasoning": "用户明确反对热情，收敛warmth。根据'只收敛不迎合'原则，调整warmth和boundaries。"
    })

    # 创建ProfileManager
    from Memory.llm.factory import LLMFactory
    with patch.object(LLMFactory, 'create_client', return_value=mock_llm_client):
        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        # Mock _query_conversation_history返回对话历史
        with patch.object(profile_manager, '_query_conversation_history', return_value=[
            {
                "role": "user",
                "content": "用户说：你太热情了",
                "timestamp": "2026-04-01T10:00:00Z",
                "emotion_category": "frustration",
                "intensity": 0.8
            }
        ]):
            # 调用update_profiles
            profile_manager.update_profiles()

            # 验证LLM被调用
            assert mock_llm_client.call.called
            call_args = mock_llm_client.call.call_args
            assert "prompt" in call_args.kwargs
            assert "张三" in call_args.kwargs["prompt"]
            assert "只收敛不迎合" in call_args.kwargs["prompt"]

            # 验证ProfileStore被更新（使用 profile_id 格式 + Dict）
            mock_profile_store.update_interaction_style.assert_called_once()
            update_call = mock_profile_store.update_interaction_style.call_args
            assert update_call[0][0] == "profile_张三"
            assert update_call[0][1]["warmth"] == 0.6
            assert update_call[0][1]["boundaries"] == 0.7

    print("✓ Gap 4修复验证通过：PROFILE-04需求已实现")
    print("  - update_profiles()调用梦境AI分析对话历史")
    print("  - 应用'只收敛不迎合'规则（warmth降低，boundaries提高）")
    print("  - ProfileStore.update_interaction_style()被调用")


def test_convergence_rule_converges_when_user_objects():
    """验证收敛规则：用户明确反对时调整相应维度（D-02实现）。"""
    import json

    mock_profile_store = Mock(spec=ProfileStore)
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_entity_store = Mock(spec=EntityStore)

    test_profile = _make_store_profile(
        "李四",
        {"warmth": 0.8, "formality": 0.3, "humor": 0.7,
         "proactivity": 0.6, "directness": 0.5, "boundaries": 0.4},
    )
    mock_profile_store.list_all.return_value = [test_profile]

    mock_llm_client = Mock()
    mock_llm_client.call.return_value = json.dumps({
        "entity_name": "李四",
        "analysis": {
            "interaction_pattern": "用户明确表达需要空间",
            "emotional_trend": "用户对过度热情感到frustration",
            "ai_self_reflection": "应该收敛warmth，提高boundaries"
        },
        "new_interaction_style": {
            "warmth": 0.6,
            "formality": 0.3,
            "humor": 0.7,
            "proactivity": 0.6,
            "directness": 0.5,
            "boundaries": 0.7
        },
        "reasoning": "用户明确表示'你太热情了，我需要一些空间'。收敛warmth并提高boundaries。"
    })

    from Memory.llm.factory import LLMFactory
    with patch.object(LLMFactory, 'create_client', return_value=mock_llm_client):
        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        with patch.object(profile_manager, '_query_conversation_history', return_value=[
            {
                "role": "user",
                "content": "你太热情了，我需要一些空间",
                "timestamp": "2026-04-01T10:00:00Z",
                "emotion_category": "frustration",
                "intensity": 0.8
            }
        ]):
            profile_manager.update_profiles()

            update_call = mock_profile_store.update_interaction_style.call_args
            new_style = update_call[0][1]
            assert new_style["warmth"] == 0.6, f"warmth应该为0.6，实际为{new_style['warmth']}"
            assert new_style["boundaries"] == 0.7, f"boundaries应该为0.7，实际为{new_style['boundaries']}"

    print("✓ 收敛规则验证通过：用户明确反对时调整相应维度")


def test_no_pandering_rule_does_not_increase_when_user_likes():
    """验证不迎合规则：用户表达喜欢时不加强（D-02实现）。"""
    import json

    mock_profile_store = Mock(spec=ProfileStore)
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_entity_store = Mock(spec=EntityStore)

    test_profile = _make_store_profile(
        "王五",
        {"warmth": 0.6, "formality": 0.3, "humor": 0.7,
         "proactivity": 0.6, "directness": 0.5, "boundaries": 0.5},
    )
    mock_profile_store.list_all.return_value = [test_profile]

    mock_llm_client = Mock()
    mock_llm_client.call.return_value = json.dumps({
        "entity_name": "王五",
        "analysis": {
            "interaction_pattern": "用户表达喜欢当前相处方式",
            "emotional_trend": "用户情感positive，表示满意",
            "ai_self_reflection": "用户喜欢不代表要加强"
        },
        "new_interaction_style": {
            "warmth": 0.6,
            "formality": 0.3,
            "humor": 0.7,
            "proactivity": 0.6,
            "directness": 0.5,
            "boundaries": 0.5
        },
        "reasoning": "用户表达喜欢，但根据'不迎合'原则保持不变。"
    })

    from Memory.llm.factory import LLMFactory
    with patch.object(LLMFactory, 'create_client', return_value=mock_llm_client):
        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        with patch.object(profile_manager, '_query_conversation_history', return_value=[
            {
                "role": "user",
                "content": "我喜欢你这样幽默",
                "timestamp": "2026-04-01T10:00:00Z",
                "emotion_category": "joy",
                "intensity": 0.7
            }
        ]):
            profile_manager.update_profiles()

            update_call = mock_profile_store.update_interaction_style.call_args
            new_style = update_call[0][1]
            assert new_style["humor"] == 0.7
            assert new_style["warmth"] == 0.6
            assert new_style["formality"] == 0.3

    print("✓ 不迎合规则验证通过：用户表达喜欢时不加强")


def test_recall_manager_single_profile_loading():
    """验证RecallManager.recall()支持单聊场景档案加载（Gap 5修复）。"""
    mock_profile_mgr = Mock()
    mock_profile_mgr.load_profile.return_value = "## 关于张三\n你们的关系: 朋友"

    mock_entity_store = Mock(spec=EntityStore)
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_edge_store = Mock()
    mock_vector_store = Mock()
    mock_embedding_service = Mock()

    recall_mgr = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=mock_edge_store,
        vector_store=mock_vector_store,
        embedding_service=mock_embedding_service,
        profile_manager=mock_profile_mgr,
    )

    # Mock 向量检索返回空结果（避免 Mock 不可下标问题）
    mock_vector_store.query_experience.return_value = {"ids": [[]], "distances": [[]]}
    mock_vector_store.query_entity.return_value = {"ids": [[]], "distances": [[]]}

    context = {"profiles_to_load": ["张三"]}
    with patch.object(recall_mgr.trigger_detector, "should_trigger", return_value=True):
        with patch.object(recall_mgr.trigger_detector, "extract_keywords", return_value=["张三"]):
            results = recall_mgr.recall("张三今天来了", context)

    assert mock_profile_mgr.load_profile.call_count == 1
    assert "loaded_profiles" in context
    assert len(context["loaded_profiles"]) == 1
    assert "张三" in context["loaded_profiles"][0]

    print("✓ Gap 5修复验证通过：单聊场景档案加载")


def test_recall_manager_multi_profile_loading():
    """验证RecallManager.recall()支持群聊场景多档案加载（Gap 6修复）。"""
    mock_profile_mgr = Mock()
    mock_profile_mgr.load_profile.side_effect = [
        "## 关于张三\n你们的关系: 朋友",
        "## 关于李四\n你们的关系: 同事",
        "## 关于王五\n你们的关系: 家人",
    ]

    mock_entity_store = Mock(spec=EntityStore)
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_edge_store = Mock()
    mock_vector_store = Mock()
    mock_embedding_service = Mock()

    recall_mgr = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=mock_edge_store,
        vector_store=mock_vector_store,
        embedding_service=mock_embedding_service,
        profile_manager=mock_profile_mgr,
    )

    mock_vector_store.query_experience.return_value = {"ids": [[]], "distances": [[]]}
    mock_vector_store.query_entity.return_value = {"ids": [[]], "distances": [[]]}

    context = {"profiles_to_load": ["张三", "李四", "王五"]}
    with patch.object(recall_mgr.trigger_detector, "should_trigger", return_value=True):
        with patch.object(recall_mgr.trigger_detector, "extract_keywords", return_value=["张三"]):
            results = recall_mgr.recall("大家好", context)

    assert mock_profile_mgr.load_profile.call_count == 3
    assert "loaded_profiles" in context
    assert len(context["loaded_profiles"]) == 3
    assert any("张三" in p for p in context["loaded_profiles"])
    assert any("李四" in p for p in context["loaded_profiles"])
    assert any("王五" in p for p in context["loaded_profiles"])

    print("✓ Gap 6修复验证通过：群聊场景多档案加载")


def test_consolidation_pipeline_calls_update_profiles():
    """验证ConsolidationPipeline在巩固完成后调用update_profiles()（Gap 7修复）。"""
    mock_profile_mgr = Mock()
    mock_profile_mgr.update_profiles = Mock()

    mock_experience_store = Mock(spec=ExperienceStore)
    mock_experience_store.get_consolidation_candidates.return_value = []

    from Memory.consolidator.pipeline import ConsolidationPipeline
    consolidation_pipeline = ConsolidationPipeline(
        experience_store=mock_experience_store,
        profile_manager=mock_profile_mgr,
    )

    result = consolidation_pipeline.run_consolidation(mode="incremental")

    assert mock_profile_mgr.update_profiles.called
    assert "profile_update" in result
    assert result["profile_update"]["status"] == "completed"

    print("✓ Gap 7修复验证通过：ConsolidationPipeline集成update_profiles()")


def test_consolidation_without_profile_manager():
    """验证ConsolidationPipeline可以不提供profile_manager（向后兼容）。"""
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_experience_store.get_consolidation_candidates.return_value = []

    from Memory.consolidator.pipeline import ConsolidationPipeline
    consolidation_pipeline = ConsolidationPipeline(
        experience_store=mock_experience_store,
    )

    result = consolidation_pipeline.run_consolidation(mode="incremental")
    assert result is not None
    assert "profile_update" in result
    assert result["profile_update"]["status"] == "skipped"
    assert result["profile_update"]["reason"] == "no_profile_manager"

    print("✓ 向后兼容验证通过：ConsolidationPipeline可不提供profile_manager")


class TestProfileManagerUpdateLogic:
    """ProfileManager.update_profiles()更新逻辑的详细测试。"""

    @pytest.mark.skip(reason="Gap 4: 未实现 - 待13-03修复")
    def test_update_profiles_should_call_dream_ai(self, mock_profile_store, mock_experience_store, mock_entity_store):
        """验证update_profiles()应该调用梦境AI。"""
        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        profile_manager.update_profiles()
        mock_profile_store.update.assert_not_called()

    @pytest.mark.skip(reason="Gap 4: 未实现 - 待13-03修复")
    def test_update_profiles_convergence_rule(self, mock_profile_store, mock_experience_store, mock_entity_store):
        """验证'只收敛不迎合'规则。"""
        profile_manager = ProfileManager(
            profile_store=mock_profile_store,
            experience_store=mock_experience_store,
            entity_store=mock_entity_store,
        )

        mock_profile = _make_store_profile(
            "张三",
            {"warmth": 0.8, "formality": 0.3, "humor": 0.7,
             "proactivity": 0.6, "directness": 0.5, "boundaries": 0.4},
        )
        mock_profile_store.get_all.return_value = [mock_profile]

        profile_manager.update_profiles()
        mock_profile_store.update.assert_not_called()


def test_recall_manager_profile_loading_integration():
    """验证RecallManager.recall()集成档案加载功能（Gap 5和6修复）。"""
    mock_profile_manager = Mock(spec=ProfileManager)

    def mock_load_profile(name):
        return f"## 关于{name}\n相处方式: ..."

    mock_profile_manager.load_profile.side_effect = mock_load_profile

    mock_entity_store = Mock(spec=EntityStore)
    mock_experience_store = Mock(spec=ExperienceStore)
    mock_edge_store = Mock()
    mock_vector_store = Mock()
    mock_embedding_service = Mock()

    recall_manager = RecallManager(
        experience_store=mock_experience_store,
        entity_store=mock_entity_store,
        edge_store=mock_edge_store,
        vector_store=mock_vector_store,
        embedding_service=mock_embedding_service,
        profile_manager=mock_profile_manager,
    )

    # Mock 向量检索返回空结果
    mock_vector_store.query_experience.return_value = {"ids": [[]], "distances": [[]]}
    mock_vector_store.query_entity.return_value = {"ids": [[]], "distances": [[]]}

    context = {
        "profiles_to_load": ["张三"],
        "recent_history": [],
        "ai_state": {},
        "current_time": datetime.now().isoformat(),
    }

    with patch.object(recall_manager.trigger_detector, "should_trigger", return_value=True):
        with patch.object(recall_manager.trigger_detector, "extract_keywords", return_value=["张三"]):
            results = recall_manager.recall("张三最近怎么样", context)

    assert "loaded_profiles" in context
    assert len(context["loaded_profiles"]) == 1
    assert mock_profile_manager.load_profile.called

    print("✓ Gap 5和6修复验证通过：RecallManager完整实现档案加载逻辑")
