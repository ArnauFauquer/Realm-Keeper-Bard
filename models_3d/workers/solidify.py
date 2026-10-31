"""Solid printable mesh from the "skin" that Pixal3D/TRELLIS.2 generate.

The models don't generate a solid but a hollow skin of almost constant
thickness (~0.5% of the height): outer wall + inner wall, with the interior
empty and open to the outside through holes (e.g. under the feet). The mesh also
has non-manifold edges and inconsistent orientation. The slicer only fills the
outline of each layer and the cavity traps resin.

`solidify` solves it in two phases that share the same voxel grids:

  1. Repair to 2-manifold (what Bambu Studio did by hand): remove faces on
     non-manifold edges, orient each face towards the side with no nearby wall
     (the other wall of the skin is ~1 thickness away), propagate the orientation
     to the doubtful faces, split vertices with several fans and close the
     "zipper" holes.
  2. Fill: a point is interior if almost none of 26 directions escapes to the
     outside without touching the surface; a solid core is generated that sits
     below the surface (inside the skin) and is united with the original using
     manifold3d. The visible surface is 100% the original.
"""

import heapq
import itertools

import numpy as np
import trimesh

# Grids as a fraction of the model's longest side (at 100 mm: 0.1 and 0.25 mm).
FINE = 0.001
COARSE = 0.0025


def _edges(F: np.ndarray):
    """Directed edges (3F, 2), their sorted version and the face of each."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    return e, np.sort(e, axis=1), np.tile(np.arange(len(F)), 3)


def _manifold(V: np.ndarray, F: np.ndarray):
    import manifold3d as m3d

    return m3d.Manifold(m3d.Mesh(
        vert_properties=np.ascontiguousarray(V, np.float32),
        tri_verts=np.ascontiguousarray(F, np.uint32),
    ))


def _is_ok(M) -> bool:
    import manifold3d as m3d

    return M.status() == m3d.Error.NoError


# ----------------------------------------------------------------- voxels

def _surface_voxels(t: np.ndarray, h: float, lo: np.ndarray, shape) -> np.ndarray:
    """Voxels crossed by the surface (dense sampling of each triangle)."""
    occ = np.zeros(shape, bool)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    longest = np.maximum(np.linalg.norm(b - a, axis=1),
                         np.maximum(np.linalg.norm(c - a, axis=1), np.linalg.norm(c - b, axis=1)))
    steps = np.ceil(longest / (h * 0.5)).astype(int) + 1
    for k in np.unique(steps):
        idx = np.nonzero(steps == k)[0]
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        m = (i + j) <= k
        u, w = (i[m] / k)[None, :, None], (j[m] / k)[None, :, None]
        for s in range(0, len(idx), 100_000):
            ii = idx[s:s + 100_000]
            p = a[ii, None] * (1 - u - w) + b[ii, None] * u + c[ii, None] * w
            q = np.floor((p.reshape(-1, 3) - lo) / h).astype(np.int32)
            occ[q[:, 0], q[:, 1], q[:, 2]] = True
    return occ


def _escapes(occ: np.ndarray, d) -> np.ndarray:
    """Per voxel, how many of the two half-lines ±d (components in {-1,0,1})
    leave the grid without touching the surface (0, 1 or 2). The diagonal line is
    turned into an axis with a shear so cumulative sums can be used."""
    neg = [ax for ax in range(3) if d[ax] < 0]
    A = np.flip(occ, neg) if neg else occ
    d = np.abs(np.array(d))
    k = int(np.argmax(d))
    order = [k] + [i for i in range(3) if i != k]
    A = np.transpose(A, order)
    dd = d[order]
    X, Y, Z = A.shape
    S = np.zeros((X, Y + X * dd[1], Z + X * dd[2]), bool)
    for x in range(X):
        S[x, x * dd[1]:x * dd[1] + Y, x * dd[2]:x * dd[2] + Z] = A[x]
    fw = np.logical_or.accumulate(S, axis=0)
    bw = np.logical_or.accumulate(S[::-1], axis=0)[::-1]
    del S
    esc = np.zeros(fw.shape, np.uint8)
    esc[1:] += ~fw[:-1]
    esc[0] += 1
    esc[:-1] += ~bw[1:]
    esc[-1] += 1
    del fw, bw
    out = np.empty((X, Y, Z), np.uint8)
    for x in range(X):
        out[x] = esc[x, x * dd[1]:x * dd[1] + Y, x * dd[2]:x * dd[2] + Z]
    out = np.transpose(out, np.argsort(order))
    return np.flip(out, neg) if neg else out


def _interior(t: np.ndarray, lo: np.ndarray, hc: float, shape) -> np.ndarray:
    """Interior by rays on the coarse grid: at most 1 of 26 half-lines
    escapes. Dilated by one cell so it overlaps the skin's inner wall."""
    from scipy import ndimage

    occ = _surface_voxels(t, hc, lo, shape)
    esc = np.zeros(shape, np.uint8)
    for d in itertools.product((-1, 0, 1), repeat=3):
        if d != (0, 0, 0) and [x for x in d if x][0] > 0:  # 13 lines = 26 half-lines
            esc += _escapes(occ, d)
    return ndimage.binary_dilation((esc <= 1) & ~occ)


