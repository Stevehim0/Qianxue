# AI-QQchat - 智能 QQ 群聊 Agent 系统

基于 AgentBrain 多轮思考架构的 QQ 群聊 AI 机器人后端。支持多轮递归推理、工具并行调用、图片识别和记忆系统接口。

> 前端已移除，后续重写。当前为纯后端 API 服务。

---

## 目录

- [系统架构](#系统架构)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [AgentBrain 思考引擎](#agentbrain-思考引擎)
- [工具系统](#工具系统)
- [记忆系统接口](#记忆系统接口)
- [API 接口文档](#api-接口文档)
- [数据库设计](#数据库设计)
- [配置说明](#配置说明)
- [开发指南](#开发指南)
- [常见问题](#常见问题)

---

## 系统架构

```
QQ 消息 → NapCat (OneBot v11) → WebSocket → QQSource → AgentMessage
                                                          ↓
                                              根据优先级路由:
                                              ├─ @消息 (priority >= 10): 立即处理
                                              └─ 普通消息: 10秒队列批量处理
                                                          ↓
                                              记忆提取 (通过 memory_interface, 异步不阻塞)
                                                          ↓
                                              AgentBrain 多轮思考引擎
                                              ┌──────────────────────────┐
                                              │ 第1轮: LLM 分析+规划工具  │
                                              │    ↓ 并行执行工具          │
                                              │ 第2轮: 基于结果继续思考    │
                                              │    ↓ 并行执行工具          │
                                              │ 第N轮: 最终决策 (最多3轮)  │
                                              └──────────────────────────┘
                                                          ↓
                                              send_message 工具发送回复
                                                          ↓
                                              上下文更新 → 数据库存储
```

### 双架构支持

通过环境变量 `USE_NEW_ARCHITECTURE` 切换：

| 特性 | 新架构 (AgentBrain) | 旧架构 |
|------|---------------------|--------|
| 思考模式 | 多轮递归思考 (最多3轮) | 双层模型 (思考+说话) |
| 工具调用 | 并行执行 + 变量替换 | 无 |
| 代码入口 | `backend/services/agent/` | `backend/services/message_handler.py` |

---

## 项目结构

```
AI-QQchat-backup/
├── backend/
│   ├── main.py                          # 应用入口, WebSocket 端点, 消息路由
│   ├── config.py                        # 配置管理器
│   ├── api/
│   │   ├── llm.py                       # LLM API 统一接口 (OpenAI/Anthropic/DeepSeek/Qwen)
│   │   └── napcat.py                    # NapCat OneBot 客户端
│   ├── database/
│   │   ├── db.py                        # SQLite 异步数据库连接 + 建表
│   │   └── models.py                    # Pydantic 数据模型
│   ├── routes/
│   │   ├── config_routes.py             # 配置管理 API
│   │   └── chat_routes.py              # 聊天管理 API
│   └── services/
│       ├── agent/                       # AgentBrain 新架构
│       │   ├── brain.py                 # 多轮思考引擎
│       │   ├── message.py               # 统一消息格式 (AgentMessage)
│       │   ├── thought.py               # 思考结果 (AgentThought)
│       │   ├── tool_call.py             # 工具调用记录 (ToolCall)
│       │   ├── sources/
│       │   │   └── qq_source.py         # QQ 消息源
│       │   └── tools/
│       │       ├── base.py              # 工具基类 (Tool ABC)
│       │       ├── registry.py          # 工具注册表 (ToolRegistry)
│       │       ├── send_message.py      # 发送消息
│       │       ├── get_time.py          # 获取时间
│       │       ├── search_memory.py     # 搜索记忆 (走 memory_interface)
│       │       ├── get_context.py       # 获取对话上下文
│       │       └── recognize_image.py   # 图片识别
│       ├── memory_interface.py          # 记忆系统抽象接口 ★
│       ├── message_handler.py           # 旧架构消息处理器
│       ├── rethink_model.py             # 旧架构思考模型
│       ├── context_manager.py           # 双层上下文管理
│       ├── reply_scheduler.py           # 回复调度器
│       └── vision_service.py            # 图片识别服务
├── data/                                # SQLite 数据库 (运行时生成)
├── memory/                              # 开发笔记 (非代码)
├── requirements.txt                     # Python 依赖
├── MIGRATION_GUIDE.md                   # 迁移指南
└── README.md                            # 本文档
```

---

## 快速开始

### 前置要求

- Python 3.10+
- Windows 版 QQ (NTQQ)
- NapCat

### 1. 安装 NapCat

1. 安装 NTQQ: https://im.qq.com/pcqq
2. 安装 NapCat: https://napneko.github.io/guide/napcat
3. 配置反向 WebSocket 地址: `ws://localhost:8000/ws/onebot`
4. 配置 HTTP 服务地址: `http://localhost:3000`

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

```bash
# 先启动 NapCat

# 启动后端 (推荐新架构)
# Windows PowerShell
$env:USE_NEW_ARCHITECTURE="true"; uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Windows CMD
set USE_NEW_ARCHITECTURE=true && uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Linux/Mac
USE_NEW_ARCHITECTURE=true uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 配置 API

通过 API 配置 LLM（前端重写前可用 curl）：

```bash
# 添加 API
curl -X POST http://localhost:8000/api/apis \
  -H "Content-Type: application/json" \
  -d '{"name": "deepseek", "api_key": "your-key", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}'

# 切换为当前 API
curl -X POST http://localhost:8000/api/apis/switch/deepseek

# 测试连接
curl -X POST http://localhost:8000/api/apis/deepseek/test
```

---

## AgentBrain 思考引擎

### 工作流程

```
第1轮: LLM 分析消息 → 规划需要调用的工具
    ↓
并行执行工具 (asyncio.gather)
    ↓
第2轮: 基于工具结果 → 继续分析或完成决策
    ↓
第N轮 (最多3轮): 最终决策
    ↓
send_message 工具发送回复
```

### 关键特性

- **自主决策**: LLM 通过 `done` 字段自行决定是否继续思考
- **并行执行**: 同一轮工具无依赖时并行执行 (`asyncio.gather`)
- **变量替换**: 工具结果通过 `{变量名}` 在下一轮引用

---

## 工具系统

### 已注册工具

| 工具名 | 文件 | 功能 |
|--------|------|------|
| `send_message` | `tools/send_message.py` | 发送回复到群聊 |
| `get_current_time` | `tools/get_time.py` | 获取当前时间 |
| `search_memory` | `tools/search_memory.py` | 搜索记忆 (通过 memory_interface) |
| `get_conversation_context` | `tools/get_context.py` | 获取群聊对话历史 |
| `recognize_image` | `tools/recognize_image.py` | 识别图片内容 |

### 添加新工具

1. 在 `backend/services/agent/tools/` 创建新文件，继承 `Tool` 基类：

```python
from .base import Tool, ToolArgument
from typing import Any, List

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "工具描述 (LLM 可见)"

    @property
    def arguments(self) -> List[ToolArgument]:
        return [
            ToolArgument(name="query", type="string", description="查询内容", required=True)
        ]

    async def execute(self, **kwargs) -> Any:
        return {"result": "..."}
```

2. 在 `backend/main.py` 中导入并注册：

```python
from backend.services.agent.tools.my_tool import MyTool
tool_registry.register(MyTool())
```

3. 重启后端，LLM 自动识别新工具

---

## 记忆系统接口

记忆系统通过 `backend/services/memory_interface.py` 抽象，当前为**空实现**。

### 接口定义

```python
class MemoryProvider:
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]
    async def retrieve_relevant(self, query: str, user_id: str, group_id: str, limit: int) -> List[RetrievedMemory]
    async def extract_and_store(self, group_id: str, user_id: str, content: str) -> None
    async def update_access_stats(self, memory_id: int) -> None
```

### 接入新记忆系统

1. 继承 `MemoryProvider` 并实现方法
2. 替换全局实例：

```python
# backend/services/memory_interface.py 末尾
from backend.services.my_new_memory import MyNewMemoryProvider
memory_provider = MyNewMemoryProvider()
```

3. 无需改动其他文件

### 调用点

| 调用位置 | 调用的方法 |
|----------|-----------|
| `context_manager.py` `get_global_context()` | `get_user_profile()`, `retrieve_relevant()`, `update_access_stats()` |
| `message_handler.py` `auto_extract_memory()` | `extract_and_store()` |
| `tools/search_memory.py` `execute()` | `retrieve_relevant()` |

### 数据模型

相关模型定义在 `backend/database/models.py`，新记忆系统的返回值需要匹配：

- `UserProfile` — 用户档案
- `UserMemory` — 单条记忆
- `RetrievedMemory` — 检索结果（包装 UserMemory + 相似度分数）

---

## API 接口文档

### WebSocket

| 端点 | 说明 |
|------|------|
| `WS /ws/onebot` | NapCat 反向 WebSocket 连接 |

### SSE

| 端点 | 说明 |
|------|------|
| `GET /logs/stream` | 实时日志流 |

### 配置管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/configs` | 获取所有配置 |
| POST | `/api/apis` | 添加 API 配置 |
| PUT | `/api/apis/{name}` | 更新 API 配置 |
| DELETE | `/api/apis/{name}` | 删除 API 配置 |
| POST | `/api/apis/{name}/test` | 测试 API 连接 |
| POST | `/api/apis/switch/{name}` | 切换当前 API |
| POST | `/api/system-prompt` | 更新系统提示词 |
| POST | `/api/context-window` | 更新上下文窗口大小 |
| GET | `/api/vision-config` | 获取 Vision 配置 |
| POST | `/api/vision-config` | 更新 Vision 配置 |

### 聊天管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/groups` | 获取所有群聊 |
| POST | `/api/groups/{group_id}/toggle` | 切换群聊启用状态 |
| POST | `/api/groups/{group_id}/auto-reply` | 切换自动回复 |
| POST | `/api/groups/{group_id}/delay` | 设置回复延迟 |
| GET | `/api/groups/{group_id}/context` | 获取群聊上下文 |
| DELETE | `/api/groups/{group_id}/context` | 清除群聊上下文 |
| GET | `/api/stats` | 获取统计信息 |

### 其他

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/` | API 状态 |
| GET | `/health` | 健康检查 |

---

## 数据库设计

数据库文件 `data/chat.db`，SQLite + aiosqlite。启动时自动创建。

```sql
-- 用户表
users (user_id TEXT PK, nickname TEXT, user_type TEXT, first_seen, last_seen, message_count)

-- 群聊表
groups (group_id TEXT PK, group_name TEXT, enabled INT, auto_reply_enabled INT, reply_delay_seconds INT)

-- 对话上下文表
conversations (id INTEGER PK, group_id, user_id, role, content, timestamp,
               sender_nickname, mentions TEXT, is_directed_at_bot INT)

-- 系统配置表
configs (key TEXT PK, value TEXT, updated_at)
```

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `USE_NEW_ARCHITECTURE` | `false` | 使用 AgentBrain 新架构 |
| `NAPCAT_HTTP_URL` | `http://localhost:3000` | NapCat HTTP 地址 |

### 支持的 LLM

| 提供商 | Base URL |
|--------|----------|
| OpenAI | `https://api.openai.com/v1` |
| Anthropic | `https://api.anthropic.com` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

---

## 开发指南

### 添加 API 端点

```python
# backend/routes/new_routes.py
from fastapi import APIRouter
router = APIRouter(prefix="/api")

@router.get("/new-endpoint")
async def new_endpoint():
    return {"data": "result"}
```

```python
# backend/main.py 中注册
from backend.routes.new_routes import router as new_router
app.include_router(new_router)
```

### 修改数据库

在 `backend/database/db.py` 的 `initialize_tables()` 中添加新表。

---

## 常见问题

**NapCat 无法连接** — 检查后端是否启动 (端口 8000)，反向 WS 地址是否正确

**机器人不回复** — 检查群聊是否启用、API 是否配置正确、查看日志流 `/logs/stream`

**端口占用** — `netstat -ano | findstr :8000` 查看占用，或换端口启动

## 许可证

MIT License
