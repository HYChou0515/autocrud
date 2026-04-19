# AutoCRUD AI Skills

Pre-built AI skills that teach coding assistants (Claude, GitHub Copilot, etc.) how to work with AutoCRUD. Install a skill and your AI can write AutoCRUD code correctly — models, schemas, routes, frontend customization, and more.

## Available Skills

| Skill | For | Description |
|-------|-----|-------------|
| **autocrud-backend** | Python / FastAPI developers | Model definition, configuration, Schema API, route templates, QB, permissions, events |
| **autocrud-frontend** | React / TypeScript developers | Generator CLI, app structure, resource customization, components, hooks |

## Installation

### Claude Code / Claude Desktop

Copy the skill folder into your project:

```bash
# Backend skill
cp -r autocrud-backend/ <your-project>/.claude/skills/

# Frontend skill
cp -r autocrud-frontend/ <your-project>/.claude/skills/
```

### GitHub Copilot (VS Code)

Copy the skill folder into `.github/skills/`:

```bash
# Backend skill
cp -r autocrud-backend/ <your-project>/.github/skills/

# Frontend skill
cp -r autocrud-frontend/ <your-project>/.github/skills/
```

### Manual (any AI tool)

You can also paste the content of `SKILL.md` directly into your AI tool's system prompt or context window.

## Which skill do I need?

- **Building an API with AutoCRUD?** → Install `autocrud-backend`
- **Building a React admin UI?** → Install `autocrud-frontend`
- **Building both?** → Install both skills

## Compatibility

- **Claude Code** ✅ (`.claude/skills/`)
- **GitHub Copilot** ✅ (`.github/skills/`)
- **Cursor** ✅ (paste into project rules)
- **Any AI with custom instructions** ✅ (paste SKILL.md content)
