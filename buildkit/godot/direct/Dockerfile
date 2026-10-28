# The direct-to-screen proof (run.sh): Weston (headless, GL renderer, Mesa llvmpipe) and its screenshooter.
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends weston libegl-mesa0 libegl1 libgles2 \
    libgl1-mesa-dri libwayland-client0 libwayland-cursor0 libwayland-egl1 libxkbcommon0 libdecor-0-0 \
    libfontconfig1 libdbus-1-3 fonts-dejavu-core xkb-data apitrace mesa-utils && rm -rf /var/lib/apt/lists/*
