"""One callable for the whole clean -> CSV -> SQLite pipeline (used by master.py and the script)."""
from pathlib import Path

from .cleaning import clean_directory
from .db import build_db


def run_pipeline(raw_dir, clean_dir, db_path, report_path) -> dict:
    raw_dir, clean_dir = Path(raw_dir), Path(clean_dir)
    if not raw_dir.exists() or not any(raw_dir.rglob("*.xls*")):
        raise FileNotFoundError(
            f"No Excel workbooks found in {raw_dir}. Generate synthetic ones first (master.py, option 4).")
    report = clean_directory(raw_dir, clean_dir)
    # remove CSVs left over from an earlier run whose workbook no longer exists (output folder only)
    current = {p.stem for p in raw_dir.rglob("*.xls*")}
    for stale in clean_dir.glob("*.csv"):
        if stale.stem not in current:
            stale.unlink()
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(report_path, index=False)
    rows = build_db(clean_dir, db_path)
    ok = report[report.status == "ok"] if len(report) else report
    return {"workbooks": len(report), "cleaned": len(ok), "skipped": len(report) - len(ok), "rows": rows,
            "dates_unparsed": int(report.dates_unparsed.sum()),
            "phones_not_11_digits": int(report.phones_not_11_digits.sum())}
