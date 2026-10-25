"""Utilidades de imagen compartidas (adaptadas de code_resources/app.py)."""

import mimetypes
from datetime import datetime
from pathlib import Path


def save_image_bytes(image_bytes: bytes, mime_type: str, out_dir: Path, prefix: str) -> str:
    ext = mimetypes.guess_extension(mime_type) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    out_path = out_dir / filename
    out_path.write_bytes(image_bytes)
    return str(out_path)
