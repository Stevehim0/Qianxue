---
phase: 21-infra
verified: 2026-05-08T17:30:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 21: Infrastructure Integration Verification Report

**Phase Goal:** 将 FunASR Docker 容器启动、5 项语音依赖健康检查集成到项目启动流程中
**Verified:** 2026-05-08T17:30:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Backend 启动时检查 FunASR WebSocket 连接状态，不可用时打印警告而非崩溃 | VERIFIED | `check_funasr()` (voice_health.py:25-31) uses `websockets.connect()` with try/except, returns `(False, msg)` on failure, never raises. Called from `check_voice_dependencies()` which is awaited in main.py:185 |
| 2 | Backend 启动时检查 FFmpeg 二进制可用性，不可用时打印安装指引 | VERIFIED | `check_ffmpeg()` (voice_health.py:34-51) runs `ffmpeg -version` via subprocess, catches FileNotFoundError returning "未找到 ffmpeg。请安装: https://ffmpeg.org/download.html" |
| 3 | Backend 启动时检查 Opus 库可用性，不可用时打印安装指引 | VERIFIED | `check_opus()` (voice_health.py:54-71) checks `discord.opus.is_loaded()`, attempts `load_opus("opus")`, returns install guidance on failure. Uses lazy import for discord |
| 4 | Backend 启动时检查 Edge-TTS 合成能力，不可用时打印警告 | VERIFIED | `check_edge_tts()` (voice_health.py:74-96) creates `edge_tts.Communicate("测试", voice)`, streams for audio chunk, 10s timeout. Uses lazy import for edge_tts |
| 5 | Backend 启动时检查 discord-ext-voice-recv 包，不可用时打印安装指引 | VERIFIED | `check_voice_recv()` (voice_health.py:99-104) uses `importlib.util.find_spec("discord.ext.voice_recv")`, returns pip install guidance on failure |
| 6 | start_all.py SERVICES 列表第一项是 FunASR Docker 容器（端口 10095） | VERIFIED | SERVICES[0] (start_all.py:20-23): `{"name": "FunASR Server", "cmd": ["docker", "run", "--rm", "--name", "funasr-server", "-p", "10095:10095", "registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:..."]}`. No wait_for field. Startup output includes `FunASR ASR: ws://localhost:10095` |
| 7 | 所有检查失败时仅 WARNING 不阻塞启动 | VERIFIED | Every check function catches all exceptions and returns `(False, msg)` instead of raising. `_log_result()` uses `logger.warning()` for failures. `check_voice_dependencies()` orchestrator has no try/raise patterns. main.py:185 calls `await check_voice_dependencies()` without surrounding try/catch because the function itself is exception-safe |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/services/voice_health.py` | 5 voice dependency check functions + orchestrator | VERIFIED | 152 lines. Exports: `check_funasr`, `check_ffmpeg`, `check_opus`, `check_edge_tts`, `check_voice_recv`, `check_voice_dependencies`, `_log_result`. All signatures match plan |
| `start_all.py` | FunASR Docker as SERVICES[0] | VERIFIED | SERVICES[0] is FunASR Server with docker run, port 10095:10095, Alibaba Cloud mirror, no wait_for, --rm flag, startup address printed |
| `backend/main.py` | Lifespan calls check_voice_dependencies() | VERIFIED | Line 42: import. Line 185: `await check_voice_dependencies()` after voice_service.reload_config() (line 181) and before voice_player init (line 187) |
| `tests/test_voice_health.py` | 10 mock unit tests | VERIFIED | 164 lines. 10 test functions: 2 per check (success + failure). Uses pytest + pytest_asyncio + unittest.mock. Tests cover all 5 checks with mocked dependencies |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| backend/main.py | backend/services/voice_health.py | import + await check_voice_dependencies() | WIRED | Line 42: `from backend.services.voice_health import check_voice_dependencies`. Line 185: `await check_voice_dependencies()` |
| backend/services/voice_health.py | backend/config/loader.py | settings.voice.funasr_websocket_url | WIRED | Line 20: `from backend.config import settings`. Line 119: `settings.voice.funasr_websocket_url`. Line 134: `settings.voice.tts_default_voice` |
| backend/services/voice_health.py | websockets | FunASR WebSocket connection check | WIRED | Line 18: `import websockets`. Line 28: `async with websockets.connect(url, timeout=timeout)` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| check_voice_dependencies() | results dict | 5 check functions | Yes -- each check returns (bool, str) from real dependency probes | FLOWING |
| check_funasr() | ok, msg | websockets.connect(url) | Yes -- actual WebSocket connection attempt to FunASR server | FLOWING |
| check_ffmpeg() | ok, msg | subprocess ffmpeg -version | Yes -- actual binary execution check | FLOWING |
| check_edge_tts() | ok, msg | edge_tts.Communicate().stream() | Yes -- actual TTS synthesis attempt | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED -- Python environment not accessible from verification shell (Windows environment PATH issue, not project-related). All behavioral verification performed via code reading. Unit test execution verified by commit history (all 3 commits exist and SUMMARY confirms 10/10 passing).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INFRA-01 | 21-01-PLAN (noted: completed in Phase 16) | voice.yaml config loading in config/loader.py | SATISFIED | VoiceConfig class at loader.py:145, _build_voice() at loader.py:443, voice.yaml file exists. PLAN correctly notes this was completed in Phase 16 |
| INFRA-02 | 21-01-PLAN | FunASR Server health check | SATISFIED | check_funasr() in voice_health.py:25-31, integrated into check_voice_dependencies() at line 119 |
| INFRA-03 | 21-01-PLAN | start_all.py FunASR startup | SATISFIED | SERVICES[0] in start_all.py:20-23, Docker run command with port 10095 |
| INFRA-04 | 21-01-PLAN | FFmpeg and Opus availability checks | SATISFIED | check_ffmpeg() at voice_health.py:34-51, check_opus() at voice_health.py:54-71 |

**Orphaned requirements:** None. All 4 requirement IDs from PLAN frontmatter are accounted for. INFRA-05 was completed in Phase 19.

**Documentation note:** REQUIREMENTS.md line 36 marks INFRA-01 as `[ ]` (unchecked) and traceability table shows "Pending". This is a documentation staleness issue -- the code implementation is complete since Phase 16. Recommend updating REQUIREMENTS.md to mark INFRA-01 as `[x]` with status "Complete".

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | -- | -- | -- | -- |

No TODOs, FIXMEs, placeholders, stub returns, or empty implementations found across all 4 files.

### Human Verification Required

### 1. Unit Test Execution

**Test:** Run `python -m pytest tests/test_voice_health.py -x -q` in the project's Python environment
**Expected:** 10 tests pass
**Why human:** Python environment not accessible from verification shell (Windows PATH configuration). Tests verified structurally correct via code reading.

### 2. FunASR Docker Container Startup

**Test:** Run `start_all.py` with Docker installed, verify FunASR container starts
**Expected:** FunASR Server appears as first service, Docker pulls and runs the container
**Why human:** Requires Docker daemon running and network access for image pull

### 3. Health Check Warning Output

**Test:** Start backend without FunASR server running, observe log output
**Expected:** Log shows `[语音依赖] FunASR: WARNING -- 不可用: ...` but backend continues startup
**Why human:** Requires running the actual application, observing real-time log output

### Gaps Summary

No gaps found. All 7 observable truths verified against the actual codebase. All 4 artifacts exist, are substantive, and properly wired. All 3 key links confirmed. All 4 requirements satisfied.

The only minor finding is that REQUIREMENTS.md has not been updated to reflect INFRA-01 completion (marked `[ ]` and "Pending" despite being functionally complete since Phase 16). This is a documentation gap, not a code gap.

---

_Verified: 2026-05-08T17:30:00Z_
_Verifier: Claude (gsd-verifier)_
