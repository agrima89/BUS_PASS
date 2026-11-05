"""Pass issuing, card image download, revocation and offline-QR checking (admin only)."""
import io
import secrets
import sqlite3
import string
from datetime import date

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)

from ..db import get_db
from ..services.branding import card_settings
from ..services.buggy_card import CARD_SELECT, card_data
from ..services.card import card_png_bytes
from ..services.sheets import CARDS_PER_SHEET, a4_pdf, a4_sheets, single_card_pdf
from ..services.verification import check_text

bp = Blueprint("passes", __name__, url_prefix="/passes")
_ALPHABET = string.ascii_uppercase + string.digits
MAX_PRINT = 200  # cap per print job (50 A4 pages)


REQUIREMENT_LABELS = {
    "photo": ("photo_path", "photograph"),
    "guardian_name": ("guardian_name", "guardian name"),
    "pickup_point": ("pickup_point_id", "pickup point"),
    "emergency_contact": ("emergency_contact", "emergency contact"),
    "address": ("address", "address"),
    "valid_until": ("valid_until", "valid-until date"),
    "department": ("department", "branch / department"),
    "year_of_study": ("year_of_study", "year of study"),
    "blood_group": ("blood_group", "blood group"),
}


def missing_keys(student):
    """Config keys (e.g. 'pickup_point') of required fields this student hasn't filled."""
    return [k for k in current_app.config["REQUIRED_FOR_PASS"]
            if k in REQUIREMENT_LABELS and not student[REQUIREMENT_LABELS[k][0]]]


def missing_for_pass(student):
    """Human-readable names of required fields that this student hasn't filled."""
    missing = []
    for key in current_app.config["REQUIRED_FOR_PASS"]:
        col, label = REQUIREMENT_LABELS.get(key, (None, None))
        if col and not student[col]:
            missing.append(label)
    return missing


