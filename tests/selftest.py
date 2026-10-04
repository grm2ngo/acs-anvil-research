#!/usr/bin/env python3
"""Self-test: synthetic fixture parses, lists, and round-trips through
forge_reader — no game files required. Exit 0 = pass. Used by CI."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import forge_reader  # noqa: E402
import forge_synth   # noqa: E402


def main() -> int:
    failures = []

    def check(label, cond):
        print(("  ok  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as td:
        fx = os.path.join(td, "synthetic.forge")
        meta = forge_synth.build_forge(fx, 12)

        forge = forge_reader.ForgeFile(fx)
        try:
            check("entry count == 12", forge.entry_count == 12)
            named = sum(1 for e in forge.entries if e.name)
            check("12/12 named", named == 12)
            check("magic/version", forge.magic == b"scimitar"
                  and forge.version == 27)
            check("entry 0 is GlobalMetaFile",
                  forge.entries[0].name == "GlobalMetaFile"
                  and forge.entries[0].file_id == 0x10)
            check("index offsets ascending",
                  all(a.offset < b.offset for a, b in
                      zip(forge.entries, forge.entries[1:])))

            # round-trip: decompressed payload must equal the synthetic
            # inner container byte for byte
            for i in (1, 5, 11):
                want = forge_synth.build_inner_container(i)
                got, sets = forge.decompress_entry(forge.entries[i])
                check(f"entry {i} decompress round-trip ({len(want)} B)",
                      got == want and len(sets) == 1)
                check(f"entry {i} adler ok",
                      all(b[3] for b in sets[0].blocks))

            # container parse: names + class hashes survive
            data, _ = forge.decompress_entry(forge.entries[3])
            res = forge.parse_container(data)
            check("resource TOC parsed",
                  res is not None and res[0].name == b"synthetic_res_3_0")

            # find() by name and by id
            check("find by name",
                  forge.find("Entry_07").index == 7)
            check("find by id", forge.find("0x2a").index == 10)
        finally:
            forge.close()

        # extract writes files
        forge = forge_reader.ForgeFile(fx)
        try:
            out = os.path.join(td, "out")
            written = forge.extract_entry(forge.entries[2], out)
            check("extract writes raw+dec",
                  any(p.endswith(".raw") for p in written)
                  and any(p.endswith(".dec") for p in written))
        finally:
            forge.close()

        # CLI surface smoke (same interpreter)
        for args in (["info", fx], ["list", fx, "--limit", "4"],
                     ["census", fx]):
            r = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "tools", "forge_reader.py")] + args,
                capture_output=True, text=True)
            check(f"CLI {args[0]} exit 0", r.returncode == 0)

        # determinism: same bytes twice
        fx2 = os.path.join(td, "again.forge")
        forge_synth.build_forge(fx2, 12)
        check("deterministic build",
              open(fx, "rb").read() == open(fx2, "rb").read())

    print(f"\n{len(failures)} failure(s)" if failures else "\nALL PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
