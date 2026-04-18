"""QQ聊天AI机器人主应用."""

import os
import logging
import json
from contextlib import asynccontextmanager
from typing import Optional
import queue
import asyncio
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse

from backend.database.db import database
from backend.database.db import get_db
from backend.db_config import config_manager
from backend.config import settings
from backend.services.memory_interface import QianxueMemoryProvider
import backend.services.memory_interface as mem_mod
from backend.api.napcat import napcat_client
from backend.api.llm import llm_manager
from backend.services.context_manager import context_manager
from backend.routes.config_routes import router as config_router
from backend.routes.chat_routes import router as chat_router
from backend.routes.core_routes import router as core_router

from backend.services.agent.sources.qq_source import QQSource
from backend.services.agent.tools.registry import ToolRegistry
from backend.services.agent.brain import AgentBrain
from backend.services.agent.tools.send_message import SendMessageTool
from backend.services.agent.tools.get_time import GetCurrentTimeTool
from backend.services.agent.tools.search_memory import SearchMemoryTool
from backend.services.agent.tools.get_context import GetConversationContextTool
from backend.services.agent.tools.recognize_image import RecognizeImageTool
from backend.services.sleep_manager import sleep_manager, run_sleep_cycle


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 日志队列 - 用于SSE推送
log_queue = queue.Queue()


class SSELogHandler(logging.Handler):
    """将日志推送到队列的处理器"""

    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'source': record.name
        }
        try:
            self.queue.put_nowait(json.dumps(log_entry))
        except Exception:
            pass


# 添加SSE日志处理器
sse_handler = SSELogHandler(log_queue)
sse_handler.setLevel(logging.INFO)
logging.getLogger('').addHandler(sse_handler)


