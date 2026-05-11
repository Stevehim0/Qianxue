# 千雪"电脑为家"架构改造计划

## 目标

把千雪从"住在 QQ/Discord 的聊天机器人"变成"住在用户电脑上的存在"。
QQ/Discord 是她看世界的窗户，电脑是她的家。

## 已完成

- [x] 屏幕感知 API + 截屏客户端
- [x] 统一身份系统（link_identity 工具，跨平台身份映射）

---

## Phase 1：本地聊天通道

### 1.1 AgentMessage 加 computer source

**文件**: `backend/services/agent/message.py`

- `source` 字段新增 `"computer"` 类型
- 新增 `is_computer` 计算属性（类似 `is_private`）

### 1.2 本地 WebSocket 端点

**文件**: `backend/routes/screen_routes.py` 扩展或新建 `backend/routes/computer_routes.py`

- `WS /ws/computer`：本地聊天 WebSocket
- 接收文本消息 → 构造 `AgentMessage(source="computer")` → 进入 debounce 队列
- 推送回复：brain 的 streaming 输出推回 WebSocket
- 同时支持推送系统通知（屏幕感知结果、身份映射更新等）

### 1.3 ComputerSource

**文件**: `backend/services/agent/sources/computer_source.py`

- 类似 `DiscordSource`，处理本地消息格式转换
- `group_id` 统一用 `"computer_home"`
- `user_id` 用 `"host_user"`（电脑主人）
- 自动设置 `is_mentioned=True`（本地聊天默认就是在跟千雪说话）

### 1.4 send_message 路由

**文件**: `backend/services/agent/tools/send_message.py`

- 加 `"computer"` 来源判断：group_id 为 `"computer_home"` 时，走 WebSocket 推送
- 需要一个全局的 WebSocket 连接引用（类似 voice_player 的模式）

### 1.5 本地聊天前端

**文件**: `frontend/` 新建

- 轻量 Web 页面：聊天窗口 + WebSocket 连接
- 支持流式显示（打字机效果）
- 显示屏幕感知状态指示器
- 纯静态 HTML/JS/CSS，不需要框架，由 FastAPI serve

---

## Phase 2：主动感知增强

### 2.1 心跳感知屏幕

**文件**: `backend/services/agent/brain.py`

- `_fetch_context_state()` 里，STM 感知已包含 `screen_perception` 事件
- 验证心跳时千雪能看到屏幕内容，能主动基于屏幕搭话

### 2.2 屏幕感知客户端增强

**文件**: `screen_capture_agent.py`

- 智能截屏：帧差分检测画面变化，变化大时才截图
- 窗口标题捕获（Windows API）
- 与本地前端整合（可选：在前端显示当前截屏缩略图）

---

## Phase 3：本地语音交互（后续）

### 3.1 本地语音输入

- 本地麦克风 → FunASR 转写 → 构造 AgentMessage → 进入对话管道
- 不经过 Discord，直接在电脑上完成

### 3.2 本地语音输出

- 千雪回复 → Edge TTS → 本地扬声器播放
- 不需要 Discord 语音频道

---

## 架构变更总览

```
新增文件：
  backend/services/agent/sources/computer_source.py
  backend/routes/computer_routes.py
  frontend/index.html + app.js + style.css

修改文件：
  backend/services/agent/message.py    — source 加 "computer"
  backend/services/agent/tools/send_message.py — computer 路由
  backend/main.py                      — 注册新路由 + computer message handler
  backend/services/agent/brain.py      — 验证 STM 屏幕感知集成
```

不改动的：
  记忆系统、LLM 调用层、流式架构、上下文管理器核心逻辑
