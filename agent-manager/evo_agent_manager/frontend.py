"""Single-file HTML dashboard for EvoScientist monitoring."""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EvoScientist Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--dim:#8b949e;--accent:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#1f6feb;--purple:#bc8cff}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}
.header{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;border-bottom:1px solid var(--border);background:var(--surface);min-height:40px}
.header h1{font-size:14px;font-weight:600;color:var(--accent)}
.header .meta{font-size:12px;color:var(--dim);display:flex;gap:12px;align-items:center}
.header select{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:12px}
.btn{padding:2px 10px;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--dim);font-size:11px;cursor:pointer}
.btn:hover{background:var(--border);color:var(--text)}
.main{display:grid;grid-template-columns:200px 1fr 180px;grid-template-rows:1fr 160px;gap:1px;flex:1;overflow:hidden;background:var(--border)}
.panel{background:var(--bg);padding:12px;overflow-y:auto;font-size:12px}
.panel-title{font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--dim);margin-bottom:8px;font-weight:600;display:flex;align-items:center;justify-content:space-between}
/* Pipeline Timeline */
.pipeline-timeline{display:flex;flex-direction:column;gap:4px}
.phase{display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:4px;border-left:3px solid var(--border)}
.phase.waiting{border-left-color:var(--dim)}
.phase.running{border-left-color:var(--yellow);background:rgba(210,153,34,0.08)}
.phase.completed{border-left-color:var(--green)}
.phase.error{border-left-color:var(--red)}
.phase.awaiting{border-left-color:var(--purple);background:rgba(188,140,255,0.08)}
.phase.paused{border-left-color:var(--yellow);background:rgba(210,153,34,0.04)}
.phase .label{font-weight:500;color:var(--text)}
.phase .status-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.phase .status-dot.waiting{background:var(--dim)}
.phase .status-dot.running{background:var(--yellow);animation:pulse 1.5s infinite}
.phase .status-dot.completed{background:var(--green)}
.phase .status-dot.error{background:var(--red)}
.phase .status-dot.awaiting{background:var(--purple);animation:pulse 2s infinite}
.phase .status-dot.paused{background:var(--yellow)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
.phase-connector{width:1px;height:8px;background:var(--border);margin-left:10px}
/* Stream panel: live response + log */
.stream-panel{grid-column:2;grid-row:1;display:flex;flex-direction:column;gap:0}
.live-response{max-height:120px;overflow-y:auto;padding:8px;background:var(--surface);border-bottom:1px solid var(--border);font-size:12px;white-space:pre-wrap;word-break:break-word;line-height:1.5;color:var(--text);display:none}
.live-response .cursor{display:inline-block;width:6px;height:12px;background:var(--accent);animation:blink 1s step-end infinite;vertical-align:text-bottom;margin-left:2px}
@keyframes blink{50%{opacity:0}}
.log-container{flex:1;overflow-y:auto;padding:4px 8px;font-family:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace;font-size:11px;line-height:1.6}
.log-entry{padding:2px 0;border-bottom:1px solid rgba(48,54,61,0.4);display:flex;gap:8px;align-items:flex-start}
.log-entry:hover{background:rgba(88,166,255,0.04)}
.log-time{color:var(--dim);flex-shrink:0;min-width:60px;font-size:10px;padding-top:1px}
.log-tag{flex-shrink:0;padding:0 4px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase;min-width:64px;text-align:center}
.log-tag.thinking{background:rgba(31,111,235,0.2);color:var(--blue)}
.log-tag.text{background:rgba(88,166,255,0.15);color:var(--accent)}
.log-tag.tool_call{background:rgba(210,153,34,0.2);color:var(--yellow)}
.log-tag.tool_result{background:rgba(63,185,80,0.15);color:var(--green)}
.log-tag.tool_result.err{background:rgba(248,81,73,0.15);color:var(--red)}
.log-tag.subagent_start{background:rgba(188,140,255,0.2);color:var(--purple)}
.log-tag.subagent_end{background:rgba(31,111,235,0.15);color:#79c0ff}
.log-tag.usage{background:rgba(139,148,158,0.15);color:var(--dim)}
.log-tag.done{background:rgba(63,185,80,0.2);color:var(--green)}
.log-tag.error{background:rgba(248,81,73,0.2);color:var(--red)}
.log-tag.system{background:rgba(139,148,158,0.1);color:var(--dim)}
.log-msg{flex:1;word-break:break-word;overflow:hidden}
.log-msg .tool-name{color:var(--yellow);font-weight:600}
.log-msg .agent-name{color:var(--purple);font-weight:600}
.log-msg .detail{color:var(--dim);font-size:10px}
.log-msg .task-desc{color:var(--text);font-size:11px;display:block;margin-top:2px;padding:3px 6px;background:rgba(88,166,255,0.06);border-left:2px solid var(--accent);max-height:200px;overflow:hidden;white-space:pre-wrap;word-break:break-word;cursor:pointer;position:relative}
.log-msg .task-desc.expanded{max-height:none}
.log-msg .task-desc .expand-hint{color:var(--accent);font-size:10px;font-weight:600}
.log-msg .output-preview{color:var(--dim);font-size:10px;display:block;margin-top:2px;padding:3px 6px;background:rgba(63,185,80,0.06);border-left:2px solid var(--green);max-height:200px;overflow:hidden;white-space:pre-wrap;word-break:break-word;cursor:pointer}
.log-msg .output-preview.expanded{max-height:none}
.log-tag.sub_text{background:rgba(188,140,255,0.1);color:#a371f7}
.log-tag.sub_tool{background:rgba(210,153,34,0.12);color:var(--yellow)}
.log-tag.sub_result{background:rgba(63,185,80,0.12);color:var(--green)}
/* Thinking box */
.thinking-box{background:rgba(31,111,235,0.08);border:1px solid var(--blue);border-radius:6px;padding:8px;font-size:12px;color:var(--dim);max-height:80px;overflow-y:auto;white-space:pre-wrap;word-break:break-word;display:none;margin:4px 8px}
/* Sidebar */
.sidebar{grid-column:3;grid-row:1;display:flex;flex-direction:column;gap:12px}
.agent-status{display:flex;align-items:center;gap:6px;padding:2px 0}
.agent-status .dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.agent-status .dot.active{background:var(--green);box-shadow:0 0 4px var(--green)}
.agent-status .dot.done{background:var(--accent)}
.agent-status .dot.idle{background:var(--dim)}
.agent-status .name{font-size:12px;color:var(--text)}
.metric{display:flex;justify-content:space-between;padding:2px 0}
.metric .label{color:var(--dim)}
.metric .value{color:var(--text);font-weight:500;font-variant-numeric:tabular-nums}
/* Memory Browser */
.memory-panel{grid-column:1/-1;grid-row:2;border-top:1px solid var(--border)}
.memory-tabs{display:flex;gap:2px;margin-bottom:8px}
.memory-tab{padding:4px 10px;background:var(--surface);border:none;color:var(--dim);font-size:11px;cursor:pointer;border-radius:4px 4px 0 0}
.memory-tab.active{color:var(--accent);background:var(--border)}
.memory-content{overflow-y:auto;max-height:110px;white-space:pre-wrap;word-break:break-word;font-size:11px;color:var(--dim);padding:4px}
/* Scrollbar */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--dim)}
/* Empty state */
.empty{color:var(--dim);text-align:center;padding:40px 20px;font-size:13px}
.session-info{font-size:11px;color:var(--dim);margin-top:12px}
</style>
</head>
<body>
<div class="header">
  <h1>EvoScientist Dashboard</h1>
  <div class="meta">
    <select id="sessionSelect"><option value="">-- Select Session --</option></select>
    <span id="statusBadge" style="padding:2px 8px;border-radius:10px;font-size:11px;background:var(--surface)">idle</span>
  </div>
</div>
<div class="main">
  <!-- Pipeline Timeline -->
  <div class="panel">
    <div class="panel-title">Pipeline</div>
    <div class="pipeline-timeline" id="pipelineTimeline">
      <div class="phase waiting" data-phase="0"><div class="status-dot waiting"></div><span class="label">W0 Init</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="1"><div class="status-dot waiting"></div><span class="label">W1 Intake</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="2"><div class="status-dot waiting"></div><span class="label">W2 Plan</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="3"><div class="status-dot waiting"></div><span class="label">W3 Research</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="3.5"><div class="status-dot waiting"></div><span class="label">W3.5 Ideate</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="4"><div class="status-dot waiting"></div><span class="label">W4 Code</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="5"><div class="status-dot waiting"></div><span class="label">W5 Analyze</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="6"><div class="status-dot waiting"></div><span class="label">W6 Write</span></div>
      <div class="phase-connector"></div>
      <div class="phase waiting" data-phase="7"><div class="status-dot waiting"></div><span class="label">W7 Review</span></div>
    </div>
    <div class="session-info" id="sessionInfo" style="margin-top:12px"></div>
    <div id="pipelineControls" style="margin-top:8px;display:none">
      <button class="btn" id="btnPause" style="margin-right:4px" onclick="pipelineControl('pause')">Pause</button>
      <button class="btn" id="btnResume" style="margin-right:4px;display:none" onclick="pipelineControl('resume')">Resume</button>
      <button class="btn" id="btnSwitchClaude" onclick="pipelineControl('switch_to_claude')">Switch to Claude</button>
      <button class="btn" id="btnSwitchAgent" style="display:none" onclick="pipelineControl('switch_to_agent')">Switch to Agent</button>
    </div>
    <div id="phaseDetail" style="margin-top:6px;font-size:10px;color:var(--purple);display:none"></div>
  </div>
  <!-- Agent Stream: live response + event log -->
  <div class="panel stream-panel" id="streamPanel" style="position:relative">
    <div class="panel-title">
      <span>Agent Log</span>
      <button class="btn" id="clearLogBtn" title="Clear log">Clear</button>
    </div>
    <div class="thinking-box" id="thinkingBox"></div>
    <div class="live-response" id="liveResponse"></div>
    <div class="log-container" id="logContainer"><div class="empty">Select a session to begin monitoring</div></div>
  </div>
  <!-- Sidebar -->
  <div class="panel sidebar">
    <div>
      <div class="panel-title">Sub-Agents</div>
      <div id="agentList">
        <div class="agent-status"><div class="dot idle"></div><span class="name">planner</span></div>
        <div class="agent-status"><div class="dot idle"></div><span class="name">researcher</span></div>
        <div class="agent-status"><div class="dot idle"></div><span class="name">coder</span></div>
        <div class="agent-status"><div class="dot idle"></div><span class="name">debugger</span></div>
        <div class="agent-status"><div class="dot idle"></div><span class="name">analyst</span></div>
        <div class="agent-status"><div class="dot idle"></div><span class="name">writer</span></div>
      </div>
    </div>
    <div>
      <div class="panel-title">Metrics</div>
      <div class="metric"><span class="label">Input tokens</span><span class="value" id="metricInput">0</span></div>
      <div class="metric"><span class="label">Output tokens</span><span class="value" id="metricOutput">0</span></div>
      <div class="metric"><span class="label">Events</span><span class="value" id="metricEvents">0</span></div>
      <div class="metric"><span class="label">Duration</span><span class="value" id="metricDuration">--</span></div>
    </div>
  </div>
  <!-- Memory Browser -->
  <div class="panel memory-panel">
    <div class="panel-title">Memory</div>
    <div class="memory-tabs" id="memoryTabs">
      <button class="memory-tab active" data-file="MEMORY.md">MEMORY.md</button>
      <button class="memory-tab" data-file="ideation-memory.md">Ideation</button>
      <button class="memory-tab" data-file="experiment-memory.md">Experiment</button>
    </div>
    <div class="memory-content" id="memoryContent">No memory data yet.</div>
  </div>
</div>
<script>
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
let currentSession = null;
let eventSource = null;
let eventCount = 0;
let startTime = null;
let durationTimer = null;
let inputTokens = 0;
let outputTokens = 0;
let autoScroll = true;

// --- Text buffering (debounce) ---
let textBuffer = '';           // accumulated text tokens
let textBufferTimer = null;    // debounce timer
let textLogEntry = null;       // the live log entry being updated
const TEXT_FLUSH_MS = 600;     // flush after 600ms of no new text
const TEXT_MAX_BUFFER = 2000;  // flush when buffer exceeds this

function flushTextBuffer() {
  if (!textBuffer) { textLogEntry = null; return; }
  const text = textBuffer;
  textBuffer = '';
  textBufferTimer = null;

  if (textLogEntry) {
    // Update existing entry with final text
    const msgEl = textLogEntry.querySelector('.log-msg');
    const preview = text.length > 500 ? text.substring(0, 500) + '...' : text;
    msgEl.textContent = preview;
    // Update time to flush time
    textLogEntry.querySelector('.log-time').textContent = logTime();
    textLogEntry = null;
  }
}

function appendTextToLog(content) {
  textBuffer += content;
  $('#thinkingBox').style.display = 'none';

  // Update live response area
  const lr = $('#liveResponse');
  lr.style.display = 'block';
  // Remove old cursor, add text, add new cursor
  const cursor = lr.querySelector('.cursor');
  if (cursor) cursor.remove();
  lr.appendChild(document.createTextNode(content));
  const c = document.createElement('span');
  c.className = 'cursor';
  lr.appendChild(c);
  lr.scrollTop = lr.scrollHeight;

  // Update or create log entry
  if (!textLogEntry) {
    textLogEntry = createLogEntryRaw('TEXT', 'text', '');
  }
  const msgEl = textLogEntry.querySelector('.log-msg');
  const preview = textBuffer.length > 300 ? textBuffer.substring(textBuffer.length - 300) : textBuffer;
  msgEl.textContent = preview + (textBuffer.length > 300 ? '...' : '');
  // Show char count
  msgEl.textContent = '[' + textBuffer.length + ' chars] ' + msgEl.textContent;

  // Reset debounce timer
  if (textBufferTimer) clearTimeout(textBufferTimer);
  if (textBuffer.length >= TEXT_MAX_BUFFER) {
    flushTextBuffer();
  } else {
    textBufferTimer = setTimeout(flushTextBuffer, TEXT_FLUSH_MS);
  }
}

function forceFlushText() {
  if (textBufferTimer) clearTimeout(textBufferTimer);
  flushTextBuffer();
}

// --- Log ---
function logTime() {
  const d = new Date();
  return d.getHours().toString().padStart(2,'0') + ':' +
         d.getMinutes().toString().padStart(2,'0') + ':' +
         d.getSeconds().toString().padStart(2,'0');
}

function createLogEntryRaw(tag, tagClass, msgHTML) {
  const container = $('#logContainer');
  const empty = container.querySelector('.empty');
  if (empty) empty.remove();

  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML =
    '<span class="log-time">' + logTime() + '</span>' +
    '<span class="log-tag ' + tagClass + '">' + tag + '</span>' +
    '<span class="log-msg">' + msgHTML + '</span>';
  container.appendChild(entry);
  while (container.children.length > 2000) container.removeChild(container.firstChild);
  if (autoScroll) container.scrollTop = container.scrollHeight;
  return entry;
}

function addLogEntry(tag, tagClass, msgHTML) {
  // Flush any pending text before adding non-text entry
  if (tag !== 'TEXT') forceFlushText();
  createLogEntryRaw(tag, tagClass, msgHTML);
}

function clearLog() {
  forceFlushText();
  const container = $('#logContainer');
  container.innerHTML = '<div class="empty">Log cleared. Waiting for new events...</div>';
  eventCount = 0;
  updateMetrics();
  // Clear live response
  $('#liveResponse').style.display = 'none';
  $('#liveResponse').textContent = '';
}

$('#clearLogBtn').addEventListener('click', clearLog);

$('#logContainer').addEventListener('scroll', () => {
  const el = $('#logContainer');
  autoScroll = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
});

function escapeHTML(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function makeExpandable(html, maxH) {
  // Returns HTML with expand/collapse toggle
  return html + ' <span class="expand-hint">[click to expand]</span>';
}

// Delegate click to expand/collapse task-desc and output-preview
document.addEventListener('click', e => {
  const el = e.target.closest('.task-desc, .output-preview');
  if (el) {
    el.classList.toggle('expanded');
    const hint = el.querySelector('.expand-hint');
    if (hint) hint.textContent = el.classList.contains('expanded') ? '[collapse]' : '[click to expand]';
  }
});

// --- Session selector ---
async function loadSessions() {
  try {
    const resp = await fetch('/api/sessions');
    const sessions = await resp.json();
    const sel = $('#sessionSelect');
    const prev = sel.value;
    sel.innerHTML = '<option value="">-- Select Session --</option>';
    sessions.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.session_id;
      opt.textContent = s.session_id + ' (' + s.status + ')';
      sel.appendChild(opt);
    });
    if (prev && sessions.find(s => s.session_id === prev)) sel.value = prev;
  } catch(e) { console.error('loadSessions', e); }
}

