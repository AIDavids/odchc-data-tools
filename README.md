# ODCHC data tools (synthetic-data reconstruction)

Two small tools I built during my SIWES placement at ODCHC, rebuilt here from scratch on **fully synthetic data** so they can be shown publicly. No real enrollee records, forms, photographs or facility data are in this repository, and none ever will be.

> **Status: prototypes.** Neither tool was approved for general enrollment use. The supervisor's concern was handling of sensitive enrollee information, and I agree with it. See "Limitations".

## Tools at a glance

| Tool | What it is | Where it lives |
|---|---|---|
| **Abiyamo Enrollee Lookup** | Cleans messy monthly facility workbooks, lets you search a name across all of them, and generates authorization codes | `lookup_tool/`, `scripts/` |
| **Form-to-Portal Prototype** | Turns photographed paper forms into clean records and fills a web form with a Chrome extension | `form_prototype/` |
| **Launcher** | One menu to run all of the above | `master.py`, `run_odchc.bat` |

Not in this repo: the ID-card tools (they handle real passport photographs) and anything containing real data.

## 1. Abiyamo Enrollee Lookup (`lookup_tool/`)

**Problem.** Surgery-authorization requests meant checking whether a person's name appeared in hundreds of monthly facility summary workbooks. The files were inconsistent: header rows in different places, drifting column names, mixed date formats.

**What I built.**
1. `cleaning.py` finds the real header row, maps columns to one schema, normalises dates, phones and ages, and writes clean CSVs. Original files are never modified.
2. `db.py` loads everything into SQLite once with an index on an order-insensitive name key.
3. `app.py` is a Flask search page showing which monthly file each match came from.

**Run everything from one place (needs Python 3.10+).**
On Windows, double-click **`run_odchc.bat`**. The first run creates a virtual environment and installs the requirements, then opens a menu:

```
[1] Abiyamo Enrollee Lookup     -> generate practice data, clean + build database, web lookup + codes, export, benchmark
[2] Form-to-Portal Prototype    -> parse sample forms, try the Chrome extension on a practice form
[3] Developer tools             -> run all tests, pre-push safety check
[H] Help: what is each tool?
```
Each tool has a "How this tool works" entry in plain language. First time with the lookup: open tool **[1]**, then choose **1** (generate), **2** (clean + build), **3** (web page). The same actions work as flags, e.g. `python master.py --generate 100 --pipeline --web` (see `python master.py --help`; `--extension` starts the practice form for the Chrome extension). If an action fails, the menu stays open and explains what to do. Errors are logged to `data/master_errors.log`.

Try searching `sample patient alpha` (planted in 3 files).

**Bugs I found in my first version, and fixed:** see [`docs/data_quality_notes.md`](docs/data_quality_notes.md). The most visible one: phone numbers displayed as `8030000001.0` because pandas guessed a number type. Reading every cell as text and restoring the leading zero fixes it, and there is a test for it.

**Benchmark (synthetic, 544 files, ~146k rows):** [`docs/benchmark_results.md`](docs/benchmark_results.md). Re-reading every CSV per search takes about a second on this data, while the indexed database answers in about a millisecond. In other words, the original prototype was probably not slow. The large gain was against *manual* searching of the workbooks one by one, which I did not formally time, so I make no numeric claim about it.

### Authorization-code step (rebuild)
At ODCHC, once a name was found, I copied the details into a second web app that generated an authorization code and saved the code and name to an Excel file. I later merged the two steps. The merged workflow was not finished when my placement ended, and the original code is lost.

This is a **rebuild**. The code format and rules are my illustrative design, **not** the ODCHC format:
- Format `AUTH-YYMM-NNNN-C`: month, a per-month sequence number and a check character that catches any single wrong digit or swapped neighbouring digits (tested exhaustively).
- Concurrency-safe: two people generating codes at the same moment never get the same number (tested with 12 simultaneous requests).
- One code per enrollee: a second click shows the existing code instead of creating a duplicate. This is an assumption of mine, not an ODCHC policy.
- SQLite is the record; **Excel is an export** (`/export`), because several people writing into one live Excel file can overwrite each other.
- `/verify` checks a typed code and shows who it was issued to.

In the search page, each result has a "Requested by" box and a **Generate code** button. There is no login, so "requested by" is self-reported.

## 2. Form-to-portal prototype (`form_prototype/`)

**Problem.** Enrollment data came on paper forms and had to be typed into a web portal.

**Pipeline.** Photographed form, then a vision model (Groq) returns `FIELD: value` text, then `parse_extracted.py` validates and cleans it into JSON/Excel, then a Chrome extension fills the form one record at a time.

- Handwritten dates are the hard part. "14th feb 19th" was once silently read as 2019-02-14. The parser now requires a four-digit year and flags anything uncertain for a human to check.
- The extension only requests the `activeTab` permission, and form field names live in `fieldmap.json`.
- The demo target is a mock form (`mock_form/index.html`), not a real portal.
- **API key:** put `GROQ_API_KEY=...` in a local `.env` file (copy `.env.example`). `.env` is git-ignored and must never be committed.
- **Not verified here:** the live Groq call (`extract_form.py`) and the extension in a browser. The parser is tested; the other two parts are untested in this repository.

**Informal timing.** For 20 forms I timed myself: about 2 hours entering them by hand, about 1 hour with the prototype (including photographing, naming and correcting). This was a self-test with one person on a small sample, not a controlled study. A friend who tried it reported a similar result.

## Limitations (please read)

- The real forms contained sensitive personal data, and sending them to a third-party API is a privacy risk. Any real use needs written approval, a data-protection review and, ideally, an on-premises model.
- Matching is by name, so two people with the same name will both appear. A person must confirm identity.
- The synthetic data copies the *structure* and *mess* of the originals, not their content. Results here say nothing about the real files.

## Also in my SIWES work (not in this repo)
For the ICT team's ID-card programme I wrote the OpenCV logic that detects the card's blue border and crops the passport photograph, and, with a senior colleague who helped substantially, the scripts that located the photographs. The ID-card generation itself was someone else's work. None of this is published because it handles real passport photographs.


## Tests
`python -m pytest` runs 49 tests covering header detection, phone/date/age cleaning, name matching, the end-to-end pipeline, the form parser, the authorization-code step and the launcher (including a locked-database case).

## Credits and licence
Built by Daniel Oluwanifesimi David. Names in the synthetic data are randomly generated; any resemblance to real people is coincidental. MIT licence.
