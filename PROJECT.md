# Qianxue - AI QQ 聊天机器人

> 面向开发者/AI 助手的快速上手文档。帮助新对话的 AI 快速理解项目架构和当前状态。

## 快速索引（各模块详细文档）

如需深入了解某个模块，直接阅读对应的 INDEX.md：

| 模块 | 索引文件 | 一句话描述 |
|------|----------|-----------|
| **Backend** | [backend/INDEX.md](backend/INDEX.md) | 主系统：消息收发、Agent 思考引擎、工具调用、QQ 协议对接 |
| **Memory** | [Memory/INDEX.md](Memory/INDEX.md) | 记忆系统：分层存储、写入/巩固/召回、人设管理、梦境、短期记忆 |
| **Heartbeat** | [heartbeat/INDEX.md](heartbeat/INDEX.md) | 心跳服务：定时触发 AI 主动思考 |

## 项目概述

一个有持续记忆和人格的 AI QQ 聊天机器人。由两个独立服务组成：

- **Backend** (`backend/`) — 主系统：消息收发、Agent 思考引擎、工具调用、QQ 协议对接
- **Memory** (`Memory/`) — 记忆系统：分层记忆存储、写入/巩固/召回、人设管理、梦境处理、短期记忆（跨会话感知）

两个服务通过 HTTP API 通信（Backend 调用 Memory 的 `/api/event`、`/api/stm/event` 等端点）。

## 核心架构

### 消息流

```
QQ 用户 → NapCat (OneBot v11) → WebSocket → Backend main.py
                                                       ↓
                                              QQSource 消息转换
                                                       ↓
                                          AgentMessage (统一格式)
                                                       ↓
                                         按优先级路由 (群聊/私聊)
                                                       ↓
                                    ┌── 睡眠检查 (00:00-08:00 群聊存DB，私聊入队)
                                    │                  ↓ (清醒时)
                                        AgentBrain 多轮思考引擎
                                        ┌───────────────────────┐
                                        │ 思考模型 (thinking)    │
                                        │  ↓ 中间回复 (可选)     │
                                        │  ↓ 规划工具调用        │
                                        │  ↓ 并行执行工具        │
                                        │  ↓ 说话模型润色        │
                                        │  ↓ 最终决策            │
                                        └───────────────────────┘
                                                       ↓
                                         send_message 工具 → NapCat → QQ
                                                       ↓
                                         Memory 提取记忆 (异步不阻塞)
                                         STM 记录事件 (异步不阻塞)
```

### 短期记忆（跨会话全局感知）

AI 在所有会话（群聊/私聊）中的行为和关键用户消息会被记录到 Memory 服务的短期记忆（STM）模块。构建 LLM 上下文时，STM 生成格式化的感知区块注入到 system prompt 中，使 AI 具备跨会话的全局感知能力。

```
事件记录流:
  用户消息/工具执行 → POST /api/stm/event → stm_events 表
                                                    ↓ (超过40条自动压缩)
                                                stm_compressed 表
                                                    ↓
感知注入流:
  构建上下文时 → GET /api/stm/perception → 格式化感知文本 → system prompt 独立区块
```

事件类型：`ai_reply`（AI回复）、`tool_call`（工具调用）、`user_mention`（@机器人）、`significant_msg`（有意义消息）
感知注入时机：处理用户消息时、心跳思考时、工具调用前
压缩机制：事件累积超过阈值时，LLM 自动将旧事件压缩为简洁摘要

### 双模型架构

Backend 使用两个独立可配置的 LLM 模型：

- **思考模型** (`thinking_provider`): 用于 AgentBrain 推理、工具决策。调用 `llm_manager.thinking_chat()`
- **说话模型** (`speaking_provider`): 用于润色最终回复。调用 `llm_manager.speaking_chat()`

配置在 `backend/llm_config.yaml`，支持任何 OpenAI 兼容接口。

### 私聊支持

私聊消息使用 `private_{user_id}` 作为 pseudo group_id，复用所有以 group_id 为 key 的逻辑（上下文管理、数据库、记忆系统）。AI 通过 system prompt 知道当前是私聊环境。

### 睡眠-觉醒周期

AI 模拟人类的睡眠节律，不在系统提示词中写"你该睡觉"的规则，而是通过**状态层**的精力变化让 AI 自然感受到困倦和清醒。

详细设计见 [docs/sleep-cycle-design.md](docs/sleep-cycle-design.md)

