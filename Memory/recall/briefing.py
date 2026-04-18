"""记忆简报生成器模块。

将召回的体验+实体综合成自然语言简报，同时过滤掉不相关的记忆。
一次LLM调用完成过滤+简报生成。
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict

from Memory.llm.base import BaseLLMClient
from Memory.recall.result import RecallResult, EntityRecallResult

logger = logging.getLogger(__name__)


class BriefingGenerator:
    """记忆简报+过滤生成器。

    一次LLM调用，同时完成：
    1. 过滤：判断哪些候选记忆值得提起
    2. 简报：基于被选中的记忆生成自然语言内心独白
    """

    def __init__(self, llm_client: BaseLLMClient, stable_text: str = ""):
        self.llm_client = llm_client
        self._stable_text = stable_text
        self.prompt_template = self._load_template()

    def _load_template(self) -> str:
        template_path = (
            Path(__file__).parent.parent / "config" / "prompts" / "memory_briefing.txt"
        )
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        logger.warning(f"Template not found: {template_path}, using fallback")
        return self._fallback_template()

    def _fallback_template(self) -> str:
        return (
            "审视以下候选记忆，判断哪些值得提起，并生成简报。\n\n"
            "AI性格:\n{ai_personality}\n\n"
            "用户输入: {query}\n\n"
            "过往经历:\n{experiences_text}\n\n"
            "相关信息:\n{entities_text}\n\n"
            "对话:\n{recent_history}\n\n"
            "心情: {ai_mood}, 精力: {ai_energy}, 关注点: {ai_focus}\n\n"
            "返回JSON: {{\"selected_experiences\": [], \"selected_entities\": [], \"briefing\": \"...\"}}"
        )

    def generate(
        self,
        experiences: List[RecallResult],
        entities: List[EntityRecallResult],
        query: str,
        context: dict,
    ) -> Optional[Dict]:
        """过滤+简报生成（一次LLM调用）。

        Args:
            experiences: 体验层召回结果
            entities: 信息层召回结果
            query: 用户查询
            context: 上下文（recent_history, ai_state）

        Returns:
            成功时返回:
            {
                "briefing": str,
                "selected_exp_indices": List[int],
                "selected_ent_indices": List[int],
            }
            失败返回 None
        """
        # 格式化体验（编号列表）
        exp_lines = []
        for i, exp in enumerate(experiences):
            line = f"[{i}] {exp.L1_text or exp.L0_text}"
            if exp.emotion_category:
                line += f"（{exp.emotion_category}）"
            if exp.time_distance_days:
                from Memory.utils.time_utils import format_time_distance
                distance_str = format_time_distance(exp.time_distance_days)
                if distance_str:
                    line += f"（{distance_str}）"
            exp_lines.append(line)
        experiences_text = "\n".join(exp_lines) if exp_lines else "无"

        # 格式化实体（编号列表）
        ent_lines = []
        for i, ent in enumerate(entities):
            parts = f"[{i}] {ent.name}({ent.type})"
            if ent.properties:
                key_props = [
                    f"{k}={v}" for k, v in list(ent.properties.items())[:2]
                ]
                parts += f" [{', '.join(key_props)}]"
            ent_lines.append(parts)
        entities_text = "\n".join(ent_lines) if ent_lines else "无"

        # 格式化对话历史
        history = context.get("recent_history", [])
        logger.info(f"Briefing context: {len(history)} history messages")
        history_text = "\n".join(
            f"{msg.get('role', '?')}: {msg.get('content', '')}"
            for msg in history[-5:]
        ) if history else "（无历史对话）"

        # AI 状态
        ai_state = context.get("ai_state", {})

        # 构建 prompt
        prompt = self.prompt_template.format(
            query=query,
            experiences_text=experiences_text,
            entities_text=entities_text,
            recent_history=history_text,
            ai_mood=ai_state.get("mood", "平静"),
            ai_energy=ai_state.get("energy", "正常"),
            ai_focus=ai_state.get("focus", "无"),
            ai_personality=self._stable_text or "无",
        )

        # 一次 LLM 调用
        try:
            result = self.llm_client.call_with_retry(
                prompt=prompt, response_format="json"
            )

            # 解析结果
            if isinstance(result, dict):
                parsed = result
            else:
                parsed = json.loads(result)

            selected_exp = parsed.get("selected_experiences", [])
            selected_ent = parsed.get("selected_entities", [])
            briefing = parsed.get("briefing", "")

            # 校验索引范围
            selected_exp = [i for i in selected_exp if 0 <= i < len(experiences)]
            selected_ent = [i for i in selected_ent if 0 <= i < len(entities)]

            logger.info(
                f"Briefing generated: selected {len(selected_exp)}/{len(experiences)} exp, "
                f"{len(selected_ent)}/{len(entities)} ent, "
                f"briefing {len(briefing)} chars"
            )

            return {
                "briefing": briefing.strip() if briefing else None,
                "selected_exp_indices": selected_exp,
                "selected_ent_indices": selected_ent,
            }

        except Exception as e:
            logger.warning(f"Failed to generate briefing: {e}")
            return None
