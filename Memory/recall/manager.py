"""召回管理器模块。

本模块提供召回层的核心协调器功能。
双轨召回：体验层 + 信息层，各自向量检索 + 扩散，通过跨层边互相关联。

参考：Memory/召回层设计文档.md §四 召回管线
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

from Memory.storage.experience_store import ExperienceStore
from Memory.storage.entity_store import EntityStore
from Memory.storage.experience_edge_store import ExperienceEdgeStore
from Memory.storage.entity_edge_store import EntityEdgeStore
from Memory.storage.cross_edge_store import CrossEdgeStore
from Memory.storage.database import db_manager
from Memory.embedding.vector_store import VectorStore
from Memory.embedding.model import EmbeddingService
from Memory.recall.detector import TriggerDetector
from Memory.recall.briefing import BriefingGenerator
from Memory.recall.result import RecallResult, EntityRecallResult

logger = logging.getLogger(__name__)

# 返回数量限制
EXPERIENCE_TOP_K = 3
ENTITY_TOP_K = 15

# 向量检索每条关键词取的数量
VECTOR_SEARCH_TOP_K = 10


class RecallManager:
    """召回层主管理器。

    双轨召回管线：
    - 体验轨：向量检索 experience_L0 → 沿 experience_edges 扩散1跳
    - 信息轨：向量检索 entities → 沿 entity_edges 扩散1跳
    - 跨层关联：通过 cross_edges 互相关联
    """

    def __init__(
        self,
        experience_store: ExperienceStore,
        entity_store: EntityStore,
        edge_store: ExperienceEdgeStore,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        llm_client=None,
        profile_manager=None,
        adjacency_cache=None,
        stable_text: str = "",
    ):
        self.experience_store = experience_store
        self.entity_store = entity_store
        self.edge_store = edge_store
        self.entity_edge_store = EntityEdgeStore()
        self.cross_edge_store = CrossEdgeStore()
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.llm_client = llm_client
        self.profile_manager = profile_manager
        self.adjacency_cache = adjacency_cache

        self.trigger_detector = TriggerDetector(entity_store)

        # 简报生成器（有LLM客户端时启用）
        self.briefing_generator = BriefingGenerator(llm_client, stable_text=stable_text) if llm_client else None

        # 预加载实体间边到内存（用于信息层扩散）
        self._entity_adjacency: Dict[str, List[tuple]] = {}
        self._load_entity_adjacency()

        logger.info("RecallManager initialized")

    def _load_entity_adjacency(self):
        """从 entity_edges 加载实体间邻接表到内存。"""
        try:
            with db_manager.transaction() as cur:
                cur.execute(
                    "SELECT from_id, to_id, confidence FROM entity_edges"
                )
                for row in cur.fetchall():
                    fid, tid, conf = row["from_id"], row["to_id"], row["confidence"]
                    self._entity_adjacency.setdefault(fid, []).append((tid, conf))
                    self._entity_adjacency.setdefault(tid, []).append((fid, conf))
            logger.info(f"Loaded {len(self._entity_adjacency)} entity adjacency nodes")
        except Exception as e:
            logger.warning(f"Failed to load entity adjacency: {e}")

    def recall(self, query: str, context: dict) -> dict:
        """主召回入口。

        双轨召回：体验层 + 信息层，各自检索+扩散，跨层关联。

        Returns:
            {
                "experiences": [Top3 体验, 只含L1],
                "entities": [Top15 实体, 含完整信息]
            }
        """
        # 步骤0：加载个人档案
        if self.profile_manager:
            profiles_to_load = context.get("profiles_to_load", [])
            if profiles_to_load:
                loaded = []
                for name in profiles_to_load:
                    try:
                        text = self.profile_manager.load_profile(name)
                        if text:
                            loaded.append(text)
                    except Exception as e:
                        logger.warning(f"Failed to load profile for {name}: {e}")
                context["loaded_profiles"] = loaded

        # 1. 触发判断
        if not self.trigger_detector.should_trigger(query):
            return {"experiences": [], "entities": []}

        # 2. 关键词提取
        keywords = self.trigger_detector.extract_keywords(query, context)
        if not keywords:
            return {"experiences": [], "entities": []}

        # ===== 体验轨 =====
        # 3. 体验层向量检索
        exp_candidates = self._experience_vector_search(keywords)

        # 4. 体验层扩散1跳（沿 experience_edges）
        exp_spread = self._experience_spread(exp_candidates)

        # 5. 合并体验结果
        all_experiences = self._merge_experiences(exp_candidates, exp_spread)

        # 6. 为每个体验附上关联实体（通过 cross_edges）
        self._attach_entities_to_experiences(all_experiences)

        # ===== 信息轨 =====
        # 7. 信息层向量检索
        entity_candidates = self._entity_vector_search(keywords)

        # 8. 信息层扩散1跳（沿 entity_edges）
        entity_spread = self._entity_spread(entity_candidates)

        # 9. 合并实体结果
        all_entities = self._merge_entities(entity_candidates, entity_spread)

        # ===== 排序截断 =====
        # 10. 体验按 rank_score 排序取 Top3
        all_experiences.sort(key=lambda x: x.rank_score, reverse=True)
        top_experiences = all_experiences[:EXPERIENCE_TOP_K]

        # 11. 实体按 activation_score 排序取 Top15
        all_entities.sort(key=lambda x: x.activation_score, reverse=True)
        top_entities = all_entities[:ENTITY_TOP_K]

        # ===== 过滤+简报（一次LLM调用） =====
        # 12. 过滤+生成自然语言简报（有生成器时启用）
        briefing = None
        if self.briefing_generator and (top_experiences or top_entities):
            before_exp, before_ent = len(top_experiences), len(top_entities)
            result = self.briefing_generator.generate(
                experiences=top_experiences,
                entities=top_entities,
                query=query,
                context=context,
            )
            if result:
                top_experiences = [
                    top_experiences[i]
                    for i in result["selected_exp_indices"]
                ]
                top_entities = [
                    top_entities[i]
                    for i in result["selected_ent_indices"]
                ]
                briefing = result["briefing"]
                logger.info(
                    f"[RecallPipeline] filtered: {before_exp}→{len(top_experiences)} exp, "
                    f"{before_ent}→{len(top_entities)} ent"
                )
            else:
                logger.info("[RecallPipeline] briefing generation failed, returning unfiltered results")
        else:
            logger.info(
                f"[RecallPipeline] briefing skipped "
                f"(generator={'yes' if self.briefing_generator else 'no'}, "
                f"has_results={bool(top_experiences or top_entities)})"
            )

        return {
            "experiences": top_experiences,
            "entities": top_entities,
            "briefing": briefing,
        }

    def recall_by_keywords(self, keywords: List[str], context: dict) -> dict:
        """关键词召回入口 — 跳过触发检测和关键词提取，直接用关键词走双轨召回。

        Args:
            keywords: 关键词列表（由调用方已提取好）
            context: 上下文字典 (recent_history, ai_state, current_time)

        Returns:
            {"experiences": [Top3], "entities": [Top15], "briefing": str|None}
        """
        if not keywords:
            return {"experiences": [], "entities": []}

        logger.info(f"[RecallPipeline] keywords: {keywords}")

        # ===== 体验轨 =====
        exp_candidates = self._experience_vector_search(keywords)
        logger.info(f"[RecallPipeline] 体验轨向量检索: {len(exp_candidates)} candidates")
        exp_spread = self._experience_spread(exp_candidates)
        logger.info(f"[RecallPipeline] 体验轨扩散: {len(exp_spread)} spread")
        all_experiences = self._merge_experiences(exp_candidates, exp_spread)
        self._attach_entities_to_experiences(all_experiences)

        # ===== 信息轨 =====
        entity_candidates = self._entity_vector_search(keywords)
        logger.info(f"[RecallPipeline] 信息轨向量检索: {len(entity_candidates)} candidates")
        entity_spread = self._entity_spread(entity_candidates)
        logger.info(f"[RecallPipeline] 信息轨扩散: {len(entity_spread)} spread")
        all_entities = self._merge_entities(entity_candidates, entity_spread)

        # ===== 排序截断 =====
        all_experiences.sort(key=lambda x: x.rank_score, reverse=True)
        top_experiences = all_experiences[:EXPERIENCE_TOP_K]

        all_entities.sort(key=lambda x: x.activation_score, reverse=True)
        top_entities = all_entities[:ENTITY_TOP_K]

        logger.info(f"[RecallPipeline] 截断后: {len(top_experiences)} experiences, {len(top_entities)} entities")

        # 详细输出召回结果
        for i, exp in enumerate(top_experiences, 1):
            logger.info(
                f"[RecallPipeline] 体验#{i}: id={exp.experience_id}, "
                f"score={exp.rank_score:.3f}, importance={exp.importance:.2f}, "
                f"source={exp.source_type}, "
                f"L0={exp.L0_text[:60] if exp.L0_text else 'None'}"
            )
        for i, ent in enumerate(top_entities, 1):
            props_str = str(ent.properties)[:80] if ent.properties else "None"
            logger.info(
                f"[RecallPipeline] 实体#{i}: name={ent.name}, type={ent.type}, "
                f"score={ent.activation_score:.3f}, source={ent.source_type}, "
                f"props={props_str}"
            )

        # ===== 过滤+简报（一次LLM调用） =====
        briefing = None
        if self.briefing_generator and (top_experiences or top_entities):
            result = self.briefing_generator.generate(
                experiences=top_experiences,
                entities=top_entities,
                query=", ".join(keywords),
                context=context,
            )
            if result:
                before_exp, before_ent = len(top_experiences), len(top_entities)
                top_experiences = [
                    top_experiences[i]
                    for i in result["selected_exp_indices"]
                ]
                top_entities = [
                    top_entities[i]
                    for i in result["selected_ent_indices"]
                ]
                briefing = result["briefing"]
                logger.info(
                    f"[RecallPipeline] filtered: {before_exp}→{len(top_experiences)} exp, "
                    f"{before_ent}→{len(top_entities)} ent, "
                    f"briefing: {briefing[:100] if briefing else 'None'}..."
                )
            else:
                logger.info("[RecallPipeline] briefing generation failed, returning unfiltered results")
        else:
            logger.info(f"[RecallPipeline] briefing skipped (generator={'yes' if self.briefing_generator else 'no'}, has_results={bool(top_experiences or top_entities)})")

        return {
            "experiences": top_experiences,
            "entities": top_entities,
            "briefing": briefing,
        }

    def expand_memory(self, memory_id: str, level: int) -> Dict[str, Optional[str]]:
        """深度展开接口（RECALL-12）。按需展开L1/L2/L3。"""
        exp = self.experience_store.get(memory_id)
        if not exp:
            return {}

        result = {"L0": exp.L0_text}
        if level >= 1 and exp.L1_text:
            result["L1"] = exp.L1_text
        if level >= 2 and exp.L2_text:
            result["L2"] = exp.L2_text
        if level >= 3 and exp.L3_raw:
            result["L3"] = exp.L3_raw

        return result

    # ================================================================
    # 体验轨
    # ================================================================

    def _experience_vector_search(self, keywords: List[str]) -> List[RecallResult]:
        """体验层向量检索：关键词 → embedding → experience_L0 集合查询。"""
        results = []
        seen = set()

        for keyword in keywords:
            embedding = self.embedding_service.encode(keyword)
            query_results = self.vector_store.query_experience(
                query_embedding=embedding.tolist(), top_k=VECTOR_SEARCH_TOP_K
            )

            if not query_results.get("ids") or not query_results["ids"][0]:
                continue

            for idx, exp_id in enumerate(query_results["ids"][0]):
                if exp_id in seen:
                    continue

                exp = self.experience_store.get(exp_id)
                if not exp:
                    continue

                seen.add(exp_id)
                similarity = float(1 - query_results["distances"][0][idx])
                time_distance = self._calculate_time_distance(exp.created_at)

                results.append(RecallResult(
                    experience_id=exp_id,
                    L0_text=exp.L0_text or "",
                    L1_text=getattr(exp, "L1_text", None),
                    recall_hint=getattr(exp, "recall_hint", None),
                    importance=exp.importance,
                    emotion_category=exp.emotion_category,
                    time_distance_days=time_distance,
                    activation_score=similarity,
                    source_type="vector_search",
                ))

        return results

    def _experience_spread(self, candidates: List[RecallResult]) -> List[RecallResult]:
        """体验层扩散1跳：从向量检索结果沿 experience_edges 找间接关联体验。"""
        if not self.adjacency_cache or not candidates:
            return []

        start_nodes = [c.experience_id for c in candidates]
        activated_scores = self.adjacency_cache.spread(start_nodes, max_hops=1)

        # 排除已被向量检索直接命中的
        hit_ids = {c.experience_id for c in candidates}

        results = []
        for exp_id, score in activated_scores.items():
            if exp_id in hit_ids:
                continue

            exp = self.experience_store.get(exp_id)
            if not exp:
                continue

            time_distance = self._calculate_time_distance(exp.created_at)

            results.append(RecallResult(
                experience_id=exp_id,
                L0_text=exp.L0_text or "",
                L1_text=getattr(exp, "L1_text", None),
                recall_hint=getattr(exp, "recall_hint", None),
                importance=exp.importance,
                emotion_category=exp.emotion_category,
                time_distance_days=time_distance,
                activation_score=score,
                source_type="activation_spread",
            ))

        return results

    def _merge_experiences(
        self, vector_results: List[RecallResult], spread_results: List[RecallResult]
    ) -> List[RecallResult]:
        """合并体验层结果，计算排序分数。

        排序公式：
        - 向量检索: similarity × importance
        - 激活扩散: activation_score(内含 decayed_weight) × importance × 0.8
        """
        merged = {}

        # 先放扩散结果
        for r in spread_results:
            merged[r.experience_id] = r

        # 向量检索结果覆盖（更直接）
        for r in vector_results:
            if r.experience_id in merged:
                existing = merged[r.experience_id]
                r.activation_score = max(r.activation_score, existing.activation_score)
            merged[r.experience_id] = r

        # 计算排序分
        multiplier_map = {"vector_search": 1.0, "activation_spread": 0.8}
        for r in merged.values():
            mult = multiplier_map.get(r.source_type, 1.0)
            r.rank_score = r.activation_score * r.importance * mult
            # 回填 recall_hint
            r.recall_hint = r.recall_hint or r.L0_text

        return list(merged.values())

    def _attach_entities_to_experiences(self, experiences: List[RecallResult]):
        """为每个体验节点附上关联的信息层实体（通过 cross_edges）。"""
        try:
            with db_manager.transaction() as cur:
                for exp in experiences:
                    cur.execute(
                        "SELECT to_id FROM cross_edges WHERE from_id = ?",
                        (exp.experience_id,),
                    )
                    entities = []
                    for row in cur.fetchall():
                        entity = self.entity_store.get(row["to_id"])
                        if entity:
                            entities.append({
                                "name": entity.name,
                                "type": entity.type,
                            })
                    exp.related_entities = entities
        except Exception as e:
            logger.warning(f"Failed to attach entities: {e}")

    # ================================================================
    # 信息轨
    # ================================================================

    def _entity_vector_search(self, keywords: List[str]) -> List[EntityRecallResult]:
        """信息层向量检索：关键词 → embedding → entities 集合查询。"""
        results = []
        seen = set()

        for keyword in keywords:
            embedding = self.embedding_service.encode(keyword)
            query_results = self.vector_store.query_entity(
                query_embedding=embedding.tolist(), top_k=VECTOR_SEARCH_TOP_K
            )

            if not query_results.get("ids") or not query_results["ids"][0]:
                continue

            for idx, entity_id in enumerate(query_results["ids"][0]):
                if entity_id in seen:
                    continue

                entity = self.entity_store.get(entity_id)
                if not entity:
                    continue

                seen.add(entity_id)
                similarity = float(1 - query_results["distances"][0][idx])

                results.append(EntityRecallResult(
                    entity_id=entity_id,
                    name=entity.name,
                    type=entity.type,
                    properties=entity.properties,
                    activation_score=similarity,
                    source_type="entity_vector_search",
                ))

        return results

    def _entity_spread(self, candidates: List[EntityRecallResult]) -> List[EntityRecallResult]:
        """信息层扩散1跳：从向量检索结果沿 entity_edges 找关联实体。"""
        hit_ids = {c.entity_id for c in candidates}
        results = []
        seen = set(hit_ids)

        for candidate in candidates:
            neighbors = self._entity_adjacency.get(candidate.entity_id, [])
            for neighbor_id, confidence in neighbors:
                if neighbor_id in seen:
                    continue

                entity = self.entity_store.get(neighbor_id)
                if not entity:
                    continue

                seen.add(neighbor_id)
                # 扩散分数 = 源实体分数 × 边置信度 × 衰减
                spread_score = candidate.activation_score * confidence * 0.8

                results.append(EntityRecallResult(
                    entity_id=neighbor_id,
                    name=entity.name,
                    type=entity.type,
                    properties=entity.properties,
                    activation_score=spread_score,
                    source_type="entity_spread",
                ))

        return results

    def _merge_entities(
        self, vector_results: List[EntityRecallResult], spread_results: List[EntityRecallResult]
    ) -> List[EntityRecallResult]:
        """合并实体结果，去重保留最高分。"""
        merged = {}

        for r in spread_results:
            if r.entity_id not in merged or r.activation_score > merged[r.entity_id].activation_score:
                merged[r.entity_id] = r

        for r in vector_results:
            if r.entity_id not in merged or r.activation_score > merged[r.entity_id].activation_score:
                merged[r.entity_id] = r

        return list(merged.values())

    # ================================================================
    # 工具方法
    # ================================================================

    def _calculate_time_distance(self, created_at: Optional[str]) -> float:
        """计算时间距离（小数天数）。"""
        if not created_at:
            return 0.0
        try:
            created_time = datetime.fromisoformat(created_at)
            delta = datetime.now() - created_time
            return delta.total_seconds() / 86400.0
        except Exception:
            return 0.0
