"""Render the complete canonical payload ledger."""

import html
import json

from hwahap_report_security import text


def payload_ledger(payload: dict) -> tuple[tuple[str, str, str], ...]:
    rows = []

    def visit(value: object, pointer: str) -> None:
        if isinstance(value, dict):
            if not value:
                rows.append((pointer, "object", "{}"))
            for key in sorted(value):
                if not isinstance(key, str):
                    raise ValueError
                visit(value[key], pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
        elif isinstance(value, list):
            if not value:
                rows.append((pointer, "array", "[]"))
            for index, item in enumerate(value):
                visit(item, pointer + "/" + str(index))
        else:
            kind = "null" if value is None else "boolean" if isinstance(value, bool) \
                else "number" if isinstance(value, (int, float)) else "string" \
                if isinstance(value, str) else None
            if kind is None:
                raise ValueError
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":"))
            rows.append((pointer, kind, encoded))

    visit(payload, "")
    return tuple(rows)


def payload_ledger_block(payload: dict) -> str:
    ledger = payload_ledger(payload)
    rows = "".join(f"<tr><td>{html.escape(path, quote=True)}</td><td>{kind}</td>"
        f"<td>{html.escape(text(value), quote=True)}</td></tr>"
        for path, kind, value in ledger)
    count = len(ledger)
    return (f'<section id="report-data"><h2>정본 데이터 전체 목록</h2>'
        f'<p class="section-intro">{count}개 JSON 값과 빈 컨테이너를 생략 없이 표시합니다. '
        '이 표는 감사를 위한 원본 근거이며, 위의 사람이 읽는 요약보다 우선하지 않습니다.</p>'
        f'<div class="table-wrap"><table><caption>정본 report-data.json ledger · {count}개 행</caption>'
        '<thead><tr><th scope="col">JSON 경로</th><th scope="col">형식</th>'
        f'<th scope="col">값</th></tr></thead><tbody>{rows}</tbody></table></div></section>')
