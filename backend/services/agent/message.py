"""Agent统一消息格式."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from datetime import datetime


class AgentMessage(BaseModel):
    """Agent统一消息格式

    整合NapCat消息格式，提供统一的消息接口
    """
    # 来源标识
    source: str = Field(default="qq", description="消息来源: 'qq'")

    # 消息元数据
    group_id: str = Field(default="heartbeat", description="群聊ID")
    user_id: str = Field(default="system", description="用户ID")
    sender_nickname: Optional[str] = Field(default=None, description="发送者昵称")

    # 消息内容
    content: str = Field(default="", description="纯文本内容")
    raw_message: Optional[str] = Field(default=None, description="原始消息")

    # 扩展信息
    is_mentioned: bool = Field(default=False, description="是否@机器人")
    mentions: List[Dict] = Field(default_factory=list, description="@信息列表")

    # 图片信息
    has_image: bool = Field(default=False, description="是否包含图片")
    image_url: Optional[str] = Field(default=None, description="图片URL")
    image_type: str = Field(default="无图片", description="图片类型: 表情包/普通图片")
    image_description: Optional[str] = Field(default=None, description="图片描述(已识别)")

    # 回复信息
    reply_content: Optional[str] = Field(default=None, description="被引用回复的原始消息内容")
    reply_sender: Optional[str] = Field(default=None, description="被引用回复的原始消息发送者昵称")
    reply_sender_id: Optional[str] = Field(default=None, description="被引用回复的原始消息发送者QQ号")

    # 语音信息
    has_voice: bool = Field(default=False, description="是否包含语音")
    voice_url: Optional[str] = Field(default=None, description="语音文件URL")
    voice_transcription: Optional[str] = Field(default=None, description="语音转写文本")

    # 时间戳
    timestamp: datetime = Field(default_factory=datetime.now)

    # 优先级标记(@消息优先)
    priority: int = Field(default=0, description="消息优先级: @消息=10, 普通=0")

    # 心跳标记
    is_heartbeat: bool = Field(default=False, description="是否为心跳触发的主动思考")

    # 私聊标记
    is_private: bool = Field(default=False, description="是否为私聊消息")

    # 心跳附加上下文（仅心跳消息使用）
    heartbeat_group_summaries: Optional[Dict] = Field(default=None, description="各群消息摘要")

    @property
    def is_computer(self) -> bool:
        """是否来自本地电脑聊天."""
        return self.source == "computer"

    @classmethod
    def create_heartbeat(cls, group_summaries: Optional[Dict] = None) -> "AgentMessage":
        """创建心跳消息（虚拟消息，不来自真实用户）。

        Args:
            group_summaries: 各群的消息摘要 {group_id: formatted_text}
        """
        return cls(
            source="heartbeat",
            group_id="heartbeat",
            user_id="system",
            sender_nickname="心跳系统",
            content="[心跳触发] 主动感知时刻",
            is_heartbeat=True,
            heartbeat_group_summaries=group_summaries or {},
            priority=0,
        )
