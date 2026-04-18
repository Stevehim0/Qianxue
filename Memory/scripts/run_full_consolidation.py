#!/usr/bin/env python3
"""全量巩固脚本 - 详细记录巩固层的所有改动

包括：
- Phase 1: L1/L2深层提取、重要性估值、隐性边发现、属性升级、信息验证、情感时间线
- Phase 2: 衰减计算
- Phase 3: 梦境模块（重组、情感、扭曲、模拟）
"""
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 确保可以从 scripts/ 目录导入 Memory 包
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from Memory.consolidator.pipeline import ConsolidationPipeline
from Memory.llm.factory import LLMFactory
from Memory.storage.database import db_manager
from Memory.storage.experience_store import experience_store as global_experience_store
from Memory.storage.entity_store import entity_store as global_entity_store
from Memory.storage.entity_edge_store import entity_edge_store as global_entity_edge_store
from Memory.storage.experience_edge_store import experience_edge_store as global_experience_edge_store
from Memory.config.settings import settings

_MEMORY_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = _MEMORY_ROOT / "reports" / "consolidation_report.txt"


class ConsolidationReporter:
    """巩固过程报告器"""

    def __init__(self):
        self.changes = {
            'before': {},
            'after': {},
            'deltas': {}
        }
        self.start_time = None
        self.end_time = None

    def capture_before_state(self):
        """捕获巩固前的状态"""
        print("📊 捕获巩固前状态...")

        # 获取体验统计
        conn = sqlite3.connect(_MEMORY_ROOT / "data" / "memory.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 体验统计
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN L1_text IS NOT NULL THEN 1 ELSE 0 END) as l1_count,
                SUM(CASE WHEN L2_text IS NOT NULL THEN 1 ELSE 0 END) as l2_count,
                SUM(CASE WHEN importance IS NOT NULL THEN 1 ELSE 0 END) as importance_count,
                SUM(CASE WHEN consolidated = 1 THEN 1 ELSE 0 END) as consolidated_count
            FROM experiences
        """)
        exp_stats = cursor.fetchone()
        self.changes['before']['experiences'] = dict(exp_stats)

        # 实体统计
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT name) as unique_names
            FROM entities
        """)
        entity_stats = cursor.fetchone()
        self.changes['before']['entities'] = dict(entity_stats)

        # 实体边统计
        cursor.execute("SELECT COUNT(*) as total FROM entity_edges")
        edge_stats = cursor.fetchone()
        self.changes['before']['entity_edges'] = dict(edge_stats)

        # 体验边统计
        cursor.execute("SELECT COUNT(*) as total FROM experience_edges")
        exp_edge_stats = cursor.fetchone()
        self.changes['before']['experience_edges'] = dict(exp_edge_stats)

        # Schema版本
        cursor.execute("SELECT version FROM schema_version")
        schema_ver = cursor.fetchone()
        self.changes['before']['schema_version'] = schema_ver[0] if schema_ver else "unknown"

        conn.close()

    def capture_after_state(self):
        """捕获巩固后的状态"""
        print("📊 捕获巩固后状态...")

        conn = sqlite3.connect(_MEMORY_ROOT / "data" / "memory.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 体验统计
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN L1_text IS NOT NULL THEN 1 ELSE 0 END) as l1_count,
                SUM(CASE WHEN L2_text IS NOT NULL THEN 1 ELSE 0 END) as l2_count,
                SUM(CASE WHEN importance IS NOT NULL THEN 1 ELSE 0 END) as importance_count,
                SUM(CASE WHEN consolidated = 1 THEN 1 ELSE 0 END) as consolidated_count
            FROM experiences
        """)
        exp_stats = cursor.fetchone()
        self.changes['after']['experiences'] = dict(exp_stats)

        # 实体统计
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT name) as unique_names
            FROM entities
        """)
        entity_stats = cursor.fetchone()
        self.changes['after']['entities'] = dict(entity_stats)

        # 实体边统计
        cursor.execute("SELECT COUNT(*) as total FROM entity_edges")
        edge_stats = cursor.fetchone()
        self.changes['after']['entity_edges'] = dict(edge_stats)

        # 体验边统计
        cursor.execute("SELECT COUNT(*) as total FROM experience_edges")
        exp_edge_stats = cursor.fetchone()
        self.changes['after']['experience_edges'] = dict(exp_edge_stats)

        # 计算差值
        self.calculate_deltas()

        conn.close()

    def calculate_deltas(self):
        """计算前后差异"""
        for key in ['experiences', 'entities', 'entity_edges', 'experience_edges']:
            if key in self.changes['before'] and key in self.changes['after']:
                before = self.changes['before'][key]
                after = self.changes['after'][key]
                deltas = {}

                for sub_key in after.keys():
                    if sub_key in before:
                        delta = after[sub_key] - before[sub_key]
                        if delta != 0:
                            deltas[sub_key] = delta

                if deltas:
                    self.changes['deltas'][key] = deltas

    def generate_detailed_report(self, consolidation_results):
        """生成详细的巩固报告"""
        output = []
        output.append("=" * 100)
        output.append("全量巩固详细报告")
        output.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("=" * 100)
        output.append("")

        # 时间统计
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            output.append("⏱️ 执行时间")
            output.append("-" * 100)
            output.append(f"  总耗时: {duration:.2f} 秒")
            output.append("")

        # 统计对比
        output.append("📊 巩固前后对比")
        output.append("=" * 100)

        for key in ['experiences', 'entities', 'entity_edges', 'experience_edges']:
            if key in self.changes['before'] and key in self.changes['after']:
                output.append(f"\n【{key.upper()}】")
                before = self.changes['before'][key]
                after = self.changes['after'][key]

                for sub_key in sorted(before.keys()):
                    before_val = before[sub_key]
                    after_val = after[sub_key]
                    delta = after_val - before_val
                    delta_str = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
                    output.append(f"  • {sub_key}: {before_val} → {after_val}{delta_str}")

        # 差异总结
        if self.changes['deltas']:
            output.append("\n")
            output.append("🔑 关键变化")
            output.append("-" * 100)

            for key, deltas in self.changes['deltas'].items():
                output.append(f"\n【{key.upper()}】")
                for sub_key, delta in deltas.items():
                    status = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
                    output.append(f"  {status} {sub_key}: {delta:+d}")

        output.append("")

        # Phase 1 任务详情
        if 'phase1' in consolidation_results:
            output.append("🔧 Phase 1: 六项并行任务详情")
            output.append("=" * 100)

            phase1 = consolidation_results['phase1']

            # L1/L2深层提取
            if 'l1l2_extraction' in phase1:
                l1l2 = phase1['l1l2_extraction']
                output.append("\n【L1/L2深层提取】")
                output.append(f"  处理体验数: {l1l2.get('processed_count', 0)}")
                output.append(f"  L1生成数: {l1l2.get('l1_count', 0)}")
                output.append(f"  L2生成数: {l1l2.get('l2_count', 0)}")
                output.append(f"  状态: {l1l2.get('status', 'unknown')}")

            # 重要性估值
            if 'importance_calculation' in phase1:
                importance = phase1['importance_calculation']
                output.append("\n【重要性估值】")
                output.append(f"  估值体验数: {importance.get('evaluated_count', 0)}")
                output.append(f"  高重要性(>0.7): {importance.get('high_importance_count', 0)}")
                output.append(f"  平均重要性: {importance.get('avg_importance', 0):.3f}")
                output.append(f"  状态: {importance.get('status', 'unknown')}")

            # 隐性边发现
            if 'implicit_edges' in phase1:
                edges = phase1['implicit_edges']
                output.append("\n【隐性边发现】")
                output.append(f"  发现边数: {edges.get('discovered_count', 0)}")
                output.append(f"  创建边数: {edges.get('created_count', 0)}")
                output.append(f"  状态: {edges.get('status', 'unknown')}")

                # 详细边信息
                if 'edges' in edges and edges['edges']:
                    output.append(f"  边详情:")
                    for edge in edges['edges'][:10]:  # 只显示前10条
                        output.append(f"      • {edge.get('from_entity')} → {edge.get('to_entity')} ({edge.get('relation')})")
                    if len(edges['edges']) > 10:
                        output.append(f"      ... 还有 {len(edges['edges']) - 10} 条边")

            # 属性升级（Phase 15新功能）
            if 'property_upgrade' in phase1:
                upgrade = phase1['property_upgrade']
                output.append("\n【属性升级扫描】(Phase 15新功能)")
                output.append(f"  扫描实体数: {upgrade.get('evaluated_count', 0)}")
                output.append(f"  升级实体数: {upgrade.get('upgraded_count', 0)}")
                output.append(f"  跳过实体数: {upgrade.get('skipped_count', 0)}")
                output.append(f"  状态: {upgrade.get('status', 'unknown')}")

                # 详细升级信息
                if 'upgrades' in upgrade and upgrade['upgrades']:
                    output.append(f"  升级详情:")
                    for upg in upgrade['upgrades'][:10]:  # 只显示前10条
                        output.append(f"      • {upg.get('entity_name')}: {upg.get('property_name')} = {upg.get('new_value')}")
                    if len(upgrade['upgrades']) > 10:
                        output.append(f"      ... 还有 {len(upgrade['upgrades']) - 10} 项升级")

            # 信息验证
            if 'verification' in phase1:
                verify = phase1['verification']
                output.append("\n【信息验证】")
                output.append(f"  验证体验数: {verify.get('verified_count', 0)}")
                output.append(f"  通过验证: {verify.get('passed_count', 0)}")
                output.append(f"  标记可疑: {verify.get('flagged_count', 0)}")
                output.append(f"  状态: {verify.get('status', 'unknown')}")

            # 情感时间线更新
            if 'emotion_timeline' in phase1:
                emotion = phase1['emotion_timeline']
                output.append("\n【情感时间线更新】")
                output.append(f"  更新体验数: {emotion.get('updated_count', 0)}")
                output.append(f"  状态: {emotion.get('status', 'unknown')}")

        output.append("")

        # Phase 2: 衰减计算
        if 'phase2' in consolidation_results:
            output.append("📉 Phase 2: 衰减计算")
            output.append("=" * 100)

            phase2 = consolidation_results['phase2']
            output.append(f"  计算节点数: {phase2.get('calculated_count', 0)}")
            output.append(f"  更新边数: {phase2.get('edge_count', 0)}")
            output.append(f"  更新节点数: {phase2.get('node_count', 0)}")
            output.append(f"  休眠节点数: {phase2.get('dormant_count', 0)}")
            output.append(f"  参数: lambda={phase2.get('lambda', 0):.3f}, alpha={phase2.get('alpha', 0):.3f}")
            output.append(f"  状态: {phase2.get('status', 'unknown')}")

        output.append("")

        # Phase 3: 梦境模块
        if 'phase3' in consolidation_results:
            output.append("🌙 Phase 3: 梦境模块")
            output.append("=" * 100)

            phase3 = consolidation_results['phase3']

            if phase3.get('status') == 'skipped':
                output.append(f"  状态: {phase3.get('reason', 'skipped')}")
            else:
                # 重组任务
                if 'reorganize' in phase3:
                    reorg = phase3['reorganize']
                    output.append(f"\n【重组任务】")
                    output.append(f"  处理节点数: {reorg.get('processed_count', 0)}")
                    output.append(f"  重组节点数: {reorg.get('reorganized_count', 0)}")
                    output.append(f"  状态: {reorg.get('status', 'unknown')}")

                # 情感任务
                if 'emotion' in phase3:
                    emotion = phase3['emotion']
                    output.append(f"\n【情感任务】")
                    output.append(f"  处理节点数: {emotion.get('processed_count', 0)}")
                    output.append(f"  更新情感数: {emotion.get('updated_count', 0)}")
                    output.append(f"  状态: {emotion.get('status', 'unknown')}")

                # 扭曲任务
                if 'distort' in phase3:
                    distort = phase3['distort']
                    output.append(f"\n【扭曲任务】")
                    output.append(f"  处理节点数: {distort.get('processed_count', 0)}")
                    output.append(f"  扭曲节点数: {distort.get('distorted_count', 0)}")
                    output.append(f"  状态: {distort.get('status', 'unknown')}")

                # 模拟任务
                if 'simulate' in phase3:
                    simulate = phase3['simulate']
                    output.append(f"\n【模拟任务】")
                    output.append(f"  采样节点数: {simulate.get('sampled_count', 0)}")
                    output.append(f"  创建节点数: {simulate.get('created_count', 0)}")
                    output.append(f"  状态: {simulate.get('status', 'unknown')}")

        output.append("")

        # 档案更新
        if 'profile_update' in consolidation_results:
            output.append("👤 个人档案更新")
            output.append("=" * 100)

            profile = consolidation_results['profile_update']
            output.append(f"  状态: {profile.get('status', 'unknown')}")

            if profile.get('status') == 'completed':
                output.append(f"  更新档案数: {profile.get('updated_count', 0)}")
            elif profile.get('status') == 'failed':
                output.append(f"  错误: {profile.get('error', 'unknown error')}")

        output.append("")
        output.append("=" * 100)
        output.append("报告结束")
        output.append("=" * 100)

        return '\n'.join(output)


