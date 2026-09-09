"""Loopback-only HTTP server for the Isaac Helper web interface."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Callable, Sequence
from urllib.parse import unquote, urlsplit, parse_qs
import webbrowser

from .catalog import CATEGORY_DEFINITIONS, CHARACTERS, build_catalog
from .discovery import AccountInfo, DiscoveryError, discover_accounts, resolve_selection
from .readers.binary_kv import BinaryKVError
from .readers.steam_stats import SteamStatsError, read_schema
from .snapshots import SnapshotError, build_snapshot, load_snapshot
from .wiki_catalog import load_wiki_overrides


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_REQUEST_BYTES = 64 * 1024


class IsaacHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        error = sys.exception()
        if isinstance(error, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def _public_characters() -> list[dict[str, object]]:
    return [
        {key: value for key, value in item.items() if key not in {"aliases", "unlock_title"}}
        for item in CHARACTERS
    ]


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    project_root: Path | None = None,
    accounts_provider: Callable[[], Sequence[AccountInfo]] = discover_accounts,
) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("Isaac Helper may only bind to 127.0.0.1")
    root = Path(project_root or PROJECT_ROOT).resolve()
    web_root = root / "web"
    profiles_root = root / "data" / "profiles"

    class Handler(SimpleHTTPRequestHandler):
        server_version = "IsaacHelper/0.1"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def log_message(self, format_string: str, *args) -> None:
            print(f"[{self.log_date_time_string()}] {format_string % args}")

        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, code: str, message: str) -> None:
            self._send_json(status, {"error": {"code": code, "message": message}})

        def _loopback_host(self) -> bool:
            host = self.headers.get("Host", "")
            try:
                hostname = urlsplit(f"//{host}").hostname
            except ValueError:
                return False
            return hostname in {"127.0.0.1", "localhost"}

        def _same_site_update(self) -> bool:
            if self.headers.get("Sec-Fetch-Site", "").casefold() == "cross-site":
                return False
            origin = self.headers.get("Origin")
            if not origin:
                return True
            try:
                parsed = urlsplit(origin)
            except ValueError:
                return False
            return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}

        def _read_request_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._error(400, "invalid_request", "Content-Length 无效")
                return None
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._error(400, "invalid_request", "请求内容为空或过大")
                return None
            body = self.rfile.read(length)
            if len(body) != length:
                self._error(400, "invalid_request", "请求内容不完整")
                return None
            return body

        def do_GET(self) -> None:
            if not self._loopback_host():
                self._error(421, "invalid_host", "仅允许通过本机地址访问")
                return
            parsed = urlsplit(self.path)
            if parsed.path == "/api/accounts":
                accounts = list(accounts_provider())
                self._send_json(200, {"accounts": [item.as_dict() for item in accounts]})
                return
            if parsed.path == "/api/catalog":
                accounts = list(accounts_provider())
                schema_path = next(
                    (item.schema_path for item in accounts if item.schema_path.is_file()), None
                )
                achievements = (
                    build_catalog(read_schema(schema_path), overrides=load_wiki_overrides())
                    if schema_path else []
                )
                self._send_json(200, {
                    "achievements": achievements,
                    "characters": _public_characters(),
                    "categories": CATEGORY_DEFINITIONS,
                    "warning": None if schema_path else "未找到本地 Steam 成就 Schema",
                })
                return
            if parsed.path == "/api/state":
                query = parse_qs(parsed.query)
                account_id = query.get("account_id", query.get("account", [""]))[0]
                try:
                    slot = int(query.get("slot", [""])[0])
                    selection = resolve_selection(account_id, slot, list(accounts_provider()))
                    state = load_snapshot(profiles_root, selection.account.id, selection.slot.number)
                except (ValueError, DiscoveryError) as exc:
                    self._error(400, "invalid_selection", str(exc))
                    return
                if state is None:
                    self._error(404, "snapshot_not_found", "该档位还没有本地进度快照")
                else:
                    self._send_json(200, state)
                return
            if parsed.path.startswith("/api/"):
                self._error(404, "not_found", "接口不存在")
                return
            decoded_parts = unquote(parsed.path).replace("\\", "/").split("/")
            if ".." in decoded_parts:
                self.send_error(404)
                return
            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path != "/api/update":
                self._error(404, "not_found", "接口不存在")
                return
            body = self._read_request_body()
            if body is None:
                return
            if not self._loopback_host():
                self._error(421, "invalid_host", "仅允许通过本机地址访问")
                return
            if not self._same_site_update():
                self._error(403, "cross_site_request", "拒绝跨站更新请求")
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                self._error(415, "unsupported_media_type", "请求必须使用 application/json")
                return
            try:
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("JSON 根节点必须是对象")
                account_id = payload.get("account_id")
                slot = payload.get("slot")
                if not isinstance(account_id, str) or not isinstance(slot, int):
                    raise ValueError("account_id 必须是字符串，slot 必须是整数")
                selection = resolve_selection(account_id, slot, list(accounts_provider()))
                state = build_snapshot(selection, profiles_root)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, DiscoveryError) as exc:
                self._error(400, "invalid_selection", str(exc))
                return
            except (OSError, BinaryKVError, SteamStatsError, SnapshotError) as exc:
                self._error(422, "read_failed", str(exc))
                return
            self._send_json(200, state)

    return IsaacHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Isaac Helper locally")
    parser.add_argument("--port", type=int, default=0, help="loopback port; 0 chooses a free port")
    parser.add_argument("--open", action="store_true", help="open the default browser")
    args = parser.parse_args()
    server = create_server(port=args.port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Isaac Helper: {url}")
    print("按 Ctrl+C 停止服务。")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nIsaac Helper 已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
