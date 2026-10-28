#!/bin/sh
# Render the epilogue-proof scene with several Godot binaries/configurations and save PNGs,
# so compare.py can prove what the colour-epilogue patches change.
#   run.sh <work-dir> <measurement-template-x86_64>
# Runs inside the portal-build image (official Godot 4.7.2 editor, xvfb-run, Mesa llvmpipe).
# The <measurement-template-x86_64> is the patch-bearing release template; it reads IR_EPILOGUE.
set -eu

image='ghcr.io/industreal-tech/portal-build@sha256:0a33d405589b5fa67e9526ba508ef42bff2c7525a04e316dcd35a84b39387a1f'

here=$(cd "$(dirname "$0")" && pwd)
work=${1:?usage: run.sh <work-dir> <measurement-template-x86_64>}
template=${2:?usage: run.sh <work-dir> <measurement-template-x86_64>}
mkdir -p "$work"
work=$(cd "$work" && pwd)

mkdir -p "$work/bin"

# The measurement template is provided from outside the container.
cp "$template" "$work/measurement-template"

# Steps 1-2 run inside the container; the container's /p is the proof dir, /w is the work dir.
docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$here:/p" -v "$work:/w" "$image" -c '
    set -eu
    rm -rf /w/project && cp -r /p/project /w/project

    # 1. import once, then export the PCK next to a copied release template.
    godot --headless --path /w/project --import >/dev/null 2>&1
    godot --headless --path /w/project --export-pack linux-x86_64 /w/bin/proof.pck

    # 2. the measurement template loads proof.pck next to it (basenames match).
    cp /w/measurement-template /w/bin/proof.x86_64
    chmod +x /w/bin/proof.x86_64
'

render_stock() {
    local out="$work/img/stock"
    local exist=0
    [ -d "$out" ] && exist=$(find "$out" -name '*.png' | wc -l)
    if [ "$exist" -ge 1 ]; then
        echo "stock: $exist PNGs present, skipping"
        return
    fi
    mkdir -p "$out"
    # STOCK_TEMPLATE=<unpatched x86_64 release template of the same Godot revision>: stock is that
    # template running the same PCK (needed when the patches sit on another revision than the
    # official editor's).
    if [ -n "${STOCK_TEMPLATE:-}" ]; then
        cp "$STOCK_TEMPLATE" "$work/bin/stock.x86_64" && chmod +x "$work/bin/stock.x86_64"
        cp "$work/bin/proof.pck" "$work/bin/stock.pck"
        docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
            -e LIBGL_ALWAYS_SOFTWARE=1 -e PROOF_OUT=/w/img/stock \
            -v "$work:/w" "$image" -c '
                set -eu
                timeout 300 xvfb-run -a -s "-screen 0 512x384x24" \
                    /w/bin/stock.x86_64 --rendering-driver opengl3 --rendering-method gl_compatibility
            ' || { echo "stock render failed" >&2; return 1; }
        return
    fi
    docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -e LIBGL_ALWAYS_SOFTWARE=1 -e PROOF_OUT=/w/img/stock \
        -v "$work:/w" "$image" -c '
            set -eu
            timeout 300 xvfb-run -a -s "-screen 0 512x384x24" \
                godot --rendering-driver opengl3 --rendering-method gl_compatibility --path /w/project
        ' || { echo "stock render failed" >&2; return 1; }
}

render_measure() {
    # $1 = config dir name, $2 = IR_EPILOGUE value
    local cfg="$1" irv="$2"
    local out="$work/img/$cfg"
    local exist=0
    [ -d "$out" ] && exist=$(find "$out" -name '*.png' | wc -l)
    if [ "$exist" -ge 1 ]; then
        echo "$cfg: $exist PNGs present, skipping"
        return
    fi
    mkdir -p "$out"
    docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -e LIBGL_ALWAYS_SOFTWARE=1 -e PROOF_OUT=/w/img/"$cfg" -e IR_EPILOGUE="$irv" \
        -v "$work:/w" "$image" -c '
            set -eu
            timeout 300 xvfb-run -a -s "-screen 0 512x384x24" \
                /w/bin/proof.x86_64 --rendering-driver opengl3 --rendering-method gl_compatibility
        ' || { echo "$cfg render failed" >&2; return 1; }
}

render_stock
render_measure m_tesc tesc
render_measure m_esc esc
render_measure m_tsc tsc
render_measure m_sc sc
render_measure m_c c
render_measure m_all ""

# forward_plus uses Vulkan/Mesa lavapipe: the portal-build image has no Vulkan driver, so build
# a derived image once. If it fails, warn and continue (compare handles a missing config).
forward_dir="$work/img/forward_plus"
if [ -d "$forward_dir" ] && [ "$(find "$forward_dir" -name '*.png' | wc -l)" -ge 1 ]; then
    echo "forward_plus: PNGs present, skipping"
else
    vk_image='industreal/epilogue-proof-vk:1'
    docker build -t "$vk_image" - >/dev/null <<DOCKERFILE
FROM $image
RUN apt-get update && apt-get install -y --no-install-recommends mesa-vulkan-drivers libvulkan1 && rm -rf /var/lib/apt/lists/*
DOCKERFILE
    mkdir -p "$forward_dir"
    if docker run --rm --entrypoint sh --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -e PROOF_OUT=/w/img/forward_plus \
        -v "$work:/w" "$vk_image" -c '
            set -eu
            timeout 300 xvfb-run -a -s "-screen 0 512x384x24" \
                godot --rendering-driver vulkan --rendering-method forward_plus --path /w/project
        ' 2>"$work/forward.log"; then
        :
    else
        echo "warning: forward_plus render failed (see forward.log); compare will skip it" >&2
    fi
fi

# Fail loudly if any expected config produced no PNGs.
for cfg in stock m_tesc m_esc m_tsc m_sc m_c m_all; do
    n=0
    [ -d "$work/img/$cfg" ] && n=$(find "$work/img/$cfg" -name '*.png' | wc -l)
    if [ "$n" -lt 1 ]; then
        echo "error: config $cfg produced no PNGs" >&2
        exit 1
    fi
    echo "$cfg: $n PNGs"
done
