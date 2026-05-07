# 千雪 AI — 记忆与语音系统

## What This Is

为千雪AI构建仿人类记忆系统 + 实时语音交互能力。记忆系统模拟人类主观记忆体验（遗忘、梦境、联想），语音系统支持 ASR/TTS 和 Discord 语音频道实时交互。

## Core Value

**让AI像人类一样拥有记忆** - 不仅是存储和检索，而是主观的、会遗忘的、会做梦的、能联想的记忆体验。语音是新的交互模态，扩展AI的感知和表达能力。

## Requirements

### Validated

- [x] v2.0 完整记忆系统 — 15 phases, 75+ plans (2026-04-10)
- [x] v3.0 实时语音功能 — 6 phases, 8 plans (2026-05-08)
  - VoiceService ASR/TTS 核心服务（FunASR + Edge-TTS）
  - AgentMessage 语音字段扩展
  - send_voice 工具 + VoicePlayer 平台抽象层
  - Discord 文字消息 + 语音附件 + 语音频道实时流
  - 基础设施集成（健康检查 + FunASR Docker）

### Active

- [ ] 个人档案高级功能 (PROFILE-03/05/06/07/08/09)
- [ ] 工程质量 (QUAL-01~07)

### Out of Scope

- **主动回忆机制** - AI独处时主动想起记忆（未来扩展）
- **自主行动记录** - AI的非对话行为写入记忆（未来扩展）
- **记忆驱动决策** - 记忆直接影响AI决策系统（未来扩展）
- **多用户支持** - 系统设计为个人使用，不考虑多租户
- **分布式部署** - 单机SQLite，不考虑分布式场景

## Context

### 当前状态

v3.0 里程碑完成。千雪具备完整记忆系统 + Discord 语音交互能力。

**v2.0 记忆系统:** 15 phases, 69/76 requirements (91%), ~31,741 LOC
**v3.0 语音功能:** 6 phases, 8 plans, 18 tasks, 52 files, 6,174 LOC added

### 技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.10+ | asyncio + FastAPI |
| 记忆存储 | SQLite + ChromaDB | 向量检索 + 关系图 |
| ASR | FunASR Server | Docker WebSocket, 16kHz mono |
| TTS | Edge-TTS | Xiaoxiao 音色 |
| Discord | discord.py 2.7 | Bot + voice channel + voice_recv |
| 音频处理 | FFmpeg + Opus | 格式转换 + 语音编码 |
| LLM | DeepSeek / 千问 | API 调用 |

## Constraints

- **技术栈锁定**: Python/SQLite/ChromaDB/bge-base-zh
- **L3不可侵犯**: 原始记录永远不能修改
- **同名即同人**: 实体识别允许误会，数据库层面强制name唯一
- **可选依赖优雅降级**: discord.py/edge_tts/Docker 缺失时 WARNING 不崩溃

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 语音是模态 | 与图片同模式，集成到现有架构 | ✓ 简洁统一 |
| VoiceService 单例 | 匹配 VisionService 模式 | ✓ 一致性好 |
| Bot 每次连接新建 | discord.py Bot 实例不可重用 | ✓ 避免 RuntimeError |
| Lazy import discord | 可选依赖不阻塞启动 | ✓ UAT 验证通过 |
| 健康检查 WARNING 不阻塞 | 开发环境常缺依赖 | ✓ 启动流程不中断 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*State initialized: 2026-03-31*
*Last updated: 2026-05-08 after v3.0 milestone completion*
