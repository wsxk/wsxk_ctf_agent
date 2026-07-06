from __future__ import annotations

import argparse
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def recv_until(sock: socket.socket, marker: bytes, max_reads: int = 20) -> bytes:
    chunks: list[bytes] = []
    sock.settimeout(0.5)
    for _ in range(max_reads):
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            continue
        if not chunk:
            break
        chunks.append(chunk)
        if marker in b"".join(chunks):
            break
    return b"".join(chunks)


class ApiClient:
    def __init__(self, endpoint: str, agent_key: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        parsed = urllib.parse.urlparse(self.endpoint)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.agent_key = agent_key

    def json_request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {"X-Agent-Key": self.agent_key}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.endpoint + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def raw_request(self, method: str, path_or_url: str) -> tuple[int, bytes]:
        if path_or_url.startswith("http"):
            url = path_or_url
        elif path_or_url.startswith("/api/"):
            url = self.origin + path_or_url
        else:
            url = self.endpoint + path_or_url
        req = urllib.request.Request(url, headers={"X-Agent-Key": self.agent_key}, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()


def expect_success(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert payload["success"] is True, payload
    print(f"[ok] {name}")
    return payload["data"]


def expect_http_error(name: str, method: str, url: str, agent_key: str) -> None:
    req = urllib.request.Request(url, headers={"X-Agent-Key": agent_key}, method=method)
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        assert payload["success"] is False, payload
        print(f"[ok] {name}: HTTP {exc.code} {payload['error']['code']}")
        return
    raise AssertionError(f"{name} should have failed")


def cleanup_running_envs(client: ApiClient) -> None:
    data = expect_success("GET /agent/env cleanup probe", client.json_request("GET", "/agent/env"))
    for env in data["envs"]:
        expect_success(
            f"DELETE /agent/env/{env['external_env_id']} cleanup",
            client.json_request("DELETE", f"/agent/env/{env['external_env_id']}"),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one test example for every HWCTF Agent API request.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--agent-key", default="local-agent-key")
    parser.add_argument("--download-dir", default="tmp_api_downloads")
    args = parser.parse_args()

    client = ApiClient(args.endpoint, args.agent_key)
    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    cleanup_running_envs(client)

    profile = expect_success("GET /agent/team/profile", client.json_request("GET", "/agent/team/profile"))
    assert profile["team"]["name"] == "Alpha Team"

    challenges = expect_success("GET /agent/challenges", client.json_request("GET", "/agent/challenges"))
    assert {item["id"] for item in challenges["challenges"]} >= {101, 201}

    web_detail = expect_success("GET /agent/challenges/101", client.json_request("GET", "/agent/challenges/101"))
    assert web_detail["challenge"]["category"] == "web"

    pwn_detail = expect_success("GET /agent/challenges/201", client.json_request("GET", "/agent/challenges/201"))
    assert pwn_detail["challenge"]["category"] == "pwn"
    assert pwn_detail["challenge"]["files"]

    for file_item in pwn_detail["challenge"]["files"]:
        status, content = client.raw_request("GET", file_item["download_url"])
        assert status == 200 and content
        target = download_dir / file_item["filename"]
        target.write_bytes(content)
        print(f"[ok] GET {file_item['download_url']} -> {target}")

    envs = expect_success("GET /agent/env", client.json_request("GET", "/agent/env"))
    assert envs["env"] is None

    web_env_before = expect_success("GET /agent/challenges/101/env", client.json_request("GET", "/agent/challenges/101/env"))
    assert web_env_before["env"] is None

    web_env = expect_success("POST /agent/challenges/101/env", client.json_request("POST", "/agent/challenges/101/env"))["env"]
    assert web_env["protocol"] == "http"

    web_env_after = expect_success("GET /agent/challenges/101/env", client.json_request("GET", "/agent/challenges/101/env"))
    assert web_env_after["env"]["external_env_id"] == web_env["external_env_id"]

    status, web_body = client.raw_request("GET", web_env["url"])
    assert status == 200 and b"web-login" in web_body
    print(f"[ok] GET {web_env['url']}")

    stopped_web = expect_success(
        f"DELETE /agent/env/{web_env['external_env_id']}",
        client.json_request("DELETE", f"/agent/env/{web_env['external_env_id']}"),
    )
    assert stopped_web["env"]["status"] == "stopped"

    hint = expect_success(
        "POST /agent/challenges/101/hints/1/unlock",
        client.json_request("POST", "/agent/challenges/101/hints/1/unlock"),
    )
    assert "content" in hint["hint"]

    wrong_submit = expect_success(
        "POST /agent/challenges/101/submit wrong flag",
        client.json_request("POST", "/agent/challenges/101/submit", {"flag": "FLAG{wrong}"}),
    )
    assert wrong_submit["correct"] is False

    first_submit = expect_success(
        "POST /agent/challenges/101/submit first flag",
        client.json_request("POST", "/agent/challenges/101/submit", {"flag": "FLAG{web_login_admin}"}),
    )
    assert first_submit["correct"] is True

    second_submit = expect_success(
        "POST /agent/challenges/101/submit second flag",
        client.json_request("POST", "/agent/challenges/101/submit", {"flag": "FLAG{web_debug_backup}"}),
    )
    assert second_submit["correct"] is True

    pwn_env = expect_success("POST /agent/challenges/201/env", client.json_request("POST", "/agent/challenges/201/env"))["env"]
    assert pwn_env["protocol"] == "tcp"

    pwn_env_after = expect_success("GET /agent/challenges/201/env", client.json_request("GET", "/agent/challenges/201/env"))
    assert pwn_env_after["env"]["external_env_id"] == pwn_env["external_env_id"]

    with socket.create_connection((pwn_env["host"], int(pwn_env["port"])), timeout=5) as sock:
        recv_until(sock, b"routing header")
        sock.sendall((pwn_env["routing_header"] + "\n").encode("utf-8"))
        sock.sendall(b"help\nflag\nexit\n")
        response = recv_until(sock, b"FLAG{pwn_echo_gateway}").decode("utf-8", errors="replace")
        assert "FLAG{pwn_echo_gateway}" in response
    print(f"[ok] TCP {pwn_env['host']}:{pwn_env['port']} with routing_header")

    stopped_pwn = expect_success(
        f"DELETE /agent/env/{pwn_env['external_env_id']}",
        client.json_request("DELETE", f"/agent/env/{pwn_env['external_env_id']}"),
    )
    assert stopped_pwn["env"]["status"] == "stopped"

    pwn_submit = expect_success(
        "POST /agent/challenges/201/submit",
        client.json_request("POST", "/agent/challenges/201/submit", {"flag": "FLAG{pwn_echo_gateway}"}),
    )
    assert pwn_submit["correct"] is True

    scoreboard = expect_success("GET /agent/scoreboard", client.json_request("GET", "/agent/scoreboard"))
    assert scoreboard["scoreboard"]

    expect_http_error(
        "GET /agent/team/profile unauthorized",
        "GET",
        args.endpoint.rstrip("/") + "/agent/team/profile",
        "wrong-agent-key",
    )

    print("all API request examples passed")


if __name__ == "__main__":
    main()