| 时间段 | 状态 | AI 行为 | 系统行为 |
|--------|------|---------|---------|
| 08:00-22:59 | AWAKE | 正常对话、主动思考 | 全部正常运行 |
| 23:00-23:59 | WINDING_DOWN | 仍响应消息，不再主动发言 | 停止心跳，精力→"困倦" |
| 00:00-07:59 | ASLEEP | 不存在 | 群聊存DB不处理，私聊入队列 |
| ~08:00 | 唤醒 | 处理积压私聊 | STM 注入梦境感知，恢复精力 |

### 中间回复（interim_message）

AI 在思考过程中可以发送简短的中间消息（如"等我想想哦"），让用户知道 AI 在处理。LLM 在决定调用工具（done=false）时，可附带 `interim_message` 字段，系统在工具执行前立即发送。不经过说话模型润色，不存入上下文。

## 关键文件速查

### Backend

| 文件 | 职责 |
|------|------|
| `backend/main.py` | 应用入口、WebSocket 路由、消息分发、心跳触发、STM 事件记录 |
| `backend/llm_config.yaml` | 双模型配置（thinking_provider + speaking_provider） |
| `backend/api/llm.py` | LLMManager（双模型管理）、各种 Provider 实现 |
| `backend/api/napcat.py` | NapCat 客户端（群发/私发消息、消息解析） |
| `backend/services/agent/brain.py` | AgentBrain 思考引擎（多轮思考循环、工具调用、JSON 解析、STM 感知注入） |
| `backend/services/agent/message.py` | AgentMessage 统一消息格式（含 is_private 字段） |
| `backend/services/agent/sources/qq_source.py` | QQ 消息 → AgentMessage 转换（群聊/私聊） |
| `backend/services/agent/tools/send_message.py` | 发送消息工具（自动区分群聊/私聊发送、STM 事件记录） |
| `backend/services/core/prompt_builder.py` | System prompt 构建（人设+STM感知+工具+格式+私聊提示） |
| `backend/services/core/loader.py` | 核心层人设加载（identity.md） |
| `backend/services/context_manager.py` | 对话上下文管理（SQLite 存储，按 group_id 查询） |
| `backend/services/memory_interface.py` | 记忆系统接口（HTTP 调用 Memory 服务） |
| `backend/services/stm_client.py` | STM HTTP 客户端（调用 Memory 的短期记忆 API） |
| `backend/services/sleep_manager.py` | 睡眠管理器（状态机、私聊队列、唤醒序列、精力状态缓存） |
| `backend/services/error_notifier.py` | 错误通知模块（出错时私聊通知管理员，含冷却防刷屏） |
| `backend/services/core/time_utils.py` | 相对时间格式化工具（"3分钟前"、"昨天"等） |
| `backend/routes/config_routes.py` | 配置管理 API（双模型配置、Vision 配置等） |

### Memory

| 文件/目录 | 职责 |
|-----------|------|
| `Memory/api/memory_api.py` | Memory HTTP API（/api/event 接收事件、/api/recall 召回） |
| `Memory/server/app.py` | FastAPI 服务器（所有 HTTP 端点，含 STM 端点） |
| `Memory/server/schemas.py` | HTTP 请求/响应模型（含 STM schemas） |
| `Memory/config/settings.py` | 全局配置（ModelsConfig、DecayConfig、DreamConfig、StmConfig 等） |
| `Memory/config/prompts/` | LLM prompt 模板（实体识别、情感分析、记忆简报等） |
| `Memory/llm/` | LLM 客户端（BaseLLMClient、QianwenClient、DeepSeekClient、LLMFactory） |
| `Memory/writer/` | 写入层（事件处理管道：L0 摘要、实体识别、情感快照） |
| `Memory/recall/` | 召回层（双轨召回：经验轨道 + 实体轨道、记忆简报生成） |
| `Memory/consolidator/` | 巩固层（梦境处理：记忆重组、情感加工、边发现、衰减计算、定时调度） |
| `Memory/storage/` | 存储层（经验节点 L0-L3、信息实体、边、用户档案） |
| `Memory/storage/stm_store.py` | 短期记忆存储（stm_events + stm_compressed 表） |
| `Memory/stm/` | 短期记忆模块（感知构建器 PerceptionBuilder、压缩器 StmCompressor） |
| `Memory/core/` | ⚠️ 已废弃 — 核心层数据现通过 Backend HTTP API 获取 |
| `Memory/.env` | Memory 系统环境变量（LLM_API_KEY、LLM_BASE_URL 等） |

### 核心层人设

`backend/services/core/identity.md` 是核心层**唯一数据源**，定义 AI 的人格三层：

