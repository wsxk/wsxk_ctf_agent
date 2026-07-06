from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    base_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    public_host: str = "127.0.0.1"
    pwn_host: str = "127.0.0.1"
    pwn_port: int = 9005

    @property
    def http_origin(self) -> str:
        return f"http://{self.public_host}:{self.port}"

    @property
    def api_endpoint(self) -> str:
        return f"{self.http_origin}/api/v1"

    @property
    def tcp_url(self) -> str:
        return f"tcp://{self.public_host}:{self.pwn_port}"
