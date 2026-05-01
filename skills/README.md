# SpecStar AI Skills

Pre-built AI skills that teach coding assistants (Claude, GitHub Copilot, etc.) how to work with SpecStar. Install a skill and your AI can write SpecStar code correctly — models, schemas, routes, frontend customization, and more.

## Available Skills

| Skill | For | Description |
|-------|-----|-------------|
| **specstar-backend** | Python / FastAPI developers | Model definition, configuration, Schema API, route templates, QB, permissions, events |
| **specstar-frontend** | React / TypeScript developers | Generator CLI, app structure, resource customization, components, hooks |

## Installation

### Claude Code / Claude Desktop

Copy the skill folder into your project:

```bash
# Backend skill
cp -r specstar-backend/ <your-project>/.claude/skills/

# Frontend skill
cp -r specstar-frontend/ <your-project>/.claude/skills/
```

### GitHub Copilot (VS Code)

Copy the skill folder into `.github/skills/`:

```bash
# Backend skill
cp -r specstar-backend/ <your-project>/.github/skills/

# Frontend skill
cp -r specstar-frontend/ <your-project>/.github/skills/
```

### Manual (any AI tool)

You can also paste the content of `SKILL.md` directly into your AI tool's system prompt or context window.

## Which skill do I need?

- **Building an API with SpecStar?** → Install `specstar-backend`
- **Building a React admin UI?** → Install `specstar-frontend`
- **Building both?** → Install both skills

## Compatibility

- **Claude Code** ✅ (`.claude/skills/`)
- **GitHub Copilot** ✅ (`.github/skills/`)
- **Cursor** ✅ (paste into project rules)
- **Any AI with custom instructions** ✅ (paste SKILL.md content)
