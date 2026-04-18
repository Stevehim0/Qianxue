# 记忆系统数据流文档

**系统:** Qianxue-master (AI Agent仿人类记忆系统)
**文档版本:** 2.1
**最后更新:** 2026-04-12

---

## 📋 目录

1. [系统架构图](#1-系统架构图)
2. [写入流程](#2-写入流程)
3. [巩固流程](#3-巩固流程)
4. [召回流程](#4-召回流程)
5. [数据存储](#5-数据存储)
6. [性能优化](#6-性能优化)

---

## 1. 系统架构图

### 1.1 整体架构

```mermaid
graph TB
    User[用户输入] --> MemoryAPI
    
    subgraph "MemoryAPI 统一接口层"
        MemoryAPI[MemoryAPI<br/>统一对外接口]
    end
    
    MemoryAPI --> Writer[写入层]
    MemoryAPI --> Recall[召回层]
    MemoryAPI --> Consolidate[巩固层]
    MemoryAPI --> State[状态层]
    MemoryAPI --> Core[核心层]
    
    subgraph "写入层 WriterPipeline"
        Writer[WriterPipeline]
        Raw[原始记录]
        L0[L0摘要生成]
        Entity[实体识别]
        Emotion[情感分析]
        Edge[边创建]
    end
    
    subgraph "巩固层 ConsolidationPipeline"
        Consolidate[ConsolidationPipeline]
        L1L2[L1/L2提取]
        Import[重要性评估]
        Implicit[隐性边发现]
        Decay[衰减计算]
        Dream[梦境处理]
    end
    
    subgraph "召回层 RecallManager"
        Recall[RecallManager]
        Trigger[触发检测]
        Vector[向量检索]
        Spread[激活扩散]
        Filter[后处理过滤]
    end
    
    subgraph "存储层 Storage"
        Experience[(Experience<br/>体验存储)]
        EntityStore[(Entity<br/>实体存储)]
        EdgeStore[(Edge<br/>边存储)]
        VectorDB[(ChromaDB<br/>向量存储)]
    end
    
    subgraph "底层支撑"
        SQLite[(SQLite<br/>关系数据库)]
        Embed[(Embedding<br/>向量编码)]
        LLM[LLM客户端]
    end
    
    Writer --> Experience
    Writer --> EntityStore
    Writer --> EdgeStore
    Writer --> Embed
    Writer --> LLM
    
    Consolidate --> Experience
    Consolidate --> EdgeStore
    Consolidate --> Embed
    Consolidate --> LLM
    
    Recall --> Experience
    Recall --> VectorDB
    Recall --> EdgeStore
    Recall --> Embed
    
    Experience --> SQLite
    EntityStore --> SQLite
    EdgeStore --> SQLite
    VectorDB --> SQLite
```

### 1.2 数据流路径

```mermaid
graph LR
    A[用户输入] --> B{选择操作}
    
    B -->|记录事件| C[写入流程]
    B -->|召回记忆| D[召回流程]
    B -->|巩固记忆| E[巩固流程]
    
    C --> F[数据库更新]
    D --> G[查询结果]
    E --> F
    
    F --> H[(SQLite数据库)]
    G --> H
```

---

## 2. 写入流程

### 2.1 写入流程总览

```mermaid
sequenceDiagram
    participant User as 用户
    participant API as MemoryAPI
    participant Pipeline as WriterPipeline
    participant Raw as RawRecorder
    participant L0 as L0Task
    participant Entity as EntityTask
    participant Emotion as EmotionTask
    participant DB as 数据库
    
    User->>API: receive_event(role, content)
    API->>Pipeline: process_event(role, content)
    
    Pipeline->>Raw: record_raw(role, content)
    Raw->>DB: 创建L3记录
    Raw-->>Pipeline: experience_id
    
    par 并行处理
        Pipeline->>L0: generate_l0_summary(content)
        L0->>DB: 生成向量并存储
        L0-->>Pipeline: l0_summary
    and
        Pipeline->>Entity: recognize_entities(content)
        Entity->>DB: 创建实体和边
        Entity-->>Pipeline: entity_ids
    and
        Pipeline->>Emotion: analyze_emotion(content)
        Emotion->>DB: 存储情感数据
        Emotion-->>Pipeline: emotion_snapshot
    end
    
    Pipeline->>DB: 创建时序边
    Pipeline-->>API: experience_id
    API-->>User: 返回ID
```

### 2.2 写入流程详细步骤

```mermaid
graph TB
    Start([用户输入]) --> Step1[Step 1: 原始记录]
    Step1 --> GenerateID[生成体验ID<br/>exp_YYYYMMDD_HHmmss]
    GenerateID --> SaveL3[保存L3层原文<br/>永不修改]
    SaveL3 --> Step2[Step 2: 三任务并行]
    
    Step2 --> TaskA[L0摘要生成任务]
    Step2 --> TaskB[实体识别任务]
    Step2 --> TaskC[情感分析任务]
    
    TaskA --> LLM1[调用LLM]
    LLM1 --> Embed1[生成768维向量]
    Embed1 --> SaveL0[存储L0摘要<br/>ChromaDB]
    
    TaskB --> LLM2[调用LLM识别]
    LLM2 --> VectorPre[向量预筛选]
    VectorPre --> CreateEntity[创建/获取实体]
    CreateEntity --> SaveCross[保存跨层边]
    
    TaskC --> LLM3[调用LLM分析]
    LLM3 --> ExtractEmotion[提取情感维度]
    ExtractEmotion --> SaveEmotion[保存情感数据]
    
    SaveL0 --> Step3[Step 3: 边创建]
    SaveCross --> Step3
    SaveEmotion --> Step3
    
    Step3 --> Temporal[创建时序边<br/>连接前一体验]
    Temporal --> Step4[Step 4: 状态更新]
    
    Step4 --> Check{情感强度>=0.8?}
    Check -->|是| StateUpdate[异步触发状态更新]
    Check -->|否| End([完成])
    StateUpdate --> End
```

### 2.3 数据状态变化

| 阶段 | L3_raw | L0_text | L0_embedding | L1/L2 | Entities | Emotion | Edges |
|------|--------|---------|--------------|-------|----------|---------|-------|
| 输入 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Step 1 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Step 2 | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ (跨层) |
| Step 3 | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ (时序) |
| Step 4 | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |

---

## 3. 巩固流程

### 3.1 巩固流程总览

```mermaid
sequenceDiagram
    participant User as 用户
    participant API as MemoryAPI
    participant Pipeline as ConsolidationPipeline
    participant DB as 数据库
    participant LLM as LLM服务
    
    User->>API: run_consolidation(mode)
    API->>Pipeline: run_consolidation(mode)
    
    Pipeline->>DB: 获取候选体验
    DB-->>Pipeline: candidates
    
    Pipeline->>Pipeline: Phase 1: 六任务并行
    
    par Phase 1 并行处理
        Pipeline->>LLM: L1/L2提取
        Pipeline->>LLM: 重要性评估
        Pipeline->>LLM: 隐性边发现
        Pipeline->>LLM: 属性升级
        Pipeline->>LLM: 信息验证
        Pipeline->>LLM: 情感时间线
    end
    
    Pipeline->>DB: 更新体验数据
    
    Pipeline->>Pipeline: Phase 2: 衰减计算
    Pipeline->>DB: 更新边权重
    
    alt mode=dream
        Pipeline->>Pipeline: Phase 3: 梦境处理
        Pipeline->>LLM: 梦境四任务
        Pipeline->>DB: 更新扭曲和审计
    end
    
    Pipeline->>Pipeline: Phase 4: 档案更新
    Pipeline->>DB: 更新个人档案
    
    Pipeline-->>API: 结果统计
    API-->>User: 返回结果
```

### 3.2 巩固流程详细步骤

```mermaid
graph TB
    Start([开始巩固]) --> Select[选择候选体验<br/>consolidated=0]
    Select --> Phase1[Phase 1: 六任务并行]
    
    Phase1 --> P1T1[L1/L2提取<br/>提取关键要点和细节]
    Phase1 --> P1T2[重要性评估<br/>0-1评分]
    Phase1 --> P1T3[隐性边发现<br/>语义关联]
    Phase1 --> P1T4[属性升级<br/>更新实体属性]
    Phase1 --> P1T5[信息验证<br/>交叉验证]
    Phase1 --> P1T6[情感时间线<br/>更新趋势]
    
    P1T1 --> Update1[更新L1/L2字段]
    P1T2 --> Update2[更新importance]
    P1T3 --> Update3[创建thematic边]
    P1T4 --> Update4[更新实体属性]
    P1T5 --> Update5[标记verify_status]
    P1T6 --> Update6[更新情感数据]
    
    Update1 --> Phase2[Phase 2: 衰减计算]
    Update2 --> Phase2
    Update3 --> Phase2
    Update4 --> Phase2
    Update5 --> Phase2
    Update6 --> Phase2
    
    Phase2 --> CalcDecay[计算时间衰减<br/>λ分层参数]
    CalcDecay --> UpdateWeight[更新decayed_weight]
    
    UpdateWeight --> CheckMode{mode?}
    
    CheckMode -->|dream| Phase3[Phase 3: 梦境处理]
    CheckMode -->|incremental/full| Phase4[Phase 4: 档案更新]
    
    Phase3 --> Dream1[梦境重组]
    Phase3 --> Dream2[梦境情感]
    Phase3 --> Dream3[梦境扭曲]
    Phase3 --> Dream4[梦境模拟]
    
    Dream1 --> UpdateDistort[更新distorted字段]
    Dream2 --> UpdateDistort
    Dream3 --> UpdateDistort
    Dream4 --> UpdateDistort
    
    UpdateDistort --> Phase4
    
    Phase4 --> UpdateProfile[更新个人档案<br/>interaction_pattern]
    UpdateProfile --> MarkConsolidated[标记consolidated=1]
    MarkConsolidated --> End([完成])
```

### 3.3 巩固前后数据对比

```mermaid
graph LR
    subgraph "巩固前"
        A1[L0: 摘要]
        A2[L1/L2: 空]
        A3[importance: 0]
        A4[consolidated: 0]
    end
    
    subgraph "巩固后"
        B1[L0: 摘要]
        B2[L1: 关键要点<br/>L2: 具体细节]
        B3[importance: 0.75]
        B4[consolidated: 1]
    end
    
    A1 --> B1
    A2 --> B2
    A3 --> B3
    A4 --> B4
```

---

## 4. 召回流程

> **v2.1 更新**: 新增关键词召回路径 (`recall_by_keywords`)，供主系统直接传入关键词，跳过触发检测，返回 briefing 文本。原有 `recall()` 路径保持不变。

### 4.0 主系统与记忆系统的召回连接架构

```
主系统 (AgentBrain)
  │
  ├─ SearchMemoryTool.execute(query="张三 天气")
  │    │
  │    ▼
  │  mem_mod.memory_provider.retrieve_briefing(query="张三 天气")
  │    │
  │    ▼ HTTP POST
  │  /api/recall/keywords  {"query": "张三 天气", "context": {...}}
  │    │
  │    ▼
  │  MemoryAPI.recall_by_keywords()
  │    │ 切分为 ["张三", "天气"]
  │    ▼
  │  RecallManager.recall_by_keywords(["张三", "天气"])
  │    │ 双轨召回 + briefing 生成
  │    ▼
  │  {"briefing": "你记得张三之前说过喜欢晴天..."}
  │    │
  │    ▼ HTTP 200
  │  RecallByKeywordsResponse(briefing="...")
  │    │
  │    ▼
  │  返回 briefing 字符串给 AgentBrain
```

**关键设计决策:**
- 主系统只传关键词（不传 user_id / group_id），记忆系统全局召回
- 返回值为纯文本 briefing（自然语言内心独白），不再是结构化的 experiences/entities 列表
- 记忆系统侧**只加新方法**，不改已有方法（`recall()` / `check_recall()` / `/api/recall` 保持不变）

**踩坑记录:**
- `from module import variable` 会在导入时绑定对象引用，后续 `module.variable = new_obj` 替换不会生效。必须用 `import module; module.variable` 运行时访问。

### 4.1 召回流程总览

```mermaid
sequenceDiagram
    participant User as 用户
    participant API as MemoryAPI
    participant Recall as RecallManager
    participant Detector as TriggerDetector
    participant Vector as VectorStore
    participant Cache as AdjacencyCache
    participant LLM as LLM服务
    participant DB as 数据库
    
    User->>API: check_recall(query, context)
    API->>Recall: recall(query, context)
    
    alt profiles_to_load指定
        Recall->>DB: load_profiles()
        DB-->>Recall: loaded_profiles
    end
    
    Recall->>Detector: detect(query, context)
    Detector-->>Recall: signals
    
    alt 无触发信号
        Recall-->>API: []
        API-->>User: []
    else 有触发信号
        Recall->>Recall: extract_keywords(query)
        Recall->>Vector: query(keywords)
        Vector-->>Recall: vector_results
        
        Recall->>Cache: activation_spread(vector_results)
        Cache-->>Recall: spread_results
        
        Recall->>Recall: merge_and_rank(results)
        Recall->>Recall: deduplicate(results)
        
        alt LLM后处理启用
            Recall->>LLM: filter_candidates(results)
            LLM-->>Recall: filtered_results
        end
        
        Recall-->>API: final_results
        API-->>User: RecallResult[]
    end
```

### 4.2 关键词召回流程（新增 v2.1）

```mermaid
sequenceDiagram
    participant Brain as AgentBrain
    participant Tool as SearchMemoryTool
    participant MI as MemoryInterface
    participant Server as Memory Server
    participant API as MemoryAPI
    participant RM as RecallManager
    participant VS as VectorStore
    participant LLM as LLM服务
    participant BG as BriefingGenerator

    Brain->>Tool: execute(query="张三 天气")
    Tool->>MI: mem_mod.memory_provider.retrieve_briefing(query)
    MI->>MI: logger.info("[Memory] recall query: ...")
    MI->>Server: POST /api/recall/keywords
    Server->>API: recall_by_keywords(query, context)
    API->>API: 切分关键词 ["张三", "天气"]

    par 体验轨
        API->>RM: _experience_vector_search(keywords)
        RM->>VS: query_experience(embedding, top_k=10)
        VS-->>RM: 向量检索结果
        RM->>RM: _experience_spread(候选) [需adjacency_cache]
    and 信息轨
        API->>RM: _entity_vector_search(keywords)
        RM->>VS: query_entity(embedding, top_k=10)
        VS-->>RM: 向量检索结果
        RM->>RM: _entity_spread(候选) [内存邻接表]
    end

    RM->>RM: 合并、排序、截断 (体验Top3, 实体Top15)
    RM->>BG: generate(experiences, entities, query, context)
    BG->>LLM: 生成自然语言简报
    LLM-->>BG: briefing 文本
    BG-->>RM: briefing
    RM-->>API: {"experiences", "entities", "briefing"}
    API-->>Server: RecallByKeywordsResponse(briefing)
    Server-->>MI: HTTP 200 {"briefing": "..."}
    MI->>MI: logger.info("[Memory] recall result: ...")
    MI-->>Tool: briefing 字符串
    Tool-->>Brain: {"success": True, "briefing": "..."}
```

### 4.3 原有召回流程详细步骤（保持不变）

```mermaid
graph TB
    Start([用户查询]) --> Step0[Step 0: 档案加载]
    Step0 --> CheckProfile{profiles_to_load?}
    CheckProfile -->|是| LoadProfile[加载个人档案]
    CheckProfile -->|否| Step1
    LoadProfile --> Step1[Step 1: 触发检测]
    
    Step1 --> Detect[检测触发信号<br/>实体/时间/状态]
    Detect --> CheckSignal{有触发信号?}
    
    CheckSignal -->|否| NoResult[返回空列表]
    CheckSignal -->|是| Step2[Step 2: 关键词提取]
    
    Step2 --> Extract[提取查询关键词<br/>排除冗余词]
    Extract --> Step3[Step 3: 向量检索]
    
    Step3 --> Encode[编码关键词向量]
    Encode --> QueryChroma[查询ChromaDB<br/>Top-K=10]
    QueryChroma --> VectorResults[向量检索结果]
    
    VectorResults --> Step4[Step 4: 激活扩散]
    Step4 --> LoadCache[加载邻接表缓存]
    LoadCache --> Spread[激活扩散计算<br/>hop_distance决定跳数]
    Spread --> SpreadResults[扩散结果]
    
    SpreadResults --> Step5[Step 5: 排序过滤]
    Step5 --> Merge[合并候选集<br/>A ∪ B]
    Merge --> Rank[按激活分数排序<br/>importance × source_type]
    Rank --> Dedup[去重]
    
    Dedup --> Step6[Step 6: 后处理]
    Step6 --> CheckLLM{LLM后处理?}
    
    CheckLLM -->|是| LLMFilter[LLM二分类<br/>should_mention?]
    CheckLLM -->|否| Step7
    LLMFilter --> Step7[Step 7: 深度展开]
    
    Step7 --> CheckExpand{需要展开?}
    CheckExpand -->|是| Expand[展开L1/L2/L3]
    CheckExpand -->|否| FinalResult[返回最终结果]
    Expand --> FinalResult
    
    NoResult --> End([结束])
    FinalResult --> End
```

### 4.4 召回结果生成

```mermaid
graph LR
    Query[查询: Alice工作] --> Vector[向量检索]
    Query --> Entity[实体匹配]
    
    Vector --> VR[5个相关体验]
    Entity --> ER[2个相关体验]
    
    VR --> Spread[激活扩散]
    ER --> Spread
    
    Spread --> SR[3个关联体验]
    
    VR --> Merge[合并去重]
    SR --> Merge
    ER --> Merge
    
    Merge --> Rank[排序]
    Rank --> Filter[过滤]
    Filter --> Result[最终结果: 5个RecallResult]
```

---

## 5. 数据存储

### 5.1 数据库架构

```mermaid
graph TB
    subgraph "SQLite数据库"
        Experience[(experiences<br/>体验节点表)]
        Entity[(entities<br/>实体节点表)]
        ExpEdge[(experience_edges<br/>体验层边表)]
        EntEdge[(entity_edges<br/>实体层边表)]
        CrossEdge[(cross_edges<br/>跨层边表)]
        Profile[(profiles<br/>个人档案表)]
    end
    
    subgraph "ChromaDB向量存储"
        L0_Collection[(experience_L0<br/>L0摘要向量集合)]
    end
    
    Experience <-->|from/to| ExpEdge
    Experience <-->|from/to| CrossEdge
    Entity <-->|from/to| CrossEdge
    Entity <-->|from/to| EntEdge
    
    Experience -->|向量查询| L0_Collection
```

### 5.2 数据分层存储

| 层级 | 存储位置 | 访问频率 | 更新频率 |
|------|----------|----------|----------|
| L0 | SQLite + ChromaDB | 极高 | 一次创建 |
| L1 | SQLite | 高 | 巩固时更新 |
| L2 | SQLite | 中 | 巩固时更新 |
| L3 | SQLite | 低 | 永不修改 |

---

## 6. 性能优化

### 6.1 并发处理策略

```mermaid
graph LR
    Input[输入数据] --> Manager[任务管理器]
    
    Manager -->|ThreadPoolExecutor| Pool[线程池]
    
    Pool --> Task1[任务1]
    Pool --> Task2[任务2]
    Pool --> Task3[任务3]
    
    Task1 --> Result1[结果1]
    Task2 --> Result2[结果2]
    Task3 --> Result3[结果3]
    
    Result1 --> Merge[合并结果]
    Result2 --> Merge
    Result3 --> Merge
    
    Merge --> Output[最终输出]
```

### 6.2 向量检索优化

```mermaid
graph TB
    Query[用户查询] --> Filter[关键词过滤<br/>排除冗余词]
    Filter --> Encode[向量编码]
    Encode --> TopK[Top-K检索<br/>K=10]
    TopK --> Rerank[重排序<br/>importance加权]
    Rerank --> Threshold[阈值过滤<br/>score>0.5]
    Threshold --> Result[最终结果]
```

---

## 7. 总结

### 7.1 数据流关键特征

1. **分层处理**: 写入、巩固、召回各司其职
2. **并行优化**: 大量使用并发处理提高性能
3. **向量加速**: 关键步骤使用向量检索
4. **状态保持**: 多层数据结构保持不同抽象级别
5. **动态更新**: 权重衰减、激活扩散等动态机制

### 7.2 数据流转路径

**写入路径**: 用户 → MemoryAPI → WriterPipeline → 并行处理 → 数据库
**巩固路径**: 数据库 → ConsolidationPipeline → 六任务并行 → 更新数据库
**召回路径**: 用户 → MemoryAPI → RecallManager → 多阶段处理 → 返回结果

---

_最后更新: 2026-04-12_
_作者: Claude (System Analysis)_
_版本: 2.1_