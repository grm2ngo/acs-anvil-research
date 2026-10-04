# Assassin's Creed Syndicate `.forge` Container Format

Target build: AC Syndicate (Steam, 2025-12-05), 24 `.forge` files, 33.4 GB.
All offsets little-endian. Research date: 2026-10-03.

Status key: **[V]** = verified against on-disk files in this session,
**[C]** = from community reverse engineering (pyUbiForge / ACExplorer by
gentlegiantJGC, GPL — clone in `tools/forge/reference/ACExplorer`),
**[?]** = uncertain.

Syndicate (internal name "ACVI", 2015) uses the same Anvil forge container
generation as AC Unity (2014): magic `scimitar`, format version **27**,
LZO-compressed datafile blocks. The structure below is the Unity-lineage
layout with Syndicate specifics noted.

## 1. Related tools / prior art

| Tool | What it does | Notes |
|---|---|---|
| **ACExplorer / pyUbiForge** (gentlegiantJGC, GPL) | Full Python explorer for AC Unity forge files; parses header, tables, LZO blocks, inner containers, textures/meshes | Primary reference; archived 2021; bundles `lzo64.dll` + `texconv.exe` |
| **Blacksmith** (theawesomecoder61, C#) | Extract/convert for Odyssey/Origins/Valhalla/Steep | Newer forge generation (Oodle/Zstd); its `Compression` enum documents compression mode bytes |
| **Delutto's Ubisoft Tool** (zenhax community) | Older AC (1–Revelations) extractor | Older scimitar format |
| **AC2IconPatcher** (Bat0oo) | Reads/writes AC2-era forge with **LZO2A** | Confirms LZO2A in older titles |

Compression mode byte (from Blacksmith `Enums/Compression.cs` **[C]**):

```
0x0 LZO1X    0x1 LZO1X    0x2 LZO2A    0x4 Oodle
0x5 LZO1C    0x7 Oodle    0x8 Oodle
```

## 2. File header (first bytes of the `.forge`) **[V]**

Every Syndicate forge file begins:

```
+0x00  char[8]  "scimitar"                       73 63 69 6D 69 74 61 72
+0x08  u8       0x00 (padding)
+0x09  u32      format version = 27 (0x1B)
+0x0D  u64      file data header offset (X)
...    zero padding to (at least) 0x1000
```

Observed header bytes (identical in all sampled files) **[V]**:

```
[hex sample omitted for publication]
```

Notes:

- The 1-byte shift at +0x08 means naive 4-aligned u32 reads show `0x1B00`
  and `0x41A00`; the real fields are at unaligned offsets 9 and 13.
- In Syndicate `X = 0x41A00` (268 800) was observed in every sampled file,
  including ones far smaller than that — see "Empty stub files" below.
- pyUbiForge rejects anything `version != 27`; Syndicate matches Unity's 27.
- The remaining header bytes (+0x15: u64 = 0x10, +0x1D: u32 = 1 observed)
  are not consumed by the ACU parser; meaning unknown **[?]**.

## 3. File data header **[C]**

The 40 bytes at `X` ("DataHeader1" in Blacksmith):

```
X+0x00  u32      total entry count (cross-check for sum of sections)
X+0x04  16 bytes unknown
X+0x14  u64      unknown
X+0x1C  u32      max files per index (reported 5000 in Odyssey-era files)
X+0x20  u32      unknown
X+0x24  u64      file data offset (D)  <- read by all parsers at X+36
```

At `D` the "file data" block starts **[C]** (Blacksmith field names added;
pyUbiForge ignores the chaining field):

```
D+0x00  u32      index count (N)
D+0x04  4 bytes  padding
D+0x08  u64      index table offset
D+0x10  u64      next data section offset  ("OffsetToNextDataSection",
                                              -1/0 = last; pyUbiForge
                                              calls it file_data_offset2
                                              and ignores it; forge_parser
                                              follows the chain)
D+0x18  4 bytes  index start (Blacksmith; padding in pyUbiForge)
D+0x1C  4 bytes  index end   (Blacksmith; padding in pyUbiForge)
D+0x20  u64      name table offset
D+0x28  u64      raw data table offset (offset table per entry)
```

Large archives may chain several such sections (each with its own index
and name tables); the "max files per index" field in DataHeader1 is
reported as 5000 in Odyssey-era files.

### 3.1 Index table — N entries x 20 bytes **[C]**

```
+0x00  u64   raw data offset
+0x08  u64   datafile id
+0x10  u32   raw data size
```

### 3.2 Name table — N entries x 192 bytes **[C]**

```
+0x00   u32    raw data size (== index table raw data size)
+0x04   u64    unknown
+0x0C   u32    unknown
+0x10   u32    datafile type id (see §6)
+0x14   u64    unknown
+0x1C   u32    next-file count
+0x20   u32    previous-file count
+0x24   u32    unknown
+0x28   u32    timestamp
+0x2C   char[128]  datafile name (NUL-padded, UTF-8)
+0xAC   u32 x5 unknown
```

The datafile ids are large 64-bit hashes (pyUbiForge skips ids `0` and
`> 2**40`).

## 4. Datafile payload & compression

A datafile payload = `raw data size` bytes at `raw data offset`.

### 4.1 Uncompressed payload **[C]**

If the payload does not start with the 8-byte compression magic
`33 AA FB 57 99 FA 04 10`, the whole payload is a single uncompressed file
("format 0" in pyUbiForge terms).

### 4.2 Compressed payload **[C]**

```
+0x00  u64   magic 33 AA FB 57 99 FA 04 10
+0x08  u16   unknown
+0x0A  u8    compression mode (0/1 LZO1X, 2 LZO2A, 4/7/8 Oodle, 5 LZO1C)
+0x0B  u8[3] unknown
+0x0E  u8    section format version: 0 or 128
```

**Format 128** (the common case in ACU):

```
u32    block count
count x { u16 uncompressed size, u16 compressed size }   (size table)
then per block:
    u32     hash/checksum of the block (skipped by readers)
    bytes   compressed block data (compressed size bytes)
```

**Format 0** (rare): `u8 more-flag (==1)`, then 8 x u32 = 4
(compressed, uncompressed) pairs, then per block hash + data.

In ACU the compressed area consists of **two** consecutive such sections
(each with its own 15-byte header); their decompressed outputs are
concatenated, in order, to form the container payload. pyUbiForge requires
exactly two then end-of-data; `forge_parser.py` loops while the magic
recurs (superset, robust if Syndicate emits 1..N sections).

Blocks are typically ≤ 64 KiB uncompressed. Decompression per mode is
straight LZO/Oodle — no per-entry encryption has been observed in this
format generation **[C]**. (`u16` sizes cap blocks at 65535 bytes in
format 128.)

### 4.3 LZO1X-1 instruction set (for compression modes 0/1)

No complete public documentation of the byte format existed in the
references, so the instruction set used by `forge_parser.py`'s built-in
pure-Python decoder is recorded here (assembled from the LZO format table
and minilzo semantics; verified against minilzo cross-checks):

```
state = number of literal bytes trailing the previous match (0..3).
"state 4" means the previous instruction was a literal run.

stream start: byte t0
    t0 > 17  -> copy (t0 - 17) literal bytes, state = 4
    t0 < 16  -> same as the state-0 opcode below

opcodes:
  state 0,  op < 16    literal run: len = 3 + L   (L = op&15;
             extended when L==0: 15 + 255*zerorun + next byte)
  state 1-3, op < 16   M1 match: len 2, dist = (H<<2) + D + 1
  state 4,  op < 16    M2 match: len 3, dist = (H<<2) + D + 2049
  op 16-31  (0001HLLL) M4 match: len = 2 + L (extended when L==0:
             7 + 255*zerorun + next; extension bytes come BEFORE the
             offset), then LE16 b0/b1: dist = 16384 + (H<<14) +
             (b0>>2) + (b1<<6); new state = b0 & 3
  op 32-63  (001LLLLL) M3 match: len = 2 + L (ext 31 + ...; extension
             before offset), then LE16 b0/b1: dist = 1 + (b0>>2) +
             (b1<<6); new state = b0 & 3
  op 64-127 (01LDDDSS) len = 3 + L, dist = (H<<3) + D + 1; state = SS
  op 128-255(1LLDDDSS) len = 5 + LL, dist = (H<<3) + D + 1; state = SS

D/L/LL/SS are the named bitfields of the opcode byte; H is the byte
after the opcode. After each match, `state` literal bytes are copied
from the stream. Matches may overlap their own output (RLE semantics).
Decoders terminate on the known uncompressed size (from the block size
table), like minilzo; the "dist == 16384" end-marker is not needed.
```

## 5. Inner container ("format 128" payload) **[C]**

```
u16                  inner file count
per file (index):    u64 id, i32 data size, u16 extra count, extra x u16
per file (data):
    u32    file type id (see §6)
    u32    file size
    u32    file name length
    bytes  file name (UTF-8, may be empty -> use id)
    u8     check byte (0, or 1 -> see below)
    [check==1: 3 pad bytes, u32 count, count x 12 bytes]
    bytes  file payload (file size bytes)
```

The per-file payload then begins with its own binary format, usually
starting with the 4-byte type id (see pyUbiForge `type_readers/`).

## 6. Type ids

Datafiles and inner files carry a u32 "type id" (big-endian-looking hex by
convention, e.g. `0645ABB5`). Names below from pyUbiForge's ACU
`fileFormats.json` (full table loaded by `forge_parser.py` when the
reference clone is present). Selected ids:

```
0645ABB5 MeshData            13237FE9 CompiledTextureMap
0B1D34C1 MeshInstancingData  1FE50BE1 TextureBase
24AECB7C Skeleton            245F5CA5 TextureGradient
0984415E Entity              354FE002 TextureInput
0FA3067F Animation           07CB6A2D Terrain
31984F55 AnimSet             0E2F4444 GridPartition
0181EFE8 AnimTrackData       0B4CE0E0 NavMeshManager
2BC49864 SoundSet            228F402A RigidBody
1B478101 SoundBankDependencies  195B695E ActionKit
2B315BEA HumanSoundSet       338CDC20 DataLayerManager
0423BD15 SoundEmitter        17FB5AA8 RegionLayout
0EFFFE90 SoundSetEvent       212DD44A ParticleSystemInstanceData
```

## 7. Syndicate-specific observations **[V so far]**

- All 24 forge files carry the same 32-byte header prefix with version 27
  and `X = 0x41A00`.
- Three files are exactly 32 768 bytes:
  `DataPC_ACVI_Prologue_2_Countryside_grid.forge`, `DataPC_ACVI_TitleScreen_gi.forge`,
  `DataPC_WhiteRoom_gi.forge`. Their mtime (03:22–03:30) differs from the
  rest (02:55), and 0x41A00+44 lies past EOF — they are **empty stub
  archives** (zero-filled after the 32-byte header) rather than corrupt
  files. They contain no entries.
  (To be confirmed: whether the game build treats them as such.)
- `DataPC_ACVI_London_grid.forge` (19.6 MB) is the smallest real archive
  and the main empirical test target.

## 8. Open questions / TODO

Session status (2026-10-03): the local shell/execution adapter was down for
the entire session, so the parser could not be run against the archives.
Everything above marked **[V]** was verified by direct byte reads at session
start; the container/compression layer is implemented from the community
references and desk-checked, but not yet executed. Validation driver:
`tools/forge/run_all.bat` (or `run_tests.py` directly).

- [ ] Run `forge_parser.py info` on `DataPC_ACVI_London_grid.forge` and
      confirm: file data offset at X+36, index/name tables, entry names.
- [ ] Verify compression mode byte (expect 0/1/2 LZO) and the number of
      compressed sections per datafile (ACU uses exactly 2).
- [ ] Cross-check the pure-Python LZO1X decoder against the lzo64.dll from
      a real ACExplorer clone (`reference/ACExplorer-git`).
- [ ] Whether any Syndicate datafiles use Oodle (modes 4/7/8); check the
      game folder for `oo2core_*.dll`.
- [ ] Whether Syndicate uses chained data sections (next-section offset at
      file-data +0x10 != -1/0) for the large archives (London.forge 12.9 GB).
- [ ] Identify Syndicate-specific type ids not in the ACU table
      (`forge_parser.py identify` prints a histogram).
- [ ] Meaning of file header fields +0x15 (u64, observed 0x10) and +0x1D
      (u32, observed 1).
- [ ] Raw data table layout (per-entry offset table; not needed for reading).

## 9. Tooling in this repository

- `tools/forge/forge_parser.py` — standalone parser/extractor
  (`info`, `list [--deep|--json]`, `extract`, `extract-all`, `identify`),
  stdlib-only, with three decompression backends (LZO DLL via ctypes,
  Oodle via ctypes if present, built-in pure-Python LZO1X).
- `tools/forge/run_tests.py` — self-tests (LZO vectors) + structure dump
  of the stub/medium forge files; writes `run_tests_output.txt`.
- `tools/forge/run_all.bat` — turnkey validation + evidence extraction.
- `tools/forge/analyze_header.py`, `scan_layout.py` — header/region
  analysis scripts used during this session.
- `tools/forge/reference/` — verbatim copies of the pyUbiForge sources
  this work is based on (GPL, attribution in `reference/README.md`).
