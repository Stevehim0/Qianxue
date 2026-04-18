"""巩固层任务模块。

Contains Phase 1 tasks (L1/L2 extraction, importance valuation, etc.)
and Phase 3 dream module tasks (reorganize, emotion, distort, simulate).
"""

from Memory.consolidator.tasks.l1l2_task import extract_l1l2
from Memory.consolidator.tasks.importance_task import calculate_importance
from Memory.consolidator.tasks.implicit_edges_task import discover_implicit_edges
from Memory.consolidator.tasks.property_upgrade_task import scan_property_upgrade
from Memory.consolidator.tasks.verify_task import verify_information
from Memory.consolidator.tasks.emotion_timeline_task import update_emotion_timeline
from Memory.consolidator.tasks.decay_calculation_task import calculate_decay
from Memory.consolidator.tasks.discover_entity_relations_task import discover_entity_relations

# Dream module tasks (Phase 3)
from Memory.consolidator.tasks.dream_reorganize_task import dream_reorganize
from Memory.consolidator.tasks.dream_emotion_task import dream_emotion
from Memory.consolidator.tasks.dream_distort_task import dream_distort
from Memory.consolidator.tasks.dream_simulate_task import dream_simulate
from Memory.consolidator.tasks.dream_malleable_task import dream_malleable

__all__ = [
    # Phase 1 tasks
    "extract_l1l2",
    "calculate_importance",
    "discover_implicit_edges",
    "scan_property_upgrade",
    "verify_information",
    "update_emotion_timeline",
    "discover_entity_relations",
    # Phase 2 task
    "calculate_decay",
    # Phase 3 dream tasks
    "dream_reorganize",
    "dream_emotion",
    "dream_distort",
    "dream_simulate",
    "dream_malleable",
]
