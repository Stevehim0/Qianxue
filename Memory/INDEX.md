# Memory 模块索引

> 快速理解 Memory 记忆系统。Memory 是独立的记忆服务，提供分层记忆存储、写入/巩固/召回、人设管理、梦境处理、短期记忆（跨会话感知）。

## 一句话总结

Memory 是一个 FastAPI 服务，接收对话事件 → 写入记忆（L0摘要+实体+情感） → 巩固记忆（L1/L2提取+衰减+梦境） → 按需召回（双轨向量检索+扩散），通过 HTTP API 与 Backend 通信。

## 启动方式

```bash
cd Memory && python -m Memory.server    # 端口 8001
```

## 数据流全景

```
Backend POST /api/event → WriterPipeline → L0摘要 + 实体识别 + 情感分析
                                                     ↓
                                              写入 SQLite + ChromaDB

Backend POST /api/recall → RecallManager → 双轨召回（体验轨 + 信息轨）
                                                     ↓
                                          向量检索 → 扩散1跳 → 过滤 → 简报

定时/手动 POST /api/consolidate → ConsolidationPipeline → 巩固处理
  Phase 1: 7个并行任务（L1/L2提取、重要性、隐性边、属性升级、验证、情感时间线、实体关系）
  Phase 2: 衰减计算（边和节点权重衰减，核心遗忘机制）
  Phase 3: 梦境模块（重组、情感、扭曲、可塑层演化）—— 仅 full 模式
  Phase 4: 个人档案更新

Backend GET /api/stm/perception → STM → 短期记忆感知文本注入 system prompt

GET /api/core → MemoryAPI.load_core() → HTTP GET Backend /api/core/identity → 返回核心层
```

## 目录结构

