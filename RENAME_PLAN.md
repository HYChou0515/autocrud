# Rename Plan: autocrud → specstar

**Current**: autocrud 0.8.5 on PyPI
**Targets** (3 releases):

| # | Version | Package | Content | Sequence |
|---|---|---|---|---|
| 1 | `autocrud==0.10.0` | autocrud | fix-274 refactor + breaking changes; **NO rename yet** | Ship first (independent) |
| 2 | `specstar==0.10.0` | specstar (new) | autocrud 0.9.0 codebase + rename | After PR1+PR2 merge |
| 3 | `autocrud==0.10.0` | autocrud (shim) | Thin redirect → specstar 0.10.0 + DeprecationWarning | Same day as #2, minutes after |

**Why split**: rename and breaking-changes are decoupled. autocrud 0.9.0 ships breaking changes under the existing name (normal upgrade path). specstar 0.10.0 ships **only** the rename (zero behavior diff vs autocrud 0.9.0). The shim can therefore safely redirect — autocrud 0.10.0 users get rename warnings without surprise behavior changes.

**Locked**: 2026-05-01

This file is temporary. Remove after release ships.

---

## Locked Decisions

### Naming
| Layer | Old | New |
|---|---|---|
| Python class | `AutoCRUD` | `SpecStar` |
| Python package | `autocrud` | `specstar` |
| Global instance (convention) | `crud` | `spec` |
| GitHub repo | `HYChou0515/autocrud` | `HYChou0515/specstar` |
| npm package | `autocrud-web-generator` | `specstar-web-generator` |
| Skill dirs | `autocrud-{vocab,fullstack,core}` | `specstar-{vocab,fullstack,core}` |

### Scope ("CRUD" handling = B-medium)
- "CRUD" as a technical term (Create/Read/Update/Delete) **stays** everywhere it's used as such ("CRUD route templates", "CRUD operations", "CRUD lifecycle").
- Only "AutoCRUD" as a brand string gets replaced with "SpecStar".
- Internal directory `autocrud/crud/` → `specstar/crud/` (submodule name kept).
- In-scope: Python core, tests, docs, repo, skills, frontend (`web/generator`, `web/app`).
- Out-of-scope (follow-up PR): Docker images, CI secret names, external integrations.

### Strategy: separate breaking-changes release, then rename
- `autocrud==0.10.0`: ships fix-274 refactor + breaking changes. Same package name. Normal `pip upgrade` path. No rename yet.
- `specstar==0.10.0`: clean new package; codebase = autocrud 0.9.0 + rename. Zero behavior diff vs autocrud 0.9.0.
- `autocrud==0.10.0`: thin shim; depends on `specstar==0.10.0`; redirects all `autocrud.*` imports to `specstar.*` with `DeprecationWarning`. Final autocrud release.
- Future: only `specstar` gets new versions. `autocrud` 0.10.0 stays frozen as the migration shim.
- specstar internal code carries **no** "formerly autocrud" notice (kept clean).

### PR strategy: two-phase
- **PR1 (mechanical rename)** — branch `rename/specstar-mechanical`. File moves + sed identifiers + package metadata. CI must be green.
- **PR2 (brand content)** — branch `rename/specstar-content`. README, docs, MIGRATION.md, CHANGELOG, descriptions, logos.
- PR2 merges after PR1.

### Release sequencing

**Phase A — autocrud 0.9.0 (now, before rename work)**
1. Merge fix-274 → master.
2. Tag `v0.9.0` on master.
3. Build + publish `autocrud==0.10.0` to PyPI.
4. GitHub Release v0.9.0 with breaking-change notes (no rename mention beyond a "rename coming next" pointer).

