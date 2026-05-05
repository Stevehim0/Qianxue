---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: 实时语音功能
status: verifying
stopped_at: Phase 18 context gathered
last_updated: "2026-05-05T17:30:49.195Z"
last_activity: 2026-05-05
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 3
  completed_plans: 3
  percent: 100
---

# 项目状态

**项目开始时间:** 2026-03-31
**当前阶段:** v3.0 里程碑 — 实时语音功能
**最后更新:** 2026-05-04

## Current Position

Phase: 18 (SendVoice 语音回复工具) — EXECUTING
Plan: 1 of 1
Status: Phase complete — ready for verification
Last activity: 2026-05-05

Progress: [██████████] 100%

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-04)

**Core value:** 让AI像人类一样拥有记忆 - 不仅是存储和检索，而是主观的、会遗忘的、会做梦的、能联想的记忆体验

**Current focus:** Phase 18 — SendVoice 语音回复工具

## Performance Metrics

**Velocity:**

- Total plans completed (v2.0): 75+
- v3.0 plans completed: 1

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| 16. VoiceService 基础服务 | 1/1 | Complete |
| 17. AgentMessage 语音扩展 | 1/1 | Complete    |
| 18. SendVoice 语音回复工具 | 1/1 | Complete |
| 19. Discord 文字与语音消息 | 0/? | Not started |
| 20. Discord 语音频道实时流 | 0/? | Not started |
| 21. 基础设施与启动集成 | 0/? | Not started |
| Phase 16 P01 | 6min | 3 tasks | 5 files |
| Phase 17 P01 | 2min | 3 tasks | 3 files |
| Phase 18 P01 | 3min | 2 tasks | 4 files |

## Accumulated Context

### Previous Milestone (v2.0) Key Results

- 15 phases completed, memory system fully operational
- 双轨召回架构（向量检索 + 激活扩散）
- 梦境模块 + 实体识别 + Web可视化
- 69/76 core requirements (91%)

### v3.0 Architecture Decisions

- Voice is a modality (like images), integrated into existing architecture
- Receiving: message source handles ASR → AgentMessage (like vision_service)
- Sending: send_voice tool (like send_message)
- FunASR Server: independent process (WebSocket)
- Edge-TTS: integrated into backend
- Discord: first target platform for voice
- QQ: text only (no voice sending support)

### Key Risks (from research)

- FunASR sync client needs asyncio.to_thread() wrapping
- Edge-TTS reverse-engineered API can break, needs version pinning
- Audio format mismatch (Discord 48kHz stereo vs FunASR 16kHz mono)
- discord-ext-voice-recv is unstable, voice receiving is high-risk

### Blockers/Concerns

None yet.

### Phase 18 Decisions

- send_voice 工具始终注册（D-01），未连接时返回错误提示而非崩溃（D-02）
- voice_player 单例框架 Phase 18 connected=false（D-06），Phase 20 接入 Discord
- send_voice 加入 send_message 同组串行执行（brain.py），避免竞态条件
- user_id 使用 "robot"（不依赖 napcat_client）
- TTS 合成失败立即返回错误，不做部分投递

### Phase 17 Decisions

- Voice fields follow exact same pattern as image fields (bool + Optional[str])
- Voice processing branch independent from image branch (both can coexist)
- context_manager does not need code change — markers passed through in content

### Phase 16 Decisions

- Default TTS voice: zh-CN-XiaoxiaoNeural (Xiaoxiao) -- warm, natural tone matching Qianxue persona
- VoiceError raised on all failures, never return None -- callers decide retry strategy
- No retry logic in VoiceService -- failures propagate immediately
- ffmpeg as fallback for complex audio format conversion (MP3/OGG)
- FunASR WebSocket protocol: binary audio chunks + JSON end marker

## Session Continuity

Last session: 2026-05-05T17:29:18Z
Stopped at: Completed 18-01-PLAN.md
Resume file: .planning/phases/18-sendvoice/18-01-SUMMARY.md

---
*State updated: 2026-05-04 - Roadmap created for v3.0*
