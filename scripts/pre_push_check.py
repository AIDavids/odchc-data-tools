"""Pre-push safety check. Run from the repo folder before every commit/push:

    python scripts/pre_push_check.py

It looks at exactly what Git would publish (or, without Git, the folder minus ignored items) and blocks on:
  - API keys / tokens / passwords in any text file,
  - an .env file that is not ignored,
  - data-like files (Excel, CSV, databases, archives, PDFs, images) outside the few allowed folders,
  - anything listed in your private blocklist (.prepush_blocklist.txt, never published),
  - a .gitignore that is missing the essential rules.
It WARNS about Nigerian-looking phone numbers in text files.
Exit code 0 = safe to continue, 1 = fix the listed problems first.

Private blocklist: create a file named .prepush_blocklist.txt (it is git-ignored) with one real value per line,
e.g. a real enrollee's name or phone number you have seen. Any match anywhere in the repo is a blocking error.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {".git", "data", "venv", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
TEXT_EXT = {".py", ".md", ".txt", ".json", ".csv", ".bat", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".html", ".js",
            ".css", ".example", ".gitignore", ".sh", ""}
DATA_EXT = {".xlsx", ".xls", ".xlsm", ".csv", ".db", ".sqlite", ".rar", ".zip", ".7z", ".pdf", ".docx",
            ".png", ".jpg", ".jpeg", ".gif", ".webp"}
# (folder prefix, extensions allowed there)
ALLOWED_DATA = [("sample_data/", {".xlsx"}), ("docs/images/", {".png", ".jpg", ".jpeg", ".gif", ".webp"}),
                ("docs/", {".csv"})]
REQUIRED_IGNORES = [".env", "data/", "venv/", "*.db", "*.rar", "*.zip", "__pycache__/", ".prepush_blocklist.txt"]
MAX_MB = 5

SECRET_PATTERNS = [
    (re.compile(r"gsk_[A-Za-z0-9]{16,}"), "Groq-style API key"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "secret key (sk-...)"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|passw(?:or)?d)\b\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]"),
     "hard-coded credential"),
]
PLACEHOLDERS = ("your-key-here", "changeme", "example", "xxxx", "placeholder")
PHONE = re.compile(r"\b0[789][01]\d{8}\b|\b[789][01]\d{8}\b")


def publishable_files() -> list[Path]:
    """Files Git would publish; falls back to a folder walk (minus ignored folders) without Git."""
    try:
        if (ROOT / ".git").exists():
            tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
            others = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout
            names = {n for n in (tracked + "\n" + others).splitlines() if n.strip()}
            return sorted(ROOT / n for n in names if (ROOT / n).is_file())
    except (OSError, subprocess.CalledProcessError):
        pass
    files = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if p.is_file() and not (set(rel.parts[:-1]) & SKIP_DIRS):
            files.append(p)
    return sorted(files)


def is_text(p: Path) -> bool:
    return p.suffix.lower() in TEXT_EXT or p.name in {".gitignore", ".env.example", "LICENSE"}


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def check(root: Path = ROOT, files: list[Path] | None = None) -> tuple[list[str], list[str]]:
    files = publishable_files() if files is None else files
    errors, warnings = [], []

    gi = (root / ".gitignore")
    ignore_text = read(gi) if gi.exists() else ""
    for rule in REQUIRED_IGNORES:
        if rule not in ignore_text:
            errors.append(f".gitignore is missing the rule '{rule}'")

    blocklist = []
    bl = root / ".prepush_blocklist.txt"
    if bl.exists():
        blocklist = [ln.strip().lower() for ln in read(bl).splitlines() if ln.strip() and not ln.startswith("#")]

    for p in files:
        rel = p.relative_to(root).as_posix()
        if rel == ".prepush_blocklist.txt":
            errors.append("'.prepush_blocklist.txt' would be published. Add it to .gitignore.")
            continue
        if p.name == ".env":
            errors.append(f"{rel}: an .env file would be published")
        if p.stat().st_size > MAX_MB * 1024 * 1024:
            errors.append(f"{rel}: larger than {MAX_MB} MB, is it real data?")
        ext = p.suffix.lower()
        if ext in DATA_EXT:
            allowed = any(rel.startswith(prefix) and ext in exts for prefix, exts in ALLOWED_DATA)
            if not allowed:
                errors.append(f"{rel}: data-like file outside the allowed folders. Real data must never be published.")
            elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                warnings.append(f"{rel}: image. Confirm by eye that it shows SYNTHETIC data only.")
        if blocklist:
            hay = (rel + "\n" + (read(p) if is_text(p) else "")).lower()
            for item in blocklist:
                if item in hay:
                    errors.append(f"{rel}: contains a value from your private blocklist")
        if not is_text(p):
            continue
        text = read(p)
        for pattern, label in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                value = m.group(0).lower()
                if any(ph in value for ph in PLACEHOLDERS):
                    continue
                errors.append(f"{rel}: looks like a {label}")
                break
        if any(not re.search(r"0000|12345678", m.group(0)) for m in PHONE.finditer(text)):
            warnings.append(f"{rel}: contains a phone-like number. Make sure it is invented, not a real person's.")
    return errors, warnings


def main() -> int:
    errors, warnings = check()
    print(f"Checked {len(publishable_files())} file(s) that Git would publish.\n")
    for w in warnings:
        print(f"  WARNING  {w}")
    for e in errors:
        print(f"  BLOCKED  {e}")
    if errors:
        print(f"\n{len(errors)} problem(s) found. Fix them before you push.")
        return 1
    print("\nNo blocking problems found." + (" Review the warnings above." if warnings else ""))
    print("Manual checks still needed: screenshots show synthetic names only, and your supervisor has agreed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
