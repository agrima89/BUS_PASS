"""Print layouts and PDF export, built with Pillow only (no extra PDF library).

- Single card: one PDF page of exactly 85.6 x 54 mm, for card printers
  (Evolis, Zebra, etc.) or for printing on pre-cut card stock.
- A4 sheet: four cards per A4 page (2 x 2, centred) with crop marks, for
  printing on plain paper or label stock and cutting by hand.

Everything is drawn at 300 DPI, so it prints at true size.
"""
import io

from PIL import Image, ImageDraw

from .card import DPI, H as CARD_H, W as CARD_W, render_card

MM = DPI / 25.4
A4_W, A4_H = round(210 * MM), round(297 * MM)  # 2480 x 3508
GAP = round(6 * MM)        # space between cards, room for cutting
MARK_LEN = round(4 * MM)   # crop mark length
MARK_OFF = round(1.5 * MM) # crop marks stop short of the card edge
CARDS_PER_SHEET = 4


def _positions():
    """Top-left corners of the 4 card slots, centred on the A4 page."""
    block_w = 2 * CARD_W + GAP
    block_h = 2 * CARD_H + GAP
    x0 = (A4_W - block_w) // 2
    y0 = round(20 * MM)  # leave the lower page free; easier to feed and cut
    return [(x0 + c * (CARD_W + GAP), y0 + r * (CARD_H + GAP)) for r in range(2) for c in range(2)]


def _crop_marks(draw, x, y):
    k = (0, 0, 0)
    for cx, sx in ((x, -1), (x + CARD_W, 1)):
        for cy, sy in ((y, -1), (y + CARD_H, 1)):
            # horizontal mark outside the corner
            draw.line((cx + sx * MARK_OFF, cy, cx + sx * (MARK_OFF + MARK_LEN), cy), fill=k, width=2)
            # vertical mark outside the corner
            draw.line((cx, cy + sy * MARK_OFF, cx, cy + sy * (MARK_OFF + MARK_LEN)), fill=k, width=2)


def a4_sheets(rows):
    """Render rows (pass+student joined) into a list of A4 page images."""
    pages = []
    for start in range(0, len(rows), CARDS_PER_SHEET):
        page = Image.new("RGB", (A4_W, A4_H), "white")
        draw = ImageDraw.Draw(page)
        for (x, y), row in zip(_positions(), rows[start:start + CARDS_PER_SHEET]):
            page.paste(render_card(row, row), (x, y))
            _crop_marks(draw, x, y)
        pages.append(page)
    return pages


def to_pdf(images, title="Passes") -> bytes:
    buf = io.BytesIO()
    first, rest = images[0], images[1:]
    first.save(buf, "PDF", resolution=DPI, save_all=True, append_images=rest, title=title)
    return buf.getvalue()


def single_card_pdf(row) -> bytes:
    return to_pdf([render_card(row, row)], title=row["pass_code"])


def a4_pdf(rows) -> bytes:
    return to_pdf(a4_sheets(rows), title="Pass sheet")
