"""Loopback-only HTTP server for the Isaac Helper web interface."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Callable, Sequence
from urllib.parse import unquote, urlsplit, parse_qs
import webbrowser

from . import APP_ID
from .catalog import CATEGORY_DEFINITIONS, CHARACTERS
from .catalog_store import CatalogLoadError, load_catalog, validate_catalog
from .catalog_update import CatalogUpdateResult, update_achievement_catalog
from .discovery import (
    AccountInfo,
    DiscoveryError,
    default_steam_roots,
    discover_accounts,
    resolve_selection,
)
from .readers.binary_kv import BinaryKVError
from .readers.steam_stats import SteamStatsError
from .snapshots import SnapshotError, build_snapshot, load_snapshot


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


def _catalog_schema_path(accounts: Sequence[AccountInfo]) -> Path:
    candidates = [item.schema_path for item in accounts]
    candidates.extend(
        root / "appcache" / "stats" / f"UserGameStatsSchema_{APP_ID}.bin"
        for root in default_steam_roots()
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    project_root: Path | None = None,
    accounts_provider: Callable[[], Sequence[AccountInfo]] = discover_accounts,
    catalog_loader: Callable[[Path], dict[str, object]] = load_catalog,
    catalog_updater: Callable[[Path, Path, Path], CatalogUpdateResult] = (
        update_achievement_catalog
    ),
) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("Isaac Helper may only bind to 127.0.0.1")
    root = Path(project_root or PROJECT_ROOT).resolve()
    web_root = root / "web"
    profiles_root = root / "data" / "profiles"
    catalog_path = root / "data" / "catalog" / "achievements.json"
    icons_dir = web_root / "assets" / "achievements"

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

        def _read_json_object(self) -> dict[str, object] | None:
            body = self._read_request_body()
            if body is None:
                return None
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._error(400, "invalid_request", f"JSON 无效：{exc}")
                return None
            if not isinstance(payload, dict):
                self._error(400, "invalid_request", "JSON 根节点必须是对象")
                return None
            return payload

        def _active_catalog(self) -> dict[str, object] | None:
            try:
                return dict(catalog_loader(catalog_path))
            except (OSError, ValueError, CatalogLoadError) as exc:
                self._error(503, "catalog_unavailable", str(exc))
                return None

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
                payload = self._active_catalog()
                if payload is None:
                    return
                payload["characters"] = _public_characters()
                payload["categories"] = CATEGORY_DEFINITIONS
                self._send_json(200, payload)
                return
            if parsed.path == "/api/catalog/status":
                payload = self._active_catalog()
                if payload is None:
                    return
                achievement_count = payload.get("achievement_count", 0)
                expected_count = (
                    achievement_count
                    if isinstance(achievement_count, int)
                    and not isinstance(achievement_count, bool)
                    else 641
                )
                validation = validate_catalog(
                    payload,
                    expected_count=expected_count,
                    assets_root=web_root,
                )
                stored_warnings = payload.get("warnings", [])
                warnings = (
                    [item for item in stored_warnings if isinstance(item, str)]
                    if isinstance(stored_warnings, list)
                    else []
                )
                warnings.extend(validation.warnings)
                self._send_json(200, {
                    "updated_at": payload.get("generated_at"),
                    "achievement_count": achievement_count,
                    "completeness": validation.completeness,
                    "warnings": warnings,
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
            if parsed.path not in {"/api/update", "/api/catalog/update"}:
                self._error(404, "not_found", "接口不存在")
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
            payload = self._read_json_object()
            if payload is None:
                return
            if parsed.path == "/api/catalog/update":
                if payload:
                    self._error(400, "invalid_request", "成就资料更新不接受参数")
                    return
                accounts = list(accounts_provider())
                schema_path = _catalog_schema_path(accounts)
                result = catalog_updater(schema_path, catalog_path, icons_dir)
                self._send_json(200 if result.ok else 422, asdict(result))
                return
            try:
                account_id = payload.get("account_id")
                slot = payload.get("slot")
                if not isinstance(account_id, str) or not isinstance(slot, int):
                    raise ValueError("account_id 必须是字符串，slot 必须是整数")
                selection = resolve_selection(account_id, slot, list(accounts_provider()))
            except (ValueError, DiscoveryError) as exc:
                self._error(400, "invalid_selection", str(exc))
                return
            try:
                state = build_snapshot(
                    selection,
                    profiles_root,
                    catalog_path=catalog_path,
                )
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
