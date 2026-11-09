"""Hidden-line technical drawings from triangle meshes (numpy only).

The meshes come from `scene.py --dump <stage>` (world-space triangles in mm). A View is an
orthographic camera; `draw()` returns the visible (and hidden) edges as 2D polylines in px,
split into silhouettes / creases / open boundaries, plus the z-buffer and face-id buffer so a
caller can paint flat fills. `section()` slices meshes with an axis plane for hatching.
"""

import json
from collections import defaultdict, deque

import numpy as np


# ---- meshes --------------------------------------------------------------------------------
def load(path):
    d = np.load(path)
    meta = json.loads(str(d["meta"]))
    return [prep(dict(name=m["name"], group=m["group"], v=d[f"v{m['i']}"].astype(np.float64),
                      t=d[f"t{m['i']}"].astype(np.int64))) for m in meta]


def prep(o):
    """Weld vertices, drop degenerate triangles, build face normals and the edge->faces table."""
    v, t = o["v"], o["t"]
    key = np.round(v * 1e4).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    V, T = v[first], inv.reshape(-1)[t]
    T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 2] != T[:, 0])]
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    a = np.linalg.norm(n, axis=1)
    T, n = T[a > 1e-10], n[a > 1e-10] / a[a > 1e-10, None]
    E = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
    F = np.tile(np.arange(len(T)), 3)
    order = np.lexsort((E[:, 1], E[:, 0]))
    E, F = E[order], F[order]
    same = np.all(E[1:] == E[:-1], axis=1)
    idx = np.nonzero(same)[0]
    paired = np.zeros(len(E), bool)
    paired[idx] = paired[idx + 1] = True
    o.update(V=V, T=T, N=n, pe=E[idx], f1=F[idx], f2=F[idx + 1],
             cos=np.einsum("ij,ij->i", n[F[idx]], n[F[idx + 1]]), be=E[~paired])
    return o


def offset(objs, d):
    """Copy of objs translated by d (mm) -- for laying out views without re-dumping."""
    out = []
    for o in objs:
        c = dict(o)
        c["V"] = o["V"] + np.asarray(d, float)
        out.append(c)
    return out


# ---- camera --------------------------------------------------------------------------------
class View:
    """Orthographic view. forward = direction the eye looks; screen x right, y down (px)."""

    def __init__(self, forward, up, scale):
        f = np.asarray(forward, float)
        f /= np.linalg.norm(f)
        r = np.cross(f, up)
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        self.R = np.stack([r, -u, f])
        self.f = f
        self.s = scale

    def __call__(self, P):
        q = np.asarray(P, float) @ self.R.T
        q[:, :2] *= self.s
        return q

    def unproject(self, sx, sy, depth):
        q = np.stack([sx / self.s, sy / self.s, depth], axis=-1)
        return q @ self.R


VIEWS = {  # name: (forward, up)
    "top": ((0, 0, -1), (0, 1, 0)),
    "front": ((0, 1, 0), (0, 0, 1)),
    "left": ((1, 0, 0), (0, 0, 1)),
    "right": ((-1, 0, 0), (0, 0, 1)),
    "iso": ((1, 1, -1), (0, 0, 1)),        # from front-left-top
    "iso_r": ((-1, 1, -1), (0, 0, 1)),     # from front-right-top
}


def view(name, scale, forward=None):
    f, u = VIEWS[name] if forward is None else (forward, (0, 0, 1))
    return View(f, u, scale)


