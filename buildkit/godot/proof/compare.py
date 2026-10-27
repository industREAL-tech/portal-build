#!/usr/bin/env python3
"""Compare proof renders: prove what the three colour-epilogue patches change, image by image.

    compare.py <img-dir> [--json out.json]

Reads ``manifest.json`` from the config dirs under <img-dir> (stock, m_tesc, m_esc,
m_tsc, m_sc, m_c, m_all, forward_plus) and runs checks A-D. Exits 1 if any check FAILs.
Only numpy + Pillow. A missing config dir is skipped with a note; a missing image or a
size mismatch within a config under test is a FAIL.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

# Configs that are part of the proof. forward_plus is informational (compare handles its absence).
CONFIGS = ["stock", "m_tesc", "m_esc", "m_tsc", "m_sc", "m_c", "m_all", "forward_plus"]

# Rows whose expected colours are fixed by the manifest (used by check C exactness).
EXPECTED_ROWS = ["A", "B", "C"]


def load_image(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, dtype=np.int16)  # signed so abs diff never wraps
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img", help="renders root dir, e.g. <work>/img")
    ap.add_argument("--json", default=None, help="write a JSON summary")
    args = ap.parse_args()
    extra = {"checks": {}}

    configs = {}
    manifest = None
    for cfg in CONFIGS:
        d = os.path.join(args.img, cfg)
        if not os.path.isdir(d):
            print("NOTE: config dir %s missing, skipping its checks" % cfg)
            continue
        mpath = os.path.join(d, "manifest.json")
        if manifest is None and os.path.exists(mpath):
            with open(mpath) as f:
                manifest = json.load(f)
        imgs = {}
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".png"):
                imgs[fn[:-4]] = load_image(os.path.join(d, fn))
        configs[cfg] = imgs

    if manifest is None:
        print("FAIL: no manifest.json found under any config dir in %s" % args.img)
        return 1

    cases = manifest["cases"]
    extra["cases"] = cases
    failed = False

    def need_config(name):
        if name in configs:
            return True
        print("FAIL: config %s is required but missing" % name)
        return False

    # Every config that exists must contain every case, all at a consistent size.
    for cfg, imgs in configs.items():
        missing = [c for c in cases if c not in imgs]
        if missing:
            failed = True
            print("FAIL: config %s missing images %s" % (cfg, missing))
        if imgs:
            sizes = {v.shape for v in imgs.values()}
            if len(sizes) > 1:
                failed = True
                print("FAIL: config %s has images of differing sizes %s" % (cfg, sizes))

    # ---- A. toggles-off is stock ---------------------------------------------
    if need_config("stock") and need_config("m_tesc"):
        diffs = identical(configs["stock"], configs["m_tesc"], cases)
        ok = not diffs
        failed |= not ok
        print("A. toggles-off is stock: %s (%d differing images%s)"
              % ("PASS" if ok else "FAIL", len(diffs), "" if not diffs else ": " + ", ".join(diffs)))
        extra["checks"]["A"] = ok

    # ---- B. patches 1 and 2 are exact --------------------------------------
    if need_config("m_tesc"):
        b_ok = True
        for sub in ("m_esc", "m_tsc", "m_sc"):
            if sub not in configs:
                print("FAIL: config %s is required but missing" % sub)
                failed = True
                b_ok = False
                continue
            diffs = identical(configs["m_tesc"], configs[sub], cases)
            if diffs:
                b_ok = False
                print("  FAIL %s: %d differing images: %s" % (sub, len(diffs), ", ".join(diffs)))
            else:
                print("  %s: identical to m_tesc" % sub)
        failed |= not b_ok
        print("B. patches 1 and 2 are exact: %s" % ("PASS" if b_ok else "FAIL"))
        extra["checks"]["B"] = b_ok

    # ---- C. patch 3 changes only what it should --------------------------------
    if need_config("m_all") and need_config("m_sc"):
        c_ok, c_detail = check_c(configs["m_all"], configs["m_sc"], cases, manifest)
        failed |= not c_ok
        print("C. patch 3 changes only what it should: %s" % ("PASS" if c_ok else "FAIL"))
        extra["checks"]["C"] = c_ok
        extra["checks"]["C_detail"] = c_detail

    # ---- D. clamp ------------------------------------------------
    if need_config("m_all") and need_config("m_c"):
        d_ok, d_detail = check_d(configs["m_all"], configs["m_c"], cases, manifest)
        failed |= not d_ok
        print("D. clamp: %s" % ("PASS" if d_ok else "FAIL"))
        extra["checks"]["D"] = d_ok
        extra["checks"]["D_detail"] = d_detail

    # ---- E. Forward+ parity (informational) -------------------------
    if "forward_plus" not in configs:
        print("NOTE: forward_plus config missing, skipping check E (informational)")
    elif need_config("m_all") and need_config("m_sc"):
        check_e(configs["m_all"], configs["m_sc"], configs["forward_plus"], manifest)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(extra, f, indent=2)

    print("RESULT: %s" % ("FAIL" if failed else "ALL PASS"))
    return 1 if failed else 0


def identical(ref, other, cases):
    """Return the list of cases where ref and other differ pixel-wise."""
    diffs = []
    for c in cases:
        if c not in ref or c not in other:
            continue
        if ref[c].shape != other[c].shape:
            diffs.append(c + "(size)")
        elif np.any(ref[c] != other[c]):
            diffs.append(c)
    return diffs


def max_abs_diff(a, b, rect):
    x0, y0, x1, y1 = rect
    sub = np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1])
    return int(sub.max()) if sub.size else 0


def _row_rects(rows, r):
    """Pixel rects of the quads in a row, independent of the per-row manifest shape."""
    if r == "A":
        return [rows["A"]["quads"][0]]
    if r == "E":
        return [q[0] for q in rows[r]["quads"]]
    return [q[:4] for q in rows[r]["quads"]]


def _rows_max_diff(a, b, rows, r):
    """Max abs channel diff of a against b over every quad of row r."""
    return max(max_abs_diff(a, b, rect) for rect in _row_rects(rows, r))


def _unorm8(c):
    """What a float colour channel becomes in an 8-bit target: clamped to [0, 1], rounded."""
    return int(round(min(max(c, 0.0), 1.0) * 255.0))


def check_c(all_imgs, sc_imgs, cases, manifest):
    """m_all (all patches) vs m_sc (patches 1+2 only): what patch 3 changes.

    Patch 3 may change unshaded pixels only (rows A-E); lit pixels (row F) and the background
    must stay identical. Every unshaded quad it changes must then show the colour the material
    wrote: rows A-C exactly the manifest's sRGB input, row D its uniform converted to 8 bits
    (within the driver's rounding of 1).
    """
    rows = manifest["rows"]
    differing = [c for c in cases if c in all_imgs and c in sc_imgs and np.any(all_imgs[c] != sc_imgs[c])]
    bad = []
    m_sc_max_err = 0
    changed_quads = 0
    for c in differing:
        a = all_imgs[c]
        s = sc_imgs[c]
        bg = background_mask(rows)
        bg_diff = int(np.abs(a[bg] - s[bg]).max()) if np.any(bg) else 0
        row_diff = ", ".join("%s:%d" % (r, _rows_max_diff(a, s, rows, r)) for r in ("A", "B", "C", "D", "E", "F"))
        print("  C: %s max abs channel diff per row = %s, background %d" % (c, row_diff, bg_diff))
        if _rows_max_diff(a, s, rows, "F") > 0:
            bad.append("%s: row F (lit) differs (max %d)" % (c, _rows_max_diff(a, s, rows, "F")))
        if bg_diff > 0:
            bad.append("%s: background differs (max %d)" % (c, bg_diff))
        # Rows A-C: every changed region must now equal the expected input exactly. On a
        # floating-point (hdr_) target the read-back is not the 8-bit output, so only report.
        if c.startswith("hdr_"):
            continue
        for r in EXPECTED_ROWS:
            regions = rows["A"]["regions"] if r == "A" else rows[r]["quads"]
            for x0, y0, x1, y1, color in regions:
                if not np.any(a[y0:y1, x0:x1] != s[y0:y1, x0:x1]):
                    continue
                changed_quads += 1
                exp = np.array(color, dtype=np.int16)
                err_all = int(np.abs(a[y0:y1, x0:x1] - exp).max())
                m_sc_max_err = max(m_sc_max_err, int(np.abs(s[y0:y1, x0:x1] - exp).max()))
                if err_all > 0:
                    bad.append("%s row %s %s: changed but %d off the input colour" % (c, r, color, err_all))
        # Row D: a changed quad must equal its uniform converted to 8 bits.
        for x0, y0, x1, y1, info in rows["D"]["quads"]:
            if not np.any(a[y0:y1, x0:x1] != s[y0:y1, x0:x1]):
                continue
            changed_quads += 1
            exp = np.array([_unorm8(v) for v in info["c"]], dtype=np.int16)
            err_all = int(np.abs(a[y0:y1, x0:x1] - exp).max())
            # These floats are not 8-bit values: the driver's float -> unorm rounding may land
            # either side (llvmpipe: 7.65 -> 7, 229.5 -> 230), so allow 1.
            if err_all > 1:
                bad.append("%s row D %s: changed but %d off its 8-bit value %s" % (c, info["c"], err_all, exp.tolist()))
    if not differing:
        print("  C: no images differ between m_all and m_sc")
    else:
        print("  C: patch 3 active in %d image(s): %s" % (len(differing), ", ".join(differing)))
        print("  C: %d changed regions, each now the exact written colour: %s" % (changed_quads, "yes" if not bad else "no"))
        print("  C: stock (m_sc) error in those regions: up to %d/255" % m_sc_max_err)
    ok = not bad
    for b in bad:
        print("  FAIL: " + b)
    return ok, {"differing": differing, "changed_regions": changed_quads, "m_sc_max_err": m_sc_max_err, "bad": bad}


def expected_errors(all_imgs, sc_imgs, manifest, row):
    """Max abs diff of the image against the manifest expected colour over that row's regions."""
    err_all = 0
    err_sc = 0
    if row == "A":
        regions = manifest["rows"]["A"]["regions"]
        for x0, y0, x1, y1, color in regions:
            exp = np.array(color, dtype=np.int16)
            err_all = max(err_all, int(np.abs(all_imgs[y0:y1, x0:x1] - exp).max()))
            err_sc = max(err_sc, int(np.abs(sc_imgs[y0:y1, x0:x1] - exp).max()))
    else:
        for x0, y0, x1, y1, color in manifest["rows"][row]["quads"]:
            exp = np.array(color, dtype=np.int16)
            err_all = max(err_all, int(np.abs(all_imgs[y0:y1, x0:x1] - exp).max()))
            err_sc = max(err_sc, int(np.abs(sc_imgs[y0:y1, x0:x1] - exp).max()))
    return err_all, err_sc


def background_mask(rows, h=384, w=512):
    m = np.zeros((h, w), dtype=bool)
    m[:] = True
    for r in ("A", "B", "C", "D", "E", "F"):
        for x0, y0, x1, y1 in _row_rects(rows, r):
            m[y0:y1, x0:x1] = False
    return m


def check_d(all_imgs, cm_imgs, cases, manifest):
    """m_c clamps patch 3's output on every target, m_all only on floating-point ones: a normalized
    target clamps by itself, so nothing may change at all."""
    rows = manifest["rows"]
    row_rects = {"A": rows["A"]["quads"][0]}
    for r in ("B", "C", "D", "F"):
        row_rects[r] = rows[r]["quads"][0][:4]
    row_rects["E"] = rows["E"]["quads"][0][0]

    differing = [c for c in cases if c in all_imgs and c in cm_imgs and np.any(all_imgs[c] != cm_imgs[c])]
    bad = []
    for c in differing:
        a = all_imgs[c]
        cm = cm_imgs[c]
        for r in ("A", "B", "C", "D", "F"):
            if _rows_max_diff(a, cm, rows, r) > 0:
                bad.append("%s: row %s differs between m_all and m_c" % (c, r))
        if _rows_max_diff(a, cm, rows, "E") > 0:
            bad.append("%s: row E differs between m_all and m_c" % c)
        bg = background_mask(rows)
        if int(np.abs(a[bg] - cm[bg]).max()) > 0:
            bad.append("%s: background differs between m_all and m_c" % c)
        print("  D: %s: row D max abs diff vs m_all = %d" % (c, _rows_max_diff(a, cm, rows, "D")))
    if not differing:
        print("  D: no images differ between m_all and m_c")
    ok = not bad
    for b in bad:
        print("  FAIL: " + b)
    return ok, {"differing": differing, "bad": bad}


def check_e(all_imgs, sc_imgs, fp_imgs, manifest):
    """Forward+ parity, informational: rows A-C max abs diff of m_all/m_sc vs forward_plus."""
    print("E. forward+ parity (informational, no FAIL):")
    rows = manifest["rows"]
    cases = [c for c in ("noenv", "linear_e1.0_fog0_glow0")
             if c in all_imgs and c in sc_imgs and c in fp_imgs]
    if not cases:
        print("  noenv / linear_e1.0_fog0_glow0 images absent; skipping")
        return
    print("  %-22s %-8s %7s %7s %7s" % ("case", "pair", "A", "B", "C"))
    for c in cases:
        for label, other in (("m_all", all_imgs), ("m_sc", sc_imgs)):
            errs = []
            for r in ("A", "B", "C"):
                e = 0
                for x0, y0, x1, y1 in _row_rects(rows, r):
                    s = np.abs(fp_imgs[c][y0:y1, x0:x1] - other[c][y0:y1, x0:x1])
                    if s.size:
                        e = max(e, int(s.max()))
                errs.append(e)
            print("  %-22s %-8s %7d %7d %7d" % (c, label + "+", errs[0], errs[1], errs[2]))


if __name__ == "__main__":
    sys.exit(main())
