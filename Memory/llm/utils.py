"""LLM客户端工具函数模块。

本模块提供JSON解析、重试机制、错误日志记录等工具功能。
"""

import json
import re
import logging
import time
import functools
from typing import Callable, TypeVar, Optional, Any
from pathlib import Path
from logging.handlers import RotatingFileHandler

from Memory.config.settings import settings

# 模块级日志器
logger = logging.getLogger(__name__)


def parse_json(response) -> dict:
    """解析LLM返回的JSON，处理markdown代码块包裹和dict返回。

    Args:
        response: LLM原始响应（字符串或字典）

    Returns:
        解析后的字典

    Raises:
        ValueError: JSON解析失败

    Examples:
        >>> parse_json('{"key": "value"}')
        {'key': 'value'}
        >>> parse_json('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}
        >>> parse_json({"key": "value"})
        {'key': 'value'}
    """
    # 第一步：如果已经是dict，直接返回
    if isinstance(response, dict):
        logger.debug("Response is already a dict, returning directly")
        return response

    response_str = str(response).strip()

    logger.debug(f"Parsing JSON response, length: {len(response_str)}, starts with: {response_str[:100]}")
    logger.debug(f"Full response preview (first 500 chars): {response_str[:500]}")

    # 辅助函数：增强的清理和解析逻辑
    def clean_and_parse(json_str, attempt_name):
        """清理JSON字符串并尝试解析。"""
        cleaned = json_str

        # 1. 移除开头和结尾的空白字符
        cleaned = cleaned.strip()

        # 2. 移除末尾的垃圾字符（包括中文标点）
        trailing_junk = ['\'', '"', ',', '.', ';', ':', '!', '`', '~', ' ', '，', '。', '；', '：', '！', '、', '「', '」', '『', '』']
        while len(cleaned) > 0:
            last_char = cleaned[-1]
            if last_char in trailing_junk:
                cleaned = cleaned[:-1]
            else:
                break

        # 3. 移除开头的垃圾字符
        leading_junk = ['\'', '"', '`', '~', ' ', '「', '」', '『', '』']
        while len(cleaned) > 0:
            first_char = cleaned[0]
            if first_char in leading_junk:
                cleaned = cleaned[1:]
            else:
                break

        if cleaned != json_str:
            logger.debug(f"[{attempt_name}] Cleaned {len(json_str)} -> {len(cleaned)} chars")
            logger.debug(f"[{attempt_name}] Removed leading/trailing junk")
            logger.debug(f"[{attempt_name}] Cleaned string preview: {cleaned[:200]}")

        try:
            result = json.loads(cleaned)
            logger.debug(f"[{attempt_name}] ✓ Parsing successful")
            return result, True
        except json.JSONDecodeError as e:
            logger.debug(f"[{attempt_name}] ✗ Parsing failed: {e}")
            logger.debug(f"[{attempt_name}] Error position: line {e.lineno}, col {e.colno}")
            logger.debug(f"[{attempt_name}] Error message: {e.msg}")
            return None, False

    # 第二步：尝试直接解析
    result, success = clean_and_parse(response_str, "direct")
    if success:
        return result

    # 第三步：尝试移除markdown代码块
    pattern = r"```json\s*([\s\S]*?)\s*```"
    match = re.search(pattern, response_str)
    if match:
        json_content = match.group(1).strip()
        logger.debug("Found markdown JSON code block, extracting...")
        result, success = clean_and_parse(json_content, "markdown")
        if success:
            return result

    # 第四步：尝试提取第一个完整的JSON对象/数组
    try:
        # 尝试提取JSON对象 {...}
        first_brace = response_str.find('{')
        if first_brace >= 0:
            last_brace = response_str.rfind('}')
            if last_brace > first_brace:
                json_content = response_str[first_brace:last_brace + 1]
                logger.debug("Attempting to extract JSON object from response...")
                result, success = clean_and_parse(json_content, "extracted_object")
                if success:
                    return result

        # 尝试提取JSON数组 [...]
        first_bracket = response_str.find('[')
        if first_bracket >= 0:
            last_bracket = response_str.rfind(']')
            if last_bracket > first_bracket:
                json_content = response_str[first_bracket:last_bracket + 1]
                logger.debug("Attempting to extract JSON array from response...")
                result, success = clean_and_parse(json_content, "extracted_array")
                if success:
                    return result
    except Exception as e:
        logger.debug(f"JSON extraction attempt failed: {e}")

    # 第五步：尝试修复截断的JSON数组
    # 当LLM输出达到max_tokens限制时，JSON会被截断（有[无]）
    try:
        logger.debug("Attempting to fix truncated JSON array...")
        first_bracket = response_str.find('[')
        last_bracket = response_str.rfind(']')

        if first_bracket >= 0 and last_bracket < first_bracket:
            # 数组被截断了，没有闭合的 ]
            truncated = response_str[first_bracket:]

            # 逐个移除末尾不完整的元素，直到能解析为止
            # 找到最后一个完整的 }, 然后补上 ]
            last_complete_obj = truncated.rfind('},')
            if last_complete_obj >= 0:
                fixed = truncated[:last_complete_obj + 1] + ']'
                logger.debug(f"Truncated array fix: keeping {fixed.count('},')} complete elements, closing with ]")
                result, success = clean_and_parse(fixed, "truncated_array")
                if success:
                    logger.info(f"Recovered {len(result)} entities from truncated JSON array")
                    return result

            # 如果连一个完整的对象都找不到，尝试找最后一个完整的 }
            last_complete_obj2 = truncated.rfind('}')
            if last_complete_obj2 >= 0:
                fixed = truncated[:last_complete_obj2 + 1] + ']'
                logger.debug(f"Truncated array fix (fallback): closing at last }}")
                result, success = clean_and_parse(fixed, "truncated_array_fallback")
                if success:
                    logger.info(f"Recovered {len(result)} entities from truncated JSON array (fallback)")
                    return result

        # 同样处理截断的JSON对象
        first_brace = response_str.find('{')
        last_brace = response_str.rfind('}')
        if first_brace >= 0 and last_brace < first_brace and first_bracket < 0:
            truncated = response_str[first_brace:]
            last_complete_field = truncated.rfind('",')
            if last_complete_field >= 0:
                fixed = truncated[:last_complete_field + 2] + '}'
                logger.debug("Truncated object fix: closing at last complete field")
                result, success = clean_and_parse(fixed, "truncated_object")
                if success:
                    logger.info("Recovered JSON object from truncated response")
                    return result
    except Exception as e:
        logger.debug(f"Truncated JSON fix attempt failed: {e}")

    # 第六步：尝试修复常见的JSON格式问题
    try:
        logger.debug("Attempting to fix common JSON format issues...")

        # 尝试修复reason字段中的单引号问题
        fixed_json = response_str
        if '"reason":"' in fixed_json and '."' in fixed_json:
            # 替换reason字段末尾的单引号
            import re as re_fix
            fixed_json = re_fix.sub(r'"reason":"([^"]*?)\'"', r'"reason":"\1"', fixed_json)
            logger.debug("Attempted to fix trailing single quotes in reason field")

        result, success = clean_and_parse(fixed_json, "fixed_format")
        if success:
            logger.debug("Successfully parsed after fixing format issues")
            return result
    except Exception as e:
        logger.debug(f"Format fixing attempt failed: {e}")

    # 所有尝试都失败，记录详细错误信息
    error_msg = f"Failed to parse LLM response as JSON after all attempts.\n"
    error_msg += f"Response length: {len(response_str)}\n"
    error_msg += f"Response preview: {response_str[:200]}...\n"
    error_msg += f"Response end: ...{response_str[-200:]}"

    logger.error(error_msg)
    raise ValueError(error_msg)


