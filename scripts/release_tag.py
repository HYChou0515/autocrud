#!/usr/bin/env python3
"""Route a pushed git tag to the package it releases, and refuse drift.

SpecStar ships two artefacts on two independent version streams:

===========  =========================  ==============  ==============
tag          version source             scheme          registry
===========  =========================  ==============  ==============
``vX.Y.Z``   specstar/__init__.py       PEP 440         PyPI
``web-vX``   web/generator/package.json SemVer          npm
===========  =========================  ==============  ==============

They are deliberately *not* unified. PEP 440 spells a pre-release
``0.13.0a2`` and SemVer spells it ``0.13.0-alpha.2``; the two schemes do not
round-trip, and this repo already carries the scar from pretending otherwise
(see ``scripts/next_version.py`` — git-cliff parsing PEP 440 tags as SemVer
is what took ``make release`` down).

The tag is the *only* instruction the release workflow receives, and an
upload cannot be taken back: neither PyPI nor npm allows a version to be
re-uploaded, so a tag that disagrees with the version recorded in the repo
burns that version number permanently. Locally ``make release`` derives the
tag from the version and they cannot drift; a hand-typed ``git tag`` has no
such guarantee. Hence :func:`verify`, which runs before anything is built.

Usage::

    python scripts/release_tag.py refs/tags/v0.13.0a2 [--root .]

Prints ``key=value`` lines for ``$GITHUB_OUTPUT``; exits non-zero when the
tag is unrecognised or disagrees with the repo.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

#: PEP 440 subset SpecStar actually publishes — X.Y.Z with an optional
#: aN / bN / rcN. Kept in step with ``scripts/next_version.py``.
_PEP440 = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")

#: SemVer 2.0.0, which is what npm enforces on `version` at publish time.
_SEMVER = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

#: Where each stream records the version the tag must match. Ordered longest
#: prefix first so ``web-v`` is never read as the bare ``v`` stream — that
#: mistake would publish the Python package at the generator's version.
_STREAMS: tuple[tuple[str, str, str], ...] = (
    ("web-v", "npm", "web/generator/package.json"),
    ("v", "pypi", "specstar/__init__.py"),
)

#: `__version__ = "..."` in specstar/__init__.py — the same line `make
#: release` rewrites with sed, matched the same way.
_DUNDER_VERSION = re.compile(r'^__version__ = "(?P<version>[^"]+)"', re.MULTILINE)


def parse_tag(tag: str) -> tuple[str, str]:
    """Return ``(target, version)`` for a release tag.

    Accepts either a bare tag name or the ``refs/tags/...`` spelling that
    ``github.ref`` hands the workflow. Raises :class:`ValueError` for any tag
    that is not a release tag — an unrecognised tag must stop the run rather
    than fall through to a default stream.
    """
    name = tag.removeprefix("refs/tags/").strip()
    for prefix, target, _ in _STREAMS:
        if not name.startswith(prefix):
            continue
        version = name[len(prefix) :]
        pattern = _SEMVER if target == "npm" else _PEP440
        if not pattern.match(version):
            raise ValueError(
                f"tag {name!r} carries {version!r}, which is not a valid "
                f"{'SemVer' if target == 'npm' else 'PEP 440'} version"
            )
        return target, version
    raise ValueError(
        f"tag {name!r} is not a release tag "
        f"(expected 'vX.Y.Z' for PyPI or 'web-vX.Y.Z' for npm)"
    )


def npm_dist_tag(version: str) -> str:
    """``next`` for a SemVer pre-release, ``latest`` otherwise.

    ``npm publish`` defaults to ``latest``, which is what a bare
    ``npm install specstar-web-generator`` resolves to. Publishing an alpha
    without redirecting it would serve that alpha to every new user.
    """
    return "next" if "-" in version.split("+", 1)[0] else "latest"


def source_version(target: str, root: pathlib.Path) -> tuple[str, str]:
    """Return ``(version, source_path)`` recorded in the repo for *target*."""
    relative = next(path for _, name, path in _STREAMS if name == target)
    source = root / relative
    try:
        text = source.read_text()
    except OSError as exc:
        raise ValueError(f"cannot read version source {relative}: {exc}") from exc

    if target == "npm":
        try:
            version = json.loads(text)["version"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"{relative} has no readable 'version': {exc}") from exc
    else:
        match = _DUNDER_VERSION.search(text)
        if match is None:
            raise ValueError(f'{relative} has no `__version__ = "..."` line')
        version = match.group("version")
    return version, relative


def verify(tag: str, root: pathlib.Path) -> tuple[str, str]:
    """Check *tag* against the version in the repo; return ``(target, version)``.

    Raises :class:`ValueError` naming both versions and the file that
    disagrees, because the operator's next move is to fix one of them.
    """
    target, tagged = parse_tag(tag)
    recorded, relative = source_version(target, root)
    if tagged != recorded:
        raise ValueError(
            f"tag says {tagged!r} but {relative} says {recorded!r} — "
            f"bump the source or delete the tag; the version cannot be "
            f"re-uploaded once published"
        )
    return target, tagged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="tag name, or the refs/tags/... spelling")
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path.cwd(),
        help="repository root (default: cwd)",
    )
    args = parser.parse_args(argv)

    try:
        target, version = verify(args.tag, args.root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"target={target}")
    print(f"version={version}")
    if target == "npm":
        print(f"dist_tag={npm_dist_tag(version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
