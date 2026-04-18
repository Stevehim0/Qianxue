"""MemoryAPI统一接口模块。

提供记忆系统的Facade接口，隐藏内部复杂性。
"""

import logging
import time
from typing import Dict, Any, List, Optional

import requests

from Memory.config.settings import settings
from Memory.api.exceptions import (
    MemoryAPIError,
    InputError,
    RecallError,
    ConsolidationError,
    StateError,
    CoreError,
)

logger = logging.getLogger(__name__)


class MemoryAPI:
    """记忆系统统一接口 (Facade Pattern)。

    封装写入层、巩固层、召回层、状态层、核心层的所有功能。
    提供简洁的 API，隐藏内部复杂性。

    Examples:
        >>> api = MemoryAPI()  # 自动初始化
        >>> exp_id = api.receive_event(role="user", content="今天天气真好")
        >>> recalls = api.check_recall(query="天气", context={...})
    """

    def __init__(self):
        """自动初始化所有层。

        从 settings 加载配置，初始化数据库连接、向量库、LLM 客户端等。
        """
        # 初始化配置
        self.config = settings

        # 初始化各层组件（使用全局实例，依赖单例模式）
        from Memory.writer.pipeline import WriterPipeline
        from Memory.recall.manager import RecallManager
        from Memory.recall.profile_manager import ProfileManager
        from Memory.consolidator.pipeline import ConsolidationPipeline
        from Memory.state.manager import DefaultStateManager
        from Memory.storage.experience_store import experience_store
        from Memory.storage.entity_store import entity_store
        from Memory.storage.experience_edge_store import experience_edge_store
        from Memory.storage.cross_edge_store import cross_edge_store
        from Memory.storage.profile_store import profile_store
        from Memory.embedding import embedding_service
        from Memory.embedding.vector_store import vector_store
        from Memory.llm import LLMFactory

        # 创建 ProfileManager（个人档案管理器，先于 Pipeline 创建）
        self.profile_manager = ProfileManager(
            profile_store=profile_store,
            experience_store=experience_store,
            entity_store=entity_store,
        )

        # 先加载稳定层文本（后续组件需要）
        self._backend_url = settings.dream.backend_url
        self._stable_text: str = ""
        self._load_stable_text()

        # 创建 Pipeline 实例，注入 ProfileManager 和稳定层
        self.writer_pipeline = WriterPipeline(
            profile_manager=self.profile_manager,
            stable_text=self._stable_text,
        )

        # ConsolidationPipeline 注入 ProfileManager 和稳定层
        self.consolidation_pipeline = ConsolidationPipeline(
            profile_manager=self.profile_manager,
            stable_text=self._stable_text,
        )
        self.state_manager = DefaultStateManager()

        # 创建 RecallManager（注入 ProfileManager 和 LLM client）
        # 根据配置创建 LLM 客户端
        provider = settings.models.llm_provider or "qianwen"
        llm_kwargs = {}
        if provider == "openai_compatible" and settings.models.llm_base_url:
            llm_kwargs["base_url"] = settings.models.llm_base_url
            if settings.models.llm_model:
                llm_kwargs["model"] = settings.models.llm_model
        self._llm_client = LLMFactory.create_client(provider=provider, **llm_kwargs)
        self.recall_manager = RecallManager(
            experience_store=experience_store,
            entity_store=entity_store,
            edge_store=experience_edge_store,
            vector_store=vector_store,
            embedding_service=embedding_service,
            llm_client=self._llm_client,
            profile_manager=self.profile_manager,
            stable_text=self._stable_text,
        )

        # 创建 BufferManager（缓冲写入管理器）
        from Memory.writer.buffer_manager import BufferManager
        self.buffer_manager = BufferManager(
            writer_pipeline=self.writer_pipeline,
            llm_client=self._llm_client,
            config=settings.buffer,
        )

        # 创建状态更新器
        from Memory.state.updater import DefaultStateUpdater
        self.state_updater = DefaultStateUpdater(
            llm_client=self._llm_client,
            stable_text=self._stable_text,
        )

        logger.info("MemoryAPI initialized successfully")

    @property
    def stable_text(self) -> str:
        """获取缓存的稳定层文本。"""
        return self._stable_text

    def _load_stable_text(self) -> None:
        """从 Backend 加载稳定层文本并缓存。"""
        try:
            core = self.load_core()
            self._stable_text = core.get("stable_text", "")
            if self._stable_text:
                logger.info(f"稳定层已缓存 ({len(self._stable_text)} 字)")
            else:
                logger.warning("稳定层为空")
        except Exception as e:
            logger.warning(f"稳定层加载失败，将使用空文本: {e}")
            self._stable_text = ""

    def receive_event(
        self,
        dialogue: Optional[str] = None,
        role: Optional[str] = None,
        content: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """接收原始事件并记录到记忆系统。

        支持两种模式：
        1. 缓冲模式（新）：提供 source_type + source_id + messages，消息先缓冲，达阈值后判断话题边界
        2. 立即模式（旧）：提供 dialogue 或 role+content，立即处理

        Args:
            dialogue: 长对话格式（多行字符串，每行标注说话者，如"张三：内容"）
            role: 角色 (user/assistant/system) - 向后兼容参数
            content: 事件内容 - 向后兼容参数
            source_type: 来源类型（如 "qq_group", "qq_private"）
            source_id: 来源标识（如群号、用户ID）
            messages: 消息列表，每项包含 speaker, content, role, timestamp
            **kwargs: 可选上下文参数

        Returns:
            结果字典:
            - 缓冲模式: {"buffered": True, "count": N, "check_triggered": bool, "success": True}
            - 立即模式: {"buffered": False, "experience_id": "exp_...", "success": True}

        Raises:
            InputError: 输入参数无效或冲突
        """
        # 路径1：缓冲模式
        if source_type and source_id:
            return self._receive_buffered_event(
                source_type, source_id, messages, **kwargs
            )

        # 路径2：立即模式（旧逻辑，向后兼容）
        return self._receive_immediate_event(
            dialogue=dialogue, role=role, content=content, **kwargs
        )

    def _receive_buffered_event(
        self,
        source_type: str,
        source_id: str,
        messages: Optional[List[dict]],
        **kwargs
    ) -> Dict[str, Any]:
        """缓冲模式：将消息追加到对应来源的缓冲区。"""
        if not messages:
            # 单条消息通过 kwargs 传入（兼容单条调用）
            # 不做任何处理，返回空结果
            return {"buffered": True, "count": 0, "check_triggered": False, "success": True}

        for msg in messages:
            self.buffer_manager.append(
                source_type=source_type,
                source_id=source_id,
                speaker=msg.get("speaker", "未知"),
                content=msg.get("content", ""),
                role=msg.get("role", "user"),
                timestamp=msg.get("timestamp"),
            )

        # 返回最后一条消息追加后的缓冲区状态
        buffer = self.buffer_manager._buffers.get((source_type, source_id))
        count = buffer.count if buffer else 0

        return {
            "buffered": True,
            "count": count,
            "check_triggered": count >= settings.buffer.initial_threshold,
            "success": True,
        }

    def _receive_immediate_event(
        self,
        dialogue: Optional[str] = None,
        role: Optional[str] = None,
        content: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """立即模式：直接处理事件（旧逻辑，向后兼容）。"""
        # 参数验证
        if dialogue is not None and (role is not None or content is not None):
            raise InputError("Cannot provide both 'dialogue' and 'role/content' parameters")

        # 处理新格式：dialogue参数
        if dialogue is not None:
            if not isinstance(dialogue, str):
                raise InputError("dialogue must be a string")
            if not dialogue.strip():
                raise InputError("dialogue cannot be empty")
            dialogue_text = dialogue

        # 处理旧格式：role+content参数（向后兼容）
        elif role is not None and content is not None:
            if not role or not isinstance(role, str):
                raise InputError("role must be a non-empty string")
            if not content or not isinstance(content, str):
                raise InputError("content must be a non-empty string")

            # 自动转换为dialogue格式
            role_label = "用户" if role == "user" else "AI" if role == "assistant" else role
            dialogue_text = f"{role_label}：{content}"

        else:
            raise InputError("Must provide either 'dialogue' or 'role+content' parameters")

        try:
            # 过滤掉writer_pipeline不认识的参数
            pipeline_kwargs = {k: v for k, v in kwargs.items()
                               if k in ('timestamp',)}
            exp_id = self.writer_pipeline.process_event(dialogue=dialogue_text, **pipeline_kwargs)
            logger.info(f"Event recorded (immediate): {exp_id}")
            return {"buffered": False, "experience_id": exp_id, "success": True}
        except ValueError as e:
            raise InputError(f"Invalid input: {e}") from e
        except Exception as e:
            raise MemoryAPIError(f"Failed to record event: {e}") from e

    def recall_by_keywords(self, query: str, context: dict) -> dict:
        """通过关键词召回，返回含 briefing 的结果。

        跳过触发检测和关键词提取，直接将 query 按空格/逗号切分为关键词列表，
        交给 RecallManager.recall_by_keywords() 执行双轨召回。

        Args:
            query: 关键词字符串（空格或逗号分隔）
            context: 上下文字典 (recent_history, ai_state, current_time)

        Returns:
            {"experiences": [], "entities": [], "briefing": str|None}

        Raises:
            InputError: 输入参数无效
            RecallError: 召回操作失败
        """
        if not query or not isinstance(query, str):
            raise InputError("query must be a non-empty string")
        if not context or not isinstance(context, dict):
            raise InputError("context must be a dictionary")

        # 按空格/逗号/中文逗号切分，过滤空串
        import re
        keywords = [k.strip() for k in re.split(r"[,，\s]+", query) if k.strip()]

        if not keywords:
            return {"experiences": [], "entities": [], "briefing": None}

        logger.info(f"[Recall] query received: {query} → keywords: {keywords}")

        try:
            result = self.recall_manager.recall_by_keywords(keywords, context)
            exp_count = len(result.get("experiences", []))
            ent_count = len(result.get("entities", []))
            briefing = result.get("briefing")
            logger.info(
                f"[Recall] result: {exp_count} experiences, {ent_count} entities, "
                f"briefing: {briefing}"
            )
            return result
        except Exception as e:
            raise RecallError(f"Recall by keywords failed: {e}") from e

    def check_recall(self, query: str, context: dict) -> List[Any]:
        """检查是否需要召回，触发则返回召回结果。

        Args:
            query: 用户查询文本
            context: 上下文字典 (recent_history, ai_state, current_time)

        Returns:
            召回结果列表，按激活分数降序排序

        Raises:
            InputError: 输入参数无效
            RecallError: 召回操作失败
        """
        if not query or not isinstance(query, str):
            raise InputError("query must be a non-empty string")
        if not context or not isinstance(context, dict):
            raise InputError("context must be a dictionary")

        try:
            recalls = self.recall_manager.recall(query=query, context=context)
            logger.info(f"Recall returned {len(recalls)} results")
            return recalls
        except Exception as e:
            raise RecallError(f"Recall failed: {e}") from e

    def expand_depth(self, experience_id: str) -> Dict[str, str]:
        """按需展开体验节点的深层内容。

        Args:
            experience_id: 体验节点 ID

        Returns:
            包含 L0/L1/L2/L3 的字典，如果某层不存在则为 None

        Raises:
            InputError: 输入参数无效或节点不存在
        """
        if not experience_id or not isinstance(experience_id, str):
            raise InputError("experience_id must be a non-empty string")

        from Memory.storage.experience_store import experience_store

        try:
            exp = experience_store.get_by_id(experience_id)
            if not exp:
                raise InputError(f"Experience {experience_id} not found")

            return {
                "L0": exp.L0_summary,
                "L1": exp.L1_summary,
                "L2": exp.L2_summary,
                "L3": exp.raw_content,  # L3 原始内容
            }
        except InputError:
            raise
        except Exception as e:
            raise RecallError(f"Failed to expand depth: {e}") from e

    def load_core(self) -> Dict[str, Any]:
        """加载核心层人设。

        通过 HTTP 从 Backend 主系统获取最新的核心层数据。
        Backend 是核心层的唯一数据源（backend/services/core/identity.md）。

        Returns:
            包含核心层信息的字典：
            - invariant_text: 不变层文本
            - stable_text: 稳定层文本
            - malleable_text: 可塑层 YAML 文本
            - identity_text: 完整人设文本（向后兼容）
            - anchors: 锚点字典
        """
        try:
            resp = requests.get(
                f"{self._backend_url}/api/core/identity",
                timeout=10,
            )
            if resp.status_code != 200:
                raise CoreError(f"Backend returned {resp.status_code}")

            data = resp.json()
            stable_text = data.get("stable_text", "")
            malleable_text = data.get("malleable_yaml", "")

            return {
                "invariant_text": "",
                "stable_text": stable_text,
                "malleable_text": malleable_text,
                "identity_text": f"{stable_text}\n\n{malleable_text}".strip(),
                "anchors": None,
            }
        except requests.ConnectionError:
            logger.warning("Backend 不可达，返回空核心层")
            return {
                "invariant_text": "",
                "stable_text": "",
                "malleable_text": "",
                "identity_text": "",
                "anchors": None,
            }
        except Exception as e:
            raise CoreError(f"Failed to load core from Backend: {e}") from e

    def check_filter(self, request: str) -> Dict[str, Any]:
        """执行核心层阀门过滤。

        通过主系统 API 检查请求是否违反底线。

        Args:
            request: 用户请求文本

        Returns:
            包含过滤结果的字典：
            - passed: 是否通过过滤
            - reason: 未通过的原因 (如果 passed=True 则为 None)
        """
        if not request or not isinstance(request, str):
            raise InputError("request must be a non-empty string")

        try:
            # 阀门过滤已移至主系统，Memory 本地不做过滤
            return {"passed": True, "reason": None}
        except Exception as e:
            raise CoreError(f"Filter check failed: {e}") from e

    def get_state_prompt(self) -> str:
        """获取当前状态的 prompt 注入文本。

        Returns:
            格式化的状态提示文本，包含 mood/energy/focus/confidence
        """
        try:
            return self.state_manager.format_state_prompt()
        except Exception as e:
            raise StateError(f"Failed to get state prompt: {e}") from e

    def get_mood_label(self) -> str:
        """获取当前情绪标签。

        Returns:
            情绪标签（如"平静"、"愉快"、"低落"等）
        """
        try:
            return self.state_manager.get_mood().label
        except Exception:
            return "平静"

    def load_profile(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """加载指定人的个人档案。

        Args:
            entity_name: 实体名称

        Returns:
            个人档案字典，如果不存在则返回 None
            档案包含：basic, interaction_style, preferences, 元信息
        """
        if not entity_name or not isinstance(entity_name, str):
            raise InputError("entity_name must be a non-empty string")

        try:
            # 使用 ProfileManager 从 person_profiles 表加载完整档案
            profile = self.profile_manager.profile_store.get_by_name(entity_name)
            if not profile:
                return None

            return {
                "basic": profile.basic,
                "interaction_style": profile.interaction_style,
                "preferences": profile.preferences,
                "metadata": {
                    "last_updated": profile.last_updated,
                    "updated_by": profile.updated_by,
                },
            }
        except Exception as e:
            raise RecallError(f"Failed to load profile: {e}") from e

    def ensure_profile(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """确保个人档案存在，不存在则创建（不受 experience 阈值限制）。

        由 Backend 根据对话轮次触发，而非 experience 积累。

        Args:
            entity_name: 实体名称（昵称）

        Returns:
            个人档案字典
        """
        if not entity_name or not isinstance(entity_name, str):
            raise InputError("entity_name must be a non-empty string")

        # 已存在则直接返回
        existing = self.profile_manager.profile_store.get_by_name(entity_name)
        if existing:
            return {
                "basic": existing.basic,
                "interaction_style": existing.interaction_style,
                "preferences": existing.preferences,
                "metadata": {
                    "last_updated": existing.last_updated,
                    "updated_by": existing.updated_by,
                },
            }

        # 不存在，检查实体是否存在
        entity = self.profile_manager.entity_store.get_by_name(entity_name)
        if not entity:
            logger.info(f"ensure_profile: 实体 {entity_name} 不存在，跳过")
            return None

        # 创建档案
        from datetime import datetime
        from Memory.storage.profile_store import PersonProfile

        profile = PersonProfile(
            id=f"profile_{entity_name}",
            memory_index=entity.id,
            basic={
                "name": entity_name,
                "type": entity.type,
                "first_met": datetime.now().isoformat(),
                "relation_to_self": entity.properties.get("relation_to_self", "unknown"),
                "notes": f"由对话轮次触发创建",
            },
            interaction_style={
                "warmth": 0.5,
                "formality": 0.5,
                "humor": 0.5,
                "proactivity": 0.5,
                "directness": 0.5,
                "boundaries": 0.5,
            },
            preferences={},
            last_updated=datetime.now().isoformat(),
            updated_by="conversation_turns",
        )
        self.profile_manager.profile_store.create(profile)
        logger.info(f"ensure_profile: 已创建 {entity_name} 的档案")

        return {
            "basic": profile.basic,
            "interaction_style": profile.interaction_style,
            "preferences": profile.preferences,
            "metadata": {
                "last_updated": profile.last_updated,
                "updated_by": profile.updated_by,
            },
        }

    def run_consolidation(self, mode: str = "incremental") -> Dict[str, Any]:
        """手动触发一次巩固处理。

        Args:
            mode: 巩固模式 ("incremental" 或 "full")

        Returns:
            包含巩固结果的字典：
            - processed_count: 处理的节点数
            - mode: 使用的模式
            - duration: 处理时长（秒）

        Raises:
            InputError: 模式参数无效
            ConsolidationError: 巩固处理失败
        """
        if mode not in ["incremental", "full"]:
            raise InputError("mode must be 'incremental' or 'full'")

        import time

        start_time = time.time()

        try:
            # 调用 ConsolidationPipeline
            results = self.consolidation_pipeline.run_consolidation(mode=mode)

            duration = time.time() - start_time

            return {
                "processed_count": len(results.get("processed", [])),
                "mode": mode,
                "duration": duration,
            }
        except Exception as e:
            raise ConsolidationError(f"Consolidation failed: {e}") from e

    def trigger_state_update(self) -> Dict[str, Any]:
        """触发定时状态更新。

        由后台定时器每10分钟调用一次。
        有新体验走体验驱动，无新体验走基线回归。

        Returns:
            {"status": "completed"}
        """
        try:
            self.state_updater.trigger_timed_update()
            return {"status": "completed"}
        except Exception as e:
            logger.error(f"Timed state update failed: {e}")
            return {"status": "failed", "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态。

        Returns:
            包含系统统计信息的字典：
            - total_experiences: 总体验节点数
            - consolidated_count: 已巩固的节点数
            - unconsolidated_count: 未巩固的节点数
            - total_entities: 总实体数
            - total_edges: 总边数
            - vector_store_size: 向量存储大小（包含experience和entity数量）
            - last_consolidation: 最后巩固时间
            - database_path: 数据库路径
            - system_health: 系统健康状态
        """
        from Memory.storage.experience_store import experience_store
        from Memory.storage.entity_store import entity_store
        from Memory.storage.experience_edge_store import experience_edge_store
        from Memory.embedding.vector_store import vector_store

        experiences = experience_store.get_all()
        entities = entity_store.get_all()
        edges = experience_edge_store.get_all()

        # 统计已巩固和未巩固的数量
        consolidated_count = sum(1 for exp in experiences if exp.consolidated)
        unconsolidated_count = len(experiences) - consolidated_count

        # 获取向量存储大小
        vector_stats = vector_store.get_collection_stats()
        vector_store_size = vector_stats["experience_count"] + vector_stats["entity_count"]

        # 简单的健康检查
        system_health = "healthy"
        if unconsolidated_count > 100:
            system_health = "warning: too many unconsolidated experiences"
        if len(experiences) == 0:
            system_health = "empty"

        return {
            "total_experiences": len(experiences),
            "consolidated_count": consolidated_count,
            "unconsolidated_count": unconsolidated_count,
            "total_entities": len(entities),
            "total_edges": len(edges),
            "vector_store_size": vector_store_size,
            "last_consolidation": None,  # 后续可从配置表读取
            "database_path": str(settings.database.db_path),
            "system_health": system_health,
        }
