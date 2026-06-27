"""Local web UI server for VE Analyse."""

from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import webapi


STATIC_DIR = Path(__file__).with_name("web_static")


@dataclass
class WebApplication:
    state_path: Path | None = None


class VeAnalyseServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], app: WebApplication) -> None:
        super().__init__(server_address, VeAnalyseHandler)
        self.app = app


class VeAnalyseHandler(BaseHTTPRequestHandler):
    server: VeAnalyseServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                self._send_file(STATIC_DIR / "index.html")
            elif parsed.path.startswith("/static/"):
                self._send_file(STATIC_DIR / parsed.path.removeprefix("/static/"))
            elif parsed.path == "/api/state":
                self._send_json(webapi.state_payload(self.server.app.state_path))
            elif parsed.path == "/api/log":
                query = parse_qs(parsed.query)
                self._send_json(webapi.log_metadata(query.get("path", [""])[0]))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/state":
                self._send_json(webapi.save_state_payload(payload, self.server.app.state_path))
            elif parsed.path == "/api/graph":
                self._send_json(
                    webapi.graph_payload(
                        str(payload.get("path", "")),
                        _string_list(payload.get("variables")),
                        int(payload.get("max_points_per_series", 2500)),
                    )
                )
            elif parsed.path == "/api/analyze":
                self._send_json(webapi.analyse_payload(payload))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def _send_json(self, payload: dict[str, object]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        static_root = STATIC_DIR.resolve()
        if static_root not in resolved.parents and resolved != static_root:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not resolved.exists() or not resolved.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        raw = resolved.read_bytes()
        content_type, _encoding = mimetypes.guess_type(str(resolved))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        raw = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the VE Analyse local web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--state-path",
        default=None,
        help="State JSON path. Defaults to .ve-analyse-web-state.json in the launch directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_path = Path(args.state_path) if args.state_path else Path.cwd() / ".ve-analyse-web-state.json"
    app = WebApplication(state_path=state_path)
    server = VeAnalyseServer((args.host, args.port), app)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"VE Analyse web UI running at {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
