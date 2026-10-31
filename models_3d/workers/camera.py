"""Camera FOV estimation with MoGe-2, the same as the official Pixal3D Space
(TencentARC/Pixal3D, app.py: get_camera_params_wild_moge).

Pixal3D projects each 3D cell onto the image pixel with a frontal camera; if the
assumed FOV is not the image's, the mesh is distorted (thicker or flatter than
the original). trellis.cpp does not port MoGe-2, so it is estimated here
(PyTorch on CPU) and passed in with --fov.
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
    """Replica of Pixal3DImageTo3DPipeline.preprocess_image: square crop
    around the alpha outline with a 10% margin, composited on black."""
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
    rgb = rgba[:, :, :3] * rgba[:, :, 3:4]  # black background
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def estimate_fov_deg(image_path: str) -> float:
    """Horizontal FOV (degrees) that MoGe-2 estimates for the preprocessed image."""
    import torch
    from moge.model.v2 import MoGeModel

    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
    model = MoGeModel.from_pretrained(MOGE_MODEL_NAME).eval()
    img = preprocess_like_pixal3d(Image.open(image_path))
    tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0).permute(2, 0, 1)
    with torch.no_grad():
        out = model.infer(tensor, use_fp16=False)  # fp16 does not work on CPU
    fx = float(out["intrinsics"].squeeze()[0, 0]) * img.width  # fx normalizado -> px
    return math.degrees(2 * math.atan(img.width / (2 * fx)))
