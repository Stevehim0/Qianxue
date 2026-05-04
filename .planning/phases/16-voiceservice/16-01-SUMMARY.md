---
phase: 16-voiceservice
plan: 01
subsystem: voice
tags: [funasr, edge-tts, websockets, asr, tts, audio, pcm, ffmpeg]

# Dependency graph
requires: []
provides:
  - VoiceService singleton with transcribe() (FunASR ASR) and synthesize() (Edge-TTS TTS)
  - voice.yaml config file with FunASR WebSocket URL, Edge-TTS voice, audio conversion params
  - VoiceConfig dataclass accessible via settings.voice
  - ConfigManager.get_voice_config() for DB override support
  - VoiceError custom exception for voice service failures
  - Audio format conversion (_convert_to_pcm) for WAV/MP3/OGG/PCM to 16kHz mono
affects: [17-agentmessage, 18-sendvoice, 19-discord, 21-infra]

# Tech tracking
tech-stack:
  added: [edge-tts, websockets]
  patterns: [voice-service-singleton, funasr-websocket-protocol, edge-tts-streaming, ffmpeg-audio-conversion]

key-files:
  created:
    - backend/config/voice.yaml
    - backend/services/voice_service.py
  modified:
    - backend/config/loader.py
    - backend/db_config.py
    - backend/main.py

key-decisions:
  - "Default TTS voice: zh-CN-XiaoxiaoNeural (Xiaoxiao) -- warm, natural, matches Qianxue persona (D-01)"
  - "VoiceError raised on all failures, never return None -- callers decide retry (D-03/D-04/D-05)"
  - "No retry logic in VoiceService -- failures propagate immediately to caller (D-05)"
  - "synthesize() accepts optional voice parameter to override default (D-02)"
  - "ffmpeg as fallback for complex audio format conversion (MP3/OGG)"

patterns-established:
  - "VoiceService singleton: module-level instance matching VisionService pattern"
  - "Config hot-reload: reload_config() from config_manager, DB overrides via get_voice_config()"
  - "Audio detection by magic bytes: WAV (RIFF), MP3 (0xFFFB), OGG (OggS), default raw PCM"

requirements-completed: [VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05]

# Metrics
duration: 6min
completed: 2026-05-04
---

# Phase 16 Plan 01: VoiceService Base Summary

**VoiceService singleton with FunASR WebSocket ASR, Edge-TTS synthesis, and automatic audio format conversion to 16kHz mono PCM**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-04T09:09:32Z
- **Completed:** 2026-05-04T09:16:07Z
- **Tasks:** 3
- **Files modified:** 4 created/modified

## Accomplishments
- Created voice.yaml config with FunASR WebSocket URL, Edge-TTS voice settings, and audio conversion parameters
- Implemented VoiceService with transcribe() (FunASR WebSocket) and synthesize() (Edge-TTS streaming)
- Built audio format conversion pipeline supporting WAV/MP3/OGG/PCM with ffmpeg fallback
- Integrated VoiceService into main.py lifespan with config reload and startup logging

## Task Commits

Each task was committed atomically:

1. **Task 1: Create voice.yaml config and VoiceConfig dataclass** - `3d1a763` (feat)
2. **Task 2: Implement VoiceService with transcribe, synthesize, and audio conversion** - `5d809fe` (feat)
3. **Task 3: Wire VoiceService into main.py lifespan** - `8bcb85e` (feat)

## Files Created/Modified
- `backend/config/voice.yaml` - Voice service configuration (FunASR WebSocket, Edge-TTS voice/audio params)
- `backend/services/voice_service.py` - VoiceService singleton with ASR/TTS/format conversion
- `backend/config/loader.py` - VoiceConfig dataclass, _build_voice(), Settings.voice field
- `backend/db_config.py` - ConfigManager.get_voice_config() with DB override support
- `backend/main.py` - VoiceService import and initialization in lifespan

## Decisions Made
- Default voice zh-CN-XiaoxiaoNeural (Xiaoxiao) selected for warm, natural tone matching Qianxue persona (D-01)
- VoiceError raised on all failures instead of returning None -- callers must handle exceptions (D-03/D-04)
- No internal retry logic -- VoiceService fails fast, callers decide retry strategy (D-05)
- ffmpeg used as fallback for complex format conversion (MP3/OGG), WAV handled by Python wave module
- FunASR WebSocket protocol: send binary audio chunks (4096 bytes), then JSON `{"is_end": true}`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Python not on PATH in this environment; used /d/Miniconda/python.exe for verification. This is a local environment issue, not a project issue.

## User Setup Required
None - no external service configuration required at this stage. FunASR Server connectivity will be validated at runtime.

## Next Phase Readiness
- VoiceService singleton ready for use by downstream phases (Phase 17: AgentMessage voice extension, Phase 18: send_voice tool, Phase 19: Discord voice messages)
- transcribe() and synthesize() methods available for integration into message processing pipeline
- Audio format conversion handles common formats; ffmpeg needed for MP3/OGG input

---
*Phase: 16-voiceservice*
*Completed: 2026-05-04*

## Self-Check: PASSED

- FOUND: backend/config/voice.yaml
- FOUND: backend/services/voice_service.py
- FOUND: backend/config/loader.py
- FOUND: backend/db_config.py
- FOUND: backend/main.py
- FOUND: .planning/phases/16-voiceservice/16-01-SUMMARY.md
- FOUND: 3d1a763 (Task 1 commit)
- FOUND: 5d809fe (Task 2 commit)
- FOUND: 8bcb85e (Task 3 commit)
