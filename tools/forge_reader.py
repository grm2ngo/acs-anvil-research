#!/usr/bin/env python3
"""
forge_reader.py - Reader/extractor for Ubisoft Anvil(Next) .forge archives.

Validated against Assassin's Creed Syndicate (AnvilNext, 2015):
  DataPC_ACVI_London_grid.forge, DataPC.forge, DataPC_ACVI_TitleScreen*.forge

Container layout (little-endian throughout):

  FILE HEADER
    0x00  char[8]  magic "scimitar"
    0x08  u8       0
    0x09  u32      version (27 = 0x1B for Syndicate)
    0x0D  u64      offset of data header (always 0x41A seen)
    0x15  u64      0x1000 (unknown; alignment?)
    0x1D  u32      1 (unknown)
    ...   zeros to data header

  DATA HEADER (at header.u64@0x0D, i.e. 0x41A)
    +0x00 u32 entryCount N
    +0x1A {u32 N, u32 2, u64 -> descriptor2}        (descriptor 1)
    +0x2C {u32 N, u32 2, u64 indexTableOffset}      (descriptor 2; 0x476 seen)
    +0x3A u64  unknown (-1 in DataPC.forge, some offset in London_grid)
    +0x42 u64  -1 terminator? (seen)
    +0x48 {u32 ~N, u32 indexTableEnd, u32 0, u32 nameTableEnd}
    Index table then name table follow before the payload region.

  INDEX TABLE (20 bytes/entry, in entry order)
    u64 rawDataOffset      absolute offset of payload in this file
    u64 fileDataID         unique id (entry 0 is always id 0x10 GlobalMetaFile)
    u32 rawDataSize        payload size in bytes

  NAME TABLE
    special slot for entry 0 (GlobalMetaFile): name at +0x0C
    entries 1..N-1: 192-byte records, name at +0x2C (44):
      +0x00 i32  rawDataSize  (== index size; used for validation)
      +0x04 u64  resource id of primary resource
      +0x0C u32  0
      +0x10 u32  class hash (CRC32 of Anvil resource class name)
      +0x14 i32[2]
      +0x1C i32  next count
      +0x20 i32  prev count
      +0x24 i32  0
      +0x28 u32  unix timestamp
      +0x2C char[128] name (NUL terminated)
    The parser discovers the name table start by validation (sizes must match
    the index table) because the gap between index end and name table varies.

  ENTRY PAYLOAD (one or more consecutive "block sets")
    u64  magic 0x1004FA9957FBAA33
    i16  version (2 in Syndicate; 1 reported for Wildlands)
    u8   compression (0/1 = LZO1X family; see below)
    u16  maxBlockSize (0x8000)
    u16  maxBlockSize2 (0x8000)
    i32  blockCount
    blockCount * { i32 uncompressedSize, i32 compressedSize }   <- i32 dialect
    blockCount * { u32 checksum, data[compressedSize] }
      - checksum = Adler-32 with BOTH accumulators zero-initialised,
        i.e. zlib.adler32(stored_bytes, 0), over the *stored* bytes
      - compressedSize == uncompressedSize  =>  stored raw (no compression)

  DECOMPRESSED PAYLOAD is usually a multi-resource container:
    u16 resCount
    resCount * { u64 resourceId, u32 recordSize, u16 flags }     (TOC)
    resCount * { u32 classHash, u32 bodySize, u32 nameLen,
                 char name[nameLen], u8 gap[], u8 body[bodySize] }
    body starts { u64 resourceId, u32 classHash, ... }
  Exceptions: GlobalMetaFile (raw, no magic), PrefetchingFileInfos
  (last entry, magic but non-standard block layout), possibly others.

Dependencies: lzallright (pure-Python-friendly LZO1X; pip install lzallright).
Only needed for decompression; listing/parsing works without it.

Usage:
  python forge_reader.py list   <file.forge> [--limit N]
  python forge_reader.py info   <file.forge>
  python forge_reader.py extract <file.forge> <name-or-id> <outdir> [--raw]
  python forge_reader.py census  <file.forge>
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time
import zlib

try:
    from lzallright import LZOCompressor

    def lzo_decompress(data: bytes, uncompressed_size: int) -> bytes:
        return LZOCompressor.decompress(data, uncompressed_size)

    HAS_LZO = True
except ImportError:
    HAS_LZO = False

MAGIC_SCIMITAR = b"scimitar"
MAGIC_BLOCKSET = 0x1004FA9957FBAA33
INDEX_RECORD_SIZE = 20
NAME_RECORD_SIZE = 192
NAME_OFFSET = 0x2C  # name at byte 44 within a name record (entries >= 1)
MAX_EXTRACT_RESOURCES = 64  # cap per entry to avoid 17k-file explosions


class ForgeFormatError(Exception):
    pass


def zero_adler32(data: bytes) -> int:
    """Adler-32 with both accumulators initialised to zero (Anvil variant)."""
    return zlib.adler32(data, 0)


class BlockSet:
    __slots__ = ("version", "compression", "max_block_size", "blocks", "data")

    def __init__(self, version, compression, max_block_size, blocks, data):
        self.version = version
        self.compression = compression
        self.max_block_size = max_block_size
        self.blocks = blocks  # list of (uncompressed, compressed, checksum, ok)
        self.data = data


class Resource:
    __slots__ = ("res_id", "record_size", "flags", "class_hash", "body_size",
                 "name", "body_offset")

    def __init__(self, res_id, record_size, flags):
        self.res_id = res_id
        self.record_size = record_size
        self.flags = flags
        self.class_hash = 0
        self.body_size = 0
        self.name = b""
        self.body_offset = 0


class ForgeEntry:
    __slots__ = ("index", "offset", "file_id", "size", "name", "class_hash",
                 "resource_id", "timestamp")

    def __init__(self, index, offset, file_id, size):
        self.index = index
        self.offset = offset
        self.file_id = file_id
        self.size = size
        self.name = None
        self.class_hash = 0
        self.resource_id = 0
        self.timestamp = 0

    def __repr__(self):
        name = self.name or "<unnamed>"
        return (f"ForgeEntry(idx={self.index} id={self.file_id:#x} "
                f"off={self.offset:#x} size={self.size} name={name!r})")


class ForgeFile:
    def __init__(self, path: str):
        self.path = path
        self.f = open(path, "rb")
        self.file_size = os.fstat(self.f.fileno()).st_size
        self.magic = None
        self.version = 0
        self.data_header_offset = 0
        self.entry_count = 0
        self.descriptor_index_offset = 0
        self.index_offset = 0
        self.index_end = 0
        self.name_table_end = 0
        self.unknown_offset = 0  # u64 at data header +0x3A
        self.entries: list[ForgeEntry] = []
        self._parse()

    # ------------------------------------------------------------------ parse
    def _parse(self):
        f = self.f
        f.seek(0)
        head = f.read(0x20)
        self.magic = head[:8]
        if self.magic != MAGIC_SCIMITAR:
            raise ForgeFormatError(f"{self.path}: bad magic {self.magic!r}")
        self.version, = struct.unpack_from("<I", head, 0x09)
        self.data_header_offset, = struct.unpack_from("<Q", head, 0x0D)
        if self.version != 27:
            print(f"warning: forge version {self.version} != 27 "
                  "(layout may differ)", file=sys.stderr)

        f.seek(self.data_header_offset)
        dh = f.read(0x60)
        if len(dh) < 0x50 or dh[:4] == b"\x00\x00\x00\x00":
            self.entry_count = 0
            return
        self.entry_count, = struct.unpack_from("<I", dh, 0)

        if self.entry_count == 0:
            return

        # descriptor 2 at +0x2C holds the index table offset
        self.descriptor_index_offset, = struct.unpack_from("<Q", dh, 0x2C + 8)
        self.unknown_offset, = struct.unpack_from("<Q", dh, 0x3C)
        self.index_end, = struct.unpack_from("<I", dh, 0x466 - self.data_header_offset)
        self.name_table_end, = struct.unpack_from("<I", dh, 0x46E - self.data_header_offset)

        # --- index table, validated
        idx_off = self.descriptor_index_offset
        f.seek(idx_off)
        raw = f.read(self.entry_count * INDEX_RECORD_SIZE)
        if len(raw) < self.entry_count * INDEX_RECORD_SIZE:
            raise ForgeFormatError("index table truncated")
        prev_off = 0
        for i in range(self.entry_count):
            off, fid, size = struct.unpack_from("<QQI", raw, i * INDEX_RECORD_SIZE)
            if off < prev_off or off + size > self.file_size:
                raise ForgeFormatError(
                    f"index[{i}] fails validation (off={off:#x} size={size:#x})")
            prev_off = off
            self.entries.append(ForgeEntry(i, off, fid, size))
        if self.index_end < idx_off:
            self.index_end = idx_off + self.entry_count * INDEX_RECORD_SIZE

        # --- name table, discovered by validation
        self._parse_names()

    def _parse_names(self):
        f = self.f
        n = self.entry_count
        if n < 2:
            return
        # search window between end of index table and first payload
        search_start = self.index_end
        search_end = min(self.entries[1].offset, search_start + 0x1000)
        want = [e.size for e in self.entries[1:max(n, 8)][:8]]
        f.seek(search_start)
        window = f.read(search_end - search_start)
        base = None
        for cand in range(0, len(window) - NAME_RECORD_SIZE * 2, 2):
            ok = True
            for k, wsize in enumerate(want):
                got, = struct.unpack_from("<I", window,
                                          cand + k * NAME_RECORD_SIZE)
                if got != wsize:
                    ok = False
                    break
            if ok:
                base = search_start + cand
                break
        if base is None:
            print("warning: name table not located; entries stay unnamed",
                  file=sys.stderr)
            return
        f.seek(base)
        raw = f.read((n - 1) * NAME_RECORD_SIZE)
        for i in range(1, n):
            e = self.entries[i]
            rec = raw[(i - 1) * NAME_RECORD_SIZE: i * NAME_RECORD_SIZE]
            e.resource_id, = struct.unpack_from("<Q", rec, 0x04)
            e.class_hash, = struct.unpack_from("<I", rec, 0x10)
            e.timestamp, = struct.unpack_from("<I", rec, 0x28)
            nm = rec[NAME_OFFSET:NAME_OFFSET + 128].split(b"\x00")[0]
            e.name = nm.decode("utf-8", "replace")
        # entry 0: special GlobalMetaFile slot just before the name table
        slot = base - 0xA0
        if slot > 0:
            f.seek(slot)
            rec = f.read(0xA0)
            nm = rec[0x0C:0x0C + 128].split(b"\x00")[0]
            if nm:
                self.entries[0].name = nm.decode("utf-8", "replace")

    # ----------------------------------------------------------------- access
    def read_entry_raw(self, entry: ForgeEntry) -> bytes:
        self.f.seek(entry.offset)
        return self.f.read(entry.size)

    def iter_block_sets(self, payload: bytes):
        """Yield (BlockSet, offset_of_next_set) for each set in a payload."""
        pos = 0
        while pos + 0x13 <= len(payload):
            magic, ver, comp, mbs1, mbs2, bc = struct.unpack_from(
                "<QhBHHI", payload, pos)
            if magic != MAGIC_BLOCKSET:
                break
            p = pos + 0x13
            if p + 8 * bc > len(payload) or bc < 0 or bc > 1 << 20:
                break  # e.g. PrefetchingFileInfos: magic but nonsense layout
            sizes = [struct.unpack_from("<ii", payload, p + 8 * i)
                     for i in range(bc)]
            p += 8 * bc
            blocks = []
            data = bytearray()
            ok_all = True
            for us, cs in sizes:
                if p + 4 + cs > len(payload) or cs < 0 or us < 0:
                    ok_all = False
                    break
                chk, = struct.unpack_from("<I", payload, p)
                blk = payload[p + 4: p + 4 + cs]
                ok = zero_adler32(blk) == chk
                blocks.append((us, cs, chk, ok))
                if cs == us:
                    data += blk
                elif HAS_LZO:
                    try:
                        data += lzo_decompress(blk, us)
                    except Exception as ex:
                        raise ForgeFormatError(f"LZO block failed: {ex}")
                else:
                    raise ForgeFormatError(
                        "compressed block but lzallright not installed")
                p += 4 + cs
            if not ok_all:
                break
            yield BlockSet(ver, comp, mbs1, blocks, bytes(data)), p
            pos = p

    def decompress_entry(self, entry: ForgeEntry) -> tuple[bytes, list[BlockSet]]:
        """Return (concatenated decompressed data, list of block sets)."""
        payload = self.read_entry_raw(entry)
        out = bytearray()
        sets = []
        for bs, _ in self.iter_block_sets(payload):
            sets.append(bs)
            out += bs.data
        if not sets:
            return payload, []  # raw entry (GlobalMetaFile etc.)
        return bytes(out), sets

    def parse_container(self, data: bytes):
        """Parse a multi-resource container. Returns list[Resource]."""
        count, = struct.unpack_from("<H", data, 0)
        if count == 0 or 2 + count * 14 > len(data):
            return None
        res = []
        off = 2
        for _ in range(count):
            rid, rsz, fl = struct.unpack_from("<QIH", data, off)
            res.append(Resource(rid, rsz, fl))
            off += 14
        for r in res:
            if off + 12 > len(data):
                break
            r.class_hash, r.body_size, nl = struct.unpack_from("<III", data, off)
            r.name = data[off + 12: off + 12 + nl].split(b"\x00")[0]
            # body sits at the tail of the record: rec_start + record_size - body_size
            rec_start = off
            r.body_offset = rec_start + r.record_size - r.body_size
            off = rec_start + r.record_size
        return res

    def find(self, key: str):
        """Find entry by name (substring) or numeric id (decimal or 0x...)."""
        try:
            fid = int(key, 0)
        except ValueError:
            fid = None
        for e in self.entries:
            if fid is not None and e.file_id == fid:
                return e
            if e.name and key.lower() in e.name.lower():
                return e
        return None

    # ------------------------------------------------------------------ write
    def extract_entry(self, entry: ForgeEntry, outdir: str,
                      decompress: bool = True) -> list[str]:
        """Extract an entry; returns list of written file paths."""
        os.makedirs(outdir, exist_ok=True)
        base = (entry.name or f"id_{entry.file_id:#x}").replace("\\", "_")
        base = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)
        written = []
        raw_path = os.path.join(outdir, base + ".raw")
        with open(raw_path, "wb") as o:
            o.write(self.read_entry_raw(entry))
        written.append(raw_path)
        if decompress:
            try:
                data, sets = self.decompress_entry(entry)
                dec_path = os.path.join(outdir, base + ".dec")
                with open(dec_path, "wb") as o:
                    o.write(data)
                written.append(dec_path)
                res = self.parse_container(data) if sets else None
                if res:
                    for r in res[:MAX_EXTRACT_RESOURCES]:
                        rn = (r.name or b"res").decode("utf-8", "replace")
                        rn = "".join(c if c.isalnum() or c in "._-" else "_"
                                     for c in rn)[:120]
                        rp = os.path.join(
                            outdir, f"{base}__{rn}_h{r.class_hash:08x}.res")
                        with open(rp, "wb") as o:
                            o.write(data[r.body_offset:
                                         r.body_offset + r.body_size])
                        written.append(rp)
            except ForgeFormatError as ex:
                print(f"  (decompress skipped: {ex})", file=sys.stderr)
        return written

    def replace_entry(self, entry: ForgeEntry, new_data: bytes,
                      out_path: str, compression: int = 1):
        """
        EXPERIMENTAL. Write a copy of this forge with one entry's decompressed
        content replaced. The new payload is encoded as a single block set.

        WARNING (from Ghost Recon Wildlands findings, same engine family):
        stock payloads use several block sets (a small leading set with the
        resource TOC); repacking everything as ONE set can make the retail
        game black-screen even though the data decompresses fine. Prefer
        mirroring the original set layout once resource-level editing lands.
        """
        if not HAS_LZO or compression:
            raise ForgeFormatError("re-compression needs lzallright")
        # build single block set
        blocks = []
        for i in range(0, len(new_data), 0x8000):
            chunk = new_data[i:i + 0x8000]
            comp = lzo1x_decompress  # placeholder to keep API symmetric
            from lzallright import LZOCompressor as _L
            cchunk = _L.compress(chunk) if compression else chunk
            if len(cchunk) >= len(chunk):
                cchunk, cs, us = chunk, len(chunk), len(chunk)
            else:
                cs, us = len(cchunk), len(chunk)
            blocks.append((us, cs, cchunk))
        body = bytearray()
        body += struct.pack("<QhBHHI", MAGIC_BLOCKSET, 2, compression,
                            0x8000, 0x8000, len(blocks))
        for us, cs, _ in blocks:
            body += struct.pack("<ii", us, cs)
        for us, cs, cchunk in blocks:
            body += struct.pack("<I", zero_adler32(cchunk))
            body += cchunk
        new_payload = bytes(body)

        # sanity: original file offsets stay valid only if size unchanged
        if len(new_payload) != entry.size:
            raise ForgeFormatError(
                f"new payload size {len(new_payload)} != original "
                f"{entry.size}; full reflow (index/name/payload move) is not "
                "implemented in this skeleton")

        with open(self.path, "rb") as src, open(out_path, "wb") as dst:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                dst.write(chunk)
            dst.flush()
        with open(out_path, "r+b") as dst:
            dst.seek(entry.offset)
            dst.write(new_payload)
        return out_path

    def close(self):
        self.f.close()


# ---------------------------------------------------------------------- CLI
# CRC32(class name) == class hash. Confirmed empirically against Syndicate:
CONFIRMED_CLASS_HASHES = {
    0x0984415E: "Entity",
    0x415D9568: "Mesh",
    0x0FA3067F: "Animation",
    0x85C817C3: "Material",
    0xA2B7E917: "TextureMap",
    0xBCFB3C7A: "MaterialTemplate",
    0x6E3C9C6F: "LocalizationPackage",
    0xB1420AD1: "GraphicsConfig",
    0x2CC42429: "GameFix",
    0xE5A83560: "GameBootstrap",
    0x49F387B1: "SoundBanksLoadOnDemand",
    0xD70E6670: "TextureSet",
    0x8DDA228D: "SoundInitSettings",
    0xB4E69FA1: "EngineOptions",
    0xFFC5A970: "TagDictionnaries",
    0x24AECB7C: "Skeleton",  # from Wildlands docs, same family
}
# additional guesses that will resolve if their hash ever shows up
KNOWN_CLASS_NAMES = [
    "AnimSet", "EntityTemplate", "Prefab", "WorldData", "Sound", "Font",
    "Shader", "Cloth", "Hair", "Vegetation", "Physics", "Camera", "Particle",
    "Texture", "Skeleton", "WwiseBank", "SoundWave", "Light", "Decal",
    "Terrain", "NavMesh", "Video", "Icon", "Scene",
]


def class_hash_to_name(h: int):
    import binascii
    if h in CONFIRMED_CLASS_HASHES:
        return CONFIRMED_CLASS_HASHES[h]
    for n in KNOWN_CLASS_NAMES:
        if binascii.crc32(n.encode()) == h:
            return n
    return None


def cmd_info(forge: ForgeFile):
    print(f"file           : {forge.path}")
    print(f"size           : {forge.file_size:#x} ({forge.file_size:,})")
    print(f"magic/version  : {forge.magic.decode()} / {forge.version}")
    print(f"data header @  : {forge.data_header_offset:#x}")
    print(f"entries        : {forge.entry_count}")
    print(f"index table @  : {forge.descriptor_index_offset:#x} "
          f"(end {forge.index_end:#x})")
    print(f"name table end : {forge.name_table_end:#x}")
    print(f"unknown u64    : {forge.unknown_offset:#x}")
    named = sum(1 for e in forge.entries if e.name)
    print(f"named entries  : {named}/{forge.entry_count}")
    first = forge.entries[1] if len(forge.entries) > 1 else None
    if first:
        print(f"first payload  : {first.offset:#x}")
    ts = [e.timestamp for e in forge.entries if e.timestamp]
    if ts:
        lo, hi = min(ts), max(ts)
        print(f"timestamps     : {time.strftime('%Y-%m-%d', time.localtime(lo))}"
              f" .. {time.strftime('%Y-%m-%d', time.localtime(hi))}")


def cmd_list(forge: ForgeFile, limit=None):
    print(f"{'#':>5} {'file_id':>14} {'offset':>10} {'size':>10} "
          f"{'class':>10}  name")
    for e in forge.entries:
        if limit and e.index >= limit:
            break
        cls = (class_hash_to_name(e.class_hash) or
               (f"h{e.class_hash:08x}" if e.class_hash else "-"))
        print(f"{e.index:>5} {e.file_id:>14x} {e.offset:>10x} "
              f"{e.size:>10,} {cls:>10}  {e.name or ''}")


def cmd_extract(forge: ForgeFile, key: str, outdir: str, raw=False):
    e = forge.find(key)
    if not e:
        print(f"entry not found: {key}", file=sys.stderr)
        return 1
    print(f"extracting {e!r}")
    files = forge.extract_entry(e, outdir, decompress=not raw)
    for p in files:
        print(f"  wrote {p} ({os.path.getsize(p):,} bytes)")
    return 0


def cmd_census(forge: ForgeFile, max_decompress=40):
    from collections import Counter
    hashes = Counter()
    for e in forge.entries:
        hashes[e.class_hash] += 1
    print(f"census of {forge.entry_count} entries by primary class hash:")
    for h, n in hashes.most_common():
        name = class_hash_to_name(h)
        print(f"  {h:08x}  x{n:<6} {name or '(unknown class)'}")
    # sample-decompress to confirm container/resource layout
    print(f"\nsampling {max_decompress} decompressible entries:")
    done = 0
    res_hash = Counter()
    for e in forge.entries[1:]:
        if done >= max_decompress:
            break
        try:
            data, sets = forge.decompress_entry(e)
        except ForgeFormatError as ex:
            continue
        if not sets:
            continue
        done += 1
        res = forge.parse_container(data)
        if res:
            for r in res:
                res_hash[r.class_hash] += 1
    print(f"resource class hashes inside containers ({done} entries sampled):")
    for h, n in res_hash.most_common(30):
        name = class_hash_to_name(h)
        print(f"  {h:08x}  x{n:<6} {name or '(unknown class)'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anvil .forge reader")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("forge")
    p = sub.add_parser("list"); p.add_argument("forge")
    p.add_argument("--limit", type=int, default=None)
    p = sub.add_parser("extract"); p.add_argument("forge"); p.add_argument("key")
    p.add_argument("outdir"); p.add_argument("--raw", action="store_true")
    p = sub.add_parser("census"); p.add_argument("forge")
    a = ap.parse_args(argv)

    forge = ForgeFile(a.forge)
    try:
        if a.cmd == "info":
            cmd_info(forge)
        elif a.cmd == "list":
            cmd_list(forge, a.limit)
        elif a.cmd == "extract":
            return cmd_extract(forge, a.key, a.outdir, a.raw)
        elif a.cmd == "census":
            cmd_census(forge)
    finally:
        forge.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
