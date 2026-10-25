# RealmKeeper Bard

Herramienta local para crear el arte de una campaña de rol con un estilo
coherente: personajes, fondos, objetos y mapas, quitar fondos y convertir
imágenes en modelos 3D imprimibles (STL).

- **Crear**: Krea 2 Turbo (texto → imagen).
- **Transformar / editar**: FLUX 3 Image Klein (con imágenes de referencia).
- **Quitar fondo**: rembg.
- **3D**: Pixal3D / TRELLIS.2 vía trellis.cpp (solo Windows, fuera de Docker).

Los modelos de imagen corren dentro de la app con
[diffusers](https://github.com/huggingface/diffusers), sin servicios externos.

## Estructura

| Ruta | Qué es |
|---|---|
| `app/` | Backend FastAPI (`server.py`), motor de imagen (`local_engine.py`), prompts y perfil de estilo |
| `web/` | Frontend React + Vite + Tailwind; se compila a `web/dist` y lo sirve el backend |
| `referencias/` | Imágenes canon de las especies (anclas de estilo) |
| `models/` | Pesos GGUF de los transformers (no se versionan) |
| `models_3d/` | Entorno aparte para imagen → 3D (`setup_3d.ps1`) |
| `world_style.json` | Perfil de estilo del mundo (lo edita la app) |

## Pesos de los modelos

Copia en `models/`:

- `krea2_turbo-Q4_K_M.gguf`
- `flux-3-image-klein-Q8_0.gguf` ([unsloth/flux-3-image-klein-GGUF](https://huggingface.co/unsloth/flux-3-image-klein-GGUF))

El resto (encoder de texto Qwen3-VL 4B, VAE, configs) se descarga de Hugging Face
la primera vez desde `krea/Krea-2-Turbo` y `black-forest-labs/flux-3-image-klein`.
FLUX 3 Klein requiere aceptar su licencia en Hugging Face y poner un token en `.env`:

```
HF_TOKEN=hf_...
```

## Arrancar con Docker (recomendado)

Requisitos: Docker Desktop con backend WSL2 y driver NVIDIA reciente (GPU con ≥10 GB de VRAM).

```bash
cp .env.example .env
docker compose up --build
```

La app queda en <http://localhost:8765>. Las imágenes generadas, subidas y el
perfil de estilo viven en carpetas del proyecto montadas como volúmenes; la caché
de Hugging Face y rembg en `.cache/`.

## Arrancar sin Docker

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
cd web && npm ci && npm run build && cd ..
python main.py
```

Para desarrollar el frontend con recarga en caliente: `python main.py` en una
terminal y `npm run dev` dentro de `web/` en otra (Vite redirige `/api` al 8765).

## 3D

La generación de mallas usa `models_3d/` (venv de Windows + trellis.cpp con CUDA),
así que solo funciona arrancando la app en Windows sin Docker. Se instala con:

```bash
powershell -ExecutionPolicy Bypass -File models_3d/setup_3d.ps1
```

## Licencia

[MIT-0](LICENSE). Los pesos de los modelos tienen sus propias licencias (FLUX 3 Klein: FLUX Kommunity License).
