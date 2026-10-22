#!/bin/sh
# Build the portal-build container (docs/CLIENT-BUILD.md) from this repository:
#   buildkit/make-build-image.sh [tag]
# Needs a CPU with SSE4.2 (the official Godot editor checks it). Published to GHCR by CI.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
ctx=$(mktemp -d)
trap 'rm -rf "$ctx"' EXIT
cp -r "$here/build" "$here/base" "$ctx/"
cp "$here/../app/imagefmt.py" "$ctx/imagefmt.py"
docker build -f "$ctx/build/Dockerfile" -t "${1:-ghcr.io/industreal-tech/portal-build:1}" "$ctx"
