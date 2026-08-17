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
    _SAFE_CREDENTIAL_VALUE_ATOM_PATTERN_TEXT + r"(?:(?!\w)[\s\S])*+\w[^'\"\s,;]*"
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
            _CREDENTIAL_FIELD_PATTERN_TEXT
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
            + _CREDENTIAL_FIELD_PATTERN_TEXT
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
        re.compile(
            r"\b"
            + _CREDENTIAL_FIELD_NAME_PATTERN_TEXT
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + r"(?:\bis\b|\bwas\b|\bset\s++to\b)"
            + _CREDENTIAL_SPACE_OPTIONAL_ATOMIC_PATTERN_TEXT
            + _CREDENTIAL_NARRATIVE_VALUE_MATCH_PATTERN_TEXT,
            re.IGNORECASE,
        ),
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
