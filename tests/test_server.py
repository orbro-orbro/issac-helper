import json
import io
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from contextlib import redirect_stderr
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.catalog_update import CatalogUpdateResult
from app.server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        project = Path(self.temp.name)
        web = project / "web"
        web.mkdir()
        (web / "index.html").write_text("<h1>Isaac Helper</h1>", encoding="utf-8")
        self.catalog = {
            "schema_version": 2,
            "generated_at": "2026-09-09T00:00:00+00:00",
            "achievement_count": 0,
            "achievements": [],
            "diagnostics": {},
        }
        self.catalog_update_calls = 0
        self.progress_update_calls = 0

        def update_catalog(schema_path, catalog_path, icons_dir):
            self.catalog_update_calls += 1
            return CatalogUpdateResult(
                ok=True,
                updated_at="2026-09-10T00:00:00+00:00",
                achievement_count=641,
                completeness={"display.name_zh": 600},
                warnings=("one fallback icon",),
                errors=(),
            )

        self.server = create_server(
            port=0,
            project_root=project,
            accounts_provider=lambda: [],
            catalog_loader=lambda _: self.catalog,
            catalog_updater=update_catalog,
        )
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method: str, path: str, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    def test_lists_accounts_with_no_cache_headers(self):
        status, headers, body = self.request("GET", "/api/accounts")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body), {"accounts": []})

    def test_rejects_update_with_unknown_account(self):
        status, _, body = self.request(
            "POST", "/api/update", {"account_id": "other", "slot": 2}
        )

        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_selection")

    def test_catalog_update_does_not_require_account_or_slot(self):
        status, _, body = self.request("POST", "/api/catalog/update", {})
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.catalog_update_calls, 1)
        self.assertEqual(self.progress_update_calls, 0)

    def test_catalog_update_rejects_client_parameters(self):
        status, _, body = self.request(
            "POST", "/api/catalog/update", {"schema_path": "C:/other.bin"}
        )

        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_request")
        self.assertEqual(self.catalog_update_calls, 0)

    def test_catalog_update_rejects_cross_site_origin(self):
        request = Request(
            self.base + "/api/catalog/update",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://attacker.test",
            },
            method="POST",
        )

        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.catalog_update_calls, 0)

    def test_serves_catalog_with_registries_without_mutating_loaded_payload(self):
        status, _, body = self.request("GET", "/api/catalog")
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertEqual(payload["generated_at"], "2026-09-09T00:00:00+00:00")
        self.assertEqual(len(payload["characters"]), 34)
        self.assertIn("character", payload["categories"])
        self.assertNotIn("characters", self.catalog)
        self.assertNotIn("categories", self.catalog)

    def test_catalog_status_reads_active_catalog_without_refreshing(self):
        status, _, body = self.request("GET", "/api/catalog/status")
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertEqual(payload["updated_at"], "2026-09-09T00:00:00+00:00")
        self.assertEqual(payload["achievement_count"], 0)
        self.assertIn("display.name_zh", payload["completeness"])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(self.catalog_update_calls, 0)

    def test_catalog_load_failure_is_stable_and_other_routes_remain_available(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

        def unavailable(_):
            raise OSError("missing catalog")

        self.server = create_server(
            port=0,
            project_root=Path(self.temp.name),
            accounts_provider=lambda: [],
            catalog_loader=unavailable,
            catalog_updater=lambda *args: None,
        )
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

        status, _, body = self.request("GET", "/api/catalog")
        accounts_status, _, accounts_body = self.request("GET", "/api/accounts")

        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"]["code"], "catalog_unavailable")
        self.assertEqual(accounts_status, 200)
        self.assertEqual(json.loads(accounts_body), {"accounts": []})

    def test_rejects_non_json_update(self):
        request = Request(
            self.base + "/api/update",
            data=b"account=123",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
        except HTTPError as error:
            body = error.read()
            self.assertEqual(error.code, 415)
            self.assertEqual(
                json.loads(body)["error"]["code"], "unsupported_media_type"
            )
        else:
            self.fail("non-JSON update unexpectedly succeeded")

    def test_rejects_non_loopback_host_header(self):
        request = Request(self.base + "/api/accounts", headers={"Host": "attacker.test"})

        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 421)

    def test_rejects_cross_site_update_origin(self):
        request = Request(
            self.base + "/api/update",
            data=b'{"account_id":"123","slot":2}',
            headers={
                "Content-Type": "application/json",
                "Origin": "https://attacker.test",
            },
            method="POST",
        )

        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 403)

    def test_static_paths_cannot_escape_web_root(self):
        status, _, _ = self.request("GET", "/%2e%2e/README.md")
        self.assertEqual(status, 404)

    def test_serves_index(self):
        status, headers, body = self.request("GET", "/")

        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Isaac Helper", body)

    def test_client_disconnect_does_not_print_traceback(self):
        captured = io.StringIO()
        with redirect_stderr(captured):
            try:
                raise ConnectionAbortedError("browser closed")
            except ConnectionAbortedError:
                self.server.handle_error(None, ("127.0.0.1", 12345))

        self.assertEqual(captured.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
