# epilogue-proof

Proves, image by image, what three Godot 4.7.2 GLES3 scene-shader patches change in rendered
output. It renders a fixed test scene (rows A-F of quads: unshaded texture gradient, unshaded
constant colours, unshaded vertex colours, out-of-range shader colours, unshaded transparency, and
lit quads) under many Environment settings across several Godot binaries/configurations, saves PNGs, and
`compare.py` reports exactly which pixels differ and checks stated expectations.

## Run

1. Everything runs inside the portal-build Docker image (official Godot 4.7.2 editor, xvfb, Mesa llvmpipe):

       ./run.sh <work-dir> <x86_64 release template built with ../measure/0004>

   `<work-dir>` receives `project/`, `bin/` (imported PCK + copied measurement template) and
   `img/<config>/` renders. The measurement template must be the patched build's Linux x86_64
   release. Renders are `stock` (official editor), `m_tesc`/`m_esc`/`m_tsc`/`m_sc`/`m_c`/
   `m_all` (measurement template), and `forward_plus` (Vulkan/lavapipe, informational).

2. Compare:

       python3 compare.py <work-dir>/img [--json out.json]     # needs numpy and Pillow

## IR_EPILOGUE letters (measurement build only)

Each letter turns one change OFF: `t` = patch 1 (tonemap code compiled out for LINEAR), `e` =
patch 2 (neutral exposure), `s` = patch 3 (sRGB round trip skipped); `c` clamps patch 3's output on
every target instead of only floating-point ones.
Patch 3 only acts when patches 1 and 2 are on.

| config | IR_EPILOGUE | patches on | expectation |
|---|---|---|---|
| m_tesc | tesc | none | pixel-identical to `stock` (A) |
| m_esc / m_tsc / m_sc | esc / tsc / sc | 1 / 2 / 1+2 | pixel-identical to m_tesc (B) |
| m_all | (empty) | 1+2+3 | vs m_sc: only unshaded pixels change, each to the exact colour written (C) |
| m_c | c | 1+2+3, clamp on every target | vs m_all (clamp on float targets only): no pixel may change (D) |

## Result (2026-10-27, Godot 4.7.2, Mesa llvmpipe / lavapipe)

- A, B: all 64 images pixel-identical: toggles off = stock; patches 1 and 2 change no pixel.
- C: patch 3 active in `noenv`, `linear_e1.0_fog0_glow0`, in `linear_e1.0_fog1_glow0` for the
  `fog_disabled` materials only, and in the same three on a floating-point (`hdr_`) target;
  every changed region is now exactly the written colour (stock: up to 7/255 off); lit pixels and
  background unchanged. With glow the 10-bit target's luminance multiplier 0.25 keeps patches 2
  and 3 off, as designed.
- D: clamping on every target gives the same pixels as clamping on float targets only (a
  normalized target clamps by itself), so the clamp, 0.5-0.7 ms on the panel, runs only there.
- E: rows A-C match Forward+ exactly with patch 3 (stock: 7/255 off).
