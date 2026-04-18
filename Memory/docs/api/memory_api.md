# MemoryAPI 参考文档

## 概述

MemoryAPI 是记忆系统的统一接口（Facade Pattern），封装了写入层、巩固层、召回层、状态层、核心层的所有功能，提供简洁易用的 API。

## 初始化

### MemoryAPI()

自动初始化所有层，无需传入参数。

```python
from Memory.api import MemoryAPI

api = MemoryAPI()
```

**说明：**
- 自动加载配置文件（Memory/config/settings.py）
- 初始化数据库连接
- 初始化向量库（ChromaDB）
- 初始化 LLM 客户端
- 创建所有 Pipeline 和 Manager 实例

## API 方法

### 1. receive_event()

记录对话事件到记忆系统。

**签名：**
```python
def receive_event(self, role: str, content: str, **kwargs) -> str
```

**参数：**
- `role` (str): 角色，可选值："user" | "assistant" | "system"
- `content` (str): 事件内容（对话文本）
- `**kwargs`: 可选上下文参数

**返回：**
- `str`: 体验节点 ID，格式：`exp_YYYYMMDD_HHmmss`

**异常：**
- `InputError`: 输入参数无效（role 或 content 为空）
- `MemoryAPIError`: 写入失败

**示例：**
```python
# 记录用户消息
exp_id = api.receive_event(role="user", content="我叫张三，是一名程序员")
print(f"Recorded: {exp_id}")

# 记录助手回复
api.receive_event(role="assistant", content="你好张三，很高兴认识你")
```

### 2. check_recall()

检查是否需要召回，触发则返回召回结果。

**签名：**
```python
def check_recall(self, query: str, context: dict) -> List[RecallResult]
```

**参数：**
- `query` (str): 用户查询文本
- `context` (dict): 上下文字典
  - `recent_history` (list): 最近对话历史
  - `ai_state` (dict): AI 当前状态
  - `current_time` (str): 当前时间（可选）

**返回：**
- `List[RecallResult]`: 召回结果列表，按激活分数降序排序
  - 每个 RecallResult 包含：
    - `experience_id`: 体验节点 ID
    - `text`: 召回文本（L0 或 L1）
    - `score`: 激活分数
    - `metadata`: 元数据（时间、实体等）

**异常：**
- `InputError`: 输入参数无效
- `RecallError`: 召回操作失败

**示例：**
```python
# 召回相关记忆
recalls = api.check_recall(
    query="张三是做什么的？",
    context={"recent_history": []}
)

for recall in recalls:
    print(f"[{recall.score:.2f}] {recall.text}")
```

### 3. expand_depth()

按需展开体验节点的深层内容。

**签名：**
```python
def expand_depth(self, experience_id: str) -> Dict[str, str]
```

**参数：**
- `experience_id` (str): 体验节点 ID

**返回：**
- `Dict[str, str]`: 包含 L0/L1/L2/L3 的字典，不存在则为 None
  - `L0`: L0 摘要（第一人称主观视角）
  - `L1`: L1 深层内容（关键信息提取）
  - `L2`: L2 结构化内容（事实性知识）
  - `L3`: L3 原始记录（完整对话）

**异常：**
- `InputError`: 节点 ID 无效或节点不存在
- `RecallError`: 展开操作失败

**示例：**
```python
# 展开记忆层次
depth = api.expand_depth("exp_20260331_120000")
print(f"L0: {depth['L0']}")
print(f"L1: {depth['L1']}")
print(f"L3: {depth['L3']}")
```

### 4. load_core()

加载核心层人设和锚点。

**签名：**
```python
def load_core(self) -> Dict[str, Any]
```

**返回：**
- `Dict[str, Any]`: 核心层信息
  - `identity_text`: 核心层自述文本
  - `anchors`: 解析后的锚点
    - `values`: 价值观排序
    - `bottom_lines`: 底线列表
    - `style_keywords`: 风格关键词

**异常：**
- `CoreError`: 核心层加载失败

**示例：**
```python
core = api.load_core()
print(f"Values: {core['anchors']['values']}")
print(f"Bottom lines: {core['anchors']['bottom_lines']}")
```

### 5. check_filter()

执行核心层阀门过滤。

**签名：**
```python
def check_filter(self, request: str) -> Dict[str, Any]
```

**参数：**
- `request` (str): 用户请求文本

**返回：**
- `Dict[str, Any]`: 过滤结果
  - `passed` (bool): 是否通过过滤
  - `reason` (str | None): 未通过的原因

**异常：**
- `InputError`: 输入参数无效
- `CoreError`: 过滤检查失败

**示例：**
```python
result = api.check_filter("帮我写一段代码")
if result['passed']:
    print("请求通过过滤")
else:
    print(f"请求被过滤: {result['reason']}")
```

### 6. get_state_prompt()

获取当前状态的 prompt 注入文本。

**签名：**
```python
def get_state_prompt(self) -> str
```

**返回：**
- `str`: 格式化的状态提示文本，包含 mood/energy/focus/confidence

