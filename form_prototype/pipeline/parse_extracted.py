"""Turn raw model output ('FIELD: value' lines) into clean records.

Logs only the form id and the reason for a failure, never the person's details.
"""
import argparse
import json
import re
from pathlib import Path

import pandas as pd
from dateutil import parser as dtparser

FIELDS = ["SURNAME", "FIRST_NAME", "DOB", "GENDER", "PHONE", "ADDRESS", "OCCUPATION"]


def parse_text(text: str) -> dict:
    rec = {f: None for f in FIELDS}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().upper().replace(" ", "_")
        val = val.strip()
        if key in rec and val and val.upper() not in {"NULL", "N/A", "NONE"}:
            rec[key] = val
    return rec


def parse_dob(text):
    """Return (iso_date, error_reason). Handwritten dates are messy: '14th feb. 1999'."""
    if not text:
        return None, "missing"
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip(), flags=re.I).replace(".", " ")
    if not re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", s):  # a 2-digit year is a guess, so flag it
        return None, "no_four_digit_year"
    try:
        d = dtparser.parse(s, dayfirst=True)
    except (ValueError, OverflowError):
        return None, "unparseable"
    if not 1900 <= d.year <= 2025:
        return None, "implausible_year"
    return d.date().isoformat(), None


def age_from_dob(iso: str, today: str = "2025-01-01") -> int:
    b, t = [int(x) for x in iso.split("-")], [int(x) for x in today.split("-")]
    return t[0] - b[0] - ((t[1], t[2]) < (b[1], b[2]))


def build_record(form_id: str, text: str) -> tuple[dict, list[dict]]:
    rec, problems = parse_text(text), []
    iso, err = parse_dob(rec["DOB"])
    if err:
        problems.append({"form_id": form_id, "field": "DOB", "reason": err})
    rec["DOB"] = iso
    rec["PHONE"] = re.sub(r"\D", "", rec["PHONE"]) if rec["PHONE"] else None
    rec["form_id"] = form_id
    return rec, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="form_prototype/sample")
    ap.add_argument("--out-json", default="data/records.json")
    ap.add_argument("--out-xlsx", default="data/records.xlsx")
    a = ap.parse_args()
    records, problems = [], []
    for p in sorted(Path(a.in_dir).glob("*.txt")):
        r, pr = build_record(p.stem, p.read_text(encoding="utf-8"))
        records.append(r)
        problems += pr
    Path(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out_json).write_text(json.dumps(records, indent=2), encoding="utf-8")
    pd.DataFrame(records).to_excel(a.out_xlsx, index=False)
    print(f"{len(records)} records, {len(problems)} flagged for manual review: {problems}")


if __name__ == "__main__":
    main()
