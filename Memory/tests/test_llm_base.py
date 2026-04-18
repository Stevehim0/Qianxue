"""LLM客户端基类测试。

测试 Memory.llm.base 模块的 BaseLLMClient 抽象基类：
- call_with_retry: 带重试机制的LLM调用
- 参数传递: system_prompt, temperature, max_tokens, response_format
- 错误处理: 重试逻辑、错误日志记录
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from Memory.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Mock LLM客户端用于测试。

    继承BaseLLMClient并实现call()方法。
    """

    def __init__(self, api_key=None, timeout=30, **kwargs):
        super().__init__(api_key, timeout, **kwargs)
        self.call_count = 0
        self.call_history = []

    def call(
        self,
        prompt: str,
        system_prompt=None,
        temperature=0.3,
        max_tokens=1000,
        response_format="json",
    ):
        """Mock call方法，记录调用历史。"""
        self.call_count += 1
        self.call_history.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            }
        )

        # 模拟成功返回
        return '{"result": "success"}'


class FailingMockLLMClient(BaseLLMClient):
    """Mock LLM客户端，模拟失败场景。"""

    def __init__(self, api_key=None, timeout=30, fail_times=2, **kwargs):
        super().__init__(api_key, timeout, **kwargs)
        self.fail_times = fail_times
        self.call_count = 0

    def call(
        self,
        prompt: str,
        system_prompt=None,
        temperature=0.3,
        max_tokens=1000,
        response_format="json",
    ):
        """Mock call方法，前N次失败，之后成功。"""
        self.call_count += 1

        if self.call_count <= self.fail_times:
            raise ConnectionError(f"Network error (attempt {self.call_count})")

        return '{"result": "success"}'


class AlwaysFailingMockLLMClient(BaseLLMClient):
    """Mock LLM客户端，始终失败。"""

    def call(
        self,
        prompt: str,
        system_prompt=None,
        temperature=0.3,
        max_tokens=1000,
        response_format="json",
    ):
        """Mock call方法，始终抛出异常。"""
        raise ConnectionError("Always fails")


class TestBaseLLMClient:
    """测试 BaseLLMClient 基类。"""

    def test_initialization(self):
        """测试客户端初始化。"""
        client = MockLLMClient(api_key="test-key", timeout=60)
        assert client.api_key == "test-key"
        assert client.timeout == 60
        assert client.provider == "mockllm"

    def test_initialization_with_defaults(self):
        """测试使用默认参数初始化。"""
        client = MockLLMClient()
        assert client.api_key is None
        assert client.timeout == 30
        assert client.provider == "mockllm"

    def test_call_is_abstract(self):
        """测试call方法是抽象的。"""
        with pytest.raises(TypeError):
            BaseLLMClient()


class TestCallWithRetry:
    """测试 call_with_retry 方法。"""

    def test_successful_call(self):
        """测试成功调用。"""
        client = MockLLMClient()
        result = client.call_with_retry("Test prompt")
        assert result == '{"result": "success"}'
        assert client.call_count == 1

    def test_call_with_all_parameters(self):
        """测试传递所有参数。"""
        client = MockLLMClient()
        result = client.call_with_retry(
            prompt="Test prompt",
            system_prompt="You are a helpful assistant",
            temperature=0.7,
            max_tokens=2000,
            response_format="text",
        )

        assert result == '{"result": "success"}'
        assert client.call_count == 1

        # 验证参数正确传递
        history = client.call_history[0]
        assert history["prompt"] == "Test prompt"
        assert history["system_prompt"] == "You are a helpful assistant"
        assert history["temperature"] == 0.7
        assert history["max_tokens"] == 2000
        assert history["response_format"] == "text"

    def test_retry_on_connection_error(self):
        """测试连接错误时重试。"""
        client = FailingMockLLMClient(fail_times=2)
        result = client.call_with_retry("Test prompt")

        assert result == '{"result": "success"}'
        assert client.call_count == 3  # 2次失败 + 1次成功

    def test_retry_exhausted(self):
        """测试重试耗尽。"""
        client = AlwaysFailingMockLLMClient()

        with pytest.raises(ConnectionError, match="Always fails"):
            client.call_with_retry("Test prompt")

    def test_default_parameters(self):
        """测试默认参数。"""
        client = MockLLMClient()
        result = client.call_with_retry("Test prompt")

        assert result == '{"result": "success"}'

        # 验证默认参数
        history = client.call_history[0]
        assert history["system_prompt"] is None
        assert history["temperature"] == 0.3
        assert history["max_tokens"] == 1000
        assert history["response_format"] == "json"

    def test_system_prompt_none(self):
        """测试system_prompt为None。"""
        client = MockLLMClient()
        result = client.call_with_retry("Test prompt", system_prompt=None)

        assert result == '{"result": "success"}'
        history = client.call_history[0]
        assert history["system_prompt"] is None

    def test_temperature_boundary(self):
        """测试temperature边界值。"""
        client = MockLLMClient()

        # temperature = 0
        result = client.call_with_retry("Test prompt", temperature=0)
        assert result == '{"result": "success"}'
        assert client.call_history[0]["temperature"] == 0

        # temperature = 1
        client.call_with_retry("Test prompt", temperature=1)
        assert client.call_history[1]["temperature"] == 1

    def test_response_format_variations(self):
        """测试不同的response_format。"""
        client = MockLLMClient()

        # json格式
        result1 = client.call_with_retry("Test prompt", response_format="json")
        assert result1 == '{"result": "success"}'
        assert client.call_history[0]["response_format"] == "json"

        # text格式
        result2 = client.call_with_retry("Test prompt", response_format="text")
        assert result2 == '{"result": "success"}'
        assert client.call_history[1]["response_format"] == "text"


