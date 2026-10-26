"""Lossless Vietnamese display formatting, separate from execution values."""

import re
from decimal import Decimal


def format_number(value: int | str | Decimal) -> str:
    raw = str(value)
    if not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", raw):
        return raw
    sign = "-" if raw.startswith("-") else ""
    whole, dot, fraction = raw.lstrip("-").partition(".")
    groups = [whole[max(0, end - 3) : end] for end in range(len(whole), 0, -3)]
    return sign + ".".join(reversed(groups)) + ("," + fraction if dot else "")
