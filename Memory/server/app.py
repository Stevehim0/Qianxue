"""Memory HTTP API Server."""

import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from Memory.api.memory_api import MemoryAPI
from Memory.server.schemas import (
    EventRequest, EventResponse,
    RecallRequest, RecallResponse, ExperienceRecallItem, EntityRecallItem,
    RecallByKeywordsResponse,
    ProfileResponse, EnsureProfileRequest,
    CoreResponse,
    StateResponse,
    ConsolidateRequest, ConsolidateResponse,
    StatusResponse,
    ErrorResponse,
    StmEventRequest, StmEventResponse,
    StmPerceptionResponse,
    StmCompressResponse,
)

# 配置 Memory 模块日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# Global MemoryAPI instance - initialized once at startup
_memory_api: Optional[MemoryAPI] = None

# State update timer
_state_update_stop_event = threading.Event()
_state_update_thread: Optional[threading.Thread] = None


def _state_update_loop():
    """后台线程：每10分钟触发一次状态定时更新。"""
    while not _state_update_stop_event.is_set():
        _state_update_stop_event.wait(timeout=600)  # 10分钟
        if _state_update_stop_event.is_set():
            break
        if _memory_api is not None:
            try:
                _memory_api.trigger_state_update()
            except Exception as e:
                logger.error(f"State update tick failed: {e}")


def _get_memory_api() -> MemoryAPI:
    """Return the initialized MemoryAPI instance, or raise if not ready."""
    if _memory_api is None:
        raise RuntimeError("MemoryAPI not initialized")
    return _memory_api


def _dataclass_to_dict(obj):
    """Convert a dataclass instance to a plain dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return {f: getattr(obj, f) for f in obj.__dataclass_fields__}
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return dict(obj)


def _init_memory_system():
    """Initialize database and MemoryAPI (runs in thread)."""
    from Memory.storage.database import db_manager
    # Ensure database tables exist before creating MemoryAPI
    db_manager.initialize()
    # Run schema migrations (handles already-initialized databases)
    from Memory.storage.schema import migrate_to_v8, migrate_to_v9, migrate_to_v10
    migrate_to_v8(db_manager)
    migrate_to_v9(db_manager)
    migrate_to_v10(db_manager)
    return MemoryAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize MemoryAPI on startup, tear down on shutdown."""
    global _memory_api
    logger.info("Initializing MemoryAPI...")
    # DB init + MemoryAPI() is synchronous and heavy (loads embedding model etc)
    # Run in thread to not block event loop
    _memory_api = await asyncio.to_thread(_init_memory_system)
    # Start buffer timeout checker
    _memory_api.buffer_manager.start_timeout_checker()
    # Start consolidation scheduler
    from Memory.consolidator.scheduler import consolidation_scheduler
    consolidation_scheduler.start()
    # Start state update timer (every 10 minutes)
    global _state_update_thread
    _state_update_stop_event.clear()
    _state_update_thread = threading.Thread(
        target=_state_update_loop, daemon=True, name="state-update-timer"
    )
    _state_update_thread.start()
    logger.info("State update timer started (interval=600s)")
    logger.info("MemoryAPI initialized successfully")
    yield
    # Stop state update timer
    _state_update_stop_event.set()
    if _state_update_thread is not None:
        _state_update_thread.join(timeout=5)
        _state_update_thread = None
    # Stop consolidation scheduler
    from Memory.consolidator.scheduler import consolidation_scheduler
    consolidation_scheduler.stop()
    # Stop buffer timeout checker
    if _memory_api is not None:
        _memory_api.buffer_manager.stop_timeout_checker()
    _memory_api = None
    logger.info("Memory server shutdown")


