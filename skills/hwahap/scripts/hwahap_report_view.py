"""HTML rendering primitives shared by report sections."""

import html
from typing import Any

from hwahap_report_security import text
from hwahap_report_types import DIFF_SNAPSHOT_FIELDS

AVAILABILITY_LABELS = {"available": "확인됨", "unavailable": "확인할 수 없음"}


class View:
    def __init__(self, payload: dict):
        self.payload = payload

    def esc(self, value: Any) -> str:
        return html.escape(text(value), quote=True)

    def items(self, values: Any) -> str:
        values = values if isinstance(values, list) else []
        if not values:
            return '<p class="empty">기록 없음</p>'
        return "<ul>" + "".join(f"<li>{self.esc(item)}</li>" for item in values) + "</ul>"

    def comma(self, values: Any) -> str:
        values = values if isinstance(values, list) else []
        return "<br>".join(self.esc(item) for item in values)

    def snapshot(self, value: Any) -> str:
        if not isinstance(value, dict):
            return '<span class="empty">기록 없음</span>'
        fields = "".join(
            f"<dt>{self.esc(key)}</dt><dd>"
            f"{self.comma(value[key]) if isinstance(value[key], list) else self.esc(value[key])}</dd>"
            for key in DIFF_SNAPSHOT_FIELDS if key in value)
        return f'<dl class="snapshot">{fields}</dl>' \
            if fields else '<span class="empty">기록 없음</span>'

    def commands(self, values: Any) -> str:
        values = values if isinstance(values, list) else []
        if not values:
            return '<p class="empty">기록 없음</p>'
        return "<ul>" + "".join(
            f"<li>{self.esc(item.get('name'))}: {self.esc(item.get('sha256'))}</li>"
            for item in values if isinstance(item, dict)) + "</ul>"

    def shown(self, value: Any) -> str:
        return "기록 없음" if value is None or value == "" else self.esc(value)

    def display(self, value: Any) -> str:
        if value is None or value == "":
            return "기록 없음"
        if isinstance(value, list):
            return self.comma(value) or "기록 없음"
        return self.esc(AVAILABILITY_LABELS.get(value, value))

    def card(self, label: str, value: Any) -> str:
        return f'<article class="card"><h3>{self.esc(label)}</h3><p>{self.esc(value)}</p></article>'
