"""内存邻接表缓存模块。

本模块提供内存邻接表缓存，优化激活扩散性能。
在内存中维护图的邻接表结构，避免实时查询SQLite。
"""

import logging
from typing import List, Dict, Tuple

from Memory.storage.experience_edge_store import ExperienceEdgeStore, ExperienceEdge

logger = logging.getLogger(__name__)


class AdjacencyCache:
    """内存邻接表缓存 - 优化激活扩散性能（RECALL-05）。

    在内存中维护图的邻接表结构，避免实时查询SQLite。
    三阶段生命周期管理（D-08）：
    - 启动加载：系统启动时全量加载所有边
    - 实时同步：写入层创建新边时增量同步
    - 巩固重载：巩固结束后全量重载

    Attributes:
        edge_store: ExperienceEdgeStore实例
        adjacency: 邻接表字典 {node_id: [(neighbor_id, edge_type, decayed_weight)]}
        hop_decay: 跳数衰减参数（默认0.6，D-07）
    """

    def __init__(self, edge_store: ExperienceEdgeStore, hop_decay: float = 0.6):
        """初始化AdjacencyCache。

        Args:
            edge_store: ExperienceEdgeStore实例
            hop_decay: 跳数衰减参数（D-07），默认0.6
        """
        self.edge_store = edge_store
        self.hop_decay = hop_decay
        self.adjacency: Dict[str, List[Tuple[str, str, float]]] = {}

        # 启动时全量加载（D-08第一阶段）
        self._load_from_db()

        logger.info(f"AdjacencyCache initialized with {len(self.adjacency)} nodes")

    def _load_from_db(self):
        """从数据库全量加载所有边到内存（D-08第一阶段）。

        构建邻接表：{node_id: [(neighbor_id, edge_type, decayed_weight)]}
        """
        logger.info("Loading adjacency table from database...")

        # 获取所有边
        all_edges = self.edge_store.get_all()

        # 构建邻接表
        for edge in all_edges:
            # 跳过休眠的边
            if edge.dormant == 1:
                continue

            # 添加 from_id -> to_id
            if edge.from_id not in self.adjacency:
                self.adjacency[edge.from_id] = []
            self.adjacency[edge.from_id].append((edge.to_id, edge.type, edge.decayed_weight))

            # 如果是无向边（如联想关系），也添加反向边
            if edge.type in ["associative", "thematic"]:
                if edge.to_id not in self.adjacency:
                    self.adjacency[edge.to_id] = []
                self.adjacency[edge.to_id].append((edge.from_id, edge.type, edge.decayed_weight))

        logger.info(f"Loaded {len(all_edges)} edges for {len(self.adjacency)} nodes")

    def spread(self, start_nodes: List[str], max_hops: int = 1) -> Dict[str, float]:
        """从起始节点扩散，返回激活分数（RECALL-05, RECALL-08）。

        激活分数公式：base_score × decayed_weight × (hop_decay ^ hop)

        Args:
            start_nodes: 起始节点ID列表
            max_hops: 最大扩散跳数（RECALL-07），默认1跳

        Returns:
            字典 {node_id: activation_score}
        """
        activated = {}
        current = {node_id: 1.0 for node_id in start_nodes}

        # BFS扩散，最多max_hops跳
        for hop in range(max_hops):
            next_current = {}

            for node_id, base_score in current.items():
                # 获取邻居
                neighbors = self.adjacency.get(node_id, [])

                for neighbor_id, edge_type, decayed_weight in neighbors:
                    # 避免重复激活
                    if neighbor_id in activated:
                        continue

                    # 计算激活分数（RECALL-08）
                    # score = base_score × decayed_weight × (hop_decay ^ hop)
                    score = base_score * decayed_weight * (self.hop_decay**hop)

                    activated[neighbor_id] = score
                    next_current[neighbor_id] = score

            # 继续下一跳
            current = next_current

            # 如果没有更多节点可扩散，提前结束
            if not current:
                break

        logger.debug(
            f"Activation spread from {len(start_nodes)} nodes "
            f"with max_hops={max_hops} found {len(activated)} nodes"
        )
        return activated

    def add_edge(self, from_id: str, to_id: str, edge_type: str, weight: float):
        """写入新边时增量同步（D-08第二阶段，RECALL-06）。

        写入层创建新边时立即调用此方法同步更新内存缓存。

        Args:
            from_id: 源节点ID
            to_id: 目标节点ID
            edge_type: 边类型
            weight: 衰减后权重
        """
        # 添加 from_id -> to_id
        if from_id not in self.adjacency:
            self.adjacency[from_id] = []
        self.adjacency[from_id].append((to_id, edge_type, weight))

        # 如果是无向边，也添加反向边
        if edge_type in ["associative", "thematic"]:
            if to_id not in self.adjacency:
                self.adjacency[to_id] = []
            self.adjacency[to_id].append((from_id, edge_type, weight))

        logger.debug(f"Added edge {from_id} -> {to_id} ({edge_type}) to cache")

    def reload(self):
        """全量重载 - 巩固结束后调用（D-08第三阶段，RECALL-06）。

        清空当前缓存并从数据库重新加载所有边。
        确保衰减值一致（巩固阶段更新了decayed_weight）。
        """
        logger.info("Reloading adjacency cache...")

        # 清空当前缓存
        self.adjacency.clear()

        # 重新加载
        self._load_from_db()

        logger.info(f"Adjacency cache reloaded with {len(self.adjacency)} nodes")
