"""梦境模块分层采样策略。

Per D-02: 模拟梦境的随机性+重要性混合特性。
Per D-04: 全库扫描选择记忆（不受巩固批次限制）。
"""

from typing import List

from Memory.storage.experience_store import ExperienceStore, Experience
from Memory.config.settings import settings

logger = __import__("logging").getLogger(__name__)


def select_memories_for_dream(
    experience_store: ExperienceStore, total_count: int = None
) -> List[Experience]:
    """分层混合采样：重要记忆40% + 随机60%。

    Per D-02: 模拟梦境的随机性+重要性混合特性。
    Per D-04: 全库扫描选择记忆（不受巩固批次限制）。

    Args:
        experience_store: ExperienceStore实例
        total_count: 要选择的总记忆数（默认使用配置）

    Returns:
        选中的体验节点列表（40%重要 + 60%随机）
    """
    # Use configured batch size if not specified
    if total_count is None:
        total_count = settings.dream.reorganize_batch_size

    # Calculate split (D-02: 40% important, 60% random)
    important_ratio = settings.dream.important_ratio
    important_count = int(total_count * important_ratio)
    random_count = total_count - important_count

    # Step 1: Get important memories (highest importance)
    important_memories = experience_store.get_top_by_importance(important_count)

    # Step 2: Get random memories (excluding important ones)
    important_ids = [exp.id for exp in important_memories]
    random_memories = experience_store.get_random_excluding(random_count, exclude_ids=important_ids)

    # Step 3: Combine and return
    return important_memories + random_memories
