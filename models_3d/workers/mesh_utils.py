"""Post-proceso de mallas: malla estanca para imprimir (vóxeles + reproyección),
exportación a STL (eje Z arriba, escalado a milímetros) y render de vistas
previas por GPU (OpenGL, con respaldo por software) para la GUI."""

import math
from pathlib import Path

import numpy as np
import pymeshlab
import trimesh
from PIL import Image, ImageDraw


def to_single_mesh(obj) -> trimesh.Trimesh:
    """Convierte una escena (GLB con varios nodos) en una única malla,
    aplicando las transformaciones de cada nodo."""
    if isinstance(obj, trimesh.Scene):
        meshes = [g for g in obj.dump(concatenate=False) if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise RuntimeError("El modelo generado no contiene ninguna malla.")
        return meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes)
    return obj


def clean_mesh(mesh: trimesh.Trimesh, max_faces: int) -> trimesh.Trimesh:
    """Elimina islas pequeñas y caras degeneradas y reduce el número de caras
    con decimación cuádrica (pymeshlab) si supera `max_faces`."""
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
    # suelda las costuras UV (vértices duplicados en la misma posición); el
    # umbral por defecto (1% de la diagonal) se comería detalle fino
    ms.meshing_merge_close_vertices(threshold=pymeshlab.PercentageValue(0.01))
    ms.meshing_remove_duplicate_faces()
    ms.meshing_remove_null_faces()
    # quita "flotantes": componentes con menos del 1% del diámetro
    ms.meshing_remove_connected_component_by_diameter(
        mincomponentdiag=pymeshlab.PercentageValue(1)
    )
    # decimar ANTES de reparar: tras close_holes la decimación cuádrica deja de
    # reducir en mallas grandes (p. ej. la malla completa de TRELLIS.2)
    if max_faces > 0 and ms.current_mesh().face_number() > max_faces:
        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=max_faces, preservenormal=True, planarquadric=True
        )
    try:  # cierra agujeros pequeños para que el STL sea imprimible
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_close_holes(maxholesize=200)
    except pymeshlab.PyMeshLabException:
        pass
    m = ms.current_mesh()
    out = trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=True)
    out.fix_normals()
    return out


def subdivide_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Una iteración de subdivisión Loop (x4 caras): redondea las facetas planas
    de una malla ya reducida sin inventar detalle. clean_mesh la vuelve a
    reducir después al máximo de caras pedido."""
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
    ms.meshing_merge_close_vertices(threshold=pymeshlab.PercentageValue(0.01))
    ms.meshing_repair_non_manifold_edges()
    ms.meshing_surface_subdivision_loop(iterations=1, threshold=pymeshlab.PercentageValue(0))
    m = ms.current_mesh()
    return trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=False)


def repair_light(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Reparación que no toca la forma: quita caras duplicadas o degeneradas,
    separa aristas/vértices no-manifold, cierra agujeritos y unifica la
    orientación. La malla del remallado oficial de TRELLIS ya es casi estanca;
    lo que quede lo corrige cualquier laminador."""
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
    ms.meshing_remove_duplicate_faces()
    ms.meshing_remove_null_faces()
    try:
        ms.meshing_repair_non_manifold_edges(method=0)
        ms.meshing_repair_non_manifold_vertices()
        ms.meshing_close_holes(maxholesize=100)
        ms.meshing_re_orient_faces_coherently()
    except pymeshlab.PyMeshLabException:
        pass
    m = ms.current_mesh()
    return trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=False)