```
Memory/
├── server/                    # HTTP 服务层
│   ├── app.py                 # ★ FastAPI 应用（所有 HTTP 端点，含 STM）
│   ├── schemas.py             # 请求/响应 Pydantic 模型
│   └── __main__.py            # 启动入口
│
├── api/                       # API 逻辑层
│   ├── memory_api.py          # ★ MemoryAPI 核心类（协调写入/召回/巩固）
│   └── exceptions.py          # 自定义异常
│
├── config/                    # 配置层
│   ├── settings.py            # ★ 全局配置（DatabaseConfig/ModelsConfig/DecayConfig/DreamConfig/StmConfig 等）
│   └── prompts/               # LLM Prompt 模板目录
│       ├── write_L0_summary.txt       # L0 摘要生成
│       ├── write_entity_recognize.txt # 实体识别
│       ├── write_emotion_snapshot.txt # 情感分析
│       ├── write_topic_boundary.txt   # 话题边界判断
│       ├── write_quality_check.txt    # 质量检查
│       ├── consolid_l1l2.txt          # L1/L2 深层提取
│       ├── consolid_implicit_edges.txt # 隐性边发现
│       ├── consolid_entity_relations.txt # 实体关系
│       ├── consolid_emotion_timeline.txt # 情感时间线
│       ├── consolid_info_verify.txt   # 信息验证
│       ├── consolid_property_upgrade.txt # 属性升级
│       ├── dream_reorganize.txt       # 梦境重组
│       ├── dream_emotion.txt          # 梦境情感
│       ├── dream_distort.txt          # 梦境扭曲
│       ├── dream_simulate.txt         # 梦境模拟
│       ├── dream_malleable.txt        # 可塑层演化
│       ├── dream_system.txt           # 梦境系统提示
│       ├── recall_filter.txt          # 召回过滤
│       ├── memory_briefing.txt        # 记忆简报
│       └── profile_update.txt         # 个人档案更新
│
├── writer/                    # ★ 写入层（事件→记忆）
│   ├── pipeline.py            # ★ WriterPipeline 主流程（原子性写入）
│   ├── buffer.py              # 消息缓冲区
│   ├── buffer_manager.py      # 缓冲管理器（超时检查、话题判断）
│   ├── raw_recorder.py        # 原始记录器
│   ├── topic_judge.py         # 话题边界判断
│   └── tasks/                 # 写入子任务
│       ├── l0_summary_task.py # L0 摘要生成 + embedding
│       ├── entity_task.py     # 实体识别 + 跨层边创建
│       └── emotion_task.py    # 情感快照分析
│
├── recall/                    # ★ 召回层（记忆检索）
│   ├── manager.py             # ★ RecallManager - 双轨召回（体验轨+信息轨）
│   ├── detector.py            # 触发判断 + 关键词提取
│   ├── filter.py              # 召回过滤
│   ├── briefing.py            # 记忆简报生成（一次LLM调用）
│   ├── profile_manager.py     # ★ 个人档案管理（自动创建+更新）
│   ├── profile_data.py        # 档案数据结构
│   ├── adjacency_cache.py     # 邻接缓存（加速扩散）
│   └── result.py              # 召回结果数据结构
│
├── consolidator/              # ★ 巩固层（记忆深化+遗忘）
│   ├── pipeline.py            # ★ ConsolidationPipeline - 4阶段并行处理
│   ├── sampling.py            # 分层采样（重要40% + 随机60%）
│   ├── config_manager.py      # 衰减参数动态管理
│   └── tasks/                 # 巩固子任务
│       ├── l1l2_task.py       # L1/L2 深层提取
│       ├── importance_task.py # 重要性估值
│       ├── implicit_edges_task.py  # 隐性边发现
│       ├── property_upgrade_task.py # 属性升级扫描
│       ├── verify_task.py     # 信息验证
│       ├── emotion_timeline_task.py # 情感时间线更新
│       ├── discover_entity_relations_task.py # 实体关系发现
│       ├── decay_calculation_task.py  # ★ 衰减计算（核心遗忘机制）
│       ├── dream_reorganize_task.py   # 梦境重组
│       ├── dream_emotion_task.py      # 梦境情感加工
│       ├── dream_distort_task.py      # 梦境扭曲
│       ├── dream_simulate_task.py     # 梦境模拟推演（已禁用）
│       └── dream_malleable_task.py    # 可塑层演化
│
├── storage/                   # ★ 存储层（SQLite + ChromaDB）
│   ├── database.py            # 数据库连接管理
│   ├── schema.py              # ★ Schema 定义 + 迁移（当前 v10）
│   ├── core_store.py          # [废弃] 核心层存储（数据现从 Backend HTTP 获取）
│   ├── state_store.py         # 状态层存储
│   ├── experience_store.py    # 体验节点存储（L0-L3）
│   ├── experience_edge_store.py # 体验层边存储
│   ├── entity_store.py        # 信息实体存储
│   ├── entity_edge_store.py   # 实体关系边存储
│   ├── cross_edge_store.py    # 跨层边存储
│   ├── profile_store.py       # 个人档案存储
│   └── stm_store.py           # 短期记忆存储（stm_events + stm_compressed）
│
├── core/                      # ⚠️ 已废弃 — 核心层数据现通过 Backend HTTP API 获取
│   ├── loader.py              # [废弃] 本地文件 loader
│   ├── models.py              # [废弃] 核心层数据模型
│   ├── filter.py              # [废弃] 过滤器
│   ├── modifier.py            # [废弃] 修改器
│   ├── parser.py              # [废弃] 解析器
│   └── time_utils.py          # [废弃] 时间工具
│
├── state/                     # 状态层（情绪/能量/专注）
│   ├── manager.py             # DefaultStateManager
│   ├── updater.py             # 状态更新器
│   └── constraints.py         # 约束条件
│
├── stm/                       # 短期记忆模块（跨会话全局感知）
│   ├── perception_builder.py  # ★ 感知构建器（生成格式化感知文本）
│   └── compressor.py          # 事件压缩器（LLM压缩旧事件为摘要）
│
├── embedding/                 # 向量化服务
│   ├── model.py               # EmbeddingService（BAAI/bge-base-zh）
│   ├── vector_store.py        # ChromaDB 向量存储
│   └── mock_service.py        # 测试用 Mock
│
├── llm/                       # LLM 客户端
│   ├── base.py                # BaseLLMClient（抽象基类）
│   ├── qianwen_client.py      # 千问客户端
│   ├── deepseek_client.py     # DeepSeek 客户端
│   ├── factory.py             # LLMFactory 工厂
│   └── utils.py               # LLM 工具函数
│
├── scripts/                   # 运维脚本
│   ├── clear_database.py      # 清空数据库
│   ├── inspect_database.py    # 检查数据库
│   ├── run_full_consolidation.py # 运行全量巩固
│   ├── experience_data_analysis.py # 数据分析
│   └── visualize_memory.py    # 可视化
│
└── tests/                     # 测试
    ├── test_e2e/              # 端到端测试
    ├── writer/                # 写入层测试
    ├── recall/                # 召回层测试
    ├── consolidator/          # 巩固层测试
    ├── storage/               # 存储层测试
    ├── test_api/              # API 测试
    ├── integration/           # 集成测试
    └── performance/           # 性能测试
```

