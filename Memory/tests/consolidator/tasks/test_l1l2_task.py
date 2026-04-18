"""L1/L2深层提取任务测试。"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import tempfile
import os

from Memory.consolidator.tasks.l1l2_task import extract_l1l2
from Memory.storage.experience_store import Experience
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
    store.update_l1l2 = Mock(return_value=True)
    return store


@pytest.fixture
def sample_experiences():
    """创建测试用的体验节点。"""
    return [
        Experience(
            id="exp_001",
            L3_raw="今天和朋友去爬山，风景很美，聊了很多话题",
            L0_text="和朋友爬山看到美景",
            L1_text=None,  # 未提取L1/L2
            L2_text=None,
            importance=0.7,
        ),
        Experience(
            id="exp_002",
            L3_raw="学习了Python的asyncio模块",
            L0_text="学习asyncio",
            L1_text="了解了事件循环和协程",
            L2_text="技术提升",
            importance=0.8,
        ),
        Experience(
            id="exp_003",
            L3_raw="简单的日常记录",
            L0_text="日常记录",
            L1_text=None,
            L2_text=None,
            importance=0.3,  # 重要性低于阈值
        ),
    ]


@pytest.fixture
def temp_prompt_template():
    """创建临时prompt模板文件。"""
    prompt_content = """你是AI的记忆深化系统。为以下L0摘要生成更详细的L1/L2记忆。

L0摘要：
{l0_summary}

原始记录：
{l3_full}

要求：
- L1：补充关键细节（说了什么、做了什么、结果如何）
- L2：提炼意义和感受（为什么重要、AI的思考）
- 保持第一人称主观视角
- 不编造信息，只基于已有内容

返回JSON：
```json
{{
  "l1_memory": "L1详细记忆（50-100字）",
  "l2_meaning": "L2意义提炼（30-50字）"
}}
```
"""
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    temp_file.write(prompt_content)
    temp_file.close()

    yield temp_file.name

    # 清理
    os.unlink(temp_file.name)


class TestExtractL1L2:
    """测试extract_l1l2函数。"""

    def test_skip_existing_l1l2(self, sample_experiences, mock_llm_client, mock_experience_store):
        """测试1：跳过已有L1和L2的节点。"""
        # exp_002已有L1和L2，应该被跳过
        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
        )

        # 验证：只有exp_001和exp_003需要处理，但exp_003会被跳过（低重要性）
        # exp_002已有L1/L2，直接跳过
        assert result["skipped_count"] >= 1  # 至少跳过exp_002
        assert result["total_count"] == 3

    def test_skip_low_importance(self, sample_experiences, mock_llm_client, mock_experience_store):
        """测试2：跳过importance<min_importance的节点。"""
        # Mock LLM返回
        mock_llm_client.call_with_retry = Mock(
            return_value='{"l1_memory": "测试L1", "l2_meaning": "测试L2"}'
        )

        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
        )

        # exp_003 importance=0.3 < 0.5，应该被跳过
        assert result["skipped_count"] >= 1  # exp_003被跳过
        # 验证exp_003没有被更新
        for call in mock_experience_store.update_l1l2.call_args_list:
            assert call[1]["experience_id"] != "exp_003"

    def test_successful_l1l2_update(
        self, sample_experiences, mock_llm_client, mock_experience_store
    ):
        """测试3：LLM调用成功更新L1_text和L2_text。"""
        # Mock LLM返回
        mock_llm_client.call_with_retry = Mock(
            return_value='{"l1_memory": "和朋友爬山聊了很多话题，心情舒畅", "l2_meaning": "社交互动带来积极情绪"}'
        )

        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
        )

        # 验证：至少有一个节点被更新（exp_001）
        assert result["updated_count"] >= 1
        # 验证update_l1l2被调用
        assert mock_experience_store.update_l1l2.call_count >= 1

        # 验证调用参数
        first_call = mock_experience_store.update_l1l2.call_args_list[0]
        assert first_call[1]["l1_text"] == "和朋友爬山聊了很多话题，心情舒畅"
        assert first_call[1]["l2_meaning"] == "社交互动带来积极情绪"

    def test_return_statistics(self, sample_experiences, mock_llm_client, mock_experience_store):
        """测试4：返回统计包含updated_count和skipped_count。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"l1_memory": "L1", "l2_meaning": "L2"}'
        )

        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
        )

        # 验证返回的统计信息
        assert "updated_count" in result
        assert "skipped_count" in result
        assert "failed_count" in result
        assert "total_count" in result
        assert result["total_count"] == 3

    def test_llm_failure_continue(self, sample_experiences, mock_llm_client, mock_experience_store):
        """测试5：LLM调用失败记录错误但继续处理下一个节点。"""
        # 第一次调用失败，第二次成功
        mock_llm_client.call_with_retry = Mock(
            side_effect=[Exception("LLM API error"), '{"l1_memory": "L1", "l2_meaning": "L2"}']
        )

        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
        )

        # 验证：有一个失败，但处理继续
        assert result["failed_count"] >= 1
        # 验证仍然有成功的更新
        assert (
            result["updated_count"] + result["skipped_count"] + result["failed_count"]
            == result["total_count"]
        )

    def test_prompt_template_loading(
        self, sample_experiences, mock_llm_client, mock_experience_store, temp_prompt_template
    ):
        """测试6：Prompt模板正确加载和格式化。"""
        mock_llm_client.call_with_retry = Mock(
            return_value='{"l1_memory": "L1", "l2_meaning": "L2"}'
        )

        # 使用临时模板文件
        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            prompt_template_path=temp_prompt_template,
        )

        # 验证LLM被调用
        assert mock_llm_client.call_with_retry.call_count >= 1

        # 验证prompt包含正确的占位符
        call_args = mock_llm_client.call_with_retry.call_args_list[0]
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt")
        assert "和朋友爬山看到美景" in prompt or "和朋友爬山，风景很美" in prompt
        assert "今天和朋友去爬山" in prompt

    def test_empty_experience_list(self, mock_llm_client, mock_experience_store):
        """测试7：空体验列表处理。"""
        result = extract_l1l2(
            experiences=[], llm_client=mock_llm_client, experience_store=mock_experience_store
        )

        assert result["updated_count"] == 0
        assert result["skipped_count"] == 0
        assert result["failed_count"] == 0
        assert result["total_count"] == 0

    def test_prompt_template_not_found(
        self, sample_experiences, mock_llm_client, mock_experience_store
    ):
        """测试8：Prompt模板文件不存在时返回错误。"""
        result = extract_l1l2(
            experiences=sample_experiences,
            llm_client=mock_llm_client,
            experience_store=mock_experience_store,
            prompt_template_path="/nonexistent/path/prompt.txt",
        )

        # 验证：全部跳过，返回错误
        assert result["updated_count"] == 0
        assert result["skipped_count"] == 3
        assert result["error"] == "prompt_template_not_found"
