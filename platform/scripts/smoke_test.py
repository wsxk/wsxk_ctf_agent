from __future__ import annotations

import argparse
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


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


def request(method: str, base_url: str, path: str, agent_key: str, body: dict | None = None) -> dict:
    data = None
    headers = {"X-Agent-Key": agent_key}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {payload}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--agent-key", default="local-agent-key")
    args = parser.parse_args()

    profile = request("GET", args.endpoint, "/agent/team/profile", args.agent_key)
    print("profile:", profile["data"]["team"]["name"])

    challenges = request("GET", args.endpoint, "/agent/challenges", args.agent_key)["data"]["challenges"]
    print("challenges:", ", ".join(challenge["name"] for challenge in challenges))

    web_env = request("POST", args.endpoint, "/agent/challenges/101/env", args.agent_key)["data"]["env"]
    print("web env:", web_env["url"])
    web_req = urllib.request.Request(web_env["url"], headers={"X-Agent-Key": args.agent_key})
    with urllib.request.urlopen(web_req, timeout=5) as resp:
        assert b"web-login" in resp.read()
    request("DELETE", args.endpoint, f"/agent/env/{web_env['external_env_id']}", args.agent_key)

    pwn_env = request("POST", args.endpoint, "/agent/challenges/201/env", args.agent_key)["data"]["env"]
    print("pwn env:", pwn_env["url"])
    with socket.create_connection((pwn_env["host"], int(pwn_env["port"])), timeout=5) as sock:
        recv_until(sock, b"routing header")
        sock.sendall((pwn_env["routing_header"] + "\n").encode("utf-8"))
        sock.sendall(b"help\nexit\n")
        response = recv_until(sock, b"commands:").decode("utf-8", errors="replace")
        assert "pwn-echo" in response or "commands:" in response
    request("DELETE", args.endpoint, f"/agent/env/{pwn_env['external_env_id']}", args.agent_key)

    wrong = request("POST", args.endpoint, "/agent/challenges/101/submit", args.agent_key, {"flag": "FLAG{wrong}"})
    assert wrong["data"]["correct"] is False
    print("smoke test passed")


if __name__ == "__main__":
    main()
