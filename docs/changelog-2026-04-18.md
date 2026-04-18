# 2026-04-18 会话改动的完整记录

## 概述

本次改动覆盖了 Backend 消息处理流程、Memory 记忆系统的工具调用、个人档案创建和睡眠管理等多个子系统。核心目标：让 AI 的行为更接近真人聊天模式。

---

## 一、Bug 修复

### 1.1 `_extract_memory` 未定义 (backend/main.py)

**问题**：`_process_immediately` 调用 `_extract_memory()`，但该函数缺少 `async def` 定义，是孤立的代码块。

**修复**：补上函数头 `async def _extract_memory(group_id, user_id, content, source_type="qq_group")`。

### 1.2 STM 压缩超时参数 (Memory/stm/compressor.py)

**问题**：`QianwenClient.call()` 不接受 `timeout` 参数，compressor 传了 `timeout=15`。

**修复**：移除 `timeout=15` 参数。

---

## 二、睡眠管理禁用

### 2.1 Backend SleepManager (backend/services/sleep_manager.py)

**改动**：添加 `enabled: bool = False`，`check_and_transition()` 在 `enabled=False` 时直接返回，AI 保持 AWAKE 状态。

### 2.2 Memory 巩固调度器 (Memory/consolidator/scheduler.py + Memory/config/settings.py)

**改动**：`ScheduleConfig` 添加 `enabled: bool = False`，scheduler `start()` 检查后跳过。手动触发 `/api/consolidate` 也受此开关控制。

---

## 三、消息处理流程重构 — Debounce 队列

### 3.1 背景

原来的消息处理分两条路径：
- @消息/私聊 → `_process_immediately`（立即处理）
- 普通消息 → `_schedule_batch`（10 秒批处理窗口）

问题：
1. AI 正在回复时新消息并发处理，导致混乱
2. 人类把一句话拆成多条短消息发送，AI 逐条回复不自然
3. 没有等待对方说完的机制

### 3.2 新设计：Per-Conversation Debounce Queue

**核心文件**：`backend/main.py`

**新增数据结构**：
```python
_debounce_state: dict[str, dict]  # key = group_id
# 每个条目: {"lock": asyncio.Lock, "queue": list, "timer": asyncio.Task}
```

**新增函数**：

| 函数 | 作用 |
|------|------|
| `_get_debounce(key)` | 获取或创建 debounce 状态 |
| `_enqueue_message(key, message)` | 消息入队，启动/重置 3s 计时器 |
| `_drain_queue(key)` | 计时器到期：合并消息 → AI 处理 |
| `_combine_messages(messages)` | 多条消息拼接为一条 |

**流程**：
1. 消息到达 → 立刻存上下文/STM → `_enqueue_message` 入队 → 启动 3s 计时器
2. 3s 内新消息 → 重置计时器（等对方说完）
3. 3s 无新消息 → `_drain_queue`：合并队列消息 → AI 处理
4. AI 处理期间的新消息 → 入队等待，AI 回完后检查队列，有消息再等 3s

**删除的旧代码**：`_process_immediately`、`_schedule_batch`、`_process_batch`、`_queue_and_process`

### 3.3 影响范围

- `_process_group_message`：不再按 priority 分流，统一走 `_enqueue_message`
- `_process_private_message`：不再直接调 `_process_immediately`，走 `_enqueue_message`

---

## 四、工具调用优化

### 4.1 search_memory 工具 (backend/services/agent/tools/search_memory.py)

**改动**：description 明确说明返回内容仅供参考，需要自己判断后自然融入回复。

### 4.2 interim_message 自动发送 (backend/services/agent/brain.py)

**改动**：即使模型忘了填 `interim_message`，只要调了信息工具没配 `send_message`，自动发 "嗯...让我想想"。

### 4.3 send_message 截断机制 (backend/services/agent/tools/send_message.py)

**新增**：
- `MAX_MESSAGE_LENGTH = 20`（单条消息最大字数）
- 超长自动截断，返回 `truncated: true` + hint
- description 说明超长会被截断，长内容分多次调用

### 4.4 Brain 截断续发 (backend/services/agent/brain.py)

**改动**：
- `max_iterations` 从 3 提升到 5
- `send_message` 结果被截断时，即使模型说 `done: true` 也强制进入下一轮继续发送
- `_format_tool_results` 对截断结果显示明确的提示信息

### 4.5 Prompt 引导 (backend/services/core/prompt_builder.py)

**search_memory 规则**：
- 必须场景：涉及过去的事、提到"关于我的事"等
- 必须 `done: false`，先搜索再回复
- 必须填 `interim_message`
- 不能念搜索结果

**消息长度**：
- 每条 send_message 不超过 20 字
- 长内容拆成多条 send_message，给出示例
- 被截断时系统会提醒

**interim_message**：
- 从"可以填写"改为"必须填写"

---

## 五、个人档案系统重构

### 5.1 问题诊断

