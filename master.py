#!/usr/bin/env python3
"""ODCHC data tools: one launcher for everything (menu or command-line flags).

    python master.py                 interactive menu
    python master.py --generate 100  make synthetic workbooks, then exit
    python master.py --pipeline --web
Run  python master.py --help  for all flags. All data used here is synthetic.
"""
import argparse
import functools
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from contextlib import closing
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
RAW = DATA / "raw_xlsx"
CLEAN = DATA / "clean_csv"
DB = DATA / "enrollees.db"
CODES_DB = DATA / "authorization.db"
ERROR_LOG = DATA / "master_errors.log"
DEFAULT_PORT = 5000


# ---------- small helpers ----------
def interactive() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def ask(prompt: str, default: str = "") -> str:
    if not interactive():
        return default
    try:
        answer = input(prompt).strip()
    except EOFError:
        return default
    return answer or default


def pause() -> None:
    if interactive():
        try:
            input("\nPress Enter to return to the menu...")
        except EOFError:
            pass


def port_in_use(port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start: int, tries: int = 20) -> int:
    for p in range(start, start + tries):
        if not port_in_use(p):
            return p
    raise RuntimeError(f"No free port found between {start} and {start + tries - 1}.")


def run_script(args: list[str], cwd=None) -> bool:
    """Run a child Python process, showing its output live. Returns True on success."""
    return subprocess.run([sys.executable, *args], cwd=cwd or ROOT).returncode == 0


def need_database() -> bool:
    if DB.exists():
        return True
    print("There is no database yet. Run option 1 first (it builds data/enrollees.db).")
    return False


def log_error() -> None:
    try:
        DATA.mkdir(exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    except OSError:
        pass


def safe_run(action) -> bool:
    """Run one menu action. Any failure is reported in plain words and never closes the menu."""
    from lookup_tool.db import DatabaseBusyError
    try:
        return action() is not False
    except KeyboardInterrupt:
        print("\nCancelled.")
    except DatabaseBusyError as e:
        print(f"\n{e}")
    except FileNotFoundError as e:
        print(f"\n{e}")
    except PermissionError as e:
        print(f"\nA file is open in another program ({e.filename}). Close it and try again.")
    except Exception as e:  # keep the menu alive whatever happens
        print(f"\nSomething went wrong: {type(e).__name__}: {e}")
        print(f"Details were saved to {ERROR_LOG}.")
        log_error()
    return False


# ---------- actions ----------
def action_pipeline():
    from lookup_tool.pipeline import run_pipeline
    if not RAW.exists() or not any(RAW.rglob("*.xls*")):
        print(f"No workbooks found in {RAW}.")
        if ask("Generate synthetic workbooks now? [Y/n]: ", "y").lower().startswith("n"):
            return False
        if action_generate() is False:
            return False
    print("Cleaning workbooks and building the database...")
    r = run_pipeline(RAW, CLEAN, DB, DATA / "cleaning_report.csv")
    print(f"\n{r['workbooks']} workbooks read | {r['cleaned']} cleaned | {r['skipped']} skipped")
    print(f"{r['rows']:,} rows loaded into {DB.relative_to(ROOT)}")
    print(f"Unparsed dates: {r['dates_unparsed']} | phone numbers not 11 digits: {r['phones_not_11_digits']}")
    print(f"Per-file report: {(DATA / 'cleaning_report.csv').relative_to(ROOT)}")


def action_web():
    if not need_database():
        return False
    from lookup_tool.app import create_app
    port = DEFAULT_PORT
    if port_in_use(port):
        port = find_free_port(port + 1)
        print(f"Port {DEFAULT_PORT} is already in use (maybe the app is already running). Using port {port} instead.")
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"Serving {url}\nPress Ctrl+C to stop the server and return to the menu.\n")
    try:
        create_app(str(DB), str(CODES_DB)).run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass
    print("\nServer stopped.")


def action_forms(show=True):
    sample = ROOT / "form_prototype" / "sample"
    if os.environ.get("GROQ_API_KEY") or (ROOT / ".env").exists():
        folder = ask("Optional live OCR: folder of SYNTHETIC form images (Enter to skip): ")
        if folder:
            if not run_script([str(ROOT / "form_prototype/pipeline/extract_form.py"), folder, "--out", str(sample)]):
                print("OCR step failed (check your key and folder). Continuing with the sample text files.")
    else:
        print("No GROQ_API_KEY found, so using the sample text files already in form_prototype/sample/.")
    if not run_script([str(ROOT / "form_prototype/pipeline/parse_extracted.py")]):
        return False
    out = DATA / "records.json"
    if show:
        print(f"\nStructured records ({out.relative_to(ROOT)}):")
        print(json.dumps(json.loads(out.read_text(encoding="utf-8")), indent=2))
    print(f"\nSaved: {out.relative_to(ROOT)} and data/records.xlsx")


