"""巩固层定时调度器。

在休眠时间段（默认 02:00~08:00）自动触发巩固：
1. 先执行增量巩固
2. 增量完成后，如果休眠时间还有剩余（>30分钟），执行全量巩固
3. 全量巩固有超时保护：不超过剩余休眠时间 - 5分钟

配置来源: Memory/config/settings.py ScheduleConfig
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional

from Memory.config.settings import settings

logger = logging.getLogger(__name__)


class SchedulerState(str, Enum):
    """调度器状态。"""
    IDLE = "idle"                # 空闲，等待休眠时间
    INCREMENTAL = "incremental"  # 增量巩固中
    FULL = "full"                # 全量巩固中
    DONE = "done"                # 本轮巩固已完成，等待下个周期


class ConsolidationScheduler:
    """巩固层定时调度器。

    后台循环运行，每 60 秒检查一次是否需要触发巩固。
    """

    CHECK_INTERVAL = 60  # 检查间隔（秒）
    MIN_REMAINING_FOR_FULL = 30 * 60  # 剩余时间阈值：30 分钟（秒）
    TIMEOUT_BUFFER = 5 * 60  # 全量巩固超时缓冲：5 分钟（秒）

    def __init__(self):
        self._state = SchedulerState.IDLE
        self._task: Optional[asyncio.Task] = None
        self._last_run_time: Optional[str] = None
        self._last_incremental_result: Optional[dict] = None
        self._last_full_result: Optional[dict] = None
        self._current_date: Optional[str] = None  # 跟踪当前休眠周期所属日期
        self._running = False

    @property
    def state(self) -> SchedulerState:
        return self._state

    @property
    def status(self) -> dict:
        """返回当前调度状态（供 API 使用）。"""
        return {
            "state": self._state.value,
            "sleep_time": settings.schedule.sleep_time,
            "wake_time": settings.schedule.wake_time,
            "last_run_time": self._last_run_time,
            "last_incremental_result": self._summarize_result(self._last_incremental_result),
            "last_full_result": self._summarize_result(self._last_full_result),
        }

    def start(self):
        """启动调度器后台任务。"""
        if not settings.schedule.enabled:
            logger.info("巩固调度器已禁用（schedule.enabled=False），跳过启动")
            return

        if self._task is not None:
            logger.warning("调度器已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"巩固调度器已启动，休眠时间 {settings.schedule.sleep_time} ~ {settings.schedule.wake_time}"
        )

    def stop(self):
        """停止调度器。"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("巩固调度器已停止")

    async def _run_loop(self):
        """主循环：每 CHECK_INTERVAL 秒检查一次。"""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器异常: {e}", exc_info=True)

            await asyncio.sleep(self.CHECK_INTERVAL)

    async def _tick(self):
        """每次检查的逻辑。"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 新的一天，重置状态
        if self._current_date != today:
            if self._state != SchedulerState.IDLE:
                logger.info(f"新的一天 {today}，重置调度状态")
            self._current_date = today
            if self._state == SchedulerState.DONE:
                self._state = SchedulerState.IDLE

        in_sleep = self._is_sleep_time(now)

        if not in_sleep:
            # 不在休眠时间，确保状态已重置
            if self._state not in (SchedulerState.IDLE, SchedulerState.DONE):
                logger.info("已过休眠时间，重置调度状态")
                self._state = SchedulerState.IDLE
            return

        # 在休眠时间内，按状态机执行
        if self._state == SchedulerState.IDLE:
            await self._run_incremental(now)

        elif self._state == SchedulerState.DONE:
            pass  # 本轮已完成，等待下一天

    async def _run_incremental(self, now: datetime):
        """执行增量巩固。"""
        logger.info("开始增量巩固...")
        self._state = SchedulerState.INCREMENTAL

        try:
            result = await asyncio.to_thread(self._create_pipeline_and_run, "incremental")
            self._last_incremental_result = result
            self._last_run_time = now.isoformat()
            logger.info("增量巩固完成")

            # 检查剩余时间是否足够全量巩固
            remaining = self._remaining_sleep_seconds(now)
            if remaining > self.MIN_REMAINING_FOR_FULL:
                logger.info(f"剩余休眠时间 {remaining/60:.0f} 分钟，开始全量巩固")
                await self._run_full(now)
            else:
                logger.info(f"剩余休眠时间 {remaining/60:.0f} 分钟，不足 30 分钟，跳过全量巩固")
                self._state = SchedulerState.DONE

        except Exception as e:
            logger.error(f"增量巩固失败: {e}", exc_info=True)
            self._state = SchedulerState.DONE

    async def _run_full(self, now: datetime):
        """执行全量巩固（带超时保护）。"""
        remaining = self._remaining_sleep_seconds(now)
        timeout = max(remaining - self.TIMEOUT_BUFFER, 60)  # 至少给 60 秒

        logger.info(f"开始全量巩固，超时限制 {timeout/60:.0f} 分钟")
        self._state = SchedulerState.FULL

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._create_pipeline_and_run, "full"),
                timeout=timeout,
            )
            self._last_full_result = result
            logger.info("全量巩固完成")

        except asyncio.TimeoutError:
            logger.warning(f"全量巩固超时（{timeout/60:.0f} 分钟），终止")
        except Exception as e:
            logger.error(f"全量巩固失败: {e}", exc_info=True)

        self._state = SchedulerState.DONE

    def _create_pipeline_and_run(self, mode: str) -> dict:
        """创建 pipeline 并运行（在线程中执行）。"""
        from Memory.consolidator.pipeline import ConsolidationPipeline

        pipeline = ConsolidationPipeline()
        return pipeline.run_consolidation(mode=mode)

    def _is_sleep_time(self, now: datetime) -> bool:
        """判断当前是否在休眠时间段内。"""
        try:
            sleep = self._parse_time(settings.schedule.sleep_time)
            wake = self._parse_time(settings.schedule.wake_time)
        except (ValueError, TypeError) as e:
            logger.warning(f"作息时间配置无效: {e}")
            return False

        current_time = now.time()

        if sleep < wake:
            # 正常区间，如 02:00 ~ 08:00
            return sleep <= current_time < wake
        else:
            # 跨午夜，如 23:00 ~ 06:00
            return current_time >= sleep or current_time < wake

    def _remaining_sleep_seconds(self, now: datetime) -> float:
        """计算距起床时间的剩余秒数。"""
        try:
            wake = self._parse_time(settings.schedule.wake_time)
        except (ValueError, TypeError):
            return 0

        wake_dt = datetime.combine(now.date(), wake)
        if wake_dt <= now:
            wake_dt += timedelta(days=1)

        return (wake_dt - now).total_seconds()

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """解析 HH:MM 格式的时间字符串。"""
        parts = time_str.strip().split(":")
        return time(int(parts[0]), int(parts[1]))

    @staticmethod
    def _summarize_result(result: Optional[dict]) -> Optional[dict]:
        """精简结果供 API 返回。"""
        if result is None:
            return None
        # 只保留各阶段的 status，避免返回大量数据
        summary = {}
        for key in ("phase1", "phase2", "phase3", "profile_update"):
            val = result.get(key)
            if isinstance(val, dict) and "status" in val:
                summary[key] = {"status": val["status"]}
            elif val is not None:
                summary[key] = str(val)[:200]
        return summary


# 全局调度器实例
consolidation_scheduler = ConsolidationScheduler()
