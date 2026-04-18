"""LLM客户端抽象基类模块。

定义LLM客户端的统一接口，所有具体客户端实现都必须继承此类。
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from Memory.llm.utils import with_retry, log_llm_error

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """LLM客户端抽象基类。

    所有LLM客户端（千问、DeepSeek等）都必须继承此类并实现call()方法。

    Attributes:
        api_key: LLM API密钥
        timeout: 请求超时时间（秒）
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30, **kwargs):
        """初始化LLM客户端。

        Args:
            api_key: LLM API密钥（可选，从环境变量或配置读取）
            timeout: 请求超时时间（秒），默认30秒
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.timeout = timeout
        self.provider = self.__class__.__name__.replace("Client", "").lower()

    @abstractmethod
    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        response_format: str = "json",
        timeout: Optional[int] = None,
    ) -> str:
        """调用LLM接口。

        子类必须实现此方法，提供具体的LLM API调用逻辑。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            temperature: 温度参数（0-1），默认0.3
            max_tokens: 最大token数，默认1000
            response_format: 响应格式（"json"或"text"），默认"json"
            timeout: 请求超时时间（秒），默认使用实例的timeout

        Returns:
            LLM响应文本

        Raises:
            Exception: API调用失败
        """
        pass

    def call_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> dict:
        """调用LLM接口并返回JSON格式响应（便捷方法）。

        这是一个便捷方法，内部调用call()并设置response_format="json"。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            temperature: 温度参数（0-1），默认0.3
            max_tokens: 最大token数，默认1000

        Returns:
            解析后的JSON字典

        Raises:
            Exception: API调用失败或JSON解析失败
        """
        return self.call(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )

    def call_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        response_format: str = "json",
    ) -> str:
        """带重试机制的LLM调用。

        使用with_retry装饰器包装call()方法，自动处理网络错误和临时故障。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            temperature: 温度参数（0-1），默认0.3
            max_tokens: 最大token数，默认1000
            response_format: 响应格式（"json"或"text"），默认"json"

        Returns:
            LLM响应文本

        Raises:
            Exception: 重试耗尽后仍然失败
        """

        # 定义内部函数以便使用with_retry装饰器
        @with_retry(max_retries=4, base_delay=2.0)
        def _call_with_error_handling():
            try:
                return self.call(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except Exception as e:
                # 记录错误详情
                log_llm_error(error=e, provider=self.provider, prompt=prompt, response=None)
                raise

        return _call_with_error_handling()
