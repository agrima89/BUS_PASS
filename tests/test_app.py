import io
import re

import pytest
from PIL import Image

from app import create_app
from app.auth import create_user
from app.services.qr import offline_payload, verify_offline
from config import TestConfig


@pytest.fixture
def app(tmp_path):
    class Cfg(TestConfig):
        DATABASE = str(tmp_path / "test.db")
        UPLOAD_FOLDER = str(tmp_path / "uploads")
    app = create_app(Cfg)
    with app.app_context():
        create_user("admin", "correct-horse-battery")
    return app


def csrf(client, url):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def client(app):
    c = app.test_client()
    tok = csrf(c, "/login")
    r = c.post("/login", data={"csrf_token": tok, "username": "admin", "password": "correct-horse-battery"})
    assert r.status_code == 302
    return c


def image_file(size=(400, 500), fmt="PNG", name="p.png"):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 120, 90)).save(buf, fmt)
    buf.seek(0)
    return buf, name


def add_student(client, **extra):
    tok = csrf(client, "/students/new")
    data = {"csrf_token": tok, "full_name": "Test Student", "roll_number": "T-001",
            "program": "B.Sc", "status": "active", "valid_until": "2099-06-30"}
    data.update(extra)
    return client.post("/students/new", data=data, content_type="multipart/form-data",
                       follow_redirects=True)


# --- Auth -------------------------------------------------------------------

def test_admin_pages_require_login(anon):
    for url in ("/", "/students/", "/passes/", "/students/new"):
        r = anon.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_wrong_password_rejected(anon):
    tok = csrf(anon, "/login")
    r = anon.post("/login", data={"csrf_token": tok, "username": "admin", "password": "nope"})
    assert b"Invalid username or password" in r.data


def test_open_redirect_blocked(anon):
    tok = csrf(anon, "/login")
    r = anon.post("/login?next=//evil.com", data={"csrf_token": tok, "username": "admin",
                                                    "password": "correct-horse-battery"})
    assert r.headers["Location"] == "/"


# --- Phase 1 behaviour ----------------------------------------------------------