def action_generate(n=None):
    if n is None:
        raw = ask("How many synthetic workbooks? [544]: ", "544")
        if not raw.isdigit() or int(raw) < 1:
            print("Please enter a whole number of 1 or more.")
            return False
        n = int(raw)
    existing = len(list(RAW.rglob("*.xls*"))) if RAW.exists() else 0
    if existing:
        print(f"Note: {RAW.relative_to(ROOT)} already holds {existing} workbook(s); same-named files are overwritten, others stay.")
    return run_script(["scripts/generate_synthetic_data.py", "--out", str(RAW), "--files", str(n)])


def action_benchmark():
    if not need_database():
        return False
    if not CLEAN.exists():
        print("Run option 1 first so the cleaned CSV files exist.")
        return False
    return run_script(["scripts/benchmark.py"])


def action_prepush():
    return run_script(["scripts/pre_push_check.py"])


def action_tests():
    return run_script(["-m", "pytest", "tests/", "-v"])


def action_export_codes():
    from lookup_tool import codegen
    if not CODES_DB.exists():
        print("No authorization codes have been generated yet (use the web page, option 2).")
        return False
    out = DATA / "authorization_codes.xlsx"
    with closing(codegen.connect(str(CODES_DB))) as con:
        n = codegen.export_excel(con, str(out))
    print(f"Exported {n} code(s) to {out.relative_to(ROOT)}")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_mock_server(port: int):
    """Serve the practice enrollment form (form_prototype/mock_form) in a background thread."""
    handler = functools.partial(_QuietHandler, directory=str(ROOT / "form_prototype" / "mock_form"))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def open_folder(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(path)  # Windows: opens File Explorer


def action_extension():
    ext_dir = ROOT / "form_prototype" / "extension"
    records = DATA / "records.json"
    if not records.exists():
        print("records.json does not exist yet, so creating it from the sample forms first...")
        if action_forms(show=False) is False:
            return False
    port = find_free_port(8000)
    server = start_mock_server(port)
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    open_folder(ext_dir)
    print(f"""
The practice enrollment form is open at {url}

Now install the Chrome extension (one time):
  1. In Chrome, type  chrome://extensions  in the address bar and press Enter.
  2. Turn on "Developer mode" (top right).
  3. Click "Load unpacked" and choose this folder:
        {ext_dir}
  4. Click the extension's icon (puzzle piece menu), choose the file below, then click "Fill current record":
        {records}
  5. Use "Next record" to move through the records. Watch the form (and the age) fill itself.
""")
    try:
        if interactive():
            input("Press Enter here when you have finished to stop the practice form...")
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    print("Practice form stopped.")


# ---------- plain-language guides ----------
def guide_lookup():
    print("""
ABIYAMO ENROLLEE LOOKUP: what it is
  Problem: to check whether someone is an enrollee you had to search hundreds of monthly Excel files, and the
  files are messy (the header row moves, column names drift, phone numbers lose their leading zero).
  Steps, in order:
    1. Generate synthetic monthly workbooks (practice data; real data never goes in this repo).
    2. Clean + build: finds each file's real header row, tidies names/phones/dates, loads everything into one database.
    3. Web page: type a name and see which monthly file(s) it appears in. Each result has a "Generate code"
       button that makes a unique authorization code (AUTH-YYMM-NNNN-C) and saves it. Re-clicking gives the same code.
    4. Export: all issued codes to an Excel file.
  The benchmark compares re-reading every file per search (the old way) with the indexed database.""")


def guide_forms():
    print("""
FORM-TO-PORTAL PROTOTYPE: what it is
  Problem: paper enrollment forms had to be typed, one by one, into a web portal.
  Idea: photo of form -> AI reads it -> program cleans it -> Chrome extension fills the portal form.
  In this repo (practice version, no real forms or portal):
    - "Parse": turns the sample text (what the AI returned) into clean records, flagging doubtful dates.
    - "Chrome extension": fills a practice form from those records so you can see the idea working.
  Live AI reading needs your own GROQ_API_KEY in a .env file and SYNTHETIC form images. Never use real forms here.""")


def status_lookup() -> str:
    n = len(list(RAW.rglob("*.xls*"))) if RAW.exists() else 0
    codes = 0
    if CODES_DB.exists():
        with closing(sqlite3.connect(CODES_DB)) as con:
            try:
                codes = con.execute("SELECT COUNT(*) FROM authorization_codes").fetchone()[0]
            except sqlite3.OperationalError:
                pass
    return f"practice workbooks: {n} | database: {'ready' if DB.exists() else 'not built yet'} | codes issued: {codes}"


def status_forms() -> str:
    return f"records file: {'ready' if (DATA / 'records.json').exists() else 'not created yet'}"


TOOLS = {
    "1": {"name": "Abiyamo Enrollee Lookup", "status": status_lookup, "items": {
        "1": ("Generate practice (synthetic) monthly workbooks", action_generate),
        "2": ("Clean the workbooks and build the search database", action_pipeline),
        "3": ("Open the web lookup + authorization-code page", action_web),
        "4": ("Export issued authorization codes to Excel", action_export_codes),
        "5": ("Run the speed benchmark", action_benchmark),
        "6": ("How this tool works", guide_lookup)}},
    "2": {"name": "Form-to-Portal Prototype (paper form -> data -> Chrome extension)", "status": status_forms, "items": {
        "1": ("Parse the sample forms into structured records (JSON + Excel)", action_forms),
        "2": ("Try the Chrome extension on the practice form", action_extension),
        "3": ("How this tool works", guide_forms)}},
    "3": {"name": "Developer tools", "status": None, "items": {
        "1": ("Run the full test suite", action_tests),
        "2": ("Pre-push safety check (secrets, real data, private blocklist)", action_prepush)}},
}


def show_help() -> None:
    print("\nWhat each tool is:")
    for key, tool in TOOLS.items():
        print(f"  [{key}] {tool['name']}")
    print("  Tip: open a tool and choose 'How this tool works' for a plain-language explanation.")


def submenu(key: str) -> None:
    tool = TOOLS[key]
    while True:
        print(f"\n--- {tool['name']} ---")
        if tool["status"]:
            print(f"    ({tool['status']()})")
        for k, (label, _) in tool["items"].items():
            print(f"  [{k}] {label}")
        print("  [0] Back")
        try:
            choice = input("\nChoose an option: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice == "0":
            return
        if choice not in tool["items"]:
            print("Please type one of the numbers shown.")
            continue
        safe_run(tool["items"][choice][1])
        pause()


def menu() -> int:
    print("\n=== ODCHC data tools (synthetic-data demo) ===")
    while True:
        print()
        for key, tool in TOOLS.items():
            print(f"  [{key}] {tool['name']}")
        print("  [H] Help: what is each tool?")
        print("  [0] Exit")
        try:
            choice = input("\nChoose a tool: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            choice = "0"
        if choice == "0":
            print("Goodbye.")
            return 0
        if choice == "H":
            show_help()
        elif choice in TOOLS:
            submenu(choice)
        else:
            print("Please type one of the numbers shown.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ODCHC data tools launcher. With no flags, shows the menu.")
    p.add_argument("--pipeline", action="store_true", help="clean workbooks and build the database")
    p.add_argument("--web", action="store_true", help="start the web page")
    p.add_argument("--forms", action="store_true", help="parse the sample enrollment forms")
    p.add_argument("--generate", nargs="?", const=544, type=int, metavar="N", help="generate N synthetic workbooks")
    p.add_argument("--benchmark", action="store_true", help="run the benchmark")
    p.add_argument("--tests", action="store_true", help="run the test suite")
    p.add_argument("--prepush", action="store_true", help="run the pre-push safety check")
    p.add_argument("--export-codes", action="store_true", help="export authorization codes to Excel")
    p.add_argument("--extension", action="store_true", help="serve the practice form and show Chrome extension steps")
    return p


def main(argv=None) -> int:
    os.chdir(ROOT)
    args = build_parser().parse_args(argv)
    steps = []
    if args.generate is not None:
        steps.append(lambda: action_generate(args.generate))
    for flag, fn in [(args.pipeline, action_pipeline), (args.forms, action_forms), (args.benchmark, action_benchmark),
                     (args.tests, action_tests), (args.prepush, action_prepush), (args.export_codes, action_export_codes),
                     (args.extension, action_extension),
                     (args.web, action_web)]:
        if flag:
            steps.append(fn)
    if not steps:
        return menu()
    return 0 if all([safe_run(s) for s in steps]) else 1


if __name__ == "__main__":
    sys.exit(main())
