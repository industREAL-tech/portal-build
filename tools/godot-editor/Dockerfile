# The Godot editor the builder exports with, compiled from the release source for any
# x86-64 CPU.
#
# Why not the official binary: since 4.5 Godot's SConstruct builds x86_64 with
# -msse4.2 -mpopcnt, and our build server is a hosted KVM VPS whose virtual CPU advertises
# neither. The official 4.5+ editors die with SIGILL/SIGABRT there before printing their
# version (measured 2026-09-30: 4.4.1 runs, 4.5.2 / 4.6.3 / 4.7.2 dump core). Only the
# EDITOR runs on the build host: it packs the project and copies the official linux
# arm64 export template, which is untouched and is what runs on the panel.
#
# Built on bookworm (glibc 2.36) so the binary runs on the builder's newer base too.
# Headless only: the builder never opens a window, so no display, audio or GPU backends.
#
#   docker build -t industreal/godot-editor:4.7.2 tools/godot-editor    (~15 min on 24 cores)
#   docker save industreal/godot-editor:4.7.2 | ssh <build server> docker load
FROM debian:bookworm AS build
ARG GODOT_VERSION=4.7.2-stable
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential scons pkg-config python3 curl ca-certificates xz-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/godot-${GODOT_VERSION}.tar.xz \
        | tar -xJ --strip-components=1
# The two changes, both about the SSE4.2 baseline and nothing else: the compiler flags
# (code that uses SSE4.2 is guarded by the compiler's own macros and falls back to SSE2),
# and main()'s cpuid check, which aborts on a CPU without it before anything runs.
# Each is asserted, so a release that moves either fails here rather than half-patched.
RUN grep -q '"-msse4.2", "-mpopcnt"' SConstruct \
    && sed -i 's/env.Append(CCFLAGS=\["-msse4.2", "-mpopcnt"\])/pass/' SConstruct \
    && ! grep -q 'msse4.2' SConstruct \
    && grep -q 'if (!(cpuinfo\[2\] & (1 << 20))) {' platform/linuxbsd/godot_linuxbsd.cpp \
    && sed -i 's/if (!(cpuinfo\[2\] & (1 << 20))) {/if (false) { \/\/ SSE4.2 check removed: see tools\/godot-editor/' \
         platform/linuxbsd/godot_linuxbsd.cpp \
    && ! grep -q 'cpuinfo\[2\] & (1 << 20)' platform/linuxbsd/godot_linuxbsd.cpp
RUN scons -j"$(nproc)" platform=linuxbsd target=editor production=yes lto=none \
        x11=no wayland=no vulkan=no opengl3=no alsa=no pulseaudio=no dbus=no speechd=no \
        fontconfig=no udev=no sdl=no accesskit=no \
    && strip bin/godot.linuxbsd.editor.x86_64 \
    && ./bin/godot.linuxbsd.editor.x86_64 --headless --version

FROM scratch
COPY --from=build /src/bin/godot.linuxbsd.editor.x86_64 /godot
