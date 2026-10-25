"""Estimación del FOV de la cámara con MoGe-2, igual que el Space oficial de
Pixal3D (TencentARC/Pixal3D, app.py: get_camera_params_wild_moge).

Pixal3D proyecta cada celda 3D sobre el píxel de la imagen con una cámara
frontal; si el FOV supuesto no es el de la imagen, la malla se deforma (más
gruesa o más plana que el original). trellis.cpp no porta MoGe-2, así que se
estima aquí (PyTorch en CPU) y se le pasa con --fov.
"""

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights"
os.environ.setdefault("HF_HOME", str(WEIGHTS_DIR / "hf_home"))

MOGE_MODEL_NAME = "Ruicheng/moge-2-vitl"


def preprocess_like_pixal3d(image: Image.Image) -> Image.Image:
    """Réplica de Pixal3DImageTo3DPipeline.preprocess_image: recorte cuadrado
    al contorno del alfa con un 10% de margen, compuesto sobre negro."""
    image = image.convert("RGBA")
    scale = min(1.0, 1024 / max(image.size))
    if scale < 1:
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS
        )
    alpha = np.array(image)[:, :, 3]
    ys, xs = np.nonzero(alpha > 0.8 * 255)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    size = int(max(x1 - x0, y1 - y0) * 1.1)
    crop = image.crop((cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2))
    rgba = np.array(crop).astype(np.float32) / 255
    rgb = rgba[:, :, :3] * rgba[:, :, 3:4]  # fondo negro
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def estimate_fov_deg(image_path: str) -> float:
    """FOV horizontal (grados) que MoGe-2 estima para la imagen preprocesada."""
    import torch
    from moge.model.v2 import MoGeModel

    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
    model = MoGeModel.from_pretrained(MOGE_MODEL_NAME).eval()
    img = preprocess_like_pixal3d(Image.open(image_path))
    tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0).permute(2, 0, 1)
    with torch.no_grad():
        out = model.infer(tensor, use_fp16=False)  # fp16 no funciona en CPU
    fx = float(out["intrinsics"].squeeze()[0, 0]) * img.width  # fx normalizado -> px
    return math.degrees(2 * math.atan(img.width / (2 * fx)))
