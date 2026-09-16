# Agent Skills Collection

A collection of Agent Skills for developers using Claude Code and Codex.

This repository contains skill instructions and reference documents. Executable source code and helper scripts are maintained outside this repository and must not be added here. Short read-only lookup examples quoted inside reference documents (for example, a single `jq` or `sqlite3` command) are documentation of a data format, not helper scripts.

Browse the [skills directory](skills/) to choose a skill. Each skill's `SKILL.md` contains its usage instructions and requirements.

For reusable project instructions, see [general](general/README.md): a common contract with C, Rust, and Go profiles and migration guidance for the former Go-only files.

For cross-project Codex and Claude Code working rules, see the [English source](global/AGENTS.md), [Korean translation](global/AGENTS.ko.md), and [standalone Claude Code rules](global/CLAUDE.md). These defaults prioritize usable results within half a working day to one working day where feasible, including long-running goals, and require a short guide for checking each delivered result. They complement project-specific instructions without reducing the requested scope or mandatory verification.

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

### Global working rules

Editing this repository does not update installed user instructions. Preserve existing custom rules and merge the desired changes when installing.

- **Codex:** Use `global/AGENTS.md` as `${CODEX_HOME:-$HOME/.codex}/AGENTS.md`, or use the synchronized Korean translation as that file's contents. Check for an active `AGENTS.override.md`. In a fresh session, ask Codex to identify its loaded instruction sources and summarize the delivery and verification rules. See [OpenAI's instruction discovery and setup verification](https://learn.chatgpt.com/docs/agent-configuration/agents-md#verify-your-setup).
- **Claude Code:** Install the contents of `global/CLAUDE.md` in `~/.claude/CLAUDE.md`, preserving existing custom rules. This single file contains the full policy and needs no companion `AGENTS.md` or import. In a fresh session, use `/context` to inspect Memory files and ask Claude to summarize the delivery and verification rules. See [Claude Code's instruction locations](https://code.claude.com/docs/en/memory#choose-where-to-put-claudemd-files) and [loading behavior](https://code.claude.com/docs/en/memory#how-claudemd-files-load).

When maintaining these documents, keep the shared obligations in `global/AGENTS.md`, `global/AGENTS.ko.md`, and `global/CLAUDE.md` synchronized in meaning. Keep client-specific discovery rules distinct and preserve the standalone Claude file's complete policy.

In either client, check that a long goal retains its full completion criteria while delivering a usable result early, and that the response includes an actual artifact location, reproducible steps, expected results, and honest verification limits. File presence or a correct summary alone does not demonstrate reliable behavior on real work; validate that on the next suitable task.

## License

MIT
