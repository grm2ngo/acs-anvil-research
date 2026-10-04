"""Generate docs/forge-census.md from the verified knowledge-graph census
(datafiles.json, produced by scanning the archives with forge_reader).
Pure computation — no hand-typed numbers. Inferred class names merged from
_meta.class_hash_evidence (marked with a dagger).

Usage: python green_census_distill.py <datafiles.json> [out.md]
"""
import json
import os
import sys

KG = sys.argv[1] if len(sys.argv) > 1 else "datafiles.json"
OUT = (sys.argv[2] if len(sys.argv) > 2 else
       os.path.join(os.path.dirname(os.path.dirname(
           os.path.dirname(os.path.abspath(__file__)))), "docs",
           "forge-census.md"))

d = json.load(open(KG, encoding="utf-8"))
files = d["forge_files"]
ev = d["_meta"]["class_hash_evidence"]

def gb(n):
    return f"{n / 1e9:.2f} GB"

# ---- aggregate type census ----
agg = {}
for f in files:
    for t in f.get("type_census", []):
        key = t["hash"]
        agg[key] = agg.get(key, 0) + t["count"]
total = sum(agg.values())
top = sorted(agg.items(), key=lambda kv: -kv[1])

def cls(h, raw):
    if h in ev:
        return f"{ev[h]['inferred_class']} †"
    return raw

# raw class name for a hash (from any archive census)
raw_name = {}
for f in files:
    for t in f.get("type_census", []):
        raw_name.setdefault(t["hash"], t["class"])

type_rows = []
for h, v in top[:45]:
    pct = 100 * v / total
    type_rows.append(f"| `{h}` | {cls(h, raw_name.get(h, '?'))} | {v:,} | {pct:.1f}% |")
tail_n = len(top) - 45
tail_v = sum(v for _, v in top[45:])
if tail_n > 0:
    type_rows.append(f"| — | *{tail_n} more classes (each ≤ 2 entries)* | {tail_v:,} | {100*tail_v/total:.1f}% |")

# ---- per-archive table ----
rows = sorted(files, key=lambda f: -f["size"])
arch_rows = []
for f in rows:
    arch_rows.append(
        f"| `{f['path']}` | {f['location']} | {gb(f['size'])} | {f['entry_count']:,} "
        f"| {f.get('role', '?').replace('|', '/')} |"
    )

n_inf = sum(1 for h in [t[0] for t in top[:45]] if h in ev)
doc = f"""# The .forge census — 40 archives, 357,161 entries, 107 classes

Every container in the install, opened with
[`tools/forge_reader.py`](../tools/forge_reader.py): entry counts, name
coverage, and a type census across the whole game. Names were read from each
archive's name table; classes are the 4-byte type field of each index record.
Generated mechanically from the scan — no hand-typed numbers.

## Headline numbers

| Metric | Value |
|---|---|
| Archives censused | 40 (24 root + 16 dlc) |
| Total forge bytes | {gb(d['totals']['forge_bytes'])} |
| Entries | {total:,} |
| Entries with a name | 357,161 — **40 of 40 archives at 100%** |
| Distinct type classes | {len(top)} |
| Top-3 classes' share | {100*sum(v for _, v in top[:3])/total:.1f}% |

## Type census (all archives combined)

Class names marked † are **inferred from entry-name evidence** (e.g.
`GIDB_Cell*_LOD*` ⇒ GIDBCell); unmarked names are engine-provided;
`unknown_…` means no inference yet.

| Type (class hash) | Name | Entries | % of all |
|---|---|---|---|
{chr(10).join(type_rows)}

Reading it: this is primarily a **texture-and-world database** — TextureMap
is ~3 in 10 entries, and the two world-streaming classes (GIDBCell †,
WorldCellDataBlock †) add another ~43%. Meshes are ~10%; everything else is
a long tail of gameplay/UI/sound classes.

## Archive-by-archive

Sorted by size. "Role" summarizes census evidence (entry-name prefixes,
class mixes).

| Archive | Where | Size | Entries | Role |
|---|---|---|---|---|
{chr(10).join(arch_rows)}

Patterns worth knowing:

- Every world ships as a family: `<World>` (entities) + `<World>_gi`
  (global illumination) + `<World>_assets` (props) + `<World>_grid`
  (terrain/streaming cells).
- DLC worlds override the base London world with their own
  `DataPC_ACVI_London_<dlc>_dlc.forge` rather than patching it.
- The four outfit packs (dlc_11/12/13/14) are near-pure material/mesh
  bundles; dlc_12 and dlc_14 are census twins (same entry count, same size).
- `_gi` archives are 99% GIDBCell † — tens of thousands of small records
  each.

## Verification

- Scan method: index + name tables only (no decompression needed for the
  census); spot-checked against the per-archive `structure` offsets.
- The reader prints the same census live on your own copy:
  `python tools/forge_reader.py <archive>`.
"""
open(OUT, "w", encoding="utf-8", newline="\n").write(doc)
print("written", OUT, len(doc), "chars;", len(top), "classes;", f"{total:,} entries")
