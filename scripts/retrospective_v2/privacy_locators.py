"""Shared deterministic locator and credential patterns for privacy validators."""

from __future__ import annotations

import ipaddress
import re
from typing import Iterator


BARE_PRIVATE_LOCATOR_RE = re.compile(
    r"(?i)\b(?:localhost|(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"(?:[a-z0-9-]+\.)+(?:corp|home|internal|intranet|lan|local))"
    r"(?::\d{1,5})?(?:/[^\s<>\"']*)?"
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
_SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT = r"(?=$|[\s,;&#)\]\}>\"']|\.(?:$|\s))"
_SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT = (
    r"(?![\[<({]?"
    + _SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + _SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT
    + r")"
)
_COMPACT_TOKEN_KEY_PATTERN_TEXT = (
    r"(?:access|api|auth|authorization|client|refresh|id|session|csrf|xsrf)Token"
)
_CREDENTIAL_FIELD_NAME_PATTERN_TEXT = (
    r"(?:authorization|aws[\s_-]?secret[\s_-]?access[\s_-]?key|"
    r"secret[\s_-]?access[\s_-]?key|access[\s_-]?token|"
    r"client[\s_-]?secret|api[\s_-]?key|private[\s_-]?key|"
    r"secret(?:[\s_-]?key)?|password|passwd|pwd|credential|token|"
    + _COMPACT_TOKEN_KEY_PATTERN_TEXT
    + r")"
)
_CREDENTIAL_FIELD_PATTERN_TEXT = (
    r"(?:(?<![\w-])|(?<=[._-]))['\"]?(?:[A-Za-z0-9]+[._-])*"
    + _CREDENTIAL_FIELD_NAME_PATTERN_TEXT
    + r"['\"]?"
)
_AUTH_SCHEME_PATTERN_TEXT = (
    r"(?:Bearer|Basic|Digest|Negotiate|Token|Api[-_]?Key|HMAC|"
    r"AWS4-HMAC-SHA256|Signature|OAuth|MAC)"
)

PRIVATE_KEY_BOUNDARY_RE = re.compile(
    r"-----\s*(?:BEGIN|END)\s+" + _PRIVATE_KEY_LABEL_PATTERN_TEXT + r"\s*-----",
    re.IGNORECASE,
)
CREDENTIAL_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "secret",
        re.compile(
            r"-----\s*BEGIN\s+" + _PRIVATE_KEY_LABEL_PATTERN_TEXT + r"\s*-----"
            r"(?:[\s\S]*?-----\s*END\s+"
            + _PRIVATE_KEY_LABEL_PATTERN_TEXT
            + r"\s*-----|[\s\S]*\Z)",
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
            r"\b(?:Proxy-)?Authorization\s*(?:=|:)\s*"
            + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
            + r"[^\r\n]+",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            r"\bBearer\s+"
            + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
            + r"[A-Za-z0-9._~+/=-]+",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            _CREDENTIAL_FIELD_PATTERN_TEXT
            + r"\s*(?:=|:)\s*['\"]?"
            + _AUTH_SCHEME_PATTERN_TEXT
            + r"\s+"
            + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
            + r"[^'\"\r\n,;]+",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        "credential",
        re.compile(
            r"(?:"
            + _CREDENTIAL_FIELD_PATTERN_TEXT
            + r"\s*(?:=|:)\s*['\"]?"
            + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
            + r"[^'\"\s,;]+|"
            r"(?<![\w-])--"
            + _CREDENTIAL_FIELD_NAME_PATTERN_TEXT
            + r"\s+"
            + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
            + r"[^'\"\s,;]+|"
            r"\b"
            + _CREDENTIAL_FIELD_NAME_PATTERN_TEXT
            + r"\s*(?:\bis\b|\bwas\b|\bset\s+to\b)\s*['\"]?"
            + _SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
            + r"[^'\"\s,;]{3,}"
            r")",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
)


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
