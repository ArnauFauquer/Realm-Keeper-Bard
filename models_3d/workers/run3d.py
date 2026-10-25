"""Worker de generación imagen → malla 3D imprimible (STL).

Se ejecuta con el Python del entorno `models_3d/venv`, lanzado por la GUI como
subproceso. Replica el flujo del Space oficial de Pixal3D (TencentARC/Pixal3D)
sobre trellis.cpp (C++/CUDA):

  1. FOV de la cámara estimado con MoGe-2 (camera.py), como el Space;
  2. trellis-cli --no-texture --dump-post: malla completa ya limpiada con la
     cadena oficial (soldado, cierre de agujeros, remallado dual-contouring,
     eliminación de flotantes);
  3. post-replay: reducción QEM oficial (en GPU) al número de caras pedido
     (el Space usa 1M por defecto);
  4. reparación a 2-manifold y relleno de la piel hueca que generan los modelos
     (solidify.py) + STL en milímetros (Z arriba) + GLB + vistas previas.

Protocolo con la GUI (stdout, una línea por mensaje):
    PROGRESS: <texto>       progreso legible
    RESULT: <json>          resultado final (rutas de STL, GLB y vistas previas)
    ERROR: <texto>          fallo
"""

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent
TRELLIS_DIR = MODELS_DIR / "trellis"
# trellis.cpp compilado desde main (septiembre 2026): trae Pixal3D, --steps y
# --dump-post; post-replay lleva un parche para escribir la malla sin textura
RUNTIME = TRELLIS_DIR / "runtime_main"
TRELLIS_EXE = RUNTIME / "trellis-cli.exe"
POST_REPLAY_EXE = RUNTIME / "post-replay.exe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_utils import export_stl, make_printable, render_turntable, repair_light  # noqa: E402
from solidify import solidify  # noqa: E402

# Resolución de la cascada (el Space usa 1536 por defecto).
QUALITY = {
    "normal": {"res": 1024},
    "maxima": {"res": 1536},
}
MODEL_FAMILIES = ("pixal3d", "trellis")
DEFAULT_FOV = 49.13  # valor por defecto de Pixal3D si MoGe-2 no está disponible


def progress(msg: str):
    print(f"PROGRESS: {msg}", flush=True)


def run_logged(cmd: list[str], title: str):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", cwd=str(RUNTIME),
    )
    tail = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        tail = (tail + [line])[-15:]
        if line.startswith("[") and "/" in line[:6]:  # etapas "[3/7] ..."
            progress(f"{title} {line}")
    if proc.wait() != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} falló:\n" + "\n".join(tail))


def generate_mesh(image: str, work: Path, args, res: int, fov: float) -> Path:
    for exe in (TRELLIS_EXE, POST_REPLAY_EXE):
        if not exe.exists():
            raise RuntimeError(f"No se encuentra {exe}. Ejecuta models_3d/setup_3d.ps1.")
    dump = work / "mesh.bin"
    title = "Pixal3D" if args.model == "pixal3d" else "TRELLIS.2"
    progress(f"{title} @res{res}" + (f", FOV {fov:.1f}°" if args.model == "pixal3d" else "") + "...")
    cmd = [
        str(TRELLIS_EXE), image, str(work / "unused.glb"),
        "--models", str(TRELLIS_DIR / "models"),
        "--model", args.model,
        "--res", str(res),
        "--seed", str(args.seed),
        "--steps", str(args.steps),
        "--no-texture",
        "--dump-post", str(dump),
        "--require-gpu",
    ]
    if args.model == "pixal3d":
        cmd += ["--fov", f"{fov:.3f}"]
    run_logged(cmd, title)
    if not dump.exists():
        raise RuntimeError("trellis-cli no generó la malla.")

    progress(f"Reduciendo a {args.faces // 1000}k caras (QEM en GPU)...")
    ply = work / "mesh.ply"
    run_logged([
        str(POST_REPLAY_EXE), str(dump), str(ply),
        "--no-remesh", "--no-bake", "--faces", str(args.faces),
    ], "QEM")
    return ply


def main():
    import trimesh

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--name", default="modelo")
    parser.add_argument("--model", default="pixal3d", choices=MODEL_FAMILIES)
    parser.add_argument("--quality", default="maxima", choices=list(QUALITY))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    # FOV horizontal de la cámara (Pixal3D). 0 = estimarlo con MoGe-2.
    parser.add_argument("--fov", type=float, default=0.0)
    parser.add_argument("--faces", type=int, default=1000000)
    parser.add_argument("--height-mm", type=float, default=100.0)
    # remallado por vóxeles: estanca garantizada, pero algo de ruido superficial
    parser.add_argument("--watertight", action="store_true")
    # deja la piel hueca tal cual sale del modelo (solo se repara)
    parser.add_argument("--no-fill", action="store_true")
    args = parser.parse_args()

    q = QUALITY[args.quality]
    image = str(Path(args.image).resolve())
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.name}_{args.model}_{time.strftime('%Y%m%d_%H%M%S')}"
    t0 = time.time()

    fov = args.fov
    if args.model == "pixal3d" and fov <= 0:
        progress("Estimando la cámara con MoGe-2...")
        try:
            from camera import estimate_fov_deg

            fov = estimate_fov_deg(image)
        except Exception as exc:  # noqa: BLE001
            progress(f"MoGe-2 no disponible ({exc}); FOV por defecto")
            fov = DEFAULT_FOV

    # el volcado de la malla completa ocupa cientos de MB: carpeta temporal
    work = Path(tempfile.mkdtemp(prefix="realmkeeper3d_"))
    try:
        ply = generate_mesh(image, work, args, q["res"], fov)
        mesh = trimesh.load(ply, force="mesh", process=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if args.model == "trellis":
        # el volcado está en el espacio TRELLIS (Z arriba); Pixal3D ya sale con
        # Y arriba. El resto del flujo usa Y arriba (convención glTF).
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))

    filled = False
    if args.watertight:
        progress("Haciendo la malla estanca (vóxeles)...")
        mesh = make_printable(mesh, args.faces)
    else:
        solid, filled = solidify(mesh, fill=not args.no_fill, progress=progress)
        if solid is None:
            progress("Reparación completa fallida; reparación ligera...")
            mesh = repair_light(mesh)
        else:
            mesh = solid
    progress("Exportando STL...")
    stl_path = out_dir / f"{stem}.stl"
    info = export_stl(mesh, stl_path, args.height_mm)
    glb_path = out_dir / f"{stem}.glb"
    # con normales: sin ellas los visores (y la app web) la pintan plana, sin sombreado
    mesh.export(glb_path, include_normals=True)  # para abrirlo en visores 3D (sin textura)

    progress("Renderizando vistas previas...")
    preview_dir = out_dir / "previews"
    preview_dir.mkdir(exist_ok=True)
    previews = render_turntable(mesh, preview_dir, stem, pitch_deg=10)

    result = {
        "model": args.model,
        "quality": args.quality,
        "seed": args.seed,
        "fov": round(fov, 1),
        "stl": str(stl_path),
        "glb": str(glb_path),
        "previews": previews,
        "filled": filled,
        "seconds": round(time.time() - t0, 1),
        **info,
    }
    print("RESULT: " + json.dumps(result), flush=True)


if __name__ == "__main__":
    # la GUI lee la salida como UTF-8 (en Windows la consola sería cp1252)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print("ERROR: " + str(exc).replace("\n", " | "), flush=True)
        sys.exit(1)
