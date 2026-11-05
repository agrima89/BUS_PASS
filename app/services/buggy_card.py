"""Turn a joined pass+student row into the values printed on the buggy pass."""
from flask import url_for
from markupsafe import Markup

from .qr import make_qr_svg, payload_for

# Every column the two card faces need (pass + student + pickup point).
CARD_SELECT = (
    "SELECT p.*, s.full_name, s.roll_number, s.program, s.department, s.year_of_study, "
    "s.blood_group, s.photo_path, s.status AS student_status, s.guardian_relation, "
    "s.guardian_name, s.emergency_contact, s.address, s.pickup_point_id, s.valid_until, "
    "pp.name AS pickup_point "
    "FROM passes p JOIN students s ON s.id = p.student_id "
    "LEFT JOIN pickup_points pp ON pp.id = s.pickup_point_id "
)


def dmy(iso):
    """2026-12-31 -> 31-12-2026 (the reference card's date style)."""
    if not iso or len(iso) != 10:
        return iso or ""
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


def card_data(row):
    return {
        "pass_code": row["pass_code"],
        "name": row["full_name"],
        "relation": row["guardian_relation"] or "S/O",
        "guardian": row["guardian_name"] or "",
        "class_line1": row["program"] or "",
        "class_line2": row["department"] or "",
        "uid": row["roll_number"],
        "pickup": row["pickup_point"] or "",
        "valid": dmy(row["expires_at"]),
        "emergency": row["emergency_contact"] or "",
        "address": (row["address"] or "").split("\n"),
        "photo_url": url_for("students.photo", student_id=row["student_id"]) if row["photo_path"] else None,
        "qr_svg": Markup(make_qr_svg(payload_for(row, row))),
    }
