# Qianxue - AI QQ 聊天机器人

一个有持续记忆和人格的 AI QQ 聊天机器人。基于 AgentBrain 多轮思考架构，支持递归推理、工具并行调用、分层记忆系统和图片识别。

## 功能特性

- **AgentBrain 多轮思考** — LLM 自主决策思考轮次，支持工具并行调用
- **分层记忆系统** — L0 短期记忆 → L1 摘要 → L2 核心记忆，带衰减和巩固机制
- **人设管理** — AI 具有可演化的人格画像，随交互持续更新
- **梦境处理** — 定期对记忆进行抽象和整理
- **双模型架构** — 思考模型和说话模型独立配置，支持任意 OpenAI 兼容 API
- **短期记忆感知** — 跨会话全局感知，AI 能感知到在其他群聊中发生的事件
- **图片识别** — 支持群聊中的图片内容理解

## 系统架构

```
QQ 用户 → NapCat (OneBot v11) → WebSocket → Backend
                                               ↓
                                    AgentBrain 多轮思考引擎
                                    ├─ 思考模型: 推理 + 工具规划
                                    └─ 说话模型: 润色最终回复
                                               ↓
                                    工具系统 (可扩展)
                                    ├─ send_message
                                    ├─ search_memory
                                    ├─ get_conversation_context
                                    ├─ recognize_image
                                    └─ get_current_time
                                               ↓
                                    Memory 服务 (分层记忆存储)
```

## 项目结构

```
qianxue/
├── backend/              # 主系统：消息收发、Agent 思考引擎、工具调用
│   ├── main.py           # 应用入口，WebSocket 端点
│   ├── services/agent/   # AgentBrain 核心架构
│   │   ├── brain.py      # 多轮思考引擎
│   │   └── tools/        # 工具系统（可扩展）
│   └── ...
├── Memory/               # 记忆系统：分层存储、写入/巩固/召回、人设管理
│   ├── core/             # 核心数据模型和解析器
│   ├── storage/          # SQLite + ChromaDB 存储层
│   ├── recall/           # 双轨召回 + 记忆简报
│   ├── consolidator/     # 记忆巩固和梦境处理
│   └── ...
├── heartbeat/            # 心跳服务：定时触发 AI 主动思考
└── docs/                 # 文档
```

## 快速开始

### 前置要求

- Python 3.10+
- Windows 版 QQ (NTQQ)
- [NapCat](https://napneko.github.io/guide/napcat)

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
# Backend LLM 配置
cp backend/llm_config.yaml.example backend/llm_config.yaml
# 编辑 llm_config.yaml，填入你的 API Key

# Memory 系统配置
cp Memory/.env.example Memory/.env
# 编辑 .env，填入你的 LLM API Key
```

### 3. 配置 NapCat

1. 安装 NTQQ: https://im.qq.com/pcqq
2. 安装 NapCat: https://napneko.github.io/guide/napcat
3. 配置反向 WebSocket 地址: `ws://localhost:8000/ws/onebot`
4. 配置 HTTP 服务地址: `http://localhost:3000`

### 4. 启动服务

```bash
# 启动 Memory 服务
python -m Memory.server

# 启动 Backend（新架构）
set USE_NEW_ARCHITECTURE=true && uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 支持的 LLM

支持任何 OpenAI 兼容接口：

| 提供商 | Base URL |
|--------|----------|
| DeepSeek | `https://api.deepseek.com` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| OpenAI | `https://api.openai.com/v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |

## 技术栈

- **Backend**: FastAPI + Uvicorn + WebSocket
- **Memory**: SQLite + ChromaDB (向量存储)
- **AI**: OpenAI 兼容 API (DeepSeek/Qwen/OpenAI)
- **协议**: OneBot v11 (通过 NapCat)
- **Embedding**: BAAI/bge-base-zh

## 许可证

[MIT License](LICENSE)
