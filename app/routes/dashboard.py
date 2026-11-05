"""Dashboard: overview statistics."""
from flask import Blueprint, render_template

from ..db import get_db

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    db = get_db()
    one = lambda sql: db.execute(sql).fetchone()[0]
    stats = {
        "total_students": one("SELECT COUNT(*) FROM students"),
        "active_students": one("SELECT COUNT(*) FROM students WHERE status = 'active'"),
        "passes_issued": one("SELECT COUNT(*) FROM passes"),
        "verifications": one("SELECT COUNT(*) FROM verifications"),
    }
    recent = db.execute(
        "SELECT id, full_name, roll_number, program, status, created_at "
        "FROM students ORDER BY id DESC LIMIT 5"
    ).fetchall()
    programs = db.execute(
        "SELECT program, COUNT(*) AS n FROM students GROUP BY program ORDER BY n DESC LIMIT 6"
    ).fetchall()
    return render_template("dashboard.html", stats=stats, recent=recent, programs=programs)
