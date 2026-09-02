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
| [grill-prfaq](skills/grill-prfaq/) | Pressure-test an idea before writing a Working Backwards PR/FAQ | KO |
| [hwahap](skills/hwahap/) | Align an implementation contract, run isolated Codex workers/reviews, and deliver a draft PR | KO/EN |
| [korean-spell-check](skills/korean-spell-check/) | Korean spelling, spacing, and grammar checker | KO |
| [wrap-up](skills/wrap-up/) | End-of-session checklist for shipping, memory, and self-improvement | EN |

## Installation

Copy the desired skill directories into the skills directory for your tool:

```bash
# Claude Code: install a single skill at user level
cp -r skills/prompt-engineering-patterns ~/.claude/skills/

# Claude Code: install all skills at once
cp -r skills/* ~/.claude/skills/

# Codex: install grill-prfaq at user level
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/grill-prfaq "${CODEX_HOME:-$HOME/.codex}/skills/"

# Codex: install the Hwahap implementation orchestrator
cp -R skills/hwahap "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Start a new session after copying to confirm that the skill is available.

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

Includes reference docs, a prompt template library, curated few-shot examples, and an automated optimization script.

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

### grill-prfaq

Pressure-test an idea through short rounds before writing a Working Backwards PR/FAQ:
- Builds a decision tree from customer, problem, core benefit, evidence, and experience
- Records facts, user decisions, assumptions, and parked questions in one file
- Requires a rubric gate, explicit user confirmation, and validator success before writing the PR
- Includes Codex display metadata, reference material, and a deterministic validator

Validate the skill from the repository root:

```bash
python3 skills/grill-prfaq/scripts/test_validate_prfaq.py
python3 skills/grill-prfaq/scripts/validate_prfaq.py --help
```

### hwahap

Hwahap v2 keeps alignment and implementation in one Codex session:

- inspect twelve decision surfaces and bind only explicit user answers
- render the exact `goal.json` contract before `CONFIRM ALIGN`
- run atomic Luna workers and independent Terra reviews in isolated worktrees
- capture scoped patches, tests, token/cost receipts, and cache evidence through four hooks
- integrate passing units once, run the full suite, and open a draft PR after the Stop gate
- optionally improve the harness only under signal, cadence, benchmark, and hard-budget gates

It requires Bash, `jq`, Git, `gh`, and Codex CLI 0.151 or newer. It uses no
Python runtime, separate Hwahap CLI, session profile, or project agent install.
Copy the skill to the Codex skills directory, then merge
[`hooks/hooks.json`](skills/hwahap/hooks/hooks.json) into `~/.codex/hooks.json`
without removing existing hooks. Restart Codex after hook registration.

Validate from the repository root:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/hwahap
for test in skills/hwahap/tests/*.sh; do bash "$test"; done
```

Target repositories keep ignored run state under `.hwahap/`. Durable summaries
and human answer ledgers live under `~/.codex/hwahap/<repo-id>/`; Hwahap never
marks a PR ready, merges it, or enables auto-merge.

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
