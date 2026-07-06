from __future__ import annotations

import argparse
from pathlib import Path

from .config import ServerConfig
from .http_api import CTFHTTPServer, CTFRequestHandler
from .pwn_gateway import PwnGateway
from .store import PlatformStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local HWCTF-compatible dynamic challenge platform.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8000, help="HTTP bind port")
    parser.add_argument("--public-host", default="127.0.0.1", help="Host returned in env URLs")
    parser.add_argument("--pwn-host", default="127.0.0.1", help="Pwn TCP gateway bind host")
    parser.add_argument("--pwn-port", type=int, default=9005, help="Pwn TCP gateway port")
    parser.add_argument("--reset-state", action="store_true", help="Clear local scoreboard, solves, and env state at startup")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_dir = Path(__file__).resolve().parents[1]
    config = ServerConfig(
        base_dir=base_dir,
        host=args.host,
        port=args.port,
        public_host=args.public_host,
        pwn_host=args.pwn_host,
        pwn_port=args.pwn_port,
    )
    store = PlatformStore(config)
    if args.reset_state:
        store.reset_state()

    pwn_gateway = PwnGateway(config.pwn_host, config.pwn_port, store)
    pwn_gateway.start()

    httpd = CTFHTTPServer((config.host, config.port), CTFRequestHandler, store, config)
    print("Local HWCTF platform is running.")
    print(f"API endpoint: {config.api_endpoint}")
    print("Default Agent Key: local-agent-key")
    print(f"Pwn TCP gateway: {config.public_host}:{config.pwn_port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        httpd.shutdown()
        httpd.server_close()
        pwn_gateway.stop()


if __name__ == "__main__":
    main()