app = FastAPI(
    title="Memory System API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get memory system status."""
    api = _get_memory_api()
    result = await asyncio.to_thread(api.get_status)
    return StatusResponse(**result)


@app.post(
    "/api/event",
    response_model=EventResponse,
    responses={500: {"model": ErrorResponse}},
)
async def create_event(request: EventRequest):
    """Record an experience event."""
    api = _get_memory_api()
    try:
        kwargs = {}
        # Buffer-based fields
        if request.source_type is not None:
            kwargs["source_type"] = request.source_type
        if request.source_id is not None:
            kwargs["source_id"] = request.source_id
        if request.messages is not None:
            kwargs["messages"] = [m.model_dump() for m in request.messages]
        # Legacy fields
        if request.dialogue is not None:
            kwargs["dialogue"] = request.dialogue
        if request.role is not None:
            kwargs["role"] = request.role
        if request.content is not None:
            kwargs["content"] = request.content

        result = await asyncio.to_thread(api.receive_event, **kwargs)
        return EventResponse(**result)
    except Exception as e:
        logger.error("Failed to create event: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/recall",
    response_model=RecallResponse,
    responses={500: {"model": ErrorResponse}},
)
async def recall_memories(request: RecallRequest):
    """Recall relevant memories."""
    api = _get_memory_api()
    try:
        result = await asyncio.to_thread(
            api.check_recall, request.query, request.context
        )

        # check_recall returns a dict with "experiences", "entities", and "briefing"
        experiences = []
        entities = []
        briefing = None

        if isinstance(result, dict):
            raw_experiences = result.get("experiences", [])
            raw_entities = result.get("entities", [])
            briefing = result.get("briefing")

            for exp in raw_experiences:
                exp_dict = _dataclass_to_dict(exp)
                experiences.append(ExperienceRecallItem(**exp_dict))

            for ent in raw_entities:
                ent_dict = _dataclass_to_dict(ent)
                entities.append(EntityRecallItem(**ent_dict))

        return RecallResponse(
            experiences=experiences,
            entities=entities,
            briefing=briefing,
        )
    except Exception as e:
        logger.error("Recall failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/recall/keywords",
    response_model=RecallByKeywordsResponse,
    responses={500: {"model": ErrorResponse}},
)
async def recall_by_keywords(request: RecallRequest):
    """Recall memories by keywords — returns briefing only."""
    api = _get_memory_api()
    try:
        result = await asyncio.to_thread(
            api.recall_by_keywords, request.query, request.context
        )
        return RecallByKeywordsResponse(briefing=result.get("briefing"))
    except Exception as e:
        logger.error("Recall by keywords failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/profile/{entity_name}", response_model=ProfileResponse)
async def get_profile(entity_name: str):
    """Load entity profile."""
    api = _get_memory_api()
    try:
        profile = await asyncio.to_thread(api.load_profile, entity_name)
        return ProfileResponse(found=profile is not None, profile=profile)
    except Exception as e:
        logger.error("Failed to load profile: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile/ensure", response_model=ProfileResponse)
async def ensure_profile(request: EnsureProfileRequest):
    """确保个人档案存在，不存在则创建。不受 experience 阈值限制。"""
    api = _get_memory_api()
    try:
        result = await asyncio.to_thread(api.ensure_profile, request.entity_name)
        return ProfileResponse(found=result is not None, profile=result)
    except Exception as e:
        logger.error("Failed to ensure profile: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/core", response_model=CoreResponse)
async def get_core():
    """Load core identity layer."""
    api = _get_memory_api()
    try:
        result = await asyncio.to_thread(api.load_core)
        return CoreResponse(**result)
    except Exception as e:
        logger.error("Failed to load core: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/state", response_model=StateResponse)
async def get_state():
    """Get current state prompt."""
    api = _get_memory_api()
    try:
        prompt = await asyncio.to_thread(api.get_state_prompt)
        mood_label = await asyncio.to_thread(api.get_mood_label)
        return StateResponse(state_prompt=prompt, mood_label=mood_label)
    except Exception as e:
        logger.error("Failed to get state: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/consolidate",
    response_model=ConsolidateResponse,
    responses={500: {"model": ErrorResponse}},
)
async def run_consolidation(request: ConsolidateRequest):
    """Manually trigger consolidation."""
    from Memory.config.settings import settings
    if not settings.schedule.enabled:
        raise HTTPException(status_code=400, detail="巩固和休眠已禁用（schedule.enabled=False）")
    api = _get_memory_api()
    try:
        result = await asyncio.to_thread(api.run_consolidation, request.mode)
        return ConsolidateResponse(**result)
    except Exception as e:
        logger.error("Consolidation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/consolidate/status")
async def get_consolidation_status():
    """获取巩固调度器的当前状态。"""
    from Memory.consolidator.scheduler import consolidation_scheduler
    return consolidation_scheduler.status


# ================================================================
# STM (Short-Term Memory) 端点
# ================================================================

def _get_stm_components():
    """获取 STM 相关组件（延迟导入以避免循环依赖）。"""
    from Memory.storage.stm_store import stm_store
    from Memory.stm.perception_builder import PerceptionBuilder
    from Memory.stm.compressor import StmCompressor
    return stm_store, PerceptionBuilder(), StmCompressor()


@app.post(
    "/api/stm/event",
    response_model=StmEventResponse,
    responses={500: {"model": ErrorResponse}},
)
async def record_stm_event(request: StmEventRequest):
    """记录一个短期记忆事件。"""
    stm_store, _, compressor = _get_stm_components()
    try:
        event_id = await asyncio.to_thread(
            stm_store.record_event,
            event_type=request.event_type,
            source_type=request.source_type,
            group_id=request.group_id,
            user_id=request.user_id,
            summary=request.summary,
            detail=request.detail,
            importance=request.importance,
        )
        active_count = await asyncio.to_thread(stm_store.get_active_count)

        # 检查是否需要压缩
        if compressor.should_compress(active_count):
            api = _get_memory_api()
            llm_client = api._llm_client
            asyncio.create_task(
                asyncio.to_thread(compressor.compress, llm_client)
            )

        return StmEventResponse(
            success=True,
            event_id=event_id,
            total_active=active_count,
        )
    except Exception as e:
        logger.error("Failed to record STM event: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/stm/perception",
    response_model=StmPerceptionResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_stm_perception(hours: float = 6.0):
    """获取格式化的短期记忆感知文本。"""
    stm_store, builder, _ = _get_stm_components()
    try:
        events = await asyncio.to_thread(stm_store.get_recent_events, hours)
        compressed = await asyncio.to_thread(stm_store.get_compressed_summaries, hours)

        perception_text = await asyncio.to_thread(builder.build_perception, events, compressed)

        return StmPerceptionResponse(
            perception_text=perception_text,
            event_count=len(events),
            compressed_count=len(compressed),
        )
    except Exception as e:
        logger.error("Failed to get STM perception: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/stm/compress",
    response_model=StmCompressResponse,
    responses={500: {"model": ErrorResponse}},
)
async def trigger_stm_compression():
    """手动触发 STM 压缩（测试用）。"""
    stm_store, _, compressor = _get_stm_components()
    try:
        events = await asyncio.to_thread(stm_store.get_events_for_compression)
        if not events:
            return StmCompressResponse(success=True, compressed_count=0)

        api = _get_memory_api()
        llm_client = api._llm_client
        summary = await asyncio.to_thread(compressor.compress, llm_client)

        return StmCompressResponse(
            success=summary is not None,
            compressed_count=len(events),
            summary=summary,
        )
    except Exception as e:
        logger.error("STM compression failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "memory_api_initialized": _memory_api is not None}


@app.post("/api/config/llm")
async def update_memory_llm_config(request: dict):
    """更新 Memory 系统的 LLM 配置（API Key / Base URL / Provider / Model），并写入 .env 持久化。"""
    from Memory.config.settings import settings
    from Memory.llm import LLMFactory
    from pathlib import Path

    api_key = request.get("api_key", "")
    base_url = request.get("base_url", "")
    provider = request.get("provider", "")
    model = request.get("model", "")

    need_recreate = False

    if api_key:
        settings.models.llm_api_key = api_key
        need_recreate = True
    if base_url:
        settings.models.llm_base_url = base_url
        need_recreate = True
    if provider:
        settings.models.llm_provider = provider
        need_recreate = True
    if model:
        settings.models.llm_model = model
        need_recreate = True

    # 重建 LLM 客户端
    if need_recreate and _memory_api:
        p = settings.models.llm_provider or "qianwen"
        llm_kwargs = {}
        if p == "openai_compatible" and settings.models.llm_base_url:
            llm_kwargs["base_url"] = settings.models.llm_base_url
            if settings.models.llm_model:
                llm_kwargs["model"] = settings.models.llm_model
        try:
            _memory_api._llm_client = LLMFactory.create_client(provider=p, **llm_kwargs)
        except Exception as e:
            logger.warning(f"Failed to recreate LLM client: {e}")

    # 写入 .env 持久化
    env_path = Path(__file__).parent.parent / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    keys_written = set()
    new_lines = []
    env_vars = {}
    if api_key:
        env_vars["LLM_API_KEY"] = api_key
    if base_url:
        env_vars["LLM_BASE_URL"] = base_url
    if provider:
        env_vars["LLM_PROVIDER"] = provider
    if model:
        env_vars["LLM_MODEL"] = model
    for line in lines:
        stripped = line.strip()
        matched = False
        for key_name in env_vars:
            if stripped.startswith(f"{key_name}="):
                new_lines.append(f"{key_name}={env_vars[key_name]}\n")
                keys_written.add(key_name)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for key_name, val in env_vars.items():
        if key_name not in keys_written:
            new_lines.append(f"{key_name}={val}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    logger.info("Memory LLM config updated")
    return {"success": True, "message": "配置已更新"}


@app.get("/api/config/llm")
async def get_memory_llm_config():
    """获取 Memory 系统的 LLM 配置（API Key 掩码）。"""
    from Memory.config.settings import settings
    key = settings.models.llm_api_key or ""
    masked = ""
    if key and len(key) > 8:
        masked = key[:4] + "*" * (len(key) - 8) + key[-4:]
    elif key:
        masked = "*" * len(key)
    return {
        "api_key": masked,
        "base_url": settings.models.llm_base_url or "",
        "provider": settings.models.llm_provider or "qianwen",
        "model": settings.models.llm_model or "",
    }
