#!/usr/bin/env python3
"""记忆系统查询前端

提供 Web 界面浏览和查询记忆库中的所有数据。
包括：仪表盘、体验浏览、实体浏览、关系网络、AI状态、人物档案。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import requests as http_requests
from flask import Flask, jsonify, render_template_string, request

from Memory.storage.database import db_manager
from Memory.storage.experience_store import experience_store
from Memory.storage.entity_store import entity_store
from Memory.storage.experience_edge_store import experience_edge_store
from Memory.storage.entity_edge_store import entity_edge_store
from Memory.storage.cross_edge_store import cross_edge_store
from Memory.storage.state_store import state_store
from Memory.config.settings import settings
from Memory.storage.profile_store import profile_store

app = Flask(__name__)


# ============================================================
# 序列化辅助函数
# ============================================================

def _exp_summary(exp):
    """体验摘要（列表用）"""
    return {
        'id': exp.id,
        'L0_text': (exp.L0_text or '')[:80] + ('...' if len(exp.L0_text or '') > 80 else ''),
        'importance': exp.importance,
        'emotion_category': exp.emotion_category,
        'emotion_intensity': exp.emotion_intensity,
        'consolidated': exp.consolidated,
        'source_type': exp.source_type,
        'created_at': exp.created_at,
    }


def _exp_full(exp):
    """体验完整详情"""
    return {
        'id': exp.id,
        'L0_text': exp.L0_text,
        'L1_text': exp.L1_text,
        'L2_text': exp.L2_text,
        'L3_raw': exp.L3_raw,
        'emotion_category': exp.emotion_category,
        'emotion_intensity': exp.emotion_intensity,
        'emotion_valence': exp.emotion_valence,
        'emotion_arousal': exp.emotion_arousal,
        'emotion_target': exp.emotion_target,
        'context_focus': exp.context_focus,
        'context_mood': exp.context_mood,
        'context_time_of_day': exp.context_time_of_day,
        'context_silence_before': exp.context_silence_before,
        'context_task': exp.context_task,
        'context_extra': exp.context_extra,
        'importance': exp.importance,
        'twist_level': exp.twist_level,
        'consolidated': exp.consolidated,
        'L0_decayed': exp.L0_decayed,
        'L1_decayed': exp.L1_decayed,
        'L2_decayed': exp.L2_decayed,
        'L3_decayed': exp.L3_decayed,
        'distorted': exp.distorted,
        'source_type': exp.source_type,
        'confidence': exp.confidence,
        'created_at': exp.created_at,
    }


def _entity_summary(ent):
    """实体摘要"""
    props = ent.properties or {}
    return {
        'id': ent.id,
        'name': ent.name,
        'type': ent.type,
        'confidence': ent.confidence,
        'property_count': len(props) if isinstance(props, dict) else 0,
        'created_at': ent.created_at,
        'updated_at': ent.updated_at,
    }


def _entity_full(ent):
    """实体完整详情"""
    result = _entity_summary(ent)
    result['properties'] = ent.properties
    result['source'] = ent.source
    result['emotion_timeline'] = ent.emotion_timeline
    result['emotion_current'] = ent.emotion_current
    return result


def _safe_json_parse(val):
    """安全解析 JSON 字符串"""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# ============================================================
# API 端点
# ============================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


# --- 统计 ---

@app.route('/api/stats')
def api_stats():
    experiences = experience_store.get_all()
    entities = entity_store.get_all()
    entity_types = entity_store.count_by_type()
    consolidated = sum(1 for e in experiences if e.consolidated)

    return jsonify({
        'experience_count': len(experiences),
        'entity_count': len(entities),
        'experience_edge_count': experience_edge_store.count(),
        'entity_edge_count': entity_edge_store.count(),
        'cross_edge_count': cross_edge_store.count(),
        'consolidated_count': consolidated,
        'unconsolidated_count': len(experiences) - consolidated,
        'entity_types': entity_types,
        'profile_count': profile_store.count(),
        'latest_experience': max((e.created_at for e in experiences), default=None),
    })


# --- 体验 ---

@app.route('/api/experiences')
def api_experiences():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    experiences = experience_store.get_all()
    total = len(experiences)
    # 按时间倒序
    experiences.sort(key=lambda e: e.created_at or '', reverse=True)
    page = experiences[offset:offset + limit]
    return jsonify({
        'items': [_exp_summary(e) for e in page],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@app.route('/api/experiences/<exp_id>')
def api_experience_detail(exp_id):
    exp = experience_store.get(exp_id)
    if not exp:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(_exp_full(exp))


@app.route('/api/experiences/<exp_id>/edges')
def api_experience_edges(exp_id):
    from_edges = experience_edge_store.get_by_from(exp_id)
    to_edges = experience_edge_store.get_by_to(exp_id)
    return jsonify({
        'from': [{'id': e.id, 'to_id': e.to_id, 'type': e.type,
                  'weight': e.weight, 'decayed_weight': e.decayed_weight} for e in from_edges],
        'to': [{'id': e.id, 'from_id': e.from_id, 'type': e.type,
                'weight': e.weight, 'decayed_weight': e.decayed_weight} for e in to_edges],
    })


@app.route('/api/experiences/<exp_id>/entities')
def api_experience_entities(exp_id):
    cross_edges = cross_edge_store.get_by_experience(exp_id)
    result = []
    for ce in cross_edges:
        ent = entity_store.get(ce.to_id)
        if ent:
            result.append({
                'id': ent.id,
                'name': ent.name,
                'type': ent.type,
                'context': ce.context,
                'weight': ce.weight,
            })
    return jsonify(result)


@app.route('/api/experiences/<exp_id>', methods=['DELETE'])
def api_delete_experience(exp_id):
    exp = experience_store.get(exp_id)
    if not exp:
        return jsonify({'error': 'Not found'}), 404
    experience_store.delete(exp_id)
    return jsonify({'success': True, 'id': exp_id})


@app.route('/api/experiences/top')
def api_experiences_top():
    limit = request.args.get('limit', 10, type=int)
    experiences = experience_store.get_top_by_importance(limit)
    return jsonify([_exp_summary(e) for e in experiences])


@app.route('/api/experiences/by_time')
def api_experiences_by_time():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    if not start or not end:
        return jsonify({'error': 'start and end required'}), 400
    experiences = experience_store.get_by_time_range(start, end)
    return jsonify([_exp_summary(e) for e in experiences])


# --- 实体 ---

@app.route('/api/entities')
def api_entities():
    entity_type = request.args.get('type', '')
    if entity_type:
        entities = entity_store.get_by_type(entity_type)
    else:
        entities = entity_store.get_all()
    return jsonify([_entity_summary(e) for e in entities])


@app.route('/api/entities/<ent_id>', methods=['DELETE'])
def api_delete_entity(ent_id):
    ent = entity_store.get(ent_id)
    if not ent:
        return jsonify({'error': 'Not found'}), 404
    entity_store.delete(ent_id)
    return jsonify({'success': True, 'id': ent_id})


@app.route('/api/entities/types')
def api_entity_types():
    return jsonify(entity_store.count_by_type())


@app.route('/api/entities/<ent_id>')
def api_entity_detail(ent_id):
    ent = entity_store.get(ent_id)
    if not ent:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(_entity_full(ent))


@app.route('/api/entities/<ent_id>/edges')
def api_entity_edges(ent_id):
    from_edges = entity_edge_store.get_by_from(ent_id)
    to_edges = entity_edge_store.get_by_to(ent_id)
    result = []
    for e in from_edges:
        target = entity_store.get(e.to_id)
        result.append({
            'id': e.id, 'direction': 'out',
            'other_id': e.to_id, 'other_name': target.name if target else e.to_id,
            'relation': e.relation, 'confidence': e.confidence,
            'source_type': e.source_type,
        })
    for e in to_edges:
        source = entity_store.get(e.from_id)
        result.append({
            'id': e.id, 'direction': 'in',
            'other_id': e.from_id, 'other_name': source.name if source else e.from_id,
            'relation': e.relation, 'confidence': e.confidence,
            'source_type': e.source_type,
        })
    return jsonify(result)


@app.route('/api/entities/<ent_id>/experiences')
def api_entity_experiences(ent_id):
    cross_edges = cross_edge_store.get_by_entity(ent_id)
    result = []
    for ce in cross_edges:
        exp = experience_store.get(ce.from_id)
        if exp:
            result.append(_exp_summary(exp))
    return jsonify(result)


# --- 网络图 ---

@app.route('/api/graph/data')
def api_graph_data():
    colors = {'experience': '#2196F3', 'entity': '#9C27B0', 'dream': '#FF9800'}

    # 体验节点
    experiences = experience_store.get_all()
    exp_nodes = []
    for exp in experiences:
        is_dream = exp.id.startswith('dream_')
        ntype = 'dream' if is_dream else 'experience'
        exp_nodes.append({
            'id': exp.id,
            'label': (exp.L0_text or '')[:40] + ('...' if len(exp.L0_text or '') > 40 else '') or exp.id,
            'type': 'experience', 'subtype': ntype,
            'color': colors.get(ntype, '#757575'),
            'size': 18 + (exp.importance or 0) * 14,
            'title': f"{ntype}\n重要度: {exp.importance or 0:.2f}",
        })

    # 实体节点
    entities = entity_store.get_all()
    ent_nodes = []
    for ent in entities:
        ent_nodes.append({
            'id': ent.id,
            'label': ent.name,
            'type': 'entity', 'subtype': 'normal',
            'color': colors['entity'],
            'size': 14 + (ent.confidence or 0) * 10,
            'title': f"实体: {ent.name}\n类型: {ent.type or 'N/A'}",
        })

    # 体验边
    exp_edges = experience_edge_store.get_all()
    edge_list = []
    for e in exp_edges:
        edge_list.append({
            'from': e.from_id, 'to': e.to_id,
            'type': e.type, 'label': e.type,
            'weight': e.weight,
        })

    # 实体边
    ent_edges = entity_edge_store.get_all()
    for e in ent_edges:
        edge_list.append({
            'from': e.from_id, 'to': e.to_id,
            'type': e.relation, 'label': e.relation,
            'weight': e.confidence,
        })

    # 跨层边（虚线样式）
    cross_edges_list = cross_edge_store.get_recent_edges(days=3650)
    for e in cross_edges_list:
        edge_list.append({
            'from': e.from_id, 'to': e.to_id,
            'type': 'cross', 'label': '关联',
            'weight': e.weight, 'dashes': True,
        })

    stats = {
        'experience_count': len(exp_nodes),
        'entity_count': len(ent_nodes),
        'edge_count': len(edge_list),
    }

    # 聚焦模式
    focus = request.args.get('focus', '')
    if focus:
        all_nodes = exp_nodes + ent_nodes
        node_ids = {n['id'] for n in all_nodes}
        # 2跳邻域
        neighbors = {focus}
        for _ in range(2):
            new_neighbors = set()
            for edge in edge_list:
                if edge['from'] in neighbors:
                    new_neighbors.add(edge['to'])
                if edge['to'] in neighbors:
                    new_neighbors.add(edge['from'])
            neighbors |= new_neighbors
        exp_nodes = [n for n in exp_nodes if n['id'] in neighbors]
        ent_nodes = [n for n in ent_nodes if n['id'] in neighbors]
        edge_list = [e for e in edge_list if e['from'] in neighbors and e['to'] in neighbors]

    return jsonify({
        'nodes': exp_nodes + ent_nodes,
        'edges': edge_list,
        'stats': stats,
    })


# --- 状态 & 核心 ---

@app.route('/api/state')
def api_state():
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


@app.route('/api/core')
def api_core():
    """获取核心层数据，从 Backend 主系统 HTTP 获取。"""
    backend_url = settings.dream.backend_url
    try:
        resp = http_requests.get(f"{backend_url}/api/core/identity", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return jsonify({
                'invariant_text': '',
                'stable_text': data.get('stable_text', ''),
                'malleable_text': data.get('malleable_yaml', ''),
                'anchors': None,
            })
    except Exception:
        pass
    # Backend 不可达时返回空数据
    return jsonify({
        'invariant_text': '',
        'stable_text': '',
        'malleable_text': '',
        'anchors': None,
    })


# --- 档案 ---

@app.route('/api/profiles')
def api_profiles():
    profiles = profile_store.get_all()
    result = []
    for p in profiles:
        basic = _safe_json_parse(p.basic) or {}
        result.append({
            'id': p.id,
            'name': basic.get('name', p.id.replace('profile_', '')),
            'basic': basic,
            'interaction_style': _safe_json_parse(p.interaction_style),
            'preferences': _safe_json_parse(p.preferences),
            'last_updated': p.last_updated,
        })
    return jsonify(result)


# --- 搜索 ---

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').lower()
    scope = request.args.get('scope', 'all')
    results = []

    if scope in ('all', 'experiences'):
        for exp in experience_store.get_all():
            text = (exp.L0_text or '') + (exp.L1_text or '') + (exp.L2_text or '')
            if q in text.lower():
                results.append({'type': 'experience', **_exp_summary(exp)})

    if scope in ('all', 'entities'):
        for ent in entity_store.get_all():
            if q in (ent.name or '').lower() or q in str(ent.properties or '').lower():
                results.append({'type': 'entity', **_entity_summary(ent)})

    return jsonify(results[:50])


# ============================================================
# HTML 模板
# ============================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>记忆系统 - 查询前端</title>
<script src="https://cdn.jsdelivr.net/npm/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
:root {
    --primary: #667eea;
    --secondary: #764ba2;
    --bg: #f0f2f5;
    --card: #ffffff;
    --sidebar-bg: #1a1a2e;
    --sidebar-active: #16213e;
    --text: #333;
    --text-light: #6c757d;
    --border: #e0e0e0;
    --success: #28a745;
    --warning: #ffc107;
    --danger: #dc3545;
    --info: #17a2b8;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'PingFang SC','Microsoft YaHei','Segoe UI',sans-serif; background:var(--bg); color:var(--text); }

/* Sidebar */
.sidebar {
    position:fixed; left:0; top:0; bottom:0; width:200px;
    background:var(--sidebar-bg); color:#ccc; z-index:100;
    display:flex; flex-direction:column;
}
.sidebar-logo {
    padding:20px; font-size:18px; font-weight:700; color:#fff;
    border-bottom:1px solid rgba(255,255,255,0.1);
}
.sidebar-nav { flex:1; padding:10px 0; }
.nav-item {
    display:block; padding:12px 20px; color:#aaa; cursor:pointer;
    transition:all .2s; font-size:14px; border-left:3px solid transparent;
}
.nav-item:hover { color:#fff; background:var(--sidebar-active); }
.nav-item.active { color:#fff; background:var(--sidebar-active); border-left-color:var(--primary); }

/* Header */
.header {
    position:fixed; top:0; left:200px; right:0; height:56px;
    background:var(--card); border-bottom:1px solid var(--border);
    display:flex; align-items:center; padding:0 24px; z-index:90;
    box-shadow:0 1px 3px rgba(0,0,0,0.05);
}
.search-box {
    flex:1; max-width:400px; position:relative;
}
.search-box input {
    width:100%; padding:8px 16px 8px 36px; border:1px solid var(--border);
    border-radius:20px; font-size:14px; outline:none;
}
.search-box input:focus { border-color:var(--primary); }
.search-icon {
    position:absolute; left:12px; top:50%; transform:translateY(-50%); color:#aaa;
}
.search-results {
    position:absolute; top:100%; left:0; right:0; background:var(--card);
    border:1px solid var(--border); border-radius:8px; margin-top:4px;
    max-height:400px; overflow-y:auto; box-shadow:0 4px 12px rgba(0,0,0,0.15);
    display:none; z-index:200;
}
.search-results.show { display:block; }
.search-item {
    padding:10px 16px; cursor:pointer; border-bottom:1px solid #f0f0f0;
}
.search-item:hover { background:#f5f5f5; }
.search-item .tag { font-size:11px; padding:2px 6px; border-radius:4px; margin-right:6px; }

/* Main */
.main {
    margin-left:200px; margin-top:56px; padding:24px; min-height:calc(100vh - 56px);
}

/* View panels */
.view { display:none; }
.view.active { display:block; }

/* Cards */
.card {
    background:var(--card); border-radius:12px; padding:20px;
    box-shadow:0 1px 3px rgba(0,0,0,0.08); margin-bottom:16px;
}
.card-title { font-size:16px; font-weight:600; margin-bottom:12px; }

/* Stat cards */
.stat-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px; }
.stat-card {
    background:var(--card); border-radius:12px; padding:20px;
    box-shadow:0 1px 3px rgba(0,0,0,0.08); border-top:3px solid var(--primary);
}
.stat-card .value { font-size:28px; font-weight:700; color:var(--primary); }
.stat-card .label { font-size:13px; color:var(--text-light); margin-top:4px; }

/* Grid layout */
.grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.grid-3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; }

/* Experience cards */
.exp-card {
    background:var(--card); border-radius:10px; padding:16px;
    box-shadow:0 1px 3px rgba(0,0,0,0.06); cursor:pointer;
    transition:all .2s; border-left:4px solid transparent;
}
.exp-card:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.1); }
.exp-card.dream { border-left-color:var(--warning); }
.exp-card.normal { border-left-color:var(--info); }
.exp-card .L0 { font-size:14px; line-height:1.6; margin-bottom:8px; }
.exp-card .meta { font-size:12px; color:var(--text-light); display:flex; gap:12px; flex-wrap:wrap; }
.badge {
    display:inline-block; padding:2px 8px; border-radius:4px;
    font-size:11px; font-weight:500;
}
.badge-success { background:#d4edda; color:#155724; }
.badge-warning { background:#fff3cd; color:#856404; }
.badge-info { background:#d1ecf1; color:#0c5460; }
.badge-purple { background:#e8daef; color:#6c3483; }

/* Importance bar */
.bar-container { height:6px; background:#e9ecef; border-radius:3px; overflow:hidden; }
.bar-fill { height:100%; border-radius:3px; }

/* Layer sections */
.layer-section {
    border:1px solid var(--border); border-radius:8px; margin-bottom:8px;
    overflow:hidden;
}
.layer-header {
    padding:12px 16px; background:#f8f9fa; cursor:pointer;
    display:flex; justify-content:space-between; align-items:center;
    font-weight:500;
}
.layer-header:hover { background:#e9ecef; }
.layer-content {
    padding:16px; display:none; font-size:14px; line-height:1.8;
    white-space:pre-wrap; border-top:1px solid var(--border);
}
.layer-content.open { display:block; }

/* Entity table */
.entity-table { width:100%; border-collapse:collapse; }
.entity-table th { text-align:left; padding:10px 12px; background:#f8f9fa; font-size:13px; color:var(--text-light); border-bottom:2px solid var(--border); }
.entity-table td { padding:10px 12px; border-bottom:1px solid #f0f0f0; font-size:14px; }
.entity-table tr:hover td { background:#f5f7ff; }
.entity-table tr { cursor:pointer; }

/* Type tabs */
.type-tabs { display:flex; gap:4px; margin-bottom:16px; flex-wrap:wrap; }
.type-tab {
    padding:6px 14px; border-radius:20px; font-size:13px; cursor:pointer;
    background:var(--card); border:1px solid var(--border); transition:all .2s;
}
.type-tab.active, .type-tab:hover { background:var(--primary); color:#fff; border-color:var(--primary); }

/* Filter bar */
.filter-bar {
    display:flex; gap:12px; align-items:center; flex-wrap:wrap;
    margin-bottom:16px; padding:12px 16px; background:var(--card);
    border-radius:8px; box-shadow:0 1px 2px rgba(0,0,0,0.04);
}
.filter-bar input, .filter-bar select {
    padding:6px 12px; border:1px solid var(--border); border-radius:6px; font-size:13px;
}

/* Detail panel */
.detail-header {
    display:flex; align-items:center; gap:12px; margin-bottom:16px;
}
.back-btn {
    padding:6px 12px; background:var(--card); border:1px solid var(--border);
    border-radius:6px; cursor:pointer; font-size:13px;
}
.back-btn:hover { background:#f0f0f0; }

/* Props table */
.props-table { width:100%; }
.props-table td { padding:6px 12px; border-bottom:1px solid #f0f0f0; font-size:13px; }
.props-table td:first-child { font-weight:600; color:var(--text-light); width:120px; }

/* Network container */
#network-container { width:100%; height:calc(100vh - 140px); background:#fff; border-radius:12px; }

/* Profile card */
.profile-card {
    background:var(--card); border-radius:10px; padding:16px;
    box-shadow:0 1px 3px rgba(0,0,0,0.06); cursor:pointer;
}
.profile-card:hover { box-shadow:0 4px 12px rgba(0,0,0,0.1); }

/* Loading */
.loading { text-align:center; padding:40px; color:var(--text-light); }
.empty { text-align:center; padding:40px; color:var(--text-light); font-size:14px; }

/* State cards */
.state-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; }
.state-card {
    background:var(--card); border-radius:12px; padding:20px; text-align:center;
    box-shadow:0 1px 3px rgba(0,0,0,0.08);
}
.state-card .icon { font-size:32px; margin-bottom:8px; }
.state-card .value { font-size:24px; font-weight:700; }
.state-card .label { font-size:12px; color:var(--text-light); margin-top:4px; }

/* Core identity sections */
.core-section {
    background:var(--card); border-radius:8px; padding:16px; margin-bottom:12px;
    border-left:4px solid;
}
.core-section h4 { margin-bottom:8px; }
.core-section pre { white-space:pre-wrap; font-size:13px; line-height:1.8; font-family:inherit; }

/* Responsive */
@media(max-width:768px) {
    .sidebar { width:60px; }
    .sidebar-logo { font-size:14px; padding:12px; }
    .nav-item { padding:12px; font-size:0; }
    .main { margin-left:60px; }
    .header { left:60px; }
    .grid-2, .grid-3 { grid-template-columns:1fr; }
}

/* Timeline */
.timeline { position:relative; padding-left:24px; }
.timeline::before { content:''; position:absolute; left:8px; top:0; bottom:0; width:2px; background:var(--border); }
.timeline-item {
    position:relative; margin-bottom:16px; padding:12px 16px;
    background:var(--card); border-radius:8px; box-shadow:0 1px 2px rgba(0,0,0,0.04);
    cursor:pointer;
}
.timeline-item::before {
    content:''; position:absolute; left:-20px; top:16px;
    width:10px; height:10px; border-radius:50%; background:var(--primary);
}
.timeline-item .time { font-size:11px; color:var(--text-light); }
.timeline-item .text { font-size:13px; margin-top:4px; }

/* Bar chart (CSS only) */
.bar-chart { }
.bar-row { display:flex; align-items:center; margin-bottom:8px; }
.bar-label { width:60px; font-size:13px; text-align:right; padding-right:12px; }
.bar-track { flex:1; height:24px; background:#f0f0f0; border-radius:4px; overflow:hidden; position:relative; }
.bar-value { height:100%; background:linear-gradient(90deg,var(--primary),var(--secondary)); border-radius:4px; display:flex; align-items:center; padding-left:8px; color:#fff; font-size:11px; min-width:20px; }

/* Delete button */
.delete-btn {
    padding:6px 16px; background:var(--danger); color:#fff; border:none;
    border-radius:6px; cursor:pointer; font-size:13px; transition:opacity .2s;
}
.delete-btn:hover { opacity:0.85; }

/* Confirm modal */
.modal-overlay {
    display:none; position:fixed; top:0; left:0; right:0; bottom:0;
    background:rgba(0,0,0,0.45); z-index:1000;
    justify-content:center; align-items:center;
}
.modal-overlay.show { display:flex; }
.modal-box {
    background:var(--card); border-radius:12px; padding:28px 32px;
    box-shadow:0 8px 32px rgba(0,0,0,0.2); max-width:420px; width:90%;
}
.modal-box h3 { margin:0 0 12px; font-size:16px; }
.modal-box p { font-size:14px; color:var(--text-light); margin:0 0 20px; line-height:1.6; }
.modal-box .modal-actions { display:flex; gap:12px; justify-content:flex-end; }
.modal-box .modal-cancel {
    padding:8px 20px; border:1px solid var(--border); border-radius:6px;
    background:var(--card); cursor:pointer; font-size:13px;
}
.modal-box .modal-confirm {
    padding:8px 20px; border:none; border-radius:6px;
    background:var(--danger); color:#fff; cursor:pointer; font-size:13px;
}
.modal-box .modal-confirm:hover { opacity:0.85; }
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
    <div class="sidebar-logo">Memory</div>
    <nav class="sidebar-nav">
        <div class="nav-item active" onclick="switchView('dashboard')">仪表盘</div>
        <div class="nav-item" onclick="switchView('experiences')">体验</div>
        <div class="nav-item" onclick="switchView('entities')">实体</div>
        <div class="nav-item" onclick="switchView('network')">关系网络</div>
        <div class="nav-item" onclick="switchView('state')">AI状态</div>
        <div class="nav-item" onclick="switchView('profiles')">人物档案</div>
    </nav>
</div>

<!-- Header -->
<div class="header">
    <div class="search-box">
        <span class="search-icon">&#128269;</span>
        <input id="searchInput" type="text" placeholder="搜索体验或实体..." oninput="onSearch(this.value)">
        <div id="searchResults" class="search-results"></div>
    </div>
</div>

<!-- Main Content -->
<div class="main">

    <!-- Dashboard -->
    <div id="view-dashboard" class="view active">
        <div id="stat-grid" class="stat-grid"></div>
        <div class="grid-2">
            <div class="card">
                <div class="card-title">实体类型分布</div>
                <div id="entity-chart"></div>
            </div>
            <div class="card">
                <div class="card-title">最近体验</div>
                <div id="recent-timeline" class="timeline"></div>
            </div>
        </div>
    </div>

    <!-- Experiences -->
    <div id="view-experiences" class="view">
        <div id="exp-list-view">
            <div class="filter-bar">
                <input id="exp-search" type="text" placeholder="搜索文本..." oninput="loadExperiences()">
                <select id="exp-source" onchange="loadExperiences()">
                    <option value="">全部来源</option>
                    <option value="direct">直接</option>
                    <option value="dream">梦境</option>
                </select>
                <select id="exp-consolidated" onchange="loadExperiences()">
                    <option value="">全部状态</option>
                    <option value="1">已巩固</option>
                    <option value="0">未巩固</option>
                </select>
                <button onclick="loadExperiences()" style="padding:6px 16px;border-radius:6px;border:1px solid var(--border);cursor:pointer;">刷新</button>
            </div>
            <div id="exp-list"></div>
            <div id="exp-more" style="text-align:center;padding:16px;">
                <button onclick="loadMoreExperiences()" style="padding:8px 24px;border-radius:6px;border:1px solid var(--border);cursor:pointer;background:var(--card);">加载更多</button>
            </div>
        </div>
        <div id="exp-detail-view" style="display:none;"></div>
    </div>

    <!-- Entities -->
    <div id="view-entities" class="view">
        <div id="ent-list-view">
            <div class="type-tabs" id="entity-type-tabs"></div>
            <div id="ent-list"></div>
        </div>
        <div id="ent-detail-view" style="display:none;"></div>
    </div>

    <!-- Network -->
    <div id="view-network" class="view">
        <div class="filter-bar">
            <label><input type="checkbox" id="net-show-exp" checked onchange="applyNetFilter()"> 体验</label>
            <label><input type="checkbox" id="net-show-ent" checked onchange="applyNetFilter()"> 实体</label>
            <label><input type="checkbox" id="net-show-dream" checked onchange="applyNetFilter()"> 梦境</label>
            <input id="net-focus" type="text" placeholder="聚焦节点ID..." style="width:200px;">
            <button onclick="focusNetwork()" style="padding:6px 16px;border-radius:6px;border:1px solid var(--border);cursor:pointer;">聚焦</button>
            <button onclick="loadGraph()" style="padding:6px 16px;border-radius:6px;border:1px solid var(--border);cursor:pointer;">重置</button>
        </div>
        <div id="network-container"></div>
    </div>

    <!-- State -->
    <div id="view-state" class="view">
        <div id="state-cards" class="state-grid"></div>
        <div id="core-sections"></div>
    </div>

    <!-- Profiles -->
    <div id="view-profiles" class="view">
        <div id="profile-list"></div>
        <div id="profile-detail" style="display:none;"></div>
    </div>
</div>

<!-- Delete Confirm Modal -->
<div id="delete-modal" class="modal-overlay">
    <div class="modal-box">
        <h3 id="delete-modal-title">确认删除</h3>
        <p id="delete-modal-msg"></p>
        <div class="modal-actions">
            <button class="modal-cancel" onclick="closeDeleteModal()">取消</button>
            <button class="modal-confirm" id="delete-modal-confirm">确认删除</button>
        </div>
    </div>
</div>

<script>
// ============================================================
// Global state
// ============================================================
let currentView = 'dashboard';
let expOffset = 0;
const EXP_LIMIT = 30;
let allExperiences = [];
let graphNodes = [];
let graphEdges = [];
let network = null;

// ============================================================
// View switching
// ============================================================
function switchView(view) {
    currentView = view;
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + view).classList.add('active');
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    event.target.classList.add('active');

    if (view === 'dashboard') loadDashboard();
    else if (view === 'experiences') loadExperiences();
    else if (view === 'entities') loadEntities();
    else if (view === 'network') loadGraph();
    else if (view === 'state') loadState();
    else if (view === 'profiles') loadProfiles();
}

// ============================================================
// API helpers
// ============================================================
async function api(url) {
    const res = await fetch(url);
    return res.json();
}

function barHtml(value, max=1.0, color='var(--primary)') {
    const pct = Math.round((value/max)*100);
    return `<div class="bar-container"><div class="bar-fill" style="width:${pct}%;background:${color};"></div></div>`;
}

// ============================================================
// Dashboard
// ============================================================
async function loadDashboard() {
    const stats = await api('/api/stats');
    const consRate = stats.experience_count > 0 ? Math.round(stats.consolidated_count / stats.experience_count * 100) : 0;

    document.getElementById('stat-grid').innerHTML = `
        <div class="stat-card"><div class="value">${stats.experience_count}</div><div class="label">体验节点</div></div>
        <div class="stat-card"><div class="value">${stats.entity_count}</div><div class="label">实体节点</div></div>
        <div class="stat-card"><div class="value">${stats.experience_edge_count + stats.entity_edge_count}</div><div class="label">关系边</div></div>
        <div class="stat-card"><div class="value">${consRate}%</div><div class="label">巩固率</div></div>
        <div class="stat-card"><div class="value">${stats.profile_count}</div><div class="label">人物档案</div></div>
    `;

    // Entity type chart
    const types = stats.entity_types || {};
    const maxCount = Math.max(...Object.values(types), 1);
    const typeLabels = {person:'人物',place:'地点',concept:'概念',event:'事件',skill:'技能',other:'其他'};
    let chartHtml = '<div class="bar-chart">';
    for (const [t, c] of Object.entries(types)) {
        chartHtml += `<div class="bar-row"><div class="bar-label">${typeLabels[t]||t}</div><div class="bar-track"><div class="bar-value" style="width:${(c/maxCount)*100}%">${c}</div></div></div>`;
    }
    chartHtml += '</div>';
    document.getElementById('entity-chart').innerHTML = chartHtml;

    // Recent experiences
    const exps = await api('/api/experiences?limit=10');
    let tlHtml = '';
    for (const e of exps.items.slice(0, 10)) {
        tlHtml += `<div class="timeline-item" onclick="showExperienceDetail('${e.id}')">
            <div class="time">${e.created_at || ''}</div>
            <div class="text">${e.L0_text || e.id}</div>
        </div>`;
    }
    document.getElementById('recent-timeline').innerHTML = tlHtml || '<div class="empty">暂无数据</div>';
}

// ============================================================
// Experiences
// ============================================================
async function loadExperiences() {
    expOffset = 0;
    const search = document.getElementById('exp-search').value;
    const source = document.getElementById('exp-source').value;
    const cons = document.getElementById('exp-consolidated').value;

    let url = `/api/experiences?limit=${EXP_LIMIT}&offset=0`;
    const data = await api(url);
    allExperiences = data.items;

    // Client-side filtering
    let filtered = allExperiences;
    if (search) filtered = filtered.filter(e => (e.L0_text||'').toLowerCase().includes(search.toLowerCase()));
    if (source) filtered = filtered.filter(e => e.source_type === source);
    if (cons) filtered = filtered.filter(e => String(e.consolidated) === cons);

    renderExperienceList(filtered);
    document.getElementById('exp-list-view').style.display = 'block';
    document.getElementById('exp-detail-view').style.display = 'none';
}

function renderExperienceList(items) {
    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;">';
    for (const e of items) {
        const isDream = e.id.startsWith('dream_');
        const cls = isDream ? 'dream' : 'normal';
        const sourceBadge = isDream ? '<span class="badge badge-warning">梦境</span>' : '<span class="badge badge-info">直接</span>';
        const consBadge = e.consolidated ? '<span class="badge badge-success">已巩固</span>' : '';
        html += `<div class="exp-card ${cls}" onclick="showExperienceDetail('${e.id}')">
            <div class="L0">${e.L0_text || e.id}</div>
            <div class="meta">
                ${sourceBadge}${consBadge}
                <span>${e.emotion_category || ''}</span>
                <span>重要度: ${(e.importance||0).toFixed(2)}</span>
                <span>${e.created_at || ''}</span>
            </div>
            ${barHtml(e.importance||0, 1.0, isDream ? 'var(--warning)' : 'var(--primary)')}
        </div>`;
    }
    html += '</div>';
    document.getElementById('exp-list').innerHTML = html || '<div class="empty">暂无数据</div>';
}

async function loadMoreExperiences() {
    expOffset += EXP_LIMIT;
    const data = await api(`/api/experiences?limit=${EXP_LIMIT}&offset=${expOffset}`);
    allExperiences = allExperiences.concat(data.items);
    renderExperienceList(allExperiences);
}

async function showExperienceDetail(id) {
    const exp = await api(`/api/experiences/${id}`);
    const edges = await api(`/api/experiences/${id}/edges`);
    const entities = await api(`/api/experiences/${id}/entities`);

    const isDream = exp.id.startsWith('dream_');

    let html = `<div class="detail-header">
        <button class="back-btn" onclick="backToExpList()">← 返回列表</button>
        <span class="badge ${isDream ? 'badge-warning' : 'badge-info'}">${isDream ? '梦境' : '体验'}</span>
        <span style="font-size:13px;color:var(--text-light);">${exp.id}</span>
        <button class="delete-btn" style="margin-left:auto;" onclick="confirmDelete('experience','${exp.id}','${(exp.L0_text||'').substring(0,40).replace(/'/g,"\\'")}')">删除此体验</button>
    </div>`;

    // Basic info
    html += `<div class="card">
        <div class="card-title">基本信息</div>
        <table class="props-table">
            <tr><td>时间</td><td>${exp.created_at||''}</td></tr>
            <tr><td>重要度</td><td>${barHtml(exp.importance||0)} ${(exp.importance||0).toFixed(3)}</td></tr>
            <tr><td>情感</td><td>${exp.emotion_category||''} (强度:${(exp.emotion_intensity||0).toFixed(2)} 效价:${(exp.emotion_valence||0).toFixed(2)})</td></tr>
            <tr><td>来源</td><td>${exp.source_type||''}</td></tr>
            <tr><td>巩固</td><td>${exp.consolidated?'是':'否'}</td></tr>
            <tr><td>扭曲</td><td>${exp.twist_level||'none'}</td></tr>
            <tr><td>置信度</td><td>${(exp.confidence||0).toFixed(2)}</td></tr>
        </table>
    </div>`;

    // Context
    if (exp.context_focus || exp.context_mood || exp.context_time_of_day) {
        html += `<div class="card"><div class="card-title">上下文</div>
        <table class="props-table">
            ${exp.context_focus ? `<tr><td>注意力</td><td>${exp.context_focus}</td></tr>` : ''}
            ${exp.context_mood ? `<tr><td>心情</td><td>${exp.context_mood}</td></tr>` : ''}
            ${exp.context_time_of_day ? `<tr><td>时间段</td><td>${exp.context_time_of_day}</td></tr>` : ''}
            ${exp.context_silence_before ? `<tr><td>沉默时长</td><td>${exp.context_silence_before}</td></tr>` : ''}
        </table></div>`;
    }

    // Four layers
    html += '<div class="card"><div class="card-title">记忆层次</div>';
    const layers = [
        {name:'L0 摘要', text:exp.L0_text, color:'var(--info)'},
        {name:'L1 要点', text:exp.L1_text, color:'var(--success)'},
        {name:'L2 细节', text:exp.L2_text, color:'var(--secondary)'},
        {name:'L3 原文', text:exp.L3_raw, color:'var(--danger)'},
    ];
    for (let i = 0; i < layers.length; i++) {
        const l = layers[i];
        const open = i === 0 ? 'open' : '';
        html += `<div class="layer-section">
            <div class="layer-header" onclick="toggleLayer(this)">
                <span style="color:${l.color}">${l.name}</span>
                <span>${l.text ? (l.text.length + '字') : '无'}</span>
            </div>
            <div class="layer-content ${open}">${l.text || '（无内容）'}</div>
        </div>`;
    }
    html += '</div>';

    // Decay
    html += `<div class="card"><div class="card-title">衰减权重</div>
    <table class="props-table">
        <tr><td>L0 衰减</td><td>${barHtml(exp.L0_decayed||0)} ${(exp.L0_decayed||0).toFixed(3)}</td></tr>
        <tr><td>L1 衰减</td><td>${barHtml(exp.L1_decayed||0)} ${(exp.L1_decayed||0).toFixed(3)}</td></tr>
        <tr><td>L2 衰减</td><td>${barHtml(exp.L2_decayed||0)} ${(exp.L2_decayed||0).toFixed(3)}</td></tr>
        <tr><td>L3 衰减</td><td>${barHtml(exp.L3_decayed||0)} ${(exp.L3_decayed||0).toFixed(3)}</td></tr>
    </table></div>`;

    // Connected entities
    if (entities.length > 0) {
        html += '<div class="card"><div class="card-title">关联实体</div><div style="display:flex;gap:8px;flex-wrap:wrap;">';
        for (const ent of entities) {
            html += `<span class="badge badge-purple" onclick="showEntityDetail('${ent.id}')" style="cursor:pointer;">${ent.name} (${ent.type||''})</span>`;
        }
        html += '</div></div>';
    }

    // Connected edges
    const allEdges = [...edges.from, ...edges.to];
    if (allEdges.length > 0) {
        html += '<div class="card"><div class="card-title">连接关系</div><table class="props-table">';
        for (const e of allEdges) {
            const dir = e.to_id ? '→' : '←';
            const target = e.to_id || e.from_id || '';
            html += `<tr><td>${e.type||''}</td><td>${dir} ${target} (权重:${(e.weight||0).toFixed(2)})</td></tr>`;
        }
        html += '</table></div>';
    }

    document.getElementById('exp-list-view').style.display = 'none';
    document.getElementById('exp-detail-view').style.display = 'block';
    document.getElementById('exp-detail-view').innerHTML = html;
}

function backToExpList() {
    document.getElementById('exp-list-view').style.display = 'block';
    document.getElementById('exp-detail-view').style.display = 'none';
}

function toggleLayer(el) {
    const content = el.nextElementSibling;
    content.classList.toggle('open');
}

// ============================================================
// Entities
// ============================================================
let currentEntityType = '';

async function loadEntities(type) {
    currentEntityType = type || '';
    const data = await api(`/api/entities${type ? '?type='+type : ''}`);

    // Type tabs
    const typeLabels = {'':'全部','person':'人物','place':'地点','concept':'概念','event':'事件','skill':'技能','other':'其他'};
    let tabsHtml = '';
    for (const [t, label] of Object.entries(typeLabels)) {
        const active = t === currentEntityType ? 'active' : '';
        tabsHtml += `<div class="type-tab ${active}" onclick="loadEntities('${t}')">${label}</div>`;
    }
    document.getElementById('entity-type-tabs').innerHTML = tabsHtml;

    // Table
    let html = '<table class="entity-table"><thead><tr><th>名称</th><th>类型</th><th>置信度</th><th>属性数</th><th>更新时间</th></tr></thead><tbody>';
    for (const e of data) {
        const typeLabels2 = {person:'人物',place:'地点',concept:'概念',event:'事件',skill:'技能',other:'其他'};
        html += `<tr onclick="showEntityDetail('${e.id}')">
            <td><strong>${e.name}</strong></td>
            <td><span class="badge badge-info">${typeLabels2[e.type]||e.type}</span></td>
            <td>${barHtml(e.confidence||0)} ${(e.confidence||0).toFixed(2)}</td>
            <td>${e.property_count}</td>
            <td style="font-size:12px;color:var(--text-light);">${e.updated_at||''}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('ent-list').innerHTML = html || '<div class="empty">暂无数据</div>';
    document.getElementById('ent-list-view').style.display = 'block';
    document.getElementById('ent-detail-view').style.display = 'none';
}

async function showEntityDetail(id) {
    const ent = await api(`/api/entities/${id}`);
    const edges = await api(`/api/entities/${id}/edges`);
    const experiences = await api(`/api/entities/${id}/experiences`);

    let html = `<div class="detail-header">
        <button class="back-btn" onclick="backToEntList()">← 返回列表</button>
        <span style="font-size:18px;font-weight:600;">${ent.name}</span>
        <span class="badge badge-info">${ent.type}</span>
        <button class="delete-btn" style="margin-left:auto;" onclick="confirmDelete('entity','${ent.id}','${(ent.name||'').replace(/'/g,"\\'")}')">删除此实体</button>
    </div>`;

    // Properties
    const props = ent.properties || {};
    if (Object.keys(props).length > 0) {
        html += '<div class="card"><div class="card-title">属性</div><table class="props-table">';
        for (const [k, v] of Object.entries(props)) {
            html += `<tr><td>${k}</td><td>${v}</td></tr>`;
        }
        html += '</table></div>';
    }

    // Meta
    html += `<div class="card"><div class="card-title">元信息</div>
    <table class="props-table">
        <tr><td>ID</td><td>${ent.id}</td></tr>
        <tr><td>置信度</td><td>${barHtml(ent.confidence||0)} ${(ent.confidence||0).toFixed(2)}</td></tr>
        <tr><td>来源</td><td>${ent.source||''}</td></tr>
        <tr><td>创建时间</td><td>${ent.created_at||''}</td></tr>
    </table></div>`;

    // Emotion timeline
    const timeline = ent.emotion_timeline;
    if (timeline && (Array.isArray(timeline) ? timeline.length > 0 : true)) {
        html += `<div class="card"><div class="card-title">情感时间线</div><pre style="font-size:13px;white-space:pre-wrap;">${JSON.stringify(timeline, null, 2)}</pre></div>`;
    }

    // Relationships
    if (edges.length > 0) {
        html += '<div class="card"><div class="card-title">关系 (' + edges.length + ')</div><table class="entity-table"><thead><tr><th>方向</th><th>关系</th><th>对象</th><th>置信度</th><th>来源</th></tr></thead><tbody>';
        for (const e of edges) {
            const dir = e.direction === 'out' ? '→' : '←';
            html += `<tr><td>${dir}</td><td>${e.relation}</td><td>${e.other_name}</td><td>${(e.confidence||0).toFixed(2)}</td><td>${e.source_type||''}</td></tr>`;
        }
        html += '</tbody></table></div>';
    }

    // Related experiences
    if (experiences.length > 0) {
        html += '<div class="card"><div class="card-title">相关体验 (' + experiences.length + ')</div>';
        for (const e of experiences) {
            html += `<div class="timeline-item" onclick="showExperienceDetail('${e.id}')">
                <div class="time">${e.created_at||''}</div>
                <div class="text">${e.L0_text||e.id}</div>
            </div>`;
        }
        html += '</div>';
    }

    document.getElementById('ent-list-view').style.display = 'none';
    document.getElementById('ent-detail-view').style.display = 'block';
    document.getElementById('ent-detail-view').innerHTML = html;
}

function backToEntList() {
    document.getElementById('ent-list-view').style.display = 'block';
    document.getElementById('ent-detail-view').style.display = 'none';
}

// ============================================================
// Network Graph
// ============================================================
async function loadGraph(focusId) {
    const url = focusId ? `/api/graph/data?focus=${encodeURIComponent(focusId)}` : '/api/graph/data';
    const data = await api(url);
    graphNodes = data.nodes;
    graphEdges = data.edges;

    if (!network) {
        const container = document.getElementById('network-container');
        network = new vis.Network(container, {nodes: graphNodes, edges: graphEdges}, {
            nodes: { shape:'dot', font:{size:12,color:'#333'}, borderWidth:2, shadow:true },
            edges: { width:1.5, smooth:{type:'continuous'}, arrows:{to:{enabled:true,scaleFactor:0.5}} },
            physics: { barnesHut:{gravitationalConstant:-5000,springConstant:0.04,springLength:80}, stabilization:{iterations:150} },
            interaction: { hover:true, zoomView:true, dragView:true },
        });
    } else {
        applyNetFilter();
    }
}

function applyNetFilter() {
    if (!network) return;
    const showExp = document.getElementById('net-show-exp').checked;
    const showEnt = document.getElementById('net-show-ent').checked;
    const showDream = document.getElementById('net-show-dream').checked;

    const filtered = graphNodes.filter(n => {
        if (n.type === 'experience' && !showExp) return false;
        if (n.type === 'entity' && !showEnt) return false;
        if (n.subtype === 'dream' && !showDream) return false;
        return true;
    });
    const ids = new Set(filtered.map(n => n.id));
    const filteredEdges = graphEdges.filter(e => ids.has(e.from) && ids.has(e.to));

    network.setData({nodes: filtered, edges: filteredEdges});
}

function focusNetwork() {
    const id = document.getElementById('net-focus').value.trim();
    if (id) loadGraph(id);
}

// ============================================================
// State
// ============================================================
async function loadState() {
    const state = await api('/api/state');
    const core = await api('/api/core');

    const stateData = [
        {icon:'&#127774;', label:'心情', value: state.mood_label || '平静', extra:`效价:${state.mood_valence} 唤醒:${state.mood_arousal}`, color:'#FF9800'},
        {icon:'&#9889;', label:'精力', value: state.energy_label || '正常', extra:`${state.energy_value}`, color:'#4CAF50'},
        {icon:'&#127919;', label:'注意力', value: state.focus || '无', extra:'', color:'#2196F3'},
        {icon:'&#128170;', label:'信心', value: state.confidence_label || '正常', extra:`${state.confidence_value}`, color:'#9C27B0'},
    ];

    let html = '';
    for (const s of stateData) {
        html += `<div class="state-card"><div class="icon">${s.icon}</div><div class="value">${s.value}</div><div class="label">${s.label}</div><div style="font-size:12px;color:var(--text-light);margin-top:4px;">${s.extra}</div></div>`;
    }
    document.getElementById('state-cards').innerHTML = html;

    // Core identity
    let coreHtml = '';
    const sections = [
        {title:'不变层', text:core.invariant_text, color:'var(--danger)'},
        {title:'稳定层', text:core.stable_text, color:'var(--warning)'},
        {title:'可塑层', text:core.malleable_text, color:'var(--success)'},
    ];
    for (const s of sections) {
        if (s.text) {
            coreHtml += `<div class="core-section" style="border-left-color:${s.color};"><h4>${s.title}</h4><pre>${s.text}</pre></div>`;
        }
    }
    if (core.anchors) {
        coreHtml += `<div class="card"><div class="card-title">锚点</div><pre style="font-size:13px;">${JSON.stringify(core.anchors, null, 2)}</pre></div>`;
    }
    document.getElementById('core-sections').innerHTML = coreHtml;
}

// ============================================================
// Profiles
// ============================================================
async function loadProfiles() {
    const profiles = await api('/api/profiles');
    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;">';
    for (const p of profiles) {
        const basic = p.basic || {};
        html += `<div class="profile-card" onclick="showProfileDetail('${p.id}')">
            <div style="font-size:16px;font-weight:600;margin-bottom:8px;">${p.name}</div>
            <div style="font-size:13px;color:var(--text-light);">
                ${Object.entries(basic).filter(([k])=>k!=='name').map(([k,v])=>`${k}: ${v}`).join(' | ')}
            </div>
            <div style="font-size:11px;color:var(--text-light);margin-top:8px;">更新: ${p.last_updated||''}</div>
        </div>`;
    }
    html += '</div>';
    document.getElementById('profile-list').innerHTML = html || '<div class="empty">暂无档案</div>';
    document.getElementById('profile-detail').style.display = 'none';
}

async function showProfileDetail(id) {
    const profiles = await api('/api/profiles');
    const p = profiles.find(x => x.id === id);
    if (!p) return;

    let html = `<div class="detail-header">
        <button class="back-btn" onclick="loadProfiles()">← 返回列表</button>
        <span style="font-size:18px;font-weight:600;">${p.name} 的档案</span>
    </div>`;

    const sections = [
        {title:'基本信息', data:p.basic},
        {title:'相处方式', data:p.interaction_style},
        {title:'沟通偏好', data:p.preferences},
    ];
    for (const s of sections) {
        if (s.data && Object.keys(s.data).length > 0) {
            html += `<div class="card"><div class="card-title">${s.title}</div><table class="props-table">`;
            for (const [k, v] of Object.entries(s.data)) {
                html += `<tr><td>${k}</td><td>${typeof v === 'object' ? JSON.stringify(v, null, 2) : v}</td></tr>`;
            }
            html += '</table></div>';
        }
    }

    document.getElementById('profile-list').style.display = 'none';
    document.getElementById('profile-detail').style.display = 'block';
    document.getElementById('profile-detail').innerHTML = html;
}

// ============================================================
// Search
// ============================================================
let searchTimer = null;
function onSearch(q) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => doSearch(q), 300);
}

async function doSearch(q) {
    const el = document.getElementById('searchResults');
    if (!q || q.length < 2) { el.classList.remove('show'); return; }

    const results = await api(`/api/search?q=${encodeURIComponent(q)}`);
    if (results.length === 0) { el.classList.remove('show'); return; }

    let html = '';
    for (const r of results.slice(0, 20)) {
        const tag = r.type === 'experience' ? '<span class="badge badge-info">体验</span>' : '<span class="badge badge-purple">实体</span>';
        const text = r.L0_text || r.name || r.id;
        const onclick = r.type === 'experience' ? `showExperienceDetail('${r.id}')` : `showEntityDetail('${r.id}')`;
        html += `<div class="search-item" onclick="${onclick}">${tag} ${text}</div>`;
    }
    el.innerHTML = html;
    el.classList.add('show');
}

// Close search on click outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-box')) {
        document.getElementById('searchResults').classList.remove('show');
    }
});

// ============================================================
// Delete
// ============================================================
let pendingDelete = null;

function confirmDelete(type, id, name) {
    pendingDelete = { type, id };
    const typeLabel = type === 'experience' ? '体验' : '实体';
    document.getElementById('delete-modal-title').textContent = `确认删除${typeLabel}`;
    document.getElementById('delete-modal-msg').textContent =
        `确定要删除${typeLabel}「${name}」吗？此操作不可撤销，关联的关系边也会被一并删除。`;
    document.getElementById('delete-modal-confirm').onclick = doDelete;
    document.getElementById('delete-modal').classList.add('show');
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('show');
    pendingDelete = null;
}

async function doDelete() {
    if (!pendingDelete) return;
    const { type, id } = pendingDelete;
    closeDeleteModal();

    const url = type === 'experience'
        ? `/api/experiences/${encodeURIComponent(id)}`
        : `/api/entities/${encodeURIComponent(id)}`;

    try {
        const res = await fetch(url, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            // Navigate back to list
            if (type === 'experience') {
                backToExpList();
                loadExperiences();
            } else {
                backToEntList();
                loadEntities();
            }
        } else {
            alert('删除失败: ' + (data.error || '未知错误'));
        }
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

// ============================================================
// Init
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
});
</script>
</body>
</html>
"""


# ============================================================
# Main entry
# ============================================================

def main():
    """启动查询前端服务器"""
    db_manager.initialize()

    print("=" * 60)
    print("记忆系统 - 查询前端")
    print("=" * 60)
    print()
    print(f"  访问地址: http://localhost:5001")
    print()
    print("  视图:")
    print("    - 仪表盘: 系统概览和统计")
    print("    - 体验:   浏览和搜索体验节点")
    print("    - 实体:   按类型浏览实体")
    print("    - 网络:   关系图可视化")
    print("    - 状态:   AI当前状态")
    print("    - 档案:   人物档案")
    print()
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    print()

    app.run(host='0.0.0.0', port=5001, debug=False)


if __name__ == '__main__':
    main()
