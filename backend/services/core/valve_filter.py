"""核心层阀门过滤器 - 关键词匹配检查不变层底线。"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from backend.services.core.models import Identity

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """过滤结果。

    Attributes:
        passed: 是否通过
        reason: 未通过原因
    """

    passed: bool
    reason: Optional[str] = None


class ValveFilter:
    """阀门过滤器。

    从不变层指令中提取否定关键词，检查消息是否违反底线。
    简单关键词匹配实现，后续可升级为 LLM 语义判断。
    """

    NEGATIVES = ["绝不", "不要", "不", "非", "别", "无", "绝"]

    def __init__(self, identity: Identity):
        self._keywords = self._extract_keywords(identity.invariant_text)

    def check(self, text: str) -> FilterResult:
        """检查文本是否违反底线。

        Args:
            text: 待检查的文本

        Returns:
            FilterResult
        """
        text_lower = text.lower()

        for keyword, original_rule in self._keywords:
            if keyword in text_lower:
                logger.warning(f"阀门拦截: 违反底线 '{original_rule}'")
                return FilterResult(
                    passed=False,
                    reason=f"违反底线：{original_rule}",
                )

        return FilterResult(passed=True)

    def _extract_keywords(self, invariant_text: str) -> List[tuple]:
        """从不变层指令中提取否定关键词。

        Returns:
            [(keyword, original_rule), ...] 列表
        """
        keywords = []

        for line in invariant_text.split("\n"):
            line = line.strip()
            if not line.startswith("-"):
                continue

            rule = line[1:].strip()
            keyword = self._extract_negative_keyword(rule)
            if keyword:
                keywords.append((keyword, rule))

        return keywords

    def _extract_negative_keyword(self, rule: str) -> Optional[str]:
        """从否定句中提取核心关键词。

        "不假装是人类" -> "假装"
        "绝不参与伤害他人的事" -> "伤害"（提取核心动词，跳过虚词）
        """
        for neg in self.NEGATIVES:
            if rule.startswith(neg):
                rest = rule[len(neg):].strip()
                if not rest:
                    return None
                # 跳过常见的虚词（参与、去、要等），提取核心词
                skip_words = ["参与", "去", "要", "会", "能", "敢"]
                for sw in skip_words:
                    if rest.startswith(sw):
                        rest = rest[len(sw):].strip()
                        break
                if rest:
                    return rest[:min(len(rest), 4)]
        return None
