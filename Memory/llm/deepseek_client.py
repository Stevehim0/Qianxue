"""DeepSeek LLM客户端实现模块。

提供DeepSeek API的Python客户端实现，继承自BaseLLMClient。
使用OpenAI SDK调用DeepSeek的OpenAI兼容API。
"""

import os
from typing import Optional
import logging

try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "openai package is required for DeepSeekClient. " "Please install it: pip install openai"
    )

from Memory.llm.base import BaseLLMClient
from Memory.llm.utils import parse_json, log_llm_error
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class DeepSeekClient(BaseLLMClient):
    """DeepSeek API客户端实现。

    通过OpenAI SDK调用DeepSeek的OpenAI兼容API。

    Attributes:
        BASE_URL: DeepSeek API基础URL
        MODEL: 使用的模型名称（deepseek-chat）
    """

    BASE_URL = "https://api.deepseek.com"
    MODEL = "deepseek-chat"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """初始化DeepSeek客户端。

        Args:
            api_key: DeepSeek API密钥（可选，从环境变量DEEPSEEK_API_KEY读取）
            **kwargs: 其他配置参数（传递给父类）
        """
        # 从统一配置读取 api_key（.env 中的 LLM_API_KEY）
        if api_key is None:
            api_key = settings.models.llm_api_key

        if not api_key:
            raise ValueError(
                "DeepSeek API key is required. " "Please set LLM_API_KEY in .env"
            )

        # 读取 .env 中的 base_url 和 model（优先用配置，否则用默认值）
        base_url = settings.models.llm_base_url or self.BASE_URL
        model = settings.models.llm_model or self.MODEL

        # 创建OpenAI客户端
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

        # 初始化父类（推理模型需要更长超时，默认 120s）
        if "timeout" not in kwargs:
            kwargs["timeout"] = 120
        super().__init__(api_key=api_key, **kwargs)
        self.provider = "deepseek"

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        response_format: str = "json",
    ) -> str:
        """调用DeepSeek API。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            temperature: 温度参数（0-1），默认0.3
            max_tokens: 最大token数，默认1000
            response_format: 响应格式（"json"或"text"），默认"json"

        Returns:
            LLM响应文本

        Raises:
            Exception: API调用失败
        """
        # 构建messages列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 调用DeepSeek API
        try:
            api_kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": self.timeout,
            }
            # JSON 模式：强制模型输出合法 JSON
            if response_format == "json":
                api_kwargs["response_format"] = {"type": "json_object"}

            # V4 模型默认开启 thinking mode，会先用 token 做推理再输出回答。
            # Memory 子系统的任务（质量检查、实体提取等）不需要深度推理，
            # 关掉 thinking mode 避免 max_tokens 被 reasoning 吃光导致 content 为空。
            if "v4" in self.model:
                api_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

            response = self.client.chat.completions.create(**api_kwargs)

        except Exception as e:
            # 记录错误详情
            log_llm_error(error=e, provider=self.provider, prompt=prompt, response=None)
            raise

        # 提取响应内容
        choice = response.choices[0]
        content = choice.message.content

        if not content or not content.strip():
            raise ValueError("DeepSeek returned empty content")

        # 检测截断：推理模型容易因 max_tokens 不够导致输出被截断
        if choice.finish_reason == "length":
            raise ValueError(
                f"DeepSeek response truncated (finish_reason=length, "
                f"max_tokens={max_tokens}). Consider increasing max_tokens."
            )

        # 如果需要JSON格式，解析JSON
        if response_format == "json":
            try:
                return parse_json(content)
            except ValueError as e:
                # JSON解析失败，记录错误
                log_llm_error(error=e, provider=self.provider, prompt=prompt, response=content)
                raise

        return content
