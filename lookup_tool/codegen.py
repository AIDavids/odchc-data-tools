"""Authorization-code step: REBUILD on synthetic data.

The original ODCHC generator was lost, so the code format and rules below are ILLUSTRATIVE
design choices, not the ODCHC format. Design goals:
  * every code is unique, even if two people click at the same moment (BEGIN IMMEDIATE + UNIQUE);
  * one code per enrollee, so a second click returns the existing code instead of a duplicate;
  * a check character catches mistyped or swapped digits when a code is read out or copied;
  * SQLite is the source of truth. Excel is an export, because several people writing to one
    live Excel file is a classic way to lose or overwrite rows.
"""
import datetime as dt
import re
import sqlite3

from openpyxl import Workbook

from .cleaning import name_key

ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # 34 characters (no I or O)
CODE_RE = re.compile(r"^AUTH-(\d{2})(\d{2})-(\d{4})-([0-9A-HJ-NP-Z])$")
COLUMNS = ["code", "client_name", "orin", "source_file", "requested_by", "requested_at"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS authorization_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    yymm TEXT NOT NULL,
    seq INTEGER NOT NULL,
    identity TEXT NOT NULL UNIQUE,
    client_name TEXT, orin TEXT, source_file TEXT,
    requested_by TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    UNIQUE (yymm, seq)
)"""


def connect(path: str) -> sqlite3.Connection:
    """Autocommit mode, so generate_code controls its own transaction."""
    con = sqlite3.connect(path, isolation_level=None)
    con.execute(SCHEMA)
    return con


def check_char(digits: str) -> str:
    """Weighted sum mod 34. 34 = 2 x 17, so any single wrong digit (weights 1-8, change 1-9)
    or swapped adjacent pair of different digits always changes the result."""
    total = sum((i + 1) * int(d) for i, d in enumerate(digits))
    return ALPHABET[total % len(ALPHABET)]


def verify_code(code: str) -> tuple[bool, str]:
    m = CODE_RE.match((code or "").strip().upper())
    if not m or not 1 <= int(m.group(2)) <= 12:
        return False, "bad_format"
    yy, mm, seq, chk = m.groups()
    return (True, "ok") if check_char(yy + mm + seq) == chk else (False, "check_character_mismatch")


def generate_code(con: sqlite3.Connection, *, orin, client_name, source_file, requested_by,
                  now: dt.datetime | None = None) -> dict:
    identity = (orin or "").strip() or (name_key(client_name) or "")
    if not identity:
        raise ValueError("need an ORIN or a name")
    if not (requested_by or "").strip():
        raise ValueError("requested_by is required")
    now = now or dt.datetime.now()
    yymm = now.strftime("%y%m")

    con.execute("BEGIN IMMEDIATE")  # takes the write lock first, so two requests cannot get the same number
    try:
        row = con.execute("SELECT code FROM authorization_codes WHERE identity = ?", (identity,)).fetchone()
        if row:
            con.execute("COMMIT")
            return {"code": row[0], "already_issued": True}
        seq = con.execute("SELECT COALESCE(MAX(seq), 0) FROM authorization_codes WHERE yymm = ?",
                          (yymm,)).fetchone()[0] + 1
        if seq > 9999:
            raise OverflowError("monthly code limit reached")
        code = f"AUTH-{yymm}-{seq:04d}-{check_char(yymm + f'{seq:04d}')}"
        con.execute(
            "INSERT INTO authorization_codes (code, yymm, seq, identity, client_name, orin, source_file, "
            "requested_by, requested_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (code, yymm, seq, identity, client_name, orin, source_file, requested_by.strip(),
             now.isoformat(timespec="seconds")))
        con.execute("COMMIT")
        return {"code": code, "already_issued": False}
    except Exception:
        con.execute("ROLLBACK")
        raise


def export_excel(con: sqlite3.Connection, target) -> int:
    """Write all issued codes to an .xlsx (path or file-like object). Returns the row count."""
    rows = con.execute(f"SELECT {', '.join(COLUMNS)} FROM authorization_codes ORDER BY id").fetchall()
    wb = Workbook()
    ws = wb.active
    ws.title = "Authorization codes"
    ws.append(COLUMNS)
    for r in rows:
        ws.append(list(r))
    for col, w in zip("ABCDEF", [18, 30, 16, 36, 16, 20]):
        ws.column_dimensions[col].width = w
    wb.save(target)
    return len(rows)
