"""SQLite connection handling and initialization."""
import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    """Additive migrations for databases created by earlier phases."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(passes)")}
    if "qr_mode" not in cols:
        conn.execute("ALTER TABLE passes ADD COLUMN qr_mode TEXT NOT NULL DEFAULT 'online'")

    # Phase 4A: buggy-pass registration fields (all nullable, so existing rows stay valid).
    student_cols = {r["name"] for r in conn.execute("PRAGMA table_info(students)")}
    for name, ddl in [
        ("guardian_relation", "TEXT"),
        ("guardian_name", "TEXT"),
        ("pickup_point_id", "INTEGER REFERENCES pickup_points(id) ON DELETE SET NULL"),
        ("emergency_contact", "TEXT"),
        ("address", "TEXT"),
    ]:
        if name not in student_cols:
            conn.execute(f"ALTER TABLE students ADD COLUMN {name} {ddl}")


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create database tables (safe to run repeatedly)."""
    init_db()
    click.echo("Database initialized.")


@click.command("backup")
@with_appcontext
@click.option("--dest", default="backups", show_default=True, help="Folder for the backup zip.")
def backup_command(dest):
    """Back up the database (consistent snapshot) and uploaded photos into one zip."""
    import os
    import zipfile
    from datetime import datetime

    os.makedirs(dest, exist_ok=True)
    out = os.path.join(dest, f"backup-{datetime.now():%Y%m%d-%H%M%S}.zip")
    snapshot = sqlite3.connect(":memory:")
    try:
        get_db().backup(snapshot)  # consistent copy, safe while the app is running
        db_bytes = snapshot.serialize()
    finally:
        snapshot.close()
    uploads = current_app.config["UPLOAD_FOLDER"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("university_pass.db", db_bytes)
        for root, _dirs, files in os.walk(uploads):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join("uploads", os.path.relpath(full, uploads)))
    click.echo(f"Backup written to {out}")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(backup_command)
    # Auto-create tables on startup; CREATE IF NOT EXISTS never drops data.
    with app.app_context():
        init_db()
