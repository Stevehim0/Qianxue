"""测试写入层端到端流程（Phase 14.1：长对话格式）。

验证：
1. API接收长对话格式
2. Pipeline并行处理三个任务
3. 体验节点正确创建
4. L0摘要使用AI第一人称视角
5. 信息提取创建信息实体
6. 情感分析emotion_target为None
"""

import pytest
from Memory.api.memory_api import MemoryAPI
from Memory.storage.experience_store import experience_store
from Memory.storage.entity_store import entity_store
from Memory.storage.cross_edge_store import cross_edge_store


@pytest.fixture
def api():
    """初始化MemoryAPI。"""
    from Memory.storage.database import db_manager
    db_manager.initialize()
    return MemoryAPI()


@pytest.fixture
def long_dialogue():
    """示例长对话（12轮）。"""
    return """
    张三：你好，我想学Python，但是完全没有编程基础，应该从哪里开始？

AI：你好！很高兴听到你想学习Python。对于完全没有基础的人来说，我建议先从Python的基础语法开始。不要着急，一步一步来。可以先了解变量、数据类型、基本运算这些概念。你有没有特别想用Python做的事情？这样我可以给你更具体的建议。

张三：其实我想做数据分析，听说Python在这方面很强。

AI：非常好的选择！Python确实是数据分析领域的热门工具。对于数据分析方向，我建议你的学习路径是：首先是Python基础语法（1-2周），然后学习NumPy和Pandas这两个核心库（2-3周），接着学习Matplotlib进行数据可视化（1-2周），最后可以学习Scikit-learn进行机器学习（可选）。你已经安装Python了吗？

张三：还没有安装，我应该用什么工具呢？

AI：对于初学者，我强烈推荐Anaconda发行版。它是一个集成的Python环境，包含了你需要的所有数据分析库（NumPy、Pandas、Matplotlib等），安装非常简单，一个安装包就搞定了。安装后还会自带Jupyter Notebook，这是一个非常适合数据分析的交互式编程环境。你可以先下载Anaconda，安装好后我们再继续。

张三：好的，我已经下载了Anaconda。安装过程中需要注意什么吗？

AI：安装时记得选择"Add Anaconda to my PATH environment variable"这个选项，虽然不是必须的，但这样可以在命令行直接使用Python命令。安装完成后，你可以打开Anaconda Navigator，这是一个图形界面，里面有Jupyter Notebook等工具。或者直接在开始菜单搜索Jupyter Notebook。你现在打开Jupyter Notebook试试看？

张三：已经打开了，但我不知道该怎么用。

AI：没关系，我来解释一下。Jupyter Notebook会在浏览器中打开，你会看到一个文件目录界面。点击右上角的"New"按钮，选择"Python 3"，就会创建一个新的notebook。现在你应该能看到一个空的单元格，你可以在里面输入代码，然后按Shift+Enter执行。试试输入 print("Hello World") 然后按Shift+Enter？

张三：成功了！我看到了输出结果。现在感觉很有信心。

AI：太好了！那我们正式开始学习吧。在Jupyter Notebook中，我们先学习Python的基础。首先，变量就像一个盒子，你可以把数据放进去。比如：name = "张三"，这里name就是变量名，"张三"是值。你可以试试创建自己的变量，比如你的年龄、喜欢的颜色等等。

张三：我写了 age = 25 和 color = "blue"，成功了！

AI：没错！现在你对数据类型有了基本了解。接下来是列表（list），这是一个非常重要的数据结构，特别适合数据分析。列表用方括号表示，比如：numbers = [1, 2, 3, 4, 5]。列表可以存储多个值，而且可以包含不同类型的数据。你现在可以试试创建一个包含你喜欢的食物的列表。

张三：我创建了 foods = ["apple", "banana", "orange"]，感觉这个很有用。

AI：确实很有用！在数据分析中，你会经常使用列表。现在你已经掌握了Python的基础：变量、数据类型、列表。建议你今天先练习这些概念，明天我们开始学习Pandas，它是数据分析的核心工具。记住，编程最重要的是多练习，不要怕犯错。

张三：非常感谢你的耐心指导，我现在对学习Python充满了信心！

AI：不客气！学习编程是一个循序渐进的过程，你今天的表现已经很好了。记住每天练习一点，积少成多。如果遇到问题，随时可以来问我。祝你学习愉快！
    """


def test_api_receives_dialogue_and_creates_experience(api, long_dialogue):
    """测试：API接收长对话格式并创建体验节点。"""
    # Act
    exp_id = api.receive_event(dialogue=long_dialogue)

    # Assert
    assert exp_id is not None
    assert exp_id.startswith("exp_")

    # 验证体验节点存在
    exp = experience_store.get(exp_id)
    assert exp is not None
    assert exp.L3_raw == long_dialogue.strip()


def test_pipeline_generates_l0_summary_with_first_person(api, long_dialogue):
    """测试：Pipeline生成L0摘要，使用AI第一人称视角。"""
    # Act
    exp_id = api.receive_event(dialogue=long_dialogue)

    # Assert
    exp = experience_store.get(exp_id)
    assert exp.L0_text is not None
    assert len(exp.L0_text) > 0

    # 验证第一人称视角
    assert "我" in exp.L0_text  # 包含"我"
    # 不应该出现"用户询问"这类客观描述
    assert "用户询问" not in exp.L0_text
    assert "AI回答" not in exp.L0_text


def test_pipeline_extracts_information_entities(api, long_dialogue):
    """测试：Pipeline提取信息并创建信息实体。"""
    # Act
    exp_id = api.receive_event(dialogue=long_dialogue)

    # Assert
    edges = cross_edge_store.get_by_experience(exp_id)
    assert len(edges) > 0  # 应该提取到一些信息

    # 验证信息实体
    for edge in edges:
        entity = entity_store.get(edge.to_id)
        assert entity is not None
        # 验证跨层边context
        assert edge.context == "contains_information"
        # 验证properties包含source
        assert "source" in entity.properties


def test_pipeline_analyzes_emotion_with_none_target(api, long_dialogue):
    """测试：Pipeline分析情感，emotion_target为None。"""
    # Act
    exp_id = api.receive_event(dialogue=long_dialogue)

    # Assert
    exp = experience_store.get(exp_id)
    assert exp.emotion_category is not None
    assert exp.emotion_target is None  # 关键验证


def test_end_to_end_integration(api, long_dialogue):
    """测试：端到端集成验证。

    验证完整流程：
    - API接收长对话
    - Pipeline并行处理
    - 三个任务全部成功
    - 数据库存储正确
    """
    # Act
    exp_id = api.receive_event(dialogue=long_dialogue)

    # Assert - 体验节点
    exp = experience_store.get(exp_id)
    assert exp is not None
    assert exp.L3_raw == long_dialogue.strip()
    assert exp.L0_text is not None
    assert exp.L0_embedding is not None
    assert exp.emotion_category is not None
    assert exp.emotion_target is None

    # Assert - 信息实体
    edges = cross_edge_store.get_by_experience(exp_id)
    assert len(edges) > 0

    # Assert - 第一人称视角
    assert "我" in exp.L0_text
    assert "张三" in exp.L0_text or "Python" in exp.L0_text
