"""Local parsing and database checks. Stdout is JSON; financial rows are opt-in."""

import argparse
import getpass
import json
import sys
from pathlib import Path

from core.config import DEFAULT_CONFIG, ConfigurationError, load_config
from core.database import DatabaseError, check_connection
from core.extraction import ParseError
from core.models import Statement
from core.output import save_statement
from core.parser import parse_pdf, parse_probe


class UsageError(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo arbitrary argument values: they may contain a secret.
        raise UsageError


def _arguments(argv):
    parser = ArgumentParser(
        description="Parse supported bank statements locally into private transaction JSON.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    database = subparsers.add_parser(
        "db-check",
        help="Check private database configuration with SELECT 1.",
        allow_abbrev=False,
    )
    database.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    for command, help_text in (
        (
            "parse",
            "Parse original PDFs; prompt privately if encrypted and a terminal is available.",
        ),
        (
            "parse-probe",
            "Review existing extraction JSON without reopening a PDF (diagnostic only).",
        ),
    ):
        subparser = subparsers.add_parser(command, help=help_text, allow_abbrev=False)
        subparser.add_argument("paths", nargs="+", type=Path)
        subparser.add_argument(
            "--output-dir",
            type=Path,
            default=Path("data/parsed"),
            help="Private result directory base (default: data/parsed).",
        )
        subparser.add_argument(
            "--show-transactions",
            action="store_true",
            help="Explicitly print all sensitive transaction data to stdout too.",
        )
    return parser.parse_args(argv)


def _parse_pdf_with_prompt(path):
    try:
        return parse_pdf(path)
    except ParseError as error:
        if error.code != "incorrect_password":
            raise
    if not sys.stdin.isatty():
        raise ParseError(
            "password_required",
            "Run parse in your own terminal for hidden password entry, "
            "or use parse-probe to review existing extraction JSON.",
        )
    password = getpass.getpass("PDF password (hidden): ")
    try:
        return parse_pdf(path, password=password)
    finally:
        password = None


def _emit(payload):
    print(json.dumps(payload, ensure_ascii=True))


def _result_payload(
    statement: Statement,
    destination: Path,
    show_transactions: bool,
    *,
    source_name: str,
) -> dict:
    if show_transactions:
        payload = statement.to_dict()
        payload["output"] = str(destination)
        return payload
    return {
        "source": source_name,
        "input_kind": statement.input_kind,
        "status": "needs_review" if statement.needs_review else "parsed",
        "transaction_count": len(statement.transactions),
        "review_issue_count": len(statement.issues)
        + sum(len(row.issues) for row in statement.transactions),
        "output": str(destination),
    }


def _process_input(path: Path, args: argparse.Namespace) -> int:
    """Process one input, keeping document errors at the CLI privacy boundary."""
    try:
        statement = (
            parse_probe(path)
            if args.command == "parse-probe"
            else _parse_pdf_with_prompt(path)
        )
        destination = save_statement(statement, args.output_dir)
        _emit(
            _result_payload(
                statement, destination, args.show_transactions, source_name=path.name
            )
        )
        return 3 if statement.needs_review else 0
    except ParseError as error:
        _emit(
            {
                "source": path.name,
                "error": {"code": error.code, "message": str(error)},
            }
        )
    except OSError:
        _emit(
            {
                "source": path.name,
                "error": {
                    "code": "output_failed",
                    "message": "Check output paths, permissions, and disk space.",
                },
            }
        )
    except (KeyboardInterrupt, EOFError):
        _emit(
            {
                "error": {
                    "code": "cancelled",
                    "message": "Cancelled; prior results remain local.",
                }
            }
        )
        return 130
    except Exception:
        # Dependency tracebacks may include document contents. API callers
        # can debug locally; CLI failures never dump those details.
        _emit(
            {
                "source": path.name,
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected parser failure; no successful result reported.",
                },
            }
        )
    return 1


def _database_check(path: Path) -> int:
    try:
        check_connection(load_config(path))
    except (ConfigurationError, DatabaseError) as error:
        _emit({"error": {"code": error.code, "message": str(error)}})
        return 1
    except (KeyboardInterrupt, EOFError):
        _emit(
            {"error": {"code": "cancelled", "message": "Connection check cancelled."}}
        )
        return 130
    except Exception:
        _emit(
            {
                "error": {
                    "code": "database_unavailable",
                    "message": "Database check failed; no connection details printed.",
                }
            }
        )
        return 1
    _emit({"status": "connected"})
    return 0


def main(argv=None) -> int:
    try:
        args = _arguments(argv)
    except UsageError:
        _emit(
            {
                "error": {
                    "code": "usage_error",
                    "message": "Use: uv run python -m core {parse,parse-probe} PATH [PATH ...], or db-check. "
                    "Options: --output-dir PATH, --show-transactions, -h.",
                }
            }
        )
        return 2
    if args.command == "db-check":
        return _database_check(args.config)
    exit_code = 0
    for path in args.paths:
        result = _process_input(path, args)
        if result == 130:
            return 130
        # Failure outranks review-needed; later successes cannot clear either.
        if result == 1 or exit_code == 0:
            exit_code = result
    return exit_code
