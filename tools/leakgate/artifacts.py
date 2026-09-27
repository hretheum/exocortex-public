"""Scanning build artifacts: wheels, sdists and container images.

Images are read from `docker save` / `podman save` archives (docker-archive
format) or from OCI image layouts, either as a directory or a tar file. Each
layer is scanned on its own, and so is the image configuration (environment,
labels, build history), because those end up in the registry too.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from .scan import Finding, Scanner


def scan_package(scanner: Scanner, path: Path) -> list[Finding]:
    """Wheel or sdist: the archive handler in meta.extract recurses into it."""
    return scanner.scan_bytes(path.name, path.read_bytes())


def _read_image(path: Path) -> dict[str, bytes]:
    """Return {name: bytes} for every file in an image archive or OCI directory."""
    files: dict[str, bytes] = {}
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                files[f.relative_to(path).as_posix()] = f.read_bytes()
        return files
    with tarfile.open(path, mode="r:*") as tf:
        for m in tf.getmembers():
            if m.isfile():
                fh = tf.extractfile(m)
                if fh is not None:
                    files[m.name] = fh.read()
    return files


def _config_text(config: dict) -> str:
    cfg = config.get("config", {}) or {}
    lines: list[str] = []
    lines.extend(cfg.get("Env", []) or [])
    for k, v in (cfg.get("Labels", {}) or {}).items():
        lines.append(f"{k}={v}")
    for h in config.get("history", []) or []:
        lines.append(h.get("created_by", ""))
        if h.get("comment"):
            lines.append(h["comment"])
    for key in ("Cmd", "Entrypoint"):
        if cfg.get(key):
            lines.append(" ".join(cfg[key]))
    return "\n".join(lines)


def scan_image(scanner: Scanner, path: Path) -> list[Finding]:
    files = _read_image(path)
    found: list[Finding] = []
    layers: list[str] = []
    configs: list[str] = []
    if "manifest.json" in files:  # docker-archive
        manifest = json.loads(files["manifest.json"])
        for entry in manifest:
            configs.append(entry["Config"])
            layers.extend(entry["Layers"])
    elif "index.json" in files:  # OCI layout
        index = json.loads(files["index.json"])
        stack = list(index.get("manifests", []))
        while stack:
            desc = stack.pop()
            blob = files.get("blobs/" + desc["digest"].replace(":", "/"))
            if blob is None:
                continue
            doc = json.loads(blob)
            if "manifests" in doc:
                stack.extend(doc["manifests"])
                continue
            configs.append("blobs/" + doc["config"]["digest"].replace(":", "/"))
            layers.extend("blobs/" + layer["digest"].replace(":", "/") for layer in doc.get("layers", []))
    else:
        return [Finding(path.name, 0, "image.unknown_format", "block", "", "not a docker-archive or OCI layout")]
    for cfg_name in configs:
        cfg = json.loads(files[cfg_name])
        found.extend(scanner.scan_text(f"{path.name}#config", _config_text(cfg)))
    for layer in dict.fromkeys(layers):
        data = files.get(layer)
        if data is None:
            found.append(Finding(path.name, 0, "image.missing_layer", "block", "", layer))
            continue
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                for m in tf.getmembers():
                    if not m.isfile() or Path(m.name).name.startswith(".wh."):
                        continue
                    fh = tf.extractfile(m)
                    if fh is not None:
                        found.extend(scanner.scan_bytes(f"{path.name}!{layer[-19:]}!/{m.name}", fh.read(), depth=1))
        except tarfile.TarError:
            found.append(Finding(path.name, 0, "image.bad_layer", "block", "", layer))
    return found
