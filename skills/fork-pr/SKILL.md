---
name: fork-pr
description: Fork된 레포에서 upstream 레포로 PR을 생성할 때 Git 내역과 검증 근거를 정리한다. fork PR, upstream PR 요청에 사용하며 같은 저장소의 일반 PR 요청에는 적용하지 않는다.
allowed-tools: Read, Grep, Glob, Bash
---

# Fork PR Creator

Fork된 레포에서 upstream 레포로 PR을 생성하는 skill입니다.
Git 내역을 분석하여 PR 본문을 자동으로 생성합니다.

---

## 사전 요구사항

### 1. GitHub CLI 설치 및 인증
```bash
# gh CLI가 설치되어 있어야 합니다
gh auth status
```

### 2. Upstream Remote 설정
```bash
# upstream이 설정되어 있어야 합니다
git remote -v

# upstream이 없다면 설정:
# git remote add upstream https://github.com/[원본소유자]/[레포이름].git
```

---

## 워크플로우

### Step 1: Remote 상태 확인

먼저 git remote 설정을 확인합니다:

```bash
git remote -v
```

**확인할 내용:**
- `origin`: fork된 레포 (예: `contributor/project`)
- `upstream`: 원본 레포 (예: `upstream-owner/project`)

upstream이 설정되어 있지 않으면 사용자에게 설정 방법을 안내합니다.

### Step 2: 커밋 내역 분석

PR에 포함될 커밋들을 분석합니다:

```bash
# 현재 브랜치 확인
git branch --show-current

# upstream의 기본 브랜치 확인
git remote show upstream | grep 'HEAD branch'

# PR에 포함될 커밋 목록
git log upstream/[base-branch]..HEAD --oneline

# 변경된 파일 통계
git diff upstream/[base-branch]...HEAD --stat
```

**분석할 내용:**
- Conventional Commits 패턴 분석 (feat, fix, docs, chore 등)
- 변경된 파일 목록과 수정 범위
- 커밋별 주요 변경 사항

### Step 3: PR 본문 생성

커밋 내역을 기반으로 PR 본문을 자동 생성합니다:

- **Summary**: Conventional Commits 타입별로 그룹화하여 요약
- **Changes**: 변경된 주요 파일 목록
- **Test plan**: 기본 검증 체크리스트

### Step 4: 검증 (테스트/빌드)

PR 생성 전에 저장소 지침, CI, 빌드·테스트 설정에서 이번 변경에 필요한 검증 명령을 확인합니다. 특정 패키지 매니저나 빌드를 모든 저장소에 강제하지 않습니다.

PR 작업에 필요한 일반적인 검증은 기존 요청 범위 안에서 실행하며 매번 승인 질문을 하지 않습니다. 외부 비용이나 중요한 부작용으로 추가 권한이 필요한 작업만 별도로 확인합니다.

검증이 실패하면 원인을 조사해 허용된 범위에서 수정하고 관련 검사를 다시 실행합니다. 해결되지 않은 실패나 실행할 수 없는 검사는 PR에 명시하며 통과로 표시하지 않습니다. 초안 PR을 포함한 게시 여부는 사용자 요청과 저장소 규칙을 따릅니다.

### Step 5: PR 생성

검증 결과와 공개할 변경 범위를 확인한 뒤 PR을 생성합니다. 본문은 실제 줄바꿈이 있는 임시 파일에 작성하고 `--body-file`로 전달합니다:

```bash
gh pr create --repo [upstream-owner]/[repo-name] \
  --base [target-branch] \
  --head [fork-owner]:[source-branch] \
  --title "[자동 생성 제목]" \
  --body-file [본문-파일]
```

---

## PR 본문 템플릿

```markdown
## Summary
[커밋 타입별 요약]

### Features
- [feat 커밋 요약]

### Bug Fixes
- [fix 커밋 요약]

### Others
- [기타 커밋 요약]

## Changes
- `[파일경로]`: [변경 설명]
- `[파일경로]`: [변경 설명]

## Test plan
- [ ] 단위 테스트 통과 확인
- [ ] 빌드 성공 확인
- [ ] 기능 동작 테스트

```

사용자나 저장소에서 요구하는 경우에만 작성 도구 표시를 추가합니다.

---

## 사용 예시

### 기본 사용

```
/fork-pr
```

또는 자연어로 요청:

```
fork에서 upstream으로 pr 만들어줘
```

### 특정 브랜치 지정

```
develop 브랜치로 fork pr 생성해줘
```

### 테스트 포함 실행

```
테스트까지 실행하고 fork pr 만들어줘
```

> 저장소와 변경에 필요한 검증을 수행하고, 실행 결과와 미실행 범위를 구분해 보고합니다.

---

## 트러블슈팅

### 1. upstream remote가 없는 경우

```bash
# upstream 추가
git remote add upstream https://github.com/[원본소유자]/[레포이름].git

# upstream fetch
git fetch upstream
```

### 2. gh CLI 인증 오류

```bash
# GitHub 로그인
gh auth login

# 상태 확인
gh auth status
```

### 3. 권한 오류 (403)

Fork된 레포의 소유자가 현재 로그인된 GitHub 계정과 일치하는지 확인합니다.

### 4. 브랜치가 최신이 아닌 경우

```bash
# upstream 최신화
git fetch upstream

# rebase (선택)
git rebase upstream/[base-branch]
```

---

## 명령어 레퍼런스

| 명령어 | 설명 |
|--------|------|
| `git remote -v` | remote 목록 확인 |
| `git log upstream/main..HEAD --oneline` | PR 포함 커밋 확인 |
| `git diff upstream/[base-branch]...HEAD --stat` | PR 변경 파일 통계 |
| `gh pr create --repo owner/repo` | PR 생성 |
| `gh pr view` | 생성된 PR 확인 |
