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
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import msgspec

from specstar.descriptor import Manifest
from specstar.lockfile import compute_file_hash, read_manifest
from specstar.skill.llm import LLMClient, LLMError, ProviderConfig, build_client
from specstar.skill.plan import (
    apply_result,
    decide_steps,
    execute_plan,
    render_decision,
    render_python_plan,
    render_spec_plan,
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
        step_input = Step2Input(
            spec_md=spec_path.read_text(encoding="utf-8"),
            previous_generated_py=previous_generated_py,
            package_name=package,
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
    temperature: float,
    stream,
    error_stream,
    client: LLMClient | None,
    confirm: Callable[[str], bool] | None,
    env: dict[str, str] | None,
) -> int:
    if not lock_path.exists():
        print(
            f"error: lock file not found: {lock_path}. Run `specstar init` first.",
            file=error_stream,
        )
        return 2
    try:
        manifest = read_manifest(lock_path)
    except msgspec.DecodeError as exc:
        print(f"error: cannot parse {lock_path}: {exc}", file=error_stream)
        return 2

    # Resolve package + paths from the lock when omitted.
    detected_pkg, detected_gen = _detect_package_and_generated(manifest)
    package = package or detected_pkg
    generated_path = generated_path or detected_gen
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
    if not spec_path.exists():
        print(f"error: spec file not found: {spec_path}", file=error_stream)
        return 2
    if not generated_path.exists():
        print(f"error: generated file not found: {generated_path}", file=error_stream)
        return 2

    # Compute hash-vs-lock booleans.
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

    # Execute (LLM call, no file writes).
    try:
        result = execute_plan(
            decision=decision,
            client=client,
            intent_path=intent_path,
            spec_path=spec_path,
            generated_path=generated_path,
            package_name=package,
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

    # Refresh lock + verify.
    rc = _refresh_lock_and_verify(
        package=package,
        generated_path=generated_path,
        spec_path=spec_path,
        intent_path=intent_path,
        lock_path=lock_path,
        stream=stream,
        error_stream=error_stream,
    )

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
