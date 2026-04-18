"""触发检测器模块。

本模块提供召回触发判断和关键词提取功能。
检测三种触发信号：实体命中、时间指代、状态变化。

参考：Memory/召回层设计文档.md §一 触发判断
"""

import logging
import re
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class TriggerDetector:
    """触发检测器。

    检测用户输入是否包含触发召回的信号。
    支持三种触发信号：实体命中、时间指代、状态变化。

    Attributes:
        entity_store: 实体存储，用于实体匹配
    """

    # 时间指代词正则表达式
    TIME_PATTERNS = [
        r"上次",
        r"之前",
        r"那天",
        r"还记得",
        r"最近",
    ]

    # 状态变化模式
    STATE_PATTERNS = [
        r"今天我.*",
        r"我刚才.*",
        r"我刚.*",
    ]

    def __init__(self, entity_store):
        """初始化TriggerDetector。

        Args:
            entity_store: EntityStore实例
        """
        self.entity_store = entity_store
        logger.info("TriggerDetector initialized")

    def should_trigger(self, query: str) -> bool:
        """判断是否应该触发召回。

        Args:
            query: 用户输入查询

        Returns:
            True if should trigger, False otherwise
        """
        # 1. 检查实体命中
        if self._check_entity_hit(query):
            return True

        # 2. 检查时间指代
        if self._check_time_reference(query):
            return True

        # 3. 检查状态变化
        if self._check_state_change(query):
            return True

        return False

    def extract_keywords(self, query: str, context: Dict[str, Any]) -> Optional[List[str]]:
        """从查询中提取关键词。

        Args:
            query: 用户输入查询
            context: 上下文字典

        Returns:
            关键词列表，或None
        """
        # 简化实现：返回查询中的实体名或时间词
        entities = self._extract_entities(query)
        if entities:
            return entities

        time_words = self._extract_time_words(query)
        if time_words:
            return time_words

        return [query]

    def _check_entity_hit(self, query: str) -> bool:
        """检查实体命中"""
        entities = self.entity_store.get_all()
        for entity in entities:
            if entity.name in query:
                return True
        return False

    def _check_time_reference(self, query: str) -> bool:
        """检查时间指代"""
        for pattern in self.TIME_PATTERNS:
            if re.search(pattern, query):
                return True
        return False

    def _check_state_change(self, query: str) -> bool:
        """检查状态变化"""
        for pattern in self.STATE_PATTERNS:
            if re.search(pattern, query):
                return True
        return False

    def _extract_entities(self, query: str) -> List[str]:
        """提取查询中的实体名"""
        entities = []
        all_entities = self.entity_store.get_all()
        for entity in all_entities:
            if entity.name in query:
                entities.append(entity.name)
        return entities

    def _extract_time_words(self, query: str) -> List[str]:
        """提取查询中的时间指代词"""
        words = []
        for pattern in self.TIME_PATTERNS:
            matches = re.findall(pattern, query)
            words.extend(matches)
        return words
