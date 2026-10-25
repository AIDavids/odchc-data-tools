"""Clean messy monthly facility workbooks into one consistent schema.

Design notes (lessons from the original SIWES prototype):
  * Every cell is read as TEXT. Letting pandas guess types turned phone numbers into
    floats ("8030000001.0", lost leading zero) and dates into timestamps.
  * Header detection needs several keyword hits, not one, so a title row like
    "Name of facility ..." is not mistaken for the header.
  * Source files are NEVER deleted or modified.
"""
import re
from pathlib import Path

import pandas as pd
from dateutil import parser as dtparser

HEADER_KEYWORDS = [
    "name of client", "date of booking", "orin", "hospital number", "phone",
    "age", "address", "type of client", "parity", "place of issue",
]
MIN_KEYWORD_HITS = 3
MAX_HEADER_SCAN_ROWS = 50

CANON_RULES = [
    (r"^s/?n\b", "serial_no"),
    (r"^name of client", "client_name"),
    (r"^date of booking", "booking_date"),
    (r"^orin", "orin"),
    (r"^place of issue", "place_of_issue"),
    (r"^hospital number", "hospital_number"),
    (r"^age\b", "age"),
    (r"^address", "address"),
    (r"^phone", "phone"),
    (r"^type of client", "client_type"),
    (r"^parity", "parity"),
]
CANON_COLUMNS = [c for _, c in CANON_RULES]


def _isnull(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def canon_col(header) -> str | None:
    n = _norm(header)
    for pattern, canon in CANON_RULES:
        if re.search(pattern, n):
            return canon
    return None


def find_header_row(raw: pd.DataFrame) -> int | None:
    for i in range(min(MAX_HEADER_SCAN_ROWS, len(raw))):
        cells = [_norm(c) for c in raw.iloc[i] if pd.notna(c)]
        hits = sum(any(k in cell for cell in cells) for k in HEADER_KEYWORDS)
        if hits >= MIN_KEYWORD_HITS:
            return i
    return None


def normalise_name(value) -> str | None:
    if _isnull(value):
        return None
    s = re.sub(r"[^A-Za-z'\- ]", " ", str(value)).upper()
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def name_key(value) -> str | None:
    """Order-insensitive key so 'ADA JOHN' matches 'JOHN ADA'."""
    n = normalise_name(value)
    return " ".join(sorted(n.split())) if n else None


def normalise_phone(value) -> str | None:
    if _isnull(value):
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0+", s):  # float artefact from Excel numbers
        s = s.split(".")[0]
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    if len(digits) == 13 and digits.startswith("234"):
        digits = "0" + digits[3:]
    if len(digits) == 10 and not digits.startswith("0"):
        digits = "0" + digits  # leading zero lost when Excel stored it as a number
    return digits


def normalise_date(value) -> str | None:
    if _isnull(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    try:
        d = dtparser.parse(s, dayfirst=True)
    except (ValueError, OverflowError):
        return None
    return d.date().isoformat() if 2000 <= d.year <= 2035 else None


def normalise_age(value) -> str | None:
    if _isnull(value):
        return None
    m = re.search(r"\d+", str(value))
    return m.group(0) if m else None


def _clean_id(v):
    return None if _isnull(v) else re.sub(r"\.0+$", "", str(v).strip())


def clean_workbook(path: Path) -> tuple[pd.DataFrame | None, dict]:
    info = {"file": path.name, "status": "ok", "sheet": None, "header_row": None,
            "rows_in": 0, "rows_out": 0, "dates_unparsed": 0, "phones_not_11_digits": 0}
    try:
        xls = pd.ExcelFile(path)
    except Exception as e:  # corrupt / unreadable workbook
        info["status"] = f"unreadable: {type(e).__name__}"
        return None, info

    raw = header_row = sheet = None
    for sheet in xls.sheet_names:
        raw = pd.read_excel(xls, sheet, header=None, dtype=str)
        header_row = find_header_row(raw)
        if header_row is not None:
            break
    if header_row is None:
        info["status"] = "no_header_found"
        return None, info

    info["sheet"], info["header_row"] = sheet, int(header_row)
    cols = [canon_col(h) if pd.notna(h) else None for h in raw.iloc[header_row]]
    body = raw.iloc[header_row + 1:].copy()
    body.columns = range(body.shape[1])
    keep, seen = {}, set()
    for idx, canon in enumerate(cols):
        if canon and canon not in seen:
            keep[idx] = canon
            seen.add(canon)
    df = body[list(keep)].rename(columns=keep)
    for c in CANON_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[CANON_COLUMNS]
    info["rows_in"] = len(df)

    df["client_name"] = df["client_name"].map(normalise_name)
    df = df[df["client_name"].notna() & (df["client_name"] != "NAME OF CLIENT")].copy()
    df["name_key"] = df["client_name"].map(name_key)

    raw_dates = df["booking_date"]
    df["booking_date"] = raw_dates.map(normalise_date)
    info["dates_unparsed"] = int((df["booking_date"].isna() & raw_dates.notna()).sum())
    df["phone"] = df["phone"].map(normalise_phone)
    info["phones_not_11_digits"] = int((df["phone"].notna() & (df["phone"].str.len() != 11)).sum())
    df["age"] = df["age"].map(normalise_age)
    for c in ("serial_no", "hospital_number"):
        df[c] = df[c].map(_clean_id)
    df["source_file"] = path.stem
    info["rows_out"] = len(df)
    return df.reset_index(drop=True), info


def clean_directory(in_dir: Path, out_dir: Path) -> pd.DataFrame:
    """Clean every workbook; write one CSV each (originals untouched). Returns a quality report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for path in sorted(Path(in_dir).rglob("*.xls*")):
        df, info = clean_workbook(path)
        if df is not None:
            df.to_csv(out_dir / f"{path.stem}.csv", index=False)
        report.append(info)
    return pd.DataFrame(report)
