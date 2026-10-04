# ACS.exe — static PE surface (the named interop points)

Everything on this page is computed from the shipped, packed executable's
headers (pefile, pure parse — no runtime, no dumping). Use it to identify a
matching copy and to find the **only stable, named entry points** the
executable itself advertises.

Copy fingerprint: `sha256 6e25f759…ca10c5a2` (38,386,360 bytes).

## Header

| Field | Value |
|---|---|
| Machine | x86-64 (`0x8664`) |
| Subsystem | 2 — GUI |
| Image base | `0x140000000` |
| TimeDateStamp | 2025-12-05 13:52:09 UTC (relinked/patched after the 2015 release) |
| Authenticode | present (security directory) |

## Sections

Nine sections have `SizeOfRawData = 0` — they are **virtual**: the protector
materializes them at runtime (see
[`ubx-packer-architecture.md`](ubx-packer-architecture.md)). Only the
protector's own sections, plus `.rsrc`, carry file bytes.

| Section | VA | Virtual size | Raw size | Entropy (raw) |
|---|---|---|---|---|
| `.text` | `0x1000` | `0x2b0740f` | 0 | — |
| `.rdata` | `0x2b09000` | `0x19f8d80` | 0 | — |
| `.data` | `0x4502000` | `0x2e62608` | 0 | — |
| `.pdata` | `0x7365000` | `0x2f5adc` | 0 | — |
| `.shared` | `0x765b000` | `0x4001c` | 0 | — |
| `.tls` | `0x769c000` | `0x109` | 0 | — |
| `_RDATA` | `0x769d000` | `0x2f50` | 0 | — |
| `.xbld` | `0x76a0000` | `0x92` | 0 | — |
| `.UBX0` | `0x76a1000` | `0x8e76b5` | 0 | — |
| `.UBX1` | `0x7f89000` | `0x340` | `0x400` | 1.28 |
| `.UBX2` | `0x7f8a000` | `0x2305770` | `0x2305800` | 7.96 |
| `.rsrc` | `0xa290000` | `0x191c16` | `0x191e00` | 4.51 |

`.UBX2` (36.7 MB, entropy 7.96) is the packed body; the entry point targets it.

## The import wall (31 DLLs, 33 functions)

One function per DLL — except `KERNEL32` (3). This is a packer-rebuilt IAT,
not a real dependency list; the story is in
[`iat-analysis.md`](iat-analysis.md).

- **Graphics**: `d3d11.dll`, `dxgi.dll`, `d3d9.dll`, `D3DCOMPILER_43.dll`, `OPENGL32.dll`
- **Input**: `DINPUT8.dll`, `XINPUT9_1_0.dll`, `HID.DLL`
- **Platform middleware** (by name): `uplay_r1_loader64.dll`, `bink2w64.dll`,
  `GFSDK_ShadowLib.win64.dll`, `GFSDK_SSAO_D3D11.win64.dll`,
  `GFSDK_TXAA.win64.dll`, `NvGsa.x64.dll`, `Tobii.EyeX.Client.dll`
- **System**: `KERNEL32.dll` (3), `USER32.dll`, `GDI32.dll`, `ADVAPI32.dll`,
  `SHELL32.dll`, `ole32.dll`, `OLEAUT32.dll`, `VERSION.dll`,
  `WindowsCodecs.dll`, `WINTRUST.dll`, `CRYPT32.dll`, `bcrypt.dll`,
  `WS2_32.dll`, `IPHLPAPI.DLL`, `WINMM.dll`, `SETUPAPI.dll`

`sqlitefs64.dll` (the engine's big-file middleware) is **not** here — it is
loaded dynamically at runtime.

## Exports — the named entry points (12)

RVAs below are as shipped in the packed image; the code bytes behind them are
materialized at runtime by the protector.

| # | Export (demangled) | RVA | Notes |
|---|---|---|---|
| 1 | `scimitar::GraphicLibFacade::GraphicLibFacade(GraphicLibFacade const&)` | `0x177cd50` | copy constructor |
| 2 | `scimitar::GraphicLibFacade::GraphicLibFacade()` | `0x177cd50` | default constructor — **same RVA as #1** |
| 3 | `scimitar::GraphicLibFacade::~GraphicLibFacade()` (virtual) | `0x177eb80` | destructor |
| 4 | `scimitar::GraphicLibFacade::operator=(GraphicLibFacade const&)` | `0x1c9f7c0` | copy-assign |
| 5 | `scimitar::GraphicLibFacade` vftable | `0x2c9bb70` | data symbol, in `.rdata` |
| 6 | `G4_GetSP()` | `0x1c83b90` | stack-pointer getter |
| 7 | `G4_GetBP()` | `0x1c83b94` | base-pointer getter — **4 bytes after GetSP** |
| 8 | `GetDataBufferSize` | `0x9920` | low-RVA quartet, near `.text` start |
| 9 | `InitBufferSynchro` | `0x9930` | 〃 |
| 10 | `ReadData` | `0x9960` | 〃 |
| 11 | `WriteData` | `0x9a90` | 〃 |
| 12 | `InstantiateGraphicLibFacade` | `0x1ee9190` | factory |

The `G4_Get*` pair reads like a pair of adjacent 4-byte register-getter
thunks. `scimitar` is the engine's internal namespace — the same word that
opens every `.forge` file.

## What this is good for

- **Tool/version identification**: header + section layout + sha256 identify
  the exact build without running it.
- **Interop hooks**: the 12 exports are the only *named* code addresses in
  the image — the natural anchor points for external tooling on an unpacked
  image, and the C++ ABI notes (vftable, copy-ctor sharing an RVA) document
  how the engine surfaces its graphic library.
- Boundaries-only function maps (≈259k ranges) were produced during this
  research but are intentionally **not** published here; the curated, named
  surface above is the interoperability-relevant subset.