# ---- z-buffer ------------------------------------------------------------------------------
def _rasterize(tri, W, H, zb, fid, base):
    """Scanline-scatter triangles (n,3,3: px x, px y, depth) into flat zb/fid (min depth wins).
    Cost is proportional to covered rows + pixels, so long sliver triangles are cheap."""
    x, y, z = tri[:, :, 0], tri[:, :, 1], tri[:, :, 2]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    n = np.cross(e1, e2)
    ok = np.abs(n[:, 2]) > 1e-9                       # skip edge-on triangles
    r0 = np.clip(np.ceil(y.min(1) - 0.5), 0, H).astype(np.int64)
    r1 = np.clip(np.floor(y.max(1) - 0.5), -1, H - 1).astype(np.int64)
    ok &= r1 >= r0
    ids = np.nonzero(ok)[0]
    if not len(ids):
        return
    A = -n[:, 0] / np.where(ok, n[:, 2], 1)
    B = -n[:, 1] / np.where(ok, n[:, 2], 1)
    C = z[:, 0] - A * x[:, 0] - B * y[:, 0]
    zlo, zhi = z.min(1), z.max(1)
    rows = (r1 - r0 + 1)[ids]
    area = np.abs(n[ids, 2]) / 2 + (x.max(1) - x.min(1))[ids] + rows
    cuts = np.searchsorted(np.cumsum(area), np.arange(0, area.sum() + 4e6, 4e6)[1:])
    for chunk in np.split(ids, np.unique(np.clip(cuts + 1, 1, len(ids) - 1))):
        if not len(chunk):
            continue
        nr = r1[chunk] - r0[chunk] + 1
        tid = np.repeat(chunk, nr)
        r = r0[tid] + np.arange(nr.sum()) - np.repeat(np.cumsum(nr) - nr, nr)
        yc = r + 0.5
        xl = np.full(len(r), np.inf)
        xr = np.full(len(r), -np.inf)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ya, yb, xa, xb = y[tid, a], y[tid, b], x[tid, a], x[tid, b]
            span = (np.minimum(ya, yb) <= yc) & (yc <= np.maximum(ya, yb)) & (ya != yb)
            xi = xa + (yc - ya) * (xb - xa) / np.where(ya != yb, yb - ya, 1)
            xl = np.where(span, np.minimum(xl, xi), xl)
            xr = np.where(span, np.maximum(xr, xi), xr)
        c0 = np.clip(np.ceil(xl - 0.5), 0, W).astype(np.int64)
        c1 = np.clip(np.floor(xr - 0.5), -1, W - 1).astype(np.int64)
        cnt = np.maximum(c1 - c0 + 1, 0)
        pid = np.repeat(np.arange(len(r)), cnt)
        px = c0[pid] + np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        py = r[pid]
        tt = tid[pid]
        zz = np.clip(A[tt] * (px + 0.5) + B[tt] * (py + 0.5) + C[tt], zlo[tt], zhi[tt])
        lin = py * W + px
        np.minimum.at(zb, lin, zz)
        win = zz <= zb[lin]
        fid[lin[win]] = tt[win] + base


def _max3(a):
    p = np.pad(a, 1, constant_values=np.inf)
    out = a.copy()
    h, w = a.shape
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            np.maximum(out, p[dy:dy + h, dx:dx + w], out=out)
    return out


# ---- edges ---------------------------------------------------------------------------------
SIL, CREASE, OPEN = 0, 1, 2


def _edges(o, v, crease):
    fd = o["N"] @ v.f
    front = fd < -1e-6                     # faces seen edge-on count as not front-facing
    f1, f2 = o["f1"], o["f2"]
    sil = front[f1] != front[f2]
    feat = (o["cos"] < np.cos(np.radians(crease))) & (front[f1] | (np.abs(fd[f1]) <= 1e-6))         & (front[f2] | (np.abs(fd[f2]) <= 1e-6)) & (front[f1] | front[f2]) & ~sil
    E = np.concatenate([o["pe"][sil], o["pe"][feat], o["be"]])
    kind = np.concatenate([np.full(sil.sum(), SIL), np.full(feat.sum(), CREASE), np.full(len(o["be"]), OPEN)])
    return o["V"][E[:, 0]], o["V"][E[:, 1]], kind


def draw(objs, v, ss=3, crease=22, occlude=None, edges=None, margin=6, eps=0.02, hidden=False):
    """Project, z-buffer and classify edges.

    occlude(o) -> bool: does o hide what is behind it (default all). edges(o) -> bool: draw o's
    edges (default all). Returns a dict with polylines [(pts Nx2, obj index, kind, visible)],
    screen bounds `lo`/`hi` (px), and the raster buffers for fills.
    """
    occlude = occlude or (lambda o: True)
    edges = edges or (lambda o: True)
    P = [v(o["V"]) for o in objs]
    allp = np.concatenate([p[:, :2] for p in P])
    lo, hi = allp.min(0) - margin, allp.max(0) + margin
    W, H = int(np.ceil((hi[0] - lo[0]) * ss)), int(np.ceil((hi[1] - lo[1]) * ss))
    zb = np.full(H * W, np.inf)
    fid = np.full(H * W, -1, np.int64)
    base, fo = 0, []
    for oi, (o, p) in enumerate(zip(objs, P)):
        if occlude(o):
            q = p.copy()
            q[:, 0] = (q[:, 0] - lo[0]) * ss
            q[:, 1] = (q[:, 1] - lo[1]) * ss
            _rasterize(q[o["T"]], W, H, zb, fid, base)
        fo.append(np.full(len(o["T"]), oi))
        base += len(o["T"])
    zb, fid = zb.reshape(H, W), fid.reshape(H, W)
    zmx = _max3(zb)

    segs = []
    for oi, o in enumerate(objs):
        if not edges(o):
            continue
        A, B, kind = _edges(o, v, crease)
        if not len(A):
            continue
        pa, pb = v(A), v(B)
        L = np.hypot(*(pb[:, :2] - pa[:, :2]).T)
        keep = L > 0.05
        pa, pb, kind, L = pa[keep], pb[keep], kind[keep], L[keep]
        n = np.maximum(2, np.ceil(L * ss / 0.8).astype(np.int64) + 1)
        eid = np.repeat(np.arange(len(n)), n)
        k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
        t = (k / (n[eid] - 1))[:, None]
        S = pa[eid] + (pb[eid] - pa[eid]) * t
        ix = np.floor((S[:, 0] - lo[0]) * ss).astype(np.int64)
        iy = np.floor((S[:, 1] - lo[1]) * ss).astype(np.int64)
        inb = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
        zref = np.full(len(S), np.inf)
        zref[inb] = zmx[iy[inb], ix[inb]]
        vis = S[:, 2] <= zref + eps
        brk = np.ones(len(S), bool)
        brk[1:] = (eid[1:] != eid[:-1]) | (vis[1:] != vis[:-1])
        starts = np.nonzero(brk)[0]
        ends = np.append(starts[1:], len(S)) - 1
        for s0, s1 in zip(starts, ends):
            if s1 == s0 or (not vis[s0] and not hidden):
                continue
            segs.append((S[s0, 0], S[s0, 1], S[s1, 0], S[s1, 1], oi, int(kind[eid[s0]]), bool(vis[s0])))
    return dict(polys=_chain(segs), lo=lo, hi=hi, ss=ss, zb=zb, fid=fid, face_obj=np.concatenate(fo),
                normals=np.concatenate([o["N"] for o in objs]), view=v)


