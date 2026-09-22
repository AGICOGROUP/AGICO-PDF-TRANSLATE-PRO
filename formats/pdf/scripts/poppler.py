"""Locate Poppler's pdftoppm without assuming one machine's runtime layout.

Two adapters previously carried a byte-for-byte copy of this lookup. Both probed a single
hardcoded layout, ``<interpreter>/../../native/poppler/Library/bin/pdftoppm.exe``, which does not
exist under the managed runtime, so every call silently fell through to ``shutil.which`` and
received the ``pdftoppm.BAT`` shim -- the exact thing the surrounding comment said to avoid,
because the shim cannot reliably forward non-ASCII Windows paths. Cyrillic and Chinese drawing
filenames are routine here, so the fall-through was a real hazard, not a style issue.

Resolution order is now explicit: an override, every layout that has shipped, then PATH. A shim is
still accepted as a last resort so existing environments keep working, but it is reported through
``last_lookup_was_shim`` so callers can surface the non-ASCII risk instead of failing mysteriously.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SHIM_SUFFIXES = (".bat", ".cmd")

# Nearest-to-managed first. The historical Windows bundle kept Poppler under a conda-style
# Library/bin prefix; other installs place the binaries directly under the runtime root.
POPPLER_LAYOUTS = (
    ("native", "poppler", "Library", "bin", "pdftoppm.exe"),
    ("native", "poppler", "bin", "pdftoppm.exe"),
    ("poppler", "Library", "bin", "pdftoppm.exe"),
    ("poppler", "bin", "pdftoppm.exe"),
    ("Library", "bin", "pdftoppm.exe"),
    ("bin", "pdftoppm.exe"),
    ("pdftoppm.exe",),
    ("bin", "pdftoppm"),
    ("pdftoppm",),
)

_LEGACY_DEPENDENCIES = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"

last_lookup_was_shim = False


def search_roots() -> list[Path]:
    base = Path(sys.executable).resolve().parent
    roots = [base, *base.parents[:3]]
    if _LEGACY_DEPENDENCIES.is_dir():
        roots.append(_LEGACY_DEPENDENCIES)
    return list(dict.fromkeys(roots))


def bundled_executables() -> list[Path]:
    return [root.joinpath(*parts) for root in search_roots() for parts in POPPLER_LAYOUTS]


def is_shim(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SHIM_SUFFIXES


def find_pdftoppm() -> str:
    """Return a pdftoppm executable, preferring a real binary over a batch shim."""
    global last_lookup_was_shim
    last_lookup_was_shim = False

    override = os.environ.get("PDFTOPPM")
    if override:
        if not Path(override).is_file():
            raise RuntimeError(f"PDFTOPPM points at a missing executable: {override}")
        last_lookup_was_shim = is_shim(override)
        return str(override)

    for candidate in bundled_executables():
        if candidate.is_file():
            return str(candidate)

    discovered = shutil.which("pdftoppm")
    if discovered:
        last_lookup_was_shim = is_shim(discovered)
        return discovered
    raise RuntimeError(
        "pdftoppm is unavailable; install Poppler or set PDFTOPPM to the real executable"
    )


def lookup_warning() -> str | None:
    """Non-ASCII path hazard introduced by the most recent lookup, if any."""
    if last_lookup_was_shim:
        return (
            "pdftoppm resolved to a batch shim; shim forwarding of non-ASCII source paths is "
            "unreliable, so prefer installing a real Poppler binary or setting PDFTOPPM"
        )
    return None
