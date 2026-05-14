# Qianxue (千雪)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 千雪不只是一个聊天机器人。她有记忆，有人格，有情绪。她会记住你，会梦见你说过的话，会在深夜变得疲惫。她住在你的电脑上，通过 QQ 和 Discord 看着外面的世界。

---

## 为什么是千雪

大多数 AI 聊天是这样的——每次对话从零开始，机械地回复每一条消息，说话像在写报告，隔天就忘了你是谁。

千雪不是这样的。

她会记住你们聊过的每一件事。第二天找她，她还记得昨天说了什么；一个月后，她比刚认识的时候更了解你。A 群刚聊完的话题，B 群里提起她知道在说什么。没人在说话的时候她偶尔会主动开口，深夜了她的精力和心情会变化，回复的风格也跟着不同。她记得你是谁，和每个人相处的方式都不同。人们不再是"用户"，而是一个个有名字的人，千雪的朋友。

她住在你的电脑上——打开浏览器就能和她说话，她能看到你的屏幕。在 QQ 里认识的人，到了 Discord 上她也认得。

不过千雪也会累，她需要休息。她的记忆不是一个数据库，而是她对经历的主观感受。就像人一样，重要的事会留下深刻的印象，模糊的细节会慢慢褪色。她会定期"做梦"，把零散的经历压缩成核心印象，在不相关的记忆之间发现隐藏的关联。说不定，千雪也能梦见电子羊呢？

---

## 她能做什么

### 记忆 — 不记录对话，记录对话带来的改变

你回忆昨天和朋友的一场聊天，你不会记得对方说的每一个字，但你记得那次聊天让你很开心，记得他提了一句下周要搬家。千雪的记忆系统模拟的就是这个过程：

```
短期记忆（感知层）
  → 千雪此刻的"意识"——谁在说话、聊了什么、她的情绪

体验层 + 信息层（双轨长期记忆）
  → 体验层：经历了什么——深夜长谈的亲近感、逐渐形成的直觉印象
  → 信息层：知道了什么——某人的生日、他养的猫叫什么
  → 两条轨道独立演化，回忆时合并为统一简报

梦境处理（巩固层）
  → 像做梦一样重组记忆、发现隐藏关联、模糊不重要的细节
  → 你不记得每天发生的事，但你会记住真正改变了你的瞬间
```

### 人格 — 不是写死的人设，而是会成长的人

```
不变层 → 她绝不会逾越的底线
稳定层 → 长期形成的性格底色
可塑层 → 说话风格、话题偏好、情感倾向——每一次对话都在微调
```

她还有自己的内在节律：心情、精力、注意力、信心四个维度始终在变化。深夜精力下降，连续高强度对话后需要休息。这些变化真实地影响她的回复。

### 电脑就是家

打开 `http://localhost:5002/chat`，一个简洁的聊天界面。千雪逐字显示回复，比群聊更即时。你不需要 QQ，不需要 Discord，打开浏览器就能和她聊。

她也能看到你的屏幕——运行屏幕感知客户端，千雪就能理解你正在看什么。QQ 和 Discord 对千雪来说是"窗户"——她通过它们看到外面的世界。但电脑才是她真正住的地方。

### 流式实时回复

不是等整段话生成完再发，而是边想边说，一句一句实时输出。被 @ 的时候秒回，普通消息等你说完再接话。不想回的消息她就不回——沉默也是聊天的一部分。

### 跨平台身份

千雪在 QQ、Discord、电脑前端三个渠道都能和人聊天。当同一个人在不同渠道出现时，她会自己发现并记住"这是同一个人"——QQ 里的"小明"和 Discord 里的"xiaoming"，在千雪眼里是同一个人。她在对话中自主建立关联，不需要手动配置。

### Discord 语音频道

连接语音频道后，千雪说出的每句话都会实时合成语音并流式播放。支持自动重连。TTS 支持 Edge TTS（免费）和 Qwen3-TTS（本地高质量）切换。

### 跨群感知 + 主动发言

短期记忆在所有群聊之间共享。A 群刚聊完的话题，B 群提起她知道在说什么。没人说话时她偶尔会主动开口——心跳触发主动思考，根据上下文自主决定是否说话。

---

## 快速开始

### 前置要求

