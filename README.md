# acs-anvil-research

Format tooling, specifications, and reverse-engineering notes for
**Assassin's Creed Syndicate** (AnvilNext, 2015) — produced by independent
interoperability and security research on a legally owned copy.

## What's here

| Area | Where | One line |
|---|---|---|
| `.forge` container tools | `tools/` | read/index/extract meshes & textures from the game's 40 `.forge` archives |
| Forge format spec | `docs/forge-format.md`, `docs/forge-format-analysis.md` | container layout, index/name tables, block sets, LZO1X |
| Uplay R1 loader ABI map | `docs/uplay-r1-semantics.json` | all 89 exports: thunk map, arg-register order, referenced strings |
| Steam shim interfaces | `docs/steam-ifaces.json` | the 9 interfaces the shipped 2014-era steam_api64 exposes |
| IAT architecture notes | `docs/iat-analysis.md` | why this title has no classic IAT and what that implies |
| `.UBX` packer research notes | `docs/ubx-packer-architecture.md` | behavior documentation of the title's custom protector |
| Agent working laws | `docs/methodology/` | the evidence-first / verify-by-computation workflow used to produce all of the above |

## Usage

Everything operates on **files you supply** — nothing from the game ships
in this repo.

```bash
# list/index a .forge archive
python tools/forge_reader.py "path/to/DataPC.forge"

# extract meshes to OBJ / textures to PNG-class decoders
python tools/mesh_extract.py --help
python tools/texture_extract.py --help

# out-of-process memory-image dumper (research instrument)
python tools/dump_module.py --help
```

Requirements: Python 3.10+ (uses only the standard library for the
reader; extractors document their optional deps inline).

## Verification discipline

Every fact in `docs/` was produced under an evidence-first workflow
(constants re-derived by computation, cross-checked by independent
methods, adversarially reviewed) — see `docs/methodology/`.
`tools/pub_gate.py` is the lint used before publication (PII/contamination
sweep over this tree).

## Status

Snapshot 2026-10-05, distilled from an active research workspace;
formats documented at the level the tools exercise (container, index,
name tables, mesh/texture layouts). Deeper entry-type coverage is
ongoing research.

## Legal

- Independent research; **not affiliated with or endorsed by Ubisoft**.
- **No game content is included** — no code, assets, or data derived from
  the game's files. Tools require your own legally obtained copy.
- Published for interoperability and security-research purposes.
- License: MIT (see `LICENSE`).
