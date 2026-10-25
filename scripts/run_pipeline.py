"""Clean workbooks -> CSVs -> SQLite. Usage: python scripts/run_pipeline.py [raw_dir]
(master.py option 1 does the same thing.)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lookup_tool.pipeline import run_pipeline

raw = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw_xlsx"
r = run_pipeline(raw, ROOT / "data" / "clean_csv", ROOT / "data" / "enrollees.db", ROOT / "data" / "cleaning_report.csv")
print(f"{r['workbooks']} workbooks read, {r['cleaned']} cleaned, {r['skipped']} skipped. "
      f"{r['rows']} rows loaded into data/enrollees.db")
print(f"Unparsed dates: {r['dates_unparsed']}  |  phones not 11 digits: {r['phones_not_11_digits']}")
