# The toolchain for the industREAL panel's Godot runtime: Godot's own buildroot SDKs (the ones
# its official Linux builds use, build-containers Dockerfile.linux) on Fedora, with SCons and the
# Wayland scanner. build-template.sh builds and runs it.
FROM fedora:42
RUN dnf install -y scons python3 wayland-devel bzip2 which findutils && dnf clean all
ARG SDK=godot-2026.05.x-1
ARG SHA_ARM64=2550952e511548d636fadce1ef09c7017a123f077918dac2a838975f4a2a43c3
ARG SHA_X86_64=9ecde61f7d500ffbd8cffddef3149a01984802c033ca19935d25e28293f34bb8
RUN set -e; cd /opt; \
    for a in aarch64:$SHA_ARM64 x86_64:$SHA_X86_64; do \
      f=${a%%:*}-godot-linux-gnu_sdk-buildroot; \
      curl -fsSLO https://github.com/godotengine/buildroot/releases/download/$SDK/$f.tar.bz2; \
      echo "${a#*:}  $f.tar.bz2" | sha256sum -c; \
      tar xf $f.tar.bz2; rm $f.tar.bz2; (cd $f && ./relocate-sdk.sh >/dev/null); \
    done
ENV SDK_ARM64=/opt/aarch64-godot-linux-gnu_sdk-buildroot SDK_X86_64=/opt/x86_64-godot-linux-gnu_sdk-buildroot
