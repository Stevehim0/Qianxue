#!/usr/bin/env python3
"""体验层数据结构直观分析"""
import sqlite3
import os

def show_experience_structure():
    """展示体验层的实际数据结构"""

    print("🔍 体验层数据存储结构分析\n")
    print("="*60)

    # 数据库表结构
    print("\n📋 DATABASE TABLE STRUCTURE (experiences)")
    print("-"*60)
    print("""
    ┌─────────────────────────────────────────────────────────┐
    │                  experiences 表                          │
    ├─────────────────────────────────────────────────────────┤
    │                                                         │
    │  🔑 id TEXT PRIMARY KEY                                 │
    │     示例: exp_20260408_171513                           │
    │                                                         │
    │  📅 created_at TEXT                                     │
    │     示例: 2026-04-08T17:15:13.123456                   │
    │                                                         │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  四层摘要结构 (核心设计)                         │   │
    │  ├─────────────────────────────────────────────────┤   │
    │  │ L0_text TEXT              AI第一人称摘要         │   │
    │  │ L0_embedding BLOB         768维向量 (3072 bytes) │   │
    │  │ L1_text TEXT              关键要点               │   │
    │  │ L2_text TEXT              具体细节               │   │
    │  │ L3_raw TEXT NOT NULL      完整原文 (永不修改)    │   │
    │  └─────────────────────────────────────────────────┘   │
    │                                                         │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  情感分析数据                                    │   │
    │  ├─────────────────────────────────────────────────┤   │
    │  │ emotion_category TEXT       joy/sadness/anger   │   │
    │  │ emotion_intensity REAL      0.0-1.0             │   │
    │  │ emotion_valence REAL        -1.0到1.0           │   │
    │  │ emotion_arousal REAL        0.0-1.0             │   │
    │  │ emotion_target TEXT         实体ID (Phase 14.1修复后为NULL) │
    │  └─────────────────────────────────────────────────┘   │
    │                                                         │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  上下文信息                                      │   │
    │  ├─────────────────────────────────────────────────┤   │
    │  │ context_focus TEXT           AI当前专注点        │   │
    │  │ context_mood TEXT            AI当前情绪          │   │
    │  │ context_time_of_day TEXT     时间推导            │   │
    │  │ context_silence_before TEXT  距上次对话时间      │   │
    │  │ context_task TEXT           外部任务            │   │
    │  │ context_extra TEXT           额外上下文(JSON)    │   │
    │  └─────────────────────────────────────────────────┘   │
    │                                                         │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  巩固层相关                                      │   │
    │  ├─────────────────────────────────────────────────┤   │
    │  │ importance REAL DEFAULT 0.5    重要度评分        │   │
    │  │ consolidated INTEGER DEFAULT 0 巩固标记         │   │
    │  │ twist_level TEXT DEFAULT 'none' 扭曲程度        │   │
    │  └─────────────────────────────────────────────────┘   │
    │                                                         │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  衰减计算                                        │   │
    │  ├─────────────────────────────────────────────────┤   │
    │  │ L0_decayed REAL DEFAULT 1.0     L0层衰减权重    │   │
    │  │ L1_decayed REAL DEFAULT 1.0     L1层衰减权重    │   │
    │  │ L2_decayed REAL DEFAULT 1.0     L2层衰减权重    │   │
    │  │ L3_decayed REAL DEFAULT 1.0     L3层衰减权重    │   │
    │  └─────────────────────────────────────────────────┘   │
    │                                                         │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  梦境相关 (Phase 09新增)                         │   │
    │  ├─────────────────────────────────────────────────┤   │
    │  │ distorted TEXT                  梦境扭曲审计追踪 │   │
    │  │ source_type TEXT DEFAULT 'direct' 来源类型      │   │
    │  │ confidence REAL DEFAULT 1.0      置信度          │   │
    │  └─────────────────────────────────────────────────┘   │
    │                                                         │
    └─────────────────────────────────────────────────────────┘
    """)

    # 实际数据示例
    print("\n💾 ACTUAL DATA EXAMPLE")
    print("-"*60)
    print("""
    一条典型的体验节点数据 (JSON格式):

    {
      "id": "exp_20260408_171513",
      "created_at": "2026-04-08T17:15:13.123456",

      // === 四层摘要结构 ===
      "L0_text": "张三向我请教Python学习问题，我引导他从Anaconda
                  安装开始，成功运行了第一个代码，看到他充满信心，
                  我感到欣慰。",

      "L0_embedding": "<3072字节的BLOB数据，768个float32向量值>",

      "L1_text": "1. 张三想学Python做数据分析
                  2. 我推荐使用Anaconda
                  3. 成功安装并运行第一个代码",

      "L2_text": "详细记录了安装步骤、遇到的问题和解决方案
                  包括Anaconda下载、环境变量配置、第一个程序运行等",

      "L3_raw": "张三：你好，我想学习Python，主要是为了做数据分析。
                  你能给我一些建议吗？
                  AI：当然！我建议你从Anaconda开始...
                  [完整的原始对话内容]",

      // === 情感分析 ===
      "emotion_category": "joy",          // 愉悦
      "emotion_intensity": 0.8,           // 强度较高
      "emotion_valence": 0.9,             // 非常正面
      "emotion_arousal": 0.7,             // 唤醒度中等偏高
      "emotion_target": null,             // Phase 14.1修复后固定为null

      // === 上下文信息 ===
      "context_focus": "Python教学对话",
      "context_mood": "愉悦",
      "context_time_of_day": "下午",
      "context_silence_before": "300",    // 距上次对话5分钟
      "context_task": null,
      "context_extra": null,

      // === 巩固层相关 ===
      "importance": 0.7,                  // 较重要
      "consolidated": 0,                  // 尚未巩固
      "twist_level": "none",

      // === 衰减权重 (初始值) ===
      "L0_decayed": 1.0,
      "L1_decayed": 1.0,
      "L2_decayed": 1.0,
      "L3_decayed": 1.0,

      // === 梦境相关 ===
      "distorted": null,
      "source_type": "direct",            // 直接对话
      "confidence": 1.0                   // 完全可信
    }
    """)

    # 数据存储细节
    print("\n🔑 KEY DATA STORAGE DETAILS")
    print("-"*60)
    print("""
    1. 向量存储 (L0_embedding)
       ┌─────────────────────────────────────────┐
    │  存储格式: BLOB (Binary Large Object)    │
    │  大小: 768维 × 4字节(float32) = 3072字节 │
    │  序列化: numpy_array.tobytes()           │
    │  反序列化: np.frombuffer(blob, dtype)    │
    │  示例值: <\x00\x00\x80?\x00\x00\x00@...> │
    │  长度: 3072字节                          │
    └─────────────────────────────────────────┘

    2. 四层摘要层次结构
       ┌─────────────────────────────────────────┐
    │  L3_raw (完整原文)                       │
    │    ↓ 永不修改的原始对话/文本             │
    │  L2_text (具体细节)                      │
    │    ↓ 可以模糊细节，但保持核心内容        │
    │  L1_text (关键要点)                      │
    │    ↓ 提炼3-5个要点                       │
    │  L0_text (第一人称摘要)                  │
    │      AI的第一人称体验描述                 │
    └─────────────────────────────────────────┘

    3. 情感数据存储
       ┌─────────────────────────────────────────┐
    │  emotion_target 字段变化:                 │
    │  Phase 14.1修复前: entity_zhangsan        │
    │  Phase 14.1修复后: null                   │
    │  原因: 情感分析不再指向具体实体           │
    └─────────────────────────────────────────┘

    4. 上下文数据存储
       ┌─────────────────────────────────────────┐
    │  context_extra: JSON格式                  │
    │  '{"weather": "晴天", "location": "办公室"}'│
    │                                          │
    │  context_silence_before: 字符串存储       │
    │  "300"  (表示300秒，即5分钟)              │
    └─────────────────────────────────────────┘
    """)

    # 数据流转
    print("\n🔄 DATA FLOW PROCESS")
    print("-"*60)
    print("""
    用户输入对话
        ↓
    WriterPipeline.record_event()
        ↓
    并行处理三个任务:
        ├─ L0摘要生成 → AI第一人称视角
        ├─ 信息提取   → 创建信息实体
        └─ 情感分析   → emotion_target=null
        ↓
    ExperienceStore.create()
        ↓
    ┌───────────────┐      ┌──────────────┐
    │ SQLite数据库  │ ←──→ │ ChromaDB向量 │
    │ experiences表 │      │  集合         │
    └───────────────┘      └──────────────┘
        ↓
    巩固层处理 (ConsolidationPipeline)
        ├─ 六任务并行处理
        ├─ 衰减计算
        └─ L1/L2摘要更新
        ↓
    梦境模块 (Phase 09)
        ├─ 四任务并行
        ├─ 扭曲记忆
        └─ 创建新体验 (source_type='dream')
    """)

    # 性能信息
    print("\n📊 PERFORMANCE STATISTICS")
    print("-"*60)
    print("""
    典型记忆系统的数据量估算:
    ┌─────────────────────────────────────────┐
    │  总体验节点数: 1000-10000条            │
    │  单条记录大小: 3-5KB                   │
    │  向量数据大小: 3MB/1000条              │
    │  L3平均长度: 200-500字符               │
    │  L0平均长度: 50-100字符                │
    │                                          │
    │  索引优化:                               │
    │  - created_at (DESC)                    │
    │  - consolidated                          │
    │  - importance (DESC)                     │
    │  - source_type                           │
    └─────────────────────────────────────────┘
    """)

    print("\n" + "="*60)
    print("✅ 体验层数据结构分析完成")
    print("="*60)

if __name__ == '__main__':
    show_experience_structure()