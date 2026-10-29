# direct-proof

Proves that `../patches/0004` makes a direct-to-screen root viewport
(`RenderingServer.viewport_set_render_direct_to_screen(root, true)`: Godot draws straight into the
window, no final blit) show exactly the picture the blit shows. Without 0004 the window keeps the
boot splash on Wayland/GLES3 (the panel, 2026-10-27), for three reasons, all fixed in 0004: the
window is only swapped after a blit; the scene and canvas draw upside down for the blit to flip
back; the depth pre-pass switches colour back on with `GL_COLOR_ATTACHMENT0`, an error on the
window's framebuffer, so nothing is drawn.

## Run

    ./run.sh <work-dir> <x86_64 release template> [<benchmark ui/ project>]
    python3 compare.py <work-dir>/img          # needs numpy and Pillow

Every case is rendered under Weston (headless, GL renderer, Mesa llvmpipe, kiosk shell) once with
the blit and once with `BENCH_DIRECT=1`, and Weston's screenshooter takes the window. `compare.py`
fails a case that differs by more than 1/255 or whose direct picture is one flat colour.

Cases: `project/` (`PROOF_CASE` view: the generator's IrView3D in the right half of an operator
screen; full: 3D across the screen under a HUD; fog: the scene shader keeps its epilogue), each with
text and a translucent bar over the 3D and a clipping control, depth pre-pass off. With the bench
project: all 19 variants of a GPU benchmark application (unshaded, lit, 2D, 100k triangles), depth pre-pass on.

MSAA cases (`../patches/0005`): `msaa4-view`/`msaa4-full` set 4x MSAA after direct-to-screen, as a
generated application does; `msaa4first-*` set it before (the 3D buffers are reconfigured on the
switch). They pass when under 0.2 % of the pixels differ by more than 2 and the direct picture is
antialiased: the blit path renders upside down and flips at the end, so its sample pattern is
mirrored (edge pixels get slightly different coverage), and it resolves at 10 bits, direct at 8.

## Result (2026-10-27, Godot 4.7.2 + 0001-0004, Mesa llvmpipe)

All 22 cases pixel-identical (max diff 0). With 0001-0003 alone all 22 fail (splash or one colour).

## Result (2026-10-29, + 0005, Mesa llvmpipe)

view/full/fog identical (max 0). MSAA: all 4 pass, antialiased in both modes; over 2 on 934 / 613 of
1,024,000 pixels (0.09 % / 0.06 %), almost all on antialiased edges; set-before and set-after identical.

## Limits of direct-to-screen

There is no render target texture: anything that reads it fails as in stock Godot (screen and depth
textures, BackBufferCopy, CanvasGroup, `get_viewport().get_texture()` -- the platform's
screenshot and render helpers). An application turns direct-to-screen on only when none of these
is in use.
