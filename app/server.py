"""App web server: exposes the generation workflows as an HTTP API and serves
the compiled browser frontend (web/dist).

Every generation goes into a queue (/api/jobs lists them all): GPU jobs (create,
transform, 3D) run one at a time in the same lane and background removal in a
separate one, so it doesn't wait behind a 3D model. Images are referenced by
their path relative to DATA_DIR ("generated_images/x.png") and only those under
ALLOWED_ROOTS are served/opened.
"""

import glob
import os
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from .background_removal import remove_background
from .config import (
    BASE_DIR, DATA_DIR, MODELS_3D_OUTPUT_DIR, OUTPUT_DIR, REFERENCES_DIR, THUMB_DIR, TRANSPARENT_DIR, UPLOAD_DIR,
)
from .generation import (
    generate_create,
    generate_transform,
    prepare_for_3d,
    prepare_for_3d_detailed,
)
from .image_utils import save_image_bytes
from .local_engine import LocalEngine
from .mesh_generation import (
    MESH_PREPARE_MODES,
    Mesh3DOptions,
    environment_ready,
    random_seed,
    run_mesh_generation,
    start_mesh_generation,
)
from .style_profile import CATEGORIES, StyleLibrary, load_style_library, save_style_library

WEB_DIST = BASE_DIR / "web" / "dist"

