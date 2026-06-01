"""Self-contained HTML replay page from agent conversation logs.

Reads agent conversations from {session}/_index/agents/{agent_name}/conversation.jsonl
and generates a single HTML file with timeline playback, agent proposal cards,
and phase navigation. Zero external dependencies.

Inspired by claude-replay's self-contained HTML approach.
"""

from __future__ import annotations

import json
import base64
import zlib
from pathlib import Path
from datetime import datetime
from typing import Any


def build_replay_html(session_dir: Path, output_path: Path | None = None) -> str:
    """Generate a self-contained HTML replay page from agent conversations.

    Args:
        session_dir: Path to session workspace (contains _index/agents/)
        output_path: If provided, write HTML to this file

    Returns:
        Complete HTML string
    """
    agents_dir = session_dir / "_index" / "agents"
    if not agents_dir.exists():
        return _empty_html("No agent conversations found")

    # Collect all agent conversations
    agents_data = {}
    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        conv_path = agent_dir / "conversation.jsonl"
        meta_path = agent_dir / "meta.json"
        if not conv_path.exists():
            continue

        turns = []
        with open(str(conv_path), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        agents_data[agent_dir.name] = {
            "turns": turns,
            "meta": meta,
        }

    if not agents_data:
        return _empty_html("No agent conversations found")

    # Read pipeline state for phase info
    pipeline_state = {}
    ps_path = session_dir / "PIPELINE_STATE.json"
    if ps_path.exists():
        try:
            pipeline_state = json.loads(ps_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Build JSON data for embedding
    replay_data = {
        "session_id": session_dir.name,
        "research_topic": pipeline_state.get("research_topic", ""),
        "phase": pipeline_state.get("phase", ""),
        "iteration": pipeline_state.get("iteration", 0),
        "agents": agents_data,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Embed directly (conversation logs are typically < 200KB)
    json_str = json.dumps(replay_data, ensure_ascii=False, default=str)

    html = _REPLAY_TEMPLATE.replace("__REPLAY_DATA__", json_str)

    if output_path:
        output_path.write_text(html, encoding="utf-8")

    return html


def _empty_html(message: str) -> str:
    return f"<!DOCTYPE html><html><body><h1>EvoScientist Session Replay</h1><p>{message}</p></body></html>"


# ── Self-contained HTML template ──

_REPLAY_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EvoScientist Session Replay</title>
<style>
:root {
  --bg: #1a1a2e; --surface: #16213e; --border: #0f3460;
  --text: #e0e0e0; --dim: #8892b0; --accent: #64ffda; --warn: #ffd700;
  --method: #00bcd4; --fact: #4caf50; --component: #ff9800; --proposal: #e91e63;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
header { background: var(--surface); padding: 16px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
header h1 { font-size: 1.2em; color: var(--accent); }
header .meta { color: var(--dim); font-size: 0.85em; }
.container { display: grid; grid-template-columns: 280px 1fr; min-height: calc(100vh - 70px); }
.sidebar { background: var(--surface); padding: 16px; border-right: 1px solid var(--border); overflow-y: auto; }
.sidebar h3 { color: var(--accent); margin-bottom: 8px; font-size: 0.9em; }
.agent-card { padding: 10px; margin-bottom: 8px; border-radius: 6px; background: rgba(255,255,255,0.03); cursor: pointer; border: 1px solid transparent; transition: .15s; }
.agent-card:hover { border-color: var(--accent); }
.agent-card.active { border-color: var(--accent); background: rgba(100,255,218,0.05); }
.agent-card .name { font-weight: 600; font-size: 0.9em; }
.agent-card .stats { font-size: 0.75em; color: var(--dim); margin-top: 4px; }
.main { padding: 24px; overflow-y: auto; }
.timeline-bar { position: sticky; top: 0; background: var(--surface); padding: 8px 16px; border-radius: 8px; margin-bottom: 16px; display: flex; gap: 4px; overflow-x: auto; }
.timeline-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; cursor: pointer; transition: .15s; }
.timeline-dot.active { transform: scale(1.5); box-shadow: 0 0 8px var(--accent); }
.turn { margin-bottom: 20px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.turn-header { background: var(--surface); padding: 10px 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.turn-header:hover { background: rgba(255,255,255,0.05); }
.turn-header .phase { color: var(--dim); font-size: 0.8em; }
.turn-header .time { color: var(--dim); font-size: 0.75em; }
.turn-body { padding: 16px; }
.prompt-box { background: rgba(255,255,255,0.03); border-radius: 6px; padding: 12px; margin-bottom: 12px; max-height: 400px; overflow-y: auto; }
.prompt-box pre { white-space: pre-wrap; font-size: 0.85em; color: var(--dim); }
.response-box { background: rgba(100,255,218,0.03); border-radius: 6px; padding: 12px; }
.proposal-card { background: var(--surface); border-radius: 8px; padding: 16px; margin-bottom: 12px; border-left: 3px solid var(--proposal); }
.proposal-card .p-title { font-weight: 700; color: var(--accent); margin-bottom: 8px; }
.proposal-card .p-hypothesis { font-size: 0.9em; color: var(--text); margin-bottom: 8px; }
.proposal-card .p-sketch { font-size: 0.85em; color: var(--dim); max-height: 200px; overflow-y: auto; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; }
.controls { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 8px; }
.controls button { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.85em; }
.controls button:hover { border-color: var(--accent); }
.toggle-btn { font-size: 0.8em; color: var(--accent); cursor: pointer; }
.empty-state { text-align: center; padding: 40px; color: var(--dim); }
</style>
</head>
<body>
<header>
  <div><h1 id="title">Session Replay</h1><span class="meta" id="meta-info"></span></div>
  <div><span class="meta" id="phase-badge"></span></div>
</header>
<div class="container">
  <aside class="sidebar" id="sidebar"></aside>
  <main class="main" id="main">
    <div class="timeline-bar" id="timeline"></div>
    <div id="content"></div>
  </main>
</div>
<div class="controls">
  <button onclick="scrollToTop()">Top</button>
  <button onclick="toggleAll()">Expand/Collapse</button>
</div>
<script>
const DATA = __REPLAY_DATA__;
let activeAgent = null;

function init() {
  const data = DATA;
  document.getElementById('title').textContent = data.research_topic || 'Session Replay';
  document.getElementById('meta-info').textContent = `Session: ${data.session_id} | Phase: ${data.phase} | ${data.generated_at}`;
  document.getElementById('phase-badge').textContent = data.phase || '';

  const agents = data.agents;
  const agentNames = Object.keys(agents);
  if (agentNames.length === 0) {
    document.getElementById('content').innerHTML = '<div class="empty-state">No agent data</div>';
    return;
  }

  // Build sidebar
  const sidebar = document.getElementById('sidebar');
  sidebar.innerHTML = '<h3>Agents</h3>';
  for (const name of agentNames) {
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.innerHTML = `<div class="name">${name}</div><div class="stats">${agents[name].turns.length} turns | ${agents[name].meta.call_count || 0} calls</div>`;
    card.onclick = () => selectAgent(name, agents[name]);
    if (!activeAgent) { activeAgent = name; card.classList.add('active'); }
    sidebar.appendChild(card);
  }

  if (activeAgent) selectAgent(activeAgent, agents[activeAgent]);
}

function selectAgent(name, agentData) {
  activeAgent = name;
  document.querySelectorAll('.agent-card').forEach(c => c.classList.remove('active'));
  event.target.closest('.agent-card')?.classList.add('active');

  const turns = agentData.turns;
  const timeline = document.getElementById('timeline');
  const content = document.getElementById('content');

  // Timeline dots
  timeline.innerHTML = turns.map((t, i) =>
    `<div class="timeline-dot" style="background: ${phaseColor(t.phase)}" title="#${i+1}: ${t.phase || 'unknown'}" onclick="scrollToTurn(${i})"></div>`
  ).join('');

  // Turns
  content.innerHTML = turns.map((t, i) => {
    const parsed = t.parsed || {};
    const hasProposal = parsed.title && (parsed.hypothesis || parsed.method_sketch);
    return `
    <div class="turn" id="turn-${i}">
      <div class="turn-header" onclick="toggleTurn(${i})">
        <span><strong>#${i+1}</strong> <span class="phase">${t.phase || ''}</span></span>
        <span class="time">${(t.timestamp || '').substring(0,19)}</span>
      </div>
      <div class="turn-body" id="turn-body-${i}">
        ${hasProposal ? `
        <div class="proposal-card">
          <div class="p-title">${esc(parsed.title)}</div>
          <div class="p-hypothesis">${esc(parsed.hypothesis || '')}</div>
          <div class="p-sketch"><pre>${esc((parsed.method_sketch || '').substring(0,2000))}</pre></div>
        </div>` : ''}
        <div class="toggle-btn" onclick="event.stopPropagation(); togglePrompt(${i})">Show prompt (${(t.prompt || '').length} chars)</div>
        <div class="prompt-box" id="prompt-${i}" style="display:none"><pre>${esc(t.prompt || '')}</pre></div>
      </div>
    </div>`;
  }).join('');
}

function toggleTurn(i) { const b = document.getElementById('turn-body-'+i); b.style.display = b.style.display === 'none' ? '' : 'none'; }
function togglePrompt(i) { const b = document.getElementById('prompt-'+i); b.style.display = b.style.display === 'none' ? '' : 'none'; }
function scrollToTurn(i) { document.getElementById('turn-'+i)?.scrollIntoView({behavior:'smooth',block:'start'}); }
function scrollToTop() { window.scrollTo({top:0,behavior:'smooth'}); }
function toggleAll() {
  const bodies = document.querySelectorAll('.turn-body');
  const anyVisible = Array.from(bodies).some(b => b.style.display !== 'none');
  bodies.forEach(b => b.style.display = anyVisible ? 'none' : '');
}

function esc(s) { return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function phaseColor(p) {
  const colors = {'W2 问题分析':'#ff9800','W3 方案方向':'#ff5722','W4 具体方案生成':'#4caf50','W5 代码实现':'#00bcd4','W6 结果分析':'#2196f3','W7 论文写作':'#9c27b0','W8 审阅':'#e91e63'};
  return colors[p] || '#666';
}

init();
</script>
</body>
</html>"""


def serve_replay_endpoint(session_dir: str) -> str:
    """Convenience: generate replay HTML for a session directory path."""
    return build_replay_html(Path(session_dir))
