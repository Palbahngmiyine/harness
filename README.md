# Agent Skills Collection

A curated collection of Agent Skills for developers using Claude Code and Codex. Each skill provides a focused workflow that a compatible agent can discover and use.

## Skills

| Skill | Description | Language |
|-------|-------------|----------|
| [prompt-engineering-patterns](skills/prompt-engineering-patterns/) | Advanced prompt engineering techniques for maximizing LLM performance | EN |
| [claude-code-analyzer](skills/claude-code-analyzer/) | Analyze Claude Code usage patterns and optimize workflows | EN |
| [skill-writer](skills/skill-writer/) | Guide for creating well-structured Agent Skills | EN |
| [conventional-commit](skills/conventional-commit/) | Conventional Commits spec with Korean commit messages | KO/EN |
| [fork-pr](skills/fork-pr/) | Fork-to-upstream PR automation workflow | KO |
| [hwahap](skills/hwahap/) | Codex **plugin**: confirm a plan with you, then build, test, review, and open a draft PR autonomously | KO/EN |
| [korean-spell-check](skills/korean-spell-check/) | Korean spelling, spacing, and grammar checker | KO |
| [wrap-up](skills/wrap-up/) | End-of-session checklist for shipping, memory, and self-improvement | EN |

## Installation

Copy the desired skill directories into the skills directory for your tool:

```bash
# Claude Code: install a single skill at user level
cp -r skills/prompt-engineering-patterns ~/.claude/skills/

# Claude Code: install all skills at once
cp -r skills/* ~/.claude/skills/
```

Start a new session after copying to confirm that the skill is available.

`hwahap` is the exception: it is a **Codex plugin**, not a copyable skill directory, because it
ships an MCP server that a bare skill cannot register. Install it with `codex plugin add` — see
[skills/hwahap/README.md](skills/hwahap/README.md).

### Skill Locations

- **User-level** (`~/.claude/skills/`): Available across all projects
- **Project-level** (`.claude/skills/`): Available only in that project (great for team sharing via git)
- **Codex user-level** (`${CODEX_HOME:-$HOME/.codex}/skills/`): Available to Codex sessions

## Skill Details

### prompt-engineering-patterns

Master advanced prompt engineering techniques including:
- Few-shot learning with dynamic example selection
- Chain-of-thought and tree-of-thought prompting
- Prompt optimization and A/B testing workflows
- Template systems with variable interpolation
- System prompt design patterns

Includes reference docs, a prompt template library, and curated few-shot examples.

### claude-code-analyzer

Complete Claude Code workflow optimization:
- Usage pattern analysis from conversation history
- GitHub community resource discovery (agents, skills, commands)
- Project structure detection and CLAUDE.md generation
- Auto-allow tool recommendations

Includes bash scripts for analysis (`analyze.sh`, `analyze-claude-md.sh`, `github-discovery.sh`, `fetch-features.sh`).

### skill-writer

A meta-skill for creating new Agent Skills:
- Step-by-step skill authoring guide
- SKILL.md frontmatter and naming conventions
- Validation checklist and debugging tips
- Common patterns (read-only, script-based, multi-file)

### conventional-commit

Generate git commit messages following the [Conventional Commits 1.0.0](https://www.conventionalcommits.org) specification:
- Korean descriptions and body content
- All standard commit types (feat, fix, docs, refactor, etc.)
- Breaking change and footer handling
- Step-by-step commit workflow

### fork-pr

Automate PR creation from a forked repo to upstream:
- Git remote validation and upstream detection
- Commit history analysis with Conventional Commits grouping
- Auto-generated PR body with summary, changes, and test plan
- Build verification before PR creation

### hwahap

Hwahap v3 is a Codex plugin that runs one implementation request end to end:

- it investigates the repository itself and asks only about preferences and trade-offs
- every material decision arrives with alternatives, a recommendation, evidence, and impact — and
  the recommendation is never an implicit default
- `CONFIRM PLAN <challenge>` freezes a digest-bound plan; after that a normal cycle asks nothing
- units are implemented, tested, and independently reviewed one at a time, each accepted unit
  becoming a checkpoint commit on a single run branch
- success is judged from repository state and exit status, never from what an agent claims
- it finishes with a draft pull request, and marks it ready only on an explicit `SHIP <challenge>`

One Rust binary is both a local STDIO MCP server (exactly three tools) and an ACP client driving a
pinned `codex-acp` adapter, one session at a time. There is no daemon, no database, no HTTP
transport, and no lifecycle hook.

Requirements: Rust 1.90 or newer, an authenticated `gh`, and `codex-acp` on `PATH`.
Installation, the architecture, the fixed model/effort policy, and the design decisions are in
[`skills/hwahap/README.md`](skills/hwahap/README.md).

Validate from the repository root:

```bash
cargo test --manifest-path skills/hwahap/runtime/Cargo.toml --all-targets
skills/hwahap/tests/gates.sh
```

CI runs fmt, clippy, and the test suite on ubuntu, macOS, and Windows, plus the static simplicity
gates that pin the design to numbers: three MCP tools, a 40-line skill, three model/effort
profiles, and zero SQLite, HTTP-server, daemon, hook, or nested-exec dependencies. The `verify`
job gates everything and is the required status check on `main`.

Target repositories keep ignored run state under `.hwahap/`. Hwahap never marks a PR ready without
an explicit confirmation, and never merges or enables auto-merge.

### korean-spell-check

Korean language spell checker:
- Spelling rules (되/돼, 웬/왠, 로써/로서, etc.)
- Spacing rules (의존명사, 보조용언, 조사)
- Grammar checks (주어-서술어 호응, 높임법, 피동/사동)
- File and inline text support
- Includes a comprehensive common-mistakes reference

### wrap-up

End-of-session workflow in four phases:
1. **Ship It**: Commit uncommitted changes, verify file placement
2. **Remember It**: Save learnings to appropriate memory locations
3. **Review & Apply**: Self-improvement findings and actions
4. **Publish It**: Draft publishable content from the session

## Skill Structure

Each skill follows this directory convention:

```
skill-name/
├── SKILL.md           # Required: Skill definition with YAML frontmatter
├── agents/            # Optional: Agent-specific display metadata
├── references/        # Optional: Reference documentation
├── scripts/           # Optional: Executable helper scripts
└── assets/            # Optional: Templates, examples, data files
```

The `SKILL.md` file requires YAML frontmatter with at minimum:

```yaml
---
name: skill-name
description: What the skill does and when to use it
---
```

## Requirements

- A compatible Agent Skills client such as [Claude Code](https://docs.claude.com/en/docs/claude-code) or Codex
- Some skills require additional tools:
  - `jq`: Required by claude-code-analyzer scripts
  - `gh`: Optional for GitHub discovery features

## License

MIT
