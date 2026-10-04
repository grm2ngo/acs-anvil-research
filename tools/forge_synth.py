#!/usr/bin/env python3
"""
forge_synth.py - Clean-room SYNTHETIC .forge archive writer (spec v27).

Builds a small, fully deterministic .forge file that follows the documented
container layout (see docs/forge-format.md). Contains ZERO game content:
every byte is generated from constants below. Its purpose:

  1. test fixture for tools/forge_reader.py without anyone supplying a game
     file (used by CI and tests/selftest.py);
  2. a working executable example of the format's write side.

Layout summary (little-endian):
  header    magic "scimitar", version 27, dataHeader@0x41A, 0x1000, 1
  data hdr  entryCount, descriptors (chain + index offset), -1 terminators,
            {~N, indexEnd, 0, nameTableEnd}
  index     N * {u64 off, u64 id, u32 size} @ 0x476
  entry-0   special 0xA0 name slot just below the name table
  names     (N-1) * 192 B records: size@+0, resId@+4, classHash@+0x10,
            ts@+0x28, name@+0x2C
  payloads  entry 0 raw; entries 1.. block sets (stored blocks, Adler-0)

Usage:
  python forge_synth.py out.forge [--entries N]
"""
from __future__ import annotations

import argparse
import os
import struct
import zlib

MAGIC_SCIMITAR = b"scimitar"
MAGIC_BLOCKSET = 0x1004FA9957FBAA33

DATA_HEADER_OFF = 0x41A
INDEX_OFF = 0x476
NAME_TABLE_OFF = 0x680
PAYLOAD_OFF = 0x1000
NAME_RECORD_SIZE = 192
TS_BASE = 1447114000  # fixed, deterministic (2015-11-04)

# confirmed class hashes (from tools/forge_reader.py) - so the census
# prints real names
CLASSES = [
    (0xA2B7E917, "TextureMap"),
    (0x415D9568, "Mesh"),
    (0x85C817C3, "Material"),
    (0x0984415E, "Entity"),
    (0x1D4B87A3, "TopMip"),  # as seen in real censuses
    (0x49F387B1, "SoundBanksLoadOnDemand"),
    (0x6E3C9C6F, "LocalizationPackage"),
    (0x0FA3067F, "Animation"),
    (0xBCFB3C7A, "MaterialTemplate"),
    (0xB1420AD1, "GraphicsConfig"),
    (0xB4E69FA1, "EngineOptions"),
]


def zero_adler32(data: bytes) -> int:
    return zlib.adler32(data, 0)


def body_bytes(seed: int, n: int) -> bytes:
    """Deterministic filler body: counter pattern, no game content."""
    return bytes((seed + i) & 0xFF for i in range(n))


def build_inner_container(entry_i: int) -> bytes:
    """Multi-resource container per docs/forge-format.md:
    u16 resCount, TOC (resId,recordSize,flags), then records
    (classHash, bodySize, nameLen, name, gap, body)."""
    out = bytearray()
    n_res = 1 + (entry_i % 2)
    recs = []
    for r in range(n_res):
        name = f"synthetic_res_{entry_i}_{r}".encode()
        body = body_bytes(entry_i * 31 + r, 48 + entry_i * 7 + r * 13)
        rec = struct.pack("<III", CLASSES[entry_i % len(CLASSES)][0],
                          len(body), len(name)) + name
        gap = b"\x00" * (8 - (len(rec) % 8))
        # body starts with resourceId+classHash like real resources
        res_id = 0x5000 + entry_i * 16 + r
        body = struct.pack("<QI", res_id, CLASSES[entry_i % len(CLASSES)][0]) + body
        recs.append(rec + gap + body)
    out += struct.pack("<H", n_res)
    for r, rec in enumerate(recs):
        out += struct.pack("<QIH", 0x5000 + entry_i * 16 + r, len(rec), 0)
    for rec in recs:
        out += rec
    return bytes(out)


def build_block_set(inner: bytes) -> bytes:
    """One block set, single STORED block (cs == us => reader needs no LZO)."""
    out = bytearray()
    out += struct.pack("<QhBHHI", MAGIC_BLOCKSET, 2, 1, 0x8000, 0x8000, 1)
    out += struct.pack("<ii", len(inner), len(inner))
    out += struct.pack("<I", zero_adler32(inner))
    out += inner
    return bytes(out)


