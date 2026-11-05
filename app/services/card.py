"""Render a student pass card with Pillow.

Output is CR80 ID-card size (85.6 x 54 mm) at 300 DPI = 1011 x 638 px, so it
prints at true size. Branding is placeholder until official assets exist.
"""
import os
from functools import lru_cache

from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from .photos import photo_path
from .qr import make_qr_image, payload_for

W, H = 1011, 638
DPI = 300
NAVY, INDIGO = (24, 45, 110), (79, 70, 229)
INK, MUTED, LINE = (20, 24, 35), (100, 108, 125), (226, 230, 238)

_FONT_CANDIDATES = {
    "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
    "bold": ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "semibold": ["seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
}
_FONT_DIRS = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
              "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]


@lru_cache(maxsize=32)
def font(weight: str, size: int):
    for name in _FONT_CANDIDATES[weight]:
        for d in _FONT_DIRS:
            path = os.path.join(d, name)
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _fit(draw, text, fnt, max_w):
    """Trim text with an ellipsis so it fits max_w pixels."""
    text = text or ""
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text + "…"


def _gradient(size, c1, c2):
    w, h = size
    grad = Image.new("RGB", (w, 1))
    for x in range(w):
        t = x / max(w - 1, 1)
        grad.putpixel((x, 0), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return grad.resize((w, h))


def _photo(student, size):
    path = photo_path(student["photo_path"]) if student["photo_path"] else None
    if path and os.path.isfile(path):
        return Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    # Placeholder silhouette.
    ph = Image.new("RGB", size, (232, 236, 244))
    d = ImageDraw.Draw(ph)
    w, h = size
    d.ellipse((w * .3, h * .18, w * .7, h * .5), fill=(190, 198, 214))
    d.ellipse((w * .12, h * .55, w * .88, h * 1.15), fill=(190, 198, 214))
    return ph


def render_card(student, pass_row) -> Image.Image:
    cfg = current_app.config
    card = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(card)

    # Header band
    card.paste(_gradient((W, 140), NAVY, INDIGO), (0, 0))
    d.ellipse((36, 26, 124, 114), fill="white")
    short = cfg["UNIVERSITY_SHORT"][:4]
    f_logo = font("bold", 34 if len(short) <= 2 else 24)
    d.text((80, 70), short, font=f_logo, fill=NAVY, anchor="mm")
    d.text((146, 36), _fit(d, cfg["UNIVERSITY_NAME"].upper(), font("bold", 40), W - 180),
           font=font("bold", 40), fill="white")
    d.text((148, 88), "STUDENT IDENTITY CARD", font=font("semibold", 22), fill=(199, 210, 254))

    # Photo
    px, py, pw, ph = 40, 170, 240, 320
    d.rounded_rectangle((px - 4, py - 4, px + pw + 4, py + ph + 4), radius=10, fill=LINE)
    card.paste(_photo(student, (pw, ph)), (px, py))

    # Details
    x = 310
    d.text((x, 168), _fit(d, student["full_name"], font("bold", 40), 400),
           font=font("bold", 40), fill=INK)
    rows = [
        ("UID", student["roll_number"]),
        ("PROGRAM", student["program"]),
        ("DEPARTMENT", student["department"] or "—"),
        ("YEAR", str(student["year_of_study"] or "—")),
        ("BLOOD GROUP", student["blood_group"] or "—"),
        ("VALID UNTIL", pass_row["expires_at"] or "—"),
    ]
    y = 232
    f_lab, f_val = font("semibold", 17), font("regular", 25)
    for label, value in rows:
        d.text((x, y), label, font=f_lab, fill=MUTED)
        d.text((x + 165, y - 5), _fit(d, value, f_val, 240), font=f_val, fill=INK)
        y += 43

    # QR
    qs = 230
    qx, qy = W - qs - 36, 172
    card.paste(make_qr_image(payload_for(student, pass_row), qs), (qx, qy))
    caption = "Scan to verify" if pass_row["qr_mode"] == "online" else "Offline verifiable"
    d.text((qx + qs // 2, qy + qs + 14), caption, font=font("semibold", 18), fill=MUTED, anchor="mt")

    # Footer
    d.rectangle((0, H - 58, W, H), fill=(243, 245, 250))
    d.line((0, H - 58, W, H - 58), fill=LINE, width=2)
    d.text((40, H - 29), f"PASS NO. {pass_row['pass_code']}", font=font("bold", 20), fill=NAVY, anchor="lm")
    d.text((W - 36, H - 29), "Property of the university · If found, please return",
           font=font("regular", 17), fill=MUTED, anchor="rm")
    d.rectangle((0, 140, W, 146), fill=(245, 158, 11))  # accent stripe
    return card


def card_png_bytes(student, pass_row) -> bytes:
    import io
    buf = io.BytesIO()
    render_card(student, pass_row).save(buf, "PNG", dpi=(DPI, DPI), optimize=True)
    return buf.getvalue()