def _pass_code(db):
    prefix = f"{current_app.config['PASS_PREFIX']}-{date.today().year}-"
    if current_app.config["PASS_NUMBER_STYLE"] == "sequential":
        # Numeric max of this year's sequential codes; random codes are ignored.
        row = db.execute(
            "SELECT MAX(CAST(substr(pass_code, ?) AS INTEGER)) FROM passes "
            "WHERE pass_code LIKE ? AND substr(pass_code, ?) GLOB '[0-9][0-9][0-9][0-9][0-9]*'",
            (len(prefix) + 1, prefix + "%", len(prefix) + 1)).fetchone()
        return f"{prefix}{(row[0] or 0) + 1:05d}"
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _get_pass(pass_id):
    row = get_db().execute(CARD_SELECT + "WHERE p.id = ?", (pass_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/")
def list_passes():
    rows = get_db().execute(
        "SELECT p.*, s.full_name, s.roll_number FROM passes p "
        "JOIN students s ON s.id = p.student_id ORDER BY p.id DESC"
    ).fetchall()
    return render_template("passes/list.html", passes=rows)


@bp.route("/issue/<int:student_id>", methods=["POST"])
def issue(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        abort(404)
    if student["status"] != "active":
        flash("Only active students can be issued a pass.", "error")
        return redirect(url_for("students.list_students"))
    if student["valid_until"] and student["valid_until"] < date.today().isoformat():
        flash("Student's 'valid until' date is in the past. Update it first.", "error")
        return redirect(url_for("students.edit", student_id=student_id))

    missing = missing_for_pass(student)
    if missing:
        flash(f"Can't issue a pass yet. Missing: {', '.join(missing)}.", "error")
        return redirect(url_for("students.edit", student_id=student_id))

    pass_id = issue_pass(db, student, request.form.get("qr_mode", "offline"))
    flash("Pass issued with a new unique QR code.", "success")
    return redirect(url_for("passes.detail", pass_id=pass_id))


def issue_pass(db, student, mode="offline"):
    """Create a pass with a fresh QR token, revoking the student's previous pass.

    Every pass gets a new random 192-bit token (online QR) and a new pass code
    (embedded in the offline QR); both columns are UNIQUE in the database, so
    no two QR codes can ever be the same.
    """
    if mode not in ("online", "offline"):
        mode = "offline"
    db.execute("UPDATE passes SET status = 'revoked' WHERE student_id = ? AND status = 'valid'",
               (student["id"],))
    for _ in range(5):  # a collision is practically impossible; retry just in case
        try:
            cur = db.execute(
                "INSERT INTO passes (student_id, pass_code, qr_token, expires_at, qr_mode) "
                "VALUES (?,?,?,?,?)",
                (student["id"], _pass_code(db), secrets.token_urlsafe(24), student["valid_until"], mode))
            db.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Could not generate a unique pass code.")


@bp.route("/<int:pass_id>")
def detail(pass_id):
    p = _get_pass(pass_id)
    verify_url = f"{current_app.config['PUBLIC_BASE_URL']}/verify/{p['qr_token']}"
    return render_template("passes/detail.html", p=p, verify_url=verify_url,
                           c=card_data(p), s=card_settings(), missing=missing_for_pass(p))


@bp.route("/<int:pass_id>/card.png")
def card_image(pass_id):
    p = _get_pass(pass_id)
    png = card_png_bytes(p, p)  # row carries both student and pass columns
    headers = {"Cache-Control": "private, no-store"}
    if request.args.get("download"):
        headers["Content-Disposition"] = f'attachment; filename="{p["pass_code"]}.png"'
    return Response(png, mimetype="image/png", headers=headers)


@bp.route("/<int:pass_id>/revoke", methods=["POST"])
def revoke(pass_id):
    _get_pass(pass_id)
    db = get_db()
    db.execute("UPDATE passes SET status = 'revoked' WHERE id = ?", (pass_id,))
    db.commit()
    flash("Pass revoked. Its QR code will now show as invalid.", "success")
    return redirect(url_for("passes.detail", pass_id=pass_id))


@bp.route("/check-offline", methods=["GET", "POST"])
def check_offline():
    result = check_text(request.form.get("payload", "")) if request.method == "POST" else None
    return render_template("passes/check_offline.html", result=result)


# --- Printing & PDF --------------------------------------------------------------

def _rows_for(ids):
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = get_db().execute(CARD_SELECT + f"WHERE p.id IN ({marks}) AND p.status = 'valid'",
                            ids).fetchall()
    order = {pid: i for i, pid in enumerate(ids)}
    return sorted(rows, key=lambda r: order[r["id"]])


def _parse_ids():
    # Accept ?ids=1&ids=2 (form checkboxes) and ?ids=1,2 (links).
    raw = [part for v in request.values.getlist("ids") for part in v.split(",")]
    ids = []
    for v in raw:
        v = v.strip()
        if v.isdigit() and int(v) not in ids:
            ids.append(int(v))
    return ids[:MAX_PRINT]


def _pdf_response(data, filename):
    disp = "attachment" if request.args.get("download") else "inline"
    return Response(data, mimetype="application/pdf", headers={
        "Content-Disposition": f'{disp}; filename="{filename}"', "Cache-Control": "private, no-store"})


# A4 slots in mm (2 x 2, centred, 6 mm gaps) -- same grid as the classic PDF sheet.
_X0, _Y0, _GAP = 16.4, 20.0, 6.0
A4_SLOTS = [(round(_X0 + c * (85.6 + _GAP), 1), round(_Y0 + r * (54 + _GAP), 1))
            for r in range(2) for c in range(2)]
# Long-edge duplex flips the sheet left<->right, so each back goes in the mirrored column.
A4_SLOTS_MIRRORED = [A4_SLOTS[i ^ 1] for i in range(4)]


def _ensure_complete(rows):
    """Printing needs the same fields as issuing; say which students are incomplete."""
    bad = [f"{r['full_name']} ({', '.join(m)})" for r in rows if (m := missing_for_pass(r))]
    if bad:
        flash("Complete these students before printing: " + "; ".join(bad), "error")
    return not bad


@bp.route("/<int:pass_id>/print")
def print_single(pass_id):
    p = _get_pass(pass_id)
    if p["status"] != "valid":
        flash("Revoked passes can't be printed.", "error")
        return redirect(url_for("passes.detail", pass_id=pass_id))
    if not _ensure_complete([p]):
        return redirect(url_for("passes.detail", pass_id=pass_id))
    return render_template("passes/print_buggy.html", layout="single", cards=[card_data(p)],
                           pass_ids=[p["id"]], s=card_settings())


@bp.route("/<int:pass_id>/print-classic")
def print_classic(pass_id):
    p = _get_pass(pass_id)
    return render_template("passes/print.html", rows=[p], layout="single")


@bp.route("/<int:pass_id>/card.pdf")
def card_pdf(pass_id):
    p = _get_pass(pass_id)
    return _pdf_response(single_card_pdf(p), f"{p['pass_code']}.pdf")


@bp.route("/sheet")
def print_sheet():
    rows = _rows_for(_parse_ids())
    if not rows:
        flash("Select at least one valid pass to print.", "error")
        return redirect(url_for("passes.list_passes"))
    if not _ensure_complete(rows):
        return redirect(url_for("passes.list_passes"))
    cards = [card_data(r) for r in rows]
    mirror = request.args.get("mirror", "1") != "0"
    return render_template(
        "passes/print_buggy.html", layout="a4", cards=cards, s=card_settings(),
        groups=[cards[i:i + CARDS_PER_SHEET] for i in range(0, len(cards), CARDS_PER_SHEET)],
        slots=A4_SLOTS, back_slots=A4_SLOTS_MIRRORED if mirror else A4_SLOTS, mirror=mirror,
        ids=",".join(str(r["id"]) for r in rows))


@bp.route("/sheet-classic")
def print_sheet_classic():
    rows = _rows_for(_parse_ids())
    if not rows:
        flash("Select at least one valid pass to print.", "error")
        return redirect(url_for("passes.list_passes"))
    pages = [rows[i:i + CARDS_PER_SHEET] for i in range(0, len(rows), CARDS_PER_SHEET)]
    return render_template("passes/print.html", pages=pages, layout="a4",
                           ids=",".join(str(r["id"]) for r in rows))


@bp.route("/sheet.pdf")
def sheet_pdf():
    rows = _rows_for(_parse_ids())
    if not rows:
        abort(400, description="No valid passes selected.")
    return _pdf_response(a4_pdf(rows), f"passes-{date.today().isoformat()}.pdf")


# --- Camera scanner ---------------------------------------------------------------

@bp.route("/scan")
def scan():
    return render_template("passes/scan.html")


@bp.route("/api/check", methods=["POST"])
def api_check():
    payload = (request.get_json(silent=True) or {}).get("text", "")
    result = check_text(payload)
    if result.get("student_id"):
        result["photo_url"] = url_for("students.photo", student_id=result.pop("student_id"))
    else:
        result.pop("student_id", None)
    return jsonify(result), 200, {"Cache-Control": "no-store"}


@bp.route("/sheet-page.png")
def sheet_page_png():
    """One A4 page as PNG; the HTML print view shows these so print == PDF."""
    rows = _rows_for(_parse_ids())
    page = request.args.get("page", "0")
    pages = a4_sheets(rows) if rows else []
    if not page.isdigit() or int(page) >= len(pages):
        abort(404)
    buf = io.BytesIO()
    pages[int(page)].save(buf, "PNG", dpi=(300, 300), optimize=True)
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "private, no-store"})
