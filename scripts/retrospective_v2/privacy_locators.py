"""Shared deterministic locator and credential patterns for privacy validators."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Mapping
from itertools import chain, islice
from operator import itemgetter
import re
from typing import Any, Iterable, Iterator


_FORBIDDEN_INVISIBLE_RE = re.compile(
    r"[\x00-\x1F\x7F-\x9F\u00AD\u034F\u061C\u115F-\u1160"
    r"\u17B4-\u17B5\u180B-\u180F\u200B-\u200F\u202A-\u202E"
    r"\u2060-\u206F\u3164\uFE00-\uFE0F\uFEFF\uFFA0\uFFF0-\uFFF8"
    r"\U0001BCA0-\U0001BCAF\U0001D173-\U0001D17A"
    r"\U000E0000-\U000E0FFF]"
)


def is_forbidden_invisible_character(character: str) -> bool:
    """Return whether one character is a control or default-ignorable codepoint."""

    return _FORBIDDEN_INVISIBLE_RE.fullmatch(character) is not None


def contains_forbidden_invisible_character(value: str) -> bool:
    """Return whether text contains a hidden character forbidden in model output."""

    return _FORBIDDEN_INVISIBLE_RE.search(value) is not None


def has_hidden_model_character(value: str) -> bool:
    """Return whether normalized model text retains a forbidden character."""

    return contains_forbidden_invisible_character(" ".join(value.split()))


def normalize_overlap_text(value: str) -> str:
    """Normalize source comparison text without retaining invisible codepoints."""

    return _FORBIDDEN_INVISIBLE_RE.sub("", " ".join(value.split())).casefold()


def normalize_model_result_strings(value: Any) -> Any:
    """Return a result tree whose string values use canonical single-line spacing."""

    match value:
        case str():
            return " ".join(value.split())
        case Mapping():
            return {
                key: normalize_model_result_strings(item) for key, item in value.items()
            }
        case list():
            return [normalize_model_result_strings(item) for item in value]
        case _:
            return value


BARE_PRIVATE_LOCATOR_RE = re.compile(
    r"(?i)\b(?:(?:localhost|(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"(?:[a-z0-9-]+\.)+(?:corp|home|internal|intranet|lan|local))"
    r"(?::\d{1,5})?|(?=[a-z0-9-]{1,63}:\d{1,5}\b)"
    r"(?:(?=[a-z0-9-]*-)|"
    r"(?=(?:host|node|server)(?:[a-z0-9-]*[a-z-]|[0-9]+):))"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?:\d{1,5})"
    r"(?:/[^\s<>\"']*)?"
)
BARE_FQDN_RE = re.compile(
    r"(?i)(?<![a-z0-9_@-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})"
    r"(?::\d{1,5})?(?:/[^\s<>\"']*)?(?![a-z0-9_-])"
)
URI_LOCATOR_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])(?<![^\W_])"
    r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']*"
)
SCP_STYLE_LOCATOR_RE = re.compile(
    r"(?<![A-Z0-9._%+-])"
    r"[A-Z0-9._%+-]+@"
    r"(?:\[[0-9A-F:.%_-]+\]|"
    r"[A-Z0-9](?:[A-Z0-9.-]{0,251}[A-Z0-9])?)"
    r":[^\s<>\"'`]*",
    re.ASCII | re.IGNORECASE,
)
EMAIL_RE = re.compile(
    r"(?<![a-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"
    r"|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?![.:])"
    r")"
    r"(?![a-z0-9-])",
    re.ASCII | re.IGNORECASE,
)
INTERNATIONAL_PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9])\+[0-9() .-]{5,40}[0-9](?![A-Za-z0-9])",
    re.ASCII,
)
PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?<![0-9][() .-])"
    r"[0-9(][0-9() .-]{8,40}[0-9]"
    r"(?![A-Za-z0-9_-])(?![() .-][0-9])",
    re.ASCII,
)
_DATE_PREFIXED_NUMERIC_RE = re.compile(
    r"(?:19|20)[0-9]{2}(?P<date_separator>[-.])"
    r"(?:0[1-9]|1[0-2])(?P=date_separator)"
    r"(?:0[1-9]|[12][0-9]|3[01])(?:[^0-9]|\Z)",
    re.ASCII,
)
_DOTTED_NUMERIC_VERSION_RE = re.compile(
    r"[0-9]+(?:\.[0-9]+){3,}",
    re.ASCII,
)
_PHONE_FIELD_PATTERN_TEXT = (
    r"\b(?:(?:call|phone|tel|telephone|mobile)"
    r"(?:[ _-]?(?:number|no))?|contact(?:[ _-]?(?:phone|number|no))?)"
)
_SHORT_PHONE_VALUE_PATTERN_TEXT = (
    r"(?![0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9]))"
    r"[0-9(][0-9() .-]{5,40}[0-9](?![A-Za-z0-9_-])"
)
CONTEXTUAL_SHORT_PHONE_RE = re.compile(
    _PHONE_FIELD_PATTERN_TEXT
    + r"[ \t]+(?P<phone>"
    + _SHORT_PHONE_VALUE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
BARE_STANDARD_SSN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?<![0-9]-)(?P<personal>"
    r"(?!(?:000|666|9[0-9]{2})-[0-9]{2}-[0-9]{4})"
    r"(?![0-9]{3}-00-[0-9]{4})(?![0-9]{3}-[0-9]{2}-0000)"
    r"[0-9]{3}-[0-9]{2}-[0-9]{4})(?![A-Za-z0-9])(?!-[0-9])",
    re.ASCII,
)
BARE_PAYMENT_CARD_RE = re.compile(
    r"(?<![A-Za-z0-9])(?<![0-9][ -])"
    r"(?P<personal>[0-9](?:[ -]?[0-9]){12,18})"
    r"(?![A-Za-z0-9])(?![ -][0-9])",
    re.ASCII,
)
BARE_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<personal>[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30})"
    r"(?![A-Za-z0-9])",
    re.ASCII | re.IGNORECASE,
)
# SWIFT IBAN Registry Release 102 (June 2026).
# https://www.swift.com/sites/default/files/files/iban_registry.pdf
_IBAN_LENGTH_BY_COUNTRY = {
    "AD": 24,
    "AE": 23,
    "AL": 28,
    "AT": 20,
    "AZ": 28,
    "BA": 20,
    "BE": 16,
    "BG": 22,
    "BH": 22,
    "BI": 27,
    "BR": 29,
    "BY": 28,
    "CH": 21,
    "CR": 22,
    "CY": 28,
    "CZ": 24,
    "DE": 22,
    "DJ": 27,
    "DK": 18,
    "DO": 28,
    "EE": 20,
    "EG": 29,
    "ES": 24,
    "FI": 18,
    "FK": 18,
    "FO": 18,
    "FR": 27,
    "GB": 22,
    "GE": 22,
    "GI": 23,
    "GL": 18,
    "GR": 27,
    "GT": 28,
    "HN": 28,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IL": 23,
    "IQ": 23,
    "IS": 26,
    "IT": 27,
    "JO": 30,
    "KW": 30,
    "KZ": 20,
    "LB": 28,
    "LC": 32,
    "LI": 21,
    "LT": 20,
    "LU": 20,
    "LV": 21,
    "LY": 25,
    "MC": 27,
    "MD": 24,
    "ME": 22,
    "MK": 19,
    "MN": 20,
    "MR": 27,
    "MT": 31,
    "MU": 30,
    "NI": 28,
    "NL": 18,
    "NO": 15,
    "OM": 23,
    "PK": 24,
    "PL": 28,
    "PS": 29,
    "PT": 25,
    "QA": 29,
    "RO": 24,
    "RS": 22,
    "RU": 33,
    "SA": 24,
    "SC": 31,
    "SD": 18,
    "SE": 24,
    "SI": 19,
    "SK": 24,
    "SM": 27,
    "SO": 23,
    "ST": 25,
    "SV": 28,
    "TL": 23,
    "TN": 24,
    "TR": 26,
    "UA": 29,
    "VA": 22,
    "VG": 24,
    "XK": 20,
    "YE": 30,
}


def _grouped_iban_country_pattern(country: str, length: int) -> str:
    full_groups, final_group_length = divmod(length - 4, 4)
    final_group = (
        rf"[ \t]+[A-Z0-9]{{{final_group_length}}}" if final_group_length else ""
    )
    return (
        country
        + r"[0-9]{2}"
        + rf"(?:[ \t]+[A-Z0-9]{{4}}){{{full_groups}}}"
        + final_group
    )


_GROUPED_IBAN_PATTERN_TEXT = "|".join(
    _grouped_iban_country_pattern(country, length)
    for country, length in _IBAN_LENGTH_BY_COUNTRY.items()
)
BARE_GROUPED_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<personal>(?:"
    + _GROUPED_IBAN_PATTERN_TEXT
    + r"))(?![A-Za-z0-9])",
    re.ASCII | re.IGNORECASE,
)
_LUHN_DOUBLED_DIGITS = (0, 2, 4, 6, 8, 1, 3, 5, 7, 9)
_PERSONAL_SUBJECT_PATTERN_TEXT = (
    r"(?:account|client|customer|employee|organization|person|tenant|user)"
)
_PERSONAL_CAMEL_SUBJECT_PATTERN_TEXT = (
    r"(?:account|Account|client|Client|customer|Customer|employee|Employee|"
    r"organization|Organization|person|Person|tenant|Tenant|user|User)"
)
_PERSONAL_POSSESSIVE_PATTERN_TEXT = r"(?:['\u2019]s)?"
_PERSONAL_NAME_FIELD_PATTERN_TEXT = (
    r"(?:nickname|surname|(?:(?:display|family|first|full|given|last|legal|"
    r"maiden|middle|preferred)[_ -]+)?name)"
)
_PERSONAL_CONTEXTUAL_NAME_FIELD_PATTERN_TEXT = (
    r"(?:"
    + _PERSONAL_NAME_FIELD_PATTERN_TEXT
    + r"|(?-i:(?:display|Display|family|Family|first|First|full|Full|given|Given|"
    r"last|Last|legal|Legal|maiden|Maiden|middle|Middle|preferred|Preferred)Name))"
)
_PERSONAL_BIRTH_DATE_FIELD_PATTERN_TEXT = (
    r"(?:dob|date[_ -]+of[_ -]+birth|birth[_ -]?(?:date|day)|"
    r"(?-i:(?:dateOfBirth|DateOfBirth)))"
)
_LABELED_SENSITIVE_NUMBER_FIELD_PATTERN_TEXT = (
    r"(?:ssn|social[_ -]?security(?:[_ -]?(?:number|no))?|"
    r"national[_ -]?(?:insurance|identity)(?:[_ -]?(?:number|no|id))?|"
    r"(?:tax(?:payer)?[_ -]?(?:identification|id))(?:[_ -]?(?:number|no))?|"
    r"passport(?:[_ -]?(?:number|no|id))?|"
    r"driver(?:['\u2019]s)?[_ -]?licen[cs]e(?:[_ -]?(?:number|no|id))?|"
    r"(?:credit|debit|payment)[_ -]?card(?:[_ -]?(?:number|no))?|"
    r"card[_ -]?(?:number|no)|"
    r"(?:bank[_ -]?)?account[_ -]?(?:number|no)|"
    r"routing[_ -]?(?:number|no)|iban|"
    r"(?-i:(?:socialSecurityNumber|nationalInsuranceNumber|nationalId|taxId|"
    r"passport(?:Number|Id)|driversLicenseNumber|creditCard(?:Number)?|"
    r"debitCard(?:Number)?|paymentCard(?:Number)?|cardNumber|"
    r"bankAccountNumber|accountNumber|routingNumber)))"
)
_LABELED_PERSONAL_NAME_FIELD_PATTERN_TEXT = (
    r"\b(?:"
    + _PERSONAL_SUBJECT_PATTERN_TEXT
    + _PERSONAL_POSSESSIVE_PATTERN_TEXT
    + r"(?:[._ -]+)?"
    + _PERSONAL_CONTEXTUAL_NAME_FIELD_PATTERN_TEXT
    + r")"
)
_LABELED_PERSONAL_FIELD_PATTERN_TEXT = (
    r"\b(?:"
    + _PERSONAL_SUBJECT_PATTERN_TEXT
    + _PERSONAL_POSSESSIVE_PATTERN_TEXT
    + r"[_ -]?"
    r"(?:id|address|" + _PERSONAL_BIRTH_DATE_FIELD_PATTERN_TEXT + r")|"
    r"(?-i:"
    + _PERSONAL_CAMEL_SUBJECT_PATTERN_TEXT
    + r"(?:Id|Address|DOB|Dob|DateOfBirth))|"
    r"(?:billing|client|customer|employee|home|mailing|person|postal|residential|"
    r"shipping|tenant|user)[_ -]?address|"
    + _PERSONAL_BIRTH_DATE_FIELD_PATTERN_TEXT
    + r"|"
    + _LABELED_SENSITIVE_NUMBER_FIELD_PATTERN_TEXT
    + r")"
)


def _markdown_labeled_field_assignment_pattern(
    field_pattern: str, *, markdown_group: str
) -> str:
    markdown_field_pattern = field_pattern.removeprefix(r"\b")
    markdown_reference = rf"(?P={markdown_group})"
    return (
        rf"(?P<{markdown_group}>\*\*|__)[ \t]*"
        + markdown_field_pattern
        + r"(?:[ \t]*(?:=|:)[ \t]*"
        + markdown_reference
        + r"|[ \t]*"
        + markdown_reference
        + r"[ \t]*(?:=|:))"
    )


def _markdown_complete_labeled_value_pattern(
    field_pattern: str, *, markdown_group: str
) -> str:
    markdown_field_pattern = field_pattern.removeprefix(r"\b")
    return (
        rf"(?P<{markdown_group}>\*\*|__)[ \t]*"
        + markdown_field_pattern
        + r"[ \t]*(?:=|:)[ \t]*(?P<value>[^\r\n]*?)[ \t]*"
        + rf"(?P={markdown_group})"
    )


def _labeled_field_assignment_pattern(
    field_pattern: str, *, markdown_group: str
) -> str:
    return (
        r"(?:"
        + _markdown_labeled_field_assignment_pattern(
            field_pattern,
            markdown_group=markdown_group,
        )
        + r"|['\"]?"
        + field_pattern
        + r"['\"]?[ \t]*(?:=|:))"
    )


def _narrative_labeled_field_assignment_pattern(field_pattern: str) -> str:
    return r"['\"]?" + field_pattern + r"['\"]?[ \t]+(?:is|was|set[ \t]+to)\b"


LABELED_PHONE_VALUE_RE = re.compile(
    _labeled_field_assignment_pattern(
        _PHONE_FIELD_PATTERN_TEXT,
        markdown_group="phone_markdown",
    )
    + r"[ \t]*(?P<phone_quote>['\"]?)(?P<phone>"
    + _SHORT_PHONE_VALUE_PATTERN_TEXT
    + r")(?P=phone_quote)",
    re.ASCII | re.IGNORECASE,
)
NARRATIVE_LABELED_PHONE_VALUE_RE = re.compile(
    _narrative_labeled_field_assignment_pattern(_PHONE_FIELD_PATTERN_TEXT)
    + r"[ \t]*(?P<phone_quote>['\"]?)(?P<phone>"
    + _SHORT_PHONE_VALUE_PATTERN_TEXT
    + r")(?P=phone_quote)",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_COMPLETE_PHONE_VALUE_RE = re.compile(
    r"(?P<phone_complete_markdown>\*\*|__)[ \t]*"
    + _PHONE_FIELD_PATTERN_TEXT.removeprefix(r"\b")
    + r"[ \t]*(?:=|:)[ \t]*"
    r"(?P<phone_complete_quote>['\"]?)(?P<phone>"
    + _SHORT_PHONE_VALUE_PATTERN_TEXT
    + r")(?P=phone_complete_quote)[ \t]*(?P=phone_complete_markdown)",
    re.ASCII | re.IGNORECASE,
)
CONTEXTUAL_PHONE_PATTERNS = (
    CONTEXTUAL_SHORT_PHONE_RE,
    LABELED_PHONE_VALUE_RE,
    NARRATIVE_LABELED_PHONE_VALUE_RE,
    MARKDOWN_COMPLETE_PHONE_VALUE_RE,
)
PHONE_PATTERNS = (
    INTERNATIONAL_PHONE_RE,
    PHONE_RE,
    *CONTEXTUAL_PHONE_PATTERNS,
)
PHONE_DIGIT_COUNT_BOUNDS = {
    INTERNATIONAL_PHONE_RE: (7, 15),
    PHONE_RE: (10, 12),
    **dict.fromkeys(CONTEXTUAL_PHONE_PATTERNS, (7, 15)),
}


_REDACTED_VALUE_NAME_PATTERN_TEXT = (
    r"(?:REDACTED_CODE|REDACTED_CREDENTIAL|REDACTED_EMAIL|"
    r"REDACTED_IDENTIFIER|REDACTED_INTERNAL_ADDRESS|REDACTED_INTERNAL_HOST|"
    r"REDACTED_IP_ADDRESS|REDACTED_ORIGINAL_PROMPT|REDACTED_PATH|"
    r"REDACTED_PERSONAL_IDENTIFIER|REDACTED_PRIVATE_KEY|REDACTED_RAW_ID|"
    r"REDACTED_SECRET|REDACTED_TOOL_OUTPUT|REDACTED_URL|REDACTED)"
)
_REDACTED_VALUE_PATTERN_TEXT = r"\[" + _REDACTED_VALUE_NAME_PATTERN_TEXT + r"\]"
_REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT = r"\[REDACTED(?:_[A-Z0-9]+)*\]"
_PERSONAL_VALUE_CAPTURE_PATTERN_TEXT = (
    r"[ \t]*(?:"
    r'\\"(?P<escaped_double_quoted_value>[^\r\n]*?)\\"'
    r"(?P<escaped_double_trailing_value>[^\r\n,)}\]]*+)|"
    r'"(?P<double_quoted_value>(?:\\[^\r\n]|[^"\\\r\n])++)"'
    r"(?P<double_trailing_value>[^\r\n,)}\]]*+)|"
    r"'(?P<single_quoted_value>(?:\\[^\r\n]|[^'\\\r\n])++)'"
    r"(?P<single_trailing_value>[^\r\n,)}\]]*+)|"
    r"(?P<value>(?:"
    + _REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT
    + r"(?:\([^()\r\n]*\)|[^\r\n,)}\]])*+|"
    r"(?:\([^()\r\n]*\)|[^\r\n,)}\]])++)))"
)
_ADDRESS_COMPONENT_FIELD_PATTERN_TEXT = (
    r"(?:apt|apartment|unit|suite|city|state|province|region|county|country|"
    r"address[_ -]+line[_ -]*[2-9]|post(?:al)?[_ -]+code|postcode|"
    r"zip(?:[_ -]+code)?)\b"
)
_NAME_TRAILING_METADATA_KEY_PATTERN_TEXT = (
    r"(?:note|notes|state|status|verification|verified)"
)
_NAME_TRAILING_METADATA_FIELD_PATTERN_TEXT = (
    r"(?:\\?['\"]"
    + _NAME_TRAILING_METADATA_KEY_PATTERN_TEXT
    + r"\\?['\"]|"
    + _NAME_TRAILING_METADATA_KEY_PATTERN_TEXT
    + r"\b)"
)
_NAME_TRAILING_METADATA_PATTERN_TEXT = (
    _NAME_TRAILING_METADATA_FIELD_PATTERN_TEXT + r"[ \t]*(?:(?:=|:)[ \t]*)?"
)
_ADDRESS_TRAILING_METADATA_PATTERN_TEXT = (
    r"(?:note|notes|status|verification|verified)\b"
)
_ADDRESS_UNQUOTED_VALUE_UNIT_PATTERN_TEXT = (
    r"(?!,[ \t]*" + _ADDRESS_TRAILING_METADATA_PATTERN_TEXT + r")"
    r"(?!,[ \t]*['\"]?(?!"
    + _ADDRESS_COMPONENT_FIELD_PATTERN_TEXT
    + r"['\"]?[ \t]*(?:=|:))[A-Za-z_][A-Za-z0-9_ -]{0,63}['\"]?"
    r"[ \t]*(?:=|:))(?:\([^()\r\n]*\)|[^\r\n)}\]])"
)
_ADDRESS_VALUE_CAPTURE_PATTERN_TEXT = (
    r"[ \t]*(?:"
    r'\\"(?P<escaped_double_quoted_value>[^\r\n]*?)\\"'
    r"(?P<escaped_double_trailing_value>[^\r\n,)}\]]*+)|"
    r'"(?P<double_quoted_value>(?:\\[^\r\n]|[^"\\\r\n])++)"'
    r"(?P<double_trailing_value>[^\r\n,)}\]]*+)|"
    r"'(?P<single_quoted_value>(?:\\[^\r\n]|[^'\\\r\n])++)'"
    r"(?P<single_trailing_value>[^\r\n,)}\]]*+)|"
    r"(?P<value>(?:"
    + _REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT
    + r"(?:"
    + _ADDRESS_UNQUOTED_VALUE_UNIT_PATTERN_TEXT
    + r")*+|(?:"
    + _ADDRESS_UNQUOTED_VALUE_UNIT_PATTERN_TEXT
    + r")++)))"
)
_NAME_COMPONENT_FIELD_PATTERN_TEXT = r"[A-Za-z_][A-Za-z0-9_ -]{0,63}"
_NAME_UNQUOTED_VALUE_UNIT_PATTERN_TEXT = (
    r"(?!,[ \t]*(?:['\"]?"
    + _NAME_COMPONENT_FIELD_PATTERN_TEXT
    + r"['\"]?[ \t]*(?:=|:)|"
    + _NAME_TRAILING_METADATA_PATTERN_TEXT
    + r"))(?:\([^()\r\n]*\)|[^\r\n)}\]])"
)
_NAME_VALUE_CAPTURE_PATTERN_TEXT = (
    r"[ \t]*(?:"
    r'\\"(?P<escaped_double_quoted_value>[^\r\n]*?)\\"'
    r"(?P<escaped_double_trailing_value>[^\r\n,)}\]]*+)|"
    r'"(?P<double_quoted_value>(?:\\[^\r\n]|[^"\\\r\n])++)"'
    r"(?P<double_trailing_value>[^\r\n,)}\]]*+)|"
    r"'(?P<single_quoted_value>(?:\\[^\r\n]|[^'\\\r\n])++)'"
    r"(?P<single_trailing_value>[^\r\n,)}\]]*+)|"
    r"(?P<value>(?:"
    + _REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT
    + r"(?:"
    + _NAME_UNQUOTED_VALUE_UNIT_PATTERN_TEXT
    + r")*+|(?:"
    + _NAME_UNQUOTED_VALUE_UNIT_PATTERN_TEXT
    + r")++)))"
)
LABELED_PERSONAL_VALUE_RE = re.compile(
    _labeled_field_assignment_pattern(
        _LABELED_PERSONAL_FIELD_PATTERN_TEXT,
        markdown_group="personal_markdown",
    )
    + _PERSONAL_VALUE_CAPTURE_PATTERN_TEXT,
    re.ASCII | re.IGNORECASE,
)
LABELED_PERSONAL_ID_RE = LABELED_PERSONAL_VALUE_RE
LABELED_PERSONAL_NAME_VALUE_RE = re.compile(
    _labeled_field_assignment_pattern(
        _LABELED_PERSONAL_NAME_FIELD_PATTERN_TEXT,
        markdown_group="personal_name_markdown",
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT,
    re.ASCII | re.IGNORECASE,
)
NARRATIVE_LABELED_PERSONAL_VALUE_RE = re.compile(
    _narrative_labeled_field_assignment_pattern(_LABELED_PERSONAL_FIELD_PATTERN_TEXT)
    + _PERSONAL_VALUE_CAPTURE_PATTERN_TEXT,
    re.ASCII | re.IGNORECASE,
)
NARRATIVE_LABELED_PERSONAL_NAME_VALUE_RE = re.compile(
    _narrative_labeled_field_assignment_pattern(
        _LABELED_PERSONAL_NAME_FIELD_PATTERN_TEXT
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT,
    re.ASCII | re.IGNORECASE,
)
_UNAMBIGUOUS_BARE_LABELED_NAME_FIELD_PATTERN_TEXT = (
    r"\b(?:surname|(?:family|first|full|given|last|legal|maiden|middle|preferred)"
    r"[_ -]+name|(?-i:(?:family|first|full|given|last|legal|maiden|middle|"
    r"preferred|Family|First|Full|Given|Last|Legal|Maiden|Middle|Preferred)Name))"
)
_AMBIGUOUS_BARE_LABELED_NAME_FIELD_PATTERN_TEXT = (
    r"\b(?:nickname|display[_ -]+name|(?-i:(?:display|Display)Name))"
)
_BARE_LABELED_NAME_FIELD_PATTERN_TEXT = (
    r"\b(?:nickname|surname|(?:display|family|first|full|given|last|legal|maiden|"
    r"middle|preferred)[_ -]+name|(?-i:(?:display|family|first|full|given|last|"
    r"legal|maiden|middle|preferred|Display|Family|First|Full|Given|Last|Legal|"
    r"Maiden|Middle|Preferred)Name))"
)
_BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT = (
    r"\b(?:address|street[_ -]+address|(?-i:(?:street|Street)Address))"
)
BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?:(?:\A|(?<=[\r\n]))[ \t]*(?:[-*+>][ \t]+)?|"
    r"(?<=[.!?;:,([{'\"])[ \t]*)"
    r"(?P<personal>"
    + _labeled_field_assignment_pattern(
        _UNAMBIGUOUS_BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="bare_name_markdown",
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
BOUNDARY_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE = re.compile(
    r"(?:(?:\A|(?<=[\r\n]))[ \t]*(?:[-*+>][ \t]+)?|"
    r"(?<=[.!?;])[ \t]+|\b(?:observed|recorded|reported)[ \t]+)"
    r"(?P<personal>"
    + _labeled_field_assignment_pattern(
        _AMBIGUOUS_BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="boundary_bare_ambiguous_name_markdown",
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
BARE_LABELED_ADDRESS_VALUE_RE = re.compile(
    r"(?:(?:\A|(?<=[\r\n]))[ \t]*(?:[-*+>][ \t]+)?|"
    r"(?<=[.!?;:,([{'\"])[ \t]*)"
    r"(?P<personal>"
    + _labeled_field_assignment_pattern(
        _BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT,
        markdown_group="bare_address_markdown",
    )
    + _ADDRESS_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
NARRATIVE_BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_*])"
    r"(?P<personal>"
    + _narrative_labeled_field_assignment_pattern(
        _UNAMBIGUOUS_BARE_LABELED_NAME_FIELD_PATTERN_TEXT
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
BOUNDARY_NARRATIVE_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE = re.compile(
    r"(?:(?:\A|(?<=[\r\n]))[ \t]*(?:[-*+>][ \t]+)?|"
    r"(?<=[.!?;])[ \t]+|\b(?:observed|recorded|reported)[ \t]+)"
    r"(?P<personal>"
    + _narrative_labeled_field_assignment_pattern(
        _AMBIGUOUS_BARE_LABELED_NAME_FIELD_PATTERN_TEXT
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_*])"
    r"(?P<personal>"
    + _narrative_labeled_field_assignment_pattern(
        _BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT
    )
    + _ADDRESS_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)


def _markdown_narrative_bare_value_unit(
    *, markdown_group: str, metadata_pattern: str
) -> str:
    return (
        r"(?:\([^()\r\n]*\)|(?!(?P="
        + markdown_group
        + r")|,[ \t]*"
        + metadata_pattern
        + r")[^\r\n(])"
    )


def _markdown_complete_narrative_bare_value_pattern(
    field_pattern: str, *, markdown_group: str, metadata_pattern: str
) -> str:
    value_unit = _markdown_narrative_bare_value_unit(
        markdown_group=markdown_group,
        metadata_pattern=metadata_pattern,
    )
    return (
        rf"(?P<{markdown_group}>\*\*|__|\*|_)[ \t]*"
        r"(?P<personal>"
        + field_pattern.removeprefix(r"\b")
        + r"[ \t]+(?:is|was|set[ \t]+to)\b[ \t]*(?P<value>"
        + value_unit
        + r"*+))"
        r"(?:[ \t]*,[ \t]*"
        + metadata_pattern
        + r"[^\r\n]*?)?[ \t]*(?P="
        + markdown_group
        + r")"
    )


def _malformed_markdown_narrative_bare_value_pattern(
    field_pattern: str, *, markdown_group: str, metadata_pattern: str
) -> str:
    value_unit = _markdown_narrative_bare_value_unit(
        markdown_group=markdown_group,
        metadata_pattern=metadata_pattern,
    )
    return (
        rf"(?P<personal>(?P<{markdown_group}>\*\*|__|\*|_)[ \t]*"
        + field_pattern.removeprefix(r"\b")
        + r"[ \t]+(?:is|was|set[ \t]+to)\b[ \t]*(?P<value>"
        + value_unit
        + r"*+)"
        r"(?:[ \t]*,[ \t]*"
        + metadata_pattern
        + r"[^\r\n]*+)?(?P<malformed_trailing_value>[^\r\n]*+))"
    )


MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_NAME_VALUE_RE = re.compile(
    _markdown_complete_narrative_bare_value_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="complete_narrative_bare_name_markdown",
        metadata_pattern=_NAME_TRAILING_METADATA_PATTERN_TEXT,
    ),
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE = re.compile(
    _markdown_complete_narrative_bare_value_pattern(
        _BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT,
        markdown_group="complete_narrative_bare_address_markdown",
        metadata_pattern=_ADDRESS_TRAILING_METADATA_PATTERN_TEXT,
    ),
    re.ASCII | re.IGNORECASE,
)
MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_NAME_VALUE_RE = re.compile(
    _malformed_markdown_narrative_bare_value_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="malformed_narrative_bare_name_markdown",
        metadata_pattern=_NAME_TRAILING_METADATA_PATTERN_TEXT,
    ),
    re.ASCII | re.IGNORECASE,
)
MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE = re.compile(
    _malformed_markdown_narrative_bare_value_pattern(
        _BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT,
        markdown_group="malformed_narrative_bare_address_markdown",
        metadata_pattern=_ADDRESS_TRAILING_METADATA_PATTERN_TEXT,
    ),
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_labeled_field_assignment_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="markdown_bare_name_markdown",
    )
    + _NAME_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_BARE_LABELED_ADDRESS_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_labeled_field_assignment_pattern(
        _BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT,
        markdown_group="markdown_bare_address_markdown",
    )
    + _ADDRESS_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_COMPLETE_LABELED_PERSONAL_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_complete_labeled_value_pattern(
        _LABELED_PERSONAL_FIELD_PATTERN_TEXT,
        markdown_group="complete_personal_markdown",
    )
    + r")",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_COMPLETE_LABELED_PERSONAL_NAME_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_complete_labeled_value_pattern(
        _LABELED_PERSONAL_NAME_FIELD_PATTERN_TEXT,
        markdown_group="complete_personal_name_markdown",
    )
    + r")",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_complete_labeled_value_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="complete_bare_name_markdown",
    )
    + r")",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_COMPLETE_BARE_LABELED_ADDRESS_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_complete_labeled_value_pattern(
        _BARE_LABELED_ADDRESS_FIELD_PATTERN_TEXT,
        markdown_group="complete_bare_address_markdown",
    )
    + r")",
    re.ASCII | re.IGNORECASE,
)
_CANONICAL_REDACTED_VALUE_RE = re.compile(r"\A" + _REDACTED_VALUE_PATTERN_TEXT + r"\Z")
_REDACTED_PLACEHOLDER_SHAPE_RE = re.compile(_REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT)
_ADDRESS_LABELED_VALUE_PATTERNS = (
    BARE_LABELED_ADDRESS_VALUE_RE,
    NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE,
    MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE,
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE,
    MARKDOWN_BARE_LABELED_ADDRESS_VALUE_RE,
    MARKDOWN_COMPLETE_BARE_LABELED_ADDRESS_VALUE_RE,
)
_NAME_LABELED_VALUE_PATTERNS = (
    LABELED_PERSONAL_NAME_VALUE_RE,
    NARRATIVE_LABELED_PERSONAL_NAME_VALUE_RE,
    BARE_LABELED_NAME_VALUE_RE,
    BOUNDARY_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE,
    NARRATIVE_BARE_LABELED_NAME_VALUE_RE,
    BOUNDARY_NARRATIVE_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_NAME_VALUE_RE,
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_LABELED_PERSONAL_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE,
)
PERSONAL_LABELED_VALUE_PATTERNS = (
    LABELED_PERSONAL_VALUE_RE,
    NARRATIVE_LABELED_PERSONAL_VALUE_RE,
    LABELED_PERSONAL_NAME_VALUE_RE,
    NARRATIVE_LABELED_PERSONAL_NAME_VALUE_RE,
    BARE_LABELED_NAME_VALUE_RE,
    BOUNDARY_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE,
    BARE_LABELED_ADDRESS_VALUE_RE,
    NARRATIVE_BARE_LABELED_NAME_VALUE_RE,
    BOUNDARY_NARRATIVE_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE,
    NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE,
    MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE,
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_NAME_VALUE_RE,
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE,
    MARKDOWN_BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_BARE_LABELED_ADDRESS_VALUE_RE,
    MARKDOWN_COMPLETE_LABELED_PERSONAL_VALUE_RE,
    MARKDOWN_COMPLETE_LABELED_PERSONAL_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_BARE_LABELED_ADDRESS_VALUE_RE,
)
_NON_ADDRESS_PERSONAL_LABELED_VALUE_PATTERNS = tuple(
    filter(
        lambda pattern: pattern
        not in _ADDRESS_LABELED_VALUE_PATTERNS + _NAME_LABELED_VALUE_PATTERNS,
        PERSONAL_LABELED_VALUE_PATTERNS,
    )
)
PERSONAL_IDENTIFIER_GROUPS = {
    **dict.fromkeys(CONTEXTUAL_PHONE_PATTERNS, "phone"),
    BARE_STANDARD_SSN_RE: "personal",
    BARE_PAYMENT_CARD_RE: "personal",
    BARE_IBAN_RE: "personal",
    BARE_GROUPED_IBAN_RE: "personal",
    LABELED_PERSONAL_NAME_VALUE_RE: 0,
    NARRATIVE_LABELED_PERSONAL_NAME_VALUE_RE: 0,
    BARE_LABELED_NAME_VALUE_RE: "personal",
    BOUNDARY_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE: "personal",
    BARE_LABELED_ADDRESS_VALUE_RE: "personal",
    NARRATIVE_BARE_LABELED_NAME_VALUE_RE: "personal",
    BOUNDARY_NARRATIVE_BARE_LABELED_AMBIGUOUS_NAME_VALUE_RE: "personal",
    NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_NAME_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE: "personal",
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_NAME_VALUE_RE: "personal",
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE: "personal",
    MARKDOWN_BARE_LABELED_NAME_VALUE_RE: "personal",
    MARKDOWN_BARE_LABELED_ADDRESS_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_LABELED_PERSONAL_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_LABELED_PERSONAL_NAME_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_BARE_LABELED_ADDRESS_VALUE_RE: "personal",
}
LABELED_INTERNAL_HOST_RE = re.compile(
    r"\b(?:host|hostname|node|server)\s*(?:=|:)\s*"
    r"(?!\[REDACTED)(?=[a-z0-9._-]*[a-z._-])"
    r"[a-z0-9][a-z0-9._-]*(?::\d{1,5})?",
    re.ASCII | re.IGNORECASE,
)
UNIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])/(?!/)"
    r"[A-Za-z0-9._~+@%=-]+(?:/[A-Za-z0-9._~+@%=-]+)*"
)
RELATIVE_PATH_RE = re.compile(
    r"(?<![-A-Za-z0-9_.~+@%=/\\])(?:\.{1,2}[/\\])?"
    r"(?:[A-Za-z0-9_.~+@%=-]+[/\\])+[A-Za-z0-9_.~+@%=-]+"
    r"(?![A-Za-z0-9_.~+@%=-])"
)
HOME_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])~[/\\]"
    r"(?:[A-Za-z0-9._~+@%=-]+(?:[/\\][A-Za-z0-9._~+@%=-]+)*)?"
)
WINDOWS_PATH_RE = re.compile(
    r"\b[A-Z]:\\(?:[^\\\s\"'<>:|?*]+(?:\\[^\\\s\"'<>:|?*]+)*)?",
    re.ASCII | re.IGNORECASE,
)
UNC_PATH_RE = re.compile(r"\\\\[^\\\s]+\\[^\s\"'<>:|?*]+")
PATH_LOCATOR_PATTERNS = (
    RELATIVE_PATH_RE,
    UNIX_PATH_RE,
    HOME_PATH_RE,
    WINDOWS_PATH_RE,
    UNC_PATH_RE,
)
UUID_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(?![A-Za-z0-9])",
    re.ASCII | re.IGNORECASE,
)
LONG_HEX_ID_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[0-9a-f]{24,})(?![A-Za-z0-9])",
    re.ASCII | re.IGNORECASE,
)
RAW_ID_LABEL_RE = re.compile(
    r"\b(?:session|thread|conversation|turn|message|tool[_ -]?call|request|"
    r"run|job|attempt)[_ -]?(?:id|ref)\s*(?:=|:|#)\s*"
    r"(?![a-z][a-z0-9_]*_ref_v2:)[A-Za-z0-9._:-]{6,}",
    re.ASCII | re.IGNORECASE,
)
RAW_IDENTIFIER_PATTERNS = (UUID_RE, LONG_HEX_ID_RE, RAW_ID_LABEL_RE)
CODE_FENCE_RE = re.compile(r"```[\s\S]*?(?:```|\Z)")
IPV4_CANDIDATE_RE = re.compile(
    r"(?<![0-9A-Za-z.])"
    r"(?P<address>(?:[0-9]{1,3}\.){3}[0-9]{1,3})"
    r"(?::(?P<port>[0-9]{1,5}))?"
    r"(?=$|[^0-9A-Za-z.]|\.(?=$|\s))"
)
IPV6_CANDIDATE_RE = re.compile(
    r"(?:"
    r"(?<![0-9A-Za-z])\[[0-9A-Za-z:.%_-]+\]|"
    r"(?<![0-9A-Za-z_.:%-])(?:[0-9A-Fa-f]{0,4}:){2,}"
    r"(?:[0-9A-Za-z:.%_-]*[0-9A-Za-z:_-])?"
    r")(?=$|[^0-9A-Za-z.]|\.(?=$|[^0-9A-Za-z.]))"
)
MAC_ADDRESS_RE = re.compile(
    r"(?<![0-9A-Za-z])(?<![0-9A-Fa-f]:)(?<![0-9A-Fa-f]-)"
    r"[0-9A-Fa-f]{2}(?P<mac_separator>[:-])"
    r"(?:[0-9A-Fa-f]{2}(?P=mac_separator)){4}[0-9A-Fa-f]{2}"
    r"(?![0-9A-Za-z])(?![:-][0-9A-Fa-f]{2})",
    re.ASCII,
)
_PRIVATE_KEY_LABEL_PATTERN_TEXT = (
    r"(?:(?:[A-Z0-9][A-Z0-9 -]{0,62})\s+)?PRIVATE\s+KEY(?:\s+BLOCK)?"
)
_SAFE_CREDENTIAL_VALUE_PATTERN_TEXT = (
    r"(?:bearer|basic|digest|negotiate|token|api[-_]?key|hmac|"
    r"aws4-hmac-sha256|signature|oauth|mac|"
    r"redacted(?:[_-][a-z0-9]+)*|masked(?:[_-][a-z0-9]+)*|"
    r"missing|omitted|present|unknown|null|none|empty|in|not|required|"
    r"denied|expired|invalid|unavailable|absent|needed|necessary|revoked|"
    r"rotated|budget|count|limit)"
)
_SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT = r"(?=[)\]\}>\"']*\s*+(?:[.,;]\s*+)?+\Z)"
_SAFE_CREDENTIAL_VALUE_ATOM_PATTERN_TEXT = (
    r"(?:"
    + _SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + r"|\["
    + _SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + r"\]|<"
    + _SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + r">|\("
    + _SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + r"\)|\{"
    + _SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + r"\})"
)
_SAFE_CREDENTIAL_VALUE_ENVELOPE_PATTERN_TEXT = (
    _SAFE_CREDENTIAL_VALUE_ATOM_PATTERN_TEXT
    + _SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT
)
_SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT = (
    r"(?!" + _SAFE_CREDENTIAL_VALUE_ENVELOPE_PATTERN_TEXT + r")"
)
_CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT = r"\s*+"
_CREDENTIAL_SPACE_REQUIRED_ATOMIC_PATTERN_TEXT = r"\s++"
_CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT = r"[^\S\r\n]*+"
_CREDENTIAL_SHELL_UNQUOTED_FRAGMENT_PATTERN_TEXT = r"(?:\\[\s\S]|[^\\'\"\s,;])++"
_CREDENTIAL_DOUBLE_QUOTED_FRAGMENT_PATTERN_TEXT = r"\"(?:\\[\s\S]|[^\"\\])*\""
_CREDENTIAL_SINGLE_QUOTED_FRAGMENT_PATTERN_TEXT = r"'(?:\\[\s\S]|[^'\\])*'"
_CREDENTIAL_ADJACENT_SHELL_FRAGMENT_PATTERN_TEXT = (
    r"(?:"
    + _CREDENTIAL_SHELL_UNQUOTED_FRAGMENT_PATTERN_TEXT
    + r"|"
    + _CREDENTIAL_DOUBLE_QUOTED_FRAGMENT_PATTERN_TEXT
    + r"|"
    + _CREDENTIAL_SINGLE_QUOTED_FRAGMENT_PATTERN_TEXT
    + r")"
)
_SAFE_CREDENTIAL_VALUE_TRAILING_MATERIAL_PATTERN_TEXT = (
    _SAFE_CREDENTIAL_VALUE_ATOM_PATTERN_TEXT
    + r"(?:"
    + r"(?:(?!\w)[\s\S])*+\w[^'\"\s,;]*|"
    + r"(?:(?!\w)[\s\S])++\Z)"
)
# Structured fields own their matching quote. A safe quoted value is exempt only
# when no material remains outside that quote in the complete retained value.
_CREDENTIAL_UNQUOTED_VALUE_MATCH_PATTERN_TEXT = (
    _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"(?:"
    + _SAFE_CREDENTIAL_VALUE_TRAILING_MATERIAL_PATTERN_TEXT
    + r"|"
    + _CREDENTIAL_SHELL_UNQUOTED_FRAGMENT_PATTERN_TEXT
    + r")"
)
_SAFE_QUOTED_CREDENTIAL_VALUE_CONTENT_PATTERN_TEXT = (
    _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
    + r"(?:"
    + _SAFE_CREDENTIAL_VALUE_ATOM_PATTERN_TEXT
    + _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
    + r"(?:[.,;]"
    + _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
    + r")?+)?+"
)
_SAFE_DOUBLE_QUOTED_CREDENTIAL_VALUE_PATTERN_TEXT = (
    _SAFE_QUOTED_CREDENTIAL_VALUE_CONTENT_PATTERN_TEXT + r"(?=\"\s*+(?:[.,;]\s*+)?+\Z)"
)
_SAFE_SINGLE_QUOTED_CREDENTIAL_VALUE_PATTERN_TEXT = (
    _SAFE_QUOTED_CREDENTIAL_VALUE_CONTENT_PATTERN_TEXT + r"(?='\s*+(?:[.,;]\s*+)?+\Z)"
)
_DOUBLE_QUOTED_SAFE_VALUE_WITH_TRAILING_MATERIAL_MATCH_PATTERN_TEXT = (
    r"\""
    + _SAFE_QUOTED_CREDENTIAL_VALUE_CONTENT_PATTERN_TEXT
    + r"\"(?=[^\r\n]*\S)[^\r\n]++"
)
_SINGLE_QUOTED_SAFE_VALUE_WITH_TRAILING_MATERIAL_MATCH_PATTERN_TEXT = (
    r"'"
    + _SAFE_QUOTED_CREDENTIAL_VALUE_CONTENT_PATTERN_TEXT
    + r"'(?=[^\r\n]*\S)[^\r\n]++"
)
_DOUBLE_QUOTED_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT = (
    r"(?:"
    + _DOUBLE_QUOTED_SAFE_VALUE_WITH_TRAILING_MATERIAL_MATCH_PATTERN_TEXT
    + r"|\"(?!"
    + _SAFE_DOUBLE_QUOTED_CREDENTIAL_VALUE_PATTERN_TEXT
    + r")(?:\\[\s\S]|[^\"\\])*(?:\""
    + _CREDENTIAL_ADJACENT_SHELL_FRAGMENT_PATTERN_TEXT
    + r"*+|(?=\Z)))"
)
_SINGLE_QUOTED_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT = (
    r"(?:"
    + _SINGLE_QUOTED_SAFE_VALUE_WITH_TRAILING_MATERIAL_MATCH_PATTERN_TEXT
    + r"|'(?!"
    + _SAFE_SINGLE_QUOTED_CREDENTIAL_VALUE_PATTERN_TEXT
    + r")(?:\\[\s\S]|[^'\\])*(?:'"
    + _CREDENTIAL_ADJACENT_SHELL_FRAGMENT_PATTERN_TEXT
    + r"*+|(?=\Z)))"
)
_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT = (
    r"(?:"
    + _DOUBLE_QUOTED_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
    + r"|"
    + _SINGLE_QUOTED_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
    + r"|"
    + _CREDENTIAL_UNQUOTED_VALUE_MATCH_PATTERN_TEXT
    + r")"
)
_SAFE_CREDENTIAL_NARRATIVE_STATUS_PATTERN_TEXT = (
    r"(?:redacted(?:[_-][a-z0-9]+)*|masked(?:[_-][a-z0-9]+)*|"
    r"not\s++(?:required|present|available)|"
    r"missing|omitted|present|unknown|null|none|empty|in|not|required|"
    r"denied|expired|invalid|unavailable|absent|needed|necessary|revoked|rotated)"
)
# Narrative status prose has a different boundary from assignments and headers.
_SAFE_CREDENTIAL_NARRATIVE_CONTINUATION_PATTERN_TEXT = (
    r"\s++(?:before|after|during|for|in|on|when|while|until|from|by|with|"
    r"without|at|because|since|through|throughout|across|within|to)\b[^\r\n]*+"
)
_SAFE_CREDENTIAL_NARRATIVE_PHRASE_PATTERN_TEXT = (
    _SAFE_CREDENTIAL_NARRATIVE_STATUS_PATTERN_TEXT
    + r"(?:"
    + _SAFE_CREDENTIAL_NARRATIVE_CONTINUATION_PATTERN_TEXT
    + r"|"
    + _SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT
    + r")"
)
_SAFE_CREDENTIAL_NARRATIVE_STATUS_LOOKAHEAD_PATTERN_TEXT = (
    r"(?!" + _SAFE_CREDENTIAL_NARRATIVE_PHRASE_PATTERN_TEXT + r")"
)
_DOUBLE_QUOTED_CREDENTIAL_NARRATIVE_MATCH_PATTERN_TEXT = (
    r"(?!\""
    + _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
    + _SAFE_CREDENTIAL_NARRATIVE_PHRASE_PATTERN_TEXT
    + r")"
    + _DOUBLE_QUOTED_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
)
_SINGLE_QUOTED_CREDENTIAL_NARRATIVE_MATCH_PATTERN_TEXT = (
    r"(?!'"
    + _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
    + _SAFE_CREDENTIAL_NARRATIVE_PHRASE_PATTERN_TEXT
    + r")"
    + _SINGLE_QUOTED_CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
)
_CREDENTIAL_NARRATIVE_VALUE_MATCH_PATTERN_TEXT = (
    r"(?:"
    + _DOUBLE_QUOTED_CREDENTIAL_NARRATIVE_MATCH_PATTERN_TEXT
    + r"|"
    + _SINGLE_QUOTED_CREDENTIAL_NARRATIVE_MATCH_PATTERN_TEXT
    + r"|"
    + _SAFE_CREDENTIAL_NARRATIVE_STATUS_LOOKAHEAD_PATTERN_TEXT
    + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"(?:"
    + r"[^'\"\s,;]{3,}[^\r\n]*+|"
    + _SAFE_CREDENTIAL_VALUE_ATOM_PATTERN_TEXT
    + r"(?=\s++\S)[^\r\n]*+)"
    + r")"
)
_COMPACT_TOKEN_KEY_PATTERN_TEXT = (
    r"(?:access|api|auth|authorization|client|refresh|id|session|csrf|xsrf)Token"
)
_CREDENTIAL_FIELD_NAME_PATTERN_TEXT = (
    r"(?:authorization|aws[\s_-]?secret[\s_-]?access[\s_-]?key|"
    r"secret[\s_-]?access[\s_-]?key|access[\s_-]?token|"
    r"client[\s_-]?secret|api[\s_-]?key|private[\s_-]?key|"
    r"secret(?:[\s_-]?key)?|password|pass[ \t_-]?phrase|pass[ \t_-]?code|"
    r"passwd|pwd|(?-i:PIN)|"
    r"credential|token|" + _COMPACT_TOKEN_KEY_PATTERN_TEXT + r")"
)
_CREDENTIAL_FIELD_PATTERN_TEXT = (
    r"(?:(?<![\w-])|(?<=[._-]))['\"]?(?:[A-Za-z0-9]+[._-])*"
    + _CREDENTIAL_FIELD_NAME_PATTERN_TEXT
    + r"['\"]?"
)
_LOWER_CAMEL_CASE_CREDENTIAL_SUFFIX_PATTERN_TEXT = (
    r"(?:Token|Secret|Password|Passphrase|Passcode|Pin|ApiKey|AccessKey|PrivateKey)"
)
_PASCAL_CASE_CREDENTIAL_SUFFIX_PATTERN_TEXT = (
    r"(?:Credential|Secret|Password|Passphrase|Passcode|PIN|Pin|APIKey|ApiKey|"
    r"AccessKey|PrivateKey|"
    r"(?:Access|API|Api|Auth|Authorization|Client|Refresh|ID|Id|Session|"
    r"CSRF|Csrf|XSRF|Xsrf)Token)"
)


def _compact_case_credential_field_pattern(
    *, initial_pattern: str, suffix_pattern: str, connector_pattern: str
) -> str:
    return (
        r"(?:(?<![\w-])|(?<=[._-]))['\"]?"
        r"(?=[A-Za-z0-9]{1,64}['\"]?"
        + _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
        + connector_pattern
        + r")"
        + r"(?-i:"
        + initial_pattern
        + r"[A-Za-z0-9]*"
        + suffix_pattern
        + r")['\"]?"
    )


_LOWER_CAMEL_CASE_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT = (
    _compact_case_credential_field_pattern(
        initial_pattern=r"[a-z]",
        suffix_pattern=_LOWER_CAMEL_CASE_CREDENTIAL_SUFFIX_PATTERN_TEXT,
        connector_pattern=r"(?:=|:)",
    )
)
_PASCAL_CASE_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT = (
    _compact_case_credential_field_pattern(
        initial_pattern=r"[A-Z]",
        suffix_pattern=_PASCAL_CASE_CREDENTIAL_SUFFIX_PATTERN_TEXT,
        connector_pattern=r"(?:=|:)",
    )
)
_LOWER_CAMEL_CASE_CREDENTIAL_NARRATIVE_FIELD_PATTERN_TEXT = (
    _compact_case_credential_field_pattern(
        initial_pattern=r"[a-z]",
        suffix_pattern=_LOWER_CAMEL_CASE_CREDENTIAL_SUFFIX_PATTERN_TEXT,
        connector_pattern=r"(?:is\b|was\b|set[ \t]++to\b)",
    )
)
_PASCAL_CASE_CREDENTIAL_NARRATIVE_FIELD_PATTERN_TEXT = (
    _compact_case_credential_field_pattern(
        initial_pattern=r"[A-Z]",
        suffix_pattern=_PASCAL_CASE_CREDENTIAL_SUFFIX_PATTERN_TEXT,
        connector_pattern=r"(?:is\b|was\b|set[ \t]++to\b)",
    )
)
_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT = (
    r"(?:"
    + _CREDENTIAL_FIELD_PATTERN_TEXT
    + r"|"
    + _LOWER_CAMEL_CASE_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT
    + r"|"
    + _PASCAL_CASE_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT
    + r")"
)
_CREDENTIAL_NARRATIVE_FIELD_PATTERN_TEXT = (
    r"(?:"
    + _CREDENTIAL_FIELD_PATTERN_TEXT
    + r"|"
    + _LOWER_CAMEL_CASE_CREDENTIAL_NARRATIVE_FIELD_PATTERN_TEXT
    + r"|"
    + _PASCAL_CASE_CREDENTIAL_NARRATIVE_FIELD_PATTERN_TEXT
    + r")"
)
_AUTH_SCHEME_PATTERN_TEXT = (
    r"(?:Bearer|Basic|Digest|Negotiate|Token|Api[-_]?Key|HMAC|"
    r"AWS4-HMAC-SHA256|Signature|OAuth|MAC)"
)

_CREDENTIAL_LABELED_VALUE_RE = re.compile(
    _CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT
    + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
    + r"(?:=|:)"
    + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
    + r"(?P<value>"
    + _CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
    + r")",
    re.IGNORECASE,
)
_CREDENTIAL_NARRATIVE_VALUE_RE = re.compile(
    _CREDENTIAL_NARRATIVE_FIELD_PATTERN_TEXT
    + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
    + r"(?:\bis\b|\bwas\b|\bset\s++to\b)"
    + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
    + r"(?P<value>"
    + _CREDENTIAL_NARRATIVE_VALUE_MATCH_PATTERN_TEXT
    + r")",
    re.IGNORECASE,
)

PRIVATE_KEY_BOUNDARY_RE = re.compile(
    r"-----\s*(?P<kind>BEGIN|END)\s+"
    r"(?P<label>" + _PRIVATE_KEY_LABEL_PATTERN_TEXT + r")\s*-----",
    re.IGNORECASE,
)
CREDENTIAL_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "secret",
        re.compile(
            r"-----\s*BEGIN\s+(?P<private_key_label>"
            + _PRIVATE_KEY_LABEL_PATTERN_TEXT
            + r")\s*-----"
            r"(?:[\s\S]*?-----\s*END\s+"
            r"(?P=private_key_label)" + r"\s*-----|[\s\S]*\Z)",
            re.IGNORECASE,
        ),
        "[REDACTED_SECRET]",
    ),
    (
        "credential",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            r"(?<![A-Za-z0-9_])(?:gh[oprsu]_|github_pat_)"
            r"[A-Za-z0-9_.-]{12,}(?![A-Za-z0-9_.-])"
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(r"\b(?:sk|rk)[-_](?:proj[-_])?[A-Za-z0-9_-]{12,}\b"),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{16,}\b"),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            r"\b(?:Proxy-)?Authorization"
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + r"(?:=|:)"
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + _CREDENTIAL_VALUE_MATCH_PATTERN_TEXT,
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            r"\bBearer"
            + _CREDENTIAL_SPACE_REQUIRED_ATOMIC_PATTERN_TEXT
            + _CREDENTIAL_VALUE_MATCH_PATTERN_TEXT,
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            _CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + r"(?:=|:)"
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + _AUTH_SCHEME_PATTERN_TEXT
            + _CREDENTIAL_SPACE_REQUIRED_ATOMIC_PATTERN_TEXT
            + _CREDENTIAL_VALUE_MATCH_PATTERN_TEXT,
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            r"(?:"
            + _CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + r"(?:=|:)"
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + _CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
            + r"|"
            r"(?<![\w-])--"
            + _CREDENTIAL_FIELD_NAME_PATTERN_TEXT
            + _CREDENTIAL_SPACE_REQUIRED_ATOMIC_PATTERN_TEXT
            + _CREDENTIAL_VALUE_MATCH_PATTERN_TEXT
            + r")",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        _CREDENTIAL_NARRATIVE_VALUE_RE,
        "[REDACTED_CREDENTIAL]",
    ),
)


def _normalized_private_key_label(match: re.Match[str]) -> str:
    return " ".join(match.group("label").upper().split())


def private_key_block_spans(value: str) -> Iterator[tuple[int, int]]:
    """Yield complete BEGIN blocks, ignoring mismatched END labels."""

    boundaries = tuple(PRIVATE_KEY_BOUNDARY_RE.finditer(value))
    index = 0
    while index < len(boundaries):
        begin = boundaries[index]
        if begin.group("kind").upper() != "BEGIN":
            index += 1
            continue
        begin_label = _normalized_private_key_label(begin)
        nesting_depth = 1
        for end_index in range(index + 1, len(boundaries)):
            end = boundaries[end_index]
            if _normalized_private_key_label(end) != begin_label:
                continue
            if end.group("kind").upper() == "BEGIN":
                nesting_depth += 1
                continue
            nesting_depth -= 1
            if nesting_depth == 0:
                yield begin.start(), end.end()
                index = end_index + 1
                break
        else:
            yield begin.start(), len(value)
            return


def redact_private_key_blocks(value: str) -> str:
    """Redact private-key blocks through their matching normalized END label."""

    spans = tuple(private_key_block_spans(value))
    for start, end in reversed(spans):
        value = value[:start] + "[REDACTED_SECRET]" + value[end:]
    return value


def _is_ip_token(value: str, *, version: int) -> bool:
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    address = candidate.split("%", 1)[0]
    if version == 4:
        address = address.split(":", 1)[0]
    try:
        return ipaddress.ip_address(address).version == version
    except ValueError:
        return False


def ipv4_matches(value: str) -> Iterator[re.Match[str]]:
    for match in IPV4_CANDIDATE_RE.finditer(value):
        if _is_ip_token(match.group(0), version=4):
            yield match


def ipv6_matches(value: str) -> Iterator[re.Match[str]]:
    for match in IPV6_CANDIDATE_RE.finditer(value):
        if _is_ip_token(match.group(0), version=6):
            yield match


def contains_ip_address(value: str) -> bool:
    return (
        next(ipv4_matches(value), None) is not None
        or next(ipv6_matches(value), None) is not None
    )


def contains_credential_material(value: str) -> bool:
    return PRIVATE_KEY_BOUNDARY_RE.search(value) is not None or any(
        pattern.search(value) is not None
        for _category, pattern, _replacement in CREDENTIAL_REDACTION_PATTERNS
    )


def is_canonical_redacted_value(value: str) -> bool:
    """Return whether value is exactly one supported retained placeholder."""

    return _CANONICAL_REDACTED_VALUE_RE.fullmatch(value) is not None


def noncanonical_redacted_placeholder_spans(
    value: str,
) -> Iterator[tuple[int, int]]:
    """Yield placeholder-shaped spans outside the closed retained vocabulary."""

    return (
        match.span()
        for match in _REDACTED_PLACEHOLDER_SHAPE_RE.finditer(value)
        if not is_canonical_redacted_value(match.group(0))
    )


def _normalized_sensitive_value(value: str) -> str:
    return " ".join(value.strip().strip("'\"").strip().split())


def _normalized_personal_sensitive_value(value: str) -> str:
    wrapper_characters = " \t'\"`*_(){}<>\u2018\u2019\u201c\u201d"
    candidate = re.sub(r"\\(['\"\\])", r"\1", value).strip()
    candidate = candidate.rstrip(".,;!?").strip(wrapper_characters)
    candidate = _PERSONAL_OUTER_SQUARE_WRAPPER_RE.sub(r"\g<value>", candidate)
    candidate = candidate.rstrip(".,;!?").strip(wrapper_characters)
    return " ".join(candidate.split())


def _decoded_sensitive_labeled_value(match: re.Match[str]) -> str:
    for group in (
        "value",
        "double_quoted_value",
        "single_quoted_value",
        "escaped_double_quoted_value",
    ):
        try:
            candidate = match.group(group)
        except IndexError:
            continue
        if candidate is not None:
            if group == "double_quoted_value":
                try:
                    decoded = json.loads('"' + candidate + '"')
                except json.JSONDecodeError:
                    decoded = candidate
                if isinstance(decoded, str):
                    candidate = decoded
            elif group == "single_quoted_value":
                candidate = re.sub(r"\\(['\\])", r"\1", candidate)
            return candidate
    raise ValueError("sensitive labeled value match omitted its value")


def _normalized_generic_sensitive_labeled_value(match: re.Match[str]) -> str:
    return _normalized_sensitive_value(_decoded_sensitive_labeled_value(match))


def _normalized_personal_labeled_value(match: re.Match[str]) -> str:
    return _normalized_personal_sensitive_value(_decoded_sensitive_labeled_value(match))


def _normalized_personal_trailing_value(match: re.Match[str]) -> str:
    group_values = match.groupdict()
    candidate = next(
        filter(
            lambda value: value is not None,
            map(
                group_values.get,
                (
                    "double_trailing_value",
                    "single_trailing_value",
                    "escaped_double_trailing_value",
                ),
            ),
        ),
        "",
    )
    return _normalized_personal_sensitive_value(candidate)


def _normalized_malformed_markdown_trailing_value(match: re.Match[str]) -> str:
    candidate = match.groupdict().get("malformed_trailing_value") or ""
    return _normalized_personal_sensitive_value(candidate)


_SAFE_REDACTED_VALUE_RE = re.compile(
    r"\A" + _REDACTED_VALUE_PATTERN_TEXT + r"[)\]}>]*\Z"
)
_REDACTED_PREFIX_VALUE_RE = re.compile(
    r"\A"
    + _REDACTED_VALUE_PATTERN_TEXT
    + r"[)\]}>`*_'\"\u2019\u201d]*+[ \t]*+(?P<value>.+)\Z"
)
_PERSONAL_OUTER_SQUARE_WRAPPER_RE = re.compile(
    r"\A\[(?!REDACTED(?:_[A-Z0-9]+)*\])(?P<value>[^\r\n]*)\]\Z"
)
_PERSONAL_NARRATIVE_SUFFIX_RE = re.compile(
    r"[ \t]++(?:after|before|during|until|when|while)\b[^\r\n]*+\Z",
    re.IGNORECASE,
)
_CREDENTIAL_NARRATIVE_CONTEXT_SUFFIX_RE = re.compile(
    _SAFE_CREDENTIAL_NARRATIVE_CONTINUATION_PATTERN_TEXT + r"\Z",
    re.ASCII | re.IGNORECASE,
)
_PERSONAL_NAME_METADATA_SUFFIX_RE = re.compile(
    r"[ \t]*,[ \t]*" + _NAME_TRAILING_METADATA_PATTERN_TEXT + r"[^\r\n]*+\Z",
    re.ASCII | re.IGNORECASE,
)
_CREDENTIAL_NARRATIVE_METADATA_SUFFIX_RE = _PERSONAL_NAME_METADATA_SUFFIX_RE
_PERSONAL_STATUS_VALUE_SUFFIX_RE = re.compile(
    r"\A(?:"
    + _SAFE_CREDENTIAL_NARRATIVE_STATUS_PATTERN_TEXT
    + r")(?:[ \t]+(?:at|by|for|from|in|on|to|with)\b[ \t]+|"
    r"[ \t]*(?:=|:|-)[ \t]*)(?P<value>.+)\Z",
    re.ASCII | re.IGNORECASE,
)
_SAFE_PERSONAL_NARRATIVE_VALUE_RE = re.compile(
    r"\A(?:"
    + _SAFE_CREDENTIAL_NARRATIVE_STATUS_PATTERN_TEXT
    + _SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT
    + r")\Z",
    re.ASCII | re.IGNORECASE,
)
_MEMORY_ADDRESS_VALUE_RE = re.compile(r"\A0x[0-9a-f]+\Z", re.ASCII | re.IGNORECASE)
_ADDRESS_COMPONENT_SEPARATOR_RE = re.compile(r"[ \t]*,[ \t]*")
_ADDRESS_COMPONENT_ASSIGNMENT_RE = re.compile(
    r"\A[ \t]*['\"]?"
    + _ADDRESS_COMPONENT_FIELD_PATTERN_TEXT
    + r"['\"]?[ \t]*(?:=|:)[ \t]*(?P<value>.+)\Z",
    re.ASCII | re.IGNORECASE,
)


def _personal_sensitive_overlap_values(match: re.Match[str]) -> tuple[str, ...]:
    core = _normalized_personal_labeled_value(match)
    unredacted_core = _SAFE_REDACTED_VALUE_RE.sub("", core)
    narrative_prefix = _PERSONAL_NARRATIVE_SUFFIX_RE.sub("", unredacted_core)
    trailing = _normalized_personal_trailing_value(match)
    quoted_redacted_trailing = _SAFE_REDACTED_VALUE_RE.sub(trailing, core)
    unquoted_redacted_trailing = _SAFE_REDACTED_VALUE_RE.sub(
        "",
        _REDACTED_PREFIX_VALUE_RE.sub(r"\g<value>", core),
    )
    malformed_trailing = _normalized_malformed_markdown_trailing_value(match)
    status_value_match = _PERSONAL_STATUS_VALUE_SUFFIX_RE.fullmatch(unredacted_core)
    status_value = (
        _normalized_personal_sensitive_value(status_value_match.group("value"))
        if status_value_match is not None
        else ""
    )
    return (
        unredacted_core,
        narrative_prefix,
        quoted_redacted_trailing,
        unquoted_redacted_trailing,
        malformed_trailing,
        status_value,
    )


def _credential_narrative_sensitive_overlap_values(
    match: re.Match[str],
) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(filter(None, _personal_sensitive_overlap_values(match)))
    )
    for _round in range(3):
        derivatives = chain.from_iterable(
            map(_credential_narrative_value_derivatives, values)
        )
        values = tuple(dict.fromkeys(filter(None, chain(values, derivatives))))
    return values


def _credential_narrative_value_derivatives(value: str) -> tuple[str, ...]:
    status_match = _PERSONAL_STATUS_VALUE_SUFFIX_RE.fullmatch(value)
    status_value = (
        _normalized_personal_sensitive_value(status_match.group("value"))
        if status_match is not None
        else ""
    )
    context_prefix = _normalized_personal_sensitive_value(
        _CREDENTIAL_NARRATIVE_CONTEXT_SUFFIX_RE.sub("", value)
    )
    metadata_prefix = _normalized_personal_sensitive_value(
        _CREDENTIAL_NARRATIVE_METADATA_SUFFIX_RE.sub("", value)
    )
    return tuple(
        candidate
        for candidate in (status_value, context_prefix, metadata_prefix)
        if candidate and candidate != value
    )


def _address_component_values(match: re.Match[str]) -> tuple[str, ...]:
    values = _personal_sensitive_overlap_values(match)
    return tuple(
        filter(
            None,
            chain.from_iterable(map(_ADDRESS_COMPONENT_SEPARATOR_RE.split, values)),
        )
    )


def _normalized_address_component_value(value: str) -> str:
    return _normalized_personal_sensitive_value(
        _ADDRESS_COMPONENT_ASSIGNMENT_RE.sub(r"\g<value>", value)
    )


def _address_sensitive_overlap_values(match: re.Match[str]) -> tuple[str, ...]:
    values = _personal_sensitive_overlap_values(match)
    components = _address_component_values(match)
    normalized_components = tuple(map(_normalized_address_component_value, components))
    return values + components + normalized_components


def _name_sensitive_overlap_values(match: re.Match[str]) -> tuple[str, ...]:
    values = _personal_sensitive_overlap_values(match)
    component_sources = map(
        lambda value: _PERSONAL_NAME_METADATA_SUFFIX_RE.sub("", value),
        values,
    )
    components = tuple(
        filter(
            None,
            map(
                _normalized_personal_sensitive_value,
                chain.from_iterable(
                    map(_ADDRESS_COMPONENT_SEPARATOR_RE.split, component_sources)
                ),
            ),
        )
    )
    return values + components


def _contains_nonstatus_personal_value(values: Iterable[str]) -> bool:
    return any(
        value and _SAFE_PERSONAL_NARRATIVE_VALUE_RE.fullmatch(value) is None
        for value in values
    )


def _personal_match_contains_sensitive_value(match: re.Match[str]) -> bool:
    return _contains_nonstatus_personal_value(_personal_sensitive_overlap_values(match))


def _address_match_contains_sensitive_value(match: re.Match[str]) -> bool:
    components = tuple(
        map(_normalized_address_component_value, _address_component_values(match))
    )
    if not _contains_nonstatus_personal_value(components):
        return False
    memory_addresses = all(map(_MEMORY_ADDRESS_VALUE_RE.fullmatch, components))
    return (bool(components), memory_addresses) == (True, False)


def _malformed_markdown_name_match_contains_sensitive_value(
    match: re.Match[str],
) -> bool:
    complete = MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_NAME_VALUE_RE.match(
        match.string,
        match.start(),
    )
    return complete is None and _personal_match_contains_sensitive_value(match)


def _malformed_markdown_address_match_contains_sensitive_value(
    match: re.Match[str],
) -> bool:
    complete = MARKDOWN_COMPLETE_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE.match(
        match.string,
        match.start(),
    )
    return complete is None and _address_match_contains_sensitive_value(match)


def _payment_card_match_is_valid(match: re.Match[str]) -> bool:
    digits = tuple(map(int, filter(str.isdigit, match.group("personal"))))
    parity = len(digits) % 2
    checksum = sum(map(_LUHN_DOUBLED_DIGITS.__getitem__, digits[parity::2])) + sum(
        digits[1 - parity :: 2]
    )
    return (checksum % 10, len(set(digits)) > 1) == (0, True)


def _iban_match_is_valid(match: re.Match[str]) -> bool:
    candidate = match.group("personal").replace(" ", "").replace("\t", "").upper()
    if _IBAN_LENGTH_BY_COUNTRY.get(candidate[:2]) != len(candidate):
        return False
    remainder = 0
    for character in candidate[4:] + candidate[:4]:
        encoded = (
            str(ord(character) - ord("A") + 10) if character.isalpha() else character
        )
        remainder = int(f"{remainder}{encoded}") % 97
    return remainder == 1


def _bare_phone_match_is_valid(match: re.Match[str]) -> bool:
    candidate = match.group(0)
    return (
        _DATE_PREFIXED_NUMERIC_RE.match(candidate) is None
        and _DOTTED_NUMERIC_VERSION_RE.fullmatch(candidate) is None
    )


def _retain_every_match(_match: re.Match[str]) -> bool:
    return True


_PERSONAL_MATCH_FILTERS = {
    **dict.fromkeys(
        PERSONAL_LABELED_VALUE_PATTERNS,
        _personal_match_contains_sensitive_value,
    ),
    **dict.fromkeys(
        _ADDRESS_LABELED_VALUE_PATTERNS,
        _address_match_contains_sensitive_value,
    ),
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_NAME_VALUE_RE: (
        _malformed_markdown_name_match_contains_sensitive_value
    ),
    MALFORMED_MARKDOWN_NARRATIVE_BARE_LABELED_ADDRESS_VALUE_RE: (
        _malformed_markdown_address_match_contains_sensitive_value
    ),
    BARE_PAYMENT_CARD_RE: _payment_card_match_is_valid,
    BARE_IBAN_RE: _iban_match_is_valid,
    BARE_GROUPED_IBAN_RE: _iban_match_is_valid,
    PHONE_RE: _bare_phone_match_is_valid,
}


def _filtered_personal_matches(
    pattern: re.Pattern[str], value: str
) -> Iterator[re.Match[str]]:
    return filter(
        _PERSONAL_MATCH_FILTERS.get(pattern, _retain_every_match),
        pattern.finditer(value),
    )


def _normalized_contextual_phone_value(match: re.Match[str]) -> str:
    return _normalized_sensitive_value(match.group("phone"))


def _normalized_sensitive_overlap_value(value: str) -> str:
    return " ".join(value.split()).casefold()


def sensitive_labeled_values(value: str) -> Iterator[str]:
    """Yield closed-taxonomy field and bare-number values for overlap checks."""

    credential_assignment_values = map(
        _normalized_generic_sensitive_labeled_value,
        _CREDENTIAL_LABELED_VALUE_RE.finditer(value),
    )
    credential_narrative_values = chain.from_iterable(
        map(
            _credential_narrative_sensitive_overlap_values,
            _CREDENTIAL_NARRATIVE_VALUE_RE.finditer(value),
        )
    )
    personal_matches = chain.from_iterable(
        map(
            lambda pattern: _filtered_personal_matches(pattern, value),
            _NON_ADDRESS_PERSONAL_LABELED_VALUE_PATTERNS,
        )
    )
    personal_values = chain.from_iterable(
        map(_personal_sensitive_overlap_values, personal_matches)
    )
    name_matches = chain.from_iterable(
        map(
            lambda pattern: _filtered_personal_matches(pattern, value),
            _NAME_LABELED_VALUE_PATTERNS,
        )
    )
    name_values = chain.from_iterable(map(_name_sensitive_overlap_values, name_matches))
    address_matches = chain.from_iterable(
        map(
            lambda pattern: _filtered_personal_matches(pattern, value),
            _ADDRESS_LABELED_VALUE_PATTERNS,
        )
    )
    address_values = chain.from_iterable(
        map(_address_sensitive_overlap_values, address_matches)
    )
    contextual_phone_values = filter(
        lambda candidate: 7 <= sum(map(str.isdigit, candidate)) <= 15,
        map(
            _normalized_contextual_phone_value,
            chain.from_iterable(
                map(
                    lambda pattern: pattern.finditer(value),
                    CONTEXTUAL_PHONE_PATTERNS,
                )
            ),
        ),
    )
    bare_sensitive_number_values = map(
        lambda match: match.group("personal"),
        chain(
            BARE_STANDARD_SSN_RE.finditer(value),
            _filtered_personal_matches(BARE_PAYMENT_CARD_RE, value),
            _filtered_personal_matches(BARE_IBAN_RE, value),
            _filtered_personal_matches(BARE_GROUPED_IBAN_RE, value),
        ),
    )
    normalized = chain(
        credential_assignment_values,
        credential_narrative_values,
        personal_values,
        name_values,
        contextual_phone_values,
        bare_sensitive_number_values,
    )
    return chain(
        filter(
            lambda candidate: len(_normalized_sensitive_overlap_value(candidate)) >= 3,
            normalized,
        ),
        filter(
            lambda candidate: bool(_normalized_sensitive_overlap_value(candidate)),
            address_values,
        ),
    )


def _tag_sensitive_labeled_value(value: str) -> tuple[str, bool]:
    return value, True


def _tagged_sensitive_expansion(value: str) -> Iterator[tuple[str, bool]]:
    labeled = map(_tag_sensitive_labeled_value, sensitive_labeled_values(value))
    return chain(((value, False),), labeled)


def _retain_unseen_tagged_expansion(
    item: tuple[str, bool], seen: set[tuple[str, bool]]
) -> bool:
    if item in seen:
        return False
    seen.add(item)
    return True


def _unique_tagged_sensitive_expansions(
    values: Iterable[str],
) -> Iterator[tuple[str, bool]]:
    seen: set[tuple[str, bool]] = set()
    return filter(
        lambda item: _retain_unseen_tagged_expansion(item, seen),
        chain.from_iterable(map(_tagged_sensitive_expansion, values)),
    )


def expand_sensitive_labeled_values(
    values: Iterable[str], *, maximum_items: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Expand source values and retain labeled three-character provenance."""

    tagged = tuple(
        islice(
            _unique_tagged_sensitive_expansions(values),
            maximum_items + 1,
        )
    )
    short_values = filter(
        lambda item: (
            item[1],
            len(_normalized_sensitive_overlap_value(item[0])) in (1, 2, 3),
        )
        == (True, True),
        tagged,
    )
    normalized_short_values = map(
        _normalized_sensitive_overlap_value,
        map(itemgetter(0), short_values),
    )
    return tuple(map(itemgetter(0), tagged)), tuple(normalized_short_values)


