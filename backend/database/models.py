"""数据模型定义."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime


# 用户模型
class User(BaseModel):
    """用户信息模型"""
    user_id: str
    nickname: Optional[str] = None
    user_type: str = Field(default="group_member", pattern="^(friend|group_member)$")
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    message_count: int = 0


# 群聊模型
class Group(BaseModel):
    """群聊信息模型"""
    group_id: str
    group_name: Optional[str] = None
    enabled: bool = True
    auto_reply_enabled: bool = True
    reply_delay_seconds: int = 5


# 对话消息模型
class ConversationMessage(BaseModel):
    """对话消息模型"""
    id: Optional[int] = None
    group_id: str
    user_id: str
    role: str = Field(pattern="^(user|assistant)$")
    content: str
    timestamp: Optional[str] = None


# API配置模型
class ApiConfig(BaseModel):
    """API配置模型"""
    current_api: str = ""
    apis: Dict[str, Dict[str, str]] = {}


class ApiEndpoint(BaseModel):
    """单个API端点配置"""
    api_key: str
    base_url: str
    model: str


# 系统提示词模型
class SystemPromptConfig(BaseModel):
    """系统提示词配置模型"""
    global_system_prompt: str = "你是一个友好的AI助手"
    group_system_prompts: Dict[str, str] = {}


# NapCat消息模型
class NapCatMessage(BaseModel):
    """NapCat消息模型"""
    post_type: str
    message_type: str
    sub_type: Optional[str] = None
    message_id: Optional[int] = None
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    sender: Optional[Dict] = None
    raw_message: Optional[str] = None
    message: Optional[str] = None
    time: Optional[int] = None
    self_id: Optional[int] = None


class MessageSegment(BaseModel):
    """消息片段模型"""
    type: str
    data: Dict[str, str]


# API响应模型
class ApiResponse(BaseModel):
    """通用API响应模型"""
    success: bool
    message: str
    data: Optional[dict] = None


# 测试连接响应
class TestConnectionResponse(ApiResponse):
    """测试API连接响应"""
    data: Optional[Dict[str, str]] = None


# 上下文列表响应
class ContextListResponse(ApiResponse):
    """上下文列表响应"""
    data: Optional[List[ConversationMessage]] = None


# 群聊列表响应
class GroupListResponse(ApiResponse):
    """群聊列表响应"""
    data: Optional[List[Group]] = None


# 聊天请求
class ChatRequest(BaseModel):
    """聊天请求模型"""
    group_id: str
    user_id: str
    content: str
    is_mentioned: bool = False


# API配置请求
class ApiConfigRequest(BaseModel):
    """添加/更新API配置请求"""
    name: str
    api_key: str
    base_url: str
    model: str


# 群聊配置请求
class GroupConfigRequest(BaseModel):
    """群聊配置请求"""
    group_id: str
    enabled: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    reply_delay_seconds: Optional[int] = None


# 系统提示词请求
class SystemPromptRequest(BaseModel):
    """系统提示词更新请求"""
    global_prompt: Optional[str] = None
    group_prompts: Optional[Dict[str, str]] = None


# ==================== 记忆系统模型 ====================

# 用户档案模型
class UserProfile(BaseModel):
    """用户档案模型"""
    user_id: str
    real_name: Optional[str] = None
    nickname: Optional[str] = None
    relationship: str = "stranger"
    location: Optional[str] = None
    occupation: Optional[str] = None
    birthday: Optional[str] = None
    bio: Optional[str] = None
    interests: List[str] = []
    custom_fields: Dict[str, Any] = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        # 允许任意类型赋值，防止类型严格验证
        arbitrary_types_allowed = True


# 用户记忆模型
class UserMemory(BaseModel):
    """用户记忆模型"""
    id: Optional[int] = None
    user_id: str
    group_id: Optional[str] = None
    memory_type: str  # basic_info, preference, event, conversation_summary
    title: Optional[str] = None
    content: str
    importance: int = Field(default=3, ge=1, le=5)
    source_context: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    access_count: int = 0
    last_accessed_at: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


# 检索到的记忆（带检索元数据）
class RetrievedMemory(BaseModel):
    """检索到的记忆（带检索元数据）"""
    memory: UserMemory
    similarity_score: Optional[float] = None
    retrieval_method: str  # semantic, recent, important, type


# 记忆检索结果
class RetrievalResult(BaseModel):
    """记忆检索结果"""
    memories: List[RetrievedMemory]
    query: str
    retrieval_config: Dict[str, Any]
    total_candidates: int


# 全局上下文模型
class GlobalContext(BaseModel):
    """全局上下文模型"""
    current_messages: List[ConversationMessage]
    user_profile: Optional[UserProfile]
    relevant_memories: List[RetrievedMemory]
    formatted_context: str


# 记忆检索配置
class MemoryRetrievalConfig(BaseModel):
    """记忆检索配置"""
    strategy: str = "hybrid"  # hybrid, semantic, recency, importance
    max_memories: int = 5
    similarity_threshold: float = 0.7
    include_profile: bool = True


# 用户档案更新请求
class UserProfileUpdateRequest(BaseModel):
    """用户档案更新请求"""
    user_id: str
    real_name: Optional[str] = None
    nickname: Optional[str] = None
    relationship: Optional[str] = None
    location: Optional[str] = None
    occupation: Optional[str] = None
    birthday: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None


# 用户记忆创建请求
class UserMemoryCreateRequest(BaseModel):
    """用户记忆创建请求"""
    user_id: str
    group_id: Optional[str] = None
    memory_type: str
    title: Optional[str] = None
    content: str
    importance: int = 3
    source_context: Optional[str] = None


# 用户记忆更新请求
class UserMemoryUpdateRequest(BaseModel):
    """用户记忆更新请求"""
    memory_id: int
    title: Optional[str] = None
    content: Optional[str] = None
    importance: Optional[int] = None
    group_id: Optional[str] = None


# 记忆配置更新请求
class MemoryConfigUpdateRequest(BaseModel):
    """记忆配置更新请求"""
    embedding_model: Optional[str] = None
    retrieval_strategy: Optional[str] = None
    max_memories_per_query: Optional[int] = None
    semantic_similarity_threshold: Optional[float] = None
    memory_update_frequency: Optional[int] = None


# 用户档案响应
class UserProfileResponse(ApiResponse):
    """用户档案响应"""
    data: Optional[UserProfile] = None


# 用户记忆列表响应
class UserMemoriesResponse(ApiResponse):
    """用户记忆列表响应"""
    data: Optional[List[UserMemory]] = None


# ==================== 回复思考模型 ====================

# 回复思考结果
class ReplyThought(BaseModel):
    """回复思考结果"""
    should_reply: bool
    reason: str
    confidence: float
    reply_instruction: str
    user_profile_summary: str
    current_topic: str
    relevant_memories: List[str] = []

    # 新增字段 - 详细对话流分析
    reply_target: Optional[str] = None  # 回复目标：None/所有人/特定用户
    conversation_flow: Optional[str] = None  # 对话流详细分析
    main_participants: List[str] = []  # 主要参与者
    topic_change: Optional[str] = None  # 话题转换点
    emotion_atmosphere: Optional[str] = None  # 情绪氛围


# ==================== @信息和群聊消息模型 ====================

# @信息模型
class MentionInfo(BaseModel):
    """@信息模型"""
    qq: str
    name: str


# 群聊消息扩展模型
class GroupMessage(ConversationMessage):
    """群聊消息扩展模型"""
    mentions: List[MentionInfo] = []
    is_directed_at_bot: bool = False
    sender_nickname: Optional[str] = None