- **不变层**: 硬约束（不假装是人类、不说套话、不参与伤害）
- **稳定层**: 行为模式（深思熟虑、喜欢追问"为什么"、第一人称说话）
- **可塑层**: 当前表达状态（语气、话题偏好、情感基调，YAML 格式可动态修改）

数据流：
- **读取**: Backend 直接读文件，Memory 通过 `GET /api/core/identity` HTTP 获取
- **写入**: 仅梦境模块 `dream_malleable` 通过 `POST /api/core/malleable` 更新可塑层
- `Memory/core/` 目录和 `Memory/storage/core_store.py` 已废弃

## 配置

### Backend 配置

`backend/llm_config.yaml`:

```yaml
thinking_provider:        # 思考模型（推理/工具决策）
  api_key: sk-xxx
  base_url: https://api.deepseek.com
  model: deepseek-reasoner

speaking_provider:        # 说话模型（润色回复）
  api_key: sk-xxx
  base_url: https://api.deepseek.com
  model: deepseek-chat

brain:
  max_iterations: 6      # 最大思考轮次

memory:
  service_url: http://localhost:8001

napcat:
  http_url: http://localhost:3000

admin:
  qq_id: "123456"       # 管理员QQ号（接收错误通知）
```

也支持旧的 `active_provider` + `providers` 格式（向后兼容）。

### Memory 配置

`Memory/.env`:

```env
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 启动

```bash
# 1. 启动 Memory 服务
cd Memory && python -m Memory.server    # 端口 8001

