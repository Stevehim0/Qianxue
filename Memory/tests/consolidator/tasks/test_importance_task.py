"""重要性估值任务测试。"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path
import tempfile
import os

from Memory.consolidator.tasks.importance_task import calculate_importance
from Memory.storage.experience_store import Experience
from Memory.storage.experience_edge_store import ExperienceEdge
from Memory.llm.base import BaseLLMClient


@pytest.fixture
def mock_llm_client():
    """Mock LLM客户端。"""
    client = Mock(spec=BaseLLMClient)
    return client


@pytest.fixture
def mock_experience_store():
    """Mock体验存储。"""
    store = Mock()
    store.update_importance = Mock(return_value=True)
    return store


@pytest.fixture
def mock_edge_store():
    """Mock体验边存储。"""
    store = Mock()
    return store


@pytest.fixture
def sample_experiences():
    """创建测试用的体验节点。"""
    return [
        Experience(
            id="exp_001",
            L3_raw="学习了Python asyncio模块",
            L0_text="学习asyncio",
            emotion_intensity=0.7,
        ),
        Experience(id="exp_002", L3_raw="和朋友聊天", L0_text="社交互动", emotion_intensity=0.5),
        Experience(
            id="exp_003", L3_raw="日常记录", L0_text="日常", emotion_intensity=None  # 无情感数据
        ),
    ]


@pytest.fixture
def temp_prompt_template():
    """创建临时prompt模板文件。"""
    prompt_content = """你是一个记忆重要性评估系统。

评估以下体验的重要程度：

体验摘要：{l0_summary}
完整内容：{l3_full}

评估维度：
1. 新颖度（novelty）：这段经历是否包含新的信息、技能或体验？
2. 后果影响（consequence）：这段经历对AI未来有何影响？