def _orientation_hint(t: np.ndarray, occ: np.ndarray, lo: np.ndarray, hf: float) -> np.ndarray:
    """+1 if the face normal already points to the free side, -1 if the opposite,
    0 if unknown. The "full" side is the one with another wall within ~0.8% of
    the size (the skin is ~0.5%); start at 2 cells to skip the face's own wall."""
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-20)[:, None]
    cen = t.mean(1)
    lim = np.array(occ.shape) - 1

    def first_hit(sign):
        hit = np.full(len(t), 99)
        for k in range(8, 1, -1):
            q = np.clip(np.floor((cen + sign * k * hf * n - lo) / hf).astype(int), 0, lim)
            hit[occ[q[:, 0], q[:, 1], q[:, 2]]] = k
        return hit

    fw, bw = first_hit(1), first_hit(-1)
    hint = np.zeros(len(t), np.int8)
    hint[(bw < 99) & (fw == 99)] = 1   # wall behind, free in front: fine
    hint[(fw < 99) & (bw == 99)] = -1  # wall in front: flip
    return hint


# ----------------------------------------------------------------- repair

def _zip_hole(V: np.ndarray, loop: list[int], existing: set) -> np.ndarray | None:
    """Cap a hole (boundary cycle) by ear clipping: each time the ear that
    adds the shortest diagonal, so long slits (typical after removing faces) close
    like a zipper, without membranes. Diagonals that already exist in the mesh
    are avoided (they would create non-manifold edges)."""
    n = len(V)
    loop = [int(v) for v in loop]  # Python ints: the key does not overflow
    key = lambda a, b: min(a, b) * n + max(a, b)  # noqa: E731
    prev = {loop[i]: loop[i - 1] for i in range(len(loop))}
    nxt = {loop[i - 1]: loop[i] for i in range(len(loop))}

    def cost(v):
        p, q = prev[v], nxt[v]
        return np.inf if key(p, q) in existing else float(np.linalg.norm(V[p] - V[q]))

    heap = [(cost(v), v) for v in loop]
    heapq.heapify(heap)
    tris = []
    while len(prev) > 3:
        c, v = heapq.heappop(heap)
        if v not in prev or c != cost(v):
            continue  # entrada caducada
        if c == np.inf:
            return None
        p, q = prev[v], nxt[v]
        tris.append((q, v, p))  # the border runs p->v->q; the cap traverses it the other way
        existing.add(key(p, q))
        nxt[p], prev[q] = q, p
        del prev[v], nxt[v]
        heapq.heappush(heap, (cost(p), p))
        heapq.heappush(heap, (cost(q), q))
    v = next(iter(prev))
    tris.append((nxt[v], v, prev[v]))
    return np.array(tris, dtype=np.int64)


