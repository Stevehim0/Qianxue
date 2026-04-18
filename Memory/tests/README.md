# LLM服务测试文档

本目录包含LLM客户端服务的完整测试套件，包括单元测试、集成测试和端到端测试。

## 测试文件概览

### 单元测试

- **test_llm_utils.py** - 工具函数测试
  - `parse_json()` - JSON解析（标准格式、markdown包裹、错误处理）
  - `with_retry()` - 指数退避重试装饰器
  - `log_llm_error()` - 错误日志记录
  - `setup_error_logger()` - 日志配置

- **test_llm_base.py** - LLM客户端基类测试
  - `BaseLLMClient` - 抽象基类
  - `call_with_retry()` - 带重试机制的调用
  - 参数传递验证
  - 错误处理逻辑

- **test_qianwen_client.py** - 千问客户端测试
  - `QianwenClient` - 千问API客户端
  - HTTP请求构造
  - 响应解析
  - 错误处理

- **test_deepseek_client.py** - DeepSeek客户端测试
  - `DeepSeekClient` - DeepSeek API客户端
  - OpenAI SDK调用
  - 参数传递
  - 错误处理

- **test_llm_factory.py** - LLM工厂测试
  - `LLMFactory` - 工厂类
  - 客户端创建
  - 提供商切换
  - 参数传递

### 集成测试

- **test_llm_integration.py** - 真实API集成测试
  - 需要真实API密钥才能运行
  - 默认跳过，通过环境变量启用
  - 测试端到端的LLM调用流程

## 运行测试

### 运行所有单元测试（不需要API密钥）

```bash
# 运行所有单元测试
pytest tests/ -v

# 只运行LLM相关测试
pytest tests/test_llm_*.py -v

# 运行特定测试文件
pytest tests/test_llm_utils.py -v

# 运行特定测试函数
pytest tests/test_llm_utils.py::TestParseJson::test_parse_standard_json -v
```

### 运行集成测试（需要API密钥）

```bash
# 设置环境变量
export REAL_API_TEST=true
export LLM_API_KEY="your-qianwen-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"

# 运行所有测试（包括集成测试）
pytest tests/ -v

# 只运行集成测试
pytest tests/test_llm_integration.py -v

# 运行特定的集成测试
pytest tests/test_llm_integration.py::TestQianwenIntegration::test_qianwen_simple_call -v
```

### 查看测试覆盖率

```bash
# 生成HTML覆盖率报告
pytest tests/ --cov=llm --cov-report=html

# 查看终端覆盖率报告
pytest tests/ --cov=llm --cov-report=term-missing

# 生成XML覆盖率报告（用于CI/CD）
pytest tests/ --cov=llm --cov-report=xml
```

覆盖率报告将生成在 `htmlcov/` 目录下，打开 `htmlcov/index.html` 查看详细报告。

## 测试组织结构

```
tests/
├── conftest.py                 # Pytest配置和共享fixtures
├── test_llm_utils.py           # 工具函数测试
├── test_llm_base.py            # 基类测试
├── test_qianwen_client.py      # 千问客户端测试
├── test_deepseek_client.py     # DeepSeek客户端测试
├── test_llm_factory.py         # 工厂类测试
├── test_llm_integration.py     # 集成测试（真实API）
└── README.md                   # 本文档
```

## 测试覆盖率目标

| 模块 | 目标覆盖率 | 当前覆盖率 |
|------|-----------|-----------|
| utils.py | 90% | 待测试 |
| base.py | 85% | 待测试 |
| qianwen_client.py | 85% | 待测试 |
| deepseek_client.py | 85% | 待测试 |
| factory.py | 90% | 待测试 |

## 测试最佳实践

### 1. 使用Mock避免真实API调用

单元测试使用 `unittest.mock` 模拟HTTP请求和API响应，确保测试快速且不消耗API配额。

```python
@patch('Memory.llm.qianwen_client.requests.post')
def test_successful_call(mock_post):
    # 配置mock响应
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {...}
    mock_post.return_value = mock_response

    # 测试代码
    client = QianwenClient(api_key="test-key")
    result = client.call("Test prompt")

    # 验证结果
    assert result == {...}
```

### 2. 使用Fixtures管理测试资源

使用 `pytest.fixture` 创建可重用的测试资源，避免重复代码。

```python
@pytest.fixture
def tmp_log_dir(tmp_path):
    """创建临时日志目录。"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
```

### 3. 测试异常路径

确保测试所有可能的错误场景，不只是成功路径。

```python
def test_http_404_error():
    """测试HTTP 404错误处理。"""
    # Mock 404响应
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = HTTPError("404 Not Found")

    # 验证异常被正确抛出
    with pytest.raises(HTTPError):
        client.call("Test prompt")
```

### 4. 使用描述性测试名称

测试名称应该清楚描述测试的内容和期望。

```python
# 好的测试名称
def test_parse_markdown_wrapped_json():
    """测试解析markdown代码块包裹的JSON。"""

# 不好的测试名称
def test_json_1():
```

## 持续集成（CI/CD）

测试套件设计为在CI/CD环境中运行：

```yaml
# .github/workflows/test.yml 示例
- name: Run unit tests
  run: pytest tests/ -v --cov=Memory.llm --cov-report=xml

- name: Run integration tests
  env:
    REAL_API_TEST: true
    LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
  run: pytest tests/test_llm_integration.py -v
```

## 常见问题

### Q: 为什么有些测试默认被跳过？

A: 集成测试需要真实的API密钥，为了避免在CI/CD中失败，这些测试默认被跳过。设置 `REAL_API_TEST=true` 环境变量来运行它们。

### Q: 如何只运行特定类型的测试？

A: 使用pytest标记：
```bash
# 只运行集成测试
pytest -m integration

# 只运行单元测试（不包含integration标记）
pytest -m "not integration"
```

### Q: 测试失败了怎么办？

A:
1. 检查是否是网络问题（集成测试）
2. 确认API密钥配置正确
3. 查看详细的错误信息：`pytest -v`
4. 运行单个测试文件隔离问题

### Q: 如何添加新的测试？

A:
1. 在相应的测试文件中添加测试函数
2. 使用 `test_` 前缀命名测试函数
3. 添加描述性的文档字符串
4. 运行 `pytest` 验证新测试通过

## 测试数据说明

测试使用的数据位于 `conftest.py` 的 `sample_llm_responses` fixture中：

```python
@pytest.fixture
def sample_llm_responses():
    return {
        "json_response": '{"city": "北京", "temperature": 25}',
        "markdown_json": '```json\n{"city": "北京"}\n```',
        "text_response": "这是一段普通文本响应。",
        # ...
    }
```

## 贡献指南

添加新测试时，请确保：

1. 测试名称清晰描述测试内容
2. 添加文档字符串说明测试目的
3. 使用适当的fixtures和mock
4. 测试独立运行，不依赖其他测试
5. 达到或超过覆盖率目标

## 参考资源

- [Pytest文档](https://docs.pytest.org/)
- [unittest.mock文档](https://docs.python.org/3/library/unittest.mock.html)
- [pytest-cov文档](https://pytest-cov.readthedocs.io/)
- [项目LLM实现文档](../../Memory/LLM调用设计-千问.md)
