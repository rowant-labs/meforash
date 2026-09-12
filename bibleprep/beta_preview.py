"""Browser wrapper for the invite-only beta backend candidate.

Static assets are loaded from a fixed allowlist. Authentication, sessions,
source lookup, generation, rate limits, and accounting remain in beta_server.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

from bibleprep import beta_server


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8877
ASSET_ROOT = ROOT / "web" / "beta"
MAX_ASSET_BYTES = 512_000
CANONICAL_ORIGIN = "https://meforash.com"
LEGACY_RAILWAY_HOST = "meforash-production.up.railway.app"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/privacy": ("privacy.html", "text/html; charset=utf-8"),
    "/terms": ("terms.html", "text/html; charset=utf-8"),
    "/brand": ("brand.html", "text/html; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon-v2.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon-v3.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/apple-touch-v4.png": ("apple-touch-icon.png", "image/png"),
    "/beta/logo.svg": ("logo.svg", "image/svg+xml"),
    "/beta/logo-v4.svg": ("logo.svg", "image/svg+xml"),
    "/beta/legal.css": ("legal.css", "text/css; charset=utf-8"),
    "/beta/consent.js": ("consent.js", "text/javascript; charset=utf-8"),
    "/beta/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/beta/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def _asset_bytes(asset_root):
    asset_root = Path(asset_root)
    if asset_root.is_symlink() or not asset_root.is_dir():
        raise ValueError("The fixed beta preview asset directory is unavailable or unsafe.")
    asset_root = asset_root.resolve()
    result = {}
    for route, (name, content_type) in ASSETS.items():
        path = asset_root / name
        if path.is_symlink() or not path.is_file() or path.parent != asset_root:
            raise ValueError("A fixed beta preview asset is unavailable or unsafe.")
        data = path.read_bytes()
        if not data or len(data) > MAX_ASSET_BYTES:
            raise ValueError("A beta preview asset has an invalid size.")
        result[route] = (data, content_type)
    return result


def runtime_origin(host, port, origin=None):
    """Return (origin, secure_cookie) under the backend's single-origin rule."""
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Choose a port between 1024 and 65535.")
    local = host in {"127.0.0.1", "localhost"}
    resolved = origin or (f"http://{host}:{port}" if local else None)
    if not local and (resolved is None or urlsplit(resolved).scheme != "https"):
        raise ValueError("Hosted mode requires an explicit HTTPS origin and TLS proxy.")
    # handler_for performs the remaining exact origin, path, and cookie checks.
    return resolved, not local


def handler_for(app, *, origin, secure_cookie, asset_root=ASSET_ROOT, trust_real_ip=False):
    """Add a fixed static allowlist to the accepted JSON backend handler."""
    assets = _asset_bytes(asset_root)
    backend = beta_server.handler_for(app, origin=origin, secure_cookie=secure_cookie,
                                      trust_real_ip=trust_real_ip)

    class PreviewHandler(backend):
        server_version = "BibleBetaPreviewCandidateV1"

        def _legacy_ui_redirect(self, parsed):
            if (origin != CANONICAL_ORIGIN
                    or self.headers.get("Host") not in {
                        LEGACY_RAILWAY_HOST, f"{LEGACY_RAILWAY_HOST}:443"
                    }
                    or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
                    or parsed.path not in assets):
                return False
            location = CANONICAL_ORIGIN + parsed.path
            self.send_response(308)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            return True

        def _send_asset(self, data, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; font-src 'none'; "
                "object-src 'none'; base-uri 'none'; form-action 'self'; "
                "frame-ancestors 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _send_static_not_found(self):
            data = b"This beta preview resource is unavailable.\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            if self._legacy_ui_redirect(parsed):
                return
            if not parsed.query and not parsed.fragment and parsed.path in assets:
                return self._send_asset(*assets[parsed.path])
            if parsed.path == "/health" or parsed.path.startswith("/api/"):
                return super().do_GET()
            return self._send_static_not_found()

        def do_HEAD(self):
            parsed = urlsplit(self.path)
            if self._legacy_ui_redirect(parsed):
                return
            self.send_error(501, "Unsupported method ('HEAD')")

    return PreviewHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invite-config", required=True)
    parser.add_argument("--database", default="runs/private-beta-v1/beta.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--origin")
    args = parser.parse_args(argv)
    try:
        origin, secure_cookie = runtime_origin(args.host, args.port, args.origin)
        store = beta_server.BetaStore(
            args.database, beta_server.load_invite_config(args.invite_config))
        app = beta_server.BetaApplication(store=store)
        server = beta_server.BetaHTTPServer(
            (args.host, args.port),
            handler_for(app, origin=origin, secure_cookie=secure_cookie),
        )
    except Exception:
        parser.exit(
            1,
            "The beta preview candidate could not start. Check its hash-only "
            "invite config, ledger, runtime, sources, and static assets.\n",
        )
    print(f"Bible beta preview candidate: {origin}", flush=True)
    print(
        "Conversation text is sent to Tinker for answers and is not stored by this backend.",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
