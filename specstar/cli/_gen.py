"""``specstar gen`` — spec-driven authoring command.

Two execution modes:

- **Dry-run** (default): print system + user prompts for one step. Useful
  for piping into your own LLM tooling, or for debugging the prompt
  content.
- **``--call``**: invoke an LLM end-to-end via litellm — STEP 1 + STEP 2
  + apply files + refresh lock + verify. Honors the edit-respect rules
  from :mod:`specstar.skill.plan` (only runs the steps the hash decision
  table says to run; never overwrites user-edited downstream files).

Provider configuration (``--call`` mode):

- Resolution order: CLI flag > env var > built-in default
- Default provider: ``anthropic`` with ``claude-sonnet-4-6``
- Self-host: ``--provider openai-compatible --base-url http://localhost:11434/v1 --model llama3.1``
- API key from ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` env (or ``--api-key``)

The Claude Code skill is the canonical "interactive" surface; this CLI is
for users without Claude Code (any provider, including self-hosted).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import msgspec

from specstar.descriptor import Manifest
from specstar.lockfile import compute_file_hash, read_manifest
from specstar.skill.features import (
    load_features_from_pyproject,
    resolve_features,
)
from specstar.skill.llm import LLMClient, LLMError, ProviderConfig, build_client
from specstar.skill.plan import (
    apply_python_plan,
    apply_result,
    decide_steps,
    execute_plan,
    render_decision,
    render_python_plan,
    render_spec_plan,
    run_step2,
)
from specstar.skill.prompts import (
    STEP1_SYSTEM_PROMPT,
    STEP2_SYSTEM_PROMPT,
    Step1Input,
    Step2Input,
    build_step1_messages,
    build_step2_messages,
)

# ---------------------------------------------------------------------------
# Argparse + dispatch
# ---------------------------------------------------------------------------


def add_gen_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``gen`` subcommand on the top-level parser."""
    p = subparsers.add_parser(
        "gen",
        help="Spec-driven authoring (dry-run prints prompts; --call invokes the LLM).",
        description=(
            "Two modes: default dry-run prints LLM prompts to stdout; "
            "--call invokes an LLM (any provider via litellm), applies the "
            "result, and refreshes spec.lock.json."
        ),
    )
    p.add_argument(
        "--step",
        type=int,
        choices=[1, 2],
        default=1,
        help="Dry-run only: which step's prompt to print (1 or 2). Ignored under --call.",
    )
    p.add_argument(
        "--package",
        default=None,
        help="Python package name. Auto-detected from spec.lock.json when omitted.",
    )
    p.add_argument(
        "--intent",
        default="intent.md",
        help="Path to intent.md (default: ./intent.md).",
    )
    p.add_argument(
        "--spec",
        default="spec.md",
        help="Path to spec.md (default: ./spec.md).",
    )
    p.add_argument(
        "--generated",
        default=None,
        help="Path to _generated.py. Auto-detected when omitted.",
    )
    p.add_argument(
        "--lock",
        default="spec.lock.json",
        help="Path to spec.lock.json (default: ./spec.lock.json).",
    )
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Dry-run output format. ``text`` for humans; ``json`` for the Anthropic API shape.",
    )
    # --- --call mode flags ---
    p.add_argument(
        "--call",
        action="store_true",
        help="Invoke an LLM end-to-end (default: dry-run only). Requires API key in env.",
    )
    p.add_argument(
        "--yes", action="store_true", help="--call: skip confirmation prompt."
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="--call: re-run STEP 1 + STEP 2 unconditionally (bypass cache + edit-respect).",
    )
    p.add_argument(
        "--from-spec",
        action="store_true",
        help="--call: skip STEP 1, run STEP 2 from current spec.md (mutually exclusive with --force).",
    )
    p.add_argument(
        "--provider", default=None, help="LLM provider (default: anthropic)."
    )
    p.add_argument(
        "--model", default=None, help="Model name (default depends on provider)."
    )
    p.add_argument(
        "--base-url", default=None, help="Override base URL (for self-host)."
    )
    p.add_argument(
        "--api-key",
        default=None,
        help="Override API key (default: read from {PROVIDER}_API_KEY env).",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=8000,
        help="Per-call token cap (default 8000).",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Schema-validation retries (default 3).",
    )
    p.add_argument(
        "--feature",
        action="append",
        default=[],
        dest="cli_enable_features",
        metavar="NAME",
        help=(
            "Enable a codegen feature for this run on top of "
            "[tool.specstar].features in pyproject.toml. Repeatable. "
            "E.g. --feature storage --feature mq."
        ),
    )
    p.add_argument(
        "--no-feature",
        action="append",
        default=[],
        dest="cli_disable_features",
        metavar="NAME",
        help=(
            "Disable a codegen feature for this run. Wins over --feature "
            "when both reference the same name. Repeatable."
        ),
    )
    p.add_argument(
        "--feedback-retries",
        type=int,
        default=2,
        help=(
            "After STEP 2 lands a syntactically valid file that the lock "
            "step refuses to import (TypeError, etc.), capture the error "
            "and re-call STEP 2 up to N times feeding the captured stderr "
            "back into the user prompt for self-correction. 0 disables "
            "(rollback on first failure). Default: 2."
        ),
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default 0).",
    )
    p.set_defaults(func=gen_cmd)


