---
name: conventional-commit
description: Generate git commit messages following Conventional Commits specification (https://www.conventionalcommits.org). Use when creating commits, writing commit messages, or when user mentions conventional commits, git commit, or 커밋 메시지.
---

# Conventional Commit Message Generator

This skill generates git commit messages following the Conventional Commits 1.0.0 specification.

## Commit Message Structure

```
<타입>[적용 범위(선택)]: <설명>

[본문(선택)]

[꼬리말(선택)]
```

## Language Rule

**IMPORTANT: Use Korean for all text content in commit messages.**

- **Type**: English (feat, fix, docs, etc.)
- **Scope**: English (api, admin, feature, etc.)
- **Description**: **Korean** (설명은 한국어로 작성)
- **Body**: **Korean** (본문은 한국어로 작성)
- **Footer**: Korean for descriptions, English for keywords (BREAKING CHANGE, Closes, Fixes)

**Examples:**
```
feat(admin): Slack 알림 기능 추가
fix(api): 요청 경쟁 조건 방지
docs: CLAUDE.md에 커밋 가이드라인 추가
refactor(feature): 투표 로직을 별도 서비스로 분리

feat(auth): JWT 인증 구현

세션 기반 인증을 JWT 기반 인증으로 교체합니다.
API 엔드포인트의 확장성과 보안성이 향상됩니다.

Closes #45
```

## Commit Types

**Required types:**
- `feat`: 새 기능 추가
- `fix`: 버그 수정

**Recommended types:**
- `build`: 빌드 시스템 또는 외부 종속성 변경
- `chore`: 기타 변경사항 (빌드 프로세스, 도구 설정 등)
- `ci`: CI 설정 파일 및 스크립트 변경
- `docs`: 문서만 변경
- `style`: 코드 의미에 영향을 주지 않는 변경 (포맷, 세미콜론 등)
- `refactor`: 버그 수정이나 기능 추가가 아닌 코드 변경
- `perf`: 성능 개선을 위한 코드 변경
- `test`: 테스트 추가 또는 수정

## Scope (적용 범위)

코드베이스의 영역을 나타내는 명사 (선택사항):
- 예: `feat(parser):`, `fix(api):`, `chore(deps):`

## Description (설명)

- 타입/범위 뒤의 콜론과 공백 이후 작성
- 코드 변경사항에 대한 짧은 요약
- **한국어로 작성**
- 명령형 현재 시제 사용 (예: "추가", "변경", "수정")
- 첫 글자 소문자
- 마침표 없음

## Body (본문)

- 설명 다음 한 줄 비우고 작성
- 변경 이유와 이전 동작과의 차이점 설명
- **한국어로 작성**
- 여러 단락 가능
- 명령형 현재 시제 사용

## Footer (꼬리말)

- 본문 다음 한 줄 비우고 작성
- Breaking changes 표시: `BREAKING CHANGE: <설명>`
- Issue 참조: `Closes #123`, `Fixes #456`

## Breaking Changes

두 가지 표현 방법:
1. 타입/범위에 ! 추가: **feat!:** or **feat(scope)!:**
2. 꼬리말에 명시: `BREAKING CHANGE: <설명>`

## Instructions

When generating a commit message, follow these steps:

### Step 1: Analyze Changes

1. Run `git status` to see modified files
2. Run `git diff` to see actual changes (both staged and unstaged)
3. Understand what was changed and why

### Step 2: Determine Commit Type

Based on the changes, select the appropriate type:

- **feat**: New features or functionality added
- **fix**: Bug fixes
- **docs**: Only documentation changes (README, comments, etc.)
- **style**: Formatting, missing semicolons, whitespace, etc.
- **refactor**: Code restructuring without changing behavior
- **perf**: Performance improvements
- **test**: Adding or modifying tests
- **build**: Changes to build system (webpack, npm, etc.)
- **ci**: Changes to CI configuration (Travis, GitHub Actions, etc.)
- **chore**: Maintenance tasks, dependency updates, etc.

### Step 3: Determine Scope (Optional)

Identify the affected area of the codebase:
- Module name: `api`, `parser`, `ui`
- Component name: `auth`, `feature`, `admin`
- Package name: `deps`, `core`

Examples:
- `feat(auth): add OAuth login`
- `fix(parser): handle null values`
- `chore(deps): update mongoose to v7`

### Step 4: Write Description

**IMPORTANT: Write description in Korean (한국어로 작성)**

Create a concise summary (max 72 characters):
- **Use Korean language**
- Use imperative mood: "추가" not "추가했다" or "추가함"
- Lowercase first letter
- No period at the end
- Focus on what changed, not why

Good examples (Korean):
- `사용자 인증 추가`
- `폼 검증 오류 수정`
- `API 엔드포인트 구조 업데이트`

Bad examples:
- `add user authentication` (English - should be Korean)
- `사용자 인증을 추가했습니다.` (past tense, period)
- `수정` (not descriptive enough)
- `버그 수정` (too vague)

### Step 5: Write Body (If Needed)

**IMPORTANT: Write body in Korean (한국어로 작성)**

Add body if:
- Changes are complex and need explanation
- Multiple related changes in one commit
- Context about why the change was made

Body should:
- **Be written in Korean**
- Explain the motivation for the change
- Contrast with previous behavior
- Use imperative mood (명령형)
- Wrap at 72 characters per line

### Step 6: Add Footer (If Needed)

Include footer for:
- Breaking changes: `BREAKING CHANGE: describe the change`
- Issue references: `Closes #123`, `Fixes #456, #789`
- Other metadata: `Reviewed-by:`, `Refs:`

### Step 7: Format the Complete Message

Combine all parts with proper spacing:

```
type(scope): description

Body paragraph explaining the change in more detail.
Can have multiple paragraphs.

BREAKING CHANGE: description of breaking change
Closes #123
```

### Step 8: Review and Validate

Check:
- [ ] Type is appropriate
- [ ] Description is concise and clear
- [ ] Imperative mood used
- [ ] No period at end of description
- [ ] Body provides context (if included)
- [ ] Breaking changes marked (if applicable)
- [ ] Issues referenced (if applicable)

## Examples

**All examples use Korean for descriptions and body content:**

### Simple feature addition
```
feat: 사용자 프로필 페이지 추가
```

### Bug fix with scope
```
fix(api): 요청 처리 시 경쟁 조건 방지
```

### Feature with body
```
feat(auth): JWT 인증 구현

세션 기반 인증을 JWT 기반 인증으로 교체합니다.
API 엔드포인트의 확장성과 보안성을 향상시킵니다.

Closes #45
```

### Breaking change
```
feat(api)!: 응답 형식을 JSON:API 스펙으로 변경

BREAKING CHANGE: 모든 API 응답이 JSON:API 명세를 따릅니다.
클라이언트는 응답 파싱 로직을 업데이트해야 합니다.

Closes #78
```

### Documentation update
```
docs: README에 설치 가이드 업데이트
```

### Refactoring
```
refactor(feature): 투표 로직을 별도 서비스로 추출
```

### Multiple changes
```
feat: 댓글 수정 및 삭제 기능 추가

- updateComment API 엔드포인트 추가
- deleteComment API 엔드포인트 추가
- 새로운 메서드를 feature 서비스에 추가
- 댓글 소유권 검증 추가

Closes #34, #35
```

## Best Practices

1. **One commit per logical change**: Don't mix unrelated changes
2. **Commit often**: Small, focused commits are better than large ones
3. **Write in present tense**: Use imperative mood ("add" not "added")
4. **Be specific**: Avoid vague descriptions like "fix bugs" or "update code"
5. **Reference issues**: Link to issue tracker when applicable
6. **Explain why, not what**: Code shows what changed; commit explains why
7. **Keep subject line short**: Max 72 characters for description
8. **Use body for details**: Explain complex changes in the body

## Common Mistakes to Avoid

- ❌ `Fix bug` → ✅ `fix(auth): 만료된 토큰 올바르게 처리`
- ❌ `Updated files` → ✅ `refactor: 서비스 레이어 구조 재구성`
- ❌ `Added feature.` → ✅ `feat: CSV 내보내기 기능 추가`
- ❌ `fixes` → ✅ `fix: 폴링 서비스의 메모리 누수 해결`
- ❌ `WIP` → ✅ Split into proper commits with clear descriptions
- ❌ `add user authentication` (English) → ✅ `feat: 사용자 인증 추가` (Korean)
- ❌ `버그를 수정했습니다.` (past tense) → ✅ `fix: 버그 수정` (imperative)

## When to Use This Skill

Use this skill when:
- Creating git commits
- User asks to commit changes
- User mentions "커밋", "commit message", or "conventional commits"
- Reviewing or improving existing commit messages
- Setting up git hooks for commit message validation

## Tool Usage

This skill may use:
- **Bash**: Run git commands (`git status`, `git diff`, `git log`)
- **Read**: Read changed files for context
- **Grep**: Search for related changes or patterns

## Output Format

When generating a commit message, provide:

1. **Suggested commit message** in code block
2. **Explanation** of why this format was chosen
3. **Git command** to use for committing

Example output:
```
Here's the suggested commit message:

\`\`\`
feat(admin): 기능 업데이트 시 Slack 알림 추가

#feature-flow 채널과 담당자에게 DM을 보내는
Slack 알림 서비스를 구현합니다.
기능이 생성되거나 업데이트될 때 알림을 전송합니다.

Closes #152
\`\`\`

This uses:
- Type: `feat` (새로운 기능)
- Scope: `admin` (관리자 모듈)
- Description: Korean (한국어 설명)
- Body: Korean explanation (한국어로 구현 세부사항 설명)
- Footer: Issue reference

To commit with this message, use:
\`\`\`bash
git commit -m "feat(admin): 기능 업데이트 시 Slack 알림 추가

#feature-flow 채널과 담당자에게 DM을 보내는
Slack 알림 서비스를 구현합니다.
기능이 생성되거나 업데이트될 때 알림을 전송합니다.

Closes #152"
\`\`\`
```
