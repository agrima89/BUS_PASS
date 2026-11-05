"""QR payloads for passes.

Offline mode (default): the QR holds plain, human-readable text, so ANY phone
              camera or QR app shows the pass details with no internet and no
              special app:

                  CHANDIGARH UNIVERSITY BUS PASS
                  Pass No: CU-2026-K7Q2XZ
                  Name: ...
                  UID: ...
                  Class: ...
                  Pickup: ...
                  Valid upto: 31-12-2026
                  Sig: 3q2+7wAbCdEf...

              The last line is an HMAC signature over the details. This app's
              scanner (or anything holding QR_SIGNING_KEY) rejects edited or
              forged codes. No guardian name, phone or address is ever included.

Online mode:  the QR holds only a verify URL with a random, unguessable token,
              e.g. https://host/verify/<token>; the server shows the live status.

Legacy:       "UPG1.<base64 json>.<sig>" offline codes from earlier versions still verify.
"""
import base64
import hashlib
import hmac
import json

import qrcode
from flask import current_app
from PIL import Image

PREFIX = "UPG1"          # legacy compact offline format
SIG_LABEL = "Sig: "      # last line of the readable offline format


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(message: bytes, key: str) -> str:
    return _b64(hmac.new(key.encode(), message, hashlib.sha256).digest()[:16])


def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _dmy(iso):
    if iso and len(iso) == 10 and iso[4] == "-":
        y, m, d = iso.split("-")
        return f"{d}-{m}-{y}"
    return iso or ""


def _iso(dmy):
    if dmy and len(dmy) == 10 and dmy[2] == "-":
        d, m, y = dmy.split("-")
        return f"{y}-{m}-{d}"
    return dmy or ""


def _canonical(code, name, uid, program, pickup, valid_iso):
    # Fields are joined with the ASCII unit separator, which can't appear in form values.
    return "\x1f".join(["UPG2", code, name, uid, program, pickup, valid_iso]).encode()


def online_payload(qr_token: str) -> str:
    return f"{current_app.config['PUBLIC_BASE_URL']}/verify/{qr_token}"


def offline_payload(student, pass_row) -> str:
    code = pass_row["pass_code"]
    name = student["full_name"] or ""
    uid = student["roll_number"] or ""
    program = student["program"] or ""
    pickup = _get(student, "pickup_point") or ""
    valid = pass_row["expires_at"] or ""
    sig = _sign(_canonical(code, name, uid, program, pickup, valid), current_app.config["QR_SIGNING_KEY"])
    lines = [f"{current_app.config['UNIVERSITY_NAME'].upper()} BUS PASS",
             f"Pass No: {code}", f"Name: {name}", f"UID: {uid}", f"Class: {program}"]
    if pickup:
        lines.append(f"Pickup: {pickup}")
    lines += [f"Valid upto: {_dmy(valid) or '-'}", f"{SIG_LABEL}{sig}"]
    return "\n".join(lines)


def is_offline_payload(text: str) -> bool:
    text = (text or "").strip().replace("\r\n", "\n")
    return text.startswith(PREFIX + ".") or f"\n{SIG_LABEL}" in text


def verify_offline(payload: str, key: str):
    """Return {c, n, r, p, k, v} if the signature is valid, else None."""
    payload = (payload or "").strip().replace("\r\n", "\n")
    if payload.startswith(PREFIX + "."):
        return _verify_legacy(payload, key)
    fields = {}
    for line in payload.split("\n")[1:]:
        label, sep, value = line.partition(": ")
        if sep:
            fields[label.strip()] = value.strip()
    sig = fields.get("Sig")
    code, name, uid = fields.get("Pass No"), fields.get("Name"), fields.get("UID")
    if not (sig and code and name is not None and uid is not None):
        return None
    program, pickup = fields.get("Class", ""), fields.get("Pickup", "")
    valid_iso = "" if fields.get("Valid upto") in (None, "-") else _iso(fields["Valid upto"])
    expected = _sign(_canonical(code, name, uid, program, pickup, valid_iso), key)
    if not hmac.compare_digest(sig, expected):
        return None
    return {"c": code, "n": name, "r": uid, "p": program, "k": pickup, "v": valid_iso}


def _verify_legacy(payload, key):
    try:
        prefix, encoded, sig = payload.split(".")
        expected = _sign(f"{prefix}.{encoded}".encode(), key)
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(_unb64(encoded))
    except (ValueError, json.JSONDecodeError):
        return None


def payload_for(student, pass_row) -> str:
    if pass_row["qr_mode"] == "offline":
        return offline_payload(student, pass_row)
    return online_payload(pass_row["qr_token"])


def make_qr_image(data: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")
    return img.resize((size, size), Image.NEAREST)


def make_qr_svg(data: str) -> str:
    """QR as inline SVG markup: vector, so it stays sharp at any print resolution."""
    from qrcode.image.svg import SvgPathImage
    # Long readable offline text -> lowest error correction keeps the modules large enough
    # to scan from a printed card; short online URLs can afford medium correction.
    level = qrcode.constants.ERROR_CORRECT_L if len(data) > 120 else qrcode.constants.ERROR_CORRECT_M
    img = qrcode.make(data, image_factory=SvgPathImage, box_size=10, border=2, error_correction=level)
    svg = img.to_string(encoding="unicode")
    return svg[svg.index("<svg"):]  # drop the XML declaration for inline use
