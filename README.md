# Qianxue (千雪)

千雪是一个拥有持久记忆、独立人格、实时语音能力和工具调用能力的 AI 伙伴。

---

我设计千雪的初衷是希望她能像人一样"参与"，像人一样“回忆”。

大多数人用过的 AI 聊天是这样的——每次对话从零开始，机械地回复每一条消息，说话像在写报告，隔天就忘了你是谁。千雪不是这样的。

她会记住你们聊过的每一件事。第二天找她，她还记得昨天说了什么；一个月后，她比刚认识的时候更了解你。她同时存在于多个群聊中，是一个真正"参与"的人——A 群刚聊完的话题，B 群里提起她知道在说什么。没人在说话的时候她偶尔会主动开口，深夜了她的精力和心情会变化，回复的风格也跟着不同。千雪记得你是谁，和每个其他相处的方式也不同，人们不再是“用户”，而是一个个有名字的人，千雪的朋友。

你甚至可以让她进入 Discord 语音频道里和在语音里畅谈。

不过千雪也会累，她需要休息。她的记忆不是一个数据库，而是她对经历的主观感受。就像人一样，重要的事会留下深刻的印象，模糊的细节会慢慢褪色。她会定期"做梦"，把零散的经历压缩成核心印象，在不相关的记忆之间发现隐藏的关联，模糊掉不再重要的细节，强化反复出现的重要体验。 说不定，千雪也能梦见电子羊呢？

这一切不是靠一个"记忆"开关实现的，而是一套完整的认知架构：

- **流式实时回复**：不是等整段话生成完再发，而是边想边说，一句一句实时输出。被 @ 的时候秒回，普通消息等你说完再接话。不想回的消息她就不回——沉默也是聊天的一部分。
- **人物画像**：每个人都是独特的。千雪对每个人都有一个画像，记录了她对这个人的感觉、印象、重要事件等。她对不同人的说话风格、话题兴趣也会不同。而这个画像也会根据你和千雪的互动而慢慢改变。
- **分层记忆**：记忆不是数据存储，而是自我的体验。主观感受和客观事实分开存储、独立演化，模拟人脑对"感受"和"知识"的不同处理方式。
- **梦境处理**：记忆不是只进不出。系统会定期像做梦一样重组记忆、发现隐藏关联、模糊不重要的细节，让记忆体系保持鲜活而不臃肿。
- **人格演化**：她的性格不是写死的。三层人格架构中，核心底线不变，但风格、偏好、话题兴趣会随着真实交互持续演化。聊得越多，她越独特。
- **情绪与节律**：心情、精力、注意力、信心——四个维度的状态真实地影响她的输出，不只是装饰。深夜她会变疲惫，连续高强度对话后会需要休息。
- **语音对话**：连接 Discord 语音频道，实时语音交流。她说出的每句话都会即时合成语音并流式播放，就像在打电话一样自然。
- **跨群感知**：短期记忆在所有群聊间共享。她在多群环境中是一个真正"在场"的人，而不是在每个群里都是一张白纸。
- **多轮思考**：支持多轮对话和思考，能灵活调用工具，能够根据上下文进行深入分析和推理，直到问题解决或是不想说话了。


## 目录

