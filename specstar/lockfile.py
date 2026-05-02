"""Lockfile read/write for ``spec.lock.json``.

The lockfile is the manifest tying ``spec.md`` and ``_generated.py`` together
with the descriptor and a per-source SHA-256 hash. ``specstar verify`` uses
the hashes to detect drift between source files and the last regeneration.

See ``docs/design/spec-driven-architecture.md`` §3.6 for the manifest layout
and case-1/2/3/4 hash decision tree.

Phase 1.3 (this module): build / read / write / hash. Hashing is raw bytes
SHA-256 — Phase 1.4 introduces content normalization (LF line endings, trim
trailing whitespace for Markdown; ``ruff format`` for Python) so that
trivial cosmetic edits do not flip the hash.

This module is internal to the v0.11 spec-driven layer.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path

import msgspec.json

from specstar import __version__ as _SPECSTAR_VERSION
from specstar.descriptor import (
    DESCRIPTOR_VERSION,
    Descriptor,
    Manifest,
    SourceFile,
    ValidationStatus,
)


def compute_file_hash(path: str | Path) -> tuple[str, int]:
    """Return ``(sha256_hex, size_bytes)`` for the file at ``path``.

    Phase 1.3 hashes raw bytes. Phase 1.4 will route through file-type-specific
    normalizers so that line-ending and whitespace differences do not flip
    the hash. Callers should treat this as "the canonical SpecStar hash" and
    not assume it stays raw across versions.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
    """
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def build_source_file(
    path: str | Path,
    *,
    regenerated_at: str | None = None,
) -> SourceFile:
    """Build a :class:`SourceFile` manifest entry for the file at ``path``.

    Args:
        path: Filesystem path to the source file.
        regenerated_at: ISO-8601 timestamp recording when this entry was
            produced. Optional — pass :func:`now_iso` for production calls;
            leave ``None`` for deterministic test fixtures.
    """
    sha256, size = compute_file_hash(path)
    return SourceFile(sha256=sha256, size=size, regenerated_at=regenerated_at)


def build_manifest(
    descriptor: Descriptor,
    sources: dict[str, str | Path],
    *,
    validation: ValidationStatus | None = None,
    skill_version: str | None = None,
    regenerated_at: str | None = None,
) -> Manifest:
    """Assemble a complete :class:`Manifest`.

    Args:
        descriptor: The property graph (from
            :meth:`SpecStar.dump_descriptor`).
        sources: Mapping from manifest key (e.g. ``"spec.md"``) to filesystem
            path. Each path is hashed; the manifest key is what later
            ``specstar verify`` looks up against the on-disk file.
        validation: AST validator outcome; defaults to ``"skipped"``.
        skill_version: Defaults to the SpecStar package version (the v0.11
            skill is bundled with the package). Override only if the skill
            is shipped on a different cadence.
        regenerated_at: Stamp applied to every :class:`SourceFile`. Pass
            :func:`now_iso` for production calls; ``None`` for deterministic
            tests.
    """
    return Manifest(
        specstar_version=_SPECSTAR_VERSION,
        skill_version=skill_version or _SPECSTAR_VERSION,
        descriptor_version=DESCRIPTOR_VERSION,
        sources={
            key: build_source_file(p, regenerated_at=regenerated_at)
            for key, p in sources.items()
        },
        descriptor=descriptor,
        validation=validation or ValidationStatus(),
    )


def read_manifest(path: str | Path) -> Manifest:
    """Decode :class:`Manifest` from ``spec.lock.json`` on disk.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        msgspec.DecodeError: if the file is not a valid manifest.
    """
    return msgspec.json.decode(Path(path).read_bytes(), type=Manifest)


def write_manifest(manifest: Manifest, path: str | Path) -> None:
    """Serialize ``manifest`` to ``path`` as indented JSON.

    The output is byte-for-byte deterministic for a given :class:`Manifest`
    input (msgspec orders struct fields by declaration order and dict keys
    by insertion order). Callers that need cross-machine reproducibility
    should likewise sort their ``sources`` mapping before passing it to
    :func:`build_manifest`.
    """
    encoded = msgspec.json.format(msgspec.json.encode(manifest), indent=2)
    Path(path).write_bytes(encoded)


def now_iso() -> str:
    """Return current UTC time as an ISO-8601 string with ``Z`` suffix.

    Convenience helper for callers that want to stamp ``regenerated_at``
    without depending directly on :mod:`datetime`.
    """
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
