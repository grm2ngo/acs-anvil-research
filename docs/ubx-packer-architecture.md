# THE .UBX PACKER — COMPLETE ARCHITECTURE DOSSIER (new base, 2026-10-03)

Every statement below is evidence-backed (artifact named inline). This
document is the NEW BASE for all unpacking work: nothing may contradict
it without new evidence. Lineage: SSOT §5-6, FRICTION #16-24, traces,
8 runtime dumps.

## 1. Identity

- Custom packer, sections `.UBX0/.UBX1/.UBX2` (+ `.xbld` build marker).
  VMProtect-STYLE lineage: polymorphic mutation junk at EP, name-hash
  import resolution, VM interpreter — but NOT stock VMP (sections
  renamed; zero public documentation — searched 2026-10-03, no hits).
- `VMProtectSDK64.dll` ships in the game folder (2013 build, 2.x-era
  SDK) but is NEVER loaded at runtime (no static import, no late load —
  cut-proven). The packer self-contains its protection.
- No active Denuvo (51 offline boots with stub backends; zero strings).

## 2. File/memory structure

| Element | Fact | Evidence |
|---|---|---|
| Code sections on disk | `.text/.rdata/.data/.pdata/.shared/.tls/_RDATA/.xbld/.UBX0` all `SizeOfRawData=0` — content exists ONLY at runtime | PE parse |
| `.UBX2` | 36.7 MB packed payload, entropy 7.117, contains the stub + packed image | PE parse |
| `.UBX1` | 832 B pointer table = the mini-IAT thunks (33 imports: KERNEL32×3 GetVersion*, 1/export for the rest) | iat_reconstruct |
| Static imports | 31 DLLs × 33 functions; OFT hint/name RVAs valid in dumps | iat_reconstruct + check_oft |
| Real API binding | `.data` function tables filled per-boot by the packer's resolver — NO classic IAT | iat-xref + iat_peek |
| EP (on disk) | RVA 0x8F9EECC in `.UBX2` — polymorphic mutation stub | EP disasm |
(instruction excerpt omitted for publication)

## 3. Boot sequence (traced end-to-end, `OEP-EARLYTRACE.txt`)

```
t=0      DLL loads (imports bind; version.dll proxy loads FIRST — pre-EP)
~1-2s    STUB runs inside on-disk .UBX2 mapping: scatter 0x80xxxxx
         → decrypt loop 0x80CF25D (rcx walks a large buffer)
         → countdown loop 0x814F820 (rdx=0x6d9b const)
         → .text phase (rdx=0x140001000 = .text base)
~2-4s    .text unpacked (OEP sig appears) — data sections still ZERO
         (stage-1 evidence: dump acs-image-13120)
+later   data sections materialize (stage-2: dump acs-image-6428)
+later   CRT initializer tables filled LAST (0x7159b58 / 0x715a360,
         count=0x17) — stage-3 evidence: dumps 16268/12456/7196/17336
throughout ORCHESTRATION 0x825C-0x825D block (907 instrs, ZERO globals,
(instruction excerpt omitted for publication)
(instruction excerpt omitted for publication)
~0x75833000, outside image)
         RESOLVER hash loop 0x82194CC..0x8219523: CRC-style 256×4 table
         @~0x8219060, name-hash API resolution (86% of trace samples)
         VM helpers in .UBX0 (0x7716644/0x7987424/0x790262d)
handoff  jumps to OEP with REGISTER STATE (al read by first test;
         mid-.text first-sighting at 0x2358E90 was POST-OEP initializer)
→ menu   (~300s to first gameplay per user observation)
```

## 4. Protection inventory (all tested)

| Layer | Behavior | Evidence |
|---|---|---|
| Header integrity | ANY section-table edit → 0xC0000005/0xDEADC0DE at load; only unreferenced tail-pad diffs tolerated (E3R: 14,822 B OK) | hybrid v1 death; E3R notes |
| Import verification | Swapping an imported DLL's implementation (Tobii stub) → death t≈8s | legacy gate |
| In-process probing | RPM(self)/VirtualQuery walks → fail-fast 0xC0000409 | legacy audit |
| Anti-debug L1 | IsDebuggerPresent-class — DEFEATED by PEB hide (BeingDebugged+NtGlobalFlag) | debug tooling |
| Anti-debug L2 | NtQueryInfo DebugPort-class — kills ATTACHED debuggers pre-OEP; NOT hideable externally; IN-PROCESS int3+VEH invisible to it | attach runs died; v6 no-crash |
| VM virtualization | 5,718 functions (~2.2%), 1:1 caller→helper, interpreter in .UBX0 (2,698 computed dispatches), self-contained (43 out-calls) | vm_callees/vm_calls |
| Staged unpack | .text → data → init-tables; anti-race windows are ms-scale | stage-1/2/3 dumps |

## 5. Attack attempts ledger (what was tried, outcome)

| # | Approach | Outcome |
|---|---|---|
| 1 | clean-1..4 (dump + EP=OEP) | EP reached; crash EXEC@0 post-entry — missing per-boot bindings + handoff regs |
| 2 | Shims on clean | CRASH — AND shims poison even the ORIGINAL (Test A) — shims unusable until rewritten |
| 3 | Hybrid (original + materialized sections) | Death: header integrity |
| 4 | Debugger attach + INT3 at OEP | L2 anti-debug kills pre-OEP |
| 5 | CreateProcess under debugger + PEB hide | Same L2 death |
| 6 | freeze-proxy (version.dll, in-proc signature watch + thread freeze + external dump) | WORKS ×4 — the golden dumps |
| 7 | trace-proxy (1ms burst RIP sampling) | WORKS ×2 — the chain map |
| 8 | v6/v6.1 in-proc INT3+VEH at OEP | No capture in 2 tries — plant window race (condition fired post-handoff) OR VEH order; game unharmed |

## 6. What the base establishes (the new foundation)

1. We OWN the observation layer: freeze/trace/in-proc-instrumentation all
   work repeatedly without tripping any protection.
2. The packer is FULLY mapped: sequence, regions, resolver mechanics,
   protection layers, handoff register-dependence.
3. The single missing datum: the exact register state at handoff (v6's
   goal) — an instrumentation-reliability problem, not an unknown.
4. Game dir is inviolable during experiments unless a run is staged
   (auto-deploy pattern); every experiment restores vanilla (hash-pinned).

## 7. Ranked next attacks (from THIS base)

A. **v7 instrumentation fix** (small): plant INT3 when OEP sig FIRST
   appears (stage-1) — .text-integrity risk is testable; add
   planted-at/hit-at logging to distinguish race vs VEH-order.
B. **Emulation route** (research-validated): run the original stub under
   Unicorn/qiling to OEP, capture full state — immune to all anti-*.
C. **Path H** (runtime host) as parallel pragmatic track.
