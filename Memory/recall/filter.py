"""后处理过滤器模块（已废弃）。

过滤+简报已合并到 briefing.py 中的 BriefingGenerator，一次LLM调用完成。
本模块不再被使用，保留仅供参考。
"""

import logging
import hashlib
import json
from typing import List, Dict, Optional
from pathlib import Path

from Memory.llm.base import BaseLLMClient
from Memory.recall.result import RecallResult

logger = logging.getLogger(__name__)


class RecallFilter:
    """后处理过滤器 - LLM二分类（RECALL-11）。

    对每个候选记忆调用LLM判断是否应该提起。
    缓存结果避免重复LLM调用（D-10）。

    Attributes:
        llm_client: LLM客户端实例
        cache: 结果缓存 {cache_key: {should_mention, reason, how_to_mention}}
        prompt_template: Prompt模板内容
    """

    def __init__(self, llm_client: BaseLLMClient, stable_text: str = ""):
        """初始化RecallFilter。

        Args:
            llm_client: BaseLLMClient实例
            stable_text: 稳定层文本
        """
        self.llm_client = llm_client
        self._stable_text = stable_text
        self.cache: Dict[str, Dict] = {}

        # 加载prompt模板
        self.prompt_template = self._load_prompt_template()

        logger.info("RecallFilter initialized")

    def _load_prompt_template(self) -> str:
        """加载后处理prompt模板（D-11）"""
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "recall_filter.txt"

        if not prompt_path.exists():
            logger.warning(f"Prompt template not found: {prompt_path}, using default")
            return self._default_prompt()

        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        logger.debug(f"Loaded prompt template from {prompt_path}")
        return template

    def _default_prompt(self) -> str:
        """默认prompt模板（如果recall_filter.txt不存在）"""
        return """你是一个记忆召回过滤器。判断候选记忆是否应该在这个对话中被提起。

# 当前用户输入
{query}

# 候选记忆
recall_hint: {recall_hint}
时间距离: {time_distance_days}天
重要度: {importance}
情感类别: {emotion_category}

# 当前对话上下文
最近对话:
{recent_history}

# AI当前状态
心情: {ai_mood}
精力: {ai_energy}
关注点: {ai_focus}

# 判断规则
1. 宁可不说也不要强行插入
2. 情感冲突时不提
3. 能帮助对话时提
4. 避免重复

# 输出格式（JSON）
{{
  "should_mention": true/false,
  "reason": "简短原因",
  "how_to_mention": "提起方式建议（可选）"
}}"""

    def filter(
        self, candidates: List[RecallResult], query: str, context: dict
    ) -> List[RecallResult]:
        """后处理过滤 - LLM二分类（RECALL-11）。

        对每个候选记忆调用LLM判断should_mention。

        Args:
            candidates: 候选记忆列表
            query: 用户查询
            context: 上下文字典（recent_history, ai_state）

        Returns:
            过滤后的候选记忆列表（只保留should_mention=True）
        """
        filtered = []

        for candidate in candidates:
            # 1. 检查缓存（D-10）
            cache_key = self._compute_cache_key(candidate.experience_id, query, context)
            if cache_key in self.cache:
                cached_result = self.cache[cache_key]
                if cached_result["should_mention"]:
                    candidate.how_to_mention = cached_result.get("how_to_mention")
                    filtered.append(candidate)
                continue

            # 2. LLM判断（D-09）
            prompt = self._build_filter_prompt(candidate, query, context)

            try:
                # 使用call_with_retry而不是call_json
                result_json = self.llm_client.call_with_retry(prompt=prompt, response_format="json")

                # 解析JSON结果 (处理可能的dict返回)
                if isinstance(result_json, dict):
                    result = result_json
                else:
                    result = json.loads(result_json)

                # 3. 处理结果
                if result.get("should_mention", False):
                    candidate.how_to_mention = result.get("how_to_mention")
                    filtered.append(candidate)

                # 4. 缓存结果（D-10）
                self.cache[cache_key] = result

            except Exception as e:
                logger.warning(f"LLM call failed for {candidate.experience_id}: {e}")
                # LLM调用失败，保守策略：不提起
                continue

        logger.debug(f"Filtered {len(candidates)} candidates to {len(filtered)}")
        return filtered

    def _compute_cache_key(self, experience_id: str, query: str, context: dict) -> str:
        """计算缓存键（D-10）。

        键为(记忆ID + 查询 + 对话上下文hash)。
        """
        # 提取最近N条对话历史
        recent_history = context.get("recent_history", [])

        # 简化hash：只取最近3条对话
        history_str = json.dumps(recent_history[-3:], ensure_ascii=False)

        # 计算hash
        key_str = f"{experience_id}_{query}_{history_str}"
        cache_key = hashlib.md5(key_str.encode("utf-8")).hexdigest()

        return cache_key

    def _build_filter_prompt(self, candidate: RecallResult, query: str, context: dict) -> str:
        """构建LLM过滤prompt（D-11）"""
        # 提取上下文
        recent_history = context.get("recent_history", [])
        ai_state = context.get("ai_state", {})

        # 格式化对话历史
        history_text = "\n".join(
            [
                f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                for msg in recent_history[-3:]
            ]
        )  # 最近3条

        # 填充prompt模板
        prompt = self.prompt_template.format(
            query=query,
            recall_hint=candidate.recall_hint or candidate.L0_text,
            time_distance_days=candidate.time_distance_days,
            importance=candidate.importance,
            emotion_category=candidate.emotion_category or "未知",
            recent_history=history_text,
            ai_mood=ai_state.get("mood", "平静"),
            ai_energy=ai_state.get("energy", "正常"),
            ai_focus=ai_state.get("focus", "无"),
            ai_personality=self._stable_text or "无",
        )

        return prompt
