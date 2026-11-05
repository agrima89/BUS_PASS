"""Production entry point (Windows or Linux): `python serve.py`.

Uses Waitress, a production-grade pure-Python WSGI server. Refuses to start
without real secrets, so a misconfigured deployment fails loudly.
"""
import os
import sys

from waitress import serve

from app import create_app

app = create_app()

if __name__ == "__main__":
    missing = [k for k in ("SECRET_KEY", "QR_SIGNING_KEY") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Refusing to start: set {', '.join(missing)} in .env (see DEPLOY.md).")

    host = os.environ.get("HOST", "127.0.0.1")  # 0.0.0.0 = reachable from the LAN
    if not app.config["REQUIRE_LOGIN"] and host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("Refusing to start: REQUIRE_LOGIN=0 (no login) only works with HOST=127.0.0.1. "
                 "Set REQUIRE_LOGIN=1 and create an admin to allow other computers.")
    port = int(os.environ.get("PORT", 8000))
    threads = int(os.environ.get("WAITRESS_THREADS", 8))
    print(f"Serving on http://{host}:{port}  (public URL in QR codes: {app.config['PUBLIC_BASE_URL']})")
    serve(app, host=host, port=port, threads=threads)
