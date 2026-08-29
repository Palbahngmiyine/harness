# Hwahap lifecycle and final review state

## States, transitions, and final review

Run states are exactly `initialized`, `contract_locked`, `implementing`,
`reviewing`, `recovering`, `replanning`, `final_review`, `completed`, `blocked`,
`failed`, `awaiting_user`, and `cancelled`.

Unit states are exactly `planned`, `implementing`, `reviewing`, `recovery`,
`replan_required`, `passed`, `blocked`, `failed`, and `awaiting_user`.

Every transition appends one `events.jsonl` object containing `timestamp`,
`type`, contiguous `sequence`, `entity`, `from`, `to`, `actor`, `role`,
`reason`, `input_digest`, nonempty `evidence_refs`, and `review_round`. The
validator rejects unknown entities, illegal graph edges, successors after a
terminal state, or a last event that disagrees with the current state.

When the user explicitly requests a Goal, Sol may call `create_goal`; it never
creates one automatically. Sol uses `get_goal` to inspect an active Goal and
records `bound`, `no_active_goal`, or `unavailable` with `goal-sync`. It links
objective, non-goals, proof, and checkpoint to the locked contract. A bound
receipt with `completion_sync: pending` is only the observed pre-completion
value; Sol keeps the external Goal control plane current by calling
`update_goal(complete)` only after local `complete` and `validate` pass. Local
state and Goal tooling cannot expand scope or authority; unavailable tooling
uses the manual contract/state path. For the
F34/F35 correction rule, a verifiable new hypothesis permits Sol to continue
correction on the same unit within locked scope; otherwise use `awaiting_user`.
The external Goal is the durable objective and verified stop condition. Hwahap
continues after first Terra recovery, second Sol replan, and later
new-evidence recursive improvements; there is no fixed failure-count ceiling.
The same blocker without a new hypothesis, or any scope, authority, or cost
change, requires `awaiting_user` and does not complete the Goal. Final-review
post-completion candidates are report-only and never execute automatically. An
unavailable or unsupported Ultra attempt remains pending for exactly one xhigh
fallback with
the same full snapshot; only an aggregate final-review failure awaits the user. Use
`HW_FINAL_REVIEW_FAILED` when the final result fails and
`HW_MODEL_UNAVAILABLE` when the xhigh fallback is unavailable or unsupported.
Do not retry after an aggregate failure.

Plain gate meanings:

Gate는 다음 단계로 가도 되는지 확인하는 조건입니다. Receipt는 검사를
실행한 결과 요약입니다. `diff_snapshot`은 작업 전후 Git 저장 시점, 각
시점의 전체 파일 목록 ID, 변경 내용 ID, 변경 파일 목록을 묶은 확인
자료입니다.

기록 위치는 여섯 곳입니다. `contract.json`은 승인된 목표와 범위,
`units/<id>.json`은 단위별 변경과 검토, `run.json`은 실행 상태와 집계,
`events.jsonl`은 상태가 바뀐 순서, `report-data.json`은 canonical report
payload, `report.html`은 사용자가 확인하는 최종 증거를 담습니다.

1. 단위 통과 게이트
   - 일상: 회원 등록만 만들고 회원 삭제는 만들지 않는지, 한 단위가 약속한
     변화만 끝났는지 확인합니다.
   - 입력 예(CRUD Create): 허용 파일 `src/members/create.py`와 검사 파일
     `tests/test_members_create.py`만 회원 등록 Create에 사용하고 Delete는
     제외한다고 제출합니다.
   - 확인: 변경 경로, 승인된 검사 결과, 두 독립 검토자의 최신 통과 결과와
     같은 전체 snapshot을 대조합니다.
   - 통과: 단위가 통과되고, 모두 통과하면 최종 검토로 진행합니다.
   - 실패: 범위 밖 입력의 실제 결과는 다음과 같습니다.
     ```text
     code: HW_SCOPE_DRIFT
     reason: requested unit input is not an exact member of the locked contract; waiting for user decision
     recovery: ask the user to approve a new Goal/contract or provide a corrected in-scope unit
     ```
     사용자에게 설명할 뜻: 회원 삭제 구현이 필요하지만 승인 범위에 없습니다.
     추가할지 결정해 주세요.
   - 사용자 할 일: 새 Goal/contract를 승인하거나 승인 범위 안의 단위로
     고칩니다.
   - 시스템 기록: 생성 전 거절이면 `units/<id>.json`은 만들지 않고
     `run.json`을 `awaiting_user`로 바꾸며 `events.jsonl`에는 상태 전이만
     기록합니다. 기존 단위의 검토 실패면 `units/<id>.json`에 failure,
     receipts, full snapshot을 기록하고 `events.jsonl`에 상태 전이를
     기록합니다.

