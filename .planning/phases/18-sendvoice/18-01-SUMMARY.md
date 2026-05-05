---
phase: 18-sendvoice
plan: 01
subsystem: agent-tools
tags: [tts, voice, edge-tts, tool-registry, send_voice, voice_player]

# Dependency graph
requires:
  - phase: 16-voiceservice
    provides: VoiceService.synthesize() TTS 合成 + VoiceError 异常
  - phase: 17-agentmessage
    provides: AgentMessage 语音字段 (has_voice/voice_transcription)
provides:
  - SendVoiceTool 工具（注册在 ToolRegistry，AI 可在思考循环中选择语音回复）
  - VoicePlayer 单例框架（平台抽象层，Phase 18 connected=false）
  - send_voice 和 send_message 同组串行执行（brain.py）
  - 语音回复后处理管线（context_manager + memory + STM）
affects: [19-discord, 20-voicechannel]

# Tech tracking
tech-stack:
  added: []
  patterns: [voice-player-singleton, serial-tool-group, tts-sentence-splitting]

key-files:
  created:
    - backend/services/voice_player.py
    - backend/services/agent/tools/send_voice.py
  modified:
    - backend/main.py
    - backend/services/agent/brain.py

key-decisions:
  - "send_voice 工具始终注册（D-01），未连接时返回错误提示而非崩溃（D-02）"
  - "voice_player 单例框架 Phase 18 connected=false（D-06），Phase 20 接入 Discord"
  - "send_voice 加入 send_message 同组串行执行（D-05），避免竞态条件"
  - "send_voice 不导入 napcat_client（D-05），user_id 使用 robot（D-10）"
  - "分句伪流式策略：按句拆分 -> 逐句 TTS -> 队列播放（D-07）"

patterns-established:
  - "平台抽象层模式: voice_player 单例解耦工具与具体平台 API"
  - "串行工具组: brain.py 中 send_message + send_voice 串行执行，避免消息/语音竞态"

requirements-completed: [AGENT-03, AGENT-04, AGENT-05, AGENT-06]

# Metrics
duration: 3min
completed: 2026-05-06
---

# Phase 18 Plan 01: SendVoice 语音回复工具 Summary

**send_voice 工具框架 + VoicePlayer 平台抽象层，AI 可在思考循环中选择语音回复（Phase 18 未连接语音频道时返回错误提示）**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-05T17:26:08Z
- **Completed:** 2026-05-05T17:29:18Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- VoicePlayer 单例框架创建（is_connected=false，Phase 20 实现 Discord 连接）
- SendVoiceTool 工具完整实现（分句 TTS + 播放 + 上下文存储 + 记忆提取 + STM 记录）
- send_voice 注册到 ToolRegistry，AI 每个思考循环可见
- brain.py 更新为 send_message + send_voice 串行执行组

## Task Commits

Each task was committed atomically:

1. **Task 1: 创建 voice_player 框架和 send_voice 工具** - `848952b` (feat)
2. **Task 2: 注册 send_voice 工具并更新 brain 串行执行组** - `0144c42` (feat)

## Files Created/Modified
- `backend/services/voice_player.py` - VoicePlayer 单例框架（Phase 18 stub，connected=false）
- `backend/services/agent/tools/send_voice.py` - SendVoiceTool 工具实现（分句、TTS、播放、上下文存储）
- `backend/main.py` - SendVoiceTool 注册 + voice_player 导入和初始化日志
- `backend/services/agent/brain.py` - send_voice 加入 send_message 串行执行组

## Decisions Made
- user_id 使用 "robot" 而非 napcat_client.self_id（D-05: 不依赖平台 API）
- source_type 为 "voice_reply"（记忆系统）和 "voice_channel"（STM），与 send_message 区分
- 分句逻辑复用 send_message 的 _split_message 相同正则模式（[。！？\n]+）
- TTS 合成失败时立即返回错误，不做部分投递

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## Self-Check: PASSED

- All 5 files verified present
- Both task commits verified (848952b, 0144c42)
- No untracked files from this plan

## Next Phase Readiness
- send_voice 工具框架完成，Phase 19 加入 Discord 后 voice_player 可接收 Discord voice client
- Phase 20 需实现 VoicePlayer 的 connect/disconnect/play_sentences 方法
- 当前所有验证通过：导入链、工具注册、未连接错误返回、串行执行组

---
*Phase: 18-sendvoice*
*Completed: 2026-05-06*
