"""千问LLM客户端测试。

测试 Memory.llm.qianwen_client 模块的 QianwenClient 类：
- 初始化: API密钥验证、从settings读取
- call(): API调用、参数构造、响应解析
- 错误处理: HTTP错误、超时、JSON解析失败
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import HTTPError, Timeout as RequestsTimeout

from Memory.llm.qianwen_client import QianwenClient


class TestQianwenClientInit:
    """测试 QianwenClient 初始化。"""

    def test_init_with_api_key(self, tmp_log_dir, monkeypatch):
        """测试使用提供的API密钥初始化。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = QianwenClient(api_key="test-key-12345")
        assert client.api_key == "test-key-12345"
        assert client.provider == "qianwen"
        assert client.timeout == 30

    def test_init_without_api_key_raises_error(self, tmp_log_dir, monkeypatch):
        """测试没有API密钥时抛出ValueError。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock settings（没有API密钥）
        mock_settings = Mock()
        mock_settings.models.llm_api_key = None
        monkeypatch.setattr("Memory.llm.qianwen_client.settings", mock_settings)

        with pytest.raises(ValueError, match="Qianwen API key is required"):
            QianwenClient()

    def test_init_from_settings(self, tmp_log_dir, monkeypatch):
        """测试从settings读取API密钥。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock settings（有API密钥）
        mock_settings = Mock()
        mock_settings.models.llm_api_key = "settings-key-67890"
        monkeypatch.setattr("Memory.llm.qianwen_client.settings", mock_settings)

        client = QianwenClient()
        assert client.api_key == "settings-key-67890"

    def test_init_with_custom_timeout(self, tmp_log_dir, monkeypatch):
        """测试自定义超时时间。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        client = QianwenClient(api_key="test-key", timeout=60)
        assert client.timeout == 60


class TestQianwenClientCall:
    """测试 QianwenClient.call 方法。"""

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_successful_call_json_response(self, mock_post, tmp_log_dir, monkeypatch):
        """测试成功调用（JSON响应）。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {
                "choices": [
                    {"message": {"content": '{"result": "success", "data": {"city": "北京"}}'}}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == {"result": "success", "data": {"city": "北京"}}

        # 验证HTTP请求
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == QianwenClient.BASE_URL
        assert call_args[1]["json"]["model"] == "qwen-turbo"

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_successful_call_text_response(self, mock_post, tmp_log_dir, monkeypatch):
        """测试成功调用（文本响应）。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": "这是一段普通文本响应。"}}]}
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")
        result = client.call("Test prompt", response_format="text")

        assert result == "这是一段普通文本响应。"

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_call_with_system_prompt(self, mock_post, tmp_log_dir, monkeypatch):
        """测试带system_prompt的调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": '{"result": "ok"}'}}]}
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")
        result = client.call(prompt="User prompt", system_prompt="You are a helpful assistant")

        assert result == {"result": "ok"}

        # 验证messages包含system prompt
        call_args = mock_post.call_args
        messages = call_args[1]["json"]["input"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "User prompt"

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_call_with_temperature_and_max_tokens(self, mock_post, tmp_log_dir, monkeypatch):
        """测试带temperature和max_tokens的调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": '{"result": "ok"}'}}]}
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")
        result = client.call(prompt="Test", temperature=0.8, max_tokens=2000)

        assert result == {"result": "ok"}

        # 验证参数传递
        call_args = mock_post.call_args
        parameters = call_args[1]["json"]["parameters"]
        assert parameters["temperature"] == 0.8
        assert parameters["max_tokens"] == 2000

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_http_headers(self, mock_post, tmp_log_dir, monkeypatch):
        """测试HTTP headers正确。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": '{"result": "ok"}'}}]}
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-api-key")
        result = client.call("Test")

        assert result == {"result": "ok"}

        # 验证headers
        call_args = mock_post.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["Content-Type"] == "application/json"


class TestQianwenClientErrors:
    """测试 QianwenClient 错误处理。"""

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_http_404_error(self, mock_post, tmp_log_dir, monkeypatch):
        """测试HTTP 404错误。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP 404响应
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError("404 Not Found")
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")

        with pytest.raises(HTTPError, match="404 Not Found"):
            client.call("Test prompt")

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_http_500_error(self, mock_post, tmp_log_dir, monkeypatch):
        """测试HTTP 500错误。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP 500响应
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = HTTPError("500 Internal Server Error")
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")

        with pytest.raises(HTTPError, match="500 Internal Server Error"):
            client.call("Test prompt")

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_timeout_error(self, mock_post, tmp_log_dir, monkeypatch):
        """测试超时错误。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock超时
        mock_post.side_effect = RequestsTimeout("Request timeout")

        client = QianwenClient(api_key="test-key")

        with pytest.raises(TimeoutError, match="Qianwen API timeout"):
            client.call("Test prompt")

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_invalid_json_response(self, mock_post, tmp_log_dir, monkeypatch):
        """测试无效JSON响应。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应（返回无效JSON）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": '{"invalid": json content}'}}]}
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")

        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            client.call("Test prompt")

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_api_error_response(self, mock_post, tmp_log_dir, monkeypatch):
        """测试API错误响应。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应（API错误）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Invalid API key"}
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")

        with pytest.raises(ValueError, match="Qianwen API error: Invalid API key"):
            client.call("Test prompt")

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_malformed_response(self, mock_post, tmp_log_dir, monkeypatch):
        """测试格式错误的响应。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应（缺少output字段）
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "some data"}
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")

        with pytest.raises(ValueError, match="Qianwen API error"):
            client.call("Test prompt")


class TestQianwenClientJsonParsing:
    """测试 QianwenClient JSON解析。"""

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_parse_markdown_wrapped_json(self, mock_post, tmp_log_dir, monkeypatch):
        """测试解析markdown包裹的JSON。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {
                "choices": [
                    {"message": {"content": '```json\n{"city": "北京", "temperature": 25}\n```'}}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == {"city": "北京", "temperature": 25}

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_parse_nested_json(self, mock_post, tmp_log_dir, monkeypatch):
        """测试解析嵌套JSON。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {
                "choices": [{"message": {"content": '{"user": {"name": "张三", "age": 30}}'}}]
            }
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")
        result = client.call("Test prompt")

        assert result == {"user": {"name": "张三", "age": 30}}


class TestIntegration:
    """集成测试。"""

    @patch("Memory.llm.qianwen_client.requests.post")
    def test_multiple_sequential_calls(self, mock_post, tmp_log_dir, monkeypatch):
        """测试多次连续调用。"""
        # Mock日志目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_log_dir.parent / p)

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": '{"result": "ok"}'}}]}
        }
        mock_post.return_value = mock_response

        client = QianwenClient(api_key="test-key")

        for i in range(3):
            result = client.call(f"Prompt {i}")
            assert result == {"result": "ok"}

        assert mock_post.call_count == 3
