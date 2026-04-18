"""话题边界判断模块。

使用 LLM 分析缓冲区中的消息，判断当前话题/事件是否已经结束，
以及在哪里切分。
"""

import json
import logging
from pathlib import Path
from typing import List

from Memory.llm.utils import parse_json
from Memory.writer.buffer import BufferedMessage, TopicJudgmentResult

logger = logging.getLogger(__name__)

# 提示模板路径
_PROMPT_PATH = Path(__file__).parent.parent / "config" / "prompts" / "write_topic_boundary.txt"


def _load_prompt_template() -> str:
    """加载话题边界判断的提示模板。"""
    if not _PROMPT_PATH.exists():
        raise FileNotFoundError(f"Topic boundary prompt not found: {_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


class TopicJudge:
    """话题边界判断器。

    通过 LLM 调用分析缓冲区中的消息序列，判断是否存在话题边界。
    LLM 调用失败时安全降级，返回"未找到边界"。

    Examples:
        >>> judge = TopicJudge(llm_client)
        >>> result = judge.judge(messages)
        >>> if result.has_boundary:
        ...     topic_messages = messages[:result.boundary_position]
    """

    def __init__(self, llm_client):
        """初始化话题边界判断器。

        Args:
            llm_client: LLM 客户端实例（支持 call_with_retry 方法）
        """
        self.llm_client = llm_client
        self._prompt_template: str | None = None

    def _get_prompt_template(self) -> str:
        """延迟加载提示模板。"""
        if self._prompt_template is None:
            self._prompt_template = _load_prompt_template()
        return self._prompt_template

    def judge(self, messages: List[BufferedMessage]) -> TopicJudgmentResult:
        """判断缓冲区中的消息是否存在话题边界。

        Args:
            messages: 缓冲区中的消息列表

        Returns:
            TopicJudgmentResult:
            - has_boundary=True 时，boundary_position 指示切分位置
            - has_boundary=False 时，表示话题仍在继续
        """
        if not messages:
            return TopicJudgmentResult(has_boundary=False, boundary_position=0)

        # 构建带编号的对话文本
        dialogue_lines = "\n".join(
            f"[{i+1}] {msg.to_dialogue_line()}"
            for i, msg in enumerate(messages)
        )

        try:
            template = self._get_prompt_template()
            prompt = template.format(
                count=len(messages),
                dialogue_lines=dialogue_lines,
            )

            response = self.llm_client.call_with_retry(
                prompt=prompt,
                response_format="json",
                temperature=0.3,
                max_tokens=500,
            )

            result = self._parse_response(response, len(messages))
            logger.info(
                f"Topic judgment: boundary={'at ' + str(result.boundary_position) if result.has_boundary else 'not found'}"
                f" ({len(messages)} messages)"
            )
            return result

        except Exception as e:
            logger.warning(f"Topic judgment failed, defaulting to no boundary: {e}")
            return TopicJudgmentResult(has_boundary=False, boundary_position=0)

    def _parse_response(self, response: str | dict, message_count: int) -> TopicJudgmentResult:
        """解析 LLM 返回的 JSON 响应。

        Args:
            response: LLM 返回的 JSON（字符串或已解析的字典）
            message_count: 消息总数，用于验证 boundary_position

        Returns:
            TopicJudgmentResult
        """
        try:
            if isinstance(response, dict):
                data = response
            else:
                data = parse_json(response)

            if not isinstance(data, dict):
                logger.warning(f"Unexpected judgment response type: {type(data)}")
                return TopicJudgmentResult(has_boundary=False, boundary_position=0)

            found = data.get("boundary_found", False)
            position = data.get("boundary_position", 0)

            # 类型安全处理
            if isinstance(found, str):
                found = found.lower() == "true"
            found = bool(found)

            try:
                position = int(position)
            except (TypeError, ValueError):
                position = 0

            # 验证 boundary_position 范围
            if found:
                if position <= 0 or position >= message_count:
                    logger.warning(
                        f"boundary_position {position} out of range [1, {message_count}), "
                        f"treating as no boundary"
                    )
                    return TopicJudgmentResult(has_boundary=False, boundary_position=0)
                return TopicJudgmentResult(has_boundary=True, boundary_position=position)
            else:
                return TopicJudgmentResult(has_boundary=False, boundary_position=0)

        except Exception as e:
            logger.warning(f"Failed to parse topic judgment response: {e}")
            return TopicJudgmentResult(has_boundary=False, boundary_position=0)
