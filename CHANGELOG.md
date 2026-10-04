# Changelog

## v1.1.1 — 2026-10-05

- Removed the CI workflow: the hosting account is billing-locked, so
  GitHub Actions jobs cannot start. The 19-check self-test and the
  publication gate remain — both run locally in seconds, no CI needed.

## v1.1.0 — 2026-10-05

- **The forge census** (`docs/forge-census.md`): all 40 archives /
  357,161 entries / 107 classes; per-archive table with roles; type
  distribution with inferred names marked †.
- **Synthetic archive writer** (`tools/forge_synth.py`): clean-room
  spec-v27 fixture, zero game content, deterministic bytes.
- **Self-test + CI**: `tests/selftest.py` (19 checks: parse, name-table
  discovery, decompress round-trip, extract, CLI smoke, determinism);
  GitHub Actions workflow runs gate + tests on every push.
- `docs/extraction-pipelines.svg` — mesh/texture lanes from container to
  asset.
- `CONTRIBUTING.md` — the three house rules.
- Correction: dlc_20 is **The Last Maharaja** (census entry-name evidence:
  TLM_*, Duleep Singh), not Dreadful Crimes as first inferred from the
  `dl2` sound-pack codename.

## v1.0.0 — 2026-10-05

- Initial publication: forge container spec + deep analysis, Uplay R1 ABI
  map (89 exports), Steam interfaces, IAT analysis, .UBX packer notes,
  exe static surface (12 named exports), install layout, localization.lang
  spec.
- Tools: `forge_reader.py`, `mesh_extract.py`, `texture_extract.py`,
  `dump_module.py`, `pub_gate.py`.
- MIT license.
