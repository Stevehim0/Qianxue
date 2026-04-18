"""写入层模块。

负责将外部事件转换为记忆系统的内部表示。

Phase 5: 步骤1原始记录（RawRecorder）
Phase 6: 步骤2并行处理（WriterPipeline）
Buffer: 消息缓冲与话题边界判断（BufferManager）
"""

from Memory.writer.raw_recorder import RawRecorder, raw_recorder
from Memory.writer.pipeline import WriterPipeline
from Memory.writer.buffer import BufferedMessage, MessageBuffer, SourceKey, TopicJudgmentResult
from Memory.writer.topic_judge import TopicJudge
from Memory.writer.buffer_manager import BufferManager

__all__ = [
    "RawRecorder",
    "raw_recorder",
    "WriterPipeline",
    "BufferedMessage",
    "MessageBuffer",
    "SourceKey",
    "TopicJudgmentResult",
    "TopicJudge",
    "BufferManager",
]