def make_printable(mesh: trimesh.Trimesh, max_faces: int, grid: int = 1024) -> trimesh.Trimesh:
    """Malla estanca (watertight/manifold) lista para imprimir, sin perder detalle.

    La salida de TRELLIS.2 trae cientos de agujeritos, aristas no-manifold y
    estructuras internas; los reparadores clásicos (pymeshfix, close_holes) o no
    la cierran o destrozan el modelo. En su lugar:
      1. superficie de referencia: la malla tal cual si es densa, o subdividida
         (Loop) si viene reducida y tiene facetas;
      2. vóxeles: se muestrea la superficie en una rejilla de `grid` celdas en el
         eje mayor, se dilata una celda (cierra los agujeros) y se rellena el
         interior; marching cubes da una superficie cerrada por construcción;
      3. reducción rápida de caras (fast-simplification) hasta `max_faces`;
      4. reproyección de cada vértice sobre la superficie de referencia: la
         topología cerrada sale del vóxel y la forma exacta, del original.
    """
    import fast_simplification
    from scipy import ndimage
    from skimage import measure

    # la malla completa de TRELLIS (sin textura, millones de caras) ya no tiene
    # facetas; la reducida del GLB texturizado sí: esa se subdivide
    ref = subdivide_mesh(mesh) if len(mesh.faces) < 1_500_000 else mesh
    lo, hi = ref.bounds
    pitch = float((hi - lo).max()) / grid
    # ~4 muestras por celda de superficie: ninguna celda atravesada queda vacía
    samples, _ = trimesh.sample.sample_surface(ref, int(ref.area / (pitch * 0.5) ** 2))
    idx = np.floor((samples - lo) / pitch).astype(np.int32) + 2
    occ = np.zeros(idx.max(axis=0) + 3, dtype=bool)
    occ[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    del samples, idx
    # sin erosión posterior: la capa extra se elimina al reproyectar y evita que
    # las partes finas (filos, dedos) se rompan en la rejilla
    occ = ndimage.binary_fill_holes(ndimage.binary_dilation(occ))
    field = ndimage.gaussian_filter(occ.astype(np.float32), 0.8)
    del occ
    verts, faces, _, _ = measure.marching_cubes(field, 0.5)
    del field
    verts = (verts - 2) * pitch + lo
    faces = faces[:, ::-1]  # normales hacia fuera

    if len(faces) > max_faces > 0:
        verts, faces = fast_simplification.simplify(
            verts.astype(np.float32), faces.astype(np.int32),
            target_reduction=1 - max_faces / len(faces),
        )

    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=ref.vertices, face_matrix=ref.faces))
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.asarray(verts, np.float64),
                               face_matrix=np.asarray(faces, np.int32)))
    ms.set_current_mesh(1)
    # piezas sueltas diminutas (motas del vóxel)
    ms.meshing_remove_connected_component_by_diameter(
        mincomponentdiag=pymeshlab.PercentageValue(1)
    )
    ms.apply_coord_taubin_smoothing(stepsmoothnum=4)
    before = ms.current_mesh().vertex_matrix().copy()
    ms.transfer_attributes_per_vertex(
        sourcemesh=0, targetmesh=1, geomtransfer=True,
        upperbound=pymeshlab.PercentageValue(1),
    )
    m = ms.current_mesh()
    after = m.vertex_matrix().copy()
    # En zonas muy finas dos vértices distintos pueden caer en el mismo punto
    # (el STL los fusionaría y aparecerían aristas no-manifold): esos vuelven a
    # su posición del vóxel, que es cerrada por construcción.
    for _ in range(3):
        key = np.round(after / (pitch * 1e-3)).astype(np.int64)
        _, inverse, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        clash = counts[inverse.ravel()] > 1
        if not clash.any():
            break
        after[clash] = before[clash]
    return trimesh.Trimesh(after, m.face_matrix(), process=False)


def export_stl(mesh: trimesh.Trimesh, path: Path, height_mm: float) -> dict:
    """Los modelos generan en Y-arriba (convención glTF); los laminadores de
    impresión 3D esperan Z-arriba. Se rota, se escala a `height_mm` de alto y se
    apoya el modelo sobre la cama (z = 0) centrado en XY."""
    m = mesh.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    extents = m.extents
    if height_mm > 0 and extents[2] > 0:
        m.apply_scale(height_mm / extents[2])
    bmin, bmax = m.bounds
    m.apply_translation([-(bmin[0] + bmax[0]) / 2, -(bmin[1] + bmax[1]) / 2, -bmin[2]])
    m.export(path)
    return {
        "faces": int(len(m.faces)),
        "watertight": is_manifold(m),
        "size_mm": [round(float(v), 1) for v in m.extents],
    }


