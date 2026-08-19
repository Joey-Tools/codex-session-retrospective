"""Shared deterministic locator and credential patterns for privacy validators."""

from __future__ import annotations

import ipaddress
import json
from itertools import chain, islice
from operator import itemgetter
import re
from typing import Iterable, Iterator


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
EMAIL_RE = re.compile(
    r"(?<![a-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"
    r"(?![a-z0-9-])",
    re.ASCII | re.IGNORECASE,
)
INTERNATIONAL_PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9])\+[0-9() .-]{5,40}[0-9](?![A-Za-z0-9])",
    re.ASCII,
)
PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[0-9(][0-9() .-]{8,40}[0-9]"
    r"(?![A-Za-z0-9_-])",
    re.ASCII,
)
CONTEXTUAL_SHORT_PHONE_RE = re.compile(
    r"\b(?:call|phone|tel|telephone|mobile|contact)"
    r"(?:[ _-]+number)?"
    r"(?:[ \t]*:[ \t]*|[ \t]+)"
    r"(?P<phone>(?![0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9]))"
    r"[0-9(][0-9() .-]{5,40}[0-9](?![A-Za-z0-9_-]))",
    re.ASCII | re.IGNORECASE,
)
PHONE_PATTERNS = (INTERNATIONAL_PHONE_RE, PHONE_RE, CONTEXTUAL_SHORT_PHONE_RE)
_PERSONAL_SUBJECT_PATTERN_TEXT = (
    r"(?:account|client|customer|employee|organization|person|tenant|user)"
)
_PERSONAL_CAMEL_SUBJECT_PATTERN_TEXT = (
    r"(?:account|Account|client|Client|customer|Customer|employee|Employee|"
    r"organization|Organization|person|Person|tenant|Tenant|user|User)"
)
_PERSONAL_POSSESSIVE_PATTERN_TEXT = r"(?:['\u2019]s)?"
_PERSONAL_NAME_OR_ID_FIELD_PATTERN_TEXT = r"(?:id|(?:(?:first|full|last)[_ -]+)?name)"
_PERSONAL_BIRTH_DATE_FIELD_PATTERN_TEXT = (
    r"(?:dob|date[_ -]+of[_ -]+birth|(?-i:(?:dateOfBirth|DateOfBirth)))"
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
_LABELED_PERSONAL_FIELD_PATTERN_TEXT = (
    r"\b(?:"
    + _PERSONAL_SUBJECT_PATTERN_TEXT
    + _PERSONAL_POSSESSIVE_PATTERN_TEXT
    + r"[_ -]?"
    r"(?:"
    + _PERSONAL_NAME_OR_ID_FIELD_PATTERN_TEXT
    + r"|address|"
    + _PERSONAL_BIRTH_DATE_FIELD_PATTERN_TEXT
    + r")|"
    r"(?-i:"
    + _PERSONAL_CAMEL_SUBJECT_PATTERN_TEXT
    + r"(?:Id|Name|(?:First|Full|Last)Name|Address|DOB|Dob|DateOfBirth))|"
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
    r"(?P<escaped_double_trailing_value>[^\r\n,}\]]*+)|"
    r'"(?P<double_quoted_value>(?:\\[^\r\n]|[^"\\\r\n])++)"'
    r"(?P<double_trailing_value>[^\r\n,}\]]*+)|"
    r"'(?P<single_quoted_value>(?:\\[^\r\n]|[^'\\\r\n])++)'"
    r"(?P<single_trailing_value>[^\r\n,}\]]*+)|"
    r"(?P<value>(?:"
    + _REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT
    + r"[^\r\n,}]*+|[^\r\n,}\]]++)))"
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
_BARE_LABELED_NAME_FIELD_PATTERN_TEXT = (
    r"\b(?:(?:first|full|last)[_ -]+name|(?-i:(?:first|full|last)Name))"
)
BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?:(?:\A|(?<=[\r\n]))[ \t]*(?:[-*+>][ \t]+)?|"
    r"(?<=[.!?;:,([{'\"])[ \t]*)"
    r"(?P<personal>"
    + _labeled_field_assignment_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="bare_name_markdown",
    )
    + _PERSONAL_VALUE_CAPTURE_PATTERN_TEXT
    + r")",
    re.ASCII | re.IGNORECASE,
)
MARKDOWN_BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_labeled_field_assignment_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="markdown_bare_name_markdown",
    )
    + _PERSONAL_VALUE_CAPTURE_PATTERN_TEXT
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
MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE = re.compile(
    r"(?P<personal>"
    + _markdown_complete_labeled_value_pattern(
        _BARE_LABELED_NAME_FIELD_PATTERN_TEXT,
        markdown_group="complete_bare_name_markdown",
    )
    + r")",
    re.ASCII | re.IGNORECASE,
)
_CANONICAL_REDACTED_VALUE_RE = re.compile(r"\A" + _REDACTED_VALUE_PATTERN_TEXT + r"\Z")
_REDACTED_PLACEHOLDER_SHAPE_RE = re.compile(_REDACTED_PLACEHOLDER_SHAPE_PATTERN_TEXT)
PERSONAL_LABELED_VALUE_PATTERNS = (
    LABELED_PERSONAL_VALUE_RE,
    BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_BARE_LABELED_NAME_VALUE_RE,
    MARKDOWN_COMPLETE_LABELED_PERSONAL_VALUE_RE,
    MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE,
)
PERSONAL_IDENTIFIER_GROUPS = {
    CONTEXTUAL_SHORT_PHONE_RE: "phone",
    BARE_LABELED_NAME_VALUE_RE: "personal",
    MARKDOWN_BARE_LABELED_NAME_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_LABELED_PERSONAL_VALUE_RE: "personal",
    MARKDOWN_COMPLETE_BARE_LABELED_NAME_VALUE_RE: "personal",
}
LABELED_INTERNAL_HOST_RE = re.compile(
    r"\b(?:host|hostname|node|server)\s*(?:=|:)\s*"
    r"(?!\[REDACTED)[a-z0-9][a-z0-9._-]*(?::\d{1,5})?",
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
_CAMEL_CASE_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT = (
    r"(?:(?<![\w-])|(?<=[._-]))['\"]?"
    r"(?-i:(?=[A-Za-z0-9]{1,64}['\"]?"
    + _CREDENTIAL_INLINE_SPACE_ATOMIC_PATTERN_TEXT
    + r"(?:=|:))[a-z][A-Za-z0-9]*"
    r"(?:Token|Secret|Password|Passphrase|Passcode|Pin|ApiKey|AccessKey|"
    r"PrivateKey))['\"]?"
)
_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT = (
    r"(?:"
    + _CREDENTIAL_FIELD_PATTERN_TEXT
    + r"|"
    + _CAMEL_CASE_CREDENTIAL_ASSIGNMENT_FIELD_PATTERN_TEXT
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
    return (
        unredacted_core,
        narrative_prefix,
        quoted_redacted_trailing,
        unquoted_redacted_trailing,
    )


def _personal_match_contains_sensitive_value(match: re.Match[str]) -> bool:
    return any(_personal_sensitive_overlap_values(match))


def _retain_every_match(_match: re.Match[str]) -> bool:
    return True


_PERSONAL_MATCH_FILTERS = {
    pattern: _personal_match_contains_sensitive_value
    for pattern in PERSONAL_LABELED_VALUE_PATTERNS
}


def _normalized_contextual_phone_value(match: re.Match[str]) -> str:
    return _normalized_sensitive_value(match.group("phone"))


def _normalized_sensitive_overlap_value(value: str) -> str:
    return " ".join(value.split()).casefold()


def sensitive_labeled_values(value: str) -> Iterator[str]:
    """Yield closed-taxonomy field values that need standalone overlap checks."""

    credential_values = map(
        _normalized_generic_sensitive_labeled_value,
        _CREDENTIAL_LABELED_VALUE_RE.finditer(value),
    )
    personal_matches = chain.from_iterable(
        map(lambda pattern: pattern.finditer(value), PERSONAL_LABELED_VALUE_PATTERNS)
    )
    personal_values = chain.from_iterable(
        map(_personal_sensitive_overlap_values, personal_matches)
    )
    contextual_phone_values = filter(
        lambda candidate: 7 <= sum(map(str.isdigit, candidate)) <= 15,
        map(
            _normalized_contextual_phone_value,
            CONTEXTUAL_SHORT_PHONE_RE.finditer(value),
        ),
    )
    normalized = chain(
        credential_values,
        personal_values,
        contextual_phone_values,
    )
    return filter(
        lambda candidate: len(_normalized_sensitive_overlap_value(candidate)) >= 3,
        normalized,
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
            len(_normalized_sensitive_overlap_value(item[0])),
        )
        == (True, 3),
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
        INTERNATIONAL_PHONE_RE,
        PHONE_RE,
        CONTEXTUAL_SHORT_PHONE_RE,
        *PERSONAL_LABELED_VALUE_PATTERNS,
    ):
        for match in filter(
            _PERSONAL_MATCH_FILTERS.get(pattern, _retain_every_match),
            pattern.finditer(value),
        ):
            group = PERSONAL_IDENTIFIER_GROUPS.get(pattern, 0)
            if pattern in PHONE_PATTERNS:
                digit_count = sum(
                    character.isdigit() for character in match.group(group)
                )
                minimum_digit_count = 10 if pattern is PHONE_RE else 7
                if not minimum_digit_count <= digit_count <= 15:
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


def personal_identifier_values(value: str) -> Iterator[str]:
    return map(lambda span: value[slice(*span)], personal_identifier_spans(value))


def personal_identifier_redaction_variants(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((value, redact_personal_identifiers(value))))


def redact_personal_identifiers(value: str) -> str:
    spans = tuple(personal_identifier_spans(value))
    for start, end in reversed(spans):
        value = value[:start] + "[REDACTED_PERSONAL_IDENTIFIER]" + value[end:]
    return value


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
