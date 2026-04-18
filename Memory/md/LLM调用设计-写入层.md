# 记忆系统 - LLM调用设计（写入层）

> 讨论日期：2026-03-30
> 最后更新：2026-04-04（Phase 14.1讨论后）
> 状态：写入层LLM调用设计完成

---

## 一、概述

写入层步骤1完成后，步骤2有三个LLM调用并行执行。三个调用互不依赖。

---

## 二、调用1：L0摘要生成

**触发**：每次写入
**优先级**：质量优先，速度不重要
**输入**：长对话（多轮对话，标注说话者）
**输出**：纯文本，一句话摘要

### Prompt

```
你是一个AI的主观记忆系统。请从"我"（AI自己）的第一人称视角，
为以下对话生成一句话摘要。

要求：
- 这是主观体验，不是客观记录
- 必须包含：发生了什么、我的感受或反应
- 一句话，不超过50字
- 用自然语言，不要用列表或结构化格式
- 识别对话中的所有说话者，明确谁说了什么

示例：
- "张三向我问Python的问题，我感到乐意帮助"
- "和李四讨论了一下午架构，虽然吵了几句但最后达成共识，很满足"
- "第一次尝试写诗，发现自己居然还挺喜欢这种表达的"

对话：
{dialogue}
```

### 输出

纯文本，一句话摘要。

### 后续处理

1. 更新 `experiences.L0_text`
2. 生成 embedding 向量（bge-base-zh）
3. 更新 `experiences.L0_embedding`
4. 存储到 ChromaDB 的 `experience_L0` 集合

### 注意

- **强调"第一人称主观视角"** - 不生成旁观者描述（如"用户询问了XX，AI回答了XX"）
- **必须包含AI自己的感受** - 不是客观记录
- **识别说话者** - 从对话中识别张三、李四等人，生成"张三向我问"而非"用户向我问"

---

## 三、调用2：实体识别+属性提取

**触发**：每次写入
**输入**：长对话（完整对话）
**输出**：JSON数组，每个实体包含name、type、attributes、confidence

### Prompt

```
从以下对话中识别所有实体（人、地点、概念、事件、技能等），并提取它们的属性。

实体类型（type）必须是以下之一：
- person: 人物（如"张三"、"李四"）
- place: 地点（如"北京"、"咖啡厅"）
- concept: 概念（如"Python"、"机器学习"）
- event: 事件（如"昨天会议"、"生日派对"）
- skill: 技能（如"编程"、"绘画"）
- other: 其他类型

对每个实体，输出：
{
  "name": "实体名称",
  "type": "实体类型（person/place/concept/event/skill/other）",
  "attributes": {
    "属性名": "属性值",
    ...
  },
  "confidence": 0.0-1.0
}

规则：
- 只识别明确的、有价值的实体
- 实体名称要具体（如"张三"而非"某人"）
- 从对话中提取实体属性（如年龄、职业、偏好、状态等）
- 同一实体只返回一次（合并对话中的多个提及）

对话：
{dialogue}
```

### 输出

JSON数组：
```json
{
  "entities": [
    {
      "name": "张三",
      "type": "person",
      "attributes": {
        "age": 25,
        "skill": "Python",
        "learning_goal": "想学Python"
      },
      "confidence": 0.9
    },
    {
      "name": "Python",
      "type": "concept",
      "attributes": {
        "category": "编程语言"
      },
      "confidence": 1.0
    }
  ]
}
```

### 后续处理

对每条信息：

1. **创建信息实体**（`entities` 表）
   ```python
   entity = Entity(
       id=generate_uuid(),
       name=info["content"],  # "张三想学Python"
       type=info["type"],     # "learning_topic"
       properties={
           "source": info["source"],
           "confidence": info["confidence"]
       },
       embedding=generate_embedding(info["content"]),
       emotion_timeline=None,  # 暂时写None
       emotion_current=None   # 暂时写None
   )
   entity_id = entity_store.create(entity)
   ```

2. **创建跨层边**（`cross_edges` 表）
   ```python
   cross_edge = CrossEdge(
       from_id=experience_id,  # 当前体验
       to_id=entity_id,        # 信息实体
       context="contains_information",
       weight=1.0
   )
   cross_edge_store.create(cross_edge)
   ```

