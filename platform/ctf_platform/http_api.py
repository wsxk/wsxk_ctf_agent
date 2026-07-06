from __future__ import annotations

import html
import json
import mimetypes
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .config import ServerConfig
from .errors import ApiError, bad_request, not_found, unauthorized
from .store import PlatformStore


class CTFHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        store: PlatformStore,
        config: ServerConfig,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.store = store
        self.config = config


class CTFRequestHandler(BaseHTTPRequestHandler):
    server: CTFHTTPServer

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[http] {self.address_string()} - {fmt % args}")

    def _dispatch(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            segments = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            if parsed.path == "/" and method == "GET":
                self._landing()
                return
            if parsed.path == "/healthz" and method == "GET":
                self._json(200, {"ok": True})
                return
            if segments[:2] == ["api", "v1"]:
                self._api_route(method, segments[2:])
                return
            if segments[:1] == ["e"]:
                self._web_env_route(method, segments[1:], parse_qs(parsed.query))
                return
            raise not_found("route not found")
        except ApiError as exc:
            self._error(exc)
        except Exception as exc:  # pragma: no cover - last line of defense
            traceback.print_exc()
            self._error(ApiError("internal_error", str(exc), 500, "Internal server error."))

    def _api_route(self, method: str, segments: list[str]) -> None:
        if segments[:1] == ["agent"]:
            team = self._require_team()
            agent_key = str(team["agent_key"])
            rest = segments[1:]
            if method == "GET" and rest == ["team", "profile"]:
                self._json_success({"team": {"id": int(team["id"]), "name": str(team["name"])}})
                return
            if method == "GET" and rest == ["challenges"]:
                self._json_success({"challenges": self.server.store.list_challenges(agent_key)})
                return
            if method == "GET" and len(rest) == 2 and rest[0] == "challenges":
                challenge_id = self._parse_int(rest[1], "challenge_id")
                self._json_success({"challenge": self.server.store.challenge_detail(agent_key, challenge_id)})
                return
            if method == "GET" and rest == ["env"]:
                envs = self.server.store.list_envs(agent_key)
                self._json_success({"envs": envs, "env": envs[0] if envs else None})
                return
            if method == "GET" and len(rest) == 3 and rest[0] == "challenges" and rest[2] == "env":
                challenge_id = self._parse_int(rest[1], "challenge_id")
                env = self.server.store.get_env_for_challenge(agent_key, challenge_id)
                self._json_success({"env": env})
                return
            if method == "POST" and len(rest) == 3 and rest[0] == "challenges" and rest[2] == "env":
                challenge_id = self._parse_int(rest[1], "challenge_id")
                env = self.server.store.start_env(agent_key, challenge_id)
                self._json_success({"env": env})
                return
            if method == "DELETE" and len(rest) == 2 and rest[0] == "env":
                env = self.server.store.stop_env(agent_key, rest[1])
                self._json_success({"env": {"external_env_id": env["external_env_id"], "status": env["status"]}})
                return
            if (
                method == "POST"
                and len(rest) == 5
                and rest[0] == "challenges"
                and rest[2] == "hints"
                and rest[4] == "unlock"
            ):
                challenge_id = self._parse_int(rest[1], "challenge_id")
                hint_id = self._parse_int(rest[3], "hint_id")
                hint = self.server.store.unlock_hint(agent_key, challenge_id, hint_id)
                self._json_success({"hint": hint})
                return
            if method == "POST" and len(rest) == 3 and rest[0] == "challenges" and rest[2] == "submit":
                challenge_id = self._parse_int(rest[1], "challenge_id")
                body = self._read_json()
                result = self.server.store.submit_flag(agent_key, challenge_id, str(body.get("flag", "")))
                self._json_success(result)
                return
            if method == "GET" and rest == ["scoreboard"]:
                self._json_success({"scoreboard": self.server.store.scoreboard()})
                return

        if segments[:1] == ["challenge-platform"]:
            self._require_team()
            rest = segments[1:]
            if method == "GET" and len(rest) == 3 and rest[0] == "files" and rest[2] == "download":
                file_id = self._parse_int(rest[1], "file_id")
                self._download_file(file_id)
                return

        raise not_found("route not found")

    def _web_env_route(self, method: str, segments: list[str], query: dict[str, list[str]]) -> None:
        if not segments:
            raise not_found("env not found")
        team = self._require_team()
        agent_key = str(team["agent_key"])
        env_id = segments[0]
        env = self.server.store.get_running_env_for_access(agent_key, env_id)
        challenge = self.server.store.get_challenge(int(env["challenge_id"]))
        if str(challenge["category"]) != "web":
            raise bad_request("env is not a web challenge", status=409)
        subpath = "/".join(segments[1:])
        if str(challenge.get("web", {}).get("template", "login")) == "login":
            self._web_login_challenge(method, env, challenge, subpath, query)
            return
        raise bad_request("unsupported web challenge template")

    def _web_login_challenge(
        self,
        method: str,
        env: dict[str, Any],
        challenge: dict[str, Any],
        subpath: str,
        query: dict[str, list[str]],
    ) -> None:
        flags = [str(flag) for flag in challenge.get("flags", [])]
        path = subpath.strip("/")
        if method == "GET" and path in {"", "index"}:
            self._html(
                200,
                self._page(
                    challenge,
                    env,
                    """
                    <form method="post" action="login">
                      <label>Username <input name="username" autocomplete="off"></label>
                      <label>Password <input name="password" type="password"></label>
                      <button type="submit">Login</button>
                    </form>
                    <p class="muted">Demo service is isolated by env id and Agent Key.</p>
                    """,
                ),
            )
            return
        if method == "POST" and path == "login":
            form = self._read_form()
            username = form.get("username", [""])[0]
            password = form.get("password", [""])[0]
            expected = str(challenge.get("web", {}).get("password", "localpass"))
            if username == "admin" and password == expected:
                self._html(
                    200,
                    self._page(
                        challenge,
                        env,
                        f"""
                        <h2>Welcome admin</h2>
                        <p class="flag">{html.escape(flags[0])}</p>
                        <p><a href="backup?debug=1">Open debug backup</a></p>
                        """,
                    ),
                )
            else:
                self._html(
                    403,
                    self._page(challenge, env, "<h2>Login failed</h2><p>Invalid username or password.</p>"),
                )
            return
        if method == "GET" and path == "backup":
            if query.get("debug", ["0"])[0] == "1":
                second = flags[1] if len(flags) > 1 else flags[0]
                self._html(
                    200,
                    self._page(
                        challenge,
                        env,
                        f"<h2>debug backup</h2><pre>{html.escape(second)}</pre>",
                    ),
                )
            else:
                self._html(404, self._page(challenge, env, "<h2>Not found</h2>"))
            return
        raise not_found("web challenge path not found")

    def _page(self, challenge: dict[str, Any], env: dict[str, Any], body: str) -> str:
        title = html.escape(str(challenge["name"]))
        env_id = html.escape(str(env["external_env_id"]))
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 48px auto; padding: 0 20px; }}
    main {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 24px; }}
    label {{ display: block; margin: 12px 0; }}
    input {{ display: block; margin-top: 4px; width: min(360px, 100%); padding: 8px; }}
    button {{ margin-top: 12px; padding: 9px 14px; }}
    .muted {{ color: #57606a; }}
    .flag {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; padding: 12px; background: #f6f8fa; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p class="muted">env: {env_id}</p>
    {body}
  </main>
</body>
</html>"""

    def _landing(self) -> None:
        api = html.escape(self.server.config.api_endpoint)
        body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Local HWCTF Platform</title></head>
<body>
  <h1>Local HWCTF Platform</h1>
  <p>API endpoint: <code>{api}</code></p>
  <p>Use <code>X-Agent-Key: local-agent-key</code> for the default team.</p>
</body>
</html>"""
        self._html(200, body)

    def _require_team(self) -> dict[str, Any]:
        agent_key = self.headers.get("X-Agent-Key")
        team = self.server.store.get_team_by_key(agent_key)
        if not team:
            raise unauthorized()
        return team

    def _parse_int(self, value: str, name: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise bad_request(f"{name} must be an integer") from exc

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise bad_request("request body must be valid JSON") from exc
        if not isinstance(data, dict):
            raise bad_request("request body must be a JSON object")
        return data

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else ""
        return parse_qs(raw)

    def _download_file(self, file_id: int) -> None:
        path, filename = self.server.store.get_file(file_id)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self._send_common_headers(content_type=mime_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_success(self, data: dict[str, Any], status: int = 200) -> None:
        self._json(status, {"success": True, "data": data})

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers(content_type="application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self._send_common_headers(content_type="text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, exc: ApiError) -> None:
        payload = {
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "description": exc.description,
                "http_status": exc.http_status,
            },
        }
        self._json(exc.http_status, payload)

    def _send_common_headers(self, content_type: str | None = None) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Agent-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        if content_type:
            self.send_header("Content-Type", content_type)
