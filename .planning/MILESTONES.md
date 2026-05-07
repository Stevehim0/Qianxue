# Milestones

## v3.0 实时语音功能 (Shipped: 2026-05-07)

**Phases completed:** 6 phases, 8 plans, 18 tasks

**Key accomplishments:**

- VoiceService singleton with FunASR WebSocket ASR, Edge-TTS synthesis, and automatic audio format conversion to 16kHz mono PCM
- send_voice 工具框架 + VoicePlayer 平台抽象层，AI 可在思考循环中选择语音回复（Phase 18 未连接语音频道时返回错误提示）
- Discord Bot 配置系统 + DiscordSource 消息源（消息转换、语音附件转写、发送能力），使用 discord.py 2.7 集成到 FastAPI 共享事件循环
- Discord connect/disconnect 工具 + send_message Discord 路由 + main.py 完整初始化与消息处理器接线
- Discord 语音频道 VoicePlayer：VoiceRecvClient 连接 + FFmpegOpusAudio 队列播放 + SilenceSegmentingSink 静音分割接收 + trigger_interruption 打断机制

---

## v2.0 — 完整记忆系统

**Status:** ✅ SHIPPED 2026-04-10
**Phases:** 01-15 (+ 额外优化)
**Timeline:** 2026-03-31 → 2026-04-10 (11天)

### Stats

- **Phases:** 15 (+ 额外优化)
- **Plans:** 75+ (with SUMMARY.md)
- **Commits:** 320+
- **Code:** ~31,741 LOC (源码) + ~16,128 LOC (测试)
- **Prompt Templates:** 17个
- **Requirements:** 69/76 core (91%)

### Key Accomplishments

1. **四层架构完整实现** — 写入→巩固→召回→存储闭环运行
2. **双轨召回架构** — 向量检索 + 激活扩散 + 记忆简报生成
3. **梦境模块** — 重组/情感/扭曲/推演四任务并行
4. **实体识别重设计** — 从"信息提取"回归"实体+属性"，符合存储层设计文档
5. **AI第一人称视角** — L0摘要使用AI主观视角体验
6. **Web可视化** — Flask + vis.js 网络图展示记忆

### Known Gaps (Deferred to v2.1)

- PROFILE-03/05/06/07/08/09: 个人档案高级功能
- QUAL-01~07: 工程质量（docstring、注释、错误处理、日志）
- Phase 11-03/04/05: 性能优化和文档完善

### Archived Files

- `.planning/milestones/v2.0-ROADMAP.md`
- `.planning/milestones/v2.0-REQUIREMENTS.md`
- `.planning/milestones/v2.0-MILESTONE-AUDIT.md`

---
*Last updated: 2026-04-10*
