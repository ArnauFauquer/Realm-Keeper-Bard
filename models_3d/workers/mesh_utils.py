"""Mesh post-processing: watertight printable mesh (voxels + reprojection),
STL export (Z up, scaled to millimetres) and GPU preview rendering (OpenGL,
with a software fallback) for the app."""

import math
from pathlib import Path

import numpy as np
import pymeshlab
import trimesh
from PIL import Image, ImageDraw


def clean_mesh(mesh: trimesh.Trimesh, max_faces: int) -> trimesh.Trimesh:
    """Remove small islands and degenerate faces and reduce the face count
    with quadric decimation (pymeshlab) if it exceeds `max_faces`."""
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
    # weld UV seams (duplicate vertices at the same position); the default
    # threshold (1% of the diagonal) would eat fine detail
    ms.meshing_merge_close_vertices(threshold=pymeshlab.PercentageValue(0.01))
    ms.meshing_remove_duplicate_faces()
    ms.meshing_remove_null_faces()
    # remove "floaters": components smaller than 1% of the diameter
    ms.meshing_remove_connected_component_by_diameter(
        mincomponentdiag=pymeshlab.PercentageValue(1)
    )
    # decimate BEFORE repairing: after close_holes quadric decimation stops
    # reducing on large meshes (e.g. the full TRELLIS.2 mesh)
    if max_faces > 0 and ms.current_mesh().face_number() > max_faces:
        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=max_faces, preservenormal=True, planarquadric=True
        )
    try:  # close small holes so the STL is printable
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_close_holes(maxholesize=200)
    except pymeshlab.PyMeshLabException:
        pass
    m = ms.current_mesh()
    out = trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=True)
    out.fix_normals()
    return out


def subdivide_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """One Loop subdivision iteration (x4 faces): rounds the flat facets of an
    already-reduced mesh without inventing detail. clean_mesh reduces it again
    afterwards to the requested maximum face count."""
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
    ms.meshing_merge_close_vertices(threshold=pymeshlab.PercentageValue(0.01))
    ms.meshing_repair_non_manifold_edges()
    ms.meshing_surface_subdivision_loop(iterations=1, threshold=pymeshlab.PercentageValue(0))
    m = ms.current_mesh()
    return trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=False)


def repair_light(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Repair that doesn't touch the shape: removes duplicate or degenerate
    faces, splits non-manifold edges/vertices, closes tiny holes and unifies the
    orientation. The mesh from the official TRELLIS remeshing is already almost
    watertight; any slicer fixes what remains."""
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
    """Watertight/manifold mesh ready to print, without losing detail.

    TRELLIS.2 output has hundreds of tiny holes, non-manifold edges and internal
    structures; classic repairers (pymeshfix, close_holes) either don't close it
    or wreck the model. Instead:
      1. reference surface: the mesh as is if dense, or subdivided (Loop) if it
         comes reduced and faceted;
      2. voxels: sample the surface on a grid of `grid` cells along the longest
         axis, dilate one cell (closes the holes) and fill the interior;
         marching cubes yields a surface that is closed by construction;
      3. fast face reduction (fast-simplification) down to `max_faces`;
      4. reproject each vertex onto the reference surface: the closed topology
         comes from the voxels and the exact shape from the original.
    """
    import fast_simplification
    from scipy import ndimage
    from skimage import measure

    # the full TRELLIS mesh (untextured, millions of faces) has no facets left;
    # the reduced one from the textured GLB does: that one gets subdivided
    ref = subdivide_mesh(mesh) if len(mesh.faces) < 1_500_000 else mesh
    lo, hi = ref.bounds
    pitch = float((hi - lo).max()) / grid
    # ~4 samples per surface cell: no crossed cell is left empty
    samples, _ = trimesh.sample.sample_surface(ref, int(ref.area / (pitch * 0.5) ** 2))
    idx = np.floor((samples - lo) / pitch).astype(np.int32) + 2
    occ = np.zeros(idx.max(axis=0) + 3, dtype=bool)
    occ[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    del samples, idx
    # no erosion afterwards: the extra layer is removed when reprojecting and
    # keeps thin parts (blades, fingers) from breaking on the grid
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
    # tiny loose pieces (voxel specks)
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
    # In very thin areas two distinct vertices can land on the same point
    # (the STL would merge them and non-manifold edges would appear): those go
    # back to their voxel position, which is closed by construction.
    for _ in range(3):
        key = np.round(after / (pitch * 1e-3)).astype(np.int64)
        _, inverse, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        clash = counts[inverse.ravel()] > 1
        if not clash.any():
            break
        after[clash] = before[clash]
    return trimesh.Trimesh(after, m.face_matrix(), process=False)


def export_stl(mesh: trimesh.Trimesh, path: Path, height_mm: float) -> dict:
    """Models are generated Y-up (glTF convention); 3D-printing slicers expect
    Z-up. Rotate, scale to `height_mm` tall and rest the model on the bed
    (z = 0), centred in XY."""
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
    """Watertight and 2-manifold according to manifold3d (the boolean library
    many slicers use); more reliable than trimesh's is_watertight."""
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
    """Per-face RGB color from the texture/vertex colors, if any."""
    try:
        visual = mesh.visual
        if visual.kind not in ("texture", "vertex", "face"):
            return None  # no color of its own (trimesh would use a default grey)
        if isinstance(visual, trimesh.visual.TextureVisuals):
            visual = visual.to_color()
        vc = np.asarray(visual.vertex_colors)[:, :3].astype(np.float32)
        if len(vc) != len(mesh.vertices):
            return None
        return vc[mesh.faces].mean(axis=1)
    except Exception:  # noqa: BLE001 - without a valid texture the default color is used
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
    // orthographic; z towards the viewer = closer
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
    """GPU render (OpenGL via moderngl): z-buffer, 8x MSAA and smooth shading
    (per-vertex normals, like a 3D viewer) or flat per face (`smooth=False`,
    useful for inspecting the triangulation)."""
    import moderngl

    verts = mesh.vertices - mesh.bounding_box.centroid
    verts = verts * (0.84 / max(np.linalg.norm(verts, axis=1).max(), 1e-6))
    faces = np.asarray(mesh.faces)
    tri = verts[faces].astype(np.float32)  # (F, 3, 3) unindexed: per-face normal
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
            # moderngl expects column-major matrices
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
    """Render `frames` views rotating around the vertical axis (Y).
    Uses the GPU (OpenGL) if available; otherwise the painter's algorithm on
    CPU. `only` limits which frames are rendered. Returns the paths."""
    try:
        return _render_gpu(mesh, out_dir, stem, frames, size, pitch_deg, only, smooth)
    except Exception:  # noqa: BLE001 - no OpenGL: software render
        pass
    verts = mesh.vertices - mesh.bounding_box.centroid
    scale = 0.84 / max(np.linalg.norm(verts, axis=1).max(), 1e-6)
    verts = verts * scale
    faces = mesh.faces
    base = _face_colors(mesh)
    if base is None:
        base = np.tile(np.array([[196, 178, 150]], np.float32), (len(faces), 1))

    ss = 2  # supersampling to smooth edges
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
        order = np.argsort(tri[idx, :, 2].mean(axis=1))  # back to front

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
