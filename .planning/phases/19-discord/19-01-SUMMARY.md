---
phase: 19-discord
plan: 01
subsystem: discord-integration
tags: [discord.py, bot, config, message-source, voice-transcription, agent-message]

# Dependency graph
requires:
  - phase: 16-voiceservice
    provides: VoiceService.transcribe() for voice attachment transcription
  - phase: 17-agentmessage
    provides: AgentMessage voice fields (has_voice, voice_url, voice_transcription)
provides:
  - "discord.yaml config with token, channels, dm_enabled, voice settings"
  - "DiscordConfig + DiscordVoiceConfig dataclasses in loader.py"
  - "DiscordSource class: message conversion, voice transcription, send, bot lifecycle"
  - "Module-level discord_source singleton (initialized by Plan 02)"
affects: [19-02, send_message, main.py, voice_player]

# Tech tracking
tech-stack:
  added: [discord.py>=2.3.0]
  patterns: [message-source-pattern, bot-lifecycle-per-connect, message-splitting]

key-files:
  created:
    - backend/config/discord.yaml
    - backend/services/agent/sources/discord_source.py
  modified:
    - backend/config/loader.py

key-decisions:
  - "Bot instance not reusable: new Bot() per connect(), destroyed on disconnect() (RISK-02)"
  - "DM group_id format: dm_{user_id} prefix for Discord private messages"
  - "send_voice_file method created for Phase 18 integration, actual usage in Phase 20"
  - "fetch_user() used for DM sending instead of get_user() to handle uncached users (RISK-04)"

patterns-established:
  - "DiscordSource mirrors QQSource pattern: receive -> convert -> AgentMessage -> handler"
  - "Config section pattern: YAML + dataclass + _build_X() + section_names/section_dc_class registration"
  - "Voice attachment flow: detect -> download to BytesIO -> voice_service.transcribe(bytes)"

requirements-completed: [DISC-01, DISC-02, DISC-03, INFRA-05]

# Metrics
duration: 5min
completed: 2026-05-07
---

# Phase 19 Plan 01: Discord Configuration & Message Source Summary

**Discord Bot 配置系统 + DiscordSource 消息源（消息转换、语音附件转写、发送能力），使用 discord.py 2.7 集成到 FastAPI 共享事件循环**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-06T17:03:22Z
- **Completed:** 2026-05-07
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- Discord 配置系统：discord.yaml + DiscordConfig dataclass + 环境变量覆盖支持
- DiscordSource 完整实现：消息接收/转换、语音附件检测与转写、消息发送（含 2000 字符限制分割）
- Bot 生命周期管理：每次 connect() 创建新实例，disconnect() 销毁，解决 RISK-02

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Discord config** - `af47764` (feat)
2. **Task 2: Create DiscordSource class** - `0508ec1` (feat)

## Files Created/Modified

- `backend/config/discord.yaml` - Discord Bot 配置（token, channels, dm_enabled, voice settings）
- `backend/config/loader.py` - 新增 DiscordConfig + DiscordVoiceConfig dataclasses，_build_discord() 方法
- `backend/services/agent/sources/discord_source.py` - DiscordSource 消息源（消息转换、语音转写、发送、Bot 生命周期管理）

## Decisions Made

- **Bot 不可重用（RISK-02）：** 每次 connect() 创建新 Bot 实例，disconnect() 销毁并置 None。避免 discord.py RuntimeError
- **DM group_id 格式：** 使用 `dm_{user_id}` 前缀，与 QQ 的 `private_{user_id}` 模式平行但可区分来源
- **fetch_user vs get_user：** DM 发送使用 `fetch_user()`（API 调用），解决用户不在缓存中的问题（RISK-04）
- **send_voice_file 方法：** 为 Phase 18 send_voice 工具预留 Discord 发送通道，实际使用在 Phase 20

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Discord Bot token 配置属于部署时操作。

## Next Phase Readiness

- Plan 01 完成，为 Plan 02（工具注册 + 路由集成）奠定基础
- Plan 02 需要创建 connect_discord / disconnect_discord 工具，注册到 ToolRegistry
- Plan 02 需要修改 send_message 工具添加 Discord 路由分支
- Plan 02 需要在 main.py 初始化 discord_source 单例

---
*Phase: 19-discord*
*Completed: 2026-05-07*

## Self-Check: PASSED

- FOUND: backend/config/discord.yaml
- FOUND: backend/services/agent/sources/discord_source.py
- FOUND: .planning/phases/19-discord/19-01-SUMMARY.md
- FOUND: af47764 (Task 1 commit)
- FOUND: 0508ec1 (Task 2 commit)