def gen_cmd(args: argparse.Namespace) -> int:
    return run_gen(
        call=args.call,
        step=args.step,
        package=args.package,
        intent_path=Path(args.intent),
        spec_path=Path(args.spec),
        generated_path=Path(args.generated) if args.generated else None,
        lock_path=Path(args.lock),
        output_format=args.format,
        yes=args.yes,
        force=args.force,
        from_spec=args.from_spec,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        max_retries=args.max_retries,
        feedback_retries=args.feedback_retries,
        cli_enable_features=args.cli_enable_features,
        cli_disable_features=args.cli_disable_features,
        temperature=args.temperature,
        stream=sys.stdout,
        error_stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


def run_gen(
    *,
    call: bool = False,
    step: int = 1,
    package: str | None = None,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path | None = None,
    lock_path: Path,
    output_format: str = "text",
    yes: bool = False,
    force: bool = False,
    from_spec: bool = False,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 8000,
    max_retries: int = 3,
    feedback_retries: int = 2,
    cli_enable_features: list[str] | None = None,
    cli_disable_features: list[str] | None = None,
    temperature: float = 0.0,
    stream,
    error_stream,
    client: LLMClient | None = None,
    confirm: Callable[[str], bool] | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Entry point for both dry-run and --call modes.

    The ``client`` and ``confirm`` parameters exist for tests to inject
    mock implementations without touching real APIs or stdin.
    """
    if call:
        return _run_call(
            package=package,
            intent_path=intent_path,
            spec_path=spec_path,
            generated_path=generated_path,
            lock_path=lock_path,
            yes=yes,
            force=force,
            from_spec=from_spec,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            max_retries=max_retries,
            feedback_retries=feedback_retries,
            cli_enable_features=cli_enable_features or [],
            cli_disable_features=cli_disable_features or [],
            temperature=temperature,
            stream=stream,
            error_stream=error_stream,
            client=client,
            confirm=confirm,
            env=env,
        )
    return _run_dry(
        step=step,
        package=package,
        intent_path=intent_path,
        spec_path=spec_path,
        generated_path=generated_path,
        lock_path=lock_path,
        output_format=output_format,
        stream=stream,
        error_stream=error_stream,
    )


# ---------------------------------------------------------------------------
# Dry-run mode (prints prompts)
# ---------------------------------------------------------------------------


def _run_dry(
    *,
    step: int,
    package: str | None,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path | None,
    lock_path: Path,
    output_format: str,
    stream,
    error_stream,
) -> int:
    if step not in (1, 2):
        print(f"error: unknown step {step}", file=error_stream)
        return 2

    manifest, package, generated_path, rc = _resolve_paths(
        package=package,
        generated_path=generated_path,
        lock_path=lock_path,
        error_stream=error_stream,
    )
    if rc != 0:
        return rc
    assert package is not None and generated_path is not None

    if step == 1:
        if not intent_path.exists():
            print(f"error: intent file not found: {intent_path}", file=error_stream)
            return 2
        previous_spec_md = (
            spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        )
        step_input = Step1Input(
            intent_md=intent_path.read_text(encoding="utf-8"),
            previous_spec_md=previous_spec_md,
            package_name=package,
        )
        system_prompt = STEP1_SYSTEM_PROMPT
        messages = build_step1_messages(step_input)
        step_label = "STEP 1 (intent.md → spec.md)"
    else:
        if not spec_path.exists():
            print(f"error: spec file not found: {spec_path}", file=error_stream)
            return 2
        previous_generated_py = (
            generated_path.read_text(encoding="utf-8")
            if generated_path.exists()
            else ""
        )
        # Resolve features so the dry-run prompt matches what --call
        # would actually send to the LLM. Reads pyproject.toml in cwd.
        enabled_features = resolve_features(
            pyproject_value=load_features_from_pyproject(Path("pyproject.toml")),
        )
        step_input = Step2Input(
            spec_md=spec_path.read_text(encoding="utf-8"),
            previous_generated_py=previous_generated_py,
            package_name=package,
            enabled_features=enabled_features,
        )
        system_prompt = STEP2_SYSTEM_PROMPT
        messages = build_step2_messages(step_input)
        step_label = "STEP 2 (spec.md → _generated.py)"

    if output_format == "json":
        payload = {"step": step, "system": system_prompt, "messages": messages}
        print(json.dumps(payload, indent=2), file=stream)
    else:
        print(f"=== {step_label} ===", file=stream)
        print(file=stream)
        print("=== system ===", file=stream)
        print(system_prompt, file=stream)
        print(file=stream)
        print("=== user ===", file=stream)
        print(messages[0]["content"], file=stream)
        print(file=stream)
        print(
            "(specstar gen dry-run. Pipe these prompts into your LLM client, "
            "or pass --call to invoke the LLM directly.)",
            file=stream,
        )
    return 0


# ---------------------------------------------------------------------------
# --call mode (full orchestration)
# ---------------------------------------------------------------------------


def _run_call(
    *,
    package: str | None,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path | None,
    lock_path: Path,
    yes: bool,
    force: bool,
    from_spec: bool,
    provider: str | None,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    max_tokens: int,
    max_retries: int,
    feedback_retries: int,
    cli_enable_features: list[str],
    cli_disable_features: list[str],
    temperature: float,
    stream,
    error_stream,
    client: LLMClient | None,
    confirm: Callable[[str], bool] | None,
    env: dict[str, str] | None,
) -> int:
    manifest: Manifest | None
    if lock_path.exists():
        try:
            manifest = read_manifest(lock_path)
        except msgspec.DecodeError as exc:
            print(f"error: cannot parse {lock_path}: {exc}", file=error_stream)
            return 2
    else:
        # Missing lock = "rebuild from scratch" signal. Mirror the
        # missing-spec / missing-_generated semantics: no recorded
        # baseline → regenerate everything from intent.md (force).
        # `--from-spec` still takes precedence for users who want to
        # skip STEP 1 and treat their hand-edited spec.md as authority.
        print(
            f"note: {lock_path} is missing — rebuilding baseline from intent.md.",
            file=stream,
        )
        manifest = None
        if not from_spec:
            force = True

    # Resolve package + paths from the lock when omitted.
    if manifest is not None:
        detected_pkg, detected_gen = _detect_package_and_generated(manifest)
        package = package or detected_pkg
        generated_path = generated_path or detected_gen
    if package is None and generated_path is None:
        # No manifest to consult — scan cwd for a single `<pkg>/_generated.py`
        # so that `rm spec.lock.json && specstar gen --call` Just Works
        # without requiring the user to remember --package.
        scanned_pkg, scanned_gen = _scan_package_from_cwd()
        package = scanned_pkg
        generated_path = scanned_gen
    if generated_path is None and package is not None:
        # Fall back to the conventional layout.
        generated_path = Path(package) / "_generated.py"
    if package is None or generated_path is None:
        print(
            "error: could not determine package or _generated.py path; "
            "pass --package and --generated explicitly",
            file=error_stream,
        )
        return 2

    if not intent_path.exists():
        print(f"error: intent file not found: {intent_path}", file=error_stream)
        return 2

    # Missing or empty spec.md / _generated.py is a "recreate from upstream"
    # signal, not an error. The user has explicitly removed the downstream
    # artifact and expects regeneration.
    spec_recreate = (
        not spec_path.exists() or spec_path.read_text(encoding="utf-8").strip() == ""
    )
    if spec_recreate:
        print(
            "note: spec.md is missing or empty — forcing STEP 1 to recreate "
            "from intent.md.",
            file=stream,
        )
        # Ensure the file exists so downstream code (hashing, apply) has a
        # path to read/write. Empty content is fine; STEP 1 will replace it.
        if not spec_path.exists():
            spec_path.write_text("", encoding="utf-8")
        force = True

    gen_recreate = (
        not generated_path.exists()
        or generated_path.read_text(encoding="utf-8").strip() == ""
    )
    if gen_recreate:
        print(
            f"note: {generated_path} is missing or empty — STEP 2 will recreate it.",
            file=stream,
        )
        if not generated_path.exists():
            generated_path.parent.mkdir(parents=True, exist_ok=True)
            generated_path.write_text("", encoding="utf-8")
        # If only py is missing, run STEP 2 from current spec; if both are
        # missing, force already covers STEP 1 + STEP 2.
        if not spec_recreate:
            from_spec = True

    # Compute hash-vs-lock booleans. With no manifest (lock was missing),
    # treat all three as "changed" — there is no recorded baseline to
    # diff against. The decision is then dominated by force/from_spec.
    if manifest is None:
        intent_changed = spec_changed = gen_changed = True
    else:
        intent_changed, spec_changed, gen_changed = _hashes_vs_lock(
            manifest,
            intent_path=intent_path,
            spec_path=spec_path,
            generated_path=generated_path,
        )

    try:
        decision = decide_steps(
            intent_changed=intent_changed,
            spec_changed=spec_changed,
            gen_changed=gen_changed,
            force=force,
            from_spec=from_spec,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    print(render_decision(decision), file=stream)

    # If neither step is needed (cases 1/4/6/8), just refresh the lock.
    if not decision.run_step1 and not decision.run_step2:
        return _refresh_lock_and_verify(
            package=package,
            generated_path=generated_path,
            spec_path=spec_path,
            intent_path=intent_path,
            lock_path=lock_path,
            stream=stream,
            error_stream=error_stream,
        )

    # Build the LLM client (unless one was injected for tests).
    if client is None:
        try:
            config = _resolve_provider_config(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=max_tokens,
                max_retries=max_retries,
                temperature=temperature,
                env=env if env is not None else os.environ,
            )
            client = build_client(config)
        except (ValueError, LLMError) as exc:
            print(f"error: {exc}", file=error_stream)
            return 2

    # Resolve feature toggles. pyproject.toml in cwd is conventional;
    # CLI flags override.
    enabled_features = resolve_features(
        pyproject_value=load_features_from_pyproject(Path("pyproject.toml")),
        cli_enable=cli_enable_features,
        cli_disable=cli_disable_features,
    )

    # Execute (LLM call, no file writes).
    try:
        result = execute_plan(
            decision=decision,
            client=client,
            intent_path=intent_path,
            spec_path=spec_path,
            generated_path=generated_path,
            package_name=package,
            enabled_features=enabled_features,
        )
    except LLMError as exc:
        print(f"error: LLM call failed: {exc}", file=error_stream)
        return 1

    # Pre-write AST validation. The LLM output may contain forbidden
    # patterns (`import os`, `Try` blocks, dunder access). Catching
    # them BEFORE writing means: (a) no broken file ever lands on disk,
    # (b) no subprocess gets to execute module-top malicious code, and
    # (c) the user sees a clean AST-attributed error instead of a late
    # subprocess failure plus rollback.
    if result.python_plan is not None:
        from specstar.validator import DeclarativeASTValidator

        validator = DeclarativeASTValidator()
        try:
            ast_errors = validator.validate(
                result.python_plan.generated_py_after,
                filename=str(generated_path),
            )
        except SyntaxError as exc:
            print(
                f"error: LLM produced invalid Python (syntax error at line "
                f"{exc.lineno}): {exc.msg}",
                file=error_stream,
            )
            print("aborted before write — no files modified.", file=error_stream)
            return 1
        if ast_errors:
            print(
                "\nerror: LLM output rejected by AST validator (no files written):",
                file=error_stream,
            )
            for e in ast_errors[:10]:
                print(
                    f"  line {e.line}:{e.col} [{e.kind}] {e.message}",
                    file=error_stream,
                )
            if len(ast_errors) > 10:
                print(
                    f"  ... and {len(ast_errors) - 10} more",
                    file=error_stream,
                )
            print(
                "\nrefine intent.md (perhaps the LLM hallucinated; "
                "see SpecStar API reference in the system prompt) "
                "and re-run.",
                file=error_stream,
            )
            return 1

    # Render plans for the user.
    if result.spec_plan is not None:
        print(render_spec_plan(result.spec_plan), file=stream)
    if result.python_plan is not None:
        print(render_python_plan(result.python_plan), file=stream)

    # Confirmation gate.
    if not yes:
        confirm_fn = confirm or _stdin_confirm
        if not confirm_fn("\nApply these changes? [y/N] "):
            print("aborted — no files written.", file=stream)
            return 1

    # Capture before-state so we can roll back if the post-write
    # lock/verify pipeline fails (LLM produced syntactically valid but
    # semantically broken code, or AST validator rejects).
    backup_spec = spec_path.read_bytes() if spec_path.exists() else None
    backup_gen = generated_path.read_bytes() if generated_path.exists() else None
    backup_lock = lock_path.read_bytes() if lock_path.exists() else None

    # Apply.
    written = apply_result(result, spec_path=spec_path, generated_path=generated_path)
    if written:
        print(f"\nwrote {len(written)} file(s):", file=stream)
        for w in written:
            print(f"  {w}", file=stream)

    # Refresh lock + verify, with feedback-retry loop on failure.
    rc, captured_err = _try_lock_with_feedback_retry(
        client=client,
        package=package,
        intent_path=intent_path,
        spec_path=spec_path,
        generated_path=generated_path,
        lock_path=lock_path,
        feedback_retries=feedback_retries,
        enabled_features=enabled_features,
        stream=stream,
        error_stream=error_stream,
    )
    # Always surface whatever the final attempt printed to its captured
    # stderr, so the user sees the actual failure mode (or nothing on
    # success).
    if captured_err:
        error_stream.write(captured_err)

    if rc != 0:
        _rollback(
            spec_path=spec_path,
            generated_path=generated_path,
            lock_path=lock_path,
            backup_spec=backup_spec,
            backup_gen=backup_gen,
            backup_lock=backup_lock,
            stream=stream,
        )
    return rc


def _try_lock_with_feedback_retry(
    *,
    client: LLMClient,
    package: str,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path,
    lock_path: Path,
    feedback_retries: int,
    enabled_features: tuple[str, ...] = (),
    stream,
    error_stream,
) -> tuple[int, str]:
    """Run lock+verify; on failure, optionally re-call STEP 2 with the
    captured stderr embedded in the prompt, until success or budget
    exhausted.

    Returns ``(rc, last_captured_stderr)``. The caller is responsible for
    rolling back if ``rc != 0``. Each retry only re-runs STEP 2 (spec.md
    is left alone — STEP 1 already produced a structurally valid spec).
    """
    attempts_remaining = feedback_retries
    while True:
        captured = io.StringIO()
        rc = _refresh_lock_and_verify(
            package=package,
            generated_path=generated_path,
            spec_path=spec_path,
            intent_path=intent_path,
            lock_path=lock_path,
            stream=stream,
            error_stream=captured,
        )
        if rc == 0:
            return rc, captured.getvalue()
        captured_text = captured.getvalue()
        if attempts_remaining <= 0:
            return rc, captured_text

        # Self-correction round: re-call STEP 2 with the captured stderr.
        attempts_remaining -= 1
        attempt_idx = feedback_retries - attempts_remaining
        print(
            f"\nfeedback retry {attempt_idx}/{feedback_retries}: "
            "re-running STEP 2 with captured error...",
            file=stream,
        )
        # Surface the captured stderr to the user too — they should see
        # what the LLM is being asked to fix.
        error_stream.write(captured_text)

        try:
            retry_plan = run_step2(
                client,
                spec_md=spec_path.read_text(encoding="utf-8"),
                previous_generated_py=generated_path.read_text(encoding="utf-8"),
                package_name=package,
                error_feedback=captured_text,
                enabled_features=enabled_features,
            )
        except LLMError as exc:
            print(
                f"error during feedback retry: {exc}",
                file=error_stream,
            )
            return 1, captured_text

        # AST-validate the retry output before writing — same defense as
        # the first attempt.
        from specstar.validator import DeclarativeASTValidator

        validator = DeclarativeASTValidator()
        try:
            ast_errors = validator.validate(
                retry_plan.generated_py_after,
                filename=str(generated_path),
            )
        except SyntaxError as exc:
            print(
                f"error: retry produced invalid Python (syntax error at "
                f"line {exc.lineno}): {exc.msg}",
                file=error_stream,
            )
            return 1, captured_text
        if ast_errors:
            print(
                "error: retry rejected by AST validator:",
                file=error_stream,
            )
            for e in ast_errors[:10]:
                print(
                    f"  line {e.line}:{e.col} [{e.kind}] {e.message}",
                    file=error_stream,
                )
            return 1, captured_text

        apply_python_plan(retry_plan, generated_path)
        print(render_python_plan(retry_plan), file=stream)
        # Loop back to lock+verify.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rollback(
    *,
    spec_path: Path,
    generated_path: Path,
    lock_path: Path,
    backup_spec: bytes | None,
    backup_gen: bytes | None,
    backup_lock: bytes | None,
    stream,
) -> None:
    """Restore the working tree to its pre-apply state on pipeline failure.

    Called when ``apply_result`` writes succeed but the subsequent
    ``lock`` or ``verify`` step rejects the LLM output (TypeError on
    import, AST violation, hash mismatch). Without rollback the user is
    left holding broken files and a stale lock.
    """
    restored: list[str] = []
    for path, backup in (
        (spec_path, backup_spec),
        (generated_path, backup_gen),
        (lock_path, backup_lock),
    ):
        if backup is None:
            if path.exists():
                path.unlink()
                restored.append(str(path) + " (deleted)")
            continue
        # Only rewrite if content actually differs to avoid touching mtime.
        if not path.exists() or path.read_bytes() != backup:
            path.write_bytes(backup)
            restored.append(str(path))
    if restored:
        print(
            "\nrolled back working tree to pre-apply state:",
            file=stream,
        )
        for r in restored:
            print(f"  {r}", file=stream)
        print(
            "(refine intent.md or re-run; nothing was permanently changed.)",
            file=stream,
        )


def _stdin_confirm(prompt: str) -> bool:
    """Default confirm: read y/yes from stdin (case-insensitive)."""
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def _resolve_provider_config(
    *,
    provider: str | None,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    max_tokens: int,
    max_retries: int,
    temperature: float,
    env,
) -> ProviderConfig:
    """CLI flag > env var > built-in default."""
    final_provider = provider or env.get("SPECSTAR_PROVIDER") or "anthropic"
    default_models = {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "openai-compatible": None,
    }
    api_key_envs = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openai-compatible": "OPENAI_API_KEY",
    }
    if final_provider not in default_models:
        raise ValueError(
            f"unknown provider {final_provider!r}; supported: anthropic, openai, openai-compatible"
        )
    final_model = model or env.get("SPECSTAR_MODEL") or default_models[final_provider]
    if final_model is None:
        raise ValueError(f"--model is required for provider {final_provider!r}")
    final_api_key = api_key or env.get(api_key_envs[final_provider])
    if final_api_key is None and final_provider != "openai-compatible":
        raise ValueError(
            f"no API key found; set {api_key_envs[final_provider]} or pass --api-key"
        )
    return ProviderConfig(
        provider=final_provider,
        model=final_model,
        base_url=base_url,
        api_key=final_api_key,
        max_tokens=max_tokens,
        max_retries=max_retries,
        temperature=temperature,
    )


def _detect_package_and_generated(
    manifest: Manifest,
) -> tuple[str | None, Path | None]:
    for relpath in manifest.sources:
        if relpath.endswith("_generated.py"):
            p = Path(relpath)
            return p.parent.name, p
    return None, None


def _scan_package_from_cwd() -> tuple[str | None, Path | None]:
    """Find a `<pkg>/_generated.py` under the cwd when no lock exists.

    Used by the missing-lock recovery path. If exactly one such file is
    present, return its package and path. Zero or multiple matches → no
    inference; the caller falls through to "pass --package explicitly".
    Hidden / dunder dirs are ignored to avoid stumbling over `.venv`,
    `__pycache__`, etc.
    """
    matches: list[Path] = []
    for sub in Path(".").iterdir():
        if not sub.is_dir():
            continue
        if sub.name.startswith(".") or sub.name.startswith("_"):
            continue
        candidate = sub / "_generated.py"
        if candidate.is_file():
            matches.append(candidate)
    if len(matches) == 1:
        only = matches[0]
        return only.parent.name, only
    return None, None


def _hashes_vs_lock(
    manifest: Manifest,
    *,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path,
) -> tuple[bool, bool, bool]:
    """Return ``(intent_changed, spec_changed, gen_changed)``."""
    intent_sha, _ = compute_file_hash(intent_path)
    spec_sha, _ = compute_file_hash(spec_path)
    gen_sha, _ = compute_file_hash(generated_path)

    intent_recorded = manifest.sources.get("intent.md")
    spec_recorded = manifest.sources.get("spec.md")
    gen_key = f"{generated_path.parent.name}/{generated_path.name}"
    gen_recorded = manifest.sources.get(gen_key)

    return (
        intent_recorded is None or intent_sha != intent_recorded.sha256,
        spec_recorded is None or spec_sha != spec_recorded.sha256,
        gen_recorded is None or gen_sha != gen_recorded.sha256,
    )


def _refresh_lock_and_verify(
    *,
    package: str,
    generated_path: Path,
    spec_path: Path,
    intent_path: Path,
    lock_path: Path,
    stream,
    error_stream,
) -> int:
    """Re-run `specstar lock` then `specstar verify`. Returns the higher rc."""
    from specstar.cli._lock import run_lock
    from specstar.cli._verify import run_verify

    lock_rc = run_lock(
        module_name=f"{package}._generated",
        spec_path=spec_path,
        generated_path=generated_path,
        out_path=lock_path,
        intent_path=intent_path,
        stream=stream,
        error_stream=error_stream,
    )
    if lock_rc != 0:
        return lock_rc
    verify_rc = run_verify(lock_path, stream=stream, error_stream=error_stream)
    return verify_rc


def _resolve_paths(
    *,
    package: str | None,
    generated_path: Path | None,
    lock_path: Path,
    error_stream,
) -> tuple[Manifest | None, str | None, Path | None, int]:
    """Helper for dry-run path detection."""
    manifest = None
    if lock_path.exists():
        try:
            manifest = read_manifest(lock_path)
        except msgspec.DecodeError as exc:
            print(f"error: cannot parse {lock_path}: {exc}", file=error_stream)
            return None, None, None, 2

    if package is None or generated_path is None:
        if manifest is not None:
            for relpath in manifest.sources:
                if relpath.endswith("_generated.py"):
                    detected = Path(relpath)
                    if generated_path is None:
                        generated_path = detected
                    if package is None:
                        package = detected.parent.name
                    break

    if package is None:
        print(
            "error: --package is required when no existing lock is present",
            file=error_stream,
        )
        return manifest, None, None, 2
    if generated_path is None:
        generated_path = Path(package) / "_generated.py"

    return manifest, package, generated_path, 0
