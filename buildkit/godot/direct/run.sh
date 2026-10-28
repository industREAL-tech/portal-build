#!/bin/sh
# Render the direct-to-screen proof: every case once through Godot's final blit and once drawn
# straight to the window (BENCH_DIRECT=1), under Weston (headless, GL renderer, Mesa llvmpipe),
# and compare the two screenshots.
#   run.sh <work-dir> <x86_64 release template> [<benchmark project dir>]
# The optional GPU benchmark project (its ui/ dir; reads BENCH_ONLY and BENCH_DIRECT) adds every
# bench variant, with the depth pre-pass on.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
build_image='ghcr.io/industreal-tech/portal-build@sha256:0641b08655707bfa73d03bac14d409578c4e673db4374f2ce3977bf47221f918'
image='industreal/direct-proof:1'
work=$(mkdir -p "${1:?usage: run.sh <work-dir> <template> [bench-project]}" && cd "$1" && pwd)
template=${2:?usage: run.sh <work-dir> <template> [bench-project]}
bench=${3:-}
docker build -q -t "$image" "$here" >/dev/null

# Export a PCK per project with the official editor; the template runs it as <name>.x86_64.
export_pck() {  # $1 = project source dir, $2 = name
    rm -rf "$work/$2" && mkdir -p "$work/$2/bin" && cp -r "$1" "$work/$2/project"
    rm -rf "$work/$2/project/.godot"
    if [ "$2" = view ]; then  # the generator's IrView3D, as a generated application gets it
        mkdir -p "$work/view/project/theme"
        cp "$here/../../../platform/theme/ir_view3d.gd" "$work/view/project/theme/"
    fi
    docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$work/$2:/w" "$build_image" -c "
        godot --headless --path /w/project --import >/dev/null 2>&1
        godot --headless --path /w/project --export-pack \$(sed -n 's/^name=\"\(.*\)\"/\1/p' /w/project/export_presets.cfg | head -1) /w/bin/$2.pck >/dev/null 2>&1"
    test -s "$work/$2/bin/$2.pck"
    cp "$template" "$work/$2/bin/$2.x86_64" && chmod +x "$work/$2/bin/$2.x86_64"
}
cp "$here/shot.sh" "$work/shot.sh"
export_pck "$here/project" view
[ -n "$bench" ] && export_pck "$bench" bench

shot() {  # $1 = out png, $2 = binary, then env assignments
    out=$1 bin=$2; shift 2
    envs=""; for e in "$@"; do envs="$envs -e $e"; done
    # shellcheck disable=SC2086
    timeout 120 docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e BIN="$bin" -e OUT="$out" \
        -e AFTER=5 -e LOGN=0 $envs -v "$work:/w" "$image" /w/shot.sh >/dev/null 2>&1 || true
}
mkdir -p "$work/img"
for d in 0 1; do
    for c in view full fog; do
        shot "/w/img/view-$c-d$d.png" /w/view/bin/view.x86_64 PROOF_CASE=$c BENCH_DIRECT=$d
    done
    if [ -n "$bench" ]; then
        for v in empty fill-1 fill-2 fill-half fill-1-2d tris-100k-small tris-100k-full fill-4 \
                fill-1-shader fill-1-const fill-1-lit fill-1-lambert fill-1-vertex fill-1-nodepth \
                fill-1-nofog fill-1-const-nofog fill-1-vertex-nofog fill-1-lit-nofog fill-2-nofog; do
            shot "/w/img/bench-$v-d$d.png" /w/bench/bin/bench.x86_64 BENCH_ONLY=$v BENCH_DIRECT=$d
        done
    fi
done
echo "renders in $work/img; compare: python3 $here/compare.py $work/img"
