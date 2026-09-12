"""Focused fake-model HTTP tests for the invite-only beta browser wrapper."""
from contextlib import closing
import http.client
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from bibleprep import beta_preview as subject
from bibleprep import beta_server


SECRET = "correct-horse-battery-staple-preview-secret"


class FakeLibrary:
    count = 2

    def select(self, messages):
        return ([{
            "id": "Gen.1.1", "reference": "Genesis 1:1",
            "requested_reference": "Genesis 1:1", "edition": "Fixture edition",
            "text": "בְּרֵאשִׁית", "language": "Hebrew",
            "url": "https://github.com/example/source/blob/revision/Gen.xml",
            "editorial_status": "main", "numbering": "source coordinates requested",
            "attribution": "Fixture attribution", "editorial_notes": [],
        }], ["Fixture source limit."])

    def context(self, sources, notes):
        return "fixture source context"


class FakeModel:
    def __init__(self):
        self.calls = []
        self.closed = False

    def generate(self, messages, evidence_context=""):
        self.calls.append((messages, evidence_context))
        return {"answer": "A final fake answer.", "answer_complete": True,
                "warnings": [], "usage": {"estimated_usd": 0.001}}

    def close(self):
        self.closed = True


class PreviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        invite = beta_server.make_invite_record(
            "reader-one", SECRET, 5 * beta_server.MAX_RESERVATION_NANO,
            salt_hex="22" * 16)
        config = {"schema_version": 1, "status": "active_hash_only_invites",
                  "global_cap_nano_usd": 10 * beta_server.MAX_RESERVATION_NANO,
                  "session_ttl_seconds": beta_server.SESSION_TTL_SECONDS,
                  "invites": [invite]}
        self.store = beta_server.BetaStore(root / "private/beta.sqlite3", config)
        self.model = FakeModel()
        self.app = beta_server.BetaApplication(
            store=self.store, root=root, model_factory=lambda: self.model,
            library=FakeLibrary())
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        handler = subject.handler_for(
            self.app, origin=self.origin, secure_cookie=False,
            asset_root=subject.ASSET_ROOT)
        self.server = beta_server.BetaHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close)

    def _close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.app.close()

    def request(self, method, path, body=None, cookie=None, origin=True, *,
                host=None, port=None):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers.update({"Content-Type": "application/json",
                            "Content-Length": str(len(data))})
        if method == "POST" and origin:
            headers["Origin"] = self.origin if origin is True else origin
        if cookie:
            headers["Cookie"] = cookie
        if host:
            headers["Host"] = host
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port if port is None else port, timeout=3)
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        content = response.read()
        result = response.status, dict(response.getheaders()), content
        connection.close()
        return result

    def login(self):
        status, headers, body = self.request("POST", "/api/login", {
            "invite_id": "reader-one", "invite_secret": SECRET})
        self.assertEqual(status, 200, body)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, _ = self.request("POST", "/api/accept-terms", {
            "terms_version": "2026-09-11.1", "adult": True}, cookie)
        self.assertEqual(status, 200)
        return cookie

    def test_static_allowlist_and_security_headers(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, (subject.ASSET_ROOT / "index.html").read_bytes())
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn(b"cloudflareinsights", body)
        self.assertNotIn("cloudflareinsights", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        for path in ("/beta/app.js", "/beta/styles.css", "/index.html", "/privacy", "/terms", "/brand", "/favicon.svg", "/favicon-v2.svg", "/favicon-v3.svg", "/favicon-v5.svg", "/favicon-dark-v5.svg", "/favicon.ico", "/favicon-v5.ico", "/apple-touch-icon.png", "/apple-touch-v4.png", "/beta/logo.svg", "/beta/logo-v4.svg", "/beta/consent.js", "/beta/legal.css"):
            self.assertEqual(self.request("GET", path)[0], 200)
        for path in ("/.env.example", "/../bibleprep/beta_server.py", "/app.js",
                     "/styles.css", "/beta/app.js?changed=1"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 404)
            self.assertNotIn(SECRET.encode(), body)
        self.assertIsNone(self.app.model)

    def test_legacy_railway_host_redirects_only_ui_for_canonical_origin(self):
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            hosted_port = sock.getsockname()[1]
        handler = subject.handler_for(
            self.app, origin=subject.CANONICAL_ORIGIN, secure_cookie=True,
            asset_root=subject.ASSET_ROOT)
        server = beta_server.BetaHTTPServer(("127.0.0.1", hosted_port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/", "/privacy", "/terms", "/brand"):
                status, headers, body = self.request(
                    "GET", path, host="meforash.com", port=hosted_port)
                self.assertEqual(status, 200)
                self.assertEqual(body.count(subject.ANALYTICS_BEACON), 1)
                self.assertEqual(int(headers["Content-Length"]), len(body))
                self.assertIn("https://static.cloudflareinsights.com", headers["Content-Security-Policy"])
                self.assertIn("https://cloudflareinsights.com", headers["Content-Security-Policy"])
                self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
            status, headers, body = self.request(
                "GET", "/", host=subject.LEGACY_RAILWAY_HOST, port=hosted_port)
            self.assertEqual(status, 308)
            self.assertEqual(headers["Location"], subject.CANONICAL_ORIGIN + "/")
            self.assertEqual(body, b"")

            status, headers, body = self.request(
                "HEAD", "/beta/app.js", host=subject.LEGACY_RAILWAY_HOST,
                port=hosted_port)
            self.assertEqual(status, 308)
            self.assertEqual(
                headers["Location"], subject.CANONICAL_ORIGIN + "/beta/app.js")
            self.assertEqual(body, b"")

            status, headers, _ = self.request(
                "GET", "/health", host=subject.LEGACY_RAILWAY_HOST,
                port=hosted_port)
            self.assertEqual(status, 200)
            self.assertNotIn("Location", headers)

            status, headers, _ = self.request(
                "GET", "/api/access", host=subject.LEGACY_RAILWAY_HOST,
                port=hosted_port)
            self.assertEqual(status, 200)
            self.assertNotIn("Location", headers)

            status, headers, body = self.request(
                "POST", "/api/guest", {}, origin=subject.CANONICAL_ORIGIN,
                host=subject.LEGACY_RAILWAY_HOST, port=hosted_port)
            self.assertEqual(status, 403, body)
            self.assertNotIn("Location", headers)

            status, _, _ = self.request(
                "GET", "/", host="meforash.com", port=hosted_port)
            self.assertEqual(status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

        # Merely receiving the old Host does not enable the redirect locally.
        self.assertEqual(self.request(
            "GET", "/", host=subject.LEGACY_RAILWAY_HOST)[0], 200)

    def test_unauthorized_api_never_initializes_model(self):
        status, _, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 401)
        status, _, _ = self.request("POST", "/api/chat", {
            "messages": [{"role": "user", "content": "Genesis 1:1"}]})
        self.assertEqual(status, 401)
        self.assertIsNone(self.app.model)
        self.assertEqual(self.model.calls, [])

    def test_login_cookie_and_authenticated_status(self):
        status, _, _ = self.request("POST", "/api/login", {
            "invite_id": "reader-one", "invite_secret": "x" * 24})
        self.assertEqual(status, 401)
        self.assertIsNone(self.app.model)
        cookie = self.login()
        status, _, body = self.request("GET", "/api/status", cookie=cookie)
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertIn("retained B", value["model"])
        self.assertEqual(value["conversation_storage"], "not_stored")
        self.assertIsNone(self.app.model)

    def test_chat_payload_polling_and_source_cards_use_existing_api(self):
        cookie = self.login()
        messages = [{"role": "user", "content": "What does Genesis 1:1 say?"}]
        status, _, body = self.request("POST", "/api/chat", {"messages": messages}, cookie)
        self.assertEqual(status, 202, body)
        request_id = json.loads(body)["request_id"]
        deadline = time.monotonic() + 2
        while True:
            status, _, body = self.request("GET", "/api/chat/" + request_id, cookie=cookie)
            self.assertEqual(status, 200, body)
            result = json.loads(body)
            if result["status"] != "running":
                break
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["answer"], "A final fake answer.")
        self.assertEqual(result["sources"][0]["reference"], "Genesis 1:1")
        self.assertEqual(self.model.calls, [(messages, "fixture source context")])

    def test_logout_clears_backend_session_and_cookie(self):
        cookie = self.login()
        status, headers, body = self.request("POST", "/api/logout", {}, cookie)
        self.assertEqual(status, 200, body)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/status", cookie=cookie)[0], 401)


class PreviewBoundaryTests(unittest.TestCase):
    def test_vector_monogram_and_favicon_fallbacks_are_wired(self):
        root = subject.ASSET_ROOT
        logo = (root / "logo.svg").read_text()
        favicon = (root / "favicon.svg").read_text()
        dark_favicon = (root / "favicon-dark.svg").read_text()
        self.assertIn("Hebrew mem and Latin m monogram", logo)
        self.assertIn("Hebrew mem mark", favicon)
        self.assertIn("dark browser themes", dark_favicon)
        self.assertIn('viewBox="8 6 53 53"', favicon)
        self.assertIn("#252a25", logo)
        self.assertNotIn("#252a25", favicon)
        self.assertIn('fill="#faf8f1"', favicon)
        self.assertIn('fill="#58715f"', dark_favicon)
        self.assertIn('stroke="#fff"', dark_favicon)
        for vector in (logo, favicon, dark_favicon):
            self.assertNotIn("<text", vector)
            self.assertNotIn("font-family", vector)
        self.assertNotIn("<rect", logo)
        for name in ("index.html", "privacy.html", "terms.html", "brand.html"):
            markup = (root / name).read_text()
            self.assertIn('src="/beta/logo-v4.svg"', markup)
            self.assertIn('<span class="brand-name">meforash</span>', markup)
            self.assertIn('<span class="brand-subtitle">original-language Bible exploration</span>', markup)
            ico_link = 'href="/favicon-v5.ico" sizes="16x16 32x32 48x48"'
            svg_link = 'href="/favicon-v5.svg" type="image/svg+xml" sizes="any" media="(prefers-color-scheme: light)"'
            dark_svg_link = 'href="/favicon-dark-v5.svg" type="image/svg+xml" sizes="any" media="(prefers-color-scheme: dark)"'
            self.assertIn(ico_link, markup)
            self.assertIn(svg_link, markup)
            self.assertIn(dark_svg_link, markup)
            self.assertLess(markup.index(ico_link), markup.index(svg_link))
            self.assertIn('href="/apple-touch-v4.png" sizes="180x180"', markup)
        png = (root / "apple-touch-icon.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(png[16:20], "big"), 180)
        self.assertEqual(int.from_bytes(png[20:24], "big"), 180)
        self.assertEqual(png[25], 6)
        ico = (root / "favicon.ico").read_bytes()
        self.assertEqual(ico[:4], b"\x00\x00\x01\x00")
        self.assertEqual(int.from_bytes(ico[4:6], "little"), 3)

        brand = subject.ROOT / "brand"
        self.assertEqual((brand / "mark-primary.svg").read_text(), logo)
        for name in ("mark-primary.svg", "mark-black.svg", "mark-reverse.svg", "mark-dark.svg"):
            vector = (brand / name).read_text()
            self.assertNotIn("<text", vector)
            self.assertNotIn("font-family", vector)
        for size in (256, 512, 1024):
            export = (brand / f"mark-primary-{size}.png").read_bytes()
            self.assertEqual(export[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(int.from_bytes(export[16:20], "big"), size)
            self.assertEqual(int.from_bytes(export[20:24], "big"), size)
            self.assertEqual(export[25], 6)
        dark_export = (brand / "mark-dark-512.png").read_bytes()
        self.assertEqual(dark_export[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(dark_export[16:20], "big"), 512)
        self.assertEqual(int.from_bytes(dark_export[20:24], "big"), 512)
        self.assertEqual(dark_export[25], 6)
        readme = (brand / "README.md").read_text()
        self.assertIn("authoritative reusable logo asset", readme)
        self.assertIn("../docs/BRAND-POLICY.md", readme)

    def test_beta_label_and_invitation_fallback_are_visible_without_javascript(self):
        markup = (subject.ASSET_ROOT / "index.html").read_text()
        self.assertIn('<span class="preview-badge">Beta</span>', markup)
        self.assertIn("JavaScript is required to use this beta.", markup)
        self.assertNotIn("private beta", markup.lower())
        self.assertIn("Invitation ID", markup)
        self.assertIn("Invitation secret", markup)

    def test_origin_rules_keep_loopback_and_hosted_modes_distinct(self):
        self.assertEqual(subject.runtime_origin("127.0.0.1", 8877),
                         ("http://127.0.0.1:8877", False))
        self.assertEqual(subject.runtime_origin("0.0.0.0", 8877,
                                                "https://beta.example.test"),
                         ("https://beta.example.test", True))
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            subject.runtime_origin("0.0.0.0", 8877, "http://beta.example.test")
        with self.assertRaisesRegex(ValueError, "port"):
            subject.runtime_origin("127.0.0.1", 80)

    def test_unsafe_asset_and_unbounded_browser_persistence_paths_are_absent(self):
        script = (subject.ASSET_ROOT / "app.js").read_text()
        for forbidden in ("localStorage", "indexedDB", "innerHTML", "document.cookie"):
            self.assertNotIn(forbidden, script)
        self.assertIn("window.sessionStorage", script)
        self.assertIn("const HANDOFF_TTL_MS = 10 * 60 * 1000", script)
        self.assertIn("clearAuthHandoff", script)
        self.assertIn("textContent", script)
        self.assertIn("resetConversation", script)
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the JavaScript syntax check")
        checked = subprocess.run([node, "--check", str(subject.ASSET_ROOT / "app.js")],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok")
            (root / "styles.css").write_text("ok")
            (root / "app.js").symlink_to(root / "index.html")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                subject._asset_bytes(root)

    def test_deferred_fetch_browser_regressions(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the browser regression test")
        script = Path(__file__).with_name("test_beta_app.js")
        checked = subprocess.run([node, str(script)], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("3 beta browser regression scenarios passed", checked.stdout)


if __name__ == "__main__":
    unittest.main()
