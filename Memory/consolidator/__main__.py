"""巩固层CLI命令入口。

使用方法：
    python -m Memory.consolidator run                    # 增量巩固（默认）
    python -m Memory.consolidator run --mode full       # 全量巩固
    python -m Memory.consolidator run --batch-size 50   # 自定义批次大小
    python -m Memory.consolidator config --list         # 列出所有衰减参数
    python -m Memory.consolidator config --set lambda_L0 0.02  # 设置参数
"""

import argparse
import logging
import sys
from pathlib import Path

from Memory.consolidator.pipeline import ConsolidationPipeline
from Memory.consolidator.config_manager import DecayConfigManager
from Memory.config.settings import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "consolidation.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def main():
    """CLI主函数。"""
    parser = argparse.ArgumentParser(
        description="记忆巩固层CLI - 支持增量/全量巩固和梦境模块",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 增量巩固（不执行梦境模块）
  %(prog)s run --mode incremental

  # 全量巩固（自动执行梦境模块）
  %(prog)s run --mode full

  # 全量巩固 + 自定义批次大小
  %(prog)s run --mode full --batch-size 50

  # 配置管理
  %(prog)s config --list         # 列出所有衰减参数
  %(prog)s config --set lambda_L0 0.02  # 设置参数

配置:
  默认配置从settings.consolidation读取，包括：
  - batch_size: 每批处理节点数（默认20）
  - max_workers: 并行工作线程数（默认None）
  - similarity_threshold: 隐性边相似度阈值（默认0.7）

梦境模块说明:
  - 仅在全量巩固（mode=full）时执行
  - 包含四个并行任务：重组、情感加工、扭曲、推演
  - 默认每任务处理20个记忆（可通过DreamConfig调整）
  - 执行日志记录到 Memory/logs/dream_audit.log
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # run子命令
    run_parser = subparsers.add_parser("run", help="执行巩固")
    run_parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="巩固模式：incremental（增量，默认）或 full（全量最近7天）",
    )
    run_parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="批次大小（默认使用settings.consolidation.batch_size）",
    )

    # config子命令
    config_parser = subparsers.add_parser("config", help="衰减参数配置")
    config_parser.add_argument("--list", action="store_true", help="列出所有衰减参数")
    config_parser.add_argument(
        "--set", nargs=2, metavar=("KEY", "VALUE"), help="设置衰减参数（如：--set lambda_L0 0.02）"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # 路由到对应的处理函数
    if args.command == "config":
        return handle_config_command(args)
    elif args.command == "run":
        return handle_run_command(args)
    else:
        parser.print_help()
        return 1


def handle_run_command(args) -> int:
    """处理run子命令。

    Args:
        args: argparse解析的参数对象

    Returns:
        退出码（0=成功，1=失败）
    """
    # 执行巩固
    try:
        logger.info("=" * 60)
        logger.info("记忆巩固开始")
        logger.info(f"模式: {args.mode}")

        # 创建pipeline实例
        pipeline = ConsolidationPipeline()

        # 如果指定了batch_size，临时覆盖配置
        if args.batch_size:
            logger.info(f"批次大小: {args.batch_size}（命令行覆盖）")
            original_batch_size = settings.consolidation.batch_size
            settings.consolidation.batch_size = args.batch_size

        # 执行巩固
        result = pipeline.run_consolidation(mode=args.mode)

        # 恢复原始配置
        if args.batch_size:
            settings.consolidation.batch_size = original_batch_size

        # 输出结果
        logger.info("=" * 60)
        logger.info("巩固完成")
        logger.info(f"状态: {result.get('status')}")
        logger.info(f"模式: {result.get('mode')}")

        if result.get("status") == "completed":
            logger.info(f"处理节点数: {result.get('node_count')}")
            logger.info(f"更新节点数: {result.get('updated_count')}")
            logger.info(f"耗时: {result.get('duration', 0):.2f}秒")

            # 输出各任务结果
            tasks = result.get("tasks", {})
            logger.info(f"任务结果:")
            for task_name, task_result in tasks.items():
                status = task_result.get("status", "unknown")
                if status == "completed":
                    result_data = task_result.get("result", {})
                    logger.info(f"  - {task_name}: {status} ({result_data})")
                else:
                    error = task_result.get("error", "unknown error")
                    logger.warning(f"  - {task_name}: {status} ({error})")
        else:
            reason = result.get("reason", "unknown")
            logger.info(f"跳过原因: {reason}")

        logger.info("=" * 60)

        return 0 if result.get("status") in ["completed", "skipped"] else 1

    except KeyboardInterrupt:
        logger.warning("\n用户中断")
        return 130
    except Exception as e:
        logger.error(f"巩固失败: {e}", exc_info=True)
        return 1


def handle_config_command(args) -> int:
    """处理config子命令。

    Args:
        args: argparse解析的参数对象

    Returns:
        退出码（0=成功，1=失败）
    """
    manager = DecayConfigManager()

    if args.list:
        # 列出所有参数
        configs = manager.list_all()
        print("=" * 60)
        print("衰减参数配置：")
        print("=" * 60)

        # 按类别分组显示
        lambda_params = {k: v for k, v in configs.items() if k.startswith("lambda_")}
        other_params = {k: v for k, v in configs.items() if not k.startswith("lambda_")}

        print("\n[分层衰减参数]")
        for key, info in sorted(lambda_params.items()):
            print(f"  {key:20s} = {info['value']:6.3f}  # {info['description']}")

        print("\n[其他参数]")
        for key, info in sorted(other_params.items()):
            print(f"  {key:20s} = {info['value']:6.3f}  # {info['description']}")

        print("=" * 60)
        return 0

    elif args.set:
        # 设置参数
        key, value_str = args.set

        try:
            value = float(value_str)
            manager.set(key, value)
            print(f"✓ 参数已更新: {key} = {value}")
            return 0
        except ValueError as e:
            print(f"✗ 参数验证失败: {e}")
            return 1

    else:
        print("错误: 请指定 --list 或 --set 参数")
        return 1


if __name__ == "__main__":
    sys.exit(main())