def is_manifold(mesh: trimesh.Trimesh) -> bool:
    """Estanca y 2-manifold según manifold3d (la librería de booleanas que usan
    muchos laminadores); más fiable que is_watertight de trimesh."""
    try:
        import manifold3d

        mf = manifold3d.Manifold(manifold3d.Mesh(
            vert_properties=np.asarray(mesh.vertices, np.float32),
            tri_verts=np.asarray(mesh.faces, np.uint32),
        ))
        return mf.status() == manifold3d.Error.NoError
    except Exception:  # noqa: BLE001
        return bool(mesh.is_watertight)


def _face_colors(mesh: trimesh.Trimesh) -> np.ndarray | None:
    """Color RGB por cara a partir de la textura/colores de vértice, si los hay."""
    try:
        visual = mesh.visual
        if visual.kind not in ("texture", "vertex", "face"):
            return None  # sin color propio (trimesh pondría un gris por defecto)
        if isinstance(visual, trimesh.visual.TextureVisuals):
            visual = visual.to_color()
        vc = np.asarray(visual.vertex_colors)[:, :3].astype(np.float32)
        if len(vc) != len(mesh.vertices):
            return None
        return vc[mesh.faces].mean(axis=1)
    except Exception:  # noqa: BLE001 - sin textura válida se usa el color por defecto
        return None


_VERT_SHADER = """
#version 330
uniform mat3 rot;
in vec3 in_pos;
in vec3 in_normal;
in vec3 in_color;
out vec3 v_normal;
out vec3 v_color;
void main() {
    vec3 p = rot * in_pos;
    v_normal = rot * in_normal;
    v_color = in_color;
    // ortográfica; z hacia el observador = más cerca
    gl_Position = vec4(p.x, p.y, -p.z * 0.5, 1.0);
}
"""
_FRAG_SHADER = """
#version 330
uniform vec3 light;
in vec3 v_normal;
in vec3 v_color;
out vec4 f_color;
void main() {
    vec3 n = normalize(v_normal);
    if (n.z < 0.0) n = -n;  // caras mal orientadas: se iluminan igual
    float shade = 0.42 + 0.78 * max(dot(n, light), 0.0);
    f_color = vec4(min(v_color * shade, vec3(1.0)), 1.0);
}
"""