def test_dashboard_loads(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Total Students" in r.data


def test_create_edit_delete_student(client):
    assert b"Test Student" in add_student(client).data
    tok = csrf(client, "/students/new")
    r = client.post("/students/new", data={"csrf_token": tok, "full_name": "X",
                    "roll_number": "T-001", "program": "B.Sc"})
    assert b"already exists" in r.data
    r = client.post("/students/1/edit", data={"csrf_token": tok, "full_name": "Renamed",
                    "roll_number": "T-001", "program": "B.Sc", "status": "inactive"},
                    follow_redirects=True)
    assert b"Renamed" in r.data
    assert b"Renamed" in client.get("/students/?q=Ren").data
    r = client.post("/students/1/delete", data={"csrf_token": tok}, follow_redirects=True)
    assert b"No students yet" in r.data


def test_csrf_required(client):
    r = client.post("/students/new", data={"full_name": "A", "roll_number": "1", "program": "P"})
    assert r.status_code == 400


def test_validation(client):
    tok = csrf(client, "/students/new")
    r = client.post("/students/new", data={"csrf_token": tok, "full_name": "",
                    "roll_number": "", "program": "", "email": "bad"})
    assert b"Full name is required" in r.data and b"Email address looks invalid" in r.data


# --- Photos ---------------------------------------------------------------------

def test_photo_upload_normalised(client, app):
    add_student(client, photo=image_file())
    r = client.get("/students/1/photo")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert Image.open(io.BytesIO(r.data)).size == (600, 800)


def test_fake_image_rejected(client):
    r = add_student(client, photo=(io.BytesIO(b"<?php echo 1; ?>"), "evil.png"))
    assert b"not a valid image" in r.data


def test_photo_requires_login(client, anon):
    add_student(client, photo=image_file())
    assert anon.get("/students/1/photo").status_code == 302


# --- Passes, card rendering, QR -------------------------------------------------------

def issue(client, mode="online"):
    tok = csrf(client, "/students/")
    return client.post("/passes/issue/1", data={"csrf_token": tok, "qr_mode": mode})


def test_issue_pass_and_render_card(client):
    add_student(client, photo=image_file())
    r = issue(client)
    assert r.status_code == 302
    r = client.get("/passes/1/card.png")
    assert r.mimetype == "image/png"
    img = Image.open(io.BytesIO(r.data))
    assert img.size == (1011, 638)


def test_online_verify_flow(client, anon, app):
    add_student(client)
    issue(client)
    with app.app_context():
        from app.db import get_db
        token = get_db().execute("SELECT qr_token FROM passes WHERE id = 1").fetchone()[0]
    r = anon.get(f"/verify/{token}")
    assert r.status_code == 200 and b"VALID PASS" in r.data
    assert b"Test Student" in r.data
    # Revoke -> invalid
    tok = csrf(client, "/passes/1")
    client.post("/passes/1/revoke", data={"csrf_token": tok})
    assert b"PASS NOT VALID" in anon.get(f"/verify/{token}").data
    assert anon.get("/verify/does-not-exist").status_code == 404


def test_reissue_revokes_previous(client):
    add_student(client)
    issue(client)
    issue(client, "offline")
    html = client.get("/passes/").get_data(as_text=True)
    assert html.count("badge-revoked") == 1 and html.count("badge-valid") == 1


def test_offline_payload_signed(app):
    with app.app_context():
        student = {"full_name": "Ana", "roll_number": "R1", "program": "BA"}
        p = {"pass_code": "DU-2026-ABC123", "expires_at": "2099-01-01"}
        payload = offline_payload(student, p)
        key = app.config["QR_SIGNING_KEY"]
        assert verify_offline(payload, key)["n"] == "Ana"
        assert verify_offline(payload.replace("Name: Ana", "Name: Bob"), key) is None
        assert "Name: Ana" in payload and "Sig: " in payload           # readable by any phone
        assert verify_offline(payload, "other-key") is None


def test_inactive_student_cannot_get_pass(client):
    add_student(client, status="inactive")
    issue(client)
    assert b"No passes yet" in client.get("/passes/").data


# --- Phase 3: printing, PDF, scanner API, backup ------------------------------------

def make_passes(client, n):
    for i in range(1, n + 1):
        add_student(client, roll_number=f"R-{i:03d}", full_name=f"Student {i}")
        tok = csrf(client, "/students/")
        client.post(f"/passes/issue/{i}", data={"csrf_token": tok, "qr_mode": "online"})


def pdf_pages(data):
    return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def test_single_card_pdf(client):
    make_passes(client, 1)
    r = client.get("/passes/1/card.pdf?download=1")
    assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert "attachment" in r.headers["Content-Disposition"]
    assert pdf_pages(r.data) == 1
    # page is exactly 85.6 x 54 mm (in PDF points: mm / 25.4 * 72)
    box = re.search(rb"/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)", r.data)
    assert abs(float(box.group(1)) - 242.65) < 1 and abs(float(box.group(2)) - 153.07) < 1


def test_a4_sheet_pdf_paginates(client):
    make_passes(client, 5)
    r = client.get("/passes/sheet.pdf?ids=1,2,3,4,5")
    assert r.data.startswith(b"%PDF") and pdf_pages(r.data) == 2
    box = re.search(rb"/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)", r.data)
    assert abs(float(box.group(1)) - 595.3) < 1 and abs(float(box.group(2)) - 841.9) < 1  # A4


def test_print_pages_and_a4_png(client):
    make_passes(client, 2)
    assert b"85.6" in client.get("/passes/1/print").data
    r = client.get("/passes/sheet-classic?ids=1&ids=2")
    assert r.status_code == 200 and b"sheet-page.png" in r.data
    img = Image.open(io.BytesIO(client.get("/passes/sheet-page.png?ids=1,2&page=0").data))
    assert img.size == (2480, 3508)
    assert client.get("/passes/sheet-page.png?ids=1,2&page=1").status_code == 404


def test_revoked_passes_not_printed(client):
    make_passes(client, 1)
    tok = csrf(client, "/passes/1")
    client.post("/passes/1/revoke", data={"csrf_token": tok})
    r = client.get("/passes/sheet?ids=1", follow_redirects=True)
    assert b"Select at least one valid pass" in r.data
    assert client.get("/passes/sheet.pdf?ids=1").status_code == 400


def api(client, text, token=None):
    tok = token if token is not None else csrf(client, "/passes/scan")
    return client.post("/passes/api/check", json={"text": text}, headers={"X-CSRF-Token": tok})


def test_scan_api_online_and_offline(client, app):
    make_passes(client, 1)
    with app.app_context():
        from app.db import get_db
        p = get_db().execute("SELECT p.*, s.full_name, s.roll_number, s.program FROM passes p "
                             "JOIN students s ON s.id = p.student_id WHERE p.id = 1").fetchone()
        offline = offline_payload(p, p)
    r = api(client, f"http://any-host/verify/{p['qr_token']}").get_json()
    assert r["status"] == "valid" and r["name"] == "Student 1" and r["method"] == "online"
    assert "email" not in r and "phone" not in r
    assert api(client, offline).get_json()["status"] == "valid"
    assert api(client, offline[:-3] + "AAA").get_json()["status"] == "invalid"
    assert api(client, "hello world").get_json()["status"] == "not_found"
    tok = csrf(client, "/passes/1")
    client.post("/passes/1/revoke", data={"csrf_token": tok})
    assert api(client, offline).get_json()["status"] == "revoked"


def test_scan_api_protected(client, anon):
    assert api(client, "x", token="wrong").status_code == 400          # CSRF
    assert anon.post("/passes/api/check", json={"text": "x"}).status_code in (302, 400)
    assert anon.get("/passes/scan").status_code == 302                  # login


def test_backup_command(app, tmp_path):
    import zipfile
    dest = tmp_path / "bk"
    result = app.test_cli_runner().invoke(args=["backup", "--dest", str(dest)])
    assert result.exit_code == 0, result.output
    z = zipfile.ZipFile(next(dest.glob("*.zip")))
    assert "university_pass.db" in z.namelist()


# --- Phase 4A: buggy-pass registration ---------------------------------------------

PRIVATE = {"guardian_name": "Private Guardian Zq", "emergency_contact": "+91 99999 00011",
           "address": "Line One Xq\nLine Two Xq"}


def add_point(client, name):
    tok = csrf(client, "/pickup-points/")
    return client.post("/pickup-points/", data={"csrf_token": tok, "name": name}, follow_redirects=True)


def test_migrates_phase1_database(tmp_path):
    import sqlite3
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.executescript("""
        CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, roll_number TEXT NOT NULL UNIQUE,
          full_name TEXT NOT NULL, program TEXT NOT NULL, department TEXT, year_of_study INTEGER,
          email TEXT, phone TEXT, blood_group TEXT, valid_until TEXT, photo_path TEXT,
          status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO students (roll_number, full_name, program) VALUES ('OLD-1', 'Old Student', 'BA');
    """)
    old.commit(); old.close()

    class Cfg(TestConfig):
        DATABASE = str(db_path)
        UPLOAD_FOLDER = str(tmp_path / "uploads")
    create_app(Cfg)
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(students)")}
    assert {"guardian_relation", "guardian_name", "pickup_point_id", "emergency_contact", "address"} <= cols
    assert {r[1] for r in conn.execute("PRAGMA table_info(passes)")} >= {"qr_mode"}
    assert conn.execute("SELECT full_name FROM students").fetchone()[0] == "Old Student"
    create_app(Cfg)  # running the migration twice is harmless
    conn.close()


def test_pickup_points_manage(client):
    assert "Main Gate".encode() in add_point(client, "  Main   Gate ").data      # spaces tidied
    assert b"already exists" in add_point(client, "main gate").data            # case-insensitive
    add_student(client, pickup_point_id="1")
    tok = csrf(client, "/pickup-points/")
    r = client.post("/pickup-points/1/delete", data={"csrf_token": tok}, follow_redirects=True)
    assert b"Hide it instead" in r.data
    client.post("/pickup-points/1/toggle", data={"csrf_token": tok})
    assert b"hidden" in client.get("/pickup-points/").data
    assert client.get("/pickup-points/", follow_redirects=False).status_code == 200


def test_pickup_points_require_login(anon):
    assert anon.get("/pickup-points/").status_code == 302


def test_student_buggy_fields_saved(client):
    add_point(client, "Library Stop")
    r = add_student(client, guardian_relation="D/O", pickup_point_id="1", **PRIVATE)
    assert b"Test Student" in r.data and b"Library Stop" in r.data
    html = client.get("/students/1/edit").get_data(as_text=True)
    assert 'value="D/O" selected' in html and "Private Guardian Zq" in html and "Line Two Xq" in html


def test_buggy_field_validation(client):
    add_point(client, "Gate 2")
    r = add_student(client, emergency_contact="call me", address="a\nb\nc\nd\ne",
                    guardian_name="x" * 121, pickup_point_id="999")
    for msg in (b"Emergency contact number looks invalid", b"at most 4 lines",
                b"Guardian name is too long", b"Choose a pickup point from the list"):
        assert msg in r.data
    # hidden point: rejected for new students, kept for a student who already has it
    add_student(client, pickup_point_id="1")
    tok = csrf(client, "/pickup-points/")
    client.post("/pickup-points/1/toggle", data={"csrf_token": tok})
    r = add_student(client, roll_number="T-002", pickup_point_id="1")
    assert b"Choose a pickup point from the list" in r.data
    r = client.post("/students/1/edit", data={"csrf_token": tok, "full_name": "Test Student",
                    "roll_number": "T-001", "program": "B.Sc", "pickup_point_id": "1"},
                    follow_redirects=True)
    assert b"Student updated" in r.data


def test_required_fields_block_pass(app, client):
    app.config["REQUIRED_FOR_PASS"] = ("photo", "guardian_name", "pickup_point")
    add_student(client)
    r = client.post("/passes/issue/1", data={"csrf_token": csrf(client, "/students/")},
                    follow_redirects=True)
    assert b"Missing: photograph, guardian name, pickup point" in r.data
    assert b"Incomplete (3)" in client.get("/students/").data
    add_point(client, "North Stop")
    tok = csrf(client, "/students/1/edit")
    client.post("/students/1/edit", data={"csrf_token": tok, "full_name": "Test Student",
                "roll_number": "T-001", "program": "B.Sc", "status": "active",
                "guardian_name": "G", "pickup_point_id": "1", "photo": image_file()},
                content_type="multipart/form-data")
    r = client.post("/passes/issue/1", data={"csrf_token": tok})
    assert r.status_code == 302 and "/passes/1" in r.headers["Location"]


def test_sequential_pass_numbers(app, client):
    app.config["PASS_NUMBER_STYLE"] = "sequential"
    make_passes(client, 3)
    from datetime import date
    codes = re.findall(r"DU-\d{4}-\d{5}", client.get("/passes/").get_data(as_text=True))
    y = date.today().year
    assert set(codes) == {f"DU-{y}-00001", f"DU-{y}-00002", f"DU-{y}-00003"}


def test_private_fields_never_public(client, anon, app):
    add_point(client, "East Stop")
    add_student(client, pickup_point_id="1", **PRIVATE)
    issue(client, "online")
    issue(client, "offline")  # pass 2 (offline) replaces pass 1
    with app.app_context():
        from app.db import get_db
        db = get_db()
        token1 = db.execute("SELECT qr_token FROM passes WHERE id = 1").fetchone()[0]
        p = db.execute("SELECT p.*, s.full_name, s.roll_number, s.program FROM passes p "
                       "JOIN students s ON s.id = p.student_id WHERE p.id = 2").fetchone()
        token2, offline = p["qr_token"], offline_payload(p, p)
        db.execute("UPDATE passes SET status = 'valid' WHERE id = 1")
        db.commit()
    decoded = offline  # readable text; must not contain private fields
    outputs = [anon.get(f"/verify/{token1}").get_data(as_text=True),
               anon.get(f"/verify/{token2}").get_data(as_text=True),
               api(client, f"/verify/{token1}").get_data(as_text=True),
               api(client, offline).get_data(as_text=True),
               decoded]
    for out in outputs:
        for secret in ("Private Guardian Zq", "99999", "Xq"):
            assert secret not in out, (secret, out[:200])


# --- Phase 4B: two-sided HTML buggy pass ------------------------------------------------

def complete_student(client, **extra):
    if b"Gate X" not in client.get("/pickup-points/").data:
        add_point(client, "Gate X")
    data = dict(guardian_relation="D/O", pickup_point_id="1", **PRIVATE)
    data.update(extra)
    return add_student(client, photo=image_file(), **data)


def test_settings_defaults_blank_official_text(client):
    html = client.get("/settings/").get_data(as_text=True)
    assert 'name="card_title" maxlength="40" value="Buggy Pass No."' in html
    for key in ("return_text", "note_lines"):
        assert re.search(rf'<textarea name="{key}"[^>]*></textarea>', html)
    for key in ("contact_value", "helpline_value"):
        assert f'name="{key}" maxlength="40" value=""' in html


def test_settings_save_and_render_on_card(client):
    tok = csrf(client, "/settings/")
    form = {"csrf_token": tok, "uni_name": "Example Institute", "card_title": "Pass No.",
            "return_text": "Return to Office A\n  Building 2  ", "helpline_value": "000-TEST",
            "helpline_label": "Helpline:", "note_lines": "Carry this pass", "qr_caption": "Scan me",
            "label_name": "Name:", "label_class": "Class/Branch:", "label_uid": "UID:",
            "label_pickup": "Pickup Point:", "label_valid": "Valid Upto :",
            "label_emergency": "Emergency Contact No.", "label_address": "Address :",
            "contact_label": "", "contact_value": "", "note_label": "Note:", "tagline": ""}
    assert b"Card settings saved" in client.post("/settings/", data=form, follow_redirects=True).data
    complete_student(client)
    issue(client)
    html = client.get("/passes/1/print").get_data(as_text=True)
    for text in (">Example<", ">Institute<", "Pass No.", "Return to Office A", "Building 2",
                 "Helpline: 000-TEST", "Carry this pass", "Scan me", "D/O", "Gate X", "Line Two Xq"):
        assert text in html, text
    ret = html[html.index("bp-return"):html.index("bp-note")]
    assert "<div> </div>" not in ret and ret.count("<div>") == 3  # 2 return lines + helpline; blank contact omitted
    bad = dict(form, uni_name="")
    assert b"can&#39;t be empty" in client.post("/settings/", data=bad).data


def test_settings_require_login(anon):
    assert anon.get("/settings/").status_code == 302
    assert anon.get("/settings/asset/logo.png").status_code == 302


def test_logo_upload_reencoded_and_removed(client, app):
    tok = csrf(client, "/settings/")
    r = client.post("/settings/asset/logo", data={"csrf_token": tok, "file": image_file((3000, 1500))},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Logo uploaded" in r.data
    img = Image.open(io.BytesIO(client.get("/settings/asset/logo.png").data))
    assert img.format == "PNG" and max(img.size) <= 1200
    r = client.post("/settings/asset/logo", data={"csrf_token": tok, "file": (io.BytesIO(b"nope"), "x.png")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"not a valid image" in r.data
    client.post("/settings/asset/logo", data={"csrf_token": tok, "remove": "1"})
    assert client.get("/settings/asset/logo.png").status_code == 404
    assert client.post("/settings/asset/evil", data={"csrf_token": tok}).status_code == 404


def test_buggy_print_single_has_both_sides_and_qr(client):
    complete_student(client, valid_until="2099-12-31")
    issue(client)
    html = client.get("/passes/1/print").get_data(as_text=True)
    assert html.count('class="bp-card bp-front"') == 1 and html.count('class="bp-card bp-back"') == 1
    assert "size: 85.6mm 54mm" in html
    assert "31-12-2099" in html                       # DD-MM-YYYY like the reference
    assert html.count("<svg") == 1 and "bp-qr" in html  # vector QR, back side only
    front = html[html.index("bp-front"):html.index("bp-back")]
    assert "<svg" not in front


def test_buggy_a4_duplex_mirrors_backs(client):
    for i in range(1, 6):
        complete_student(client, roll_number=f"R-{i}", full_name=f"Student {i}")
        issue_for(client, i)
    html = client.get("/passes/sheet?ids=1,2,3,4,5").get_data(as_text=True)
    assert html.count('bp-card bp-front') == 5 and html.count('bp-card bp-back') == 5
    assert html.count('class="page bp-sheet"') == 4      # 2 sheets x (fronts + backs)
    slots = re.findall(r'class="bp-slot" style="left: ([\d.]+)mm; top: ([\d.]+)mm">\s*<div class="bp-card (bp-\w+)', html)
    fronts = [s[:2] for s in slots if s[2] == "bp-front"][:4]
    backs = [s[:2] for s in slots if s[2] == "bp-back"][:4]
    assert backs == [fronts[1], fronts[0], fronts[3], fronts[2]]   # columns swapped
    plain = client.get("/passes/sheet?ids=1,2,3,4&mirror=0").get_data(as_text=True)
    slots = re.findall(r'class="bp-slot" style="left: ([\d.]+)mm; top: ([\d.]+)mm">\s*<div class="bp-card (bp-\w+)', plain)
    assert [s[:2] for s in slots if s[2] == "bp-back"] == [s[:2] for s in slots if s[2] == "bp-front"]


def issue_for(client, student_id, mode="online"):
    tok = csrf(client, "/students/")
    return client.post(f"/passes/issue/{student_id}", data={"csrf_token": tok, "qr_mode": mode})


def test_print_blocked_for_incomplete_or_revoked(app, client):
    add_student(client)            # incomplete, but no requirements in TestConfig
    issue(client)
    app.config["REQUIRED_FOR_PASS"] = ("guardian_name",)
    r = client.get("/passes/1/print", follow_redirects=True)
    assert b"Complete these students before printing" in r.data
    assert b"Complete these students" in client.get("/passes/sheet?ids=1", follow_redirects=True).data
    app.config["REQUIRED_FOR_PASS"] = ()
    tok = csrf(client, "/passes/1")
    client.post("/passes/1/revoke", data={"csrf_token": tok})
    assert b"Revoked passes can" in client.get("/passes/1/print", follow_redirects=True).data


def test_card_text_is_escaped(client):
    complete_student(client, full_name="<script>alert(1)</script>")
    issue(client)
    for url in ("/passes/1/print", "/passes/1", "/students/1/edit"):
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_student_form_preview_uses_card_template(client):
    html = client.get("/students/new").get_data(as_text=True)
    assert "bp-card bp-front" in html and "bp-card bp-back" in html
    assert "Assigned on issue" not in html  # pass number left blank by default (PRINT_PASS_NUMBER=0)


def test_classic_design_still_available(client):
    make_passes(client, 1)
    assert client.get("/passes/1/print-classic").status_code == 200
    assert client.get("/passes/1/card.png").mimetype == "image/png"


# --- Auto-issue on save + unique QR ---------------------------------------------------

def test_auto_issue_on_complete_save(app, client):
    app.config["AUTO_ISSUE_PASS"] = True
    app.config["REQUIRED_FOR_PASS"] = ("guardian_name", "pickup_point")
    add_point(client, "Stop 1")
    tok = csrf(client, "/students/new")
    base = {"csrf_token": tok, "full_name": "Auto One", "roll_number": "A-1", "program": "BA",
            "status": "active", "qr_mode": "offline"}
    r = client.post("/students/new", data=base)                       # incomplete
    assert "/students/1/edit" in r.headers["Location"]
    assert b"isn&#39;t created yet" in client.get("/students/1/edit").data or b"created yet" in client.get("/students/1/edit").data
    assert b"No passes yet" in client.get("/passes/").data
    r = client.post("/students/1/edit", data=dict(base, guardian_name="G", pickup_point_id="1"))
    assert "/passes/1" in r.headers["Location"]                       # pass + QR created on save
    html = client.get("/passes/1").get_data(as_text=True)
    assert "Offline" in html and "<svg" in html
    # editing again keeps the same pass/QR, and follows the new validity date
    r = client.post("/students/1/edit", data=dict(base, guardian_name="G", pickup_point_id="1",
                                                  valid_until="2099-01-31"))
    assert "/passes/1" in r.headers["Location"]
    assert b"2099-01-31" in client.get("/passes/1").data
    assert client.get("/passes/").get_data(as_text=True).count("badge-valid") == 1


def test_every_qr_unique(client, app):
    for i in range(1, 4):
        add_student(client, roll_number=f"U-{i}")
        for _ in range(3):
            issue_for(client, i)          # reissue revokes but always mints a new QR
    with app.app_context():
        from app.db import get_db
        rows = get_db().execute("SELECT qr_token, pass_code FROM passes").fetchall()
    assert len(rows) == 9
    assert len({r[0] for r in rows}) == 9 and len({r[1] for r in rows}) == 9


def test_qr_at_bottom_of_back(client):
    css = client.get("/static/css/card.css").get_data(as_text=True)
    top = float(re.search(r"\.bp-qr \{[^}]*top: ([\d.]+)mm", css).group(1))
    assert top + 18.5 + 2 <= 52   # QR + caption stay inside the 2 mm frame
    assert top > 30             # lower half of the card


def test_no_login_mode_local_only(app, anon):
    app.config["REQUIRE_LOGIN"] = False
    assert anon.get("/students/").status_code == 200                         # office PC: straight in
    r = anon.get("/students/", environ_base={"REMOTE_ADDR": "192.168.1.50"})
    assert r.status_code == 403                                               # other computers blocked
    assert anon.get("/verify/whatever", environ_base={"REMOTE_ADDR": "10.0.0.9"}).status_code == 404  # verify stays public


def test_oversized_upload_friendly_message(app, client):
    app.config["MAX_CONTENT_LENGTH"] = 1024  # simulate a huge photo
    tok = csrf(client, "/students/new")
    r = client.post("/students/new", data={"csrf_token": tok, "full_name": "Big", "roll_number": "B-1",
                    "program": "BA", "photo": (io.BytesIO(b"x" * 5000), "big.jpg")},
                    content_type="multipart/form-data", headers={"Referer": "/students/new"},
                    follow_redirects=True)
    assert r.status_code == 200 and b"too large to upload" in r.data


def test_large_photo_accepted(client):
    # a 4000x3000 camera-size photo (several MB as PNG) is accepted and normalised
    r = add_student(client, photo=image_file((4000, 3000)))
    assert b"Test Student" in r.data
    assert Image.open(io.BytesIO(client.get("/students/1/photo").data)).size == (600, 800)


def test_pickup_point_free_text(client):
    r = add_student(client, pickup_point="  Kharar   Bus Stand ")
    assert b"Test Student" in r.data
    assert b"Kharar Bus Stand" in client.get("/pickup-points/").data       # added to the list
    add_student(client, roll_number="T-2", pickup_point="kharar bus stand")  # same stop, other case
    html = client.get("/pickup-points/").get_data(as_text=True)
    assert html.count("Kharar Bus Stand") == 1 and ">2</td>" in html          # reused, 2 students
    assert 'value="Kharar Bus Stand"' in client.get("/students/1/edit").get_data(as_text=True)
    r = add_student(client, roll_number="T-3", pickup_point="x" * 81)
    assert b"Pickup point is too long" in r.data


def test_static_cache_busting_and_favicon(client):
    html = client.get("/students/new").get_data(as_text=True)
    assert re.search(r'/static/js/preview\.js\?v=\d+', html)
    r = client.get("/favicon.ico")
    assert r.status_code == 301 and "favicon.png" in r.headers["Location"]


def test_offline_default_and_legacy_qr_still_verifies(client, app):
    add_student(client)
    tok = csrf(client, "/students/")
    client.post("/passes/issue/1", data={"csrf_token": tok})            # no mode given
    with app.app_context():
        from app.db import get_db
        from app.services.qr import PREFIX, _b64, _sign
        import json
        row = get_db().execute("SELECT qr_mode, pass_code FROM passes WHERE id = 1").fetchone()
        assert row["qr_mode"] == "offline"
        body = _b64(json.dumps({"c": row["pass_code"], "n": "Test Student", "r": "T-001", "p": "B.Sc",
                                "v": "2099-06-30"}, separators=(",", ":")).encode())
        legacy = f"{PREFIX}.{body}.{_sign(f'{PREFIX}.{body}'.encode(), app.config['QR_SIGNING_KEY'])}"
    assert api(client, legacy).get_json()["status"] == "valid"            # cards printed earlier