**Phase B — specstar 0.10.0 + autocrud 0.10.0 (post PR1+PR2 merge)**
1. PR1 (mechanical rename) merges into master.
2. PR2 (brand content) merges into master.
3. Tag `v0.10.0` on master.
4. Build + publish `specstar==0.10.0` to PyPI **first**.
5. Verify clean install from fresh venv.
6. Build + publish `autocrud==0.10.0` (shim).
7. Verify shim install + deprecation warning fires.
8. Cut GitHub Release v0.10.0 with notes pointing to MIGRATION.md.
9. `gh repo rename specstar` (auto-redirects).
10. Update repo description, homepage, topics in Settings.

### Migration support
- `MIGRATION.md` at repo root: sed commands + API mapping table + FAQ.
- `docs/migration/from-autocrud.md`: same content under MkDocs nav.

### Documentation
- Custom domain deferred. GitHub Pages auto-republishes at `hychou0515.github.io/specstar/` after repo rename.
- README header gets `branding/logo-text.svg`.
- Docs favicon: `branding/logo-mark.svg`.

### Defaults applied to remaining minor decisions
- **Migration guide depth**: lean — sed commands + API mapping table + short FAQ. No recipe rewrites.
- **CHANGELOG**: `CHANGELOG.md` at repo root + GitHub Release notes link to it.
- **Release order**: same day; specstar first, autocrud-shim within the hour.
- **Skill content**: PR1 only does mechanical sed on examples. SKILL.md prose stays unless explicitly broken by rename. PR2 revisits if needed.

---

## PR1 — Mechanical Rename

**Branch**: `rename/specstar-mechanical`

### File-system changes
- `git mv autocrud specstar`
- Create `autocrud-shim/` subdirectory at repo root.
- Rename skill dirs: `git mv .claude/skills/autocrud-{vocab,fullstack,core} .claude/skills/specstar-{vocab,fullstack,core}`.

### `autocrud-shim/` contents
```
autocrud-shim/
├── pyproject.toml           # name=autocrud, version=0.9.0, deps=[specstar==0.10.0]
├── README.md                # one paragraph: "Deprecated. See https://github.com/.../specstar"
└── autocrud/
    └── __init__.py          # MetaPathFinder + DeprecationWarning + re-export
```

`autocrud/__init__.py` strategy (meta_path finder so all submodule imports work without listing each one):

```python
import importlib.abc
import importlib.util
import sys
import warnings

_PREFIX = "autocrud"
_TARGET = "specstar"
_MIGRATION_URL = "https://github.com/HYChou0515/specstar/blob/master/MIGRATION.md"
_warned = set()

class _AutocrudRedirector(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != _PREFIX and not name.startswith(_PREFIX + "."):
            return None
        new_name = _TARGET + name[len(_PREFIX):]
        if name not in _warned:
            warnings.warn(
                f"`{name}` is deprecated. Use `{new_name}` instead. See {_MIGRATION_URL}",
                DeprecationWarning,
                stacklevel=2,
            )
            _warned.add(name)
        return importlib.util.find_spec(new_name)

sys.meta_path.insert(0, _AutocrudRedirector())

# Make `from autocrud import <symbol>` work too (top-level re-export)
from specstar import *  # noqa: F401, F403, E402
```

