# 千雪项目路线图

## Milestones

- ✅ **v2.0 完整记忆系统** — Phases 01-15 + 额外优化 (shipped 2026-04-10) → [查看归档](milestones/v2.0-ROADMAP.md)
- 🚧 **v3.0 实时语音功能** — Phases 16-21 (in progress)

## Phases

<details>
<summary>✅ v2.0 完整记忆系统 (Phases 01-15) — SHIPPED 2026-04-10</summary>

### 阶段列表

- [x] Phase 01: 项目骨架和基础设施 (4 plans) — 2026-03-31
- [x] Phase 02: 存储层实现 (6 plans) — 2026-03-31
- [x] Phase 03: 基础服务层 (4 plans) — 2026-03-31
- [x] Phase 04: 核心层和状态层接口 (4 plans) — 2026-03-31
- [x] Phase 05: 写入层-基础功能 (1 plan) — 2026-03-31
- [x] Phase 06: 写入层-并行处理 (7 plans) — 2026-04-01
- [x] Phase 07: 巩固层-Phase1六任务并行 (5 plans) — 2026-04-01
- [x] Phase 08: 巩固层-Phase2衰减计算 (3 plans) — 2026-04-01
- [x] Phase 09: 梦境模块 (4 plans) — 2026-04-02
- [x] Phase 10: 召回层 (8 plans) — 2026-04-02
- [x] Phase 11: 整合与优化 (6/7 plans) — 2026-04-02
- [x] Phase 12: 修复衰减计算 (4 plans) — 2026-04-03
- [x] Phase 13: 个人档案系统集成 (6 plans) — 2026-04-03
- [x] Phase 14: 系统验证与测试修复 (8 plans) — 2026-04-04
- [x] Phase 14.1: 修复AI第一人称视角 (5 plans) — 2026-04-08
- [x] Phase 15: 实体识别重设计 (5 plans) — 2026-04-09
- [x] 额外优化: 双轨召回重构 + 记忆简报 — 2026-04-10

### 统计

- **总阶段:** 15 + 额外优化
- **开发周期:** 11天 (2026-03-31 ~ 2026-04-10)
- **源码:** ~31,741 LOC
- **测试:** ~16,128 LOC
- **需求完成:** 69/76 (91%)
- **Prompt模板:** 17个
- **Git commits:** 320+

</details>

### 🚧 v3.0 实时语音功能 (In Progress)

**Milestone Goal:** 千雪能接收语音消息(ASR转写)和发送语音回复(TTS合成)，并通过Discord平台支持语音频道实时交互

- [x] **Phase 16: VoiceService 基础服务** - 语音ASR/TTS核心服务，含配置和音频格式处理 (completed 2026-05-04)
- [x] **Phase 17: AgentMessage 语音扩展** - 消息模型增加语音字段，Brain处理语音转写展示 (completed 2026-05-04)
- [x] **Phase 18: SendVoice 语音回复工具** - AI可选择发送语音回复，平台感知路由 (completed 2026-05-05)
- [x] **Phase 19: Discord 文字与语音消息** - Discord Bot接入，文字消息和语音附件消息处理 (completed 2026-05-06)
- [ ] **Phase 20: Discord 语音频道实时流** - 语音频道加入/播放/接收/打断机制
- [ ] **Phase 21: 基础设施与启动集成** - 配置加载、健康检查、启动脚本、依赖检查

## Phase Details

### Phase 16: VoiceService 基础服务
**Goal**: 语音核心能力可用——系统可以将音频文件转为文字(ASR)，也可以将文字转为音频文件(TTS)
**Depends on**: Nothing (独立基础，与 Phase 17 可并行)
**Requirements**: VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05
**Success Criteria** (what must be TRUE):
  1. 给定一段中文语音文件，VoiceService.transcribe() 返回正确的文字转写结果
  2. 给定一段中文文字，VoiceService.synthesize() 返回可播放的 MP3 音频文件
  3. voice.yaml 配置文件存在且包含 FunASR 地址、Edge-TTS 音色、超时等所有参数
  4. VoiceService 在 main.py 中以单例模式初始化，与 VisionService 模式一致
  5. FunASR 客户端自动处理音频格式转换（任意输入转为 16kHz mono PCM）
**Plans**: 1 plan
Plans:
- [x] 16-01-PLAN.md -- VoiceService config + service + integration (VOICE-01~05)

### Phase 17: AgentMessage 语音扩展
**Goal**: 消息数据模型支持语音元数据，Brain 可以识别并展示语音转写内容
**Depends on**: Nothing (独立于 Phase 16，可并行开发)
**Requirements**: AGENT-01, AGENT-02
**Success Criteria** (what must be TRUE):
  1. AgentMessage 包含 has_voice、voice_url、voice_transcription 三个新字段，均有默认值不影响现有代码
  2. 当消息包含语音转写文本时，Brain 的用户消息头显示 "[语音消息转写]" 前缀及转写内容
  3. 现有的纯文字消息处理流程不受任何影响（向后兼容）
