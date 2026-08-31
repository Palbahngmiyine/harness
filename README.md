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
| [align-goal](skills/align-goal/) | Resolve every implementation-direction choice into a traceable goal specification | KO/EN |
| [hwahap](skills/hwahap/) | Execute an approved PR/FAQ with Sol planning, atomic Luna implementation, and independent Luna/Terra review | KO/EN |
| [korean-spell-check](skills/korean-spell-check/) | Korean spelling, spacing, and grammar checker | KO |
| [wrap-up](skills/wrap-up/) | End-of-session checklist for shipping, memory, and self-improvement | EN |

## Installation

Copy the desired skill directories into the skills directory for your tool:

```bash
# Claude Code: install a single skill at user level
cp -r skills/prompt-engineering-patterns ~/.claude/skills/

# Claude Code: install all skills at once
cp -r skills/* ~/.claude/skills/

# Codex: install align-goal at user level
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/align-goal "${CODEX_HOME:-$HOME/.codex}/skills/"

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

### align-goal

Resolve every implementation-direction choice with the user before implementation planning:
- Inspects repository and runtime evidence before mapping the complete decision surface
- Records facts, exact user-confirmed choices, specification clauses, acceptance checks, units, and open items with stable IDs
- Rejects delegated or vague answers and recursively returns new ambiguity findings to explicit choices
- Requires digest-bound ambiguity and cold-consumer reviews before `aligned` or `handoff-ready`
- Includes deterministic gate tests and target/oracle-separated forward-evaluation cases

Validate the skill from the repository root:

```bash
python3 skills/align-goal/scripts/test_validate_goal_spec.py
python3 skills/align-goal/scripts/test_validate_behavioral_evals.py
python3 skills/align-goal/scripts/validate_goal_spec.py --help
```

### hwahap

Execute a confirmed `status: prfaq` specification through a fixed implementation and review loop:
- Sol Extra High plans and owns structured state in the target workspace's `.hwahap`
- one Luna High implementer writes one mechanically verifiable unit at a time
- a separate Luna Extra High verifier and Terra Extra High scope reviewer inspect the same diff in parallel
- the first failed review gets one bounded recovery; the second returns to Sol for one replan
- final Sol review attempts Ultra and records an Extra High fallback only when Ultra is unavailable or unsupported
- elapsed time and observable run counters are always reported; exact tokens are reported only when surfaced by the runtime

Hwahap requires no login credential, API key, or access token. Here, “exact
tokens” means a numeric model-usage receipt. The approved PR/FAQ is read as an
input path and is not copied into this repository's `docs/prfaq`.

The Sol profile requests Fast, but this platform exposes no verifiable runtime
receipt. Hwahap therefore records local `fast_status: unknown`; it never infers
`enabled` or `disabled` from profile metadata.

Validate the skill and its state contract from the repository root:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/hwahap
python3 skills/hwahap/scripts/test_repository_security.py
python3 skills/hwahap/scripts/test_install_project_agents.py
python3 skills/hwahap/scripts/test_hwahap_dependency_integrity.py
python3 skills/hwahap/scripts/test_hwahap_report.py
python3 skills/hwahap/scripts/test_hwahap_state.py
"$PWD/skills/hwahap/scripts/hwahap" --help
```

Use the absolute `"$PWD/skills/hwahap/scripts/hwahap"` launcher. It isolates the
state program; copied, linked, replaced, or direct `hwahap_state.py` execution
is outside the boundary. The launcher, adjacent state script, `/bin/sh`, kernel,
selected Python, and standard library remain trust roots; same-UID races and a
native signed bootstrap are outside this scope.

Completed runs use a v4 receipt: canonical `report-data.json` and validated
`report.html` are single-link files with separate digests. The visible ledger
has no history cap. Recovery is best-effort, not crash/power-loss durable; v3
and earlier receipts are rejected without silent migration.

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
