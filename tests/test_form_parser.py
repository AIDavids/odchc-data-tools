import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "form_prototype" / "pipeline"))
from parse_extracted import build_record, parse_dob, age_from_dob


def test_messy_handwritten_dates():
    assert parse_dob("14th Feb. 1991") == ("1991-02-14", None)
    assert parse_dob("3/11/1985") == ("1985-11-03", None)
    assert parse_dob("14th. feb. 19th")[0] is None


def test_unparseable_dob_is_flagged_without_personal_data():
    rec, problems = build_record("form_003", "SURNAME: X\nDOB: 14th. feb. 19th\nPHONE: 0813 000 0003")
    assert rec["DOB"] is None and rec["PHONE"] == "08130000003"
    assert problems == [{"form_id": "form_003", "field": "DOB", "reason": "no_four_digit_year"}]
    assert "X" not in str(problems)


def test_null_values_become_none():
    rec, _ = build_record("f", "SURNAME: Bello\nOCCUPATION: NULL\nDOB: 3/11/1985")
    assert rec["OCCUPATION"] is None


def test_age_from_dob():
    assert age_from_dob("1991-02-14", "2025-01-01") == 33