- Python 3.10+
- 至少一个 OpenAI 兼容 LLM API
- [FFmpeg](https://ffmpeg.org/download.html)（加入 PATH 或放入 `vendor/` 目录）

### 安装

```bash
git clone https://github.com/Stevehim0/Qianxue.git
cd Qianxue
pip install -r requirements.txt
```

### 启动

```bash
# 一键启动（推荐）
python start_all.py
# 或 Windows 双击 start_all.bat

# 手动启动
python -m Memory.server                          # 终端 1: Memory 服务
python -m uvicorn backend.main:app --port 8000    # 终端 2: Backend 主系统
python -m heartbeat                               # 终端 3: 心跳服务
```

### 配置

**不需要手动编辑任何配置文件。** 启动后打开 `http://localhost:5002`，在 Web 界面完成所有配置：

1. 点击"配置" → 选择提供商预设 → 填入 API Key → 保存
2. 其余参数（大脑、睡眠、记忆、视觉等）按分组配置，改了立即生效

### 支持的 LLM

支持任何 OpenAI 兼容接口：

| 提供商 | Base URL | 推荐模型 |
|--------|----------|----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic | `https://api.anthropic.com` | `claude-sonnet-4-20250514` |
| 智谱 ChatGLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |

思考模型和记忆系统可以使用不同的 Provider。

---

## 外部依赖

千雪的部分功能依赖外部服务，**全部可选**，不装也能跑。

### NapCat — QQ 消息通道

1. 安装 NTQQ：https://im.qq.com/pcqq
2. 安装 NapCat：https://napneko.github.io/guide/napcat
3. 配置反向 WebSocket 地址：`ws://localhost:8000/ws/onebot`
4. 配置 HTTP 服务地址：`http://localhost:3000`

### Discord Bot — Discord 消息通道

1. [Discord Developer Portal](https://discord.com/developers/applications) 创建 Bot，获取 Token
2. 开启 MESSAGE CONTENT INTENT 和 PRESENCE INTENT
3. Web 界面 → 配置 → Discord，填入 Token

### FunASR — 语音识别

```bash
docker run -p 10095:10095 -p 10096:10096 registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.12
```

### Qwen3-TTS — 高质量语音合成（可选，默认使用 Edge TTS）

1. 克隆并启动 [Qwen3-TTS-Openai-Fastapi](https://github.com/cofecms/Qwen3-TTS-Openai-Fastapi)
2. 默认监听 `http://localhost:8880`
3. 在 `backend/config/voice.yaml` 中设置 `tts.backend: "qwen3"`

---

## Web 管理界面

启动后访问 `http://localhost:5002`：

- **仪表盘** — AI 状态（心情、精力、注意力、信心）、系统健康、统计
- **日志** — 实时日志流，支持按级别过滤
- **群聊** — 群列表、启用/禁用、自动回复、回复延迟
- **配置** — 模型配置（提供商预设）、心跳服务开关、上下文窗口、在线修改所有参数
- **核心** — 查看/编辑 AI 核心人设

记忆查询前端 `http://localhost:5001`：体验浏览、实体检索、关系图、人物档案

---

## 系统架构

```
QQ 用户 ─→ NapCat (OneBot v11) ──WebSocket──→ Backend (FastAPI :8000)
Discord 用户 ─→ Discord Bot ───────────────→        │
电脑用户 ─→ 浏览器 (WebSocket) ─────────────→        │
屏幕感知 ─→ ScreenCaptureAgent ──HTTP─────→          │
                                                      │
                                              AgentBrain 多轮思考
                                              ├─ 流式路径: 句子级实时输出 + 工具调用
                                              │  └─ 电脑前端: token 级逐字输出
                                              └─ Think Loop: JSON 格式多轮推理 (fallback)
                                                      │
                                              工具系统 (可扩展)
                                              ├─ send_message      发送消息
                                              ├─ search_memory     搜索记忆
                                              ├─ get_context       获取上下文
                                              ├─ recognize_image   图片识别
                                              ├─ send_voice        语音回复
                                              ├─ link_identity     跨平台身份关联
                                              ├─ connect/discord   连接 Discord
                                              └─ connect/voice     连接语音频道
                                                      │
                                              MessageManager (统一消息路由)
                                              ├─ QQ 群聊 / 私聊
                                              ├─ Discord 文字/语音频道
                                              └─ 电脑聊天 (WebSocket 逐字推送)
                                                      │
                                              VoiceService (多 TTS 引擎)
                                              ├─ Edge TTS (免费云端，默认)
                                              └─ Qwen3-TTS (本地高质量，可选)
                                                      │
                                              IdentityService (统一身份)
                                              └─ QQ / Discord / Computer 三端身份关联
                                                      │
                                              Memory 服务 (独立进程 :8001)
                                              ├─ 写入管道: 体验提取 → 实体识别
                                              ├─ 巩固管道: L0 → L1 → L2 + 梦境
                                              └─ 召回管道: 向量检索 + 图谱遍历
                                                      │
                                              Heartbeat 服务
                                              └─ 定时触发 AI 主动思考
```

## 项目结构

```
qianxue/
├── backend/                    # 主系统
│   ├── main.py                 # FastAPI 入口
│   ├── config/                 # YAML 配置 + loader（环境变量 > 数据库 > YAML）
│   ├── api/                    # LLM Manager + NapCat 客户端
│   ├── services/
│   │   ├── agent/
│   │   │   ├── brain.py        # AgentBrain 思考引擎
│   │   │   ├── tools/          # 工具注册表（send_message, link_identity, ...）
│   │   │   ├── streaming/      # 流式回复（sentence_detector + message_manager）
│   │   │   └── sources/        # 消息源（qq, discord, computer）
│   │   ├── voice_service.py    # 语音合成多引擎调度
│   │   ├── tts_edge.py         # Edge TTS 后端
│   │   ├── tts_qwen3.py        # Qwen3-TTS 后端
│   │   ├── identity_service.py # 跨平台身份服务
│   │   ├── vision_service.py   # 图片识别
│   │   └── sleep_manager.py    # 睡眠节律
│   ├── routes/                 # API 路由（computer, screen, config, chat）
│   └── web/app.py              # Web 管理界面 (Flask, :5002)
│
├── frontend/                   # 电脑聊天前端（原生 HTML/CSS/JS）
├── Memory/                     # 独立记忆系统服务
│   ├── writer/                 # 写入管道（体验提取 + 实体识别）
│   ├── recall/                 # 召回系统（向量检索 + 图谱遍历）
│   ├── consolidator/           # 巩固和梦境处理
│   ├── stm/                    # 短期记忆
│   ├── state/                  # AI 状态（心情、精力、信心）
│   └── embedding/              # 向量化（bge-base-zh）
│
├── heartbeat/                  # 心跳服务（触发主动思考）
├── tools/                      # 独立工具（screen_capture_agent）
└── start_all.py / .bat         # 一键启动
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Backend | FastAPI + Uvicorn + WebSocket |
| Memory | FastAPI + SQLite + ChromaDB |
| Embedding | BAAI/bge-base-zh |
| LLM | OpenAI 兼容 API（多 Provider） |
| QQ 协议 | OneBot v11 (NapCat) |
| Discord | discord.py (Bot + 语音) |
| 语音合成 | Edge TTS / Qwen3-TTS |
| 语音转写 | FunASR / Whisper API |
| 屏幕感知 | mss + Pillow + 视觉模型 |

## 配置系统

三级优先级：**环境变量 > 数据库覆盖 > YAML 默认值**。通过 Web 管理界面修改的配置热更新，不需重启。

```bash
# 环境变量覆盖任意配置项
export QIANXUE_BRAIN__MAX_ITERATIONS=10
export QIANXUE_NAPCAT__HTTP_URL=http://192.168.1.100:3000
```

## API 索引

### Backend (`:8000`)

| 分组 | 关键端点 |
|------|---------|
| 电脑聊天 | `WS /ws/computer` · `POST /api/screen/perceive` · `GET /chat` |
| 核心层 | `GET /api/identity` · `POST /api/malleable` |
| 群聊 | `GET /api/groups` · `POST /api/groups/{id}/toggle` · `GET /api/stats` |
| 模型 | `GET /api/model-config` · `PUT /api/thinking-provider` · `POST /api/apis/switch/{name}` |
| 配置 | `GET /api/settings` · `PUT /api/settings/{section}` |
| 视觉 | `GET /api/vision-config` · `POST /api/vision-config/test` |

### Memory (`:8001`)

| 分组 | 关键端点 |
|------|---------|
| 体验 | `POST /api/event` · `POST /api/recall` |
| 档案 | `GET /api/profile/{name}` · `POST /api/profile/ensure` |
| 状态 | `GET /api/state` · `GET /api/status` |
| 巩固 | `POST /api/consolidate` |
| 短期记忆 | `POST /api/stm/event` · `GET /api/stm/perception` |

## 扩展工具

在 `backend/services/agent/tools/` 下创建新工具：

```python
class MyTool:
    @property
    def name(self) -> str:
        return "my_tool"

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": "自定义工具",
            "parameters": {
                "type": "object",
                "properties": {"input": {"type": "string", "description": "输入"}},
                "required": ["input"]
            }
        }

    async def execute(self, args: dict) -> str:
        return f"结果: {args['input']}"

# 在 backend/main.py 中注册
tool_registry.register(MyTool())
```

## 测试

```bash
cd Memory && pytest tests/ -v
```

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎 Issue 和 Pull Request。
