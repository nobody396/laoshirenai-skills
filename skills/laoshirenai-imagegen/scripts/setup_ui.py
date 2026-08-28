#!/usr/bin/env python3
"""Open a one-time localhost form for secure image-key onboarding."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser

from _runtime import (
    ImagegenConfigError,
    agent_switch_path,
    ensure_runtime,
    store_secret_agent_switch,
    store_secret_file,
)
from doctor import check_access


MAX_FORM_BYTES = 8192


def page(token: str, script_nonce: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>配置老实人AI生图</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    body {{ margin:0; background:#f6f3ee; color:#201d19; }}
    main {{ max-width:520px; margin:10vh auto; padding:32px; background:#fff; border:1px solid #e6ddd2; border-radius:18px; box-shadow:0 18px 55px rgba(50,35,20,.10); }}
    h1 {{ margin:0 0 12px; font-size:28px; }}
    p {{ line-height:1.65; color:#62584d; }}
    label {{ display:block; margin:24px 0 8px; font-weight:650; }}
    input {{ box-sizing:border-box; width:100%; padding:13px 14px; border:1px solid #cfc4b8; border-radius:10px; font-size:16px; }}
    button {{ width:100%; margin-top:16px; padding:13px; border:0; border-radius:10px; color:#fff; background:#9d3f24; font-size:16px; font-weight:700; cursor:pointer; }}
    button:disabled {{ opacity:.55; cursor:wait; }}
    #status {{ min-height:24px; margin-top:14px; font-weight:600; }}
    .safe {{ font-size:13px; color:#75695d; }}
  </style>
</head>
<body>
<main>
  <h1>配置老实人AI生图</h1>
  <p>粘贴从“GPT Image 2 生图分组”创建的 API Key。保存后会自动检查权限并准备运行环境，不会生成图片或产生费用。</p>
  <form id="setup">
    <label for="key">独立生图 API Key</label>
    <input id="key" name="key" type="password" required autofocus autocomplete="off" spellcheck="false">
    <input name="token" type="hidden" value="{token}">
    <button id="submit" type="submit">保存并完成配置</button>
  </form>
  <div id="status" role="status" aria-live="polite"></div>
  <p class="safe">Key 只提交到本机 127.0.0.1，不会进入聊天记录、Shell 历史或项目文件。</p>
</main>
<script nonce="{script_nonce}">
const form = document.getElementById('setup');
const button = document.getElementById('submit');
const status = document.getElementById('status');
form.addEventListener('submit', async (event) => {{
  event.preventDefault();
  button.disabled = true;
  status.textContent = '正在检查 Key 并准备环境，请稍候……';
  try {{
    const response = await fetch('/configure', {{
      method: 'POST',
      headers: {{'Content-Type':'application/x-www-form-urlencoded'}},
      body: new URLSearchParams(new FormData(form)),
      cache: 'no-store',
    }});
    const result = await response.json();
    status.textContent = result.message;
    if (result.ok) {{ form.reset(); button.textContent = '配置完成'; }}
    else {{ button.disabled = false; }}
  }} catch (_) {{
    status.textContent = '配置连接中断，请重新打开配置页。';
    button.disabled = false;
  }}
}});
</script>
</body>
</html>""".encode("utf-8")


class SetupState:
    def __init__(self, token: str, skip_runtime: bool, storage: str) -> None:
        self.token = token
        self.skip_runtime = skip_runtime
        self.storage = storage
        self.success = False


def handler_factory(state: SetupState, script_nonce: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LaoshirenAISetup/1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def security_headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{script_nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'",
            )

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != "/" or query.get("token", [""])[0] != state.token:
                self.send_error(404)
                return
            body = page(state.token, script_nonce)
            self.send_response(200)
            self.security_headers("text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def json_response(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.security_headers("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/configure":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_FORM_BYTES:
                self.json_response(413, {"ok": False, "message": "提交内容无效。"})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/x-www-form-urlencoded":
                self.json_response(415, {"ok": False, "message": "提交格式无效。"})
                return
            values = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            if values.get("token", [""])[0] != state.token:
                self.json_response(403, {"ok": False, "message": "配置页已经失效，请重新打开。"})
                return
            key = values.get("key", [""])[0].strip()
            if not key or len(key) > 4096 or any(ch.isspace() for ch in key):
                self.json_response(400, {"ok": False, "message": "请输入有效的 API Key。"})
                return
            try:
                check_access(key)
                use_agent_switch = state.storage == "agent-switch" or (
                    state.storage == "auto" and agent_switch_path() and os.name != "nt"
                )
                if use_agent_switch:
                    store_secret_agent_switch(key)
                else:
                    store_secret_file(key)
                if not state.skip_runtime:
                    ensure_runtime()
            except ImagegenConfigError as exc:
                self.json_response(400, {"ok": False, "message": f"配置失败：{exc}"})
                return
            state.success = True
            self.json_response(200, {"ok": True, "message": "配置成功，可以关闭此页面并回到 Codex。"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Open the 老实人AI image Skill setup page")
    parser.add_argument("--no-browser", action="store_true", help="print the local URL without opening a browser")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--storage", choices=("auto", "agent-switch", "file"), default="auto")
    parser.add_argument("--skip-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout < 10 or args.timeout > 3600:
        parser.error("--timeout must be between 10 and 3600 seconds")

    token = secrets.token_urlsafe(32)
    script_nonce = secrets.token_urlsafe(24)
    state = SetupState(token, args.skip_runtime, args.storage)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(state, script_nonce))
    url = f"http://127.0.0.1:{server.server_port}/?token={urllib.parse.quote(token)}"
    opened = False if args.no_browser else webbrowser.open(url, new=1, autoraise=True)
    if opened:
        print("Configuration page opened in your browser.", flush=True)
    else:
        print(f"Setup URL: {url}", flush=True)
    timer = threading.Timer(args.timeout, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        timer.cancel()
        server.server_close()
    if state.success:
        print("Image Skill configuration completed.")
        return 0
    print("Configuration timed out or was cancelled.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
