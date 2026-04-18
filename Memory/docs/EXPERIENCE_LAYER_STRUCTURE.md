# 体验层数据存储结构详解

## 📊 数据库表结构 (experiences表)

### 表结构概览
```sql
CREATE TABLE experiences (
    -- === 主键和基本信息 ===
    id TEXT PRIMARY KEY,                    -- exp_20260408_171513
    created_at TEXT NOT NULL,               -- 2026-04-08T17:15:13.123456

    -- === 四层摘要结构 (核心设计) ===
    L0_text TEXT,                          -- AI第一人称摘要
    L0_embedding BLOB,                     -- 768维向量 (3072 bytes)
    L1_text TEXT,                          -- 关键要点
    L2_text TEXT,                          -- 具体细节
    L3_raw TEXT NOT NULL,                  -- 完整原文 (永不修改)

    -- === 情感分析数据 ===
    emotion_category TEXT,                 -- joy/sadness/anger等
    emotion_intensity REAL,                -- 0.0-1.0 (强度)
    emotion_valence REAL,                  -- -1.0到1.0 (正负面)
    emotion_arousal REAL,                  -- 0.0-1.0 (唤醒度)
    emotion_target TEXT,                   -- 指向的实体ID

    -- === 上下文信息 ===
    context_focus TEXT,                    -- AI当前专注点
    context_mood TEXT,                     -- AI当前情绪
    context_time_of_day TEXT,              -- 时间推导 (凌晨/上午等)
    context_silence_before TEXT,           -- 距上次对话时间
    context_task TEXT,                     -- 外部任务
    context_extra TEXT,                    -- 额外上下文 (JSON格式)

    -- === 巩固层相关 ===
    importance REAL DEFAULT 0.5,           -- 重要度评分
    consolidated INTEGER DEFAULT 0,        -- 巩固标记
    twist_level TEXT DEFAULT 'none',       -- 扭曲程度

    -- === 衰减计算 ===
    L0_decayed REAL DEFAULT 1.0,           -- L0层衰减权重
    L1_decayed REAL DEFAULT 1.0,           -- L1层衰减权重
    L2_decayed REAL DEFAULT 1.0,           -- L2层衰减权重
    L3_decayed REAL DEFAULT 1.0,           -- L3层衰减权重

    -- === 梦境相关 (Phase 09新增) ===
    distorted TEXT,                        -- 梦境扭曲审计追踪 (JSON)
    source_type TEXT DEFAULT 'direct',     -- 来源类型 (direct/dream)
    confidence REAL DEFAULT 1.0            -- 置信度
)
```

## 🗂️ 实际数据存储示例

### 典型的体验节点数据

```json
{
  "id": "exp_20260408_171513",
  "created_at": "2026-04-08T17:15:13.123456",

  // === 四层摘要结构 ===
  "L0_text": "张三向我请教Python学习问题，我引导他从Anaconda安装开始，成功运行了第一个代码，看到他充满信心，我感到欣慰。",
  "L0_embedding": "<3072字节的BLOB数据，768个float32值>",
  "L1_text": "1. 张三想学Python做数据分析\n2. 我推荐使用Anaconda\n3. 成功安装并运行第一个代码",
  "L2_text": "详细记录了安装步骤、遇到的问题和解决方案",
  "L3_raw": "张三：你好，我想学习Python，主要是为了做数据分析。你能给我一些建议吗？\nAI：当然！...[完整对话内容]",

  // === 情感分析 ===
  "emotion_category": "joy",
  "emotion_intensity": 0.8,
  "emotion_valence": 0.9,
  "emotion_arousal": 0.7,
  "emotion_target": null,  // Phase 14.1修复后固定为null

  // === 上下文信息 ===
  "context_focus": "Python教学对话",
  "context_mood": "愉悦",
  "context_time_of_day": "下午",
  "context_silence_before": "300",  // 距上次对话5分钟
  "context_task": null,
  "context_extra": null,

  // === 巩固层相关 ===
  "importance": 0.7,
  "consolidated": 0,  // 尚未巩固
  "twist_level": "none",

  // === 衰减权重 (初始值) ===
  "L0_decayed": 1.0,
  "L1_decayed": 1.0,
  "L2_decayed": 1.0,
  "L3_decayed": 1.0,

  // === 梦境相关 ===
  "distorted": null,
  "source_type": "direct",
  "confidence": 1.0
}
```