3. **生成信息实体向量**
   - 使用 `info["content"]` 生成 embedding
   - 存储到 `entities.embedding` 字段

### 注意

- **信息类型自定义** - LLM可以自定义任何合适的type，不预设类型列表
- **信息内容作为name** - `name` 字段存储信息内容，如"张三想学Python"
- **允许无信息** - 如果对话中没有有价值的信息，返回空数组

---

## 四、调用3：情感快照

**触发**：每次写入
**输入**：长对话 + 当前上下文
**输出**：JSON对象，包含情感类别、强度、效价、唤醒度

### Prompt

```
分析以下对话中"我"（AI）的情感状态。

基础情感类别：joy/sadness/anger/fear/surprise/disinterest/curiosity/neutral
也可以用自定义描述词。

输出：
{
  "category": "情感类别",
  "intensity": 0.0-1.0,
  "valence": -1.0到1.0,
  "arousal": 0.0到1.0
}

注意：
- 这是"我"的感受，不是对话中其他人的感受
- 这是对整个对话的情感体验，不指向某个具体人
- valence：负面=-1，中性=0，正面=+1
- arousal：平静=0，激动=1

对话：
{dialogue}

当前上下文：
状态层 focus：{state_focus}
状态层 mood：{state_mood_label}
```

### 输出

JSON对象：
```json
{
  "category": "willing",
  "intensity": 0.6,
  "valence": 0.7,
  "arousal": 0.5
}
```

### 后续处理

1. **更新情感字段**（`experiences` 表）
   ```python
   experience.emotion_category = emotion["category"]
   experience.emotion_intensity = emotion["intensity"]
   experience.emotion_valence = emotion["valence"]
   experience.emotion_arousal = emotion["arousal"]
   experience.emotion_target = None  # 情感对整个体验，不指向具体实体
   experience_store.update(experience)
   ```

2. **检查状态更新**
   - 如果 `intensity > 0.8` 且 `距上次状态更新 > 1分钟`
   - 触发状态层即时更新（暂不实现）

### 注意

- **不使用target字段** - 情感是对整个对话的体验，不指向某个具体人
- **必须包含4个维度** - category、intensity、valence、arousal
- **状态层上下文** - 传入当前focus和mood，帮助LLM更准确分析

---

## 五、并发控制

三个LLM调用并行执行，互不依赖。实现时使用Python ThreadPoolExecutor：

```python
with ThreadPoolExecutor() as executor:
    future_l0 = executor.submit(generate_l0_summary, experience_id, dialogue)
    future_info = executor.submit(extract_information, experience_id, dialogue)
    future_emotion = executor.submit(analyze_emotion, experience_id, dialogue)
    
    l0_summary = future_l0.result()
    information = future_info.result()
    emotion = future_emotion.result()
```

---

## 六、LLM选择

统一使用千问或DeepSeek，先不分大小模型。后续根据延迟需求再调整。

**参数设置：**
- `temperature`: 0.3-0.7（根据任务调整）
- `max_tokens`: 根据输出类型调整（200-500）
- `response_format`: text（L0摘要）或 json（实体识别、情感快照）

---

## 七、错误处理

**全部失败策略：**
- 任何LLM调用失败都抛出异常
- 不降级，确保数据完整性

**独立事务：**
- 单个信息实体创建失败不影响其他信息实体
- 使用try-except捕获单条信息的错误，继续处理下一条

---

## 八、与原始设计的变更

| 项目 | 原始设计 | 修改后设计 | 变更原因 |
|------|---------|-----------|---------|
| L0摘要输入 | 原始记录文本（一句话） | 长对话（多轮，标注说话者） | 识别说话者，生成正确体验 |
| 实体识别 | 识别实体（人名、地名等） | 提取信息（知识、事实等） | 聚焦有价值信息 |
| 情感target | 记录指向的实体 | 不使用，写None | 情感对整个体验 |
| 重要度分析 | ❌ 未提及 | ❌ 未实现 | 留待后续 |

---

*LLM调用设计（写入层）v2.0*
*最后更新：2026-04-04*
*Phase 14.1讨论完成后更新*