2. 최종 검토 게이트
   - 일상: 모든 단위가 끝난 뒤 Sol이 전체 결과를 마지막으로 확인합니다.
   - 입력 예: Ultra 검토가 사용 불가하면 같은 snapshot으로 xhigh를 한 번
     자동 실행하고, 두 결과와 근거를 제출합니다.
   - 확인: 모든 검토자가 같은 최종 변경본을 봤는지, 허용된 시도 순서,
     통과 근거와 aggregate 결과를 대조합니다.
   - 통과: 최종 검토 통과 후 개선 제안과 로컬 완료로 진행합니다.
   - 실패: Ultra 불가/미지원은 사용자에게 묻지 않고 xhigh로 이어집니다.
     둘 다 실패하면 `code: HW_FINAL_REVIEW_FAILED / reason: 최종 검토가
     실패했습니다. / evidence: 두 검토 결과 / recovery: 실패 원인을 고친
     뒤 사용자가 다음 진행을 결정해 주세요.`로 표시합니다. xhigh 자체가
     불가하면 code는 `HW_MODEL_UNAVAILABLE`입니다.
   - 사용자 할 일: fallback은 할 일이 없고, aggregate 실패일 때만 다음
     수정이나 중단을 결정합니다. 같은 최종 검토를 자동 재시도하지 않습니다.
   - 시스템 기록: `run.json`에 각 attempt와 full snapshot을, `events.jsonl`에
     상태 전이만 기록합니다. 검토자 thread와 aggregate code/근거도 run에
     보관합니다.

3. 개선 후보 기록 게이트
   - 일상: 최종 검토가 통과한 뒤 발견한 선택적 개선을 메모만 하는 단계이며,
     원래 완료를 막지 않습니다.
   - 입력 예: 개선 요약, 근거, 기대 효과, 다음 행동을 제안하거나 후보 없이
     바로 완료합니다.
   - 확인: 최종 검토 통과 근거에 연결되고 내용이 충분한지 확인합니다.
   - 통과: 후보는 제안으로만 남기고 원래 실행은 완료로 진행합니다. 후보가
     없어도 통과입니다.
   - 실패: 잘못된 후보는 `HW_STATE_INVALID`이고 상태는 변경 전과 같습니다.
     현재 최종 검토가 통과한 상태에서 후보 때문에
     `HW_USER_DECISION_REQUIRED`/`awaiting_user`로 전이하지 않습니다. 새
     범위 후보는 report-only로 남기고 원래 실행을 완료한 뒤, 사용자가 새
     Goal과 contract를 승인할 때 별도 실행을 시작합니다.
   - 사용자 할 일: 후보를 지금 실행할 필요가 없습니다. 완료 후 실제로
     추진할 때만 새 범위와 Goal을 결정합니다.
   - 시스템 기록: valid candidate만 `run.json`에 기록하며
     `units/<id>.json`과 `events.jsonl`은 바뀌지 않습니다. invalid candidate는
     어디에도 기록하지 않고 `HW_STATE_INVALID`를 반환하며 모든 bytes를
     변경 전과 같게 둡니다.

