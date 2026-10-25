import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pre_push_check as ppc  # noqa: E402

GOOD_IGNORE = "\n".join(ppc.REQUIRED_IGNORES) + "\n"


def repo(tmp_path, files, ignore=GOOD_IGNORE):
    (tmp_path / ".gitignore").write_text(ignore)
    made = [tmp_path / ".gitignore"]
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
        made.append(p)
    return ppc.check(tmp_path, made)


def test_clean_repo_passes(tmp_path):
    errors, _ = repo(tmp_path, {"a.py": "print('hi')", "sample_data/x.xlsx": b"PK", "README.md": "hello"})
    assert errors == []


def test_api_key_is_blocked(tmp_path):
    fake = "gs" + "k_" + "A1b2C3d4E5f6G7h8I9j0K1l2"   # built at runtime so this test file is not itself flagged
    errors, _ = repo(tmp_path, {"x.py": f'KEY = "{fake}"'})
    assert any("API key" in e for e in errors)


def test_placeholder_key_is_allowed(tmp_path):
    errors, _ = repo(tmp_path, {".env.example": "GROQ_API_KEY=your-key-here"})
    assert errors == []


def test_hardcoded_password_is_blocked(tmp_path):
    line = "pass" + "word = " + '"' + "SuperSecret" + "12345" + '"'   # built at runtime, see test above
    errors, _ = repo(tmp_path, {"x.py": line})
    assert any("credential" in e for e in errors)


def test_env_file_is_blocked(tmp_path):
    errors, _ = repo(tmp_path, {".env": "A=1"})
    assert any(".env file" in e for e in errors)


def test_real_data_files_outside_allowed_folders_are_blocked(tmp_path):
    errors, _ = repo(tmp_path, {"cleaned/GH Ore April 2020.csv": "a,b", "forms/scan.png": b"x", "x.rar": b"x",
                                "sample_data/ok.xlsx": b"PK", "notes.xlsx": b"PK"})
    flagged = " ".join(errors)
    assert "GH Ore" in flagged and "scan.png" in flagged and "x.rar" in flagged and "notes.xlsx" in flagged
    assert "sample_data/ok.xlsx" not in flagged


def test_images_allowed_only_in_docs_images_with_a_reminder(tmp_path):
    errors, warnings = repo(tmp_path, {"docs/images/search.png": b"x"})
    assert errors == [] and any("SYNTHETIC" in w for w in warnings)


def test_private_blocklist_catches_real_values_but_is_never_published(tmp_path):
    (tmp_path / ".prepush_blocklist.txt").write_text("# real values\nJane Realperson\n08099887766\n")
    errors, _ = repo(tmp_path, {"README.md": "Searched for jane realperson in the files"})
    assert any("blocklist" in e for e in errors)
    errors, _ = ppc.check(tmp_path, [tmp_path / ".gitignore", tmp_path / ".prepush_blocklist.txt"])
    assert any("would be published" in e for e in errors)


def test_missing_gitignore_rules_are_reported(tmp_path):
    errors, _ = repo(tmp_path, {"a.py": "x"}, ignore="venv/\n")
    assert any("'.env'" in e for e in errors) and any("data/" in e for e in errors)


def test_real_looking_phone_warns_but_obviously_fake_ones_do_not(tmp_path):
    _, warnings = repo(tmp_path, {"a.md": "call 08099887766", "b.md": "fake 08030000001 and 08012345678"})
    flagged = " ".join(warnings)
    assert "a.md" in flagged and "b.md" not in flagged


def test_this_repo_itself_passes():
    errors, _ = ppc.check()
    assert errors == [], errors
