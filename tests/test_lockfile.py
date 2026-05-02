"""Tests for ``specstar.lockfile``: hashing, manifest build / read / write."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import msgspec
import pytest

from specstar.descriptor import (
    DESCRIPTOR_VERSION,
    Descriptor,
    Edge,
    EdgeType,
    Node,
    NodeType,
    ValidationStatus,
)
from specstar.lockfile import (
    build_manifest,
    build_source_file,
    compute_file_hash,
    now_iso,
    read_manifest,
    write_manifest,
)


@pytest.fixture()
def tmp_md(tmp_path: Path) -> Path:
    p = tmp_path / "spec.md"
    p.write_text("# Demo\n\nA short specification.\n")
    return p


@pytest.fixture()
def tmp_py(tmp_path: Path) -> Path:
    p = tmp_path / "_generated.py"
    p.write_text("x = 1\n")
    return p


@pytest.fixture()
def sample_descriptor() -> Descriptor:
    return Descriptor(
        nodes=[
            Node(id="resource:user", type=NodeType.resource),
            Node(id="field:user.name", type=NodeType.field),
        ],
        edges=[
            Edge(
                type=EdgeType.has_field,
                source_id="resource:user",
                target_id="field:user.name",
            )
        ],
    )


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------


class TestComputeFileHash:
    def test_returns_sha256_and_size(self, tmp_md: Path) -> None:
        sha, size = compute_file_hash(tmp_md)
        expected_sha = hashlib.sha256(tmp_md.read_bytes()).hexdigest()
        assert sha == expected_sha
        assert size == len(tmp_md.read_bytes())
        assert len(sha) == 64

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_bytes(b"hello")
        b.write_bytes(b"hello")
        assert compute_file_hash(a) == compute_file_hash(b)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_bytes(b"hello")
        b.write_bytes(b"world")
        assert compute_file_hash(a)[0] != compute_file_hash(b)[0]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compute_file_hash(tmp_path / "nope.txt")


# ---------------------------------------------------------------------------
# build_source_file / build_manifest
# ---------------------------------------------------------------------------


class TestBuildSourceFile:
    def test_minimal_no_timestamp(self, tmp_md: Path) -> None:
        sf = build_source_file(tmp_md)
        assert sf.sha256 == hashlib.sha256(tmp_md.read_bytes()).hexdigest()
        assert sf.size == len(tmp_md.read_bytes())
        assert sf.regenerated_at is None

    def test_with_explicit_timestamp(self, tmp_md: Path) -> None:
        ts = "2026-05-02T10:00:00Z"
        sf = build_source_file(tmp_md, regenerated_at=ts)
        assert sf.regenerated_at == ts


class TestBuildManifest:
    def test_assembles_specstar_and_descriptor_versions(
        self, sample_descriptor: Descriptor, tmp_md: Path, tmp_py: Path
    ) -> None:
        manifest = build_manifest(
            sample_descriptor,
            sources={"spec.md": tmp_md, "my_app/_generated.py": tmp_py},
        )
        from specstar import __version__ as version

        assert manifest.specstar_version == version
        assert manifest.skill_version == version
        assert manifest.descriptor_version == DESCRIPTOR_VERSION

    def test_each_source_entry_hashes_its_file(
        self, sample_descriptor: Descriptor, tmp_md: Path, tmp_py: Path
    ) -> None:
        manifest = build_manifest(
            sample_descriptor,
            sources={"spec.md": tmp_md, "my_app/_generated.py": tmp_py},
        )
        assert (
            manifest.sources["spec.md"].sha256
            == hashlib.sha256(tmp_md.read_bytes()).hexdigest()
        )
        assert (
            manifest.sources["my_app/_generated.py"].sha256
            == hashlib.sha256(tmp_py.read_bytes()).hexdigest()
        )

    def test_validation_default_is_skipped(
        self, sample_descriptor: Descriptor, tmp_md: Path
    ) -> None:
        manifest = build_manifest(sample_descriptor, sources={"spec.md": tmp_md})
        assert manifest.validation.ast_check == "skipped"
        assert manifest.validation.errors == []

    def test_skill_version_override(
        self, sample_descriptor: Descriptor, tmp_md: Path
    ) -> None:
        manifest = build_manifest(
            sample_descriptor,
            sources={"spec.md": tmp_md},
            skill_version="0.99-dev",
        )
        assert manifest.skill_version == "0.99-dev"

    def test_regenerated_at_propagated_to_sources(
        self, sample_descriptor: Descriptor, tmp_md: Path
    ) -> None:
        ts = "2026-05-02T10:00:00Z"
        manifest = build_manifest(
            sample_descriptor,
            sources={"spec.md": tmp_md},
            regenerated_at=ts,
        )
        assert manifest.sources["spec.md"].regenerated_at == ts


# ---------------------------------------------------------------------------
# read / write round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_write_then_read_preserves_structure(
        self,
        sample_descriptor: Descriptor,
        tmp_md: Path,
        tmp_path: Path,
    ) -> None:
        manifest = build_manifest(
            sample_descriptor,
            sources={"spec.md": tmp_md},
            validation=ValidationStatus(ast_check="passed"),
        )
        out = tmp_path / "spec.lock.json"
        write_manifest(manifest, out)
        restored = read_manifest(out)
        assert restored == manifest

    def test_write_is_indented_and_parseable(
        self,
        sample_descriptor: Descriptor,
        tmp_md: Path,
        tmp_path: Path,
    ) -> None:
        manifest = build_manifest(sample_descriptor, sources={"spec.md": tmp_md})
        out = tmp_path / "spec.lock.json"
        write_manifest(manifest, out)
        text = out.read_text()
        assert "\n  " in text  # has indentation
        # Standard library json must also parse it cleanly.
        parsed = json.loads(text)
        assert parsed["descriptor_version"] == DESCRIPTOR_VERSION
        assert "spec.md" in parsed["sources"]

    def test_write_byte_deterministic_for_same_input(
        self,
        sample_descriptor: Descriptor,
        tmp_md: Path,
        tmp_path: Path,
    ) -> None:
        manifest = build_manifest(sample_descriptor, sources={"spec.md": tmp_md})
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        write_manifest(manifest, out_a)
        write_manifest(manifest, out_b)
        assert out_a.read_bytes() == out_b.read_bytes()

    def test_read_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_manifest(tmp_path / "nope.lock.json")

    def test_read_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.lock.json"
        bad.write_text("{not json")
        with pytest.raises(msgspec.DecodeError):
            read_manifest(bad)


# ---------------------------------------------------------------------------
# now_iso helper
# ---------------------------------------------------------------------------


class TestNowIso:
    def test_format(self) -> None:
        result = now_iso()
        # ISO-8601 with Z suffix; second precision (no microseconds).
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)
