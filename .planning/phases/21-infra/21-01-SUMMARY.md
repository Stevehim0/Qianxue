---
phase: 21-infra
plan: 01
subsystem: infra
tags: [funasr, docker, health-check, ffmpeg, opus, edge-tts, discord-ext-voice-recv]

# Dependency graph
requires:
  - phase: 16-voiceservice
    provides: VoiceService + VoiceConfig (settings.voice)
  - phase: 20-discord
    provides: VoicePlayer with Opus/voice_recv checks pattern
provides:
  - voice_health.py module with 5 dependency check functions
  - check_voice_dependencies() orchestrator with unified logging
  - FunASR Docker container as start_all.py SERVICES[0]
  - main.py lifespan health check integration
affects: [startup, voice, infrastructure, monitoring]

# Tech tracking
tech-stack:
  added: [websockets (for health check), importlib.util]
  patterns: [lazy imports for optional dependencies, WARNING-only health checks]

key-files:
  created:
    - backend/services/voice_health.py
    - tests/test_voice_health.py
  modified:
    - start_all.py
    - backend/main.py

key-decisions:
  - "Lazy imports for discord/edge_tts inside functions: avoids ModuleNotFoundError when packages not installed"
  - "FunASR Docker uses Alibaba Cloud mirror (funasr_repo) for China mainland, no wait_for field"

patterns-established:
  - "Health check pattern: each check returns tuple[bool, str], orchestrator logs with [语音依赖] prefix"
  - "WARNING-only dependency checks: failures never block startup (D-04)"

requirements-completed: [INFRA-02, INFRA-03, INFRA-04]

# Metrics
duration: 7min
completed: 2026-05-08
---

# Phase 21: Infrastructure Integration Summary

**Voice infrastructure health checks (5 dependencies) + FunASR Docker container integration into startup pipeline**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-07T16:44:27Z
- **Completed:** 2026-05-07T16:51:44Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created voice_health.py with 5 independent dependency checks (FunASR, FFmpeg, Opus, Edge-TTS, voice_recv)
- Integrated FunASR Docker container as first service in start_all.py with Alibaba Cloud mirror
- Added check_voice_dependencies() call to main.py lifespan after voice service initialization
- All 10 mock unit tests passing (TDD: RED -> GREEN)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for voice_health module** - `2e97588` (test)
2. **Task 1 (GREEN): Voice_health module implementation** - `0ee0a34` (feat)
3. **Task 2: FunASR Docker + main.py integration** - `41351fd` (feat)

_Note: Task 1 used TDD with RED (failing test) then GREEN (implementation) commits._

## Files Created/Modified
- `backend/services/voice_health.py` - 5 voice dependency check functions + orchestrator with unified logging
- `tests/test_voice_health.py` - 10 mock unit tests covering all check functions (success/failure)
- `start_all.py` - FunASR Docker container as SERVICES[0], FunASR address in startup output
- `backend/main.py` - import + await check_voice_dependencies() in lifespan

## Decisions Made
- **Lazy imports for discord/edge_tts**: Used function-level imports instead of module-level to prevent ImportError when packages not installed in test/development environments. This aligns with the non-blocking philosophy (D-04).
- **Alibaba Cloud mirror for FunASR**: Using `registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr` as primary image source, with Docker Hub path documented as comment for overseas environments.
- **No wait_for on FunASR**: FunASR container needs to download models on first run (can take minutes). The health check in main.py will report availability status without blocking startup.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Lazy imports for optional dependencies**
- **Found during:** Task 1 (GREEN phase - test execution)
- **Issue:** Module-level `import discord` and `import edge_tts` cause ModuleNotFoundError when packages not installed (e.g., in test environment)
- **Fix:** Changed to function-level (lazy) imports inside `check_opus()` and `check_edge_tts()`. Updated tests to use `sys.modules` patching instead of direct module attribute mocking.
- **Files modified:** backend/services/voice_health.py, tests/test_voice_health.py
- **Verification:** All 10 tests pass, module import works without discord/edge_tts installed

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal - lazy imports are a best practice for optional dependencies. No scope creep.

## Issues Encountered
None - straightforward implementation following TDD workflow.

## User Setup Required
None - no external service configuration required. Docker is optional (FunASR check will show WARNING if container not running).

## Self-Check: PASSED

- All 5 files verified present (voice_health.py, test_voice_health.py, start_all.py, main.py, SUMMARY.md)
- All 3 task commits verified in git log (2e97588, 0ee0a34, 41351fd)
- 10 unit tests passing

## Next Phase Readiness
- All voice infrastructure checks integrated into startup pipeline
- v3.0 milestone core functionality complete (phases 16-21)
- Ready for any follow-up optimization or additional platform integrations

---
*Phase: 21-infra*
*Completed: 2026-05-08*
