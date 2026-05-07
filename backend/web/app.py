#!/usr/bin/env python3
"""千雪 - 后台管理前端

提供 Web 界面管理系统配置、查看 AI 状态、群聊管理、日志等。
代理后端 API (port 8000) 和 Memory API (port 8001)。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import requests as http_requests
from flask import Flask, jsonify, render_template_string, request, Response, stream_with_context

from Memory.storage.state_store import state_store

app = Flask(__name__)

# 目标服务地址
BACKEND_URL = "http://localhost:8000"
MEMORY_URL = "http://localhost:8001"


# ============================================================
# 工具函数
# ============================================================

def _proxy_get(url, timeout=10):
    """代理 GET 请求。"""
    try:
        resp = http_requests.get(url, timeout=timeout)
        return jsonify(resp.json()), resp.status_code
    except http_requests.ConnectionError:
        return jsonify({"error": "服务不可达"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 502


def _proxy_post(url, data=None, timeout=10):
    """代理 POST 请求。"""
    try:
        resp = http_requests.post(url, json=data, timeout=timeout)
        return jsonify(resp.json()), resp.status_code
    except http_requests.ConnectionError:
        return jsonify({"error": "服务不可达"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 502


def _proxy_put(url, data=None, timeout=10):
    """代理 PUT 请求。"""
    try:
        resp = http_requests.put(url, json=data, timeout=timeout)
        return jsonify(resp.json()), resp.status_code
    except http_requests.ConnectionError:
        return jsonify({"error": "服务不可达"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 502


def _proxy_delete(url, timeout=10):
    """代理 DELETE 请求。"""
    try:
        resp = http_requests.delete(url, timeout=timeout)
        return jsonify(resp.json()), resp.status_code
    except http_requests.ConnectionError:
        return jsonify({"error": "服务不可达"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ============================================================
# 页面路由
# ============================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


# ============================================================
# 仪表盘代理
# ============================================================

@app.route('/proxy/health')
def proxy_health():
    return _proxy_get(f"{BACKEND_URL}/health")


@app.route('/proxy/memory-health')
def proxy_memory_health():
    return _proxy_get(f"{MEMORY_URL}/health")


@app.route('/proxy/state')
def proxy_state():
    """AI 状态：直接读 state_store（同进程，不走 HTTP）。"""
    try:
        s = state_store.get()
        return jsonify({
            'mood_valence': s.mood_valence,
            'mood_arousal': s.mood_arousal,
            'mood_label': s.mood_label,
            'energy_value': s.energy_value,
            'energy_label': s.energy_label,
            'focus': s.focus,
            'confidence_value': s.confidence_value,
            'confidence_label': s.confidence_label,
            'updated_at': s.updated_at,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route('/proxy/stats')
def proxy_stats():
    return _proxy_get(f"{BACKEND_URL}/api/stats")


@app.route('/proxy/model-config')
def proxy_model_config():
    return _proxy_get(f"{BACKEND_URL}/api/model-config")


@app.route('/proxy/memory-status')
def proxy_memory_status():
    return _proxy_get(f"{MEMORY_URL}/api/status")


# ============================================================
# 日志代理（SSE 流）
# ============================================================

@app.route('/proxy/logs/stream')
def proxy_logs_stream():
    def generate():
        try:
            resp = http_requests.get(
                f"{BACKEND_URL}/logs/stream",
                stream=True,
                timeout=None,
            )
            for line in resp.iter_lines(decode_unicode=True):
                if line:
                    yield line + '\n\n'
        except Exception:
            yield ": connection lost\n\n"
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    )


# ============================================================
# 群聊代理
# ============================================================

@app.route('/proxy/groups')
def proxy_groups():
    return _proxy_get(f"{BACKEND_URL}/api/groups")


@app.route('/proxy/groups/<group_id>/toggle', methods=['POST'])
def proxy_group_toggle(group_id):
    return _proxy_post(
        f"{BACKEND_URL}/api/groups/{group_id}/toggle",
        request.json,
    )


@app.route('/proxy/groups/<group_id>/auto-reply', methods=['POST'])
def proxy_group_auto_reply(group_id):
    return _proxy_post(
        f"{BACKEND_URL}/api/groups/{group_id}/auto-reply",
        request.json,
    )


@app.route('/proxy/groups/<group_id>/delay', methods=['POST'])
def proxy_group_delay(group_id):
    return _proxy_post(
        f"{BACKEND_URL}/api/groups/{group_id}/delay",
        request.json,
    )


@app.route('/proxy/groups/<group_id>/context')
def proxy_group_context(group_id):
    limit = request.args.get('limit', 50, type=int)
    return _proxy_get(f"{BACKEND_URL}/api/groups/{group_id}/context?limit={limit}")


@app.route('/proxy/groups/<group_id>/context', methods=['DELETE'])
def proxy_group_context_clear(group_id):
    return _proxy_delete(f"{BACKEND_URL}/api/groups/{group_id}/context")


# ============================================================
# 配置代理
# ============================================================

@app.route('/proxy/configs')
def proxy_configs():
    return _proxy_get(f"{BACKEND_URL}/api/configs")


@app.route('/proxy/apis', methods=['POST'])
def proxy_add_api():
    return _proxy_post(f"{BACKEND_URL}/api/apis", request.json)


@app.route('/proxy/apis/<name>', methods=['PUT'])
def proxy_update_api(name):
    return _proxy_put(f"{BACKEND_URL}/api/apis/{name}", request.json)


@app.route('/proxy/apis/<name>', methods=['DELETE'])
def proxy_delete_api(name):
    return _proxy_delete(f"{BACKEND_URL}/api/apis/{name}")


@app.route('/proxy/apis/<name>/test', methods=['POST'])
def proxy_test_api(name):
    return _proxy_post(f"{BACKEND_URL}/api/apis/{name}/test")


@app.route('/proxy/apis/switch/<name>', methods=['POST'])
def proxy_switch_api(name):
    return _proxy_post(f"{BACKEND_URL}/api/apis/switch/{name}")


@app.route('/proxy/context-window', methods=['POST'])
def proxy_context_window():
    return _proxy_post(f"{BACKEND_URL}/api/context-window", request.json)


@app.route('/proxy/thinking-provider', methods=['PUT'])
def proxy_thinking_provider():
    return _proxy_put(f"{BACKEND_URL}/api/thinking-provider", request.json)


@app.route('/proxy/thinking-provider/test', methods=['POST'])
def proxy_thinking_provider_test():
    return _proxy_post(f"{BACKEND_URL}/api/thinking-provider/test", request.json)


# ================================================================
# 思考模型 Profiles（快速切换）
# ================================================================

@app.route('/proxy/thinking-profiles')
def proxy_thinking_profiles():
    return _proxy_get(f"{BACKEND_URL}/api/thinking-profiles")


@app.route('/proxy/thinking-profiles', methods=['POST'])
def proxy_thinking_profiles_save():
    return _proxy_post(f"{BACKEND_URL}/api/thinking-profiles", request.json)


@app.route('/proxy/thinking-profiles/<name>', methods=['DELETE'])
def proxy_thinking_profiles_delete(name):
    try:
        resp = http_requests.delete(f"{BACKEND_URL}/api/thinking-profiles/{name}", timeout=10)
        return jsonify(resp.json()), resp.status_code
    except http_requests.ConnectionError:
        return jsonify({"error": "服务不可达"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route('/proxy/thinking-profiles/<name>/activate', methods=['POST'])
def proxy_thinking_profiles_activate(name):
    return _proxy_post(f"{BACKEND_URL}/api/thinking-profiles/{name}/activate")


# ================================================================
# 心跳服务配置（代理后端内置心跳管理器）
# ================================================================

@app.route('/proxy/heartbeat-config')
def proxy_heartbeat_config():
    return _proxy_get(f"{BACKEND_URL}/api/heartbeat/status")


@app.route('/proxy/heartbeat-config', methods=['POST'])
def proxy_heartbeat_config_update():
    data = request.json
    # 保存配置到文件
    import yaml
    from pathlib import Path
    cfg_path = Path(__file__).resolve().parent.parent.parent / "heartbeat_config.yaml"
    current = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}
    for key in ("enabled", "interval", "backend_url"):
        if key in data:
            current[key] = data[key]
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(current, f, allow_unicode=True, default_flow_style=False)

    # 同步启停心跳
    if data.get("enabled"):
        return _proxy_post(f"{BACKEND_URL}/api/heartbeat/start")
    else:
        return _proxy_post(f"{BACKEND_URL}/api/heartbeat/stop")


# ============================================================
# 核心层代理
# ============================================================

@app.route('/proxy/core/identity')
def proxy_core_identity():
    return _proxy_get(f"{BACKEND_URL}/api/core/identity")


@app.route('/proxy/core/malleable', methods=['POST'])
def proxy_core_malleable():
    return _proxy_post(f"{BACKEND_URL}/api/core/malleable", request.json)


# ============================================================
# 通用 Settings 代理
# ============================================================

@app.route('/proxy/settings')
def proxy_settings():
    return _proxy_get(f"{BACKEND_URL}/api/settings")


@app.route('/proxy/settings/<section>', methods=['PUT'])
def proxy_settings_update(section):
    return _proxy_put(f"{BACKEND_URL}/api/settings/{section}", request.json)


@app.route('/proxy/memory-llm-config')
def proxy_memory_llm_config():
    return _proxy_get(f"{MEMORY_URL}/api/config/llm")


@app.route('/proxy/memory-llm-config', methods=['POST'])
def proxy_memory_llm_config_update():
    return _proxy_post(f"{MEMORY_URL}/api/config/llm", request.json)


# ============================================================
# HTML 模板
# ============================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>千雪 - 后台管理</title>
<style>
:root {
    --primary: #667eea;
    --primary-dark: #5a6fd6;
    --secondary: #764ba2;
    --bg: #0f0f1a;
    --bg-secondary: #1a1a2e;
    --card: #1e1e32;
    --card-hover: #252542;
    --sidebar-bg: #0a0a18;
    --sidebar-active: #1a1a2e;
    --text: #e0e0e0;
    --text-light: #8888aa;
    --border: #2a2a45;
    --success: #28a745;
    --warning: #ffc107;
    --danger: #dc3545;
    --info: #17a2b8;
    --shadow: rgba(0,0,0,0.4);
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--text); display:flex; height:100vh; overflow:hidden; }
::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:var(--bg-secondary); }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:var(--text-light); }

/* Sidebar */
.sidebar { width:200px; min-width:200px; background:var(--sidebar-bg); border-right:1px solid var(--border); display:flex; flex-direction:column; }
.sidebar-logo { padding:20px; font-size:20px; font-weight:700; color:var(--primary); letter-spacing:2px; text-align:center; border-bottom:1px solid var(--border); }
.sidebar-nav { flex:1; padding:10px 0; }
.nav-item { padding:12px 20px; cursor:pointer; color:var(--text-light); transition:all .2s; border-left:3px solid transparent; }
.nav-item:hover { background:var(--sidebar-active); color:var(--text); }
.nav-item.active { background:var(--sidebar-active); color:var(--primary); border-left-color:var(--primary); }

/* Main area */
.main-area { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.header { padding:16px 24px; background:var(--bg-secondary); border-bottom:1px solid var(--border); font-size:18px; font-weight:600; display:flex; align-items:center; gap:12px; }
.content { flex:1; overflow-y:auto; padding:24px; }

/* Cards */
.card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:16px; }
.card-title { font-size:14px; font-weight:600; color:var(--text-light); margin-bottom:12px; text-transform:uppercase; letter-spacing:1px; }

/* Stat grid */
.stat-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:16px; margin-bottom:20px; }
.stat-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; text-align:center; }
.stat-card .icon { font-size:28px; margin-bottom:8px; }
.stat-card .value { font-size:24px; font-weight:700; }
.stat-card .label { font-size:12px; color:var(--text-light); margin-top:4px; }
.stat-card .extra { font-size:11px; color:var(--text-light); margin-top:4px; }

/* State cards row */
.state-row { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:20px; }

/* Health badges */
.health-bar { display:flex; gap:12px; margin-bottom:20px; flex-wrap:wrap; }
.health-badge { display:inline-flex; align-items:center; gap:6px; padding:6px 14px; border-radius:20px; font-size:13px; font-weight:500; }
.health-badge.ok { background:rgba(40,167,69,.15); color:var(--success); border:1px solid rgba(40,167,69,.3); }
.health-badge.err { background:rgba(220,53,69,.15); color:var(--danger); border:1px solid rgba(220,53,69,.3); }
.health-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.health-dot.ok { background:var(--success); }
.health-dot.err { background:var(--danger); }

/* Model cards */
.model-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }
.model-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; }
.model-card h4 { color:var(--primary); margin-bottom:8px; font-size:14px; }
.model-card .info { font-size:12px; color:var(--text-light); margin-bottom:4px; }
.model-card .info span { color:var(--text); }

/* Tables */
table { width:100%; border-collapse:collapse; }
th,td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--border); font-size:13px; }
th { color:var(--text-light); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
tr:hover { background:var(--card-hover); }

/* Toggle switch */
.toggle { position:relative; display:inline-block; width:40px; height:22px; }
.toggle input { opacity:0; width:0; height:0; }
.toggle-slider { position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:var(--border); border-radius:22px; transition:.3s; }
.toggle-slider:before { position:absolute; content:""; height:16px; width:16px; left:3px; bottom:3px; background:var(--text-light); border-radius:50%; transition:.3s; }
.toggle input:checked + .toggle-slider { background:var(--primary); }
.toggle input:checked + .toggle-slider:before { transform:translateX(18px); background:white; }

/* Buttons */
.btn { display:inline-flex; align-items:center; gap:6px; padding:8px 16px; border:none; border-radius:6px; font-size:13px; cursor:pointer; transition:all .2s; font-weight:500; }
.btn-primary { background:var(--primary); color:white; }
.btn-primary:hover { background:var(--primary-dark); }
.btn-success { background:var(--success); color:white; }
.btn-success:hover { opacity:.85; }
.btn-danger { background:var(--danger); color:white; }
.btn-danger:hover { opacity:.85; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-outline { background:transparent; color:var(--text-light); border:1px solid var(--border); }
.btn-outline:hover { border-color:var(--primary); color:var(--primary); }

/* Forms */
input[type=text], input[type=number], input[type=password], textarea, select {
    background:var(--bg-secondary); color:var(--text); border:1px solid var(--border);
    border-radius:6px; padding:8px 12px; font-size:13px; width:100%; outline:none; transition:border .2s;
}
input:focus, textarea:focus, select:focus { border-color:var(--primary); }
textarea { font-family:'Consolas','Monaco',monospace; resize:vertical; }
label { display:block; font-size:12px; color:var(--text-light); margin-bottom:4px; font-weight:500; }

/* Log viewer */
.log-controls { display:flex; gap:8px; margin-bottom:12px; align-items:center; flex-wrap:wrap; }
.log-controls .btn.active { background:var(--primary); color:white; border-color:var(--primary); }
.log-output { background:var(--bg); border:1px solid var(--border); border-radius:6px; padding:12px; font-family:'Consolas','Monaco',monospace; font-size:12px; line-height:1.6; height:calc(100vh - 200px); overflow-y:auto; white-space:pre-wrap; word-break:break-all; }
.log-line { padding:1px 0; }
.log-line.info { color:#58a6ff; }
.log-line.warning { color:#d29922; }
.log-line.error { color:#f85149; }
.log-line.debug { color:#666; }
.log-line.hidden { display:none; }

/* Modal */
.modal-overlay { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,.6); z-index:1000; align-items:center; justify-content:center; }
.modal-overlay.active { display:flex; }
.modal { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:24px; max-width:600px; width:90%; max-height:80vh; overflow-y:auto; }
.modal h3 { margin-bottom:16px; color:var(--primary); }
.modal-actions { display:flex; gap:8px; justify-content:flex-end; margin-top:16px; }

/* Toast */
.toast { position:fixed; top:20px; right:20px; padding:12px 20px; border-radius:8px; font-size:13px; z-index:2000; opacity:0; transform:translateY(-10px); transition:all .3s; }
.toast.show { opacity:1; transform:translateY(0); }
.toast.success { background:var(--success); color:white; }
.toast.error { background:var(--danger); color:white; }

/* Core sections */
.core-section { border-left:3px solid var(--border); padding-left:16px; margin-bottom:20px; }
.core-section.stable { border-left-color:var(--warning); }
.core-section.malleable { border-left-color:var(--success); }
.core-section h4 { margin-bottom:8px; }
.core-section pre { background:var(--bg); padding:12px; border-radius:6px; font-size:13px; white-space:pre-wrap; border:1px solid var(--border); max-height:400px; overflow-y:auto; }

/* Context messages */
.ctx-msg { padding:8px 12px; margin:4px 0; border-radius:6px; font-size:13px; }
.ctx-msg.user { background:rgba(102,126,234,.1); border-left:2px solid var(--primary); }
.ctx-msg.assistant { background:rgba(40,167,69,.1); border-left:2px solid var(--success); }
.ctx-msg .role { font-size:11px; color:var(--text-light); font-weight:600; }
.ctx-msg .content { margin-top:2px; }

/* Form row */
.form-row { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.form-group { margin-bottom:12px; }

/* Views */
.view { display:none; }
.view.active { display:block; }

/* Settings sections */
.settings-section { background:var(--card); border:1px solid var(--border); border-radius:8px; margin-bottom:16px; overflow:hidden; }
.settings-header { padding:12px 16px; cursor:pointer; display:flex; align-items:center; justify-content:space-between; user-select:none; border-bottom:1px solid var(--border); }
.settings-header:hover { background:var(--card-hover); }
.settings-header h4 { margin:0; font-size:14px; }
.settings-header .badge { font-size:11px; padding:2px 8px; border-radius:10px; margin-left:8px; }
.settings-header .badge.restart { background:rgba(255,193,7,.15); color:var(--warning); }
.settings-header .badge.live { background:rgba(40,167,69,.15); color:var(--success); }
.settings-body { padding:16px; }
.settings-body.collapsed { display:none; }
.settings-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px 20px; }
.settings-grid .form-group { margin-bottom:0; }
.settings-actions { margin-top:16px; display:flex; justify-content:flex-end; gap:8px; }
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
    <div class="sidebar-logo">千雪</div>
    <div class="sidebar-nav">
        <div class="nav-item active" onclick="switchView('dashboard')">仪表盘</div>
        <div class="nav-item" onclick="switchView('logs')">日志</div>
        <div class="nav-item" onclick="switchView('groups')">群聊</div>
        <div class="nav-item" onclick="switchView('settings')">配置</div>
        <div class="nav-item" onclick="switchView('core')">核心</div>
    </div>
</div>

<!-- Main -->
<div class="main-area">
    <div class="header">
        <span id="page-title">仪表盘</span>
        <span id="header-status" style="font-size:12px;color:var(--text-light);margin-left:auto;"></span>
    </div>
    <div class="content">

        <!-- Dashboard -->
        <div id="view-dashboard" class="view active">
            <div id="health-bar" class="health-bar"></div>
            <div id="state-cards" class="state-row"></div>
            <div id="stats-grid" class="stat-grid"></div>
            <div id="model-cards" class="model-grid"></div>
            <div id="memory-status" class="card"></div>
        </div>

        <!-- Logs -->
        <div id="view-logs" class="view">
            <div class="log-controls">
                <button class="btn btn-outline" id="btn-log-pause" onclick="toggleLogPause()">暂停</button>
                <button class="btn btn-outline" onclick="clearLogs()">清屏</button>
                <span style="color:var(--text-light);font-size:12px;margin-left:8px;">过滤:</span>
                <button class="btn btn-outline btn-sm active" onclick="setLogFilter('all',this)">ALL</button>
                <button class="btn btn-outline btn-sm" onclick="setLogFilter('info',this)">INFO</button>
                <button class="btn btn-outline btn-sm" onclick="setLogFilter('warning',this)">WARN</button>
                <button class="btn btn-outline btn-sm" onclick="setLogFilter('error',this)">ERROR</button>
                <span id="log-count" style="color:var(--text-light);font-size:12px;margin-left:auto;"></span>
            </div>
            <div id="log-output" class="log-output"></div>
        </div>

        <!-- Groups -->
        <div id="view-groups" class="view">
            <div class="card">
                <div class="card-title">群聊列表</div>
                <table>
                    <thead><tr><th>群名</th><th>ID</th><th>启用</th><th>自动回复</th><th>延迟(秒)</th><th>操作</th></tr></thead>
                    <tbody id="groups-tbody"></tbody>
                </table>
            </div>
        </div>

        <!-- Settings -->
        <div id="view-settings" class="view">
            <div class="card" style="border-color:var(--warning);margin-bottom:16px;">
                <div class="card-title" style="color:var(--warning);">思考模型配置（首次使用必填）</div>
                <div style="display:flex;gap:8px;align-items:end;margin-bottom:12px;flex-wrap:wrap;">
                    <div class="form-group" style="flex:1;min-width:160px;margin:0;">
                        <label>已保存配置</label>
                        <select id="cfg-thinking-profiles" onchange="loadThinkingProfile(this.value)">
                            <option value="">-- 选择已保存配置 --</option>
                        </select>
                    </div>
                    <button class="btn btn-outline btn-sm" onclick="saveThinkingProfile()">保存当前</button>
                    <button class="btn btn-outline btn-sm" style="color:var(--danger)" onclick="deleteThinkingProfile()">删除</button>
                    <button class="btn btn-outline btn-sm" style="color:var(--primary)" onclick="activateThinkingProfile()">切换并生效</button>
                </div>
                <div class="settings-grid">
                    <div class="form-group"><label>提供商预设</label>
                        <select id="cfg-thinking-preset" onchange="applyThinkingPreset(this.value)">
                            <option value="">-- 选择预设 --</option>
                        </select>
                    </div>
                    <div class="form-group"><label>API Key</label><input type="password" id="cfg-thinking-key" placeholder="sk-..."></div>
                    <div class="form-group"><label>Base URL</label><input type="text" id="cfg-thinking-url" placeholder="https://api.openai.com/v1"></div>
                    <div class="form-group"><label>模型</label><input type="text" id="cfg-thinking-model" placeholder="gpt-4o"></div>
                </div>
                <div class="settings-actions">
                    <button class="btn btn-outline btn-sm" onclick="testThinkingProvider()">测试连接</button>
                    <button class="btn btn-success" onclick="saveApiKeys()">保存并生效</button>
                </div>
            </div>
            <div class="card" style="border-color:var(--info);margin-bottom:16px;">
                <div class="card-title" style="color:var(--info);">记忆系统模型配置</div>
                <div class="settings-grid">
                    <div class="form-group"><label>提供商预设</label>
                        <select id="cfg-memory-preset" onchange="applyMemoryPreset(this.value)">
                            <option value="">-- 选择预设 --</option>
                        </select>
                    </div>
                    <div class="form-group"><label>API Key</label><input type="password" id="cfg-memory-key" placeholder="sk-..."></div>
                    <div class="form-group"><label>Base URL</label><input type="text" id="cfg-memory-url" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"></div>
                    <div class="form-group"><label>模型</label><input type="text" id="cfg-memory-model" placeholder="qwen-turbo"></div>
                </div>
                <div class="settings-actions">
                    <button class="btn btn-success" onclick="saveApiKeys()">保存并生效</button>
                </div>
            </div>
            <div class="card" style="border-color:var(--success);margin-bottom:16px;">
                <div class="card-title" style="color:var(--success);">心跳服务</div>
                <div class="settings-grid">
                    <div class="form-group"><label>启用心跳</label>
                        <label class="toggle"><input type="checkbox" id="cfg-hb-enabled"><span class="toggle-slider"></span></label>
                    </div>
                    <div class="form-group"><label>心跳间隔（秒）</label><input type="number" id="cfg-hb-interval" min="10" max="3600" value="500"></div>
                    <div class="form-group"><label>后端地址</label><input type="text" id="cfg-hb-url" value="http://localhost:8000"></div>
                </div>
                <div class="settings-actions">
                    <button class="btn btn-success" onclick="saveHeartbeatConfig()">保存</button>
                </div>
            </div>
            <div class="card">
                <div class="card-title">上下文窗口</div>
                <div style="display:flex;align-items:center;gap:12px;">
                    <input type="number" id="ctx-window" min="1" max="100" style="width:80px;">
                    <button class="btn btn-primary btn-sm" onclick="saveContextWindow()">保存</button>
                </div>
            </div>
            <div class="card">
                <div class="card-title">API 提供者（备用列表）</div>
                <div style="margin-bottom:12px;"><button class="btn btn-primary btn-sm" onclick="showApiForm()">+ 添加</button></div>
                <table>
                    <thead><tr><th>名称</th><th>模型</th><th>Base URL</th><th>操作</th></tr></thead>
                    <tbody id="apis-tbody"></tbody>
                </table>
            </div>
            <div id="settings-container"></div>
        </div>

        <!-- Core -->
        <div id="view-core" class="view">
            <div class="core-section stable">
                <h4 style="color:var(--warning);">稳定层（只读）</h4>
                <pre id="core-stable">加载中...</pre>
            </div>
            <div class="core-section malleable">
                <h4 style="color:var(--success);">可塑层（可编辑）</h4>
                <textarea id="core-malleable" rows="10" style="width:100%;margin-top:8px;" placeholder="加载中..."></textarea>
                <div style="margin-top:8px;">
                    <button class="btn btn-success" onclick="saveMalleable()">保存可塑层</button>
                </div>
            </div>
        </div>

    </div>
</div>

<!-- API Form Modal -->
<div class="modal-overlay" id="api-modal">
    <div class="modal">
        <h3 id="api-modal-title">添加 API</h3>
        <input type="hidden" id="api-edit-name">
        <div class="form-group"><label>名称</label><input type="text" id="api-name" placeholder="如 deepseek"></div>
        <div class="form-row">
            <div class="form-group"><label>API Key</label><input type="password" id="api-key" placeholder="sk-..."></div>
            <div class="form-group"><label>Model</label><input type="text" id="api-model" placeholder="deepseek-chat"></div>
        </div>
        <div class="form-group"><label>Base URL</label><input type="text" id="api-url" placeholder="https://api.deepseek.com/v1"></div>
        <div class="modal-actions">
            <button class="btn btn-outline" onclick="closeModal('api-modal')">取消</button>
            <button class="btn btn-primary" onclick="saveApi()">保存</button>
        </div>
    </div>
</div>

<!-- Context Modal -->
<div class="modal-overlay" id="ctx-modal">
    <div class="modal" style="max-width:700px;">
        <h3 id="ctx-modal-title">对话上下文</h3>
        <div id="ctx-messages" style="max-height:50vh;overflow-y:auto;"></div>
        <div class="modal-actions">
            <button class="btn btn-danger btn-sm" onclick="clearCurrentContext()">清除上下文</button>
            <button class="btn btn-outline" onclick="closeModal('ctx-modal')">关闭</button>
        </div>
    </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
// ============================================================
// 全局状态
// ============================================================
let currentView = 'dashboard';
let logEventSource = null;
let logPaused = false;
let logFilter = 'all';
let logLineCount = 0;
let dashboardTimer = null;
let currentContextGroupId = null;

const TITLES = {
    dashboard:'仪表盘', logs:'日志', groups:'群聊',
    settings:'配置', core:'核心'
};

// ============================================================
// 工具函数
// ============================================================
function api(url, opts = {}) {
    return fetch(url, {
        headers: {'Content-Type':'application/json'},
        ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(r => r.json()).catch(e => ({error: e.message}));
}

function showToast(msg, type='success') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast ' + type + ' show';
    setTimeout(() => t.className = 'toast', 3000);
}

function closeModal(id) { document.getElementById(id).classList.remove('active'); }
function openModal(id) { document.getElementById(id).classList.add('active'); }

function barHtml(val, max=1, color='var(--primary)') {
    const pct = Math.min(100, Math.max(0, (val/max)*100));
    return `<div style="background:var(--bg);border-radius:3px;height:6px;overflow:hidden;display:inline-block;width:60px;vertical-align:middle;"><div style="background:${color};height:100%;width:${pct}%;"></div></div>`;
}

// ============================================================
// 视图切换
// ============================================================
function switchView(view) {
    // 离开日志视图时断开 SSE
    if (currentView === 'logs' && logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }
    // 离开仪表盘时停止刷新
    if (currentView === 'dashboard' && dashboardTimer) {
        clearInterval(dashboardTimer);
        dashboardTimer = null;
    }

    currentView = view;
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + view).classList.add('active');
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => {
        if (n.textContent.trim() === TITLES[view]) n.classList.add('active');
    });
    document.getElementById('page-title').textContent = TITLES[view];

    // 加载数据
    if (view === 'dashboard') loadDashboard();
    if (view === 'logs') startLogStream();
    if (view === 'groups') loadGroups();
    if (view === 'settings') { loadSettings(); loadApis(); }
    if (view === 'core') loadCore();
    if (view === 'core') loadCore();
}

// ============================================================
// 仪表盘
// ============================================================
async function loadDashboard() {
    // 并行请求
    const [health, memHealth, state, stats, modelCfg, memStatus] = await Promise.all([
        api('/proxy/health'),
        api('/proxy/memory-health'),
        api('/proxy/state'),
        api('/proxy/stats'),
        api('/proxy/model-config'),
        api('/proxy/memory-status'),
    ]);

    // 健康状态
    let hb = '';
    const bhOk = !health.error && health.status === 'healthy';
    hb += `<span class="health-badge ${bhOk?'ok':'err'}"><span class="health-dot ${bhOk?'ok':'err'}"></span>Backend ${bhOk?'正常':'离线'}</span>`;
    const mhOk = !memHealth.error && memHealth.status === 'healthy';
    hb += `<span class="health-badge ${mhOk?'ok':'err'}"><span class="health-dot ${mhOk?'ok':'err'}"></span>Memory ${mhOk?'正常':'离线'}</span>`;
    document.getElementById('health-bar').innerHTML = hb;

    // AI 状态
    if (!state.error) {
        const stateData = [
            {icon:'\u{1F319}', label:'心情', value: state.mood_label||'平静', extra:`效价:${(state.mood_valence||0).toFixed(2)} 唤醒:${(state.mood_arousal||0).toFixed(2)}`, color:'#FF9800'},
            {icon:'\u26A1', label:'精力', value: state.energy_label||'正常', extra:`${(state.energy_value||0).toFixed(2)}`, color:'#4CAF50'},
            {icon:'\u{1F3AF}', label:'注意力', value: state.focus||'无', extra:'', color:'#2196F3'},
            {icon:'\u{1F4AA}', label:'信心', value: state.confidence_label||'正常', extra:`${(state.confidence_value||0).toFixed(2)}`, color:'#9C27B0'},
        ];
        let sh = '';
        for (const s of stateData) {
            sh += `<div class="stat-card"><div class="icon">${s.icon}</div><div class="value" style="color:${s.color}">${s.value}</div><div class="label">${s.label}</div><div class="extra">${s.extra}</div></div>`;
        }
        document.getElementById('state-cards').innerHTML = sh;
    }

    // 统计
    if (!stats.error && stats.data) {
        const d = stats.data;
        const items = [
            {icon:'\u{1F465}', label:'用户', value:d.user_count||0, color:'var(--info)'},
            {icon:'\u{1F4AC}', label:'群聊', value:d.group_count||0, color:'var(--success)'},
            {icon:'\u{1F4E8}', label:'消息', value:d.message_count||0, color:'var(--warning)'},
            {icon:'\u{1F9E0}', label:'API', value:d.api_count||0, color:'var(--primary)'},
        ];
        let sg = '';
        for (const i of items) {
            sg += `<div class="stat-card"><div class="icon">${i.icon}</div><div class="value" style="color:${i.color}">${i.value}</div><div class="label">${i.label}</div></div>`;
        }
        document.getElementById('stats-grid').innerHTML = sg;
    }

    // 模型
    if (!modelCfg.error) {
        let mh = '';
        const tp = modelCfg.thinking_provider;
        mh += `<div class="model-card"><h4>LLM 模型</h4>${tp ? `<div class="info">Model: <span>${tp.model||'-'}</span></div><div class="info">URL: <span>${tp.base_url||'-'}</span></div><div class="info">Key: <span>${tp.api_key||'-'}</span></div>` : '<div class="info">未配置</div>'}</div>`;
        document.getElementById('model-cards').innerHTML = mh;
    }

    // Memory 状态
    if (!memStatus.error) {
        document.getElementById('memory-status').innerHTML = `<div class="card-title">Memory 系统状态</div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:13px;">
            <div>体验: <strong>${memStatus.total_experiences||0}</strong></div>
            <div>已巩固: <strong>${memStatus.consolidated_count||0}</strong></div>
            <div>未巩固: <strong>${memStatus.unconsolidated_count||0}</strong></div>
            <div>实体: <strong>${memStatus.total_entities||0}</strong></div>
            <div>边: <strong>${memStatus.total_edges||0}</strong></div>
            <div>向量: <strong>${memStatus.vector_store_size||0}</strong></div>
            <div>健康: <strong style="color:${memStatus.system_health==='healthy'?'var(--success)':'var(--danger)'}">${memStatus.system_health||'-'}</strong></div>
            <div>上次巩固: <span style="color:var(--text-light)">${memStatus.last_consolidation||'无'}</span></div>
        </div>`;
    }

    // 自动刷新
    if (!dashboardTimer) {
        dashboardTimer = setInterval(loadDashboard, 30000);
    }
}

// ============================================================
// 日志
// ============================================================
function startLogStream() {
    if (logEventSource) return;
    const output = document.getElementById('log-output');
    logEventSource = new EventSource('/proxy/logs/stream');
    logEventSource.onmessage = function(e) {
        if (logPaused) return;
        appendLog(e.data);
    };
    logEventSource.onerror = function() {
        appendLogRaw('[连接断开，正在重连...]', 'error');
    };
}

function appendLog(raw) {
    // 尝试解析为 JSON
    try {
        const obj = JSON.parse(raw);
        const level = (obj.level || 'info').toLowerCase();
        const msg = obj.message || obj.msg || raw;
        const ts = obj.created || obj.asctime || '';
        const name = obj.name || '';
        appendLogRaw(`${ts} ${level.toUpperCase().padEnd(7)} ${name}: ${msg}`, level);
    } catch {
        // 纯文本
        let level = 'info';
        const lower = raw.toLowerCase();
        if (lower.includes('error') || lower.includes('exception')) level = 'error';
        else if (lower.includes('warn')) level = 'warning';
        appendLogRaw(raw, level);
    }
}

function appendLogRaw(text, level) {
    const output = document.getElementById('log-output');
    const line = document.createElement('div');
    line.className = 'log-line ' + level;
    if (logFilter !== 'all' && logFilter !== level) line.classList.add('hidden');
    line.textContent = text;
    output.appendChild(line);
    logLineCount++;
    // 限制行数
    while (output.children.length > 1000) output.removeChild(output.firstChild);
    logLineCount = output.children.length;
    // 自动滚动
    if (output.scrollTop + output.clientHeight >= output.scrollHeight - 50) {
        output.scrollTop = output.scrollHeight;
    }
    document.getElementById('log-count').textContent = logLineCount + ' 行';
}

function toggleLogPause() {
    logPaused = !logPaused;
    document.getElementById('btn-log-pause').textContent = logPaused ? '恢复' : '暂停';
}

function clearLogs() {
    document.getElementById('log-output').innerHTML = '';
    logLineCount = 0;
    document.getElementById('log-count').textContent = '';
}

function setLogFilter(filter, btn) {
    logFilter = filter;
    document.querySelectorAll('.log-controls .btn-sm').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const output = document.getElementById('log-output');
    for (const line of output.children) {
        if (filter === 'all') {
            line.classList.remove('hidden');
        } else {
            line.classList.toggle('hidden', !line.classList.contains(filter));
        }
    }
}

// ============================================================
// 群聊管理
// ============================================================
async function loadGroups() {
    const res = await api('/proxy/groups');
    const tbody = document.getElementById('groups-tbody');
    if (res.error || !res.data) {
        tbody.innerHTML = `<tr><td colspan="6" style="color:var(--danger)">${res.error || '加载失败'}</td></tr>`;
        return;
    }
    let html = '';
    for (const g of res.data) {
        const name = g.group_name || g.group_id;
        html += `<tr>
            <td>${name}</td>
            <td style="font-size:11px;color:var(--text-light)">${g.group_id}</td>
            <td><label class="toggle"><input type="checkbox" ${g.enabled?'checked':''} onchange="toggleGroup('${g.group_id}',this.checked)"><span class="toggle-slider"></span></label></td>
            <td><label class="toggle"><input type="checkbox" ${g.auto_reply_enabled?'checked':''} onchange="toggleAutoReply('${g.group_id}',this.checked)"><span class="toggle-slider"></span></label></td>
            <td><input type="number" value="${g.reply_delay_seconds}" min="1" max="60" style="width:60px;font-size:12px;" onchange="setDelay('${g.group_id}',this.value)"></td>
            <td><button class="btn btn-outline btn-sm" onclick="viewContext('${g.group_id}','${name}')">上下文</button></td>
        </tr>`;
    }
    tbody.innerHTML = html || '<tr><td colspan="6" style="color:var(--text-light)">暂无群聊</td></tr>';
}

async function toggleGroup(id, enabled) {
    const res = await api('/proxy/groups/' + id + '/toggle', {method:'POST', body:{enabled}});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
}

async function toggleAutoReply(id, enabled) {
    const res = await api('/proxy/groups/' + id + '/auto-reply', {method:'POST', body:{enabled}});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
}

async function setDelay(id, seconds) {
    const res = await api('/proxy/groups/' + id + '/delay', {method:'POST', body:{delay_seconds: parseInt(seconds)}});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
}

async function viewContext(groupId, groupName) {
    currentContextGroupId = groupId;
    document.getElementById('ctx-modal-title').textContent = '对话上下文 - ' + (groupName || groupId);
    const res = await api('/proxy/groups/' + groupId + '/context');
    const container = document.getElementById('ctx-messages');
    if (res.error || !res.data) {
        container.innerHTML = `<div style="color:var(--text-light);padding:12px;">${res.error || '无上下文'}</div>`;
        openModal('ctx-modal');
        return;
    }
    let html = '';
    for (const m of res.data) {
        const role = m.role || 'user';
        html += `<div class="ctx-msg ${role}"><div class="role">${role === 'user' ? (m.sender_nickname || m.user_id) : 'AI'}</div><div class="content">${escHtml(m.content||'')}</div></div>`;
    }
    container.innerHTML = html || '<div style="color:var(--text-light);padding:12px;">暂无消息</div>';
    openModal('ctx-modal');
}

async function clearCurrentContext() {
    if (!currentContextGroupId) return;
    if (!confirm('确认清除该群的对话上下文？')) return;
    const res = await api('/proxy/groups/' + currentContextGroupId + '/context', {method:'DELETE'});
    showToast(res.message || '已清除', res.error ? 'error' : 'success');
    closeModal('ctx-modal');
}

function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ============================================================
// API 提供者列表 & 上下文窗口
// ============================================================
async function loadApis() {
    const configs = await api('/proxy/configs');
    if (!configs.error) {
        document.getElementById('ctx-window').value = configs.context_window || 10;
    }
    if (!configs.error && configs.api_config) {
        const apis = configs.api_config.apis || {};
        const current = configs.api_config.current_api || '';
        let ah = '';
        for (const [name, cfg] of Object.entries(apis)) {
            const isCurrent = name === current;
            ah += `<tr>
                <td>${name} ${isCurrent ? '<span style="color:var(--success);font-size:11px;">[当前]</span>' : ''}</td>
                <td style="font-size:12px;">${cfg.model||'-'}</td>
                <td style="font-size:11px;color:var(--text-light);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${cfg.base_url||'-'}</td>
                <td>
                    ${!isCurrent ? `<button class="btn btn-outline btn-sm" onclick="switchApi('${name}')">切换</button>` : ''}
                    <button class="btn btn-outline btn-sm" onclick="testApi('${name}')">测试</button>
                    <button class="btn btn-outline btn-sm" onclick="editApi('${name}')">编辑</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteApi('${name}')">删除</button>
                </td>
            </tr>`;
        }
        document.getElementById('apis-tbody').innerHTML = ah || '<tr><td colspan="4" style="color:var(--text-light)">暂无 API 配置</td></tr>';
    }
}

function showApiForm() {
    document.getElementById('api-modal-title').textContent = '添加 API';
    document.getElementById('api-edit-name').value = '';
    document.getElementById('api-name').value = '';
    document.getElementById('api-name').disabled = false;
    document.getElementById('api-key').value = '';
    document.getElementById('api-model').value = '';
    document.getElementById('api-url').value = '';
    openModal('api-modal');
}

function editApi(name) {
    document.getElementById('api-modal-title').textContent = '编辑 API - ' + name;
    document.getElementById('api-edit-name').value = name;
    document.getElementById('api-name').value = name;
    document.getElementById('api-name').disabled = true;
    document.getElementById('api-key').value = '';
    document.getElementById('api-model').value = '';
    document.getElementById('api-url').value = '';
    openModal('api-modal');
}

async function saveApi() {
    const editName = document.getElementById('api-edit-name').value;
    const name = document.getElementById('api-name').value.trim();
    const apiKey = document.getElementById('api-key').value.trim();
    const model = document.getElementById('api-model').value.trim();
    const baseUrl = document.getElementById('api-url').value.trim();

    if (!name || !model || !baseUrl) {
        showToast('请填写完整信息', 'error');
        return;
    }

    const isEdit = editName && !editName.startsWith('__');
    const url = isEdit ? '/proxy/apis/' + editName : '/proxy/apis';
    const method = isEdit ? 'PUT' : 'POST';
    const res = await api(url, {method, body:{name, api_key: apiKey, base_url: baseUrl, model}});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
    if (!res.error) {
        closeModal('api-modal');
        loadApis();
    }
}

async function deleteApi(name) {
    if (!confirm('确认删除 API: ' + name + '？')) return;
    const res = await api('/proxy/apis/' + name, {method:'DELETE'});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
    loadApis();
}

async function switchApi(name) {
    const res = await api('/proxy/apis/switch/' + name, {method:'POST'});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
    loadApis();
}

async function testApi(name) {
    showToast('正在测试 ' + name + ' ...');
    const res = await api('/proxy/apis/' + name + '/test', {method:'POST'});
    showToast(res.message || (res.error || '测试完成'), res.error ? 'error' : 'success');
}

async function saveContextWindow() {
    const size = parseInt(document.getElementById('ctx-window').value);
    if (isNaN(size) || size < 1 || size > 100) {
        showToast('大小必须在 1-100 之间', 'error');
        return;
    }
    const res = await api('/proxy/context-window', {method:'POST', body:{size}});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
}

// ============================================================
// 核心身份
// ============================================================
async function loadCore() {
    const res = await api('/proxy/core/identity');
    if (!res.error) {
        document.getElementById('core-stable').textContent = res.stable_text || '（空）';
        document.getElementById('core-malleable').value = res.malleable_yaml || '';
    } else {
        document.getElementById('core-stable').textContent = '加载失败: ' + res.error;
    }
}

async function saveMalleable() {
    if (!confirm('确认保存可塑层？这将修改 AI 的核心人设。')) return;
    const yaml = document.getElementById('core-malleable').value;
    const res = await api('/proxy/core/malleable', {method:'POST', body:{malleable_yaml: yaml, reason:'Web 前端编辑'}});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
}

// ============================================================
// 通用配置
// ============================================================
const SETTINGS_META = {
    brain: {
        label: '大脑', icon: '\u{1F9E0}',
        fields: {
            max_iterations: {label:'最大迭代轮次', type:'int', min:1, max:20},
            context_limit: {label:'上下文条数', type:'int', min:1, max:100},
            context_time_window: {label:'上下文时间窗口(分)', type:'int', min:1},
            gap_threshold: {label:'对话间隔阈值(秒)', type:'int', min:0},
            interim_max_length: {label:'中间消息最大长度', type:'int', min:1, max:200},
            state_api_timeout: {label:'状态API超时(秒)', type:'float', min:0.1},
            proactive_context_limit: {label:'主动发言上下文数', type:'int', min:1},
            proactive_context_time_window: {label:'主动发言时间窗口(分)', type:'float', min:0.1},
            proactive_speak_cooldown: {label:'主动发言冷却(秒)', type:'int', min:0},
            proactive_speak_max_per_hour: {label:'每小时主动发言上限', type:'int', min:0},
            mention_priority: {label:'@消息优先级', type:'int', min:1},
            significant_length: {label:'重要消息长度阈值', type:'int', min:1},
            stm_importance_user_mention: {label:'@消息记忆权重(0-1)', type:'float', min:0, max:1, step:0.1},
            stm_importance_significant_msg: {label:'长消息/提问记忆权重(0-1)', type:'float', min:0, max:1, step:0.1},
            stm_importance_private_chat: {label:'私聊记忆权重(0-1)', type:'float', min:0, max:1, step:0.1},
        }
    },
    sleep: {
        label: '睡眠', icon: '\u{1F634}',
        fields: {
            enabled: {label:'启用睡眠', type:'bool'},
            wind_down_hour: {label:'困倦时段(时)', type:'int', min:0, max:23},
            sleep_hour: {label:'睡眠时间(时)', type:'int', min:0, max:23},
            wake_hour: {label:'起床时间(时)', type:'int', min:0, max:23},
            awake_energy_value: {label:'清醒精力值', type:'float', min:0, max:1, step:0.1},
            awake_energy_label: {label:'清醒精力标签', type:'str'},
            tired_energy_value: {label:'困倦精力值', type:'float', min:0, max:1, step:0.1},
            tired_energy_label: {label:'困倦精力标签', type:'str'},
            check_interval: {label:'检查间隔(秒)', type:'int', min:10},
        }
    },
    memory: {
        label: '记忆', icon: '\u{1F4BE}',
        fields: {
            service_url: {label:'记忆服务地址', type:'str'},
            provider_connect_timeout: {label:'连接超时(秒)', type:'float', min:0.1},
            provider_read_timeout: {label:'读取超时(秒)', type:'float', min:0.1},
            provider_write_timeout: {label:'写入超时(秒)', type:'float', min:0.1},
            provider_pool_timeout: {label:'连接池超时(秒)', type:'float', min:0.1},
            stm_connect_timeout: {label:'STM连接超时(秒)', type:'float', min:0.1},
            stm_read_timeout: {label:'STM读取超时(秒)', type:'float', min:0.1},
            stm_write_timeout: {label:'STM写入超时(秒)', type:'float', min:0.1},
            stm_pool_timeout: {label:'STM池超时(秒)', type:'float', min:0.1},
            profile_ensure_timeout: {label:'档案超时(秒)', type:'float', min:0.1},
            profile_turn_threshold: {label:'档案对话轮次阈值', type:'int', min:1},
        }
    },
    napcat: {
        label: 'NapCat (QQ)', icon: '\u{1F4AC}',
        fields: {
            http_url: {label:'NapCat HTTP 地址', type:'str'},
            timeout: {label:'请求超时(秒)', type:'float', min:1},
        }
    },
    admin: {
        label: '管理员', icon: '\u{1F464}',
        fields: {
            qq_id: {label:'管理员 QQ 号', type:'str'},
            cooldown_seconds: {label:'通知冷却(秒)', type:'int', min:0},
        }
    },
    vision: {
        label: '视觉', icon: '\u{1F441}',
        fields: {
            enabled: {label:'启用视觉', type:'bool'},
            provider: {label:'服务商', type:'str'},
            model: {label:'模型', type:'str'},
            api_key: {label:'API Key', type:'password'},
            base_url: {label:'Base URL', type:'str'},
            max_retries: {label:'最大重试', type:'int', min:0},
            timeout: {label:'超时(秒)', type:'int', min:1},
            image_download_timeout: {label:'图片下载超时(秒)', type:'float', min:1},
        }
    },
    context: {
        label: '上下文', icon: '\u{1F4D1}',
        fields: {
            group_context_limit: {label:'群上下文条数', type:'int', min:1, max:200},
            group_context_time_window: {label:'群上下文时间窗口(分)', type:'int', min:1},
            memory_recall_limit: {label:'记忆召回条数', type:'int', min:1, max:20},
        }
    },
    llm: {
        label: 'LLM', icon: '\u{1F916}',
        fields: {
            anthropic_max_tokens: {label:'Anthropic 最大 token', type:'int', min:1},
            api_timeout: {label:'API 超时(秒)', type:'float', min:1},
        }
    },
    server: {
        label: '服务', icon: '\u{1F5A5}', restart: true,
        fields: {
            host: {label:'监听地址', type:'str'},
            port: {label:'端口', type:'int', min:1, max:65535},
            log_level: {label:'日志级别', type:'select', options:['debug','info','warning','error']},
            reload: {label:'热重载', type:'bool'},
            sse_heartbeat_timeout: {label:'SSE 心跳超时(秒)', type:'float', min:0.1},
        }
    },
};

// LLM 提供商预设
const PROVIDER_PRESETS = {
    openai:       { name: 'OpenAI',       base_url: 'https://api.openai.com/v1',                               model: 'gpt-4o' },
    deepseek:     { name: 'DeepSeek',     base_url: 'https://api.deepseek.com',                                 model: 'deepseek-chat' },
    anthropic:    { name: 'Anthropic',    base_url: 'https://api.anthropic.com',                                model: 'claude-sonnet-4-20250514' },
    qwen:         { name: '通义千问',      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',       model: 'qwen-turbo' },
    zhipu:        { name: '智谱 ChatGLM',  base_url: 'https://open.bigmodel.cn/api/paas/v4',                    model: 'glm-4-flash' },
    moonshot:     { name: 'Moonshot',     base_url: 'https://api.moonshot.cn/v1',                               model: 'moonshot-v1-8k' },
    minimax:      { name: 'MiniMax',      base_url: 'https://api.minimax.chat/v1',                              model: 'MiniMax-Text-01' },
    doubao:       { name: '火山引擎 豆包', base_url: 'https://ark.cn-beijing.volces.com/api/v3',                 model: 'doubao-pro-32k' },
    siliconflow:  { name: 'SiliconFlow',  base_url: 'https://api.siliconflow.cn/v1',                            model: 'Qwen/Qwen2.5-7B-Instruct' },
    ollama:       { name: 'Ollama (本地)', base_url: 'http://localhost:11434/v1',                                model: 'qwen3:8b' },
    custom:       { name: '自定义',        base_url: '',                                                         model: '' },
};

function populatePresetSelects() {
    const opts = Object.entries(PROVIDER_PRESETS).map(([k, v]) =>
        `<option value="${k}">${v.name}${v.model ? ' (' + v.model + ')' : ''}</option>`
    ).join('');
    document.getElementById('cfg-thinking-preset').innerHTML = '<option value="">-- 选择预设 --</option>' + opts;
    document.getElementById('cfg-memory-preset').innerHTML = '<option value="">-- 选择预设 --</option>' + opts;
}

function applyThinkingPreset(key) {
    const p = PROVIDER_PRESETS[key];
    if (!p) return;
    if (p.base_url) document.getElementById('cfg-thinking-url').value = p.base_url;
    if (p.model) document.getElementById('cfg-thinking-model').value = p.model;
}

function applyMemoryPreset(key) {
    const p = PROVIDER_PRESETS[key];
    if (!p) return;
    if (p.base_url) document.getElementById('cfg-memory-url').value = p.base_url;
    if (p.model) document.getElementById('cfg-memory-model').value = p.model;
}

function detectPresetByUrl(url) {
    if (!url) return '';
    const u = url.toLowerCase();
    if (u.includes('api.openai.com')) return 'openai';
    if (u.includes('api.deepseek.com')) return 'deepseek';
    if (u.includes('anthropic.com')) return 'anthropic';
    if (u.includes('dashscope') || u.includes('aliyuncs')) return 'qwen';
    if (u.includes('bigmodel.cn')) return 'zhipu';
    if (u.includes('moonshot.cn') || u.includes('kimi')) return 'moonshot';
    if (u.includes('minimax.chat')) return 'minimax';
    if (u.includes('volces.com')) return 'doubao';
    if (u.includes('siliconflow.cn')) return 'siliconflow';
    if (u.includes('11434') || u.includes('ollama')) return 'ollama';
    if (u.includes('localhost') || u.includes('127.0.0.1')) return 'ollama';
    return '';
}

// ============================================================
// 思考模型 Profiles 管理
// ============================================================

let _thinkingProfiles = {};

async function loadThinkingProfiles() {
    const r = await api('/proxy/thinking-profiles');
    if (r.error || !r.profiles) return;
    _thinkingProfiles = r.profiles;
    const sel = document.getElementById('cfg-thinking-profiles');
    sel.innerHTML = '<option value="">-- 选择已保存配置 --</option>';
    for (const [name, cfg] of Object.entries(r.profiles)) {
        sel.innerHTML += `<option value="${name}">${name} (${cfg.model})</option>`;
    }
}

function loadThinkingProfile(name) {
    if (!name || !_thinkingProfiles[name]) return;
    const cfg = _thinkingProfiles[name];
    document.getElementById('cfg-thinking-url').value = cfg.base_url || '';
    document.getElementById('cfg-thinking-model').value = cfg.model || '';
    // API Key 不从 profile 回填（脱敏的），让用户看到星号提示
    const keyInput = document.getElementById('cfg-thinking-key');
    if (cfg.api_key) keyInput.value = cfg.api_key;
    const detected = detectPresetByUrl(cfg.base_url);
    if (detected) document.getElementById('cfg-thinking-preset').value = detected;
    else document.getElementById('cfg-thinking-preset').value = '';
}

async function saveThinkingProfile() {
    const name = prompt('为当前配置命名（英文/数字，如 deepseek-prod）:');
    if (!name || !name.trim()) return;
    const tk = document.getElementById('cfg-thinking-key').value.trim();
    const tu = document.getElementById('cfg-thinking-url').value.trim();
    const tm = document.getElementById('cfg-thinking-model').value.trim();
    if (!tu || !tm) { showToast('请先填写 Base URL 和模型', 'error'); return; }
    const r = await api('/proxy/thinking-profiles', {
        method: 'POST',
        body: { name: name.trim(), api_key: tk, base_url: tu, model: tm },
    });
    if (r.error) { showToast(r.error, 'error'); return; }
    showToast(r.message || '已保存');
    await loadThinkingProfiles();
    document.getElementById('cfg-thinking-profiles').value = name.trim();
}

async function deleteThinkingProfile() {
    const name = document.getElementById('cfg-thinking-profiles').value;
    if (!name) { showToast('请先选择一个配置', 'error'); return; }
    if (!confirm(`确定删除配置 "${name}"？`)) return;
    const r = await api(`/proxy/thinking-profiles/${name}`, { method: 'DELETE' });
    if (r.error) { showToast(r.error, 'error'); return; }
    showToast(r.message || '已删除');
    document.getElementById('cfg-thinking-profiles').value = '';
    await loadThinkingProfiles();
}

async function activateThinkingProfile() {
    const name = document.getElementById('cfg-thinking-profiles').value;
    if (!name) { showToast('请先选择一个配置', 'error'); return; }
    showToast('正在切换...');
    const r = await api(`/proxy/thinking-profiles/${name}/activate`, { method: 'POST' });
    if (r.error) { showToast(r.error, 'error'); return; }
    showToast(r.message || '切换成功');
    // 刷新显示
    const mc = await api('/proxy/model-config');
    if (!mc.error && mc.thinking_provider) {
        const tp = mc.thinking_provider;
        document.getElementById('cfg-thinking-url').value = tp.base_url || '';
        document.getElementById('cfg-thinking-model').value = tp.model || '';
        document.getElementById('cfg-thinking-key').value = tp.api_key || '';
    }
}

async function testThinkingProvider() {
    const tk = document.getElementById('cfg-thinking-key').value.trim();
    const tu = document.getElementById('cfg-thinking-url').value.trim();
    const tm = document.getElementById('cfg-thinking-model').value.trim();
    if (!tk || !tu || !tm) { showToast('请先填写完整的 API Key、Base URL 和模型', 'error'); return; }
    showToast('正在测试连接...');
    const r = await api('/proxy/thinking-provider/test', {method:'POST', body:{api_key:tk,base_url:tu,model:tm}});
    if (r.success) showToast('连接测试成功');
    else showToast('连接失败: ' + (r.message||'未知错误'), 'error');
}

let settingsData = {};

async function loadHeartbeatConfig() {
    const cfg = await api('/proxy/heartbeat-config');
    if (cfg.error) return;
    document.getElementById('cfg-hb-enabled').checked = cfg.running || cfg.enabled || false;
    document.getElementById('cfg-hb-interval').value = cfg.interval || 10;
    document.getElementById('cfg-hb-url').value = cfg.backend_url || 'http://localhost:8000';
}

async function saveHeartbeatConfig() {
    const body = {
        enabled: document.getElementById('cfg-hb-enabled').checked,
        interval: parseInt(document.getElementById('cfg-hb-interval').value) || 10,
        backend_url: document.getElementById('cfg-hb-url').value.trim(),
    };
    const r = await api('/proxy/heartbeat-config', {method:'POST', body});
    showToast(r.message || (r.error || '心跳配置已保存并生效'), r.error ? 'error' : 'success');
}

async function loadSettings() {
    populatePresetSelects();
    loadHeartbeatConfig();
    loadThinkingProfiles();

    // 加载模型配置（不依赖 settings API）
    const [modelCfg, memCfg, res] = await Promise.all([
        api('/proxy/model-config'),
        api('/proxy/memory-llm-config'),
        api('/proxy/settings'),
    ]);

    // 填充思考模型
    if (!modelCfg.error && modelCfg.thinking_provider) {
        const tp = modelCfg.thinking_provider;
        if (tp.base_url) document.getElementById('cfg-thinking-url').value = tp.base_url;
        if (tp.model) document.getElementById('cfg-thinking-model').value = tp.model;
        const detected = detectPresetByUrl(tp.base_url);
        if (detected) document.getElementById('cfg-thinking-preset').value = detected;
    }

    // 填充记忆系统模型
    if (!memCfg.error) {
        if (memCfg.base_url) document.getElementById('cfg-memory-url').value = memCfg.base_url;
        if (memCfg.model) document.getElementById('cfg-memory-model').value = memCfg.model;
        const memDetected = detectPresetByUrl(memCfg.base_url);
        if (memDetected) document.getElementById('cfg-memory-preset').value = memDetected;
    }

    // 渲染 settings 区域
    if (res.error || !res.data) {
        document.getElementById('settings-container').innerHTML = '<div style="color:var(--danger)">加载失败: ' + (res.error || '未知错误') + '</div>';
    } else {
        settingsData = res.data;
        renderSettings();
    }
}

async function saveApiKeys() {
    const tk = document.getElementById('cfg-thinking-key').value.trim();
    const tu = document.getElementById('cfg-thinking-url').value.trim();
    const tm = document.getElementById('cfg-thinking-model').value.trim();
    const mk = document.getElementById('cfg-memory-key').value.trim();
    const mu = document.getElementById('cfg-memory-url').value.trim();

    let anyOk = true;

    if (tk || tu || tm) {
        const body = {base_url: tu, model: tm};
        if (tk) body.api_key = tk;
        const r = await api('/proxy/thinking-provider', {method:'PUT', body});
        if (r.error) { showToast('LLM: ' + r.error, 'error'); anyOk = false; }
    }
    if (mk || mu) {
        const mm = document.getElementById('cfg-memory-model').value.trim();
        const mp = document.getElementById('cfg-memory-preset').value;
        const body = {};
        if (mk) body.api_key = mk;
        if (mu) body.base_url = mu;
        if (mm) body.model = mm;
        if (mp === 'qwen') body.provider = 'qwen';
        else if (mp === 'deepseek') body.provider = 'deepseek';
        else if (mp) body.provider = 'openai_compatible';
        const r = await api('/proxy/memory-llm-config', {method:'POST', body});
        if (r.error) { showToast('记忆系统: ' + r.error, 'error'); anyOk = false; }
    }

    if (anyOk) showToast('API 配置已保存并生效');
}

function renderSettings() {
    const container = document.getElementById('settings-container');
    let html = '';
    for (const [section, meta] of Object.entries(SETTINGS_META)) {
        const data = settingsData[section] || {};
        const isRestart = meta.restart || false;
        html += `<div class="settings-section">
            <div class="settings-header" onclick="toggleSettingsSection(this)">
                <h4>${meta.icon} ${meta.label} <span class="badge ${isRestart ? 'restart' : 'live'}">${isRestart ? '需重启' : '实时生效'}</span></h4>
                <span class="arrow" style="transition:transform .2s">&#9660;</span>
            </div>
            <div class="settings-body">
                <div class="settings-grid">`;
        for (const [key, field] of Object.entries(meta.fields)) {
            const val = data[key] !== undefined ? data[key] : '';
            html += `<div class="form-group"><label>${field.label}</label>`;
            if (field.type === 'bool') {
                html += `<label class="toggle"><input type="checkbox" data-section="${section}" data-key="${key}" ${val ? 'checked' : ''}><span class="toggle-slider"></span></label>`;
            } else if (field.type === 'select') {
                html += `<select data-section="${section}" data-key="${key}">`;
                for (const opt of field.options) {
                    html += `<option value="${opt}" ${val === opt ? 'selected' : ''}>${opt}</option>`;
                }
                html += `</select>`;
            } else if (field.type === 'password') {
                html += `<input type="password" data-section="${section}" data-key="${key}" value="${escHtml(String(val))}" placeholder="不修改请留空">`;
            } else {
                const inputType = field.type === 'int' || field.type === 'float' ? 'number' : 'text';
                const step = field.step || (field.type === 'float' ? '0.1' : undefined);
                html += `<input type="${inputType}" data-section="${section}" data-key="${key}" value="${escHtml(String(val))}"${field.min !== undefined ? ' min="' + field.min + '"' : ''}${field.max !== undefined ? ' max="' + field.max + '"' : ''}${step ? ' step="' + step + '"' : ''}>`;
            }
            html += `</div>`;
        }
        html += `</div>
                <div class="settings-actions">
                    <button class="btn btn-primary btn-sm" onclick="saveSettings('${section}')">保存 ${meta.label}</button>
                </div>
            </div>
        </div>`;
    }
    container.innerHTML = html;
}

function toggleSettingsSection(header) {
    const body = header.nextElementSibling;
    const arrow = header.querySelector('.arrow');
    body.classList.toggle('collapsed');
    arrow.style.transform = body.classList.contains('collapsed') ? 'rotate(-90deg)' : '';
}

async function saveSettings(section) {
    const meta = SETTINGS_META[section];
    const data = {};
    const inputs = document.querySelectorAll(`[data-section="${section}"]`);
    for (const el of inputs) {
        const key = el.dataset.key;
        const field = meta.fields[key];
        if (!field) continue;
        if (field.type === 'bool') {
            data[key] = el.checked;
        } else if (field.type === 'int') {
            data[key] = parseInt(el.value);
        } else if (field.type === 'float') {
            data[key] = parseFloat(el.value);
        } else {
            data[key] = el.value;
        }
    }
    const res = await api('/proxy/settings/' + section, {method:'PUT', body: data});
    showToast(res.message || (res.error || '操作完成'), res.error ? 'error' : 'success');
}

// ============================================================
// 启动
// ============================================================
switchView('dashboard');
</script>
</body>
</html>
"""


# ============================================================
# 入口
# ============================================================

def main():
    print("=" * 60)
    print("千雪 - 后台管理前端")
    print("=" * 60)
    print()
    print("  访问地址: http://localhost:5002")
    print()
    print("  视图:")
    print("    - 仪表盘: 系统概览和AI状态")
    print("    - 日志:   实时日志查看")
    print("    - 群聊:   QQ群管理")
    print("    - 模型:   LLM模型配置")
    print("    - 提示词: 系统提示词编辑")
    print("    - 核心:   身份核心层")
    print()
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5002, debug=False)


if __name__ == '__main__':
    main()
