#!/usr/bin/env python3
"""dump_module.py — out-of-process module dumper for ACS.exe (Tier-0 route).

WHY OUT-OF-PROCESS: the packer fail-fasts ANY in-process probing
(0xC0000409) but external reads are safe (proven: settings_scan.py line of
evidence, and the two legacy dumps this repo's funcdb was built from).

WHAT IT DOES (when the game runs):
  1. OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION) on ACS.exe
  2. Read the PE headers of the module image
  3. Walk sections; read every committed, readable page of the image
  4. Write a flat image dump  <out>.bin  (file offsets == RVAs, headers at 0)
  5. Print SHA-256 + a section coverage report (raw=0 sections must show
     committed runtime bytes — that is the unpack evidence)

Usage:
  python tools/dump_module.py [--pid N | --name ACS.exe] [--out evidence/dumps]

Notes:
  * Takes TWO dumps per funcdb contract (reference + selfhost): run once at
    main menu, once with the loader candidate deployed, different sessions.
  * Deterministic requirement: build_funcdb.py pins dump SHA-256 in
    spec/contract.json and refuses to proceed on mismatch (fail-closed).
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import hashlib
import os
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD),
                ("Protect", wt.DWORD),
                ("Type", wt.DWORD)]

class LIST_ENTRY(ctypes.Structure):
    _fields_ = [("Flink", ctypes.c_void_p), ("Blink", ctypes.c_void_p)]

class PROCESS_ENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    e = PROCESS_ENTRY32W(); e.dwSize = ctypes.sizeof(e)
    if k32.Process32FirstW(snap, ctypes.byref(e)):
        while True:
            if e.szExeFile.lower() == name.lower():
                k32.CloseHandle(snap)
                return e.th32ProcessID
            if not k32.Process32NextW(snap, ctypes.byref(e)):
                break
    k32.CloseHandle(snap)
    return None


def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--name", default="ACS.exe")
    ap.add_argument("--out", default=os.path.join("evidence", "dumps"))
    a = ap.parse_args()

    pid = a.pid or find_pid(a.name)
    if not pid:
        sys.exit(f"no running process named {a.name} — start the game first")
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        sys.exit(f"OpenProcess({pid}) failed: WinError {ctypes.get_last_error()}")

    # module base: enumerate with Toolhelp modules for the exact image size
    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD), ("modBaseAddr", ctypes.c_void_p),
                    ("modBaseSize", wt.DWORD), ("hModule", wt.HMODULE), ("szModule", ctypes.c_wchar * 256),
                    ("szExePath", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)  # TH32CS_SNAPMODULE|MODULE32
    me = MODULEENTRY32W(); me.dwSize = ctypes.sizeof(me)
    base = size = None
    if k32.Module32FirstW(snap, ctypes.byref(me)):
        while True:
            if me.szModule.lower() == a.name.lower():
                base, size = me.modBaseAddr, me.modBaseSize
                break
            if not k32.Module32NextW(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    if base is None:
        sys.exit(f"module {a.name} not found in pid {pid}")
    print(f"pid={pid} module base={base:#x} size={size:#x}")

    # headers
    hdr = read_mem(h, base, 0x1000)
    if not hdr or hdr[:2] != b"MZ":
        sys.exit("cannot read MZ headers at module base")
    e_lfanew = int.from_bytes(hdr[0x3C:0x40], "little")
    nsec = int.from_bytes(hdr[e_lfanew + 6:e_lfanew + 8], "little")
    opt = e_lfanew + 24
    size_of_image = int.from_bytes(hdr[opt + 56:opt + 60], "little")
    image = bytearray(size_of_image)
    image[:len(hdr)] = hdr

    # walk committed readable regions inside the image; copy into flat image
    addr = base
    end = base + size_of_image
    mbi = MEMORY_BASIC_INFORMATION()
    committed = 0
    regions = 0
    while addr < end:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        rsize = mbi.RegionSize or 0x1000
        if (mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD))
                and mbi.Protect & 0xFF):
            data = read_mem(h, addr, min(rsize, end - addr))
            if data:
                off = addr - base
                image[off:off + len(data)] = data
                committed += len(data)
                regions += 1
        addr += rsize

    os.makedirs(a.out, exist_ok=True)
    # [FRICTION#13] name by pid+timestamp: same-process re-dumps must not
    # overwrite each other (this cost us dump B once).
    import time as _time
    stamp = _time.strftime("%Y%m%dT%H%M%S")
    out = os.path.join(a.out, f"acs-image-{pid}-{stamp}.bin")
    blob = bytes(image)
    with open(out, "wb") as f:
        f.write(blob)
    digest = hashlib.sha256(blob).hexdigest()

    # section coverage report (runtime bytes present where rawsize == 0?)
    # [fix 2026-10-03 FRICTION#10] SizeOfOptionalHeader lives at
    # e_lfanew+20 (file-header field), NOT optional-header+16 (that is the
    # entry point — my earlier misread made every section print as zeros).
    print(f"wrote {out} ({len(blob):,} bytes) sha256={digest}")
    print(f"committed readable: {committed:,} bytes across {regions} regions")
    size_opt = int.from_bytes(hdr[e_lfanew + 20:e_lfanew + 22], "little")
    sec_off = e_lfanew + 24 + size_opt
    print(f"{'section':<10} {'vaddr':>10} {'vsize':>12} {'runtime-nonzero':>16}")
    for i in range(nsec):
        s = hdr[sec_off + 40 * i: sec_off + 40 * (i + 1)]
        name = s[:8].decode(errors="replace").rstrip("\x00")
        vsize = int.from_bytes(s[8:12], "little")
        vaddr = int.from_bytes(s[12:16], "little")
        seg = blob[vaddr:vaddr + min(vsize, 0x100000)]
        nz = sum(1 for b in seg if b) if seg else 0
        print(f"{name:<10} {vaddr:#10x} {vsize:>12,} {nz:>16,}")
    k32.CloseHandle(h)


if __name__ == "__main__":
    main()