$('#sessionSelect').addEventListener('change', e => {
  if (eventSource) { eventSource.close(); eventSource = null; }
  currentSession = e.target.value;
  if (currentSession) {
    connectSSE(currentSession);
    pollPipeline(currentSession);
    pollMemory(currentSession, 'MEMORY.md');
    pollState(currentSession);
  } else {
    resetUI();
  }
});

function resetUI() {
  clearLog();
  $('#thinkingBox').style.display = 'none';
  $('#statusBadge').textContent = 'idle';
  $('#statusBadge').style.background = 'var(--surface)';
  eventCount = 0; inputTokens = 0; outputTokens = 0;
  updateMetrics();
  $$('.phase').forEach(p => { p.className = 'phase waiting'; p.querySelector('.status-dot').className = 'status-dot waiting'; });
}

// --- SSE connection ---
function connectSSE(sessionId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource('/api/sessions/' + sessionId + '/events');
  startTime = Date.now();
  if (durationTimer) clearInterval(durationTimer);
  durationTimer = setInterval(updateDuration, 1000);

  addLogEntry('SYSTEM', 'system', 'SSE connected, streaming events...');

  eventSource.addEventListener('agent_event', e => {
    try {
      const ev = JSON.parse(e.data);
      handleEvent(ev);
      eventCount++;
      updateMetrics();
    } catch(err) { console.error('parse', err); }
  });

  eventSource.addEventListener('heartbeat', () => {});

  eventSource.onerror = () => {
    console.log('SSE error, reconnecting in 3s...');
    addLogEntry('SYSTEM', 'system', 'SSE disconnected, reconnecting...');
    eventSource.close();
    setTimeout(() => { if (currentSession === sessionId) connectSSE(sessionId); }, 3000);
  };

  // Reset live response for new connection
  forceFlushText();
  forceFlushAllSubText();
  subTextBuffers = {}; subTextTimers = {}; subTextEntries = {};
  $('#liveResponse').style.display = 'none';
  $('#liveResponse').textContent = '';
  $('#thinkingBox').style.display = 'none';
}

