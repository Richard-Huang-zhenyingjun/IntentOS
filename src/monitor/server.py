"""
IntentOS Workspace Monitor Server.

Serves the browser UI and streams workspace state via WebSocket.
State is pushed by CommandLoop after each turn.

Run alongside the workspace terminal session:
    python src/monitor/server.py
    python scripts/run_workspace.py --preset workspace_easy_clean --no-llm --headless --reset-history
"""
from __future__ import annotations

import asyncio
import copy
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)


class WorkspaceState:
    """
    In-memory state shared between CommandLoop thread and FastAPI server.
    Thread-safe via lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = self._initial_state()

    @staticmethod
    def _initial_state() -> dict:
        return {
            "intentos_state": "IDLE",
            "kernel_state": "IDLE",
            "false_executions": 0,
            "goal": "",
            "nodes_total": 0,
            "nodes_complete": 0,
            "plan_source": "",
            "current_node": "",
            "uncertainty_max": 0.0,
            "task_graph": [],
            "conversation": [],
            "workspace": {
                "objects": [],
                "arm_position": "home",
                "arm_target": None,
                "bin_count": 0,
                "tray_count": 0,
                "table_count": 0,
            },
            "last_updated": 0.0,
        }

    def reset(self) -> None:
        """Clear all monitor state for a fresh workspace session."""
        with self._lock:
            self._state = self._initial_state()
            self._state["last_updated"] = time.time()

    def update(self, patch: dict) -> None:
        with self._lock:
            self._state.update(patch)
            self._state["last_updated"] = time.time()

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def add_conversation_turn(self, role: str, text: str) -> None:
        """role: 'user' | 'system'"""
        with self._lock:
            self._state["conversation"].append(
                {
                    "role": role,
                    "text": text,
                    "timestamp": time.time(),
                }
            )
            if len(self._state["conversation"]) > 50:
                self._state["conversation"] = self._state["conversation"][-50:]
            self._state["last_updated"] = time.time()


workspace_state = WorkspaceState()
command_queue: deque[str] = deque(maxlen=20)


app = FastAPI(title="IntentOS Workspace Monitor")
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        await websocket.send_json(workspace_state.get())

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, state: dict) -> None:
        stale = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(state)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


manager = ConnectionManager()
_broadcast_loop: Optional[asyncio.AbstractEventLoop] = None
_broadcast_lock = threading.Lock()


def push_state(patch: dict) -> None:
    """CommandLoop can import this helper when running in-process."""
    workspace_state.update(patch)


def push_conversation(role: str, text: str) -> None:
    """CommandLoop can import this helper when running in-process."""
    workspace_state.add_conversation_turn(role, text)


def push_state_update() -> None:
    """
    Called from CommandLoop thread to push state to browser.
    Thread-safe: schedules broadcast on the loop serving WebSocket clients.
    """
    state = workspace_state.get()
    with _broadcast_lock:
        loop = _broadcast_loop
    if loop is not None and not loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(_broadcast(state), loop)
        except Exception:
            pass


async def _broadcast(state: dict) -> None:
    """Send state to all connected browsers."""
    await manager.broadcast(state)


@app.get("/")
async def root() -> HTMLResponse:
    html_path = STATIC_DIR / "monitor.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse(_MONITOR_HTML)


@app.get("/state")
async def get_state() -> dict:
    return workspace_state.get()


@app.post("/state")
async def post_state(patch: dict) -> dict:
    workspace_state.update(patch)
    await manager.broadcast(workspace_state.get())
    return {"ok": True}


@app.post("/conversation")
async def post_conversation(turn: dict) -> dict:
    role = str(turn.get("role", "system"))
    text = str(turn.get("text", ""))
    workspace_state.add_conversation_turn(role, text)
    await manager.broadcast(workspace_state.get())
    return {"ok": True}


@app.post("/command")
async def receive_command(payload: dict) -> dict:
    """
    Browser posts here when user types a command.
    CommandLoop reads from command_queue each tick.
    """
    text = str(payload.get("text", "")).strip()
    if text:
        command_queue.append(text)
        return {"status": "queued", "text": text}
    return {"status": "ignored"}


@app.post("/reset")
async def reset_state() -> dict:
    """Reset monitor state and clear pending browser commands."""
    command_queue.clear()
    workspace_state.reset()
    await manager.broadcast(workspace_state.get())
    return {"status": "reset"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    global _broadcast_loop
    with _broadcast_lock:
        _broadcast_loop = asyncio.get_running_loop()
    await manager.connect(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(app, host=host, port=port)


def run_server(host: str = "127.0.0.1", port: int = 7788) -> None:
    """Start the monitor server. Call in a background thread."""
    print(f"\n[MONITOR] Starting at http://{host}:{port}")
    print("[MONITOR] Open this in your browser to watch the workspace\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")


_MONITOR_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>IntentOS Workspace Monitor</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #111315;
      --panel: #181c20;
      --line: #2c333a;
      --text: #f0f4f8;
      --muted: #9aa7b4;
      --accent: #49a078;
      --warn: #f0b44c;
      --bad: #ef6f6c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      height: 48px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      border-bottom: 1px solid var(--line);
      background: #0f1113;
    }
    header h1 {
      margin: 0;
      font-size: 15px;
      font-weight: 650;
    }
    #updated { color: var(--muted); font-size: 12px; }
    main {
      height: calc(100vh - 48px);
      display: grid;
      grid-template-columns: minmax(260px, 0.85fr) minmax(360px, 1.35fr) minmax(240px, 0.8fr);
    }
    section {
      min-width: 0;
      border-right: 1px solid var(--line);
      background: var(--panel);
      display: flex;
      flex-direction: column;
    }
    section:last-child { border-right: 0; }
    h2 {
      margin: 0;
      padding: 12px 14px;
      font-size: 12px;
      letter-spacing: 0;
      color: var(--muted);
      text-transform: uppercase;
      border-bottom: 1px solid var(--line);
    }
    #conversation {
      padding: 12px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .turn {
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      white-space: pre-wrap;
    }
    .user { background: #17231d; border-color: #254836; }
    .system { background: #171b20; }
    .role { display: block; color: var(--muted); font-size: 11px; margin-bottom: 4px; }
    #workspace-wrap {
      flex: 1;
      min-height: 0;
      display: flex;
      align-items: stretch;
      padding: 12px;
    }
    canvas {
      width: 100%;
      height: 100%;
      background: #20262b;
      border: 1px solid var(--line);
      border-radius: 6px;
    }
    #status {
      padding: 12px;
      overflow: auto;
    }
    .kv {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 6px 10px;
      margin-bottom: 14px;
    }
    .k { color: var(--muted); }
    .v { overflow-wrap: anywhere; }
    .ok { color: var(--accent); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .graph {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .node {
      padding: 7px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #14181c;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; height: auto; }
      section { min-height: 320px; border-right: 0; border-bottom: 1px solid var(--line); }
    }
  </style>
</head>
<body>
  <header>
    <h1>IntentOS Workspace Monitor</h1>
    <div id="updated">connecting...</div>
  </header>
  <main>
    <section>
      <h2>Conversation</h2>
      <div id="conversation"></div>
    </section>
    <section>
      <h2>Workspace</h2>
      <div id="workspace-wrap"><canvas id="workspace"></canvas></div>
    </section>
    <section>
      <h2>Status</h2>
      <div id="status"></div>
    </section>
  </main>
  <script>
    const state = { data: null };
    const convo = document.getElementById('conversation');
    const statusEl = document.getElementById('status');
    const updatedEl = document.getElementById('updated');
    const canvas = document.getElementById('workspace');
    const ctx = canvas.getContext('2d');

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onmessage = event => {
        state.data = JSON.parse(event.data);
        render();
      };
      ws.onopen = () => updatedEl.textContent = 'connected';
      ws.onclose = () => {
        updatedEl.textContent = 'disconnected - retrying';
        setTimeout(connect, 1000);
      };
    }

    function render() {
      renderConversation();
      renderStatus();
      renderWorkspace();
    }

    function renderConversation() {
      const turns = state.data?.conversation || [];
      convo.innerHTML = turns.map(t => `
        <div class="turn ${escapeHtml(t.role)}">
          <span class="role">${escapeHtml(t.role)}</span>${escapeHtml(t.text)}
        </div>
      `).join('');
      convo.scrollTop = convo.scrollHeight;
    }

    function renderStatus() {
      const s = state.data || {};
      const falseClass = Number(s.false_executions || 0) === 0 ? 'ok' : 'bad';
      statusEl.innerHTML = `
        <div class="kv">
          <div class="k">IntentOS</div><div class="v">${escapeHtml(s.intentos_state || 'IDLE')}</div>
          <div class="k">Kernel</div><div class="v">${escapeHtml(s.kernel_state || 'IDLE')}</div>
          <div class="k">Goal</div><div class="v">${escapeHtml(s.goal || '-')}</div>
          <div class="k">Progress</div><div class="v">${s.nodes_complete || 0}/${s.nodes_total || 0}</div>
          <div class="k">Uncertainty</div><div class="v">${Number(s.uncertainty_max || 0).toFixed(2)}</div>
          <div class="k">false_ex</div><div class="v ${falseClass}">${s.false_executions || 0}</div>
        </div>
        <h2>Node Graph</h2>
        <div class="graph">${(s.task_graph || []).map(node => `
          <div class="node">
            <span>${escapeHtml(node.node_id || '?')} · ${escapeHtml(node.action_type || '?')}</span>
            <span>${escapeHtml(node.status || '?')}</span>
          </div>
        `).join('') || '<div class="k">No active graph</div>'}</div>
      `;
      const updated = s.last_updated ? new Date(s.last_updated * 1000).toLocaleTimeString() : 'waiting';
      updatedEl.textContent = `updated ${updated}`;
    }

    function renderWorkspace() {
      const ratio = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);
      drawTable(w, h);
      const ws = state.data?.workspace || {};
      drawZones(w, h, ws);
      drawObjects(w, h, ws.objects || []);
      drawArm(w, h, ws);
    }

    function drawTable(w, h) {
      ctx.fillStyle = '#252c32';
      ctx.fillRect(22, 22, w - 44, h - 44);
      ctx.strokeStyle = '#4d5964';
      ctx.lineWidth = 2;
      ctx.strokeRect(22, 22, w - 44, h - 44);
    }

    function drawZones(w, h, ws) {
      drawZone(w - 132, 42, 90, 70, 'BIN', '#27483b');
      drawZone(42, h - 112, 100, 70, 'TRAY', '#37435a');
      ctx.fillStyle = '#9aa7b4';
      ctx.fillText(`${ws.bin_count || 0} in bin`, w - 126, 128);
      ctx.fillText(`${ws.table_count || 0} on table`, 42, 42);
    }

    function drawZone(x, y, w, h, label, color) {
      ctx.fillStyle = color;
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = '#72808c';
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = '#f0f4f8';
      ctx.font = '12px system-ui';
      ctx.fillText(label, x + 10, y + 24);
    }

    function drawObjects(w, h, objects) {
      if (!objects.length) {
        const defaults = [
          { id: 'red_block', label: 'red block', color: 'red', x: 0.34, y: 0.38 },
          { id: 'blue_block', label: 'blue block', color: 'blue', x: 0.50, y: 0.45 },
          { id: 'yellow_block', label: 'yellow block', color: 'yellow', x: 0.40, y: 0.60 },
        ];
        objects = defaults;
      }
      for (const obj of objects) {
        const x = obj.x ? obj.x * w : seededX(obj.id, w);
        const y = obj.y ? obj.y * h : seededY(obj.id, h);
        const color = colorFor(obj.color || obj.id);
        ctx.fillStyle = color;
        ctx.strokeStyle = obj.highlighted ? '#ffffff' : '#111315';
        ctx.lineWidth = obj.highlighted ? 4 : 2;
        ctx.beginPath();
        ctx.roundRect(x - 14, y - 14, 28, 28, 5);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = '#f0f4f8';
        ctx.font = '11px system-ui';
        ctx.fillText(obj.label || obj.id, x - 24, y + 30);
      }
    }

    function drawArm(w, h, ws) {
      const baseX = w / 2;
      const baseY = h - 54;
      const target = ws.arm_target || { x: 0.55, y: 0.46 };
      const tx = target.x ? target.x * w : w / 2;
      const ty = target.y ? target.y * h : h / 2;
      ctx.strokeStyle = '#c4ccd4';
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.moveTo(baseX, baseY);
      ctx.lineTo((baseX + tx) / 2, (baseY + ty) / 2);
      ctx.lineTo(tx, ty);
      ctx.stroke();
      ctx.fillStyle = '#c4ccd4';
      ctx.beginPath();
      ctx.arc(baseX, baseY, 13, 0, Math.PI * 2);
      ctx.fill();
    }

    function seededX(id, w) {
      return 90 + (hash(id || '') % Math.max(120, Math.floor(w - 220)));
    }

    function seededY(id, h) {
      return 90 + (hash((id || '') + 'y') % Math.max(120, Math.floor(h - 220)));
    }

    function colorFor(value) {
      if (String(value).includes('red')) return '#e55353';
      if (String(value).includes('blue')) return '#4f83e8';
      if (String(value).includes('yellow')) return '#d7b84f';
      return '#9aa7b4';
    }

    function hash(str) {
      let h = 0;
      for (let i = 0; i < str.length; i++) h = ((h << 5) - h + str.charCodeAt(i)) | 0;
      return Math.abs(h);
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[ch]));
    }

    if (!CanvasRenderingContext2D.prototype.roundRect) {
      CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
        this.moveTo(x + r, y);
        this.arcTo(x + w, y, x + w, y + h, r);
        this.arcTo(x + w, y + h, x, y + h, r);
        this.arcTo(x, y + h, x, y, r);
        this.arcTo(x, y, x + w, y, r);
      };
    }
    connect();
    addEventListener('resize', () => renderWorkspace());
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_server()
