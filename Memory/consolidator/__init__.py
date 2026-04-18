"""巩固层模块。

本模块提供记忆巩固功能，模拟人类睡眠时的记忆处理过程。
包含六个并行任务的协调和执行。

主要组件：
- ConsolidationPipeline: 巩固层主流程，协调六个并行任务
"""

from Memory.consolidator.pipeline import ConsolidationPipeline

__all__ = ["ConsolidationPipeline"]
