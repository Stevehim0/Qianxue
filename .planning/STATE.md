---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: 实时语音功能
status: verifying
stopped_at: Completed 17-01-PLAN.md
last_updated: "2026-05-04T10:08:20Z"
last_activity: 2026-05-04 -- Phase 17 Plan 01 complete
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 2
  completed_plans: 2
  percent: 100
---

# 项目状态

**项目开始时间:** 2026-03-31
**当前阶段:** v3.0 里程碑 — 实时语音功能
**最后更新:** 2026-05-04

## Current Position

Phase: 17 (AgentMessage 语音扩展) — COMPLETE
Plan: 1/1 (complete)
Status: Phase 17 complete — all plans executed
Last activity: 2026-05-04

Progress: [██████████] 100%

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-04)

**Core value:** 让AI像人类一样拥有记忆 - 不仅是存储和检索，而是主观的、会遗忘的、会做梦的、能联想的记忆体验

**Current focus:** Phase 17 — AgentMessage 语音扩展

## Performance Metrics

**Velocity:**

- Total plans completed (v2.0): 75+
- v3.0 plans completed: 1

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| 16. VoiceService 基础服务 | 1/1 | Complete |
| 17. AgentMessage 语音扩展 | 1/1 | Complete    |
| 18. SendVoice 语音回复工具 | 0/? | Not started |
| 19. Discord 文字与语音消息 | 0/? | Not started |
| 20. Discord 语音频道实时流 | 0/? | Not started |
| 21. 基础设施与启动集成 | 0/? | Not started |
| Phase 16 P01 | 6min | 3 tasks | 5 files |
| Phase 17 P01 | 2min | 3 tasks | 3 files |

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

Last session: 2026-05-04T10:08:20Z
Stopped at: Completed 17-01-PLAN.md
Resume file: .planning/phases/17-agentmessage/17-01-SUMMARY.md

---
*State updated: 2026-05-04 - Roadmap created for v3.0*
