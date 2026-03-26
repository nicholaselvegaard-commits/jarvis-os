"""
JARVIS Brain Cloud — Interaktiv hjernevisualisering.
Iron Man-stil holografisk graf over alt Jarvis vet.

Port 8085 (nginx proxy: 8086)
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv("/opt/nexus/.env")
sys.path.insert(0, "/opt/nexus")

logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _brain():
    from memory.brain import Brain
    return Brain()


def _kg():
    return _brain().kg


# ── API ────────────────────────────────────────────────────────────────────────

@app.route("/api/graph")
def api_graph():
    """Full KG som nodes + edges for D3."""
    try:
        kg = _kg()
        raw_nodes = kg.get_all_nodes(limit=200)
        nodes = []
        for n in raw_nodes:
            nodes.append({
                "id":         n["id"],
                "label":      n["label"],
                "type":       n["type"],
                "importance": n["importance"],
                "attrs":      n.get("attrs", {}),
            })

        # Hent alle edges
        rows = kg.conn.execute(
            "SELECT from_id, to_id, relation, confidence FROM edges LIMIT 500"
        ).fetchall()
        edges = [
            {"source": r[0], "target": r[1], "relation": r[2], "confidence": r[3]}
            for r in rows
            if any(n["id"] == r[0] for n in nodes) and any(n["id"] == r[1] for n in nodes)
        ]

        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        return jsonify({"error": str(e), "nodes": [], "edges": []}), 500


@app.route("/api/memories")
def api_memories():
    """Siste vector-minner."""
    try:
        b = _brain()
        if not b.vector:
            return jsonify({"memories": []})
        q = request.args.get("q", "jarvis norway AI agent")
        k = int(request.args.get("k", 20))
        results = b.vector.search(q, k=k)
        return jsonify({"memories": results})
    except Exception as e:
        return jsonify({"error": str(e), "memories": []}), 500


@app.route("/api/notes")
def api_notes():
    """Obsidian vault notater."""
    try:
        b = _brain()
        if not b.obsidian:
            return jsonify({"notes": []})
        folder = request.args.get("folder", "")
        notes = b.obsidian.list_notes(folder if folder else None)
        return jsonify({"notes": notes[:50]})
    except Exception as e:
        return jsonify({"error": str(e), "notes": []}), 500


@app.route("/api/status")
def api_status():
    """Brain system status."""
    try:
        b = _brain()
        s = b.status()
        return jsonify(s)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/remember", methods=["POST"])
def api_remember():
    """Lagre ny memory i brain (vector + KG)."""
    data = request.json or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Mangler content"}), 400
    try:
        b = _brain()
        b.remember(
            content,
            category=data.get("category", "insight"),
            tags=data.get("tags", []),
            importance=int(data.get("importance", 1)),
        )
        return jsonify({"ok": True, "stored": content[:80]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/know", methods=["POST"])
def api_know():
    """Legg til node i KG."""
    data = request.json or {}
    node_id = data.get("node_id", "").strip().lower().replace(" ", "_")
    label = data.get("label", data.get("node_id", "")).strip()
    if not node_id:
        return jsonify({"error": "Mangler node_id"}), 400
    try:
        b = _brain()
        b.know(
            node_id,
            node_type=data.get("type", "concept"),
            attrs={k: v for k, v in data.items() if k not in ("node_id", "label", "type", "importance")},
            importance=int(data.get("importance", 1)),
        )
        # Oppdater label separat
        if label and label != node_id:
            b.kg.add_node(node_id, label=label, type=data.get("type", "concept"),
                          importance=int(data.get("importance", 1)))
        return jsonify({"ok": True, "node_id": node_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/relate", methods=["POST"])
def api_relate():
    """Legg til kant mellom to noder."""
    data = request.json or {}
    from_id = data.get("from_id", "").strip()
    to_id = data.get("to_id", "").strip()
    relation = data.get("relation", "relatert_til").strip()
    if not from_id or not to_id:
        return jsonify({"error": "Mangler from_id eller to_id"}), 400
    try:
        b = _brain()
        b.relate(from_id, to_id, relation)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/search")
def api_search():
    """Søk på tvers av alt."""
    q = request.args.get("q", "")
    if not q:
        return jsonify({"results": []})
    try:
        b = _brain()
        ctx = b.get_context(q)
        kg_nodes = b.kg.search_nodes(q, limit=10)
        return jsonify({"context": ctx, "nodes": kg_nodes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── HTML ───────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JARVIS — Brain Cloud</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root {
    --bg: #040d1a;
    --panel: #080f20;
    --border: #0d2545;
    --cyan: #00d4ff;
    --cyan2: #00a8cc;
    --green: #00ff88;
    --orange: #ff8c00;
    --red: #ff3366;
    --dim: #1a3a5c;
    --text: #8ab4cc;
    --text-bright: #c8e8f8;
    --font: 'JetBrains Mono', 'Courier New', monospace;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    height: 100vh;
    overflow: hidden;
    display: grid;
    grid-template-rows: 52px 1fr;
    grid-template-columns: 1fr 340px;
  }

  /* Animated grid overlay */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  /* Header */
  header {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    padding: 0 20px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    z-index: 10;
    gap: 20px;
  }
  .logo {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 4px;
    color: var(--cyan);
    text-shadow: 0 0 20px var(--cyan), 0 0 40px var(--cyan2);
  }
  .logo span { color: var(--text); font-weight: 400; }
  .pulse-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 10px var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.8); }
  }
  .stats-bar {
    display: flex; gap: 24px; margin-left: auto;
    font-size: 11px; letter-spacing: 1px;
  }
  .stat { display: flex; flex-direction: column; align-items: center; }
  .stat-val { color: var(--cyan); font-size: 16px; font-weight: 700; text-shadow: 0 0 8px var(--cyan); }
  .stat-lbl { color: var(--dim); font-size: 10px; text-transform: uppercase; }

  /* Main graph area */
  #graph-area {
    position: relative;
    overflow: hidden;
    z-index: 1;
  }
  svg#graph { width: 100%; height: 100%; }

  /* Sidebar */
  #sidebar {
    background: var(--panel);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1;
  }

  .tab-bar {
    display: flex;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .tab {
    flex: 1;
    padding: 10px 4px;
    text-align: center;
    cursor: pointer;
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--dim);
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--cyan); border-bottom-color: var(--cyan); text-shadow: 0 0 8px var(--cyan); }

  .panel { display: none; flex-direction: column; flex: 1; overflow: hidden; padding: 16px; }
  .panel.active { display: flex; }

  /* Node detail */
  #node-detail {
    background: rgba(0,212,255,0.04);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 12px;
    flex-shrink: 0;
    min-height: 80px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  #node-detail h3 { color: var(--cyan); font-size: 14px; }
  #node-detail .node-type { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--dim); }
  #node-detail .node-attrs { font-size: 11px; color: var(--text); line-height: 1.7; overflow-y: auto; max-height: 100px; }
  #node-detail.empty::after { content: 'Klikk på en node'; color: var(--dim); font-size: 11px; letter-spacing: 1px; }

  /* Memories list */
  #memories-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .memory-card {
    background: rgba(0,212,255,0.03);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px;
    cursor: default;
    transition: border-color 0.2s;
  }
  .memory-card:hover { border-color: var(--cyan2); }
  .memory-cat {
    font-size: 9px; letter-spacing: 2px; text-transform: uppercase;
    color: var(--orange); margin-bottom: 4px;
  }
  .memory-content { font-size: 11px; color: var(--text-bright); line-height: 1.6; }

  /* Add memory form */
  .add-form {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .add-form h4 {
    font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
    color: var(--dim); margin-bottom: 4px;
  }
  input, textarea, select {
    background: rgba(0,0,0,0.4);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-bright);
    font-family: var(--font);
    font-size: 12px;
    padding: 8px 10px;
    width: 100%;
    outline: none;
    transition: border-color 0.2s;
  }
  input:focus, textarea:focus, select:focus { border-color: var(--cyan2); }
  textarea { resize: vertical; min-height: 60px; }
  select option { background: var(--panel); }
  .row { display: flex; gap: 8px; }
  .row > * { flex: 1; }

  button {
    background: rgba(0,212,255,0.1);
    border: 1px solid var(--cyan2);
    border-radius: 4px;
    color: var(--cyan);
    cursor: pointer;
    font-family: var(--font);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 9px 14px;
    text-transform: uppercase;
    transition: all 0.2s;
    width: 100%;
  }
  button:hover {
    background: rgba(0,212,255,0.2);
    box-shadow: 0 0 12px rgba(0,212,255,0.3);
    text-shadow: 0 0 8px var(--cyan);
  }
  button.danger { border-color: var(--red); color: var(--red); background: rgba(255,51,102,0.08); }
  button.green  { border-color: var(--green); color: var(--green); background: rgba(0,255,136,0.06); }

  .ok-msg { color: var(--green); font-size: 11px; text-align: center; display: none; }
  .ok-msg.show { display: block; }

  /* Notes list */
  #notes-list { flex: 1; overflow-y: auto; }
  .note-item {
    padding: 8px 10px;
    border-bottom: 1px solid rgba(13,37,69,0.6);
    cursor: pointer;
    font-size: 11px;
    color: var(--text);
    transition: background 0.15s;
  }
  .note-item:hover { background: rgba(0,212,255,0.05); color: var(--cyan); }

  /* Search */
  .search-wrap { position: relative; }
  #search-box {
    padding-left: 28px;
  }
  .search-icon { position: absolute; left: 10px; top: 9px; color: var(--dim); font-size: 12px; }
  #search-results {
    flex: 1; overflow-y: auto;
    display: flex; flex-direction: column; gap: 6px;
    padding-top: 10px;
  }
  .search-result {
    background: rgba(0,212,255,0.03);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px;
  }
  .search-result .sr-label { color: var(--cyan); font-size: 12px; font-weight: 700; }
  .search-result .sr-type { font-size: 9px; letter-spacing: 2px; color: var(--dim); text-transform: uppercase; }
  .search-result .sr-body { font-size: 11px; color: var(--text); margin-top: 4px; line-height: 1.5; }

  /* Type colors */
  .type-person   { stroke: #4488ff !important; fill: #4488ff !important; }
  .type-company  { stroke: #00d4ff !important; fill: #00d4ff !important; }
  .type-concept  { stroke: #aa66ff !important; fill: #aa66ff !important; }
  .type-product  { stroke: #00ff88 !important; fill: #00ff88 !important; }
  .type-place    { stroke: #ff8c00 !important; fill: #ff8c00 !important; }
  .type-tool     { stroke: #ffdd00 !important; fill: #ffdd00 !important; }

  /* Tooltip */
  #tooltip {
    position: fixed;
    background: var(--panel);
    border: 1px solid var(--cyan2);
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 11px;
    pointer-events: none;
    z-index: 100;
    display: none;
    max-width: 220px;
    box-shadow: 0 0 20px rgba(0,212,255,0.2);
  }
  #tooltip h4 { color: var(--cyan); margin-bottom: 4px; }
  #tooltip p  { color: var(--text); line-height: 1.6; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
</head>
<body>

<header>
  <div class="logo">JARVIS <span>/ BRAIN CLOUD</span></div>
  <div class="pulse-dot"></div>
  <div class="stats-bar">
    <div class="stat"><div class="stat-val" id="s-nodes">—</div><div class="stat-lbl">Noder</div></div>
    <div class="stat"><div class="stat-val" id="s-edges">—</div><div class="stat-lbl">Kanter</div></div>
    <div class="stat"><div class="stat-val" id="s-vec">—</div><div class="stat-lbl">Minner</div></div>
    <div class="stat"><div class="stat-val" id="s-notes">—</div><div class="stat-lbl">Notater</div></div>
  </div>
</header>

<div id="graph-area">
  <svg id="graph"></svg>
</div>

<div id="sidebar">
  <div class="tab-bar">
    <div class="tab active" onclick="switchTab('node')">NODE</div>
    <div class="tab" onclick="switchTab('add')">LEGG TIL</div>
    <div class="tab" onclick="switchTab('memories')">MINNER</div>
    <div class="tab" onclick="switchTab('search')">SØK</div>
  </div>

  <!-- NODE panel -->
  <div class="panel active" id="panel-node">
    <div id="node-detail" class="empty"></div>
    <div id="node-related" style="flex:1;overflow-y:auto"></div>
  </div>

  <!-- ADD panel -->
  <div class="panel" id="panel-add">
    <div style="flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:16px">

      <!-- Add memory -->
      <div>
        <h4 style="color:var(--dim);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">
          ◈ Ny Hukommelse (Vector + KG)
        </h4>
        <div style="display:flex;flex-direction:column;gap:8px">
          <textarea id="mem-content" placeholder="Hva skal Jarvis huske?"></textarea>
          <div class="row">
            <select id="mem-cat">
              <option value="insight">Innsikt</option>
              <option value="lead">Lead</option>
              <option value="strategy">Strategi</option>
              <option value="learning">Lærdom</option>
              <option value="contact">Kontakt</option>
              <option value="project">Prosjekt</option>
              <option value="revenue">Inntekt</option>
              <option value="task">Oppgave</option>
            </select>
            <select id="mem-imp">
              <option value="1">Normal (1)</option>
              <option value="2">Viktig (2)</option>
              <option value="3">Kritisk (3)</option>
            </select>
          </div>
          <button class="green" onclick="addMemory()">⬡ HUSK DETTE</button>
          <div class="ok-msg" id="mem-ok">Lagret i hjernen ✓</div>
        </div>
      </div>

      <!-- Add KG node -->
      <div>
        <h4 style="color:var(--dim);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">
          ◈ Ny KG-node
        </h4>
        <div style="display:flex;flex-direction:column;gap:8px">
          <input id="node-label" placeholder="Navn / Label">
          <div class="row">
            <select id="node-type">
              <option value="person">Person</option>
              <option value="company">Bedrift</option>
              <option value="concept">Konsept</option>
              <option value="product">Produkt</option>
              <option value="place">Sted</option>
              <option value="tool">Verktøy</option>
              <option value="project">Prosjekt</option>
            </select>
            <select id="node-imp">
              <option value="1">Normal</option>
              <option value="2">Viktig</option>
              <option value="3">Kritisk</option>
            </select>
          </div>
          <textarea id="node-desc" placeholder="Beskrivelse / notater om denne (valgfritt)" style="min-height:48px"></textarea>
          <button onclick="addNode()">⬡ LEGG TIL NODE</button>
          <div class="ok-msg" id="node-ok">Node lagt til ✓</div>
        </div>
      </div>

      <!-- Add edge -->
      <div>
        <h4 style="color:var(--dim);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">
          ◈ Ny relasjon
        </h4>
        <div style="display:flex;flex-direction:column;gap:8px">
          <input id="edge-from" placeholder="Fra node ID (f.eks. nicholas)">
          <input id="edge-rel"  placeholder="Relasjon (f.eks. eier, jobber_for, kjenner)">
          <input id="edge-to"   placeholder="Til node ID">
          <button onclick="addEdge()">⬡ KOBLE NODER</button>
          <div class="ok-msg" id="edge-ok">Kobling lagt til ✓</div>
        </div>
      </div>
    </div>
  </div>

  <!-- MEMORIES panel -->
  <div class="panel" id="panel-memories">
    <div id="memories-list"></div>
  </div>

  <!-- SEARCH panel -->
  <div class="panel" id="panel-search">
    <div class="search-wrap">
      <span class="search-icon">⌕</span>
      <input id="search-box" placeholder="Søk i Jarvis sin hjerne..." oninput="debounceSearch()">
    </div>
    <div id="search-results"></div>
  </div>
</div>

<div id="tooltip"><h4 id="tt-label"></h4><p id="tt-body"></p></div>

<script>
const API = '';  // same origin

// ── D3 Graph ─────────────────────────────────────────────────────────────────

const TYPE_COLORS = {
  person:  '#4488ff',
  company: '#00d4ff',
  concept: '#aa66ff',
  product: '#00ff88',
  place:   '#ff8c00',
  tool:    '#ffdd00',
  project: '#ff6688',
  default: '#668899',
};

function nodeColor(t) { return TYPE_COLORS[t] || TYPE_COLORS.default; }
function nodeRadius(imp) { return 6 + imp * 5; }

let simulation, svg, nodeEl, linkEl, labelEl;
let graphData = { nodes: [], edges: [] };
let selectedNode = null;

function initGraph() {
  svg = d3.select('#graph');
  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;

  // Defs for glow
  const defs = svg.append('defs');
  ['cyan','blue','green','orange'].forEach((name, i) => {
    const colors = ['#00d4ff','#4488ff','#00ff88','#ff8c00'];
    const f = defs.append('filter').attr('id', 'glow-'+name);
    f.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    const merge = f.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');
  });

  const g = svg.append('g').attr('class', 'main');

  // Zoom
  svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

  linkEl  = g.append('g').attr('class', 'links');
  nodeEl  = g.append('g').attr('class', 'nodes');
  labelEl = g.append('g').attr('class', 'labels');

  simulation = d3.forceSimulation()
    .force('link', d3.forceLink().id(d => d.id).distance(120).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => nodeRadius(d.importance) + 12));
}

function renderGraph(data) {
  const { nodes, edges } = data;

  linkEl.selectAll('line').remove();
  nodeEl.selectAll('circle').remove();
  labelEl.selectAll('text').remove();

  const link = linkEl.selectAll('line').data(edges).enter().append('line')
    .attr('stroke', 'rgba(0,212,255,0.2)')
    .attr('stroke-width', d => 1 + (d.confidence || 0.5))
    .style('filter', 'url(#glow-cyan)');

  const node = nodeEl.selectAll('circle').data(nodes).enter().append('circle')
    .attr('r', d => nodeRadius(d.importance))
    .attr('fill', d => nodeColor(d.type) + '22')
    .attr('stroke', d => nodeColor(d.type))
    .attr('stroke-width', 1.5)
    .style('cursor', 'pointer')
    .style('filter', d => d.importance >= 2 ? 'url(#glow-cyan)' : 'none')
    .on('click', (e, d) => showNodeDetail(d))
    .on('mouseover', (e, d) => showTooltip(e, d))
    .on('mouseout', hideTooltip)
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  // Pulse for importance=3
  node.filter(d => d.importance >= 3).append('animate')
    .attr('attributeName', 'r')
    .attr('values', d => `${nodeRadius(d.importance)};${nodeRadius(d.importance)+4};${nodeRadius(d.importance)}`)
    .attr('dur', '2s').attr('repeatCount', 'indefinite');

  const label = labelEl.selectAll('text').data(nodes).enter().append('text')
    .text(d => d.label.length > 18 ? d.label.slice(0,16)+'…' : d.label)
    .attr('font-size', d => 9 + d.importance)
    .attr('font-family', 'JetBrains Mono, monospace')
    .attr('fill', d => nodeColor(d.type))
    .attr('text-anchor', 'middle')
    .attr('dy', d => nodeRadius(d.importance) + 14)
    .style('pointer-events', 'none')
    .style('opacity', 0.8);

  simulation.nodes(nodes).on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('cx', d => d.x).attr('cy', d => d.y);
    label.attr('x', d => d.x).attr('y', d => d.y);
  });

  simulation.force('link').links(edges);
  simulation.alpha(1).restart();
}

function showTooltip(event, d) {
  const tt = document.getElementById('tooltip');
  document.getElementById('tt-label').textContent = d.label;
  const attrs = d.attrs || {};
  const parts = [];
  if (attrs.city) parts.push('By: ' + attrs.city);
  if (attrs.employees) parts.push('Ansatte: ' + attrs.employees);
  if (attrs.score) parts.push('Score: ' + attrs.score + '/10');
  document.getElementById('tt-body').textContent = `[${d.type}]` + (parts.length ? '\n' + parts.join(' · ') : '');
  tt.style.display = 'block';
  tt.style.left = (event.clientX + 14) + 'px';
  tt.style.top  = (event.clientY - 10) + 'px';
}
function hideTooltip() { document.getElementById('tooltip').style.display = 'none'; }

function showNodeDetail(d) {
  selectedNode = d;
  const det = document.getElementById('node-detail');
  det.classList.remove('empty');
  const attrs = d.attrs || {};
  const attrLines = Object.entries(attrs)
    .filter(([k]) => !['found_date'].includes(k))
    .map(([k,v]) => `<span style="color:var(--dim)">${k}:</span> ${v}`)
    .join('<br>');
  det.innerHTML = `
    <div class="node-type">[${d.type}] imp=${d.importance}</div>
    <h3>${d.label}</h3>
    <div class="node-attrs">${attrLines || '<span style="color:var(--dim)">Ingen ekstra data</span>'}</div>
    <div style="margin-top:6px;font-size:10px;color:var(--dim)">id: ${d.id}</div>
  `;
  // Pre-fill edge form
  document.getElementById('edge-from').value = d.id;
}

// ── Tabs ─────────────────────────────────────────────────────────────────────

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    const names = ['node','add','memories','search'];
    t.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
  if (name === 'memories') loadMemories();
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function loadGraph() {
  const r = await fetch(API + '/api/graph');
  graphData = await r.json();
  renderGraph(graphData);
  document.getElementById('s-nodes').textContent = graphData.nodes.length;
  document.getElementById('s-edges').textContent = graphData.edges.length;
}

async function loadStatus() {
  const r = await fetch(API + '/api/status');
  const s = await r.json();
  const vm = s.vector_memory || {};
  const obs = s.obsidian || {};
  document.getElementById('s-vec').textContent   = vm.count || '—';
  document.getElementById('s-notes').textContent = obs.total_notes || '—';
}

async function loadMemories() {
  const r = await fetch(API + '/api/memories?q=jarvis+norway+AI&k=30');
  const d = await r.json();
  const list = document.getElementById('memories-list');
  list.innerHTML = (d.memories || []).map(m => `
    <div class="memory-card">
      <div class="memory-cat">${m.category || 'ukjent'}</div>
      <div class="memory-content">${(m.content || '').slice(0, 140)}</div>
    </div>
  `).join('');
}

async function addMemory() {
  const content = document.getElementById('mem-content').value.trim();
  if (!content) return;
  const body = {
    content,
    category: document.getElementById('mem-cat').value,
    importance: +document.getElementById('mem-imp').value,
  };
  const r = await fetch(API + '/api/remember', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
  });
  const d = await r.json();
  if (d.ok) {
    document.getElementById('mem-content').value = '';
    flash('mem-ok');
    setTimeout(() => { loadGraph(); loadStatus(); }, 1500);
  }
}

async function addNode() {
  const label = document.getElementById('node-label').value.trim();
  if (!label) return;
  const desc = document.getElementById('node-desc').value.trim();
  const body = {
    node_id: label.toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,''),
    label,
    type: document.getElementById('node-type').value,
    importance: +document.getElementById('node-imp').value,
  };
  if (desc) body.description = desc;
  const r = await fetch(API + '/api/know', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
  });
  const d = await r.json();
  if (d.ok) {
    document.getElementById('node-label').value = '';
    document.getElementById('node-desc').value = '';
    flash('node-ok');
    setTimeout(loadGraph, 1500);
  }
}

async function addEdge() {
  const from_id   = document.getElementById('edge-from').value.trim();
  const relation  = document.getElementById('edge-rel').value.trim();
  const to_id     = document.getElementById('edge-to').value.trim();
  if (!from_id || !relation || !to_id) return;
  const r = await fetch(API + '/api/relate', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ from_id, to_id, relation })
  });
  const d = await r.json();
  if (d.ok) {
    flash('edge-ok');
    setTimeout(loadGraph, 1500);
  }
}

let searchTimer = null;
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 400);
}

async function doSearch() {
  const q = document.getElementById('search-box').value.trim();
  if (!q) return;
  const r = await fetch(API + '/api/search?q=' + encodeURIComponent(q));
  const d = await r.json();
  const el = document.getElementById('search-results');
  const nodes = d.nodes || [];
  el.innerHTML = nodes.length
    ? nodes.map(n => `
        <div class="search-result" onclick="showNodeDetail(${JSON.stringify(n).replace(/</g,'&lt;')})">
          <div class="sr-label">${n.label}</div>
          <div class="sr-type">[${n.type}] imp=${n.importance}</div>
          <div class="sr-body">${JSON.stringify(n.attrs||{}).slice(0,120)}</div>
        </div>
      `).join('')
    : '<div style="color:var(--dim);font-size:11px;padding:10px">Ingen noder funnet.</div>';
  if (d.context) {
    el.innerHTML += `<div class="search-result" style="margin-top:8px">
      <div class="sr-type">KONTEKST</div>
      <div class="sr-body">${d.context.slice(0,500)}</div>
    </div>`;
  }
}

function flash(id) {
  const el = document.getElementById(id);
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

// ── Init ──────────────────────────────────────────────────────────────────────

window.addEventListener('load', () => {
  initGraph();
  loadGraph();
  loadStatus();
  // Refresh every 30s
  setInterval(() => { loadGraph(); loadStatus(); }, 30000);
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "brain_cloud"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv("BRAIN_CLOUD_PORT", "8085"))
    app.run(host="0.0.0.0", port=port, debug=False)
