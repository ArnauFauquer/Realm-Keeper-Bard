"""Malla maciza para imprimir a partir de la "piel" que generan Pixal3D/TRELLIS.2.

Los modelos no generan un sólido sino una piel hueca de grosor casi constante
(~0,5% de la altura): pared exterior + pared interior, con el interior vacío y
abierto al exterior por agujeros (p. ej. bajo los pies). Además la malla trae
aristas no-manifold y orientación incoherente. El laminador solo rellena el
contorno de cada capa y el hueco atrapa resina.

`solidify` lo resuelve en dos fases que comparten las mismas rejillas de vóxeles:

  1. Reparación a 2-manifold (lo que hacía Bambu Studio a mano): quita las caras
     de aristas no-manifold, orienta cada cara hacia el lado sin pared cercana
     (la otra pared de la piel está a ~1 grosor), propaga la orientación a las
     caras dudosas, separa vértices con varios abanicos y cierra los agujeros
     "en cremallera".
  2. Relleno: un punto es interior si casi ninguna de 26 direcciones escapa al
     exterior sin tocar la superficie; se genera un núcleo sólido que queda por
     debajo de la superficie (dentro de la piel) y se une al original con
     manifold3d. La superficie visible es la original al 100%.
"""

import heapq
import itertools

import numpy as np
import trimesh

# Rejillas en fracción del lado mayor del modelo (a 100 mm: 0,1 y 0,25 mm).
FINE = 0.001
COARSE = 0.0025


def _edges(F: np.ndarray):
    """Aristas dirigidas (3F, 2), su versión ordenada y la cara de cada una."""
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


# ----------------------------------------------------------------- vóxeles

def _surface_voxels(t: np.ndarray, h: float, lo: np.ndarray, shape) -> np.ndarray:
    """Vóxeles atravesados por la superficie (muestreo denso de cada triángulo)."""
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
    """Por vóxel, cuántas de las dos semirrectas ±d (componentes en {-1,0,1})
    salen de la rejilla sin tocar la superficie (0, 1 o 2). La recta diagonal se
    convierte en un eje con una cizalla para usar acumulados."""
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
    """Interior por rayos en la rejilla gruesa: como mucho 1 de 26 semirrectas
    escapa. Se dilata una celda para que solape la pared interior de la piel."""
    from scipy import ndimage

    occ = _surface_voxels(t, hc, lo, shape)
    esc = np.zeros(shape, np.uint8)
    for d in itertools.product((-1, 0, 1), repeat=3):
        if d != (0, 0, 0) and [x for x in d if x][0] > 0:  # 13 rectas = 26 semirrectas
            esc += _escapes(occ, d)
    return ndimage.binary_dilation((esc <= 1) & ~occ)


def _orientation_hint(t: np.ndarray, occ: np.ndarray, lo: np.ndarray, hf: float) -> np.ndarray:
    """+1 si la normal de la cara ya apunta al lado libre, -1 si al revés, 0 si
    no se sabe. El lado "lleno" es el que tiene otra pared a menos de ~0,8% del
    tamaño (la piel mide ~0,5%); se empieza a 2 celdas para saltar la propia."""
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
    hint[(bw < 99) & (fw == 99)] = 1   # pared detrás, libre delante: bien
    hint[(fw < 99) & (bw == 99)] = -1  # pared delante: girar
    return hint


# ----------------------------------------------------------------- reparación

def _zip_hole(V: np.ndarray, loop: list[int], existing: set) -> np.ndarray | None:
    """Tapa un agujero (ciclo de borde) recortando orejas: cada vez la que
    añade la diagonal más corta, así las rendijas largas (lo típico al quitar
    caras) se cierran como una cremallera, sin membranas. Se evitan diagonales
    que ya existen en la malla (crearían aristas no-manifold)."""
    n = len(V)
    loop = [int(v) for v in loop]  # enteros de Python: la clave no desborda
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
        tris.append((q, v, p))  # el borde va p->v->q; la tapa lo recorre al revés
        existing.add(key(p, q))
        nxt[p], prev[q] = q, p
        del prev[v], nxt[v]
        heapq.heappush(heap, (cost(p), p))
        heapq.heappush(heap, (cost(q), q))
    v = next(iter(prev))
    tris.append((nxt[v], v, prev[v]))
    return np.array(tris, dtype=np.int64)


