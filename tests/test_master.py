import socket
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import master  # noqa: E402
from lookup_tool.db import DatabaseBusyError, build_db  # noqa: E402
from lookup_tool.pipeline import run_pipeline  # noqa: E402


def _csv_dir(tmp_path):
    d = tmp_path / "csv"
    d.mkdir()
    pd.DataFrame({"client_name": ["ADA JOHN", "BOLA KEMI"], "name_key": ["ADA JOHN", "BOLA KEMI"]}).to_csv(
        d / "a.csv", index=False)
    return d


def test_free_port_skips_a_busy_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    busy = s.getsockname()[1]
    try:
        assert master.port_in_use(busy)
        free = master.find_free_port(busy)
        assert free != busy and not master.port_in_use(free)
    finally:
        s.close()


def test_rebuilding_does_not_duplicate_rows_or_delete_the_file(tmp_path):
    d, db = _csv_dir(tmp_path), tmp_path / "x.db"
    assert build_db(d, db) == 2
    assert build_db(d, db) == 2
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM enrollees").fetchone()[0] == 2


def test_locked_database_gives_a_clean_message_not_a_traceback(tmp_path):
    d, db = _csv_dir(tmp_path), tmp_path / "x.db"
    build_db(d, db)
    blocker = sqlite3.connect(db, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(DatabaseBusyError) as e:
            build_db(d, db, timeout=0.2)
        assert "in use by another program" in str(e.value)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert build_db(d, db) == 2  # works again once the lock is released


def test_pipeline_explains_missing_workbooks(tmp_path):
    with pytest.raises(FileNotFoundError, match="option 4"):
        run_pipeline(tmp_path / "none", tmp_path / "c", tmp_path / "d.db", tmp_path / "r.csv")


def test_safe_run_survives_any_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(master, "DATA", tmp_path)
    monkeypatch.setattr(master, "ERROR_LOG", tmp_path / "err.log")

    def boom():
        raise RuntimeError("kaboom")

    assert master.safe_run(boom) is False
    assert "Something went wrong" in capsys.readouterr().out
    assert "kaboom" in (tmp_path / "err.log").read_text()


def test_menu_stays_open_after_a_failed_action(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(master, "DB", tmp_path / "missing.db")
    # open tool 1, run the benchmark with no database (fails), a bad choice, back, exit
    answers = iter(["1", "5", "nonsense", "0", "0"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert master.menu() == 0
    out = capsys.readouterr().out
    assert "Run option 1 first" in out and "Please type one of the numbers" in out and "Goodbye" in out


def test_flags_parse():
    a = master.build_parser().parse_args(["--generate", "5", "--pipeline", "--export-codes"])
    assert a.generate == 5 and a.pipeline and a.export_codes


def test_menu_is_grouped_by_named_tool():
    names = [t["name"] for t in master.TOOLS.values()]
    assert any("Abiyamo Enrollee Lookup" in n for n in names)
    assert any("Chrome extension" in n for n in names)
    assert not any("Tracker" in n for n in names)
    lookup = [label for label, _ in master.TOOLS["1"]["items"].values()]
    assert any("authorization-code" in x for x in lookup) and any("Clean" in x for x in lookup)
    forms = [label for label, _ in master.TOOLS["2"]["items"].values()]
    assert any("Chrome extension" in x for x in forms)
    for tool in master.TOOLS.values():
        assert all(callable(fn) for _, fn in tool["items"].values())


def test_help_lists_every_tool(capsys):
    master.show_help()
    out = capsys.readouterr().out
    assert all(t["name"] in out for t in master.TOOLS.values())


def test_practice_form_server_serves_the_mock_form_and_stops():
    import urllib.request
    port = master.find_free_port(8100)
    server = master.start_mock_server(port)
    try:
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5).read().decode()
        assert 'id="surname"' in html and 'id="dob"' in html
    finally:
        server.shutdown()
        server.server_close()
