"""A closed bilingual grammar for one unconditional numeric rule, not general NLU."""

import re
import unicodedata
from dataclasses import dataclass
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