def _orient(F: np.ndarray, hint: np.ndarray) -> np.ndarray:
    """Orienta las caras: las que tienen pista geométrica la usan; el resto la
    hereda de sus vecinas por BFS (desde un nodo virtual unido a todas las caras
    con pista, o a una cara cualquiera en las islas sin ninguna)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import breadth_first_order, connected_components

    n = len(F)
    e, es, fid = _edges(F)
    _, einv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(einv, kind="stable")
    pairs = order[cnt[einv[order]] == 2].reshape(-1, 2)
    fa, fb = fid[pairs[:, 0]], fid[pairs[:, 1]]
    same = e[pairs[:, 0], 0] == e[pairs[:, 1], 0]  # misma dirección: hay que girar una
    # caras sin pista en islas sin ninguna pista: se usa la primera como semilla
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
        # aristas dirigidas repetidas: dos caras vecinas con orientación
        # incompatible; se quita la de la segunda semiarista (queda un agujero)
        e, _, fid = _edges(F)
        _, first, dinv = np.unique(e, axis=0, return_index=True, return_inverse=True)
        dup = first[dinv.reshape(-1)] != np.arange(len(e))
        if not dup.any():
            break
        bad = np.zeros(len(F), bool)
        bad[fid[dup]] = True
        F, hint = F[~bad], hint[~bad]

    # vértices con varios abanicos (pajarita): un vértice nuevo por abanico
    e, es, fid = _edges(F)
    corner = np.arange(3 * len(F)).reshape(3, -1).T  # esquina (cara, k) -> id
    _, einv, cnt = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(einv, kind="stable")
    pairs = order[cnt[einv[order]] == 2].reshape(-1, 2)
    links = []
    for side in (0, 1):  # los dos extremos de cada arista
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

    # agujeros: cada vértice de borde tiene una sola arista de borde saliente,
    # así que los bordes forman ciclos simples
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
            if tris is None:  # sin orejas válidas: abanico desde un vértice nuevo
                c = len(V) + len(new_v)
                new_v.append(V[loop].mean(0))
                tris = np.stack([np.roll(loop, -1), loop, np.full(len(loop), c)], 1)
            new_f.append(tris)
        if new_v:
            V = np.concatenate([V, np.array(new_v)])
        F = np.concatenate([F] + new_f)

    # componentes enteras al revés (islas pequeñas sin pista fiable)
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
    """Devuelve (malla, rellena): la malla reparada a 2-manifold y, si `fill` y
    es una piel, maciza. Si la reparación falla devuelve (None, False)."""
    import manifold3d as m3d
    from scipy import ndimage
    from skimage.measure import marching_cubes

    V, inv = np.unique(np.asarray(mesh.vertices, np.float64), axis=0, return_inverse=True)
    F = inv.reshape(-1)[np.asarray(mesh.faces)].reshape(-1, 3)
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    _, keep = np.unique(np.sort(F, axis=1), axis=0, return_index=True)
    F = F[np.sort(keep)]
    # caras en aristas compartidas por 3+ caras: fuera (se tapan después)
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

    progress("Reparando la malla (orientación y agujeros)...")
    occ = _surface_voxels(t, hf, lo, shf)
    rep = _repair(V, F, _orientation_hint(t, occ, lo, hf))
    if rep is None:
        return None, False
    V, F = rep
    repaired = trimesh.Trimesh(V, F, process=False)
    M = _manifold(V, F)
    area = repaired.area
    thick = 2 * M.volume() / area if area > 0 else 0  # grosor medio de la piel
    if not fill or not 0 < thick < 0.02 * size:
        return repaired, False  # ya es un sólido (o no se pide rellenar)

    progress("Rellenando la piel: buscando el interior...")
    shc = tuple(np.ceil((hi - lo) / hc).astype(int) + 1)
    inside = _interior(t, lo, hc, shc)
    progress("Rellenando la piel: núcleo sólido...")
    ci = [np.minimum((np.arange(n) * hf / hc).astype(int), shc[a] - 1) for a, n in enumerate(shf)]
    for x in range(shf[0]):
        occ[x] |= inside[ci[0][x]][np.ix_(ci[1], ci[2])]
    del inside
    lab, _ = ndimage.label(~occ)
    solid = lab != lab[0, 0, 0]  # todo lo que no es exterior
    del lab, occ
    # núcleo ~0,6 grosores bajo la superficie: queda dentro de la piel
    erode = max(1, round(0.6 * thick / hf))
    core = ndimage.binary_erosion(solid, ndimage.generate_binary_structure(3, 1), iterations=erode)
    del solid
    if not core.any():
        return repaired, False
    cv, cf, _, _ = marching_cubes(np.pad(core, 1).astype(np.float32), 0.5)
    del core
    cv = (cv - 1 + 0.5) * hf + lo  # índice de vóxel -> centro de la celda
    C = _manifold(cv, cf)
    if not _is_ok(C) or C.volume() < 0:
        C = _manifold(cv, cf[:, ::-1])
    if not _is_ok(C):
        return repaired, False

    progress("Rellenando la piel: uniendo...")
    R = M + C.simplify(hf * 0.1)
    # burbujas cerradas que queden dentro: atraparían resina
    R = m3d.Manifold.compose([p for p in R.decompose() if p.volume() > 0])
    if not _is_ok(R) or R.volume() <= M.volume():
        return repaired, False
    out = R.to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts),
                           process=False), True
