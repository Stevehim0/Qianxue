# 记忆系统项目

## What This Is

为完全类人的AI Agent构建仿人类记忆系统。核心特性包括：AI以自我为主体、记忆是主观体验、像人一样遗忘（衰减/扭曲/模糊）、状态连续无会话边界。支持写入→巩固→召回的完整闭环，包含梦境模块、激活扩散、记忆扭曲等类人特性。

## Core Value

**让AI像人类一样拥有记忆** - 不仅是存储和检索，而是主观的、会遗忘的、会做梦的、能联想的记忆体验。记忆是AI决策和行为的底层驱动。

## Requirements

### Validated

- [x] 项目骨架和基础设施 - Phase 1 完成（2026-03-31）
  - INFRA-01: 项目目录结构完整，包含所有15个模块目录
  - INFRA-02: 全局配置系统（settings.py）支持所有配置项
  - INFRA-03: 14个 LLM prompt 模板使用 {variable} 占位符
  - INFRA-04: requirements.txt 包含所有依赖，版本固定
  - INFRA-05: main.py 入口文件能启动并验证配置

- [x] 存储层完整实现 - Phase 2 完成（2026-03-31）
  - STORE-01~08: SQLite + ChromaDB 完整实现

- [x] 基础服务层 - Phase 3 完成（2026-03-31）
  - EMBED-01~05: Embedding服务完整实现
  - LLM-01~06: LLM客户端完整实现

- [x] 核心层和状态层接口 - Phase 4 完成（2026-03-31）
  - CORE-01~05: 核心层完整实现
  - STATE-01~07: 状态层完整实现

- [x] 写入层完整实现 - Phase 5-6 完成（2026-03-31 ~ 2026-04-01）
  - WRITE-01~12: 写入层全部功能实现

- [x] 巩固层完整实现 - Phase 7-9 + Phase 12 完成（2026-04-01 ~ 2026-04-03）
  - CONSOLID-01~18: 巩固层全部18个需求实现
  - DREAM-01~04: 梦境模块完整实现

- [x] 召回层完整实现 - Phase 10 完成（2026-04-02）
  - RECALL-01~13: 召回层全部13个需求实现
  - 双轨召回架构（向量检索 + 激活扩散）

- [x] 系统集成 - Phase 11 完成（2026-04-02）
  - API-01~10: MemoryAPI统一接口完整实现
  - TEST-01~10: 端到端集成测试覆盖

- [x] Gap Closure - Phase 12-13 完成（2026-04-03）
  - 衰减计算修复（CONSOLID-11/12/13）
  - 个人档案基础功能（PROFILE-01/02/04）

- [x] 质量提升 - Phase 14-15 完成（2026-04-04 ~ 2026-04-09）
  - 系统验证与测试修复（336个错误修复）
  - AI第一人称视角修复
  - 实体识别重设计

- [x] 召回优化 - 额外优化（2026-04-10）
  - 双轨召回重构
  - 记忆简报生成
  - 实体关系发现

### Active

<!-- v3.0 milestone scope -->

- [x] 语音消息接收（ASR）— 消息源自动识别并转写语音 — Phase 19 完成（2026-05-07）
- [x] 语音消息发送（TTS）— AI可通过工具发送语音回复 — Phase 18 完成（2026-05-06）
  - AGENT-03: send_voice 工具注册在 ToolRegistry，AI 可见可选
  - AGENT-04: 工具描述明确告知 AI 仅在语音频道可用
  - AGENT-05: TTS 合成 + voice_player 播放链路
  - AGENT-06: 未连接语音频道时返回错误提示而非崩溃
- [x] Discord平台接入 — 消息源+工具+路由 — Phase 19 完成（2026-05-07）
  - DISC-01: DiscordSource 消息源（connect/disconnect/message handling）
  - DISC-02: 消息转换 Discord→AgentMessage + send_message Discord 路由
  - DISC-03: 语音附件自动检测、下载、ASR 转写
  - INFRA-05: discord.yaml 配置 + DiscordConfig dataclass
- [x] voice_service共享服务 — FunASR + Edge-TTS — Phase 16 完成（2026-05-04）
  - VOICE-01: transcribe() 异步方法，FunASR WebSocket 音频转文字
  - VOICE-02: synthesize() 异步方法，Edge-TTS 文字转MP3
  - VOICE-03: VoiceService 单例，main.py 初始化
  - VOICE-04: voice.yaml 配置文件
  - VOICE-05: 音频格式自动转换（16kHz mono PCM）

- [x] AgentMessage 语音扩展 — Phase 17 完成（2026-05-04）
  - AGENT-01: AgentMessage 新增语音元数据字段（has_voice/voice_url/voice_transcription）
  - AGENT-02: Brain 语音转写展示逻辑（[语音消息转写] 标注）

- [x] Discord 语音频道实时流 — Phase 20 完成（2026-05-07）
  - VOICE-06: VoicePlayer 连接 Discord 语音频道 + PCM 音频播放
  - VOICE-07: 语音接收（SilenceSegmentingSink）+ 实时打断
  - DISC-04: connect_discord / disconnect_discord 工具
