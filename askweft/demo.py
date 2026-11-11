"""Record actual engine transitions on the labelled synthetic example."""

from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from .domain import encoded
from .store import Engine

SCOPE = "Recorded synthetic engine states; read-only, no financial actions"


def recording():
    stages = []
    with TemporaryDirectory(prefix="askweft-record-") as temporary:
        engine = Engine(Path(temporary) / "demo.sqlite")
        view = engine.import_case(
            files("askweft").joinpath("examples", "invoice.json").read_bytes(), synthetic=True
        )

        def stage(name, label):
            stages.append({"id": name, "label": label, "state": {**view, "mode": "recorded"}})

        stage("alternatives", "Alternatives")
        session = view["session"]
        view = engine.request(session["id"], session["revision"], "reference")
        stage("reference-request", "Reference request")
        session = view["session"]
        view = engine.answer(
            session["id"], session["revision"], session["pending"]["id"], {"reference": "PAY-42"}
        )
        stage("two-survivors", "Two survivors")
        session = view["session"]
        view = engine.request(session["id"], session["revision"], "duplicate")
        stage("duplicate-request", "Duplicate request")
        session = view["session"]
        view = engine.answer(
            session["id"], session["revision"], session["pending"]["id"], {"duplicate": True}
        )
        stage("resolved", "Resolved in model")
        view = engine.restart(view["session"]["id"])
        session = view["session"]
        view = engine.request(session["id"], session["revision"], "reference")
        session = view["session"]
        view = engine.answer(
            session["id"],
            session["revision"],
            session["pending"]["id"],
            {"reference": "OUTSIDE-MODEL"},
        )
        stage("contradiction", "Contradiction")
    return {"format": 1, "scope": SCOPE, "stages": stages}


def export_recording(path):
    with Path(path).open("xb") as stream:
        stream.write(encoded(recording()) + b"\n")
