# University Pass Generator

> **Deploying on Netlify?** Use the [`netlify-site/`](netlify-site/) folder (static site + Netlify Functions +
> Supabase). Step-by-step guide: [netlify-site/SETUP.md](netlify-site/SETUP.md).
> The Flask app in this folder stays available for running on a single office PC.

Admin tool for managing students and generating ID/pass cards with QR verification.
**Current status: Phase 3 (feature-complete).** Admin login, student management with photos,
a live card preview, Pillow-rendered ID cards with online or offline QR codes, single-card and
four-per-A4 printing, PDF export, a camera QR scanner, a public verification page, backups and a deployment guide.

**Deploying?** See [DEPLOY.md](DEPLOY.md). Use `python serve.py` (Waitress) in production, never `run.py`.

Branding is placeholder ("Demo University") until official assets are provided.

## Setup on Windows

Open **PowerShell** in the project folder:

```powershell
# 1. Create and activate a virtual environment (skip creation if venv\ exists)
python -m venv venv
.\venv\Scripts\Activate.ps1
# If activation is blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your local config
copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# paste the output as SECRET_KEY in .env, run it again for QR_SIGNING_KEY

# 4. Create your admin account (password is hashed, never stored in plain text)
flask --app run create-admin

# 5. Run
python run.py
```

Open http://127.0.0.1:5000 and sign in. The database (`instance\university_pass.db`) is created
automatically. A Phase 1 database is upgraded in place, and no data is lost.

Using Command Prompt instead? Activate with `venv\Scripts\activate.bat`.

## Using it

1. **Pickup Points**: add the buggy stops students can choose from.
   **Students → Add Student**: fill in the details (including the *Buggy pass details* section) and upload a photo.
   The card preview updates as you type. A pass can be issued only once the fields in `REQUIRED_FOR_PASS` are filled;
   until then the student shows **⚠ Incomplete**.
2. On the Students list, pick **Online QR** or **Offline QR** and click **Issue pass**.
   Issuing again revokes the student's previous pass.
3. The pass page shows the card (true CR80 ID size at 300 DPI) with **Download PNG** and **Revoke**.
4. **Online QR** holds only a link: `PUBLIC_BASE_URL/verify/<random token>`. Scanning it shows the live
   status (valid, expired or revoked). Set `PUBLIC_BASE_URL` to an address phones can reach.
5. **Offline QR** holds a signed payload (`UPG1.…`) with name, roll number, program and expiry.
   It can be checked without contacting the server that issued it, by anything holding the signing key.
6. **Printing**:
   - *Single card*: on a pass, click **Print card** (an 85.6 × 54 mm page for ID-card printers) or **⬇ PDF**.
   - *Four per A4*: on **Issued Passes**, tick passes and click **Print selected** or **⬇ PDF**. Pages
     have crop marks, and more than four passes run onto extra pages.
   - In the browser print dialog, set **Scale 100% / Actual size** and **Margins: None**.
     The print view uses the same images as the PDF, so both come out identical.
7. **Scan QR**: opens the camera and checks online and offline QR codes as soon as they are seen, showing
   the holder's photo for comparison. It needs `https://` or `localhost`. **Check QR Text** is the fallback with no camera.
8. **Backups**: `flask --app run backup` writes a zip with the database and photos to `backups\`.

## Tests

```powershell
python -m pytest -q
```

## Project structure

```
config.py                 Settings from environment / .env (no hardcoded secrets)
run.py                    Development entry point
serve.py                  Production entry point (Waitress); refuses to start without secrets
DEPLOY.md                 This PC / campus LAN / internet deployment, HTTPS, backups, checklist
app/__init__.py           App factory, blueprints, login guard, branding
app/auth.py               Login/logout, brute-force throttle, `create-admin` command
app/db.py                 SQLite connection per request, init-db, in-place migrations
app/schema.sql            Tables: students, passes, verifications, users, pickup_points, settings
app/security.py           CSRF protection + security headers
app/routes/               dashboard, students, passes, pickup_points, settings (admin) · verify (public)
app/services/photos.py    Photo validation and re-encoding (strips EXIF/GPS metadata)
app/services/qr.py        Online verify-URL QR and HMAC-signed offline QR
app/services/card.py      Classic one-sided Pillow card (kept as fallback)
app/services/branding.py  Card wording and logo/seal settings
app/services/buggy_card.py  Pass + student row -> values printed on the buggy pass
app/templates/cards/_buggy.html  Front/back card templates (mm-based)
app/static/css/card.css   Card geometry · app/static/js/cardfit.js  shrink-to-fit + preview scaling
app/services/sheets.py    Single-card and 4-per-A4 layouts with crop marks, PDF export
app/services/verification.py  Shared online/offline QR check used by the scanner and the paste page
app/static/js/preview.js  Live card preview on the student form
app/static/js/scan.js     Camera scanner (built-in BarcodeDetector, or the bundled jsQR)
app/static/vendor/        jsQR 1.4.0 (Apache-2.0), bundled so scanning works offline
app/templates/            Jinja templates
tests/                    pytest suite
instance/, uploads/       Runtime data, git-ignored, never commit
```

## Security notes

- Set `SECRET_KEY` and `QR_SIGNING_KEY` in `.env`. The `.env` file, the database and uploads are git-ignored.
- All admin pages need a login. Passwords are hashed, failed logins are throttled, and sessions are reset on login.
- All forms are CSRF-protected, and all SQL is parameterized.
- Photos are decoded and re-encoded on upload, so metadata and anything hidden in the file are dropped.
  They are served only to signed-in admins, plus on the verify page of a valid pass.
- The public verify page never shows email, phone or blood group.
- Keep `QR_SIGNING_KEY` secret. Anyone who has it can create offline QR codes that pass the check.
  Changing it makes offline QR codes issued earlier fail the check.

## Buggy pass (two-sided)

The card is the two-sided buggy pass (Phase 4, see [PLAN.md](PLAN.md)), built in HTML/CSS at 85.6 × 54 mm.
- **Card Settings** (sidebar): university name, tagline, all labels, return instructions, contact and helpline
  numbers, notes, and the official **logo** and **seal** images. Official text starts blank; enter what the university supplies.
- **Print card** on a pass prints the front and back. **Print selected** on Issued Passes makes A4 duplex sheets
  (backs mirrored so they line up on long-edge duplex). For a PDF, choose *Save as PDF* in the print dialog.
- Print settings: Scale 100%, Margins None, Background graphics on.

## Before going live

- Replace the placeholder branding (`UNIVERSITY_NAME`, `UNIVERSITY_SHORT`) once official assets arrive.
- Decide `PUBLIC_BASE_URL` before printing cards, because it is printed inside every online QR code.
- Work through the checklist at the end of [DEPLOY.md](DEPLOY.md).
