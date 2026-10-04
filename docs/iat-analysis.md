# IAT ANALYSIS — U2 conclusion (2026-10-03, evidence-first)

Tools: `iat_reconstruct.py` (static pass), `iat_xref.py` (xref pass),
`iat_peek.py` (pointer peek). Evidence: `knowledge/iat-reconstruction.json`,
`knowledge/iat-xref.json`, dump A (acs-image-17356.bin).

## Findings

1. **The static import table is INTACT in the dump** (import dir RVA
   `0x8A1B5B0`, 31 descriptors) but it is the PACKER'S MINI-IAT: each DLL's
   FirstThunk points into `.UBX1` (RVA 0x7F89000, 832 B = 104 qwords) with
   only **33 imported functions total** — matching the on-disk stub table.
2. **xref sweep of all .text indirect calls** (`call/jmp qword ptr
   [rip+…]`): only **132 distinct slots / 2,480 sites**. Pointer peek shows
   these are NOT a Windows IAT:
   - most hot slots point INTO the image's own `.text` (engine-internal
     dispatch tables, e.g. slot 0x70A5028 → fn 0x246BF20, 403 uses);
   - many are NULL at menu-time (lazy/late-bound);
   - only a few point at system modules directly.
3. Conclusion: **the game's real import binding is dynamic** — function
   tables in `.data` filled at boot by the packer's resolver (lives in
   `.UBX0`). There is NO classic big IAT to reconstruct.

## Implication for U3 (rebuild design)

- The rebuilt PE does NOT need Scylla-style IAT repair: keep the intact
  33-entry import directory + `.UBX1` thunks as they are in the dump; the
  OS loader resolves those 33 at load.
- **`.UBX0` must be KEPT** in the clean image: its resolver populates the
  `.data` function tables at boot. Stripping `.UBX0` would leave them NULL
  (game dead). This aligns with the earlier verdict: VM stays as harmless
  runtime.
- `.UBX2` stays droppable (0 calls) — BUT it is the on-disk container the
  packer's entry stub normally unpacks FROM; in a rebuilt-already-unpacked
  image the entry must bypass the unpacker entirely → **OEP hunt required**
  (find the `.UBX0` handoff that jumps to the original entry point).
- Post-unpack CUT phase is unaffected: cutting DRM/online call-sites works
  on `.text`/`.data` directly.
