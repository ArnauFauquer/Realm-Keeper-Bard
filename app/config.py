"""Rutas y configuración compartida de la aplicación."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "generated_images"
TRANSPARENT_DIR = BASE_DIR / "generated_transparent"
MODELS_3D_OUTPUT_DIR = BASE_DIR / "generated_3d"
OUTPUT_DIR.mkdir(exist_ok=True)
TRANSPARENT_DIR.mkdir(exist_ok=True)
MODELS_3D_OUTPUT_DIR.mkdir(exist_ok=True)

# Entorno aislado (Python 3.12 + PyTorch CUDA) con los modelos imagen → 3D.
MODELS_3D_DIR = BASE_DIR / "models_3d"
MODELS_3D_PYTHON = MODELS_3D_DIR / "venv" / "Scripts" / "python.exe"
MODELS_3D_WORKER = MODELS_3D_DIR / "workers" / "run3d.py"

ENV_PATH = BASE_DIR / ".env"
STYLE_PATH = BASE_DIR / "world_style.json"

load_dotenv(ENV_PATH)

# Motor de imagen local (diffusers): Krea 2 para crear y FLUX 3 Image Klein para
# transformar/editar. Ver local_engine.py. Los transformers son GGUF locales; el
# resto de componentes sale de estos repos de Hugging Face.
MODELS_DIR = Path(os.environ.get("MODELS_DIR", BASE_DIR / "models"))
KREA_GGUF = MODELS_DIR / os.environ.get("KREA_GGUF", "krea2_turbo-Q4_K_M.gguf")
FLUX3_GGUF = MODELS_DIR / os.environ.get("FLUX3_GGUF", "flux-3-image-klein-Q8_0.gguf")
KREA_REPO = os.environ.get("KREA_REPO", "krea/Krea-2-Turbo")
FLUX3_REPO = os.environ.get("FLUX3_REPO", "black-forest-labs/flux-3-image-klein")
OFFLOAD = os.environ.get("ENGINE_OFFLOAD", "group")  # "group" (por capas) | "model"
