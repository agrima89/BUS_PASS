"""Secure handling of student photographs.

Uploads are never stored as-is: each file is decoded with Pillow, auto-rotated,
cropped to a 3:4 portrait, resized and re-encoded as JPEG. This strips EXIF/GPS
metadata and any non-image payload. Files get random names and live outside
/static, so they are only served through an authenticated route.
"""
import os
import secrets

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
PHOTO_SIZE = (600, 800)  # 3:4 portrait
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


class PhotoError(ValueError):
    pass


def photo_dir():
    return os.path.join(current_app.config["UPLOAD_FOLDER"], "photos")


def photo_path(name):
    # name always comes from our DB, but guard against path tricks anyway.
    safe = os.path.basename(name or "")
    return os.path.join(photo_dir(), safe) if safe else None


def save_photo(file_storage):
    """Validate + normalise an uploaded photo; return stored filename."""
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise PhotoError("Photo must be a JPG, PNG or WEBP image.")
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoError("That file is not a valid image.")
    if min(img.size) < 200:
        raise PhotoError("Photo is too small (minimum 200 px on the short side).")

    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, PHOTO_SIZE, Image.LANCZOS, centering=(0.5, 0.35))
    name = f"{secrets.token_hex(16)}.jpg"
    img.save(os.path.join(photo_dir(), name), "JPEG", quality=90, optimize=True)
    return name


def delete_photo(name):
    path = photo_path(name)
    if path and os.path.isfile(path):
        os.remove(path)
