"""Student registration: list, search, create, edit, delete, photo."""
import os
import re
import sqlite3
from datetime import date

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request, send_file,
                   url_for)

from ..db import get_db
from ..services.branding import card_settings
from ..services.buggy_card import dmy
from .passes import REQUIREMENT_LABELS as REQ_COLUMNS, issue_pass, missing_for_pass, missing_keys
from .pickup_points import active_points
from ..services.photos import PhotoError, delete_photo, photo_path, save_photo

bp = Blueprint("students", __name__, url_prefix="/students")

FIELDS = ["roll_number", "full_name", "program", "department", "year_of_study",
          "email", "phone", "blood_group", "valid_until", "status",
          "guardian_relation", "guardian_name", "pickup_point_id", "emergency_contact", "address"]
BLOOD_GROUPS = ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
STATUSES = ["active", "inactive", "suspended"]
RELATIONS = ["S/O", "D/O", "W/O", "C/O"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"[0-9+\-\s]{7,20}")
MAX_LEN = {"roll_number": 40, "full_name": 120, "program": 80, "department": 80, "email": 120,
           "phone": 20, "guardian_name": 120, "emergency_contact": 20, "address": 300}
ADDRESS_MAX_LINES = 4
LABELS = {"roll_number": "UID", "full_name": "Full name", "program": "Class / Program",
          "department": "Branch / Department", "email": "Email", "phone": "Phone",
          "guardian_name": "Guardian name", "emergency_contact": "Emergency contact",
          "address": "Address"}
OPTIONAL = ("department", "email", "phone", "blood_group", "valid_until",
            "guardian_name", "emergency_contact", "address")


