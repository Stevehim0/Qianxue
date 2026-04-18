"""Memory HTTP API request/response schemas."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# --- Event ---

class BufferedMessageItem(BaseModel):
    """Single message in a buffer batch."""
    speaker: str
    content: str
    role: str  # "user" or "assistant"
    timestamp: Optional[float] = None


class EventRequest(BaseModel):
    """Request body for receive_event."""
    # Buffer-based fields (new)
    source_type: Optional[str] = None   # "qq_group", "qq_private", etc.
    source_id: Optional[str] = None     # group_id or user_id
    messages: Optional[List[BufferedMessageItem]] = None  # batch of messages
    # Legacy fields (backward compatible)
    dialogue: Optional[str] = None
    role: Optional[str] = None
    content: Optional[str] = None


class EventResponse(BaseModel):
    """Response for receive_event."""
    buffered: bool = True
    buffer_count: int = 0
    success: bool = True
    experience_id: Optional[str] = None  # Only set in legacy (immediate) mode


# --- Recall ---

class RecallRequest(BaseModel):
    """Request body for check_recall."""
    query: str
    context: Dict[str, Any]  # {recent_history: [], ai_state: {}, current_time: str}


class ExperienceRecallItem(BaseModel):
    """Single experience recall result."""
    experience_id: str
    L0_text: str = ""
    L1_text: Optional[str] = None
    recall_hint: Optional[str] = None
    importance: float = 0.0
    emotion_category: Optional[str] = None
    time_distance_days: int = 0
    activation_score: float = 0.0
    source_type: str = "vector_search"
    rank_score: float = 0.0
    related_entities: Optional[List[Dict[str, Any]]] = None


class EntityRecallItem(BaseModel):
    """Single entity recall result."""
    entity_id: str
    name: str
    type: str
    properties: Optional[Dict[str, Any]] = None
    activation_score: float = 0.0
    source_type: str = "entity_vector_search"


class RecallResponse(BaseModel):
    """Response for check_recall."""
    experiences: List[ExperienceRecallItem] = []
    entities: List[EntityRecallItem] = []
    briefing: Optional[str] = None


class RecallByKeywordsResponse(BaseModel):
    """Response for recall_by_keywords — only briefing."""
    briefing: Optional[str] = None


# --- Profile ---

class ProfileResponse(BaseModel):
    """Response for load_profile."""
    found: bool
    profile: Optional[Dict[str, Any]] = None


class EnsureProfileRequest(BaseModel):
    """Request for ensure_profile."""
    entity_name: str


# --- Core ---

class CoreResponse(BaseModel):
    """Response for load_core.

    数据来源于 Backend 主系统的 identity.md，通过 HTTP 获取。
    """
    invariant_text: Optional[str] = None
    stable_text: Optional[str] = None
    malleable_text: Optional[str] = None
    identity_text: Optional[str] = None
    anchors: Optional[Dict[str, Any]] = None


# --- State ---

class StateResponse(BaseModel):
    """Response for get_state_prompt."""
    state_prompt: str
    mood_label: str = "平静"


# --- Consolidation ---

class ConsolidateRequest(BaseModel):
    """Request body for run_consolidation."""
    mode: str = "incremental"  # "incremental" or "full"


class ConsolidateResponse(BaseModel):
    """Response for run_consolidation."""
    processed_count: int
    mode: str
    duration: float


# --- Status ---

class StatusResponse(BaseModel):
    """Response for get_status."""
    total_experiences: int
    consolidated_count: int
    unconsolidated_count: int
    total_entities: int
    total_edges: int
    vector_store_size: int
    last_consolidation: Optional[str] = None
    database_path: str
    system_health: str


# --- Error ---

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None


# --- STM (Short-Term Memory) ---

class StmEventRequest(BaseModel):
    """Request body for recording an STM event."""
    event_type: str           # ai_reply | tool_call | user_mention | significant_msg
    source_type: str          # qq_group | qq_private
    group_id: str
    user_id: Optional[str] = None
    summary: str              # One-line summary
    detail: Optional[str] = None
    importance: float = 0.5


class StmEventResponse(BaseModel):
    """Response for recording an STM event."""
    success: bool
    event_id: int
    total_active: int         # Current active event count (for compression trigger)


class StmPerceptionResponse(BaseModel):
    """Response for getting STM perception."""
    perception_text: str      # Formatted perception block, empty string if no events
    event_count: int
    compressed_count: int


class StmCompressResponse(BaseModel):
    """Response for manual compression trigger."""
    success: bool
    compressed_count: int     # How many events were compressed
    summary: Optional[str] = None