4. 완료 및 Goal 동기화 게이트
   - 일상: 외부 Goal을 완료라고 말하기 전에 로컬 파일과 정적 보고서를 먼저
     확인합니다.
   - 입력 예: 최종 통과 변경본의 확인 ID, 완료 근거, 생성된 보고서를 제출한
     다음에만 외부 완료 동기화를 요청합니다.
   - 확인: 계약 잠금, 모든 단위와 최종 검토 통과, 보고서 생성·검증, 로컬
     완료 상태를 확인하고 외부 Goal에는 같은 결과를 전달합니다.
   - 통과: 로컬 실행을 완료로 확정하고, 연결된 Goal이 있으면 로컬 검증
     뒤에 외부 동기화를 요청합니다.
   - 실패: `code: HW_STATE_INVALID` 또는
     `HW_REPORT_GENERATION_FAILED / reason: 로컬 완료 증거가 유효하지 않거나
     보고서 검증에 실패했습니다. / evidence: 실패한 검증 / recovery: 로컬
     파일을 복구하고 원인을 고친 뒤 다시 확인합니다.` 외부 Goal은 호출하지
     않습니다.
   - 사용자 할 일: 로컬 실패는 수정하고, 외부 동기화 실패는 기존 receipt를
     확인한 뒤 재시도하거나 결정을 내립니다.
   - 시스템 기록: `run.json`의 `goal_link/history`와 `events.jsonl`,
     `report-data.json` 및 `report.html`에 로컬 결과를 기록하고, 외부
     동기화 결과도 Goal receipt로 보관합니다. 로컬 artifact 검증이 먼저
     통과해야 외부 Goal 완료 동기화를 호출합니다.

Before completion, `final_review` is validated against this exact aggregate
matrix (attempts are `gpt-5.6-sol` only):

- `pending`: no attempts (A), or one `ultra` attempt with
  `unavailable|unsupported` (B); B must remain in `final_review` until its one
  same-snapshot `xhigh` fallback produces the aggregate result;
- `pass`: one `ultra` `pass` attempt (C), or an `ultra`
  `unavailable|unsupported` attempt followed by one `xhigh` `pass` attempt
  (D);
- `fail`: one `ultra` `fail` attempt (E), or an `ultra`
  `unavailable|unsupported` attempt followed by one `xhigh` attempt with
  `fail|unavailable|unsupported` (F).

Other statuses, more than two attempts, an `xhigh`-only attempt, a terminal
attempt while pending, or any other sequence is invalid. Only an aggregate
`fail` (E or F) may transition to `awaiting_user`, with its matching failure
code. Every attempt has a
nonempty `thread_id` and `evidence`, and the exact six-field `diff_snapshot`.
Its `diff_digest` must match the snapshot, and two attempts share the exact
same full snapshot. An aggregate final-review failure is not retried:
a run in `final_review` may transition only to completion or `awaiting_user`;
pending B must first receive its xhigh fallback. The latter transition requires
failure evidence and `HW_FINAL_REVIEW_FAILED` for a failed final result or
`HW_MODEL_UNAVAILABLE` for an unavailable/unsupported fallback. Completion also
requires aggregate `pass` (C or D), and `complete --input-digest` must equal
the verified digest in the sole passing final-review snapshot exactly.

A run may enter `final_review` only after all units are passed and each unit's
latest passing Luna/Terra review pair shares one full snapshot and its latest
passing receipts match the Luna verifier thread and snapshot. Passed units are
ordered by their `unit -> passed` events in `events.jsonl`, not filenames. Their
review snapshots must be adjacent Git revisions: each next unit's base
commit/tree equals the previous unit's target commit/tree. Every passing
final-review snapshot must span the chain from the first unit's base to the last
unit's target; a missing, duplicated, or mismatched pass-event mapping fails
closed. Every nonempty final-review attempt snapshot, including failed,
unsupported, or unavailable attempts, must use those same endpoints. This
chain gate applies as soon as final review is entered, even with
pending attempts or only an unavailable/unsupported model probe. A run may be
`completed` only when its contract is locked, at least one unit exists, every
unit is `passed`, final review passed, `completed_at` is present, metrics agree
with recorded state, and validation succeeds.

Stable failure codes include `HW_AGENT_CONFIG_INVALID`,
`HW_SPEC_UNCONFIRMED`, `HW_SCOPE_DRIFT`, `HW_IMPLEMENTATION_BLOCKED`,
`HW_IMPLEMENTATION_FAILED`, `HW_VERIFICATION_FAILED`, `HW_REPLAN_REQUIRED`,
`HW_FINAL_REVIEW_FAILED`, `HW_MODEL_UNAVAILABLE`,
`HW_USER_DECISION_REQUIRED`, `HW_REPORT_GENERATION_FAILED`, and
`HW_STATE_INVALID`. `init` may also return
`HW_RUN_EXISTS` for an existing conflicting run. Every terminal failure record
contains a code, plain reason, nonempty evidence, and recovery or next action.
