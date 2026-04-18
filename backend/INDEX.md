# Backend 模块索引

> 快速理解 Backend 服务。Backend 是 AI QQ 聊天机器人的主系统，负责消息收发、Agent 思考引擎、工具调用、QQ 协议对接。

## 一句话总结

Backend 是一个 FastAPI 应用，通过 WebSocket 接收 NapCat（QQ 协议）消息，经过 AgentBrain 多轮思考后生成回复。

## 启动方式

```bash
# Backend 主服务
cd backend && uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 后台管理前端（另开终端）
conda activate SpaceX
python backend/web/app.py    # 端口 5002，浏览器访问 http://localhost:5002
```

## 消息流（核心路径）

```
QQ → NapCat → WebSocket(/ws/onebot) → main.py
  → QQSource 转换为 AgentMessage
  → context_manager 存上下文（立刻）
  → STM 事件记录（立刻，fire-and-forget）
  → _enqueue_message(group_id, message)
      → 消息入队，启动/重置 3s debounce 计时器
      → 3s 内新消息：重置计时器（等对方说完）
      → 3s 无新消息：_drain_queue
          → 合并队列消息（多条短消息拼成一条）
          → 记忆提取（每条单独提取）
          → 档案创建检查（10 轮对话触发）
          → AgentBrain._think_loop → LLM思考 → [中间回复] → 工具调用 → 发消息
      → AI 回完后检查队列，有新消息则再等 3s
```

## 目录结构

```
backend/
├── main.py                    # 应用入口、WebSocket路由、消息分发、心跳触发
├── config.py                  # 全局配置管理
├── llm_config.yaml            # 双模型配置文件（thinking + speaking）
├── requirements.txt
│
├── api/                       # 外部 API 客户端
│   ├── llm.py                 # ★ LLMManager - 双模型管理（thinking_chat/speaking_chat）
│   └── napcat.py              # ★ NapCatClient - QQ消息收发（群发/私发/消息解析）
│
├── database/                  # 数据库层
│   ├── db.py                  # SQLite 异步数据库管理
│   └── models.py              # 数据模型（NapCatMessage、MessageSegment 等）
│
├── routes/                    # HTTP API 路由
│   ├── config_routes.py       # 配置管理 API（双模型配置、Vision 配置）
│   ├── chat_routes.py         # 聊天相关 API
│   └── core_routes.py         # 核心层 API（人设读取/更新）
│
├── web/                       # ★ 后台管理前端（Flask, 端口 5002）
│   └── app.py                 # 单文件 Flask 应用，暗色主题，代理后端+Memory API
│
└── services/                  # 业务逻辑层
    ├── agent/                 # ★ Agent 思考引擎
    │   ├── brain.py           # ★ AgentBrain - 多轮思考循环、工具并行执行
    │   ├── message.py         # AgentMessage - 统一消息格式（含 is_private/is_heartbeat）
    │   ├── thought.py         # AgentThought - 思考结果
    │   ├── tool_call.py       # ToolCall - 工具调用封装
    │   ├── sources/
    │   │   └── qq_source.py   # QQ消息 → AgentMessage 转换
    │   └── tools/             # 可用工具列表
    │       ├── registry.py    # 工具注册中心
    │       ├── base.py        # 工具基类
    │       ├── send_message.py    # ★ 发送消息（自动区分群聊/私聊）
    │       ├── get_time.py        # 获取当前时间
    │       ├── search_memory.py   # 搜索记忆（调用 Memory 服务）
    │       ├── get_context.py     # 获取对话上下文
    │       └── recognize_image.py # 图片识别（Vision 模型）
    │
    ├── core/                  # 核心层（人设系统）
    │   ├── identity.md        # ★ AI人格三层定义（不变层/稳定层/可塑层）
    │   ├── loader.py          # 人设加载器
    │   ├── models.py          # 核心层数据模型
    │   ├── prompt_builder.py  # ★ System prompt 构建（人设+STM感知+工具+格式）
    │   └── valve_filter.py    # 阀门过滤器
    │
    ├── context_manager.py     # ★ 对话上下文管理（SQLite，按 group_id 查询）
    ├── memory_interface.py    # ★ 记忆系统 HTTP 接口（调用 Memory 服务）
    ├── stm_client.py          # ★ STM HTTP 客户端（短期记忆感知）
    ├── sleep_manager.py       # ★ 睡眠管理器（状态机、私聊队列、唤醒序列、精力缓存）
    └── vision_service.py      # 图片识别服务
```

## 关键类和函数速查

### 入口和路由

| 位置 | 名称 | 职责 |
|------|------|------|
| `main.py:230` | `onebot_websocket()` | WebSocket 端点，接收 NapCat 消息 |
| `main.py:323` | `_get_debounce()` | 获取/创建会话 debounce 状态 |
| `main.py:337` | `_enqueue_message()` | 消息入队 + 启动/重置 3s 计时器 |
| `main.py:360` | `_drain_queue()` | Debounce 到期：合并消息 → 记忆提取 → 档案检查 → AI 思考 |
| `main.py:317` | `_process_group_message()` | 群消息处理：转换 → 存上下文 → 入 debounce 队列 |
| `main.py:415` | `_process_private_message()` | 私聊消息处理（复用群逻辑，group_id=`private_{user_id}`） |
| `main.py` | `_check_profile_for_batch()` | 检查用户消息数是否达到创建档案的阈值（10 条） |
| `main.py` | `_ensure_profile()` | 调 Memory API 确保档案存在 |

