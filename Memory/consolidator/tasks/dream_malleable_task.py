"""梦境可塑层演化任务。

分析近期经历，判断AI外在表现是否需要调整，将新的可塑层推送给主系统。
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

import requests

from Memory.storage.experience_store import ExperienceStore
from Memory.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def dream_malleable(
    llm_client: BaseLLMClient,
    experience_store: ExperienceStore,
    backend_url: str = "http://localhost:8000",
) -> Dict[str, Any]:
    """梦境可塑层演化任务。

    流程：
    1. 查询最近2天的体验 L0 summary
    2. 从主系统获取当前核心层
    3. LLM 分析，输出新可塑层 YAML
    4. 推送给主系统更新

    Args:
        llm_client: LLM客户端
        experience_store: 体验存储
        backend_url: 主系统地址

    Returns:
        统计信息字典
    """
    start_time = time.time()

    try:
        # Step 1: 获取近期经历
        cutoff = (datetime.now() - timedelta(days=2)).isoformat()
        now = datetime.now().isoformat()
        recent_experiences = experience_store.get_by_time_range(cutoff, now)

        if not recent_experiences:
            logger.info("dream_malleable: 无近期经历，跳过")
            return {
                "status": "skipped",
                "reason": "no_recent_experiences",
                "experience_count": 0,
                "duration_seconds": time.time() - start_time,
            }

        # 拼接 L0 summary
        exp_summaries = []
        for exp in recent_experiences:
            summary = exp.L0_text or ""
            if summary:
                emotion = f" [{exp.emotion_category}]" if exp.emotion_category else ""
                exp_summaries.append(f"- {summary}{emotion}")

        experiences_text = "\n".join(exp_summaries) if exp_summaries else "无摘要信息"

        logger.info(f"dream_malleable: 获取到 {len(recent_experiences)} 条近期经历")

        # Step 2: 从主系统获取核心层
        core_data = _fetch_core_identity(backend_url)
        if not core_data:
            return {
                "status": "failed",
                "reason": "cannot_reach_backend",
                "experience_count": len(recent_experiences),
                "duration_seconds": time.time() - start_time,
            }

        stable_text = core_data.get("stable_text", "")
        current_malleable = core_data.get("malleable_yaml", "")

        # Step 3: 加载 prompt 模板
        prompt_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "dream_malleable.txt"
        prompt_template = prompt_path.read_text(encoding="utf-8")

        prompt = prompt_template.format(
            stable_text=stable_text,
            current_malleable=current_malleable,
            recent_experiences=experiences_text,
        )

        # Step 4: LLM 分析（必须用 text 格式，不能用 json，否则 YAML 会被解析为 list）
        new_malleable = llm_client.call(
            prompt=prompt,
            system_prompt="你是AI人设演化分析系统，只输出YAML，不做其他解释。",
            temperature=0.3,
            response_format="text",
        )

        if not new_malleable:
            logger.info("dream_malleable: LLM 返回空，跳过")
            return {
                "status": "skipped",
                "reason": "empty_llm_response",
                "experience_count": len(recent_experiences),
                "duration_seconds": time.time() - start_time,
            }

        # LLM 返回非字符串类型（list/dict），说明输出格式不对，直接拒绝
        if not isinstance(new_malleable, str):
            logger.warning(f"dream_malleable: LLM 返回非字符串类型 {type(new_malleable).__name__}，跳过")
            return {
                "status": "skipped",
                "reason": f"invalid_type_{type(new_malleable).__name__}",
                "experience_count": len(recent_experiences),
                "duration_seconds": time.time() - start_time,
            }

        if not new_malleable.strip():
            logger.info("dream_malleable: LLM 返回空白，跳过")
            return {
                "status": "skipped",
                "reason": "blank_llm_response",
                "experience_count": len(recent_experiences),
                "duration_seconds": time.time() - start_time,
            }

        # 清理 LLM 输出（可能包含 ```yaml 标记）
        new_malleable = _clean_yaml_output(new_malleable)

        # 验证是合法 YAML 且包含必要结构
        if not _validate_malleable_yaml(new_malleable):
            logger.warning("dream_malleable: LLM 输出不是合法的可塑层 YAML，跳过")
            return {
                "status": "skipped",
                "reason": "invalid_yaml_structure",
                "experience_count": len(recent_experiences),
                "duration_seconds": time.time() - start_time,
            }

        # Step 5: 推送给主系统
        success = _push_malleable_update(backend_url, new_malleable)

        duration = time.time() - start_time
        result = {
            "status": "completed" if success else "failed",
            "experience_count": len(recent_experiences),
            "updated": success,
            "duration_seconds": duration,
        }

        logger.info(f"dream_malleable: {result}")
        return result

    except Exception as e:
        logger.error(f"dream_malleable failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "experience_count": 0,
            "duration_seconds": time.time() - start_time,
        }


def _fetch_core_identity(backend_url: str) -> Optional[Dict[str, Any]]:
    """从主系统获取核心层信息。"""
    try:
        resp = requests.get(
            f"{backend_url}/api/core/identity",
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            logger.warning(f"获取核心层失败: {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"无法连接主系统: {e}")
        return None


def _push_malleable_update(backend_url: str, new_yaml: str) -> bool:
    """推送可塑层更新到主系统。"""
    try:
        resp = requests.post(
            f"{backend_url}/api/core/malleable",
            json={
                "malleable_yaml": new_yaml,
                "reason": "dream_malleable_evolution",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("success", False)
        else:
            logger.warning(f"推送可塑层失败: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"推送可塑层异常: {e}")
        return False


def _clean_yaml_output(text: str) -> str:
    """清理 LLM 输出中可能包含的 YAML 标记。"""
    text = text.strip()
    # 去除 ```yaml 和 ```
    if text.startswith("```yaml"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _validate_malleable_yaml(text: str) -> bool:
    """验证输出是否是合法的可塑层 YAML 结构。

    必须包含 style/preferences/emotional 中的至少一个顶级键，
    且能被 YAML 解析器正确解析为 dict。
    """
    try:
        import yaml
        parsed = yaml.safe_load(text)
        if not isinstance(parsed, dict):
            return False
        required_keys = {"style", "preferences", "emotional"}
        if not required_keys.intersection(parsed.keys()):
            return False
        return True
    except Exception:
        return False