// --- Sub-agent text buffering ---
let subTextBuffers = {};  // agentName -> accumulated text
let subTextTimers = {};   // agentName -> timer id
let subTextEntries = {};  // agentName -> log entry element

function flushSubText(agentName) {
  const text = subTextBuffers[agentName] || '';
  if (!text) { delete subTextEntries[agentName]; return; }
  subTextBuffers[agentName] = '';
  subTextTimers[agentName] = null;
  const entry = subTextEntries[agentName];
  if (entry) {
    const msgEl = entry.querySelector('.log-msg');
    const showExpand = text.length > 100;
    const preview = text.length > 500 ? text.substring(0, 500) + '...' : text;
    msgEl.innerHTML = '<span class="agent-name">' + escapeHTML(agentName) + '</span> <span class="detail">[' + text.length + ' chars]</span><span class="output-preview">' + escapeHTML(preview) + (showExpand ? ' <span class="expand-hint">[click to expand]</span>' : '') + '</span>';
    entry.querySelector('.log-time').textContent = logTime();
    delete subTextEntries[agentName];
  }
}

function appendSubText(agentName, content) {
  if (!subTextBuffers[agentName]) subTextBuffers[agentName] = '';
  subTextBuffers[agentName] += content;

  if (!subTextEntries[agentName]) {
    subTextEntries[agentName] = createLogEntryRaw('OUTPUT', 'sub_text', '');
  }
  const entry = subTextEntries[agentName];
  const msgEl = entry.querySelector('.log-msg');
  const buf = subTextBuffers[agentName];
  const showExpand = buf.length > 100;
  const preview = buf.length > 500 ? buf.substring(0, 500) + '...' : buf;
  msgEl.innerHTML = '<span class="agent-name">' + escapeHTML(agentName) + '</span> <span class="detail">streaming [' + buf.length + ' chars]...</span><span class="output-preview">' + escapeHTML(preview) + (showExpand ? ' <span class="expand-hint">[click to expand]</span>' : '') + '</span>';

  if (subTextTimers[agentName]) clearTimeout(subTextTimers[agentName]);
  if (buf.length >= 2000) {
    flushSubText(agentName);
  } else {
    subTextTimers[agentName] = setTimeout(() => flushSubText(agentName), 800);
  }
}

