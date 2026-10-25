"""Worker de generación imagen → malla 3D imprimible (STL).

Se ejecuta con el Python del entorno `models_3d/venv`, lanzado por la GUI como
subproceso. Replica el flujo del Space oficial de Pixal3D (TencentARC/Pixal3D)
sobre trellis.cpp (C++/CUDA):

  1. FOV de la cámara estimado con MoGe-2 (camera.py), como el Space;
  2. trellis-cli --dump-post: malla completa ya limpiada con la cadena oficial
     (soldado, cierre de agujeros, remallado dual-contouring, eliminación de
     flotantes) + volumen PBR de la textura;
  3. post-replay (dos pasadas sobre el mismo volcado):
     - reducción QEM oficial (en GPU) al número de caras pedido, sin textura
       (el Space usa 1M por defecto) -> malla para imprimir;
     - misma reducción + desplegado UV + horneado de la textura (atlas
       TEXTURED_ATLAS) -> GLB pintado como el del Space, solo para verlo;
  4. reparación a 2-manifold y relleno de la piel hueca que generan los modelos
     (solidify.py) + STL en milímetros (Z arriba) + GLB + vistas previas.

Protocolo con la GUI (stdout, una línea por mensaje):
    PROGRESS: <texto>       progreso legible
    RESULT: <json>          resultado final (rutas de STL, GLB y vistas previas)
    ERROR: <texto>          fallo
"""

import argparse
import json
import struct
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
# --dump-post; post-replay lleva un parche para escribir la malla sin hornear
RUNTIME = TRELLIS_DIR / "runtime_main"
TRELLIS_EXE = RUNTIME / "trellis-cli.exe"
POST_REPLAY_EXE = RUNTIME / "post-replay.exe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_utils import export_stl, make_printable, render_turntable, repair_light  # noqa: E402
from solidify import solidify  # noqa: E402

# Resolución de la cascada: la máxima, la que usa el Space por defecto.
CASCADE_RES = 1536
# atlas de la textura del GLB pintado, el máximo (trellis-cli usa 2048 @1024)
TEXTURED_ATLAS = 4096
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


def stand_up_glb(path: Path):
    """El escritor de GLB de trellis.cpp gira (x,y,z)->(x,z,-y) para pasar de Z
    arriba (TRELLIS.2) a Y arriba, pero Pixal3D ya sale con Y arriba y el modelo
    queda tumbado. Se deshace con una rotación de +90° en X en el nodo raíz,
    sin tocar la geometría ni recodificar las texturas."""
    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_len])
    for i in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        gltf["nodes"][i]["rotation"] = [0.7071068, 0.0, 0.0, 0.7071068]
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    rest = data[20 + json_len:]  # chunk binario tal cual
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(js) + len(rest))
                     + struct.pack("<II", len(js), 0x4E4F534A) + js + rest)


def generate_mesh(image: str, work: Path, args, res: int, fov: float) -> tuple[Path, Path | None]:
    """Devuelve (PLY sin textura para imprimir, GLB pintado o None si falla)."""
    for exe in (TRELLIS_EXE, POST_REPLAY_EXE):
        if not exe.exists():
            raise RuntimeError(f"No se encuentra {exe}. Ejecuta models_3d/setup_3d.ps1.")
    dump = work / "mesh.bin"
    progress(f"Pixal3D @res{res}, FOV {fov:.1f}°...")
    run_logged([
        str(TRELLIS_EXE), image, str(work / "unused.glb"),
        "--models", str(TRELLIS_DIR / "models"),
        "--model", "pixal3d",
        "--res", str(res),
        "--seed", str(args.seed),
        "--steps", str(args.steps),
        "--fov", f"{fov:.3f}",
        "--dump-post", str(dump),
        "--require-gpu",
    ], "Pixal3D")
    if not dump.exists():
        raise RuntimeError("trellis-cli no generó la malla.")

    progress(f"Reduciendo a {args.faces // 1000}k caras (QEM en GPU)...")
    ply = work / "mesh.ply"
    run_logged([
        str(POST_REPLAY_EXE), str(dump), str(ply),
        "--no-remesh", "--no-bake", "--faces", str(args.faces),
    ], "QEM")

    progress("Horneando la textura...")
    textured = work / "color.glb"
    try:
        run_logged([
            str(POST_REPLAY_EXE), str(dump), str(textured),
            "--no-remesh", "--faces", str(args.faces), "--atlas", str(TEXTURED_ATLAS),
        ], "Textura")
    except RuntimeError as exc:  # la malla imprimible no depende de la textura
        progress(f"Sin textura ({exc.args[0].splitlines()[0]})")
    if not textured.exists():
        return ply, None
    stand_up_glb(textured)
    return ply, textured


def main():
    import trimesh

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--name", default="modelo")
    parser.add_argument("--res", type=int, default=CASCADE_RES, choices=(512, 1024, 1536))
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

    image = str(Path(args.image).resolve())
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.name}_pixal3d_{time.strftime('%Y%m%d_%H%M%S')}"
    t0 = time.time()

    fov = args.fov
    if fov <= 0:
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
        ply, textured = generate_mesh(image, work, args, args.res, fov)
        mesh = trimesh.load(ply, force="mesh", process=False)  # Pixal3D ya sale con Y arriba
        color_path = None
        if textured:
            color_path = out_dir / f"{stem}_color.glb"
            shutil.move(textured, color_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)

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
        "model": "pixal3d",
        "seed": args.seed,
        "fov": round(fov, 1),
        "stl": str(stl_path),
        "glb": str(glb_path),
        "glb_color": str(color_path) if color_path else None,
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
