"""LLM服务集成测试。

这些测试需要真实的API密钥才能运行。默认情况下，这些测试会被跳过。
要运行这些测试，需要设置环境变量 REAL_API_TEST=true 和相应的API密钥。

运行集成测试：
```bash
# 设置环境变量
export REAL_API_TEST=true
export LLM_API_KEY="your-qianwen-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"

# 运行所有测试（包括集成测试）
pytest tests/test_llm_integration.py -v

# 只运行集成测试
pytest tests/test_llm_integration.py -v -m integration
```
"""

import pytest
import os

# 标记集成测试
pytestmark = pytest.mark.integration


def is_real_api_test_enabled():
    """检查是否启用真实API测试。"""
    return os.getenv("REAL_API_TEST", "false").lower() == "true"


def has_qianwen_api_key():
    """检查是否有千问API密钥。"""
    return bool(os.getenv("LLM_API_KEY") or os.getenv("QIANWEN_API_KEY"))


def has_deepseek_api_key():
    """检查是否有DeepSeek API密钥。"""
    return bool(os.getenv("DEEPSEEK_API_KEY"))


class TestQianwenIntegration:
    """千问客户端集成测试（需要真实API密钥）。"""

    @pytest.fixture(scope="class")
    def qianwen_client(self):
        """创建千问客户端实例。"""
        from Memory.llm import QianwenClient

        api_key = os.getenv("LLM_API_KEY") or os.getenv("QIANWEN_API_KEY")
        if not api_key:
            pytest.skip("Qianwen API key not set")

        return QianwenClient(api_key=api_key)

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_qianwen_api_key(),
        reason="Real API test not enabled or Qianwen API key not set",
    )
    def test_qianwen_simple_call(self, qianwen_client):
        """测试简单的千问API调用。"""
        response = qianwen_client.call(prompt="请用一句话介绍北京", response_format="text")

        assert isinstance(response, str)
        assert len(response) > 0
        assert "北京" in response

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_qianwen_api_key(),
        reason="Real API test not enabled or Qianwen API key not set",
    )
    def test_qianwen_json_response(self, qianwen_client):
        """测试千问API返回JSON格式。"""
        response = qianwen_client.call(
            prompt="请返回一个JSON对象，包含city字段（值为'北京'）和temperature字段（值为25）",
            response_format="json",
        )

        assert isinstance(response, dict)
        assert "city" in response
        assert response["city"] == "北京"
        assert "temperature" in response

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_qianwen_api_key(),
        reason="Real API test not enabled or Qianwen API key not set",
    )
    def test_qianwen_with_system_prompt(self, qianwen_client):
        """测试带system_prompt的千问API调用。"""
        response = qianwen_client.call(
            prompt="介绍一下你自己",
            system_prompt="你是一个专业的AI助手，请用简洁的语言回答",
            response_format="text",
        )

        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_qianwen_api_key(),
        reason="Real API test not enabled or Qianwen API key not set",
    )
    def test_qianwen_with_retry(self, qianwen_client):
        """测试带重试机制的千问API调用。"""
        response = qianwen_client.call_with_retry(
            prompt="What is the capital of China?", response_format="text"
        )

        assert isinstance(response, str)
        assert len(response) > 0


class TestDeepSeekIntegration:
    """DeepSeek客户端集成测试（需要真实API密钥）。"""

    @pytest.fixture(scope="class")
    def deepseek_client(self):
        """创建DeepSeek客户端实例。"""
        from Memory.llm import DeepSeekClient

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            pytest.skip("DeepSeek API key not set")

        return DeepSeekClient(api_key=api_key)

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_deepseek_api_key(),
        reason="Real API test not enabled or DeepSeek API key not set",
    )
    def test_deepseek_simple_call(self, deepseek_client):
        """测试简单的DeepSeek API调用。"""
        response = deepseek_client.call(
            prompt="What is the capital of France?", response_format="text"
        )

        assert isinstance(response, str)
        assert len(response) > 0
        # 可能是"Paris"或包含"Paris"的句子
        assert "Paris" in response or "capital" in response.lower()

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_deepseek_api_key(),
        reason="Real API test not enabled or DeepSeek API key not set",
    )
    def test_deepseek_json_response(self, deepseek_client):
        """测试DeepSeek API返回JSON格式。"""
        response = deepseek_client.call(
            prompt="Return a JSON object with city field (value: 'London') and temperature field (value: 15)",
            response_format="json",
        )

        assert isinstance(response, dict)
        assert "city" in response
        assert response["city"] == "London"
        assert "temperature" in response

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_deepseek_api_key(),
        reason="Real API test not enabled or DeepSeek API key not set",
    )
    def test_deepseek_with_system_prompt(self, deepseek_client):
        """测试带system_prompt的DeepSeek API调用。"""
        response = deepseek_client.call(
            prompt="Introduce yourself",
            system_prompt="You are a professional AI assistant. Answer concisely.",
            response_format="text",
        )

        assert isinstance(response, str)
        assert len(response) > 0


class TestLLMFactoryIntegration:
    """LLM工厂集成测试（需要真实API密钥）。"""

    @pytest.mark.skipif(not is_real_api_test_enabled(), reason="Real API test not enabled")
    def test_factory_create_qianwen_client(self):
        """测试工厂创建千问客户端。"""
        from Memory.llm import LLMFactory

        if not has_qianwen_api_key():
            pytest.skip("Qianwen API key not set")

        client = LLMFactory.create_client(provider="qianwen")
        assert client.provider == "qianwen"

    @pytest.mark.skipif(not is_real_api_test_enabled(), reason="Real API test not enabled")
    def test_factory_create_deepseek_client(self):
        """测试工厂创建DeepSeek客户端。"""
        from Memory.llm import LLMFactory

        if not has_deepseek_api_key():
            pytest.skip("DeepSeek API key not set")

        client = LLMFactory.create_client(provider="deepseek")
        assert client.provider == "deepseek"


class TestErrorHandlingIntegration:
    """错误处理集成测试（需要真实API密钥）。"""

    @pytest.fixture(scope="class")
    def qianwen_client(self):
        """创建千问客户端实例。"""
        from Memory.llm import QianwenClient

        api_key = os.getenv("LLM_API_KEY") or os.getenv("QIANWEN_API_KEY")
        if not api_key:
            pytest.skip("Qianwen API key not set")

        return QianwenClient(api_key=api_key)

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_qianwen_api_key(),
        reason="Real API test not enabled or Qianwen API key not set",
    )
    def test_invalid_api_key(self):
        """测试无效API密钥。"""
        from Memory.llm import QianwenClient

        client = QianwenClient(api_key="invalid-key-12345")

        with pytest.raises(Exception):  # 可能是HTTPError或其他异常
            client.call("Test prompt")

    @pytest.mark.skipif(
        not is_real_api_test_enabled() or not has_qianwen_api_key(),
        reason="Real API test not enabled or Qianwen API key not set",
    )
    def test_timeout_handling(self, qianwen_client):
        """测试超时处理。"""
        # 设置非常短的超时时间
        qianwen_client.timeout = 0.001  # 1毫秒

        with pytest.raises((TimeoutError, Exception)):
            qianwen_client.call(
                prompt="Please generate a very long response about the history of China",
                max_tokens=10000,
            )
