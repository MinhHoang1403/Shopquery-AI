"""A closed bilingual grammar for one unconditional numeric rule, not general NLU."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

OPERATORS = {
    ">=": "gte",
    ">": "gt",
    "<=": "lte",
    "<": "lt",
    "=": "eq",
    "ít nhất": "gte",
    "tối thiểu": "gte",
    "lớn hơn": "gt",
    "nhỏ hơn": "lt",
    "không vượt quá": "lte",
    "tối đa": "lte",
    "bằng": "eq",
    "at least": "gte",
    "no less than": "gte",
    "greater than": "gt",
    "more than": "gt",
    "at most": "lte",
    "no more than": "lte",
    "not exceeding": "lte",
    "less than": "lt",
    "equals": "eq",
    "equal to": "eq",
}
AGGREGATES = {
    "tổng": "sum",
    "sum of": "sum",
    "total": "sum",
    "trung bình": "avg",
    "average of": "avg",
    "average": "avg",
    "số dòng": "row_count",
    "row count of": "row_count",
    "số giá trị không null": "non_null_value_count",
    "non-null count of": "non_null_value_count",
}
WORD = r"[\w ]{1,100}"
NUMBER = r"[-+]?\d[\d.,]*"
UNIT = r"[\w]+(?: units)?"


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    return "".join(c for c in value if c.isalnum() and not unicodedata.combining(c))


def regulation_title_supported(title: str, prose: "ProseRule") -> bool:
    """Section headings are policy evidence too, not decoration to discard."""
    if prose.period is None:
        return False
    start, end = (date.fromisoformat(value) for value in prose.period)
    title = "".join(
        c
        for c in unicodedata.normalize("NFKD", title.casefold().replace("đ", "d"))
        if not unicodedata.combining(c)
    ).replace("_", " ")
    title = re.sub(r"^\d+[ -]*", "", title)
    title = re.sub(r"\btrang\s+\d+\b", "", title)
    for match in re.finditer(r"\b(?:thang|month)\s+(\d{1,2})\b", title):
        if int(match[1]) != start.month or start.month != end.month:
            return False
    for match in re.finditer(r"\b(?:nam|year)?\s*(\d{4})\b", title):
        if int(match[1]) != start.year or start.year != end.year:
            return False
    title = re.sub(r"\b(?:thang|month)\s+\d{1,2}\b", "", title)
    title = re.sub(r"\b(?:nam|year)?\s*\d{4}\b", "", title)
    words = re.findall(r"[^\W_]+", title)
    vocabulary = re.findall(
        r"[^\W_]+", prose.subject + " " + prose.metric_reference + " " + prose.identity_reference
    )
    vocabulary += [
        "quy",
        "định",
        "KPI",
        "tổng",
        "theo",
        "chính",
        "sách",
        "policy",
        "rule",
        "phạm",
        "vi",
        "số",
        "liệu",
        "cần",
        "dùng",
        "ngưỡng",
        "đánh",
        "giá",
        "trường",
        "hợp",
        "bằng",
        "tắc",
        "kết",
        "luận",
        "phân",
        "biệt",
        "tài",
        "liệu",
        "vận",
        "hành",
        "hiệu",
        "lực",
    ]
    return {normalized(w) for w in words} <= {normalized(w) for w in vocabulary}


@dataclass(frozen=True)
class ProseRule:
    subject: str
    aggregate: str
    metric_reference: str
    identity_reference: str
    operator: str
    threshold: str
    unit: str
    via_reference: str | None
    criterion: str | None
    quote: str
    record_reference: str | None = None
    status_example: str | None = None
    relative_record: str | None = None
    presentation_reference: str | None = None
    period: tuple[str, str] | None = None
    required_status: str | None = None
    declared_unit: bool = False


def _number(value: str, locale: str | None) -> str | None:
    if locale == "vi-VN":
        if not re.fullmatch(r"[-+]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?", value):
            return None
        value = value.replace(".", "").replace(",", ".")
    elif locale == "en-US":
        if not re.fullmatch(r"[-+]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
            return None
        value = value.replace(",", "")
    elif not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value) or re.fullmatch(
        r"[-+]?[1-9]\d{0,2}\.\d{3}", value
    ):
        return None
    return format(Decimal(value), "f")


def parse_prose(content: str) -> ProseRule | None:
    """Every sentence must be consumed; an unknown qualifier invalidates the rule."""
    if not content or len(content) > 12000:
        return None
    regulation = _parse_regulation(content)
    if regulation is not None:
        return regulation
    body = " ".join(content.split())
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ])", body)
    sentences = [s.removesuffix(".") for s in sentences]
    locale = None
    for sentence in sentences:
        if sentence in {"Numbers use en-US", "Số dùng định dạng en-US"}:
            if locale is not None:
                return None
            locale = "en-US"
        elif sentence in {"Numbers use vi-VN", "Số dùng định dạng vi-VN"}:
            if locale is not None:
                return None
            locale = "vi-VN"
    first = sentences[0]
    first = re.sub(r"^Trong bộ dữ liệu(?: giả lập)? này, ", "", first)
    prefix = re.fullmatch(
        rf"(?:một |Mỗi |Each )?(?P<subject>{WORD}?) "
        rf"(?:đạt(?: KPI(?: (?P<criterion>{WORD}?))?)? (?:khi|nếu)|qualifies when) "
        rf"(?P<condition>.+)",
        first,
    )
    if prefix is None:
        return None
    subject, condition = prefix["subject"], prefix["condition"]
    if re.search(r"\b(unless|except|only|if|nếu|trừ|không|hoặc|và)\b", subject, re.I):
        return None
    aggregate = None
    for phrase in sorted(AGGREGATES, key=len, reverse=True):
        if condition.startswith(phrase + " "):
            aggregate = AGGREGATES[phrase]
            condition = condition[len(phrase) + 1 :]
            break
    if aggregate is None:
        return None
    threshold = operator = unit = metric = None
    operator_phrases = "|".join(re.escape(p) for p in sorted(OPERATORS, key=len, reverse=True))
    comparison = re.fullmatch(
        rf"(?P<metric>{WORD}?) (?:is )?(?P<op>{operator_phrases}) (?P<number>{NUMBER})"
        rf"(?: (?P<unit>{UNIT}))?",
        condition,
    )
    between = re.fullmatch(
        rf"(?P<metric>{WORD}?) từ (?P<number>{NUMBER})(?: (?P<unit>{UNIT}))? trở lên",
        condition,
    )
    match = comparison or between
    if match is None:
        return None
    operator = OPERATORS[match["op"]] if comparison else "gte"
    threshold = _number(match["number"], locale)
    metric, unit = match["metric"], match["unit"] or "source"
    # The record-relative clause does not authorize a filter or another table.
    relative = re.fullmatch(
        rf"(?P<field>{WORD}?) của các (?P<records>{WORD}?) thuộc (?P<entity>.+) đó", metric
    )
    if relative:
        if normalized(relative["entity"]) != normalized(subject):
            return None
        metric = relative["field"]
    scope, identity, via = False, None, None
    record_reference = status_example = presentation_reference = None
    for sentence in sentences[1:]:
        if sentence in {
            "Numbers use en-US",
            "Số dùng định dạng en-US",
            "Numbers use vi-VN",
            "Số dùng định dạng vi-VN",
        }:
            continue
        if sentence in {"Include all rows", "Tính tất cả dòng", "Tính mọi trạng thái"}:
            if scope:
                return None
            scope = True
            continue
        all_statuses = re.fullmatch(
            rf"Tính tất cả trạng thái (?P<records>{WORD}), không chỉ trạng thái (?P<status>{WORD})",
            sentence,
        )
        if all_statuses and not scope:
            scope = True
            record_reference, status_example = all_statuses["records"], all_statuses["status"]
            continue
        key = re.fullmatch(
            rf"(?:Identify each {re.escape(subject)} by|"
            rf"Phân biệt từng {re.escape(subject)} theo mã) (?P<key>\w+)",
            sentence,
        )
        relationship = re.fullmatch(
            rf"Xác định {re.escape(subject)} của {WORD}? qua (?P<via>{WORD}?) "
            rf"và liên kết (?P<key>\w+); "
            rf"phân biệt từng {re.escape(subject)} theo mã (?P<again>\w+), không gộp theo tên",
            sentence,
        )
        if key or relationship:
            if identity is not None:
                return None
            key_match = key or relationship
            identity = key_match["key"]
            if relationship:
                if identity != relationship["again"]:
                    return None
                via = relationship["via"]
            continue
        if (
            sentence
            in {
                "SUM bỏ qua giá trị NULL, giữ số 0 là giá trị hợp lệ",
                "SUM ignores NULL; zero is valid",
            }
            and aggregate == "sum"
        ):
            continue
        final = re.fullmatch(
            rf"Trả kết luận đạt hoặc chưa đạt cho từng {re.escape(subject)} "
            rf"dựa trên (?P<label>{WORD}) SQL thực tế, không áp dụng KPI khác",
            sentence,
        )
        if final:
            if presentation_reference is not None:
                return None
            presentation_reference = final["label"]
            continue
        return None
    if not scope or identity is None or threshold is None:
        return None
    return ProseRule(
        subject,
        aggregate,
        metric,
        identity,
        operator,
        threshold,
        unit,
        via,
        prefix["criterion"],
        content,
        record_reference,
        status_example,
        relative["records"] if relative else None,
        presentation_reference,
    )


def _parse_regulation(content: str) -> ProseRule | None:
    """Closed sectioned SUM regulation: every clause is consumed, never extracted away.

    References, period, status, threshold, entity and unit are captured from the
    document. Registry/full-column proofs are required separately before authority.
    An exception or an extra sentence cannot silently become an all-row rule.
    """
    body = " ".join(content.split())
    scope = re.search(
        r"Chính sách này áp dụng cho từng (?P<subject>[\w ]+?) trong kỳ từ ngày "
        r"(?P<start>\d{2}/\d{2}/\d{4}) đến hết ngày (?P<end>\d{2}/\d{2}/\d{4})\. "
        r"Bộ dữ liệu kiểm thử chỉ gồm các (?P<records>[\w ]+?) đã "
        r"(?P<status>[\w ]+?) trong kỳ này\. "
        r"Đơn vị tiền là (?P<unit>[\w ]+?) \((?P<unit_code>[A-Z]{3})\)\. ",
        body,
    )
    if scope is None:
        return None
    prefix = body[: scope.start()]
    # Header is descriptive only; allow one title/reference/publication header,
    # with an explicit test period, not arbitrary preconditions or exceptions.
    header = re.fullmatch(
        r"[A-ZÀ-ỸĐ0-9 _/-]+ \| Ban hành cho bộ dữ liệu tổng hợp \| "
        r"Hiệu lực kiểm thử: (?P<first>\d{2})[–-](?P<last>\d{2})/(?P<month>\d{2})/(?P<year>\d{4}) "
        r"1\. Phạm vi và số liệu cần dùng ",
        prefix,
    )
    if header is None:
        return None
    tail = body[scope.end() :]
    definition = re.match(
        r"2\. Định nghĩa chỉ tiêu KPI Chỉ tiêu duy nhất dùng để đánh giá là tổng "
        r"(?P<label>[\w ]+?) của tất cả (?P<completed>[\w ]+?) "
        r"thuộc một (?P<entity>[\w ]+?) trong kỳ\. "
        r"Tổng (?P=label) phải được lấy từ trường (?P<metric>\w+) của bảng (?P<fact>[\w ]+?), "
        r"gom nhóm theo (?P<identity>\w+)\. "
        r"Tên (?P=entity) lấy từ bảng danh mục (?P=entity) "
        r"bằng liên kết khóa (?P=entity) đã xác minh\. ",
        tail,
    )
    if definition is None:
        return None
    entity, label = definition["entity"], definition["label"]
    title = prefix.split(" |", 1)[0]
    title = re.sub(r"\b[A-Z]+(?:-[A-Z0-9]+)+\b", "", title)
    allowed_title = {
        normalized(w) for w in ("quy định KPI tổng theo " + label + " " + entity).split()
    }
    if any(normalized(w) not in allowed_title for w in title.split()):
        return None
    if normalized(definition["completed"]) != normalized(scope["records"] + " " + scope["status"]):
        return None
    if not normalized(scope["subject"]).startswith(normalized(entity)):
        return None
    rest = tail[definition.end() :]
    entity_pattern, metric_pattern = re.escape(entity), re.escape(label)
    verdict = re.match(
        r"3\. Ngưỡng đánh giá và trường hợp bằng ngưỡng "
        rf"Một {entity_pattern} được xếp loại ĐẠT KPI "
        rf"khi tổng {metric_pattern} lớn hơn hoặc bằng "
        rf"(?P<threshold>{NUMBER}) (?P<code>[A-Z]{{3}})\. "
        rf"{entity_pattern.capitalize()} có tổng {metric_pattern} nhỏ hơn "
        r"(?P=threshold) (?P=code) được xếp loại CHƯA ĐẠT KPI\. "
        rf"Trường hợp tổng {metric_pattern} bằng đúng (?P=threshold) "
        r"(?P=code) phải được coi là ĐẠT KPI, "
        r"không được xếp vào nhóm chưa đạt\. ",
        rest,
    )
    if verdict is None or verdict["code"] != scope["unit_code"]:
        return None
    remainder = rest[verdict.end() :]
    if not re.fullmatch(
        rf"4\. Quy tắc kết luận Đánh giá riêng từng {entity_pattern}, không dùng phí bình quân mỗi "
        rf"{re.escape(scope['records'])} để thay thế tổng {metric_pattern}\. "
        r"Không cộng trùng phí khi kết nối bảng danh mục dịch vụ\. "
        rf"Mỗi {entity_pattern} phải xuất hiện đúng một lần "
        rf"trong kết quả tổng hợp theo {entity_pattern}\. "
        rf"Nếu thiếu {re.escape(definition['fact'])}, "
        rf"thiếu liên kết {entity_pattern} đã được kiểm chứng "
        r"hoặc thiếu số liệu cần thiết, kết quả phải ghi là chưa đủ bằng chứng; "
        r"không tự gán doanh thu bằng 0 rồi kết luận chưa đạt\. "
        r"5\. Phân biệt tài liệu quy định và số liệu vận hành "
        r"Tài liệu này chỉ mô tả quy tắc KPI và không công bố "
        rf"tổng phí thực tế của bất kỳ {entity_pattern} nào\. "
        rf"Muốn trả lời {entity_pattern} nào đạt/chưa đạt, "
        r"phải kết hợp tài liệu chính sách này với số liệu "
        r"trong các bảng CSV của cùng workspace\. "
        r"Ghi chú: Tất cả tên doanh nghiệp, [\w ,]+ và số liệu trong bộ kiểm thử đều là dữ liệu "
        r"tổng hợp giả lập, không đại diện cho giao dịch thật\.",
        remainder,
    ):
        return None
    try:
        start = date.fromisoformat("-".join(reversed(scope["start"].split("/"))))
        end = date.fromisoformat("-".join(reversed(scope["end"].split("/"))))
        header_start = date(int(header["year"]), int(header["month"]), int(header["first"]))
        header_end = date(int(header["year"]), int(header["month"]), int(header["last"]))
    except ValueError:
        return None
    threshold = _number(verdict["threshold"], "vi-VN")
    if (
        start > end
        or threshold is None
        or len(threshold) > 100
        or (header_start, header_end) != (start, end)
    ):
        return None
    return ProseRule(
        scope["subject"],
        "sum",
        definition["metric"],
        definition["identity"],
        "gte",
        threshold,
        scope["unit_code"],
        None,
        None,
        content,
        period=(str(start), str(end)),
        required_status=scope["status"],
        declared_unit=True,
        relative_record=definition["fact"],
    )
