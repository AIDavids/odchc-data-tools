"""Send a photographed paper form to a vision model and save the raw text.

SECURITY: the key is read from the GROQ_API_KEY environment variable. Never hardcode it.
PRIVACY: real enrollment forms contain personal data. Use synthetic forms only in this repo,
and get written approval before sending real forms to any third-party API.
Status: not tested against the live API in this repository's CI (no key available there).
"""
import argparse
import base64
import os
from pathlib import Path

try:  # loads GROQ_API_KEY from a local .env file (which is git-ignored)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROMPT = ("Read this enrollment form. Return one line per field as 'FIELD: value' using exactly these "
          "fields: SURNAME, FIRST_NAME, DOB, GENDER, PHONE, ADDRESS, OCCUPATION. "
          "Write NULL if a field is blank or illegible. Do not guess.")


def extract(image_path: Path) -> str:
    from groq import Groq  # imported here so --dry-run works without the package
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    resp = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
    return resp.choices[0].message.content


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("images", type=Path, help="folder of synthetic form images")
    ap.add_argument("--out", type=Path, default=Path("form_prototype/sample"))
    a = ap.parse_args()
    if "GROQ_API_KEY" not in os.environ:
        raise SystemExit("Set GROQ_API_KEY first (see .env.example). Or skip this step: sample .txt outputs are included.")
    for img in sorted(a.images.glob("*.png")):
        (a.out / f"{img.stem}.txt").write_text(extract(img), encoding="utf-8")
        print("done", img.name)
