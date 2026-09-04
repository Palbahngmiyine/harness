# Plans

| Date | Plan | Status |
|---|---|---|
| 2026-09-04 | [Hwahap V3: Plan Freeze 기반 자율 구현 사이클](2026-09-04-hwahap-v3.md) | Proposed |
| 2026-09-04 | [Hwahap V3 구현·검증 계획](2026-09-04-hwahap-v3-delivery.md) | Proposed |

기획 문서는 구현 전에 결정과 검증 계약을 고정한다. Hwahap V3는 v2와 병행하는 호환 버전이 아니라 breaking replacement다. V3 cutover가 완료되면 `skills/hwahap`의 v2 runtime/hook/schema는 지원 대상에서 제거되고 V3 코드와 운영 문서가 유일한 source of truth가 된다. v2 artifact 자동 migration이나 v2/v3 dual-mode는 제공하지 않는다.
