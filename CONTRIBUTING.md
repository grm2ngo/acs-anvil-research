# Contributing

Small, evidence-first project — contributions welcome, with three rules.

## 1. Facts only, computed

Every claim in `docs/` should be reproducible: a tool run, a parse, a
measured number. If you add a fact, say how it was obtained (command or
script). Unverified hypotheses are fine **if marked as such** — see the
hypothesis tables in `localization-lang.md` for the pattern.

## 2. No game content

No bytes, dumps, assets, name dumps, or derived binaries from any Ubisoft
file. Tools must run on files the user supplies. If your change needs a
real game file to test, use the synthetic fixture instead:

```bash
python tools/forge_synth.py test.forge   # clean-room v27 container
python tests/selftest.py                 # 19 checks, no game files
```

## 3. Gate must stay green

`python tools/pub_gate.py` (PII / contamination sweep) must print
`ALL CLEAN` before you push. CI runs it on every commit, plus the
self-test above.

---

Practical notes:

- Python 3.10+, stdlib only for the core tools; `lzallright` is optional
  (listing works without it, compressed-block decompression needs it).
- Keep new SVG diagrams on an opaque canvas (GitHub dark mode) and run
  `python tools/_audit/svg_geometry_lint.py docs/*.svg`.
- Docs are plain Markdown, one topic per file, lowercase-hyphen names.