def build_forge(path: str, n_entries: int = 12) -> dict:
    """Write a synthetic archive; returns metadata dict for verification."""
    assert n_entries >= 9, "name-table discovery in forge_reader samples 8 records"
    metas = []
    for i in range(n_entries):
        if i == 0:
            name, cls_h, payload = "GlobalMetaFile", 0, body_bytes(7, 212)
        else:
            name = f"Synthetic_Entry_{i:02d}_{CLASSES[i % len(CLASSES)][1]}"
            cls_h = CLASSES[i % len(CLASSES)][0]
            payload = build_block_set(build_inner_container(i))
        metas.append({"i": i, "name": name, "class": cls_h,
                      "id": 0x10 if i == 0 else 0x20 + i,
                      "payload": payload})

    buf = bytearray(PAYLOAD_OFF)

    def put(off: int, data: bytes):
        if len(buf) < off:
            buf.extend(b"\x00" * (off - len(buf)))
        buf[off:off + len(data)] = data

    # --- file header
    put(0, MAGIC_SCIMITAR)
    put(0x08, b"\x00")
    put(0x09, struct.pack("<I", 27))
    put(0x0D, struct.pack("<Q", DATA_HEADER_OFF))
    put(0x15, struct.pack("<Q", 0x1000))
    put(0x1D, struct.pack("<I", 1))

    # --- payloads (compute index offsets)
    off = PAYLOAD_OFF
    for m in metas:
        m["offset"] = off
        put(off, m["payload"])
        off += len(m["payload"])
        off += (16 - off % 16) % 16  # 16-byte alignment padding
    file_size = len(buf)

    index_end = INDEX_OFF + n_entries * 20
    name_table_end = NAME_TABLE_OFF + (n_entries - 1) * NAME_RECORD_SIZE
    assert name_table_end <= PAYLOAD_OFF

    # --- data header
    dh = DATA_HEADER_OFF
    put(dh + 0x00, struct.pack("<I", n_entries))
    put(dh + 0x1A, struct.pack("<I", n_entries))
    put(dh + 0x1E, struct.pack("<I", 2))
    put(dh + 0x22, struct.pack("<Q", dh + 0x2C))          # -> descriptor 2
    put(dh + 0x2C, struct.pack("<I", n_entries))
    put(dh + 0x30, struct.pack("<I", 2))
    put(dh + 0x34, struct.pack("<Q", INDEX_OFF))          # index table offset
    # one -1 field at +0x3C: serves both the reader's "unknown u64" and the
    # documented -1 terminator (the RE'd doc offsets +0x3A/+0x42 overlap by
    # two bytes, so a single u64 keeps the index offset intact)
    put(dh + 0x3C, struct.pack("<Q", 0xFFFFFFFFFFFFFFFF))
    put(dh + 0x48, struct.pack("<I", n_entries - 1))
    put(dh + 0x4C, struct.pack("<I", index_end))
    put(dh + 0x50, struct.pack("<I", 0))
    put(dh + 0x54, struct.pack("<I", name_table_end))

    # --- index table
    idx = bytearray()
    for m in metas:
        idx += struct.pack("<QQI", m["offset"], m["id"], len(m["payload"]))
    put(INDEX_OFF, bytes(idx))

    # --- entry-0 special name slot (0xA0, name @ +0x0C) just below names
    slot = bytearray(0xA0)
    slot[0x0C:0x0C + len(metas[0]["name"])] = metas[0]["name"].encode()
    put(NAME_TABLE_OFF - 0xA0, bytes(slot))

    # --- name records
    for m in metas[1:]:
        rec = bytearray(NAME_RECORD_SIZE)
        struct.pack_into("<i", rec, 0x00, len(m["payload"]))
        struct.pack_into("<Q", rec, 0x04, 0x5000 + m["i"] * 16)
        struct.pack_into("<I", rec, 0x10, m["class"])
        struct.pack_into("<I", rec, 0x28, TS_BASE + m["i"])
        rec[0x2C:0x2C + len(m["name"])] = m["name"].encode()
        put(NAME_TABLE_OFF + (m["i"] - 1) * NAME_RECORD_SIZE, bytes(rec))

    with open(path, "wb") as f:
        f.write(buf)
    return {"path": path, "entries": metas, "size": file_size,
            "index_end": index_end, "name_table_end": name_table_end}


def main(argv=None):
    ap = argparse.ArgumentParser(description="synthetic .forge writer")
    ap.add_argument("out")
    ap.add_argument("--entries", type=int, default=12)
    a = ap.parse_args(argv)
    info = build_forge(a.out, a.entries)
    print(f"wrote {a.out}: {info['size']:,} B, {a.entries} entries")
    for m in info["entries"]:
        print(f"  [{m['i']:>2}] id {m['id']:#x} off {m['offset']:#x} "
              f"{len(m['payload']):>6,} B  {m['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
