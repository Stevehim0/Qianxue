# Requirements: 千雪实时语音功能

**Defined:** 2026-05-04
**Core Value:** 让AI像人类一样拥有记忆 — 语音是新的交互模态，扩展AI的感知和表达能力

## v3.0 Requirements (Milestone v3.0)

### 语音核心 (Voice Core)

- [x] **VOICE-01**: VoiceService 提供 `transcribe(audio_url)` 异步方法，通过 FunASR Server WebSocket 将音频转为文字
- [x] **VOICE-02**: VoiceService 提供 `synthesize(text, voice)` 异步方法，通过 Edge-TTS 将文字转为 MP3 音频
- [x] **VOICE-03**: VoiceService 作为单例服务，类似 vision_service 的模式，在 main.py 中初始化
- [x] **VOICE-04**: voice.yaml 配置文件，包含 FunASR Server 地址、Edge-TTS 音色、超时等参数
- [x] **VOICE-05**: FunASR WebSocket 客户端支持音频格式转换（自动转为 16kHz mono PCM）

### Agent 集成 (Agent Integration)

- [x] **AGENT-01**: AgentMessage 新增 `has_voice: bool`、`voice_url: Optional[str]`、`voice_transcription: Optional[str]` 字段
- [x] **AGENT-02**: Brain 的 `_build_user_message_header` 中处理语音转写，标注 `[语音消息转写]` 并展示内容
- [x] **AGENT-03**: send_voice 工具注册到 ToolRegistry，AI 可在思考循环中选择调用
- [x] **AGENT-04**: send_voice 工具描述明确告知 AI：仅在 Discord 等支持语音的平台可用
- [x] **AGENT-05**: send_voice 工具执行时调用 voice_service.synthesize() 生成音频，通过平台 API 发送
- [x] **AGENT-06**: send_voice 工具在不受支持的平台（如 QQ）返回错误提示

### Discord 平台 (Discord)

- [ ] **DISC-01**: Discord Bot 客户端（discord.py）连接并监听 Discord 服务器的文字和语音频道
- [ ] **DISC-02**: DiscordSource 将 Discord 文字消息转换为 AgentMessage 格式（类似 QQSource）
- [ ] **DISC-03**: DiscordSource 检测语音附件消息，调用 voice_service.transcribe() 转写后填入 AgentMessage
- [ ] **DISC-04**: Discord Bot 能加入语音频道并实时播放 TTS 生成的音频
- [ ] **DISC-05**: Discord 语音频道支持接收用户语音流，通过 FunASR 转写后进入对话流程
- [ ] **DISC-06**: 语音频道实时流支持打断机制（用户说话时停止当前 TTS 播放）

### 基础设施 (Infrastructure)

- [ ] **INFRA-01**: voice.yaml 配置加载集成到 config/loader.py
- [ ] **INFRA-02**: FunASR Server 健康检查端点（backend 启动时验证连接）
- [ ] **INFRA-03**: start_all.py 集成 FunASR Server 启动逻辑
- [ ] **INFRA-04**: FFmpeg 和 Opus 库可用性检查（Discord 语音必需）
- [ ] **INFRA-05**: Discord Bot token 和配置管理

## v3.1 Requirements (Deferred)

### 生产加固

- **PROD-01**: Edge-TTS 健康检查和自动降级（TTS 不可用时回退到文字）
- **PROD-02**: FunASR WebSocket 断线自动重连
- **PROD-03**: 长文本 TTS 自动分块（Edge-TTS 有 ~4KB 限制）
- **PROD-04**: 音频缓存机制（相同文本不重复合成）

### QQ 语音

- **QQ-01**: QQ 语音消息接收（NapCat [CQ:record] 格式解析）
- **QQ-02**: Silk v3 音频解码（QQ 语音编码格式）

### 高级功能

- **ADV-01**: 多 TTS 音色选择（根据千雪人设切换声音）
- **ADV-02**: 语音消息波形图生成（Discord 语音消息展示）
- **ADV-03**: VAD (Voice Activity Detection) 用于精确的说话端点检测

## Out of Scope

| Feature | Reason |
|---------|--------|
| QQ 语音消息发送 | NapCat 不稳定支持 silk 编码，实现复杂度高 |
| 多人语音会议 | 超出单聊/群聊的交互模型 |
| 实时翻译语音 | ASR/MT/TTS 链路过长，延迟不可接受 |
| 语音克隆 (GPT-SoVITS) | 需要 GPU 训练，部署复杂度超出本里程碑 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| VOICE-01 | Phase 16 | Complete |
| VOICE-02 | Phase 16 | Complete |
| VOICE-03 | Phase 16 | Complete |
| VOICE-04 | Phase 16 | Complete |
| VOICE-05 | Phase 16 | Complete |
| AGENT-01 | Phase 17 | Complete |
| AGENT-02 | Phase 17 | Complete |
| AGENT-03 | Phase 18 | Complete |
| AGENT-04 | Phase 18 | Complete |
| AGENT-05 | Phase 18 | Complete |
| AGENT-06 | Phase 18 | Complete |
| DISC-01 | Phase 19 | Pending |
| DISC-02 | Phase 19 | Pending |
| DISC-03 | Phase 19 | Pending |
| DISC-04 | Phase 20 | Pending |
| DISC-05 | Phase 20 | Pending |
| DISC-06 | Phase 20 | Pending |
| INFRA-01 | Phase 21 | Pending |
| INFRA-02 | Phase 21 | Pending |
| INFRA-03 | Phase 21 | Pending |
| INFRA-04 | Phase 21 | Pending |
| INFRA-05 | Phase 19 | Pending |

**Coverage:**
- v3.0 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-05-04*
*Last updated: 2026-05-04 after roadmap creation*
