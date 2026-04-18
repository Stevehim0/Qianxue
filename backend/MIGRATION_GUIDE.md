# 项目迁移指南

将项目移动到新位置或新机器后的操作指引。

---

## 好消息：几乎不需要改任何东西

项目所有路径都通过 `Path(__file__)` 动态计算，不硬编码绝对路径。所有 Python 导入使用 `from backend.xxx` 模式，只要从项目根目录启动即可。

---

## 唯一需要改的文件

### `.gitignore` 第 60 行

```
E:\NapcatQQ\runtime\
```

这是唯一的硬编码绝对路径。修改为新的 NapCat 路径，或删除该行。

---

## 迁移步骤

### 同机移动

```bash
# 1. 复制项目
xcopy "d:\Code\AI-QQchat-backup" "D:\NewPath\AI-QQchat" /E /I /H

# 2. 清除 Python 缓存 (可选但推荐)
cd D:\NewPath\AI-QQchat
find . -type d -name __pycache__ -exec rm -rf {} +

# 3. 重新安装依赖 (如果有虚拟环境)
pip install -r requirements.txt

# 4. 修改 .gitignore 中的 NapCat 路径

# 5. 删除旧数据库让它重建 (可选)
rm -f data/chat.db

# 6. 启动
cd D:\NewPath\AI-QQchat
$env:USE_NEW_ARCHITECTURE="true"; uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 新机器部署

```bash
# 1. clone
git clone <repo-url> /opt/ai-qqchat
cd /opt/ai-qqchat

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 NapCat 并配置反向 WS: ws://<服务器IP>:8000/ws/onebot

# 4. 确保 data/ 目录可写
mkdir -p data && chmod 755 data

# 5. 启动
USE_NEW_ARCHITECTURE=true uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 路径计算原理

三个关键路径都是动态计算的，不依赖项目位置：

| 文件 | 代码 | 计算结果 |
|------|------|----------|
| `backend/database/db.py:10` | `Path(__file__).parent.parent.parent / "data" / "chat.db"` | `<项目根>/data/chat.db` |

逻辑：`db.py` → `database/` → `backend/` → 项目根 → `data/chat.db`

**只要目录结构不变，路径就自动正确。**

---

## 目录结构约束

**不可改名的目录**：

```
<项目根>/
├── backend/           ← 所有 import 依赖此名称 (from backend.xxx)
│   ├── __init__.py    ← 必须存在
│   ├── main.py
│   ├── api/
│   ├── database/
│   ├── routes/
│   └── services/
│       ├── agent/
│       └── memory_interface.py
└── data/              ← 数据库目录，启动时自动创建
```

**启动约束**：必须 `cd` 到项目根目录再执行 `uvicorn`，否则 Python 找不到 `backend` 包。

---

## 排查清单

| 问题 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'backend'` | 不在项目根目录启动 | `cd <项目根>` 后再启动 |
| `no such table: users` | `data/chat.db` 不存在 | 确保 `data/` 可写，启动时自动建表 |
| NapCat 连不上 | NapCat 未启动或 WS 地址错 | 检查 `ws://localhost:8000/ws/onebot` |
| 端口占用 | 8000 端口被占 | `netstat -ano \| findstr :8000` 查看或换端口 |

## 许可证

MIT License
