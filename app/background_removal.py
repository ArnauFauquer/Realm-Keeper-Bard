"""Workflow para eliminar el fondo de una imagen y dejarla en PNG con alpha."""

from rembg import remove


def remove_background(image_path: str) -> bytes:
    """Lee una imagen de cualquier formato soportado y devuelve un PNG con
    canal alpha (fondo transparente). La primera vez que se llama, rembg
    descarga el modelo de segmentación (requiere conexión a internet)."""
    with open(image_path, "rb") as f:
        input_bytes = f.read()
    return remove(input_bytes)
