#!/usr/bin/env python3
"""
mesh_extract.py - Mesh/Entity resource decoder for Assassin's Creed Syndicate
(AnvilNext) .forge files. Exports Mesh resources to Wavefront OBJ.

Decodes the Mesh resource body (class hash 0x415D9568) and maps Entity
(0x0984415E) -> Mesh/Material cross references. See
system/knowledge/forge-format-analysis.md section 14 for the full layout
analysis behind this tool.

MESH RESOURCE LAYOUT (body = the `.res` blob forge_reader.py extracts):

    +0x00 u8   0x01                 resource framing
    +0x01 u64  resourceId
    +0x09 u32  classHash            0x415D9568
    ---- mesh header (variable length; three flavours observed) ----
    +0x18 6f32 bbox (simple primitives only; weapons/trees leave it 0)
    +0x40..     flavour A (primitives, weapons, props): fixed 0x43-byte header
    +0x20..     flavour B/C (skinned hair etc.): N x 79-byte bone records,
                recognised by the GUID fragment `a1 e7 f0 9e` at +0x20
    common anchor in every flavour: the 5 bytes `43 ee 51 c3 01`
                (at +0x52 in flavour A, later in B/C); the u16 VERTEX STRIDE
                sits at anchor+9 (20 for static, 28 for primitives with extra
                stream, 32/40 for skinned hair)
    +anchor+0x11 6f32 second bbox (world/instance space for props; often a
                positive-octant copy for primitives - informational only)
    ---- geometry (located by pattern scan, see locate_geometry) ----
    [u32 vertBufferSize][vertex records, `stride` bytes each]
    [u32 indexBufferSize][u16 triangle list]
    Index buffer is padded with degenerate triangles (all indices = last
    vertex); real triangles come first. Vertex record (stride 20):
        +0x00 i16 x3   position, divide by 16384.0 (verified: UnitSphere
                      decodes to a radius-1.0 sphere, UnitCube to +-1.0)
        +0x06 i16      small signed value (+-2 or -1); purpose unknown
        +0x08 4B       snorm8 x3 + ~0 pad; varies per vertex/face; not the
                      normal (kukri blade test); likely tangent-frame data
        +0x0C 4B       snorm8 x3 + ~0 pad; same
        +0x10 u16 x2   UV pair; 0..2047 (11-bit) or 0..65535 scale depending
                      on mesh (auto-detected); stride-28 records carry the
                      UV 8 bytes from the end instead
    Skinned records (stride 32/40) additionally contain bone weights/indices
    in the extra bytes (layout not decoded).

Entity resources embed references as [01][u64 sibling resourceId] records;
`forge --entities` resolves them against the container contents.

Usage:
    python mesh_extract.py info    <mesh.res>
    python mesh_extract.py obj     <mesh.res> [more...] [-o DIR]
                                       [--normals] [--keep-stitch] [--no-uv]
    python mesh_extract.py forge   <file.forge> <name-or-id> [more...]
                                       [-o DIR] [--entities]
    python mesh_extract.py scan    <file.forge> [limit]

`obj` writes <name>.obj (positions + UVs + faces; degenerate stitch triangles
dropped; optional recomputed smooth normals). `forge` exports every Mesh
resource in the given entry (works for Mesh- and Entity-primary entries).
Requires forge_reader.py next to this file (forge/scan commands) and
lzallright for decompression.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import forge_reader as fr
except ImportError:
    fr = None

MESH_HASH = 0x415D9568
ENTITY_HASH = 0x0984415E
ANCHOR = b"\x43\xee\x51\xc3\x01"      # common header anchor; stride at +9
BONE_GUID = b"\xa1\xe7\xf0\x9e"       # first bone record marker (skinned)
POS_SCALE = 16384.0
STRIDE_CANDIDATES = (64, 60, 56, 52, 48, 44, 40, 36, 32, 28, 24, 20, 16)
MAX_VERTS = 4_000_000


class MeshFormatError(Exception):
    pass


class Geometry:
    __slots__ = ("vb_off", "stride", "vert_count", "ib_off", "index_count",
                 "positions", "uvs", "triangles", "stitch_tris",
                 "uv_scale", "bbox")

    def __repr__(self):
        (mnx, mny, mnz), (mxx, mxy, mxz) = self.bbox
        return (f"Geometry(stride={self.stride} verts={self.vert_count} "
                f"tris={len(self.triangles)} (+{self.stitch_tris} stitch) "
                f"bbox=[{mnx:.3f},{mny:.3f},{mnz:.3f}.."
                f"{mxx:.3f},{mxy:.3f},{mxz:.3f}])")


class MeshResource:
    """Parsed Mesh resource body."""

    def __init__(self, body: bytes):
        if len(body) < 0x60 or body[0] != 1:
            raise MeshFormatError("not a resource body (bad framing byte)")
        self.body = body
        (self.res_id,) = struct.unpack_from("<Q", body, 0x01)
        (self.class_hash,) = struct.unpack_from("<I", body, 0x09)
        if self.class_hash != MESH_HASH:
            raise MeshFormatError(
                f"class hash {self.class_hash:08x} is not Mesh (415D9568)")
        self.skinned = body.find(BONE_GUID, 0x18, 0x30) == 0x20
        self.anchor_off = body.find(ANCHOR, 0x10, 0x800)
        self.stride = None
        if self.anchor_off >= 0:
            s, = struct.unpack_from("<H", body, self.anchor_off + 9)
            if s in STRIDE_CANDIDATES:
                self.stride = s
        # informational bboxes
        self.bbox18 = self._bbox(0x18) if not self.skinned else None
        self.bbox2 = self._bbox(self.anchor_off + 0x11) \
            if self.anchor_off >= 0 else None
        self.geom = locate_geometry(body, self.stride)
        self._decode()

    def _bbox(self, off):
        if off + 24 > len(self.body):
            return None
        f = struct.unpack_from("<6f", self.body, off)
        return f

    def _decode(self):
        g, body = self.geom, self.body
        stride = g.stride
        g.positions = [None] * g.vert_count
        g.uvs = [None] * g.vert_count
        maxu = maxv = 0
        for i in range(g.vert_count):
            o = g.vb_off + 4 + i * stride
            x, y, z = struct.unpack_from("<hhh", body, o)
            g.positions[i] = (x / POS_SCALE, y / POS_SCALE, z / POS_SCALE)
            if stride >= 20:
                u, v = struct.unpack_from("<HH", body, o + stride - 4)
                if u > maxu:
                    maxu = u
                if v > maxv:
                    maxv = v
                g.uvs[i] = (u, v)
        # UV scale: 11-bit (0..2047) or full u16 depending on mesh
        g.uv_scale = 2048.0 if max(maxu, maxv) <= 2050 else 65536.0
        n = g.index_count
        idx = struct.unpack_from(f"<{n}H", body, g.ib_off + 4)
        tris, stitch = [], 0
        for i in range(0, n - 2, 3):
            a, b, c = idx[i], idx[i + 1], idx[i + 2]
            if a == b or b == c or a == c:
                stitch += 1
            else:
                tris.append((a, b, c))
        g.triangles = tris
        g.stitch_tris = stitch
        xs = [p[0] for p in g.positions]
        ys = [p[1] for p in g.positions]
        zs = [p[2] for p in g.positions]
        g.bbox = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def summary(self):
        g = self.geom
        (mnx, mny, mnz), (mxx, mxy, mxz) = g.bbox
        lines = [
            f"resource id   : {self.res_id:#018x}",
            f"skinned      : {self.skinned}",
            f"anchor @     : +0x{self.anchor_off:x}" if self.anchor_off >= 0
            else "anchor       : NOT FOUND",
            f"stride       : {g.stride}",
            f"vertex buf   : @+0x{g.vb_off:x}  {g.vert_count} verts "
            f"({g.vert_count * g.stride} bytes)",
            f"index buf    : @+0x{g.ib_off:x}  {g.index_count} u16 indices",
            f"triangles    : {len(g.triangles)} real (+{g.stitch_tris} "
            f"degenerate stitch)",
            f"bbox         : [{mnx:.4f}, {mny:.4f}, {mnz:.4f}] .. "
            f"[{mxx:.4f}, {mxy:.4f}, {mxz:.4f}]",
            f"extent       : {mxx-mnx:.4f} x {mxy-mny:.4f} x {mxz-mnz:.4f}",
        ]
        if self.bbox18:
            b = self.bbox18
            lines.append(f"hdr bbox@18  : [{b[0]:.4f},{b[1]:.4f},{b[2]:.4f}]"
                         f"..[{b[4]:.4f},{b[5]:.4f},{b[6] if len(b)>6 else 0:.4f}]"
                         " (primitive flavour)")
        if self.bbox2 and any(v for v in self.bbox2):
            b = self.bbox2
            lines.append(f"hdr bbox@anc : [{b[0]:.4f},{b[1]:.4f},{b[2]:.4f}]"
                         f"..[{b[3]:.4f},{b[4]:.4f},{b[5]:.4f}] (info only)")
        return "\n".join(lines)


def locate_geometry(body: bytes, stride_hint=None, start=0x50):
    """
    Find the [u32 vertSize][vertex buffer][u32 idxSize][u16 index buffer]
    chain. The mesh header before it is variable-length (three flavours),
    so we scan byte-wise; the double size-field, index-bounds AND coverage
    validation make false positives vanishingly unlikely.

    Strides are tried largest-first: a stride that is too large produces a
    vertex count smaller than the largest index (rejected); the correct
    stride is the largest one where all indices stay in range and reach at
    least half the buffer (Anvil packs buffers tightly).
    """
    n = len(body)
    strides = ([stride_hint] if stride_hint else []) + \
              [s for s in STRIDE_CANDIDATES if s != stride_hint]
    for stride in strides:
        if not stride:
            continue
        for off in range(start, n - 16):
            s = int.from_bytes(body[off:off + 4], "little")
            if s < stride * 3 or s % stride or s > n - off - 16:
                continue
            vc = s // stride
            if vc > MAX_VERTS:
                continue
            ib = off + 4 + s
            t = int.from_bytes(body[ib:ib + 4], "little")
            if t < 6 or t % 2 or t > n - ib - 4:
                continue
            nidx = t // 2
            idx_all = struct.unpack_from(f"<{nidx}H", body, ib + 4)
            mx = max(idx_all)
            if mx >= vc:
                continue
            if 2 * mx <= vc:   # indices must reach well into the buffer
                continue
            g = Geometry()
            g.vb_off, g.stride, g.vert_count = off, stride, vc
            g.ib_off, g.index_count = ib, nidx
            return g
    raise MeshFormatError("geometry chain not found "
                          "(unknown header flavour or unsupported variant)")


# ---------------------------------------------------------------- OBJ export

def compute_normals(positions, triangles):
    acc = [[0.0, 0.0, 0.0] for _ in positions]
    for a, b, c in triangles:
        pa, pb, pc = positions[a], positions[b], positions[c]
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        for i in (a, b, c):
            acc[i][0] += nx
            acc[i][1] += ny
            acc[i][2] += nz
    out = []
    for x, y, z in acc:
        l = (x * x + y * y + z * z) ** 0.5
        out.append((x / l, y / l, z / l) if l > 1e-12 else (0.0, 0.0, 1.0))
    return out


def write_obj(path, mesh: MeshResource, name, want_normals=True,
              want_uv=True, keep_stitch=False):
    g = mesh.geom
    tris = list(g.triangles)
    if keep_stitch:
        # re-derive including stitch triangles
        n = g.index_count
        idx = struct.unpack_from(f"<{n}H", mesh.body, g.ib_off + 4)
        tris = [tuple(idx[i:i + 3]) for i in range(0, n - 2, 3)]
    lines = [f"# {name}",
             f"# exported by mesh_extract.py from AnvilNext Mesh resource "
             f"{mesh.res_id:#x}",
             f"# {g.vert_count} verts, {len(g.triangles)} triangles "
             f"(+{g.stitch_tris} stitch dropped)",
             f"# positions i16/16384 from vertex buffer @+0x{g.vb_off:x}"]
    for p in g.positions:
        lines.append(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")
    if want_uv and g.uvs and g.uvs[0] is not None:
        sc = g.uv_scale
        for u, v in g.uvs:
            lines.append(f"vt {u / sc:.6f} {v / sc:.6f}")
    normals = compute_normals(g.positions, tris) if want_normals else None
    if normals:
        for nx, ny, nz in normals:
            lines.append(f"vn {nx:.6f} {ny:.6f} {nz:.6f}")
    has_uv = want_uv and g.uvs and g.uvs[0] is not None
    for a, b, c in tris:
        if normals and has_uv:
            lines.append(f"f {a+1}/{a+1}/{a+1} {b+1}/{b+1}/{b+1} {c+1}/{c+1}/{c+1}")
        elif normals:
            lines.append(f"f {a+1}//{a+1} {b+1}//{b+1} {c+1}//{c+1}")
        elif has_uv:
            lines.append(f"f {a+1}/{a+1} {b+1}/{b+1} {c+1}/{c+1}")
        else:
            lines.append(f"f {a+1} {b+1} {c+1}")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines)


def geometry_check(mesh: MeshResource):
    """Sanity metrics for exported geometry. Edge counts merge vertices by
    position (UV-split corner vertices are distinct ids in the buffer)."""
    g = mesh.geom
    pid = {}
    def vid(i):
        p = g.positions[i]
        k = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
        v = pid.get(k)
        if v is None:
            v = pid[k] = len(pid)
        return v
    edges = {}
    for a, b, c in g.triangles:
        for e in ((vid(a), vid(b)), (vid(b), vid(c)), (vid(c), vid(a))):
            k = e if e[0] < e[1] else (e[1], e[0])
            edges[k] = edges.get(k, 0) + 1
    shared2 = sum(1 for v in edges.values() if v == 2)
    (mnx, mny, mnz), (mxx, mxy, mxz) = g.bbox
    checks = {
        "verts": g.vert_count,
        "verts_unique_pos": len(pid),
        "tris_real": len(g.triangles),
        "tris_stitch": g.stitch_tris,
        "stitch_ratio": g.stitch_tris / max(1, g.stitch_tris + len(g.triangles)),
        "edges_shared_by_2": f"{shared2}/{len(edges)}",
        "manifold_closed": shared2 == len(edges),
        "max_extent": max(mxx - mnx, mxy - mny, mxz - mnz),
        "zero_area_tris": sum(1 for a, b, c in g.triangles
                              if g.positions[a] == g.positions[b]
                              or g.positions[b] == g.positions[c]),
    }
    return checks


# ------------------------------------------------------------- entity linkage

def entity_references(entity_body: bytes, sibling_rids):
    """Find [u64 rid] references to sibling resources inside an Entity body.
    Returns {rid: [offsets]}."""
    out = {}
    for rid in sibling_rids:
        pat = struct.pack("<Q", rid)
        hits, off = [], 0
        while True:
            i = entity_body.find(pat, off)
            if i < 0:
                break
            hits.append(i)
            off = i + 1
        if hits:
            out[rid] = hits
    return out


# ---------------------------------------------------------------------- CLI

def safe_name(s):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s)[:100]


def cmd_info(path):
    body = open(path, "rb").read()
    m = MeshResource(body)
    print(f"file         : {path} ({len(body)} bytes)")
    print(m.summary())
    for k, v in geometry_check(m).items():
        print(f"check {k:<17}: {v}")
    return 0


def cmd_obj(paths, outdir, normals, keep_stitch, no_uv):
    os.makedirs(outdir, exist_ok=True)
    rc = 0
    for p in paths:
        base = safe_name(os.path.splitext(os.path.basename(p))[0])
        try:
            m = MeshResource(open(p, "rb").read())
        except (MeshFormatError, ValueError) as ex:
            print(f"{p}: FAILED - {ex}", file=sys.stderr)
            rc = 1
            continue
        out = os.path.join(outdir, base + ".obj")
        write_obj(out, m, base, want_normals=normals,
                  want_uv=not no_uv, keep_stitch=keep_stitch)
        print(f"{base}: {m.geom!r}")
        print(f"  -> {out} ({os.path.getsize(out):,} bytes)")
        chk = geometry_check(m)
        print(f"  checks: closed={chk['manifold_closed']} "
              f"edges2x={chk['edges_shared_by_2']} "
              f"stitch={chk['tris_stitch']} zero-area={chk['zero_area_tris']}")
    return rc


def iter_resources(forge, entry):
    data, sets = forge.decompress_entry(entry)
    if not sets:
        return data, []
    return data, forge.parse_container(data) or []


def cmd_forge(forge_path, keys, outdir, entities):
    if fr is None:
        print("forge_reader.py not found next to mesh_extract.py",
              file=sys.stderr)
        return 1
    os.makedirs(outdir, exist_ok=True)
    forge = fr.ForgeFile(forge_path)
    rc = 0
    try:
        for key in keys:
            e = forge.find(key)
            if not e:
                print(f"entry not found: {key}", file=sys.stderr)
                rc = 1
                continue
            print(f"== entry '{e.name}' ({e.file_id:#x})")
            try:
                data, res = iter_resources(forge, e)
            except Exception as ex:
                print(f"  decompress failed: {ex}", file=sys.stderr)
                rc = 1
                continue
            if not res:
                print("  no container resources", file=sys.stderr)
                rc = 1
                continue
            meshes, others = [], []
            for r in res:
                body = data[r.body_offset:r.body_offset + r.body_size]
                if r.class_hash == MESH_HASH:
                    meshes.append((r, body))
                else:
                    others.append((r, body))
            exported = {}
            for r, body in meshes:
                rn = (r.name or b"mesh").decode("utf-8", "replace")
                try:
                    m = MeshResource(body)
                except MeshFormatError as ex:
                    print(f"  {rn}: {ex}", file=sys.stderr)
                    rc = 1
                    continue
                out = os.path.join(outdir, safe_name(rn) + ".obj")
                write_obj(out, m, rn)
                exported[r.res_id] = rn
                chk = geometry_check(m)
                print(f"  MESH {rn}: {m.geom!r}")
                print(f"       closed={chk['manifold_closed']} "
                      f"stitch={chk['tris_stitch']} -> {out}")
            if entities:
                sib = {r.res_id: ((r.name or b"res").decode("utf-8", "replace"),
                                  fr.class_hash_to_name(r.class_hash)
                                  or f"h{r.class_hash:08x}")
                       for r, _ in meshes + others}
                for r, body in others:
                    if r.class_hash != ENTITY_HASH:
                        continue
                    rn = (r.name or b"entity").decode("utf-8", "replace")
                    refs = entity_references(body, sib.keys())
                    if refs:
                        print(f"  ENTITY {rn} ({r.res_id:#x}) references:")
                        for rid, offs in refs.items():
                            nm, cls = sib[rid]
                            print(f"    -> {cls:<10} {nm}  "
                                  f"rid={rid:#x} @ {[hex(o) for o in offs[:3]]}")
            if not meshes:
                print("  no Mesh resources in this entry")
    finally:
        forge.close()
    return rc


def cmd_scan(forge_path, limit):
    if fr is None:
        print("forge_reader.py not found", file=sys.stderr)
        return 1
    forge = fr.ForgeFile(forge_path)
    n = 0
    try:
        print(f"{'entry name':<56} {'stride':>6} {'verts':>7} {'tris':>7} "
              f"{'closed':>7} extent")
        for e in forge.entries[1:]:
            if e.class_hash != MESH_HASH:
                continue
            if limit and n >= limit:
                break
            n += 1
            try:
                data, res = iter_resources(forge, e)
                row = ""
                for r in res:
                    if r.class_hash != MESH_HASH:
                        continue
                    body = data[r.body_offset:r.body_offset + r.body_size]
                    m = MeshResource(body)
                    chk = geometry_check(m)
                    (a, b, c), (d, f_, g) = m.geom.bbox
                    ext = max(d - a, f_ - b, g - c)
                    print(f"{(e.name or '')[:56]:<56} {m.geom.stride:>6} "
                          f"{m.geom.vert_count:>7} {len(m.geom.triangles):>7} "
                          f"{str(chk['manifold_closed']):>7} {ext:.2f}")
            except Exception as ex:
                print(f"{(e.name or '')[:56]:<56} ERROR {ex}")
    finally:
        forge.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="ACS AnvilNext Mesh -> OBJ extractor (see "
                    "forge-format-analysis.md section 14)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="parse one Mesh .res body")
    p.add_argument("res")
    p = sub.add_parser("obj", help="export .res body(s) to OBJ")
    p.add_argument("res", nargs="+")
    p.add_argument("-o", "--outdir", default=".")
    p.add_argument("--no-normals", dest="normals", action="store_false",
                   help="skip recomputed smooth normals")
    p.add_argument("--keep-stitch", action="store_true")
    p.add_argument("--no-uv", action="store_true")
    p = sub.add_parser("forge", help="export Mesh resources from a forge entry")
    p.add_argument("forge")
    p.add_argument("keys", nargs="+")
    p.add_argument("-o", "--outdir", default="meshes_out")
    p.add_argument("--entities", action="store_true",
                   help="also report Entity -> resource references")
    p = sub.add_parser("scan", help="summarise Mesh entries in a forge")
    p.add_argument("forge")
    p.add_argument("limit", type=int, nargs="?")
    a = ap.parse_args(argv)

    if a.cmd == "info":
        return cmd_info(a.res)
    if a.cmd == "obj":
        return cmd_obj(a.res, a.outdir, a.normals, a.keep_stitch, a.no_uv)
    if a.cmd == "forge":
        return cmd_forge(a.forge, a.keys, a.outdir, a.entities)
    if a.cmd == "scan":
        return cmd_scan(a.forge, a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
