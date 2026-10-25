import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from lookup_tool.cleaning import (clean_directory, find_header_row, name_key, normalise_age,
                                  normalise_date, normalise_phone)
from lookup_tool.db import build_db, search

ROOT = Path(__file__).resolve().parents[1]


def test_header_found_below_title_rows():
    raw = pd.DataFrame([["Facility X monthly summary"], [None],
                        ["S/N", "Name of client", "Phone number", "Age"], [1, "A B", "0801", "20"]])
    assert find_header_row(raw) == 2


def test_title_row_alone_is_not_a_header():
    raw = pd.DataFrame([["Name of client register for the facility"], ["data"]])
    assert find_header_row(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("8030000001.0", "08030000001"), (8030000001, "08030000001"),
    ("08012345678", "08012345678"), ("2348012345678", "08012345678"), (None, None)])
def test_phone_keeps_leading_zero(raw, expected):
    assert normalise_phone(raw) == expected


def test_dates_are_iso_and_bad_dates_become_none():
    assert normalise_date("2020-04-06 00:00:00") == "2020-04-06"
    assert normalise_date("06-04-2020") == "2020-04-06"
    assert normalise_date("06/04/2020") == "2020-04-06"
    assert normalise_date("not a date") is None


def test_age_variants():
    assert normalise_age("22YRS") == "22" and normalise_age(31) == "31"


def test_name_key_ignores_order_case_and_spacing():
    assert name_key("Ada  john ") == name_key("JOHN ADA")


def test_legacy_default_dtype_bug_is_real(tmp_path):
    """The original prototype's bug: pandas guessed a float and showed 8030000001.0."""
    p = tmp_path / "x.csv"
    p.write_text("phone,age\n8030000001,22\n,30\n")  # one blank phone makes pandas guess float
    assert str(pd.read_csv(p)["phone"].iloc[0]) == "8030000001.0"
    assert pd.read_csv(p, dtype=str)["phone"].iloc[0] == "8030000001"


def test_end_to_end_on_generated_files(tmp_path):
    raw = tmp_path / "raw"
    subprocess.run([sys.executable, str(ROOT / "scripts/generate_synthetic_data.py"), "--out", str(raw),
                    "--files", "6", "--min-rows", "20", "--max-rows", "40"], check=True, cwd=ROOT)
    report = clean_directory(raw, tmp_path / "csv")
    assert (report.status == "ok").all()
    n = build_db(tmp_path / "csv", tmp_path / "t.db")
    assert n > 0
    with sqlite3.connect(tmp_path / "t.db") as con:
        hits = search(con, "patient sample alpha")
        assert len(hits) >= 1 and all(h["client_name"] == "SAMPLE PATIENT ALPHA" for h in hits)
        assert all(len(r["phone"]) == 11 for r in search(con, "sample patient", "partial"))
