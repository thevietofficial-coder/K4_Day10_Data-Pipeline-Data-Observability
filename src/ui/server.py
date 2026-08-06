from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.config import Settings, load_settings
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex

_LOCK = threading.RLock()
_INDEX_CACHE: dict[str, LocalEmbeddingIndex] = {}
_AGENT_CACHE: dict[str, Any] = {}

_STATE_LABELS = {
    "baseline": "Baseline (sạch)",
    "corrupted": "Corrupted (đã làm hỏng)",
    "repaired": "Repaired (đã phục hồi)",
}


def _state_path(settings: Settings, state: str) -> Path:
    return {
        "baseline": settings.paths.embeddings_json,
        "corrupted": settings.paths.corrupted_embeddings_json,
        "repaired": settings.paths.repaired_embeddings_json,
    }[state]


def _get_index(settings: Settings, state: str) -> LocalEmbeddingIndex:
    with _LOCK:
        if state not in _INDEX_CACHE:
            path = _state_path(settings, state)
            if not path.exists():
                raise FileNotFoundError(
                    f"Chưa có index cho trạng thái '{state}'. "
                    "Chạy script/run_phase1.py hoặc script/run_corruption_flow.py trước."
                )
            _INDEX_CACHE[state] = LocalEmbeddingIndex.load(settings, embeddings_path=path)
        return _INDEX_CACHE[state]


def _get_agent(settings: Settings, state: str):
    with _LOCK:
        if state not in _AGENT_CACHE:
            index = _get_index(settings, state)
            _AGENT_CACHE[state] = build_agent(settings, index)
        return _AGENT_CACHE[state]


