"""Agent思考结果数据结构."""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class ThoughtStatus(str, Enum):
    """思考状态"""
    THINKING = "thinking"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETE = "complete"
    FAILED = "failed"


class AgentThought(BaseModel):
    """Agent思考结果

    集成ReplyThinker的输出，支持多轮思考
    """
    # 基础信息
    status: ThoughtStatus = Field(default=ThoughtStatus.THINKING)
    iteration: int = Field(default=0, description="当前思考轮次")

    # 思考内容
    should_reply: bool = Field(default=False, description="是否需要回复")
    reason: str = Field(default="", description="决策理由")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # 回复指令
    reply_instruction: str = Field(default="", description="回复内容")
    reply_target: Optional[str] = Field(default=None, description="回复目标")

    # 上下文分析(复用ReplyThinker的输出)
    current_topic: str = Field(default="")
    user_profile_summary: str = Field(default="")
    relevant_memories: List[str] = Field(default_factory=list)
    conversation_flow: Optional[str] = None
    main_participants: List[str] = Field(default_factory=list)
    topic_change: Optional[str] = None
    emotion_atmosphere: Optional[str] = None

    # 工具调用计划
    planned_tools: List[str] = Field(default_factory=list, description="计划调用的工具")

    # LLM 工具调用相关
    thought_content: str = Field(default="", description="LLM 的思考内容")
    tool_calls: List[dict] = Field(default_factory=list, description="LLM 规划的工具调用")
    done: bool = Field(default=False, description="是否完成思考")

    # 元数据
    error: Optional[str] = Field(default=None, description="错误信息")
