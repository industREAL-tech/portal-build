"""Application images: the application's own files as ONE layer over portal-base, written
without a docker daemon and byte-for-byte reproducibly (docs/CLIENT-BUILD.md).

The same code runs in two places:
- on the user's machine, inside hmi-build, it writes `app-image.tar` from a built tree;
- on the server it checks an uploaded `app-image.tar` before anything is signed.

The server cannot see that the binaries came from the source (the owner accepted that,
2026-10-21). Everything else it can recompute, so it does: the layer may hold only plain
files and directories under app/, run.sh must be the one the generator wrote, and the
config must be byte-equal to the one built here. The config's digest is the image ID the
panel's docker reports after `docker load`, so the ID that gets signed is known exactly.

The archive is a docker-archive (what `docker save` writes; the panel runs Docker 25 with
the classic overlay2 store). Its manifest lists every layer, but only the application's is
in it: Docker 25 reuses a layer it already holds by chain ID and never opens the missing
file (moby v25.0.9 image/tarexport/load.go:104), and the panel holds the base from its own
artifact. A containerd image store would need the full archive.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import stat
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

# Every file in the layer gets this mtime, and the config this `created`: the build is a
# function of the files alone, so the same tree gives the same image ID on any machine.
EPOCH = 0
CREATED = "1970-01-01T00:00:00Z"
ROOT = "app"

# Executable whatever their mode on disk: the entry point and the two programs it starts.
# The server writes run.sh without the x bit, and the Dockerfile this replaces made all
# three executable at install time (`chmod +x`); without it the container cannot start.
EXECUTABLES = (f"{ROOT}/run.sh", f"{ROOT}/daemon/daemon", f"{ROOT}/ui")

# What a layer may hold, generously above today's applications (a Godot UI is ~70 MB).
MAX_LAYER_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 20000

# The pinned bases' records: buildkit/base in this repository, /opt/hmi-build/base in the
# hmi-build container, which carries this module on its own.
BASE_DIR = Path(os.environ.get("HMI_BASE_DIR")
                or Path(__file__).resolve().parent.parent / "buildkit" / "base")


@dataclass
class Base:
    """A pinned portal-base: its reference, image ID and the config it was built with."""
    ref: str                 # "portal-base:1"
    image_id: str            # "sha256:…", the config digest
    config: dict

    @property
    def diff_ids(self) -> list[str]:
        return list(self.config["rootfs"]["diff_ids"])

    @property
    def pinned(self) -> str:
        return f"{self.ref}@{self.image_id}"


def load_base(version: int = 1) -> Base:
    """The base this generator builds against, from buildkit/base/base-<n>.json: docker's
    own config bytes for it, which are what its image ID is the digest of."""
    rec = json.loads((BASE_DIR / f"base-{version}.json").read_text())
    raw = rec["config_bytes"].encode()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != rec["image_id"]:
        raise ValueError(f"base-{version}.json: config does not hash to its image_id")
    return Base(ref=rec["ref"], image_id=rec["image_id"], config=json.loads(raw))


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# ------------------------------------------------------------------ the layer

def layer_from_tree(items: list[tuple[Path, str]]) -> bytes:
    """One uncompressed tar of `items` -- (path on disk, path under app/) -- with fixed
    owner, time and modes. Directories are walked; anything that is not a plain file or a
    directory (a symlink, a device) is refused rather than silently skipped."""
    entries: dict[str, tuple[str, Path | None, int]] = {ROOT: ("dir", None, 0o755)}

    def add_dir(rel: str) -> None:
        parts = rel.split("/")
        for i in range(1, len(parts) + 1):
            entries.setdefault("/".join(parts[:i]), ("dir", None, 0o755))

    for src, inner in items:
        name = f"{ROOT}/{inner.strip('/')}"
        if src.is_symlink():
            raise ValueError(f"{src}: a symlink cannot go into an application image")
        if src.is_dir():
            add_dir(name)
            for p in sorted(src.rglob("*")):
                rel = f"{name}/{p.relative_to(src).as_posix()}"
                if p.is_symlink():
                    raise ValueError(f"{p}: a symlink cannot go into an application image")
                if p.is_dir():
                    add_dir(rel)
                elif p.is_file():
                    add_dir(rel.rsplit("/", 1)[0])
                    entries[rel] = ("file", p, _mode(p))
                else:
                    raise ValueError(f"{p}: only files and directories go into an image")
        elif src.is_file():
            add_dir(name.rsplit("/", 1)[0])
            entries[name] = ("file", src, _mode(src))
        else:
            raise ValueError(f"{src}: missing, or not a file or directory")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(entries):
            kind, path, mode = entries[name]
            if kind == "file" and name in EXECUTABLES:
                mode = 0o755
            info = tarfile.TarInfo(name)
            info.mtime, info.uid, info.gid, info.uname, info.gname = EPOCH, 0, 0, "", ""
            info.mode = mode
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                data = path.read_bytes()
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _mode(p: Path) -> int:
    return 0o755 if p.stat().st_mode & 0o111 else 0o644


def diff_id(layer: bytes) -> str:
    return "sha256:" + hashlib.sha256(layer).hexdigest()


# ------------------------------------------------------------------ the config

def app_config(base: Base, layer_diff_id: str, *, name: str, version: str) -> bytes:
    """The application image's config, canonical JSON: the base's, with the entry point,
    the working directory, the application's labels and its layer. The launcher prunes
    only images labelled tech.industreal.app, which the base itself is not."""
    cfg = copy.deepcopy(base.config)
    cfg["created"] = CREATED
    c = cfg.setdefault("config", {})
    c["WorkingDir"] = "/app"
    c["Entrypoint"] = ["/app/run.sh"]
    c.pop("Cmd", None)
    labels = dict(c.get("Labels") or {})
    labels["tech.industreal.app"] = name
    labels["tech.industreal.app.version"] = version
    c["Labels"] = labels
    cfg["rootfs"] = {"type": "layers", "diff_ids": base.diff_ids + [layer_diff_id]}
    cfg["history"] = list(cfg.get("history") or []) + [
        {"created": CREATED, "created_by": f"hmi-build: {name} {version}"}]
    return _canon(cfg)


def image_id(config: bytes) -> str:
    return "sha256:" + hashlib.sha256(config).hexdigest()


# ------------------------------------------------------------------ the archive

def write_archive(dest: Path, base: Base, layer: bytes, *, name: str, version: str,
                  tag: str) -> str:
    """Write `app-image.tar` and return its image ID. Only the config and the
    application's layer are inside; the base's layers are named in the manifest only."""
    lid = diff_id(layer)
    cfg = app_config(base, lid, name=name, version=version)
    iid = image_id(cfg)
    layers = [f"base/{d.split(':', 1)[1]}.tar" for d in base.diff_ids]
    layers.append(f"{lid.split(':', 1)[1]}/layer.tar")
    manifest = [{"Config": f"{iid.split(':', 1)[1]}.json", "RepoTags": [tag], "Layers": layers}]
    with tarfile.open(dest, "w", format=tarfile.PAX_FORMAT) as tar:
        for member, data in ((f"{lid.split(':', 1)[1]}/layer.tar", layer),
                             (manifest[0]["Config"], cfg),
                             ("manifest.json", json.dumps(manifest).encode())):
            info = tarfile.TarInfo(member)
            info.mtime, info.mode, info.size = EPOCH, 0o644, len(data)
            tar.addfile(info, io.BytesIO(data))
    return iid


# ------------------------------------------------------------------ the server's check

@dataclass
class Verdict:
    image_id: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and self.image_id is not None


def verify(archive: Path, base: Base, *, name: str, version: str, tag: str,
           run_sh: bytes, needs_ui: bool) -> Verdict:
    """Everything the server can know about an uploaded application image without
    rebuilding it. A Verdict with problems is never signed."""
    v = Verdict()
    bad = v.problems.append
    try:
        outer = tarfile.open(archive, "r:")
    except (tarfile.TarError, OSError) as exc:
        return Verdict(problems=[f"not a tar archive: {exc}"])
    with outer:
        members = {}
        for m in outer.getmembers():
            if not m.isfile() or m.name.startswith("/") or ".." in m.name.split("/"):
                bad(f"archive entry {m.name!r} is not a plain relative file")
                continue
            members[m.name] = m
        if v.problems:
            return v
        try:
            manifest = json.loads(outer.extractfile(members["manifest.json"]).read())
            (entry,) = manifest
            cfg_name, layers, tags = entry["Config"], entry["Layers"], entry.get("RepoTags")
        except (KeyError, ValueError, TypeError) as exc:
            return Verdict(problems=[f"manifest.json is not one image: {exc}"])
        if tags != [tag]:
            bad(f"tagged {tags!r}, expected [{tag!r}]")
        if not isinstance(layers, list) or len(layers) != len(base.diff_ids) + 1:
            return Verdict(problems=[f"expected {len(base.diff_ids)} base layers and one "
                                     f"application layer, the manifest lists {layers!r}"])
        app_name = layers[-1]
        extra = set(members) - {"manifest.json", cfg_name, app_name, "repositories"}
        if extra:
            bad(f"unexpected entries {sorted(extra)}: only the config and the application's "
                f"layer may be in the archive")
        if cfg_name not in members or app_name not in members:
            return Verdict(problems=v.problems + ["the config or the application layer is missing"])
        if members[app_name].size > MAX_LAYER_BYTES:
            return Verdict(problems=[f"the application layer is {members[app_name].size} "
                                     f"bytes, over {MAX_LAYER_BYTES}"])
        layer = outer.extractfile(members[app_name]).read()
        cfg = outer.extractfile(members[cfg_name]).read()

    v.problems += _check_layer(layer, run_sh=run_sh, needs_ui=needs_ui)
    expected = app_config(base, diff_id(layer), name=name, version=version)
    if cfg != expected:
        bad("the config is not the one this application builds to (base, entry point, "
            "labels or layers differ)")
    elif cfg_name != f"{image_id(cfg).split(':', 1)[1]}.json":
        bad("the config's file name is not its digest")
    if not v.problems:
        v.image_id = image_id(expected)
    return v


def _check_layer(layer: bytes, *, run_sh: bytes, needs_ui: bool) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    try:
        tar = tarfile.open(fileobj=io.BytesIO(layer), mode="r:")
        members = tar.getmembers()
    except tarfile.TarError as exc:
        return [f"the application layer is not a tar: {exc}"]
    if len(members) > MAX_ENTRIES:
        return [f"the application layer has {len(members)} entries, over {MAX_ENTRIES}"]
    for m in members:
        n = m.name.rstrip("/")
        parts = n.split("/")
        if parts[0] != ROOT or ".." in parts or "" in parts or n.startswith("/"):
            out.append(f"{m.name!r} is outside {ROOT}/")
        elif not (m.isfile() or m.isdir()):
            out.append(f"{m.name!r} is not a plain file or directory")
        elif m.mode & ~0o777 or stat.S_IMODE(m.mode) & 0o022:
            out.append(f"{m.name!r} has mode {oct(m.mode)} (no setuid, setgid, sticky "
                       f"or group/world-writable bits)")
        elif m.uid or m.gid:
            out.append(f"{m.name!r} is owned by {m.uid}:{m.gid}, not root")
        elif n in seen:
            out.append(f"{m.name!r} appears twice")
        seen.add(n)
    names = {m.name.rstrip("/"): m for m in members}
    need = [f"{ROOT}/run.sh", f"{ROOT}/daemon/daemon"] + ([f"{ROOT}/ui"] if needs_ui else [])
    for n in need:
        if n not in names:
            out.append(f"{n} is missing")
        elif n != f"{ROOT}/ui" and not names[n].isfile():
            out.append(f"{n} is not a file")
        elif names[n].isfile() and stat.S_IMODE(names[n].mode) & 0o111 != 0o111:
            out.append(f"{n} is not executable (mode {oct(names[n].mode)}): the container "
                       f"could not start")
    if f"{ROOT}/run.sh" in names and names[f"{ROOT}/run.sh"].isfile():
        if tar.extractfile(names[f"{ROOT}/run.sh"]).read() != run_sh:
            out.append(f"{ROOT}/run.sh is not the one the generator wrote")
    return out


# ------------------------------------------------------------------ the full archive

def complete(trimmed: Path, base_tar: Path, base: Base, dest: Path) -> None:
    """`trimmed` plus the base's layers: an archive a panel can load with nothing loaded
    before it. Signed instead of the trimmed one until panels hold the base on their own
    (docs/CLIENT-BUILD.md); docker reuses the layers it already has, so the cost is
    bandwidth, not disk. `base_tar` is `docker save` of the base, checked against its
    pinned image ID before anything of it is used."""
    with tarfile.open(base_tar, "r:") as bt:
        bman = json.loads(bt.extractfile("manifest.json").read())
        (bentry,) = bman
        cfg = bt.extractfile(bentry["Config"]).read()
        if image_id(cfg) != base.image_id:
            raise ValueError(f"{base_tar} is not {base.pinned}")
        if len(bentry["Layers"]) != len(base.diff_ids):
            raise ValueError(f"{base_tar} has {len(bentry['Layers'])} layers, the base "
                             f"{len(base.diff_ids)}")
        with tarfile.open(trimmed, "r:") as tt:
            (entry,) = json.loads(tt.extractfile("manifest.json").read())
            names = entry["Layers"][:len(base.diff_ids)]
            with tarfile.open(dest, "w", format=tarfile.PAX_FORMAT) as out:
                for m in tt.getmembers():
                    out.addfile(m, tt.extractfile(m))
                # Docker checks every layer against the config's diff_ids as it loads it,
                # compressed or not, so a wrong base layer is refused on the panel too.
                for name, src in zip(names, bentry["Layers"]):
                    m = bt.getmember(src)
                    info = tarfile.TarInfo(name)
                    info.size, info.mtime, info.mode = m.size, EPOCH, 0o644
                    out.addfile(info, bt.extractfile(m))