def run_full_consolidation():
    """执行全量巩固并生成报告"""
    print("=" * 100)
    print("🚀 开始全量巩固")
    print("=" * 100)
    print()

    # 创建报告器
    reporter = ConsolidationReporter()

    # 捕获巩固前状态
    reporter.capture_before_state()

    # 创建巩固pipeline
    print("🔧 初始化巩固Pipeline...")
    pipeline = ConsolidationPipeline()

    # 执行全量巩固
    print()
    print("🔄 执行全量巩固...")
    print("  • Phase 1: 六项并行任务")
    print("  • Phase 2: 衰减计算")
    print("  • Phase 3: 梦境模块（重组、情感、扭曲、模拟）")
    print()

    reporter.start_time = datetime.now()

    try:
        results = pipeline.run_consolidation(mode="full")
    except Exception as e:
        print(f"❌ 巩固失败: {e}")
        import traceback
        traceback.print_exc()
        return

    reporter.end_time = datetime.now()

    # 捕获巩固后状态
    reporter.capture_after_state()

    # 生成报告
    print()
    print("📝 生成详细报告...")

    report = reporter.generate_detailed_report(results)

    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"✅ 报告已写入: {OUTPUT_FILE}")
    print()

    # 打印关键结果到控制台
    print("=" * 100)
    print("📊 巩固结果摘要")
    print("=" * 100)

    if 'deltas' in reporter.changes and reporter.changes['deltas']:
        for key, deltas in reporter.changes['deltas'].items():
            print(f"\n【{key.upper()}】")
            for sub_key, delta in deltas.items():
                print(f"  • {sub_key}: {delta:+d}")

    print()
    print("✅ 全量巩固完成！")
    print(f"📄 详细报告: {OUTPUT_FILE}")


if __name__ == "__main__":
    run_full_consolidation()
