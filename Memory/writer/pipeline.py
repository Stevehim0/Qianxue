"""写入层并行处理主流程。

协调步骤1原始记录、步骤2三项并行任务、步骤3边创建、步骤4即时状态更新。
"""

import logging
import threading
import time
import json
import uuid
import struct
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from Memory.writer.raw_recorder import RawRecorder, raw_recorder as global_raw_recorder
from Memory.storage.experience_store import ExperienceStore, experience_store as global_experience_store
from Memory.storage.entity_store import EntityStore, entity_store as global_entity_store
from Memory.storage.experience_edge_store import (
    ExperienceEdgeStore,
    ExperienceEdge,
    experience_edge_store as global_experience_edge_store,
)
from Memory.storage.cross_edge_store import CrossEdgeStore, CrossEdge, cross_edge_store as global_cross_edge_store
from Memory.storage.database import db_manager
from Memory.llm.factory import LLMFactory
from Memory.embedding import EmbeddingService, embedding_service as global_embedding_service
from Memory.embedding.vector_store import VectorStore, vector_store as global_vector_store
from Memory.state.manager import DefaultStateManager
from Memory.writer.tasks.emotion_task import EmotionSnapshot
from Memory.writer.tasks.entity_task import recognize_entities_and_create_edges
from Memory.writer.tasks.l0_summary_task import generate_l0_summary
from Memory.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """处理结果数据类（用于任务间传递）"""

    experience_id: str
    l0_summary: Optional[str] = None
    entity_ids: List[str] = None
    emotion_snapshot: Optional[EmotionSnapshot] = None


