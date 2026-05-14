"""Agent大脑 - 主思考引擎."""

import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

import httpx

from .message import AgentMessage
from .thought import AgentThought, ThoughtStatus
from .tool_call import ToolCall, ToolCallStatus
from .tools.registry import ToolRegistry

from backend.api.llm import llm_manager
from backend.api.napcat import napcat_client
from backend.config import settings
from backend.services.core.loader import identity_loader
from backend.services.core.prompt_builder import build_system_prompt


logger = logging.getLogger(__name__)


class AgentBrain:
    """Agent大脑 - 主思考引擎

    支持对话式多轮思考循环:
    - 逐步感知-决策-行动
    - 工具并行执行（假设无依赖）
    - 详细的日志记录和错误追踪
    """

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self.max_iterations = settings.brain.max_iterations  # 最大思考轮次
        self._state_client: Optional[httpx.AsyncClient] = None
        # 用户档案缓存: user_id -> (text, expire_time)
        self._profile_cache: Dict[str, tuple[str, float]] = {}
        self._PROFILE_CACHE_TTL = 300.0  # 5 分钟
        # 对话活跃状态: key (group_id / private_xxx) -> expire_time
        self._active_conversations: Dict[str, float] = {}

    async def _get_state_client(self) -> httpx.AsyncClient:
        """获取持久 HTTP 客户端（连接池复用）。"""
        if self._state_client is None or self._state_client.is_closed:
            self._state_client = httpx.AsyncClient(
                timeout=settings.brain.state_api_timeout,
            )
        return self._state_client

    async def close(self):
        """释放资源。"""
        if self._state_client and not self._state_client.is_closed:
            await self._state_client.aclose()
            self._state_client = None

    def mark_conversation_active(self, key: str):
        """标记某个群/私聊正在对话中（消息入队时调用）。

        活跃窗口覆盖 debounce 等待 + AI 处理 + 对方可能回复的时间。
        """
        self._active_conversations[key] = asyncio.get_event_loop().time() + 120.0

    def _is_conversation_active(self, key: str) -> bool:
        """检查某个群/私聊是否正在对话中。"""
        expire = self._active_conversations.get(key)
        if expire is None:
            return False
        if asyncio.get_event_loop().time() < expire:
            return True
        del self._active_conversations[key]
        return False

    async def process_message(self, message: AgentMessage) -> AgentThought:
        """
        处理消息的主流程

        Args:
            message: 统一格式的消息

        Returns:
            思考结果
        """
        logger.info(f"AgentBrain开始处理消息: group={message.group_id}, user={message.user_id}")

        # 心跳/图片消息走原有 think loop
        if message.is_heartbeat or message.has_image:
            return await self._think_loop(message)

        # 流式路径
        if settings.brain.streaming_enabled:
            try:
                return await self._stream_reply(message)
            except Exception as e:
                logger.error(f"流式回复失败: {e}", exc_info=True)
                raise

        # 流式关闭时退回 think loop
        return await self._think_loop(message)

    async def _think_loop(self, message: AgentMessage) -> AgentThought:
        """
        思考循环 - 让 LLM 感知工具并进行多轮思考

        Args:
            message: 消息

        Returns:
            最终思考结果
        """
        thought = AgentThought()
        previous_results = {}

        for iteration in range(self.max_iterations):
            thought.iteration = iteration + 1
            logger.info(f"思考轮次 {iteration + 1}/{self.max_iterations}")

            # 第1步：让 LLM 思考并规划工具
            llm_response = await self._think_with_tools(
                message=message,
                previous_results=previous_results,
                iteration=iteration
            )

            # 第2步：获取工具调用
            tool_calls = llm_response.get("tool_calls", [])

            # 记录模型决策
            if tool_calls:
                logger.info(f"模型决策: 参与对话 (工具调用数: {len(tool_calls)})")
                logger.info(f"调用的工具: {[tc.get('tool_name') for tc in tool_calls]}")

                # 新增详细日志
                for tc in tool_calls:
                    logger.info(f"  工具调用 [{tc['id']}] {tc['tool_name']}")
                    logger.info(f"    原始参数: {tc.get('arguments', {})}")
                    logger.info(f"    store_as: {tc.get('store_as', '无')}")
            else:
                logger.info(f"模型决策: 不参与 (工具调用数: 0)")

            # 第3步：如果没有工具调用，完成思考
            if not tool_calls:
                thought.status = ThoughtStatus.COMPLETE
                logger.info("LLM未规划任何工具调用，思考完成")
                break

            # 第4步：创建 ToolCall 对象
            tool_call_objs = self._create_tool_calls(tool_calls, message, previous_results)

            # 第5步：执行工具（处理依赖）
            execution_results = await self._execute_tools(tool_call_objs, message, previous_results)

            # 第6步：更新结果映射
            for call in tool_call_objs:
                # 存储结果到 previous_results
                if call.tool_id in execution_results:
                    previous_results[call.tool_id] = execution_results[call.tool_id]
                else:
                    logger.warning(f"工具 {call.tool_id} 的结果不存在于 execution_results 中")

                # 如果有 store_as，额外存储别名
                store_as = call.arguments.get("store_as")
                if store_as:
                    previous_results[store_as] = execution_results.get(call.tool_id)

            # 记录工具执行结果摘要
            if execution_results:
                logger.info(f"工具执行结果摘要: {len(execution_results)}个工具执行完成")

            logger.info(f"第{iteration + 1}轮工具执行完成，结果数: {len(execution_results)}")

            # 第6步：检查是否完成（在执行工具之后）
            if llm_response.get("done"):
                thought.status = ThoughtStatus.COMPLETE
                thought.reason = "思考完成"
                logger.info("LLM表示思考完成")
                break

        # 如果达到最大轮次仍未完成，强制完成
        if thought.status != ThoughtStatus.COMPLETE:
            logger.warning(f"达到最大思考轮次 {self.max_iterations}，强制完成")
            thought.status = ThoughtStatus.COMPLETE

        # 通知电脑前端回复结束（非流式路径）
        if message.source == "computer":
            try:
                from backend.routes.computer_routes import send_done_to_computer
                await send_done_to_computer()
            except Exception:
                pass

        return thought

    async def _think_with_tools(
        self,
        message: AgentMessage,
        previous_results: Dict[str, Any] = None,
        iteration: int = 0
    ) -> dict:
        """
        让 LLM 进行工具感知的思考

        Args:
            message: 消息
            previous_results: 之前的工具结果
            iteration: 当前轮次

        Returns:
            {
                "thought_content": "思考内容",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "tool_name": "get_current_time",
                        "arguments": {},
                        "store_as": "time_result"
                    }
                ],
                "done": True/False
            }
        """
        # 获取可用工具列表
        available_tools = self._get_available_tools_description()

        # 处理 previous_results 为 None 的情况
        if previous_results is None:
            previous_results = {}

        # 构造用户消息内容
        if iteration == 0:
            user_content = await self._build_user_message_with_context(message)
        else:
            # 后续轮次：带上工具结果
            success_count = sum(1 for r in previous_results.values()
                              if isinstance(r, dict) and r.get("success") is True)
            fail_count = sum(1 for r in previous_results.values()
                            if r is None or (isinstance(r, dict) and r.get("success") is False))

            user_content = await self._build_user_message_header(message) + f"""

工具执行结果（共收到 {len(previous_results)} 个结果：{success_count} 个成功，{fail_count} 个失败）:
{self._format_tool_results(previous_results)}

请根据工具结果决定是否需要继续调用工具或完成回复。
注意：search_memory 返回的内容仅供你参考，你需要自己判断其相关性，自然地融入回复中，不要照搬搜索结果。"""

        # 从核心层构建 system prompt（并行获取 STM 感知 + 精力 + 情绪 + 电脑前端状态）
        stm_perception_text, energy_label, mood_label, computer_status = await self._fetch_context_state()

        system_prompt = build_system_prompt(
            identity=identity_loader.identity,
            tools_description=available_tools,
            is_heartbeat=message.is_heartbeat,
            is_private=message.is_private,
            stm_perception=stm_perception_text,
            energy_label=energy_label,
            mood_label=mood_label,
            computer_status=computer_status,
        )

        try:
            # 调用思考模型，将用户消息作为 user prompt 传入
            messages = [{"role": "user", "content": user_content}]
            response = await llm_manager.thinking_chat(
                messages=messages,
                system_prompt=system_prompt
            )

            # 解析 JSON 响应
            logger.info(f"LLM 响应前200字符: {response[:200]}")

            llm_data = self._parse_llm_response(response)
            if llm_data is None:
                # 心跳消息不主动发送纯文本回复，避免模型产生无关内容被误发
                if message.is_heartbeat:
                    logger.info("心跳模式: 模型返回非 JSON，选择沉默")
                    return {
                        "done": True,
                        "thought_content": "",
                        "tool_calls": [],
                    }
                # 真正的纯文本回复，包装为 send_message
                return {
                    "done": True,
                    "thought_content": "直接回复",
                    "tool_calls": [{
                        "id": "call_direct_reply",
                        "tool_name": "send_message",
                        "arguments": {"content": response.strip()},
                        "store_as": None,
                    }],
                }

            logger.info(f"模型思考: {llm_data.get('thought_content', '无')}")
            return llm_data
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}", exc_info=True)
            # 通知管理员
            try:
                from backend.services.error_notifier import notify_error
                await notify_error(
                    error_type="LLM 调用失败",
                    source=f"群{message.group_id} 消息处理",
                    error=f"{type(e).__name__} - {str(e)[:200]}",
                )
            except Exception:
                pass
            # 返回默认完成状态
            return {
                "done": True,
                "thought_content": "",
                "tool_calls": []
            }

    async def _fetch_context_state(self) -> tuple[str, str, str, dict]:
        """并行获取 STM 感知、精力标签、情绪标签、电脑前端状态。"""
        async def _get_stm():
            try:
                from backend.services.stm_client import stm_client
                return await stm_client.get_perception() or ""
            except Exception:
                return ""

        async def _get_energy():
            try:
                from backend.services.sleep_manager import sleep_manager
                return sleep_manager.energy_label
            except Exception:
                return "充沛"

        async def _get_mood():
            try:
                client = await self._get_state_client()
                resp = await client.get(settings.brain.state_api_url)
                if resp.status_code == 200:
                    return resp.json().get("mood_label", "平静")
            except Exception:
                pass
            return "平静"

        def _get_computer_status():
            try:
                from backend.routes.computer_routes import get_computer_status
                return get_computer_status()
            except Exception:
                return {"online": False}

        stm, energy, mood = await asyncio.gather(
            _get_stm(), _get_energy(), _get_mood()
        )
        computer_status = _get_computer_status()
        return stm, energy, mood, computer_status

    def _parse_llm_response(self, response: str) -> Optional[dict]:
        """解析 LLM 响应为 JSON，兼容 markdown 代码块包裹。

        解析顺序：
        1. 直接解析
        2. 提取 ```json ... ``` 代码块后解析
        3. 提取第一个 { ... } 对象后解析
        4. 全部失败返回 None（调用方按纯文本处理）

        Args:
            response: LLM 原始响应文本

        Returns:
            解析后的字典，或 None
        """
        # 1. 直接解析
        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. 提取 markdown 代码块
        import re
        md_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
        if md_match:
            try:
                return json.loads(md_match.group(1))
            except (json.JSONDecodeError, ValueError):
                pass

        # 3. 提取第一个完整 JSON 对象
        first_brace = response.find('{')
        if first_brace >= 0:
            last_brace = response.rfind('}')
            if last_brace > first_brace:
                try:
                    return json.loads(response[first_brace:last_brace + 1])
                except (json.JSONDecodeError, ValueError):
                    pass

        # 4. 不是 JSON
        logger.info(f"LLM 返回非 JSON，将作为直接回复处理: {response[:100]}")
        return None

    def _get_available_tools_description(self) -> str:
        """获取可用工具的描述"""
        tools = []
        for tool_name in self.tool_registry.list_tools():
            tool = self.tool_registry.get(tool_name)
            desc = f"- {tool.name}: {tool.description}\n"
            if tool.arguments:
                arg_parts = []
                for arg in tool.arguments:
                    arg_str = f"{arg.name}({arg.type})"
                    if arg.description:
                        arg_str += f" — {arg.description}"
                    arg_parts.append(arg_str)
                desc += "  参数: " + ", ".join(arg_parts) + "\n"
            tools.append(desc)
        return "\n".join(tools)

    async def _build_user_message_header(self, message: AgentMessage) -> str:
        """构建用户消息的公共头部，包含当前时间、对话上下文和用户档案"""
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekdays[now.weekday()]

        sender = message.sender_nickname or "未知"
        time_str = now.strftime('%Y-%m-%d %H:%M:%S')
        header = "当前时间: " + time_str + " (" + weekday + ")" + chr(10)

        # 群信息：优先显示群名
        group_display = str(message.group_id)
        group_name = napcat_client.get_group_name(str(message.group_id))
        if group_name:
            group_display = f"{group_name}（{message.group_id}）"
        header += "当前群: " + group_display + chr(10)

        header += "用户ID: " + str(message.user_id) + chr(10)
        header += "发送者昵称: " + sender

        # 加载用户档案
        profile_text = await self._load_profile_text(message.user_id)
        if profile_text:
            header += "\n\n关于对方:\n" + profile_text

        # 群聊中展示 @ 信息（带QQ号，方便AI知道@谁）
        if not message.is_private and message.mentions:
            bot_name = "千雪"
            mentioned_info = []
            for m in message.mentions:
                qq = m.get("qq", "")
                name = m.get("name", "")
                if name:
                    mentioned_info.append(f"{name}(QQ:{qq})" if qq else name)
            if message.is_mentioned:
                header += f"\n这条消息是 @你（{bot_name}）的"
            elif mentioned_info:
                header += f"\n这条消息是 @{'、'.join(mentioned_info)} 的，不是 @你（{bot_name}）的"

        content = message.content

        # 回复引用上下文
        if message.reply_content:
            reply_who = message.reply_sender or "某人"
            if message.reply_sender_id:
                reply_who += f"(QQ:{message.reply_sender_id})"
            header += f"\n[回复引用] {reply_who}: {message.reply_content}"

        # 有真实图片描述时，去掉 NapCat 附带的 [图片] 占位文本
        if message.has_image and message.image_description:
            import re
            content = re.sub(r'\[图片\]', '', content).strip()
            header += "\n用户消息: " + content
            header += "\n[图片内容]: " + message.image_description
        else:
            header += "\n用户消息: " + content

        # 语音转写展示（per D-01/D-02: 占位符替换 + 转写标注）
        if message.has_voice and message.voice_transcription:
            import re
            # 去掉 [语音] 占位符（如果存在）
            content = re.sub(r'\[语音\]', '', content).strip()
            # 更新用户消息行（如果上面已经被图片分支写过，需要覆盖）
            header_lines = header.split('\n')
            for i, line in enumerate(header_lines):
                if line.startswith('用户消息: '):
                    header_lines[i] = '用户消息: ' + content
                    break
            header = '\n'.join(header_lines)
            header += "\n[语音消息转写]: " + message.voice_transcription

        return header

    async def _load_profile_text(self, user_id: str) -> str:
        """从缓存或 Memory 服务加载用户档案，返回简短描述文本。"""
        # 检查缓存
        cached = self._profile_cache.get(user_id)
        if cached:
            text, expire_at = cached
            if asyncio.get_event_loop().time() < expire_at:
                return text

        result = await self._fetch_profile_text(user_id)

        # 写入缓存
        now = asyncio.get_event_loop().time()
        self._profile_cache[user_id] = (result, now + self._PROFILE_CACHE_TTL)
        return result

    async def _fetch_profile_text(self, user_id: str) -> str:
        """实际从 Memory 服务获取用户档案。"""
        try:
            import backend.services.memory_interface as mem_mod
            nickname = mem_mod.memory_provider._nickname_map.get(user_id)
            if not nickname:
                return ""

            client = await mem_mod.memory_provider._get_client()
            resp = await client.get("/api/profile/" + nickname)
            if resp.status_code != 200:
                return ""

            data = resp.json()
            if not data.get("found") or not data.get("profile"):
                return ""

            profile = data["profile"]
            basic = profile.get("basic", {})
            style = profile.get("interaction_style", {})

            parts = []
            if basic.get("relation_to_self"):
                parts.append("关系: " + basic["relation_to_self"])
            if basic.get("notes"):
                parts.append("备注: " + basic["notes"])

            if style:
                labels = []
                if style.get("warmth", 0.5) > 0.6:
                    labels.append("亲近")
                if style.get("formality", 0.5) > 0.6:
                    labels.append("正式")
                if style.get("humor", 0.5) > 0.6:
                    labels.append("幽默")
                if labels:
                    parts.append("相处风格: " + "、".join(labels))

            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    async def _build_user_message_with_context(self, message: AgentMessage) -> str:
        """构建带对话上下文的用户消息"""
        from backend.services.context_manager import context_manager
        from backend.services.core.time_utils import format_gap

        # 心跳消息使用主动思考的上下文
        if message.is_heartbeat:
            return await self._build_proactive_context(message)

        header = await self._build_user_message_header(message)

        # 获取最近对话上下文
        try:
            messages = await context_manager.get_group_context(
                group_id=message.group_id,
                limit=settings.brain.context_limit,
                time_window_minutes=settings.brain.context_time_window,
            )
            if messages:
                context_text = context_manager.format_group_context_for_llm(messages)

                # 检测对话间隔：最后一条消息距现在的时间
                try:
                    last_msg = messages[-1]
                    last_time = datetime.fromisoformat(last_msg.timestamp)
                    gap_seconds = (datetime.now() - last_time).total_seconds()
                    if gap_seconds > settings.brain.gap_threshold:  # 超过阈值标注间隔
                        gap_str = format_gap(gap_seconds)
                        context_text = "[距上一条消息已过 " + gap_str + "]\n" + context_text
                except Exception:
                    pass

                return header + "\n\n最近对话:\n" + context_text
        except Exception as e:
            logger.warning("获取对话上下文失败: " + str(e))

        return header

    def _format_tool_results(self, results: Dict[str, Any]) -> str:
        """格式化工具结果供 LLM 查看"""
        if not results:
            return "无"

        formatted = []
        for call_id, result in results.items():
            if result is None:
                formatted.append("- " + call_id + ": 执行失败")
            elif isinstance(result, dict) and "success" in result:
                if result["success"]:
                    # 优先展示有语义的结果字段（如 briefing），避免把内容吞掉
                    content = result.get("briefing") or result.get("message") or result.get("data")
                    if content:
                        formatted.append("- " + call_id + ": " + str(content))
                    else:
                        formatted.append("- " + call_id + ": 已发送")
                else:
                    error = result.get("error", "未知错误")
                    error_type = result.get("error_type", "")
                    if error_type:
                        formatted.append("- " + call_id + ": 失败 (" + error_type + ") - " + error)
                    else:
                        formatted.append("- " + call_id + ": 失败 - " + error)
            else:
                formatted.append("- " + call_id + ": " + str(result))

        return "\n".join(formatted)

    def _create_tool_calls(
        self,
        llm_tool_calls: List[dict],
        message: AgentMessage,
        previous_results: Dict[str, Any]
    ) -> List[ToolCall]:
        """将 LLM 的工具调用转换为 ToolCall 对象"""
        tool_calls = []

        for tc in llm_tool_calls:
            tool_calls.append(ToolCall(
                tool_name=tc["tool_name"],
                tool_id=tc["id"],
                arguments=tc.get("arguments", {}),
                resolved_arguments={},
                depends_on=[]
            ))

        for call in tool_calls:
            dependencies = self._extract_variable_dependencies(call.arguments)
            batch_store_as_names = {tc.arguments.get("store_as") for tc in tool_calls if tc.arguments.get("store_as")}
            batch_tool_ids = {tc.tool_id for tc in tool_calls}

            detected_deps = []
            for dep in dependencies:
                if dep in batch_store_as_names or dep in batch_tool_ids:
                    detected_deps.append(dep)

            if detected_deps:
                logger.info("工具 " + call.tool_id + " 检测到对本批次其他工具的依赖: " + str(detected_deps))
                logger.warning("工具调用存在依赖关系，但当前批次会并行执行，可能导致变量替换失败")

            call.depends_on = detected_deps

        return tool_calls

    def _extract_variable_dependencies(self, arguments: Dict[str, Any]) -> List[str]:
        """从参数中提取变量引用"""
        dependencies = []

        for key, value in arguments.items():
            if isinstance(value, str):
                import re
                matches = re.findall(r'\{([^{}]+)\}', value)
                dependencies.extend(matches)

        return dependencies

    def _resolve_arguments_with_results(
        self,
        arguments: Dict[str, Any],
        message: AgentMessage,
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析参数，支持引用之前的工具结果"""
        variables = {
            "group_id": message.group_id,
            "user_id": message.user_id,
            "sender_nickname": message.sender_nickname or "",
            "content": message.content,
            "image_description": message.image_description or "",
            "voice_transcription": message.voice_transcription or ""
        }

        variables.update(results)

        resolved = {}
        for key, value in arguments.items():
            if isinstance(value, str) and "{" in value:
                resolved_value = value
                for var_name, var_value in variables.items():
                    resolved_value = resolved_value.replace("{" + var_name + "}", str(var_value))
                resolved[key] = resolved_value
            else:
                resolved[key] = value

        return resolved

    async def _execute_tools(
        self,
        tool_calls: List[ToolCall],
        message: AgentMessage,
        previous_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具调用。

        send_message 和 send_voice 按顺序串行（保证消息/语音顺序），其余工具并行。
        """
        results = {}

        # 分离 send_message/send_voice/forward_message 和其他工具
        send_msgs = [tc for tc in tool_calls if tc.tool_name in ("send_message", "send_voice", "forward_message")]
        others = [tc for tc in tool_calls if tc.tool_name not in ("send_message", "send_voice", "forward_message")]

        # 其他工具并行执行
        if others:
            other_results = await asyncio.gather(*[
                self._execute_single_tool(tc, message, previous_results)
                for tc in others
            ])
            for tc, result in zip(others, other_results):
                results[tc.tool_id] = result

        # send_message/send_voice 串行执行（保证消息/语音顺序）
        for tc in send_msgs:
            result = await self._execute_single_tool(tc, message, previous_results)
            results[tc.tool_id] = result

        return results

    async def _execute_single_tool(
        self,
        tool_call: ToolCall,
        message: AgentMessage,
        previous_results: Dict[str, Any]
    ) -> Any:
        """执行单个工具"""
        tool_call.status = ToolCallStatus.RUNNING
        tool_call.start_time = datetime.now().timestamp()

        try:
            resolved_args = self._resolve_arguments_with_results(
                tool_call.arguments,
                message,
                previous_results
            )

            # forward_message → 映射到 send_message
            if tool_call.tool_name == "forward_message":
                target = resolved_args.pop("target", message.group_id)
                # 群名解析：尝试把群名转成群号
                resolved_target = napcat_client.resolve_group_id(target)
                if resolved_target is None:
                    tool_call.status = ToolCallStatus.FAILED
                    logger.warning(f"forward_message 无法解析目标: {target}")
                    return {"success": False, "error": f"找不到群「{target}」，请确认群名是否正确"}
                # 校验群号：太短说明被截断了
                clean = resolved_target.replace("private_", "")
                if clean.isdigit() and len(clean) < 6:
                    tool_call.status = ToolCallStatus.FAILED
                    logger.warning(f"forward_message 群号疑似被截断: {target} → {resolved_target}")
                    return {"success": False, "error": f"群号太短，请用群名而不是群号"}
                resolved_args["group_id"] = resolved_target
                tool_call.tool_name = "send_message"
            else:
                if "group_id" not in resolved_args:
                    resolved_args["group_id"] = message.group_id
            if "user_id" not in resolved_args:
                resolved_args["user_id"] = message.user_id

            tool_call.resolved_arguments = resolved_args

            result = await self.tool_registry.execute_tool(
                tool_call.tool_name,
                **resolved_args
            )

            tool_call.result = result
            tool_call.status = ToolCallStatus.SUCCESS
            tool_call.end_time = datetime.now().timestamp()

            if tool_call.tool_name != "send_message":
                try:
                    from backend.services.stm_client import stm_client
                    asyncio.create_task(stm_client.record_event(
                        event_type="tool_call",
                        source_type="qq_group",
                        group_id=message.group_id,
                        summary="你调用了 " + tool_call.tool_name,
                        detail=str(resolved_args)[:200],
                        importance=0.3,
                    ))
                except Exception:
                    pass

            logger.info("工具 " + tool_call.tool_name + " 执行成功，参数: " + str(resolved_args))
            logger.debug("工具 " + tool_call.tool_id + " 完整返回结果: " + str(result))
            return result

        except Exception as e:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.end_time = datetime.now().timestamp()

            logger.error("工具 " + tool_call.tool_name + " 执行失败", exc_info=True)
            logger.error("  工具ID: " + tool_call.tool_id)
            logger.error("  错误类型: " + type(e).__name__)
            logger.error("  错误信息: " + str(e))

            try:
                from backend.services.error_notifier import notify_error
                await notify_error(
                    error_type="工具执行失败 (" + tool_call.tool_name + ")",
                    source="群" + message.group_id,
                    error=type(e).__name__ + " - " + str(e)[:200],
                )
            except Exception:
                pass

            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def _send_interim_message(
        self,
        message: AgentMessage,
        text: str,
    ) -> None:
        """发送中间消息到用户（思考过程中的简短提示）。"""
        try:
            text = text[:settings.brain.interim_max_length] if len(text) > settings.brain.interim_max_length else text

            # Discord 路由
            if message.source == "discord":
                from backend.services.agent.sources.discord_source import discord_source
                if discord_source and discord_source.is_connected():
                    is_private = message.group_id.startswith("dm_")
                    await discord_source.send_message(
                        channel_id=message.group_id,
                        text=text,
                        is_private=is_private,
                    )
                    logger.info("中间消息已发送(Discord): " + text)
                    return

            # QQ 路由
            if message.is_private:
                await napcat_client.send_private_message(int(message.user_id), text)
            else:
                await napcat_client.send_group_message(int(message.group_id), text)
            logger.info("中间消息已发送: " + text)
        except Exception as e:
            logger.warning("中间消息发送失败（非关键）: " + str(e))

    # ------------------------------------------------------------------
    # 流式回复路径
    # ------------------------------------------------------------------

    async def _stream_reply(self, message: AgentMessage) -> AgentThought:
        """流式回复 — 文字和工具调用并行收集，多轮流式循环。"""
        from .streaming.sentence_detector import SentenceDetector
        from .streaming.streaming_prompt import build_streaming_prompt, build_api_tools
        from .streaming.message_manager import message_manager

        thought = AgentThought()
        full_reply_parts: list[str] = []
        all_tool_results: Dict[str, Any] = {}
        tool_call_counts: Dict[str, int] = {}  # 追踪每个工具被调用的次数，防死循环

        # 构建流式 system prompt
        stm_perception_text, energy_label, mood_label, computer_status = await self._fetch_context_state()
        system_prompt = build_streaming_prompt(
            identity=identity_loader.identity,
            is_private=message.is_private,
            stm_perception=stm_perception_text,
            energy_label=energy_label,
            mood_label=mood_label,
            computer_status=computer_status,
        )

        # 构建 API tools
        api_tools = build_api_tools(self.tool_registry)
        logger.info(f"流式路径 API tools: {[t['function']['name'] for t in api_tools]}")

        # 构建用户消息
        user_content = await self._build_user_message_with_context(message)
        messages = [{"role": "user", "content": user_content}]

        # 语音频道：启动 TTS 管道
        voice_queue: Optional[asyncio.Queue] = None
        voice_task = None
        if message.group_id.startswith("voice_"):
            voice_queue = asyncio.Queue()
            message_manager.set_voice_sentence_queue(voice_queue)
            from backend.services.voice_player import voice_player
            voice_task = asyncio.create_task(voice_player.play_streaming(voice_queue))

        try:
            # 初始化有序并发 TTS 生命周期
            message_manager.begin_tts_reply()

            for iteration in range(self.max_iterations):
                thought.iteration = iteration + 1
                logger.info(f"流式轮次 {iteration + 1}/{self.max_iterations}")

                detector = SentenceDetector()
                collected_text = ""
                collected_tool_calls: list[dict] = []
                last_tool_delta: list[dict] = []
                has_tool_calls = False

                async for event in llm_manager.stream_chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=api_tools if api_tools else None,
                ):
                    event_type = event["type"]

                    if event_type == "content":
                        token = event["delta"]
                        collected_text += token
                        # token 级推送到电脑前端（逐字显示）
                        if message.source == "computer" and token:
                            if token.strip() != "（沉默）":
                                await message_manager.send_token(message, token)
                        sentences = detector.feed(token)
                        for sentence in sentences:
                            if sentence.strip() == "（沉默）":
                                continue
                            await message_manager.send_sentence(message, sentence)
                            full_reply_parts.append(sentence)

                    elif event_type == "tool_call_delta":
                        has_tool_calls = True
                        last_tool_delta = event["delta"]

                    elif event_type == "done":
                        # flush 剩余文字
                        for sentence in detector.flush():
                            if sentence.strip() == "（沉默）":
                                continue
                            await message_manager.send_sentence(message, sentence)
                            full_reply_parts.append(sentence)

                        if event.get("reason") == "tool_calls" or has_tool_calls:
                            collected_tool_calls = self._convert_api_tool_calls(last_tool_delta)

                if not collected_tool_calls:
                    # 没有工具调用，完成
                    thought.status = ThoughtStatus.COMPLETE
                    break

                # 执行工具
                logger.info(f"流式路径: 执行 {len(collected_tool_calls)} 个工具调用")
                tool_call_objs = self._create_tool_calls(collected_tool_calls, message, all_tool_results)
                execution_results = await self._execute_tools(tool_call_objs, message, all_tool_results)

                # 更新结果映射
                for call in tool_call_objs:
                    if call.tool_id in execution_results:
                        all_tool_results[call.tool_id] = execution_results[call.tool_id]
                    tool_call_counts[call.tool_name] = tool_call_counts.get(call.tool_name, 0) + 1

                # 将工具结果喂回消息，继续下一轮流式
                assistant_content = collected_text or ""
                tool_results_content = self._format_tool_results(execution_results)

                # 构建反馈消息 — 检测重复工具调用，防死循环
                max_repeat = max(tool_call_counts.values()) if tool_call_counts else 0
                send_already_ok = any(
                    isinstance(all_tool_results.get(tid), dict) and all_tool_results.get(tid, {}).get("success")
                    for tid in all_tool_results
                )

                if max_repeat >= 2:
                    repeated = [name for name, cnt in tool_call_counts.items() if cnt >= 2]
                    feedback_msg = (
                        f"工具执行结果:\n{tool_results_content}\n\n"
                        f"⚠️ 你已经多次调用 {', '.join(repeated)}，获得了足够的信息。"
                        f"不要再调用该工具，直接根据已有结果回复。如需其他工具可以继续调用。"
                    )
                elif send_already_ok:
                    feedback_msg = (
                        f"工具执行结果:\n{tool_results_content}\n\n"
                        f"消息已成功发送，不要再次调用发送工具。直接回复即可。"
                    )
                else:
                    feedback_msg = f"工具执行结果:\n{tool_results_content}\n\n请根据结果回复。如果不需要更多工具，直接回复即可。"

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": feedback_msg})

            # 达到最大轮次
            if thought.status != ThoughtStatus.COMPLETE:
                logger.warning(f"流式路径达到最大轮次 {self.max_iterations}")
                thought.status = ThoughtStatus.COMPLETE

        finally:
            # 等待所有 TTS 任务完成
            await message_manager.end_tts_reply()
            # 结束语音管道
            if voice_queue is not None:
                await voice_queue.put(None)
            if voice_task is not None:
                try:
                    await voice_task
                except Exception:
                    pass

        # 存储上下文和记忆
        if full_reply_parts:
            await self._store_streaming_reply(message, full_reply_parts)

        # 通知电脑前端回复结束
        if message.source == "computer":
            try:
                from backend.routes.computer_routes import send_done_to_computer
                await send_done_to_computer()
            except Exception:
                pass

        return thought

    def _convert_api_tool_calls(self, delta_list: list[dict]) -> list[dict]:
        """将 API 格式的工具调用 delta 转为内部格式。

        delta_list 是 stream_chat() 最后一次 tool_call_delta 事件的累积结果，
        结构为 [{id, type, function: {name, arguments}}, ...]。
        """
        results = []
        for i, tc in enumerate(delta_list):
            fn = tc.get("function", {})
            arguments = {}
            if fn.get("arguments"):
                try:
                    arguments = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    arguments = {"raw": fn["arguments"]}

            results.append({
                "id": tc.get("id", f"call_{i}"),
                "tool_name": fn.get("name", ""),
                "arguments": arguments,
            })
        return results

    async def _store_streaming_reply(self, message: AgentMessage, reply_parts: list[str]) -> None:
        """存储流式回复的上下文和记忆。"""
        from backend.services.context_manager import context_manager

        full_reply = "".join(reply_parts)
        if not full_reply.strip():
            return

        # 确定参数
        if message.source == "computer":
            user_id = "robot"
            source_type = "computer_chat"
        elif message.source == "discord":
            user_id = "robot"
            if message.group_id.startswith("dm_"):
                source_type = "discord_private"
            elif message.group_id.startswith("voice_"):
                source_type = "voice_channel"
            else:
                source_type = "discord_channel"
        else:
            user_id = str(napcat_client.self_id)
            source_type = "qq_private" if message.is_private else "qq_group"

        # 上下文存储
        try:
            await context_manager.add_group_message(
                group_id=message.group_id,
                user_id=user_id,
                role="assistant",
                content=full_reply,
                sender_nickname="机器人",
                mentions=[],
                is_directed_at_bot=False,
            )
        except Exception as e:
            logger.warning(f"流式回复上下文存储失败: {e}")

        # 记忆提取（fire-and-forget）
        try:
            import backend.services.memory_interface as mem_mod
            asyncio.create_task(
                mem_mod.memory_provider.extract_and_store(
                    group_id=message.group_id,
                    user_id=user_id,
                    content=full_reply,
                    role="assistant",
                    speaker="千雪",
                    source_type=source_type,
                )
            )
        except Exception:
            pass

        # STM 事件（fire-and-forget）
        try:
            from backend.services.stm_client import stm_client
            asyncio.create_task(stm_client.record_event(
                event_type="ai_reply",
                source_type=source_type,
                group_id=message.group_id,
                summary=f"你回复了: {full_reply[:60]}",
                importance=0.6,
            ))
        except Exception:
            pass

    _last_proactive_speak: Dict[str, datetime] = {}
    _proactive_speak_count: int = 0
    _proactive_speak_hour_start: Optional[datetime] = None

    async def proactive_think(self):
        """主动思考模式（心跳触发）。"""
        try:
            context = await self._gather_proactive_context()

            if not context.get("has_activity"):
                logger.debug("proactive_think: no activity, skipping")
                return

            heartbeat_msg = AgentMessage.create_heartbeat(
                group_summaries=context.get("group_summaries")
            )

            logger.info("proactive_think: activity detected, entering think loop")
            thought = await self._think_loop(heartbeat_msg)
            logger.info("proactive_think: completed, status=" + str(thought.status))

        except Exception as e:
            logger.error("proactive_think failed: " + str(e), exc_info=True)
            try:
                from backend.services.error_notifier import notify_error
                await notify_error(
                    error_type="心跳主动思考失败",
                    source="proactive_think",
                    error=type(e).__name__ + " - " + str(e)[:200],
                )
            except Exception:
                pass

    async def _gather_proactive_context(self) -> dict:
        """自己查看各群最近的动静。"""
        from backend.services.context_manager import context_manager

        has_activity = False
        group_summaries = {}

        try:
            from backend.database.db import get_db
            conn = await get_db()
            cursor = await conn.execute(
                "SELECT DISTINCT group_id FROM conversations ORDER BY group_id"
            )
            rows = await cursor.fetchall()
            group_ids = [row[0] for row in rows]
        except Exception as e:
            logger.warning("Failed to query groups: " + str(e))
            return {"has_activity": False, "group_summaries": {}}

        for gid in group_ids:
            # 跳过正在对话中的群/私聊，避免心跳插嘴
            if self._is_conversation_active(gid):
                logger.debug(f"proactive_think: skip {gid}, conversation active")
                continue

            try:
                messages = await context_manager.get_group_context(
                    group_id=gid,
                    limit=settings.brain.proactive_context_limit,
                    time_window_minutes=settings.brain.proactive_context_time_window,
                )

                if messages:
                    has_activity = True
                    formatted = context_manager.format_group_context_for_llm(messages)
                    group_summaries[gid] = "### 群 " + gid + "\n" + formatted

            except Exception as e:
                logger.warning("Failed to gather context for group " + gid + ": " + str(e))

        return {
            "has_activity": has_activity,
            "group_summaries": group_summaries,
        }

    async def _check_recent_ai_reply(self, group_id: str, seconds: int = 60) -> bool:
        """检查 AI 最近是否在指定群发过消息。"""
        try:
            from backend.database.db import get_db
            from datetime import timedelta

            cutoff = (datetime.now() - timedelta(seconds=seconds)).isoformat()
            conn = await get_db()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE group_id = ? AND role = 'assistant' AND timestamp >= ?",
                (group_id, cutoff),
            )
            row = await cursor.fetchone()
            return row[0] > 0
        except Exception:
            return False

    async def _build_proactive_context(self, message: AgentMessage) -> str:
        """构建心跳消息的用户上下文。"""
        parts = ["当前时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S')]

        summaries = message.heartbeat_group_summaries or {}
        if summaries:
            parts.append("\n## 各群最近消息")
            for gid, text in summaries.items():
                parts.append(text)
        else:
            parts.append("\n各群最近没有新消息。")

        # 并行获取状态 + STM 感知
        async def _get_state_prompt():
            try:
                client = await self._get_state_client()
                resp = await client.get(settings.brain.state_api_url)
                if resp.status_code == 200:
                    return resp.json().get("state_prompt", "")
            except Exception:
                pass
            return ""

        async def _get_stm_perception():
            try:
                from backend.services.stm_client import stm_client
                return await stm_client.get_perception()
            except Exception:
                return None

        state_text, perception = await asyncio.gather(
            _get_state_prompt(), _get_stm_perception()
        )

        if state_text:
            parts.append("\n## AI 当前状态\n" + state_text)
        if perception:
            parts.append("\n## 短期记忆\n" + perception)

        parts.append("\n请根据你的真实感受决定现在想做什么。")

        return "\n".join(parts)

    def _can_proactive_speak(self, group_id: str) -> bool:
        """检查是否允许在指定群主动发言（频率控制）。"""
        now = datetime.now()

        last = self._last_proactive_speak.get(group_id)
        if last and (now - last).seconds < settings.brain.proactive_speak_cooldown:
            return False

        if self._proactive_speak_hour_start:
            elapsed = (now - self._proactive_speak_hour_start).seconds
            if elapsed < 3600:
                if self._proactive_speak_count >= settings.brain.proactive_speak_max_per_hour:
                    return False
            else:
                self._proactive_speak_count = 0
                self._proactive_speak_hour_start = now
        else:
            self._proactive_speak_hour_start = now

        return True