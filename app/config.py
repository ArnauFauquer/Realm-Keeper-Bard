"""Rutas y configuración compartida de la aplicación."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

# Todo lo que no es código vive en DATA_DIR (en Docker, el volumen /data): lo que
# genera la app, las referencias, el perfil de estilo, los pesos y las cachés.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
OUTPUT_DIR = DATA_DIR / "generated_images"
TRANSPARENT_DIR = DATA_DIR / "generated_transparent"
MODELS_3D_OUTPUT_DIR = DATA_DIR / "generated_3d"
UPLOAD_DIR = DATA_DIR / "uploads"
THUMB_DIR = DATA_DIR / "thumbs"
REFERENCES_DIR = DATA_DIR / "referencias"
STYLE_PATH = DATA_DIR / "world_style.json"
for _dir in (OUTPUT_DIR, TRANSPARENT_DIR, MODELS_3D_OUTPUT_DIR, UPLOAD_DIR, THUMB_DIR, REFERENCES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# Cachés de Hugging Face (componentes de los modelos) y rembg (u2net).
os.environ.setdefault("HF_HOME", str(DATA_DIR / "cache" / "huggingface"))
os.environ.setdefault("U2NET_HOME", str(DATA_DIR / "cache" / "u2net"))

# Entorno aislado (Python 3.12 + PyTorch CUDA) con los modelos imagen → 3D.
MODELS_3D_DIR = BASE_DIR / "models_3d"
MODELS_3D_PYTHON = MODELS_3D_DIR / "venv" / "Scripts" / "python.exe"
MODELS_3D_WORKER = MODELS_3D_DIR / "workers" / "run3d.py"

# Motor de imagen local (diffusers): Krea 2 para crear y FLUX 3 Image Klein para
# transformar/editar. Ver local_engine.py. Los transformers son GGUF locales; el
# resto de componentes sale de estos repos de Hugging Face.
MODELS_DIR = DATA_DIR / "models"
KREA_GGUF = MODELS_DIR / os.environ.get("KREA_GGUF", "krea2_turbo-Q4_K_M.gguf")
FLUX3_GGUF = MODELS_DIR / os.environ.get("FLUX3_GGUF", "flux-3-image-klein-Q8_0.gguf")
KREA_REPO = os.environ.get("KREA_REPO", "krea/Krea-2-Turbo")
FLUX3_REPO = os.environ.get("FLUX3_REPO", "black-forest-labs/flux-3-image-klein")
OFFLOAD = os.environ.get("ENGINE_OFFLOAD", "group")  # "group" (por capas) | "model"
