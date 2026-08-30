"""Strict generated-report markup parser."""

from html.parser import HTMLParser

TAGS = frozenset(("a", "article", "body", "br", "caption", "dd", "details",
    "div", "dl", "dt", "footer", "h1", "h2", "h3", "head", "header",
    "html", "li", "main", "meta", "nav", "ol", "p", "section", "small",
    "span", "strong", "style", "summary", "table", "tbody", "td", "th",
    "thead", "time", "title", "tr", "ul"))
ATTRS = frozenset(("aria-label", "aria-live", "charset", "class", "colspan",
    "content", "href", "id", "lang", "name", "scope"))
BOUNDARIES = frozenset(("a", "article", "body", "br", "caption", "dd",
    "details", "div", "dl", "dt", "footer", "h1", "h2", "h3", "head",
    "header", "html", "li", "main", "nav", "ol", "p", "section", "strong",
    "summary", "table", "tbody", "td", "th", "thead", "time", "title", "tr", "ul"))


class ReportContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values = []
        self.text_segments = [[]]
        self.tag_counts = {}
        self.id_values = []

    def _attributes(self, attrs):
        self.id_values.extend(value for name, value in attrs
                              if name == "id" and value is not None)
        self.values.extend(value for _, value in attrs if value is not None)

    def _boundary(self, tag):
        if tag in BOUNDARIES and self.text_segments[-1]:
            self.text_segments.append([])

    def _markup(self, tag, attrs):
        names = [name for name, _ in attrs]
        if tag not in TAGS or any(name not in ATTRS for name in names) \
                or len(names) != len(set(names)):
            raise ValueError("unsupported report markup")
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1

    def handle_starttag(self, tag, attrs):
        self._markup(tag, attrs)
        self._boundary(tag)
        self._attributes(attrs)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in TAGS:
            raise ValueError("unsupported report markup")
        self._boundary(tag)

    def handle_data(self, data):
        self.values.append(data)
        if data:
            self.text_segments[-1].append(data)

    def handle_comment(self, data):
        raise ValueError("unsupported report markup")

    handle_pi = handle_comment
    unknown_decl = handle_comment

    def handle_decl(self, decl):
        if decl != "doctype html":
            raise ValueError("unsupported report markup")
