"""SQLite request/answer transactions; reads and answer replay never charge effort."""

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import uuid

from . import domain, planner
from .domain import Error, encoded, require


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def uid(prefix):
    return prefix + uuid.uuid4().hex


def dump(value):
    return encoded(value).decode("utf-8")


class Engine:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if not tables:
                connection.execute("CREATE TABLE metadata (format INTEGER NOT NULL)")
                connection.execute("INSERT INTO metadata VALUES (1)")
                connection.execute("""CREATE TABLE sessions (
                    id TEXT PRIMARY KEY, raw BLOB NOT NULL, input_sha256 TEXT NOT NULL,
                    config TEXT NOT NULL, created_at TEXT NOT NULL, synthetic INTEGER NOT NULL,
                    revision INTEGER NOT NULL, state TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE requests (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    request TEXT NOT NULL, answer TEXT, receipt TEXT)""")
            else:
                require(tables == {"metadata", "sessions", "requests"},
                        "Database is not an Askweft v1 store", "invalid_store")
                require([tuple(row) for row in connection.execute("SELECT format FROM metadata")]
                        == [(1,)], "Unsupported database format", "invalid_store")

    @contextmanager
    def _connect(self):
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            if connection:
                connection.rollback()
            raise Error("store_unavailable", "Cannot read or commit the local database") from error
        except BaseException:
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                connection.close()

    @staticmethod
    def _row(connection, session_id):
        domain.identifier(session_id)
        row = connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        require(row is not None, "Session does not exist", "not_found")
        return row

    @staticmethod
    def _revision(row, expected):
        require(type(expected) is int and expected >= 0, "Expected a nonnegative integer revision")
        require(row["revision"] == expected, "Session changed; read its state and explicitly retry",
                "stale_revision")

    @staticmethod
    def _session(row):
        state = json.loads(row["state"])
        case = domain.parse_case(bytes(row["raw"]))
        analysis = planner.analyze(case, json.loads(row["config"]), state["known"],
                                   state["unavailable_fields"], state["used"], state["usage"],
                                   state["pending"])
        return {"id": row["id"], "title": case.get("title", case["id"]),
                "revision": row["revision"], "input_sha256": row["input_sha256"],
                "created_at": row["created_at"], "config": json.loads(row["config"]),
                "case": case, "known": state["known"],
                "unavailable_fields": state["unavailable_fields"], "usage": state["usage"],
                "pending": state["pending"], "journal": list(reversed(state["journal"])),
                **analysis}

    def _view(self, connection, session_id=None):
        rows = connection.execute("SELECT * FROM sessions ORDER BY rowid DESC").fetchall()
        selected = self._row(connection, session_id) if session_id else (rows[0] if rows else None)
        sessions = []
        for row in rows:
            session = self._session(row)
            sessions.append({key: session[key] for key in ("id", "title", "status", "created_at")})
        return {"mode": "synthetic-local" if selected and selected["synthetic"] else "local",
                "sessions": sessions, "session": self._session(selected) if selected else None}

    def state(self, session_id=None):
        with self._connect() as connection:
            connection.execute("BEGIN")
            return self._view(connection, session_id)

    def _insert(self, connection, raw, settings, synthetic):
        case = domain.parse_case(raw)
        settings = domain.config(settings)
        raw = raw.encode("utf-8") if type(raw) is str else raw
        session_id = uid("s_")
        state = {"known": case["confirmed"], "unavailable_fields": [], "used": [],
                 "usage": {"questions": 0, "fields": 0, "field_names": [], "cost": 0},
                 "pending": None, "journal": []}
        connection.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                           (session_id, raw, sha256(raw).hexdigest(), dump(settings), now(),
                            int(synthetic), 0, dump(state)))
        return session_id

    def import_case(self, raw, config=None, *, synthetic=False):
        # Parse before opening the write transaction: malformed imports leave the store unchanged.
        domain.parse_case(raw)
        domain.config(config)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session_id = self._insert(connection, raw, config, synthetic)
            return self._view(connection, session_id)

    def restart(self, session_id, config=None):
        domain.config(config)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, session_id)
            new_id = self._insert(connection, bytes(row["raw"]), config, bool(row["synthetic"]))
            return self._view(connection, new_id)

    @staticmethod
    def _save(connection, row, state):
        result = connection.execute("UPDATE sessions SET revision=?,state=? WHERE id=? AND revision=?",
                                    (row["revision"] + 1, dump(state), row["id"], row["revision"]))
        require(result.rowcount == 1, "Session changed; read state and retry", "stale_revision")

    def request(self, session_id, expected_revision, question_id):
        domain.identifier(question_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, session_id)
            self._revision(row, expected_revision)
            session = self._session(row)
            require(session["status"] == "active", "Session has no available request", "request_refused")
            option = next((item for item in session["options"] if item["id"] == question_id), None)
            require(option is not None, "Question is not currently feasible", "request_refused")
            state = json.loads(row["state"])
            request_id = uid("r_")
            pending = {**option, "id": request_id, "question_id": question_id,
                       "revision": row["revision"] + 1, "basis_revision": row["revision"],
                       "survivors": session["survivors"]}
            connection.execute("INSERT INTO requests VALUES (?,?,?,NULL,NULL)",
                               (request_id, session_id, dump(pending)))
            state["pending"] = pending
            state["used"].append(question_id)
            state["usage"]["questions"] += 1
            state["usage"]["cost"] += option["cost"]
            state["usage"]["field_names"] = [field for field in domain.FIELDS
                if field in set(state["usage"]["field_names"]) | set(option["fields"])]
            state["usage"]["fields"] = len(state["usage"]["field_names"])
            state["journal"].append({"sequence": len(state["journal"]) + 1, "kind": "request",
                "at": now(), "request_id": request_id, "question_id": question_id,
                "fields": option["fields"], "values": None, "remaining": session["survivors"],
                "cost": option["cost"], "receipt_id": None})
            self._save(connection, row, state)
            return self._view(connection, session_id)

    def answer(self, session_id, expected_revision, request_id, values):
        domain.identifier(request_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, session_id)
            request_row = connection.execute("SELECT * FROM requests WHERE id=? AND session_id=?",
                                              (request_id, session_id)).fetchone()
            require(request_row is not None, "Request does not exist in this session", "not_found")
            request = json.loads(request_row["request"])
            answer = domain.values(values, request["fields"])
            if request_row["answer"] is not None:
                require(answer == json.loads(request_row["answer"]),
                        "This request already has a different answer; start a new session",
                        "answer_conflict")
                return {**self._view(connection, session_id),
                        "receipt": json.loads(request_row["receipt"]), "replayed": True}
            self._revision(row, expected_revision)
            state = json.loads(row["state"])
            require(state["pending"] and state["pending"]["id"] == request_id,
                    "Request is not pending", "request_refused")
            for field, value in answer.items():
                if value is None:
                    state["unavailable_fields"].append(field)
                else:
                    state["known"][field] = value
            state["pending"] = None
            case = domain.parse_case(bytes(row["raw"]))
            analysis = planner.analyze(case, json.loads(row["config"]), state["known"],
                                       state["unavailable_fields"], state["used"], state["usage"])
            receipt = {"id": uid("a_"), "request_id": request_id, "values": answer,
                       "revision": row["revision"] + 1, "at": now(),
                       "survivors": analysis["survivors"], "status": analysis["status"]}
            connection.execute("UPDATE requests SET answer=?,receipt=? WHERE id=? AND answer IS NULL",
                               (dump(answer), dump(receipt), request_id))
            state["journal"].append({"sequence": len(state["journal"]) + 1, "kind": "answer",
                "at": receipt["at"], "request_id": request_id,
                "question_id": request["question_id"], "fields": request["fields"],
                "values": answer, "remaining": analysis["survivors"], "cost": 0,
                "receipt_id": receipt["id"]})
            self._save(connection, row, state)
            return {**self._view(connection, session_id), "receipt": receipt, "replayed": False}

    def original(self, session_id):
        with self._connect() as connection:
            return bytes(self._row(connection, session_id)["raw"])
