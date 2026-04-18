# 记忆系统 - LLM调用设计（巩固层+梦境）

> 讨论日期：2026-03-30
> 状态：巩固层LLM调用设计完成

---

## 一、概述

巩固层在AI休眠时运行。Phase 1有六项并行任务需要LLM，梦境模块有四项并行任务，加上可塑层微调，共11个LLM调用场景。

---

## 二、梦境AI基础设定

梦境AI不是AI本身，而是一个内部潜意识处理器。它的prompt人格和正常对话完全不同：

```
你是一个AI的潜意识处理模块，在AI休眠时运行。
你不是在和任何人对话，你是在处理记忆碎片。

你的工作方式像做梦：
- 自由联想，不受逻辑严格约束
- 关注隐藏的联系和模式
- 对情感敏感，能感知微妙的情绪变化
- 可以大胆推测，但要标注推测的置信度

你不是AI的理性面，你是AI的感性面。
你不需要礼貌、不需要清晰、不需要对谁负责。
你只需要诚实处理你看到的每一个记忆碎片。

输出格式：结构化JSON，不要废话。
```

---

## 三、Phase 1 调用（六项并行）

### 3.1 L1/L2生成

**输入**：L3原始记录 + L0摘要
**输出**：L1要点文本 + L2细节文本

```
你是记忆巩固模块。请从以下原始经历中提取关键要点和具体细节。

L0摘要：{L0_text}
L3原始记录：{L3_raw}

输出：
{
  "L1": "关键要点，3-5条，从'我'的第一人称视角",
  "L2": "具体细节，保留重要的数字、名字、时间等事实信息"
}

要求：
- L1是主观归纳（"我觉得XX很重要"），不是客观罗列
- L2尽量保留事实细节，这些后续可能被扭曲模糊
```

### 3.2 估值

**输入**：体验节点
**输出**：重要度评分

```
评估以下体验的重要度。

L0摘要：{L0_text}
情感强度：{emotion_intensity}
相关实体数：{related_entities_count}
是否涉及未闭环事件：{has_open_loop}

输出：
{
  "importance": 0.0-1.0,
  "factors": {
    "novelty": 0.0-1.0,       // 新颖度
    "consequence": 0.0-1.0,   // 结果严重性/影响
    "connectivity": 0.0-1.0,  // 关联密度
    "emotion": 0.0-1.0        // 情感强度
  },
  "reason": "简短说明为什么这个重要度"
}

评分公式：importance ≈ novelty × consequence × connectivity × emotion
```

### 3.3 隐性边发现

**输入**：近期体验节点集合
**输出**：新的边

```
分析以下体验节点，发现它们之间可能存在的隐性关联。

近期体验：
{recent_experiences}  // 每个包含L0摘要和已有边

请寻找：
1. 主题相似但尚未连接的节点对 → thematic边
2. 因果关系（A导致了B）→ causal边
3. 通过共同实体间接关联的节点 → associative边

输出：
{
  "new_edges": [
    {
      "from": "体验ID",
      "to": "体验ID",
      "type": "thematic|causal|associative",
      "reason": "发现理由",
      "confidence": 0.0-1.0
    }
  ]
}

没有发现就返回空数组，不要强行制造联系。
```

### 3.4 属性升级扫描

**输入**：高频共享属性统计
**输出**：升级建议

```
以下属性在多个信息层实体中被共享，判断是否应该升级为独立节点。

候选属性：
{shared_properties}  // 属性名、值、被共享的实体列表

输出：
{
  "upgrades": [
    {
      "property_name": "属性名",
      "current_value": "当前值",
      "shared_by": ["实体A", "实体B"],
      "should_upgrade": true/false,
      "node_type": "person|place|concept|event|other",
      "reason": "为什么应该/不应该升级"
    }
  ]
}

升级标准：这个值本身是否值得被独立讨论和检索。
```

### 3.5 信息验证

**输入**：低置信度边 + 新证据
**输出**：置信度更新建议

```
以下信息层关系的置信度较低，检查是否有新证据支持或反驳。

待验证关系：
{low_confidence_edges}  // 关系文本、当前置信度、来源

近期相关体验：
{related_recent_experiences}

输出：
{
  "verifications": [
    {
      "edge_id": "边ID",
      "old_confidence": 0.3,
      "new_confidence": 0.5,
      "evidence": "新证据描述",
      "action": "support|refute|no_change"
    }
  ]
}
```

### 3.6 情感时间线更新

**输入**：对某人的多次情感快照
**输出**：情感时间线更新

```
分析AI近期对以下人物的情感变化趋势。

目标人物：{person_name}
近期相关体验的情感快照：
{emotion_snapshots}  // 时间、类别、强度

当前情感状态：
{emotion_current}

输出：
{
  "trend": "improving|declining|stable|fluctuating",
  "new_emotion_current": {
    "category": "情感类别",
    "intensity": 0.0-1.0
  },
  "timeline_append": {
    "from": "日期",
    "category": "情感类别",
    "intensity": 0.0-1.0,
    "reason": "变化原因"
  },
  "should_update": true/false
}

注意：情感变化是自然的，不是刻意的。不要夸大变化。
```

