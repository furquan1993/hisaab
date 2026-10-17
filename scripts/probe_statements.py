"""Local, interactive PDF extraction experiment; not a transaction parser."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pdfminer.pdfdocument import PDFPasswordIncorrect


TEXT_TABLES = {"vertical_strategy": "text", "horizontal_strategy": "text"}


def extract_statement(path, password):
    """Keep decrypted contents in memory; never include the password in results.

    APIs: https://github.com/jsvine/pdfplumber#loading-a-pdf
    https://github.com/jsvine/pdfplumber#extracting-tables
    """
    pages = []
    try:
        document = pdfplumber.open(path, password=password)
    except PdfminerException as error:
        # pdfplumber 0.11.10 wraps PDFMiner errors in its own exception.
        if error.args and isinstance(error.args[0], PDFPasswordIncorrect):
            raise PDFPasswordIncorrect from None
        raise
    with document as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            pages.append({
                "page": number,
                "text": page.extract_text() or "",
                "words": page.extract_words(),
                "tables_lines": page.extract_tables(),
                "tables_text": page.extract_tables(TEXT_TABLES),
            })
    return {"source": path.name, "pages": pages}


def save_result(result, directory):
    """Write sensitive extraction results to a new owner-only file."""
    destination = directory / (Path(result["source"]).stem + ".json")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
        output.write("\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path,
                        help="PDF paths; defaults to PDFs directly inside data/")
    args = parser.parse_args()
    paths = args.paths or sorted(Path("data").glob("*.pdf"))
    if not paths:
        print("No PDFs found in data/. Add statements or supply PDF paths.", file=sys.stderr)
        return 2
    if any(not path.is_file() or path.suffix.lower() != ".pdf" for path in paths):
        print("Every input must be an existing PDF file.", file=sys.stderr)
        return 2
    if len({path.stem for path in paths}) != len(paths):
        print("Input PDF filenames must have distinct stems.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print("Run in your terminal to enter passwords securely. Do not pipe passwords.",
              file=sys.stderr)
        return 2

    # New directories/files are private even if the caller's umask is permissive.
    os.umask(0o077)
    root = Path("data/probes")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    print(f"Private extraction output: {directory}", file=sys.stderr)
    failed = False
    for path in paths:
        password = getpass.getpass(f"Password for {path.name} (Enter if none): ")
        try:
            result = extract_statement(path, password)
        except PDFPasswordIncorrect:
            print(f"{path.name}: incorrect password; rerun to retry.", file=sys.stderr)
            failed = True
            continue
        except Exception:
            # Raw PDF errors can contain document contents. Never print them.
            print(f"{path.name}: extraction failed; no result saved.", file=sys.stderr)
            failed = True
            continue
        finally:
            password = None
        destination = save_result(result, directory)
        pages = result["pages"]
        chars = sum(len(page["text"]) for page in pages)
        tables = sum(len(page["tables_lines"]) + len(page["tables_text"]) for page in pages)
        print(f"{path.name}: pages={len(pages)}, text_chars={chars}, "
              f"table_candidates={tables}, output={destination}")
        if not chars:
            print("  No text extracted; inspect the PDF for scanned pages/OCR needs.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; previously saved local results remain.", file=sys.stderr)
        sys.exit(130)
    except OSError:
        print("Local file operation failed. Check paths, permissions, and disk space.",
              file=sys.stderr)
        sys.exit(1)
