# Qianxue-master 记忆系统文档

本目录包含Qianxue-master AI Agent仿人类记忆系统的完整技术文档。

## 📚 文档列表

### 1. [DATA_FLOW.md](DATA_FLOW.md) - 数据流文档
**详细描述整个系统的数据流程，包括：**
- 系统层次结构和架构
- 写入流程详细分析（从用户输入到数据存储）
- 巩固流程详细分析（六任务并行处理）
- 召回流程详细分析（触发检测到最终结果）
- 数据在各层的状态变化
- 关键数据结构定义
- 性能考虑和优化策略

**适合读者:**
- 系统架构师
- 后端开发者
- 数据工程师
- 性能优化工程师

---

### 2. [API_REFERENCE.md](API_REFERENCE.md) - 接口文档
**完整记录所有对外暴露的API接口，包括：**
- MemoryAPI统一接口层（9个主要方法）
- WriterPipeline写入层接口
- RecallManager召回层接口
- ConsolidationPipeline巩固层接口
- 存储层接口（Experience/Entity/Edge存储）
- 状态层接口（StateManager）
- 核心层接口（CoreModifier）
- 异常处理和辅助类

**适合读者:**
- 应用开发者
- API集成工程师
- 测试工程师
- 文档维护者

---

## 🚀 快速开始

### 对于新用户

1. **阅读顺序:**
   - 先阅读 [DATA_FLOW.md](DATA_FLOW.md) 了解系统架构
   - 再阅读 [API_REFERENCE.md](API_REFERENCE.md) 学习如何使用

2. **快速示例:**
   ```python
   from Memory.api.memory_api import MemoryAPI

   # 初始化系统
   api = MemoryAPI()

   # 记录事件
   exp_id = api.receive_event("user", "My name is Alice")

   # 召回记忆
   recalls = api.check_recall("What's my name?", context={})
   ```

### 对于开发者

1. **贡献代码:**
   - 阅读 [DATA_FLOW.md](DATA_FLOW.md) 了解数据流
   - 参考 [API_REFERENCE.md](API_REFERENCE.md) 添加新接口

2. **性能优化:**
   - 关注并行处理和向量检索部分
   - 参考数据流文档中的性能考虑章节

---

## 📖 文档使用指南

### 数据流文档 (DATA_FLOW.md)

**主要内容:**
- ✅ 系统架构概览
- ✅ 写入流程（4个阶段详解）
- ✅ 巩固流程（3个Phase详解）
- ✅ 召回流程（7个阶段详解）
- ✅ 数据状态变化示例
- ✅ 关键数据结构
- ✅ 性能优化策略

**如何使用:**
- 理解系统整体架构 → 阅读"系统层次结构"
- 学习数据如何处理 → 阅读"写入流程详细分析"
- 了解记忆如何巩固 → 阅读"巩固流程详细分析"
- 掌握召回机制 → 阅读"召回流程详细分析"

---

### 接口文档 (API_REFERENCE.md)

**主要内容:**
- ✅ MemoryAPI - 9个主要接口
- ✅ WriterPipeline - 事件处理接口
- ✅ RecallManager - 记忆召回接口
- ✅ ConsolidationPipeline - 巩固处理接口
- ✅ 存储层接口 - CRUD操作
- ✅ 状态层接口 - AI状态访问
- ✅ 核心层接口 - 身份和信念管理
- ✅ 异常处理 - 6种异常类型
- ✅ 使用示例 - 实战代码

**如何使用:**
- 查找API方法 → 使用目录导航
- 学习参数用法 → 查看方法签名和参数说明
- 查看代码示例 → 参考"使用示例"章节
- 错误处理 → 参考"异常处理"章节

---

## 🔍 文档特点

### 数据流文档特点

1. **流程化描述:** 每个流程都分阶段详细描述
2. **代码示例:** 关键节点提供代码示例
3. **数据追踪:** 展示数据在各层的状态变化
4. **性能分析:** 分析性能瓶颈和优化策略

### 接口文档特点

1. **完整覆盖:** 包含所有对外暴露的接口
2. **分层组织:** 按系统层次组织接口
3. **详细说明:** 每个接口都有详细的参数和返回值说明
4. **实战导向:** 提供丰富的使用示例

---

## 🛠️ 技术细节

### 系统架构

```
MemoryAPI (统一接口层)
    ↓
WriterPipeline (写入层) | RecallManager (召回层) | ConsolidationPipeline (巩固层)
    ↓
Storage Layer (存储层) | Vector Store (向量存储) | State/Core Layer (状态/核心层)
    ↓
SQLite Database + ChromaDB
```

### 核心技术栈

- **数据库:** SQLite 3.x
- **向量存储:** ChromaDB 0.4.22
- **Embedding:** sentence-transformers (bge-base-zh)
- **LLM:** 千问/DeepSeek API
- **并发:** ThreadPoolExecutor

---

## 📝 文档维护

### 更新频率

- **数据流文档:** 架构变更时更新
- **接口文档:** 每次API变更时更新

### 贡献指南

1. **保持同步:** 代码变更时同步更新文档
2. **添加示例:** 新增接口时添加使用示例
3. **更新版本:** 每次更新修改"最后更新"日期

### 文档规范

1. **格式规范:** 使用Markdown格式
2. **命名规范:** 类名、方法名使用代码格式
3. **示例规范:** 代码示例要简洁易懂
4. **版本规范:** 记录文档版本号

---

## 🤝 支持与反馈

### 问题反馈

如果您发现文档中的错误或有改进建议，请：
1. 提交Issue到项目仓库
2. 在PR中描述文档变更内容
3. 保持文档的准确性和完整性

### 联系方式

- 项目仓库: [GitHub]
- 文档维护者: Claude (System Documentation)
- 最后更新: 2026-04-04

---

## 📄 许可证

本文档遵循项目的MIT许可证。

---

**祝您使用愉快！** 🚀

_最后更新: 2026-04-04_
_文档版本: 1.0_