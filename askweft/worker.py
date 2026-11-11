"""JSON-line planner worker; receives only input, config and the current requested answer."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .domain import Error, config, encoded, keys, loads, require
from .server import BODY_LIMIT
from .store import Engine


def main():
    temporary = None
    engine = None
    session = None
    try:
        while True:
            raw = sys.stdin.buffer.readline(BODY_LIMIT + 2)
            if not raw:
                break
            try:
                data = loads(raw, limit=BODY_LIMIT)
                require(type(data) is dict, "Expected a worker command object")
                if data.get("op") == "start":
                    keys(data, ("op", "source_json", "config"))
                    # Each run uses a new store; no run can inherit another run's journal.
                    if temporary:
                        temporary.cleanup()
                    temporary = TemporaryDirectory(prefix="askweft-worker-")
                    engine = Engine(Path(temporary.name) / "run.sqlite")
                    session = None
                    keys(data["config"], ("lambda", "question_budget", "field_budget"))
                    session = engine.import_case(data["source_json"], config(data["config"]))["session"]
                else:
                    if data.get("op") == "state" and engine is not None and session is None:
                        keys(data, ("op",))
                        response = {"ok": True, "session": None}
                        sys.stdout.buffer.write(encoded(response) + b"\n")
                        sys.stdout.buffer.flush()
                        continue
                    if engine is None or session is None:
                        raise Error("not_found", "Start a case first")
                    if data.get("op") == "request":
                        keys(data, ("op", "question_id"))
                        session = engine.request(session["id"], session["revision"],
                                                 data["question_id"])["session"]
                    elif data.get("op") == "answer":
                        keys(data, ("op", "values"))
                        if session["pending"] is None:
                            raise Error("request_refused", "No pending request")
                        session = engine.answer(session["id"], session["revision"],
                                                session["pending"]["id"], data["values"])["session"]
                    elif data.get("op") == "state":
                        keys(data, ("op",))
                        session = engine.state(session["id"])["session"]
                    else:
                        raise Error("invalid_input", "Unknown worker operation")
                response = {"ok": True, "session": session}
            except Error as error:
                response = {"ok": False, "error": {"code": error.code, "message": str(error)}}
            sys.stdout.buffer.write(encoded(response) + b"\n")
            sys.stdout.buffer.flush()
    finally:
        if temporary:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
