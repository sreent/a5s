"""Typed values: the keys, amounts and dates in text, found by code, so they can be matched
exactly against where they came from, never by asking a model.

A record's key is found by the scenario's pattern for its keys. An amount is a number with
a currency, such as £1,240.50, $300, GBP 1,240.50 or 1,240.50 EUR. A date is a full date,
such as 2026-11-04, or a day and month either way round, such as 4 Nov, 4 November or
Nov 4, a month by its name alone, or a day, month and year in figures, the day first, such as
13/11/2026. In Thai, as agents answer people who read it, a date such as 6 พฤศจิกายน 2569,
6 พ.ย. 69 or 13/11/2569, its year in the Buddhist era, and an amount such as 860 บาท, 860.- บาท,
860 บ. or ฿860, in Thai digits or not.
Each is normalised, so the same
value written two ways matches: £1,240.5 and £1240.50 are one amount, and 4 Nov matches
2026-11-04, though 2025-11-04 doesn't.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_NAMES = ("january", "february", "march", "april", "june", "july", "august", "september",
          "october", "november", "december", "sept")
_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY", "₹": "INR", "฿": "THB"}
_CODES = ("GBP|USD|EUR|JPY|CNY|INR|SGD|HKD|AUD|NZD|CAD|CHF|SEK|NOK|DKK|PLN|CZK|ZAR|BRL|MXN|AED|SAR"
          "|KRW|TWD|THB|MYR|IDR|PHP|ILS|TRY")
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# A symbol or a code before the number, such as £1,240.50 or GBP 1,240.50, or a code after it
_AMOUNT = re.compile(rf"([£$€¥₹฿])\s?({_NUMBER})|\b({_CODES})\s?({_NUMBER})"
                     rf"|({_NUMBER})\s?({_CODES})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# A day, month and year in figures, the day first, as Thai and British people write them, such
# as 13/11/2569, 13-11-69 or 13.11.2026: a year of the Buddhist era, or its last two digits, as
# Thai does (round 15, A9)
_FIGURES = re.compile(r"(?<![\d/.-])(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/.-]|\.\d)")
# A month by its name, or as it's cut short, and nothing more: never one with words run on
# after it, as in NovemberFinanceApproved, which a form would carry (round 15, F7)
_MONTH = "(" + "|".join(sorted({*_MONTHS, *_NAMES}, key=len, reverse=True)) + r")\.?(?![a-z])"
# The day before the month, such as 4 Nov, or after it, such as Nov 4 or November 4th, 2026
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:\s+(\d{{4}}))?\b",
                        re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?",
                        re.IGNORECASE)
# Thai, as people write it and as agents answer them in it: each month by its name or as it's
# cut short, such as 6 พฤศจิกายน 2569 or 6 พ.ย. 69, its year in the Buddhist era, 543 years on,
# and often only its last two digits; Thai digits; and the currencies by their Thai names, such
# as 860 บาท, beside ฿ (core/languages.py)
_TH_MONTHS = (("มกราคม", "ม.ค."), ("กุมภาพันธ์", "ก.พ."), ("มีนาคม", "มี.ค."), ("เมษายน", "เม.ย."),
              ("พฤษภาคม", "พ.ค."), ("มิถุนายน", "มิ.ย."), ("กรกฎาคม", "ก.ค."), ("สิงหาคม", "ส.ค."),
              ("กันยายน", "ก.ย."), ("ตุลาคม", "ต.ค."), ("พฤศจิกายน", "พ.ย."), ("ธันวาคม", "ธ.ค."))
_TH_MONTH = {name: n for n, names in enumerate(_TH_MONTHS, 1) for name in names}
# A year after its month: four digits, after พ.ศ. or ค.ศ., which say its era, as in
# 6 พฤศจิกายน พ.ศ. 2568, or two, never a time's, as in 6 พ.ย. 10:00 น., and only where they make a
# year near this one (_era), so a count, as in 6 พ.ย. 15 รายการ, is no year (round 14)
_TH_YEAR = r"(?:(?:พ\.ศ\.|ค\.ศ\.)\s*)?(\d{4}(?!\d)|\d{2}(?![\d:]|\.\d))"
_TH_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*(" + "|".join(
    re.escape(m) for m in sorted(_TH_MONTH, key=len, reverse=True)) + r")(?:\s*" + _TH_YEAR + ")?")
_TH_CURRENCY = {"บาท": "THB", "บ.": "THB", "ปอนด์": "GBP", "ดอลลาร์": "USD", "ยูโร": "EUR", "เยน": "JPY",
                "รูปี": "INR"}
# How many, by its word before the currency's, as 1.5 ล้านบาท is a million and a half baht
_TH_SCALE = {"พัน": 1_000, "หมื่น": 10_000, "แสน": 100_000, "ล้าน": 1_000_000}
# and as receipts write it, 860.- บาท (round 15, A9)
_TH_AMOUNT = re.compile(rf"(?<![\d.,])({_NUMBER})(?:\.-)?\s?(" + "|".join(_TH_SCALE) + r")?\s?("
                        + "|".join(re.escape(c) for c in _TH_CURRENCY) + ")")
_TH_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")  # one for one, so each keeps its place


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
    written, text = text, text.translate(_TH_DIGITS)  # what's matched; what's said, as written
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
    for m in _ISO.finditer(text):  # a Buddhist era's year, as Thai writes one, in its own era
        year = int(m.group(1))
        norm = f"{year - 543 if year >= 2400 else year}-{m.group(2)}-{m.group(3)}"
        spans.append((m.start(), Value("date", written[m.start():m.end()], norm)))
    for m in _FIGURES.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(3)), _era(m.group(4))
        if 1 <= day <= 31 and 1 <= month <= 12:
            spans.append((m.start(), Value("date", written[m.start():m.end()],
                                           _norm(year, month, day))))
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
    for m in _TH_AMOUNT.finditer(text):
        try:
            amount = Decimal(m.group(1).replace(",", "")) * _TH_SCALE.get(m.group(2) or "", 1)
        except InvalidOperation:
            continue
        spans.append((m.start(), Value("amount", written[m.start():m.end()],
                                       f"{_TH_CURRENCY[m.group(3)]} {amount:.2f}")))
    for m in _TH_DATE.finditer(text):
        day, month, year = int(m.group(1)), _TH_MONTH[m.group(2)], _era(m.group(3))
        if 1 <= day <= 31:  # what it couldn't take as the year is no part of the date
            end = m.end() if year else m.end(2)
            spans.append((m.start(), Value("date", written[m.start():end].strip(),
                                           _norm(year, month, day))))
    for _, value in sorted(spans, key=lambda s: s[0]):
        values.setdefault((value.kind, value.norm), value)
    return list(values.values())


NEAR = 20  # years from this one that two digits after a Thai month may name, at most


def _era(given: str | None) -> str | None:
    """A year as Thai writes it, in the common era: one of the Buddhist era, 543 years on, or
    only its last two digits, as 69 is 2569 and so 2026; one already in the common era as it is.
    Two digits that make no year near this one are none, such as a count after the month."""
    if not given:
        return None
    given = given.translate(_TH_DIGITS)
    year = int(given) + (2500 if len(given) == 2 else 0)
    year = year - 543 if year >= 2400 else year
    if len(given) == 2 and abs(year - date.today().year) > NEAR:
        return None
    return str(year)


def _norm(year: str | None, month: int, day: int) -> str:
    return f"{year}-{month:02d}-{day:02d}" if year else f"--{month:02d}-{day:02d}"


def unmatched(values: list[Value], sources: list[Value]) -> list[Value]:
    """The values that match none of the sources."""
    return [v for v in values if not any(v.matches(s) for s in sources)]
