"""Portable Windows launcher for the local web UI."""

from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from pathlib import Path

from ve_analyse.webui import create_server


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app_dir = portable_app_dir(args.app_dir)
    state_path = Path(args.state_path) if args.state_path else default_state_path(app_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    port = available_port(args.host, args.port)
    server = create_server(args.host, port, state_path)
    url = f"http://{args.host}:{server.server_port}/"

    print("VE Analyse portable is running.", flush=True)
    print(f"Open: {url}", flush=True)
    print(f"State: {state_path}", flush=True)
    print("Close this window or press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url, new=2)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the portable VE Analyse web UI")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred port. Falls back to a free port.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser.")
    parser.add_argument("--state-path", default=None, help="Override state JSON path.")
    parser.add_argument("--app-dir", default=None, help="Override portable app directory.")
    return parser


def portable_app_dir(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def default_state_path(app_dir: Path) -> Path:
    return app_dir / "data" / "state.json"


def available_port(host: str, preferred_port: int) -> int:
    if preferred_port <= 0:
        return 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, preferred_port))
        except OSError:
            return 0
    return preferred_port


if __name__ == "__main__":
    raise SystemExit(main())
