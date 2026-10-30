"""Outputs dict -> files under the site dir (write-if-changed, orphan cleanup)."""

import json
import os
import tempfile
from pathlib import Path

CALENDAR_DIR = "calendar"


def render_json(season: dict) -> bytes:
    return (
        json.dumps(season, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def write_outputs(site_dir: Path, outputs: dict[str, bytes], dry_run: bool = False) -> list[str]:
    """Write each `relpath -> bytes` under `site_dir` only if the bytes differ.

    Also deletes `calendar/*.ics` files that are no longer produced. Returns the changed
    relpaths (written, created or deleted); with `dry_run` nothing is touched.
    """
    site_dir = Path(site_dir)
    changed = []
    for relpath, data in sorted(outputs.items()):
        path = site_dir / relpath
        if path.is_file() and path.read_bytes() == data:
            continue
        changed.append(relpath)
        if not dry_run:
            _atomic_write(path, data)
    calendar = site_dir / CALENDAR_DIR
    if calendar.is_dir():
        for path in sorted(calendar.glob("*.ics")):
            relpath = f"{CALENDAR_DIR}/{path.name}"
            if relpath not in outputs:
                changed.append(relpath)
                if not dry_run:
                    path.unlink()
    return sorted(changed)