### sed/replace patterns
1. `from autocrud` → `from specstar`
2. `import autocrud` → `import specstar`
3. `class AutoCRUD` → `class SpecStar`
4. `AutoCRUD(` → `SpecStar(` (constructor calls)
5. `AutoCRUD ` (trailing space, in type hints / docstrings) → `SpecStar ` (audit case-by-case)
6. `"autocrud"` string literals (package name in metadata) → `"specstar"`
7. Variable name `crud` (where it's the framework instance) → `spec` (audit; do not blanket sed — `crud` may appear in unrelated contexts like `CrudRouteTemplate`)
8. `autocrud-web-generator` (npm) → `specstar-web-generator`
9. `autocrud-vocab` / `autocrud-fullstack` / `autocrud-core` (skill names + frontmatter) → `specstar-*`
10. Repo URLs `github.com/HYChou0515/autocrud` → `github.com/HYChou0515/specstar`

### Files touched (rough scope)
- `pyproject.toml` (root)
- `specstar/**/*.py` (all)
- `tests/**/*.py` (all)
- `web/generator/package.json` + `web/generator/src/**`
- `web/app/**` (API client imports)
- `.claude/skills/specstar-{vocab,fullstack,core}/SKILL.md` (frontmatter `name:` + code blocks)
- `.claude/skills/*/SKILL.md` (any code blocks importing autocrud)
- `Makefile` (any references)
- `docs/**` (deferred to PR2 for prose; PR1 only updates code blocks if they break)

### Validation
- `make test` passes
- `uv build` (root) → `dist/specstar-0.10.0.{whl,tar.gz}`
- `cd autocrud-shim && uv build` → `dist/autocrud-0.10.0.{whl,tar.gz}`
- Fresh venv:
  - `pip install dist/specstar-0.10.0-*.whl` → `python -c "from specstar import spec; print(spec)"` works, no warning
  - `pip install dist/autocrud-0.10.0-*.whl` (pulls specstar) → `python -c "from autocrud import spec; print(spec)"` shows DeprecationWarning, works

---

## PR2 — Brand Content Rewrite

**Branch**: `rename/specstar-content` (off updated master after PR1 merge)

### Content updates
- `README.md`: header rewrite + embed logo (use `<picture>` tag for light/dark)
- `CLAUDE.md`: project overview rewrite (keep skill table; update intro)
- `pyproject.toml`: `description` field
- `docs/index.md` (or landing page equivalent): "What is SpecStar"
- `docs/migration/from-autocrud.md`: full migration guide
- `MIGRATION.md` (repo root): mirror of above for git-level discoverability
- `CHANGELOG.md` (new file): v0.9.0 entry
- `branding/`: already in place; reference from README

### MIGRATION.md template
```markdown
# Migrating from autocrud to specstar

autocrud has been renamed to specstar starting from v0.9.0. The behavior is identical;
only names changed.

## TL;DR

```bash
pip uninstall autocrud
pip install specstar
sed -i 's/from autocrud/from specstar/g; s/import autocrud/import specstar/g; s/AutoCRUD/SpecStar/g' $(git ls-files '*.py')
# Audit: rename your instance variable from `crud` to `spec` if you used the recommended convention.
```

## Compatibility shim

If you cannot migrate immediately, keep using `pip install autocrud==0.10.0`. It depends on
specstar internally and emits `DeprecationWarning` on each import path. No new versions of
`autocrud` will be released after 0.9.0.

## API mapping

| autocrud | specstar |
|---|---|
| `from autocrud import AutoCRUD` | `from specstar import SpecStar` |
| `from autocrud import crud` | `from specstar import spec` |
| `crud = AutoCRUD()` | `spec = SpecStar()` |
| `crud.add_model(...)` | `spec.add_model(...)` |
| All other public symbols | identical names |

## FAQ

**Q: Why the rename?**
A: ...

**Q: Will autocrud get bug fixes?**
A: No. autocrud 0.9.0 is the final release of that name. New work happens in specstar.

**Q: Can I install both?**
A: Don't. autocrud-0.10.0 and specstar both expose top-level packages; install one.
```

### Validation
- `make docs` builds clean
- `make serve` shows new branding
- README renders on GitHub with logo

---

## Rollback Plan

- PR1 fails CI → don't merge; iterate on branch.
- specstar 0.9.0 has bug → yank from PyPI, ship 0.9.1 (autocrud-shim must update its `specstar==0.10.0` pin to `>=0.9.0,<0.10` if multiple patches expected).
- autocrud-shim 0.9.0 has bug → ship autocrud 0.9.1.
- Repo rename → reversible via `gh repo rename autocrud` (24h re-use window).

---

## Open Items (post-rename)

- Custom domain `specstar.dev` (deferred)
- Docker / CI secrets rename (separate follow-up)
- Existing GitHub issues mentioning "AutoCRUD" — leave as historical record
