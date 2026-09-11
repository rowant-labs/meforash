"""Run the private Bible chat on loopback. Never exposes the provider key.

Start with ``python -m bibleprep.chat_server``. Conversations are held in the
browser and short-lived process memory only; no request/answer logs are written.
This is a local research application, not a public deployment server.
"""
from __future__ import annotations

import argparse
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from bibleprep.chat_model import ChatModel, ChatModelError, build_payload
from bibleprep.chat_sources import PassageLibrary

ROOT = Path(__file__).resolve().parents[1]
MAX_REQUEST_BYTES = 192000
MAX_RESERVATION = (24000 * 1.87 + 8192 * 4.68) / 1000000


class RequestStartError(RuntimeError):
    """A local worker could not start; no model request was submitted."""


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


class ChatApplication:
    def __init__(self, *, root=ROOT, model=None, library=None, budget=5.0,
                 streaming=False):
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("Set a positive, finite process budget.")
        self.root = Path(root)
        self.model = model if model is not None else ChatModel(
            root=self.root, streaming=streaming)
        self.library = library if library is not None else PassageLibrary(self.root)
        self.budget = budget
        self.accounted = 0.0
        self.jobs = {}
        self.lock = threading.Lock()
        self.running = False
        self.closed = False
        self.cookie = secrets.token_urlsafe(32)

    def status(self):
        metadata = self.model.status()
        return {"configured": metadata.get("configured", False),
                "ready": metadata.get("ready", False),
                "model_label": "Original-language model",
                "model": "Inkling · fine-tuned on biblical Hebrew, Aramaic, and Greek",
                "source_count": self.library.count,
                "source_lookup": "Explicit passage references; English-to-MT whole-verse mappings; SBLGNT NT coordinates",
                "historical_evidence_loaded": False,
                "busy": self.running, "blocked": metadata.get("blocked", False),
                "conversation_storage": "memory_only",
                "provider": "Thinking Machines / Tinker",
                "budget_available": self.accounted + MAX_RESERVATION <= self.budget}

    def submit(self, body):
        if not isinstance(body, dict) or set(body) != {"messages"}:
            raise ChatModelError("invalid_messages")
        messages = body["messages"]
        build_payload(messages)
        with self.lock:
            self._expire()
            if self.closed:
                raise ChatModelError("closed")
            if self.running:
                raise ChatModelError("busy")
            if self.accounted + MAX_RESERVATION > self.budget:
                return None
            self.accounted += MAX_RESERVATION
            self.running = True
            identifier = secrets.token_urlsafe(24)
            self.jobs[identifier] = {
                "status": "running", "revision": 0, "answer": "",
                "complete": False, "created": time.monotonic(),
            }
        worker = threading.Thread(target=self._generate, args=(identifier, messages), daemon=True)
        try:
            worker.start()
        except Exception:
            with self.lock:
                self.accounted -= MAX_RESERVATION
                self.running = False
                self.jobs.pop(identifier, None)
            raise RequestStartError from None
        return identifier

    def _generate(self, identifier, messages):
        actual_cost = None

        def on_progress(answer, revision):
            with self.lock:
                job = self.jobs.get(identifier)
                if (self.closed or job is None or job.get("status") != "running"
                        or type(revision) is not int or revision <= job.get("revision", 0)
                        or not isinstance(answer, str)
                        or not answer.startswith(job.get("answer", ""))):
                    return
                job["answer"] = answer
                job["revision"] = revision

        def snapshot():
            with self.lock:
                job = self.jobs.get(identifier, {})
                return job.get("answer", ""), job.get("revision", 0)

        try:
            sources, notes = self.library.select(messages)
            options = {"evidence_context": self.library.context(sources, notes)}
            if getattr(self.model, "supports_progress", False):
                options["on_progress"] = on_progress
            result = self.model.generate(messages, **options)
            usage = result.get("usage", {})
            value = usage.get("estimated_usd")
            if type(value) in (float, int) and math.isfinite(value) and 0 <= value <= MAX_RESERVATION:
                actual_cost = value
            partial, revision = snapshot()
            final_answer = result["answer"]
            if final_answer != partial:
                revision += 1
            outcome = {"status": "complete", "answer": final_answer, "sources": sources,
                       "source_notes": notes, "complete": result["answer_complete"],
                       "warnings": result.get("warnings", []), "revision": revision}
        except ChatModelError as exc:
            if exc.code in {"invalid_messages", "input_too_long", "not_configured", "checkpoint_unavailable", "runtime_unavailable", "busy", "blocked", "closed"}:
                actual_cost = 0
            outcome = {"status": "error", "error": {"code": exc.code, "message": str(exc)}}
        except Exception:
            # Never serialize provider exceptions, paths, input, or raw tokens.
            outcome = {"status": "error", "error": {"code": "server_error", "message": "The private server could not finish this request. It was not retried."}}
        partial, revision = snapshot()
        if outcome["status"] == "error" and partial:
            outcome.update({"partial_answer": partial, "complete": False,
                            "revision": revision})
        with self.lock:
            if actual_cost is not None:
                self.accounted -= MAX_RESERVATION - actual_cost
            if not self.closed:
                self.jobs[identifier] = {**outcome, "created": time.monotonic()}
            self.running = False

    def _expire(self):
        now = time.monotonic()
        for identifier in list(self.jobs):
            if self.jobs[identifier]["status"] != "running" and now - self.jobs[identifier]["created"] > 900:
                del self.jobs[identifier]
        done = [k for k, v in self.jobs.items() if v["status"] != "running"]
        for identifier in done[:-20]:
            del self.jobs[identifier]

    def result(self, identifier):
        with self.lock:
            self._expire()
            result = self.jobs.get(identifier)
            return {k: v for k, v in result.items() if k != "created"} if result else None

    def close(self):
        with self.lock:
            self.closed = True
            self.jobs.clear()
        self.model.close()


class PreviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # HTTP request contents and provider details must not enter terminal logs.
        pass


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BibleResearchPreview"

        def log_message(self, format, *args):
            pass

        def _valid_host(self):
            port = self.server.server_address[1]
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _authorized(self):
            if not self._valid_host():
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return False
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                return secrets.compare_digest(cookie["bible_preview"].value, app.cookie)
            except (KeyError, ValueError, CookieError):
                return False

        def _send(self, code, data, content_type="application/json; charset=utf-8", cookie=False):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if cookie:
                self.send_header("Set-Cookie", f"bible_preview={app.cookie}; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self._valid_host():
                return self._send(403, {"error": {"message": "Use the local preview address."}})
            path = urlsplit(self.path).path
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8")}
            if path in static:
                name, content_type = static[path]
                return self._send(200, (app.root / "web" / name).read_bytes(), content_type, cookie=path == "/")
            if not self._authorized():
                return self._send(403, {"error": {"message": "Open the local chat page before requesting an answer."}})
            if path == "/api/status":
                return self._send(200, app.status())
            if path.startswith("/api/chat/"):
                result = app.result(path.removeprefix("/api/chat/"))
                if result:
                    return self._send(200, result)
            return self._send(404, {"error": {"message": "This preview resource is unavailable."}})

        def do_POST(self):
            if not self._authorized():
                return self._send(403, {"error": {"message": "This request must come from the local chat page."}})
            if urlsplit(self.path).path != "/api/chat":
                return self._send(404, {"error": {"message": "This preview resource is unavailable."}})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": {"message": "This request must use JSON."}})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST_BYTES or self.headers.get("Transfer-Encoding"):
                    return self._send(413, {"error": {"message": "The conversation is too large. Start a new chat or shorten it."}})
                self.connection.settimeout(15)
                body = strict_json(self.rfile.read(size))
                identifier = app.submit(body)
                if identifier is None:
                    return self._send(429, {"error": {"message": "This preview has reached its session allowance. Restart it with a new allowance to continue."}})
                return self._send(202, {"request_id": identifier})
            except ChatModelError as exc:
                return self._send(409 if exc.code == "busy" else 400, {"error": {"code": exc.code, "message": str(exc)}})
            except RequestStartError:
                return self._send(503, {"error": {"message": "The private server could not start this request. No model call was made."}})
            except (ValueError, TypeError, UnicodeError, TimeoutError):
                return self._send(400, {"error": {"message": "The conversation could not be read. Please reload the page."}})

        def do_OPTIONS(self):
            self._send(403, {"error": {"message": "Cross-site requests are not supported."}})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--budget", type=float, default=5.0, help="Estimated/reserved USD allowance for this process; not an invoice limit.")
    parser.add_argument("--streaming", action="store_true",
                        help="Opt into the separately gated progressive model transport.")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    try:
        app = ChatApplication(budget=args.budget, streaming=args.streaming)
        server = PreviewServer(("127.0.0.1", args.port), handler_for(app))
    except Exception:
        parser.exit(1, "The local preview could not start. Check its source preparation, runtime and port using docs/PRIVATE-CHAT.md.\n")
    print(f"Private Bible chat: http://127.0.0.1:{args.port}", flush=True)
    print("Conversations stay in memory here and are sent to Tinker for answers. No chat logs or training data are saved.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
