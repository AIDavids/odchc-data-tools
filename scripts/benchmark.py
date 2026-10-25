"""Compare the original approach (re-read every CSV on every search) with the SQLite index."""
import argparse
import platform
import random
import sqlite3
import statistics as st
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lookup_tool.db import search


def legacy_search(csv_dir: Path, name: str) -> int:
    """What the original webapp did: read every CSV with pandas defaults, exact-match the name."""
    hits = 0
    for p in csv_dir.glob("*.csv"):
        df = pd.read_csv(p)
        if "client_name" in df.columns:
            hits += int((df["client_name"].astype(str).str.strip().str.lower() == name.strip().lower()).sum())
    return hits


def stats(xs):
    xs = sorted(xs)
    return {"median": st.median(xs), "p95": xs[int(0.95 * (len(xs) - 1))], "min": xs[0], "max": xs[-1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", default="data/clean_csv")
    ap.add_argument("--db", default="data/enrollees.db")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="docs/benchmark_results.md")
    a = ap.parse_args()
    csv_dir = Path(a.csv_dir)
    con = sqlite3.connect(a.db)
    total_rows = con.execute("SELECT COUNT(*) FROM enrollees").fetchone()[0]
    n_files = len(list(csv_dir.glob("*.csv")))
    names = [r[0] for r in con.execute("SELECT client_name FROM enrollees").fetchall()]
    sample = random.Random(a.seed).sample(names, a.n)

    t_old, t_new, ok = [], [], True
    for name in sample:
        t0 = time.perf_counter(); old = legacy_search(csv_dir, name); t_old.append(time.perf_counter() - t0)
        t0 = time.perf_counter(); new = len(search(con, name)); t_new.append(time.perf_counter() - t0)
        ok &= new >= old  # indexed search is order-insensitive so it may find more, never fewer
    con.close()
    so, sn = stats(t_old), stats(t_new)
    md = f"""# Benchmark: legacy scan vs SQLite index (synthetic data)

Synthetic workbooks sized to mirror the original project ({n_files} monthly files, {total_rows:,} rows).
{a.n} random names searched with each method on this machine.
**Timings depend on hardware and file size. Treat them as indicative, not as a claim about the original ODCHC data.**

| Method | Median | 95th pct | Min | Max |
|---|---|---|---|---|
| Legacy: re-read every CSV per search | {so['median']:.2f} s | {so['p95']:.2f} s | {so['min']:.2f} s | {so['max']:.2f} s |
| SQLite: indexed name key | {sn['median']*1000:.1f} ms | {sn['p95']*1000:.1f} ms | {sn['min']*1000:.1f} ms | {sn['max']*1000:.1f} ms |

Speed-up at the median: about **{so['median']/sn['median']:,.0f}x**. Indexed search never returned fewer matches than the legacy scan: **{ok}**.
One-off cost: loading all files into SQLite (see `scripts/run_pipeline.py`).

Environment: Python {platform.python_version()}, pandas {pd.__version__}, {platform.platform()}.
"""
    Path(a.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
