"""DeepSeek LLM客户端测试。

测试 Memory.llm.deepseek_client 模块的 DeepSeekClient 类：
- 初始化: API密钥验证、从环境变量读取
- call(): API调用、参数构造、响应解析
- 错误处理: API错误、超时、JSON解析失败
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from openai import OpenAI

from Memory.llm.deepseek_client import DeepSeekClient


class TestDeepSeekClientInit:
    """测试 DeepSeekClient 初始化。"""

    def test_init_with_api_key(self, tmp_log_dir, monkeypatch):
        """测试使用提供的API密钥初始化。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = DeepSeekClient(api_key="test-key-12345")
        assert client.api_key == "test-key-12345"
        assert client.provider == "deepseek"
        assert client.timeout == 30
        assert isinstance(client.client, OpenAI)

    def test_init_without_api_key_raises_error(self, tmp_log_dir, monkeypatch):
        """测试没有API密钥时抛出ValueError。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock环境变量（没有API密钥）
        monkeypatch.setenv("DEEPSEEK_API_KEY", "")

        with pytest.raises(ValueError, match="DeepSeek API key is required"):
            DeepSeekClient()

    def test_init_from_environment_variable(self, tmp_log_dir, monkeypatch):
        """测试从环境变量读取API密钥。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock环境变量（有API密钥）
        monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key-67890")

        client = DeepSeekClient()
        assert client.api_key == "env-key-67890"

    def test_init_with_custom_timeout(self, tmp_log_dir, monkeypatch):
        """测试自定义超时时间。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = DeepSeekClient(api_key="test-key", timeout=60)
        assert client.timeout == 60

    def test_openai_client_configuration(self, tmp_log_dir, monkeypatch):
        """测试OpenAI客户端配置。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = DeepSeekClient(api_key="test-key")

        # 验证OpenAI客户端配置
        assert client.client.api_key == "test-key"
        assert client.client.base_url == "https://api.deepseek.com"


class TestDeepSeekClientCall:
    """测试 DeepSeekClient.call 方法。"""

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_successful_call_json_response(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试成功调用（JSON响应）。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "success", "data": {"city": "北京"}}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == {"result": "success", "data": {"city": "北京"}}

        # 验证API调用
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["model"] == "deepseek-chat"

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_successful_call_text_response(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试成功调用（文本响应）。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "这是一段普通文本响应。"

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call("Test prompt", response_format="text")

        assert result == "这是一段普通文本响应。"

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_call_with_system_prompt(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试带system_prompt的调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "ok"}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call(prompt="User prompt", system_prompt="You are a helpful assistant")

        assert result == {"result": "ok"}

        # 验证messages包含system prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "User prompt"

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_call_with_temperature_and_max_tokens(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试带temperature和max_tokens的调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "ok"}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call(prompt="Test", temperature=0.8, max_tokens=2000)

        assert result == {"result": "ok"}

        # 验证参数传递
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0.8
        assert call_args[1]["max_tokens"] == 2000

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_call_with_timeout(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试超时参数传递。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "ok"}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key", timeout=60)
        result = client.call("Test")

        assert result == {"result": "ok"}

        # 验证timeout参数
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["timeout"] == 60


class TestDeepSeekClientErrors:
    """测试 DeepSeekClient 错误处理。"""

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_api_error(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试API错误。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock API错误
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")

        with pytest.raises(Exception, match="API error"):
            client.call("Test prompt")

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_timeout_error(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试超时错误。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock超时
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("Request timeout")
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")

        with pytest.raises(Exception, match="Request timeout"):
            client.call("Test prompt")

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_invalid_json_response(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试无效JSON响应。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应（返回无效JSON）
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"invalid": json content}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")

        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            client.call("Test prompt")


class TestDeepSeekClientJsonParsing:
    """测试 DeepSeekClient JSON解析。"""

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_parse_markdown_wrapped_json(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试解析markdown包裹的JSON。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = (
            '```json\n{"city": "北京", "temperature": 25}\n```'
        )

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == {"city": "北京", "temperature": 25}

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_parse_nested_json(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试解析嵌套JSON。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"user": {"name": "张三", "age": 30}}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == {"user": {"name": "张三", "age": 30}}

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_parse_json_array(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试解析JSON数组。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "[1, 2, 3, 4, 5]"

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == [1, 2, 3, 4, 5]


class TestIntegration:
    """集成测试。"""

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_multiple_sequential_calls(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试多次连续调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "ok"}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")

        for i in range(3):
            result = client.call(f"Prompt {i}")
            assert result == {"result": "ok"}

        assert mock_client.chat.completions.create.call_count == 3

    @patch("Memory.llm.deepseek_client.OpenAI")
    def test_call_with_retry(self, mock_openai, tmp_log_dir, monkeypatch):
        """测试带重试的调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock OpenAI响应
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "ok"}'

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="test-key")
        result = client.call_with_retry("Test prompt")

        assert result == {"result": "ok"}
