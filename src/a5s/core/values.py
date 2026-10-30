"""Typed values: the keys, amounts and dates in text, found by code, so they can be matched
exactly against where they came from, never by asking a model.

A record's key is found by the scenario's pattern for its keys. An amount is a number with
a currency, such as £1,240.50, $300 or 1,240.50 EUR. A date is a full date, such as
2026-11-04, or a day and month, such as 4 Nov or 4 November. Each is normalised, so the same
value written two ways matches: £1,240.5 and £1240.50 are one amount, and 4 Nov matches
2026-11-04, though 2025-11-04 doesn't.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR"}
_AMOUNT = re.compile(r"([£$€])\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(GBP|USD|EUR)\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")[a-z]*\.?(?:\s+(\d{4}))?\b",
                        re.IGNORECASE)


@dataclass(frozen=True)
class Value:
    kind: str  # key, amount or date
    text: str  # as it was written
    norm: str  # what it's matched by: such as Q-1001, GBP 1240.50, or 2026-11-04 and --11-04

    def matches(self, other: Value) -> bool:
        if self.kind != other.kind:
            return False
        if self.kind == "date":  # a day and month matches a full date on that day
            return self.norm == other.norm or self.norm[-5:] == other.norm[-5:] and (
                self.norm.startswith("--") or other.norm.startswith("--"))
        return self.norm == other.norm


def found(text: str, record_pattern: str | None) -> list[Value]:
    """The typed values in text, in the order they appear, each once."""
    values: dict[tuple[str, str], Value] = {}
    spans = []
    if record_pattern:
        for m in re.finditer(record_pattern, text):
            spans.append((m.start(), Value("key", m.group(0), m.group(0))))
    for m in _AMOUNT.finditer(text):
        currency = _SYMBOLS.get(m.group(1) or "", m.group(4))
        try:
            amount = Decimal((m.group(2) or m.group(3)).replace(",", ""))
        except InvalidOperation:
            continue
        spans.append((m.start(), Value("amount", m.group(0), f"{currency} {amount:.2f}")))
    for m in _ISO.finditer(text):
        spans.append((m.start(), Value("date", m.group(0), m.group(0))))
    for m in _DAY_MONTH.finditer(text):
        day, month, year = int(m.group(1)), _MONTHS.index(m.group(2)[:3].lower()) + 1, m.group(3)
        if 1 <= day <= 31:
            spans.append((m.start(), Value("date", m.group(0).rstrip("."),
                                           f"{year}-{month:02d}-{day:02d}" if year
                                           else f"--{month:02d}-{day:02d}")))
    for _, value in sorted(spans, key=lambda s: s[0]):
        values.setdefault((value.kind, value.norm), value)
    return list(values.values())


def unmatched(values: list[Value], sources: list[Value]) -> list[Value]:
    """The values that match none of the sources."""
    return [v for v in values if not any(v.matches(s) for s in sources)]
