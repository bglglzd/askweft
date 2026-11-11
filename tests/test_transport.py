import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest

from askweft.domain import encoded
from askweft.server import make_server
from askweft.store import Engine

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / "askweft/examples/invoice.json").read_bytes()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="askweft-http-test-")
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine(Path(self.temp.name) / "http.sqlite")
        self.server = make_server(self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        status, data = self.call("GET", "/api/session")
        self.assertEqual(status, 200)
        self.token = data["token"]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def call(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            body = None if data is None else encoded(data)
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            result = json.loads(response.read())
            return response.status, result
        finally:
            connection.close()

    def post(self, path, data, extra=None):
        return self.call(
            "POST",
            path,
            data,
            {
                "Content-Type": "application/json",
                "Origin": self.origin,
                "X-Askweft-Token": self.token,
                **(extra or {}),
            },
        )

    def start(self):
        status, view = self.post(
            "/api/import",
            {
                "source_json": RAW.decode(),
                "config": {"lambda": 1, "question_budget": 4, "field_budget": 4},
            },
        )
        self.assertEqual(status, 200)
        return view["session"]

    def test_explicit_empty_session_is_refused(self):
        session = self.start()
        status, data = self.call("GET", "/api/state?session=")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "invalid_input")
        self.assertEqual(self.engine.state()["session"], session)

    def test_real_http_transition_and_replay(self):
        session = self.start()
        status, view = self.post(
            "/api/request",
            {"session_id": session["id"], "expected_revision": 0, "question_id": "reference"},
        )
        self.assertEqual(status, 200)
        request = view["session"]["pending"]
        payload = {
            "session_id": session["id"],
            "expected_revision": 1,
            "request_id": request["id"],
            "values": {"reference": "PAY-41"},
        }
        status, view = self.post("/api/answer", payload)
        self.assertEqual((status, view["session"]["survivors"]), (200, ["single-a"]))
        payload["expected_revision"] = 0
        status, replay = self.post("/api/answer", payload)
        self.assertEqual(status, 200)
        self.assertEqual(replay["receipt"], view["receipt"])
        self.assertEqual(replay["session"], view["session"])

    def test_origin_token_host_and_closed_payload_refusals(self):
        session = self.start()
        payload = {"session_id": session["id"], "expected_revision": 0, "question_id": "reference"}
        for headers, expected in (
            ({"Origin": "https://example.invalid"}, 403),
            ({"X-Askweft-Token": "refused"}, 409),
            ({"Host": "attacker.invalid"}, 403),
        ):
            with self.subTest(headers=headers):
                status, _ = self.post("/api/request", payload, headers)
                self.assertEqual(status, expected)
                self.assertEqual(self.engine.state()["session"], session)
        status, _ = self.post("/api/request", {**payload, "unexpected": True})
        self.assertEqual(status, 400)
        for path in ("/api/state?other=x", "/api/state?session=x&session=y", "/api/session?x=1"):
            self.assertEqual(self.call("GET", path)[0], 400)

    def test_raw_duplicate_keys_and_null_config_refused(self):
        self.start()
        before = self.engine.state()
        for raw in ('{"format":1,"format":1}', "{"):
            status, _ = self.post(
                "/api/import",
                {
                    "source_json": raw,
                    "config": {"lambda": 1, "question_budget": 4, "field_budget": 4},
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(self.engine.state(), before)
        status, _ = self.post("/api/import", {"source_json": RAW.decode(), "config": None})
        self.assertEqual(status, 400)


class ProcessTests(unittest.TestCase):
    def test_worker_refusal_clears_previous_run(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        commands = [
            {
                "op": "start",
                "source_json": RAW.decode(),
                "config": {"lambda": 1, "question_budget": 4, "field_budget": 4},
            },
            {
                "op": "start",
                "source_json": "{",
                "config": {"lambda": 1, "question_budget": 4, "field_budget": 4},
            },
            {"op": "state"},
        ]
        process = subprocess.run(
            [sys.executable, "-m", "askweft.worker"],
            input=b"".join(encoded(command) + b"\n" for command in commands),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._temporary_cwd(),
            env=env,
            timeout=20,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        outputs = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertTrue(outputs[0]["ok"])
        self.assertFalse(outputs[1]["ok"])
        self.assertEqual(outputs[2], {"ok": True, "session": None})

    def _temporary_cwd(self):
        temp = TemporaryDirectory(prefix="askweft-process-test-")
        self.addCleanup(temp.cleanup)
        return temp.name

    def test_cli_separate_process_reopens_actual_file(self):
        scratch = Path(self._temporary_cwd())
        source = scratch / "fresh.json"
        case = json.loads(RAW)
        case["id"] = "fresh-arbitrary-2026"
        case["bank_events"][0]["reference"] = "EXTERNAL-IMPORT"
        source.write_bytes(encoded(case))
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        command = [sys.executable, "-m", "askweft", "--db", str(scratch / "actual.sqlite")]

        def run(*args):
            result = subprocess.run(
                command + list(args), cwd=scratch, env=env, capture_output=True, timeout=20
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return json.loads(result.stdout)

        session = run("import", str(source))["session"]
        pending = run(
            "request", "--session", session["id"], "--revision", "0", "--question", "reference"
        )["session"]
        answer = scratch / "answer.json"
        answer.write_bytes(encoded({"reference": "EXTERNAL-IMPORT"}))
        resolved = run(
            "answer",
            "--session",
            session["id"],
            "--revision",
            "1",
            "--request",
            pending["pending"]["id"],
            "--answer-file",
            str(answer),
        )["session"]
        self.assertEqual(resolved["survivors"], ["single-a"])
        reopened = run("export", "--session", session["id"])["session"]
        self.assertEqual(reopened, resolved)
        self.assertEqual(reopened["case"]["id"], "fresh-arbitrary-2026")


if __name__ == "__main__":
    unittest.main()
