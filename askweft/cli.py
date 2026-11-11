"""File-based CLI; all mutations use the same engine as the local browser UI."""

import argparse
from importlib.resources import files
from pathlib import Path
import sys

from . import __version__
from .domain import MAX_INPUT, Error, encoded, loads
from .store import Engine


def read(path):
    if path == "-":
        return sys.stdin.buffer.read(MAX_INPUT + 1)
    with Path(path).open("rb") as stream:
        return stream.read(MAX_INPUT + 1)


def settings(args):
    return {
        "lambda": args.cost_lambda,
        "question_budget": args.question_budget,
        "field_budget": args.field_budget,
    }


def add_settings(parser):
    parser.add_argument("--lambda", dest="cost_lambda", type=int, default=1)
    parser.add_argument("--question-budget", type=int, default=4)
    parser.add_argument("--field-budget", type=int, default=4)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="askweft", description="Plan and record document field requests."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--db", default="askweft.sqlite", help="Local SQLite file (default: askweft.sqlite)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser(
        "record", help="Record actual synthetic engine states to a new file"
    )
    record.add_argument("file")
    start = commands.add_parser("import", help="Import arbitrary Case v1 JSON bytes")
    start.add_argument("file")
    add_settings(start)
    for command in ("state", "suggest", "export"):
        sub = commands.add_parser(command)
        sub.add_argument("--session")
        if command == "export":
            sub.add_argument(
                "--original", action="store_true", help="Write exact original case bytes"
            )
    request = commands.add_parser("request", help="Explicitly charge and create a pending request")
    request.add_argument("--session", required=True)
    request.add_argument("--revision", required=True, type=int)
    request.add_argument("--question", required=True)
    answer = commands.add_parser("answer")
    answer.add_argument("--session", required=True)
    answer.add_argument("--revision", required=True, type=int)
    answer.add_argument("--request", required=True)
    answer.add_argument(
        "--answer-file", required=True, help="Typed field mapping JSON, or - for stdin"
    )
    restart = commands.add_parser(
        "restart", help="New session from retained input; old journal is preserved"
    )
    restart.add_argument("--session", required=True)
    add_settings(restart)
    for command in ("serve", "demo"):
        sub = commands.add_parser(command)
        sub.add_argument("--port", type=int, default=8746)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            from .demo import export_recording

            export_recording(args.file)
            return 0
        engine = Engine(args.db)
        command = args.command
        if command == "import":
            result = engine.import_case(read(args.file), settings(args))
        elif command == "restart":
            result = engine.restart(args.session, settings(args))
        elif command == "request":
            result = engine.request(args.session, args.revision, args.question)
        elif command == "answer":
            result = engine.answer(
                args.session, args.revision, args.request, loads(read(args.answer_file))
            )
        elif command in ("serve", "demo"):
            if command == "demo" and engine.state()["session"] is None:
                engine.import_case(
                    files("askweft").joinpath("examples", "invoice.json").read_bytes(),
                    synthetic=True,
                )
            from .server import serve

            serve(engine, port=args.port)
            return 0
        else:
            result = engine.state(args.session)
            if command == "suggest":
                result = result["session"]["suggestion"] if result["session"] else None
            elif command == "export" and args.original:
                if result["session"] is None:
                    raise Error("not_found", "No session to export")
                sys.stdout.buffer.write(engine.original(result["session"]["id"]))
                return 0
        sys.stdout.buffer.write(encoded(result) + b"\n")
        return 0
    except Error as error:
        sys.stderr.buffer.write(
            encoded({"error": {"code": error.code, "message": str(error)}}) + b"\n"
        )
        return 2
    except OSError:
        sys.stderr.write("Cannot read or write the requested local file.\n")
        return 2
