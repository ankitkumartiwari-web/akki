from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from . import __version__

logger = logging.getLogger("akki.webui")

ChatHandler = Callable[[str], dict[str, Any]]
StatusHandler = Callable[[], dict[str, Any]]
ToolsHandler = Callable[[], list[dict[str, Any]]]

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AKKI</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #080b12;
      --panel: #101624;
      --panel-2: #151d2e;
      --line: #263149;
      --text: #e7ecf5;
      --muted: #8c9ab3;
      --accent: #6ee7ff;
      --user: #1d4ed8;
      --akki: #162033;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(circle at top, #132039 0, var(--bg) 48%);
      color: var(--text);
      font-family: "Segoe UI", system-ui, sans-serif;
    }
    .shell {
      width: min(980px, 100%);
      min-height: 100vh;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 18px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 18px 20px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
    }
    h1 { margin: 0; font-size: 1.2rem; letter-spacing: 0.18em; }
    .status { color: var(--muted); font-size: 0.82rem; text-align: right; }
    .messages {
      overflow-y: auto;
      padding: 4px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .message {
      max-width: 82%;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--akki);
    }
    .message.user {
      align-self: flex-end;
      background: var(--user);
      border-color: #2f6bff;
    }
    .role {
      margin-bottom: 6px;
      color: var(--accent);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .message.user .role { color: #bfdbfe; }
    .text { white-space: pre-wrap; line-height: 1.5; overflow-wrap: anywhere; }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      padding: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
    }
    input {
      width: 100%;
      padding: 13px 14px;
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 11px;
      font: inherit;
      outline: none;
    }
    input:focus { border-color: var(--accent); }
    button {
      padding: 0 20px;
      background: var(--accent);
      color: #041019;
      border: 0;
      border-radius: 11px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    .hint { color: var(--muted); font-size: 0.74rem; }
    @media (max-width: 640px) {
      .shell { padding: 12px; }
      header { align-items: flex-start; flex-direction: column; }
      .message { max-width: 94%; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>AKKI</h1>
        <div class="hint">Local-first assistant. Type a command or question.</div>
      </div>
      <div class="status" id="status">connecting...</div>
    </header>
    <main class="messages" id="messages" aria-live="polite"></main>
    <form id="chat-form">
      <input id="message" autocomplete="off" autofocus placeholder="Ask AKKI or enter a command">
      <button id="send" type="submit">Send</button>
    </form>
  </div>
  <script>
    const messages = document.querySelector("#messages");
    const form = document.querySelector("#chat-form");
    const input = document.querySelector("#message");
    const send = document.querySelector("#send");
    const status = document.querySelector("#status");

    function append(role, text) {
      const article = document.createElement("article");
      article.className = "message " + role;
      const label = document.createElement("div");
      label.className = "role";
      label.textContent = role === "user" ? "You" : "AKKI";
      const body = document.createElement("div");
      body.className = "text";
      body.textContent = text;
      article.append(label, body);
      messages.append(article);
      messages.scrollTop = messages.scrollHeight;
    }

    async function refreshStatus() {
      try {
        const response = await fetch("/api/status");
        const data = await response.json();
        status.textContent = data.version + " | " + data.profile + " | " + data.model;
      } catch (error) {
        status.textContent = "status unavailable";
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      append("user", text);
      input.value = "";
      send.disabled = true;
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text })
        });
        const data = await response.json();
        append("akki", data.message || "no reply");
      } catch (error) {
        append("akki", "request failed: " + error);
      } finally {
        send.disabled = false;
        input.focus();
      }
    });

    refreshStatus();
    append("akki", "AKKI is ready.");
  </script>
</body>
</html>"""


class WebUIError(RuntimeError):
    pass


class _Handler(BaseHTTPRequestHandler):
    server_version = f"AKKI/{__version__}"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send_json(self.server.akki_status())
            return
        if path == "/api/tools":
            self._send_json({"tools": self.server.akki_tools()})
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"ok": False, "message": "invalid content length"}, HTTPStatus.BAD_REQUEST)
            return
        if length <= 0 or length > 1_000_000:
            self._send_json({"ok": False, "message": "request body is empty or too large"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"ok": False, "message": "invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return
        text = str(payload.get("text", "")).strip() if isinstance(payload, dict) else ""
        if not text:
            self._send_json({"ok": False, "message": "text is required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            reply = self.server.akki_chat(text)
        except Exception as exc:
            logger.exception("web chat failed")
            self._send_json({"ok": False, "message": f"request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(reply)

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("webui %s - %s", self.address_string(), format % args)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status)

    def _send_bytes(
        self, body: bytes, content_type: str, *, status: int = HTTPStatus.OK
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class WebUI:
    def __init__(
        self,
        chat: ChatHandler,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        status: StatusHandler | None = None,
        tools: ToolsHandler | None = None,
    ) -> None:
        self.chat = chat
        self.host = host
        self.port = port
        self.status = status or (lambda: {})
        self.tools = tools or (lambda: [])
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self.active:
            return self.url
        try:
            server = ThreadingHTTPServer((self.host, self.port), _Handler)
        except OSError as exc:
            raise WebUIError(f"could not start web UI on {self.host}:{self.port}: {exc}") from exc
        server.akki_chat = self.chat
        server.akki_status = self.status
        server.akki_tools = self.tools
        server.daemon_threads = True
        self.port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, name="akki-webui", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        logger.info("web ui started at %s", self.url)
        return self.url

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(2)
        logger.info("web ui stopped")
