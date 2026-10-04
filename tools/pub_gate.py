#!/usr/bin/env python3
"""_sweep.py — publication gate for the assembled tree (same patterns as
pubaudit_sweep.py; root parameterized; also checks D:\\ path leak)."""
import os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\me\Desktop\acs\acs-anvil-research"
PII = [
    (re.compile(r"Users\\me", re.I), "user-path"),
    (re.compile(r"Users\\(?!me\b)[A-Za-z0-9_.-]+", re.I), "other-user"),
    (re.compile(r"\bme@\w+\.\w+"), "email"),
    (re.compile(r"SteamLibrary", re.I), "machine-path"),
]
HEXRUN = re.compile(r"\b(?:[0-9a-fA-F]{2}[\s:]+){15,}[0-9a-fA-F]{2}\b")
ASM = re.compile(r"\b(?:mov|lea|push|jmp|call|test|xor|sub|add)\s+(?:r?[a-z0-9]+,)", re.I)
THIRDPARTY = re.compile(r"Copyright\s*\(c\)\s+(?!.*acs-enhance)", re.I)
STRLONG = re.compile(r"(?:\"[A-Za-z][^\"]{40,}\"[,;\s]*){8,}")

fails = 0
for dirpath, dirs, files in os.walk(ROOT):
    if ".git" in dirpath:
        continue
    for f in sorted(files):
        p = os.path.join(dirpath, f)
        rel = os.path.relpath(p, ROOT)
        if f in ("pub_gate.py",):
            continue
        if not f.lower().endswith((".py", ".md", ".json", ".txt")):
            continue
        txt = open(p, encoding="utf-8", errors="replace").read()
        findings = []
        for rx, name in PII:
            n = len(rx.findall(txt))
            if n:
                findings.append(f"{name} x{n}")
        if HEXRUN.search(txt):
            findings.append("hexdump")
        density = len(ASM.findall(txt)) / max(1, txt.count("\n"))
        if density > 0.02:
            findings.append(f"asm-density {density:.3f}")
        if THIRDPARTY.search(txt):
            findings.append("third-party-copyright")
        if STRLONG.search(txt):
            findings.append("string-blob")
        if findings:
            fails += 1
            print(f"[FAIL] {rel}: {'; '.join(findings)}")
print("RESULT:", "ALL CLEAN" if fails == 0 else f"{fails} files need work")
sys.exit(1 if fails else 0)
