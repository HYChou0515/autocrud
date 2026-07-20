#!/usr/bin/env python3
"""Compute the next release version. Used by `make release`.

SpecStar ships **PEP 440** versions (`0.13.0a1`), not the SemVer spelling
(`0.13.0-alpha.1`). git-cliff parses tags as SemVer, so as soon as a
pre-release tag exists its `--bumped-version` fails outright::

    $ git-cliff --bumped-version --bump patch
    ERROR Semver error: `unexpected character 'v' while parsing major version`

which quietly took `make release patch|minor|major` with it. Rather than
bend the published version scheme to suit the changelog generator, the
arithmetic lives here and git-cliff is left to do what it is good at:
turning commits into changelog prose.

Usage::

    python scripts/next_version.py <current> <step>

where *step* is ``alpha``, ``beta``, ``rc``, ``final``, ``patch``, ``minor``
or ``major``. Prints the next version to stdout.
"""

from __future__ import annotations

import re
import sys

#: PEP 440 subset SpecStar actually uses: X.Y.Z with an optional aN / bN / rcN.
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")

#: Pre-release stages in release order. PEP 440 sorts a < b < rc < final, and
#: the index is what makes "is this step going backwards?" answerable.
_STAGES = {"alpha": "a", "beta": "b", "rc": "rc"}
_ORDER = ["a", "b", "rc"]


def _parse(version: str) -> tuple[int, int, int, str | None, int]:
    m = _VERSION.match(version.strip())
    if not m:
        raise ValueError(
            f"cannot parse {version!r} — expected PEP 440 X.Y.Z, X.Y.ZaN, "
            f"X.Y.ZbN or X.Y.ZrcN"
        )
    major, minor, patch, stage, num = m.groups()
    return int(major), int(minor), int(patch), stage, int(num or 0)


def bump(current: str, step: str) -> str:
    """Return the version that follows *current* for *step*."""
    major, minor, patch, stage, num = _parse(current)

    if step in _STAGES:
        target = _STAGES[step]
        if stage is None:
            # A pre-release previews the *next feature release*. Hanging it off
            # a patch version would promise a bugfix and deliver a feature.
            return f"{major}.{minor + 1}.0{target}1"
        if _ORDER.index(target) < _ORDER.index(stage):
            raise ValueError(
                f"{current} → {step} goes backwards: PEP 440 orders "
                f"a < b < rc, so the new version would sort *older* than the "
                f"one already published"
            )
        if target == stage:
            return f"{major}.{minor}.{patch}{stage}{num + 1}"
        # New stage, fresh counter — the stage itself carries the ordering.
        return f"{major}.{minor}.{patch}{target}1"

    if step == "final":
        if stage is None:
            raise ValueError(f"{current} is already final")
        return f"{major}.{minor}.{patch}"

    if step == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if step == "minor":
        return f"{major}.{minor + 1}.0"
    if step == "major":
        return f"{major + 1}.0.0"

    raise ValueError(
        f"unknown step {step!r} — expected alpha, beta, rc, final, patch, "
        f"minor or major"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(bump(argv[1], argv[2]))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
