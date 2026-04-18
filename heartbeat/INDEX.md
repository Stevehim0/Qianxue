# Heartbeat 心跳模块索引

> 快速理解 Heartbeat 服务。Heartbeat 是独立的心跳定时器，定期向 Backend 发送心跳信号，触发 AI 主动思考。

## 一句话总结

Heartbeat 是一个极简的定时循环服务，每隔 N 秒向 Backend 发一个空 POST 请求（"叮"一声），Backend 自己决定要不要响应。

## 启动方式

```bash
python -m heartbeat    # 根据 heartbeat_config.yaml 配置
```

## 目录结构

```
heartbeat/
├── __init__.py
├── __main__.py    # 启动入口
├── config.py      # HeartbeatConfig 配置类
└── loop.py        # ★ HeartbeatLoop 主循环
```

## 核心流程

```
HeartbeatLoop.run()
  → while True:
      POST http://localhost:8000/api/heartbeat  (空请求，无业务数据)
      sleep(interval)
```

## 关键类

| 位置 | 名称 | 职责 |
|------|------|------|
| `config.py` | `HeartbeatConfig` | 配置（interval 间隔、backend_url 地址） |
| `loop.py:19` | `HeartbeatLoop` | 心跳主循环，只发空 POST |
| `loop.py:44` | `_tick()` | 执行一次心跳——发 POST，不传任何业务数据 |

## 配置

`heartbeat_config.yaml`（项目根目录）：

```yaml
interval: 300          # 心跳间隔（秒），默认5分钟
backend_url: http://localhost:8000/api/heartbeat
```

## 设计理念

- **极简原则**：Heartbeat 不传任何数据、不传群号、不传上下文——只是"叮"一声
- **决策权归 Backend**：Backend 收到心跳后自己查数据库、自己决定要不要说话
- **频率控制**：Backend 的 `AgentBrain._can_proactive_speak()` 控制主动发言频率（最少2分钟间隔，每小时最多3次）

## Backend 侧处理

心跳到达 Backend 后的完整链路：

```
POST /api/heartbeat → main.py:heartbeat_trigger()
  → asyncio.create_task(agent_brain.proactive_think())
  → _gather_proactive_context()    # 查各群最近30秒有没有新消息
  → 有活动 → AgentMessage.create_heartbeat() → _think_loop()
  → 无活动 → 跳过（省 token）
```
