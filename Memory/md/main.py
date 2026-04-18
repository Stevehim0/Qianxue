"""记忆系统主入口。

此脚本验证项目结构和配置。
运行此脚本可检查系统是否正确设置。
"""

import sys
from pathlib import Path

# 确保可以从 Memory/ 目录导入自身包
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_project_structure() -> bool:
    """检查所有必需的目录是否存在。"""
    base = Path(__file__).parent
    required_dirs = [
        "config",
        "config/prompts",
        "core",
        "core_text",
        "storage",
        "embedding",
        "llm",
        "writer",
        "recall",
        "consolidator",
        "consolidator/tasks",
        "state",
        "api",
        "tests",
        "data",
    ]

    missing = []
    for dir_path in required_dirs:
        if not (base / dir_path).exists():
            missing.append(dir_path)

    if missing:
        print("缺少以下目录：")
        for d in missing:
            print(f"   - {d}")
        return False

    print("所有必需的目录都存在")
    return True


def check_config() -> bool:
    """检查配置是否可以加载。"""
    try:
        from Memory.config.settings import settings

        if not settings.models.llm_api_key:
            print("LLM_API_KEY 未设置")
            print("   请创建 .env 文件并设置：LLM_API_KEY=your_key_here")
            return False

        print("配置加载成功")
        return True
    except ImportError as e:
        print(f"无法导入配置：{e}")
        return False
    except Exception as e:
        print(f"配置错误：{e}")
        return False


def check_prompt_templates() -> bool:
    """检查 prompt 模板文件是否存在。"""
    required_templates = [
        "write_L0_summary.txt",
        "write_entity_recognize.txt",
        "write_emotion_snapshot.txt",
        "recall_filter.txt",
        "consolid_l1l2.txt",
        "consolid_implicit_edges.txt",
        "consolid_property_upgrade.txt",
        "consolid_info_verify.txt",
        "consolid_emotion_timeline.txt",
        "dream_system.txt",
        "dream_reorganize.txt",
        "dream_emotion.txt",
        "dream_distort.txt",
        "dream_simulate.txt",
    ]

    prompts_dir = Path(__file__).parent / "config" / "prompts"
    missing = []
    for template in required_templates:
        if not (prompts_dir / template).exists():
            missing.append(template)

    if missing:
        print("缺少以下 prompt 模板：")
        for t in missing:
            print(f"   - {t}")
        return False

    print(f"所有 {len(required_templates)} 个 prompt 模板都存在")
    return True


def check_core_identity() -> bool:
    """检查核心人设文件是否存在。"""
    identity_path = Path(__file__).parent / "core_text" / "identity.md"
    if not identity_path.exists():
        print("未找到核心人设文件：core_text/identity.md")
        return False

    print("核心人设文件存在")
    return True


def print_config_summary():
    """打印当前配置的摘要。"""
    try:
        from Memory.config.settings import settings

        summary = settings.get_summary()

        print("\n" + "=" * 50)
        print("配置摘要")
        print("=" * 50)

        print("\n[数据库]")
        print(f"  数据库路径: {summary['database']['db_path']}")
        print(f"  ChromaDB: {summary['database']['chroma_persist_dir']}")

        print("\n[模型]")
        print(f"  Embedding 模型: {summary['models']['embedding_model']}")
        print(f"  LLM 提供商: {summary['models']['llm_provider']}")
        print(f"  API 密钥: {summary['models']['llm_api_key']}")
        print(f"  基础 URL: {summary['models']['llm_base_url']}")

        print("\n[衰减参数]")
        print(f"  Lambda L0: {summary['decay']['lambda_L0']}")
        print(f"  Lambda L3: {summary['decay']['lambda_L3']}")
        print(f"  Alpha: {summary['decay']['alpha']}")
        print(f"  Beta: {summary['decay']['beta']}")

        print("\n[作息时间]")
        print(f"  入睡时间: {summary['schedule']['sleep_time']}")
        print(f"  起床时间: {summary['schedule']['wake_time']}")
        print(f"  时区: {summary['schedule']['timezone']}")

        print("\n[召回]")
        print(f"  Top-K: {summary['recall']['default_top_k']}")
        print(f"  相似度阈值: {summary['recall']['similarity_threshold']}")
        print(f"  最大跳数: {summary['recall']['max_hop_depth']}")

        print("=" * 50 + "\n")
    except Exception as e:
        print(f"无法打印配置摘要：{e}")


def main():
    """主入口。"""
    print("=" * 50)
    print("记忆系统 - 结构验证")
    print("=" * 50 + "\n")

    all_passed = True

    if not check_project_structure():
        all_passed = False

    if not check_config():
        all_passed = False

    if not check_prompt_templates():
        all_passed = False

    if not check_core_identity():
        all_passed = False

    if all_passed:
        print_config_summary()
        print("所有检查通过！系统已准备就绪。\n")
        return 0
    else:
        print("\n部分检查失败，请修复上述问题。\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
