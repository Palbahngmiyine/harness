---
name: align-goal
description: 사용자와 구현 방향의 모든 material choice를 개별 확정하고, 다른 LLM이 추가 선택 없이 실행 계획을 세울 수 있는 추적 가능한 goal spec을 작성한다. 모든 확정은 사용자가 직접 실행한 response log에 결속한다. 아이디어 탐색, 저장소 조사, 구현 전 합의, 모호성 감사에 사용한다.
metadata:
  short-description: 사용자와 구현 방향을 확정하는 정밀 기획
---

# align-goal

현재 목표와 repository snapshot에서 구현 결과를 바꿀 수 있는 모든 선택을 찾아 사용자와 확정한다. 결과는 `docs/goals/YYYY-MM-DD-slug.md` 한 파일과 그 옆의 `docs/goals/YYYY-MM-DD-slug.responses.jsonl` response log이며, 정확히 하나의 `json align-goal-contract` fenced block만 규범적 source of truth다. 요약·PRD·PRFAQ는 이 블록에서 만든 비규범적 projection이다. 기획 상태는 코드 수정·배포·외부 쓰기 권한이 아니다.

목표는 무음 선택 0이다: 사용자가 인지하지 못한 채 남는 선택이 없어야 한다. LLM의 insight는 계속 흐른다 — 모든 C에 recommendation과 evidence를 제공하고, 답에서 파생되는 choice를 재귀적으로 계속 질문한다. 다만 어떤 recommendation도, 어떤 대화 속 문장도 확정이 아니다. 확정은 아래 response log의 문법 항목만이다.

## Response log와 확정 문법

사용자는 `scripts/record_response.py`를 **직접** 실행해 답을 기록한다. Claude Code에서는 `!python3 <skill>/scripts/record_response.py docs/goals/<slug>.responses.jsonl "C1=ALT2"`, Codex에서는 같은 명령을 터미널에서 실행한다. 기획 LLM은 이 스크립트를 사용자 대신 실행하지 않는다. 로그는 seq 연속·prev hash 연결·시각 비감소·NFC 정규화된 hash chain이며, validator가 모든 확정을 이 로그에 대조한다. 이는 위조 불가가 아니라 위조 흔적 보장이다: 조작은 세션 transcript에 도구 호출로 남는다.

확정 문법은 `C<n>=<답>`이고 `;`로 여러 답을 한 항목에 담을 수 있다. `<답>`은 alternative ID(`ALT2`), alternative value 전문, `OTHER: <새 값>`(사용자 제시 대안, `origin: user`로 기록), `SAME`(reask 재확정, 직전 명시답과 같은 alternative만 재확정 — 값을 바꾸려면 SAME이 아니라 supersession) 중 하나다. `ok`, `네`, `추천대로`, `알아서 해줘`, `you choose` 같은 자유 문장은 문법에 걸려 확정될 수 없다 — 같은 C ID로 다시 묻는다. 위임을 걸러내는 것은 별도 denylist가 아니라 이 문법과 alternative 일치이므로, `follow the repo convention` 같은 **구체적** 답은 `OTHER:`로 정상 기록된다. 최종 확인은 `CONFIRM ALIGNMENT: <문장>`과 `CONFIRM HANDOFF: <문장>` 항목으로만 기록한다.

## 판정과 루프

모든 판단을 `material choice`, `forced consequence`, `local coding`으로 분류한다. 둘 이상의 구현이 동작·오류·상태·순서·기본값·이름·경로·포맷·schema·계약·경계·dependency·data lifecycle·compatibility·security·performance·operation·acceptance를 다르게 만들면 material choice다. 확인된 C 또는 `immutable_for_scope` F가 결과를 하나로 강제할 때만 forced consequence로 기록한다. repository 관례와 LLM recommendation은 강제가 아니다. local-coding 조건은 [decision-surfaces.md](references/decision-surfaces.md)에 따른다.

repository/runtime을 먼저 조사해 F를 만들고, 12개 surface를 판정한 뒤 dependency 없는 C를 라운드당 최대 8개씩 질문한다. 답에서 파생되는 choice를 라운드 수 제한 없이 재귀 탐색하고 S/A/U로 컴파일한다. 미완성 슬롯은 예약 sentinel(`{{TODO …}}`류 double-brace, `[TODO]`류 bracket)로만 표시하며 handoff 전에 전부 채워야 한다 — 이 lint는 backtick 안이든 밖이든 sentinel을 차단하고, `{{username}}`·`Result<T,E>` 같은 일반 표기는 통과시킨다. 4라운드마다 checkpoint를 남긴다(그 외 round의 checkpoint는 null). confirmed C를 뒤집는 값 변경은 반드시 supersession으로 기록하고, supersede된 C에 의존하던 confirmed C는 그 이후 seq로 재확정하거나 `reask`로 되돌린다. reask는 `SAME` 재확정으로만 닫힌다.

ambiguity auditor와 cold consumer는 이전 reasoning 없이 canonical contract와 repository context만 받아 검사한다. 암묵적 assumption 탐지는 단어 정규식이 아니라 auditor의 `implicit_assumptions`·`new_material_choices` finding이 담당한다. finding은 C 또는 O로 되돌린다. 구현 중 새 material choice가 나오면 구현 LLM은 선택하거나 가정하지 않고 구현을 중단해 align-goal로 돌아간다.

세션 시작 시 [contract-schema.md](references/contract-schema.md)와 [decision-surfaces.md](references/decision-surfaces.md)를 완전히 읽는다. review 실행 전 [review-protocol.md](references/review-protocol.md)를 읽는다. 독립 forward evaluation은 [behavioral-evals.md](references/behavioral-evals.md)를 따른다.

## Gate

`aligned`는 모든 C가 log-bound confirmed 또는 valid superseded이고(reask 0), open O가 0이며, 12 surface가 current confirmed C 또는 immutable F로 닫히고, repository 재관찰에 drift가 없고, fresh ambiguity PASS와 log-bound alignment summary confirmation이 있을 때만 가능하다. `target: implementation`의 `handoff_ready`는 여기에 S provenance, S-A-U 추적, U DAG, open item·placeholder 부재, fresh cold PASS, cold 이후 log-bound handoff confirmation을 요구한다. `target: decision`은 handoff_status가 반드시 `not_requested`다.

`alignment_status`와 `handoff_status`는 LLM이 주장하는 값이 아니라 validator가 계산하는 값이다. substance가 충족되면 validator가 `next_action: stamp_status`를 반환하고 `--stamp`가 frontmatter에 기록한다. 계산보다 앞선 주장은 오류다. gate 실행 시 validator는 `git_head`/`file` repository context를 실제 저장소에서 재관찰해 drift를 차단한다(`command`/`runtime`은 재관찰 불가로 보고만 한다). `--no-observe`는 cross-machine 리뷰 전용이며 gate를 약화시킨다는 사실이 출력에 남는다.

`validate_goal_spec.py PATH [--require structural|aligned|handoff-ready] [--json] [--repo-root PATH] [--no-observe] [--stamp]`의 exit code는 `0=pass`, `1=validation failure`, `2=I/O or usage failure`다. `record_response.py LOG [TEXT…|--verify]`도 같은 규약이다. validator는 발화의 의미를 증명하지 못한다 — 보장하는 것은 모든 확정이 사용자가 직접 남긴 로그 항목과 문법에 결속된다는 것뿐이다.