ALLOWED_ROOTS = {
    "generated_images": OUTPUT_DIR,
    "generated_transparent": TRANSPARENT_DIR,
    "generated_3d": MODELS_3D_OUTPUT_DIR,
    "uploads": UPLOAD_DIR,
    "references": REFERENCES_DIR,
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
LIBRARY_FOLDERS = {"images": OUTPUT_DIR, "transparent": TRANSPARENT_DIR, "references": REFERENCES_DIR}


# --------------------------------------------------------------- rutas
def to_rel(path: str | Path) -> str:
    return Path(path).resolve().relative_to(DATA_DIR.resolve()).as_posix()


def resolve_rel(rel: str) -> Path:
    """Frontend relative path -> absolute path, only within ALLOWED_ROOTS."""
    path = (DATA_DIR / rel).resolve()
    for root in ALLOWED_ROOTS.values():
        if path == root.resolve() or root.resolve() in path.parents:
            return path
    raise HTTPException(403, "Path outside the app folders.")


def resolve_image(rel: str) -> str:
    path = resolve_rel(rel)
    if not path.is_file():
        raise HTTPException(404, f"Image {rel} does not exist.")
    return str(path)


def image_item(path: str | Path) -> dict:
    rel = to_rel(path)
    try:
        with Image.open(path) as img:
            width, height = img.size
    except OSError:
        width = height = 0
    return {"kind": "image", "path": rel, "name": Path(path).name, "width": width, "height": height,
            "mtime": Path(path).stat().st_mtime}


def mesh_item(result: dict) -> dict:
    return {
        "kind": "mesh",
        **{k: v for k, v in result.items() if k not in ("stl", "glb", "glb_color", "previews")},
        "stl": to_rel(result["stl"]),
        "glb": to_rel(result["glb"]),
        "glb_color": to_rel(result["glb_color"]) if result.get("glb_color") else None,
        "previews": [to_rel(p) for p in result.get("previews", [])],
        "name": Path(result["stl"]).stem,
    }


# --------------------------------------------------------------- estado
class EngineState:
    def __init__(self):
        self.engine = LocalEngine()
        self.status = "stopped"  # stopped | starting | ready | error
        self.message = "Engine stopped."
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.status == "starting":
                return
            self.status, self.message = "starting", "Starting the local engine..."

        def worker():
            try:
                self.engine.ensure_running()
                self.status, self.message = "ready", "Local engine ready."
            except Exception as exc:  # noqa: BLE001
                self.status, self.message = "error", f"Failed to start: {exc}"

        threading.Thread(target=worker, daemon=True).start()

    def snapshot(self) -> dict:
        if self.status == "ready" and not self.engine.is_running():
            self.status, self.message = "stopped", "The engine has stopped."
        return {"status": self.status, "message": self.message}


class Job:
    def __init__(self, kind: str, label: str, lane: str, fn, model: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.lane = lane
        self.fn = fn
        self.model = model  # image model it needs ("krea" | "flux3"), or None
        self.status = "queued"  # queued | running | done | error | cancelled
        self.progress = ""
        self.results: list[dict] = []
        self.error = ""
        self.warning = ""
        self.created = time.time()
        self.started: float | None = None
        self.finished: float | None = None
        self.proc: subprocess.Popen | None = None
        self.cancelled = False

    def to_dict(self) -> dict:
        position = lanes[self.lane].position(self) if self.status == "queued" else 0
        return {"id": self.id, "kind": self.kind, "label": self.label, "status": self.status,
                "progress": self.progress, "results": self.results, "error": self.error,
                "warning": self.warning, "created": self.created, "started": self.started,
                "finished": self.finished, "position": position}


engine_state = EngineState()
style_library: StyleLibrary = load_style_library()
jobs: dict[str, Job] = {}
last = {"generated": None, "transparent": None}

KEEP_FINISHED = 80
# Group by model: loading Krea or FLUX 3 takes ~30-60 s, so jobs that use the
# already-loaded model go first. So nobody waits forever, the oldest job goes
# first once it has waited more than MAX_WAIT or after MAX_STREAK skips.
MAX_WAIT = 600
MAX_STREAK = 6


class Lane:
    """Queue for one job lane with a single worker."""

    def __init__(self, name: str, model_aware: bool):
        self.name = name
        self.model_aware = model_aware
        self.pending: list[Job] = []
        self.cond = threading.Condition()
        self.streak = 0  # consecutive jobs that have jumped ahead of the oldest
        self.model: str | None = None  # model of the last job that used one (loaded or loading)
        threading.Thread(target=self._worker, daemon=True).start()

    def put(self, job: Job):
        with self.cond:
            self.pending.append(job)
            self.cond.notify()

    def drop(self, job: Job):
        with self.cond:
            if job in self.pending:
                self.pending.remove(job)

    def _order(self) -> list[Job]:
        """Order in which pending jobs will run (ignoring the wait limit)."""
        if not self.model_aware or not self.pending:
            return list(self.pending)
        oldest = self.pending[0]
        if self.streak >= MAX_STREAK or time.time() - oldest.created > MAX_WAIT:
            return [oldest, *self.pending[1:]]
        loaded = self.model or engine_state.engine.loaded
        # stable: within each group, arrival order is kept
        return sorted(self.pending, key=lambda j: j.model not in (None, loaded))

    def position(self, job: Job) -> int:
        with self.cond:
            order = self._order()
            return order.index(job) + 1 if job in order else 0

    def _next(self) -> Job:
        with self.cond:
            while not self.pending:
                self.cond.wait()
            job = self._order()[0]
            self.streak = 0 if job is self.pending[0] else self.streak + 1
            self.pending.remove(job)
            self.model = job.model or self.model
            return job

    def _worker(self):
        while True:
            job = self._next()
            job.status, job.started = "running", time.time()
            try:
                job.fn(job)
                job.status = "cancelled" if job.cancelled else "done"
            except Exception as exc:  # noqa: BLE001
                job.status = "cancelled" if job.cancelled else "error"
                job.error = str(exc)[-1500:]
            finally:
                job.proc = None
                job.finished = time.time()


# "gpu": image models and 3D do not fit in VRAM together. "light": background removal.
lanes = {"gpu": Lane("gpu", model_aware=True), "light": Lane("light", model_aware=False)}


def run_job(kind: str, label: str, fn, lane: str = "gpu", model: str | None = None) -> dict:
    job = Job(kind, label, lane, fn, model)
    jobs[job.id] = job
    finished = [j for j in jobs.values() if j.finished]
    for old in finished[:max(0, len(finished) - KEEP_FINISHED)]:
        del jobs[old.id]
    lanes[lane].put(job)
    return job.to_dict()


def short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1] + "…"


def finish_image(job: Job, image_bytes: bytes, mime_type: str, prefix: str, remove_bg: bool):
    """Save the result and, if requested, chain background removal."""
    path = save_image_bytes(image_bytes, mime_type, OUTPUT_DIR, prefix)
    last["generated"] = path
    job.results.append(image_item(path))
    if not remove_bg:
        return
    job.progress = "Image ready. Removing background..."
    try:
        out = save_image_bytes(remove_background(path), "image/png", TRANSPARENT_DIR, "no_background")
    except Exception as exc:  # noqa: BLE001
        job.warning = f"Image generated, but the background could not be removed: {exc}"
        return
    last["transparent"] = out
    job.results.append(image_item(out))


# --------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(_app: FastAPI):
    engine_state.start()
    yield
    # Free the loaded image model (VRAM and RAM).
    engine_state.engine.stop()


app = FastAPI(title="RealmKeeper Bard", lifespan=lifespan)


@app.get("/api/engine")
def get_engine():
    return engine_state.snapshot()


@app.post("/api/engine/start")
def post_engine_start():
    engine_state.start()
    return engine_state.snapshot()


@app.get("/api/options")
def get_options():
    return {
        "categories": list(CATEGORIES),
        "mesh_prepare_modes": [{"label": l, "value": v} for l, v in MESH_PREPARE_MODES],
        "mesh_ready": environment_ready(),
    }


def newest_image(folder: Path) -> Path | None:
    files = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS]
    return max(files, key=lambda p: p.stat().st_mtime, default=None)


