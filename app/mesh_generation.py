"""Workflow image → printable 3D mesh (STL) with Pixal3D.

Inference is done by trellis.cpp (C++/CUDA) and mesh post-processing by a
worker in the separate `models_3d/venv` environment (trimesh + pymeshlab). This
module only launches `models_3d/workers/run3d.py` as a subprocess and parses
its output.
"""

import json
import os
import re
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import MODELS_3D_OUTPUT_DIR, MODELS_3D_PYTHON, MODELS_3D_WORKER


# Image preparation with FLUX 3 (local engine) before meshing:
# "detailed" = highly detailed grey sculpture (profile's style_3d), "clay" =
# smooth clay (PREPARE_3D_PROMPT), "none" = use the image as is.
MESH_PREPARE_MODES = (
    ("No preparation", "none"),
    ("Detailed sculpture", "detailed"),
    ("Smooth clay", "clay"),
)


@dataclass
class Mesh3DOptions:
    seed: int = 0
    max_faces: int = 1000000
    height_mm: float = 100.0


def environment_ready() -> bool:
    return MODELS_3D_PYTHON.exists() and MODELS_3D_WORKER.exists()


def random_seed() -> int:
    """Every mesh uses a fresh seed: variants are different interpretations
    of whatever the image does not show."""
    return secrets.randbelow(2**31)


def start_mesh_generation(image_path: str, options: Mesh3DOptions) -> subprocess.Popen:
    # strip the timestamp from app-generated file names
    name = re.sub(r"_\d{8}_\d{6}(_\d+)?$", "", Path(image_path).stem)[:48] or "model"
    cmd = [
        str(MODELS_3D_PYTHON), "-u", str(MODELS_3D_WORKER),
        "--image", str(Path(image_path).resolve()),
        "--out-dir", str(MODELS_3D_OUTPUT_DIR),
        "--name", name,
        "--seed", str(options.seed),
        "--faces", str(options.max_faces),
        "--height-mm", str(options.height_mm),
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def run_mesh_generation(proc: subprocess.Popen, on_progress: Callable[[str], None]) -> dict:
    """Read the worker output until it exits. Return the RESULT dict or raise
    RuntimeError with the error message and the last log lines."""
    result = None
    error = None
    tail: list[str] = []
    for raw in proc.stdout:
        line = raw.rstrip()
        if not line:
            continue
        tail = (tail + [line])[-20:]
        if line.startswith("PROGRESS: "):
            on_progress(line[len("PROGRESS: "):])
        elif line.startswith("RESULT: "):
            result = json.loads(line[len("RESULT: "):])
        elif line.startswith("ERROR: "):
            error = line[len("ERROR: "):]
    code = proc.wait()
    if result is not None and code == 0:
        return result
    detail = "\n".join(tail[-12:])
    raise RuntimeError(f"{error or 'The process exited with code ' + str(code)}\n\n{detail}")
