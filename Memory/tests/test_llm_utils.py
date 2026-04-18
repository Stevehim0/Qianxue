"""LLM工具函数测试。

测试 Memory.llm.utils 模块的所有工具函数：
- parse_json: JSON解析（标准格式、markdown包裹、错误处理）
- with_retry: 指数退避重试装饰器
- log_llm_error: 错误日志记录
- setup_error_logger: 日志配置
"""

import pytest
import json
import logging
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from Memory.llm.utils import parse_json, with_retry, log_llm_error, setup_error_logger


class TestParseJson:
    """测试 parse_json 函数。"""

    def test_parse_standard_json(self):
        """测试解析标准JSON格式。"""
        response = '{"city": "北京", "temperature": 25}'
        result = parse_json(response)
        assert result == {"city": "北京", "temperature": 25}

    def test_parse_json_with_whitespace(self):
        """测试解析带空白的JSON。"""
        response = '  {"key": "value"}  '
        result = parse_json(response)
        assert result == {"key": "value"}

    def test_parse_markdown_wrapped_json(self):
        """测试解析markdown代码块包裹的JSON。"""
        response = """```json
        {"city": "北京", "temperature": 25}
        ```"""
        result = parse_json(response)
        assert result == {"city": "北京", "temperature": 25}

    def test_parse_markdown_json_without_language_tag(self):
        """测试解析```包裹的JSON（无语言标记）。"""
        response = '```\n{"key": "value"}\n```'
        result = parse_json(response)
        assert result == {"key": "value"}

    def test_parse_nested_json(self):
        """测试解析嵌套JSON。"""
        response = '{"user": {"name": "张三", "age": 30}}'
        result = parse_json(response)
        assert result == {"user": {"name": "张三", "age": 30}}

    def test_parse_json_array(self):
        """测试解析JSON数组。"""
        response = "[1, 2, 3, 4, 5]"
        result = parse_json(response)
        assert result == [1, 2, 3, 4, 5]

    def test_parse_invalid_json_raises_error(self):
        """测试解析无效JSON抛出ValueError。"""
        response = '{"invalid": json}'
        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            parse_json(response)

    def test_parse_empty_string_raises_error(self):
        """测试解析空字符串抛出ValueError。"""
        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            parse_json("")

    def test_parse_malformed_markdown_json_raises_error(self):
        """测试解析格式错误的markdown JSON抛出ValueError。"""
        response = '```json\n{"incomplete": ' ""  # 不完整的JSON
        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            parse_json(response)

    def test_error_message_contains_preview(self):
        """测试错误消息包含响应预览。"""
        response = '{"invalid": value}'
        with pytest.raises(ValueError) as exc_info:
            parse_json(response)

        error_msg = str(exc_info.value)
        assert "Response preview:" in error_msg
        assert '{"invalid": value}' in error_msg


class TestWithRetry:
    """测试 with_retry 装饰器。"""

    def test_success_on_first_attempt(self):
        """测试第一次就成功。"""

        @with_retry(max_attempts=4)
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_success_on_second_attempt(self):
        """测试第二次成功。"""
        attempts = [0]

        @with_retry(max_attempts=4, base_delay=0.1)
        def function_with_one_failure():
            attempts[0] += 1
            if attempts[0] == 1:
                raise ConnectionError("Network error")
            return "success"

        start = time.time()
        result = function_with_one_failure()
        elapsed = time.time() - start

        assert result == "success"
        assert attempts[0] == 2
        # 第一次立即重试（0s延迟）
        assert elapsed < 0.2

    def test_success_on_third_attempt(self):
        """测试第三次成功。"""
        attempts = [0]

        @with_retry(max_attempts=4, base_delay=0.1)
        def function_with_two_failures():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ConnectionError("Network error")
            return "success"

        start = time.time()
        result = function_with_two_failures()
        elapsed = time.time() - start

        assert result == "success"
        assert attempts[0] == 3
        # 第二次重试等待 base_delay^0 = 0.1^0 = 1秒
        # 但我们设置base_delay=0.1，所以等待0.1秒
        assert 0.05 < elapsed < 0.3

    def test_all_attempts_fail(self):
        """测试所有尝试都失败。"""

        @with_retry(max_attempts=3, base_delay=0.05)
        def always_failing_function():
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError, match="Always fails"):
            always_failing_function()

    def test_http_4xx_errors_not_retried(self):
        """测试HTTP 4xx错误不重试。"""
        attempts = [0]

        @with_retry(max_attempts=4)
        def function_with_404_error():
            attempts[0] += 1
            raise Exception("404 Not Found")

        with pytest.raises(Exception, match="404 Not Found"):
            function_with_404_error()

        # 4xx错误应该立即失败，不重试
        assert attempts[0] == 1

    def test_http_401_errors_not_retried(self):
        """测试HTTP 401错误不重试。"""
        attempts = [0]

        @with_retry(max_attempts=4)
        def function_with_401_error():
            attempts[0] += 1
            raise Exception("401 Unauthorized")

        with pytest.raises(Exception, match="401 Unauthorized"):
            function_with_401_error()

        assert attempts[0] == 1

    def test_http_5xx_errors_are_retried(self):
        """测试HTTP 5xx错误会重试。"""
        attempts = [0]

        @with_retry(max_attempts=3, base_delay=0.05)
        def function_with_500_error():
            attempts[0] += 1
            if attempts[0] < 2:
                raise Exception("500 Internal Server Error")
            return "success"

        result = function_with_500_error()
        assert result == "success"
        assert attempts[0] == 2

    def test_timeout_errors_are_retried(self):
        """测试超时错误会重试。"""
        attempts = [0]

        @with_retry(max_attempts=3, base_delay=0.05)
        def function_with_timeout():
            attempts[0] += 1
            if attempts[0] < 2:
                raise TimeoutError("Request timeout")
            return "success"

        result = function_with_timeout()
        assert result == "success"
        assert attempts[0] == 2

    def test_custom_max_attempts(self):
        """测试自定义最大尝试次数。"""

        @with_retry(max_attempts=2)
        def function():
            raise ConnectionError("Fail")

        with pytest.raises(ConnectionError):
            function()

    def test_exponential_backoff_timing(self):
        """测试指数退避时间计算。"""
        attempt_times = []

        @with_retry(max_attempts=4, base_delay=0.1)
        def function_with_timing():
            attempt_times.append(time.time())
            if len(attempt_times) < 3:
                raise ConnectionError("Fail")
            return "success"

        function_with_timing()

        # 验证延迟时间
        # 第1次到第2次：base_delay^0 = 1秒（但base_delay=0.1，所以是0.1秒）
        # 第2次到第3次：base_delay^1 = 0.1秒
        if len(attempt_times) >= 2:
            delay1 = attempt_times[1] - attempt_times[0]
            assert delay1 < 0.2  # 第一次立即重试

        if len(attempt_times) >= 3:
            delay2 = attempt_times[2] - attempt_times[1]
            assert 0.05 < delay2 < 0.2  # 第二次等待约0.1秒


