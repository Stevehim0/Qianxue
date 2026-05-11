"""L0摘要生成任务。

使用LLM从第一人称主观视角生成一句话摘要，
生成embedding向量并存储到数据库和ChromaDB。
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from Memory.llm.base import BaseLLMClient
from Memory.config.settings import settings
from Memory.embedding.model import EmbeddingService
from Memory.embedding.vector_store import VectorStore
from Memory.storage.experience_store import ExperienceStore, Experience

logger = logging.getLogger(__name__)


def generate_l0_summary(
    experience_id: str,
    dialogue: str,
    llm_client: BaseLLMClient,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    experience_store: ExperienceStore,
    stable_text: str = "",
) -> str:
    """生成L0摘要并存储。

    Args:
        experience_id: 体验节点ID
        dialogue: 长对话（多轮对话，标注说话者）
        llm_client: LLM客户端实例
        embedding_service: Embedding服务实例
        vector_store: 向量存储实例
        experience_store: 体验存储实例

    Returns:
        L0摘要文本

    Raises:
        Exception: LLM调用失败时抛出异常（不降级）

    Examples:
        >>> from Memory.llm.factory import LLMFactory
        >>> from Memory.embedding.model import embedding_service
        >>> from Memory.embedding.vector_store import vector_store
        >>> from Memory.storage.experience_store import experience_store
        >>>
        >>> llm_client = LLMFactory.create_client()
        >>> dialogue = \"\"\"
        ... 张三：你好
        ... AI：你好呀，有什么可以帮助你的吗？
        ... 张三：我想问一下Python的事
        ... \"\"\"
        >>> l0_text = generate_l0_summary(
        ...     experience_id="exp_20260331_120000",
        ...     dialogue=dialogue,
        ...     llm_client=llm_client,
        ...     embedding_service=embedding_service,
        ...     vector_store=vector_store,
        ...     experience_store=experience_store
        ... )
        >>> print(l0_text)
        张三向我问Python的问题，我感到乐意帮助
    """
    # ========== Step 1: 加载Prompt模板 ==========
    prompt_template = _load_prompt_template()
    prompt = prompt_template.format(dialogue=dialogue, ai_personality=stable_text or "无", bot_name=settings.writer.bot_name)

    logger.debug(f"Generating L0 summary for {experience_id} from dialogue")

    # ========== Step 2: 调用LLM生成摘要 ==========
    try:
        l0_text = llm_client.call_with_retry(
            prompt=prompt,
            response_format="text",  # 返回文本而非JSON
            temperature=0.7,  # 略高温度增加表达多样性
            max_tokens=200,  # 摘要较短，200 token足够
        )
        l0_text = l0_text.strip()

        logger.debug(f"LLM generated L0 summary: {l0_text}")

    except Exception as e:
        logger.error(f"LLM call failed for L0 summary generation: {e}")
        # 不降级，直接抛出异常（全部失败策略）
        raise

    # ========== Step 3: 生成embedding向量 ==========
    embedding = embedding_service.encode(l0_text)
    logger.debug(f"Generated embedding: shape={embedding.shape}, dtype={embedding.dtype}")

    # ========== Step 4: 存储到数据库（experiences表） ==========
    # 获取现有Experience对象
    experience = experience_store.get(experience_id)
    if experience is None:
        raise ValueError(f"Experience {experience_id} not found")

    # 更新L0字段
    experience.L0_text = l0_text
    experience.L0_embedding = embedding  # numpy数组

    success = experience_store.update(experience)
    if not success:
        raise RuntimeError(f"Failed to update experience {experience_id} with L0 summary")

    logger.debug(f"Updated experience {experience_id} with L0 summary")

    # ========== Step 5: 存储到ChromaDB（experience_L0集合） ==========
    # ChromaDB要求embedding是list格式
    vector_store.add_experience(
        exp_id=experience_id,
        embedding=embedding.tolist(),
        metadata={"L0_text": l0_text, "created_at": experience.created_at},
    )
    logger.debug(f"Added L0 vector to ChromaDB: {experience_id}")

    return l0_text


def _load_prompt_template() -> str:
    """加载L0摘要生成Prompt模板。

    Returns:
        Prompt模板字符串

    Raises:
        FileNotFoundError: 模板文件不存在
    """
    prompt_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "write_L0_summary.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template
