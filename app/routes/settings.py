"""Admin Settings: card wording and official logo/seal uploads."""
import os

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for

from ..services.branding import (ASSETS, FIELDS, asset_path, card_settings, remove_asset,
                                 save_asset, save_settings)

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        errors = save_settings(request.form)
        for e in errors:
            flash(e, "error")
        if not errors:
            flash("Card settings saved.", "success")
            return redirect(url_for("settings.index"))
    return render_template("settings.html", s=card_settings(), fields=FIELDS, form=request.form)


@bp.route("/asset/<kind>", methods=["POST"])
def upload_asset(kind):
    if kind not in ASSETS:
        abort(404)
    if request.form.get("remove") == "1":
        remove_asset(kind)
        flash(f"{kind.capitalize()} removed.", "success")
    else:
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Choose an image file first.", "error")
        else:
            try:
                save_asset(kind, f)
                flash(f"{kind.capitalize()} uploaded.", "success")
            except ValueError as exc:
                flash(str(exc), "error")
    return redirect(url_for("settings.index"))


@bp.route("/asset/<kind>.png")
def asset(kind):
    if kind not in ASSETS:
        abort(404)
    path = asset_path(kind)
    if not path or not os.path.isfile(path):
        abort(404)
    resp = send_file(path, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
