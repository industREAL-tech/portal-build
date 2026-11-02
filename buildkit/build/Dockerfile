# hmi-build -- what a user's machine builds an industREAL HMI application with
# (docs/CLIENT-BUILD.md). The toolchain the codegen service used to build with on the
# server, plus hmi_build.py and imagefmt.py, which assemble the application image over
# the pinned portal-base exactly as the server checks it.
#
# Build context: buildkit/ with app/imagefmt.py copied in (buildkit/make-build-image.sh).
# The fixed entropy for Godot's build steps (fixed_entropy.c): built apart, so no compiler ships.
FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad AS entropy
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY build/fixed_entropy.c /tmp/
RUN gcc -O2 -shared -fPIC -nostdlib -o /tmp/hmi-fixed-entropy.so /tmp/fixed_entropy.c

# The toolchain is pinned: the SDK by digest (a rebuild of this image keeps the compiler, so
# the same tree keeps building to the same image), Godot by its release checksums.
FROM mcr.microsoft.com/dotnet/sdk:10.0.403@sha256:de4fe90a98845d75910b9769662465c84de1a934665c431279d1382b2bddc02b
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 libfontconfig1 libfreetype6 curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Godot: the official 4.7.2 x86_64 editor, for the export and the render alike, and OUR linux
# arm64 release export template: Godot 4.7.2 with buildkit/godot/patches applied (the stock
# scene shader's colour epilogue cost the panel's GPU ~11 ms of a full-screen frame; 0001-0003
# take an unshaded full screen from 19.6 to 8.3 ms, 0004 lets the root viewport be drawn
# straight to the window, 4.2 ms -- generated 3D apps turn that on, ui/platform_direct.gd -- and
# 0005 gives that direct viewport 3D MSAA: 4x for ~1 ms a full screen, 5 ms with 50k triangles), built by
# buildkit/godot/build-template.sh and published as a release asset of this repository, pinned
# by its sha256. The renders still come from the stock editor, so an unshaded colour there can
# be up to 2/255 darker (7/255 in near-black) than on the panel, which shows it exactly. The official binary needs SSE4.2,
# which every machine that builds applications has (the codegen server, whose CPU lacks it,
# no longer builds them; it keeps its own patched editor, tools/godot-editor). The templates
# sit under a world-readable XDG_DATA_HOME because the container runs as the user's uid,
# whose home is not root's.
ARG GODOT_VERSION=4.7.2-stable
ARG GODOT_TEMPLATE_DIR=4.7.2.stable
ARG PANEL_TEMPLATE=https://github.com/industREAL-tech/portal-build/releases/download/godot-4.7.2-ir4/linux_release.arm64
ARG PANEL_TEMPLATE_SHA256=e6ce28a69d422aca6113dc8a4d663ec24253ab50cdf56635a692b0eac19a9ea1
ARG GODOT_EDITOR_SHA512=9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65
ARG GODOT_TEMPLATES_SHA512=ca4d71c4d7b81dfc15d1a98baa07534aa95b03fdda78a0075b06672e1648d2e5f40980c9adc28d23e1b92e732ee7bf3461997aa804af74ec2fcd7a93ccb84079
RUN curl -fsSL -o /tmp/godot.zip https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_linux.x86_64.zip \
    && echo "${GODOT_EDITOR_SHA512}  /tmp/godot.zip" | sha512sum -c - \
    && unzip -q /tmp/godot.zip -d /tmp/godot \
    && install -m 0755 /tmp/godot/Godot_v${GODOT_VERSION}_linux.x86_64 /usr/local/bin/godot \
    && ln -s godot /usr/local/bin/godot-display \
    && rm -rf /tmp/godot /tmp/godot.zip
ENV XDG_DATA_HOME=/opt/godot-data
RUN t=/opt/godot-data/godot/export_templates/${GODOT_TEMPLATE_DIR} \
    && mkdir -p $t \
    && curl -fsSL -o /tmp/templates.tpz https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_export_templates.tpz \
    && echo "${GODOT_TEMPLATES_SHA512}  /tmp/templates.tpz" | sha512sum -c - \
    && unzip -q -j /tmp/templates.tpz templates/linux_release.arm64 templates/version.txt -d $t \
    && rm -f /tmp/templates.tpz \
    && test "$(cat $t/version.txt)" = "${GODOT_TEMPLATE_DIR}" \
    && curl -fsSL -o $t/linux_release.arm64 ${PANEL_TEMPLATE} \
    && echo "${PANEL_TEMPLATE_SHA256}  $t/linux_release.arm64" | sha256sum -c - \
    && chmod -R a+rwX /opt/godot-data \
    && godot --headless --version

# Rendering the screens (hmi_build.py `_render`): a virtual display and software OpenGL
# (Mesa llvmpipe) for the same Godot (`godot-display`, kept as a name for hmi_build).
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb xauth libgl1 libglx-mesa0 libgl1-mesa-dri libegl1 \
        libxcursor1 libxinerama1 libxrandr2 libxi6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=entropy /tmp/hmi-fixed-entropy.so /usr/local/lib/
COPY build/hmi_build.py imagefmt.py /opt/hmi-build/
COPY base/base-1.json /opt/hmi-build/base/
# EnableWriteXorExecute=0: on an arm64 Linux host this x86_64 container runs under QEMU, where
# .NET's W^X JIT mappings crash dotnet (SIGSEGV); without them the build is the same, image ID
# for image ID (checked on an Orin, 2026-11-02).
ENV HMI_BASE_DIR=/opt/hmi-build/base \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_EnableWriteXorExecute=0
WORKDIR /src
ENTRYPOINT ["python3", "/opt/hmi-build/hmi_build.py"]
