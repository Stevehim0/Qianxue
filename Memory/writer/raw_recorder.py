"""原始事件记录器。

负责写入层步骤1：接收原始事件，存储L3完整原文到experiences表，
自动附加上下文快照（状态层信息+时间推导）。

核心职责：
- 宽松写入：零结构化要求，先接住所有内容
- 最小化处理：只做必要的上下文附加，不调用LLM
- 不丢东西：L3原始记录原封不动存入

上下文快照来源：
- 状态层：focus/mood（从StateManager读取）
- 时间推导：time_of_day/silence_before（从timestamp推导）
- 外部传入：task等额外上下文（可选）

Phase 5: 步骤1原始记录（本阶段）
Phase 6: 步骤2并行处理（L0摘要/实体识别/情感分析）
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from Memory.storage.experience_store import Experience, experience_store as global_experience_store
from Memory.state.manager import StateManager, DefaultStateManager

logger = logging.getLogger(__name__)


@dataclass
class EventContext:
    """事件上下文数据类。

    Attributes:
        task: 外部任务描述（可选）
        extra: 扩展字段（可选）
    """

    task: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class RawRecorder:
    """原始事件记录器。

    负责写入层步骤1：接收原始事件，存储L3完整原文，
    自动附加上下文快照（状态层+时间推导）。

    Examples:
        >>> recorder = RawRecorder()
        >>> exp_id = recorder.record_event(role="user", content="你好")
        >>> print(exp_id)
        exp_20260331_120000
    """

    # 时段边界定义（来自05-CONTEXT.md）
    TIME_OF_DAY_BOUNDARIES = {
        "凌晨": (5, 8),
        "上午": (8, 12),
        "下午": (12, 18),
        "傍晚": (18, 22),
        "深夜": (22, 24),  # 包含22-24和0-5
    }

    # 首次调用silence_before默认值（秒）
    DEFAULT_SILENCE_BEFORE = 300

    # 对话事件角色过滤（用于silence_before查询）
    CONVERSATION_ROLES = {"user", "assistant"}

    def __init__(self, experience_store=None, state_manager: Optional[StateManager] = None):
        """初始化原始事件记录器。

        Args:
            experience_store: 体验节点存储实例，默认使用全局experience_store
            state_manager: 状态管理器实例，默认使用DefaultStateManager
        """
        self.experience_store = experience_store if experience_store is not None else global_experience_store
        self.state_manager = state_manager if state_manager is not None else DefaultStateManager()
        self.logger = logging.getLogger(__name__)

    def record_event(
        self,
        dialogue: str,
        timestamp: Optional[float] = None,
        external_context: Optional[EventContext] = None,
    ) -> str:
        """记录原始事件。

        Args:
            dialogue: 长对话格式（多行字符串，每行标注说话者）
                      示例：
                      张三：你好
                      AI：你好呀，有什么可以帮助你的吗？
                      张三：我想问一下Python的事
            timestamp: 事件时间戳（Unix时间戳），默认当前时间
            external_context: 外部上下文（task等）

        Returns:
            创建的体验节点ID（格式：exp_YYYYMMDD_HHmmss）

        Raises:
            ValueError: dialogue为空或格式错误
            sqlite3.IntegrityError: experience_id重复

        Examples:
            >>> recorder = RawRecorder()
            >>> dialogue = '''
            ... 张三：你好
            ... AI：你好呀，有什么可以帮助你的吗？
            ... 张三：我想问一下Python的事
            ... '''
            >>> exp_id = recorder.record_event(dialogue=dialogue)
            >>> print(exp_id)
            exp_20260331_120000
        """
        # 1. 参数验证
        if not dialogue or not isinstance(dialogue, str):
            raise ValueError("dialogue must be a non-empty string")

        # 2. 时间戳处理
        if timestamp is None:
            timestamp = time.time()

        # 3. 读取状态层上下文（写入前读取，保证状态时间戳与experience记录对齐）
        mood = self.state_manager.get_mood()
        focus = self.state_manager.get_focus()

        # 4. 时间推导
        time_of_day = self._derive_time_of_day(timestamp)
        # silence_before不再依赖role参数，查询所有对话事件
        silence_before = self._calculate_silence_before_general(timestamp)

        # 5. 构建Experience对象
        exp_id = self._generate_exp_id(timestamp)
        experience = Experience(
            id=exp_id,
            L3_raw=dialogue,  # L3完整原文，永不修改
            context_focus=focus,
            context_mood=f"{mood.label} (valence:{mood.valence}, arousal:{mood.arousal})",
            context_time_of_day=time_of_day,
            context_silence_before=str(silence_before),
            context_task=external_context.task if external_context else None,
            context_extra=(
                str(external_context.extra) if external_context and external_context.extra else None
            ),
            created_at=datetime.fromtimestamp(timestamp).isoformat(),
        )

        # 6. 写入数据库
        try:
            created_id = self.experience_store.create(experience)
            self.logger.debug(
                f"Recorded event: {created_id} (time_of_day={time_of_day})"
            )
            return created_id
        except Exception as e:
            self.logger.error(f"Failed to record event: {e}")
            raise

    def record_message(self, dialogue: str, timestamp: Optional[float] = None) -> str:
        """记录对话（便捷方法）。

        Args:
            dialogue: 长对话格式（多行字符串，每行标注说话者）
            timestamp: 事件时间戳，默认当前时间

        Returns:
            创建的体验节点ID

        Examples:
            >>> recorder = RawRecorder()
            >>> dialogue = "张三：你好\\nAI：你好呀"
            >>> exp_id = recorder.record_message(dialogue=dialogue)
        """
        return self.record_event(dialogue=dialogue, timestamp=timestamp)

    def _derive_time_of_day(self, timestamp: float) -> str:
        """从时间戳推导时段分类。

        Args:
            timestamp: Unix时间戳

        Returns:
            时段标签（凌晨/上午/下午/傍晚/深夜）

        Note:
            时段边界定义：
            - 凌晨：05:00-08:00
            - 上午：08:00-12:00
            - 下午：12:00-18:00
            - 傍晚：18:00-22:00
            - 深夜：22:00-05:00
        """
        dt = datetime.fromtimestamp(timestamp)
        hour = dt.hour

        # 时段分类（左闭右开区间）
        if 5 <= hour < 8:
            return "凌晨"
        elif 8 <= hour < 12:
            return "上午"
        elif 12 <= hour < 18:
            return "下午"
        elif 18 <= hour < 22:
            return "傍晚"
        else:  # 22 <= hour < 24 or 0 <= hour < 5
            return "深夜"

    def _calculate_silence_before_general(self, current_timestamp: float) -> int:
        """计算距上一条对话事件的时间差（通用版本，不依赖role）。

        Args:
            current_timestamp: 当前事件时间戳

        Returns:
            时间差（秒）

        Note:
            - 查询所有体验事件，不区分角色
            - 首次调用返回默认值300秒
            - 时间单位：秒（整数）
        """
        from Memory.storage.database import db_manager

        # 查询最后一条对话事件
        with db_manager.transaction() as cursor:
            cursor.execute(
                """
                SELECT created_at FROM experiences
                ORDER BY created_at DESC
                LIMIT 1
            """
            )

            row = cursor.fetchone()

            if row is None:
                # 数据库为空，返回默认值
                return self.DEFAULT_SILENCE_BEFORE

            # 解析created_at时间戳
            last_created_at = row[0]
            last_timestamp = datetime.fromisoformat(last_created_at).timestamp()

            # 计算时间差（向下取整到整数秒）
            silence_seconds = int(current_timestamp - last_timestamp)
            return max(0, silence_seconds)  # 确保非负

    def _calculate_silence_before(self, current_timestamp: float, current_role: str) -> int:
        """计算距上一条对话事件的时间差（已废弃，保留用于向后兼容）。

        Args:
            current_timestamp: 当前事件时间戳
            current_role: 当前事件角色（已废弃）

        Returns:
            时间差（秒）

        Note:
            - 此方法已废弃，使用_calculate_silence_before_general替代
            - 保留用于向后兼容
        """
        return self._calculate_silence_before_general(current_timestamp)

    def _generate_exp_id(self, timestamp: float) -> str:
        """生成体验节点ID。

        Args:
            timestamp: Unix时间戳

        Returns:
            体验节点ID（格式：exp_YYYYMMDD_HHmmss）

        Examples:
            >>> _generate_exp_id(1711886400.0)
            exp_20260331_120000
        """
        dt = datetime.fromtimestamp(timestamp)
        return f"exp_{dt.year:04d}{dt.month:02d}{dt.day:02d}_{dt.hour:02d}{dt.minute:02d}{dt.second:02d}"


# 全局RawRecorder实例
raw_recorder = RawRecorder()