class WriterPipeline:
    """写入层并行处理主流程。

    步骤1：原始记录（调用RawRecorder）
    步骤2：三项并行任务（L0摘要/实体识别/情感分析）
    步骤3：创建边（时序边+跨层边）
    步骤4：异步触发状态更新（如果需要）

    Examples:
        >>> pipeline = WriterPipeline()
        >>> exp_id = pipeline.process_event(role="user", content="今天天气真好")
        >>> print(exp_id)
        exp_20260331_120000
    """

    # 状态更新触发条件（来自CONTEXT.md）
    EMOTION_INTENSITY_THRESHOLD = 0.8
    STATE_UPDATE_INTERVAL = 60  # 秒

    def __init__(
        self,
        raw_recorder: Optional[RawRecorder] = None,
        llm_client=None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[VectorStore] = None,
        experience_store: Optional[ExperienceStore] = None,
        entity_store: Optional[EntityStore] = None,
        experience_edge_store: Optional[ExperienceEdgeStore] = None,
        cross_edge_store: Optional[CrossEdgeStore] = None,
        state_manager: Optional[DefaultStateManager] = None,
        profile_manager=None,
        stable_text: str = "",
    ):
        """初始化WriterPipeline。

        Args:
            raw_recorder: 原始记录器实例
            llm_client: LLM客户端实例（默认使用LLMFactory创建）
            embedding_service: Embedding服务实例
            vector_store: 向量存储实例
            experience_store: 体验存储实例
            entity_store: 实体存储实例
            experience_edge_store: 体验边存储实例
            cross_edge_store: 跨层边存储实例
            state_manager: 状态管理器实例
            profile_manager: 个人档案管理器实例（可选，用于自动创建档案）
        """
        # 如果参数不为None，使用参数；否则使用全局单例
        self.raw_recorder = raw_recorder if raw_recorder is not None else global_raw_recorder
        self.llm_client = llm_client if llm_client is not None else LLMFactory.create_client()
        self.embedding_service = embedding_service if embedding_service is not None else global_embedding_service
        self.vector_store = vector_store if vector_store is not None else global_vector_store
        self.experience_store = experience_store if experience_store is not None else global_experience_store
        self.entity_store = entity_store if entity_store is not None else global_entity_store
        self.experience_edge_store = experience_edge_store if experience_edge_store is not None else global_experience_edge_store
        self.cross_edge_store = cross_edge_store if cross_edge_store is not None else global_cross_edge_store
        self.state_manager = state_manager if state_manager is not None else DefaultStateManager()
        self.profile_manager = profile_manager
        self.stable_text = stable_text

        # 内部记录上次状态更新时间（使用单调时钟）
        self.last_state_update_time = time.monotonic()

        self.logger = logging.getLogger(__name__)

    def process_event(self, dialogue: str, timestamp: Optional[float] = None) -> str:
        """处理事件的主入口（原子性版本）。

        核心改进：
        1. 延迟写入：所有处理在内存中完成
        2. 原子提交：只有所有步骤成功后才写入数据库
        3. 统一事务：使用一个大的事务包含所有写入操作

        Args:
            dialogue: 长对话格式（多行字符串，每行标注说话者）
            timestamp: 事件时间戳（可选）

        Returns:
            体验节点ID

        Raises:
            Exception: 任何步骤失败时抛出异常，不写入任何数据

        Examples:
            >>> pipeline = WriterPipeline()
            >>> dialogue = "张三：你好\\nAI：你好呀"
            >>> exp_id = pipeline.process_event(dialogue=dialogue)
        """
        if timestamp is None:
            timestamp = time.time()

        # ========== 阶段1：内存处理（无数据库操作）==========
        try:
            self.logger.debug("开始内存处理阶段")

            # 1.1 准备基础数据
            experience_id = self._generate_exp_id(timestamp)
            context_data = self._collect_context(timestamp)

            # 1.2 并行执行三项任务（在内存中）
            l0_summary, l0_embedding, entity_data_list, emotion_snapshot = self._process_in_memory(
                experience_id, dialogue, context_data
            )

            # 1.3 准备跨层边数据
            cross_edges_data = self._prepare_cross_edges(experience_id, entity_data_list)

            self.logger.debug(
                f"内存处理完成 - L0生成, {len(entity_data_list)}个实体, "
                f"情感强度={emotion_snapshot.intensity if emotion_snapshot else 0}"
            )

        except Exception as e:
            self.logger.error(f"内存处理阶段失败: {e}")
            raise  # 内存处理失败，无任何数据库写入

        # ========== 阶段2：原子写入（统一事务）==========
        try:
            result = self._atomic_write(
                experience_id=experience_id,
                dialogue=dialogue,
                timestamp=timestamp,
                l0_summary=l0_summary,
                l0_embedding=l0_embedding,
                entity_data_list=entity_data_list,
                emotion_snapshot=emotion_snapshot,
                cross_edges_data=cross_edges_data,
                context_data=context_data
            )
            self.logger.info(f"原子写入成功: {experience_id}")
        except Exception as e:
            self.logger.error(f"原子写入阶段失败: {e}")
            raise  # 写入失败，保证"全无"

        # ========== 阶段3：档案创建检查（写入成功后）==========
        if self.profile_manager:
            self._check_profile_creation(entity_data_list, context_data)

        return result

    def _check_profile_creation(self, entity_data_list: list, context_data: dict):
        """原子写入成功后，检查 person 类型实体是否需要创建个人档案。

        对每个 person 类型实体调用 ProfileManager.check_and_create_profile()，
        当实体出现 >=3 次且跨 >=3 天时自动创建档案。
        单个实体检查失败不影响其他实体。

        Args:
            entity_data_list: 实体数据列表（来自 _extract_entities_in_memory）
            context_data: 上下文数据（含 created_at）
        """
        from Memory.storage.experience_store import Experience

        for entity_data in entity_data_list:
            if entity_data.get("type") != "person":
                continue

            entity_name = entity_data.get("name")
            if not entity_name:
                continue

            # 跳过 AI 自身（不为被服务的主体建档案）
            if entity_name == settings.writer.bot_name:
                continue

            try:
                # 构建 Experience 对象（check_and_create_profile 需要用于推导初始相处方式）
                experience = Experience(
                    id="",
                    L3_raw="",
                    emotion_category=None,
                    emotion_intensity=None,
                    context_time_of_day=context_data.get("time_of_day"),
                    created_at=context_data.get("created_at", ""),
                )
                self.profile_manager.check_and_create_profile(entity_name, experience)
            except Exception as e:
                self.logger.warning(f"Profile creation check failed for {entity_name}: {e}")

    def _process_in_memory(self, experience_id: str, dialogue: str, context_data: dict) -> tuple:
        """在内存中完成所有处理（无数据库操作）

        这是核心改进：所有LLM调用、向量编码都在内存中完成
        只有全部成功才进入下一阶段

        Args:
            experience_id: 体验节点ID
            dialogue: 对话内容
            context_data: 上下文数据

        Returns:
            (l0_summary, l0_embedding, entity_data_list, emotion_snapshot)

        Raises:
            Exception: 任何任务失败时抛出异常
        """
        with ThreadPoolExecutor() as executor:
            # 提交三项并行任务（内存版本）
            future_l0 = executor.submit(
                self._generate_l0_in_memory,
                experience_id, dialogue
            )
            future_entities = executor.submit(
                self._extract_entities_in_memory,
                experience_id, dialogue
            )
            future_emotion = executor.submit(
                self._analyze_emotion_in_memory,
                experience_id, dialogue, context_data
            )

            # 等待所有任务完成
            try:
                l0_summary, l0_embedding = future_l0.result()
                entity_data_list = future_entities.result()
                emotion_snapshot = future_emotion.result()
            except Exception as e:
                self.logger.error(f"内存并行处理失败: {e}")
                raise

        return l0_summary, l0_embedding, entity_data_list, emotion_snapshot

    def _atomic_write(self, experience_id: str, dialogue: str, timestamp: float, **data) -> str:
        """原子写入：使用统一事务写入所有数据

        核心改进：所有数据库操作在一个事务中完成
        任何步骤失败都会回滚，保证原子性

        Args:
            experience_id: 体验节点ID
            dialogue: 原始对话
            timestamp: 时间戳
            **data: 包含所有要写入的数据

        Returns:
            体验节点ID

        Raises:
            Exception: 任何写入失败时抛出异常，事务回滚
        """
        with db_manager.transaction() as cursor:
            try:
                # 1. 写入体验节点
                cursor.execute("""
                    INSERT INTO experiences (
                        id, L3_raw, L0_text, L0_embedding,
                        emotion_category, emotion_intensity, emotion_valence,
                        emotion_arousal, emotion_target,
                        context_focus, context_mood, context_time_of_day,
                        context_silence_before, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    experience_id,
                    dialogue,
                    data['l0_summary'],
                    data['l0_embedding'],
                    data['emotion_snapshot'].category if data['emotion_snapshot'] else None,
                    data['emotion_snapshot'].intensity if data['emotion_snapshot'] else None,
                    data['emotion_snapshot'].valence if data['emotion_snapshot'] else None,
                    data['emotion_snapshot'].arousal if data['emotion_snapshot'] else None,
                    data['emotion_snapshot'].target if data['emotion_snapshot'] else None,
                    data['context_data']['focus'],
                    data['context_data']['mood'],
                    data['context_data']['time_of_day'],
                    data['context_data']['silence_before'],
                    data['context_data']['created_at']
                ))

                # 2. 写入向量存储（体验节点）
                if data['l0_embedding']:
                    self.vector_store.add_experience(
                        experience_id,
                        self._blob_to_list(data['l0_embedding']),
                        {"L0_text": data['l0_summary']}
                    )

                # 3. 写入实体和跨层边
                entity_ids = []
                for entity_data in data['entity_data_list']:
                    # 检查实体是否已存在（通过名称）
                    cursor.execute("SELECT id FROM entities WHERE name = ?", (entity_data['name'],))
                    existing_entity = cursor.fetchone()

                    if existing_entity:
                        # 实体已存在，使用现有ID
                        existing_entity_id = existing_entity[0]
                        entity_ids.append(existing_entity_id)

                        # 写入跨层边（连接到现有实体）
                        cursor.execute("""
                            INSERT OR IGNORE INTO cross_edges (from_id, to_id, context, weight, created_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            experience_id,
                            existing_entity_id,
                            'contains_information',
                            1.0,
                            data['context_data']['created_at']
                        ))
                    else:
                        # 新实体，写入数据库
                        cursor.execute("""
                            INSERT INTO entities (id, name, type, properties, source, confidence, embedding, emotion_timeline, emotion_current, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            entity_data['id'],
                            entity_data['name'],
                            entity_data['type'],
                            entity_data['properties'],
                            entity_data.get('source', 'entity_recognition'),
                            entity_data.get('confidence', 1.0),
                            entity_data['embedding'],
                            entity_data.get('emotion_timeline'),
                            entity_data.get('emotion_current'),
                            entity_data['created_at'],
                            entity_data['updated_at']
                        ))
                        entity_ids.append(entity_data['id'])

                        # 写入向量存储（实体）
                        if entity_data.get('embedding'):
                            self.vector_store.add_entity(
                                entity_data['id'],
                                self._blob_to_list(entity_data['embedding']),
                                {"name": entity_data['name'], "type": entity_data['type']}
                            )

                        # 写入跨层边
                        cursor.execute("""
                            INSERT OR IGNORE INTO cross_edges (from_id, to_id, context, weight, created_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            experience_id,
                            entity_data['id'],
                            'contains_information',
                            1.0,
                            data['context_data']['created_at']
                        ))

                # 4. 创建时序边
                self._create_temporal_edge_in_transaction(cursor, experience_id, data['context_data']['created_at'])

                # 所有操作成功，事务将自动提交
                self.logger.debug(f"原子事务完成: {experience_id}, {len(entity_ids)}个实体")
                return experience_id

            except Exception as e:
                # 任何错误都会导致回滚
                self.logger.error(f"原子写入失败，事务回滚: {e}")
                raise  # 重新抛出异常，确保事务回滚

    def _create_temporal_edge_in_transaction(self, cursor, experience_id: str, created_at: str):
        """在事务中创建时序边"""
        try:
            cursor.execute(
                """
                SELECT id FROM experiences
                WHERE created_at < (
                    SELECT created_at FROM experiences WHERE id = ?
                )
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (experience_id,),
            )

            row = cursor.fetchone()

            if row:
                last_exp_id = row[0]

                # 创建时序边
                temporal_edge = ExperienceEdge(
                    from_id=experience_id,
                    to_id=last_exp_id,
                    type="temporal",
                    weight=1.0,
                    created_at=created_at,
                )

                self.experience_edge_store.create(temporal_edge)
                self.logger.debug(f"Created temporal edge: {experience_id} -> {last_exp_id}")
            else:
                self.logger.debug(f"No previous experience found for {experience_id}")

        except Exception as e:
            self.logger.warning(f"Failed to create temporal edge for {experience_id}: {e}")
            # 时序边创建失败不影响主流程

    def _generate_l0_in_memory(self, experience_id: str, dialogue: str) -> tuple:
        """在内存中生成L0摘要和向量（不写入数据库）

        Returns:
            (l0_summary_text, l0_embedding_blob)
        """
        from Memory.writer.tasks.l0_summary_task import _load_prompt_template

        # 加载prompt模板（使用原有逻辑）
        prompt_template = _load_prompt_template()
        prompt = prompt_template.format(
            dialogue=dialogue,
            ai_personality=self.stable_text or "无",
            bot_name=settings.writer.bot_name,
        )

        # 调用LLM（使用原有逻辑）
        l0_text = self.llm_client.call_with_retry(
            prompt=prompt,
            response_format="text",  # 返回文本而非JSON
            temperature=0.7,  # 略高温度增加表达多样性
            max_tokens=200,  # 摘要较短，200 token足够
        )
        l0_text = l0_text.strip()

        # 生成embedding（使用原有逻辑）
        embedding_array = self.embedding_service.encode(l0_text)
        l0_embedding_blob = embedding_array.tobytes()

        return l0_text, l0_embedding_blob

    def _extract_entities_in_memory(self, experience_id: str, dialogue: str) -> list:
        """在内存中提取实体（不写入数据库）

        Returns:
            实体数据列表，每个实体包含id, name, type, properties, embedding, created_at, updated_at
        """
        from Memory.writer.tasks.entity_task import _load_prompt_template

        # 构建prompt（使用原有逻辑）
        prompt_template = _load_prompt_template()
        prompt = prompt_template.format(dialogue=dialogue)

        # 调用LLM（使用原有逻辑）
        result_json = self.llm_client.call_with_retry(
            prompt=prompt,
            response_format="json",
            temperature=0.3,  # 低温度保证提取稳定
            max_tokens=2000,  # 增加到2000以支持长对话的多实体识别
        )

        # 解析JSON (处理多种可能的返回格式)
        if isinstance(result_json, dict):
            # Phase 15: {"entities": [...]}
            entity_list = result_json.get("entities", [])
        elif isinstance(result_json, list):
            # 直接返回实体数组
            entity_list = result_json
        elif isinstance(result_json, str):
            # JSON字符串，需要解析
            result = json.loads(result_json)
            if isinstance(result, dict):
                entity_list = result.get("entities", [])
            elif isinstance(result, list):
                entity_list = result
            else:
                entity_list = []
        else:
            self.logger.error(f"Unexpected result type: {type(result_json)}")
            entity_list = []

        # 为每个实体生成embedding（Phase 15格式）
        entity_data_list = []
        bot_name = settings.writer.bot_name
        for entity_item in entity_list:
            entity_id = str(uuid.uuid4())
            # Phase 15实体格式
            entity_name = entity_item.get("name", "")
            entity_type = entity_item.get("type", "other")

            # 跳过 AI 自身的实体（不应为被服务的主体建实体）
            if entity_name == bot_name:
                self.logger.debug(f"Skipping bot self-entity: {entity_name}")
                continue
            entity_attributes = entity_item.get("attributes", {})
            entity_confidence = entity_item.get("confidence", 1.0)

            # 验证entity_type
            valid_types = ["person", "place", "concept", "event", "skill", "other"]
            if entity_type not in valid_types:
                self.logger.warning(f"Invalid entity type '{entity_type}', using 'other'")
                entity_type = "other"

            # 生成embedding（只对实体名称编码）
            if entity_name:
                embedding_array = self.embedding_service.encode(text=entity_name)
                embedding_blob = embedding_array.tobytes()
            else:
                embedding_blob = None

            # 创建时间戳
            now = datetime.now().isoformat()

            # Phase 15: properties只包含业务属性，元数据在表字段
            entity_data_list.append({
                'id': entity_id,
                'name': entity_name,
                'type': entity_type,
                'properties': json.dumps(entity_attributes, ensure_ascii=False),
                'source': 'entity_recognition',  # Phase 15: 元数据在表字段
                'confidence': entity_confidence,  # Phase 15: 元数据在表字段
                'embedding': embedding_blob,
                'emotion_timeline': None,
                'emotion_current': None,
                'created_at': now,
                'updated_at': now
            })

        return entity_data_list

    def _analyze_emotion_in_memory(self, experience_id: str, dialogue: str, context_data: dict) -> Optional[EmotionSnapshot]:
        """在内存中分析情感（不写入数据库）

        Returns:
            EmotionSnapshot对象
        """
        from Memory.writer.tasks.emotion_task import _load_prompt_template

        # 解析mood label
        mood_label = context_data['mood'].split(' ')[0] if context_data['mood'] else 'neutral'
        state_focus = context_data['focus']

        # 构建Prompt（使用原有逻辑）
        prompt_template = _load_prompt_template()
        prompt = prompt_template.format(
            dialogue=dialogue,
            ai_personality=self.stable_text or "无",
            state_focus=state_focus if state_focus else "无",
            state_mood_label=mood_label,
            bot_name=settings.writer.bot_name,
        )

        try:
            # 调用LLM（使用原有逻辑）
            result_json = self.llm_client.call_with_retry(
                prompt=prompt,
                response_format="json",
                temperature=0.3,  # 低温度保证分析稳定
                max_tokens=300,
            )

            # 解析JSON (处理可能的dict返回，使用原有逻辑)
            if isinstance(result_json, dict):
                result = result_json
            else:
                result = json.loads(result_json)

            emotion = EmotionSnapshot(
                category=result.get("category", "neutral"),
                intensity=float(result.get("intensity", 0.5)),
                valence=float(result.get("valence", 0.0)),
                arousal=float(result.get("arousal", 0.3)),
                target=result.get("target"),
            )

            return emotion

        except Exception as e:
            self.logger.warning(f"情感分析失败: {e}")
            return None

    def _collect_context(self, timestamp: float) -> dict:
        """收集上下文数据"""
        mood = self.state_manager.get_mood()
        focus = self.state_manager.get_focus()

        return {
            'mood': f"{mood.label} (valence:{mood.valence}, arousal:{mood.arousal})",
            'focus': focus,
            'time_of_day': self._derive_time_of_day(timestamp),
            'silence_before': str(self._calculate_silence_before(timestamp)),
            'created_at': datetime.fromtimestamp(timestamp).isoformat()
        }

    def _generate_exp_id(self, timestamp: float) -> str:
        """生成体验节点ID（添加微秒和随机数避免冲突）"""
        import random

        dt = datetime.fromtimestamp(timestamp)
        microseconds = int((timestamp % 1) * 1_000_000)
        random_suffix = random.randint(0, 999)

        return f"exp_{dt.year:04d}{dt.month:02d}{dt.day:02d}_{dt.hour:02d}{dt.minute:02d}{dt.second:02d}_{microseconds:06d}_{random_suffix:03d}"

    def _prepare_cross_edges(self, experience_id: str, entity_data_list: list) -> list:
        """准备跨层边数据"""
        cross_edges = []
        for entity_data in entity_data_list:
            cross_edges.append({
                'to_id': entity_data['id'],
                'context': 'contains_information',
                'weight': 1.0
            })
        return cross_edges

    def _derive_time_of_day(self, timestamp: float) -> str:
        """从时间戳推导时段分类"""
        dt = datetime.fromtimestamp(timestamp)
        hour = dt.hour

        if 5 <= hour < 8: return "凌晨"
        elif 8 <= hour < 12: return "上午"
        elif 12 <= hour < 18: return "下午"
        elif 18 <= hour < 22: return "傍晚"
        else: return "深夜"

    def _calculate_silence_before(self, current_timestamp: float) -> int:
        """计算距上一条对话的时间差"""
        with db_manager.transaction() as cursor:
            cursor.execute(
                """
                SELECT created_at FROM experiences
                ORDER BY created_at DESC
                LIMIT 1
            """
            )

            row = cursor.fetchone()

            if row is None:
                return 300  # 默认值

            last_created_at = row[0]
            last_timestamp = datetime.fromisoformat(last_created_at).timestamp()
            silence_seconds = int(current_timestamp - last_timestamp)
            return max(0, silence_seconds)

    def _blob_to_list(self, blob: bytes) -> list:
        """将blob转换为list"""
        if blob is None:
            return []
        import struct
        # 假设是float32数组
        return list(struct.unpack(f'{len(blob)//4}f', blob))

    def _build_entity_prompt(self, dialogue: str) -> str:
        """构建实体识别prompt"""
        return f"""请从以下对话中提取信息实体，以JSON格式返回：

对话内容：
{dialogue}

请返回JSON格式：
{{
    "entities": [
        {{
            "name": "实体名称（完整信息单元）",
            "type": "实体类型（goal/tool_recommendation/basic_concept/data_structure/environment_setup/other）",
            "properties": {{
                "source": "信息来源",
                "confidence": 0.95
            }}
        }}
    ]
}}"""

    def _generate_l0_task(self, experience_id: str, dialogue: str) -> str:
        """任务1：L0摘要生成 + embedding存储（并行任务）

        Args:
            experience_id: 体验节点ID
            dialogue: 长对话格式（多行字符串，每行标注说话者）

        Returns:
            L0摘要文本

        Raises:
            Exception: LLM调用失败时抛出异常
        """
        return generate_l0_summary(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=self.llm_client,
            embedding_service=self.embedding_service,
            vector_store=self.vector_store,
            experience_store=self.experience_store,
            stable_text=self.stable_text,
        )

    def _recognize_entities_task(self, experience_id: str, dialogue: str) -> List[str]:
        """任务2：实体识别 + 边创建（并行任务）

        Args:
            experience_id: 体验节点ID
            dialogue: 长对话格式（多行字符串，每行标注说话者）

        Returns:
            实体ID列表

        Raises:
            Exception: LLM调用失败时抛出异常
        """
        from Memory.writer.tasks.entity_task import recognize_entities_and_create_edges

        return recognize_entities_and_create_edges(
            experience_id=experience_id,
            dialogue=dialogue,
            llm_client=self.llm_client,
            embedding_service=self.embedding_service,
            entity_store=self.entity_store,
            cross_edge_store=self.cross_edge_store,
        )

    def _analyze_emotion_task(self, experience_id: str, dialogue: str) -> Optional[EmotionSnapshot]:
        """任务3：情感快照 + 状态更新检查（并行任务）

        Args:
            experience_id: 体验节点ID
            dialogue: 长对话格式（多行字符串，每行标注说话者）

        Returns:
            情感快照对象，如果分析失败返回None

        Raises:
            Exception: LLM调用失败时抛出异常
        """
        from Memory.writer.tasks.emotion_task import analyze_emotion_and_check_state

        # 读取状态层上下文
        mood = self.state_manager.get_mood()
        focus = self.state_manager.get_focus()

        return analyze_emotion_and_check_state(
            experience_id=experience_id,
            dialogue=dialogue,
            state_focus=focus,
            state_mood_label=mood.label,
            llm_client=self.llm_client,
            experience_store=self.experience_store,
            stable_text=self.stable_text,
        )

    def _create_edges(self, experience_id: str, entity_ids: List[str]):
        """步骤3：创建时序边和跨层边（所有任务完成后）

        Args:
            experience_id: 体验节点ID
            entity_ids: 实体ID列表（已创建跨层边，这里只创建时序边）

        Note:
            跨层边已在entity_task中创建，这里只创建时序边。
        """
        # ========== 创建时序边：连到上一个体验节点 ==========
        try:
            with db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM experiences
                    WHERE created_at < (
                        SELECT created_at FROM experiences WHERE id = ?
                    )
                    ORDER BY created_at DESC
                    LIMIT 1
                """,
                    (experience_id,),
                )

                row = cursor.fetchone()

                if row:
                    last_exp_id = row[0]

                    # 创建时序边
                    temporal_edge = ExperienceEdge(
                        from_id=experience_id,
                        to_id=last_exp_id,
                        type="temporal",
                        weight=1.0,
                        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    )

                    self.experience_edge_store.create(temporal_edge)
                    self.logger.debug(f"Created temporal edge: {experience_id} -> {last_exp_id}")
                else:
                    self.logger.debug(f"No previous experience found for {experience_id}")

        except Exception as e:
            self.logger.warning(f"Failed to create temporal edge for {experience_id}: {e}")
            # 独立事务：时序边创建失败不影响主流程

    def _async_trigger_state_update(self, emotion_snapshot: EmotionSnapshot):
        """步骤4：异步触发状态层即时更新（不阻塞主流程）

        Args:
            emotion_snapshot: 情感快照对象

        Note:
            - 检查intensity>0.8且距上次更新>1分钟
            - 使用单独线程异步触发，不阻塞主流程
            - 状态更新失败记录warning，不影响写入成功
        """
        # 检查情感强度阈值
        if emotion_snapshot.intensity <= self.EMOTION_INTENSITY_THRESHOLD:
            self.logger.debug(
                f"Emotion intensity {emotion_snapshot.intensity} <= threshold "
                f"{self.EMOTION_INTENSITY_THRESHOLD}, skip state update"
            )
            return

        # 检查时间间隔
        now = time.monotonic()
        if now - self.last_state_update_time <= self.STATE_UPDATE_INTERVAL:
            self.logger.debug(
                f"Time interval {now - self.last_state_update_time:.1f}s <= threshold "
                f"{self.STATE_UPDATE_INTERVAL}s, skip state update"
            )
            return

        # 异步触发状态更新
        def trigger():
            try:
                from Memory.state.updater import DefaultStateUpdater
                updater = DefaultStateUpdater()
                updater.trigger_immediate_update({
                    "category": emotion_snapshot.category,
                    "intensity": emotion_snapshot.intensity,
                    "valence": emotion_snapshot.valence,
                    "arousal": emotion_snapshot.arousal,
                    "target": emotion_snapshot.target,
                })

                # 更新上次更新时间
                self.last_state_update_time = time.monotonic()

            except Exception as e:
                self.logger.warning(f"State update failed: {e}")
                # 状态更新失败不影响写入成功

        # 使用daemon线程，主线程退出时自动终止
        thread = threading.Thread(target=trigger, daemon=True)
        thread.start()

        self.logger.info("State update triggered asynchronously")


# 全局WriterPipeline实例
writer_pipeline = None
