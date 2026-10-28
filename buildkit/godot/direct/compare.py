"""Compare <dir>/<case>-d0.png (blit) with <case>-d1.png (direct): differing pixels, max channel diff."""
import sys, glob, os
import numpy as np
from PIL import Image
d = sys.argv[1]
worst = 0
bad = 0
for a in sorted(glob.glob(os.path.join(d, "*-d0.png"))):
    case = os.path.basename(a)[:-7]
    b = a[:-7] + "-d1.png"
    if not os.path.exists(b):
        print(f"{case:24s} MISSING direct"); bad += 1; continue
    x = np.asarray(Image.open(a).convert("RGB")).astype(int)
    y = np.asarray(Image.open(b).convert("RGB")).astype(int)
    if x.shape != y.shape:
        print(f"{case:24s} SIZE {x.shape} vs {y.shape}"); bad += 1; continue
    diff = np.abs(x - y).max(axis=2)
    n = int((diff > 0).sum()); m = int(diff.max())
    worst = max(worst, m)
    # a blank direct frame (the boot splash / one flat colour) is a failure whatever the diff
    flat = len(np.unique(y.reshape(-1, 3), axis=0)) <= 1
    print(f"{case:24s} diff_px={n:7d} max={m:3d}{'  DIRECT FLAT' if flat else ''}")
    if m > 1 or flat:
        bad += 1
print(f"cases with max>1 or blank: {bad}; worst max diff {worst}")
