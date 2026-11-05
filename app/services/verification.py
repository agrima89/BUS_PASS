"""Decide whether scanned QR text is a valid pass.

Accepts either an online QR (a URL ending in /verify/<token>) or an offline
signed payload (UPG1.<data>.<sig>). Every check is recorded in `verifications`.
"""
import re
from datetime import date

from flask import current_app

from ..db import get_db
from .qr import is_offline_payload, verify_offline

TOKEN_RE = re.compile(r"/verify/([A-Za-z0-9_-]{16,64})/?$")


def _row_by(column, value):
    return get_db().execute(
        "SELECT p.id, p.pass_code, p.status, p.expires_at, s.id AS student_id, s.full_name, "
        "s.roll_number, s.program, s.photo_path, s.status AS student_status "
        f"FROM passes p JOIN students s ON s.id = p.student_id WHERE p.{column} = ?", (value,)
    ).fetchone()


def _status(row, expires_at):
    if row is not None and (row["status"] == "revoked" or row["student_status"] != "active"):
        return "revoked"
    if expires_at and expires_at < date.today().isoformat():
        return "expired"
    return "valid"


def _log(pass_id, result, method):
    db = get_db()
    db.execute("INSERT INTO verifications (pass_id, result, method) VALUES (?, ?, ?)",
               (pass_id, result, method))
    db.commit()


def check_text(text: str) -> dict:
    """Return {status, method, pass_code, name, roll, program, valid_until, student_id}."""
    text = (text or "").strip()[:4096]

    if is_offline_payload(text):
        data = verify_offline(text, current_app.config["QR_SIGNING_KEY"])
        if not data:
            _log(None, "invalid", "offline")
            return {"status": "invalid", "method": "offline"}
        row = _row_by("pass_code", data["c"])
        status = _status(row, data.get("v"))
        _log(row["id"] if row else None, status, "offline")
        return {"status": status, "method": "offline", "pass_code": data["c"], "name": data["n"],
                "roll": data["r"], "program": data["p"], "valid_until": data.get("v") or None,
                "student_id": row["student_id"] if row and row["photo_path"] else None}

    m = TOKEN_RE.search(text)
    row = _row_by("qr_token", m.group(1)) if m else None
    if row is None:
        _log(None, "not_found", "online")
        return {"status": "not_found", "method": "online"}
    status = _status(row, row["expires_at"])
    _log(row["id"], status, "online")
    return {"status": status, "method": "online", "pass_code": row["pass_code"],
            "name": row["full_name"], "roll": row["roll_number"], "program": row["program"],
            "valid_until": row["expires_at"],
            "student_id": row["student_id"] if row["photo_path"] else None}