- [x] 基础设施与启动集成 — Phase 21 完成（2026-05-08）
  - INFRA-02: FunASR WebSocket 健康检查
  - INFRA-03: start_all.py FunASR Docker 容器一键启动
  - INFRA-04: FFmpeg/Opus/Edge-TTS/voice_recv 依赖检查

- [ ] 个人档案高级功能 (PROFILE-03/05/06/07/08/09)
- [ ] 工程质量 (QUAL-01~07)

### Out of Scope

- **主动回忆机制** - AI独处时主动想起记忆（未来扩展）
- **自主行动记录** - AI的非对话行为写入记忆（未来扩展）
- **记忆驱动决策** - 记忆直接影响AI决策系统（未来扩展）
- **多用户支持** - 系统设计为个人使用，不考虑多租户
- **分布式部署** - 单机SQLite，不考虑分布式场景

## Context

### 项目完成状态

项目经过15个阶段 + 额外优化，全部核心功能已实现并正常运行：

**开发周期:** 2026-03-31 ~ 2026-04-10 (11天)
**阶段数:** 15 (+ 额外优化)
**需求完成:** 核心需求 102/115 (89%)

### 技术栈

| 组件 | 选型 | 版本要求 |
|---|---|---|
| 语言 | Python | 3.10+ |
| 数据库 | SQLite | 内置 |
| 向量库 | ChromaDB | 0.4+ |
| Embedding | bge-base-zh | via sentence-transformers |
| LLM | 千问或DeepSeek | API调用 |
| 并发 | ThreadPoolExecutor | 内置 |
| Web | Flask + vis.js | 可视化 |

### 实现成果

**四层架构完整实现:**
1. **写入层** - 原始事件记录 + 并行处理（L0/实体/情感）
2. **巩固层** - 六任务并行 + 衰减计算 + 梦境模块 + 实体关系发现
3. **召回层** - 双轨召回（向量检索 + 激活扩散）+ 记忆简报
4. **存储层** - SQLite + ChromaDB 持久化

**系统数据:**
- 体验节点: 72
- 实体节点: 122
- 边: 303
- 梦境节点: 65
- 可视化Web界面

### 协作模式

- 用户负责设计决策和思路指导（文档已完整）
- AI负责代码实现（遵循设计文档）
- 分阶段完成，每阶段包含规划→实现→验证

## Constraints

- **技术栈锁定**: 必须使用设计文档中确定的技术栈（Python/SQLite/ChromaDB/bge-base-zh）
- **代码质量**: 代码结构必须清晰，模块化设计，易于理解和扩展
- **L3不可侵犯**: 原始记录永远不能修改，这是铁律
- **同名即同人**: 实体识别允许误会，但数据库层面强制name唯一
- **增量优先**: 巩固层先处理新增未巩固节点，有余力再全量
- **异步并行**: 写入层步骤2三项并行，巩固层Phase1六项并行，梦境四项并行
- **激活扩散缓存**: 使用内存邻接表缓存，不走数据库实时查询
- **梦境独立**: 梦境模块用专门的system prompt，和正常对话完全不同

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 分阶段实现 | 项目规模大，需要逐步验证 | 按工程文档11步分解为15个阶段 |
| 核心层/状态层暂不实现 | 降低初期复杂度，聚焦记忆核心 | 预留接口，第一版用默认值 |
| 只收敛不迎合 | AI以自我为主体，不服务用户 | 个人档案相处方式调整原则 |
| 先LLM后轻量模型 | 召回后处理先训练数据积累 | 后续替换为轻量分类模型 |
| ThreadPoolExecutor | LLM调用通常是同步SDK | 避免异步复杂度，用线程池并行 |
| 双轨召回架构 | 向量检索+激活扩散互补 | 更全面的记忆召回 |
| 实体识别重设计 | 从"信息提取"回归"实体+属性" | 符合存储层设计文档 |
| 记忆简报生成 | 为AI提供结构化记忆摘要 | briefing模块独立 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

## Current Milestone: v3.0 实时语音功能 — COMPLETE

**Goal:** 为千雪AI系统添加语音消息的接收(ASR)和发送(TTS)能力，作为模态集成到现有工具架构中，支持Discord等平台

**Status:** All 6 phases (16-21) complete. 8 plans executed.

**Completed features:**
- voice_service 共享语音服务（FunASR Server ASR + Edge-TTS TTS）— Phase 16
- AgentMessage 语音扩展（has_voice/voice_url/voice_transcription）— Phase 17
- send_voice 工具 — AI可选择发送语音消息 — Phase 18
- Discord 消息源（文字+语音附件+语音频道）— Phase 19-20
- 基础设施与启动集成（健康检查+FunASR Docker）— Phase 21

---
*State initialized: 2026-03-31*
*Last updated: 2026-05-08 after v3.0 milestone completion (Phase 21 infra)*
