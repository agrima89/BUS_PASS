"""Public verification page reached by scanning an online QR code.

Shows only what a gate guard needs (name, roll no., program, photo, status).
Email, phone and blood group are never exposed here.
"""
import os
from datetime import date

from flask import Blueprint, abort, render_template, send_file

from ..db import get_db
from ..services.photos import photo_path

bp = Blueprint("verify", __name__, url_prefix="/verify")


def _lookup(token):
    if not token or len(token) > 64:
        return None
    return get_db().execute(
        "SELECT p.id, p.pass_code, p.status, p.expires_at, s.full_name, s.roll_number, "
        "s.program, s.photo_path, s.status AS student_status "
        "FROM passes p JOIN students s ON s.id = p.student_id WHERE p.qr_token = ?", (token,)
    ).fetchone()


def _status(row):
    if row is None:
        return "not_found"
    if row["status"] == "revoked" or row["student_status"] != "active":
        return "revoked"
    if row["expires_at"] and row["expires_at"] < date.today().isoformat():
        return "expired"
    return "valid"


@bp.route("/<token>")
def verify(token):
    row = _lookup(token)
    status = _status(row)
    db = get_db()
    db.execute("INSERT INTO verifications (pass_id, result, method) VALUES (?, ?, 'online')",
               (row["id"] if row else None, status))
    db.commit()
    resp = render_template("verify.html", row=row if status != "not_found" else None,
                           status=status, token=token)
    return resp, (404 if status == "not_found" else 200), {
        "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}


@bp.route("/<token>/photo")
def photo(token):
    row = _lookup(token)
    if _status(row) != "valid":
        abort(404)
    path = photo_path(row["photo_path"]) if row["photo_path"] else None
    if not path or not os.path.isfile(path):
        abort(404)
    resp = send_file(path, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store"
    return resp
