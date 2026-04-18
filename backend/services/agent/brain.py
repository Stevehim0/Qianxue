"""Agent大脑 - 主思考引擎."""

import logging
import asyncio
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from .message import AgentMessage
from .thought import AgentThought, ThoughtStatus
from .tool_call import ToolCall, ToolCallStatus
from .tools.registry import ToolRegistry

from backend.api.llm import llm_manager
from backend.api.napcat import napcat_client
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
        self.max_iterations = 5  # 最大思考轮次

    async def process_message(self, message: AgentMessage) -> AgentThought:
        """
        处理消息的主流程

        Args:
            message: 统一格式的消息

        Returns:
            思考结果
        """
        logger.info(f"AgentBrain开始处理消息: group={message.group_id}, user={message.user_id}")

        # 每条消息都独立思考，不使用缓存
        # 因为每条消息的内容都不同，复用思考结果会导致错误回复
        thought = await self._think_loop(message)

        return thought

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
        interim_sent = False  # 每次思考最多发一条中间消息

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

            # 第3.5步：中间回复——耗时工具执行前提示用户
            # 快速工具（get_time, get_context）不需要 interim，避免简单对话显得不自然
            FAST_TOOLS = {"get_time", "get_context"}
            called_tool_names = {tc.get("tool_name") for tc in tool_calls}
            has_slow_tool = bool(called_tool_names - FAST_TOOLS - {"send_message"})
            has_send = any(tc.get("tool_name") == "send_message" for tc in tool_calls)

            interim_msg = llm_response.get("interim_message", "")

            # 模型显式提供了 interim_message
            if interim_msg and tool_calls and not llm_response.get("done") and not interim_sent:
                interim_sent = True
                logger.info(f"发送中间消息: {interim_msg[:50]}")
                asyncio.create_task(self._send_interim_message(message, interim_msg))
            # 仅当调了耗时工具且没有 send_message 时，自动发一条
            elif has_slow_tool and not has_send and not interim_sent:
                interim_sent = True
                import random
                auto_msgs = [
                    "嗯...让我想想",
                    "等一下哈",
                    "我想想...",
                    "稍等",
                    "让我回忆一下",
                    "嗯.....",
                    "哈......",
                    "啊...",
                    "唔...",
                    "诶...",
                    "呃...",
                    "嗯...",
                    "等等哈",
                    "等下",
                ]
                auto_msg = random.choice(auto_msgs)
                logger.info(f"自动发送中间消息: {auto_msg}")
                asyncio.create_task(self._send_interim_message(message, auto_msg))

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
                # 如果 send_message 被截断，强制再走一轮让模型继续发送
                send_truncated = any(
                    isinstance(r, dict) and r.get("truncated")
                    for r in execution_results.values()
                )
                if send_truncated and iteration + 1 < self.max_iterations:
                    logger.info("send_message 被截断，强制进入下一轮继续发送")
                    llm_response["done"] = False
                else:
                    thought.status = ThoughtStatus.COMPLETE
                    thought.reason = "思考完成"
                    logger.info("LLM表示思考完成")
                    break

        # 如果达到最大轮次仍未完成，强制完成
        if thought.status != ThoughtStatus.COMPLETE:
            logger.warning(f"达到最大思考轮次 {self.max_iterations}，强制完成")
            thought.status = ThoughtStatus.COMPLETE

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

        # 从核心层构建 system prompt（包含 STM 感知 + 精力状态）
        stm_perception_text = ""
        try:
            from backend.services.stm_client import stm_client
            stm_perception_text = await stm_client.get_perception() or ""
        except Exception:
            pass

        energy_label = "充沛"
        mood_label = "平静"
        try:
            from backend.services.sleep_manager import sleep_manager
            energy_label = sleep_manager.energy_label
        except Exception:
            pass

        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get("http://localhost:8001/api/state")
                if resp.status_code == 200:
                    mood_label = resp.json().get("mood_label", "平静")
        except Exception:
            pass

        system_prompt = build_system_prompt(
            identity=identity_loader.identity,
            tools_description=available_tools,
            is_heartbeat=message.is_heartbeat,
            is_private=message.is_private,
            stm_perception=stm_perception_text,
            energy_label=energy_label,
            mood_label=mood_label,
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
                args_desc = ", ".join([
                    f"{arg.name}({arg.type})"
                    for arg in tool.arguments
                ])
                desc += f"  参数: {args_desc}\n"
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
        header += "群聊ID: " + str(message.group_id) + chr(10)
        header += "用户ID: " + str(message.user_id) + chr(10)
        header += "发送者昵称: " + sender

        # 加载用户档案
        profile_text = await self._load_profile_text(message.user_id)
        if profile_text:
            header += "\n\n关于对方:\n" + profile_text

        header += "\n用户消息: " + message.content
        return header

    async def _load_profile_text(self, user_id: str) -> str:
        """从 Memory 服务加载用户档案，返回简短描述文本。"""
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
                limit=20,
                time_window_minutes=60,
            )
            if messages:
                context_text = context_manager.format_group_context_for_llm(messages)

                # 检测对话间隔：最后一条消息距现在的时间
                try:
                    last_msg = messages[-1]
                    last_time = datetime.fromisoformat(last_msg.timestamp)
                    gap_seconds = (datetime.now() - last_time).total_seconds()
                    if gap_seconds > 600:  # 超过10分钟标注间隔
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
                    if result.get("truncated"):
                        formatted.append(
                            "- " + call_id + ": 消息被截断！原长" + str(result['original_length']) + "字，"
                            "上限" + str(result['max_length']) + "字，已发送前半部分。请继续发送剩余内容。"
                        )
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
            "image_description": message.image_description or ""
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
        """执行工具调用（并行）"""
        results = {}

        tasks = [
            self._execute_single_tool(tool_call, message, previous_results)
            for tool_call in tool_calls
        ]
        execution_results = await asyncio.gather(*tasks)

        for tool_call, result in zip(tool_calls, execution_results):
            results[tool_call.tool_id] = result

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
            text = text[:50] if len(text) > 50 else text

            if message.is_private:
                await napcat_client.send_private_message(int(message.user_id), text)
            else:
                await napcat_client.send_group_message(int(message.group_id), text)
            logger.info("中间消息已发送: " + text)
        except Exception as e:
            logger.warning("中间消息发送失败（非关键）: " + str(e))

    async def _refine_with_speaking_model(self, draft_message: str, original_message: AgentMessage) -> Optional[str]:
        """使用说话模型润色消息内容。"""
        speaking_provider = llm_manager.get_speaking_provider()
        if not speaking_provider:
            return None

        thinking_provider = llm_manager.get_thinking_provider()
        if thinking_provider and speaking_provider is thinking_provider:
            return None

        refine_prompt = "你是一个消息润色助手。请将以下草稿消息润色为更自然、更口语化的回复。\n\n要求：\n- 保持原始意图和核心信息不变\n- 使语气更自然、更像真人说话\n- 不要添加草稿中没有的信息\n- 只返回润色后的消息内容\n\n草稿消息：\n" + draft_message

        messages = [{"role": "user", "content": refine_prompt}]
        response = await llm_manager.speaking_chat(messages=messages)
        return response.strip() if response else None

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
            try:
                messages = await context_manager.get_group_context(
                    group_id=gid,
                    limit=10,
                    time_window_minutes=0.5,
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

        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get("http://localhost:8001/api/state")
                if resp.status_code == 200:
                    state_data = resp.json()
                    state_text = state_data.get("state_prompt", "")
                    if state_text:
                        parts.append("\n## AI 当前状态\n" + state_text)
        except Exception:
            pass

        try:
            from backend.services.stm_client import stm_client
            perception = await stm_client.get_perception()
            if perception:
                parts.append("\n## 短期记忆\n" + perception)
        except Exception:
            pass

        parts.append("\n请决定你现在想做什么。大多数时候选择沉默就好。")

        return "\n".join(parts)

    def _can_proactive_speak(self, group_id: str) -> bool:
        """检查是否允许在指定群主动发言（频率控制）。"""
        now = datetime.now()

        last = self._last_proactive_speak.get(group_id)
        if last and (now - last).seconds < 120:
            return False

        if self._proactive_speak_hour_start:
            elapsed = (now - self._proactive_speak_hour_start).seconds
            if elapsed < 3600:
                if self._proactive_speak_count >= 3:
                    return False
            else:
                self._proactive_speak_count = 0
                self._proactive_speak_hour_start = now
        else:
            self._proactive_speak_hour_start = now

        return True