"""Admin authentication: login/logout, login_required, create-admin CLI."""
import functools
import time

import click
from flask import (Blueprint, current_app, flash, g, redirect, render_template, request,
                   session, url_for)
from flask.cli import with_appcontext
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

# Simple in-memory brute-force throttle: max attempts per IP per window.
_ATTEMPTS: dict[str, list[float]] = {}
MAX_ATTEMPTS, WINDOW = 5, 300


def _throttled(ip):
    now = time.time()
    recent = [t for t in _ATTEMPTS.get(ip, []) if now - t < WINDOW]
    _ATTEMPTS[ip] = recent
    return len(recent) >= MAX_ATTEMPTS


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _safe_next(target):
    # Only allow relative, same-site redirects.
    return target if target and target.startswith("/") and not target.startswith("//") else None


@bp.before_app_request
def load_user():
    uid = session.get("user_id")
    g.user = None
    if uid is not None:
        g.user = get_db().execute("SELECT id, username FROM users WHERE id = ?", (uid,)).fetchone()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _throttled(ip):
            flash("Too many failed attempts. Try again in a few minutes.", "error")
            return render_template("login.html"), 429
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            _ATTEMPTS.pop(ip, None)
            token = session.get("_csrf")
            session.clear()  # prevent session fixation
            if token:
                session["_csrf"] = token
            session["user_id"] = user["id"]
            return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))
        _ATTEMPTS.setdefault(ip, []).append(time.time())
        flash("Invalid username or password.", "error")
    no_users = get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    return render_template("login.html", no_users=no_users)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def create_user(username, password):
    db = get_db()
    db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
               (username, generate_password_hash(password)))
    db.commit()


@click.command("create-admin")
@with_appcontext
@click.option("--username", prompt=True)
@click.password_option()
def create_admin_command(username, password):
    """Create an admin account (password is hashed, never stored in plain text)."""
    if len(password) < 8:
        raise click.BadParameter("Password must be at least 8 characters.")
    try:
        create_user(username.strip(), password)
    except Exception as exc:  # e.g. duplicate username
        raise click.ClickException(f"Could not create user: {exc}")
    click.echo(f"Admin '{username}' created.")


def init_app(app):
    app.register_blueprint(bp)
    app.cli.add_command(create_admin_command)
