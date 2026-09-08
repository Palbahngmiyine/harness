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
| [plan-intent](skills/plan-intent/) | 의도·동작·중요한 선택·검증 기준을 연결하는 Markdown 전용 기획 | KO |
| [hwahap](https://github.com/Palbahngmiyine/hwahap) | Confirm a plan with you, then build, test, review, and open a draft PR autonomously | KO/EN |
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

Hwahap is now maintained and installed separately from
[Palbahngmiyine/hwahap](https://github.com/Palbahngmiyine/hwahap). It is not included in `skills/*`.

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

Hwahap has moved to [Palbahngmiyine/hwahap](https://github.com/Palbahngmiyine/hwahap).
Its Codex plugin, Rust MCP runtime, CI, and versioned releases are maintained there.
See the [installation guide](https://github.com/Palbahngmiyine/hwahap#설치) and
[releases](https://github.com/Palbahngmiyine/hwahap/releases).

### plan-intent

사용자의 원래 의도와 실제 경험을 구체적인 동작·검증 기준에 연결합니다.
`$plan-intent 이 아이디어를 내 의도에 맞게 기획해줘`로 사용합니다.
기존 합의를 보존하고 중요한 이해 차이만 질문하며, 구현자가 이어받을 기획서를 만듭니다.
스킬은 Markdown 3개로 구성되며 스크립트나 실행기 의존성이 없습니다.
OpenAI GPT-6 Astra 가이드와 일반 설계 원칙은 스킬의 references에 기록했습니다.

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
