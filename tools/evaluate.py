"""Replay published synthetic Askweft cases; all public reruns are regression evaluations."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import queue
import random
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks/corpus-v1"
CONTRACT = ROOT / "docs/preregistration-v1.md"
CONTRACT_SHA256 = "9c87088f714dad60c549b49172f87aa46882185f6e921d4c2f99f5ddb831eae5"
MANIFEST_SHA256 = "532551b3876bf13217f41793476bca395062f6ca55b623d928128ac0dd07e366"
MENU = ("reference", "date", "party", "duplicate", "reference_date", "packet")
CONFIG = {
    "version": 1,
    "policies": ["adaptive", "fixed", "random"],
    "lambdas": [0, 1, 4],
    "random_seeds": list(range(20)),
    "menu_order": list(MENU),
    "seed": "first 8 SHA256 bytes big-endian of UTF-8 split:case_id:decimal_seed",
    "median": "ordinary midpoint",
    "p90": "nearest rank ceil(0.9*n), one-based",
    "empty_conditional": None,
    "sensitivity": "override lambda only",
}


class EvaluationError(Exception):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def encoded(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(condition, message):
    if not condition:
        raise EvaluationError(message)


def save_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def git(root, *arguments):
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=20,
    )
    return result.stdout.strip()


def source_record(root, clean=False):
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    checked(not clean or not status, "Freeze requires a clean complete source checkout")
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    files = []
    for name in sorted(set(names)):
        path = (root / name).resolve()
        checked(path.is_relative_to(root) and path.is_file(), "Invalid source manifest path")
        files.append({"path": name, "sha256": digest(path), "bytes": path.stat().st_size})
    try:
        commit = git(root, "rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        commit = None
    return {"root": str(root), "commit": commit, "clean": not status, "files": files}


def toolchain(python):
    program = (
        "import json,platform,sys;print(json.dumps({"
        "'version':sys.version,'implementation':platform.python_implementation(),"
        "'platform':platform.platform(),'machine':platform.machine(),"
        "'processor':platform.processor()}))"
    )
    result = subprocess.run(
        [str(python), "-c", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=20,
    )
    return {"executable": str(Path(python).resolve()), **json.loads(result.stdout)}


def file_record(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def sealed_metadata():
    checked(
        digest(CONTRACT) == CONTRACT_SHA256,
        "Preregistered domain contract bytes changed",
    )
    checked(
        digest(CORPUS / "manifest.json") == MANIFEST_SHA256,
        "Original corpus manifest seal changed",
    )
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    checked(manifest["contract_sha256"] == CONTRACT_SHA256, "Corpus contract seal mismatch")
    return manifest


def prepare_freeze(args):
    checked(
        args.artifact,
        "At least one tested artifact must be bound before held-out execution",
    )
    sealed_metadata()
    source = source_record(args.product_root, clean=True)
    checked(
        source["commit"] and len(source["commit"]) == 40,
        "A full source commit is required",
    )
    record = {
        "schema_version": 1,
        "created_at": utc(),
        "purpose": "published regression replay",
        "source": source,
        "contract": file_record(CONTRACT),
        "evaluator": file_record(__file__),
        "corpus_manifest": file_record(CORPUS / "manifest.json"),
        "evaluation_config": CONFIG,
        "evaluation_config_sha256": hashlib.sha256(encoded(CONFIG)).hexdigest(),
        "toolchain": toolchain(args.python),
        "artifacts": [file_record(path) for path in args.artifact],
        "heldout_content_opened": False,
    }
    save_new(args.prepare_freeze, record)
    print(
        json.dumps(
            {
                "freeze_record": str(args.prepare_freeze),
                "sha256": digest(args.prepare_freeze),
                "heldout_content_opened": False,
            }
        )
    )


def verify_freeze(path, root, python):
    sealed_metadata()
    record = json.loads(path.read_text(encoding="utf-8"))
    checked(record.get("schema_version") == 1, "Unsupported freeze record")
    checked(
        record.get("evaluation_config") == CONFIG
        and record.get("evaluation_config_sha256") == hashlib.sha256(encoded(CONFIG)).hexdigest(),
        "Evaluation configuration changed after freeze",
    )
    for key, expected in (
        ("contract", CONTRACT),
        ("evaluator", Path(__file__)),
        ("corpus_manifest", CORPUS / "manifest.json"),
    ):
        checked(record[key] == file_record(expected), f"Frozen {key} bytes changed")
    checked(record.get("artifacts"), "Freeze record lacks tested artifact binding")
    for artifact in record["artifacts"]:
        checked(artifact == file_record(artifact["path"]), "Frozen artifact bytes changed")
    checked(
        record.get("toolchain") == toolchain(python),
        "Worker toolchain changed after freeze",
    )
    checked(
        record.get("source") == source_record(root, clean=True),
        "Source changed after freeze",
    )
    return record


def corpus_cases(split):
    manifest = sealed_metadata()
    # D/S authoring never opens H. A guarded H execution verifies every sealed byte first.
    records = (
        manifest["files"] if split == "H" else [r for r in manifest["files"] if r["split"] == split]
    )
    for record in records:
        path = (CORPUS / record["path"]).resolve()
        checked(path.is_relative_to(CORPUS.resolve()), "Corpus path escapes its root")
        checked(
            path.stat().st_size == record["bytes"] and digest(path) == record["sha256"],
            f"Sealed corpus bytes changed: {record['path']}",
        )
    selected = [r for r in manifest["files"] if r["split"] == split]
    cases = []
    for case_id in sorted({r["case_id"] for r in selected}):
        paths = {r["kind"]: CORPUS / r["path"] for r in selected if r["case_id"] == case_id}
        checked(set(paths) == {"input", "oracle", "settings"}, "Incomplete sealed case")
        raw = paths["input"].read_bytes()
        # Decoding preserves all bytes of the sealed UTF-8 cases, including invalid JSON syntax.
        source = raw.decode("utf-8")
        checked(source.encode("utf-8") == raw, "Input UTF-8 round trip changed sealed bytes")
        cases.append(
            {
                "id": case_id,
                "source_json": source,
                "input_sha256": digest(paths["input"]),
                "oracle": json.loads(paths["oracle"].read_text(encoding="utf-8")),
                "settings": json.loads(paths["settings"].read_text(encoding="utf-8")),
            }
        )
    return cases, len(records)


class Worker:
    def __init__(self, python, root, transcript, timeout=30, command=None):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(root)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        self.process = subprocess.Popen(
            command or [str(python), "-m", "askweft.worker"],
            cwd=root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.lines = queue.Queue()
        self.stderr = []
        self.timeout, self.transcript = timeout, transcript

        def read_stdout():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)

        def read_stderr():
            for line in self.process.stderr:
                if sum(map(len, self.stderr)) < 65536:
                    self.stderr.append(line)

        self.reader = threading.Thread(target=read_stdout, daemon=True)
        self.errors = threading.Thread(target=read_stderr, daemon=True)
        self.reader.start()
        self.errors.start()

    def call(self, payload):
        self.transcript.write(
            json.dumps(
                {"at": utc(), "direction": "to_worker", "payload": payload},
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        self.transcript.flush()
        try:
            self.process.stdin.write(encoded(payload).decode("utf-8") + "\n")
            self.process.stdin.flush()
            line = self.lines.get(timeout=self.timeout)
        except (OSError, queue.Empty) as error:
            raise EvaluationError("Worker exited or exceeded response timeout") from error
        checked(line is not None, "Worker exited before a protocol response")
        try:
            response = json.loads(line)
        except (ValueError, TypeError) as error:
            raise EvaluationError("Worker returned invalid JSON protocol") from error
        checked(
            type(response) is dict and type(response.get("ok")) is bool,
            "Worker response lacks an explicit boolean ok",
        )
        self.transcript.write(
            json.dumps(
                {"at": utc(), "direction": "from_worker", "payload": response},
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        self.transcript.flush()
        return response

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        self.errors.join(timeout=1)
        return {"exit_code": self.process.returncode, "stderr": "".join(self.stderr)}


def seed_value(split, case_id, seed):
    text = f"{split}:{case_id}:{seed}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "big")


def choose_question(session, policy, rng):
    options = session["options"]
    checked(
        options and len({q["id"] for q in options}) == len(options),
        "Invalid feasible menu",
    )
    checked(all(q["id"] in MENU for q in options), "Worker returned an unknown menu ID")
    ordered = sorted(options, key=lambda question: MENU.index(question["id"]))
    if policy == "adaptive":
        chosen = session["suggestion"]
        checked(
            chosen and any(q == chosen for q in options),
            "Suggestion is not a feasible option",
        )
        return chosen
    return ordered[0] if policy == "fixed" else rng.choice(ordered)


def terminal_matches(status, reason, expected):
    return any(
        status == item["status"] and ("reason" not in item or reason == item["reason"])
        for item in expected
    )


def run_case(worker, case, split, policy, lam, seed, setting):
    settings = {key: setting[key] for key in ("lambda", "question_budget", "field_budget")}
    settings["lambda"] = lam
    row = {
        "split": split,
        "case_id": case["id"],
        "subrun_id": setting.get("id", "default"),
        "input_sha256": case["input_sha256"],
        "policy": policy,
        "config": settings,
        "seed": seed,
        "seed_value": seed_value(split, case["id"], seed) if seed is not None else None,
        "questions": 0,
        "unique_fields": 0,
        "field_request_events": 0,
        "cost": 0,
        "trace": [],
        "error": None,
        "import_refusal_no_mutation": None,
    }
    started = time.perf_counter()
    rng = random.Random(row["seed_value"])
    try:
        response = worker.call(
            {"op": "start", "source_json": case["source_json"], "config": settings}
        )
        if not response["ok"]:
            row.update(
                status="import_error",
                reason=response.get("error", {}).get("code"),
                error=response.get("error"),
                survivors=[],
            )
            state = worker.call({"op": "state"})
            row["import_refusal_no_mutation"] = (
                state.get("ok") is True and state.get("session") is None
            )
        else:
            session = response["session"]
            observed_fields = set()
            for _ in range(5):
                if session["status"] != "active":
                    break
                question = choose_question(session, policy, rng)
                response = worker.call({"op": "request", "question_id": question["id"]})
                checked(response["ok"], "Worker refused a feasible request")
                session = response["session"]
                pending = session["pending"]
                checked(
                    session["status"] == "awaiting_answer" and pending,
                    "Request did not create a pending answer",
                )
                checked(
                    pending["question_id"] == question["id"]
                    and pending["fields"] == question["fields"],
                    "Request changed selected fields",
                )
                fields = pending["fields"]
                checked(
                    not observed_fields.intersection(fields),
                    "Worker requested a field more than once",
                )
                observed_fields.update(fields)
                row["questions"] += 1
                row["unique_fields"] = len(observed_fields)
                row["field_request_events"] += len(fields)
                row["cost"] += pending["cost"]
                # Only currently requested keys cross into the planner worker.
                answer = {field: case["oracle"]["answers"][field] for field in fields}
                step = {
                    "question_id": question["id"],
                    "fields": fields,
                    "cost": pending["cost"],
                    "answer": answer,
                    "answer_committed": False,
                }
                row["trace"].append(step)
                response = worker.call({"op": "answer", "values": answer})
                checked(response["ok"], "Worker refused its typed oracle answer")
                session = response["session"]
                step.update(
                    answer_committed=True,
                    survivors=session["survivors"],
                    status=session["status"],
                    reason=session["reason"],
                )
            checked(
                session["status"] in ("resolved_within_model", "unresolved"),
                "Worker did not terminate within the four-field budget",
            )
            row.update(
                status=session["status"],
                reason=session["reason"],
                survivors=session["survivors"],
                questions=session["usage"]["questions"],
                unique_fields=session["usage"]["fields"],
                field_request_events=sum(len(step["fields"]) for step in row["trace"]),
                cost=session["usage"]["cost"],
            )
            checked(
                row["questions"] == len(row["trace"])
                and row["unique_fields"] == len(observed_fields)
                and row["cost"] == sum(step["cost"] for step in row["trace"]),
                "Worker effort totals disagree with actual requests",
            )
    except (EvaluationError, KeyError, TypeError, ValueError) as error:
        row.update(
            status="execution_error",
            reason="worker_protocol",
            survivors=[],
            error={"code": type(error).__name__, "message": str(error)},
        )
    row["wall_seconds"] = time.perf_counter() - started
    gold = case["oracle"]["gold_alternative_id"]
    row["gold_alternative_id"] = gold
    row["correct_resolution"] = row["status"] == "resolved_within_model" and row["survivors"] == [
        gold
    ]
    row["wrong_resolution"] = (
        row["status"] == "resolved_within_model" and not row["correct_resolution"]
    )
    expected = (
        [setting["expected_terminal"]]
        if "expected_terminal" in setting
        else case["oracle"]["expectations"]["allowed_terminal_states"]
    )
    row["expectation_pass"] = terminal_matches(row["status"], row["reason"], expected)
    if case["oracle"]["expectations"].get("wrong_resolution_count") == 0:
        row["expectation_pass"] &= not row["wrong_resolution"]
    if row["status"] == "import_error":
        row["expectation_pass"] &= row["import_refusal_no_mutation"] is True
    return row


def distribution(numbers):
    numbers = sorted(numbers)
    if not numbers:
        return {"denominator": 0, "median": None, "p90": None}
    return {
        "denominator": len(numbers),
        "median": statistics.median(numbers),
        "p90": numbers[math.ceil(0.9 * len(numbers)) - 1],
    }


def summarize(rows):
    n = len(rows)
    correct = [row for row in rows if row["correct_resolution"]]
    counts = Counter(row["status"] for row in rows)
    measures = (
        "questions",
        "unique_fields",
        "field_request_events",
        "cost",
        "wall_seconds",
    )
    return {
        "run_denominator": n,
        "independent_case_count": len({row["case_id"] for row in rows}),
        "case_subrun_count": len({(row["case_id"], row["subrun_id"]) for row in rows}),
        "status_counts": dict(counts),
        "correct_resolutions": len(correct),
        "correct_resolution_rate": len(correct) / n if n else None,
        "resolved": counts["resolved_within_model"],
        "unresolved": counts["unresolved"],
        "unresolved_rate": counts["unresolved"] / n if n else None,
        "wrong_resolutions": sum(row["wrong_resolution"] for row in rows),
        "wrong_resolution_rate": sum(row["wrong_resolution"] for row in rows) / n if n else None,
        "expectation_failures": sum(not row["expectation_pass"] for row in rows),
        "all_case_effort": {key: distribution([row[key] for row in rows]) for key in measures},
        "conditional_on_correct_resolution": {
            key: distribution([row[key] for row in correct]) for key in measures
        },
        "effort_totals": {key: sum(row[key] for row in rows) for key in measures},
    }


def grouped_summaries(rows):
    result = []
    for lam in CONFIG["lambdas"]:
        for policy in CONFIG["policies"]:
            selected = [
                row for row in rows if row["config"]["lambda"] == lam and row["policy"] == policy
            ]
            entry = {"lambda": lam, "policy": policy, **summarize(selected)}
            budgets = sorted(
                {(r["config"]["question_budget"], r["config"]["field_budget"]) for r in selected}
            )
            entry["by_budget"] = [
                {
                    "question_budget": questions,
                    "field_budget": fields,
                    **summarize(
                        [
                            r
                            for r in selected
                            if r["config"]["question_budget"] == questions
                            and r["config"]["field_budget"] == fields
                        ]
                    ),
                }
                for questions, fields in budgets
            ]
            if policy == "random":
                entry["pooled_rows_are_repeated_runs"] = True
                entry["per_seed"] = [
                    {
                        "seed": seed,
                        **summarize([r for r in selected if r["seed"] == seed]),
                    }
                    for seed in CONFIG["random_seeds"]
                ]
                entry["seed_variation"] = {
                    key: {
                        "min": min(seed[key] for seed in entry["per_seed"]),
                        "max": max(seed[key] for seed in entry["per_seed"]),
                        "mean": statistics.mean(seed[key] for seed in entry["per_seed"]),
                    }
                    for key in (
                        "correct_resolutions",
                        "unresolved",
                        "wrong_resolutions",
                    )
                }
                for label, group, measure in (
                    ("median_all_questions", "all_case_effort", "questions"),
                    (
                        "median_correct_questions",
                        "conditional_on_correct_resolution",
                        "questions",
                    ),
                    ("median_all_declared_cost", "all_case_effort", "cost"),
                ):
                    values = [
                        seed[group][measure]["median"]
                        for seed in entry["per_seed"]
                        if seed[group][measure]["median"] is not None
                    ]
                    entry["seed_variation"][label] = {
                        "non_null_seed_count": len(values),
                        "min": min(values) if values else None,
                        "max": max(values) if values else None,
                        "mean": statistics.mean(values) if values else None,
                    }
            result.append(entry)
    return result


def evaluate(args):
    checked(
        not args.output.exists(),
        "Output already exists; first results must never be overwritten",
    )
    freeze = None
    if args.split == "H":
        checked(
            args.freeze_record is not None,
            "H requires a verified freeze record before access",
        )
        freeze = verify_freeze(args.freeze_record, args.product_root, args.python)
    elif args.freeze_record:
        freeze = verify_freeze(args.freeze_record, args.product_root, args.python)
    cases, verified_count = corpus_cases(args.split)
    source = source_record(args.product_root)
    environment = toolchain(args.python)
    args.output.mkdir(parents=True)
    started, started_at = time.perf_counter(), utc()
    metadata = {
        "schema_version": 1,
        "split": args.split,
        "evaluation_class": "published_regression",
        "fresh_heldout_claim": False,
        "started_at": started_at,
        "source": source,
        "evaluator": file_record(__file__),
        "contract": file_record(CONTRACT),
        "corpus_manifest": file_record(CORPUS / "manifest.json"),
        "verified_sealed_file_count": verified_count,
        "evaluation_config": CONFIG,
        "worker_toolchain": environment,
        "evaluator_toolchain": {
            "version": sys.version,
            "rng": "Python random.Random / MT19937",
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "freeze_record": file_record(args.freeze_record) if freeze else None,
        "independent_input_count": len(cases),
        "complete": False,
    }
    save_new(args.output / "started.json", metadata)
    rows = []
    worker = None
    with (
        (args.output / "worker-transcript.ndjson").open(
            "x", encoding="utf-8", newline="\n"
        ) as transcript,
        (args.output / "runs.ndjson").open("x", encoding="utf-8", newline="\n") as receipts,
    ):
        try:
            worker = Worker(args.python, args.product_root, transcript)
            for case in cases:
                settings = case["settings"].get("runs", [case["settings"]])
                for setting in settings:
                    for lam in CONFIG["lambdas"]:
                        for policy in CONFIG["policies"]:
                            seeds = CONFIG["random_seeds"] if policy == "random" else [None]
                            for seed in seeds:
                                row = run_case(worker, case, args.split, policy, lam, seed, setting)
                                rows.append(row)
                                receipts.write(
                                    json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                                )
                                receipts.flush()
                                if row["status"] == "execution_error":
                                    cleanup = worker.close()
                                    transcript.write(
                                        json.dumps({"worker_cleanup_after_failure": cleanup}) + "\n"
                                    )
                                    worker = Worker(args.python, args.product_root, transcript)
                print(
                    json.dumps(
                        {
                            "split": args.split,
                            "case_completed": case["id"],
                            "retained_runs": len(rows),
                        }
                    ),
                    flush=True,
                )
        finally:
            if worker:
                save_new(args.output / "worker-cleanup.json", worker.close())
    unchanged = source_record(args.product_root) == source
    if freeze:
        verify_freeze(args.freeze_record, args.product_root, args.python)
    result = {
        **metadata,
        "complete": True,
        "finished_at": utc(),
        "wall_seconds": time.perf_counter() - started,
        "source_unchanged": unchanged,
        "run_count": len(rows),
        "expectation_failures": sum(not row["expectation_pass"] for row in rows),
        "execution_errors": sum(row["status"] == "execution_error" for row in rows),
        "groups": grouped_summaries(rows),
        "limitations": [
            "Public reruns are published regression evaluations, never fresh held-out evidence.",
            "Synthetic authored cases, not customers or independently sampled real documents.",
            "Twenty random seeds repeat the same cases; they are not extra independent inputs.",
            "Declared field cost is neither elapsed time nor money.",
            "Resolution is conditional on supplied alternatives; a mimicking outside truth is undetectable.",
        ],
    }
    save_new(args.output / "result.json", result)
    save_new(
        args.output / "index.json",
        {"files": [file_record(path) for path in sorted(args.output.iterdir()) if path.is_file()]},
    )
    print(
        json.dumps(
            {
                "complete": True,
                "run_count": len(rows),
                "result_sha256": digest(args.output / "result.json"),
                "expectation_failures": result["expectation_failures"],
                "source_unchanged": unchanged,
            }
        )
    )
    return (
        0
        if unchanged and result["expectation_failures"] == 0 and result["execution_errors"] == 0
        else 1
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("D", "H", "S"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--product-root", type=Path, default=ROOT)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--freeze-record", type=Path)
    parser.add_argument("--prepare-freeze", type=Path)
    parser.add_argument("--artifact", type=Path, action="append")
    args = parser.parse_args(argv)
    args.product_root = args.product_root.resolve()
    args.python = args.python.resolve()
    try:
        if args.prepare_freeze:
            checked(
                not args.split and not args.output,
                "Freeze preparation does not execute a split",
            )
            prepare_freeze(args)
            return 0
        checked(args.split and args.output, "Evaluation requires --split and --output")
        return evaluate(args)
    except (EvaluationError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"complete": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