def _orient(F: np.ndarray, hint: np.ndarray) -> np.ndarray:
    """Orient the faces: those with a geometric hint use it; the rest inherit it
    from their neighbours by BFS (from a virtual node joined to all faces with a
    hint, or to an arbitrary face in islands with none)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import breadth_first_order, connected_components

    n = len(F)
    e, es, fid = _edges(F)
    _, einv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(einv, kind="stable")
    pairs = order[cnt[einv[order]] == 2].reshape(-1, 2)
    fa, fb = fid[pairs[:, 0]], fid[pairs[:, 1]]
    same = e[pairs[:, 0], 0] == e[pairs[:, 1], 0]  # same direction: one must be flipped
    # faces without a hint in islands without any hint: the first is used as seed
    g = coo_matrix((np.ones(len(fa)), (fa, fb)), shape=(n, n))
    _, comp = connected_components(g, directed=False)
    seeded = np.zeros(comp.max() + 1, bool)
    seeded[comp[hint != 0]] = True
    seeds = np.nonzero(hint != 0)[0]
    extra = np.unique(comp, return_index=True)[1]
    extra = extra[~seeded[comp[extra]]]
    seeds = np.concatenate([seeds, extra])
    # nodo virtual n -> semillas
    g = coo_matrix((np.ones(len(fa) + len(seeds)),
                    (np.concatenate([fa, np.full(len(seeds), n)]), np.concatenate([fb, seeds]))),
                   shape=(n + 1, n + 1)).tocsr()
    key = np.minimum(fa, fb).astype(np.int64) * n + np.maximum(fa, fb)
    korder = np.argsort(key)
    key, same = key[korder], same[korder]
    nodes, pred = breadth_first_order(g, n, directed=False, return_predecessors=True)
    nodes = nodes[1:]
    p = pred[nodes]
    flip = np.zeros(n + 1, bool)
    flip[seeds] = hint[seeds] < 0
    tree = p != n
    nt, pt = nodes[tree], p[tree]
    rel = same[np.searchsorted(key, np.minimum(nt, pt).astype(np.int64) * n + np.maximum(nt, pt))]
    rel_of = np.zeros(n, bool)
    rel_of[nt] = rel
    fl = flip.tolist()
    ro = rel_of.tolist()
    for f, pf in zip(nt.tolist(), pt.tolist()):
        fl[f] = fl[pf] ^ ro[f]
    flip = np.array(fl[:n])
    F = F.copy()
    F[flip] = F[flip][:, ::-1]
    return F


def _repair(V: np.ndarray, F: np.ndarray, hint: np.ndarray):
    """(V, F) 2-manifold cerrada y orientada hacia fuera, o None."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    F = _orient(F, hint)
    for _ in range(4):
        # repeated directed edges: two neighbouring faces with incompatible
        # orientation; the one on the second half-edge is removed (leaves a hole)
        e, _, fid = _edges(F)
        _, first, dinv = np.unique(e, axis=0, return_index=True, return_inverse=True)
        dup = first[dinv.reshape(-1)] != np.arange(len(e))
        if not dup.any():
            break
        bad = np.zeros(len(F), bool)
        bad[fid[dup]] = True
        F, hint = F[~bad], hint[~bad]

    # vertices with several fans (bow-tie): one new vertex per fan
    e, es, fid = _edges(F)
    corner = np.arange(3 * len(F)).reshape(3, -1).T  # esquina (cara, k) -> id
    _, einv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(einv, kind="stable")
    pairs = order[cnt[einv[order]] == 2].reshape(-1, 2)
    links = []
    for side in (0, 1):  # both ends of each edge
        a = e[pairs[:, 0], side]
        f0, f1 = fid[pairs[:, 0]], fid[pairs[:, 1]]
        k0 = np.argmax(F[f0] == a[:, None], axis=1)
        k1 = np.argmax(F[f1] == a[:, None], axis=1)
        links.append(np.stack([corner[f0, k0], corner[f1, k1]], 1))
    links = np.concatenate(links)
    nc = 3 * len(F)
    _, lab = connected_components(
        coo_matrix((np.ones(len(links)), (links[:, 0], links[:, 1])), shape=(nc, nc)), directed=False)
    first = np.zeros(lab.max() + 1, int)
    first[lab[corner.ravel()]] = F.ravel()
    V, F = V[first], lab[corner]

    # holes: each boundary vertex has a single outgoing boundary edge,
    # so the boundaries form simple cycles
    e, es, _ = _edges(F)
    _, einv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    b = e[cnt[einv] == 1]
    if len(b):
        nxt = np.full(len(V), -1)
        nxt[b[:, 0]] = b[:, 1]
        visited = np.zeros(len(V), bool)
        existing = set((es[:, 0].astype(np.int64) * len(V) + es[:, 1]).tolist())
        new_v, new_f = [], []
        for start in b[:, 0]:
            if visited[start]:
                continue
            loop = [start]
            visited[start] = True
            v = nxt[start]
            while v != start and v >= 0 and not visited[v]:
                loop.append(v)
                visited[v] = True
                v = nxt[v]
            if v != start or len(loop) < 3:
                return None
            tris = _zip_hole(V, loop, existing)
            if tris is None:  # no valid ears: fan from a new vertex
                c = len(V) + len(new_v)
                new_v.append(V[loop].mean(0))
                tris = np.stack([np.roll(loop, -1), loop, np.full(len(loop), c)], 1)
            new_f.append(tris)
        if new_v:
            V = np.concatenate([V, np.array(new_v)])
        F = np.concatenate([F] + new_f)

    # whole components reversed (small islands without a reliable hint)
    _, es, _ = _edges(F)
    _, comp = connected_components(
        coo_matrix((np.ones(len(es)), (es[:, 0], es[:, 1])), shape=(len(V), len(V))), directed=False)
    fc = comp[F[:, 0]]
    t = V[F]
    vol = np.bincount(fc, np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])))
    neg = vol[fc] < 0
    F[neg] = F[neg][:, ::-1]

    used = np.unique(F)
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    V, F = V[used], remap[F]
    return (V, F) if _is_ok(_manifold(V, F)) else None