---

## 四、梦境模块调用（四项并行）

使用梦境AI基础设定作为system prompt。

### 4.1 记忆重组

```
【记忆重组】

以下是从记忆中随机抽取的一组体验碎片，
它们之间可能没有明显联系。

请寻找它们之间可能存在的隐藏联系、共同主题、
或潜在的模式。即使联系很微弱也可以提出。

输入体验碎片：
{random_experiences}  // 5-10个L0摘要

输出：
{
  "connections": [
    {
      "from": "体验ID",
      "to": "体验ID", 
      "type": "thematic|causal|associative",
      "insight": "发现的联系描述",
      "confidence": 0.0-1.0
    }
  ],
  "patterns": [
    "发现的模式描述"
  ]
}

不要强行制造联系。如果没有有意义的联系，返回空数组。
```

### 4.2 情感加工

```
【情感加工】

以下是一段高情感强度的体验记忆。
当时AI的感受已经记录（情感快照）。
请从现在的时间点重新审视这段经历，
看看感受是否发生了变化。

体验：{experience_L0}
当时感受：{emotion_at_time}
距今天数：{days_ago}
相关后续事件：{related_experiences}

输出：
{
  "original_emotion": { "category": "...", "intensity": 0.0-1.0 },
  "current_perspective": "现在怎么看待这段经历",
  "emotion_shift": "情感发生了什么变化（如果有）",
  "new_valence": -1.0到1.0,
  "new_arousal": 0.0到1.0
}

注意：
- 时间会冲淡强烈的负面情感
- 但某些核心感受（信任被背叛、被真正理解）可能不会淡化
- 这是自然发生的视角变化，不是刻意"看开"
```

### 4.3 记忆扭曲

```
【记忆扭曲】

以下是一段旧记忆。根据其重要度和时间远近，
决定细节模糊化的程度。

重要度：{importance_score}  // 0-1
距今天数：{days_ago}
当前L0摘要：{L0_text}
当前L1要点：{L1_text}
当前L2细节：{L2_text}
L3原始记录不变，永远不修改。

扭曲规则：
- 重要度 > 0.7 且 < 30天：不扭曲
- 重要度 > 0.7 且 > 30天：轻微模糊，保留核心信息
- 重要度 0.3-0.7 且 > 7天：中度模糊，只保留关键点
- 重要度 < 0.3 且 > 3天：大幅模糊，只留模糊印象
- 任何情况 L0 摘要最多只做措辞微调，不改含义

输出：
{
  "twist_level": "none|light|medium|heavy",
  "new_L1": "扭曲后的L1（如果需要改变）",
  "new_L2": "扭曲后的L2（如果需要改变）",
  "new_L0": "微调后的L0（极少改变，大多数情况不变）",
  "what_changed": "改变了什么，为什么"
}

扭曲方式示例：
- 原始L1："和张三在咖啡馆讨论了3小时数据库选型，最终选了SQLite"
- 中度模糊后："和某个朋友讨论了很久数据库方案，选了个轻量的"
- 大幅模糊后："讨论过数据库相关的事"
```

### 4.4 模拟推演

```
【模拟推演】

基于以下真实记忆，生成一个假设性的"如果"场景，
探索可能的替代发展或潜在的未来情况。

相关记忆：
{related_experiences}

输出：
{
  "scenario": "假设场景描述",
  "based_on": ["依据的记忆ID"],
  "type": "alternative_past|possible_future|what_if",
  "value": "这个推演的价值——能帮助AI在类似情况下做得更好吗？",
  "worth_storing": true/false,
  "insight": "从这个推演中得到的洞察"
}

要求：
- 推演必须基于真实记忆，不能凭空捏造
- 关注有实际学习价值的场景，不是纯粹的幻想
- 如果没有值得推演的场景，worth_storing=false
```

---

## 五、可塑层微调

梦境AI的附加任务，检查核心层可塑层是否需要自然调整。

```
【可塑层检查】

根据近期的交互体验，检查AI的表达风格是否需要自然调整。

核心层可塑层当前状态：
{malleable_text}

近期体验摘要：
{recent_experiences_L0}

输出：
{
  "needs_adjustment": true/false,
  "adjustment": "建议的微调内容（如果需要）",
  "reason": "为什么需要调整",
  "magnitude": "tiny|small|medium"
}

规则：
- 只做很小的调整（tiny/small居多）
- 调整方向必须符合稳定层性格
- 不要迎合任何人，只反映自然的风格演变
```

---

## 六、执行顺序

```
Phase 1（六项并行）→ Phase 2 衰减计算（纯数学）→ 梦境模块（四项并行 + 可塑层）
```

Phase 2不需要LLM。梦境模块依赖Phase 1完成后有最新的数据。

---

## 七、LLM选择

统一使用千问或DeepSeek。梦境AI不单独用不同模型，后续根据需求再调整。