def _clean(form, current_point_id=None):
    data = {f: (form.get(f) or "").strip() for f in FIELDS}
    # Normalise line endings and trim each address line.
    address_lines = [line.strip() for line in data["address"].splitlines() if line.strip()]
    data["address"] = "\n".join(address_lines)
    errors = []
    for f, label in (("roll_number", "UID"), ("full_name", "Full name"), ("program", "Class / Program")):
        if not data[f]:
            errors.append(f"{label} is required.")
    for f, n in MAX_LEN.items():
        if len(data[f]) > n:
            errors.append(f"{LABELS[f]} is too long (max {n} characters).")
    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors.append("Email address looks invalid.")
    if data["phone"] and not PHONE_RE.fullmatch(data["phone"]):
        errors.append("Phone number looks invalid.")
    if data["emergency_contact"] and not PHONE_RE.fullmatch(data["emergency_contact"]):
        errors.append("Emergency contact number looks invalid.")
    if len(address_lines) > ADDRESS_MAX_LINES:
        errors.append(f"Address can have at most {ADDRESS_MAX_LINES} lines.")
    if data["blood_group"] not in BLOOD_GROUPS:
        errors.append("Invalid blood group.")
    if data["status"] not in STATUSES:
        data["status"] = "active"
    if data["guardian_relation"] not in RELATIONS:
        data["guardian_relation"] = RELATIONS[0]
    if data["year_of_study"]:
        if not data["year_of_study"].isdigit() or not 1 <= int(data["year_of_study"]) <= 8:
            errors.append("Year of study must be 1–8.")
        else:
            data["year_of_study"] = int(data["year_of_study"])
    else:
        data["year_of_study"] = None

    pid = data["pickup_point_id"]
    if "pickup_point" in form:
        # Free-text entry: reuse a matching stop (any letter case) or add it to the list.
        name = " ".join((form.get("pickup_point") or "").split())
        data["pickup_point_text"] = name
        pid = None
        if len(name) > 80:
            errors.append("Pickup point is too long (max 80 characters).")
        elif name:
            db = get_db()
            row = db.execute("SELECT id FROM pickup_points WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
            if row is None and not errors:
                db.execute("INSERT INTO pickup_points (name) VALUES (?)", (name,))
                db.commit()
                row = db.execute("SELECT id FROM pickup_points WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
            pid = row["id"] if row else None
        data["pickup_point_id"] = pid
    elif pid:
        pid = int(pid) if pid.isdigit() else -1
        # Allowed: any active point, or the (possibly hidden) point the student already has.
        row = get_db().execute("SELECT active FROM pickup_points WHERE id = ?", (pid,)).fetchone()
        if row is None or (not row["active"] and pid != current_point_id):
            errors.append("Choose a pickup point from the list.")
        data["pickup_point_id"] = pid
    else:
        data["pickup_point_id"] = None

    for k in OPTIONAL:
        data[k] = data[k] or None
    if not data["guardian_name"]:
        data["guardian_relation"] = None
    return data, errors


def _form_context(student):
    """Pickup points offered on the form: active ones plus the student's current one."""
    points = [dict(r) for r in active_points()]
    current = student.get("pickup_point_id")
    if current and all(p["id"] != current for p in points):
        row = get_db().execute("SELECT id, name FROM pickup_points WHERE id = ?", (current,)).fetchone()
        if row:
            points.append({"id": row["id"], "name": f"{row['name']} (hidden)"})
    pickup = next((p["name"] for p in points if p["id"] == current), "")
    preview = {
        "pass_code": "Assigned on issue",
        "name": student.get("full_name") or "",
        "relation": student.get("guardian_relation") or RELATIONS[0],
        "guardian": student.get("guardian_name") or "",
        "class_line1": student.get("program") or "",
        "class_line2": student.get("department") or "",
        "uid": student.get("roll_number") or "",
        "pickup": pickup.removesuffix(" (hidden)"),
        "valid": dmy(student.get("valid_until")),
        "emergency": student.get("emergency_contact") or "",
        "address": (student.get("address") or "").splitlines(),
        "photo_url": (url_for("students.photo", student_id=student["id"])
                      if student.get("id") and student.get("photo_path") else None),
        "qr_svg": None,
    }
    has_pass = bool(student.get("id") and get_db().execute(
        "SELECT 1 FROM passes WHERE student_id = ? AND status = 'valid'", (student["id"],)).fetchone())
    # Only flag missing fields on an already-saved record (not on a blank new form).
    missing = []
    if student.get("id") and not has_pass:
        missing = missing_keys(student)
    return {"blood_groups": BLOOD_GROUPS, "statuses": STATUSES, "relations": RELATIONS,
            "pickup_points": points, "preview": preview, "s": card_settings(), "has_pass": has_pass,
            "missing": missing, "missing_labels": [REQ_COLUMNS[k][1] for k in missing]}


def _handle_photo(errors):
    """Return a new stored photo name, or None if no file was uploaded."""
    f = request.files.get("photo")
    if not f or not f.filename:
        return None
    try:
        return save_photo(f)
    except PhotoError as exc:
        errors.append(str(exc))
        return None


def _after_save(student_id):
    """Create the pass + QR automatically once the record is complete.

    Returns the redirect target: the new/current pass page, or the student list
    with a note about what's still missing.
    """
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    current = db.execute("SELECT id FROM passes WHERE student_id = ? AND status = 'valid' "
                         "ORDER BY id DESC LIMIT 1", (student_id,)).fetchone()
    if current:
        # Keep the existing QR; just follow the (possibly changed) validity date.
        db.execute("UPDATE passes SET expires_at = ? WHERE id = ?", (student["valid_until"], current["id"]))
        db.commit()
        return url_for("passes.detail", pass_id=current["id"])
    if not current_app.config["AUTO_ISSUE_PASS"]:
        return url_for("students.list_students")
    missing = missing_for_pass(student)
    expired = student["valid_until"] and student["valid_until"] < date.today().isoformat()
    if student["status"] != "active" or expired:
        return url_for("students.list_students")
    if missing:
        return url_for("students.edit", student_id=student_id)
    pass_id = issue_pass(db, student, request.form.get("qr_mode", "offline"))
    flash("Pass created with a unique QR code. Ready to print.", "success")
    return url_for("passes.detail", pass_id=pass_id)


def _get_or_404(student_id):
    row = get_db().execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/")
def list_students():
    q = request.args.get("q", "").strip()
    sql = ("SELECT s.*, pp.name AS pickup_point, (SELECT p.id FROM passes p WHERE p.student_id = s.id "
           "AND p.status = 'valid' ORDER BY p.id DESC LIMIT 1) AS pass_id "
           "FROM students s LEFT JOIN pickup_points pp ON pp.id = s.pickup_point_id")
    params = ()
    if q:
        sql += (" WHERE s.full_name LIKE ? OR s.roll_number LIKE ? OR s.program LIKE ?"
                " OR pp.name LIKE ?")
        like = f"%{q}%"
        params = (like, like, like, like)
    rows = get_db().execute(sql + " ORDER BY s.id DESC", params).fetchall()
    missing = {r["id"]: missing_for_pass(r) for r in rows}
    return render_template("students/list.html", students=rows, q=q, missing=missing)


@bp.route("/new", methods=["GET", "POST"])
def create():
    student = {}
    if request.method == "POST":
        data, errors = _clean(request.form)
        photo = _handle_photo(errors) if not errors else None
        if not errors:
            try:
                db = get_db()
                cols = ", ".join(FIELDS + ["photo_path"])
                marks = ", ".join("?" for _ in range(len(FIELDS) + 1))
                cur = db.execute(f"INSERT INTO students ({cols}) VALUES ({marks})",
                                 [data[f] for f in FIELDS] + [photo])
                db.commit()
                flash(f"Student {data['full_name']} saved.", "success")
                return redirect(_after_save(cur.lastrowid))
            except sqlite3.IntegrityError:
                errors.append("A student with that UID already exists.")
        if photo:
            delete_photo(photo)  # don't keep orphaned files when the save failed
        for e in errors:
            flash(e, "error")
        student = data
    return render_template("students/form.html", student=student, mode="create",
                           **_form_context(student))


@bp.route("/<int:student_id>/edit", methods=["GET", "POST"])
def edit(student_id):
    student = dict(_get_or_404(student_id))
    if request.method == "POST":
        data, errors = _clean(request.form, current_point_id=student.get("pickup_point_id"))
        photo = _handle_photo(errors) if not errors else None
        old_photo = student.get("photo_path")
        remove = request.form.get("remove_photo") == "1"
        if not errors:
            try:
                db = get_db()
                new_photo = photo or (None if remove else old_photo)
                sets = ", ".join(f"{f} = ?" for f in FIELDS)
                db.execute(f"UPDATE students SET {sets}, photo_path = ?, "
                           "updated_at = datetime('now') WHERE id = ?",
                           [data[f] for f in FIELDS] + [new_photo, student_id])
                db.commit()
                if old_photo and old_photo != new_photo:
                    delete_photo(old_photo)
                flash("Student updated.", "success")
                return redirect(_after_save(student_id))
            except sqlite3.IntegrityError:
                errors.append("A student with that UID already exists.")
        if photo:
            delete_photo(photo)
        for e in errors:
            flash(e, "error")
        student.update(data)
    return render_template("students/form.html", student=student, mode="edit",
                           **_form_context(student))


@bp.route("/<int:student_id>/delete", methods=["POST"])
def delete(student_id):
    student = _get_or_404(student_id)
    db = get_db()
    db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    db.commit()
    delete_photo(student["photo_path"])
    flash(f"Student {student['full_name']} deleted.", "success")
    return redirect(url_for("students.list_students"))


@bp.route("/<int:student_id>/photo")
def photo(student_id):
    student = _get_or_404(student_id)
    path = photo_path(student["photo_path"])
    if not path or not os.path.isfile(path):
        abort(404)
    resp = send_file(path, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
