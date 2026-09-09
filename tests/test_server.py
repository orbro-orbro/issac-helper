import json
import io
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from contextlib import redirect_stderr
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        project = Path(self.temp.name)
        web = project / "web"
        web.mkdir()
        (web / "index.html").write_text("<h1>Isaac Helper</h1>", encoding="utf-8")
        self.server = create_server(
            port=0,
            project_root=project,
            accounts_provider=lambda: [],
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
