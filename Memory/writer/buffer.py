"""消息缓冲数据结构。

提供按来源缓冲消息的核心数据结构，支持阈值检查和话题边界切分。
"""

import threading
import time
from dataclasses import dataclass
from typing import List, Tuple

# 来源标识类型：(source_type, source_id)
# 例如: ("qq_group", "12345"), ("qq_private", "user_678")
SourceKey = Tuple[str, str]


@dataclass
class BufferedMessage:
    """缓冲区中的单条消息。

    Attributes:
        speaker: 说话者名称（如 "张三", "AI"）
        content: 消息文本内容
        timestamp: Unix 时间戳
        role: 角色 ("user" 或 "assistant")
    """

    speaker: str
    content: str
    timestamp: float
    role: str

    def to_dialogue_line(self) -> str:
        """转换为对话格式: 'speaker：content'"""
        return f"{self.speaker}：{self.content}"


@dataclass
class TopicJudgmentResult:
    """话题边界判断结果。

    Attributes:
        has_boundary: 是否在当前缓冲区中找到了话题边界
        boundary_position: 话题边界位置（exclusive），即 messages[0:position] 构成一个完整话题
                           仅在 has_boundary=True 时有意义
    """

    has_boundary: bool
    boundary_position: int


class MessageBuffer:
    """按来源管理消息缓冲区。

    线程安全的消息缓冲区，支持：
    - 追加消息并检查是否达到阈值
    - 按位置排空（取出已完成话题的消息）
    - 全量排空（超时强制写入）
    - 阈值递进（30 → 60 → 90 → ... → max_threshold）

    Examples:
        >>> buf = MessageBuffer("qq_group", "12345", buffer_config)
        >>> should_check, count = buf.append(BufferedMessage("张三", "你好", time.time(), "user"))
        >>> if should_check:
        ...     # 触发话题判断
    """

    def __init__(self, source_type: str, source_id: str, config):
        """初始化消息缓冲区。

        Args:
            source_type: 来源类型（如 "qq_group"）
            source_id: 来源标识（如群号）
            config: BufferConfig 实例
        """
        self.source_type = source_type
        self.source_id = source_id
        self._messages: List[BufferedMessage] = []
        self._lock = threading.Lock()
        self._last_append_time: float = time.time()
        self._next_threshold: int = config.initial_threshold
        self._config = config

    def append(self, message: BufferedMessage) -> Tuple[bool, int]:
        """追加消息到缓冲区。

        Args:
            message: 要缓冲的消息

        Returns:
            (should_check_topic, current_count)
            - should_check_topic: 是否达到了话题判断阈值
            - current_count: 当前缓冲区中的消息总数
        """
        with self._lock:
            self._messages.append(message)
            self._last_append_time = time.time()
            count = len(self._messages)
            should_check = count >= self._next_threshold
            return should_check, count

    def get_messages(self) -> List[BufferedMessage]:
        """返回缓冲区中所有消息的副本。"""
        with self._lock:
            return list(self._messages)

    def drain_up_to(self, position: int) -> List[BufferedMessage]:
        """取出 messages[0:position]，剩余消息保留在缓冲区。

        Args:
            position: 取出到此位置（exclusive）

        Returns:
            被取出的消息列表
        """
        with self._lock:
            drained = self._messages[:position]
            self._messages = self._messages[position:]
            # 重置阈值到初始值
            self._next_threshold = self._config.initial_threshold
            # 如果剩余消息已经超过新阈值，直接设置到下一个
            remaining = len(self._messages)
            if remaining >= self._next_threshold:
                self._next_threshold = (
                    (remaining // self._config.threshold_step + 1)
                    * self._config.threshold_step
                )
                self._next_threshold = min(self._next_threshold, self._config.max_threshold)
            return drained

    def drain_all(self) -> List[BufferedMessage]:
        """取出缓冲区中的全部消息。

        Returns:
            所有缓冲消息列表
        """
        with self._lock:
            drained = self._messages
            self._messages = []
            self._next_threshold = self._config.initial_threshold
            return drained

    def seconds_since_last_append(self) -> float:
        """返回距上次追加消息的秒数。"""
        return time.time() - self._last_append_time

    @property
    def next_threshold(self) -> int:
        """下次触发话题判断的消息数阈值。"""
        return self._next_threshold

    def advance_threshold(self) -> int:
        """将阈值推进到下一档（30 → 60 → 90 → ... → max_threshold）。

        Returns:
            新的阈值
        """
        with self._lock:
            self._next_threshold = min(
                self._next_threshold + self._config.threshold_step,
                self._config.max_threshold,
            )
            return self._next_threshold

    @property
    def count(self) -> int:
        """当前缓冲区消息数。"""
        with self._lock:
            return len(self._messages)
