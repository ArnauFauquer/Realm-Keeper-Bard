"""Workflow imagen → malla 3D imprimible (STL) con Pixal3D.

La inferencia la hace trellis.cpp (C++/CUDA) y el post-proceso de la malla un
worker en el entorno aparte `models_3d/venv` (trimesh + pymeshlab). Aquí solo
se lanza `models_3d/workers/run3d.py` como subproceso y se interpreta su salida.
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


# Preparación de la imagen con FLUX 3 (motor local) antes de la malla:
# "detailed" = escultura gris de alto detalle (style_3d del perfil), "clay" =
# arcilla lisa (PREPARE_3D_PROMPT), "none" = se usa la imagen tal cual.
MESH_PREPARE_MODES = (
    ("Sin preparar", "none"),
    ("Escultura detallada", "detailed"),
    ("Arcilla lisa", "clay"),
)


@dataclass
class Mesh3DOptions:
    seed: int = 0
    max_faces: int = 1000000
    height_mm: float = 100.0


def environment_ready() -> bool:
    return MODELS_3D_PYTHON.exists() and MODELS_3D_WORKER.exists()


def random_seed() -> int:
    """Cada malla usa una semilla nueva: las variantes son interpretaciones
    distintas de lo que no se ve en la imagen."""
    return secrets.randbelow(2**31)


def start_mesh_generation(image_path: str, options: Mesh3DOptions) -> subprocess.Popen:
    # quita el sello de tiempo de los nombres generados por la app
    name = re.sub(r"_\d{8}_\d{6}(_\d+)?$", "", Path(image_path).stem)[:48] or "modelo"
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
    """Lee la salida del worker hasta que termina. Devuelve el dict RESULT o
    lanza RuntimeError con el mensaje de error y las últimas líneas del log."""
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
    raise RuntimeError(f"{error or 'El proceso terminó con código ' + str(code)}\n\n{detail}")
