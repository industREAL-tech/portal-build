# Measurement-only patch (never shipped)

`0004` applies on top of `../patches/0001-0003` and adds the `IR_EPILOGUE` environment switch:
`t`, `e`, `s` turn patch 1, 2, 3 off one by one; `c` clamps patch 3's output on every render
target instead of only floating-point ones. Used for the per-change board measurements and for
`../proof/`.

| patch | change | output | panel gain (full screen / 3D test application in play) |
|---|---|---|---|
| 0001 | tonemap code compiled out for LINEAR | pixel-identical | 2.1 / 3.5 ms |
| 0002 | `NEUTRAL_EXPOSURE`: exposure and luminance multiplier of 1.0 left out | pixel-identical | 2.1 / 3.5 ms |
| 0003 | unshaded pixels skip the sRGB round trip when nothing changes them; clamp only on float targets | the written colour exactly (stock: up to 7/255 off, godotengine/godot#96633); matches Forward+ | 6.7 / 10.6 ms on top of 1+2 |

On a panel (i.MX 8M Plus, Vivante GC7000UL, 1280x800), 2026-10-27, uncapped: stock 19.6 ms per unshaded full screen, all three 8.3;
a full-screen 3D test application in play 32.6 -> 14.3 ms.
