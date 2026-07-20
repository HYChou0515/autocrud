"""Version arithmetic for `make release` (PEP 440, not SemVer).

SpecStar ships PEP 440 versions — `0.13.0a1`, not the SemVer spelling
`0.13.0-alpha.1`. git-cliff parses tags as SemVer, so the moment a
pre-release tag exists it can no longer compute the next version:

    $ git-cliff --bumped-version --bump patch
    ERROR Semver error: `unexpected character 'v' while parsing major version`

That took `make release patch|minor|major` down with it, silently, and left
`make release VERSION=...` as the only working path. So the arithmetic lives
here instead, and git-cliff is used only for what it is good at — turning
commits into changelog prose.

These rules only ever run at release time, where a mistake means a wrong
version on PyPI that cannot be taken back.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_MODULE = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "next_version.py"
_spec = importlib.util.spec_from_file_location("next_version", _MODULE)
assert _spec and _spec.loader
next_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(next_version)

bump = next_version.bump


# ---------------------------------------------------------------------------
# Pre-release steps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("0.13.0a1", "0.13.0a2"),
        ("0.13.0a2", "0.13.0a3"),
        ("0.13.0a9", "0.13.0a10"),
        ("1.0.0a1", "1.0.0a2"),
    ],
)
def test_alpha_advances_the_alpha_counter(current, expected):
    assert bump(current, "alpha") == expected


def test_alpha_from_a_final_release_opens_the_next_minor():
    """0.12.3 is shipped, so the next alpha belongs to 0.13.0 — not 0.12.4.

    An alpha is a preview of the *next* feature release; attaching it to a
    patch version would promise a bugfix and deliver a feature.
    """
    assert bump("0.12.3", "alpha") == "0.13.0a1"
    assert bump("1.4.7", "alpha") == "1.5.0a1"


def test_beta_and_rc_follow_the_same_shape():
    assert bump("0.13.0b1", "beta") == "0.13.0b2"
    assert bump("0.13.0rc1", "rc") == "0.13.0rc2"


def test_moving_up_a_stage_restarts_the_counter():
    """a2 → b1, not b3: the counter belongs to the stage, and PEP 440 orders
    a < b < rc so the version still moves forward."""
    assert bump("0.13.0a2", "beta") == "0.13.0b1"
    assert bump("0.13.0b4", "rc") == "0.13.0rc1"
    assert bump("0.13.0a7", "rc") == "0.13.0rc1"


def test_moving_down_a_stage_is_refused():
    """rc1 → alpha would sort *backwards*; PyPI would keep serving the rc as
    the newer release and the mistake would be invisible."""
    with pytest.raises(ValueError, match="backwards"):
        bump("0.13.0rc1", "alpha")
    with pytest.raises(ValueError, match="backwards"):
        bump("0.13.0b2", "alpha")


# ---------------------------------------------------------------------------
# Leaving pre-release
# ---------------------------------------------------------------------------


def test_final_drops_the_pre_release_suffix():
    """The common exit from an alpha series: 0.13.0a3 ships as 0.13.0."""
    assert bump("0.13.0a3", "final") == "0.13.0"
    assert bump("0.13.0rc1", "final") == "0.13.0"


def test_final_on_an_already_final_version_is_refused():
    with pytest.raises(ValueError, match="already final"):
        bump("0.13.0", "final")


# ---------------------------------------------------------------------------
# Ordinary bumps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "part", "expected"),
    [
        ("0.12.3", "patch", "0.12.4"),
        ("0.12.3", "minor", "0.13.0"),
        ("0.12.3", "major", "1.0.0"),
        ("1.4.7", "major", "2.0.0"),
    ],
)
def test_regular_bumps_from_a_final_release(current, part, expected):
    assert bump(current, part) == expected


def test_regular_bumps_from_a_pre_release_work_off_the_base_version():
    """These are what git-cliff could no longer compute once a1 was tagged.

    From 0.13.0a2 the base is 0.13.0, so minor gives 0.14.0. To *ship* 0.13.0
    itself use `final` — that is the case this deliberately does not guess at.
    """
    assert bump("0.13.0a2", "patch") == "0.13.1"
    assert bump("0.13.0a2", "minor") == "0.14.0"
    assert bump("0.13.0a2", "major") == "1.0.0"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_an_unknown_step_is_refused():
    with pytest.raises(ValueError, match="unknown"):
        bump("0.13.0", "sideways")


@pytest.mark.parametrize("bad", ["", "1.2", "v1.2.3", "1.2.3.4", "not-a-version"])
def test_an_unparseable_current_version_is_refused(bad):
    with pytest.raises(ValueError, match="cannot parse"):
        bump(bad, "alpha")


def test_every_result_is_a_version_the_next_bump_can_read():
    """A release tool must not paint itself into a corner: whatever it emits
    has to be valid input for the following release."""
    version = "0.12.3"
    steps = ("alpha", "alpha", "beta", "rc", "final", "patch", "minor", "major")
    seen = [version]
    for step in steps:
        version = bump(version, step)
        seen.append(version)

    assert seen == [
        "0.12.3",
        "0.13.0a1",
        "0.13.0a2",
        "0.13.0b1",
        "0.13.0rc1",
        "0.13.0",
        "0.13.1",
        "0.14.0",
        "1.0.0",
    ]
