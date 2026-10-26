#!/bin/sh
# Build the industREAL panel's Godot runtime: the Godot release export template, Godot
# 4.7.2-stable with patches/ applied, built the way Godot's official Linux templates are
# (its buildroot SDK, production=yes).
#   buildkit/godot/build-template.sh <out-dir> [arm64] [x86_64]
# Writes <out-dir>/linux_release.<arch> (default: arm64, what the panel runs) and SHA256SUMS.
# Heavy: run it on a build server (nice -n 10); the source and objects go to <out-dir>/work.
#
# Why: on the panel's GPU (Vivante GC7000UL) the scene shader's colour epilogue is most of an
# unshaded pixel, ~11 ms of a full-screen 1280x800 frame; see the patch's message.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mkdir -p "${1:?usage: build-template.sh <out-dir> [arm64] [x86_64]}" && cd "$1" && pwd)
shift
archs=${*:-arm64}
GODOT_TAG=4.7.2-stable
GODOT_COMMIT=ed1daf0bf001b61586d9930840f2f1394092c079
IMAGE=industreal/godot-template-build:2026.05.x-1

src="$out/work/godot"
if [ ! -d "$src" ]; then
    git clone -q --depth 1 --branch "$GODOT_TAG" https://github.com/godotengine/godot.git "$src"
    test "$(git -C "$src" rev-parse HEAD)" = "$GODOT_COMMIT"
    for p in "$here"/patches/*.patch; do git -C "$src" apply "$p"; done
fi
docker build -q -t "$IMAGE" "$here" >/dev/null

for arch in $archs; do
    case $arch in
        arm64) sdk='$SDK_ARM64' ;;
        x86_64) sdk='$SDK_X86_64' ;;
        *) echo "unknown arch $arch" >&2; exit 2 ;;
    esac
    docker run --rm -v "$src:/src" -v "$out:/out" -w /src "$IMAGE" sh -c "
        set -e
        export PATH=$sdk/bin:\$PATH
        scons -j\$(nproc) platform=linuxbsd arch=$arch target=template_release production=yes \
            accesskit=no progress=no warnings=no
        cp bin/godot.linuxbsd.template_release.$arch /out/linux_release.$arch
        chown $(id -u):$(id -g) /out/linux_release.$arch"
done
(cd "$out" && sha256sum linux_release.* > SHA256SUMS && cat SHA256SUMS)