def _chain(segs):
    """Join segments that meet end to end (same object / kind / visibility) into polylines."""
    groups = defaultdict(list)
    for s in segs:
        groups[s[4:]].append(s[:4])
    out = []
    for (oi, kind, vis), ss_ in groups.items():
        S = np.array(ss_)
        key = lambda x, y: (int(round(x * 200)), int(round(y * 200)))
        ends = defaultdict(list)
        for i, (x0, y0, x1, y1) in enumerate(S):
            ends[key(x0, y0)].append((i, 0))
            ends[key(x1, y1)].append((i, 1))
        used = np.zeros(len(S), bool)
        for i in range(len(S)):
            if used[i]:
                continue
            used[i] = True
            pts = deque([S[i, :2], S[i, 2:]])
            for fwd in (True, False):
                while True:
                    tip = pts[-1] if fwd else pts[0]
                    inc = ends[key(*tip)]
                    nxt = [(j, e) for j, e in inc if not used[j]]
                    if len(inc) != 2 or not nxt:
                        break
                    j, e = nxt[0]
                    used[j] = True
                    p = S[j, 2:] if e == 0 else S[j, :2]
                    pts.append(p) if fwd else pts.appendleft(p)
            out.append((_simplify(np.array(pts)), oi, kind, vis))
    return out


def _simplify(P, tol=0.05):
    if len(P) < 3:
        return P
    keep = [0]
    for i in range(1, len(P) - 1):
        a, b, c = P[keep[-1]], P[i], P[i + 1]
        ab, ac = b - a, c - a
        if abs(ab[0] * ac[1] - ab[1] * ac[0]) > tol * max(np.hypot(*ac), 1e-9):
            keep.append(i)
    keep.append(len(P) - 1)
    return P[keep]


# ---- sections ------------------------------------------------------------------------------
def section(o, axis, value):
    """Closed loops (list of Nx3 arrays, mm) where plane coord[axis] == value cuts the mesh."""
    V, T = o["V"], o["T"]
    d = V[:, axis] - value
    d = np.where(np.abs(d) < 1e-7, 1e-7, d)
    sd = np.sign(d)
    loops = []
    E = np.stack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], axis=1)          # (nt,3,2)
    cross = sd[E[:, :, 0]] != sd[E[:, :, 1]]                                  # (nt,3)
    tri = np.nonzero(cross.sum(1) == 2)[0]
    if not len(tri):
        return loops
    adj = defaultdict(list)
    pos = {}
    for ti in tri:
        ks = []
        for k in range(3):
            if cross[ti, k]:
                a, b = sorted(E[ti, k])
                ks.append((a, b))
                if (a, b) not in pos:
                    t = d[a] / (d[a] - d[b])
                    pos[(a, b)] = V[a] + t * (V[b] - V[a])
        adj[ks[0]].append(ks[1])
        adj[ks[1]].append(ks[0])
    seen = set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) >= 3:
            loops.append(np.array([pos[k] for k in loop]))
    return loops


# ---- SVG helpers ---------------------------------------------------------------------------
def path_d(P, close=False):
    s = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in P)
    return s + (" Z" if close else "")
