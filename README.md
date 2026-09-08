# Agent Skills Collection

A collection of Agent Skills for developers using Claude Code and Codex.

This repository contains skill instructions and reference documents. Executable source code and helper scripts are maintained outside this repository and must not be added here.

Browse the [skills directory](skills/) to choose a skill. Each skill's `SKILL.md` contains its usage instructions and requirements.

## Installation

From a local checkout, copy the desired skill into your tool's skills directory. For example, with Claude Code:

```bash
mkdir -p ~/.claude/skills
cp -r skills/prompt-engineering-patterns ~/.claude/skills/
```

Skill locations:

- **Claude Code, user:** `~/.claude/skills/`
- **Claude Code, project:** `.claude/skills/`
- **Codex, user:** `${CODEX_HOME:-$HOME/.codex}/skills/`

Start a new session after copying to confirm that the skill is available.

[Hwahap](https://github.com/Palbahngmiyine/hwahap) is maintained and installed separately.

## License

MIT
