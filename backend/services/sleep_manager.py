"""AI 睡眠管理器 — 模拟人类睡眠节律。

状态机：AWAKE → WINDING_DOWN → ASLEEP → AWAKE（唤醒）

通过更新 state 层的能量状态让 AI 自然感受到困倦/清醒，
而非通过系统提示词强制告知"你该睡了"。
prompt_builder 直接读取 energy_label 注入到 prompt 中。
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.services.agent.message import AgentMessage

logger = logging.getLogger(__name__)


class SleepManager:
    """AI 睡眠状态管理器。"""

    enabled: bool = False  # 设为 True 启用睡眠节律
    WIND_DOWN_HOUR = 23
    SLEEP_HOUR = 0
    WAKE_HOUR = 8

    def __init__(self):
        self._private_queue: Dict[str, List[Tuple[AgentMessage, str]]] = {}
        self._state = "AWAKE"
        self._last_wind_down_date: str = ""
        self._brain = None
        self._energy_label: str = "充沛"

    def set_brain(self, brain) -> None:
        self._brain = brain

    @property
    def energy_label(self) -> str:
        """当前精力标签，供 prompt_builder 注入。"""
        return self._energy_label

    @property
    def is_asleep(self) -> bool:
        return self._state == "ASLEEP"

    @property
    def is_winding_down(self) -> bool:
        return self._state == "WINDING_DOWN"

    @property
    def should_skip_heartbeat(self) -> bool:
        return self._state in ("ASLEEP", "WINDING_DOWN")

    def check_and_transition(self) -> bool:
        """检查当前时间，执行状态转换。返回是否刚发生唤醒。"""
        if not self.enabled:
            return False

        hour = datetime.now().hour
        today = datetime.now().strftime("%Y-%m-%d")
        prev = self._state

        if self.WAKE_HOUR <= hour < self.WIND_DOWN_HOUR:
            # 08:00 ~ 22:59 → 清醒
            if self._state != "AWAKE":
                logger.info(f"睡眠状态转换: {self._state} → AWAKE")
                self._state = "AWAKE"
                self._energy_label = "充沛"
                self._sync_state_api(0.8, "充沛")
                return True

        elif hour >= self.WIND_DOWN_HOUR:
            # 23:00 ~ 23:59 → 困倦
            if self._state == "AWAKE" and self._last_wind_down_date != today:
                self._last_wind_down_date = today
                logger.info("睡眠状态转换: AWAKE → WINDING_DOWN")
                self._state = "WINDING_DOWN"
                self._energy_label = "困倦"
                self._sync_state_api(0.3, "困倦")

        elif hour < self.WAKE_HOUR:
            # 00:00 ~ 07:59 → 睡眠
            if self._state != "ASLEEP":
                logger.info(f"睡眠状态转换: {self._state} → ASLEEP")
                self._state = "ASLEEP"
                self._energy_label = "沉睡"

        return False

    def queue_private_message(self, message: AgentMessage) -> None:
        """睡眠期间私聊消息入队，附带接收时间。"""
        key = message.group_id
        if key not in self._private_queue:
            self._private_queue[key] = []
        now_str = datetime.now().strftime("%H:%M")
        self._private_queue[key].append((message, now_str))
        logger.info(f"私聊消息入队: {key} (队列: {len(self._private_queue[key])}条)")

    def drain_private_queue(self) -> Dict[str, List[Tuple[AgentMessage, str]]]:
        """取出并清空私聊消息队列。"""
        queue = self._private_queue.copy()
        self._private_queue.clear()
        return queue

    def _sync_state_api(self, value: float, label: str) -> None:
        """同步更新 Memory 服务 state 层的 energy（fire-and-forget HTTP）。"""
        try:
            import httpx
            # Memory 服务目前没有 PUT /api/state 端点，
            # 这里先记日志，后续可以加上
            logger.info(f"状态同步: energy={value}, label={label}（待 Memory API 支持）")
        except Exception as e:
            logger.warning(f"状态同步失败: {e}")

    async def handle_wake_up(self) -> None:
        """唤醒序列：恢复能量 + STM 注入 + 处理积压私聊。"""
        logger.info("=== AI 唤醒序列开始 ===")

        # 1. STM 注入唤醒感知
        try:
            from backend.services.stm_client import stm_client
            await stm_client.record_event(
                event_type="ai_reply",
                source_type="system",
                group_id="global",
                summary="刚经历了一夜的梦境处理，记忆已经整理完毕",
                importance=0.9,
            )
        except Exception as e:
            logger.warning(f"STM 唤醒注入失败: {e}")

        # 2. 处理积压私聊消息
        queue = self.drain_private_queue()
        if not queue:
            logger.info("无积压私聊消息")
            return

        if not self._brain:
            logger.warning("brain 未注入，无法处理积压消息")
            return

        logger.info(f"处理 {len(queue)} 个用户的积压私聊")

        for user_key, messages in queue.items():
            try:
                lines = []
                for msg, ts in messages:
                    name = msg.sender_nickname or "对方"
                    lines.append(f"[{ts}] {name}: {msg.content}")

                last_msg = messages[-1][0]
                wake_msg = AgentMessage(
                    source=last_msg.source,
                    group_id=last_msg.group_id,
                    user_id=last_msg.user_id,
                    sender_nickname=last_msg.sender_nickname,
                    content="[以下是你休息期间收到的私聊消息，请回复对方]\n" + "\n".join(lines),
                    is_mentioned=True,
                    priority=10,
                    is_heartbeat=False,
                    is_private=True,
                    has_image=False,
                    image_description="",
                )
                await self._brain.process_message(wake_msg)
                logger.info(f"已处理 {user_key} 积压消息 ({len(messages)}条)")
            except Exception as e:
                logger.error(f"处理 {user_key} 积压消息失败: {e}")


async def run_sleep_cycle() -> None:
    """睡眠周期后台任务，每 60 秒检查一次状态转换。"""
    logger.info("睡眠周期监控已启动")
    while True:
        try:
            just_woke = sleep_manager.check_and_transition()
            if just_woke:
                await sleep_manager.handle_wake_up()
        except Exception as e:
            logger.error(f"睡眠周期检查异常: {e}")
        await asyncio.sleep(60)


# 模块级单例
sleep_manager = SleepManager()
