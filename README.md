# RealmKeeper Bard

A local tool for creating tabletop RPG campaign art with a consistent style:
characters, backgrounds, objects and maps, background removal, and turning
images into printable 3D models (STL).

- **Create**: Krea 2 Turbo (text → image).
- **Transform / edit**: FLUX 3 Image Klein (with reference images).
- **Remove background**: rembg.
- **3D**: Pixal3D via trellis.cpp (Windows only, outside Docker).

The image models run inside the app through
[diffusers](https://github.com/huggingface/diffusers); no external services are needed.

## Layout

| Path | What it is |
|---|---|
| `app/` | FastAPI backend (`server.py`), image engine (`local_engine.py`), prompts and style profile |
| `web/` | React + Vite + Tailwind frontend; built to `web/dist` and served by the backend |
| `data/` | Everything that is not code (in Docker, the `/data` volume); git-ignored |
| `data/references/` | Canonical species reference images (style anchors) |
| `data/models/` | GGUF transformer weights |
| `data/world_style.json` | World style profile (edited by the app) |
| `data/generated_*`, `data/uploads/`, `data/thumbs/`, `data/cache/` | Results, uploads, thumbnails and Hugging Face / rembg caches |
| `models_3d/` | Separate environment for image → 3D (`setup_3d.ps1`) |

## Model weights

Put these in `data/models/`:

- `krea2_turbo-Q4_K_M.gguf`
- `flux-3-image-klein-Q8_0.gguf` ([unsloth/flux-3-image-klein-GGUF](https://huggingface.co/unsloth/flux-3-image-klein-GGUF))

The remaining components (Qwen3-VL 4B text encoder, VAE, configs) are downloaded
from Hugging Face on first use from `krea/Krea-2-Turbo` and `black-forest-labs/flux-3-image-klein`.
FLUX 3 Klein requires accepting its license on Hugging Face and setting a token in `.env`:

```
HF_TOKEN=hf_...
```

## Run with Docker (recommended)

Requirements: Docker Desktop with the WSL2 backend and a recent NVIDIA driver (GPU with ≥10 GB VRAM).

```bash
cp .env.example .env
docker compose up --build
```

The app is served at <http://localhost:8765>. All data lives in `data/`, mounted
as the single volume `/data` (override with `DATA_DIR`).

## Run without Docker

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
cd web && npm ci && npm run build && cd ..
python main.py
```

To develop the frontend with hot reload, run `python main.py` in one terminal and
`npm run dev` inside `web/` in another (Vite proxies `/api` to port 8765).

## 3D

Mesh generation uses `models_3d/` (a Windows venv + trellis.cpp with CUDA), so it
only works when running the app on Windows without Docker. Install it with:

```bash
powershell -ExecutionPolicy Bypass -File models_3d/setup_3d.ps1
```

## License

[MIT-0](LICENSE). Model weights have their own licenses (FLUX 3 Klein: FLUX Kommunity License).
