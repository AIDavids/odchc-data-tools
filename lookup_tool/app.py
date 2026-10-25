"""Flask pages: search -> generate authorization code -> verify / export. Synthetic demo."""
import io
import sqlite3
import time
from contextlib import closing

from flask import Flask, Response, render_template_string, request

from . import codegen
from .db import search

STYLE = """<style>body{font-family:Arial,sans-serif;margin:40px}th,td{border:1px solid #ddd;padding:6px 8px;text-align:left}
th{background:#2c3e50;color:#fff}table{border-collapse:collapse;margin:8px 0 24px}.note{color:#666}
.code{font-size:28px;font-weight:bold;letter-spacing:1px}.warn{color:#a15c00}input[type=text]{padding:4px}</style>"""

PAGE = STYLE + """<title>Enrollee Search (synthetic demo)</title>
<h2>Enrollee Search</h2>
<p class="note">Demo on synthetic data only. &middot; <a href="/verify">Verify a code</a> &middot; <a href="/export">Export codes (Excel)</a></p>
<form method="get"><input type="text" name="name" size="36" value="{{ q }}" placeholder="Enter enrollee's name" required>
<select name="mode"><option value="exact" {{ 'selected' if mode=='exact' }}>Exact (any word order)</option>
<option value="partial" {{ 'selected' if mode=='partial' }}>Partial</option></select> <button>Search</button></form>
{% if searched %}<p>{{ total }} match(es) in {{ files|length }} file(s) &middot; {{ ms }} ms</p>
{% for f, rows in files.items() %}<b>Found in: {{ f }}</b>
<table><tr>{% for c in cols %}<th>{{ c }}</th>{% endfor %}<th>Authorization</th></tr>
{% for r in rows %}<tr>{% for c in cols %}<td>{{ r[c] or '' }}</td>{% endfor %}
<td><form method="post" action="/generate">
<input type="hidden" name="orin" value="{{ r['orin'] }}"><input type="hidden" name="client_name" value="{{ r['client_name'] }}">
<input type="hidden" name="source_file" value="{{ r['source_file'] }}">
<input type="text" name="requested_by" size="12" placeholder="Requested by" required> <button>Generate code</button></form></td></tr>{% endfor %}</table>
{% else %}<p>No enrollee found in any file.</p>{% endfor %}{% endif %}"""

RESULT = STYLE + """<h2>Authorization code</h2><p>For: {{ name }}</p><p class="code">{{ code }}</p>
{% if existing %}<p class="warn">This enrollee already had a code. The existing one is shown, and no duplicate was created.</p>
{% else %}<p>Saved. Use <a href="/export">Export codes</a> to get the Excel file.</p>{% endif %}<p><a href="/">Back to search</a></p>"""

VERIFY = STYLE + """<h2>Verify a code</h2><form method="get"><input type="text" name="code" value="{{ code }}" placeholder="AUTH-2610-0001-X">
<button>Check</button></form>{% if code %}<p>{{ 'Valid format and check character.' if ok else 'NOT valid: ' + reason }}</p>
{% if ok %}<p class="{{ '' if issued else 'warn' }}">{{ 'Issued to: ' + issued if issued else 'Well-formed, but not found in the issued list.' }}</p>{% endif %}{% endif %}
<p><a href="/">Back to search</a></p>"""

SHOW = ["serial_no", "client_name", "booking_date", "orin", "place_of_issue",
        "hospital_number", "age", "address", "phone", "client_type", "parity"]


def create_app(db_path: str = "data/enrollees.db", codes_db: str = "data/authorization.db") -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def home():
        q = request.args.get("name", "").strip()
        mode = request.args.get("mode", "exact")
        files, total, ms = {}, 0, 0
        if q:
            t0 = time.perf_counter()
            with closing(sqlite3.connect(db_path)) as con:  # 'with connect()' alone does not close the file
                rows = search(con, q, mode)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            for r in rows:
                files.setdefault(r["source_file"], []).append(r)
            total = len(rows)
        return render_template_string(PAGE, q=q, mode=mode, searched=bool(q), files=files,
                                      total=total, ms=ms, cols=SHOW)

    @app.post("/generate")
    def generate():
        f = request.form
        try:
            with closing(codegen.connect(codes_db)) as con:
                res = codegen.generate_code(con, orin=f.get("orin"), client_name=f.get("client_name"),
                                            source_file=f.get("source_file"), requested_by=f.get("requested_by", ""))
        except ValueError as e:
            return f"Could not generate a code: {e}", 400
        return render_template_string(RESULT, name=f.get("client_name"), code=res["code"],
                                      existing=res["already_issued"])

    @app.get("/verify")
    def verify():
        code = request.args.get("code", "").strip().upper()
        ok, reason, issued = False, "", ""
        if code:
            ok, reason = codegen.verify_code(code)
            if ok:
                with closing(codegen.connect(codes_db)) as con:
                    row = con.execute("SELECT client_name FROM authorization_codes WHERE code = ?", (code,)).fetchone()
                issued = row[0] if row else ""
        return render_template_string(VERIFY, code=code, ok=ok, reason=reason, issued=issued)

    @app.get("/export")
    def export():
        buf = io.BytesIO()
        with closing(codegen.connect(codes_db)) as con:
            codegen.export_excel(con, buf)
        return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=authorization_codes.xlsx"})
    return app


if __name__ == "__main__":
    create_app().run(debug=False)