def personal_identifier_spans(value: str) -> Iterator[tuple[int, int]]:
    """Yield deterministic merged spans for supported personal identifiers."""

    candidates: list[tuple[int, int]] = []
    for pattern in (
        EMAIL_RE,
        *PHONE_PATTERNS,
        BARE_STANDARD_SSN_RE,
        BARE_PAYMENT_CARD_RE,
        BARE_IBAN_RE,
        BARE_GROUPED_IBAN_RE,
        *PERSONAL_LABELED_VALUE_PATTERNS,
    ):
        for match in _filtered_personal_matches(pattern, value):
            group = PERSONAL_IDENTIFIER_GROUPS.get(pattern, 0)
            if pattern in PHONE_PATTERNS:
                digit_count = sum(
                    character.isdigit() for character in match.group(group)
                )
                minimum_digit_count, maximum_digit_count = PHONE_DIGIT_COUNT_BOUNDS[
                    pattern
                ]
                if not minimum_digit_count <= digit_count <= maximum_digit_count:
                    continue
            candidates.append((match.start(group), match.end(group)))
    candidates.sort(key=lambda span: (span[0], span[1]))
    if not candidates:
        return
    start, end = candidates[0]
    for candidate_start, candidate_end in candidates[1:]:
        if candidate_start < end:
            end = max(end, candidate_end)
            continue
        yield start, end
        start, end = candidate_start, candidate_end
    yield start, end


