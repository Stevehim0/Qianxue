"""巩固层并行处理主流程。

协调六个并行任务执行巩固处理。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from Memory.storage.experience_store import (
    ExperienceStore,
    experience_store as global_experience_store,
)
from Memory.storage.experience_edge_store import (
    ExperienceEdgeStore,
    experience_edge_store as global_experience_edge_store,
)
from Memory.storage.entity_store import EntityStore, entity_store as global_entity_store
from Memory.storage.entity_edge_store import (
    EntityEdgeStore,
    entity_edge_store as global_entity_edge_store,
)
from Memory.llm.factory import LLMFactory
from Memory.embedding import EmbeddingService, embedding_service as global_embedding_service
from Memory.embedding.vector_store import VectorStore, vector_store as global_vector_store
from Memory.config.settings import settings
from Memory.consolidator.tasks import (
    # Phase 1 tasks
    extract_l1l2,
    calculate_importance,
    discover_implicit_edges,
    scan_property_upgrade,
    verify_information,
    update_emotion_timeline,
    discover_entity_relations,
    # Phase 2 task
    calculate_decay,
    # Phase 3 dream tasks
    dream_reorganize,
    dream_emotion,
    dream_distort,
    dream_simulate,
    dream_malleable,
)
from Memory.consolidator.sampling import select_memories_for_dream
from Memory.consolidator.config_manager import DecayConfigManager

logger = logging.getLogger(__name__)


class ConsolidationPipeline:
    """巩固层并行处理主流程。

    六项并行任务：
    1. L1/L2深层提取
    2. 重要性估值
    3. 隐性边发现
    4. 属性升级扫描
    5. 信息验证
    6. 情感时间线更新

    Args:
        llm_client: LLM客户端实例
        embedding_service: Embedding服务实例
        vector_store: 向量存储实例
        experience_store: 体验存储实例
        experience_edge_store: 体验边存储实例
        entity_store: 实体存储实例
        entity_edge_store: 实体边存储实例
    """

    def __init__(
        self,
        llm_client=None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[VectorStore] = None,
        experience_store: Optional[ExperienceStore] = None,
        experience_edge_store: Optional[ExperienceEdgeStore] = None,
        entity_store: Optional[EntityStore] = None,
        entity_edge_store: Optional[EntityEdgeStore] = None,
        config_manager: Optional[DecayConfigManager] = None,
        profile_manager=None,  # 新增：个人档案管理器
        stable_text: str = "",
    ):
        """初始化ConsolidationPipeline。

        Args:
            llm_client: LLM客户端实例（默认使用LLMFactory创建）
            embedding_service: Embedding服务实例
            vector_store: 向量存储实例
            experience_store: 体验存储实例
            experience_edge_store: 体验边存储实例
            entity_store: 实体存储实例
            entity_edge_store: 实体边存储实例
            config_manager: 衰减配置管理器实例（默认创建新实例）
            profile_manager: 个人档案管理器实例（可选，用于巩固后更新档案）
        """
        self.llm_client = llm_client if llm_client is not None else LLMFactory.create_client()
        self.embedding_service = (
            embedding_service if embedding_service is not None else global_embedding_service
        )
        self.vector_store = vector_store if vector_store is not None else global_vector_store
        self.experience_store = (
            experience_store if experience_store is not None else global_experience_store
        )
        self.experience_edge_store = (
            experience_edge_store
            if experience_edge_store is not None
            else global_experience_edge_store
        )
        self.entity_store = entity_store if entity_store is not None else global_entity_store
        self.entity_edge_store = (
            entity_edge_store if entity_edge_store is not None else global_entity_edge_store
        )
        self.config_manager = config_manager if config_manager is not None else DecayConfigManager()
        self.profile_manager = profile_manager  # 新增：个人档案管理器
        self.stable_text = stable_text

        self.logger = logging.getLogger(__name__)

        # Setup dream audit logger (D-20)
        self.dream_logger = logging.getLogger("Memory.consolidator.dream")
        dream_log_path = Path(settings.dream.audit_log_path)
        dream_log_path.parent.mkdir(parents=True, exist_ok=True)

        dream_handler = logging.FileHandler(dream_log_path, encoding="utf-8")
        dream_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self.dream_logger.addHandler(dream_handler)
        self.dream_logger.setLevel(logging.INFO)

    def run_consolidation(self, mode: str = "full") -> Dict[str, Any]:
        """Run consolidation process with all phases.

        Args:
            mode: 'full' or 'incremental'

        Returns:
            巩固结果字典，包含：
            - phase1: Phase1任务结果
            - phase2: Phase2衰减计算结果
            - phase3: Phase3梦境任务结果（如果mode="full"）
            - profile_update: 档案更新结果（如果提供profile_manager）

        Note:
            - 如果提供profile_manager，会在巩固完成后调用update_profiles()
            - 梦境AI分析对话历史并更新个人档案的相处方式
            - 档案更新失败不影响巩固成功
        """
        logger = logging.getLogger(__name__)
        results = {}

        # Phase 1: Six parallel tasks
        logger.info("Starting Phase 1: Six parallel tasks...")
        phase1_results = self._run_phase1_tasks()
        results["phase1"] = phase1_results

        # Phase 2: Decay calculation
        logger.info("Starting Phase 2: Decay calculation...")
        phase2_results = self._run_decay_calculation()
        results["phase2"] = phase2_results

        # Phase 3: Dream module (ONLY in full consolidation - D-01, D-17)
        if mode == "full":
            logger.info("Starting Phase 3: Dream module (full consolidation only)...")
            dream_results = self._run_dream_module()
            results["phase3"] = dream_results
        else:
            logger.info("Skipping Phase 3: Dream module (incremental consolidation)")
            results["phase3"] = {"status": "skipped", "reason": "incremental mode"}

        # ========== Phase 4: 更新个人档案（新增）==========
        if self.profile_manager:
            logger.info("Updating profiles after consolidation")
            try:
                self.profile_manager.update_profiles()
                logger.info("Profile update completed")
                results["profile_update"] = {"status": "completed"}
            except Exception as e:
                logger.error(f"Profile update failed: {e}")
                results["profile_update"] = {"status": "failed", "error": str(e)}
                # 档案更新失败不影响巩固成功
        else:
            logger.debug("ProfileManager not provided, skipping profile update")
            results["profile_update"] = {"status": "skipped", "reason": "no_profile_manager"}

        # Final: Mark consolidated
        self._mark_consolidated()

        return results

    def _run_phase1_tasks(self) -> Dict[str, Any]:
        """Execute Phase 1: Six parallel tasks.

        Returns:
            Phase 1 results dict
        """
        # Get candidates
        candidates = self.experience_store.get_consolidation_candidates(
            batch_size=settings.consolidation.batch_size, mode="full"
        )

        if not candidates:
            self.logger.info("No candidates for Phase 1")
            return {"status": "skipped", "reason": "no_candidates"}

        # Initialize execution state
        task_status = {}
        node_count = len(candidates)

        self.logger.info(f"Starting Phase 1: {node_count} nodes")

        # Seven tasks in parallel
        with ThreadPoolExecutor(max_workers=settings.consolidation.max_workers) as executor:
            futures = {
                "l1l2_extraction": executor.submit(self._extract_l1l2_task, candidates),
                "importance_valuation": executor.submit(
                    self._calculate_importance_task, candidates
                ),
                "implicit_edges": executor.submit(self._discover_implicit_edges_task, candidates),
                "property_upgrade": executor.submit(self._scan_property_upgrade_task, candidates),
                "information_verification": executor.submit(
                    self._verify_information_task, candidates
                ),
                "emotion_timeline": executor.submit(self._update_emotion_timeline_task, candidates),
                "entity_relations": executor.submit(self._discover_entity_relations_task, candidates),
            }

            # Wait for all tasks
            for task_name, future in futures.items():
                try:
                    result = future.result(timeout=300)  # 5 minutes
                    task_status[task_name] = {"status": "completed", "result": result}
                    self.logger.info(f"{task_name} completed: {result}")
                except Exception as e:
                    task_status[task_name] = {"status": "failed", "error": str(e)}
                    self.logger.error(f"{task_name} failed: {e}", exc_info=True)

        # Mark consolidated
        experience_ids = [exp.id for exp in candidates]
        updated_count = self.experience_store.update_consolidated_batch(
            experience_ids, consolidated=True
        )

        self.logger.info(f"Phase 1 complete: {node_count} nodes, {updated_count} updated")

        return {
            "status": "completed",
            "node_count": node_count,
            "updated_count": updated_count,
            "tasks": task_status,
        }

    # CRITICAL: DO NOT COMMENT OUT - Core forgetting mechanism
    # See: Phase 08 CONTEXT.md (Decision D-14: L3不改细节先忘)
    #       Phase 12 CONTEXT.md (Gap 1: calculate_decay() orphaned)
    def _run_decay_calculation(self) -> Dict[str, Any]:
        """Execute Phase 2: Decay calculation.

        Returns:
            Phase 2 results dict with edge_count, node_count, dormant_count, awakened_count
        """
        self.logger.info("Starting Phase 2: Decay calculation")

        try:
            result = self._decay_calculation_task()
            self.logger.info(
                f"Phase 2 decay calculation completed: "
                f"{result.get('edge_count', 0)} edges, "
                f"{result.get('node_count', 0)} nodes, "
                f"{result.get('dormant_count', 0)} dormant, "
                f"{result.get('awakened_count', 0)} awakened"
            )
            return result
        except Exception as e:
            self.logger.error(
                f"Phase 2 decay calculation failed: {e}",
                exc_info=True
            )
            return {
                "status": "error",
                "message": str(e),
                "edge_count": 0,
                "node_count": 0,
            }

    def _mark_consolidated(self):
        """Mark all processed experiences as consolidated."""
        # This is a placeholder - actual marking happens in _run_phase1_tasks
        pass

    def _extract_l1l2_task(self, experiences: List) -> Dict:
        """L1/L2深层提取任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        return extract_l1l2(
            experiences=experiences,
            llm_client=self.llm_client,
            experience_store=self.experience_store,
            stable_text=self.stable_text,
        )

    def _calculate_importance_task(self, experiences: List) -> Dict:
        """重要性估值任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        return calculate_importance(
            experiences=experiences,
            llm_client=self.llm_client,
            experience_store=self.experience_store,
            experience_edge_store=self.experience_edge_store,
        )

    def _discover_implicit_edges_task(self, experiences: List) -> Dict:
        """隐性边发现任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        return discover_implicit_edges(
            experiences=experiences,
            llm_client=self.llm_client,
            experience_store=self.experience_store,
            experience_edge_store=self.experience_edge_store,
            embedding_service=self.embedding_service,
        )

    def _scan_property_upgrade_task(self, experiences: List) -> Dict:
        """属性升级扫描任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        return scan_property_upgrade(
            experiences=experiences, llm_client=self.llm_client, entity_store=self.entity_store
        )

    def _verify_information_task(self, experiences: List) -> Dict:
        """信息验证任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        return verify_information(
            experiences=experiences,
            llm_client=self.llm_client,
            entity_edge_store=self.entity_edge_store,
            entity_store=self.entity_store,
            experience_store=self.experience_store,
        )

    def _update_emotion_timeline_task(self, experiences: List) -> Dict:
        """情感时间线更新任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        return update_emotion_timeline(
            experiences=experiences,
            llm_client=self.llm_client,
            entity_store=self.entity_store,
            experience_store=self.experience_store,
        )

    def _discover_entity_relations_task(self, experiences: List) -> Dict:
        """实体关系发现任务。

        Args:
            experiences: 待处理的体验节点列表

        Returns:
            任务结果摘要
        """
        # 获取所有实体
        all_entities = self.entity_store.get_all()
        return discover_entity_relations(
            entities=all_entities,
            llm_client=self.llm_client,
            entity_store=self.entity_store,
            entity_edge_store=self.entity_edge_store,
        )

    def _decay_calculation_task(self) -> Dict[str, Any]:
        """衰减计算任务（Phase 2）。

        CRITICAL: This is the core forgetting mechanism of the memory system.
        DO NOT COMMENT OUT the calculate_decay() call below.
        If decay calculation is disconnected, memories never fade,
        violating the fundamental design principle (D-14: L3不改细节先忘).

        在六个并行任务完成后执行，计算所有边和节点的衰减权重。
        从decay_config表读取参数，支持运行时动态调整。

        See: Memory/衰减函数设计文档.md, Phase 08 CONTEXT.md, Phase 12 CONTEXT.md

        Returns:
            任务结果摘要 {
                'edge_count': 处理的边数,
                'node_count': 处理的节点数,
                'dormant_count': 标记休眠的边数,
                'awakened_count': 唤醒的边数
            }
        """
        # 从decay_config表读取参数
        lambda_map = {
            "temporal": self.config_manager.get("lambda_temporal"),
            "thematic": self.config_manager.get("lambda_thematic"),
            "causal": self.config_manager.get("lambda_causal"),
            "associative": self.config_manager.get("lambda_associative"),
        }

        # 准备分层衰减参数
        lambda_L0 = self.config_manager.get("lambda_L0")
        lambda_L1 = self.config_manager.get("lambda_L1")
        lambda_L2 = self.config_manager.get("lambda_L2")
        lambda_L3 = self.config_manager.get("lambda_L3")
        alpha = self.config_manager.get("alpha")
        beta = self.config_manager.get("beta")
        dormancy_threshold = self.config_manager.get("dormancy_threshold")

        self.logger.info(
            f"Decay calculation parameters: lambda_map={lambda_map}, "
            f"lambda_L0={lambda_L0}, lambda_L1={lambda_L1}, lambda_L2={lambda_L2}, lambda_L3={lambda_L3}, "
            f"alpha={alpha}, beta={beta}, dormancy_threshold={dormancy_threshold}"
        )

        # CRITICAL: Uncommented for Phase 12 Gap Closure
        # Re-connected from orphaned state (see 08-VERIFICATION.md gap 1)
        # DO NOT COMMENT OUT - Core forgetting mechanism
        from Memory.consolidator.tasks.decay_calculation_task import calculate_decay
        result = calculate_decay(
            experience_store=self.experience_store,
            experience_edge_store=self.experience_edge_store,
            lambda_map=lambda_map,
            lambda_L0=lambda_L0,
            lambda_L1=lambda_L1,
            lambda_L2=lambda_L2,
            lambda_L3=lambda_L3,
            alpha=alpha,
            beta=beta,
            dormancy_threshold=dormancy_threshold
        )

        self.logger.info(
            f"Decay calculation completed: "
            f"{result.get('edge_count', 0)} edges processed, "
            f"{result.get('node_count', 0)} nodes processed, "
            f"{result.get('dormant_count', 0)} edges marked dormant, "
            f"{result.get('awakened_count', 0)} edges awakened"
        )

        return result

    def _load_prompt(self, template_name: str) -> str:
        """加载Prompt模板。

        Args:
            template_name: 模板文件名（如'consolid_l1l2.txt'）

        Returns:
            模板内容字符串
        """
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / template_name
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def _run_dream_module(self) -> Dict[str, Any]:
        """执行梦境模块：四任务并行执行。

        Per D-01: 仅在全量巩固时执行（增量巩固不执行）
        Per D-05: Phase 1+2完成后才执行梦境模块
        Per D-06: 四个任务完全独立，互不依赖
        Per D-07: 复用Phase 1的ThreadPoolExecutor
        Per D-08: 任务级超时控制（每任务30分钟）
        Per D-13: 单任务失败记录警告，其他继续
        Per D-20: 所有操作记录到审计日志

        Returns:
            Statistics dict with results from all four dream tasks:
            {
                'reorganize': {...},
                'emotion': {...},
                'distort': {...},
                'simulate': {...},
                'total_duration_seconds': float
            }
        """
        import time

        logger = logging.getLogger(__name__)

        start_time = time.time()

        # Audit logging: Dream module start
        self.dream_logger.info("=" * 60)
        self.dream_logger.info("Dream module started")
        self.dream_logger.info(f"Mode: full consolidation")
        logger.info("Starting dream module...")

        # Step 1: Select memories for each task (independent sampling)
        memories_reorganize = select_memories_for_dream(
            self.experience_store, settings.dream.reorganize_batch_size
        )
        memories_emotion = select_memories_for_dream(
            self.experience_store, settings.dream.emotion_batch_size
        )
        memories_distort = select_memories_for_dream(
            self.experience_store, settings.dream.distort_batch_size
        )
        # DISABLED: dream_simulate task disabled to prevent generating too many dream experiences
        # memories_simulate = select_memories_for_dream(
        #     self.experience_store, settings.dream.simulate_batch_size
        # )
        memories_simulate = []  # Empty list to disable simulate task

        # Audit logging: Sampling results
        self.dream_logger.info(
            f"Dream sampling: reorganize={len(memories_reorganize)}, "
            f"emotion={len(memories_emotion)}, "
            f"distort={len(memories_distort)}, "
            f"simulate=DISABLED, malleable=enabled"
        )
        logger.info(
            f"Dream sampling complete: "
            f"reorganize={len(memories_reorganize)}, "
            f"emotion={len(memories_emotion)}, "
            f"distort={len(memories_distort)}, "
            f"simulate=DISABLED, malleable=enabled"
        )

        # Step 2: Execute tasks in parallel using ThreadPoolExecutor
        # Three memory tasks + malleable evolution task (simulate disabled)
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit memory tasks
            future_reorganize = executor.submit(
                dream_reorganize,
                memories_reorganize,
                self.llm_client,
                self.experience_store,
                self.experience_edge_store,
            )
            future_emotion = executor.submit(
                dream_emotion, memories_emotion, self.llm_client, self.experience_store
            )
            future_distort = executor.submit(
                dream_distort, memories_distort, self.llm_client, self.experience_store
            )
            # Malleable evolution task
            backend_url = getattr(settings.dream, "backend_url", "http://localhost:8000")
            future_malleable = executor.submit(
                dream_malleable,
                self.llm_client,
                self.experience_store,
                backend_url,
            )

            # Step 3: Wait for all tasks with timeout (D-08: 30 minutes per task)
            results = {}
            futures = {
                "reorganize": future_reorganize,
                "emotion": future_emotion,
                "distort": future_distort,
                "simulate": None,  # Disabled
                "malleable": future_malleable,
            }

            for task_name, future in futures.items():
                # Skip disabled simulate task
                if task_name == "simulate" and future is None:
                    results[task_name] = {
                        "status": "disabled",
                        "processed_count": 0,
                        "failed_count": 0,
                        "message": "Simulate task disabled to prevent generating too many dream experiences"
                    }
                    self.dream_logger.info("Dream task simulate: DISABLED")
                    logger.info("Dream task simulate: DISABLED")
                    continue

                try:
                    result = future.result(timeout=1800)  # 30 minutes
                    results[task_name] = result
                    # Audit logging: Task completion
                    self.dream_logger.info(f"Dream task {task_name} completed: {result}")
                    logger.info(f"Dream task {task_name} completed: {result}")
                except FuturesTimeoutError:
                    timeout_msg = f"Dream task {task_name} timed out after 30 minutes"
                    self.dream_logger.warning(timeout_msg)
                    logger.warning(timeout_msg)
                    results[task_name] = {
                        "status": "timeout",
                        "processed_count": 0,
                        "failed_count": 0,
                    }
                except Exception as e:
                    error_msg = f"Dream task {task_name} failed: {e}"
                    self.dream_logger.error(error_msg, exc_info=True)
                    logger.error(error_msg)
                    results[task_name] = {
                        "status": "failed",
                        "error": str(e),
                        "processed_count": 0,
                        "failed_count": 0,
                    }

        # Step 4: Calculate total duration and log results
        total_duration = time.time() - start_time
        results["total_duration_seconds"] = total_duration

        # Audit logging: Final results
        self.dream_logger.info("Dream module results:")
        for task_name, result in results.items():
            if task_name != "total_duration_seconds":
                self.dream_logger.info(f"  {task_name}: {result}")

        self.dream_logger.info(f"Dream module completed in {total_duration:.2f}s")
        self.dream_logger.info("=" * 60)
        logger.info(f"Dream module completed in {total_duration:.2f}s")

        return results


# 全局ConsolidationPipeline实例
consolidation_pipeline = None
