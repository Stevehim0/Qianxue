# 记忆系统API接口文档

**系统:** Qianxue-master (AI Agent仿人类记忆系统)
**文档版本:** 2.1
**最后更新:** 2026-04-12

---

## 📋 目录

1. [MemoryAPI层 - 统一接口层](#1-memoryapi层---统一接口层)
2. [WriterPipeline层 - 写入层](#2-writerpipeline层---写入层)
3. [ConsolidationPipeline层 - 巩固层](#3-consolidationpipeline层---巩固层)
4. [RecallManager层 - 召回层](#4-recallmanager层---召回层)
5. [Storage层 - 存储层](#5-storage层---存储层)
6. [State层 - 状态层](#6-state层---状态层)
7. [Core层 - 核心层](#7-core层---核心层)
8. [异常处理](#8-异常处理)
9. [使用示例](#9-使用示例)

---

## 1. MemoryAPI层 - 统一接口层

**位置:** `Memory/api/memory_api.py`
**作用:** 对外统一接口，封装所有层的功能
**使用场景:** 一般应用开发，主要使用此层的接口

### 1.1 初始化接口

#### `MemoryAPI.__init__()`
**功能:** 创建MemoryAPI实例，自动初始化所有层
**返回:** MemoryAPI实例
**用法:**
```python
from Memory.api.memory_api import MemoryAPI
api = MemoryAPI()
```

---

### 1.2 事件记录接口

#### `MemoryAPI.receive_event(role, content, **kwargs)`
**功能:** 记录用户对话事件
**层归属:** 调用WriterPipeline层
**参数:**
- `role` (str): "user"或"assistant"
- `content` (str): 对话内容
- `**kwargs`: 可选参数，如timestamp
**返回:** str - 体验ID (exp_YYYYMMDD_HHmmss)
**用法:**
```python
exp_id = api.receive_event(role="user", content="My name is Alice")
```

---

### 1.3 记忆召回接口

#### `MemoryAPI.check_recall(query, context)`
**功能:** 根据查询召回相关记忆（原有接口，触发检测+关键词提取）
**层归属:** 调用RecallManager层
**参数:**
- `query` (str): 用户查询
- `context` (dict): 上下文信息
  - `recent_history`: 最近对话历史
  - `ai_state`: AI当前状态
  - `current_time`: 当前时间
  - `profiles_to_load`: 要加载的档案（可选）
**返回:** List[RecallResult] - 召回结果列表
**用法:**
```python
recalls = api.check_recall(
    query="Alice是做什么的？",
    context={"recent_history": ["Tell me about Alice"]}
)
```

#### `MemoryAPI.recall_by_keywords(query, context)` *(新增 v2.1)*
**功能:** 通过关键词直接召回，跳过触发检测和关键词提取，返回含 briefing 的结果
**层归属:** 调用RecallManager.recall_by_keywords()
**参数:**
- `query` (str): 关键词字符串（空格或逗号分隔，如 "张三 天气" 或 "生日,爱好"）
- `context` (dict): 上下文信息（同 check_recall）
**返回:** dict - `{"experiences": [], "entities": [], "briefing": str|None}`
**与 check_recall 的区别:**
- check_recall: 输入完整句子 → 触发检测 → 关键词提取 → 双轨召回
- recall_by_keywords: 输入关键词 → 直接双轨召回（跳过检测和提取）
**用法:**
```python
result = api.recall_by_keywords(
    query="张三 天气",
    context={"recent_history": [], "ai_state": {}}
)
briefing = result["briefing"]  # 自然语言简报
```

#### `MemoryAPI.expand_depth(experience_id)`
**功能:** 按需展开记忆的深层内容（L1/L2/L3）
**层归属:** 调用RecallManager层
**参数:**
- `experience_id` (str): 体验ID
**返回:** Dict[str, str] - 包含L0-L3层内容的字典
**用法:**
```python
depth = api.expand_depth("exp_20260404_120000")
```

---

### 1.4 核心层接口

#### `MemoryAPI.load_core()`
**功能:** 加载AI身份和核心信念
**层归属:** 调用Core层
**返回:** Dict[str, Any] - 核心层数据
**用法:**
```python
core_data = api.load_core()
```

#### `MemoryAPI.check_filter(request)`
**功能:** 检查请求是否违反核心约束
**层归属:** 调用Core层
**参数:**
- `request` (str): 用户请求文本
**返回:** Dict[str, Any] - 过滤结果
**用法:**
```python
result = api.check_filter("假装成人类")
```

---

### 1.5 状态层接口

#### `MemoryAPI.get_state_prompt()`
**功能:** 获取AI当前状态的Prompt格式
**层归属:** 调用State层
**返回:** str - 状态Prompt文本
**用法:**
```python
state_prompt = api.get_state_prompt()
```

---

### 1.6 个人档案接口

#### `MemoryAPI.load_profile(entity_name)`
**功能:** 加载指定人物的个人档案
**层归属:** 调用RecallManager层（ProfileManager）
**参数:**
- `entity_name` (str): 人物名称
**返回:** Optional[Dict[str, Any]] - 档案数据，不存在返回None
**用法:**
```python
profile = api.load_profile("Alice")
```

#### `MemoryAPI.ensure_profile(entity_name)`
**功能:** 确保个人档案存在，不存在则创建（不受 experience 阈值限制）
**层归属:** 调用RecallManager层（ProfileManager）
**参数:**
- `entity_name` (str): 人物名称
**返回:** Optional[Dict[str, Any]] - 档案数据
**触发方式:** 由 Backend 根据对话轮次（10 条消息）触发
**说明:** 不依赖 experience 表积累，只要有对应实体就直接创建

#### `ProfileManager.process_pending_facts(threshold=20)`
**功能:** 从 `profile_pending_facts` 表积累的事实更新个人档案
**参数:**
- `threshold` (int): 触发更新的最小 fact 条数，默认 20
**触发方式:** 由 BufferManager 超时检查循环每 ~10 分钟调用一次
**说明:** 质量检查时顺带提取人物信息存入 `profile_pending_facts`，攒够后合并到档案 notes

---

### 1.7 巩固接口

#### `MemoryAPI.run_consolidation(mode)`
**功能:** 执行记忆巩固流程
**层归属:** 调用ConsolidationPipeline层
**参数:**
- `mode` (str): 巩固模式
  - `"incremental"`: 增量巩固（默认）
  - `"full"`: 全量巩固
  - `"dream"`: 梦境巩固
**返回:** Dict[str, Any] - 巩固结果统计
**用法:**
```python
result = api.run_consolidation(mode="incremental")
```

---

### 1.8 系统状态接口

#### `MemoryAPI.get_status()`
**功能:** 获取系统整体状态
**层归属:** 调用Storage层
**返回:** Dict[str, Any] - 系统状态信息
**用法:**
```python
status = api.get_status()
```

---

## 2. WriterPipeline层 - 写入层

**位置:** `Memory/writer/pipeline.py`
**作用:** 协调事件记录的并行处理流程
**使用场景:** 直接控制事件写入过程，自定义写入逻辑

### 2.1 初始化接口

#### `WriterPipeline.__init__(raw_recorder, llm_client, ...)`
**功能:** 创建WriterPipeline实例
**参数:** 所有参数都是可选的，默认使用全局实例
**返回:** WriterPipeline实例
**用法:**
```python
from Memory.writer.pipeline import WriterPipeline
pipeline = WriterPipeline()
```

---

### 2.2 事件处理接口

#### `WriterPipeline.process_event(role, content, timestamp)`
**功能:** 处理用户事件，执行完整的写入流程
**参数:**
- `role` (str): 用户角色
- `content` (str): 对话内容
- `timestamp` (float): 自定义时间戳（可选）
**返回:** str - 体验ID
**处理流程:**
1. Step 1: 原始记录（生成ID，保存L3层）
2. Step 2: 并行执行三个任务（L0摘要、实体识别、情感分析）
3. Step 3: 创建边（时序边、跨层边）
4. Step 4: 异步触发状态更新
**用法:**
```python
exp_id = pipeline.process_event(role="user", content="今天天气真好")
```

---

### 2.3 内部任务接口（一般不直接调用）

#### `WriterPipeline._generate_l0_task(experience_id, content)`
**功能:** 生成L0摘要和向量（内部任务）
#### `WriterPipeline._recognize_entities_task(experience_id, content)`
**功能:** 识别实体并创建边（内部任务）
#### `WriterPipeline._analyze_emotion_task(experience_id, content)`
**功能:** 分析情感（内部任务）
#### `WriterPipeline._create_edges(experience_id, entity_ids)`
**功能:** 创建时序边和跨层边（内部任务）

---

## 3. ConsolidationPipeline层 - 巩固层

**位置:** `Memory/consolidator/pipeline.py`
**作用:** 协调记忆巩固的并行处理流程
**使用场景:** 手动触发巩固，自定义巩固逻辑

### 3.1 初始化接口

#### `ConsolidationPipeline.__init__(llm_client, embedding_service, ...)`
**功能:** 创建ConsolidationPipeline实例
**参数:** 所有参数都是可选的，默认使用全局实例
**返回:** ConsolidationPipeline实例
**用法:**
```python
from Memory.consolidator.pipeline import ConsolidationPipeline
pipeline = ConsolidationPipeline()
```

---

### 3.2 巩固执行接口

#### `ConsolidationPipeline.run_consolidation(mode, candidates)`
**功能:** 执行记忆巩固流程
**参数:**
- `mode` (str): 巩固模式（"incremental"/"full"/"dream"）
- `candidates` (List[Experience]): 待巩固的体验列表（可选）
**返回:** Dict[str, Any] - 巩固结果统计
**巩固流程:**
1. Phase 1: 六任务并行（L1/L2提取、重要性评估、隐性边发现等）
2. Phase 2: 衰减计算
3. Phase 3: 梦境处理（仅dream模式）
4. Phase 4: 个人档案更新
**用法:**
```python
result = pipeline.run_consolidation(mode="incremental")
```

---

### 3.3 衰减计算接口

#### `ConsolidationPipeline.run_phase2_decay(candidates)`
**功能:** 执行衰减计算任务
**参数:**
- `candidates` (List[Experience]): 待计算衰减的体验列表
**返回:** Dict[str, Any] - 衰减计算结果
**用法:**
```python
result = pipeline.run_phase2_decay(candidates)
```

---

### 3.4 档案更新接口

#### `ConsolidationPipeline.update_profiles(experiences)`
**功能:** 更新相关人物的档案
**参数:**
- `experiences` (List[Experience]): 体验列表
**返回:** None
**用法:**
```python
pipeline.update_profiles(experiences)
```

---

## 4. RecallManager层 - 召回层

**位置:** `Memory/recall/manager.py`
**作用:** 协调记忆召回的完整流程
**使用场景:** 自定义召回逻辑，直接访问召回功能

### 4.1 初始化接口

#### `RecallManager.__init__(experience_store, entity_store, edge_store, ...)`
**功能:** 创建RecallManager实例
**参数:** 需要提供各种Store实例
**返回:** RecallManager实例
**用法:**
```python
from Memory.recall.manager import RecallManager
from Memory.storage.experience_store import experience_store
from Memory.storage.entity_store import entity_store
from Memory.storage.experience_edge_store import experience_edge_store
from Memory.embedding.vector_store import vector_store
from Memory.embedding.model import embedding_service

recall_manager = RecallManager(
    experience_store=experience_store,
    entity_store=entity_store,
    edge_store=experience_edge_store,
    vector_store=vector_store,
    embedding_service=embedding_service
)
```

---

### 4.2 记忆召回接口

#### `RecallManager.recall(query, context)`
**功能:** 执行完整的记忆召回流程（含触发检测）
**参数:**
- `query` (str): 用户查询
- `context` (dict): 上下文信息
**返回:** List[RecallResult] - 召回结果列表
**召回流程:**
1. Step 0: 加载个人档案（如果提供）
2. Step 1: 触发检测
3. Step 2: 关键词提取
4. Step 3: 向量检索
5. Step 4: 激活扩散
6. Step 5: 排序过滤
7. Step 6: 后处理（LLM二分类）
**用法:**
```python
recalls = recall_manager.recall(
    query="Alice的工作是什么？",
    context={"recent_history": ["告诉我关于Alice"]}
)
```

#### `RecallManager.recall_by_keywords(keywords, context)` *(新增 v2.1)*
**功能:** 跳过触发检测，直接用关键词执行双轨召回 + briefing 生成
**参数:**
- `keywords` (List[str]): 关键词列表（调用方已提取好）
- `context` (dict): 上下文信息
**返回:** dict - `{"experiences": [Top3 RecallResult], "entities": [Top15 EntityRecallResult], "briefing": str|None}`
**召回流程:**
1. 体验轨：向量检索 → 扩散1跳 → 合并排序
2. 信息轨：向量检索 → 扩散1跳 → 合并排序
3. 截断：体验 Top3，实体 Top15
4. BriefingGenerator 生成自然语言简报（一次 LLM 调用）
**用法:**
```python
result = recall_manager.recall_by_keywords(
    keywords=["张三", "天气"],
    context={}
)
print(result["briefing"])  # "你记得张三之前说过喜欢晴天..."
```

#### `RecallManager.recall(query, context)`
**功能:** 执行完整的记忆召回流程
**参数:**
- `query` (str): 用户查询
- `context` (dict): 上下文信息
**返回:** List[RecallResult] - 召回结果列表
**召回流程:**
1. Step 0: 加载个人档案（如果提供）
2. Step 1: 触发检测
3. Step 2: 关键词提取
4. Step 3: 向量检索
5. Step 4: 激活扩散
6. Step 5: 排序过滤
7. Step 6: 后处理（LLM二分类）
**用法:**
```python
recalls = recall_manager.recall(
    query="Alice的工作是什么？",
    context={"recent_history": ["告诉我关于Alice"]}
)
```

---

### 4.3 记忆展开接口

#### `RecallManager.expand_memory(memory_id, level)`
**功能:** 展开记忆的深层内容
**参数:**
- `memory_id` (str): 体验ID
- `level` (int): 展开层级（1=L1, 2=L2, 3=L3）
**返回:** Dict[str, Optional[str]] - 展开的内容
**用法:**
```python
l1_content = recall_manager.expand_memory("exp_20260404_120000", level=1)
l2_content = recall_manager.expand_memory("exp_20260404_120000", level=2)
l3_content = recall_manager.expand_memory("exp_20260404_120000", level=3)
```

---

## 5. Storage层 - 存储层

**位置:** `Memory/storage/`
**作用:** 直接访问数据库存储
**使用场景:** 底层数据操作，性能优化，数据管理

### 5.1 ExperienceStore - 体验存储

**位置:** `Memory/storage/experience_store.py`

#### `ExperienceStore.__init__(db_manager)`
**功能:** 创建ExperienceStore实例
**用法:**
```python
from Memory.storage.experience_store import ExperienceStore
store = ExperienceStore()
```

#### `ExperienceStore.create(exp)`
**功能:** 创建新的体验节点
**参数:** `exp` (Experience) - Experience对象
**返回:** str - 体验ID
**用法:**
```python
exp = Experience(id="exp_20260404_120000", L3_raw="内容")
exp_id = store.create(exp)
```

#### `ExperienceStore.get(exp_id)`
**功能:** 获取指定体验
**参数:** `exp_id` (str) - 体验ID
**返回:** Optional[Experience] - Experience对象，不存在返回None
**用法:**
```python
exp = store.get("exp_20260404_120000")
```

#### `ExperienceStore.get_all(limit)`
**功能:** 获取所有体验
**参数:** `limit` (int) - 限制返回数量（可选）
**返回:** List[Experience] - Experience列表
**用法:**
```python
all_exps = store.get_all()
recent_exps = store.get_all(limit=10)
```

#### `ExperienceStore.update(exp)`
**功能:** 更新体验
**参数:** `exp` (Experience) - Experience对象
**返回:** bool - 更新是否成功
**用法:**
```python
exp = store.get("exp_20260404_120000")
exp.L1_text = "新的关键要点"
success = store.update(exp)
```

#### `ExperienceStore.delete(exp_id)`
**功能:** 删除体验
**参数:** `exp_id` (str) - 体验ID
**返回:** bool - 删除是否成功
**用法:**
```python
success = store.delete("exp_20260404_120000")
```

#### `ExperienceStore.get_consolidation_candidates(limit)`
**功能:** 获取待巩固的候选体验
**参数:** `limit` (int) - 限制返回数量（可选）
**返回:** List[Experience] - 未巩固的Experience列表
**用法:**
```python
candidates = store.get_consolidation_candidates(limit=50)
```

#### `ExperienceStore.update_l1l2(experience_id, l1_text, l1_topic, l1_thematic, l2_text)`
**功能:** 更新L1/L2层内容
**参数:** 体验ID和L1/L2内容
**返回:** bool - 更新是否成功
**用法:**
```python
success = store.update_l1l2(
    experience_id="exp_20260404_120000",
    l1_text="关键要点",
    l1_topic="个人信息",
    l1_thematic="身份认知",
    l2_text="具体细节"
)
```

#### `ExperienceStore.update_importance(experience_id, importance)`
**功能:** 更新重要度评分
**参数:** 体验ID和重要度分数
**返回:** bool - 更新是否成功
**用法:**
```python
success = store.update_importance("exp_20260404_120000", 0.8)
```

---

### 5.2 EntityStore - 实体存储

**位置:** `Memory/storage/entity_store.py`

#### `EntityStore.__init__(db_manager)`
**功能:** 创建EntityStore实例
**用法:**
```python
from Memory.storage.entity_store import EntityStore
store = EntityStore()
```

#### `EntityStore.create(entity)`
**功能:** 创建新的实体
**参数:** `entity` (Entity) - Entity对象
**返回:** str - 实体ID
**用法:**
```python
entity = Entity(id="ent_Alice", name="Alice", type="person")
entity_id = store.create(entity)
```

#### `EntityStore.get(entity_id)`
**功能:** 获取指定实体
**参数:** `entity_id` (str) - 实体ID
**返回:** Optional[Entity] - Entity对象
**用法:**
```python
entity = store.get("ent_Alice")
```

#### `EntityStore.get_by_name(name)`
**功能:** 根据名称获取实体
**参数:** `name` (str) - 实体名称
**返回:** Optional[Entity] - Entity对象
**用法:**
```python
entity = store.get_by_name("Alice")
```

#### `EntityStore.get_all(limit)`
**功能:** 获取所有实体
**参数:** `limit` (int) - 限制返回数量
**返回:** List[Entity] - Entity列表
**用法:**
```python
all_entities = store.get_all()
```

---

### 5.3 ExperienceEdgeStore - 体验边存储

**位置:** `Memory/storage/experience_edge_store.py`

#### `ExperienceEdgeStore.__init__(db_manager)`
**功能:** 创建ExperienceEdgeStore实例
**用法:**
```python
from Memory.storage.experience_edge_store import ExperienceEdgeStore
store = ExperienceEdgeStore()
```

#### `ExperienceEdgeStore.create(edge)`
**功能:** 创建新的体验层边
**参数:** `edge` (ExperienceEdge) - ExperienceEdge对象
**返回:** int - 边ID
**用法:**
```python
edge = ExperienceEdge(
    from_id="exp_20260404_120000",
    to_id="exp_20260404_115900",
    type="temporal",
    weight=1.0
)
edge_id = store.create(edge)
```

#### `ExperienceEdgeStore.get(edge_id)`
**功能:** 获取指定边
**参数:** `edge_id` (int) - 边ID
**返回:** Optional[ExperienceEdge] - ExperienceEdge对象
**用法:**
```python
edge = store.get(1)
```

#### `ExperienceEdgeStore.get_by_from(from_id)`
**功能:** 获取从指定体验出发的所有边
**参数:** `from_id` (str) - 源体验ID
**返回:** List[ExperienceEdge] - ExperienceEdge列表
**用法:**
```python
edges = store.get_by_from("exp_20260404_120000")
```

#### `ExperienceEdgeStore.get_all(limit)`
**功能:** 获取所有边
**参数:** `limit` (int) - 限制返回数量
**返回:** List[ExperienceEdge] - ExperienceEdge列表
**用法:**
```python
all_edges = store.get_all()
```

#### `ExperienceEdgeStore.update_decayed_weight(edge_id, decayed_weight)`
**功能:** 更新边的衰减权重
**参数:** 边ID和衰减权重
**返回:** bool - 更新是否成功
**用法:**
```python
success = store.update_decayed_weight(1, 0.95)
```

---

## 6. State层 - 状态层

**位置:** `Memory/state/manager.py`
**作用:** 管理AI的当前状态
**使用场景:** 获取和更新AI状态

### 6.1 DefaultStateManager - 状态管理器

#### `DefaultStateManager.__init__()`
**功能:** 创建StateManager实例
**用法:**
```python
from Memory.state.manager import DefaultStateManager
state_manager = DefaultStateManager()
```

#### `DefaultStateManager.get_mood()`
**功能:** 获取当前情绪状态
**返回:** MoodState - 情绪状态对象
**用法:**
```python
mood = state_manager.get_mood()
print(f"Mood: {mood.label} (intensity: {mood.intensity})")
```

#### `DefaultStateManager.get_energy()`
**功能:** 获取当前能量状态
**返回:** EnergyState - 能量状态对象
**用法:**
```python
energy = state_manager.get_energy()
print(f"Energy: {energy.label} (level: {energy.level})")
```

#### `DefaultStateManager.get_focus()`
**功能:** 获取当前专注内容
**返回:** Optional[str] - 专注内容，无专注返回None
**用法:**
```python
focus = state_manager.get_focus()
```

#### `DefaultStateManager.get_confidence()`
**功能:** 获取当前信心水平
**返回:** float - 信心值 (0-1)
**用法:**
```python
confidence = state_manager.get_confidence()
print(f"Confidence: {confidence:.2f}")
```

#### `DefaultStateManager.format_state_prompt()`
**功能:** 格式化状态为Prompt文本
**返回:** str - 状态Prompt文本
**用法:**
```python
state_prompt = state_manager.format_state_prompt()
```

---

## 7. Core层 - 核心层

**位置:** `Memory/core/modifier.py`
**作用:** 管理AI身份和核心信念
**使用场景:** 修改AI的核心属性和约束

### 7.1 CoreModifier - 核心修改器

#### `CoreModifier.__init__(identity)`
**功能:** 创建CoreModifier实例
**参数:** `identity` (Identity) - Identity对象
**用法:**
```python
from Memory.core.modifier import CoreModifier
from Memory.core.loader import IdentityLoader

identity = IdentityLoader().load_identity()
modifier = CoreModifier(identity)
```

#### `CoreModifier.modify_stable_layer(proposed_change, reason)`
**功能:** 修改稳定层（经过严格验证）
**参数:** 拟议的变更和原因
**返回:** ModificationResult - 修改结果
**用法:**
```python
result = modifier.modify_stable_layer(
    proposed_change={"name": "New Name"},
    reason="用户正式更名"
)
```

#### `CoreModifier.update_malleable_layer(updates)`
**功能:** 更新可变层（宽松验证）
**参数:** 更新内容字典
**返回:** ModificationResult - 修改结果
**用法:**
```python
result = modifier.update_malleable_layer({
    "current_mood": "happy",
    "energy_level": 0.8
})
```

#### `CoreModifier.propose_stable_layer_change(proposed_change, reason)`
**功能:** 提议稳定层变更（不直接修改，仅评估）
**参数:** 拟议的变更和原因
**返回:** ModificationResult - 评估结果
**用法:**
```python
result = modifier.propose_stable_layer_change(
    proposed_change={"personality": "new traits"},
    reason="性格演进建议"
)
```

---

## 8. 异常处理

**位置:** `Memory/api/exceptions.py`

### 8.1 异常类型

#### `MemoryAPIError`
**描述:** MemoryAPI基础异常
**用法:**
```python
from Memory.api.exceptions import MemoryAPIError
try:
    api.receive_event(role="user", content="test")
except MemoryAPIError as e:
    print(f"Memory API error: {e}")
```

#### `InputError`
**描述:** 输入参数错误
**用法:**
```python
from Memory.api.exceptions import InputError
try:
    api.receive_event(role="", content="")
except InputError as e:
    print(f"Input error: {e}")
```

#### `RecallError`
**描述:** 召回过程错误
**用法:**
```python
from Memory.api.exceptions import RecallError
try:
    recalls = api.check_recall("query", context)
except RecallError as e:
    print(f"Recall error: {e}")
```

#### `ConsolidationError`
**描述:** 巩固过程错误
**用法:**
```python
from Memory.api.exceptions import ConsolidationError
try:
    result = api.run_consolidation("incremental")
except ConsolidationError as e:
    print(f"Consolidation error: {e}")
```

#### `StateError`
**描述:** 状态层错误
**用法:**
```python
from Memory.api.exceptions import StateError
try:
    state_prompt = api.get_state_prompt()
except StateError as e:
    print(f"State error: {e}")
```

#### `CoreError`
**描述:** 核心层错误
**用法:**
```python
from Memory.api.exceptions import CoreError
try:
    core_data = api.load_core()
except CoreError as e:
    print(f"Core error: {e}")
```

---

## 9. 使用示例

### 9.1 完整对话流程

```python
from Memory.api.memory_api import MemoryAPI

# 初始化
api = MemoryAPI()

# 记录对话
conversation = [
    ("user", "My name is Alice and I'm a software engineer"),
    ("assistant", "Hello Alice! Nice to meet you."),
    ("user", "I love Python programming and AI development"),
]

for role, content in conversation:
    exp_id = api.receive_event(role=role, content=content)
    print(f"Recorded: {exp_id}")

# 召回记忆
recalls = api.check_recall(
    query="What does Alice do for work?",
    context={"recent_history": ["Tell me about Alice"]}
)

for recall in recalls:
    print(f"Recall: {recall.L0_text}")
```

### 9.2 巩固和更新

```python
from Memory.api.memory_api import MemoryAPI

api = MemoryAPI()

# 记录事件
for i in range(10):
    api.receive_event("user", f"Event number {i}")

# 执行增量巩固
result = api.run_consolidation(mode="incremental")
print(f"Consolidated {result['processed_count']} experiences")
```

### 9.3 直接使用各层接口

```python
# 直接使用写入层
from Memory.writer.pipeline import WriterPipeline
pipeline = WriterPipeline()
exp_id = pipeline.process_event("user", "直接调用写入层")

# 直接使用存储层
from Memory.storage.experience_store import experience_store
exp = experience_store.get(exp_id)
print(f"Direct access: {exp.L0_text}")

# 直接使用召回层
from Memory.recall.manager import RecallManager
from Memory.storage.experience_store import experience_store
from Memory.storage.entity_store import entity_store
from Memory.storage.experience_edge_store import experience_edge_store
from Memory.embedding.vector_store import vector_store
from Memory.embedding.model import embedding_service

recall_manager = RecallManager(
    experience_store=experience_store,
    entity_store=entity_store,
    edge_store=experience_edge_store,
    vector_store=vector_store,
    embedding_service=embedding_service
)

recalls = recall_manager.recall(
    query="直接查询",
    context={}
)
```

---

## 10. 总结

### 10.1 层级接口总结

| 层级 | 主要接口数量 | 使用场景 | 推荐使用频率 |
|------|-------------|----------|-------------|
| MemoryAPI层 | 9个 | 一般应用开发 | 每日使用 |
| WriterPipeline层 | 1个主接口 | 自定义写入逻辑 | 按需使用 |
| ConsolidationPipeline层 | 3个接口 | 手动触发巩固 | 定期使用 |
| RecallManager层 | 2个主接口 | 自定义召回逻辑 | 按需使用 |
| Storage层 | 15+个接口 | 底层数据操作 | 高级功能 |
| State层 | 5个接口 | 状态管理 | 按需使用 |
| Core层 | 3个接口 | 核心属性管理 | 偶尔使用 |

### 10.2 推荐使用方式

**初学者/一般应用:**
- 只使用MemoryAPI层的9个接口
- 简单、安全、功能完整

**高级开发者/特殊需求:**
- 直接使用各层接口
- 更灵活的控制
- 需要理解系统架构

**性能优化/系统集成:**
- 直接使用Storage层接口
- 绕过上层逻辑
- 适合性能敏感场景

---

## 11. HTTP API 端点汇总

### 11.1 记忆系统 HTTP 端点

**服务地址:** `http://localhost:8001`

| 端点 | 方法 | 功能 | 版本 |
|------|------|------|------|
| `/health` | GET | 健康检查 | v1 |
| `/api/status` | GET | 系统状态 | v1 |
| `/api/event` | POST | 记录事件（缓冲/立即） | v1 |
| `/api/recall` | POST | 完整召回（触发检测+关键词提取） | v1 |
| `/api/recall/keywords` | POST | 关键词召回（跳过检测，返回briefing） | v2.1 新增 |
| `/api/profile/{entity_name}` | GET | 加载个人档案 | v1 |
| `/api/profile/ensure` | POST | 确保档案存在（不存在则创建） | v2.2 新增 |
| `/api/core` | GET | 加载核心层 | v1 |
| `/api/state` | GET | 获取状态 | v1 |
| `/api/consolidate` | POST | 手动触发巩固 | v1 |

### 11.2 `/api/profile/ensure` 端点详情 *(新增 v2.2)*

**请求体:**
```json
{
  "entity_name": "深"
}
```

**响应体:**
```json
{
  "found": true,
  "profile": {
    "basic": {"name": "深", "type": "person", ...},
    "interaction_style": {"warmth": 0.5, ...},
    "preferences": {},
    "metadata": {"last_updated": "...", "updated_by": "conversation_turns"}
  }
}
```

**说明:** 由 Backend 根据对话轮次触发，不依赖 experience 阈值。

### 11.3 `/api/recall/keywords` 端点详情 *(新增 v2.1)*

**请求体:**
```json
{
  "query": "张三 天气",
  "context": {
    "recent_history": [],
    "ai_state": {},
    "current_time": ""
  }
}
```

**响应体:**
```json
{
  "briefing": "你记得张三之前说过喜欢晴天，那天你们聊得很开心。要注意自然地把这些记忆融入对话中。"
}
```

### 11.4 主系统侧调用链

```
SearchMemoryTool.execute(query)
  → mem_mod.memory_provider.retrieve_briefing(query)
    → HTTP POST /api/recall/keywords
      → MemoryAPI.recall_by_keywords()
        → RecallManager.recall_by_keywords()
    ← briefing: str | None
  ← {"success": bool, "briefing": str|None, "query": str}
```

**注意:** 主系统侧必须使用 `import module; module.provider` 模式，不能用 `from module import provider`，否则运行时替换的实例不会生效。

---

_最后更新: 2026-04-12_
_作者: Claude (API Documentation)_
_版本: 2.1_