function forceFlushAllSubText() {
  Object.keys(subTextTimers).forEach(k => {
    if (subTextTimers[k]) clearTimeout(subTextTimers[k]);
    flushSubText(k);
  });
}

function handleEvent(ev) {
  const type = ev.type;
  const data = ev.data || {};

  switch(type) {
    case 'thinking':
      forceFlushText();
      $('#liveResponse').style.display = 'none';
      $('#liveResponse').textContent = '';
      const tb = $('#thinkingBox');
      tb.style.display = 'block';
      tb.textContent = (data.content || '').substring(0, 500);
      addLogEntry('THINK', 'thinking', escapeHTML((data.content || '').substring(0, 200)) + ((data.content || '').length > 200 ? '...' : ''));
      break;
    case 'text':
      appendTextToLog(data.content || '');
      break;
    case 'tool_call': {
      const name = data.name || 'tool';
      const args = data.args || {};
      let descHTML = '';
      // Show task description for sub-agent dispatch
      if (name === 'task' && args.description) {
        const desc = typeof args.description === 'string' ? args.description : JSON.stringify(args.description);
        descHTML = '<span class="task-desc">' + escapeHTML(desc) + (desc.length > 100 ? ' <span class="expand-hint">[click to expand]</span>' : '') + '</span>';
      } else if (Object.keys(args).length > 0) {
        const argsStr = JSON.stringify(args);
        if (argsStr.length > 2) {
          descHTML = ' <span class="detail">' + escapeHTML(argsStr.substring(0, 200)) + '</span>';
        }
      }
      addLogEntry('TOOL', 'tool_call',
        '<span class="tool-name">' + escapeHTML(name) + '</span>' + descHTML);
      $('#liveResponse').style.display = 'none';
      break;
    }
    case 'tool_result': {
      const content = data.content || '';
      const isErr = data.success === false;
      let msgHTML = '<span class="tool-name">' + escapeHTML(data.name || data.id || 'tool') + '</span> ';
      if (isErr) {
        msgHTML += '<span style="color:var(--red)">' + escapeHTML(content.substring(0, 300) || 'failed') + '</span>';
      } else {
        msgHTML += '<span class="detail">ok</span>';
        if (content) {
          msgHTML += '<span class="output-preview">' + escapeHTML(content) + (content.length > 100 ? ' <span class="expand-hint">[click to expand]</span>' : '') + '</span>';
        }
      }
      addLogEntry('RESULT', isErr ? 'tool_result err' : 'tool_result', msgHTML);
      break;
    }
    case 'subagent_start': {
      forceFlushAllSubText();
      const agentName = (data.name || 'unknown').replace(/-agent$/, '');
      const desc = data.description || '';
      let msgHTML = '<span class="agent-name">' + escapeHTML(agentName) + '</span> started';
      if (desc) {
        msgHTML += '<span class="task-desc">' + escapeHTML(desc) + (desc.length > 100 ? ' <span class="expand-hint">[click to expand]</span>' : '') + '</span>';
      }
      addLogEntry('AGENT', 'subagent_start', msgHTML);
      const dot = document.querySelector('#agentList .agent-status:nth-child(' + getAgentIndex(agentName) + ') .dot');
      if (dot) dot.className = 'dot active';
      $('#liveResponse').style.display = 'none';
      $('#liveResponse').textContent = '';
      $('#thinkingBox').style.display = 'none';
      break;
    }
    case 'subagent_end': {
      forceFlushAllSubText();
      const endName = (data.name || 'unknown').replace(/-agent$/, '');
      addLogEntry('AGENT', 'subagent_end',
        '<span class="agent-name">' + escapeHTML(endName) + '</span> finished');
      const endDot = document.querySelector('#agentList .agent-status:nth-child(' + getAgentIndex(endName) + ') .dot');
      if (endDot) endDot.className = 'dot done';
      break;
    }
    case 'subagent_text': {
      const subName = (data.subagent || data.name || 'unknown').replace(/-agent$/, '');
      appendSubText(subName, data.content || '');
      break;
    }
    case 'subagent_tool_call': {
      const subName2 = (data.subagent || 'unknown').replace(/-agent$/, '');
      const subToolName = data.name || 'tool';
      const subArgs = data.args || {};
      let subArgsStr = '';
      if (subToolName === 'task' && subArgs.description) {
        subArgsStr = escapeHTML(subArgs.description.substring(0, 150));
      } else if (Object.keys(subArgs).length > 0) {
        subArgsStr = escapeHTML(JSON.stringify(subArgs).substring(0, 120));
      }
      addLogEntry('S·TOOL', 'sub_tool',
        '<span class="agent-name">' + escapeHTML(subName2) + '</span> → <span class="tool-name">' + escapeHTML(subToolName) + '</span>' +
        (subArgsStr ? ' <span class="detail">' + subArgsStr + '</span>' : ''));
      break;
    }
    case 'subagent_tool_result': {
      const subName3 = (data.subagent || 'unknown').replace(/-agent$/, '');
      const subContent = data.content || '';
      addLogEntry('S·RES', 'sub_result',
        '<span class="agent-name">' + escapeHTML(subName3) + '</span> ' +
        '<span class="tool-name">' + escapeHTML(data.name || 'tool') + '</span> ' +
        (data.success === false ? '<span style="color:var(--red)">failed</span>' : '<span class="detail">ok</span>') +
        (subContent ? '<span class="output-preview">' + escapeHTML(subContent.substring(0, 300)) + (subContent.length > 100 ? ' <span class="expand-hint">[click to expand]</span>' : '') + '</span>' : ''));
      break;
    }
    case 'usage_stats':
      inputTokens = data.input_tokens || inputTokens;
      outputTokens = data.output_tokens || outputTokens;
      addLogEntry('STATS', 'usage',
        'tokens: ' + (data.input_tokens || 0).toLocaleString() + ' in / ' + (data.output_tokens || 0).toLocaleString() + ' out');
      updateMetrics();
      break;
    case 'done':
      forceFlushText();
      forceFlushAllSubText();
      addLogEntry('DONE', 'done',
        'Agent finished' + (data.response ? ' — ' + escapeHTML(data.response).substring(0, 100) + '...' : ''));
      $('#statusBadge').textContent = 'idle';
      $('#statusBadge').style.background = 'rgba(63,185,80,0.15)';
      $('#thinkingBox').style.display = 'none';
      const cursor = $('#liveResponse .cursor');
      if (cursor) cursor.remove();
      if (durationTimer) clearInterval(durationTimer);
      break;
    case 'error':
      forceFlushText();
      forceFlushAllSubText();
      addLogEntry('ERROR', 'error', escapeHTML(data.message || 'unknown error'));
      $('#statusBadge').textContent = 'error';
      $('#statusBadge').style.background = 'rgba(248,81,73,0.15)';
      break;
  }

  if (['thinking','tool_call','subagent_start','subagent_text'].includes(type)) {
    $('#statusBadge').textContent = 'running';
    $('#statusBadge').style.background = 'rgba(210,153,34,0.15)';
  }

  // Pipeline control SSE events
  if (type === 'pipeline_control_changed') {
    addLogEntry('CONTROL', 'system',
      'Pipeline: ' + (data.action || '') + ' → ' + (data.status || ''));
    if (currentSession) pollPipeline(currentSession);
  }
}