INDEX_HTML = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>SilverFlag — RAG Agent</title>
<style>
  :root {
    --surface: #F4F6F9; --surface-card: #FFFFFF; --surface-alt: #FAFBFD; --surface-sunken: #EDF0F4;
    --ink: #121821; --ink-secondary: #45505C; --ink-muted: #7A8592;
    --border: #E1E6EC; --border-strong: #CBD3DB;
    --blue: #3B66C4; --blue-soft: #E9EEFA;
    --red: #E03131; --red-soft: #FBE3E3;
    --teal: #12959B; --teal-soft: #DFF3F3;
    --shadow: 0 1px 2px rgba(18,24,33,.04), 0 8px 24px -12px rgba(18,24,33,.12);
    --font-display: Georgia, 'Iowan Old Style', 'Palatino Linotype', serif;
    --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    --font-mono: ui-monospace, 'SF Mono', 'Cascadia Code', Consolas, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root { --surface:#0B0F14; --surface-card:#131A22; --surface-alt:#0F151C; --surface-sunken:#0E141B;
      --ink:#EEF2F6; --ink-secondary:#B4BEC9; --ink-muted:#7E8B99; --border:#232E3A; --border-strong:#33404F;
      --blue:#6E93E8; --blue-soft:#1B2740; --red:#F0555A; --red-soft:#3A1E22; --teal:#22B4BA; --teal-soft:#10302E;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 12px 32px -16px rgba(0,0,0,.55); }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { background: var(--surface); color: var(--ink); font-family: var(--font-body); display: flex; flex-direction: column; }

  header { border-bottom: 1px solid var(--border); padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; background: var(--surface-card); }
  .brand { display: flex; flex-direction: column; gap: 2px; }
  .eyebrow { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--blue); font-weight: 700; }
  h1 { font-family: var(--font-display); font-weight: 400; font-size: 20px; margin: 0; }

  .state-toggle { display: flex; gap: 6px; background: var(--surface-sunken); padding: 4px; border-radius: 10px; }
  .state-btn { font-family: var(--font-mono); font-size: 11.5px; font-weight: 600; padding: 7px 12px; border-radius: 7px; border: none; background: transparent; color: var(--ink-muted); cursor: pointer; white-space: nowrap; transition: all .15s ease; }
  .state-btn:disabled { opacity: .35; cursor: not-allowed; }
  .state-btn.active[data-state="baseline"] { background: var(--surface-card); color: var(--blue); box-shadow: var(--shadow); }
  .state-btn.active[data-state="corrupted"] { background: var(--surface-card); color: var(--red); box-shadow: var(--shadow); }
  .state-btn.active[data-state="repaired"] { background: var(--surface-card); color: var(--teal); box-shadow: var(--shadow); }

  main { flex: 1; display: flex; flex-direction: column; max-width: 860px; width: 100%; margin: 0 auto; padding: 20px; gap: 14px; min-height: 0; }
  .hint { font-size: 12.5px; color: var(--ink-muted); text-align: center; }
  .hint strong { color: var(--ink-secondary); }

  #thread { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; padding: 4px 2px 12px; min-height: 0; }
  .msg { display: flex; flex-direction: column; gap: 6px; max-width: 82%; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.agent { align-self: flex-start; align-items: flex-start; }
  .bubble { border-radius: 14px; padding: 12px 14px; font-size: 14px; line-height: 1.5; box-shadow: var(--shadow); }
  .msg.user .bubble { background: var(--blue); color: #fff; border-bottom-right-radius: 4px; }
  .msg.agent .bubble { background: var(--surface-card); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  .msg.agent .bubble.error { background: var(--red-soft); border-color: transparent; color: var(--red); }
  .state-tag { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .04em; text-transform: uppercase; font-weight: 700; padding: 2px 7px; border-radius: 999px; }
  .state-tag.baseline { color: var(--blue); background: var(--blue-soft); }
  .state-tag.corrupted { color: var(--red); background: var(--red-soft); }
  .state-tag.repaired { color: var(--teal); background: var(--teal-soft); }

  .sources { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
  .source-chip { font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-secondary); background: var(--surface-alt); border: 1px solid var(--border); border-radius: 7px; padding: 4px 8px; max-width: 260px; }
  .source-chip .sc-id { color: var(--ink-muted); }
  .source-chip .sc-score { color: var(--teal); font-weight: 700; }

  .typing { display: flex; gap: 4px; padding: 4px 2px; }
  .typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-muted); animation: bounce 1.1s infinite ease-in-out; }
  .typing span:nth-child(2) { animation-delay: .15s; }
  .typing span:nth-child(3) { animation-delay: .3s; }
  @keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .5; } 30% { transform: translateY(-4px); opacity: 1; } }

  form#composer { display: flex; gap: 8px; border-top: 1px solid var(--border); padding-top: 14px; }
  #question { flex: 1; font-family: var(--font-body); font-size: 14px; padding: 12px 14px; border-radius: 10px; border: 1px solid var(--border-strong); background: var(--surface-card); color: var(--ink); }
  #question:focus { outline: 2px solid var(--blue); outline-offset: 1px; }
  #send { font-family: var(--font-mono); font-size: 12.5px; font-weight: 700; padding: 0 20px; border-radius: 10px; border: none; background: var(--blue); color: #fff; cursor: pointer; }
  #send:disabled { opacity: .5; cursor: not-allowed; }

  @media (max-width: 640px) { .msg { max-width: 92%; } header { flex-direction: column; align-items: flex-start; } }
</style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="eyebrow">SilverFlag · Day 10 Data Pipeline Lab</span>
      <h1>RAG Agent — hỏi đáp trên corpus Crossref</h1>
    </div>
    <div class="state-toggle" id="state-toggle">
      <button class="state-btn active" data-state="baseline">Baseline</button>
      <button class="state-btn" data-state="corrupted">Corrupted</button>
      <button class="state-btn" data-state="repaired">Repaired</button>
    </div>
  </header>
  <main>
    <p class="hint">Đang hỏi trên dataset <strong id="hint-state">Baseline (sạch)</strong> — đổi nút phía trên để hỏi cùng một câu trên dataset khác và so sánh câu trả lời trực tiếp.</p>
    <div id="thread"></div>
    <form id="composer">
      <input id="question" type="text" autocomplete="off" placeholder="Ví dụ: When was &quot;Hi-RAG&quot; published? / Who authored ...?" />
      <button id="send" type="submit">Gửi</button>
    </form>
  </main>