返回JSON：
```json
{{
  "novelty": 0.0-1.0,
  "consequence": 0.0-1.0,
  "reason": "简要说明"
}}
```
"""
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    temp_file.write(prompt_content)
    temp_file.close()

    yield temp_file.name

    os.unlink(temp_file.name)


class TestCalculateImportance:
    """测试calculate_importance函数。"""

    def test_importance_formula(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试1：计算四因子估值（novelty×consequence×connectivity×emotion）。"""
        # Mock LLM返回
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 0.8, "consequence": 0.7, "reason": "新技能学习"}'
        )

        # Mock边数据（exp_001有3条边）
        mock_edge_store.get_by_from = Mock(
            return_value=[
                ExperienceEdge(from_id="exp_001", to_id="exp_002", type="temporal"),
                ExperienceEdge(from_id="exp_001", to_id="exp_003", type="thematic"),
                ExperienceEdge(from_id="exp_001", to_id="exp_004", type="causal"),
            ]
        )

        result = calculate_importance(
            experiences=sample_experiences[:1],  # 只测试exp_001
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证：至少更新了一个节点
        assert result["updated_count"] >= 1

        # 验证update_importance被调用
        assert mock_experience_store.update_importance.call_count >= 1

        # 验证importance值在合理范围内
        call_args = mock_experience_store.update_importance.call_args_list[0]
        importance = call_args[1]["importance"]
        assert 0.0 <= importance <= 1.0

    def test_connectivity_calculation(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试2：connectivity基于已有边数量统计。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 0.5, "consequence": 0.5, "reason": "test"}'
        )

        # 测试无边的情况
        mock_edge_store.get_by_from = Mock(return_value=[])

        result = calculate_importance(
            experiences=sample_experiences[:1],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证：仍然成功处理（connectivity有基础值0.3）
        assert result["updated_count"] >= 1

        # 测试有边的情况（5条边）
        mock_edge_store.get_by_from = Mock(
            return_value=[
                ExperienceEdge(from_id="exp_001", to_id=f"exp_00{i}", type="temporal")
                for i in range(2, 7)
            ]
        )

        result2 = calculate_importance(
            experiences=sample_experiences[:1],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        assert result2["updated_count"] >= 1

    def test_emotion_conversion(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试3：emotion基于emotion_intensity转换。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 0.5, "consequence": 0.5, "reason": "test"}'
        )
        mock_edge_store.get_by_from = Mock(return_value=[])

        # 测试有情感强度的节点（exp_001: 0.7）
        result = calculate_importance(
            experiences=sample_experiences[:1],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        assert result["updated_count"] >= 1

        # 测试无情感强度的节点（exp_003: None，应使用默认0.5）
        result2 = calculate_importance(
            experiences=sample_experiences[2:3],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        assert result2["updated_count"] >= 1

    def test_llm_evaluation(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试4：LLM评估novelty和consequence。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 0.9, "consequence": 0.8, "reason": "高度新颖"}'
        )
        mock_edge_store.get_by_from = Mock(return_value=[])

        result = calculate_importance(
            experiences=sample_experiences[:1],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证LLM被调用
        assert mock_llm_client.call_with_retry.call_count >= 1

        # 验证prompt包含正确的信息
        call_args = mock_llm_client.call_with_retry.call_args_list[0]
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt")
        assert "学习asyncio" in prompt or "学习了Python" in prompt

    def test_importance_update(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试5：最终importance更新到数据库。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 0.6, "consequence": 0.7, "reason": "test"}'
        )
        mock_edge_store.get_by_from = Mock(return_value=[])

        result = calculate_importance(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证所有节点都被更新
        assert result["updated_count"] == 3
        assert mock_experience_store.update_importance.call_count == 3

        # 验证每次调用都传入了experience_id和importance
        for call in mock_experience_store.update_importance.call_args_list:
            assert "experience_id" in call[1]
            assert "importance" in call[1]
            assert 0.0 <= call[1]["importance"] <= 1.0

    def test_return_statistics(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试6：返回处理统计。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 0.5, "consequence": 0.5, "reason": "test"}'
        )
        mock_edge_store.get_by_from = Mock(return_value=[])

        result = calculate_importance(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证返回的统计信息
        assert "updated_count" in result
        assert "total_count" in result
        assert "avg_importance" in result
        assert result["total_count"] == 3
        assert result["updated_count"] == 3
        assert 0.0 <= result["avg_importance"] <= 1.0

    def test_empty_experience_list(self, mock_llm_client, mock_experience_store, mock_edge_store):
        """测试7：空体验列表处理。"""
        result = calculate_importance(
            experiences=[],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        assert result["updated_count"] == 0
        assert result["total_count"] == 0
        assert result["avg_importance"] == 0.0

    def test_llm_failure_continue(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试8：LLM调用失败继续处理下一个节点。"""
        # 第一次调用失败，第二次成功
        mock_llm_client.call_with_retry = Mock(
            side_effect=[
                Exception("LLM API error"),
                '{"novelty": 0.5, "consequence": 0.5, "reason": "test"}',
            ]
        )
        mock_edge_store.get_by_from = Mock(return_value=[])

        result = calculate_importance(
            experiences=sample_experiences[:2],  # 只测试前两个
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证：第一个失败，第二个成功
        assert result["updated_count"] == 1

    def test_novelty_consequence_clamping(
        self, sample_experiences, mock_llm_client, mock_experience_store, mock_edge_store
    ):
        """测试9：novelty和consequence限制在[0,1]范围。"""
        # Mock返回超出范围的值
        mock_llm_client.call_with_retry = Mock(
            return_value='{"novelty": 1.5, "consequence": -0.2, "reason": "test"}'
        )
        mock_edge_store.get_by_from = Mock(return_value=[])

        result = calculate_importance(
            experiences=sample_experiences[:1],
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            experience_edge_store=mock_edge_store,
        )

        # 验证：仍然成功处理（值被限制在[0,1]）
        assert result["updated_count"] >= 1

        # 验证最终importance在合理范围内
        call_args = mock_experience_store.update_importance.call_args_list[0]
        importance = call_args[1]["importance"]
        assert 0.0 <= importance <= 1.0
