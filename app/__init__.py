"""Flask application factory."""
import os

from flask import Flask, g, redirect, request, url_for

from config import Config
from . import auth, db
from .security import init_security


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    if app.config.get("TRUST_PROXY"):
        # Behind nginx/Caddy/a cloud load balancer: trust one hop of X-Forwarded-* so
        # request.remote_addr (login throttle) and https detection are correct.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "photos"), exist_ok=True)

    if not app.config.get("SECRET_KEY_FROM_ENV") and not app.config.get("TESTING"):
        app.logger.warning("SECRET_KEY not set; using a temporary key. Sessions and offline "
                           "QR signatures will not survive a restart. Set it in .env.")

    db.init_app(app)
    init_security(app)
    auth.init_app(app)

    from .routes.dashboard import bp as dashboard_bp
    from .routes.passes import bp as passes_bp
    from .routes.pickup_points import bp as pickup_points_bp
    from .routes.settings import bp as settings_bp
    from .routes.students import bp as students_bp
    from .routes.verify import bp as verify_bp

    # Everything except login, static files and the public verify page needs an admin.
    for bp in (dashboard_bp, students_bp, passes_bp, pickup_points_bp, settings_bp, verify_bp):
        app.register_blueprint(bp)
    app.before_request(_require_login)

    @app.url_defaults
    def static_cache_bust(endpoint, values):
        """Add ?v=<file mtime> to static URLs so browsers never run stale JS/CSS after an update."""
        if endpoint == "static" and "filename" in values and "v" not in values:
            path = os.path.join(app.static_folder, values["filename"])
            if os.path.isfile(path):
                values["v"] = int(os.path.getmtime(path))

    @app.route("/favicon.ico")
    def favicon():
        return redirect(url_for("static", filename="img/favicon.png"), code=301)

    @app.errorhandler(413)
    def too_large(_exc):
        from flask import flash
        flash("That photo is too large to upload (max 25 MB). Please choose a smaller image.", "error")
        return redirect(request.referrer or url_for("students.list_students"))

    @app.context_processor
    def inject_branding():
        return {
            "university_name": app.config["UNIVERSITY_NAME"],
            "university_short": app.config["UNIVERSITY_SHORT"],
        }

    return app


PROTECTED_BLUEPRINTS = {"dashboard", "students", "passes", "pickup_points", "settings"}


def _require_login():
    from flask import abort, current_app
    if request.blueprint not in PROTECTED_BLUEPRINTS:
        return None
    if not current_app.config["REQUIRE_LOGIN"]:
        # No-login mode is for the office PC only: refuse anyone connecting from elsewhere.
        if request.remote_addr not in ("127.0.0.1", "::1"):
            abort(403, description="This app is in single-PC mode. Turn on REQUIRE_LOGIN to allow other computers.")
        return None
    if g.get("user") is None:
        return redirect(url_for("auth.login", next=request.path))
