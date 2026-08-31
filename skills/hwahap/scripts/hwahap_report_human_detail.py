"""Completion evidence wording for the human-first report."""

from hwahap_report_human_context import fivew3h


def _unique(values):
    result = []
    for value in values if isinstance(values, list) else []:
        if value and value not in result:
            result.append(value)
    return result


def _receipt_count(view):
    groups = view.payload.get("tests-metrics", {}).get("test_receipts", [])
    return sum(len(item.get("receipts", [])) for item in groups
               if isinstance(item, dict) and isinstance(item.get("receipts"), list))


def _duration(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return "기록 없음"
    days, seconds = divmod(int(value), 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = ([f"{days}일"] if days else []) + ([f"{hours}시간"] if hours else [])
    parts += ([f"{minutes}분"] if minutes else []) + ([f"{seconds}초"] if seconds or not parts else [])
    return " ".join(parts)


def _review_passes(review):
    if not isinstance(review, dict) or review.get("outcome") != "pass":
        return False
    verifier, scope = review.get("verifier", {}), review.get("scope_reviewer", {})
    values = [review.get("diff_digest"), verifier.get("diff_digest"),
              scope.get("diff_digest"), review.get("diff_snapshot", {}).get("diff_digest")]
    values = [value for value in values if isinstance(value, str) and value]
    return (verifier.get("status") == "pass" and scope.get("status") == "pass"
            and len(values) == 4 and len(set(values)) == 1)


def completion(view, metrics, counts):
    payload = view.payload
    summary, reviews = payload.get("summary", {}), payload.get("reviews", {})
    units = payload.get("units", [])
    latest = [unit.get("review_history", [])[-1] for unit in units
              if isinstance(unit, dict) and unit.get("review_history")]
    reviewed = sum(_review_passes(item) for item in latest)
    final = reviews.get("final_review", {})
    attempts = final.get("attempts", [])
    final_pass = final.get("status") == "pass" and any(
        isinstance(item, dict) and item.get("status") == "pass" for item in attempts)
    consistent = (summary.get("status") == "completed" and counts["total"] > 0
                  and counts["passed"] == counts["total"] and reviewed == counts["total"] and final_pass)
    conclusion = (f'실행 기록상 완료 판정은 일관됩니다. 작업 단위 {counts["passed"]}개가 모두 통과했고, '
                  f'각 단위의 최신 Luna 검증과 Terra 범위 검수 {reviewed}개가 같은 diff에서 통과했으며, '
                  'Sol 최종 검토도 통과한 뒤 상태가 completed로 기록됐습니다.' if consistent else
                  f'상태는 {summary.get("status")}로 기록됐지만 완료 판정에 필요한 기록이 모두 맞물리지 않습니다. '
                  f'작업 단위 {counts["passed"]}/{counts["total"]}, 단위 검토 {reviewed}/{counts["total"]}, '
                  f'Sol 최종 검토 {"통과" if final_pass else "미통과"}입니다.')
    receipt_count, recorded = _receipt_count(view), metrics.get("test_runs")
    explanation = (f'메트릭에는 테스트 실행 {recorded}회가 기록됐지만 상세 실행 receipt는 {receipt_count}건입니다. '
                   '두 수치는 같은 증거가 아니므로 상세 receipt가 없는 실행은 이 HTML만으로 명령과 출력을 재현할 수 없습니다. 직접 연결된 구조화 receipt 필드는 없음.'
                   if recorded != receipt_count else f'기록된 테스트 실행은 {recorded}회이고 상세 실행 receipt는 {receipt_count}건입니다.')
    evidence = _unique([value for item in latest if isinstance(item, dict)
                        for role in (item.get("verifier", {}), item.get("scope_reviewer", {}))
                        if isinstance(role, dict) for value in role.get("evidence", [])]
                       + [value for item in attempts if isinstance(item, dict)
                          for value in item.get("evidence", [])])
    rows = (("누가 (Who)", "구현·검증·범위 검수·최종 검토 담당자는 정본 evidence에서 대조"),
            ("언제 (When)", "완료 상태가 기록된 시점; 개별 단계 시간은 미기록"),
            ("어디서 (Where)", "최종 검토 snapshot의 변경 경로와 정본 report-data"),
            ("무엇을 (What)", f"목표 ‘{summary.get('goal')}’의 상태를 판정"),
            ("왜 (Why)", conclusion),
            ("어떻게 (How)", "작업 단위 상태 → Luna 기능 검증 → Terra 계획·범위 검수 → Sol 최종 snapshot 검토 → completed 상태 순서로 기록을 대조"),
            ("얼마나 (How much)", f"검수 회차 {metrics.get('review_rounds')}회; 기록된 테스트 실행 {recorded}회; 상세 receipt {receipt_count}건; 개선 {counts['deviations']}건"),
            ("얼마 동안 (How long)", f"소요 시간 메트릭 {_duration(metrics.get('elapsed_seconds'))}; 개별 단계 시간은 미기록"))
    return conclusion, explanation, fivew3h(view, "완료 판단의 5W3H와 근거 원문 보기",
        conclusion, rows, evidence, explanation)
