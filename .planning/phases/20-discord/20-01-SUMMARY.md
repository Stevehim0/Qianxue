---
phase: 20-discord
plan: 01
subsystem: voice
tags: [discord, voice-channel, discord-ext-voice-recv, ffmpeg, opus, audio-sink, tts, asr, interruption]

# Dependency graph
requires:
  - phase: 18-sendvoice
    provides: voice_player 框架占位（connect/disconnect/play_sentences 签名）
  - phase: 19-discord
    provides: DiscordSource Bot 实例、discord.yaml 配置系统、DiscordConfig dataclass
  - phase: 16-voiceservice
    provides: VoiceService.transcribe() ASR、VoiceService.synthesize() TTS

provides:
  - VoicePlayer 完整实现（Discord 语音频道连接、TTS 队列播放、语音接收、打断机制）
  - SilenceSegmentingSink（能量检测静音分割 AudioSink 子类）
  - voice_channel_id 配置字段（discord.yaml + DiscordConfig）

affects: [20-02-PLAN, send_voice 工具, connect_discord 工具]

# Tech tracking
tech-stack:
  added: [discord-ext-voice-recv, PyNaCl, davey]
  patterns: [AudioSink 静音分割模式, FFmpegOpusAudio 管道播放, after 回调链式播放, run_coroutine_threadsafe 线程桥接]

key-files:
  created: []
  modified:
    - backend/services/voice_player.py
    - backend/config/discord.yaml
    - backend/config/loader.py

key-decisions:
  - "SilenceSegmentingSink 模块级继承 voice_recv.AudioSink（try/except ImportError 降级为 object）"
  - "触发打断使用 stop_playing() 而非 stop()，保持语音接收不被中断"
  - "48kHz 立体声 PCM 包装为 WAV bytes，由 VoiceService._convert_to_pcm() 自动重采样"

patterns-established:
  - "AudioSink 子类模式：wants_opus()=False 接收 PCM，write() 线程安全，run_coroutine_threadsafe 调度异步"
  - "播放队列链式模式：play_sentences 入队列，after 回调驱动 _play_next_chunk"
  - "打断三步模式：设标志 + 清队列 + stop_playing()"

requirements-completed: [DISC-04, DISC-05, DISC-06]

# Metrics
duration: 6min
completed: 2026-05-07
---

# Phase 20 Plan 01: VoicePlayer 核心实现 Summary

**Discord 语音频道 VoicePlayer：VoiceRecvClient 连接 + FFmpegOpusAudio 队列播放 + SilenceSegmentingSink 静音分割接收 + trigger_interruption 打断机制**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-06T18:24:42Z
- **Completed:** 2026-05-07
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- VoicePlayer 完整实现替代 Phase 18 占位框架，支持 Discord 语音频道连接/断开/播放/打断
- SilenceSegmentingSink 能量检测静音分割，48kHz 立体声 PCM 接收，300ms 打断确认延迟
- discord.yaml 新增 voice_channel_id 配置字段，DiscordConfig dataclass 对应扩展

## Task Commits

Each task was committed atomically:

1. **Task 1: Add voice_channel_id to Discord config** - `8b6f8ed` (feat)
2. **Task 2: Implement VoicePlayer with Discord voice channel + AudioSink + interruption** - `d7289b4` (feat)

## Files Created/Modified
- `backend/services/voice_player.py` - VoicePlayer 完整实现 + SilenceSegmentingSink（447 行，从 49 行框架重写）
- `backend/config/discord.yaml` - 新增 voice_channel_id: null 配置
- `backend/config/loader.py` - DiscordConfig 新增 voice_channel_id 字段 + _build_discord() 读取

## Decisions Made
- SilenceSegmentingSink 在模块级直接继承 voice_recv.AudioSink，用 try/except ImportError 降级为 object 基类，避免运行时才能确定继承关系的问题
- 打断使用 stop_playing()（只停播放，不停接收），符合 research R-05 的 VoiceRecvClient API
- 语音段处理：48kHz 立体声 PCM 直接包装为 WAV，利用已有的 VoiceService._convert_to_pcm() 自动重采样为 16kHz mono

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- discord-ext-voice-recv 未安装在 Miniconda 环境中，执行验证前安装了 discord-ext-voice-recv + PyNaCl + davey 依赖
- SilenceSegmentingSink 初始使用动态继承（__init__ 中 AudioSink.__init__(self)），issubclass 检查失败，改为模块级直接继承

## User Setup Required

None - voice_channel_id 默认为 null（不自动加入语音频道），需要用户在 discord.yaml 中配置后才能使用。

## Next Phase Readiness
- VoicePlayer 核心就绪，Plan 02 需要扩展 connect_discord/disconnect_discord 工具和 main.py 初始化
- set_bot() 和 set_message_handler() 已就绪，等待 Plan 02 调用注入
- voice_player.play_sentences() 已实现真实播放，send_voice 工具无需修改即可工作

## Self-Check: PASSED

- voice_player.py: FOUND
- discord.yaml: FOUND
- loader.py: FOUND
- 20-01-SUMMARY.md: FOUND
- 8b6f8ed (Task 1): FOUND
- d7289b4 (Task 2): FOUND

---
*Phase: 20-discord*
*Completed: 2026-05-07*
