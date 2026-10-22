#!/usr/bin/env python3
"""hmi-build: build an industREAL HMI application on this machine and upload its image
(docs/CLIENT-BUILD.md). Runs in the hmi-build container, the project mounted at /src:

    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/src" <hmi-build image> build \
        --spec '<run>/build-spec?t=…' --upload '<run>/image?t=…'

The server says what to build (the spec: build steps, the files of the layer, the names
the image must carry); this runs it, assembles the image with imagefmt -- the same code
the server checks it with -- and uploads it. Exit 0 when the image is built and uploaded.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imagefmt  # noqa: E402

STEP_TIMEOUT_S = 1800
# Godot's export prints its progress in colour whether or not stdout is a terminal, and the
# output ends up in a tool call (office-wordle r4: 110 of 209 lines).
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"hmi-build: the build spec was refused ({exc.code}): "
                 f"{exc.read().decode(errors='replace')[:300]}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        sys.exit(f"hmi-build: could not fetch the build spec: {exc}")


def _put(url: str, path: Path) -> dict:
    req = urllib.request.Request(url, data=path.read_bytes(), method="PUT",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        sys.exit(f"hmi-build: the upload was refused ({exc.code}): "
                 f"{exc.read().decode(errors='replace')[:300]}")
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"hmi-build: the upload failed: {exc}")


def _steps(src: Path, spec: dict) -> bool:
    """The archetype's build steps, as the server ran them: an advisory step may fail."""
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    # Godot refuses to export into a directory that does not exist ("The given export path
    # doesn't exist"); the server makes these before its own build (runs._write_owned).
    for rel in spec["artifacts"]:
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
    for step in spec["steps"]:
        cwd = (src / step["cwd"]).resolve()
        print(f"$ cd {step['cwd']} && {' '.join(step['argv'])}", flush=True)
        if step.get("advisory"):
            print("(this step's ERROR lines -- fonts, the theme, fontconfig -- are expected on "
                  "a first import; only the final exit status counts)", flush=True)
        try:
            p = subprocess.Popen(step["argv"], cwd=cwd, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, errors="replace")
        except OSError as exc:
            print(f"[{step['name']}] could not run: {exc}", flush=True)
            return False
        assert p.stdout is not None
        for line in p.stdout:
            print(_ANSI.sub("", line), end="", flush=True)
        try:
            rc = p.wait(timeout=STEP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            p.kill()
            print(f"[{step['name']}] TIMED OUT after {STEP_TIMEOUT_S}s", flush=True)
            return False
        r = subprocess.CompletedProcess(step["argv"], rc)
        if r.returncode != 0:
            if step.get("advisory"):
                print(f"[{step['name']}] exit {r.returncode} (advisory step, continuing)")
                continue
            print(f"[{step['name']}] FAILED with exit {r.returncode}", flush=True)
            return False
    for rel in spec["artifacts"]:
        a = src / rel
        if not a.exists() or (a.is_file() and a.stat().st_size == 0):
            print(f"[artifact] expected {rel} after a successful build; it is not there")
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="hmi-build")
    ap.add_argument("command", choices=["build"])
    ap.add_argument("--spec", required=True, help="the run's build-spec URL, from the step")
    ap.add_argument("--upload", help="the run's image URL; without it the image stays local")
    ap.add_argument("--src", default="/src")
    a = ap.parse_args()

    # A writable home for dotnet and Godot when the container runs as the user's uid.
    home = Path(os.environ.get("HOME") or "/tmp")
    if not os.access(home, os.W_OK):
        os.environ["HOME"] = "/tmp/hmi-home"
        Path("/tmp/hmi-home").mkdir(exist_ok=True)
    os.environ.setdefault("DOTNET_CLI_HOME", os.environ["HOME"])
    # Plain output: the log ends up in a tool call, where colour codes are noise.
    os.environ.setdefault("NO_COLOR", "1")
    os.environ.setdefault("TERM", "dumb")

    src = Path(a.src)
    spec = _get(a.spec)
    base = imagefmt.load_base()
    if spec.get("base") != base.pinned:
        sys.exit(f"hmi-build: this build container builds on {base.pinned}, the server "
                 f"expects {spec.get('base')}: run the image the step names")
    if not _steps(src, spec):
        print("hmi-build: the build failed; nothing was uploaded", flush=True)
        return 1

    layer = imagefmt.layer_from_tree([(src / rel, inner) for rel, inner in spec["layer"]])
    dest = src / "out" / "app-image.tar"
    iid = imagefmt.write_archive(dest, base, layer, name=spec["name"],
                                 version=spec["version"], tag=spec["tag"])
    print(f"hmi-build: image {spec['tag']} {iid} ({dest.stat().st_size} bytes) on {base.pinned}")
    if a.upload:
        _put(a.upload, dest)
        print("hmi-build: uploaded; call ireal_build with ok=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
