# .forge Format Analysis — Assassin's Creed Syndicate (AnvilNext)

Status: COMPLETE for reading. Verified against all 24 forge files (33.4 GB,
188,328 entries, 100% named, all offsets validated). Decompression (LZO1X)
and multi-resource container parsing verified on samples.

Tools: `system/tools/forge/forge_reader.py` (list / info / extract / census),
`system/tools/forge/texture_extract.py` (TextureMap -> PNG/DDS, §12),
`system/tools/forge/mesh_extract.py` (Mesh -> OBJ + Entity linkage, §14).
Samples: `system/evidence/forge-samples/` — textures in
`system/evidence/forge-samples/textures/`, mesh/entity `.res` bodies in
`system/evidence/forge-samples/meshes/`, exported OBJs in
`system/evidence/forge-samples/meshes/obj/`.

## 1. Executive summary

A `.forge` file is Ubisoft Anvil's package archive ("scimitar" heritage,
magic `scimitar` + version 27). Structure in one picture:

```
+---------------------------+ 0x0
| file header               |
+---------------------------+ 0x41A (fixed)
| data header + descriptors |
+---------------------------+ 0x476
| index table  (20 B/entry) |
+---------------------------+
| name table (192 B/entry)  |
|  + special entry-0 slot   |
+---------------------------+
| entry payloads            |  block sets: LZO1X-compressed chunks
|  ...                      |    wrapped in multi-resource containers
+---------------------------+
| tail directory copy       |  (redundant TOC; some forges)
+---------------------------+ file end, padded to 0x8000
```

Everything is little-endian. IDs are u64. The same format family is used
from at least AC3 through Ghost Recon Wildlands (see §6); Syndicate
differences vs the newer Wildlands dialect are called out below.

## 2. File header (0x00-0x20)

| off | type | value (observed) | meaning |
|-----|------|------------------|---------|
| 0x00 | char[8] | `scimitar` | magic |
| 0x08 | u8 | 0 | unknown |
| 0x09 | u32 | 27 (0x1B) | format version |
| 0x0D | u64 | 0x41A | offset of data header |
| 0x15 | u64 | 0x1000 | unknown (alignment hint?) |
| 0x1D | u32 | 1 | unknown |

The data-header offset has been 0x41A in every Syndicate forge examined,
including the empty 32 KB stubs.

## 3. Data header (at 0x41A)

Relative offsets from 0x41A:

| off | type | meaning |
|-----|------|---------|
| +0x00 | u32 | entryCount N |
| +0x1A | {u32 N, u32 2, u64 -> next descriptor} | descriptor 1 |
| +0x2C | {u32 N, u32 2, u64 indexTableOffset} | descriptor 2 (0x476) |
| +0x3C | u64 | offset of tail-directory copy (-1 = none, DataPC.forge) |
| +0x44 | u64 | -1 terminator (observed) |
| +0x4C | {u32 ~N, u32 indexEnd, u32 0, u32 nameEnd} | table extents |

Notes:
- Wildlands-era docs describe a chained "DataHeader2" section list with a
  5000-entry cap. Syndicate files observed use a SINGLE section even at
  69,414 entries (DataPC_ACVI_London.forge); the descriptor fields exist
  but no chaining was needed.
- The tail-directory copy sits after the payloads and mirrors the index +
  name tables: `{u64 0, u64 self+0x30, u64 -1, u32 N, u32 unk,
  u64 tailIndexOff, u64 tailNameOff}`. Not needed for reading.
- Field arithmetic is NOT reliable across files (name-table start varies).
  The parser therefore discovers the name table by validating that record
  `+0x00 == index[i].size` for i >= 1 — robust on all 24 files.

## 4. Index table (20 bytes/entry, entry order)

| off | type | meaning |
|-----|------|---------|
| +0x00 | u64 | rawDataOffset (absolute file offset) |
| +0x08 | u64 | fileDataID (unique per forge; entry 0 is always id 0x10) |
| +0x10 | u32 | rawDataSize (bytes on disk) |