原档案系统的死循环：
1. 对话 → buffer 积累 → 质量检查（大部分闲聊被过滤）→ 不写入 experience
2. 档案创建依赖 experience 表 ≥3 次 + ≥3 天 → 永远达不到
3. 档案更新也查 experience 表 → 无数据 → 永远是默认值

### 5.2 按对话轮次创建档案

**Backend 端** (`backend/main.py`)：
- 新增 `_check_profile_for_batch(batch)`：每批消息处理后统计该用户消息数
- 新增 `_ensure_profile(nickname, user_id)`：调 Memory API 创建档案
- 阈值：10 条消息（`_PROFILE_TURN_THRESHOLD = 10`）
- 用 `_profile_checked_users` 集合去重

**Memory 端**：
- `Memory/api/memory_api.py`：新增 `ensure_profile()` 方法，不受 experience 阈值限制
- `Memory/server/app.py`：新增 `POST /api/profile/ensure` 端点
- `Memory/server/schemas.py`：新增 `EnsureProfileRequest` 模型

### 5.3 Pending Facts 机制

**目标**：从所有对话中提取人物信息（包括被质量过滤掉的），积累后更新档案。

**新增表** (`Memory/storage/schema.py`)：
```sql
CREATE TABLE profile_pending_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL,
    fact_text TEXT NOT NULL,
    source_type TEXT,
    created_at TEXT NOT NULL
)
```

**质量检查 prompt** (`Memory/config/prompts/write_quality_check.txt`)：
- 输出格式新增 `people` 字段：`{"人名": "一句话摘要"}`
- 零额外 LLM 开销——本来就是质量检查，顺带提取人物信息

**Buffer Manager** (`Memory/writer/buffer_manager.py`)：
- `_check_quality`：解析 `people` 字段，调用 `_save_pending_facts` 写入 SQLite
- `_timeout_checker_loop`：每 ~10 分钟（20 次检查循环）调用 `_process_pending_facts`
- `_process_pending_facts`：调用 ProfileManager 处理

**Profile Manager** (`Memory/recall/profile_manager.py`)：
- 新增 `process_pending_facts(threshold=20)`：某人的 facts 攒够 20 条，合并追加到档案 `notes`，删除已处理的 facts

---

## 六、对话上下文增强

### 6.1 用户档案注入 (backend/services/agent/brain.py)

**新增** `_load_profile_text(user_id)`：从 Memory API 加载用户档案。

**改动** `_build_user_message_header`：变为 async，加载档案后注入到消息头部。

效果：
```
当前时间: 2026-04-18 01:15:00 (星期五)
群聊ID: private_2950056105
用户ID: 2950056105
发送者昵称: 深

关于对方:
关系: 创造者
备注: 喜欢编程
相处风格: 亲近、幽默

用户消息: 想想关于我的事情
```

### 6.2 私聊语气词不回复 (backend/services/core/prompt_builder.py)

`_build_private_context_section` 新增规则：
> 对方发"嗯"、"哦"、"好"、"哈哈"这种语气词/回应时，不需要回复，沉默就好

---

## 七、文件变更清单

### Backend

| 文件 | 改动类型 |
|------|----------|
| `backend/main.py` | 重构：debounce 队列替代旧流程，新增档案检查 |
| `backend/services/agent/brain.py` | 截断续发、auto interim、档案注入、max_iterations 5→5 |
| `backend/services/agent/tools/search_memory.py` | description 增强 |
| `backend/services/agent/tools/send_message.py` | 20 字截断 + 返回截断信息 |
| `backend/services/core/prompt_builder.py` | search_memory 规则、短消息示例、私聊语气词、interim 必须 |
| `backend/services/sleep_manager.py` | `enabled = False` |

### Memory

| 文件 | 改动类型 |
|------|----------|
| `Memory/config/settings.py` | `ScheduleConfig.enabled = False` |
| `Memory/config/prompts/write_quality_check.txt` | 新增 `people` 字段输出 |
| `Memory/consolidator/scheduler.py` | 检查 `enabled` 标志 |
| `Memory/stm/compressor.py` | 移除 `timeout` 参数 |
| `Memory/storage/schema.py` | 新增 `profile_pending_facts` 表 + v11 迁移 |
| `Memory/recall/profile_manager.py` | 新增 `process_pending_facts` 方法 |
| `Memory/api/memory_api.py` | 新增 `ensure_profile` 方法 |
| `Memory/server/app.py` | 新增 `POST /api/profile/ensure` 端点 + consolidation 开关 |
| `Memory/server/schemas.py` | 新增 `EnsureProfileRequest` |

---

## 八、待更新文档

以下文档需要同步更新以反映本次改动：

1. **backend/INDEX.md** — 消息流图需要更新（debounce 队列替代了旧的分流逻辑）
2. **backend/README.md** — AgentBrain 工具调用说明、消息处理流程
3. **Memory/docs/API_REFERENCE.md** — 新增 `/api/profile/ensure` 端点、`ensure_profile` 方法
4. **Memory/docs/DATA_FLOW.md** — 档案创建新路径（对话轮次触发 + pending facts）
