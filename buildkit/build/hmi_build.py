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
import shutil
import subprocess
import time
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


# A runtime error in the screen's own code, which the build and the static checks cannot see
# (fruit-slice r2: a typed assignment of a freed node, every frame of the menu -> game cut).
_SCRIPT_ERROR = re.compile(r"^\s*SCRIPT ERROR:")
# Godot with a display (the official 4.7.2 build); `godot` is the export toolchain's.
RENDER_GODOT = os.environ.get("HMI_RENDER_GODOT", "godot-display")


def _render(src: Path, spec: dict) -> bool | None:
    """The screens rendered to out/render/<name>.png from the application's ui/render.json
    (or the spec's default shots), the daemon running beside the screen as on the panel.
    True: rendered. False: the screen's code raised a SCRIPT ERROR -- the build fails. None:
    no picture could be made (no virtual display here, say): reported, not a failure."""
    r = spec.get("render")
    if not r:
        return True
    out = src / "out" / "render"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    plan = src / r["plan"]
    if not plan.is_file():
        plan = out / "default-plan.json"
        plan.write_text(json.dumps(r["default"]))
        print(f"render: no {r['plan']}; rendering the default shots", flush=True)
    w, h = r["resolution"]
    shots = [s for s in (json.loads(plan.read_text()).get("shots") or []) if isinstance(s, dict)]
    last = max([float(s.get("at_s") or 0) for s in shots] or [0])
    log_path = out / "render.log"
    procs: list[subprocess.Popen] = []
    disp = ":97"
    env = {**os.environ, "DISPLAY": disp, "PLATFORM_RENDER": str(plan),
           "PLATFORM_RENDER_OUT": str(out), "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    try:
        with open(log_path, "w") as log:
            procs.append(subprocess.Popen(["Xvfb", disp, "-screen", "0", f"{w}x{h}x24",
                                           "-nolisten", "tcp"], stdout=log, stderr=log))
            sock = Path("/tmp/.X11-unix/X97")
            for _ in range(50):
                if sock.exists():
                    break
                time.sleep(0.2)
            else:
                print("render: no virtual display could be started; nothing rendered", flush=True)
                return None
            daemon = src / r["daemon"]
            if daemon.is_file():
                procs.append(subprocess.Popen(["dotnet", str(daemon)], cwd=src, env=env,
                                              stdout=log, stderr=log))
            argv = [RENDER_GODOT, "--path", str(src / "ui"), "--rendering-driver", "opengl3",
                    "--display-driver", "x11", "--audio-driver", "Dummy",
                    "--resolution", f"{w}x{h}", "--fixed-fps", "60"]
            print(f"render: {len(shots)} shot(s) (first start compiles shaders: 1-2 min)",
                  flush=True)
            g = subprocess.run(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors="replace", timeout=int(last) + 300)
            text = _ANSI.sub("", g.stdout or "")
            log.write(text)
    except subprocess.TimeoutExpired:
        print("render: the screen did not finish its shots in time; see out/render/render.log",
              flush=True)
        return None
    except OSError as exc:
        print(f"render: could not run ({exc}); nothing rendered", flush=True)
        return None
    finally:
        for p in reversed(procs):
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    lines = text.splitlines()
    errors = []
    for i, line in enumerate(lines):
        if _SCRIPT_ERROR.match(line):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            errors.append(line.strip() + (f"  {nxt}" if nxt.startswith("at:") else ""))
    pictures = sorted(p.name for p in out.glob("*.png"))
    for line in lines:
        if line.startswith("render: shot"):
            print(line, flush=True)
    calls = [int(m.group(1)) for m in re.finditer(r"render: shot \S+ at [0-9.]+ s, (\d+) draw calls", text)]
    # The host's budget (60 fps) and ceiling, from its measured capacity: each draw call
    # costs ~0.2 ms of the panel's frame (drawcall-bench, 2026-10-22).
    budget, limit = r.get("draw_calls"), r.get("max_draw_calls")
    how = ("the text of repeated cells as a Label child with z_index 1 so the boxes draw "
           "first, fewer boxes (one per cell, from the theme), hand-drawn shapes through "
           "IrShapes")
    if calls:
        print(f"render: at most {max(calls)} draw calls in a shot"
              + (f" (budget {budget}, limit {limit})" if limit else ""), flush=True)
    if limit and calls and max(calls) > limit:
        print(f"render: FAILED -- {max(calls)} draw calls in one frame, over the panel's {limit} "
              f"(~{max(calls) * 0.2:.0f} ms of a 16.7 ms frame): batch them -- {how}", flush=True)
        return False
    if budget and calls and max(calls) > budget:
        print(f"render: WARNING -- {max(calls)} draw calls is over the panel's 60 fps budget of "
              f"{budget} (~{max(calls) * 0.2:.0f} ms of a 16.7 ms frame): {how}", flush=True)
    if errors:
        uniq = list(dict.fromkeys(errors))
        print(f"render: FAILED -- the screen raised {len(errors)} SCRIPT ERROR(s) "
              f"({len(uniq)} distinct):", flush=True)
        for e in uniq[:20]:
            print(f"  {e}", flush=True)
        return False
    if not pictures:
        print("render: no pictures were made (did the screen start?); see "
              "out/render/render.log", flush=True)
        return None
    print(f"render: {len(pictures)} picture(s) in out/render/: {', '.join(pictures)} -- "
          f"look at every one before calling ireal_build", flush=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="hmi-build")
    ap.add_argument("command", choices=["build"])
    ap.add_argument("--spec", required=True, help="the run's build-spec URL, from the step")
    ap.add_argument("--upload", help="the run's image URL; without it the image stays local")
    ap.add_argument("--src", default="/src")
    ap.add_argument("--no-render", action="store_true",
                    help="skip rendering the screens (the build itself is unchanged)")
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
    # The base's identity is its image ID; names are aliases (a renamed base is the same
    # image). Only a different image is a mismatch, and the message says what to run.
    want = spec.get("base_id") or str(spec.get("base", "")).rsplit("@", 1)[-1]
    if want != base.image_id:
        sys.exit(f"hmi-build: this build container builds on {base.pinned}; the server builds "
                 f"on {spec.get('base')}. Run exactly the container the step names"
                 + (f": {spec['build_image']} (docker pull {spec['build_image']})"
                    if spec.get("build_image") else "") + ".")
    if not _steps(src, spec):
        print("hmi-build: the build failed; nothing was uploaded", flush=True)
        return 1
    if not a.no_render and _render(src, spec) is False:
        print("hmi-build: the build failed (runtime errors in the screen); nothing was "
              "uploaded", flush=True)
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
