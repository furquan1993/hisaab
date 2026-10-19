"""Read labeled examples from private XLSX files without importing transactions."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import posixpath
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from core.persistence.store import StoreError

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass(frozen=True)
class HistoryExample:
    source_key: str
    description: str
    direction: str
    account: str | None
    category: str | None


def read_history(path: Path) -> list[HistoryExample]:
    """Only labeled rows with a numeric amount; summaries and formula errors are skipped."""
    with path.open("rb") as file:
        data = file.read(20_000_001)
    if len(data) > 20_000_000:
        raise StoreError("invalid_workbook", "Workbook exceeds the 20 MB limit.")
    digest = sha256(data).hexdigest()
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100_000_000:
                raise ValueError("Workbook is too large")
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = ["".join(x.itertext()) for x in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
            relations = {x.attrib["Id"]: x.attrib["Target"] for x in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
            sheets = ET.fromstring(archive.read("xl/workbook.xml")).find("s:sheets", NS)
            examples = []
            for sheet in sheets:
                target = relations[sheet.attrib[f"{{{REL}}}id"]]
                member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
                header = None
                for row in ET.fromstring(archive.read(member)).findall("s:sheetData/s:row", NS):
                    values = {}
                    for cell in row.findall("s:c", NS):
                        column = "".join(c for c in cell.attrib["r"] if c.isalpha())
                        value = cell.find("s:v", NS)
                        text = value.text or "" if value is not None else ""
                        if cell.get("t") == "s":
                            text = strings[int(text)]
                        elif cell.get("t") == "inlineStr":
                            text = "".join(cell.find("s:is", NS).itertext())
                        elif cell.get("t") == "e":
                            text = ""
                        values[column] = text.strip()
                    names = {v.lower(): c for c, v in values.items() if v}
                    if ("description" in names or "item" in names) and ("account" in names or "category" in names):
                        header = names
                        continue
                    if header is None:
                        continue
                    def get(*names):
                        return next((values.get(header[n], "") for n in names if n in header), "")
                    description = get("description", "item")
                    account, category = get("account"), get("category")
                    try:
                        amount = Decimal(get("actual amount", "calculated amount", "amount", "amt").replace(",", ""))
                    except InvalidOperation:
                        continue
                    if not amount.is_finite() or not description or not (account or category):
                        continue
                    if any(len(x) > 120 or x.startswith("#") or any(ord(c) < 32 for c in x) for x in (account, category)) or len(description) > 2000:
                        continue
                    marker = get("debit / credit", "debit /credit", "debit/credit").lower()
                    if marker not in ("", "cr", "credit", "dr", "debit"):
                        continue
                    direction = "credit" if amount < 0 or marker in ("cr", "credit") else "debit"
                    key = sha256(f"{digest}:{sheet.attrib['name']}:{row.attrib['r']}".encode()).hexdigest()
                    examples.append(HistoryExample(key, description, direction, account or None, category or None))
            return examples
    except (KeyError, ValueError, ET.ParseError, BadZipFile, IndexError, AttributeError) as error:
        raise StoreError("invalid_workbook", "Workbook structure is unsupported.") from error
