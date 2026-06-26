"""Filesystem fanout (sharding) helpers — see #387.

Disk-backed stores historically wrote every object as a sibling directly
under one root directory (``root/<name>``). At scale this puts millions of
entries in a single directory, which on NAS / networked filesystems hits
per-directory inode / dirent limits and degrades lookups.

The fix spreads objects across a fixed two-level subdirectory tree rooted at
a reserved container segment::

    <root>/_sh/<ab>/<cd>/<name>

The ``<ab>``/``<cd>`` prefix comes from a fresh ``xxh3`` hash of the *leaf
name*, so the distribution is uniform whether the name is itself a content
hash (already uniform) or a caller-supplied key / slug (arbitrary, possibly
clustered). Both the writer and any later reader hold the leaf name, so the
prefix is fully recomputable and deterministic — no marker file needed.

Two-level × 2 hex = 65,536 leaf directories: every level (including the
intermediates) stays ``<= 256`` children, and even at 100M objects a leaf
holds only ~1.5k entries. The geometry is a fixed module constant on
purpose — making it a per-store parameter would let an operator change the
scheme after data exists, at which point old objects become unreachable
because their shard path no longer computes.

The reserved container segment :data:`SHARD_ROOT` ("_sh") gives every store a
single, unambiguous rule for telling sharded data apart from pre-fanout
("legacy") data during enumeration and migration: anything under ``_sh/`` is
sharded; every other top-level entry is legacy. ``_sh`` is therefore a
reserved name — a resource_id / blob key / pk equal to ``"_sh"`` is not
supported (the default ``resource_id`` carries a ``:`` and never collides).
"""

from __future__ import annotations

from pathlib import Path

from xxhash import xxh3_128_hexdigest

#: Reserved directory name under each store root that contains the sharded tree.
SHARD_ROOT = "_sh"

#: Number of nested prefix directories (``_sh/<ab>/<cd>`` -> 2).
SHARD_LEVELS = 2

#: Hex characters consumed per prefix level (2 -> 256 buckets/level).
SHARD_HEX_PER_LEVEL = 2


def shard_segments(name: str) -> tuple[str, ...]:
    """Return the prefix segments for *name*, e.g. ``("ab", "cd")``.

    Derived from a fresh ``xxh3`` hash of *name* so the spread is uniform
    regardless of the name's own shape.
    """
    digest = xxh3_128_hexdigest(name.encode("utf-8"))
    width = SHARD_HEX_PER_LEVEL
    return tuple(digest[i * width : (i + 1) * width] for i in range(SHARD_LEVELS))


def sharded_dir(root: Path, name: str) -> Path:
    """Return the sharded directory under *root* that holds *name*.

    ``<root>/_sh/<ab>/<cd>``.
    """
    directory = root / SHARD_ROOT
    for segment in shard_segments(name):
        directory = directory / segment
    return directory


def sharded_path(root: Path, name: str) -> Path:
    """Return the full sharded leaf path ``<root>/_sh/<ab>/<cd>/<name>``."""
    return sharded_dir(root, name) / name


def iter_legacy_children(root: Path):
    """Yield top-level entries under *root* that are not the shard container.

    Used by migration and by enumeration fallbacks to walk pre-fanout data
    without descending into the sharded tree. Yields nothing if *root* does
    not exist.
    """
    if not root.exists():
        return
    for child in root.iterdir():
        if child.name == SHARD_ROOT:
            continue
        yield child
