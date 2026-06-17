"""``specstar backfill-set-index`` CLI — wiring / error paths (no DB needed)."""

from __future__ import annotations

import argparse
import io


def test_backfill_set_cli_rejects_bad_spec_arg():
    from specstar.cli._backfill import backfill_set_cmd

    args = argparse.Namespace(spec="no_colon", model="foo", field="keys")
    err = io.StringIO()
    code = backfill_set_cmd(args, stream=io.StringIO(), error_stream=err)
    assert code == 2
    assert "module:attr" in err.getvalue()