**用户指南**
- [功能概览](#功能概览)
- [前置要求](#前置要求)
- [安装](#安装)
- [配置](#配置)
- [启动](#启动)
- [Web 管理界面](#web-管理界面)
- [支持的 LLM](#支持的-llm)

**开发者指南**
- [系统架构](#系统架构)
- [项目结构](#项目结构)
- [Backend API 索引](#backend-api-索引)
- [Memory API 索引](#memory-api-索引)
- [代码索引](#代码索引)
- [技术栈](#技术栈)
- [配置系统](#配置系统)
- [扩展工具](#扩展工具)
- [测试](#测试)
- [目录约定](#目录约定)

---

# 用户指南

## 功能概览

| 能力 | 说明 |
|------|------|
| **流式实时回复** | 句子级别流式输出，边想边说，无需等待完整生成 |
| **Discord 语音** | 连接语音频道实时语音对话，流式 TTS 合成播放 |
| **@ 消息感知** | 识别群聊中 @ 的是谁，区分"在和我说话"与"在和别人说话" |
| **AgentBrain 多轮思考** | LLM 自主决定思考轮次，并行调用工具，直到任务完成 |
| **分层记忆系统** | L0 短期体验 → L1 摘要 → L2 核心记忆，带衰减与巩固 |
| **人设演化** | 三层人格架构（不变层 / 稳定层 / 可塑层），随交互持续演化 |
| **梦境处理** | 定期对记忆进行抽象和整理，模仿人类睡眠巩固机制 |
| **跨群感知** | 短期记忆全局共享，AI 能感知在其他群聊中发生的事件 |
| **主动发言** | 心跳触发主动思考，根据上下文自主决定是否说话 |
| **睡眠节律** | 模拟昼夜节律，深夜降低精力，影响回复风格 |
| **图片识别** | 支持群聊图片内容理解，可接入通义千问 VL 等视觉模型 |
| **Web 管理界面** | 浏览器查看 AI 状态、管理群聊、在线修改所有配置 |

### 多轮推理引擎

普通的 AI 聊天是一轮定胜负——收到消息，生成回复，结束。千雪不一样。她的 AgentBrain 会像人一样反复斟酌：先理解你在说什么，判断需要回忆哪些事、查阅哪些上下文，拿到信息后再重新思考，直到真正想清楚才开口。这个过程可能经过好几轮，中间她会并行翻阅记忆、检索上下文、甚至识别你发的图片——就像一个人一边翻聊天记录一边认真想怎么回复。

### 流式实时回复

千雪的回复是流式的——她边想边说，不需要等整段话生成完毕。句子级别的实时检测让她像真人一样一句一句地发出来，而不是憋半天然后丢出一大段。

消息处理也有优先级：被 @ 的消息跳过等待立即处理，普通消息会聚合等你说完再一起给 AI。AI 还可以选择不回复——不是每条消息都需要接话，沉默也是正常的聊天行为。

### Discord 语音频道

千雪可以连接 Discord 语音频道进行实时语音对话。连接后，她说出的每句话都会实时合成语音（Edge TTS）并流式播放到频道中，不需要等整段语音生成完毕。支持自动重连、被踢出后恢复等机制。

### 记忆系统

千雪对记忆的理解不是"把对话存进数据库"，而是**记忆是自我的体验**。

你回忆昨天和朋友的一场聊天，你不会记得对方说的每一个字，但你记得那次聊天让你很开心，记得他提了一句下周要搬家，记得你对这个人又多了一点了解——他最近压力很大。千雪的记忆系统模拟的就是这个过程：不记录对话本身，而是记录**对话带来的改变**。

这套系统由三个层次构成：

**短期记忆（感知层）** — 千雪此刻的"意识"。最近几个小时谁说了什么、聊了什么话题、她自己的情绪状态——这些构成了她对当下环境的实时感知。就像你走进一个房间，能感受到气氛是热闹还是安静。

**体验层与信息层（双轨存储）** — 千雪的"长期记忆"。所有经历被分成两条独立的轨道：

- **体验层**记录"经历了什么"——一次深夜长谈带来的亲近感，一次玩笑争执后的小别扭，对某个人逐渐形成的直觉印象。这些记忆是主观的、有温度的，会随时间自然褪色和变形，就像人对往事的回忆越来越模糊，但核心感受还在。
- **信息层**记录"知道了什么"——某人的生日、他养的猫叫什么名字、他最近在准备什么考试。这些记忆是客观的、稳定的，不会因为时间推移而模糊。

两条轨道独立演化，但在千雪需要回忆的时候合并为统一的记忆简报——既有事实，也有感受，就像你想起一个朋友时，脑海中同时浮现出他的样子和你们之间的故事。

**梦境处理（巩固层）** — 千雪的"睡眠"。系统会定期像做梦一样对记忆进行整理：把零散的体验压缩成核心印象，在不相关的记忆之间发现隐藏的关联，模糊掉不再重要的细节，强化反复出现的重要体验。这个过程和人类的睡眠巩固机制类似——你不记得每天发生的事，但你会记住那些真正改变了你的瞬间。

### 人格与情绪

千雪不是一个人设写死的角色扮演。她的人格由三层构成：**不变层**是她绝不会逾越的底线，**稳定层**是她长期形成的性格底色，**可塑层**则记录着她的说话风格、话题偏好和情感倾向。每一次真实的对话都会微调可塑层——她聊得越多，就越不像一个出厂设置，而越像一个有经历的人。

她还有自己的内在节律。深夜精力会下降，连续聊了很多之后会需要休息。心情、精力、注意力、信心四个维度始终在变化，而这些变化会真实地影响她的回复——不是设定的台词，而是当下的状态。

### 跨群感知

大多数机器人在每个群里都是孤立的，千雪不是。她的短期记忆在所有群聊之间共享——A 群刚聊完的话题，B 群里提起她知道在说什么；在某个群里认识的人，换个群她还记得。这让她在多群环境中表现得像一个真正"在场"的人，而不是同时存在于 N 个群里的 N 个陌生人。当然，私聊也可以。

## 前置要求

- Python 3.10+
- 至少一个 OpenAI 兼容 LLM API
- [FFmpeg](https://ffmpeg.org/download.html)（音频处理，需加入 PATH 或放入 `vendor/` 目录）

## 安装

```bash
git clone https://github.com/your-repo/qianxue.git
cd qianxue
pip install -r requirements.txt
```

## 外部依赖

千雪的部分功能依赖外部服务，按需安装即可。

### NapCat — QQ 消息通道（可选）

如果你需要千雪接入 QQ 群聊：

1. 安装 NTQQ：https://im.qq.com/pcqq
2. 安装 NapCat：https://napneko.github.io/guide/napcat
3. 配置反向 WebSocket 地址：`ws://localhost:8000/ws/onebot`
4. 配置 HTTP 服务地址：`http://localhost:3000`

不配置 NapCat 则 QQ 通道不可用，但仍可使用 Discord 和电脑前端。

### Discord Bot — Discord 消息通道（可选）

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications) 创建应用
2. 创建 Bot，获取 Token
3. 开启 MESSAGE CONTENT INTENT 和 PRESENCE INTENT
4. 通过 Web 管理界面 (`http://localhost:5002`) → 配置 → Discord，填入 Token

不配置 Discord Token 则 Discord 通道不可用，但仍可使用 QQ 和电脑前端。

### FunASR — 语音识别（语音功能需要）

语音转文字依赖 [FunASR](https://github.com/modelscope/FunASR)，推荐 Docker 部署：

```bash
docker run -p 10095:10095 -p 10096:10096 registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.12
```

启动后 WebSocket 地址为 `ws://localhost:10095`。不部署则无法识别语音消息。

### Qwen3-TTS — 高质量语音合成（可选，默认使用 Edge TTS）

默认使用 Edge TTS（免费、无需部署）。如需更高音质，可部署 Qwen3-TTS 本地服务：

1. 克隆并启动 [Qwen3-TTS-Openai-Fastapi](https://github.com/cofecms/Qwen3-TTS-Openai-Fastapi)
2. 默认监听 `http://localhost:8880`
3. 在 `backend/config/voice.yaml` 中设置 `tts.backend: "qwen3"`

不部署则使用 Edge TTS，功能完全可用，音质略低。

## 配置

**不需要手动编辑任何配置文件。** 所有配置都可以在启动后通过前端完成。

1. 安装依赖 → 启动服务 → 打开 `http://localhost:5002`
2. 点击"配置"，选择提供商预设，填入 API Key，保存
3. 其余参数（大脑、睡眠、记忆、视觉等）按分组配置，改了立即生效

## 启动

### 一键启动（推荐）

```bash
# Windows 双击 start_all.bat 或：
python start_all.py

# 指定 Python 解释器：
set QIANXUE_PYTHON=D:\Miniconda\envs\myenv\python.exe
python start_all.py
```

### 手动启动

```bash
python -m Memory.server                          # 终端 1: Memory 服务
python -m uvicorn backend.main:app --port 8000    # 终端 2: Backend 主系统
python -m heartbeat                               # 终端 3: 心跳服务
```

## Web 管理界面

启动后访问 `http://localhost:5002`：

- **仪表盘** — AI 状态（心情、精力、注意力、信心）、系统健康、统计
- **日志** — 实时日志流，支持按级别过滤
- **群聊** — 群列表、启用/禁用、自动回复、回复延迟
- **配置** — 思考模型/记忆系统模型配置（提供商预设）、心跳服务开关、上下文窗口、在线修改所有参数
- **核心** — 查看/编辑 AI 核心人设

记忆查询前端 `http://localhost:5001`：体验浏览、实体检索、关系图、人物档案

## 支持的 LLM

支持任何 OpenAI 兼容接口，前端提供预设快速配置：

| 提供商 | Base URL | 推荐模型 |
|--------|----------|----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic | `https://api.anthropic.com` | `claude-sonnet-4-20250514` |
| 智谱 ChatGLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| MiniMax | `https://api.minimax.chat/v1` | `MiniMax-Text-01` |
| 火山引擎 豆包 | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-pro-32k` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |

思考模型和记忆系统可以使用不同的 Provider。

---

# 开发者指南

## 系统架构

```
QQ 用户 ─→ NapCat (OneBot v11) ──WebSocket──→ Backend (FastAPI :8000)
Discord 用户 ─→ Discord Bot ───────────────→        │
                                                      │
                                              AgentBrain 多轮思考
                                              ├─ 流式路径: 句子级实时输出 + 工具调用
                                              └─ Think Loop: JSON 格式多轮推理 (fallback)
                                                      │
                                              工具系统 (可扩展)
                                              ├─ send_message      发送消息
                                              ├─ search_memory     搜索记忆
                                              ├─ get_context       获取上下文
                                              ├─ recognize_image   图片识别
                                              ├─ send_voice        语音回复
                                              ├─ connect/discord   连接 Discord
                                              ├─ connect/voice     连接语音频道
                                              └─ get_current_time  获取时间
                                                      │
                                              MessageManager (统一消息路由)
                                              ├─ QQ 群聊 / 私聊
                                              ├─ Discord 文字频道 / 私聊
                                              └─ Discord 语音频道 (TTS 流式播放)
                                                      │
                                              Memory 服务 (独立进程 :8001)
                                              ├─ 写入管道: 体验提取 → 实体识别
                                              ├─ 巩固管道: L0 → L1 → L2 + 梦境
                                              └─ 召回管道: 向量检索 + 图谱遍历
                                                      │
                                              Heartbeat 服务
                                              └─ 定时触发 AI 主动思考
```

### 消息处理流程

```
QQ 消息 → NapCat → WebSocket → Backend
Discord 消息 → Discord Bot → Backend
  → QQSource / DiscordSource 解析 → AgentMessage
    ├─ @ 消息识别: <@id> → @名字, 标记 is_mentioned
    └─ 语音附件: 下载 → FunASR/Whisper 转写
  → Context Manager 存储上下文
  → STM 事件记录
  → Debounce 分流:
      @ 消息 → 跳过等待立即处理
      普通消息 → 聚合等待（等对方说完）
  → AgentBrain 流式回复:
      SentenceDetector 句子级拆分
      → MessageManager 实时发送每个句子
      → 工具调用 (search_memory / send_voice 等)
      → AI 可选择沉默（不输出内容）
```

### 记忆系统管道

```
写入: 消息 → 体验提取(LLM) → 实体识别(LLM) → SQLite + ChromaDB
巩固: L0 短期体验 → L1 摘要(定时压缩) → L2 核心记忆(长期) + 梦境处理
召回: 双轨召回(向量相似度 + 实体图谱遍历) → 简报生成
```

## 项目结构

```
qianxue/
├── backend/                    # 主系统
│   ├── main.py                 # FastAPI 入口，WebSocket 端点，消息分发
│   ├── config/                 # YAML 配置文件 + loader
│   │   ├── loader.py           # 统一配置加载器（环境变量 > 数据库 > YAML）
│   │   └── *.yaml.example      # 配置模板
│   ├── api/
│   │   ├── llm.py              # LLM Manager（多 Provider，自动识别）
│   │   └── napcat.py           # NapCat OneBot HTTP 客户端
│   ├── services/
│   │   ├── agent/
│   │   │   ├── brain.py        # AgentBrain 思考引擎（流式 + Think Loop 双路径）
│   │   │   ├── message.py      # AgentMessage 统一消息模型
│   │   │   ├── thought.py      # AgentThought 思考过程模型
│   │   │   ├── tools/          # 工具注册表（含 Discord/语音工具）
│   │   │   ├── streaming/      # 流式回复系统
│   │   │   │   ├── streaming_prompt.py  # 流式 system prompt 构建器
│   │   │   │   ├── sentence_detector.py # 句子边界检测器
│   │   │   │   └── message_manager.py   # 统一消息路由（QQ/Discord/TTS）
│   │   │   └── sources/        # 消息源
│   │   │       ├── qq_source.py       # QQ (NapCat) 消息源
│   │   │       └── discord_source.py  # Discord 消息源 + 语音附件处理
│   │   ├── context_manager.py  # 对话上下文管理
│   │   ├── voice_service.py    # 语音合成服务 (Edge TTS)
│   │   ├── voice_player.py     # 语音播放器 (Discord 语音频道流式播放)
│   │   ├── sleep_manager.py    # 睡眠节律管理
│   │   ├── vision_service.py   # 图片识别服务
│   │   ├── memory_interface.py # 记忆系统接口
│   │   └── stm_client.py       # 短期记忆客户端
│   ├── routes/
│   │   ├── config_routes.py    # 配置、模型、视觉 API
│   │   └── chat_routes.py      # 群聊、上下文、统计 API
│   ├── database/               # SQLite 数据层
│   ├── web/app.py              # Web 管理界面 (Flask, :5002)
│   └── db_config.py            # 运行时配置管理器（DB 覆盖 YAML）
│
├── Memory/                     # 独立记忆系统服务
│   ├── server/app.py           # FastAPI HTTP 服务 (:8001)
│   ├── api/memory_api.py       # 记忆 API 接口
│   ├── storage/                # 存储层（SQLite + ChromaDB）
│   ├── recall/                 # 召回系统（向量检索 + 图谱遍历）
│   ├── consolidator/           # 巩固和梦境处理
│   ├── writer/                 # 写入管道（体验提取 + 实体识别）
│   ├── stm/                    # 短期记忆
│   ├── embedding/              # 向量化服务（bge-base-zh）
│   ├── state/                  # AI 状态管理（心情、精力、信心）
│   ├── llm/                    # LLM 客户端（千问 / DeepSeek / 通用 OpenAI 兼容）
│   ├── config/settings.py      # 集中配置（dataclass + .env）
│   └── web/app.py              # 记忆查询前端 (Flask, :5001)
│
├── heartbeat/                  # 心跳服务（触发主动思考）
│   ├── loop.py                 # 心跳主循环
│   └── config.py               # 心跳配置加载
├── tools/                      # 独立工具
│   └── screen_capture_agent.py # 屏幕感知客户端
├── start_all.py / .bat         # 一键启动
└── heartbeat_config.yaml       # 心跳配置（enabled / interval / backend_url）
```

## Backend API 索引

### 基础

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/logs/stream` | SSE 实时日志流 |
| POST | `/api/heartbeat` | 心跳触发主动思考 |

### 核心层

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/identity` | 获取核心层身份（稳定层 + 可塑层） |
| GET | `/api/core/identity` | 获取核心层（Memory 格式） |
| POST | `/api/malleable` | 更新可塑层 YAML |

### 群聊 & 统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/groups` | 获取所有群聊配置 |
| POST | `/api/groups/{id}/toggle` | 启用/禁用群聊 |
| POST | `/api/groups/{id}/auto-reply` | 开关自动回复 |
| POST | `/api/groups/{id}/delay` | 设置回复延迟(1-60s) |
| GET | `/api/groups/{id}/context` | 获取群对话上下文 |
| DELETE | `/api/groups/{id}/context` | 清除群对话上下文 |
| GET | `/api/stats` | 统计信息（用户数、群数、消息数） |

### 模型 & 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/model-config` | 获取当前模型配置 |
| PUT | `/api/thinking-provider` | 更新思考模型（持久化到 llm.yaml） |
| POST | `/api/thinking-provider/test` | 测试思考模型连接 |
| GET | `/api/configs` | 获取所有配置 |
| GET | `/api/settings` | 获取所有 settings 分组 |
| PUT | `/api/settings/{section}` | 更新指定 settings 分组 |
| POST | `/api/context-window` | 更新上下文窗口大小(1-100) |

### API 提供者管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/apis` | 添加 API 配置 |
| PUT | `/api/apis/{name}` | 更新 API 配置 |
| DELETE | `/api/apis/{name}` | 删除 API 配置 |
| POST | `/api/apis/{name}/test` | 测试 API 连接 |
| POST | `/api/apis/switch/{name}` | 切换当前 API |

### 视觉服务

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/vision-config` | 获取视觉服务配置 |
| POST | `/api/vision-config` | 更新视觉服务配置 |
| POST | `/api/vision-config/test` | 测试视觉 API 连接 |

## Memory API 索引

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/status` | 记忆系统状态（体验数、实体数、健康度） |
| POST | `/api/event` | 记录体验事件（对话/内容/结构化） |
| POST | `/api/recall` | 召回相关记忆（向量 + 图谱） |
| POST | `/api/recall/keywords` | 按关键词召回记忆 |
| GET | `/api/profile/{name}` | 获取实体档案 |
| POST | `/api/profile/ensure` | 确保档案存在（不存在则创建） |
| GET | `/api/core` | 获取核心层身份 |
| GET | `/api/state` | 获取当前 AI 状态（心情、精力） |
| POST | `/api/consolidate` | 手动触发巩固 |
| GET | `/api/consolidate/status` | 巩固调度器状态 |
| POST | `/api/stm/event` | 记录短期记忆事件 |
| GET | `/api/stm/perception` | 获取短期记忆感知文本 |
| POST | `/api/stm/compress` | 手动触发 STM 压缩 |
| GET | `/api/config/llm` | 获取记忆系统 LLM 配置 |
| POST | `/api/config/llm` | 更新记忆系统 LLM 配置（持久化到 .env） |

## 代码索引

关键类和函数的快速定位：

| 位置 | 符号 | 说明 |
|------|------|------|
| `backend/services/agent/brain.py` | `AgentBrain` | 思考引擎（流式 + Think Loop 双路径） |
| `backend/services/agent/brain.py` | `_stream_reply()` | 流式回复 — 句子级实时输出 + 工具调用循环 |
| `backend/services/agent/brain.py` | `proactive_think()` | 心跳触发的主动思考入口 |
| `backend/services/agent/streaming/sentence_detector.py` | `SentenceDetector` | 流式句子边界检测（。！？\n.!?） |
| `backend/services/agent/streaming/message_manager.py` | `MessageManager` | 统一消息路由（QQ/Discord/TTS） |
| `backend/services/agent/streaming/streaming_prompt.py` | `build_streaming_prompt()` | 流式路径 system prompt 构建器 |
| `backend/services/agent/sources/discord_source.py` | `DiscordSource` | Discord 消息源 + @ 转换 + 语音附件处理 |
| `backend/services/voice_player.py` | `VoicePlayer` | Discord 语音频道流式播放器 |
| `backend/services/voice_service.py` | `VoiceService` | 语音合成 + 语音转写服务 |
| `backend/services/agent/message.py` | `AgentMessage` | 统一消息模型（含 is_private/is_mentioned） |
| `backend/api/llm.py` | `LLMManager` | LLM 提供者管理 + 流式 stream_chat |
| `backend/api/napcat.py` | `extract_plain_text()` | QQ 消息文本提取（保留 @ 名字） |
| `backend/main.py` | `_enqueue_message()` | 消息入队分流（@ 立即处理 / 普通 debounce） |
| `backend/services/context_manager.py` | `ContextManager` | 对话上下文存储与检索 |
| `backend/services/sleep_manager.py` | `SleepManager` | 睡眠节律 + 精力管理 |
| `Memory/api/memory_api.py` | `MemoryAPI` | 记忆系统统一 API 入口 |
| `Memory/recall/briefing.py` | `RecallManager` | 双轨召回（向量 + 图谱） |
| `Memory/consolidator/pipeline.py` | `ConsolidationPipeline` | 巩固管道（L0→L1→L2） |
| `Memory/writer/pipeline.py` | `WriterPipeline` | 写入管道（体验提取 + 实体识别） |
| `Memory/llm/factory.py` | `LLMFactory` | 记忆系统 LLM 客户端工厂 |
| `Memory/llm/openai_compatible_client.py` | `OpenAICompatibleClient` | 通用 OpenAI 兼容客户端 |
| `Memory/config/settings.py` | `settings` | 记忆系统集中配置 |
| `heartbeat/loop.py` | `HeartbeatLoop` | 心跳主循环 |
| `heartbeat/config.py` | `HeartbeatConfig` | 心跳配置（enabled/interval/backend_url） |

## 技术栈

| 组件 | 技术 |
|------|------|
| Backend | FastAPI + Uvicorn + WebSocket (async) |
| Memory | FastAPI + SQLite + ChromaDB (向量存储) |
| Embedding | BAAI/bge-base-zh (sentence-transformers) |
| LLM | OpenAI 兼容 API (多 Provider，前端预设配置) |
| QQ 协议 | OneBot v11 (NapCat) |
| Discord | discord.py (Bot + 语音频道) |
| 语音合成 | Edge TTS (流式合成) |
| 语音转写 | FunASR (Docker) / Whisper API |
| Web UI | Flask + 原生 HTML/CSS/JS |
| 数据库 | SQLite (aiosqlite) |

## 配置系统

三级优先级：**环境变量 > 数据库覆盖 > YAML 默认值**。

```bash
# 环境变量命名：QIANXUE_{SECTION}__{KEY}
export QIANXUE_BRAIN__MAX_ITERATIONS=10
export QIANXUE_NAPCAT__HTTP_URL=http://192.168.1.100:3000
```

通过 Web 管理界面修改的配置保存到数据库并热更新，不需重启（Server 分组除外）。

| 变量 | 用途 | 示例 |
|------|------|------|
| `QIANXUE_PYTHON` | 指定 Python 解释器 | `D:\Miniconda\envs\myenv\python.exe` |
| `QIANXUE_{SECTION}__{KEY}` | 覆盖任意配置项 | `QIANXUE_BRAIN__MAX_ITERATIONS=10` |
| `PYTHONIOENCODING` | Python 输出编码 | `utf-8` |
| `PYTHONUTF8` | UTF-8 模式 | `1` |
| `HF_ENDPOINT` | HuggingFace 镜像 | `https://hf-mirror.com` |

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
                "properties": {
                    "input": {"type": "string", "description": "输入"}
                },
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
cd backend && pytest tests/ -v
```

## 目录约定

```
data/               # Backend SQLite 数据库（自动创建）
Memory/data/        # Memory SQLite + ChromaDB 数据（自动创建）
backend/config/     # 配置文件（*.yaml 已被 .gitignore 排除）
logs/               # 日志目录（可选）
```

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎 Issue 和 Pull Request。

- 开发前先读开发者指南的[系统架构](#系统架构)和[项目结构](#项目结构)
- 提交前确保现有测试通过：`cd Memory && pytest tests/ -v`
- PR 描述请说明改动目的和影响范围