# 2. 启动 Backend
cd backend && uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 3. 启动管理前端（可选）
conda activate SpaceX
python backend/web/app.py              # 端口 5002，浏览器访问 http://localhost:5002
```

## 已知问题 & TODO

### 待解决

1. **Gemini 模型兼容性**: 部分 Gemini 模型不严格遵循 JSON 输出指令
   - 已有 fallback：`_parse_llm_response()` 尝试 markdown 代码块提取 + 纯文本包装
   - 心跳模式已处理：纯文本 fallback 时选择沉默而非发送

2. **说话模型润色延迟**: 双模型架构下每条回复多一次 API 调用
   - 当 thinking 和 speaking 是同一模型时自动跳过润色
   - 无配置开关控制是否启用润色

### 最近完成的改动

- **睡眠-觉醒周期**: AI 模拟人类睡眠节律，通过状态层精力变化自然感受困倦/清醒
  - 新增 `backend/services/sleep_manager.py`（状态机：AWAKE → WINDING_DOWN → ASLEEP → 唤醒）
  - 23:00 精力→"困倦"（停心跳），00:00 入睡（消息存DB不处理），08:00 唤醒（STM注入+处理私聊）
  - 群聊消息睡眠期间仅存DB，醒来后AI自然发现；私聊消息入队列，唤醒后主动处理
  - 详细设计见 [docs/sleep-cycle-design.md](docs/sleep-cycle-design.md)
- **中间回复 (interim_message)**: AI 在思考过程中发送简短提示（如"等我想想"），在工具执行前异步发送
  - `prompt_builder.py` 在回复格式中增加 `interim_message` 字段
  - `brain.py` 在工具执行前检测并发送，不经过说话模型润色，不存入上下文
  - 每次思考最多一条，LLM 驱动内容，每次用不同说法
- **数据库 Schema v9**: `experience_edges` 表新增 `dormant` 列（休眠标记），修复巩固层隐性边写入失败
- **数据库 Schema v10**: 三张边表新增 `UNIQUE(from_id, to_id)` 约束，从数据库层面防止巩固层重复创建边。所有边写入使用 `INSERT OR REPLACE` 防并发冲突
- **后台管理前端**: `backend/web/app.py`（Flask, 端口 5002），暗色主题，5 个页面（仪表盘、日志、群聊、模型、核心），代理 Backend(8000) + Memory(8001) API
- **巩固层边去重**: 同一对节点只存一条边（不区分方向），写入时检查反向边；`implicit_edges_task` 不再创建双向边；`dream_malleable_task` 使用 `response_format="text"` 并校验 YAML 结构合法性
- **Backend health 修复**: `config_manager.get_current_api()` 改用 `self.api_config` 属性（有 None 保护），修复 `_api_config` 为 None 时的 AttributeError
- **巩固层定时调度**: 巩固层从手动 CLI 触发改为休眠期间自动调度
  - 新增 `Memory/consolidator/scheduler.py`（状态机：IDLE → INCREMENTAL → FULL → DONE）
  - 休眠时间（默认 02:00~08:00）自动触发：先增量巩固，剩余时间 > 30min 再全量巩固
  - 全量巩固带超时保护（不超过剩余休眠时间 - 5分钟）
  - 新增 `GET /api/consolidate/status` 端点查看调度状态
  - 仍支持手动 CLI 触发：`python -m Memory.consolidator run`
- **错误通知**: 系统出错时自动私聊通知管理员
  - 新增 `backend/services/error_notifier.py`（fire-and-forget，不阻塞主流程）
  - 覆盖 7 个错误点：LLM 调用失败、工具执行失败、消息处理失败、心跳失败等
  - 同类错误 60 秒内只通知一次（防刷屏）
  - 配置：`llm_config.yaml` 的 `admin.qq_id`
- **时间间隔感知修复**: 修复 AI 无法准确判断上下文间隔时间的问题
  - 新增 `backend/services/core/time_utils.py`（相对时间格式化："3分钟前"、"昨天 14:30"）
  - STM 感知和对话上下文从裸 `HH:MM` 改为带相对时间标注
  - 消息头添加当前时间，超过 10 分钟的对话间隔自动标注
  - 记忆简报时间距离从整数天改为小数天（2小时显示"2小时前"而非"0天前"）
  - recall_context 的 `current_time` 从空字符串改为实际时间
- **核心层双写不一致修复**: Memory 服务的核心层读取统一改为通过 HTTP 从 Backend 获取，消除 Memory 本地文件/SQLite 与 Backend identity.md 之间的数据不一致
  - `MemoryAPI.load_core()` 改为 `requests.get(Backend /api/core/identity)`
  - Web UI `/api/core` 同步改为 HTTP 获取
  - `ProfileManager._load_identity()` 同步改为 HTTP 获取
  - `Memory/core/` 目录和 `Memory/storage/core_store.py` 标记为废弃
  - Backend `backend/services/core/identity.md` 是核心层唯一数据源
- **短期记忆（STM）跨会话感知**: Memory 服务新增 STM 模块，记录 AI 所有行为和关键用户消息，构建感知区块注入 LLM 上下文，解决跨会话失忆问题
  - 新增文件：`Memory/stm/`（感知构建、压缩器）、`Memory/storage/stm_store.py`、`backend/services/stm_client.py`
  - API 端点：`POST /api/stm/event`、`GET /api/stm/perception`、`POST /api/stm/compress`
  - 数据库 Schema v8：`stm_events` + `stm_compressed` 表
- **双模型架构** (thinking_provider + speaking_provider): `backend/api/llm.py` LLMManager 支持
- **私聊功能**: 完整适配群聊→私聊（消息收发、AI 环境感知、记忆系统 source_type="qq_private"）
- **JSON 解析兼容**: `brain.py` 的 `_parse_llm_response()` 兼容 markdown 代码块包裹的 JSON
- **心跳模式安全**: 非JSON 响应在心跳模式下自动沉默

### 已知未实现项

1. **边 access_count 未递增**: 召回时走过的边不会增加 access_count，导致衰减公式中的强化因子 `(1 + α × access_count)` 永远等于 1，缺少"越想越记得"的复习强化效果。需要修改 AdjacencyCache 和 RecallManager 在扩散完成后批量递增。
2. **节点衰减值算而不用**: 巩固 Phase 2 计算了 L0-L3 的 decayed 值写回数据库，但召回排序（rank_score = activation_score × importance）不消费这些值。
3. **信息层置信度不衰减**: 设计文档要求实体 confidence 按 `confidence × e^(-λt)` 衰减（λ=0.005），但当前衰减计算只处理体验边和体验节点。

## 开发约定

- Backend 使用 httpx (async)，Memory 使用 requests (sync) + OpenAI SDK
- LLM 超时: Backend 120s（支持慢速推理模型），Memory 30s
- 工具参数命名: `SendMessageTool` 使用 `instruction`（不是 `message`）
- 私聊 group_id 格式: `private_{user_id}`
- 记忆 source_type: 群聊 `"qq_group"`, 私聊 `"qq_private"`
- STM 事件记录: 所有 `asyncio.create_task(stm_client.record_event(...))` 均为 fire-and-forget，不阻塞主流程
- STM 感知注入: 通过 `build_system_prompt(stm_perception=...)` 注入到 system prompt 的独立区块
- 向后兼容: 旧的单模型 `active_provider` 配置仍然可用
- Schema 版本: 当前 v10（边表 UNIQUE 约束），迁移在 Memory 服务启动时自动执行
- 边表写入统一使用 `INSERT OR REPLACE`，同一对节点只存一条边，写入时自动检查反向边
- LLM `call()` 默认 `response_format="json"` 会返回解析后的 Python 对象（dict/list），需要纯文本时必须传 `response_format="text"`