### AgentBrain（思考引擎）

| 位置 | 名称 | 职责 |
|------|------|------|
| `brain.py:35` | `process_message()` | 消息处理入口 |
| `brain.py:53` | `_think_loop()` | 多轮思考循环（max_iterations=5），含中间回复+截断续发 |
| `brain.py:138` | `_think_with_tools()` | 单轮思考：构建prompt → 调LLM → 解析JSON |
| `brain.py` | `_load_profile_text()` | 加载用户档案注入到消息头部 |
| `brain.py:250` | `_parse_llm_response()` | JSON解析（兼容markdown代码块、纯文本） |
| `brain.py:470` | `_execute_tools()` | 并行执行工具调用 |
| `brain.py:566` | `_refine_with_speaking_model()` | 说话模型润色 |
| `brain.py:609` | `_send_interim_message()` | 发送中间回复（思考中的简短提示） |
| `brain.py:631` | `proactive_think()` | 心跳触发的主动思考 |

### 睡眠管理

| 位置 | 名称 | 职责 |
|------|------|------|
| `sleep_manager.py` | `SleepManager` | 睡眠状态机（AWAKE/WINDING_DOWN/ASLEEP） |
| `sleep_manager.py` | `queue_private_message()` | 睡眠期间私聊消息入队 |
| `sleep_manager.py` | `handle_wake_up()` | 唤醒序列（STM注入+恢复能量+处理私聊队列） |
| `sleep_manager.py` | `run_sleep_cycle()` | 后台任务，每60秒检查状态转换 |
| `sleep_manager.py` | `energy_label` | 当前精力标签（供 prompt_builder 注入） |

### LLM 管理

| 位置 | 名称 | 职责 |
|------|------|------|
| `llm.py:13` | `LLMProvider` | API提供者基类（OpenAI格式） |
| `llm.py:266` | `LLMManager` | 双模型管理器 |
| `llm.py:336` | `thinking_chat()` | 思考模型调用（推理/工具决策） |
| `llm.py:347` | `speaking_chat()` | 说话模型调用（润色回复，无则回退thinking） |

### 消息格式

| 位置 | 名称 | 职责 |
|------|------|------|
| `message.py:9` | `AgentMessage` | 统一消息（source/group_id/user_id/content/is_private/is_heartbeat） |
| `message.py:52` | `create_heartbeat()` | 创建心跳消息 |

### 人设系统

| 位置 | 名称 | 职责 |
|------|------|------|
| `prompt_builder.py` | `build_system_prompt()` | 构建system prompt（人设+精力状态+STM感知+工具描述+格式+中间回复说明） |
| `identity.md` | 三层人格定义 | 不变层(硬约束)/稳定层(行为模式)/可塑层(YAML可动态修改) |

### 管理前端（backend/web/）

| 页面 | 路径 | 职责 |
|------|------|------|
| 仪表盘 | `/` | AI状态、Backend/Memory健康、统计、当前模型 |
| 日志 | `/logs/stream` | SSE实时日志流，按级别过滤 |
| 群聊 | `/proxy/groups` | QQ群开关、自动回复、延迟、上下文查看/清除 |
| 模型 | `/proxy/model-config` | 双模型配置、API提供者CRUD、上下文窗口 |
| 核心 | `/proxy/core/identity` | 稳定层只读、可塑层编辑保存 |

前端通过 `/proxy/*` 路由代理 Backend(8000) 和 Memory(8001) 的 API。AI 状态直接读 Memory 的 `state_store`（同进程）。

## 配置

`llm_config.yaml` 核心字段：

```yaml
thinking_provider:        # 思考模型
  api_key / base_url / model
speaking_provider:        # 说话模型（可选，无则回退thinking）
  api_key / base_url / model
brain:
  max_iterations: 6       # 最大思考轮次
memory:
  service_url: http://localhost:8001
napcat:
  http_url: http://localhost:3000
```

## 开发约定

- 使用 httpx (async)，超时 120s（支持慢速推理模型）
- 工具参数命名: `SendMessageTool` 用 `instruction`（不是 `message`）
- 私聊 group_id 格式: `private_{user_id}`
- STM 事件记录: `asyncio.create_task(...)` 均为 fire-and-forget
- 向后兼容: 旧的单模型 `active_provider` 配置仍可用
- LLM 响应必须 JSON，纯文本当直接回复处理；心跳模式下纯文本选择沉默
- 睡眠周期: 目前已禁用（`SleepManager.enabled = False`），AI 保持 AWAKE
- 巩固调度: 目前已禁用（`ScheduleConfig.enabled = False`），不自动触发巩固
- Debounce 队列: 所有消息通过 3s debounce，等对方说完再回复；AI 处理期间新消息排队，回完后合并处理
- 消息长度: `send_message` 单条限 20 字，超长截断后模型自动续发
- 中间回复: LLM 调信息工具时自动发送（如 "嗯...让我想想"），不存上下文
- 档案创建: 用户消息满 10 条自动创建，不依赖 experience 阈值
- Pending Facts: 质量检查时顺带提取人物信息，攒够 20 条更新档案