**异常：**
- `StateError`: 状态读取失败

**示例：**
```python
state_prompt = api.get_state_prompt()
print(f"当前状态: {state_prompt}")
```

### 7. load_profile()

加载指定人的个人档案。

**签名：**
```python
def load_profile(self, entity_name: str) -> Optional[Dict[str, Any]]
```

**参数：**
- `entity_name` (str): 实体名称（人名）

**返回：**
- `Dict[str, Any] | None`: 个人档案字典，不存在则返回 None
  - `basic`: 基本信息（姓名、类型、首次见面时间）
  - `interaction_style`: 相处方式（第一版占位）
  - `preferences`: 偏好（第一版占位）
  - `metadata`: 元信息

**异常：**
- `InputError`: 输入参数无效
- `RecallError`: 档案加载失败

**示例：**
```python
profile = api.load_profile("张三")
if profile:
    print(f"Type: {profile['basic']['type']}")
    print(f"First seen: {profile['basic']['first_seen']}")
else:
    print("Profile not found")
```

### 8. run_consolidation()

手动触发一次巩固处理。

**签名：**
```python
def run_consolidation(self, mode: str = "incremental") -> Dict[str, Any]
```

**参数：**
- `mode` (str): 巩固模式，可选值："incremental" | "full"
  - "incremental": 增量巩固，处理未巩固的节点
  - "full": 全量巩固，处理最近 7 天的所有节点（包含梦境模块）

**返回：**
- `Dict[str, Any]`: 巩固结果
  - `processed_count`: 处理的节点数
  - `mode`: 使用的模式
  - `duration`: 处理时长（秒）

**异常：**
- `InputError`: 模式参数无效
- `ConsolidationError`: 巩固处理失败

**示例：**
```python
# 增量巩固
result = api.run_consolidation(mode="incremental")
print(f"Processed {result['processed_count']} nodes")

# 全量巩固（包含梦境模块）
result = api.run_consolidation(mode="full")
print(f"Full consolidation took {result['duration']:.2f}s")
```

### 9. get_status()

获取系统状态。

**签名：**
```python
def get_status(self) -> Dict[str, Any]
```

**返回：**
- `Dict[str, Any]`: 系统统计信息
  - `total_experiences`: 总体验节点数
  - `total_entities`: 总实体数
  - `total_edges`: 总边数
  - `last_consolidation`: 最后巩固时间
  - `database_path`: 数据库路径

**示例：**
```python
status = api.get_status()
print(f"Experiences: {status['total_experiences']}")
print(f"Entities: {status['total_entities']}")
print(f"Edges: {status['total_edges']}")
print(f"Database: {status['database_path']}")
```

## 异常处理

MemoryAPI 使用自定义异常类层次提供清晰的错误分类：

### 异常类

- `MemoryAPIError`: 所有 API 错误的基类
- `InputError`: 输入参数无效
- `RecallError`: 召回操作失败
- `ConsolidationError`: 巩固操作失败
- `StateError`: 状态操作失败
- `CoreError`: 核心层操作失败

### 异常处理示例

```python
from Memory.api import MemoryAPI, InputError, RecallError

api = MemoryAPI()

try:
    exp_id = api.receive_event(role="user", content="测试消息")
except InputError as e:
    print(f"输入错误: {e}")
except RecallError as e:
    print(f"召回错误: {e}")
except MemoryAPIError as e:
    print(f"API 错误: {e}")
```

## 完整示例

```python
from Memory.api import MemoryAPI

# 初始化
api = MemoryAPI()

# 记录对话
api.receive_event("user", "我叫李四，在上海工作")
api.receive_event("assistant", "记住了，你在上海工作")
api.receive_event("user", "我是一名设计师，喜欢摄影")

# 触发巩固
api.run_consolidation(mode="incremental")

# 召回记忆
recalls = api.check_recall(
    query="李四是什么工作？",
    context={"recent_history": []}
)

for recall in recalls:
    print(f"[{recall.score:.2f}] {recall.text}")

# 查看系统状态
status = api.get_status()
print(f"Total experiences: {status['total_experiences']}")
```

## 注意事项

1. **自动初始化**: MemoryAPI() 无需传入参数，自动加载配置和初始化所有组件
2. **异常风格**: 所有错误通过异常抛出，成功时返回结果
3. **线程安全**: MemoryAPI 实例不是线程安全的，多线程环境需要使用锁
4. **数据库路径**: 默认使用 `data/memory.db`，可通过 `settings.database.path` 修改
5. **LLM 调用**: 首次调用会下载 Embedding 模型（约 400MB），需要网络连接
6. **核心层过滤**: `check_filter()` 第一版为占位实现，总是返回 True
7. **个人档案**: `load_profile()` 第一版只返回基本信息，完整档案系统后续实现
8. **梦境模块**: 只有在 `mode="full"` 时才会执行梦境模块
9. **状态层**: `get_state_prompt()` 返回当前四变量状态，影响 AI 输出姿态
10. **L3 不可变**: `expand_depth()` 返回的 L3 是原始记录，永远不可修改
