"""Typed values: the keys, amounts and dates in text, found by code, so they can be matched
exactly against where they came from, never by asking a model.

A record's key is found by the scenario's pattern for its keys. An amount is a number with
a currency, such as £1,240.50, $300, GBP 1,240.50 or 1,240.50 EUR. A date is a full date,
such as 2026-11-04, or a day and month either way round, such as 4 Nov, 4 November or
Nov 4. Each is normalised, so the same
value written two ways matches: £1,240.5 and £1240.50 are one amount, and 4 Nov matches
2026-11-04, though 2025-11-04 doesn't.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY", "₹": "INR"}
_CODES = ("GBP|USD|EUR|JPY|CNY|INR|SGD|HKD|AUD|NZD|CAD|CHF|SEK|NOK|DKK|PLN|CZK|ZAR|BRL|MXN|AED|SAR"
          "|KRW|TWD|THB|MYR|IDR|PHP|ILS|TRY")
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# A symbol or a code before the number, such as £1,240.50 or GBP 1,240.50, or a code after it
_AMOUNT = re.compile(rf"([£$€¥₹])\s?({_NUMBER})|\b({_CODES})\s?({_NUMBER})"
                     rf"|({_NUMBER})\s?({_CODES})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH = "(" + "|".join(_MONTHS) + r")[a-z]*\.?"
# The day before the month, such as 4 Nov, or after it, such as Nov 4 or November 4th, 2026
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:\s+(\d{{4}}))?\b",
                        re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?",
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
        currency = _SYMBOLS.get(m.group(1) or "") or m.group(3) or m.group(6)
        try:
            amount = Decimal((m.group(2) or m.group(4) or m.group(5)).replace(",", ""))
        except InvalidOperation:
            continue
        spans.append((m.start(), Value("amount", m.group(0), f"{currency} {amount:.2f}")))
    for m in _ISO.finditer(text):
        spans.append((m.start(), Value("date", m.group(0), m.group(0))))
    taken = []  # where a date is, so a day after its month isn't read twice
    for m in _DAY_MONTH.finditer(text):
        day, month, year = int(m.group(1)), _MONTHS.index(m.group(2)[:3].lower()) + 1, m.group(3)
        if 1 <= day <= 31:
            taken.append(range(m.start(), m.end()))
            spans.append((m.start(), Value("date", m.group(0).rstrip("."), _norm(year, month, day))))
    for m in _MONTH_DAY.finditer(text):
        month, day, year = _MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2)), m.group(3)
        if 1 <= day <= 31 and not any(m.start() in r or m.end() - 1 in r for r in taken):
            spans.append((m.start(), Value("date", m.group(0), _norm(year, month, day))))
    for _, value in sorted(spans, key=lambda s: s[0]):
        values.setdefault((value.kind, value.norm), value)
    return list(values.values())


def _norm(year: str | None, month: int, day: int) -> str:
    return f"{year}-{month:02d}-{day:02d}" if year else f"--{month:02d}-{day:02d}"


def unmatched(values: list[Value], sources: list[Value]) -> list[Value]:
    """The values that match none of the sources."""
    return [v for v in values if not any(v.matches(s) for s in sources)]