@app.get("/api/last")
def get_last():
    """Latest image of the session; if there is none yet, the newest in the folder."""
    out = {}
    for key, folder in (("generated", OUTPUT_DIR), ("transparent", TRANSPARENT_DIR)):
        path = last[key] if last[key] and os.path.exists(last[key]) else newest_image(folder)
        out[key] = to_rel(path) if path else None
    return out


class CreateBody(BaseModel):
    category: str
    description: str
    style_id: str = ""
    species_id: str = ""  # empty = no anatomy
    remove_bg: bool = False


@app.post("/api/create")
def post_create(body: CreateBody):
    if not body.description.strip():
        raise HTTPException(400, "Describe what you want to generate.")
    profile = style_library.resolve(body.style_id, body.species_id)

    def fn(job: Job):
        job.progress = "Generating image with Krea 2..."
        data, mime = generate_create(engine_state.engine, profile, body.category, body.description,
                                     bool(body.species_id))
        finish_image(job, data, mime, body.category, body.remove_bg)

    return run_job("create", f"{body.category}: {short(body.description)}", fn, model="krea")


class TransformBody(BaseModel):
    reference: str
    is_map: bool = False
    extra: str = ""
    style_id: str = ""
    species_id: str = ""  # empty = no anatomy
    remove_bg: bool = False


@app.post("/api/transform")
def post_transform(body: TransformBody):
    ref = resolve_image(body.reference)
    profile = style_library.resolve(body.style_id, body.species_id)

    def fn(job: Job):
        job.progress = "Transforming with FLUX 3..."
        data, mime = generate_transform(engine_state.engine, profile, ref, body.extra, body.is_map,
                                        bool(body.species_id))
        finish_image(job, data, mime, "mapa_estilizado" if body.is_map else "estilizado", body.remove_bg)

    return run_job("transform", Path(ref).name, fn, model="flux3")


class SourceBody(BaseModel):
    source: str


@app.post("/api/remove-bg")
def post_remove_bg(body: SourceBody):
    src = resolve_image(body.source)

    def fn(job: Job):
        job.progress = "Removing background..."
        out = save_image_bytes(remove_background(src), "image/png", TRANSPARENT_DIR, "no_background")
        last["transparent"] = out
        job.results.append(image_item(out))

    return run_job("remove_bg", Path(src).name, fn, lane="light")


class MeshBody(BaseModel):
    source: str
    prepare: str = "detailed"
    expression: str = ""
    height_mm: float = Field(100, ge=10, le=999)
    faces_k: int = Field(1000, ge=50, le=3000)
    variants: int = Field(1, ge=1, le=6)


@app.post("/api/mesh")
def post_mesh(body: MeshBody):
    if not environment_ready():
        raise HTTPException(400, "The 3D environment is missing: run models_3d\\setup_3d.ps1.")
    source = resolve_image(body.source)
    profile = style_library.resolve()  # the 3D style is shared by all templates
    options = Mesh3DOptions(max_faces=body.faces_k * 1000,
                            height_mm=body.height_mm)

    def fn(job: Job):
        image = source
        if body.prepare != "none":
            detailed = body.prepare == "detailed"
            tag = "sculpture" if detailed else "clay"
            job.progress = f"Preparing the image with FLUX 3 ({tag})..."
            if detailed:
                data, mime = prepare_for_3d_detailed(engine_state.engine, profile, source, body.expression)
            else:
                data, mime = prepare_for_3d(engine_state.engine, source)
            raw = save_image_bytes(data, mime, OUTPUT_DIR, tag)
            image = save_image_bytes(remove_background(raw), "image/png", TRANSPARENT_DIR, f"{tag}_no_background")
            job.results.append({**image_item(image), "role": "prepared"})
        for i in range(body.variants):
            if job.cancelled:
                break
            options.seed = random_seed()
            prefix = f"[{i + 1}/{body.variants}] " if body.variants > 1 else ""
            job.proc = start_mesh_generation(image, options)

            def on_progress(msg, prefix=prefix):
                job.progress = prefix + msg

            job.results.append(mesh_item(run_mesh_generation(job.proc, on_progress)))

    variants = f" ×{body.variants}" if body.variants > 1 else ""
    return run_job("mesh", f"{Path(source).name}{variants}", fn,
                   model=None if body.prepare == "none" else "flux3")