## HTTP API 端点速查

| 方法 | 路径 | 职责 |
|------|------|------|
| POST | `/api/event` | 接收对话事件 → 写入记忆 |
| POST | `/api/recall` | 召回记忆（双轨检索+简报） |
| POST | `/api/recall/keywords` | 关键词召回（返回简报） |
| GET  | `/api/profile/{name}` | 加载个人档案 |
| GET  | `/api/core` | 加载核心层（从 Backend HTTP 获取，非本地文件） |
| GET  | `/api/state` | 获取当前状态 prompt |
| POST | `/api/consolidate` | 手动触发巩固 |
| POST | `/api/stm/event` | 记录短期记忆事件 |
| GET  | `/api/stm/perception` | 获取 STM 感知文本 |
| POST | `/api/stm/compress` | 手动触发 STM 压缩 |
| GET  | `/api/status` | 系统状态 |
| GET  | `/health` | 健康检查 |

## 数据库 Schema 速查（v10）

| 表名 | 职责 | 核心字段 | UNIQUE 约束 |
|------|------|----------|-------------|
| `experiences` | 体验节点（L0-L3 四层摘要） | id, L0_text, L1_text, L2_text, L3_raw, importance, emotion_*, consolidated, decayed_* | id |
| `experience_edges` | 体验间关系边 | from_id, to_id, type, weight, decayed_weight, dormant | **(from_id, to_id)** |
| `entities` | 信息实体 | id, name, type, properties(JSON), embedding | name |
| `entity_edges` | 实体间关系边 | from_id, to_id, relation, confidence, source_type | **(from_id, to_id)** |
| `cross_edges` | 跨层边（体验↔实体） | from_id(experience), to_id(entity), context | **(from_id, to_id)** |
| `core` | ⚠️ 已废弃 — 核心层 | invariant_text, stable_text, malleable_text | — |
| `state` | 状态层（单行表） | mood_valence/arousal/label, energy, focus, confidence | id=1 |
| `person_profiles` | 个人档案 | id, memory_index, basic, interaction_style, preferences | id |
| `decay_config` | 衰减参数 | key, value（运行时可调） | key |
| `stm_events` | 短期记忆事件 | event_type, source_type, group_id, summary | id |
| `stm_compressed` | 压缩后摘要 | summary, event_count, time_range_start/end | id |
| `schema_version` | Schema 版本 | version (当前 v10) | id=1 |

> **v10 变更**：三张边表新增 `UNIQUE(from_id, to_id)` 约束，从数据库层面防止巩固层重复创建边。之前的应用层查重在并发场景下不可靠。同时清理了已有的重复数据。

## 关键流程详解

### 写入流程（WriterPipeline.process_event）

1. **内存处理阶段**（无数据库操作）：
   - 并行执行三项任务：L0摘要生成、实体识别、情感分析
   - 所有 LLM 调用在内存完成