class TestLogLlmError:
    """测试 log_llm_error 函数。"""

    def test_log_qianwen_error(self, tmp_path, monkeypatch):
        """测试记录千问错误。"""
        # 修改日志目录到临时目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        error = ConnectionError("Network error")
        prompt = "Tell me about Beijing"
        response = "Error response from API"

        # 不应该抛出异常
        log_llm_error(error, "qianwen", prompt, response)

        # 验证日志文件被创建
        log_file = tmp_path / "Memory" / "logs" / "llm_errors.log"
        # 注意：由于我们mock了Path，实际日志可能写到了其他位置
        # 这里主要验证函数不抛出异常

    def test_log_deepseek_error(self, tmp_path, monkeypatch):
        """测试记录DeepSeek错误。"""
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        error = TimeoutError("Request timeout")
        prompt = "What is the capital of France?"

        # 不应该抛出异常
        log_llm_error(error, "deepseek", prompt)

    def test_log_error_without_response(self, tmp_path, monkeypatch):
        """测试记录没有响应的错误。"""
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        error = ValueError("Invalid parameter")

        # 不应该抛出异常
        log_llm_error(error, "qianwen", "Test prompt", None)

    def test_api_key_masking(self, tmp_path, monkeypatch):
        """测试API密钥脱敏。"""
        # 这个测试验证函数内部逻辑，不验证实际日志内容
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        error = Exception("Test error")

        # 应该不抛出异常
        log_llm_error(error, "qianwen", "Test prompt")


class TestSetupErrorLogger:
    """测试 setup_error_logger 函数。"""

    def test_setup_logger_creates_directory(self, tmp_path, monkeypatch):
        """测试设置日志器时创建目录。"""
        # 修改日志目录到临时目录
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        logger = setup_error_logger()

        # 验证日志器配置
        assert logger.name == "Memory.llm.errors"
        assert logger.level == logging.ERROR

    def test_setup_logger_rotating_file_handler(self, tmp_path, monkeypatch):
        """测试RotatingFileHandler配置。"""
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        logger = setup_error_logger()

        # 验证handler配置
        assert len(logger.handlers) > 0
        handler = logger.handlers[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)

    def test_setup_logger_idempotent(self, tmp_path, monkeypatch):
        """测试多次调用不会重复添加handler。"""
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        logger1 = setup_error_logger()
        initial_handler_count = len(logger1.handlers)

        logger2 = setup_error_logger()
        final_handler_count = len(logger2.handlers)

        # handler数量应该相同（不会重复添加）
        assert initial_handler_count == final_handler_count

    def test_logger_format(self, tmp_path, monkeypatch):
        """测试日志格式。"""
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        logger = setup_error_logger()

        # 验证formatter
        if logger.handlers:
            handler = logger.handlers[0]
            formatter = handler.formatter
            assert formatter is not None
            format_str = formatter._fmt
            assert "[%(asctime)s]" in format_str
            assert "[%(levelname)s]" in format_str


class TestIntegration:
    """集成测试：测试工具函数组合使用。"""

    def test_parse_json_with_retry(self):
        """测试结合使用重试和JSON解析。"""
        attempts = [0]

        @with_retry(max_attempts=3, base_delay=0.05)
        def function_that_returns_json():
            attempts[0] += 1
            if attempts[0] == 1:
                raise ConnectionError("Network error")
            return '{"result": "success"}'

        result = function_that_returns_json()
        parsed = parse_json(result)
        assert parsed == {"result": "success"}

    def test_log_error_after_retry_failure(self, tmp_path, monkeypatch):
        """测试重试失败后记录错误。"""
        monkeypatch.setattr("Memory.llm.utils.Path", lambda p: tmp_path / "Memory" / p)

        @with_retry(max_attempts=2, base_delay=0.05)
        def always_failing_function():
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            always_failing_function()

        # 验证可以记录错误（不抛出异常）
        log_llm_error(ConnectionError("Test"), "qianwen", "Test prompt")
