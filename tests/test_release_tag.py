"""Tag → package routing for the tag-triggered release workflows.

SpecStar publishes two independent artefacts on two independent version
streams: the Python distribution (`specstar/__init__.py`, PEP 440, tagged
`vX.Y.Z`) and the npm code generator (`web/generator/package.json`, SemVer,
tagged `web-vX.Y.Z`). CI publishes whatever a pushed tag points at, so the
tag is the only instruction the workflow gets — and a tag that disagrees
with the version recorded in the repo is unrecoverable once uploaded:
neither PyPI nor npm lets a version be re-uploaded.

Locally `make release` derives the tag *from* the version, so they cannot
drift. A hand-typed `git tag` has no such guarantee, which is exactly the
case these rules exist for.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_MODULE = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "release_tag.py"
_spec = importlib.util.spec_from_file_location("release_tag", _MODULE)
assert _spec and _spec.loader
release_tag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_tag)

parse_tag = release_tag.parse_tag
npm_dist_tag = release_tag.npm_dist_tag
verify = release_tag.verify


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A miniature repo carrying just the two version sources."""
    pkg = tmp_path / "specstar"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        '"""doc."""\n\nfrom x import y\n\n__version__ = "0.13.0a2"\n'
    )
    gen = tmp_path / "web" / "generator"
    gen.mkdir(parents=True)
    (gen / "package.json").write_text(
        json.dumps({"name": "specstar-web-generator", "version": "0.3.4"})
    )
    return tmp_path


# ---------------------------------------------------------------------------
# parse_tag — which package does this tag release, and at what version?
# ---------------------------------------------------------------------------


def test_plain_v_tag_is_the_python_distribution():
    assert parse_tag("v0.13.0a2") == ("pypi", "0.13.0a2")


def test_web_prefixed_tag_is_the_npm_generator():
    assert parse_tag("web-v0.3.4") == ("npm", "0.3.4")


def test_refs_tags_prefix_is_accepted():
    """Workflows get ``refs/tags/...`` in ``github.ref``, not the bare name."""
    assert parse_tag("refs/tags/v0.13.0a2") == ("pypi", "0.13.0a2")
    assert parse_tag("refs/tags/web-v0.3.4") == ("npm", "0.3.4")


def test_web_tag_is_not_read_as_a_python_release():
    """The `v*` glob must never swallow the npm stream, or a web tag would
    publish the Python package at the generator's version."""
    target, _ = parse_tag("web-v0.3.4")
    assert target == "npm"


@pytest.mark.parametrize(
    "tag",
    [
        "0.13.0a2",  # no v
        "v",  # no version
        "vnext",  # not a version
        "web-v",  # no version
        "release-v1.0.0",  # unknown stream
        "v1.0.0-extra-junk",  # PEP 440 has no SemVer pre-release spelling
    ],
)
def test_unrecognised_tags_are_refused(tag: str):
    with pytest.raises(ValueError):
        parse_tag(tag)


# ---------------------------------------------------------------------------
# npm_dist_tag — a pre-release must never take over `latest`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["0.3.4", "1.0.0", "10.2.30"])
def test_release_versions_take_latest(version: str):
    assert npm_dist_tag(version) == "latest"


@pytest.mark.parametrize(
    "version", ["0.4.0-alpha.1", "0.4.0-beta.2", "1.0.0-rc.1", "1.0.0-next.0"]
)
def test_prereleases_are_parked_on_next(version: str):
    """`npm publish` defaults to `latest`; an alpha landing there would be
    served to everyone running a bare `npm install specstar-web-generator`."""
    assert npm_dist_tag(version) == "next"


# ---------------------------------------------------------------------------
# verify — the tag must agree with the version recorded in the repo
# ---------------------------------------------------------------------------


def test_verify_returns_the_version_when_the_tag_agrees(repo: pathlib.Path):
    assert verify("v0.13.0a2", repo) == ("pypi", "0.13.0a2")
    assert verify("web-v0.3.4", repo) == ("npm", "0.3.4")


def test_verify_rejects_a_python_tag_that_outran_the_source(repo: pathlib.Path):
    with pytest.raises(ValueError) as excinfo:
        verify("v0.13.0a3", repo)
    message = str(excinfo.value)
    assert "0.13.0a3" in message and "0.13.0a2" in message
    assert "specstar/__init__.py" in message


def test_verify_rejects_an_npm_tag_that_outran_the_source(repo: pathlib.Path):
    with pytest.raises(ValueError) as excinfo:
        verify("web-v0.4.0", repo)
    message = str(excinfo.value)
    assert "0.4.0" in message and "0.3.4" in message
    assert "web/generator/package.json" in message


def test_verify_reports_a_missing_version_source(tmp_path: pathlib.Path):
    with pytest.raises(ValueError):
        verify("v1.0.0", tmp_path)