## 🔍 关键数据存储细节

### 1. 向量存储 (L0_embedding)
```python
# 存储格式：BLOB (Binary Large Object)
# 大小：768维 × 4字节(float32) = 3072字节
# 序列化：numpy_array.astype(np.float32).tobytes()
# 反序列化：np.frombuffer(blob, dtype=np.float32)

示例值：
<b'\x00\x00\x80?\x00\x00\x00@\x00\x00\x40?\...'>  # 3072字节
```

### 2. 四层摘要结构
```
L3_raw (完整原文)       → 永不修改的原始对话/文本
    ↓
L2_text (具体细节)      → 可以模糊细节，但保持核心内容
    ↓
L1_text (关键要点)      → 提炼3-5个要点
    ↓
L0_text (第一人称摘要)  → AI的第一人称体验描述 (Phase 14.1修复)
```

### 3. 情感数据结构
```python
# Phase 14.1修复前：emotion_target指向具体实体
emotion_target = "entity_zhangsan"

# Phase 14.1修复后：emotion_target固定为null
emotion_target = None  # 不再指向具体实体
```

### 4. 上下文信息存储
```python
# context_extra: JSON格式存储额外信息
context_extra = '{"weather": "晴天", "location": "办公室"}'

# context_silence_before: 字符串存储时间差
context_silence_before = "300"  # 秒数
```

## 📈 数据流转过程

### 写入流程
```
用户输入对话
    ↓
WriterPipeline.record_event()
    ↓
1. 生成L0摘要 (AI第一人称)
2. 提取关键信息
3. 分析情感状态
4. 读取当前状态
    ↓
ExperienceStore.create()
    ↓
存储到experiences表 + ChromaDB
```

### 巩固流程
```
ConsolidationPipeline.run_consolidation()
    ↓
1. 获取待巩固节点 (consolidated=0)
2. 执行六任务并行处理
3. 计算衰减权重
4. 更新L1/L2摘要
    ↓
ExperienceStore.update_l1l2()
ExperienceStore.update_consolidated_batch()
```

### 梦境扭曲流程 (Phase 09)
```
梦境模块四任务并行
    ↓
1. reorganize: 重组记忆
2. merge: 合并相似记忆
3. distort: 扭曲时间/情感
4. simulate: 模拟新体验
    ↓
更新distorted字段
更新L0/L1/L2摘要
创建新体验节点 (source_type='dream')
```

## 🎯 与设计文档对比

### ✅ 正确实现的设计
- **四层摘要结构**：L0/L1/L2/L3完整实现
- **L3不可变性**：有专门的代码保护
- **向量存储**：使用BLOB字段高效存储
- **情感分析**：完整的情感维度存储
- **上下文信息**：支持多种上下文维度
- **衰减计算**：每层独立的衰减权重
- **梦境扭曲**：完整的审计追踪机制

### ⚠️ Phase 14.1修复的问题
- **AI第一人称视角**：L0_text现在从AI视角生成
- **情感目标对象**：emotion_target固定为null

## 🔧 性能优化

### 索引设计
```sql
CREATE INDEX idx_experiences_created_at ON experiences(created_at DESC);
CREATE INDEX idx_experiences_consolidated ON experiences(consolidated);
CREATE INDEX idx_experiences_importance ON experiences(importance DESC);
CREATE INDEX idx_experiences_source_type ON experiences(source_type);
```

### 查询优化
```python
# 按重要性查询 (使用索引)
def get_top_by_importance(self, limit: int):
    cursor.execute("SELECT * FROM experiences ORDER BY importance DESC LIMIT ?")

# 随机查询 (用于梦境采样)
def get_random_excluding(self, limit: int, exclude_ids: List[str]):
    cursor.execute("SELECT * FROM experiences WHERE id NOT IN (...) ORDER BY RANDOM() LIMIT ?")
```

## 📊 数据统计信息

```python
# 典型记忆系统的数据量
{
  "总体验节点数": "1000-10000条",
  "单条记录大小": "3-5KB (包含BLOB)",
  "向量数据大小": "3MB/1000条",
  "L3平均长度": "200-500字符",
  "L0平均长度": "50-100字符"
}
```