function getAgentIndex(name) {
  const agents = ['planner','researcher','coder','debugger','analyst','writer'];
  const idx = agents.findIndex(a => name.includes(a));
  return idx >= 0 ? idx + 1 : 1;
}

function updateMetrics() {
  $('#metricInput').textContent = inputTokens.toLocaleString();
  $('#metricOutput').textContent = outputTokens.toLocaleString();
  $('#metricEvents').textContent = eventCount;
}

function updateDuration() {
  if (startTime) {
    const s = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(s / 60);
    $('#metricDuration').textContent = m > 0 ? m + 'm ' + (s % 60) + 's' : s + 's';
  }
}

// Pipeline state polling
async function pollPipeline(sessionId) {
  try {
    const resp = await fetch('/api/sessions/' + sessionId + '/pipeline');
    const state = await resp.json();
    if (state.status === 'no_pipeline') {
      $('#pipelineControls').style.display = 'none';
      $('#phaseDetail').style.display = 'none';
      return;
    }
    const phase = state.phase || 0;
    const status = state.status || 'in_progress';

    $$('.phase').forEach(p => {
      const pPhase = parseFloat(p.dataset.phase);
      if (pPhase < phase) {
        p.className = 'phase completed'; p.querySelector('.status-dot').className = 'status-dot completed';
      } else if (pPhase === phase) {
        // Current phase — pick class based on status
        let cls = 'running', dotCls = 'running';
        if (status === 'awaiting_claude_code') { cls = 'awaiting'; dotCls = 'awaiting'; }
        else if (status === 'paused') { cls = 'paused'; dotCls = 'paused'; }
        else if (status === 'claude_code_running') { cls = 'awaiting'; dotCls = 'awaiting'; }
        p.className = 'phase ' + cls; p.querySelector('.status-dot').className = 'status-dot ' + dotCls;
      } else {
        p.className = 'phase waiting'; p.querySelector('.status-dot').className = 'status-dot waiting';
      }
    });
    const info = $('#sessionInfo');
    info.innerHTML = 'Iteration: ' + (state.iteration || 0) + '<br>Status: ' + status;

    // Show control buttons
    $('#pipelineControls').style.display = 'block';
    const isAwaiting = status === 'awaiting_claude_code' || status === 'claude_code_running';
    const isPaused = status === 'paused';
    $('#btnPause').style.display = (!isPaused && !isAwaiting) ? '' : 'none';
    $('#btnResume').style.display = isPaused ? '' : 'none';
    $('#btnSwitchClaude').style.display = (!isAwaiting && !isPaused) ? '' : 'none';
    $('#btnSwitchAgent').style.display = isAwaiting ? '' : 'none';

    // Phase detail
    const detail = $('#phaseDetail');
    if (isAwaiting) {
      detail.style.display = 'block';
      detail.textContent = status === 'claude_code_running'
        ? 'Claude Code is programming...'
        : 'Awaiting Claude Code...';
    } else if (isPaused) {
      detail.style.display = 'block';
      detail.textContent = 'Pipeline paused';
    } else if (state.code_proposals && state.code_proposals.length > 0) {
      detail.style.display = 'block';
      detail.textContent = state.code_proposals.length + ' code proposals ready';
    } else {
      detail.style.display = 'none';
    }
  } catch(e) {}
}

