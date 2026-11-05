"""Admin-managed pickup points, so every student uses the same spelling.

A point that students use can't be deleted, only hidden (inactive). Hidden
points stay on existing students but aren't offered for new selections.
"""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("pickup_points", __name__, url_prefix="/pickup-points")
MAX_NAME = 80


def active_points():
    return get_db().execute(
        "SELECT id, name FROM pickup_points WHERE active = 1 ORDER BY name").fetchall()


@bp.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        name = " ".join(request.form.get("name", "").split())  # collapse stray spaces
        if not name:
            flash("Enter a pickup point name.", "error")
        elif len(name) > MAX_NAME:
            flash(f"Name is too long (max {MAX_NAME} characters).", "error")
        else:
            try:
                db.execute("INSERT INTO pickup_points (name) VALUES (?)", (name,))
                db.commit()
                flash(f"Pickup point “{name}” added.", "success")
            except sqlite3.IntegrityError:
                flash("That pickup point already exists.", "error")
        return redirect(url_for("pickup_points.index"))

    points = db.execute(
        "SELECT pp.*, (SELECT COUNT(*) FROM students s WHERE s.pickup_point_id = pp.id) AS used "
        "FROM pickup_points pp ORDER BY pp.active DESC, pp.name").fetchall()
    return render_template("pickup_points.html", points=points)


@bp.route("/<int:point_id>/toggle", methods=["POST"])
def toggle(point_id):
    db = get_db()
    db.execute("UPDATE pickup_points SET active = 1 - active WHERE id = ?", (point_id,))
    db.commit()
    return redirect(url_for("pickup_points.index"))


@bp.route("/<int:point_id>/delete", methods=["POST"])
def delete(point_id):
    db = get_db()
    used = db.execute("SELECT COUNT(*) FROM students WHERE pickup_point_id = ?", (point_id,)).fetchone()[0]
    if used:
        flash("This pickup point is assigned to students. Hide it instead.", "error")
    else:
        db.execute("DELETE FROM pickup_points WHERE id = ?", (point_id,))
        db.commit()
        flash("Pickup point deleted.", "success")
    return redirect(url_for("pickup_points.index"))