async def _ensure_robot_user():
    """确保机器人用户存在"""
    try:
        conn = await get_db()
        cursor = await conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            ("robot",)
        )
        exists = await cursor.fetchone()

        if not exists:
            try:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO users (user_id, nickname, user_type, message_count)
                    VALUES (?, ?, ?, 0)
                    """,
                    ("robot", "机器人", "robot")
                )
                await conn.commit()
                logger.info("已创建机器人用户记录")
            except Exception as e:
                logger.warning(f"创建机器人用户失败: {e}")
    except Exception as e:
        logger.warning(f"创建机器人用户记录失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("正在启动QQ聊天AI机器人...")

    # 初始化数据库
    await database.initialize_tables()
    logger.info("数据库初始化完成")

    # 创建机器人用户记录
    await _ensure_robot_user()
    logger.info("机器人用户初始化完成")

    # 初始化 LLM providers（使用统一配置）
    from backend.routes.config_routes import create_provider

    thinking_cfg = settings.llm.thinking_provider

    if thinking_cfg.api_key:
        provider = create_provider("thinking", thinking_cfg.api_key, thinking_cfg.base_url, thinking_cfg.model)
        if provider:
            llm_manager.set_thinking_provider_direct(provider)
            logger.info(f"思考模型已加载: {thinking_cfg.base_url} / {thinking_cfg.model}")

    if not thinking_cfg.api_key:
        logger.warning("未设置 LLM API Key，请在 Web 界面配置")

    # 初始化NapCat客户端
    napcat_client.http_url = settings.napcat.http_url
    logger.info(f"NapCat HTTP地址: {napcat_client.http_url}")

    # 初始化AgentBrain
    global qq_source, tool_registry, agent_brain
    qq_source = QQSource()
    tool_registry = ToolRegistry()
    agent_brain = AgentBrain(tool_registry)
    agent_brain.max_iterations = settings.brain.max_iterations

    # 注册工具
    tool_registry.register(SendMessageTool())
    tool_registry.register(GetCurrentTimeTool())
    tool_registry.register(SearchMemoryTool())
    tool_registry.register(GetConversationContextTool())
    tool_registry.register(RecognizeImageTool())
    logger.info("AgentBrain 已初始化，工具已注册")

    # 初始化核心层
    from backend.services.core.loader import identity_loader
    identity_loader.load()
    logger.info("核心层人设加载完成")

    # 初始化记忆系统
    memory_url = settings.memory.service_url
    qianxue_provider = QianxueMemoryProvider(base_url=memory_url)
    if await qianxue_provider.health_check():
        mem_mod.memory_provider = qianxue_provider
        logger.info(f"记忆系统: 已连接 {memory_url}")
    else:
        logger.warning("记忆系统: Memory 服务不可用，使用默认空实现")

    # 初始化 STM 客户端（短期记忆，跨会话感知）
    from backend.services.stm_client import stm_client
    stm_client.base_url = memory_url
    logger.info(f"STM 客户端已初始化: {memory_url}")

    # 初始化睡眠管理器
    sleep_manager.set_brain(agent_brain)
    asyncio.create_task(run_sleep_cycle())
    logger.info("睡眠周期管理已启动")

    logger.info("应用启动完成")

    yield

    # 关闭时执行
    logger.info("正在关闭应用...")
    if isinstance(mem_mod.memory_provider, QianxueMemoryProvider):
        await mem_mod.memory_provider.close()
    from backend.services.stm_client import stm_client
    await stm_client.close()
    await llm_manager.close_all()
    await napcat_client.close()
    await database.close()
    logger.info("应用已关闭")


# 创建FastAPI应用
app = FastAPI(
    title="QQ聊天AI机器人",
    description="基于FastAPI和NapCat的QQ聊天机器人",
    version="1.0.0",
    lifespan=lifespan
)

# 注册路由
app.include_router(config_router)
app.include_router(chat_router)
app.include_router(core_router)


@app.websocket("/ws/onebot")
async def onebot_websocket(websocket: WebSocket):
    """NapCat反向WebSocket连接端点"""
    await websocket.accept()
    logger.info("NapCat WebSocket连接已建立")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            post_type = message.get("post_type")
            logger.info(f"收到事件: {post_type}")

            if post_type == "message":
                message_type = message.get("message_type")

                if message_type == "group":
                    self_id = message.get("self_id")
                    if self_id:
                        napcat_client.self_id = self_id

                    await _process_group_message(message)

                elif message_type == "private":
                    self_id = message.get("self_id")
                    if self_id:
                        napcat_client.self_id = self_id

                    await _process_private_message(message)

    except WebSocketDisconnect:
        logger.warning("NapCat WebSocket连接已断开")
    except Exception as e:
        logger.error(f"WebSocket处理异常: {e}", exc_info=True)
    finally:
        logger.info("NapCat WebSocket连接已关闭")


@app.get("/")
async def root():
    """根路径"""
    return {"message": "QQ聊天AI机器人 API", "status": "running"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "current_api": config_manager.get_current_api(),
        "connected_groups": len(config_manager.api_config.apis) if hasattr(config_manager, 'api_config') else 0
    }


@app.get("/logs/stream")
async def log_stream(request: Request):
    """Server-Sent Events日志流"""
    async def event_generator():
        try:
            while True:
                try:
                    log_data = await asyncio.wait_for(
                        asyncio.to_thread(log_queue.get),
                        timeout=settings.server.sse_heartbeat_timeout
                    )
                    yield f"data: {log_data}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )


# ================================================================
# 消息处理核心流程
# ================================================================

# 每个会话的 debounce 状态：{ lock, queue, timer }
_debounce_state: dict[str, dict] = {}


def _get_debounce(key: str) -> dict:
    if key not in _debounce_state:
        _debounce_state[key] = {
            "lock": asyncio.Lock(),
            "queue": [],
            "timer": None,
        }
    return _debounce_state[key]


async def _enqueue_message(key: str, message):
    """消息入队，启动/重置 debounce 计时器。

    - AI 空闲：等待后处理（等对方说完）
    - AI 忙：排队等 AI 回完，等待时间内没新消息再处理
    """
    state = _get_debounce(key)
    state["queue"].append(message)

    # 取消旧计时器，启动新的
    if state["timer"] is not None:
        state["timer"].cancel()

    async def _fire():
        await asyncio.sleep(config_manager.debounce_seconds)
        await _drain_queue(key)

    state["timer"] = asyncio.create_task(_fire())

    if state["lock"].locked():
        logger.info(f"[{key}] AI忙，消息排队 (队列: {len(state['queue'])}条)")


async def _drain_queue(key: str):
    """Debounce 到期：合并队列消息，交给 AI 处理。"""
    state = _get_debounce(key)
    state["timer"] = None

    async with state["lock"]:
        batch = state["queue"]
        state["queue"] = []

        if not batch:
            return

        # 记忆提取（每条单独提取）
        for msg in batch:
            source_type = "qq_private" if msg.is_private else "qq_group"
            await _extract_memory(msg.group_id, msg.user_id, msg.content, source_type=source_type)

        # 检查是否需要创建个人档案（10 轮对话触发）
        await _check_profile_for_batch(batch)

        # 合并消息
        if len(batch) == 1:
            combined = batch[0]
        else:
            logger.info(f"[{key}] 合并 {len(batch)} 条消息一起处理")
            combined = _combine_messages(batch)

        # AI 思考
        try:
            thought = await agent_brain.process_message(combined)
            logger.info(f"思考完成，状态: {thought.status}, 理由: {thought.reason}")
        except Exception as e:
            logger.error(f"AI 处理失败: {e}", exc_info=True)
            _notify_error_async("AI 处理失败", f"消息处理", e)

    # AI 回完了，检查期间是否有新消息入队
    if state["queue"] and state["timer"] is None:
        async def _fire_again():
            await asyncio.sleep(config_manager.debounce_seconds)
            await _drain_queue(key)
        state["timer"] = asyncio.create_task(_fire_again())


def _combine_messages(messages: list):
    """将多条消息合并为一条（取最后一条的元数据，拼接内容）。"""
    from backend.services.agent.message import AgentMessage
    last = messages[-1]
    combined_content = "\n".join(msg.content for msg in messages)
    return AgentMessage(
        source=last.source,
        group_id=last.group_id,
        user_id=last.user_id,
        sender_nickname=last.sender_nickname,
        content=combined_content,
        is_mentioned=any(msg.is_mentioned for msg in messages),
        priority=max(msg.priority for msg in messages),
        is_heartbeat=last.is_heartbeat,
        is_private=last.is_private,
        has_image=last.has_image,
        image_description=last.image_description or "",
    )


# 已检查过档案的用户（避免重复调 API）
_profile_checked_users: set[str] = set()
_PROFILE_TURN_THRESHOLD = settings.memory.profile_turn_threshold


async def _check_profile_for_batch(batch: list):
    """检查批次中的用户是否达到创建档案的对话轮次。"""
    for msg in batch:
        if msg.is_heartbeat or not msg.user_id or msg.user_id == "system":
            continue

        user_key = msg.user_id
        if user_key in _profile_checked_users:
            continue

        # 统计该用户在所有会话中的消息数
        try:
            from backend.database.db import get_db
            conn = await get_db()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ? AND role = 'user'",
                (user_key,),
            )
            row = await cursor.fetchone()
            count = row[0] if row else 0

            if count >= _PROFILE_TURN_THRESHOLD:
                _profile_checked_users.add(user_key)
                nickname = msg.sender_nickname
                if nickname:
                    asyncio.create_task(_ensure_profile(nickname, user_key))
        except Exception as e:
            logger.warning(f"档案轮次检查失败: {e}")


async def _ensure_profile(nickname: str, user_id: str):
    """调 Memory API 确保档案存在。"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=settings.memory.profile_ensure_timeout) as client:
            resp = await client.post(
                settings.memory.profile_ensure_url,
                json={"entity_name": nickname},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("found"):
                    logger.info(f"档案已确保: {nickname} (user={user_id})")
            else:
                logger.warning(f"档案确保失败: {resp.status_code}")
    except Exception as e:
        logger.warning(f"档案确保请求失败: {e}")

async def _process_group_message(message_data: dict):
    """处理群消息：转换格式 → 存上下文 → 记忆提取 → AgentBrain思考"""
    try:
        # 1. QQSource转换消息
        agent_message = await qq_source.receive_message(message_data)
        if not agent_message:
            return

        # 2. 更新记忆系统的用户ID映射
        if isinstance(mem_mod.memory_provider, QianxueMemoryProvider):
            mem_mod.memory_provider.update_nickname_map(
                agent_message.user_id, agent_message.sender_nickname
            )

        # 3. 存入上下文
        await context_manager.add_group_message(
            group_id=agent_message.group_id,
            user_id=agent_message.user_id,
            role="user",
            content=agent_message.content,
            sender_nickname=agent_message.sender_nickname,
            mentions=agent_message.mentions,
            is_directed_at_bot=agent_message.is_mentioned
        )

        # 睡眠期间：群消息已存入DB，不触发AI处理
        if sleep_manager.is_asleep:
            logger.info(f"睡眠中，群消息仅存DB: {agent_message.content[:30]}")
            return

        # 4. 入 debounce 队列（等对方说完再回复）
        if agent_message.priority >= settings.brain.mention_priority:  # @消息
            logger.info(f"@消息: {agent_message.content[:50]}...")
            _record_stm_event(
                event_type="user_mention",
                source_type="qq_group",
                group_id=agent_message.group_id,
                user_id=agent_message.user_id,
                summary=f"{agent_message.sender_nickname} @你: {agent_message.content[:50]}",
                importance=settings.brain.stm_importance_user_mention,
            )
        else:
            logger.info(f"普通消息: {agent_message.content[:50]}...")
            if len(agent_message.content) > settings.brain.significant_length or '？' in agent_message.content or '?' in agent_message.content:
                _record_stm_event(
                    event_type="significant_msg",
                    source_type="qq_group",
                    group_id=agent_message.group_id,
                    user_id=agent_message.user_id,
                    summary=f"{agent_message.sender_nickname} 说: {agent_message.content[:60]}",
                    importance=settings.brain.stm_importance_significant_msg,
                )
        await _enqueue_message(agent_message.group_id, agent_message)

    except Exception as e:
        logger.error(f"消息处理失败: {e}", exc_info=True)
        _notify_error_async("消息处理失败", f"群消息", e)


async def _extract_memory(group_id, user_id, content, source_type="qq_group"):
    """提取并存储记忆到 Memory 服务（fire-and-forget，不阻塞主流程）"""
    try:
        asyncio.create_task(mem_mod.memory_provider.extract_and_store(
            group_id, user_id, content, source_type=source_type
        ))
    except Exception as e:
        logger.warning(f"记忆提取失败: {e}")


def _record_stm_event(event_type: str, source_type: str, group_id: str,
                       user_id: str = None, summary: str = "", importance: float = 0.5):
    """记录 STM 事件（fire-and-forget，不阻塞主流程）"""
    try:
        from backend.services.stm_client import stm_client
        asyncio.create_task(stm_client.record_event(
            event_type=event_type,
            source_type=source_type,
            group_id=group_id,
            user_id=user_id,
            summary=summary,
            importance=importance,
        ))
    except Exception:
        pass


def _notify_error_async(error_type: str, source: str, error: Exception):
    """fire-and-forget 发送错误通知，不阻塞主流程。"""
    try:
        from backend.services.error_notifier import notify_error
        asyncio.create_task(notify_error(
            error_type=error_type,
            source=source,
            error=f"{type(error).__name__} - {str(error)[:200]}",
        ))
    except Exception:
        pass


async def _process_private_message(message_data: dict):
    """处理私聊消息：转换格式 → 存上下文 → 记忆提取 → AgentBrain思考"""
    try:
        # 1. QQSource转换消息
        agent_message = await qq_source.receive_message(message_data)
        if not agent_message:
            return

        # 2. 更新记忆系统的用户ID映射
        if isinstance(mem_mod.memory_provider, QianxueMemoryProvider):
            mem_mod.memory_provider.update_nickname_map(
                agent_message.user_id, agent_message.sender_nickname
            )

        # 3. 存入上下文（复用 group 方法，group_id 为 private_{user_id}）
        await context_manager.add_group_message(
            group_id=agent_message.group_id,
            user_id=agent_message.user_id,
            role="user",
            content=agent_message.content,
            sender_nickname=agent_message.sender_nickname,
            mentions=[],
            is_directed_at_bot=True
        )

        # 睡眠期间：私聊消息存DB + 入队等待唤醒处理
        if sleep_manager.is_asleep:
            logger.info(f"睡眠中，私聊消息入队: {agent_message.content[:30]}")
            sleep_manager.queue_private_message(agent_message)
            return

        # 4. 私聊消息入 debounce 队列
        logger.info(f"私聊消息: {agent_message.content[:50]}...")
        _record_stm_event(
            event_type="user_mention",
            source_type="qq_private",
            group_id=agent_message.group_id,
            user_id=agent_message.user_id,
            summary=f"私聊: {agent_message.sender_nickname} 说: {agent_message.content[:50]}",
            importance=settings.brain.stm_importance_private_chat,
        )
        await _enqueue_message(agent_message.group_id, agent_message)

    except Exception as e:
        logger.error(f"私聊消息处理失败: {e}", exc_info=True)
        _notify_error_async("私聊消息处理失败", "私聊", e)


# ================================================================
# 心跳端点
# ================================================================

@app.post("/api/heartbeat")
async def heartbeat_trigger():
    """心跳触发端点。

    独立的心跳服务每 N 秒调用一次，只是"叮"一声唤醒主系统。
    不接受任何参数——主系统自己决定要查什么、要不要说话。
    """
    if agent_brain is None:
        return {"status": "error", "reason": "brain_not_initialized"}

    # 睡眠/困倦期间跳过心跳
    if sleep_manager.should_skip_heartbeat:
        return {"status": "skipped", "reason": "sleeping"}

    # 后台执行，不阻塞响应
    asyncio.create_task(_proactive_think())

    return {"status": "ok"}


async def _proactive_think():
    """心跳触发的主动思考——brain 自己决定一切。"""
    try:
        await agent_brain.proactive_think()
    except Exception as e:
        logger.error(f"Proactive think failed: {e}", exc_info=True)
        _notify_error_async("心跳触发失败", "heartbeat", e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        log_level=settings.server.log_level
    )