async function pipelineControl(action) {
  if (!currentSession) return;
  try {
    await fetch('/api/sessions/' + currentSession + '/pipeline/control', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: action}),
    });
    pollPipeline(currentSession);
  } catch(e) { console.error('pipelineControl', e); }
}

// State polling
async function pollState(sessionId) {
  try {
    const resp = await fetch('/api/sessions/' + sessionId + '/state');
    const st = await resp.json();
    if (st.subagents) {
      st.subagents.forEach(sa => {
        const idx = getAgentIndex(sa.name);
        const dot = document.querySelector('#agentList .agent-status:nth-child(' + idx + ') .dot');
        if (dot && sa.is_active) dot.className = 'dot active';
      });
    }
  } catch(e) {}
}

// Memory browser
$$('.memory-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    $$('.memory-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    if (currentSession) pollMemory(currentSession, tab.dataset.file);
  });
});

async function pollMemory(sessionId, file) {
  try {
    const resp = await fetch('/api/sessions/' + sessionId + '/memory');
    const mem = await resp.json();
    $('#memoryContent').textContent = mem[file] || mem.status || 'No data.';
  } catch(e) { $('#memoryContent').textContent = 'Error loading memory.'; }
}

// Auto-refresh
setInterval(() => { loadSessions(); if (currentSession) { pollPipeline(currentSession); pollMemory(currentSession, document.querySelector('.memory-tab.active')?.dataset.file || 'MEMORY.md'); } }, 5000);
loadSessions();
</script>
</body>
</html>
"""
