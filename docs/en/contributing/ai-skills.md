# AI skills guide for contributors

This page is for **humans who want to create or maintain AI skills for AutoCRUD**.

It is **not** itself a triggerable skill file. If you want to build a real skill, start from the skill folders under `skills/` and then install or mirror them into the AI tool's expected location.

## Where to start

The canonical examples for this repository live under `skills/`:

- `skills/autocrud-backend/`
- `skills/autocrud-frontend/`
- `skills/README.md`

If you want to understand what a good AutoCRUD skill looks like, read those folders first.

## What goes where

### Human-authored skill source

Put reusable skill content under `skills/<skill-name>/`.

A typical skill package looks like this:

```text
skills/
  <skill-name>/
    SKILL.md
    references/
    scripts/
```

Use this location when you are:

- designing a new skill,
- expanding an existing skill,
- collecting references and examples,
- reviewing the skill with other humans.

### Tool-specific installation location

If you want GitHub Copilot in this repo to use the skill directly, place the active copy under `.github/skills/`.

In short:

- `skills/` = human-maintained source and examples
- `.github/skills/` = repo-local skill installation for Copilot-style tools

## How to create a new AI skill

### 1. Choose one responsibility

A skill should own one clear job, for example:

- backend resource lifecycle work,
- frontend generator changes,
- documentation maintenance.

Avoid putting unrelated responsibilities into a single giant skill.

### 2. Create a `SKILL.md`

Start with a minimal structure like this:

```markdown
---
name: example-skill
description: Explain what this skill does and when it should trigger.
---

# Example Skill

## Use this when
narrow list of situations where the skill should be loaded.

## Workflow
step-by-step guidance the model should follow.

## Verification
the checks or commands the model should run before claiming success.
```

The `description` field matters a lot. It should clearly say both:

- what the skill helps with, and
- when the assistant should use it.

### 3. Add references only when needed

If the skill needs lots of background material, put it under `references/` instead of making `SKILL.md` huge.

### 4. Reuse real project conventions

A good AutoCRUD skill should reflect the real repo workflow, such as:

- use `uv run` for Python commands;
- follow TDD for bug fixes;
- add targeted tests for new behavior;
- update docs and docstrings when public behavior changes;
- respect the generated versus customizable boundary in the web app.

### 5. Test the skill on real prompts

Before considering the skill finished, try it against a few realistic prompts and check whether it:

- triggers at the right time,
- follows the correct project conventions,
- suggests or runs the right verification steps.

## Existing AutoCRUD skill map

### Backend examples

- `skills/autocrud-backend/SKILL.md`

### Frontend examples

- `skills/autocrud-frontend/SKILL.md`

### Repo-installed skills for Copilot

The repo-local installed skills live under `.github/skills/`.

These are the versions the assistant can discover directly while working inside this repository.

## Recommended workflow for contributors

1. read the examples under `skills/`;
2. draft or update the new skill there first;
3. keep the trigger description concrete;
4. verify the skill with realistic prompts;
5. if needed, mirror the finalized version into `.github/skills/` for repo use.

## Need help writing one?

If you want the assistant to help design a skill, ask it to create or refine a skill for a specific workflow and point it to the examples in `skills/`.

That usually works best when you provide:

- the type of task,
- when the skill should trigger,
- the expected workflow,
- the checks the assistant must perform before saying the work is done.
