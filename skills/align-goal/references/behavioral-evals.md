# Behavioral evaluations

구조 validator가 증명할 수 없는 상호작용과 재귀는 독립 forward evaluation으로 확인한다. 실행 가능한 case source는 [evals/behavioral-cases.json](evals/behavioral-cases.json)이다. fixture schema와 필수 capability/domain coverage는 `scripts/validate_behavioral_evals.py`가 검사한다. 이 검사는 LLM 행동을 실행하거나 채점하지 않는다.

## Forward-run protocol

각 case를 새 temporary workspace에서 실행한다. 먼저 fixture와 harness를 기계적으로 확인한다.

```bash
python3 -B skills/align-goal/scripts/validate_behavioral_evals.py \
  skills/align-goal/references/evals/behavioral-cases.json
python3 -B skills/align-goal/scripts/test_validate_behavioral_evals.py
```

대상 LLM에는 intended answer, oracle, 후속 turn, 이전 결론을 주지 않는다. 다음 명령으로 뽑은 initial package의 workspace 파일만 격리된 workspace에 만들고, `initial_user_message`와 현재 skill만 준다.

```bash
python3 -B skills/align-goal/scripts/validate_behavioral_evals.py \
  skills/align-goal/references/evals/behavioral-cases.json --emit-target E01
```

평가 controller는 source fixture의 `stimulus.follow_ups`를 미리 보여주지 않고 trigger가 실제로 충족될 때 한 turn씩 보낸다. `{{...}}`는 직전 transcript에서 실제 C ID와 표시된 exact alternative value를 사용해 치환한다. target model은 자신의 temporary workspace 밖에 쓰지 않는다. transcript와 `artifacts_to_collect`를 보존한다.

실행이 끝난 뒤 별도 assessor에게 transcript, 산출물, repository fixture와 다음 명령의 assessor-only package를 준다. 작성 model의 reasoning이나 기대 답은 주지 않는다.

```bash
python3 -B skills/align-goal/scripts/validate_behavioral_evals.py \
  skills/align-goal/references/evals/behavioral-cases.json --emit-oracle E01
```

assessor는 `must_observe`, `must_not_observe`, `mechanical_checks`를 실제 결과와 대조한다. 단일 PASS는 특정 실행의 관찰 결과일 뿐 LLM 결정성, 미래 입력의 완전성, 모든 구현 선택의 부재를 증명하지 않는다. 모델 동작은 unit test로 통과했다고 보고하지 않는다.

## Required behavior

1. repository naming convention을 자동 선택하지 않고 exact 유지/변경 alternatives를 질문한다.
2. `알아서 해줘`, `you choose`, `best judgment`, `looks good`, 추상 `follow repo`를 confirmed로 저장하지 않고 exact value를 다시 묻는다.
3. cold consumer가 timeout을 누락으로 찾으면 새 C를 확정하고 영향받는 S/A/U와 receipt를 갱신한 뒤 재검토한다.
4. 독립 choice 9개를 8개와 1개 round로 분리한다.
5. 동일 question/alternatives/outcome의 반복 표면만 policy C로 묶고 모든 policy_targets를 기록한다.
6. confirmed C 변경 시 영향받는 S/A/U와 관련 receipt를 stale로 만든다. receipt timestamp만 바꿀 때는 freshness를 유지한다.
7. private helper inline/split은 다섯 local proof가 완전할 때만 제외한다.
8. CLI, API, UI, stateful workflow, data migration에서 구현 LLM이 임의로 choice를 만들지 않는지 검사한다.
9. 5라운드 이후에도 종료하지 않고 pause/resume 뒤 ID와 exact response를 보존한다.

## Deterministic validator coverage

- exact top-level key에서 `next_action`, `spec_digest`, `repository_context_digest` 또는 alias를 추가한다.
- C candidate/asked에 non-null response를 넣거나 confirmed/superseded 필드를 누락한다.
- alternative/value mismatch, nested vague response, recommendation-only auto-confirm을 만든다.
- exact 12 names 대신 alias, missing surface, duplicate surface, DS id/name 혼동을 만든다.
- snapshot F로 forced를 만들거나 forced derivation·immutable basis를 누락한다.
- policy_targets omission, empty policy, duplicate target을 만든다.
- round에 9개 choice, duplicate membership, same/future dependency, round-4 checkpoint omission을 만든다.
- applicable surface C omission, superseded C provenance, S provenance omission, S/A/U mapping omission을 만든다.
- open O, placeholder, assumption, non-functional measurement omission을 만든다.
- receipt/confirmation digest stale, missing two confirmations, cold-later handoff confirmation omission을 만든다.
- cold blocker, unknown reference, plural unit_ids 누락, incomplete full coverage를 만든다.
- local proof 하나 누락, decision target nonempty U, U self/cycle/order/orphan을 만든다.
- fence 0/2, duplicate JSON key, wrong prefix, duplicate global ID를 만든다.
- frontmatter/contract target or revision mismatch와 claimed aligned/ready gate 우회를 만든다.
- 모든 next_action precedence 전이와 exit code 0/1/2를 검사한다.

위 항목은 `test_validate_goal_spec.py`의 deterministic negative test 대상이다. forward case의 schema 분리, case ID, safe fixture path, capability/domain coverage, target/oracle 분리는 `test_validate_behavioral_evals.py`가 검사한다. 어느 쪽도 실제 사용자 발화의 의미나 모델의 재귀 탐색 품질을 증명하지 않는다.

판정 문구는 “현재 spec과 repository snapshot에서 두 LLM이 추가 material choice를 발견하지 못했다”로 제한한다. PASS는 미래의 모든 선택, 제품 성공, 사용자 발화의 의미적 진실을 증명하지 않는다.
