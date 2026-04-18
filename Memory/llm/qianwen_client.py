"""千问LLM客户端实现模块。

提供千问API的Python客户端实现，继承自BaseLLMClient。
"""

import requests
from typing import Optional
import logging

from Memory.llm.base import BaseLLMClient
from Memory.llm.utils import parse_json, log_llm_error
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class QianwenClient(BaseLLMClient):
    """千问API客户端实现。

    通过阿里云DashScope API调用千问大语言模型。

    Attributes:
        BASE_URL: 千问API基础URL
        MODEL: 使用的模型名称（qwen-turbo）
    """

    BASE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    MODEL = "qwen-turbo"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """初始化千问客户端。

        Args:
            api_key: 千问API密钥（可选，从settings.models.llm_api_key读取）
            **kwargs: 其他配置参数（传递给父类）
        """
        if api_key is None:
            api_key = settings.models.llm_api_key

        if not api_key:
            logger.warning("LLM_API_KEY 未配置，LLM 调用将失败，请通过前端或 .env 配置")

        super().__init__(api_key=api_key or "", **kwargs)
        self.provider = "qianwen"

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        response_format: str = "json",
    ) -> str:
        """调用千问API。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            temperature: 温度参数（0-1），默认0.3
            max_tokens: 最大token数，默认1000
            response_format: 响应格式（"json"或"text"），默认"json"

        Returns:
            LLM响应文本

        Raises:
            requests.HTTPError: HTTP请求失败
            ValueError: JSON解析失败
            Exception: 其他API错误
        """
        # 构建HTTP headers
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        # 构建messages列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 构建请求payload
        payload = {
            "model": self.MODEL,
            "input": {"messages": messages},
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "result_format": "message",
            },
        }

        # 发送HTTP请求
        try:
            response = requests.post(
                self.BASE_URL, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()

        except requests.HTTPError as e:
            # 记录错误详情
            log_llm_error(
                error=e,
                provider=self.provider,
                prompt=prompt,
                response=response.text if hasattr(response, "text") else None,
            )
            raise

        except requests.Timeout as e:
            # 超时错误
            log_llm_error(error=e, provider=self.provider, prompt=prompt, response=None)
            raise TimeoutError(f"Qianwen API timeout after {self.timeout}s") from e

        # 解析响应
        result = response.json()

        # 检查API错误
        if "output" not in result or "choices" not in result["output"]:
            error_msg = result.get("message", "Unknown API error")
            log_llm_error(
                error=Exception(error_msg),
                provider=self.provider,
                prompt=prompt,
                response=str(result),
            )
            raise ValueError(f"Qianwen API error: {error_msg}")

        # 提取响应内容
        content = result["output"]["choices"][0]["message"]["content"]

        # 记录原始响应用于调试
        self.last_response = content
        logger.debug(f"LLM raw response length: {len(content)}")
        logger.debug(f"LLM raw response preview: {content[:200]}...")

        # 如果需要JSON格式，解析JSON
        if response_format == "json":
            try:
                parsed_result = parse_json(content)
                logger.debug(f"JSON parsing successful, result type: {type(parsed_result)}")
                return parsed_result
            except ValueError as e:
                # JSON解析失败，记录详细错误信息
                logger.error(f"JSON parsing failed for response: {content[:500]}")
                logger.error(f"Response end: ...{content[-500:]}")
                log_llm_error(error=e, provider=self.provider, prompt=prompt, response=content)
                raise

        return content
