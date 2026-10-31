"""Workflow that removes an image background and returns a PNG with alpha."""

from rembg import remove


def remove_background(image_path: str) -> bytes:
    """Read an image in any supported format and return a PNG with an alpha
    channel (transparent background). The first call makes rembg download the
    segmentation model (requires an internet connection)."""
    with open(image_path, "rb") as f:
        input_bytes = f.read()
    return remove(input_bytes)