# ----------------------------------------------------------------- todo junto

def solidify(mesh: trimesh.Trimesh, fill: bool = True, progress=lambda msg: None):
    """Return (mesh, filled): the mesh repaired to 2-manifold and, if `fill` is set
    and it is a skin, solid. If the repair fails, return (None, False)."""
    import manifold3d as m3d
    from scipy import ndimage
    from skimage.measure import marching_cubes

    V, inv = np.unique(np.asarray(mesh.vertices, np.float64), axis=0, return_inverse=True)
    F = inv.reshape(-1)[np.asarray(mesh.faces)].reshape(-1, 3)
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    _, keep = np.unique(np.sort(F, axis=1), axis=0, return_index=True)
    F = F[np.sort(keep)]
    # faces on edges shared by 3+ faces: drop them (capped later)
    _, es, fid = _edges(F)
    _, einv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    bad = np.zeros(len(F), bool)
    bad[fid[cnt[einv.reshape(-1)] > 2]] = True
    F = F[~bad]
    t = V[F]

    size = float((V.max(0) - V.min(0)).max())
    hf, hc = FINE * size, COARSE * size
    lo = V.min(0) - 4 * hc
    hi = V.max(0) + 4 * hc
    shf = tuple(np.ceil((hi - lo) / hf).astype(int) + 1)

    progress("Repairing the mesh (orientation and holes)...")
    occ = _surface_voxels(t, hf, lo, shf)
    rep = _repair(V, F, _orientation_hint(t, occ, lo, hf))
    if rep is None:
        return None, False
    V, F = rep
    repaired = trimesh.Trimesh(V, F, process=False)
    M = _manifold(V, F)
    area = repaired.area
    thick = 2 * M.volume() / area if area > 0 else 0  # mean skin thickness
    if not fill or not 0 < thick < 0.02 * size:
        return repaired, False  # already a solid (or filling not requested)

    progress("Filling the skin: finding the interior...")
    shc = tuple(np.ceil((hi - lo) / hc).astype(int) + 1)
    inside = _interior(t, lo, hc, shc)
    progress("Filling the skin: solid core...")
    ci = [np.minimum((np.arange(n) * hf / hc).astype(int), shc[a] - 1) for a, n in enumerate(shf)]
    for x in range(shf[0]):
        occ[x] |= inside[ci[0][x]][np.ix_(ci[1], ci[2])]
    del inside
    lab, _ = ndimage.label(~occ)
    solid = lab != lab[0, 0, 0]  # everything that is not exterior
    del lab, occ
    # core ~0.6 thicknesses below the surface: stays inside the skin
    erode = max(1, round(0.6 * thick / hf))
    core = ndimage.binary_erosion(solid, ndimage.generate_binary_structure(3, 1), iterations=erode)
    del solid
    if not core.any():
        return repaired, False
    cv, cf, _, _ = marching_cubes(np.pad(core, 1).astype(np.float32), 0.5)
    del core
    cv = (cv - 1 + 0.5) * hf + lo  # voxel index -> cell centre
    C = _manifold(cv, cf)
    if not _is_ok(C) or C.volume() < 0:
        C = _manifold(cv, cf[:, ::-1])
    if not _is_ok(C):
        return repaired, False

    progress("Filling the skin: joining...")
    R = M + C.simplify(hf * 0.1)
    # closed bubbles left inside: they would trap resin
    R = m3d.Manifold.compose([p for p in R.decompose() if p.volume() > 0])
    if not _is_ok(R) or R.volume() <= M.volume():
        return repaired, False
    out = R.to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts),
                           process=False), True
