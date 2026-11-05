"""Configurable card branding and wording (Phase 4B).

Everything printed on the buggy pass that isn't student data lives here and is
edited on the admin Settings page. Defaults are the field labels from the
reference layout plus *blank* official text: no university wording, numbers,
logos or seals are invented. The admin enters the official content.
"""
import io
import os
import secrets

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from ..db import get_db

# key -> (default, max length, multiline?, section, label shown on the Settings page)
FIELDS = {
    # Front
    "uni_name": (None, 80, False, "front", "University name"),
    "tagline": ("", 80, False, "front", "Tagline under the name"),
    "name_color_1": ("#222222", 7, False, "front", "Colour: first line of name (hex, e.g. #CE1A19)"),
    "name_color_2": ("#222222", 7, False, "front", "Colour: rest of name (hex)"),
    "tagline_color": ("#333333", 7, False, "front", "Colour: tagline (hex)"),
    "card_title": ("Buggy Pass No.", 40, False, "front", "Card title (next to the pass number)"),
    "label_name": ("Name:", 30, False, "front", "Label: name"),
    "label_class": ("Class/Branch:", 30, False, "front", "Label: class/branch"),
    "label_uid": ("UID:", 30, False, "front", "Label: UID"),
    "label_pickup": ("Pickup Point:", 30, False, "front", "Label: pickup point"),
    # Back
    "label_valid": ("Valid Upto :", 30, False, "back", "Label: valid upto"),
    "label_emergency": ("Emergency Contact No.", 40, False, "back", "Label: emergency contact"),
    "label_address": ("Address :", 30, False, "back", "Label: address"),
    "return_text": ("", 400, True, "back", "Return instructions (one line per row)"),
    "contact_label": ("Contact No.", 40, False, "back", "Label: contact number"),
    "contact_value": ("", 40, False, "back", "Contact number"),
    "helpline_label": ("Transport Helpline number:", 50, False, "back", "Label: helpline"),
    "helpline_value": ("", 40, False, "back", "Helpline number"),
    "note_label": ("Note:", 20, False, "back", "Label: note"),
    "note_lines": ("", 300, True, "back", "Note lines (one per row)"),
    "qr_caption": ("Scan with any phone", 30, False, "back", "Caption under the QR code"),
}
ASSETS = ("logo", "seal")
ASSET_MAX_PX = 1200


def _defaults():
    d = {k: v[0] for k, v in FIELDS.items()}
    d["uni_name"] = current_app.config["UNIVERSITY_NAME"]
    return d


def card_settings():
    """All card settings, with defaults for anything not saved yet."""
    s = _defaults()
    s.update({"logo": None, "seal": None})
    for row in get_db().execute("SELECT key, value FROM settings"):
        if row["key"] in s:
            s[row["key"]] = row["value"]
    return s


def save_settings(form):
    errors, values = [], {}
    for key, (_default, max_len, multiline, _sec, label) in FIELDS.items():
        raw = (form.get(key) or "").replace("\r\n", "\n")
        value = "\n".join(l.strip() for l in raw.split("\n")).strip() if multiline else " ".join(raw.split())
        if len(value) > max_len:
            errors.append(f"{label} is too long (max {max_len} characters).")
        values[key] = value
    import re
    for key in ("name_color_1", "name_color_2", "tagline_color"):
        if values[key] and not re.fullmatch(r"#[0-9a-fA-F]{6}", values[key]):
            errors.append(f"{FIELDS[key][4].split(':')[0]} must be a hex colour like #CE1A19.")
    if not values["uni_name"]:
        errors.append("University name can't be empty.")
    if errors:
        return errors
    db = get_db()
    db.executemany("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", values.items())
    db.commit()
    return []


def _asset_dir():
    d = os.path.join(current_app.config["UPLOAD_FOLDER"], "branding")
    os.makedirs(d, exist_ok=True)
    return d


def asset_path(kind):
    name = card_settings().get(kind)
    return os.path.join(_asset_dir(), os.path.basename(name)) if name else None


def save_asset(kind, file_storage):
    """Validate and re-encode an uploaded logo/seal as PNG (keeps transparency)."""
    if kind not in ASSETS:
        raise ValueError("Unknown asset.")
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file is not a valid image (use PNG, JPG or WEBP).")
    img = ImageOps.exif_transpose(img).convert("RGBA")
    img.thumbnail((ASSET_MAX_PX, ASSET_MAX_PX), Image.LANCZOS)
    name = f"{kind}-{secrets.token_hex(8)}.png"
    img.save(os.path.join(_asset_dir(), name), "PNG", optimize=True)
    old = asset_path(kind)
    db = get_db()
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (kind, name))
    db.commit()
    if old and os.path.isfile(old):
        os.remove(old)


def remove_asset(kind):
    old = asset_path(kind)
    db = get_db()
    db.execute("DELETE FROM settings WHERE key = ?", (kind,))
    db.commit()
    if old and os.path.isfile(old):
        os.remove(old)