<script>
  const thread = document.getElementById("thread");
  const form = document.getElementById("composer");
  const input = document.getElementById("question");
  const sendBtn = document.getElementById("send");
  const toggle = document.getElementById("state-toggle");
  const hintState = document.getElementById("hint-state");
  const STATE_LABEL = { baseline: "Baseline (sạch)", corrupted: "Corrupted (đã làm hỏng)", repaired: "Repaired (đã phục hồi)" };
  let currentState = "baseline";

  function addMessage(role, html, stateTag) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const tag = stateTag ? `<span class="state-tag ${stateTag}">${STATE_LABEL[stateTag]}</span>` : "";
    wrap.innerHTML = `${tag}<div class="bubble">${html}</div>`;
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
    return wrap;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function refreshStates() {
    try {
      const res = await fetch("/api/states");
      const data = await res.json();
      Object.entries(data.states).forEach(([state, available]) => {
        const btn = toggle.querySelector(`[data-state="${state}"]`);
        if (btn) btn.disabled = !available;
      });
    } catch (e) { /* server chưa sẵn sàng, bỏ qua */ }
  }

  toggle.addEventListener("click", (e) => {
    const btn = e.target.closest(".state-btn");
    if (!btn || btn.disabled) return;
    toggle.querySelectorAll(".state-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentState = btn.dataset.state;
    hintState.textContent = STATE_LABEL[currentState];
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    addMessage("user", escapeHtml(question));
    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;

    const typingMsg = addMessage("agent", '<div class="typing"><span></span><span></span><span></span></div>', currentState);

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, state: currentState }),
      });
      const data = await res.json();
      typingMsg.remove();
      if (!res.ok || data.error) {
        addMessage("agent", `<span class="bubble error">${escapeHtml(data.error || "Lỗi không xác định")}</span>`.replace(/^<span class="bubble error">/, '').replace(/<\/span>$/, ''), currentState);
        const last = thread.lastElementChild.querySelector(".bubble");
        last.classList.add("error");
        last.textContent = data.error || "Lỗi không xác định";
      } else {
        const sourcesHtml = (data.sources || []).map(s =>
          `<span class="source-chip"><span class="sc-id">${escapeHtml(s.paper_id)}</span> · ${escapeHtml((s.title||"").slice(0,42))}${s.title && s.title.length>42?"…":""} · <span class="sc-score">${s.score}</span></span>`
        ).join("");
        addMessage("agent", `${escapeHtml(data.answer)}${sourcesHtml ? `<div class="sources">${sourcesHtml}</div>` : ""}`, currentState);
      }
    } catch (err) {
      typingMsg.remove();
      addMessage("agent", "Không kết nối được tới server. Kiểm tra lại terminal đang chạy script/run_ui.py.", currentState);
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });

  refreshStates();
  addMessage("agent", "Xin chào! Tôi là agent trả lời câu hỏi dựa trên corpus bài báo học thuật đã index từ Crossref. Chọn dataset ở góc trên và đặt câu hỏi.", "baseline");
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    settings: Settings

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/states":
            states = {state: _state_path(self.settings, state).exists() for state in _STATE_LABELS}
            self._send_json({"states": states})
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/ask":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
            question = str(payload.get("question", "")).strip()
            state = str(payload.get("state", "baseline")).strip()
            if not question:
                raise ValueError("Câu hỏi rỗng.")
            if state not in _STATE_LABELS:
                raise ValueError(f"Trạng thái không hợp lệ: {state!r}")

            index = _get_index(self.settings, state)
            sources = index.search(question, top_k=4)
            agent = _get_agent(self.settings, state)
            answer = run_agent_question(agent, question)

            self._send_json(
                {
                    "answer": answer,
                    "state": state,
                    "sources": [
                        {
                            "paper_id": s.paper_id,
                            "title": s.title,
                            "score": round(s.score, 3),
                        }
                        for s in sources
                    ],
                }
            )
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=409)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 - surface any agent/LLM failure to the UI
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=500)

    def log_message(self, fmt: str, *args) -> None:  # quieter stdlib access log
        pass


def run(port: int = 8765) -> None:
    settings = load_settings()
    Handler.settings = settings
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"SilverFlag RAG Agent UI dang chay tai: {url}")
    print("Mo link tren trong trinh duyet. Nhan Ctrl+C de dung server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
