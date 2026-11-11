"""Numeric-loopback HTTP transport over the same transactional engine as the CLI."""

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import secrets
from urllib.parse import parse_qs, urlsplit

from .domain import MAX_INPUT, Error, config, encoded, keys, loads, require

ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "mark.svg": "image/svg+xml",
    "icon.svg": "image/svg+xml",
    "recorded.json": "application/json; charset=utf-8",
}
BODY_LIMIT = MAX_INPUT * 6 + 4096  # JSON escaping can expand the raw case string.


def make_server(engine, *, port=0):
    require(type(port) is int and 0 <= port <= 65535, "Port must be an integer in 0..65535")
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *_):
            pass

        def _reply(self, status, body, mime="application/json; charset=utf-8"):
            raw = body if isinstance(body, bytes) else encoded(body)
            self.send_response(status)
            for key, value in (
                ("Content-Type", mime),
                ("Content-Length", str(len(raw))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
                ("Connection", "close"),
                (
                    "Content-Security-Policy",
                    "default-src 'self'; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                ),
            ):
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def _host(self):
            host = "127.0.0.1:" + str(self.server.server_port)
            require(
                self.headers.get_all("Host") == [host],
                "Use the printed numeric loopback address",
                "host_refused",
            )
            location = urlsplit(self.path)
            require(
                not location.scheme and not location.netloc and not location.fragment,
                "Only local relative paths are supported",
            )
            return "http://" + host, location

        def _error(self, error):
            status = {
                "invalid_input": 400,
                "too_large": 413,
                "not_found": 404,
                "origin_refused": 403,
                "host_refused": 403,
                "store_unavailable": 503,
                "invalid_store": 503,
            }.get(error.code, 409)
            self._reply(status, {"error": {"code": error.code, "message": str(error)}})

        def do_GET(self):
            try:
                _, location = self._host()
                if location.path == "/api/state":
                    try:
                        query = parse_qs(
                            location.query,
                            keep_blank_values=True,
                            strict_parsing=True,
                            max_num_fields=1,
                        )
                    except ValueError as error:
                        raise Error(
                            "invalid_input", "Only one session query parameter is supported"
                        ) from error
                    require(not query or set(query) == {"session"}, "Unknown query parameter")
                    selected = query["session"][0] if query else None
                    self._reply(200, engine.state(selected))
                else:
                    require(not location.query, "Query parameters are not supported on this route")
                    if location.path == "/api/session":
                        self._reply(200, {"token": token})
                    else:
                        name = "index.html" if location.path == "/" else location.path[1:]
                        require(name in ASSETS, "Unknown resource", "not_found")
                        asset = files("askweft").joinpath("assets", name)
                        require(asset.is_file(), "Resource is unavailable", "not_found")
                        self._reply(200, asset.read_bytes(), ASSETS[name])
            except Error as error:
                self._error(error)
            except OSError:
                self._reply(
                    503, {"error": {"code": "unavailable", "message": "Local resource unavailable"}}
                )

        def do_POST(self):
            try:
                origin, location = self._host()
                require(not location.query, "Mutation queries are not supported")
                require(
                    self.headers.get_all("Origin") in (None, [origin]),
                    "Origin is outside this server",
                    "origin_refused",
                )
                supplied = self.headers.get_all("X-Askweft-Token")
                require(
                    supplied is not None
                    and len(supplied) == 1
                    and supplied[0].isascii()
                    and hmac.compare_digest(supplied[0], token),
                    "Session token required; refresh and explicitly retry",
                    "token_refused",
                )
                lengths = self.headers.get_all("Content-Length")
                require(
                    not self.headers.get_all("Transfer-Encoding")
                    and lengths
                    and len(lengths) == 1
                    and lengths[0].isascii()
                    and lengths[0].isdigit()
                    and len(lengths[0]) <= 8,
                    "One bounded Content-Length is required; Transfer-Encoding is refused",
                )
                size = int(lengths[0])
                require(size <= BODY_LIMIT, "Request body exceeds the size limit", "too_large")
                require(
                    self.headers.get_content_type() == "application/json",
                    "Content-Type must be application/json",
                )
                self.connection.settimeout(3)
                raw = self.rfile.read(size)
                require(len(raw) == size, "Incomplete JSON body")
                data = loads(raw, limit=BODY_LIMIT)
                route = location.path
                if route == "/api/import":
                    keys(data, ("source_json", "config"))
                    require(type(data["source_json"]) is str, "source_json must be raw JSON text")
                    keys(data["config"], ("lambda", "question_budget", "field_budget"))
                    result = engine.import_case(data["source_json"], config(data["config"]))
                elif route == "/api/request":
                    keys(data, ("session_id", "expected_revision", "question_id"))
                    result = engine.request(
                        data["session_id"], data["expected_revision"], data["question_id"]
                    )
                elif route == "/api/answer":
                    keys(data, ("session_id", "expected_revision", "request_id", "values"))
                    result = engine.answer(
                        data["session_id"],
                        data["expected_revision"],
                        data["request_id"],
                        data["values"],
                    )
                elif route == "/api/restart":
                    keys(data, ("session_id", "config"))
                    keys(data["config"], ("lambda", "question_budget", "field_budget"))
                    result = engine.restart(data["session_id"], config(data["config"]))
                else:
                    raise Error("not_found", "Unknown mutation")
                self._reply(200, result)
            except Error as error:
                self._error(error)
            except (OSError, ValueError):
                self._reply(
                    400,
                    {"error": {"code": "invalid_input", "message": "Request could not be read"}},
                )

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(engine, *, port=8746, stop_event=None):
    server = make_server(engine, port=port)
    server.timeout = 0.2
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        while stop_event is None or not stop_event.is_set():
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
