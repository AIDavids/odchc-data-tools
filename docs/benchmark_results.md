# Benchmark: legacy scan vs SQLite index (synthetic data)

Synthetic workbooks sized to mirror the original project (544 monthly files, 145,883 rows).
20 random names searched with each method on this machine.
**Timings depend on hardware and file size. Treat them as indicative, not as a claim about the original ODCHC data.**

| Method | Median | 95th pct | Min | Max |
|---|---|---|---|---|
| Legacy: re-read every CSV per search | 1.22 s | 1.34 s | 1.10 s | 1.44 s |
| SQLite: indexed name key | 0.6 ms | 1.0 ms | 0.2 ms | 4.6 ms |

Speed-up at the median: about **2,140x**. Indexed search never returned fewer matches than the legacy scan: **True**.
One-off cost: loading all files into SQLite (see `scripts/run_pipeline.py`).

Environment: Python 3.12.3, pandas 3.0.2, Linux-6.18.44-fc-v139-x86_64-with-glibc2.39.
