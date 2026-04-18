#!/usr/bin/env python3
"""记忆库可视化服务器

提供Web界面可视化展示记忆节点和边的关系网络。
"""

import sys
from pathlib import Path

# 确保可以从 scripts/ 目录导入 Memory 包
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
from flask import Flask, jsonify, render_template_string
from Memory.storage.database import db_manager
from Memory.storage.experience_store import experience_store
from Memory.storage.entity_store import entity_store
from Memory.storage.experience_edge_store import experience_edge_store
from Memory.storage.entity_edge_store import entity_edge_store

app = Flask(__name__)

# 颜色配置
colors = {
    'experience': '#2196F3',
    'entity': '#9C27B0',
    'dream': '#FF9800',
    'default': '#757575'
}

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>记忆库可视化 - Memory Network</title>
    <script src="https://cdn.jsdelivr.net/npm/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            overflow: hidden;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            padding: 15px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header h1 {
            color: #333;
            font-size: 24px;
            font-weight: 600;
        }

        .stats {
            display: flex;
            gap: 20px;
            font-size: 14px;
        }

        .stat-item {
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 20px;
            border: 1px solid #dee2e6;
        }

        .stat-label {
            color: #6c757d;
            margin-right: 5px;
        }

        .stat-value {
            color: #495057;
            font-weight: 600;
        }

        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
        }

        .btn-primary {
            background: #667eea;
            color: white;
        }

        .btn-primary:hover {
            background: #5568d3;
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: #6c757d;
            color: white;
        }

        .btn-secondary:hover {
            background: #5a6268;
        }

        .filter-group {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .filter-group label {
            font-size: 14px;
            color: #495057;
        }

        .checkbox-wrapper {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .checkbox-wrapper input[type="checkbox"] {
            cursor: pointer;
        }

        .checkbox-wrapper span {
            font-size: 13px;
            color: #495057;
        }

        #network {
            width: 100%;
            height: calc(100vh - 80px);
            background: white;
        }

        .node-info {
            position: absolute;
            top: 90px;
            right: 20px;
            width: 350px;
            background: rgba(255, 255, 255, 0.98);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            display: none;
            max-height: calc(100vh - 120px);
            overflow-y: auto;
        }

        .node-info.active {
            display: block;
        }

        .node-info h3 {
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }

        .info-row {
            margin-bottom: 12px;
        }

        .info-label {
            font-weight: 600;
            color: #495057;
            font-size: 13px;
            margin-bottom: 4px;
        }

        .info-value {
            color: #6c757d;
            font-size: 14px;
            line-height: 1.5;
        }

        .info-value.long-text {
            max-height: 150px;
            overflow-y: auto;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 6px;
        }

        .tag {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
            margin-right: 5px;
            margin-bottom: 5px;
        }

        .tag-experience {
            background: #e3f2fd;
            color: #1976d2;
        }

        .tag-entity {
            background: #f3e5f5;
            color: #7b1fa2;
        }

        .tag-dream {
            background: #fff3e0;
            color: #f57c00;
        }

        .close-btn {
            position: absolute;
            top: 15px;
            right: 15px;
            background: none;
            border: none;
            font-size: 20px;
            cursor: pointer;
            color: #6c757d;
        }

        .close-btn:hover {
            color: #495057;
        }

        .edge-info {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
        }

        .edge-list {
            margin-top: 10px;
        }

        .edge-item {
            background: white;
            padding: 8px 12px;
            border-radius: 6px;
            margin-bottom: 8px;
            border-left: 3px solid #667eea;
        }

        .edge-type {
            font-weight: 600;
            color: #333;
            font-size: 13px;
        }

        .edge-weight {
            font-size: 12px;
            color: #6c757d;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧠 记忆库可视化</h1>

        <div class="stats">
            <div class="stat-item">
                <span class="stat-label">体验节点:</span>
                <span class="stat-value" id="experience-count">0</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">实体节点:</span>
                <span class="stat-value" id="entity-count">0</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">体验边:</span>
                <span class="stat-value" id="experience-edge-count">0</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">实体边:</span>
                <span class="stat-value" id="entity-edge-count">0</span>
            </div>
        </div>

        <div class="controls">
            <div class="filter-group">
                <div class="checkbox-wrapper">
                    <input type="checkbox" id="show-experiences" checked>
                    <span>体验</span>
                </div>
                <div class="checkbox-wrapper">
                    <input type="checkbox" id="show-entities" checked>
                    <span>实体</span>
                </div>
                <div class="checkbox-wrapper">
                    <input type="checkbox" id="show-dreams" checked>
                    <span>梦境</span>
                </div>
            </div>
            <button class="btn btn-secondary" onclick="resetView()">重置视图</button>
            <button class="btn btn-primary" onclick="refreshData()">刷新数据</button>
        </div>
    </div>

    <div id="network"></div>

    <div class="node-info" id="node-info">
        <button class="close-btn" onclick="closeNodeInfo()">×</button>
        <h3 id="node-title">节点详情</h3>
        <div id="node-content"></div>
    </div>

    <script>
        let network = null;
        let allNodes = [];
        let allEdges = [];

        // 颜色配置
        const colors = {
            experience: '#2196F3',
            entity: '#9C27B0',
            dream: '#FF9800',
            default: '#757575'
        };

        // 初始化网络
        function initNetwork() {
            const container = document.getElementById('network');
            const data = {
                nodes: new vis.DataSet([]),
                edges: new vis.DataSet([])
            };

            const options = {
                nodes: {
                    shape: 'dot',
                    size: 16,
                    font: {
                        size: 12,
                        color: '#333'
                    },
                    borderWidth: 2,
                    shadow: true
                },
                edges: {
                    width: 2,
                    smooth: {
                        type: 'continuous',
                        forceDirection: 'none',
                        roundness: 0.5
                    },
                    arrows: {
                        to: {
                            enabled: true,
                            scaleFactor: 0.5
                        }
                    }
                },
                physics: {
                    enabled: true,
                    barnesHut: {
                        gravitationalConstant: -8000,
                        springConstant: 0.04,
                        springLength: 95
                    },
                    stabilization: {
                        iterations: 200
                    }
                },
                interaction: {
                    hover: true,
                    tooltipDelay: 100,
                    zoomView: true,
                    dragView: true
                }
            };

            network = new vis.Network(container, data, options);

            // 点击事件
            network.on('click', function(params) {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    showNodeInfo(nodeId);
                }
            });

            // 双击聚焦
            network.on('doubleClick', function(params) {
                if (params.nodes.length > 0) {
                    network.focus(params.nodes[0], {
                        scale: 1.2,
                        animation: true
                    });
                }
            });
        }

        // 加载数据
        async function loadData() {
            try {
                const response = await fetch('/api/data');
                const data = await response.json();

                // 更新统计
                document.getElementById('experience-count').textContent = data.stats.experience_count;
                document.getElementById('entity-count').textContent = data.stats.entity_count;
                document.getElementById('experience-edge-count').textContent = data.stats.experience_edge_count;
                document.getElementById('entity-edge-count').textContent = data.stats.entity_edge_count;

                // 存储所有数据
                allNodes = data.nodes;
                allEdges = data.edges;

                // 应用过滤器
                applyFilters();

            } catch (error) {
                console.error('加载数据失败:', error);
            }
        }

        // 应用过滤器
        function applyFilters() {
            const showExperiences = document.getElementById('show-experiences').checked;
            const showEntities = document.getElementById('show-entities').checked;
            const showDreams = document.getElementById('show-dreams').checked;

            let filteredNodes = allNodes.filter(node => {
                if (node.type === 'experience' && !showExperiences) return false;
                if (node.type === 'entity' && !showEntities) return false;
                if (node.subtype === 'dream' && !showDreams) return false;
                return true;
            });

            let filteredEdges = allEdges.filter(edge => {
                const fromNode = allNodes.find(n => n.id === edge.from);
                const toNode = allNodes.find(n => n.id === edge.to);

                if (!fromNode || !toNode) return false;

                if (fromNode.type === 'experience' && !showExperiences) return false;
                if (fromNode.type === 'entity' && !showEntities) return false;
                if (fromNode.subtype === 'dream' && !showDreams) return false;

                if (toNode.type === 'experience' && !showExperiences) return false;
                if (toNode.type === 'entity' && !showEntities) return false;
                if (toNode.subtype === 'dream' && !showDreams) return false;

                return true;
            });

            network.setData({
                nodes: filteredNodes,
                edges: filteredEdges
            });
        }

        // 显示节点信息
        function showNodeInfo(nodeId) {
            const node = allNodes.find(n => n.id === nodeId);
            if (!node) return;

            const infoPanel = document.getElementById('node-info');
            const title = document.getElementById('node-title');
            const content = document.getElementById('node-content');

            // 设置标题
            const typeLabel = node.type === 'experience' ? '体验节点' : '实体节点';
            const subtypeTag = node.subtype === 'dream' ? '<span class="tag tag-dream">梦境</span>' : '';
            const typeTag = `<span class="tag tag-${node.type}">${typeLabel}</span>`;

            title.innerHTML = `${typeTag} ${subtypeTag} ${node.label}`;

            // 构建内容
            let html = '';

            if (node.type === 'experience') {
                html += `
                    <div class="info-row">
                        <div class="info-label">ID</div>
                        <div class="info-value">${node.id}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">创建时间</div>
                        <div class="info-value">${node.created_at || 'N/A'}</div>
                    </div>
                `;

                if (node.importance !== undefined) {
                    const importancePercent = Math.round(node.importance * 100);
                    html += `
                        <div class="info-row">
                            <div class="info-label">重要性</div>
                            <div class="info-value">
                                <div style="background: #e9ecef; border-radius: 10px; height: 20px; overflow: hidden;">
                                    <div style="background: linear-gradient(90deg, #667eea, #764ba2); width: ${importancePercent}%; height: 100%;"></div>
                                </div>
                                <div style="margin-top: 5px; font-size: 12px;">${importancePercent}%</div>
                            </div>
                        </div>
                    `;
                }

                if (node.L0_text) {
                    html += `
                        <div class="info-row">
                            <div class="info-label">L0 摘要</div>
                            <div class="info-value long-text">${node.L0_text}</div>
                        </div>
                    `;
                }

                if (node.L1_text) {
                    html += `
                        <div class="info-row">
                            <div class="info-label">L1 深层语义</div>
                            <div class="info-value long-text">${node.L1_text}</div>
                        </div>
                    `;
                }

                if (node.L2_text) {
                    html += `
                        <div class="info-row">
                            <div class="info-label">L2 隐性含义</div>
                            <div class="info-value long-text">${node.L2_text}</div>
                        </div>
                    `;
                }

            } else if (node.type === 'entity') {
                html += `
                    <div class="info-row">
                        <div class="info-label">实体名称</div>
                        <div class="info-value">${node.label}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">实体类型</div>
                        <div class="info-value">${node.entity_type || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">置信度</div>
                        <div class="info-value">${(node.confidence || 0).toFixed(2)}</div>
                    </div>
                `;

                if (node.properties) {
                    const props = Object.entries(node.properties);
                    if (props.length > 0) {
                        html += `
                            <div class="info-row">
                                <div class="info-label">属性</div>
                                <div class="info-value long-text">
                        `;
                        props.forEach(([key, value]) => {
                            html += `<div><strong>${key}:</strong> ${value}</div>`;
                        });
                        html += `
                                </div>
                            </div>
                        `;
                    }
                }
            }

            // 显示连接的边
            const connectedEdges = allEdges.filter(e => e.from === nodeId || e.to === nodeId);
            if (connectedEdges.length > 0) {
                html += `
                    <div class="edge-info">
                        <div class="info-label">连接关系 (${connectedEdges.length})</div>
                        <div class="edge-list">
                `;

                connectedEdges.forEach(edge => {
                    const otherNodeId = edge.from === nodeId ? edge.to : edge.from;
                    const otherNode = allNodes.find(n => n.id === otherNodeId);
                    const otherNodeLabel = otherNode ? otherNode.label : otherNodeId;

                    html += `
                        <div class="edge-item">
                            <div class="edge-type">${edge.label || edge.type}</div>
                            <div class="edge-weight">
                                ${edge.from === nodeId ? '→' : '←'} ${otherNodeLabel}
                                ${edge.weight !== undefined ? ` | 权重: ${(edge.weight * 100).toFixed(1)}%` : ''}
                            </div>
                        </div>
                    `;
                });

                html += `
                        </div>
                    </div>
                `;
            }

            content.innerHTML = html;
            infoPanel.classList.add('active');
        }

        // 关闭节点信息
        function closeNodeInfo() {
            document.getElementById('node-info').classList.remove('active');
        }

        // 重置视图
        function resetView() {
            network.fit({
                animation: true
            });
        }

        // 刷新数据
        function refreshData() {
            loadData();
        }

        // 过滤器事件监听
        document.getElementById('show-experiences').addEventListener('change', applyFilters);
        document.getElementById('show-entities').addEventListener('change', applyFilters);
        document.getElementById('show-dreams').addEventListener('change', applyFilters);

        // 初始化
        document.addEventListener('DOMContentLoaded', function() {
            initNetwork();
            loadData();
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """主页"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/data')
def get_data():
    """获取网络图数据"""

    # 获取体验节点
    experiences = experience_store.get_all()
    exp_nodes = []
    for exp in experiences:
        # 判断是否为梦境节点
        is_dream = exp.id.startswith('dream_')
        node_type = 'dream' if is_dream else 'experience'

        node = {
            'id': exp.id,
            'label': exp.L0_text[:50] + '...' if len(exp.L0_text or '') > 50 else (exp.L0_text or exp.id),
            'type': 'experience',
            'subtype': node_type,
            'title': f"类型: {node_type}\n重要性: {exp.importance or 0:.2f}\n创建: {exp.created_at or 'N/A'}",
            'color': colors[node_type],
            'size': 20 + (exp.importance or 0) * 15,
            'L0_text': exp.L0_text,
            'L1_text': exp.L1_text,
            'L2_text': exp.L2_text,
            'importance': exp.importance,
            'created_at': exp.created_at
        }
        exp_nodes.append(node)

    # 获取实体节点
    entities = entity_store.get_all()
    entity_nodes = []
    for entity in entities:
        node = {
            'id': entity.id,
            'label': entity.name,
            'type': 'entity',
            'subtype': 'normal',
            'title': f"实体: {entity.name}\n类型: {entity.type or 'N/A'}\n置信度: {entity.confidence or 0:.2f}",
            'color': colors['entity'],
            'size': 15 + (entity.confidence or 0) * 10,
            'entity_type': entity.type,
            'confidence': entity.confidence,
            'properties': entity.properties
        }
        entity_nodes.append(node)

    # 获取体验边
    exp_edges = experience_edge_store.get_all()
    edge_list = []
    exp_ids = {e['id'] for e in exp_nodes}

    for edge in exp_edges:
        is_experience_edge = edge.from_id in exp_ids or edge.to_id in exp_ids

        edge_list.append({
            'from': edge.from_id,
            'to': edge.to_id,
            'type': edge.type,
            'label': edge.type,
            'weight': edge.weight,
            'title': f"类型: {edge.type}\n权重: {edge.weight:.2f}",
            'is_experience_edge': is_experience_edge
        })

    # 获取实体边
    entity_edges = entity_edge_store.get_all()
    entity_ids = {e['id'] for e in entity_nodes}

    for edge in entity_edges:
        is_entity_edge = edge.from_id in entity_ids or edge.to_id in entity_ids

        edge_list.append({
            'from': edge.from_id,
            'to': edge.to_id,
            'type': edge.relation,
            'label': edge.relation,
            'weight': edge.confidence,
            'title': f"关系: {edge.relation}\n置信度: {edge.confidence:.2f}",
            'is_entity_edge': is_entity_edge
        })

    # 统计信息
    exp_edges_list = [e for e in edge_list if e.get('is_experience_edge', False)]
    entity_edges_list = [e for e in edge_list if e.get('is_entity_edge', False)]

    stats = {
        'experience_count': len(exp_nodes),
        'entity_count': len(entity_nodes),
        'experience_edge_count': len(exp_edges_list),
        'entity_edge_count': len(entity_edges_list)
    }

    return jsonify({
        'nodes': exp_nodes + entity_nodes,
        'edges': edge_list,
        'stats': stats
    })


def main():
    """启动服务器"""
    print("=" * 60)
    print("记忆库可视化服务器")
    print("=" * 60)
    print()
    print("服务信息:")
    print(f"  - 访问地址: http://localhost:5000")
    print(f"  - 体验节点: {len(experience_store.get_all())}")
    print(f"  - 实体节点: {len(entity_store.get_all())}")
    print(f"  - 体验边: {len(experience_edge_store.get_all())}")
    print(f"  - 实体边: {len(entity_edge_store.get_all())}")
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    print()

    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
