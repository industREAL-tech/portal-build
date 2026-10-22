# hmi-build -- what a user's machine builds an industREAL HMI application with
# (docs/CLIENT-BUILD.md). The toolchain the codegen service used to build with on the
# server, plus hmi_build.py and imagefmt.py, which assemble the application image over
# the pinned hmi-app-base exactly as the server checks it.
#
# Build context: buildkit/ with app/imagefmt.py copied in (buildkit/make-build-image.sh).
FROM mcr.microsoft.com/dotnet/sdk:10.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 libfontconfig1 libfreetype6 curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Godot as in the codegen image: our build of the 4.7.2 editor (the official x86_64 binary
# needs SSE4.2) and the official linux arm64 release export template, untouched. The
# templates sit under a world-readable XDG_DATA_HOME because the container runs as the
# user's uid, whose home is not root's.
ARG GODOT_VERSION=4.7.2-stable
ARG GODOT_TEMPLATE_DIR=4.7.2.stable
COPY --from=industreal/godot-editor:4.7.2 /godot /usr/local/bin/godot
ENV XDG_DATA_HOME=/opt/godot-data
RUN t=/opt/godot-data/godot/export_templates/${GODOT_TEMPLATE_DIR} \
    && mkdir -p $t \
    && curl -fsSL -o /tmp/templates.tpz https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/Godot_v${GODOT_VERSION}_export_templates.tpz \
    && unzip -q -j /tmp/templates.tpz templates/linux_release.arm64 templates/version.txt -d $t \
    && rm -f /tmp/templates.tpz \
    && test "$(cat $t/version.txt)" = "${GODOT_TEMPLATE_DIR}" \
    && chmod -R a+rwX /opt/godot-data \
    && godot --headless --version

COPY build/hmi_build.py imagefmt.py /opt/hmi-build/
COPY base/base-1.json /opt/hmi-build/base/
ENV HMI_BASE_DIR=/opt/hmi-build/base \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
WORKDIR /src
ENTRYPOINT ["python3", "/opt/hmi-build/hmi_build.py"]
