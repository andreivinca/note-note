"""A local HTTP server for the provider transport suites.

What only a real socket shows — a redirect followed or refused, a body
dripped a byte at a time — is tested against a server on 127.0.0.1, never
the network. services/microsoft/selftest.py and
plugins/org.note-note.notion/selftest.py share it.
"""
import http.server
import threading
import time


class LocalServer:
    """Serves `answer(handler)` for every request, and keeps each request
    that arrives in `seen` as (method, path, Authorization, body)."""

    def __init__(self, answer):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def respond(self):
                length = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, self.headers.get("Authorization"),
                             self.rfile.read(length)))
                try:
                    answer(self)
                except (BrokenPipeError, ConnectionResetError):
                    pass    # the client stopped listening, which is the point

            do_GET = do_POST = do_PATCH = do_DELETE = respond

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False


def answer_with(status, body=b"{}", **fields):
    """A whole response at once; `fields` are headers, `_` for `-`."""
    def answer(handler):
        handler.send_response(status)
        for name, value in fields.items():
            handler.send_header(name.replace("_", "-"), value)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    return answer


def drip(status, length=60, gap=0.05):
    """A response whose body — a JSON string `length` bytes long — arrives
    one byte every `gap` seconds: never a socket timeout, and `length * gap`
    seconds in all."""
    body = b'"' + b"x" * (length - 2) + b'"'

    def answer(handler):
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(length))
        handler.end_headers()
        for i in range(length):
            handler.wfile.write(body[i:i + 1])
            handler.wfile.flush()
            time.sleep(gap)
    return answer