@app.get("/api/jobs")
def get_jobs():
    return [job.to_dict() for job in list(jobs.values())]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    if job.status not in ("queued", "running"):
        return job.to_dict()
    job.cancelled = True
    if job.status == "queued":
        lanes[job.lane].drop(job)
        job.status, job.finished = "cancelled", time.time()
        return job.to_dict()
    proc = job.proc
    if proc and proc.poll() is None:
        if os.name == "nt":
            # the 3D worker in turn launches trellis-cli: kill the whole tree
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            proc.kill()
    job.progress = "Cancelling..."
    return job.to_dict()


@app.post("/api/uploads")
async def post_upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTS:
        raise HTTPException(400, "Unsupported image format.")
    stem = Path(file.filename).stem[:40] or "imagen"
    out = UPLOAD_DIR / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"
    with out.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return image_item(out)


@app.get("/api/library")
def get_library(folder: str = "images", offset: int = 0, limit: int = 60):
    if folder == "models":
        files = sorted((p for p in MODELS_3D_OUTPUT_DIR.glob("*.glb") if not p.stem.endswith("_color")),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        items = []
        for glb in files[offset:offset + limit]:
            stl = glb.with_suffix(".stl")
            color = glb.with_name(f"{glb.stem}_color.glb")
            preview = MODELS_3D_OUTPUT_DIR / "previews" / f"{glb.stem}_00.png"
            items.append({
                "kind": "mesh", "name": glb.stem, "glb": to_rel(glb),
                "stl": to_rel(stl) if stl.exists() else None,
                "glb_color": to_rel(color) if color.exists() else None,
                "previews": [to_rel(preview)] if preview.exists() else [],
                "mtime": glb.stat().st_mtime,
            })
        return {"items": items, "total": len(files)}
    root = LIBRARY_FOLDERS.get(folder)
    if root is None:
        raise HTTPException(400, "Unknown folder.")
    files = sorted((p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    items = [{"kind": "image", "path": to_rel(p), "name": p.name, "mtime": p.stat().st_mtime}
             for p in files[offset:offset + limit]]
    return {"items": items, "total": len(files)}


class OpenBody(BaseModel):
    path: str


@app.post("/api/open")
def post_open(body: OpenBody):
    """Open a file or folder with the Windows application (the app is local)."""
    path = resolve_rel(body.path)
    if not path.exists():
        raise HTTPException(404, "Does not exist.")
    os.startfile(path)
    return {"ok": True}


@app.post("/api/delete")
def post_delete(body: OpenBody):
    """Delete an image or 3D model (its .glb with the .stl, the _color.glb and the
    previews) from the library, along with its cached thumbnails."""
    path = resolve_rel(body.path)
    if not path.is_file():
        raise HTTPException(404, "Does not exist.")
    rel = to_rel(path)
    used_by = [sp["name"] for sp in style_library.to_dict()["species"] if sp.get("species_ref") == rel]
    if used_by:
        raise HTTPException(409, f"It is the reference of species {', '.join(used_by)}; change it before deleting.")
    if path.suffix.lower() == ".glb":
        targets = [path, path.with_suffix(".stl"), path.with_name(f"{path.stem}_color.glb"),
                   *(MODELS_3D_OUTPUT_DIR / "previews").glob(f"{path.stem}_*.png"),
                   THUMB_DIR / f"{path.stem}_normals.glb"]
    else:
        targets = [path]
    for target in targets:
        if target.is_file():
            thumbs = THUMB_DIR.glob(f"{glob.escape(to_rel(target).replace('/', '__'))}_*.webp")
            for thumb in [target, *thumbs]:
                thumb.unlink(missing_ok=True)
    for key, value in last.items():
        if value and Path(value).resolve() == path:
            last[key] = None
    return {"ok": True}


def style_payload() -> dict:
    data = style_library.to_dict()
    for sp in data["species"]:
        # the saved path may not exist: the frontend previews only the resolved one
        ref = style_library.resolve(None, sp["id"]).species_ref_path()
        sp["species_ref_resolved"] = to_rel(ref) if ref else None
    return data


@app.get("/api/style")
def get_style():
    return style_payload()


class StylePresetBody(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    style_prompt: str
    constraints: str


class SpeciesPresetBody(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    species_prompt: str
    species_ref: str = ""


class StyleBody(BaseModel):
    styles: list[StylePresetBody] = Field(min_length=1)
    species: list[SpeciesPresetBody]
    active_style: str
    active_species: str = ""
    pov: dict[str, str]
    style_3d: str
    map_style: str
    map_constraints: str


@app.put("/api/style")
def put_style(body: StyleBody):
    """Save the whole library (templates + shared) at once."""
    global style_library
    for sp in body.species:
        if sp.species_ref:
            resolve_rel(sp.species_ref)
    for group in (body.styles, body.species):
        if len({p.id for p in group}) != len(group):
            raise HTTPException(400, "Two templates share the same id.")
    style_library = StyleLibrary.from_dict(body.model_dump())
    save_style_library(style_library)
    return style_payload()


# --------------------------------------------------------------- ficheros
def glb_with_normals(path: Path) -> Path:
    """GLBs from before 25 Oct 2026 were exported without normals and the viewer
    renders them flat. Return a cached copy with per-vertex normals (newer ones
    already have them and are served as is)."""
    import json
    import struct

    import numpy as np

    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_len])
    prim = gltf["meshes"][0]["primitives"][0]
    if "NORMAL" in prim["attributes"] or len(gltf["meshes"]) != 1 or len(gltf["meshes"][0]["primitives"]) != 1:
        return path
    cached = THUMB_DIR / f"{path.stem}_normals.glb"
    if cached.exists() and cached.stat().st_mtime >= path.stat().st_mtime:
        return cached

    bin_start = 20 + json_len + 8
    binary = data[bin_start:bin_start + struct.unpack_from("<I", data, 20 + json_len)[0]]
    dtypes = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}

    def read(accessor_idx: int, width: int) -> np.ndarray:
        acc = gltf["accessors"][accessor_idx]
        view = gltf["bufferViews"][acc["bufferView"]]
        offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        arr = np.frombuffer(binary, dtypes[acc["componentType"]], acc["count"] * width, offset)
        return arr.reshape(-1, width) if width > 1 else arr

    pos = read(prim["attributes"]["POSITION"], 3).astype(np.float64)
    faces = read(prim["indices"], 1).reshape(-1, 3)
    face_n = np.cross(pos[faces[:, 1]] - pos[faces[:, 0]], pos[faces[:, 2]] - pos[faces[:, 0]])
    normals = np.zeros_like(pos)
    for k in range(3):
        np.add.at(normals, faces[:, k], face_n)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    binary = bytearray(binary) + b"\0" * (-len(binary) % 4)
    gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": normals.size * 4,
                                "target": 34962})
    binary += normals.astype(np.float32).tobytes()
    gltf["accessors"].append({"bufferView": len(gltf["bufferViews"]) - 1, "componentType": 5126,
                              "count": len(normals), "type": "VEC3"})
    prim["attributes"]["NORMAL"] = len(gltf["accessors"]) - 1
    gltf["buffers"][0]["byteLength"] = len(binary)

    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = (struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(binary))
           + struct.pack("<II", len(js), 0x4E4F534A) + js
           + struct.pack("<II", len(binary), 0x004E4942) + bytes(binary))
    cached.write_bytes(out)
    return cached


@app.get("/files/{rel:path}")
def get_file(rel: str):
    path = resolve_rel(rel)
    if not path.is_file():
        raise HTTPException(404)
    if path.suffix.lower() == ".glb":
        try:
            return FileResponse(glb_with_normals(path), media_type="model/gltf-binary")
        except Exception:  # noqa: BLE001 - odd GLB: better flat than nothing
            pass
    return FileResponse(path)


@app.get("/thumbs/{rel:path}")
def get_thumb(rel: str, s: int = 360):
    """Cached WebP thumbnail (the library has hundreds of ~1 MP images)."""
    path = resolve_rel(rel)
    if not path.is_file():
        raise HTTPException(404)
    size = max(64, min(s, 1024))
    thumb = THUMB_DIR / f"{rel.replace('/', '__')}_{size}.webp"
    if not thumb.exists() or thumb.stat().st_mtime < path.stat().st_mtime:
        with Image.open(path) as img:
            img.thumbnail((size, size))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(thumb, "WEBP", quality=82)
    return FileResponse(thumb, headers={"Cache-Control": "max-age=86400"})


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