def contains_personal_identifier(value: str) -> bool:
    return next(personal_identifier_spans(value), None) is not None


def contains_mac_address(value: str) -> bool:
    """Return whether text contains a strict six-octet MAC address."""

    return MAC_ADDRESS_RE.search(value) is not None


def personal_identifier_values(value: str) -> Iterator[str]:
    return map(lambda span: value[slice(*span)], personal_identifier_spans(value))


def personal_identifier_redaction_variants(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((value, redact_personal_identifiers(value))))


def redact_personal_identifiers(value: str) -> str:
    spans = tuple(personal_identifier_spans(value))
    for start, end in reversed(spans):
        value = value[:start] + "[REDACTED_PERSONAL_IDENTIFIER]" + value[end:]
    return value


def redact_mac_addresses(value: str) -> str:
    """Redact strict colon- or hyphen-delimited MAC addresses."""

    return MAC_ADDRESS_RE.sub("[REDACTED_INTERNAL_ADDRESS]", value)


def contains_raw_identifier(value: str) -> bool:
    return any(pattern.search(value) for pattern in RAW_IDENTIFIER_PATTERNS)


def contains_path_locator(value: str) -> bool:
    return any(pattern.search(value) for pattern in PATH_LOCATOR_PATTERNS)


def redact_ip_addresses(value: str) -> str:
    redacted = IPV4_CANDIDATE_RE.sub(
        lambda match: "[REDACTED_IP_ADDRESS]"
        if _is_ip_token(match.group(0), version=4)
        else match.group(0),
        value,
    )
    return IPV6_CANDIDATE_RE.sub(
        lambda match: "[REDACTED_IP_ADDRESS]"
        if _is_ip_token(match.group(0), version=6)
        else match.group(0),
        redacted,
    )
