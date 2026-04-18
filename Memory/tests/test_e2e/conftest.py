"""端到端测试专用 fixtures。"""

import pytest
import tempfile
import shutil
from pathlib import Path
from Memory.api import MemoryAPI
from Memory.config.settings import settings


@pytest.fixture(scope="function")
def real_api():
    """使用真实 LLM 的 MemoryAPI 实例。

    每个测试函数使用独立的临时数据库，测试后自动清理。
    """
    # 创建临时数据库
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test_memory.db"

    # 临时覆盖配置
    original_db_path = settings.database.db_path
    settings.database.db_path = temp_db_path

    # 创建 API 实例（自动初始化）
    api = MemoryAPI()

    yield api

    # 清理：关闭数据库连接，删除临时文件
    settings.database.db_path = original_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def clean_database(real_api):
    """提供干净的数据库环境。

    在每个测试后清理数据，确保测试隔离。
    """
    yield real_api
    # 测试结束后自动清理（通过 real_api fixture 的 teardown）


@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录路径。"""
    return Path(__file__).parent / "data"
