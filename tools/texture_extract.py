#!/usr/bin/env python3
"""
texture_extract.py - TextureMap decoder for Assassin's Creed Syndicate .forge.

Decodes TextureMap resources (class hash 0xA2B7E917) to PNG previews and
native DDS files. Pure Python + zlib; no Pillow/numpy required.

TextureMap body layout (little-endian; body = the `.res` file forge_reader.py
extracts, or a resource inside a decompressed entry container).  Fixed
0x7E-byte header; all evidence from DataPC.forge / DataPC_ACVI_London_grid.forge
(see system/knowledge/forge-format-analysis.md section 13):

    +0x00 u8   0x01                 resource framing
    +0x01 u64  resourceId
    +0x09 u32  classHash            0xA2B7E917
    ---- texture descriptor A (u32 fields at odd offsets) ----
    +0x0D u32  width
    +0x11 u32  height
    +0x15 u32  1
    +0x19 u32  pixelFormat          enum, see FORMATS below
    +0x1D u32  1
    +0x21 u32  srgb                 1 = sRGB data (diffuse/specular)
    +0x25 u32  mipCount             log2(max(w,h)) + 1 (0 = single mip)
    +0x29 u32  usage                0 diffuse 1 normal 2 specular 3 height
                                    11 gfx/effects (others seen, unresolved)
    +0x2D u32  flags                0 or 0x100 seen
    +0x31 u32  0
    +0x35 u64  TopMip resourceId    companion resource (class 0x1D4B87A3)
                                    holding the streamed top mip; 0 = none
    +0x3D u64  0
    ---- texture descriptor B (repeat; u32 fields) ----
    +0x46 u32  0x13237FE9           constant
    +0x4A u32  1
    +0x4E u32  7
    +0x52 u32  width
    +0x56 u32  height
    +0x5A u32  1
    +0x5E u32  mipCount
    +0x62 u32  pixelFormat
    +0x66 u32  1
    +0x6A u32  srgb
    +0x6E..    zero padding
    +0x7A u32  pixel data length
    +0x7E ...  pixel data

TopMip companion body layout (class hash 0x1D4B87A3):

    +0x00 u8   0x01
    +0x01 u64  resourceId
    +0x09 u32  classHash            0x1D4B87A3
    +0x0D u32  pixel data length    (exactly one mip: full width x height)
    +0x11 ...  pixel data           (linear, same block format as the parent)
    +9 bytes trailing (observed; meaning unknown)

Pixel data: standard GPU block layout, LINEAR (no tiling/swizzle - verified
by visual decode), largest mip first, mips contiguous.  Each mip is
ceil(w/4) x ceil(h/4) blocks (min 1 block).  When a TopMip companion exists
the TextureMap body holds mips 1..N and the top mip streams separately.

Formats (enum @0x19; bpp verified by exact mip-chain size fits):
    0  RGBA8    uncompressed 4 B/px          (usage 11/gfx, "Default Diffuse")
    1  4B/px    layout unresolved (1 entry: "Noise Gradient Texture" 256x1)
    2  BC1      DXT1  8 B/block              verified visually (bark diffuse)
    3  BC1      DXT1  8 B/block              verified visually (coal hole)
               (2 vs 3 both decode as DXT1; semantic difference unresolved)
    4  BC2      DXT3  16 B/block             verified visually (UI star icon)
    5  BC3      DXT5  16 B/block             verified visually (swamp diffuse)
    7  CUBEMAP  16 B blocks x 6 faces, each face a full mip chain (BC3 decode
               verified visually on face 0)
    8  BC5      16 B/block                  verified visually (normal maps)
    9  R8       uncompressed 1 B/px
    10 6-byte placeholder ("IndexCubeTexture")
    13 R32F     uncompressed 4 B/px float    ("DefaultDepthTexture")

Usage:
    python texture_extract.py info   <file.res>
    python texture_extract.py decode <file.res> [file.res ...] [-o DIR]
                                        [--topmip topmip.res] [--png-mip N]
                                        [--no-dds] [--no-png]
    python texture_extract.py forge  <file.forge> <name-or-id> [more...]
                                        [-o DIR] [--deep]
    python texture_extract.py scan   <file.forge> [limit]

`decode` writes <name>.png (preview of the largest available mip; BC5 shown
as a normal-map preview) and <name>.dds (native DXT1/DXT3/DXT5, or DX10
header for BC4/BC5/uncompressed) containing every stored mip.

`forge` finds entries by name/id, decodes every TextureMap resource inside,
and automatically looks for the TopMip companion in the same entry and in
TopMip-primary entries (--deep scans every entry; slow on large forges).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import forge_reader as fr
except ImportError:
    fr = None

TEXTUREMAP_HASH = 0xA2B7E917
TOPMIP_HASH = 0x1D4B87A3

# fmt enum -> (name, kind, bytes-per-block or bytes-per-pixel, dxgi)
# kind: "bc" block-compressed | "raw" uncompressed
FORMATS = {
    0:  ("RGBA8", "raw", 4, 28),    # DXGI_FORMAT_R8G8B8A8_UNORM
    1:  ("RGBA8?", "raw", 4, 28),   # unresolved channel layout
    2:  ("BC1", "bc", 8, None),
    3:  ("BC1", "bc", 8, None),
    4:  ("BC2", "bc", 16, None),
    5:  ("BC3", "bc", 16, None),
    7:  ("CUBEMAP16", "bc", 16, None),  # 6 faces of 16B-block data
    8:  ("BC5", "bc", 16, 83),      # DXGI_FORMAT_BC5_UNORM
    9:  ("R8", "raw", 1, 61),       # DXGI_FORMAT_R8_UNORM
    10: ("PLACEHOLDER", "raw", 6, 28),
    13: ("R32F", "raw", 4, 41),     # DXGI_FORMAT_R32_FLOAT
}
DDS_FOURCC = {"BC1": b"DXT1", "BC2": b"DXT3", "BC3": b"DXT5"}
CUBE_FACES = 6

USAGE_NAMES = {0: "diffuse", 1: "normal", 2: "specular", 3: "height",
               4: "usage4", 5: "usage5", 7: "usage7", 10: "cube",
               11: "gfx"}


def mip_dims(w, h, count):
    dims = []
    for _ in range(max(1, count)):
        dims.append((w, h))
        w, h = max(1, w // 2), max(1, h // 2)
    return dims


def mip_bytes(w, h, fmt):
    name, kind, sz, _ = FORMATS[fmt]
    if kind == "bc":
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * sz
    return w * h * sz


class TextureMap:
    """Parsed TextureMap resource body."""

    def __init__(self, body: bytes):
        if len(body) < 0x7E or body[0] != 1:
            raise ValueError("not a TextureMap body (bad framing)")
        (self.res_id,) = struct.unpack_from("<Q", body, 0x01)
        (self.class_hash,) = struct.unpack_from("<I", body, 0x09)
        (self.width,) = struct.unpack_from("<I", body, 0x0D)
        (self.height,) = struct.unpack_from("<I", body, 0x11)
        (self.fmt,) = struct.unpack_from("<I", body, 0x19)
        (self.srgb,) = struct.unpack_from("<I", body, 0x21)
        (self.mip_count,) = struct.unpack_from("<I", body, 0x25)
        (self.usage,) = struct.unpack_from("<I", body, 0x29)
        (self.flags,) = struct.unpack_from("<I", body, 0x2D)
        (self.topmip_id,) = struct.unpack_from("<Q", body, 0x35)
        (self.data_len,) = struct.unpack_from("<I", body, 0x7A)
        if self.fmt not in FORMATS:
            raise ValueError(f"unknown pixel format {self.fmt}")
        self.data = body[0x7E:]
        if self.data_len > len(self.data):
            raise ValueError(f"data length {self.data_len} exceeds body "
                             f"({len(self.data)} bytes left)")

    # -- stored mip chain -------------------------------------------------
    def mips(self, top_data: bytes | None = None):
        """[(w, h, size, offset)] largest first; offsets index the buffer the
        size came from.  If top_data (TopMip body) is given it becomes mip 0
        and TextureMap data provides the rest.  For cubemaps (fmt 7) the
        returned chain describes ONE face; self.faces holds the face count
        (6) and offsets are relative to face 0."""
        out = []
        if top_data is not None:
            out.append((self.width, self.height, len(top_data), None))
        dims = mip_dims(self.width, self.height, self.mip_count)
        start = 0 if top_data is None and not self.topmip_id else \
            (1 if self.topmip_id else 0)
        # accumulate while data remains; tolerate truncated tails
        remaining = self.data_len
        off = 0
        for w, h in dims[start:]:
            sz = mip_bytes(w, h, self.fmt)
            if sz > remaining:
                break
            out.append((w, h, sz, off))
            remaining -= sz
            off += sz
        self.faces = 1
        if FORMATS[self.fmt][0] == "CUBEMAP16":
            chain = sum(sz for _, _, sz, _ in out)
            self.faces = self.data_len // chain if chain else 1
            remaining = self.data_len - chain * self.faces
        self.unaccounted = remaining
        return out

    def __repr__(self):
        f = FORMATS[self.fmt][0]
        return (f"TextureMap({self.width}x{self.height} {f} mips={self.mip_count} "
                f"srgb={self.srgb} usage={USAGE_NAMES.get(self.usage, self.usage)} "
                f"dataLen={self.data_len} "
                f"topmip={hex(self.topmip_id) if self.topmip_id else 'none'})")


class TopMip:
    """Parsed TopMip companion resource body (one streamed top mip)."""

    def __init__(self, body: bytes):
        if len(body) < 0x11 or body[0] != 1:
            raise ValueError("not a TopMip body")
        (self.res_id,) = struct.unpack_from("<Q", body, 0x01)
        (self.class_hash,) = struct.unpack_from("<I", body, 0x09)
        (self.size,) = struct.unpack_from("<I", body, 0x0D)
        self.data = body[0x11:]
        if self.size > len(self.data):
            raise ValueError("TopMip size exceeds body")
        self.trailing = len(self.data) - self.size


# ---------------------------------------------------------------------------
# block decoders: each returns 16 pixels as list of (r,g,b,a) / (v,) / (r,g)

def _rgb565(v):
    r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def _bc1_colors(c0, c1):
    p0, p1 = _rgb565(c0), _rgb565(c1)
    if c0 > c1:
        p2 = tuple((2 * a + b) // 3 for a, b in zip(p0, p1))
        p3 = tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))
        a3 = 255
    else:  # 3-color mode: index 3 = transparent black
        p2 = tuple((a + b) // 2 for a, b in zip(p0, p1))
        p3 = (0, 0, 0)
        a3 = 0
    return [(p0[0], p0[1], p0[2], 255), (p1[0], p1[1], p1[2], 255),
            (p2[0], p2[1], p2[2], 255), (p3[0], p3[1], p3[2], a3)]


def decode_bc1(b, o):
    c0, c1 = struct.unpack_from("<HH", b, o)
    pal = _bc1_colors(c0, c1)
    idx, = struct.unpack_from("<I", b, o + 4)
    return [pal[(idx >> (2 * i)) & 3] for i in range(16)]


def decode_bc2(b, o):
    av = b[o:o + 4]
    c0, c1 = struct.unpack_from("<HH", b, o + 4)
    pal = _bc1_colors(c0, c1)
    idx, = struct.unpack_from("<I", b, o + 8)
    out = []
    for i in range(16):
        a = (av[i >> 2] >> (4 * (i & 3))) & 0xF
        p = pal[(idx >> (2 * i)) & 3]
        out.append((p[0], p[1], p[2], a * 17))
    return out


def _bc345_alpha(b, o):
    a0, a1 = b[o], b[o + 1]
    bits, = struct.unpack_from("<Q", b, o)  # grabs 8 bytes; only 48 bits used
    if a0 > a1:
        al = [a0, a1,
              (6 * a0 + a1) // 7, (5 * a0 + 2 * a1) // 7,
              (4 * a0 + 3 * a1) // 7, (3 * a0 + 4 * a1) // 7,
              (2 * a0 + 5 * a1) // 7, (a0 + 6 * a1) // 7]
    else:
        al = [a0, a1,
              (4 * a0 + 3 * a1) // 7, (3 * a0 + 4 * a1) // 7,
              (2 * a0 + 5 * a1) // 7, (a0 + 6 * a1) // 7,
              0, 255]
    idx = []
    pos = 16
    for _ in range(16):
        v = 0
        for k in range(3):
            v |= ((bits >> (pos + k)) & 1) << k
        idx.append(v)
        pos += 3
    return [al[i] for i in idx]


def decode_bc3(b, o):
    al = _bc345_alpha(b, o)
    c0, c1 = struct.unpack_from("<HH", b, o + 8)
    pal = _bc1_colors(c0, c1)
    idx, = struct.unpack_from("<I", b, o + 12)
    return [pal[(idx >> (2 * i)) & 3][:3] + (al[i],) for i in range(16)]


def decode_bc5(b, o):
    r = _bc345_alpha(b, o)
    g = _bc345_alpha(b, o + 8)
    return [(r[i], g[i]) for i in range(16)]


def decode_bc4(b, o):
    r = _bc345_alpha(b, o)
    return [(v,) for v in r]


DECODERS = {"BC1": decode_bc1, "BC2": decode_bc2, "BC3": decode_bc3,
            "BC4": decode_bc4, "BC5": decode_bc5}


def decode_blocks(data, off, w, h, name):
    """Decode one block-compressed mip -> RGBA bytearray (row-major)."""
    dec = DECODERS[name]
    bb = 8 if name in ("BC1", "BC4") else 16
    bw, bh = (w + 3) // 4, (h + 3) // 4
    img = bytearray(w * h * 4)
    for by in range(bh):
        for bx in range(bw):
            px = dec(data, off + (by * bw + bx) * bb)
            for j in range(4):
                y = by * 4 + j
                if y >= h:
                    break
                row = (y * w + bx * 4) * 4
                for i in range(4):
                    x = bx * 4 + i
                    if x >= w:
                        continue
                    p = px[j * 4 + i]
                    o4 = row + i * 4
                    if len(p) == 4:
                        img[o4:o4 + 4] = bytes(p)
                    elif len(p) == 2:  # BC5 normal-map preview
                        r, g = p
                        bl = max(0, min(255, 2 * 255 - r - g))
                        img[o4:o4 + 4] = bytes((r, g, bl, 255))
                    else:              # BC4 grayscale
                        img[o4:o4 + 4] = bytes((p[0], p[0], p[0], 255))
    return img


def decode_raw(data, off, w, h, fmt):
    img = bytearray(w * h * 4)
    name, kind, sz, _ = FORMATS[fmt]
    n = w * h
    if name == "RGBA8":
        for i in range(n):
            o = off + i * 4
            img[i * 4:i * 4 + 4] = bytes(
                (data[o], data[o + 1], data[o + 2], data[o + 3]))
    elif name == "R8":
        for i in range(n):
            v = data[off + i]
            img[i * 4:i * 4 + 4] = bytes((v, v, v, 255))
    elif name == "R32F":
        for i in range(n):
            f, = struct.unpack_from("<f", data, off + i * 4)
            v = max(0, min(255, int(f * 255)))
            img[i * 4:i * 4 + 4] = bytes((v, v, v, 255))
    else:
        raise ValueError(f"no raw decoder for {name}")
    return img


def decode_mip(data, off, w, h, fmt):
    name, kind, sz, _ = FORMATS[fmt]
    if kind == "bc":
        return decode_blocks(data, off, w, h,
                             "BC3" if name == "CUBEMAP16" else name)
    return decode_raw(data, off, w, h, fmt)


# ---------------------------------------------------------------------------
# writers

def write_png(path, w, h, rgba):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(chunk(b"IEND", b""))


def dds_header(w, h, mips, fmt, cubemap=False):
    """128-byte DDS header (+ DX10 extension when needed). Offsets are
    file-absolute (magic included)."""
    name, kind, sz, dxgi = FORMATS[fmt]
    flags = 0x1 | 0x2 | 0x4 | 0x1000          # CAPS|HEIGHT|WIDTH|PIXELFORMAT
    if mips > 1:
        flags |= 0x20000 | 0x8                # MIPMAPCOUNT|COMPLEX
    if kind == "bc":
        flags |= 0x80000                      # LINEARSIZE
    linear = mip_bytes(w, h, fmt)
    hdr = bytearray(128)
    hdr[0:4] = b"DDS "
    struct.pack_into("<III", hdr, 4, 124, flags, h)   # size, flags, height
    struct.pack_into("<II", hdr, 16, w,
                     linear if kind == "bc" else w * sz)  # width, pitch
    struct.pack_into("<II", hdr, 24, 0, mips)         # depth, mipcount
    struct.pack_into("<II", hdr, 76, 32, 0x4)         # ddspf size, FOURCC
    caps = 0x1000 | (0x400000 | 0x8 if mips > 1 else 0)
    struct.pack_into("<II", hdr, 108, caps, 0xFE00 if cubemap else 0)
    if name in DDS_FOURCC:
        hdr[84:88] = DDS_FOURCC[name]
        return bytes(hdr)
    hdr[84:88] = b"DX10"
    # dxgiFormat, resourceDimension(3=TEXTURE2D), miscFlag(0x4=CUBE),
    # arraySize, miscFlags2
    dx10 = struct.pack("<IIIII", dxgi, 3, 0x4 if cubemap else 0,
                       CUBE_FACES if cubemap else 1, 0)
    return bytes(hdr) + dx10


def write_dds(path, tex: TextureMap, top_data: bytes | None):
    """Write every stored mip (optionally merged TopMip as mip 0)."""
    fmt = tex.fmt
    cubemap = FORMATS[fmt][0] == "CUBEMAP16"
    mips = tex.mips(top_data)
    body = bytearray()
    if cubemap:
        # each face stores its own full chain; body already face-major
        body += tex.data[:tex.data_len]
        total_mips = max(1, tex.mip_count)
        with open(path, "wb") as f:
            f.write(dds_header(tex.width, tex.height, total_mips, 5,
                               cubemap=True))
            f.write(body)
        return
    count = len(mips)
    with open(path, "wb") as f:
        f.write(dds_header(tex.width, tex.height, count, fmt))
        for w, h, sz, off in mips:
            if off is None:
                f.write(top_data[:sz])
            else:
                f.write(tex.data[off:off + sz])


# ---------------------------------------------------------------------------

def safe_name(s):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s)[:100]


def decode_texture(body, top_body=None, outdir=".", base=None,
                   want_png=True, want_dds=True, png_mip=0, label=""):
    tex = TextureMap(body)
    top = TopMip(top_body) if top_body else None
    if top and top.size != mip_bytes(tex.width, tex.height, tex.fmt):
        print(f"  warning: TopMip size {top.size} != expected "
              f"{mip_bytes(tex.width, tex.height, tex.fmt)}; skipping merge")
        top = None
    base = base or safe_name(label or "texture")
    mips = tex.mips(top.data[:top.size] if top else None)
    print(f"  {tex}" + (f" +TopMip({top.size}B)" if top else ""))
    print(f"    stored mips: {len(mips)} "
          f"(top {mips[0][0]}x{mips[0][1]})"
          + (f", {tex.faces} faces" if tex.faces > 1 else "")
          + (f", {tex.unaccounted}B unaccounted" if tex.unaccounted else ""))
    if want_png:
        idx = min(png_mip, len(mips) - 1)
        w, h, sz, off = mips[idx]
        src = top.data if off is None else tex.data
        img = decode_mip(src, off or 0, w, h, tex.fmt)
        p = os.path.join(outdir, base + ".png")
        write_png(p, w, h, img)
        print(f"    png  {p} ({w}x{h})")
    if want_dds:
        p = os.path.join(outdir, base + ".dds")
        write_dds(p, tex, top.data[:top.size] if top else None)
        print(f"    dds  {p}")
    return tex


def cmd_info(path):
    body = open(path, "rb").read()
    if len(body) >= 12 and struct.unpack_from("<I", body, 9)[0] == TOPMIP_HASH:
        t = TopMip(body)
        print(f"TopMip rid={t.res_id:#x} size={t.size} trailing={t.trailing}")
        return 0
    t = TextureMap(body)
    print(repr(t))
    print(f"file: {path} ({os.path.getsize(path)} bytes)")
    mips = t.mips()
    print(f"stored mips here: {len(mips)} of {max(1, t.mip_count)}"
          + (f" (top streamed, rid {t.topmip_id:#x})" if t.topmip_id else ""))
    for w, h, sz, off in mips[:5]:
        print(f"   {w}x{h}  {sz} bytes @ +0x{off:x}")
    if t.unaccounted:
        print(f"   ({t.unaccounted} bytes of dataLen unaccounted by the chain)")


def cmd_decode(paths, outdir, topmip, png_mip, no_png, no_dds):
    os.makedirs(outdir, exist_ok=True)
    top_body = open(topmip, "rb").read() if topmip else None
    for p in paths:
        base = safe_name(os.path.splitext(os.path.basename(p))[0])
        print(f"== {p}")
        try:
            body = open(p, "rb").read()
            if len(body) >= 13 and struct.unpack_from("<I", body, 9)[0] == \
                    TOPMIP_HASH:
                print("  this is a TopMip body (single streamed mip, no "
                      "width/format of its own); pass it via --topmip "
                      "together with its TextureMap body")
                continue
            decode_texture(body, top_body, outdir, base,
                           not no_png, not no_dds, png_mip)
        except Exception as ex:
            print(f"  FAILED: {ex}")
    return 0


def iter_resources(forge, entry):
    data, sets = forge.decompress_entry(entry)
    if not sets:
        return data, []
    return data, forge.parse_container(data) or []


def cmd_forge(forge_path, keys, outdir, deep=False):
    if fr is None:
        print("forge_reader.py not found next to texture_extract.py", file=sys.stderr)
        return 1
    os.makedirs(outdir, exist_ok=True)
    forge = fr.ForgeFile(forge_path)
    rc = 0
    try:
        # optional TopMip index (built lazily / only when needed)
        topmap = None

        def top_lookup(rid, hint_data=None, hint_res=None):
            nonlocal topmap
            for r in (hint_res or []):
                if r.class_hash == TOPMIP_HASH and r.res_id == rid:
                    return hint_data[r.body_offset:r.body_offset + r.body_size]
            if topmap is None:
                topmap = {}
                for e in forge.entries[1:]:
                    candidates = None
                    if not deep and e.class_hash not in (TOPMIP_HASH,
                                                         TEXTUREMAP_HASH):
                        continue
                    try:
                        d, res = iter_resources(forge, e)
                    except Exception:
                        continue
                    for r in res:
                        if r.class_hash == TOPMIP_HASH and r.res_id not in topmap:
                            topmap[r.res_id] = d[r.body_offset:
                                                 r.body_offset + r.body_size]
            return topmap.get(rid)

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
            hit = False
            for r in res:
                if r.class_hash != TEXTUREMAP_HASH:
                    continue
                hit = True
                body = data[r.body_offset:r.body_offset + r.body_size]
                name = (r.name or e.name or "tex").decode("utf-8", "replace")
                try:
                    t = TextureMap(body)
                except Exception as ex:
                    print(f"  {name}: {ex}", file=sys.stderr)
                    rc = 1
                    continue
                top_body = None
                if t.topmip_id:
                    top_body = top_lookup(t.topmip_id, data, res)
                    if top_body is None:
                        print(f"  note: TopMip {t.topmip_id:#x} not found in "
                              f"this forge; largest stored mip used")
                try:
                    decode_texture(body, top_body, outdir,
                                   safe_name(name), label=name)
                except Exception as ex:
                    print(f"  {name}: decode failed: {ex}", file=sys.stderr)
                    rc = 1
            if not hit:
                print("  no TextureMap resources in this entry")
    finally:
        forge.close()
    return rc


def cmd_scan(forge_path, limit=None):
    if fr is None:
        print("forge_reader.py not found", file=sys.stderr)
        return 1
    forge = fr.ForgeFile(forge_path)
    n = 0
    from collections import Counter
    stats = Counter()
    try:
        print(f"{'name':<58} {'size':>11} {'fmt':>5} {'srgb':>4} "
              f"{'usage':>8} {'mips':>4} {'top':>3} chain")
        for e in forge.entries[1:]:
            if e.class_hash != TEXTUREMAP_HASH:
                continue
            if limit and n >= limit:
                break
            n += 1
            try:
                data, sets = forge.decompress_entry(e)
                body = None
                for r in forge.parse_container(data) or []:
                    if r.class_hash == TEXTUREMAP_HASH:
                        body = data[r.body_offset:r.body_offset + r.body_size]
                        break
                if body is None:
                    continue
                t = TextureMap(body)
                mips = t.mips()
                ok = "ok" if t.unaccounted == 0 else f"+{t.unaccounted}B"
                stats[(t.fmt, ok == "ok")] += 1
                print(f"{e.name[:58]:<58} {t.width:>5}x{t.height:<5} "
                      f"{FORMATS[t.fmt][0]:>5} {t.srgb:>4} "
                      f"{USAGE_NAMES.get(t.usage, str(t.usage)):>8} "
                      f"{t.mip_count:>4} {'yes' if t.topmip_id else '':>3} {ok}")
            except Exception as ex:
                print(f"{e.name[:58]:<58} ERROR {ex}")
        print("\nfmt totals:", dict(stats))
    finally:
        forge.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="ACS TextureMap decoder (PNG + DDS)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="print parsed header of a .res body")
    p.add_argument("res")
    p = sub.add_parser("decode", help="decode .res bodies to png/dds")
    p.add_argument("res", nargs="+")
    p.add_argument("-o", "--outdir", default=".")
    p.add_argument("--topmip", help="TopMip .res to merge as mip 0")
    p.add_argument("--png-mip", type=int, default=0)
    p.add_argument("--no-png", action="store_true")
    p.add_argument("--no-dds", action="store_true")
    p = sub.add_parser("forge", help="decode textures from a .forge entry")
    p.add_argument("forge")
    p.add_argument("keys", nargs="+")
    p.add_argument("-o", "--outdir", default=".")
    p.add_argument("--deep", action="store_true",
                   help="scan every entry for TopMip companions (slow)")
    p = sub.add_parser("scan", help="list TextureMaps in a forge")
    p.add_argument("forge")
    p.add_argument("limit", type=int, nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "info":
        return cmd_info(a.res)
    if a.cmd == "decode":
        return cmd_decode(a.res, a.outdir, a.topmip, a.png_mip,
                          a.no_png, a.no_dds)
    if a.cmd == "forge":
        return cmd_forge(a.forge, a.keys, a.outdir, a.deep)
    if a.cmd == "scan":
        return cmd_scan(a.forge, a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
