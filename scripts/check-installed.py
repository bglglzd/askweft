"""Exercise installed package bytes outside the source tree, without runtime downloads."""

from importlib.resources import files
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import askweft
from askweft.demo import recording
from askweft.domain import encoded

ROOT = Path(__file__).resolve().parents[1]
assert not Path(askweft.__file__).resolve().is_relative_to(ROOT / "askweft"), (
    "Source tree shadows installed wheel"
)
assert files("askweft").joinpath("assets", "app.js").is_file()

with TemporaryDirectory(prefix="askweft-installed-") as temporary:
    scratch = Path(temporary)
    raw = files("askweft").joinpath("examples", "invoice.json").read_bytes()
    case = json.loads(raw)
    case["id"] = "fresh-installed-import"
    case["bank_events"][0]["reference"] = "INSTALLED-FILE-713"
    source = scratch / "fresh.json"
    source.write_bytes(encoded(case))
    command = [sys.executable, "-I", "-m", "askweft", "--db", str(scratch / "session.sqlite")]

    def run(*args):
        result = subprocess.run(
            command + list(args), cwd=scratch, capture_output=True, check=True, timeout=20
        )
        return json.loads(result.stdout)

    session = run("import", str(source))["session"]
    pending = run(
        "request", "--session", session["id"], "--revision", "0", "--question", "reference"
    )["session"]
    answer = scratch / "answer.json"
    answer.write_bytes(encoded({"reference": "INSTALLED-FILE-713"}))
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
    assert resolved["status"] == "resolved_within_model" and resolved["survivors"] == ["single-a"]
    assert run("export", "--session", session["id"])["session"] == resolved
    print(
        json.dumps(
            {
                "installed_module": askweft.__file__,
                "source_shadowed": False,
                "fresh_file_reopened": True,
                "status": resolved["status"],
            }
        )
    )
stages = recording()["stages"]
assert len(stages) == 6 and stages[-1]["state"]["session"]["reason"] == "inconsistent_observations"
