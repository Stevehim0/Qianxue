"""缓冲管理器。

协调消息缓冲、话题边界判断和写入流水线的核心组件。
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from Memory.config.settings import settings
from Memory.writer.buffer import BufferedMessage, MessageBuffer, SourceKey
from Memory.writer.topic_judge import TopicJudge

logger = logging.getLogger(__name__)

# 缓冲专用日志 —— 独立文件，方便调试缓冲行为
_buffer_logger = logging.getLogger("Memory.writer.buffer")
_buffer_logger.setLevel(logging.DEBUG)


def _setup_buffer_logger():
    """初始化缓冲日志的 FileHandler（只在首次调用时生效）。"""
    if _buffer_logger.handlers:
        return
    log_path = Path(__file__).parent.parent / "logs" / "buffer.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S")
    )
    _buffer_logger.addHandler(handler)


class BufferManager:
    """消息缓冲管理器。

    负责：
    1. 为每个消息来源维护独立的 MessageBuffer
    2. 消息到达阈值时触发话题边界判断（后台线程，不阻塞调用方）
    3. 话题结束后将消息排空并交给 WriterPipeline 处理
    4. 写入前进行对话质量检查，过滤无价值对话
    5. 后台超时检查，强制写入长时间无新消息的缓冲区

    线程安全：
    - 每个 SourceKey 有独立的 MessageBuffer 和 processing_lock
    - 全局 _buffers_lock 仅在创建/查找缓冲区时短暂持有
    - append() 调用立即返回，话题判断在后台线程中执行

    Examples:
        >>> manager = BufferManager(writer_pipeline, llm_client, buffer_config)
        >>> manager.start_timeout_checker()
        >>> result = manager.append("qq_group", "12345", "张三", "你好", "user")
    """

    def __init__(self, writer_pipeline, llm_client, config):
        """初始化缓冲管理器。

        Args:
            writer_pipeline: WriterPipeline 实例
            llm_client: LLM 客户端实例
            config: BufferConfig 实例
        """
        self._buffers: Dict[SourceKey, MessageBuffer] = {}
        self._buffers_lock = threading.Lock()
        self._processing_locks: Dict[SourceKey, threading.Lock] = {}
        self._writer_pipeline = writer_pipeline
        self._topic_judge = TopicJudge(llm_client)
        self._llm_client = llm_client
        self._config = config

        # 超时检查器相关
        self._stop_event = threading.Event()
        self._checker_thread: Optional[threading.Thread] = None

        # 质量检查 prompt（延迟加载）
        self._quality_prompt_template: Optional[str] = None

        # 初始化缓冲专用日志
        _setup_buffer_logger()
        _buffer_logger.info("=" * 50)
        _buffer_logger.info("BufferManager 初始化 | 阈值=%d | 步长=%d | 超时=%.1fmin",
                            config.initial_threshold, config.threshold_step, config.timeout_minutes)

    def append(
        self,
        source_type: str,
        source_id: str,
        speaker: str,
        content: str,
        role: str,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """追加消息到对应来源的缓冲区。

        此方法立即返回，不阻塞在 LLM 调用上。
        当缓冲区达到阈值时，话题判断在后台线程中执行。

        Args:
            source_type: 来源类型（如 "qq_group", "qq_private"）
            source_id: 来源标识（如群号、用户ID）
            speaker: 说话者名称
            content: 消息内容
            role: 角色 ("user" 或 "assistant")
            timestamp: 消息时间戳（可选，默认为当前时间）

        Returns:
            状态字典: {"buffered": True, "count": N, "check_triggered": bool}
        """
        if timestamp is None:
            timestamp = time.time()

        source_key = (source_type, source_id)
        message = BufferedMessage(
            speaker=speaker,
            content=content,
            timestamp=timestamp,
            role=role,
        )

        buffer = self._get_or_create_buffer(source_key)
        should_check, count = buffer.append(message)

        # 缓冲日志：记录本次追加 + 所有缓冲区状态
        _buffer_logger.info(
            "收到消息 | %s:%s | %s: %s | 本缓冲区: %d条 | 阈值: %d",
            source_type, source_id, speaker,
            content[:40].replace('\n', ' ') + ("..." if len(content) > 40 else ""),
            count, buffer.next_threshold,
        )
        if should_check:
            _buffer_logger.info(">>> 触发话题判断 | %s:%s | %d条 >= 阈值%d",
                                source_type, source_id, count, buffer.next_threshold)

        # 每10条或首次/触发时打印全量缓冲区概览
        if should_check or count <= 2 or count % 10 == 0:
            self._log_all_buffers()

        check_triggered = False
        if should_check:
            check_triggered = self._dispatch_topic_check(source_key)

        return {
            "buffered": True,
            "count": count,
            "check_triggered": check_triggered,
        }

    def start_timeout_checker(self):
        """启动后台超时检查线程。"""
        if self._checker_thread is not None and self._checker_thread.is_alive():
            return
        self._stop_event.clear()
        self._checker_thread = threading.Thread(
            target=self._timeout_checker_loop,
            daemon=True,
            name="buffer-timeout-checker",
        )
        self._checker_thread.start()
        _buffer_logger.info("超时检查器启动 | 轮询间隔: %.0fs", self._config.check_interval_seconds)

    def stop_timeout_checker(self):
        """停止后台超时检查线程。"""
        self._stop_event.set()
        if self._checker_thread is not None:
            self._checker_thread.join(timeout=5)
            self._checker_thread = None
        _buffer_logger.info("超时检查器停止")

    def check_timeouts(self):
        """检查所有缓冲区的超时状态，强制写入超时的缓冲区。

        可手动调用，也会被后台线程定期调用。
        """
        with self._buffers_lock:
            source_keys = list(self._buffers.keys())

        for key in source_keys:
            try:
                buffer = self._buffers.get(key)
                if buffer is None:
                    continue

                timeout_seconds = self._config.timeout_minutes * 60
                if buffer.seconds_since_last_append() > timeout_seconds:
                    # 获取处理锁，避免与话题检查冲突
                    proc_lock = self._get_or_create_processing_lock(key)
                    if proc_lock.acquire(timeout=1.0):
                        try:
                            messages = buffer.drain_all()
                            if messages:
                                _buffer_logger.info(
                                    "超时写入 | %s:%s | %d条 | 空闲%.0fs",
                                    key[0], key[1], len(messages),
                                    buffer.seconds_since_last_append(),
                                )
                                self._flush_to_pipeline(key, messages)
                                self._log_all_buffers()
                        finally:
                            proc_lock.release()
            except Exception as e:
                logger.warning(f"Error checking timeout for {key}: {e}")

    # ==================== 内部方法 ====================

    def _get_or_create_buffer(self, source_key: SourceKey) -> MessageBuffer:
        """获取或创建指定来源的缓冲区。线程安全。"""
        # 快速路径：已存在
        buffer = self._buffers.get(source_key)
        if buffer is not None:
            return buffer

        with self._buffers_lock:
            # 双重检查
            buffer = self._buffers.get(source_key)
            if buffer is not None:
                return buffer
            buffer = MessageBuffer(
                source_type=source_key[0],
                source_id=source_key[1],
                config=self._config,
            )
            self._buffers[source_key] = buffer
            return buffer

    def _get_or_create_processing_lock(self, source_key: SourceKey) -> threading.Lock:
        """获取或创建指定来源的处理锁。"""
        lock = self._processing_locks.get(source_key)
        if lock is not None:
            return lock
        with self._buffers_lock:
            lock = self._processing_locks.get(source_key)
            if lock is None:
                lock = threading.Lock()
                self._processing_locks[source_key] = lock
            return lock

    def _dispatch_topic_check(self, source_key: SourceKey) -> bool:
        """将话题检查调度到后台线程。

        如果该来源正在处理中（processing_lock 被持有），则跳过。

        Returns:
            是否成功调度了后台检查
        """
        proc_lock = self._get_or_create_processing_lock(source_key)

        # 非阻塞尝试获取锁，如果正在处理则跳过
        if not proc_lock.acquire(blocking=False):
            logger.debug(f"Topic check already in progress for {source_key}, skipping")
            return False

        # 启动后台线程执行话题检查
        def _run():
            try:
                self._try_topic_check(source_key)
            finally:
                proc_lock.release()

        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=f"topic-check-{source_key[0]}-{source_key[1]}",
        )
        thread.start()
        return True

    def _try_topic_check(self, source_key: SourceKey):
        """执行话题边界判断，如果找到边界则排空并写入。

        此方法在后台线程中调用，已持有 processing_lock。

        Args:
            source_key: 来源标识
        """
        buffer = self._buffers.get(source_key)
        if buffer is None:
            return

        messages = buffer.get_messages()
        if not messages:
            return

        # 调用话题判断
        result = self._topic_judge.judge(messages)

        if result.has_boundary:
            # 话题在 boundary_position 处结束，取出前 N 条
            drained = buffer.drain_up_to(result.boundary_position)
            if drained:
                _buffer_logger.info(
                    "话题边界 | %s:%s | 边界在%d/%d | 写入%d条 | 剩余%d条",
                    source_key[0], source_key[1],
                    result.boundary_position, len(messages),
                    len(drained), len(messages) - result.boundary_position,
                )
                self._flush_to_pipeline(source_key, drained)
                self._log_all_buffers()
        else:
            # 未找到边界，推进阈值继续积累
            new_threshold = buffer.advance_threshold()
            _buffer_logger.info(
                "未找到边界 | %s:%s | %d条继续缓冲 | 下一阈值→%d",
                source_key[0], source_key[1], len(messages), new_threshold,
            )

    def _flush_to_pipeline(self, source_key: SourceKey, messages: List[BufferedMessage]):
        """将缓冲消息格式化为 dialogue 字符串并交给 WriterPipeline 处理。

        写入前进行对话质量检查，过滤无价值的对话。

        Args:
            source_key: 来源标识
            messages: 要写入的消息列表
        """
        if not messages:
            return

        dialogue = self._format_dialogue(messages)

        # 质量检查：判断对话是否值得记住
        if not self._check_quality(dialogue):
            _buffer_logger.info(
                "质量过滤 | %s:%s | %d条被过滤（无记忆价值）",
                source_key[0], source_key[1], len(messages),
            )
            logger.info(
                "质量过滤 | %s:%s | %d条对话被过滤，不写入记忆",
                source_key[0], source_key[1], len(messages),
            )
            return

        try:
            # 使用第一条消息的时间戳作为体验时间
            timestamp = messages[0].timestamp
            exp_id = self._writer_pipeline.process_event(
                dialogue=dialogue,
                timestamp=timestamp,
            )
            _buffer_logger.info(
                "写入完成 | %s:%s | %d条 → %s",
                source_key[0], source_key[1], len(messages), exp_id,
            )
        except Exception as e:
            _buffer_logger.error(
                "写入失败 | %s:%s | %d条 | 错误: %s",
                source_key[0], source_key[1], len(messages), e,
            )
            # 写入失败不重试，消息丢失（可接受，与设计一致）

    def _check_quality(self, dialogue: str) -> bool:
        """用 LLM 判断对话是否值得记住。

        Args:
            dialogue: 格式化的对话文本

        Returns:
            True 表示值得记住，False 表示应过滤
        """
        try:
            logger.info("质量检查: 开始判断对话是否值得记住...")
            template = self._load_quality_prompt()
            prompt = template.format(dialogue=dialogue, bot_name=settings.writer.bot_name)

            response = self._llm_client.call_with_retry(
                prompt=prompt,
                response_format="json",
                temperature=0.2,
                max_tokens=200,
            )

            from Memory.llm.utils import parse_json
            if isinstance(response, dict):
                data = response
            else:
                data = parse_json(response)

            if not isinstance(data, dict):
                # 解析失败，默认保留
                logger.warning("质量检查: LLM返回格式异常，默认保留")
                return True

            worth = data.get("worth_remembering", True)
            reason = data.get("reason", "")
            if isinstance(worth, str):
                worth = worth.lower() == "true"

            # 提取人物信息，存入 profile_pending_facts
            people = data.get("people", {})
            if people and isinstance(people, dict):
                self._save_pending_facts(people)

            if not worth:
                logger.info(f"质量检查: 过滤掉无价值对话 | 原因: {reason}")
                return False

            logger.info(f"质量检查: 通过，值得记住 | 原因: {reason}")
            return True

        except Exception as e:
            # 质量检查失败时默认保留，宁可多记也不丢记忆
            logger.warning(f"质量检查失败，默认保留: {e}")
            return True

    def _save_pending_facts(self, people: dict):
        """将质量检查中提取的人物信息存入 profile_pending_facts 表。"""
        try:
            from Memory.storage.database import db_manager
            from datetime import datetime

            now = datetime.now().isoformat()
            bot_name = settings.writer.bot_name
            with db_manager.transaction() as cursor:
                for name, fact in people.items():
                    if not name or not fact or not isinstance(fact, str):
                        continue
                    if name == bot_name:
                        continue
                    cursor.execute(
                        "INSERT INTO profile_pending_facts (entity_name, fact_text, source_type, created_at) VALUES (?, ?, ?, ?)",
                        (name, fact, "quality_check", now),
                    )
                logger.info(f"已保存 {len(people)} 条人物信息到 pending_facts")
        except Exception as e:
            logger.warning(f"保存 pending_facts 失败: {e}")

    def _load_quality_prompt(self) -> str:
        """延迟加载质量检查 prompt 模板。"""
        if self._quality_prompt_template is None:
            prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "write_quality_check.txt"
            if prompt_path.exists():
                self._quality_prompt_template = prompt_path.read_text(encoding="utf-8")
            else:
                raise FileNotFoundError(f"Quality check prompt not found: {prompt_path}")
        return self._quality_prompt_template

    def _format_dialogue(self, messages: List[BufferedMessage]) -> str:
        """将消息列表格式化为 dialogue 字符串。

        格式: "speaker：content\\nspeaker：content\\n..."

        Args:
            messages: 消息列表

        Returns:
            多行对话字符串
        """
        return "\n".join(msg.to_dialogue_line() for msg in messages)

    _pending_facts_counter: int = 0  # 超时检查计数器，用于触发 pending facts 处理

    def _timeout_checker_loop(self):
        """后台超时检查循环。"""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._config.check_interval_seconds)
            if self._stop_event.is_set():
                break
            try:
                self.check_timeouts()
                # 每 20 次检查（约 10 分钟）处理一次 pending facts
                BufferManager._pending_facts_counter += 1
                if BufferManager._pending_facts_counter >= 20:
                    BufferManager._pending_facts_counter = 0
                    self._process_pending_facts()
            except Exception as e:
                logger.error(f"Error in timeout checker: {e}")

    def _process_pending_facts(self):
        """定时处理积累的 pending facts，更新个人档案。"""
        try:
            if hasattr(self, '_writer_pipeline') and self._writer_pipeline.profile_manager:
                self._writer_pipeline.profile_manager.process_pending_facts(threshold=5)
        except Exception as e:
            logger.warning(f"处理 pending facts 失败: {e}")

    def _log_all_buffers(self):
        """打印所有缓冲区的当前状态概览。"""
        with self._buffers_lock:
            keys = list(self._buffers.keys())

        if not keys:
            _buffer_logger.debug("缓冲区概览 | (空)")
            return

        lines = ["缓冲区概览"]
        for key in keys:
            buf = self._buffers.get(key)
            if buf is None:
                continue
            idle = buf.seconds_since_last_append()
            lines.append(
                f"  {key[0]}:{key[1]} | {buf.count}条 | 阈值{buf.next_threshold} | "
                f"空闲{idle:.0f}s"
            )
        _buffer_logger.debug("\n".join(lines))
