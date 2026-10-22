# hmi-app-base -- what every generated application runs on (docs/CLIENT-BUILD.md).
#
# Built ONCE per version for linux/arm64 and pinned by digest everywhere: the build
# container carries its config and layer ids, the panel loads it from its own signed RAUC
# artifact. An application image is this plus one layer of the application's own files,
# so installing one needs no network and no build on the panel.
#
# Everything here used to be in each application's Dockerfile and was fetched by the panel
# at install time (apt from deb.debian.org): an offline panel could not install a UI app.
#
# Inputs are pinned: the two images by digest, apt by a snapshot.debian.org date. It must
# NOT carry the tech.industreal.app label -- the launcher's space-freeing deletes images
# that do.
FROM mcr.microsoft.com/dotnet/runtime:10.0@sha256:0cf09aaccf6a9f68900aed4c73fb28fe25bb59ec85de4dea08ba02240a8635f3 AS dotnet
FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
ARG SNAPSHOT=20261021T000000Z
# The UI libraries (archetypes.UI_PACKAGES), iproute2 and gpiod for the CAN bring-up in
# run.sh, ca-certificates for an application that fetches over HTTPS.
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${SNAPSHOT} trixie main" > /etc/apt/sources.list \
 && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${SNAPSHOT} trixie-security main" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        gpiod \
        iproute2 \
        libdrm2 \
        libssl3 \
        libstdc++6 \
        libwayland-client0 \
        libwayland-cursor0 \
        libwayland-egl1 \
        libwayland-server0 \
        libx11-data \
        libxkbcommon0 \
 && rm -rf /var/lib/apt/lists/* /var/log/apt /var/log/dpkg.log /var/cache/ldconfig/aux-cache
COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
# The app host looks for the runtime here; PATH alone is not enough. The slim base ships
# no ICU. The panel mounts its own GPU userspace at /gpu.
ENV DOTNET_ROOT=/usr/share/dotnet \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/share/dotnet \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
    EGL_PLATFORM=wayland \
    LD_LIBRARY_PATH=/gpu
LABEL tech.industreal.base="hmi-app-base"
