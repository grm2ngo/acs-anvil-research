# The .forge census — 40 archives, 357,161 entries, 107 classes

Every container in the install, opened with
[`tools/forge_reader.py`](../tools/forge_reader.py): entry counts, name
coverage, and a type census across the whole game. Names were read from each
archive's name table; classes are the 4-byte type field of each index record.
Generated mechanically from the scan — no hand-typed numbers.

## Headline numbers

| Metric | Value |
|---|---|
| Archives censused | 40 (24 root + 16 dlc) |
| Total forge bytes | 58.27 GB |
| Entries | 357,161 |
| Entries with a name | 357,161 — **40 of 40 archives at 100%** |
| Distinct type classes | 107 |
| Top-3 classes' share | 72.6% |

## Type census (all archives combined)

Class names marked † are **inferred from entry-name evidence** (e.g.
`GIDB_Cell*_LOD*` ⇒ GIDBCell); unmarked names are engine-provided;
`unknown_…` means no inference yet.

| Type (class hash) | Name | Entries | % of all |
|---|---|---|---|
| `A2B7E917` | TextureMap | 104,757 | 29.3% |
| `F7D22B3C` | GIDBCell † | 89,465 | 25.0% |
| `AC2BBF68` | WorldCellDataBlock † | 65,007 | 18.2% |
| `415D9568` | Mesh | 35,549 | 10.0% |
| `85C817C3` | Material | 17,551 | 4.9% |
| `EEBB2443` | LocalCubeMap † | 14,433 | 4.0% |
| `1D4B87A3` | TopMip | 12,607 | 3.5% |
| `B22B3E61` | PropObject † | 5,506 | 1.5% |
| `989DC6B2` | UIIconDesc † | 3,556 | 1.0% |
| `18B9D8B1` | WwiseVoicePack | 1,885 | 0.5% |
| `22ECBE63` | MaterialOverwrite † | 1,762 | 0.5% |
| `0984415E` | Entity | 1,105 | 0.3% |
| `BCFB3C7A` | MaterialTemplate | 678 | 0.2% |
| `E33044BA` | ClothAsset † | 608 | 0.2% |
| `E55F39F1` | AnimStreamBlock † | 603 | 0.2% |
| `971A842E` | CharacterSet † | 598 | 0.2% |
| `49F387B1` | SoundBanksLoadOnDemand | 417 | 0.1% |
| `E6545731` | TestEntity † | 157 | 0.0% |
| `3F742D26` | TrafficSetup † | 141 | 0.0% |
| `6E3C9C6F` | LocalizationPackage | 128 | 0.0% |
| `E802B9DA` | DominoScript † | 118 | 0.0% |
| `4107267C` | BulkLODSet † | 98 | 0.0% |
| `00000000` | GlobalMetaFile | 89 | 0.0% |
| `7E6BE629` | SkinnedHairMesh † | 62 | 0.0% |
| `F29157B2` | unknown_F29157B2 | 32 | 0.0% |
| `F7485E9F` | unknown_F7485E9F | 22 | 0.0% |
| `0FA3067F` | Animation | 19 | 0.0% |
| `2D675BA2` | MergedShape † | 18 | 0.0% |
| `51DC6B80` | unknown_51DC6B80 | 17 | 0.0% |
| `63B0A8F8` | unknown_63B0A8F8 | 12 | 0.0% |
| `AADF2263` | unknown_AADF2263 | 12 | 0.0% |
| `FBB63E47` | unknown_FBB63E47 | 10 | 0.0% |
| `4DB4B1FE` | unknown_4DB4B1FE | 10 | 0.0% |
| `C69A7F31` | unknown_C69A7F31 | 8 | 0.0% |
| `D9049CF5` | unknown_D9049CF5 | 6 | 0.0% |
| `D0ACB241` | unknown_D0ACB241 | 6 | 0.0% |
| `1BF46DC6` | unknown_1BF46DC6 | 5 | 0.0% |
| `E05D09EF` | unknown_E05D09EF | 4 | 0.0% |
| `77A4447F` | unknown_77A4447F | 4 | 0.0% |
| `C427713B` | WorldTags † | 4 | 0.0% |
| `B52AC9FF` | unknown_B52AC9FF | 4 | 0.0% |
| `19E4C196` | unknown_19E4C196 | 4 | 0.0% |
| `824A23BA` | unknown_824A23BA | 3 | 0.0% |
| `8C2A387B` | Cinematic † | 2 | 0.0% |
| `85E86216` | SoundSettings † | 2 | 0.0% |
| — | *62 more classes (each ≤ 2 entries)* | 77 | 0.0% |

