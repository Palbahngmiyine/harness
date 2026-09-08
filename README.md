# Agent Skills Collection

A curated collection of Agent Skills for developers using Claude Code and Codex. Each skill provides a focused workflow that a compatible agent can discover and use.

This repository contains skill instructions and reference documents. Executable source code and helper scripts are maintained outside this repository and must not be added here.

The Skills workflow checks skill entry points and remains required for pull requests. CodeQL analysis is disabled in the repository settings because this collection does not contain executable source code.

## Skills

| Skill | Description | Language |
|-------|-------------|----------|
| [prompt-engineering-patterns](skills/prompt-engineering-patterns/) | 대상 모델·실패 사례·평가 근거에 맞춘 Markdown 프롬프트 개선 | KO |
| [skill-writer](skills/skill-writer/) | Guide for creating well-structured Agent Skills | EN |
| [conventional-commit](skills/conventional-commit/) | Conventional Commits spec with Korean commit messages | KO/EN |
| [fork-pr](skills/fork-pr/) | Fork-to-upstream PR automation workflow | KO |
| [plan-intent](skills/plan-intent/) | 의도·동작·중요한 선택·검증 기준을 연결하는 Markdown 전용 기획 | KO |
| [evening-socratic-journal](skills/evening-socratic-journal/) | Codex 활동과 일상 문답으로 함께 쓰는 Markdown 전용 저녁 일기 | KO |
| [hwahap](https://github.com/Palbahngmiyine/hwahap) | Confirm a plan with you, then build, test, review, and open a draft PR autonomously | KO/EN |
| [korean-spell-check](skills/korean-spell-check/) | Korean spelling, spacing, and grammar checker | KO |

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

대상 모델과 실제 실패 사례를 바탕으로 목표·출력 형식·작업 범위를 보존하는 프롬프트를 작성합니다.
GPT-6 Astra의 공식 지침과 API 호환성을 확인하고, 문서 대조·모의 문답·실제 모델 평가를 구분합니다.
Markdown 지침과 참고 문서로 구성되며, 실행하지 않은 실험의 정확도·토큰·비용 개선을 주장하지 않습니다.

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
- Repository-specific validation before PR creation

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

### evening-socratic-journal

오늘의 Codex 대화와 Codex 밖 활동을 소크라테스식 질문으로 돌아보고 저녁 일기를 함께 씁니다.
`$evening-socratic-journal 오늘 하루를 돌아보며 일기 같이 쓰자`로 사용합니다.
단점을 단정하지 않고 답변과 반대 사례를 살피며, 사용자가 고른 작은 실천을 일기에 연결합니다.
Markdown 3개로 구성되며 기록 읽기 도구가 없어도 문답으로 진행합니다. 예약 실행은 별도 요청 사항입니다.

### korean-spell-check

Korean language spell checker:
- Spelling rules (되/돼, 웬/왠, 로써/로서, etc.)
- Spacing rules (의존명사, 보조용언, 조사)
- Grammar checks (주어-서술어 호응, 높임법, 피동/사동)
- File and inline text support
- Includes a comprehensive common-mistakes reference

## Skill Structure

Each skill follows this directory convention:

```
skill-name/
├── SKILL.md           # Required: Skill definition with YAML frontmatter
├── agents/            # Optional: Agent-specific display metadata
├── references/        # Optional: Reference documentation
└── assets/            # Optional: Document templates and examples
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
  - `gh`: Required by the `fork-pr` workflow

## License

MIT