**Plans**: 1 plan
Plans:
- [x] 17-01-PLAN.md -- AgentMessage 语音字段 + Brain 展示 + context_manager 标记 (AGENT-01, AGENT-02)

### Phase 18: SendVoice 语音回复工具
**Goal**: AI 可以在思考循环中选择发送语音回复，且仅在有语音能力的平台上生效
**Depends on**: Phase 16 (需要 VoiceService.synthesize 生成音频)
**Requirements**: AGENT-03, AGENT-04, AGENT-05, AGENT-06
**Success Criteria** (what must be TRUE):
  1. send_voice 工具注册在 ToolRegistry 中，AI 在思考循环中可以看到并选择调用
  2. send_voice 工具描述明确告知 AI：仅在 Discord 等支持语音的平台可用
  3. 在 Discord 平台调用 send_voice 时，AI 的文字回复被转为语音并发送给用户
  4. 在不支持语音的平台（如 QQ）调用 send_voice 时，返回错误提示而非崩溃
**Plans**: 1 plan
Plans:
- [x] 18-01-PLAN.md -- VoicePlayer 单例 + SendVoiceTool + brain 串行执行 + main 注册 (AGENT-03~06)

### Phase 19: Discord 文字与语音消息
**Goal**: 千雪可以通过 Discord 文字频道收发消息，并能接收和转写语音附件消息
**Depends on**: Phase 16 (需要 VoiceService.transcribe 转写语音), Phase 17 (需要 AgentMessage 语音字段)
**Requirements**: DISC-01, DISC-02, DISC-03, INFRA-05
**Success Criteria** (what must be TRUE):
  1. Discord Bot 连接到指定服务器并监听文字频道消息
  2. 用户在 Discord 文字频道发送的消息被正确转为 AgentMessage 并进入千雪对话流程
  3. 用户在 Discord 发送语音附件消息时，千雪自动转写语音内容并正常回复
  4. Discord Bot token 和服务器配置可管理，不在代码中硬编码
**Plans**: 2 plans
Plans:
- [x] 19-01-PLAN.md -- Discord config + DiscordSource message source (DISC-01~03, INFRA-05)
- [x] 19-02-PLAN.md -- connect/disconnect tools + send_message routing + main.py init (DISC-01, DISC-02)

### Phase 20: Discord 语音频道实时流
**Goal**: 千雪可以加入 Discord 语音频道，实时播放 TTS 音频并接收用户语音流
**Depends on**: Phase 18 (需要 send_voice 工具中的 TTS 能力), Phase 19 (需要 Discord Bot 连接)
**Requirements**: DISC-04, DISC-05, DISC-06
**Success Criteria** (what must be TRUE):
  1. 千雪 Bot 可以加入 Discord 语音频道并播放 TTS 生成的音频流
  2. 用户在语音频道说话时，千雪能接收语音流并通过 FunASR 转写后进入对话流程
  3. TTS 音频播放过程中，如果用户开始说话，千雪停止当前播放并处理用户输入（打断机制）
**Plans**: TBD
**UI hint**: yes

### Phase 21: 基础设施与启动集成
**Goal**: 所有语音相关基础设施集成到项目启动和健康检查流程中
**Depends on**: Phase 16 (配置需要先定义), Phase 19 (Discord 集成需要先完成)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):
  1. voice.yaml 配置通过 config/loader.py 正确加载，VoiceConfig 数据类可用
  2. 后端启动时检查 FunASR Server 连接状态，不可用时打印警告而非崩溃
  3. start_all.py 包含 FunASR Server Docker 容器的启动逻辑
  4. 系统启动时验证 FFmpeg 和 Opus 库可用性，缺失时给出明确安装指引
**Plans**: TBD

## Progress

**Execution Order:**
Phases 16-17 (可并行) → 18 → 19 → 20 → 21

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 16. VoiceService 基础服务 | 1/1 | Complete    | 2026-05-04 |
| 17. AgentMessage 语音扩展 | 1/1 | Complete    | 2026-05-04 |
| 18. SendVoice 语音回复工具 | 1/1 | Complete    | 2026-05-05 |
| 19. Discord 文字与语音消息 | 2/2 | Complete   | 2026-05-06 |
| 20. Discord 语音频道实时流 | 0/? | Not started | - |
| 21. 基础设施与启动集成 | 0/? | Not started | - |

---
*Last updated: 2026-05-06*
