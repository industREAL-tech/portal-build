# hmi-build -- what a user's machine builds an industREAL HMI application with
# (docs/CLIENT-BUILD.md). The toolchain the codegen service used to build with on the
# server, plus hmi_build.py and imagefmt.py, which assemble the application image over
# the pinned portal-base exactly as the server checks it.
#
# Build context: buildkit/ with app/imagefmt.py copied in (buildkit/make-build-image.sh).
FROM mcr.microsoft.com/dotnet/sdk:10.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 libfontconfig1 libfreetype6 curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Godot: the official 4.7.2 x86_64 editor, for the export and the render alike, and OUR linux
# arm64 release export template: Godot 4.7.2 with buildkit/godot/patches applied (the panel's
# GPU spends ~11 ms of a full-screen frame on the stock scene shader's colour epilogue), built
# by buildkit/godot/build-template.sh and published as a release asset of this repository,
# pinned by its sha256. The renders still come from the stock editor, so an unshaded colour
# there can be up to 2/255 darker (7/255 in near-black) than on the panel. The official binary needs SSE4.2,
# which every machine that builds applications has (the codegen server, whose CPU lacks it,
# no longer builds them; it keeps its own patched editor, tools/godot-editor). The templates
# sit under a world-readable XDG_DATA_HOME because the container runs as the user's uid,
# whose home is not root's.
ARG GODOT_VERSION=4.7.2-stable
ARG GODOT_TEMPLATE_DIR=4.7.2.stable
ARG PANEL_TEMPLATE=https://github.com/industREAL-tech/portal-build/releases/download/godot-4.7.2-ir1/linux_release.arm64
ARG PANEL_TEMPLATE_SHA256=327cd47bd0416420ecfa1b730dec3f1b3546593135de341a0e7a97b3e02f9ee5
RUN curl -fsSL -o /tmp/godot.zip https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_linux.x86_64.zip \
    && unzip -q /tmp/godot.zip -d /tmp/godot \
    && install -m 0755 /tmp/godot/Godot_v${GODOT_VERSION}_linux.x86_64 /usr/local/bin/godot \
    && ln -s godot /usr/local/bin/godot-display \
    && rm -rf /tmp/godot /tmp/godot.zip
ENV XDG_DATA_HOME=/opt/godot-data
RUN t=/opt/godot-data/godot/export_templates/${GODOT_TEMPLATE_DIR} \
    && mkdir -p $t \
    && curl -fsSL -o /tmp/templates.tpz https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_export_templates.tpz \
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

COPY build/hmi_build.py imagefmt.py /opt/hmi-build/
COPY base/base-1.json /opt/hmi-build/base/
ENV HMI_BASE_DIR=/opt/hmi-build/base \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
WORKDIR /src
ENTRYPOINT ["python3", "/opt/hmi-build/hmi_build.py"]
