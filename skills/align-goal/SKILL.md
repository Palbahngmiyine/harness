---
name: align-goal
description: 사용자와 구현 방향의 모든 material choice를 개별 확정하고, 다른 LLM이 추가 선택 없이 실행 계획을 세울 수 있는 추적 가능한 goal spec을 작성한다. 아이디어 탐색, 저장소 조사, 구현 전 합의, 모호성 감사에 사용한다.
metadata:
  short-description: 사용자와 구현 방향을 확정하는 정밀 기획
---

# align-goal

현재 목표와 repository snapshot에서 구현 결과를 바꿀 수 있는 모든 선택을 찾아 사용자와 확정한다. 결과는 `docs/goals/YYYY-MM-DD-slug.md` 한 파일이며, 정확히 하나의 `json align-goal-contract` fenced block만 규범적 source of truth다. 요약·PRD·PRFAQ는 이 블록에서 만든 비규범적 projection이다. 기존 `grill-prfaq`를 완전히 대체하며 alias나 별도 산출물 경로를 만들지 않는다. 기획 상태는 코드 수정·배포·외부 쓰기 권한이 아니다.

## 판정과 루프

모든 판단을 `material choice`, `forced consequence`, `local coding`으로 분류한다. 둘 이상의 구현이 동작·오류·상태·순서·기본값·이름·경로·포맷·schema·계약·경계·dependency·data lifecycle·compatibility·security·performance·operation·acceptance를 다르게 만들면 material choice다. 확인된 C 또는 `immutable_for_scope` F가 결과를 하나로 강제할 때만 forced consequence로 기록한다. repository 관례와 LLM recommendation은 강제가 아니다. observable behavior와 named/system surface를 보존하고 하나의 private unit에만 남는 local-coding 조건은 [decision-surfaces.md](references/decision-surfaces.md)에 따른다.

repository/runtime을 먼저 조사해 F를 만들고, 12개 surface를 판정한 뒤 dependency 없는 C를 라운드당 최대 8개씩 질문한다. 사용자의 답은 ID별 exact response와 value로 기록한다. `looks good`, `you choose`, `best judgment`, 추상적인 `follow repo`, `알아서 해줘`는 확정이 아니다. 답에서 파생되는 choice를 라운드 수 제한 없이 재귀 탐색하고 S/A/U로 컴파일한다. assumption·placeholder는 허용하지 않는다. 4라운드마다 checkpoint를 남긴다.

ambiguity auditor와 cold consumer는 이전 reasoning 없이 canonical contract와 repository context만 받아 검사한다. finding은 C 또는 O로 되돌린다. 구현 중 새 material choice가 나오면 구현 LLM은 선택하거나 가정하지 않고 구현을 중단해 align-goal로 돌아간다. validator의 `next_action`은 저장하지 않고 [review-protocol.md](references/review-protocol.md)의 precedence로 계산하며, 매번 허용 vocabulary 중 하나만 반환한다.

세션 시작 시 [contract-schema.md](references/contract-schema.md)와 [decision-surfaces.md](references/decision-surfaces.md)를 완전히 읽는다. review를 실행하기 전 [review-protocol.md](references/review-protocol.md)를 읽는다. 독립 forward evaluation을 실행하거나 수정할 때 [behavioral-evals.md](references/behavioral-evals.md)의 target/oracle 분리 protocol과 structured cases를 사용한다.

## Gate

`aligned`는 모든 C가 user-bound confirmed 또는 valid superseded이고, open O가 0이며, 12 surface가 current confirmed C 또는 immutable F로 닫히고, fresh ambiguity PASS와 alignment summary confirmation이 있을 때만 가능하다. summary confirmation은 개별 C 확인을 대체하지 않는다.

`target: implementation`의 `handoff_ready`는 aligned에 더해 S provenance, S-A-U 추적, U DAG, open item·placeholder·assumption 부재, fresh cold PASS, cold 이후 별도 handoff document confirmation을 요구한다. `target: decision`은 handoff_status가 반드시 `not_requested`다. receipt와 confirmation은 canonical projection 또는 repository context가 바뀌면 stale이다. 이 상태는 실행 승인이 아니다. validator는 구조·reference·receipt shape만 검사하므로 실제 발화와 의미적 완결성을 암호학적으로 증명하지 못한다. 안정적인 turn ID가 없으면 확인 시각과 그 한계를 저장한다.

`validate_goal_spec.py PATH [--require structural|aligned|handoff-ready] [--json]`의 exit code는 `0=pass`, `1=validation failure`, `2=I/O or usage failure`다.