Reading it: this is primarily a **texture-and-world database** — TextureMap
is ~3 in 10 entries, and the two world-streaming classes (GIDBCell †,
WorldCellDataBlock †) add another ~43%. Meshes are ~10%; everything else is
a long tail of gameplay/UI/sound classes.

## Archive-by-archive

Sorted by size. "Role" summarizes census evidence (entry-name prefixes,
class mixes).

| Archive | Where | Size | Entries | Role |
|---|---|---|---|---|
| `DataPC_ACVI_London.forge` | root | 12.95 GB | 69,414 | London open world: main-city entities, meshes, animations (largest) |
| `DataPC_ACVI_London_gi.forge` | root | 7.89 GB | 65,666 | Global-illumination database (GIDB cells) for its world |
| `DataPC_ACVI_SIN_WW1.forge` | root | 3.70 GB | 8,421 | WW1 mission world 'The Darkest Hour' (Lydia Frye, 1916 London; WwiseVoicePack x94, ACVI_SIN/WW1 prefixes) |
| `dlc_21\DataPC_21_dlc.forge` | dlc_21 | 3.30 GB | 1,356 | DLC 21 'Jack the Ripper' main pack (JACK_* gameplay/UI/textures) |
| `dlc_21\DataPC_ACVI_London_21_dlc.forge` | dlc_21 | 2.93 GB | 52,803 | DLC 21 'Jack the Ripper' London world override (Cell*_DLC21_DataBlock, LocalCubeMap probes, JACK_* entries) |
| `DataPC_ACVI_Tower_London.forge` | root | 2.80 GB | 7,174 | Tower of London borough world |
| `dlc_21\DataPC_ACVI_DLC_Asylum.forge` | dlc_21 | 2.66 GB | 15,474 | DLC 21 'Asylum' world (Jack the Ripper campaign area) |
| `dlc_20\DataPC_ACVI_London_20_dlc.forge` | dlc_20 | 2.58 GB | 50,462 | DLC 20 'The Last Maharaja' London world override (Cell*_DLC20_DataBlock, Duleep Singh characters, TLM evidence) |
| `dlc_21\DataPC_ACVI_DLC_Prison.forge` | dlc_21 | 2.37 GB | 11,574 | DLC 21 'Prison' world (Jack the Ripper campaign area) |
| `dlc_21\DataPC_ACVI_DLC_Manor.forge` | dlc_21 | 2.34 GB | 10,697 | DLC 21 'Manor' world (Jack the Ripper campaign area) |
| `dlc_20\DataPC_ACVI_Tower_London_20_dlc.forge` | dlc_20 | 1.63 GB | 4,966 | DLC 20 'The Last Maharaja' Tower of London world override |
| `dlc_12\DataPC_12_dlc.forge` | dlc_12 | 1.49 GB | 2,262 | DLC 12 character-outfit pack (large; census twin of dlc_14) |
| `dlc_14\DataPC_14_dlc.forge` | dlc_14 | 1.49 GB | 2,262 | DLC 14 character-outfit pack (census twin of dlc_12) |
| `DataPC_SharedGroup_00.forge` | root | 1.49 GB | 2,086 | Cross-world shared assets (character/generic textures, LIB_ library) |
| `dlc_21\DataPC_WhiteRoom_21_dlc.forge` | dlc_21 | 1.41 GB | 2,791 | DLC 21 White Room additions (JTR) |
| `DataPC_ACVI_Prologue_1_BowRailway.forge` | root | 0.80 GB | 4,189 | Prologue 1 'BowRailway' world (intro borough) |
| `dlc_11\DataPC_11_dlc.forge` | dlc_11 | 0.78 GB | 1,156 | DLC 11 character-outfit pack (Evie/Jacob outfit materials) |
| `dlc_13\DataPC_13_dlc.forge` | dlc_13 | 0.74 GB | 1,266 | DLC 13 character-outfit pack |
| `DataPC_extra.forge` | root | 0.68 GB | 7,120 | UI icons, gear, crafting, DLC addon lists (JACK_* JTR icons, SoundBanksLoadOnDemand) |
| `DataPC_ACVI_Prologue_2_Countryside.forge` | root | 0.58 GB | 2,430 | Prologue 2 'Countryside' world |
| `dlc_21\DataPC_ACVI_DLC_Manor_gi.forge` | dlc_21 | 0.49 GB | 2,945 | DLC 21 'Manor' world (Jack the Ripper campaign area) |
| `DataPC.forge` | root | 0.43 GB | 2,183 | Global shared data: engine configs, common/UI textures, localization |
| `dlc_21\DataPC_ACVI_DLC_Asylum_gi.forge` | dlc_21 | 0.34 GB | 4,994 | DLC 21 'Asylum' world (Jack the Ripper campaign area) |
| `DataPC_ACVI_SIN_WW1_gi.forge` | root | 0.33 GB | 2,734 | Global-illumination database (GIDB cells) for its world |
| `DataPC_ACVI_Tower_London_gi.forge` | root | 0.33 GB | 5,478 | Global-illumination database (GIDB cells) for its world |
| `DataPC_ACVI_Prologue_1_BowRailway_gi.forge` | root | 0.30 GB | 2,002 | Global-illumination database (GIDB cells) for its world |
| `dlc_21\DataPC_ACVI_DLC_Prison_gi.forge` | dlc_21 | 0.25 GB | 3,694 | DLC 21 'Prison' world (Jack the Ripper campaign area) |
| `DataPC_ACVI_Prologue_2_Countryside_gi.forge` | root | 0.21 GB | 1,968 | Global-illumination database (GIDB cells) for its world |
| `DataPC_WhiteRoom_assets.forge` | root | 0.19 GB | 1,555 | Static prop/asset meshes for its world |
| `DataPC_WhiteRoom.forge` | root | 0.18 GB | 1,260 | White Room (Animus/modern-day shell) assets |
| `DataPC_ACVI_Prologue_2_Countryside_assets.forge` | root | 0.18 GB | 1,242 | Static prop/asset meshes for its world |
| `DataPC_ACVI_Prologue_1_BowRailway_assets.forge` | root | 0.16 GB | 1,253 | Static prop/asset meshes for its world |
| `DataPC_dom.forge` | root | 0.11 GB | 485 | Domino mission-logic data (DM_* subscripts, challenges, cinematics; DominoScript/AnimStreamBlock/Cinematic classes) |
| `DataPC_ACVI_TitleScreen.forge` | root | 0.09 GB | 1,221 | Title-screen world/UI assets |
| `DataPC_ACVI_TitleScreen_assets.forge` | root | 0.03 GB | 217 | Static prop/asset meshes for its world |
| `DataPC_ACVI_London_grid.forge` | root | 0.02 GB | 222 | Terrain/streaming grid cells + ground entities for its world |
| `dlc_20\DataPC_20_dlc.forge` | dlc_20 | 0.01 GB | 131 | DLC 20 'The Last Maharaja' addon config pack (TLM_* DLCAddon entries) |
| `DataPC_ACVI_Prologue_2_Countryside_grid.forge` | root | 0.00 GB | 4 | Terrain/streaming grid cells + ground entities for its world |
| `DataPC_ACVI_TitleScreen_gi.forge` | root | 0.00 GB | 2 | Global-illumination database (GIDB cells) for its world |
| `DataPC_WhiteRoom_gi.forge` | root | 0.00 GB | 2 | Global-illumination database (GIDB cells) for its world |

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