2. **原子写入阶段**（统一事务）：
   - 写入 experience 节点 + embedding
   - 写入 entities（已存在则复用） + cross_edges
   - 创建 temporal edge
3. **档案创建检查**：person 类型实体出现 >=3 次且跨 >=3 天时自动创建档案

### 召回流程（RecallManager.recall）

1. **触发判断** → 关键词提取
2. **体验轨**：向量检索 experience_L0 → 沿 experience_edges 扩散1跳
3. **信息轨**：向量检索 entities → 沿 entity_edges 扩散1跳
4. **跨层关联**：通过 cross_edges 附上关联实体
5. **排序截断**：体验 Top3，实体 Top15
6. **过滤+简报**：一次 LLM 调用生成自然语言简报

### 巩固流程（ConsolidationPipeline.run_consolidation）

- **Phase 1**（7 个并行任务）：L1/L2提取、重要性、隐性边、属性升级、验证、情感时间线、实体关系
- **Phase 2**（衰减计算）：**核心遗忘机制**，边和节点权重按时间衰减，低于阈值标记休眠
  - 边衰减：`weight × e^(-λt) × (1 + α × access_count)`（当前 access_count 未递增，强化因子不生效）
  - 节点衰减：`e^(-λt)`（算了 L0-L3 decayed 值但召回时不消费）
  - 信息层置信度衰减：设计要求但未实现
- **Phase 3**（梦境模块，仅 full 模式）：记忆重组、情感加工、扭曲、可塑层演化
- **Phase 4**（档案更新）：巩固后更新个人档案

### STM 短期记忆流程

- **记录**：Backend 异步 POST `/api/stm/event`（事件类型：ai_reply/tool_call/user_mention/significant_msg）
- **压缩**：事件超过 40 条时 LLM 自动压缩旧事件为摘要
- **感知**：GET `/api/stm/perception` → 格式化感知文本 → 注入 Backend 的 system prompt

## 配置

`Memory/.env`:
```env
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

`Memory/config/settings.py` 管理所有配置（ModelsConfig/DecayConfig/DreamConfig/StmConfig/BufferConfig 等）。

## 开发约定

- 使用 requests (sync) + OpenAI SDK 调用 LLM（非异步，在 ThreadPool 中运行）
- LLM 超时: 30s
- 记忆 source_type: 群聊 `"qq_group"`, 私聊 `"qq_private"`
- Schema 版本: v10，迁移在 Memory 服务启动时自动执行
- 三张边表有 `UNIQUE(from_id, to_id)` 约束，所有 INSERT 使用 `INSERT OR REPLACE` 防并发冲突
- 同一对节点只存一条边（不区分方向），写入时自动检查反向边
- 梦境可塑层演化必须使用 `response_format="text"` 调用 LLM（`call()` 默认是 `"json"` 会把 YAML 解析为 list）
- 巩固的 Phase 2 衰减计算是**核心遗忘机制**，不可注释禁用
- 梦境 simulate 任务已禁用（防止生成过多梦境体验）
- L3 永远不可改（梦境铁律）
- 实体类型: person/place/concept/event/skill/other
- Embedding 模型: BAAI/bge-base-zh
- 核心层数据源: Backend `identity.md` 是唯一数据源，Memory 通过 HTTP 获取（`GET /api/core/identity`）

## 已知未实现项

| 项 | 设计要求 | 现状 | 优先级 |
|---|---------|------|--------|
| 边 access_count 未递增 | 召回时递增走过的边，强化因子 `(1 + α × access_count)` 生效 | access_count 永远为 0，强化因子等于 1 | 中 |
| 节点衰减值未消费 | L0-L3 decayed 值影响检索优先级 | 计算并写回数据库，但召回排序不使用 | 低 |
| 信息层置信度不衰减 | `confidence × e^(-λt)`，λ=0.005 | 未实现，实体 confidence 创建后不变 | 低 |
