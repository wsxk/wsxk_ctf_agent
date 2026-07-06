from __future__ import annotations

import contextlib
import socketserver
import threading
from typing import Any

from .store import PlatformStore


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler_class: type[socketserver.BaseRequestHandler], store: PlatformStore):
        super().__init__(server_address, handler_class)
        self.store = store


class PwnGatewayHandler(socketserver.BaseRequestHandler):
    server: ThreadedTCPServer

    def handle(self) -> None:
        with contextlib.suppress(ConnectionError, OSError):
            self.request.settimeout(120)
            self._send(b"HWCTF TCP Gateway\n")
            self._send(b"Send routing header: HWCTF <env_id> <agent_key>\n")
            header = self._readline()
            parts = header.strip().split()
            if len(parts) != 3 or parts[0] != "HWCTF":
                self._send(b"ERR invalid routing header\n")
                return
            _, env_id, agent_key = parts
            env = self.server.store.get_env_for_routing(env_id, agent_key)
            if not env:
                self._send(b"ERR env not found or not running\n")
                return
            challenge = self.server.store.get_challenge(int(env["challenge_id"]))
            if str(challenge["category"]) != "pwn":
                self._send(b"ERR env is not a pwn challenge\n")
                return
            self._serve_demo_pwn(challenge, env)

    def _serve_demo_pwn(self, challenge: dict[str, Any], env: dict[str, Any]) -> None:
        flags = [str(flag) for flag in challenge.get("flags", [])]
        banner = str(challenge.get("pwn", {}).get("banner", "demo pwn service"))
        self._send(f"\n{banner}\n".encode())
        self._send(f"challenge={challenge['name']} env={env['external_env_id']}\n".encode())
        self._send(b"Type help for commands.\n")
        while True:
            self._send(b"> ")
            command_line = self._readline()
            if not command_line:
                return
            command = command_line.strip()
            if command in {"exit", "quit"}:
                self._send(b"bye\n")
                return
            if command == "help":
                self._send(b"commands: help, echo <text>, flag, exit\n")
            elif command.startswith("echo "):
                self._send((command[5:] + "\n").encode())
            elif command == "flag":
                flag = flags[0] if flags else "FLAG{missing}"
                self._send((flag + "\n").encode())
            else:
                self._send(b"unknown command\n")

    def _readline(self) -> str:
        chunks: list[bytes] = []
        while True:
            chunk = self.request.recv(1)
            if not chunk:
                break
            if chunk == b"\n":
                break
            if chunk != b"\r":
                chunks.append(chunk)
            if len(chunks) > 4096:
                break
        return b"".join(chunks).decode("utf-8", errors="replace")

    def _send(self, data: bytes) -> None:
        self.request.sendall(data)


class PwnGateway:
    def __init__(self, host: str, port: int, store: PlatformStore) -> None:
        self.host = host
        self.port = port
        self.store = store
        self.server = ThreadedTCPServer((host, port), PwnGatewayHandler, store)
        self.thread = threading.Thread(target=self.server.serve_forever, name="pwn-gateway", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
