"""Worker: image → printable 3D mesh (STL).

Runs with the Python of the `models_3d/venv` environment, launched by the app
as a subprocess. Replicates the flow of the official Pixal3D Space
(TencentARC/Pixal3D) on top of trellis.cpp (C++/CUDA):

  1. Camera FOV estimated with MoGe-2 (camera.py), like the Space;
  2. trellis-cli --dump-post: full mesh already cleaned with the official chain
     (welding, hole closing, dual-contouring remeshing, floater removal) +
     PBR texture volume;
  3. post-replay (two passes over the same dump):
     - official QEM reduction (on GPU) to the requested face count, untextured
       (the Space uses 1M by default) -> mesh to print;
     - same reduction + UV unwrapping + texture baking (TEXTURED_ATLAS atlas)
       -> painted GLB like the Space's, for viewing only;
  4. repair to 2-manifold and filling of the hollow skin the models generate
     (solidify.py) + STL in millimetres (Z up) + GLB + previews.

Protocol with the app (stdout, one line per message):
    PROGRESS: <text>        human-readable progress
    RESULT: <json>          final result (STL, GLB and preview paths)
    ERROR: <text>           failure
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
# trellis.cpp built from main (September 2026): ships Pixal3D, --steps and
# --dump-post; post-replay carries a patch to write the mesh without baking
RUNTIME = TRELLIS_DIR / "runtime_main"
TRELLIS_EXE = RUNTIME / "trellis-cli.exe"
POST_REPLAY_EXE = RUNTIME / "post-replay.exe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesh_utils import export_stl, make_printable, render_turntable, repair_light  # noqa: E402
from solidify import solidify  # noqa: E402

# Cascade resolution: the maximum, the Space's default.
CASCADE_RES = 1536
# texture atlas of the painted GLB, the maximum (trellis-cli uses 2048 @1024)
TEXTURED_ATLAS = 4096
DEFAULT_FOV = 49.13  # Pixal3D default if MoGe-2 is not available


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
        raise RuntimeError(f"{Path(cmd[0]).name} failed:\n" + "\n".join(tail))


def stand_up_glb(path: Path):
    """trellis.cpp's GLB writer rotates (x,y,z)->(x,z,-y) to go from Z-up
    (TRELLIS.2) to Y-up, but Pixal3D already outputs Y-up, so the model ends up
    lying down. Undo it with a +90° rotation about X on the root node, without
    touching the geometry or re-encoding the textures."""
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
    """Return (untextured PLY to print, painted GLB or None on failure)."""
    for exe in (TRELLIS_EXE, POST_REPLAY_EXE):
        if not exe.exists():
            raise RuntimeError(f"{exe} not found. Run models_3d/setup_3d.ps1.")
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
        raise RuntimeError("trellis-cli did not produce the mesh.")

    progress(f"Reducing to {args.faces // 1000}k faces (QEM on GPU)...")
    ply = work / "mesh.ply"
    run_logged([
        str(POST_REPLAY_EXE), str(dump), str(ply),
        "--no-remesh", "--no-bake", "--faces", str(args.faces),
    ], "QEM")

    progress("Baking the texture...")
    textured = work / "color.glb"
    try:
        run_logged([
            str(POST_REPLAY_EXE), str(dump), str(textured),
            "--no-remesh", "--faces", str(args.faces), "--atlas", str(TEXTURED_ATLAS),
        ], "Textura")
    except RuntimeError as exc:  # the printable mesh does not depend on the texture
        progress(f"No texture ({exc.args[0].splitlines()[0]})")
    if not textured.exists():
        return ply, None
    stand_up_glb(textured)
    return ply, textured


def main():
    import trimesh

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--name", default="model")
    parser.add_argument("--res", type=int, default=CASCADE_RES, choices=(512, 1024, 1536))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    # Horizontal camera FOV (Pixal3D). 0 = estimate it with MoGe-2.
    parser.add_argument("--fov", type=float, default=0.0)
    parser.add_argument("--faces", type=int, default=1000000)
    parser.add_argument("--height-mm", type=float, default=100.0)
    # voxel remeshing: guaranteed watertight, but some surface noise
    parser.add_argument("--watertight", action="store_true")
    # leave the hollow skin as the model outputs it (repair only)
    parser.add_argument("--no-fill", action="store_true")
    args = parser.parse_args()

    image = str(Path(args.image).resolve())
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.name}_pixal3d_{time.strftime('%Y%m%d_%H%M%S')}"
    t0 = time.time()

    fov = args.fov
    if fov <= 0:
        progress("Estimating the camera with MoGe-2...")
        try:
            from camera import estimate_fov_deg

            fov = estimate_fov_deg(image)
        except Exception as exc:  # noqa: BLE001
            progress(f"MoGe-2 unavailable ({exc}); using default FOV")
            fov = DEFAULT_FOV

    # the full-mesh dump takes hundreds of MB: temporary folder
    work = Path(tempfile.mkdtemp(prefix="realmkeeper3d_"))
    try:
        ply, textured = generate_mesh(image, work, args, args.res, fov)
        mesh = trimesh.load(ply, force="mesh", process=False)  # Pixal3D already outputs Y-up
        color_path = None
        if textured:
            color_path = out_dir / f"{stem}_color.glb"
            shutil.move(textured, color_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    filled = False
    if args.watertight:
        progress("Making the mesh watertight (voxels)...")
        mesh = make_printable(mesh, args.faces)
    else:
        solid, filled = solidify(mesh, fill=not args.no_fill, progress=progress)
        if solid is None:
            progress("Full repair failed; light repair...")
            mesh = repair_light(mesh)
        else:
            mesh = solid
    progress("Exporting STL...")
    stl_path = out_dir / f"{stem}.stl"
    info = export_stl(mesh, stl_path, args.height_mm)
    glb_path = out_dir / f"{stem}.glb"
    # with normals: without them viewers (and the web app) render it flat, unshaded
    mesh.export(glb_path, include_normals=True)  # to open in 3D viewers (untextured)

    progress("Rendering previews...")
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
    # the app reads the output as UTF-8 (the Windows console would be cp1252)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print("ERROR: " + str(exc).replace("\n", " | "), flush=True)
        sys.exit(1)
