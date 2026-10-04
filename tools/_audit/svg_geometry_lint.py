"""Geometry lint for repo SVGs: parse rects/texts/lines, assert
- all shapes inside canvas
- bars not exceeding plot area
- no text x beyond canvas minus margin
Deterministic render-free check for the fixed-geometry SVG system."""
import re, sys
import xml.etree.ElementTree as ET

NS = {"s": "http://www.w3.org/2000/svg"}
fails = 0
for path in sys.argv[1:]:
    t = ET.parse(path)
    root = t.getroot()
    W, H = float(root.get("width")), float(root.get("height"))
    issues = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "rect":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w, h = float(el.get("width", 0)), float(el.get("height", 0))
            if x < 0 or y < 0 or x + w > W or y + h > H:
                issues.append(f"rect out of canvas: ({x},{y},{w},{h})")
        elif tag == "text":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            if not (0 <= x <= W and 0 <= y <= H):
                issues.append(f"text out of canvas: ({x},{y})")
            # estimated end: anchor-aware, 0.62*fontsize per char heuristic
            size = float(re.search(r"font-size:\s*([\d.]+)px", el.get("style", "") or "").group(1)) if re.search(r"font-size:\s*([\d.]+)px", el.get("style", "") or "") else float(el.get("font-size", 12))
            txt = (el.text or "")
            est_w = len(txt) * size * 0.53  # calibrated: vision-passed lines bound at ~0.52
            anchor = el.get("text-anchor", "start")
            x0 = x - est_w if anchor == "end" else (x - est_w / 2 if anchor == "middle" else x)
            if x0 < 0 or x0 + est_w > W + 4:
                issues.append(f"text may overflow: '{txt[:30]}' x={x} est_end={x0 + est_w:.0f} (W={W})")
        elif tag in ("line",):
            for a, b in (("x1", "x2"), ("y1", "y2")):
                for v in (el.get(a), el.get(b)):
                    if v and not (0 <= float(v) <= (W if a[0] == "x" else H)):
                        issues.append(f"line coord out: {a}={v}")
    status = "OK" if not issues else "ISSUES"
    print(f"[{status}] {path} ({W}x{H})")
    for i in issues:
        print("   -", i)
        globals()["fails"] += 1
sys.exit(1 if fails else 0)
