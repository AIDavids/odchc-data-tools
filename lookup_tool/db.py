"""Load cleaned CSVs into SQLite once, then search with an index."""
import sqlite3
from pathlib import Path

import pandas as pd

from .cleaning import name_key, normalise_name


class DatabaseBusyError(RuntimeError):
    """The database file is locked by another program (usually the running web app)."""


BUSY_MESSAGE = (
    "The database ({path}) is in use by another program, most likely the web app.\n"
    "  -> Stop the web app (press Ctrl+C in its window), or close any other window using it, then try again."
)


def build_db(csv_dir: Path, db_path: Path, timeout: float = 5.0) -> int:
    """(Re)build the enrollee table. The file is never deleted: the table is replaced inside an
    open connection, which avoids the Windows 'file is being used by another process' error."""
    frames = [pd.read_csv(p, dtype=str, keep_default_na=False) for p in sorted(Path(csv_dir).glob("*.csv"))]
    if not frames:
        raise FileNotFoundError(f"No cleaned CSV files found in {csv_dir}.")
    df = pd.concat(frames, ignore_index=True)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = sqlite3.connect(db_path, timeout=timeout)
        try:
            con.execute("DROP INDEX IF EXISTS idx_name_key")
            df.to_sql("enrollees", con, index=False, if_exists="replace")
            con.execute("CREATE INDEX idx_name_key ON enrollees(name_key)")
            con.commit()
        finally:
            con.close()
    except PermissionError as e:
        raise DatabaseBusyError(BUSY_MESSAGE.format(path=db_path)) from e
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            raise DatabaseBusyError(BUSY_MESSAGE.format(path=db_path)) from e
        raise
    return len(df)


def search(con: sqlite3.Connection, query: str, mode: str = "exact", limit: int = 200) -> list[dict]:
    con.row_factory = sqlite3.Row
    if mode == "exact":
        key = name_key(query)
        if not key:
            return []
        cur = con.execute("SELECT * FROM enrollees WHERE name_key = ? ORDER BY source_file LIMIT ?", (key, limit))
    else:  # every typed word must appear somewhere in the name
        tokens = (normalise_name(query) or "").split()
        if not tokens:
            return []
        where = " AND ".join("client_name LIKE ?" for _ in tokens)
        cur = con.execute(f"SELECT * FROM enrollees WHERE {where} ORDER BY source_file LIMIT ?",
                          [f"%{t}%" for t in tokens] + [limit])
    return [dict(r) for r in cur.fetchall()]