Validated on all 24 files: offsets ascending, `off+size <= file size`,
payloads contiguous in index order, file end = last payload padded up to
0x8000.

## 5. Name table

- Entry 0 (GlobalMetaFile, id 0x10) occupies a special slot with its name at
  +0x40, located right before the regular records. [CORRECTED 2026-10-05 by
  origin-loop L5c hexdump measurement: the slot is **212 B** with the ASCII
  name "GlobalMetaFile" at slot+0x40 (= +0x2C of the 192-byte pseudo-record
  view) — this earlier "~0xA0 / name @+0x0C" reading was an off-by-
  convention; entry 0 IS named, and a parser keying +0x0C reads N−1 names.
  Evidence: ORIGIN-LOOP1-20261005.md #55-#56, measured on 3 forges.]
- Entries 1..N-1: 192-byte records, name at +0x2C (= 44, same as Wildlands):

| off | type | meaning |
|-----|------|---------|
| +0x00 | i32 | rawDataSize (== index size; validation key) |
| +0x04 | u64 | primary resource id |
| +0x0C | u32 | 0 |
| +0x10 | u32 | class hash = CRC32(Anvil class name) |
| +0x14 | i32[2] | 0 |
| +0x1C | i32 | next count |
| +0x20 | i32 | prev count |
| +0x24 | i32 | 0 |
| +0x28 | u32 | unix timestamp (2015-10..2016-03 observed = build dates) |
| +0x2C | char[128] | entry name, NUL-terminated |
| +0xAC | i32[5] | trailing fields |

Names are NOT guaranteed unique; address entries by fileDataID.
The class hash at +0x10 enables a type census WITHOUT decompressing.

## 6. Entry payloads — block sets

One payload = one or more consecutive block sets:

| off | type | meaning |
|-----|------|---------|
| +0x00 | u64 | magic 0x1004FA9957FBAA33 |
| +0x08 | i16 | version (2 in Syndicate; 1 reported in Wildlands) |
| +0x0A | u8 | compression (0 and 1 both = LZO1X family) |
| +0x0B | u16 | maxBlockSize (0x8000) |
| +0x0D | u16 | maxBlockSize2 (0x8000) |
| +0x0F | i32 | blockCount |
| +0x13 | blockCount × {i32 uncompressedSize, i32 compressedSize} | sizes |
| then | blockCount × {u32 checksum, data[compressedSize]} | blocks |

- Syndicate uses the **i32** size dialect (Wildlands uses u16).
- `compressedSize == uncompressedSize` ⇒ stored raw (no compression).
  Observed ~27% raw / 73% LZO blocks.
- Checksum = Adler-32 over the STORED bytes with both accumulators
  zero-initialised ⇒ exactly `zlib.adler32(block, 0)`.
  Verified 845/845 blocks across two forges.
- Compression byte 1 ⇒ LZO1X. `lzallright` (pip) decompresses these
  streams correctly (all samples verified).

### Set structure is load-bearing
Stock payloads chain several block sets: a small leading set (often stored
raw) containing the resource TOC, then body sets. Community evidence from
the same engine family (Wildlands) shows that repacking everything as a
single block set makes the retail game black-screen even though the data
decompresses fine. Replacement tooling must mirror the original set
structure.

## 7. Decompressed payload — multi-resource container

```
u16 resCount
resCount × { u64 resourceId, u32 recordSize, u16 flags }   ; 14 B TOC entries
resCount × {
    u32 classHash        ; CRC32 of class name
    u32 bodySize
    u32 nameLen
    char name[nameLen]
    u8  gap[]            ; usually one NUL, sometimes more; preserve verbatim
    u8  body[bodySize]   ; at record_start + recordSize - bodySize
}
```
Resource body starts with `01, u64 resourceId, u32 classHash` (mirrors of
TOC values; the leading 0x01 byte is Syndicate-specific framing).

### Exception entries (no container)
- `GlobalMetaFile` (entry 0, id 0x10): raw data, no block-set magic.
- `PrefetchingFileInfos` (last entry): has the magic but block count parses
  as nonsense — contains entry fileDataIDs only; pass through verbatim.
- The three 32 KB `_gi`/`_grid` stub forges contain exactly these two
  bookkeeping entries and nothing else.

## 8. Class hash dictionary (CRC32 of class name)

Confirmed against Syndicate data (crc32 computed and matched to observed
hashes, with name-evidence):

| hash | class | evidence |
|------|-------|----------|
| 0984415E | Entity | weapon entity templates |
| 415D9568 | Mesh | UnitCube, *_LOD0 |
| 0FA3067F | Animation | UI idle animations |
| 85C817C3 | Material | materials inside containers |
| A2B7E917 | TextureMap | *_DiffuseMap/_NormalMap/_SpecularMap |
| 1D4B87A3 | (texture, TopMip) | *_TopMip — name unresolved |
| BCFB3C7A | MaterialTemplate | "* Material Template" |
| D70E6670 | TextureSet | *_GroundField_Set |
| 6E3C9C6F | LocalizationPackage | LocalizationPackage_English |
| B1420AD1 | GraphicsConfig | GraphicsConfig |
| E5A83560 | GameBootstrap | Game Bootstrap Settings |
| 2CC42429 | GameFix | Game Fix |
| 49F387B1 | SoundBanksLoadOnDemand | SoundBanksLoadOnDemand_* |
| 8DDA228D | SoundInitSettings | SoundInitSettings |
| B4E69FA1 | EngineOptions | EngineOptions |
| FFC5A970 | TagDictionnaries | TagDictionnaries_ACVI |
| 24AECB7C | Skeleton | (from Wildlands docs) |
| 18B9D8B1 | (Wwise voice pack) | large voice packs — name unresolved |
| E6545731, 971A842E, B22B3E61, 51DC6B80, A826919A, 2EE12657 | unresolved | see census |

## 9. DataPC.forge census (2183 entries)

| count | class | notes |
|-------|-------|-------|
| 1700 | TextureMap | textures (engine-internal format, not DDS) |
| 156 | unknown hE6545731 | test/design entities (TST_LD_*) |
| 137 | TopMip textures h1D4B87a3 | *_TopMip texture variants |
| 74 | Entity | weapon/entity templates |
| 44 | LocalizationPackage | per-language text |
| 19 | Animation | |
| 17+14 | unknown (AI, props) | |
| 10 | Mesh | base shapes (UnitCube...) |
| 5 | MaterialTemplate | |
| 1 each | GraphicsConfig, GameBootstrap, GameFix, SoundBanksLoadOnDemand | |

- No Lua/Python scripts found; Syndicate logic is not shipped as plain
  scripts in forges (configs like GameFix/EngineOptions are binary blobs).
- No standalone DDS/PNG files; textures are TextureMap resources in the
  engine's own pixel container (needs a separate TextureMap decoder).
- Sounds: no Wwise `.bnk` files stored raw; audio is inside container
  entries — big voice packs (h18B9D8B1, e.g. ACVI_CWL_STA_*_Voice_Pack in
  DataPC_ACVI_London.forge) plus SoundBanksLoadOnDemand metadata lists.
- Across ALL 24 forges: 188,328 entries, 100% named, all tables validated.

## 10. Reader usage

```
python forge_reader.py list    <forge> [--limit N]
python forge_reader.py info    <forge>
python forge_reader.py extract <forge> <name-or-id> <outdir> [--raw]
python forge_reader.py census  <forge>
```
`extract` writes `<name>.raw` (payload as stored), `<name>.dec`
(decompressed container) and per-resource `<name>__<res>_h<hash>.res`
bodies (capped at 64). Requires `pip install lzallright` for decompression.

`replace_entry()` exists as an experimental skeleton (single-block-set,
same-size-only rewrite). Real replacement must mirror original block-set
structure and patch both index and name-table sizes; see warning in §6.

## 11. Community knowledge & sources

- Ghost Recon Wildlands AnvilNext 2.0 documentation (closest public spec,
  same engine family; Syndicate = i32 size dialect + version 2 block sets):
  https://github.com/Firejumper93/GhostReconWildlands-AnvilNext2.0-Documentation
  (docs/02-formats.md — container, block sets, LZO1X, zero-init Adler-32,
  multi-resource container, exceptions, writer constraints)
- Mischa-Alff/broadside wiki (credited by the above for the container
  format write-up)
- AnvilToolkit (Kamzik123) — main community unpack/repack tool (Nexus
  Mods; source not readily public)
- theawesomecoder61/Blacksmith — forge viewer/extractor for Odyssey/
  Origins/Valhalla (newer forge generation)
- zenhax/xentax archive threads — original reverse engineering (sites
  mostly offline; content lives in web archives)

## 12. TextureMap layout (DECODED)

Tool: `system/tools/forge/texture_extract.py` (info / decode / forge / scan).
Samples: `system/evidence/forge-samples/textures/` (PNG + DDS, visually
verified). TextureMap = class hash `A2B7E917`; its streamed top-mip
companion = class `1D4B87A3` ("TopMip", the `*_TopMip` entries).

### 12.1 TextureMap body (fixed 0x7E-byte header + pixel data)

After the standard 13-byte resource framing (`01, u64 resourceId,
u32 classHash`), two parallel u32 texture descriptors follow. All offsets
below are file-absolute; field grid verified byte-exact on ~30 textures
across DataPC.forge and DataPC_ACVI_London_grid.forge (1700-entry census:
100% of fmt 2/3/5/8 entries match the implied mip-chain byte arithmetic).

| off | type | meaning | evidence |
|-----|------|---------|----------|
| +0x0D | u32 | width | 4/16/64/128/256/512/1024/2048 seen; matches name context |
| +0x11 | u32 | height | non-square (512x1024 bark, 128x512 scaffold...) |
| +0x15 | u32 | 1 | constant |
| +0x19 | u32 | pixelFormat enum | see 12.4 |
| +0x1D | u32 | 1 | constant |
| +0x21 | u32 | sRGB content flag | 1 for diffuse/specular, 0 for normal/height |
| +0x25 | u32 | mipCount = log2(max(w,h))+1 | 4x4->3, 16->5, 1024->11; 0 = single mip |
| +0x29 | u32 | usage enum | 0 diffuse, 1 normal, 2 specular, 3 height, 11 gfx; 4/5/7/10 rare |
| +0x2D | u32 | flags | 0 or 0x100 |
| +0x31 | u32 | 0 | |
| +0x35 | u64 | TopMip resourceId (companion) | 0 = none; sizes confirm it holds mip 0 |
| +0x3D | u64 | 0 | |
| +0x46 | u32 | 0x13237FE9 | constant hash in every sample |
| +0x4A | u32 | 1 | |
| +0x4E | u32 | 7 | |
| +0x52 | u32 | width (repeat of +0x0D) | descriptor B |
| +0x56 | u32 | height | |
| +0x5A | u32 | 1 | |
| +0x5E | u32 | mipCount | |
| +0x62 | u32 | pixelFormat | |
| +0x66 | u32 | 1 | |
| +0x6A | u32 | sRGB | |
| +0x6E..0x79 | | zero padding | |
| +0x7A | u32 | pixel data length | == bodyLen - 0x7E in every sample |
| +0x7E | ... | pixel data | see 12.3 |

Unresolved: the u8 pair at +0x2F/+0x30 (values 0x00/0x09 or 0x00/0x16
observed) groups textures in a way that does not correlate with format,
size, usage or forge.

### 12.2 TopMip companion body

| off | type | meaning |
|-----|------|---------|
| +0x00 | u8/u64/u32 | framing: `01, u64 resourceId, u32 1D4B87A3` |
| +0x0D | u32 | pixel data length (== exactly ONE mip at full w×h) |
| +0x11 | ... | pixel data, same block format as the parent TextureMap |
| end | +9 | 9 trailing bytes after the data (meaning unknown) |

Evidence: `ACVI_GEN_ALL_Bark_02_DiffuseMap_TopMip` = 0x4001A bytes =
0x11 + 0x40000 + 9, and 0x40000 = 512×1024×0.5 B = the missing top mip
of its 512x1024 BC1 parent; decoding those 0x40000 bytes as DXT1 yields
clean bark (offset 0x1A instead shifts everything and yields noise).
TopMip bodies for the London_grid "FAKE" ground textures are NOT stored
in DataPC_ACVI_London_grid.forge — streamed top mips can live in other
forges; `texture_extract.py forge` warns when the companion is absent.

### 12.3 Pixel data layout

- Standard GPU block order, **LINEAR** — no tiling, no Morton/128x128
  swizzle. Decoded images (bark, swamp, shop signs, icons, cubemap face)
  are pixel-coherent, proving block row-major order.
- Mips are contiguous, **largest first**.
- If `TopMip rid` is present the TextureMap body holds mips 1..N (its
  top stored mip is width>>1 x height>>1); otherwise mips 0..N.
- Each mip = ceil(w/4) × ceil(h/4) blocks (min 1 block), or w×h×bpp when
  uncompressed.
- A few chains are short by one 8-16 B tail mip (e.g. Bark_02_DiffuseMap:
  87400 stored vs 87416 computed); the decoder tolerates truncated tails
  and reports unaccounted bytes.
- mipCount 0 (fmt 0/1/10 placeholders) = single mip.

### 12.4 pixelFormat enum (@ +0x19)

bpp verified by exact mip-chain size fits across the 1700-texture
DataPC.forge census; formats 2,3,4,5,7,8 verified by visual decode:

| fmt | format | bytes | evidence |
|-----|--------|-------|----------|
| 0 | RGBA8 | 4/px | "Default Diffuse Texture" data = `50 50 50 ff` ×16 |
| 1 | 4 B/px, layout unresolved | 4/px | 1 entry ("Noise Gradient Texture" 256x1) |
| 2 | BC1/DXT1 | 8/block | bark diffuse decodes clean; BC4 interpretation = noise |
| 3 | BC1/DXT1 | 8/block | CoalHole diffuse decodes clean with correct colors |
| 4 | BC2/DXT3 | 16/block | UI_Icon_Star = transparent golden star |
| 5 | BC3/DXT5 | 16/block | swamp diffuse = coherent organic terrain |
| 7 | cubemap, 16-B blocks, 6 faces, each a full mip chain | 524448 = 6×87408 | face 0 decodes as BC3 = white Animus room |
| 8 | BC5 | 16/block | swamp normal = proper purple/embossed normal map |
| 9 | R8 | 1/px | ZoneOverlapPattern byte values |
| 10 | placeholder | 6 B | "IndexCubeTexture" (1x1) |
| 13 | R32F | 4/px | `00 00 80 3f` (1.0f) ×16 in DefaultDepthTexture |

fmt 2 vs 3: both are 8-byte-block DXT1 and both decode as BC1; the
semantic difference (sRGB variant? punch-through alpha?) is unresolved.
DataPC.forge fmt census: 5×683, 8×476, 2×~371, 3×28, 0×~243 (mostly
usage 11 gfx), 4×12, 7/9/10/13/1 single digits.

### 12.5 Usage

```
python texture_extract.py info   <texture.res>
python texture_extract.py decode <texture.res> [-o DIR] [--topmip topmip.res]
                                   [--png-mip N] [--no-png|--no-dds]
python texture_extract.py forge  <file.forge> <name-or-id> [more...] [-o DIR] [--deep]
python texture_extract.py scan   <file.forge> [limit]
```

PNG output is the largest available mip (BC5 rendered as a normal-map
preview, R32F tonemapped 0-1); DDS output is lossless with every stored
mip (classic DXT1/DXT3/DXT5 fourcc, or DX10 header for BC5/RGBA8/R8/R32F,
cubemaps flagged CAPS2+DX10 array 6). `forge` auto-merges the TopMip
companion when it is in the same forge (searches the same entry, then
TopMip/TextureMap-primary entries; `--deep` scans everything).

## 13. Mesh / Entity census (all 24 forges, name-table class hashes)

18,075 Mesh + 1,083 Entity primary entries live in 16 of the 24 forges
(class hash scan, no decompression needed; §5 +0x10 field):

| forge | Mesh | Entity |
|-------|------|--------|
| DataPC_ACVI_London.forge | 13,017 | 810 |
| DataPC_ACVI_SIN_WW1.forge | 1,469 | 85 |
| DataPC_ACVI_Prologue_1_BowRailway_assets.forge | 959 | 0 |
| DataPC_ACVI_Tower_London.forge | 808 | 0 |
| DataPC_ACVI_WhiteRoom_assets.forge | 806 | 0 |
| DataPC_ACVI_Prologue_2_Countryside_assets.forge | 803 | 0 |
| DataPC_ACVI_TitleScreen_assets.forge | 168 | 0 |
| DataPC.forge | 10 | 74 |
| DataPC_ACVI_London_grid.forge | 20 | 110 |
| DataPC_extra.forge | 15 | 0 |
| DataPC_ACVI_Prologue_2_Countryside.forge | 0 | 3 |
| DataPC_ACVI_Prologue_2_Countryside_grid.forge | 0 | 1 |
| **total** | **18,075** | **1,083** |

Entity containers typically hold the weapon's actual meshes: a DataPC
Entity entry = { Entity, h51DC6B80 (unknown class), Material, Mesh LOD0,
TextureSet } — 5-7 resources. Mesh-primary entries (Unit* primitives,
*_LOD0 assets) = { Mesh, Material, MaterialTemplate }.

## 14. Mesh / Entity resource layout (Mesh DECODED to OBJ)

Tool: `system/tools/forge/mesh_extract.py`. Samples: `.res` bodies under
`system/evidence/forge-samples/meshes/`, exported OBJs under
`.../meshes/obj/` (visually verified via ASCII renders: cube faces, sphere
dome, kukri recurved blade, tree canopy+trunk, hanging hair strands).

### 14.1 Mesh body — header (variable length, three flavours)

After the standard 13-byte framing (`01, u64 resourceId, u32 415D9568`):

| off | type | meaning | evidence |
|-----|------|---------|----------|
| +0x11 | u32 | 0 (flavour A/B) / 1 (some skinned) | hair meshes set 1 |
| +0x18 | 6-7×f32 | bbox min/max — **only primitive meshes** (Unit*); weapons/props leave 0 | UnitCube (-1,-1,-1)..(1,1,1); Plane ±8; zero in Kukri/Tree |
| +0x20.. | | flavour A (static: primitives, weapons, props, trees): zero padding to anchor | |
| +0x20.. | | flavours B/C (skinned hair etc.): N × 79-byte bone records, first marked by GUID fragment `a1 e7 f0 9e` | LongHairRight01: 1 record; SideBurns: 4+ records |
| anchor | 5B | **constant `43 ee 51 c3 01`** — present in every flavour; at +0x52 in flavour A, later in B/C | all 233 sample meshes |
| anchor+9 | u16 | **vertex stride**: 20 (static), 28 (Plane/UnitQuad), 32/40 (skinned hair) | 219×20, 2×28, hair 32/40 |
| anchor+0x11 | 6×f32 | second bbox: world/instance-space for props, positive-octant copy for primitives — NOT the local bbox, do not scale verts with it | Tree (0.82,0.14,9.03)..(6.03,6.42,9.75) vs local verts ±0.7; Kukri real extents |

Count/LOD tables follow (flavour-dependent; tree has extra submesh counts
3,3,3,111,9,3..., kukri 1,1,67,1,0,1) — not needed for geometry extraction.

### 14.2 Geometry chain

The vertex/index buffers follow the header as a packed
(4-byte-unaligned!) stream:

```
[u32 vertBufferSize][vertex records, stride bytes each]
[u32 indexBufferSize][u16 triangle list]
```

| mesh | vb @ | stride | verts | ib @ | u16 idx | real tris (stitch) |
|------|------|--------|-------|------|---------|--------------------|
| UnitCube | +0x90 | 20 | 24 | +0x274 | 192 | 12 (+52) |
| UnitQuad | +0x90 | 28 | 4 | +0x104 | 192 | 2 (+62) |
| UnitSphere | +0x90 | 20 | 100 | +0x864 | 576 | 160 (+32) |
| Kukri18_LOD0 | +0x90 | 20 | 2,927 | +0xE540 | 12,864 | 4,228 (+60) |
| Tree_01_LOD0 | +0xA0 | 20 | 7,277 | +0x23928 | 23,616 | 7,713 (+159) |
| LongHairRight01_GP_LOD0 | +0xE1 | 40 | 1,990 | +0x137D5 | 6,240 | 2,080 (+0) |
| SideBurnsShortA_CIN_LOD0 | (scan) | 40 | 1,580 | (scan) | 4,380 | 730 (+0) |

- Index buffer = u16 triangle list **padded with degenerate triangles**
  (all indices = last vertex). Real triangles come first; the real count
  also appears in the tail metadata (kukri tail repeats `2927` (verts) and
  `0x1084` = 4,228 (tris) exactly). Export drops degenerates.
- Because the header length varies, `mesh_extract.py` LOCATES the chain by
  scanning every byte offset for a u32 that (a) divides by the stride,
  (b) is followed `size` bytes later by a plausible u16 index buffer whose
  max index < vertexCount and reaches > half the buffer. Strides are tried
  largest-first: a too-large stride fails the index bound, a too-small one
  fails the coverage test (this catches the SideBurns half-coverage trap).

### 14.3 Vertex record (stride 20; stride 28/32/40 add fields)

| off | type | meaning | evidence |
|-----|------|---------|----------|
| +0x00 | i16 ×3 | **position, ÷ 16384.0** | UnitSphere: every decoded vertex has \|p\| = 1.000 (perfect unit sphere); UnitCube corners ±1.0 = bbox; Kukri 0.06×0.54×1.82 m |
| +0x06 | i16 | small value (±2, -1); suspected engine mirror/side selector for primitives | cube face pairs duplicated with w = +2 / -2 |
| +0x08 | 4×i8 | snorm8 ×3 + ~0 pad; per-face constant on the cube, smooth on the sphere — **NOT the normal** (Kukri blade is flat in X but values cluster on (1,1,0)/(1,0,1)/(0,1,1) diagonals); likely tangent frame | kukri: 2,171 distinct values in 2,927 verts |
| +0x0C | 4×i8 | second snorm8 group, same character | |
| +0x10 (stride-4) | u16 ×2 | **UV** — 0..2047 (11-bit) or 0..65535 scale depending on mesh (auto-detected by observed max) | cube face corners = (0,0)/(2047,0)/(0,2047)/(2047,2047); Kukri UVs span [0.004,0.998]² with seams (1,873 distinct in 2,927 verts) |
| +0x14.. | | stride-28 records: +8B mostly zero; stride 32/40 (skinned): bone weights/indices (NOT decoded) | |

Position scaling proof: the divisor is FIXED 16384, not bbox-relative
(Plane uses ±1.78 of its ±8 bbox; tree i16 z-axis uses 97% of range while
x/y use 34% — a bbox-proportional mapping is impossible; i16/16384 gives
a 3.9 m tree and 1.0 m sphere).

### 14.4 Half-geometry primitives (engine mirror)

Unit* primitives store only HALF the object: UnitCube's 24 verts form 3
face directions (-Z, -X, +Y), each appearing TWICE with w16 = ±2 and
slightly different tangent/UV groups; UnitSphere's 100 verts all have
y ≥ 0 (a hemisphere). The engine reconstructs the full shape at render
time (mirror flag presumably the +0x06 i16). Exported OBJs of primitives
therefore show half shells; content meshes (weapons, trees, hair) are
complete (kukri/hair render 100% vertex-index coverage as full objects).

### 14.5 Entity -> Mesh/Material linkage

Entity bodies (class 0984415E) embed references to sibling resources as
`[u8 0x01][u64 sibling resourceId]` records. Kukri_18 Entity body (0x649 B):
references Mesh rid 0x5EE2BC224E @+0x3C6 (the LOD0), Material
0x5EE2BC21F3 @+0x40B/+0x415, h51DC6B80 resource 0x5EE2BC224C
@+0x39A/+0x3B0. Within one entry the sibling rids share a GUID batch
prefix (0x5EE2BC2x). `mesh_extract.py forge --entities` resolves these
against the container contents automatically. The TextureSet is not
referenced by the Entity directly (Material -> TextureSet -> TextureMap
chain, rid at TextureMap +0x35 per §12).

### 14.6 Usage

```
python mesh_extract.py info    <mesh.res>
python mesh_extract.py obj     <mesh.res> [more...] [-o DIR]
                                    [--keep-stitch] [--no-uv]
python mesh_extract.py forge   <file.forge> <name-or-id> [more...]
                                    [-o DIR] [--entities]
python mesh_extract.py scan    <file.forge> [limit]
```

`obj` writes positions + UVs + recomputed smooth normals (the stored
tangent groups are not decoded, §14.3) and drops stitch triangles.
Validation built into every export: real/stitch triangle split,
position-merged edge manifold check, zero-area count, vertex-coverage.

### 14.7 Unresolved / future work

- +0x06 i16 semantics (mirror selector hypothesis), the two snorm8 groups
  (tangent frame?), the tail submesh/LOD metadata tables (kukri: counts +
  3× GUID 0xA57387EF + mesh GUID 0x5EE2BC21F3), the cube's second vertex
  copy near the tail.
- Tree LOD0: first index buffer references 5,844 of 7,277 verts (80%) —
  remaining verts likely serve a second (non-standard-chain) index list.
- Skinned vertex extra fields (bone weights/indices) and the 79-byte bone
  records (bind transforms, 6×f32 + GUID each) are located but not decoded.
- Bulk `.res` extraction of the other 15 mesh-bearing forges (~18k entries)
  is mechanical: reuse the extraction script pattern from
  `meshes/DataPC/` (manifests included).

## 15. Open questions / next steps

1. Resolve remaining class hashes (AI/prop classes, Wwise pack class) —
   brute-force with a bigger Anvil vocabulary or extract the CRC table
   scan from the game executable. (TopMip class resolved: 1D4B87A3.)
2. TextureMap decoder: DONE (§12) for every format found in
   DataPC.forge. Remaining texture unknowns: fmt 1 channel layout,
   fmt 2 vs 3 semantics, TopMip 9 trailing bytes, +0x2F/+0x30 pair.
   Bulk decode of the 65k-entry London_gi forges is I/O work, not
   reverse-engineering work.
3. Resource-body schemas per class: Mesh DONE (§14, positions/UV/indices);
   Entity references mapped (§14.5). Remaining: §14.7 items (tangent
   groups, skinned weights, submesh tables).
4. Full repack path: mirror block-set layout, patch index + name sizes +
   tail directory copy, pad to 0x8000. Only entry replacement (not count
   changes) is community-verified as safe in this engine family.
5. The u64 at data-header +0x3C (tail TOC offset) is -1 in DataPC.forge
   despite that file having payloads — confirm where (whether) its tail
   copy lives before relying on it.