class TestErrorHandling:
    """测试错误处理。"""

    def test_connection_error_triggers_retry(self):
        """测试连接错误触发重试。"""
        client = FailingMockLLMClient(fail_times=1)
        result = client.call_with_retry("Test prompt")

        assert result == '{"result": "success"}'
        assert client.call_count == 2  # 1次失败 + 1次成功

    def test_timeout_error_triggers_retry(self):
        """测试超时错误触发重试。"""

        class TimeoutMockClient(BaseLLMClient):
            def __init__(self, fail_times=1):
                super().__init__()
                self.call_count = 0
                self.fail_times = fail_times

            def call(
                self,
                prompt,
                system_prompt=None,
                temperature=0.3,
                max_tokens=1000,
                response_format="json",
            ):
                self.call_count += 1
                if self.call_count <= self.fail_times:
                    raise TimeoutError("Request timeout")
                return '{"result": "success"}'

        client = TimeoutMockClient(fail_times=1)
        result = client.call_with_retry("Test prompt")

        assert result == '{"result": "success"}'
        assert client.call_count == 2

    def test_error_logging(self, tmp_log_dir, monkeypatch):
        """测试错误日志记录。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = AlwaysFailingMockLLMClient()

        with pytest.raises(ConnectionError):
            client.call_with_retry("Test prompt")

        # 验证错误被记录（不抛出异常）
        # 实际日志内容验证需要检查日志文件，这里主要验证不崩溃

    def test_4xx_error_no_retry(self):
        """测试HTTP 4xx错误不重试。"""

        class ClientErrorMockClient(BaseLLMClient):
            def __init__(self):
                super().__init__()
                self.call_count = 0

            def call(
                self,
                prompt,
                system_prompt=None,
                temperature=0.3,
                max_tokens=1000,
                response_format="json",
            ):
                self.call_count += 1
                raise Exception("401 Unauthorized")

        client = ClientErrorMockClient()

        with pytest.raises(Exception, match="401 Unauthorized"):
            client.call_with_retry("Test prompt")

        # 4xx错误应该立即失败，不重试
        assert client.call_count == 1


class TestParameterPassing:
    """测试参数传递。"""

    def test_prompt_parameter(self):
        """测试prompt参数传递。"""
        client = MockLLMClient()
        client.call_with_retry(prompt="Hello, world!")

        assert client.call_history[0]["prompt"] == "Hello, world!"

    def test_system_prompt_parameter(self):
        """测试system_prompt参数传递。"""
        client = MockLLMClient()
        client.call_with_retry(prompt="Test", system_prompt="You are a test assistant")

        assert client.call_history[0]["system_prompt"] == "You are a test assistant"

    def test_temperature_parameter(self):
        """测试temperature参数传递。"""
        client = MockLLMClient()
        client.call_with_retry(prompt="Test", temperature=0.8)

        assert client.call_history[0]["temperature"] == 0.8

    def test_max_tokens_parameter(self):
        """测试max_tokens参数传递。"""
        client = MockLLMClient()
        client.call_with_retry(prompt="Test", max_tokens=500)

        assert client.call_history[0]["max_tokens"] == 500

    def test_response_format_parameter(self):
        """测试response_format参数传递。"""
        client = MockLLMClient()
        client.call_with_retry(prompt="Test", response_format="text")

        assert client.call_history[0]["response_format"] == "text"

    def test_all_parameters_together(self):
        """测试所有参数一起传递。"""
        client = MockLLMClient()
        client.call_with_retry(
            prompt="Complete test",
            system_prompt="Test system",
            temperature=0.9,
            max_tokens=3000,
            response_format="json",
        )

        history = client.call_history[0]
        assert history["prompt"] == "Complete test"
        assert history["system_prompt"] == "Test system"
        assert history["temperature"] == 0.9
        assert history["max_tokens"] == 3000
        assert history["response_format"] == "json"


class TestProviderAttribute:
    """测试provider属性。"""

    def test_provider_attribute_mockllm(self):
        """测试MockLLMClient的provider属性。"""
        client = MockLLMClient()
        assert client.provider == "mockllm"

    def test_provider_attribute_custom_client(self):
        """测试自定义客户端的provider属性。"""

        class CustomClient(BaseLLMClient):
            def call(
                self,
                prompt,
                system_prompt=None,
                temperature=0.3,
                max_tokens=1000,
                response_format="json",
            ):
                return '{"result": "success"}'

        client = CustomClient()
        assert client.provider == "custom"


class TestIntegration:
    """集成测试。"""

    def test_multiple_sequential_calls(self):
        """测试多次连续调用。"""
        client = MockLLMClient()

        for i in range(5):
            result = client.call_with_retry(f"Prompt {i}")
            assert result == '{"result": "success"}'

        assert client.call_count == 5

    def test_call_after_failure(self):
        """测试失败后继续调用。"""
        client = FailingMockLLMClient(fail_times=2)

        # 第一次调用会失败2次后成功
        result1 = client.call_with_retry("First call")
        assert result1 == '{"result": "success"}'
        assert client.call_count == 3

        # 第二次调用应该成功
        result2 = client.call_with_retry("Second call")
        assert result2 == '{"result": "success"}'
        assert client.call_count == 4