def setup_error_logger() -> logging.Logger:
    """设置LLM错误日志记录器。

    创建日志目录（如果不存在），配置RotatingFileHandler实现日志轮转。

    Returns:
        配置好的日志记录器
    """
    # 确保日志目录存在
    log_dir = Path(__file__).parent.parent / "logs" / "llm_errors"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 创建日志记录器
    error_logger = logging.getLogger("Memory.llm.errors")
    error_logger.setLevel(logging.ERROR)

    # 避免重复添加handler
    if not error_logger.handlers:
        # 创建RotatingFileHandler：每个文件最大10MB，保留5个备份
        file_handler = RotatingFileHandler(
            log_dir / "llm_errors.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        error_logger.addHandler(file_handler)

    return error_logger


def with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """重试装饰器，用于LLM调用的自动重试。

    Args:
        max_retries: 最大重试次数（默认3次）
        base_delay: 基础延迟时间（秒），默认1秒

    Returns:
        装饰器函数

    Examples:
        >>> @with_retry(max_retries=3)
        ... def call_llm(prompt):
        ...     # LLM调用逻辑
        ...     pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # 最后一次尝试失败，不再重试
                    if attempt == max_retries - 1:
                        break

                    # 计算延迟时间（指数退避）
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)

            # 所有重试都失败，抛出最后一次异常
            raise last_exception

        return wrapper

    return decorator


def log_llm_error(
    error: Exception,
    provider: str,
    prompt: str,
    response: Optional[str] = None,
):
    """记录LLM调用错误到专门的日志文件。

    Args:
        error: 异常对象
        provider: LLM提供商名称（qianwen/deepseek等）
        prompt: 发送的prompt
        response: LLM的响应（如果有的话）
    """
    error_logger = setup_error_logger()

    error_msg = f"\n{'=' * 60}\n"
    error_msg += f"Provider: {provider}\n"
    error_msg += f"Error Type: {type(error).__name__}\n"
    error_msg += f"Error Message: {str(error)}\n"
    error_msg += f"\nPrompt:\n{prompt[:500]}\n"

    if response:
        error_msg += f"\nResponse:\n{response[:500]}\n"

    error_msg += f"{'=' * 60}\n"

    error_logger.error(error_msg)
