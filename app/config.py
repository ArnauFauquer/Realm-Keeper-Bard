"""Shared paths and configuration for the application."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

# Everything that is not code lives in DATA_DIR (in Docker, the /data volume):
# app output, reference images, the style profile, model weights and caches.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
OUTPUT_DIR = DATA_DIR / "generated_images"
TRANSPARENT_DIR = DATA_DIR / "generated_transparent"
MODELS_3D_OUTPUT_DIR = DATA_DIR / "generated_3d"
UPLOAD_DIR = DATA_DIR / "uploads"
THUMB_DIR = DATA_DIR / "thumbs"
REFERENCES_DIR = DATA_DIR / "references"
STYLE_PATH = DATA_DIR / "world_style.json"
# Migrate data from before the English rename.
_legacy_refs = DATA_DIR / "referencias"
if _legacy_refs.is_dir() and not REFERENCES_DIR.exists():
    _legacy_refs.rename(REFERENCES_DIR)
    if (REFERENCES_DIR / "especie_rata.jpg").exists():
        (REFERENCES_DIR / "especie_rata.jpg").rename(REFERENCES_DIR / "species_rat.jpg")
for _dir in (OUTPUT_DIR, TRANSPARENT_DIR, MODELS_3D_OUTPUT_DIR, UPLOAD_DIR, THUMB_DIR, REFERENCES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# Hugging Face (model components) and rembg (u2net) caches.
os.environ.setdefault("HF_HOME", str(DATA_DIR / "cache" / "huggingface"))
os.environ.setdefault("U2NET_HOME", str(DATA_DIR / "cache" / "u2net"))

# Isolated environment (Python 3.12 + PyTorch CUDA) with the image → 3D models.
MODELS_3D_DIR = BASE_DIR / "models_3d"
MODELS_3D_PYTHON = MODELS_3D_DIR / "venv" / "Scripts" / "python.exe"
MODELS_3D_WORKER = MODELS_3D_DIR / "workers" / "run3d.py"

# Local image engine (diffusers): Krea 2 to create, FLUX 3 Image Klein to
# transform/edit. See local_engine.py. The transformers are local GGUF files; the
# remaining components come from these Hugging Face repos.
MODELS_DIR = DATA_DIR / "models"
KREA_GGUF = MODELS_DIR / os.environ.get("KREA_GGUF", "krea2_turbo-Q4_K_M.gguf")
FLUX3_GGUF = MODELS_DIR / os.environ.get("FLUX3_GGUF", "flux-3-image-klein-Q8_0.gguf")
KREA_REPO = os.environ.get("KREA_REPO", "krea/Krea-2-Turbo")
FLUX3_REPO = os.environ.get("FLUX3_REPO", "black-forest-labs/flux-3-image-klein")
OFFLOAD = os.environ.get("ENGINE_OFFLOAD", "group")  # "group" (per layer) | "model"