def _view_matrix(yaw: float, pitch: float) -> np.ndarray:
    rx = np.array(
        [[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]]
    )
    ry = np.array(
        [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
    )
    return rx @ ry


def _vertex_colors(mesh: trimesh.Trimesh) -> np.ndarray | None:
    try:
        visual = mesh.visual
        if visual.kind not in ("texture", "vertex"):
            return None
        if isinstance(visual, trimesh.visual.TextureVisuals):
            visual = visual.to_color()
        vc = np.asarray(visual.vertex_colors)[:, :3].astype(np.float32) / 255.0
        return vc if len(vc) == len(mesh.vertices) else None
    except Exception:  # noqa: BLE001
        return None


def _render_gpu(mesh, out_dir, stem, frames, size, pitch_deg, only, smooth=True) -> list[str]:
    """Render por GPU (OpenGL vía moderngl): z-buffer, MSAA 8x y sombreado suave
    (normales por vértice, como un visor 3D) o plano por cara (`smooth=False`,
    útil para inspeccionar la triangulación)."""
    import moderngl

    verts = mesh.vertices - mesh.bounding_box.centroid
    verts = verts * (0.84 / max(np.linalg.norm(verts, axis=1).max(), 1e-6))
    faces = np.asarray(mesh.faces)
    tri = verts[faces].astype(np.float32)  # (F, 3, 3) sin indexar: normal por cara
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    if smooth:
        normals = np.asarray(mesh.vertex_normals, np.float32)[faces]
    else:
        normals = np.repeat(fn[:, None, :], 3, axis=1).astype(np.float32)
    vc = _vertex_colors(mesh)
    if vc is None:
        colors = np.full(tri.shape, [196 / 255, 178 / 255, 150 / 255], np.float32)
    else:
        colors = vc[faces].astype(np.float32)
    data = np.concatenate([tri, normals, colors], axis=2).reshape(-1, 9)

    ctx = moderngl.create_standalone_context()
    try:
        prog = ctx.program(vertex_shader=_VERT_SHADER, fragment_shader=_FRAG_SHADER)
        light = np.array([0.35, 0.55, 0.75])
        prog["light"].value = tuple(light / np.linalg.norm(light))
        vbo = ctx.buffer(data.astype("f4").tobytes())
        vao = ctx.vertex_array(prog, [(vbo, "3f 3f 3f", "in_pos", "in_normal", "in_color")])
        msaa = ctx.framebuffer(
            color_attachments=[ctx.renderbuffer((size, size), 4, samples=8)],
            depth_attachment=ctx.depth_renderbuffer((size, size), samples=8),
        )
        resolved = ctx.framebuffer(color_attachments=[ctx.texture((size, size), 4)])
        ctx.enable(moderngl.DEPTH_TEST)
        paths = []
        for i in range(frames):
            if only is not None and i not in only:
                continue
            yaw = 2 * math.pi * i / frames + math.radians(30)
            # moderngl espera matrices por columnas
            prog["rot"].write(_view_matrix(yaw, math.radians(pitch_deg)).T.astype("f4").tobytes())
            msaa.use()
            msaa.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
            vao.render(moderngl.TRIANGLES)
            ctx.copy_framebuffer(resolved, msaa)
            raw = resolved.read(components=4)
            img = Image.frombytes("RGBA", (size, size), raw).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            path = out_dir / f"{stem}_{i:02d}.png"
            img.save(path)
            paths.append(str(path))
        return paths
    finally:
        ctx.release()


def render_turntable(
    mesh: trimesh.Trimesh,
    out_dir: Path,
    stem: str,
    frames: int = 12,
    size: int = 560,
    pitch_deg: float = 18.0,
    only: set[int] | None = None,
    smooth: bool = True,
) -> list[str]:
    """Renderiza `frames` vistas girando alrededor del eje vertical (Y).
    Usa la GPU (OpenGL) si está disponible; si no, el algoritmo del pintor en
    CPU. `only` limita qué fotogramas se renderizan. Devuelve las rutas."""
    try:
        return _render_gpu(mesh, out_dir, stem, frames, size, pitch_deg, only, smooth)
    except Exception:  # noqa: BLE001 - sin OpenGL: render por software
        pass
    verts = mesh.vertices - mesh.bounding_box.centroid
    scale = 0.84 / max(np.linalg.norm(verts, axis=1).max(), 1e-6)
    verts = verts * scale
    faces = mesh.faces
    base = _face_colors(mesh)
    if base is None:
        base = np.tile(np.array([[196, 178, 150]], np.float32), (len(faces), 1))

    ss = 2  # supermuestreo para suavizar bordes
    px = size * ss
    light = np.array([0.35, 0.55, 0.75])
    light /= np.linalg.norm(light)
    pitch = math.radians(pitch_deg)
    rx = np.array(
        [[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]]
    )

    paths = []
    for i in range(frames):
        if only is not None and i not in only:
            continue
        yaw = 2 * math.pi * i / frames + math.radians(30)
        ry = np.array(
            [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
        )
        v = verts @ (rx @ ry).T
        tri = v[faces]
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        norm_len = np.linalg.norm(normals, axis=1)
        visible = (normals[:, 2] > 0) & (norm_len > 0)
        idx = np.nonzero(visible)[0]
        n = normals[idx] / norm_len[idx, None]
        shade = 0.42 + 0.78 * np.clip(n @ light, 0, 1)
        colors = np.clip(base[idx] * shade[:, None], 0, 255).astype(np.uint8)
        order = np.argsort(tri[idx, :, 2].mean(axis=1))  # de atrás hacia delante

        xy = tri[idx][:, :, :2]
        screen = np.empty_like(xy)
        screen[..., 0] = (xy[..., 0] * 0.5 + 0.5) * px
        screen[..., 1] = (0.5 - xy[..., 1] * 0.5) * px

        img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for j in order:
            c = colors[j]
            draw.polygon([tuple(p) for p in screen[j]], fill=(int(c[0]), int(c[1]), int(c[2]), 255))
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        path = out_dir / f"{stem}_{i:02d}.png"
        img.save(path)
        paths.append(str(path))
    return paths
