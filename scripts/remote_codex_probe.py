#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import binascii
import collections
import dataclasses
import datetime as dt
import errno
import hashlib
import io
import json
import os
import pathlib
import re
import selectors
import socket
import subprocess
import stat
import sys
import time
from collections.abc import Iterable
from typing import Any, BinaryIO

sys.dont_write_bytecode = True

from retrospective_v2 import private_output  # noqa: E402

DATE_FORMAT = "%Y/%m/%d"
MAX_SESSION_META_LIMIT = 500
MAX_SESSION_META_CANDIDATE_LIMIT = MAX_SESSION_META_LIMIT + 1
MAX_SESSION_META_DATE_COUNT = 31
MAX_FETCH_ROLLOUT_BYTES = 16 * 1024 * 1024
MAX_REMOTE_SESSION_META_SERIALIZED_ROW_BYTES = 64 * 1024
REMOTE_SESSION_META_FRAME_OVERHEAD_BYTES = 64 * 1024
MAX_REMOTE_SESSION_META_STDOUT_BYTES = (
    (MAX_SESSION_META_LIMIT + 1) * MAX_REMOTE_SESSION_META_SERIALIZED_ROW_BYTES
    + REMOTE_SESSION_META_FRAME_OVERHEAD_BYTES
)
MAX_ROLLOUT_SUMMARY_LIMIT = 200
MAX_ROLLOUT_SUMMARY_SCAN_BYTES = MAX_FETCH_ROLLOUT_BYTES
MAX_ROLLOUT_SUMMARY_LINE_BYTES = 1024 * 1024
MAX_ROLLOUT_SUMMARY_TAIL_RECORDS = 50
MAX_ROLLOUT_SUMMARY_TEXT_CHARS = 1200
MAX_REMOTE_ROLLOUT_SUMMARY_SERIALIZED_RECORD_BYTES = 64 * 1024
MAX_REMOTE_ROLLOUT_SUMMARY_SERIALIZED_BYTES = (
    2 * MAX_ROLLOUT_SUMMARY_LIMIT + 4
) * MAX_REMOTE_ROLLOUT_SUMMARY_SERIALIZED_RECORD_BYTES
REMOTE_ROLLOUT_SUMMARY_FRAME_OVERHEAD_BYTES = 64 * 1024
MAX_REMOTE_ROLLOUT_SUMMARY_STDOUT_BYTES = (
    MAX_REMOTE_ROLLOUT_SUMMARY_SERIALIZED_BYTES
    + REMOTE_ROLLOUT_SUMMARY_FRAME_OVERHEAD_BYTES
)
MAX_REMOTE_STDERR_BYTES = 64 * 1024
MAX_REMOTE_STDOUT_BYTES = 1024 * 1024
MAX_HOST_SELECTORS = 16
REMOTE_FETCH_FRAME_OVERHEAD_BYTES = 64 * 1024
SESSION_META_READ_CHUNK_BYTES = 64 * 1024
REMOTE_GENERATED_SUMMARY_COVERAGE_PROOF = "remote_generated_rollout_summary_v1"
REMOTE_GENERATED_SUMMARY_SOURCE_IDENTITY_PROOF = (
    "remote_generated_rollout_source_identity_v1"
)
SOURCE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BARE_64_HEX_SIGNAL_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
SAFE_CREDENTIAL_VALUE_PATTERN_TEXT = (
    r"(?:bearer|basic|digest|negotiate|token|api[-_]?key|hmac|aws4-hmac-sha256|signature|oauth|mac|"
    r"redacted(?:[_-][a-z0-9]+)*|masked(?:[_-][a-z0-9]+)*|missing|omitted|present|unknown|null|none|empty|"
    r"in|not|required|denied|expired|invalid|unavailable|absent|needed|necessary|revoked|rotated|budget|count|limit)"
)
SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT = (
    r"(?=$|[\s,;&#，。；)\]\}>\"']|\.(?:$|\s))"
)
SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT = (
    r"(?![\[<({]?"
    + SAFE_CREDENTIAL_VALUE_PATTERN_TEXT
    + SAFE_CREDENTIAL_VALUE_BOUNDARY_PATTERN_TEXT
    + r")"
)
COMPACT_TOKEN_KEY_PATTERN_TEXT = (
    r"(?:access|api|auth|authorization|client|refresh|id|session|csrf|xsrf)Token"
)
COMPACT_TOKEN_FIELD_PATTERN_TEXT = (
    r"(?:(?<![\w-])|(?<=[._-]))['\"]?(?:[A-Za-z0-9]+[._-])*"
    + COMPACT_TOKEN_KEY_PATTERN_TEXT
    + r"['\"]?"
)
AUTH_SCHEME_NAME_PATTERN_TEXT = r"(?:Bearer|Basic|Digest|Negotiate|Token|Api[-_]?Key|HMAC|AWS4-HMAC-SHA256|Signature|OAuth|MAC)"
AUTH_SCHEME_CREDENTIAL_PATTERN_TEXT = (
    r"\b(?:Proxy-)?Authorization\s*[:=]\s*"
    + AUTH_SCHEME_NAME_PATTERN_TEXT
    + r"\s+"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\r\n;]+"
)
AUTHORIZATION_FIELD_SCHEME_CREDENTIAL_PATTERN_TEXT = (
    r"(?:(?<![\w-])|(?<=[._-]))['\"]?(?:[A-Za-z0-9]+[._-])*authorization['\"]?\s*[:=]\s*['\"]?"
    + AUTH_SCHEME_NAME_PATTERN_TEXT
    + r"\s+"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\r\n,;]+"
)
CREDENTIAL_FIELD_KEY_PATTERN_TEXT = r"(?:(?<![\w-])|(?<=[._-]))['\"]?(?:[A-Za-z0-9]+[._-])*(?:authorization|aws[\s_-]?secret[\s_-]?access[\s_-]?key|secret[\s_-]?access[\s_-]?key|access[\s_-]?token|client[\s_-]?secret|api[\s_-]?key|private[\s_-]?key|secret(?:[\s_-]?key)?|password|passwd|pwd|credential|token)['\"]?"
CREDENTIAL_FIELD_AUTH_SCHEME_CREDENTIAL_PATTERN_TEXT = (
    r"(?:"
    + CREDENTIAL_FIELD_KEY_PATTERN_TEXT
    + r"|"
    + COMPACT_TOKEN_FIELD_PATTERN_TEXT
    + r")"
    r"\s*[:=]\s*['\"]?"
    + AUTH_SCHEME_NAME_PATTERN_TEXT
    + r"\s+"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\r\n,;]+"
)
MAX_SESSION_META_SCAN_BYTES = 256 * 1024
SESSION_META_FLAT_UNDATED_ALIAS_PREFIX = "flat_archived_undated_v1"
REMOTE_COMMAND_TIMEOUT_SECONDS = 60
TASK_OUTPUT_RELATIVE_DIR = pathlib.Path(".codex-tmp/remote-host-context")
ACTIVE_ROLLOUT_RELATIVE_RE = re.compile(
    r"^sessions/\d{4}/\d{2}/\d{2}/rollout-(?!summary)[^/]+\.jsonl$"
)
ARCHIVED_ROLLOUT_RELATIVE_RE = re.compile(
    r"^archived_sessions/(?:\d{4}/\d{2}/\d{2}/)?rollout-(?!summary)[^/]+\.jsonl$"
)
ROOT_ROLLOUT_RELATIVE_RE = re.compile(r"^rollout-(?!summary)[^/]+\.jsonl$")
RAW_ROLLOUT_BASENAME_RE = re.compile(r"^rollout-(?!summary)[^/]+\.jsonl$")
SECURE_ROLLOUT_DIR_FD_SUPPORTED = (
    getattr(os, "O_DIRECTORY", None) is not None
    and getattr(os, "O_NOFOLLOW", None) is not None
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
)
ROLLOUT_FILENAME_TIME_RE = re.compile(
    r"^rollout-(\d{4}-\d{2}-\d{2})(?:T(\d{2})-(\d{2})-(\d{2}))?(?:-|\.jsonl$)"
)
PRIVATE_IPV4_SIGNAL_RE = re.compile(
    r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|100\.(?:6[4-9]|[78]\d|9\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}|127(?:\.\d{1,3}){3}|169\.254(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|192\.168(?:\.\d{1,3}){2})(?![\d.])"
)
PRIVATE_IPV6_SIGNAL_RE = re.compile(
    r"(?<![0-9A-Fa-f:])(?:::1|f[cd][0-9A-Fa-f]{0,2}(?::[0-9A-Fa-f]{0,4}){1,7}|fe[89abAB][0-9A-Fa-f]?(?::[0-9A-Fa-f]{0,4}){1,7})(?![0-9A-Fa-f:])",
    re.I,
)
INTERNAL_HOSTNAME_SIGNAL_RE = re.compile(
    r"\b(?:[A-Za-z0-9-]+\.)+(?:internal|corp|local|localhost|lan|example|invalid|test)(?=$|[:/?#\s,;)>\]\"']|\.(?:$|\s))",
    re.I,
)
SECRET_TOKEN_SIGNAL_RE = re.compile(
    r"(?:"
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|"
    r"\b(?:(?:sk|rk)[-_](?:proj[-_])?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,})\b|"
    r"\bAKIA[0-9A-Z]{16}\b|" + AUTH_SCHEME_CREDENTIAL_PATTERN_TEXT + r"|"
    r"\bBearer\s+"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[A-Za-z0-9._~+/\-]+=*|"
    + CREDENTIAL_FIELD_AUTH_SCHEME_CREDENTIAL_PATTERN_TEXT
    + r"|"
    + AUTHORIZATION_FIELD_SCHEME_CREDENTIAL_PATTERN_TEXT
    + r"|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    r")",
    re.I,
)
COMPACT_TOKEN_ASSIGNMENT_SIGNAL_RE = re.compile(
    r"(?:"
    + COMPACT_TOKEN_FIELD_PATTERN_TEXT
    + r"\s*[:=]\s*['\"]?"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\s,;]+|"
    r"(?<![\w-])--"
    + COMPACT_TOKEN_KEY_PATTERN_TEXT
    + r"\s+"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\s,;]+|"
    r"\b"
    + COMPACT_TOKEN_KEY_PATTERN_TEXT
    + r"\s*(?:\bis\b|\bwas\b|\bset\s+to\b)\s*['\"]?"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\s,;]{3,}|"
    r"\b(?:https?|ssh|sftp|git\+ssh)://[^\s)>\]\"']*[?&#]"
    + COMPACT_TOKEN_KEY_PATTERN_TEXT
    + r"="
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^&#\s)>\]\"']+"
    r")",
    re.I,
)
CREDENTIAL_ASSIGNMENT_SIGNAL_RE = re.compile(
    r"(?:"
    r"(?:(?<![\w-])|(?<=[._-]))['\"]?(?:[A-Za-z0-9]+[._-])*(?:authorization|aws[\s_-]?secret[\s_-]?access[\s_-]?key|secret[\s_-]?access[\s_-]?key|access[\s_-]?token|client[\s_-]?secret|api[\s_-]?key|private[\s_-]?key|secret(?:[\s_-]?key)?|password|passwd|pwd|credential|token)['\"]?\s*[:=]\s*['\"]?"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\s,;]+|"
    r"(?<![\w-])--(?:authorization|aws[\s_-]?secret[\s_-]?access[\s_-]?key|secret[\s_-]?access[\s_-]?key|access[\s_-]?token|client[\s_-]?secret|api[\s_-]?key|private[\s_-]?key|secret(?:[\s_-]?key)?|password|passwd|pwd|credential|token)\s+"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\s,;]+|"
    r"\b(?:aws[\s_-]?secret[\s_-]?access[\s_-]?key|secret[\s_-]?access[\s_-]?key|access[\s_-]?token|client[\s_-]?secret|api[\s_-]?key|private[\s_-]?key|secret(?:[\s_-]?key)?|password|passwd|pwd|credential|token)\s*(?:\bis\b|\bwas\b|\bset\s+to\b)\s*['\"]?"
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^'\"\s,;]{3,}"
    r")",
    re.I,
)
CHINESE_CREDENTIAL_ASSIGNMENT_SIGNAL_RE = re.compile(
    r"(?:密码|口令|凭据|凭证|密钥|令牌|授权)\s*(?:[:=：]|是|为|设置为)\s*['\"]?"
    r"(?!(?:[\[<({]?(?:(?i:redacted(?:[_-][a-z0-9]+)*|masked(?:[_-][a-z0-9]+)*|missing|omitted|unknown|null|none|empty)|已脱敏|缺失|不存在|未知|为空|空|未设置|无|没有|必须|必需|需要|被拒绝|拒绝|过期|已过期|失效|已失效|不可用|无效|错误|失败|未授权)(?:[\]\)>}]|(?:的|了)?(?:[\s,;，。；]|$))))"
    r"[^'\"\s,;，。；]+"
)
SENSITIVE_IDENTIFIER_SIGNAL_RE = re.compile(
    r"\b(?:customer|client|account|tenant|org|organi[sz]ation)[_-]?(?:id|name)?\s*[:=]\s*['\"]?"
    r"(?!(?:[\[<({]?(?:(?i:redacted(?:[_-][a-z0-9]+)*|masked(?:[_-][a-z0-9]+)*|missing|omitted|unknown|null|none|empty)|已脱敏|缺失|不存在|未知|为空|空|未设置|无|没有)(?:[\]\)>}]|(?:的|了)?(?:[\s,;，。；]|$))))"
    r"[^'\"\s,;，。；]+",
    re.I,
)
CHINESE_IDENTIFIER_SIGNAL_RE = re.compile(
    r"(?:客户|客户端|租户|账户|账号|组织|机构)(?:ID|Id|id|编号|名称|名)?\s*[:=：]\s*['\"]?"
    r"(?!(?:[\[<({]?(?:(?i:redacted(?:[_-][a-z0-9]+)*|masked(?:[_-][a-z0-9]+)*|missing|omitted|unknown|null|none|empty)|已脱敏|缺失|不存在|未知|为空|空|未设置|无|没有)(?:[\]\)>}]|(?:的|了)?(?:[\s,;，。；]|$))))"
    r"[^'\"\s,;，。；]+"
)
URL_CREDENTIAL_SIGNAL_RE = re.compile(
    r"\b(?:https?|ssh|sftp|git\+ssh)://(?:"
    r"[^/\s:@]+:[^@\s/]+@[^\s)>\]\"']+|"
    r"[^\s)>\]\"']*(?:[?&#](?:[A-Za-z0-9]+[_-])*(?:token|key|secret|credential|authorization|password|passwd)="
    + SAFE_CREDENTIAL_VALUE_LOOKAHEAD_PATTERN_TEXT
    + r"[^&#\s)>\]\"']+)"
    r")",
    re.I,
)
EMAIL_SIGNAL_RE = re.compile(
    r"(?<![\w.+-])(?!(?:git|ssh)@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::[^\s]|/[^\s]))[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
PRIVATE_URL_SIGNAL_RE = re.compile(
    rf"(?:"
    rf"\b(?:https?://|ssh://|sftp://|git\+ssh://)(?:[^@\s/]+@)?(?:localhost|{PRIVATE_IPV4_SIGNAL_RE.pattern}|(?:[A-Za-z0-9-]+\.)+(?:internal|corp|local|localhost|lan|example|invalid|test))(?=$|[:/?#\s,;)>\]\"']|\.(?:$|\s))(?::\d+)?(?:[/?#][^\s)>\]\"']*)?|"
    rf"\b(?:https?://|ssh://|sftp://|git\+ssh://)(?:[^@\s/]+@)?[A-Za-z][A-Za-z0-9-]*(?::\d+)?(?:[/?#][^\s)>\]\"']*|(?=$|[\s,;)>\]\"']|\.(?:$|\s)))|"
    rf"\bgit@(?:localhost|{PRIVATE_IPV4_SIGNAL_RE.pattern}|(?:[A-Za-z0-9-]+\.)+(?:internal|corp|local|lan|example|invalid|test)):[^\s)>\]\"']+|"
    rf"\bgit@[A-Za-z][A-Za-z0-9-]*:[^\s)>\]\"']+"
    rf")",
    re.I,
)
PRIVACY_RISK_SIGNAL_RE = re.compile(
    r"(?:"
    r"\b(?:customer|client|tenant|account|personal)\s+data\b|"
    r"\b(?:pii|personally identifiable information)\b|"
    r"\bprivacy\s+(?:risk|issue|concern|leak|exposure|breach)\b|"
    r"\b(?:credential|secret|data|api[\s_-]?key|private[\s_-]?key|token|password|passwd|key)\s+(?:leaks?|leaked|expos(?:ure|ed|e|es)|breach(?:ed|es)?)\b|"
    r"\b(?:leaks?|leaked|expos(?:ure|ed|e|es)|breach(?:ed|es)?)\s+(?:credential|secret|data|api[\s_-]?key|private[\s_-]?key|token|password|passwd|key)\b|"
    r"客户数据|客户隐私|个人信息|隐私风险|隐私泄露|凭据泄露|凭证泄露|密钥泄露|敏感数据"
    r")",
    re.I,
)
DESTRUCTIVE_COMMAND_SIGNAL_RE = re.compile(
    r"(?:\brm\s+(?=(?:[^\n\r]|\\\r?\n)*(?:-[A-Za-z]*r[A-Za-z]*\b|--recursive\b))(?=(?:[^\n\r]|\\\r?\n)*(?:-[A-Za-z]*f[A-Za-z]*\b|--force\b))(?:[^\n\r]|\\\r?\n)*|\bgit\s+reset\s+--hard\b|\breset\s+--hard\b|\bdrop\s+(?:database|table|schema)\b|\btruncate\s+table\b|\bdelete\s+from\s+[`\"\[]?[A-Za-z_][A-Za-z0-9_.$`\"\]]*(?=\s*(?:where\b|;|$)))",
    re.I,
)
PRODUCTION_RISK_SIGNAL_RE = re.compile(
    r"(?:"
    r"\b(?:production|prod)\s+(?:database|db|system|server|host|cluster|environment|tenant|customer|(?:(?:api|private|secret|access|auth)\s+)?(?:credentials?|secrets?|tokens?|keys?|passwords?|passwds?|pwds?)|traffic|data)\b|"
    r"\b(?:prod|production)[-_](?:db|database|server|host|cluster|environment|tenant|customer|data|traffic|credentials?|secrets?|tokens?|keys?|passwords?|passwds?|pwds?|(?:(?:api|private|secret|access|auth)[-_])(?:credentials?|secrets?|tokens?|keys?|passwords?|passwds?|pwds?))[-_]?[A-Za-z0-9.-]*\b|"
    r"\b(?:deploy|write|delete|migrate|run|execute|operate)\b[\s\S]{0,80}\bproduction\b[\s\S]{0,40}\b(?:database|db|data|system|server|cluster|environment)\b|"
    r"\b(?:deploy|deploying|deployed|migrate|migration|rollback|restart|apply|write|delete|execute|operate)\b[\s\S]{0,40}\b(?:to|in|on|against)?\s*(?:prod|production)\b|"
    r"\brun\b[\s\S]{0,20}\b(?:migration|migrate|schema\s+change|destructive\s+command)\b[\s\S]{0,40}\b(?:in|on|against)?\s*(?:prod|production)\b|"
    r"\b(?:prod|production)\s+(?:deploy(?:ment)?|migration|rollback|write|delete|operation|change)\b|"
    r"(?:生产(?:数据库|系统|服务器|主机|集群|环境|租户|客户|凭据|凭证|密钥|令牌|密码|口令|流量|数据)|(?:部署|写入|删除|迁移|运行|执行|操作)[\s\S]{0,80}生产[\s\S]{0,40}(?:数据库|数据|系统|服务器|集群|环境)|破坏性(?:命令|操作|删除|重置|清空|销毁))"
    r")",
    re.I,
)
WRAPPER_PREFIXES = (
    "# AGENTS.md instructions",
    "<skill>",
    "<environment_context>",
    "<subagent_notification>",
    "# Review findings:",
    "<turn_aborted>",
    "Persistent internal Codex readonly review contract:",
    "Review discipline:",
)
WRAPPER_END_MARKERS = (
    "</INSTRUCTIONS>",
    "</environment_context>",
    "</skill>",
    "</subagent_notification>",
    "</turn_aborted>",
)
AUTOMATION_PROMPT_PATTERN_TEXTS = (
    r"^Run the (?:daily|weekly) Codex session retrospective\b",
    r"^Run a read-only (?:daily|weekly) retrospective over Joey's Codex session activity\b",
    r"^Run inside the dedicated worktree provisioned for this automation\b",
    r"^Use \$codex-session-retrospective to run\b",
    r"^Use the installed codex-session-retrospective workflow\b",
)
AUTOMATION_PROMPT_PATTERNS = tuple(
    re.compile(pattern, re.I) for pattern in AUTOMATION_PROMPT_PATTERN_TEXTS
)
AUTOMATION_PROMPT_MARKERS = (
    "Run a read-only daily retrospective over Joey's Codex session activity.",
    "Run a read-only weekly retrospective over Joey's Codex session activity.",
    "Evidence scope must match $remote-host-context's default host policy",
    "Use the automation's configured model and reasoning effort",
    "When reconstructing the real user task from rollouts, ignore injected wrapper content",
    "Write task-local artifacts under .codex-local/session-retrospective/runs/",
)
SUMMARY_SIGNAL_MARKERS = (
    "error:",
    "approval",
    "could not run",
    "you missed",
    "assumed",
    "over exploration",
    "under asking",
    "secret",
)
SUMMARY_SIGNAL_CHUNK_CHARS = 8192
SUMMARY_SIGNAL_CHUNK_OVERLAP = 256
SUMMARY_SIGNAL_CATEGORY_PATTERNS = (
    (
        "error:",
        r"(?:exit(?:ed)?(?: with)? code [1-9]\d*|failed|traceback|error:|permission denied)",
    ),
    (
        "approval",
        r"(?:approval|require_escalated|sandbox|\bauth(?:entication|orization|[-_ ]?gated)?\b|(?<![\w-])(?!(?:redacted|masked)(?:[_-][a-z0-9]+)*\b)[\w-]*credential|permission denied|TCC)",
    ),
    (
        "could not run",
        r"(?:not run|did not run|unable to run|could not run|untested|未运行|无法运行)",
    ),
    (
        "you missed",
        r"(?:you missed|you forgot|wrong|incorrect|not what I asked|漏了|忘了|不对|错了)",
    ),
    (
        "assumed",
        r"(?:lost context|misunderstood|I misunderstood|assumption|assumed|上下文|误解)",
    ),
    (
        "over exploration",
        r"(?:over[-_ ]?explor|over[-_ ]?investigat|over[-_ ]?search|explored too much|too much exploration|unrelated files|unrelated paths)",
    ),
    (
        "under asking",
        r"(?:under[-_ ]?ask|did not ask|didn't ask|should have asked|without asking|missing clarification|needed clarification)",
    ),
)
SUMMARY_SIGNAL_CATEGORY_LABELS = tuple(
    label for label, _pattern in SUMMARY_SIGNAL_CATEGORY_PATTERNS
)
SUMMARY_SIGNAL_CATEGORY_RES = tuple(
    (label, re.compile(pattern, re.I))
    for label, pattern in SUMMARY_SIGNAL_CATEGORY_PATTERNS
)
SUMMARY_SENSITIVE_SIGNAL_PATTERN_TEXT = "|".join(
    f"(?:{pattern})"
    for pattern in (
        PRIVATE_IPV4_SIGNAL_RE.pattern,
        PRIVATE_IPV6_SIGNAL_RE.pattern,
        INTERNAL_HOSTNAME_SIGNAL_RE.pattern,
        SECRET_TOKEN_SIGNAL_RE.pattern,
        COMPACT_TOKEN_ASSIGNMENT_SIGNAL_RE.pattern,
        CREDENTIAL_ASSIGNMENT_SIGNAL_RE.pattern,
        CHINESE_CREDENTIAL_ASSIGNMENT_SIGNAL_RE.pattern,
        SENSITIVE_IDENTIFIER_SIGNAL_RE.pattern,
        CHINESE_IDENTIFIER_SIGNAL_RE.pattern,
        URL_CREDENTIAL_SIGNAL_RE.pattern,
        EMAIL_SIGNAL_RE.pattern,
        PRIVATE_URL_SIGNAL_RE.pattern,
        PRIVACY_RISK_SIGNAL_RE.pattern,
        DESTRUCTIVE_COMMAND_SIGNAL_RE.pattern,
        PRODUCTION_RISK_SIGNAL_RE.pattern,
        BARE_64_HEX_SIGNAL_RE.pattern,
    )
)
SUMMARY_SENSITIVE_SIGNAL_RE = re.compile(SUMMARY_SENSITIVE_SIGNAL_PATTERN_TEXT, re.I)
REMOTE_SESSION_META_BEGIN = "__REMOTE_CODEX_PROBE_SESSION_META_BEGIN__"
REMOTE_SESSION_META_END = "__REMOTE_CODEX_PROBE_SESSION_META_END__"
SESSION_META_LIMIT_TRUNCATED_REASON = "session_meta_limit_truncated"
SESSION_META_CANDIDATE_LIMIT_TRUNCATED_REASON = "session_meta_candidate_limit_truncated"
SESSION_META_OUTPUT_ROW_TOO_LARGE_ERROR = "session-meta output row too large"
REMOTE_FETCH_ROLLOUT_BEGIN = "__REMOTE_CODEX_PROBE_FETCH_ROLLOUT_BEGIN__"
REMOTE_FETCH_ROLLOUT_END = "__REMOTE_CODEX_PROBE_FETCH_ROLLOUT_END__"
REMOTE_ROLLOUT_SUMMARY_BEGIN = "__REMOTE_CODEX_PROBE_ROLLOUT_SUMMARY_BEGIN__"
REMOTE_ROLLOUT_SUMMARY_END = "__REMOTE_CODEX_PROBE_ROLLOUT_SUMMARY_END__"
ROLLOUT_SUMMARY_OUTPUT_TOO_LARGE_ERROR = "rollout summary output too large"

LOCAL_HOST = "local"
HOST_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")


@dataclasses.dataclass(frozen=True)
class SessionMetaScan:
    rows: list[dict[str, str]]
    truncated: bool


@dataclasses.dataclass(frozen=True)
class RolloutIdentity:
    mode: int
    uid: int
    gid: int
    size: int
    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int


@dataclasses.dataclass(frozen=True)
class RolloutInventoryIdentity:
    mode: int
    uid: int
    gid: int
    size: int
    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int


@dataclasses.dataclass(frozen=True)
class RolloutStableIdentity:
    device: int
    inode: int


@dataclasses.dataclass(frozen=True)
class RolloutPrefixProof:
    length: int
    sha256: str


@dataclasses.dataclass(frozen=True)
class RolloutCandidateIdentity:
    snapshot: RolloutIdentity
    stable: RolloutStableIdentity
    prefix_proof: RolloutPrefixProof | None = None


@dataclasses.dataclass(frozen=True)
class EnumeratedRolloutParent:
    fd: int
    expected_identity: RolloutCandidateIdentity
    allow_append: bool


class SessionMetaRolloutError(ValueError):
    def __init__(self, error: str, *, rollout: str | None = None) -> None:
        super().__init__(error)
        self.error = error
        self.rollout = rollout


def _error(message: str) -> int:
    print(f"error={message}", file=sys.stderr)
    return 2


def _parse_date(value: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise ValueError(f"invalid date: {value}; expected YYYY/MM/DD") from exc


def _iter_dates(start: dt.date, end: dt.date) -> list[dt.date]:
    if end < start:
        raise ValueError("--to must be on or after --from")
    current = start
    dates: list[dt.date] = []
    while current <= end:
        dates.append(current)
        current += dt.timedelta(days=1)
    if len(dates) > MAX_SESSION_META_DATE_COUNT:
        raise ValueError(
            f"date range must stay within {MAX_SESSION_META_DATE_COUNT} days"
        )
    return dates


def _resolve_dates(args: argparse.Namespace) -> list[dt.date]:
    explicit_dates = [_parse_date(value) for value in args.date]
    if explicit_dates and (args.from_date or args.to_date):
        raise ValueError("--date cannot be combined with --from/--to")
    if explicit_dates:
        unique_dates = sorted(dict.fromkeys(explicit_dates))
        if len(unique_dates) > MAX_SESSION_META_DATE_COUNT:
            raise ValueError(
                f"date selection must stay within {MAX_SESSION_META_DATE_COUNT} days"
            )
        return unique_dates
    if args.from_date or args.to_date:
        if not args.from_date or not args.to_date:
            raise ValueError("--from and --to must be provided together")
        return _iter_dates(_parse_date(args.from_date), _parse_date(args.to_date))
    raise ValueError("at least one --date or a --from/--to range is required")


def _parse_rollout_bound(value: str | None, option: str) -> dt.datetime | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        raise ValueError(f"{option} must not be empty")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"invalid {option}: {value}; expected ISO timestamp such as 2026-05-21T10:00:00Z"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def _resolve_rollout_bounds(
    args: argparse.Namespace,
) -> tuple[dt.datetime | None, dt.datetime | None]:
    rollout_start = _parse_rollout_bound(
        getattr(args, "rollout_start", None), "--rollout-start"
    )
    rollout_end = _parse_rollout_bound(
        getattr(args, "rollout_end", None), "--rollout-end"
    )
    if rollout_start and rollout_end and rollout_end <= rollout_start:
        raise ValueError("--rollout-end must be after --rollout-start")
    return rollout_start, rollout_end


def _iso_utc(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rollout_filename_window(
    path: pathlib.Path,
) -> tuple[dt.datetime, dt.datetime, bool] | None:
    match = ROLLOUT_FILENAME_TIME_RE.search(path.name)
    if not match:
        return None
    try:
        if match.group(2):
            timestamp = dt.datetime(
                int(match.group(1)[0:4]),
                int(match.group(1)[5:7]),
                int(match.group(1)[8:10]),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                tzinfo=dt.timezone.utc,
            )
            return timestamp, timestamp + dt.timedelta(seconds=1), True
        day_start = dt.datetime(
            int(match.group(1)[0:4]),
            int(match.group(1)[5:7]),
            int(match.group(1)[8:10]),
            tzinfo=dt.timezone.utc,
        )
        return day_start, day_start + dt.timedelta(days=1), False
    except ValueError:
        return None


def _rollout_matches_bounds(
    path: pathlib.Path,
    rollout_start: dt.datetime | None,
    rollout_end: dt.datetime | None,
    *,
    filename_mode: str = "all",
) -> bool:
    window = _rollout_filename_window(path)
    if filename_mode == "unknown":
        return window is None or not window[2]
    if filename_mode == "known" and (window is None or not window[2]):
        return False
    if rollout_start is None and rollout_end is None:
        return True
    if window is None:
        return False
    window_start, window_end, _has_exact_time = window
    if rollout_start and window_end <= rollout_start:
        return False
    if rollout_end and window_start >= rollout_end:
        return False
    return True


def _resolve_hosts(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    hosts: list[str] = []
    for value in values:
        if not isinstance(value, str) or HOST_TOKEN_RE.fullmatch(value) is None:
            raise ValueError(f"invalid host selector: {value}")
        canonical = value
        if canonical in seen:
            continue
        seen.add(canonical)
        hosts.append(canonical)
        if len(hosts) > MAX_HOST_SELECTORS:
            raise ValueError(f"host selector count exceeds {MAX_HOST_SELECTORS}")
    if not hosts:
        raise ValueError("at least one --host is required")
    return hosts


def _local_codex_root() -> pathlib.Path:
    return pathlib.Path.home() / ".codex"


def _task_output_root(workspace_root: pathlib.Path | None = None) -> pathlib.Path:
    root = (
        workspace_root.resolve()
        if workspace_root is not None
        else pathlib.Path.cwd().resolve()
    )
    return root / TASK_OUTPUT_RELATIVE_DIR


def _reject_symlink_components(path: pathlib.Path) -> None:
    if not path.is_absolute():
        raise ValueError("output path must be absolute after normalization")
    current = pathlib.Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(current_stat.st_mode):
            raise ValueError("output path uses a symlink component")
        if current != path and not stat.S_ISDIR(current_stat.st_mode):
            raise ValueError("output path ancestor is not a directory")


def _validate_output_path(candidate: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not _path_is_relative_to(resolved_candidate, resolved_root):
        raise ValueError(f"output path must stay under {resolved_root}")
    _reject_symlink_components(candidate)
    return resolved_candidate


def _resolve_output_path(
    output: str, *, workspace_root: pathlib.Path | None = None
) -> pathlib.Path:
    raw_path = pathlib.Path(output).expanduser()
    if any(part == ".." for part in raw_path.parts):
        raise ValueError("output path must not contain ..")
    workspace = (
        workspace_root.resolve()
        if workspace_root is not None
        else pathlib.Path.cwd().resolve()
    )
    task_output_root = _task_output_root(workspace_root)
    tmp_alias_root = pathlib.Path("/tmp")
    tmp_root = pathlib.Path("/tmp").resolve()
    if not raw_path.is_absolute():
        task_output_parts = TASK_OUTPUT_RELATIVE_DIR.parts
        if raw_path.parts[: len(task_output_parts)] == task_output_parts:
            return _validate_output_path(workspace / raw_path, task_output_root)
        return _validate_output_path(task_output_root / raw_path, task_output_root)
    if _path_is_relative_to(raw_path, tmp_alias_root):
        raw_path = tmp_root / raw_path.relative_to(tmp_alias_root)
    resolved_output = raw_path.resolve(strict=False)
    for root in (task_output_root, tmp_root):
        resolved_root = root.resolve(strict=False)
        if _path_is_relative_to(resolved_output, resolved_root):
            if root == tmp_root and resolved_output.parent == resolved_root:
                raise ValueError(
                    "output path under /tmp must use an owner-private subdirectory"
                )
            return _validate_output_path(raw_path, root)
    raise ValueError(
        f"output path must stay under {task_output_root.resolve(strict=False)} or {tmp_root}"
    )


def _resolve_rollout_relative_path(value: str) -> pathlib.PurePosixPath:
    candidate = pathlib.PurePosixPath(value)
    normalized = candidate.as_posix()
    if not (
        ACTIVE_ROLLOUT_RELATIVE_RE.fullmatch(normalized)
        or ARCHIVED_ROLLOUT_RELATIVE_RE.fullmatch(normalized)
        or ROOT_ROLLOUT_RELATIVE_RE.fullmatch(normalized)
    ):
        raise ValueError(
            "rollout path must match sessions/YYYY/MM/DD/rollout-*.jsonl, archived_sessions/rollout-*.jsonl, or rollout-*.jsonl"
        )
    return candidate


def _path_is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _directory_open_flags() -> int:
    if not SECURE_ROLLOUT_DIR_FD_SUPPORTED:
        raise OSError(
            "secure rollout reads require O_DIRECTORY, O_NOFOLLOW, and descriptor-relative open/stat"
        )
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _regular_file_open_flags() -> int:
    _directory_open_flags()
    nonblocking_flag = getattr(os, "O_NONBLOCK", None)
    if nonblocking_flag is None:
        raise OSError("secure rollout reads require O_NONBLOCK")
    return os.O_RDONLY | os.O_NOFOLLOW | nonblocking_flag | getattr(os, "O_CLOEXEC", 0)


def _validate_relative_path_parts(
    relative_path: pathlib.PurePosixPath,
) -> tuple[str, ...]:
    if relative_path.is_absolute():
        raise ValueError("path must stay under Codex root")
    parts = relative_path.parts
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path must stay under Codex root")
    return parts


def _inspect_safe_codex_root(
    codex_root: pathlib.Path,
) -> tuple[pathlib.Path, os.stat_result]:
    expanded_root = codex_root.expanduser()
    root_entry = expanded_root.lstat()
    if stat.S_ISLNK(root_entry.st_mode):
        raise ValueError("Codex root is a symlink")
    if not stat.S_ISDIR(root_entry.st_mode):
        raise ValueError("Codex root is not a directory")
    return expanded_root, root_entry


def _open_pinned_codex_root(codex_root: pathlib.Path) -> int:
    expanded_root, observed = _inspect_safe_codex_root(codex_root)
    try:
        fd = os.open(str(expanded_root), _directory_open_flags())
    except FileNotFoundError as error:
        raise ValueError("Codex root changed after initial inspection") from error
    try:
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise ValueError("Codex root is not a directory")
        if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
            raise ValueError("Codex root changed during open")
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_pinned_directory_from_fd(
    root_fd: int,
    relative_path: pathlib.PurePosixPath,
) -> int:
    directory_fd = os.dup(root_fd)
    try:
        for part in _validate_relative_path_parts(relative_path):
            observed = os.stat(part, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(observed.st_mode):
                raise ValueError("path uses a symlink ancestor")
            if not stat.S_ISDIR(observed.st_mode):
                raise ValueError("path ancestor is not a directory")
            try:
                next_fd = os.open(part, _directory_open_flags(), dir_fd=directory_fd)
            except FileNotFoundError as error:
                raise ValueError("path ancestor changed during open") from error
            try:
                opened = os.fstat(next_fd)
                if not stat.S_ISDIR(opened.st_mode):
                    raise ValueError("path ancestor is not a directory")
                if (opened.st_dev, opened.st_ino) != (
                    observed.st_dev,
                    observed.st_ino,
                ):
                    raise ValueError("path ancestor changed during open")
            except Exception:
                os.close(next_fd)
                raise
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except Exception:
        os.close(directory_fd)
        raise


def _rollout_identity_from_stat(stat_result: os.stat_result) -> RolloutIdentity:
    if not stat.S_ISREG(stat_result.st_mode):
        raise ValueError("rollout path is not a regular file")
    return RolloutIdentity(
        mode=stat_result.st_mode,
        uid=stat_result.st_uid,
        gid=stat_result.st_gid,
        size=stat_result.st_size,
        device=stat_result.st_dev,
        inode=stat_result.st_ino,
        mtime_ns=stat_result.st_mtime_ns,
        ctime_ns=stat_result.st_ctime_ns,
    )


def _stable_rollout_identity_from_stat(
    stat_result: os.stat_result,
) -> RolloutStableIdentity:
    if stat.S_ISLNK(stat_result.st_mode):
        raise ValueError("rollout path is a symlink")
    if not stat.S_ISREG(stat_result.st_mode):
        raise ValueError("rollout path is not a regular file")
    return RolloutStableIdentity(
        device=stat_result.st_dev,
        inode=stat_result.st_ino,
    )


def _rollout_inventory_identity_from_stat(
    stat_result: os.stat_result,
) -> RolloutInventoryIdentity:
    return RolloutInventoryIdentity(
        mode=stat_result.st_mode,
        uid=stat_result.st_uid,
        gid=stat_result.st_gid,
        size=stat_result.st_size,
        device=stat_result.st_dev,
        inode=stat_result.st_ino,
        mtime_ns=stat_result.st_mtime_ns,
        ctime_ns=stat_result.st_ctime_ns,
    )


def _capture_rollout_inventory_identity_from_parent_fd(
    parent_fd: int,
    name: str,
) -> RolloutInventoryIdentity:
    try:
        stat_result = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as error:
        raise ValueError("rollout identity changed during enumeration") from error
    return _rollout_inventory_identity_from_stat(stat_result)


def _assert_rollout_inventory_identity(
    actual: RolloutInventoryIdentity,
    expected: RolloutInventoryIdentity,
    *,
    allow_append: bool,
    phase: str,
) -> None:
    matches = _rollout_protected_properties_match(
        actual,
        expected,
        allow_append=allow_append,
    )
    if not matches:
        raise ValueError(f"rollout identity changed {phase}")


def _rollout_protected_properties_match(
    actual: RolloutIdentity | RolloutInventoryIdentity,
    expected: RolloutIdentity | RolloutInventoryIdentity,
    *,
    allow_append: bool,
) -> bool:
    """Compare object identity, access policy, and the permitted size relation."""

    # mtime/ctime are observation hints only. Prefix checkpoints bind every byte
    # this command consumes, so timestamp drift causes revalidation, not failure.
    size_matches = (
        actual.size >= expected.size if allow_append else actual.size == expected.size
    )
    return (
        actual.device == expected.device
        and actual.inode == expected.inode
        and actual.mode == expected.mode
        and actual.uid == expected.uid
        and actual.gid == expected.gid
        and size_matches
    )


def _validated_rollout_inventory_identity_from_parent_fd(
    parent_fd: int,
    name: str,
    expected: RolloutInventoryIdentity,
    *,
    allow_append: bool,
    phase: str,
) -> RolloutInventoryIdentity:
    try:
        stat_result = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as error:
        raise ValueError(f"rollout identity changed {phase}") from error
    actual = _rollout_inventory_identity_from_stat(stat_result)
    _assert_rollout_inventory_identity(
        actual,
        expected,
        allow_append=allow_append,
        phase=phase,
    )
    if stat.S_ISLNK(actual.mode):
        raise ValueError("rollout path is a symlink")
    if not stat.S_ISREG(actual.mode):
        raise ValueError("rollout path is not a regular file")
    return actual


def _rollout_candidate_identity_from_stat(
    stat_result: os.stat_result,
) -> RolloutCandidateIdentity:
    stable = _stable_rollout_identity_from_stat(stat_result)
    return RolloutCandidateIdentity(
        snapshot=_rollout_identity_from_stat(stat_result),
        stable=stable,
    )


def _capture_rollout_candidate_identity_from_parent_fd(
    parent_fd: int,
    name: str,
    inventory_identity: RolloutInventoryIdentity,
) -> RolloutCandidateIdentity:
    phase = "after enumeration"
    _validated_rollout_inventory_identity_from_parent_fd(
        parent_fd,
        name,
        inventory_identity,
        allow_append=False,
        phase=phase,
    )
    try:
        fd = os.open(name, _regular_file_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError as error:
        raise ValueError("rollout identity changed during open") from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError("rollout identity changed during open") from error
        raise
    try:
        descriptor_stat = os.fstat(fd)
        descriptor_inventory_identity = _rollout_inventory_identity_from_stat(
            descriptor_stat
        )
        _assert_rollout_inventory_identity(
            descriptor_inventory_identity,
            inventory_identity,
            allow_append=False,
            phase="during open",
        )
        descriptor_identity = _rollout_candidate_identity_from_stat(descriptor_stat)
        initial_proof, _snapshot = _read_rollout_prefix_proof(
            fd,
            min(descriptor_identity.snapshot.size, MAX_SESSION_META_SCAN_BYTES),
            phase="during open",
        )
        current, _snapshot_identity, proof, _verified_snapshot = (
            _assert_immutable_rollout_checkpoint(
                fd,
                parent_fd,
                name,
                descriptor_identity.snapshot,
                initial_proof,
                phase="during open",
            )
        )
        return RolloutCandidateIdentity(
            snapshot=current,
            stable=RolloutStableIdentity(
                device=current.device,
                inode=current.inode,
            ),
            prefix_proof=proof,
        )
    finally:
        os.close(fd)


def _assert_rollout_identity(
    actual: RolloutIdentity,
    expected: RolloutIdentity,
    *,
    phase: str,
) -> None:
    if actual != expected:
        raise ValueError(f"rollout identity changed {phase}")


def _assert_append_only_rollout_identity(
    actual: RolloutIdentity,
    expected: RolloutIdentity,
    *,
    phase: str,
) -> None:
    if not _rollout_protected_properties_match(
        actual,
        expected,
        allow_append=True,
    ):
        raise ValueError(f"rollout identity changed {phase}")


def _assert_immutable_rollout_identity(
    actual: RolloutIdentity,
    expected: RolloutIdentity,
    *,
    phase: str,
) -> None:
    if not _rollout_protected_properties_match(
        actual,
        expected,
        allow_append=False,
    ):
        raise ValueError(f"rollout identity changed {phase}")


def _read_rollout_prefix_proof(
    fd: int,
    length: int,
    *,
    expected_prefix: RolloutPrefixProof | None = None,
    phase: str,
) -> tuple[RolloutPrefixProof, bytes]:
    if length < 0 or length > MAX_SESSION_META_SCAN_BYTES:
        raise ValueError(f"rollout identity changed {phase}")
    if expected_prefix is not None and (
        expected_prefix.length < 0
        or expected_prefix.length > length
        or expected_prefix.length > MAX_SESSION_META_SCAN_BYTES
    ):
        raise ValueError(f"rollout identity changed {phase}")
    digest = hashlib.sha256()
    snapshot = bytearray()
    offset = 0
    verified_length = expected_prefix.length if expected_prefix is not None else 0

    def read_through(target: int) -> None:
        nonlocal offset
        while offset < target:
            requested = min(SESSION_META_READ_CHUNK_BYTES, target - offset)
            chunk = os.pread(fd, requested, offset)
            if not chunk or len(chunk) > requested:
                raise ValueError(f"rollout identity changed {phase}")
            digest.update(chunk)
            snapshot.extend(chunk)
            offset += len(chunk)

    read_through(verified_length)
    if expected_prefix is not None and digest.hexdigest() != expected_prefix.sha256:
        raise ValueError(f"rollout identity changed {phase}")
    read_through(length)
    return (
        RolloutPrefixProof(length=length, sha256=digest.hexdigest()),
        bytes(snapshot),
    )


def _rollout_checkpoint_identity(
    fd: int,
    parent_fd: int,
    name: str,
    expected: RolloutIdentity,
    *,
    allow_append: bool,
    phase: str,
) -> RolloutIdentity:
    assertion = (
        _assert_append_only_rollout_identity
        if allow_append
        else _assert_immutable_rollout_identity
    )
    descriptor_identity = _rollout_identity_from_stat(os.fstat(fd))
    assertion(descriptor_identity, expected, phase=phase)
    try:
        path_identity = _rollout_identity_from_stat(
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        )
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(f"rollout identity changed {phase}") from error
    assertion(path_identity, descriptor_identity, phase=phase)
    return path_identity


def _assert_immutable_rollout_checkpoint(
    fd: int,
    parent_fd: int,
    name: str,
    expected: RolloutIdentity,
    prefix_proof: RolloutPrefixProof | None,
    *,
    phase: str,
) -> tuple[RolloutIdentity, RolloutIdentity, RolloutPrefixProof, bytes]:
    """Revalidate the bounded content consumed from an immutable rollout."""

    if prefix_proof is None:
        raise ValueError(f"rollout identity changed {phase}")
    path_identity = _rollout_checkpoint_identity(
        fd, parent_fd, name, expected, allow_append=False, phase=phase
    )
    advanced_proof, _snapshot = _read_rollout_prefix_proof(
        fd,
        min(path_identity.size, MAX_SESSION_META_SCAN_BYTES),
        expected_prefix=prefix_proof,
        phase=phase,
    )
    path_after = _rollout_checkpoint_identity(
        fd, parent_fd, name, path_identity, allow_append=False, phase=phase
    )
    _verified_proof, verified_snapshot = _read_rollout_prefix_proof(
        fd,
        advanced_proof.length,
        expected_prefix=advanced_proof,
        phase=phase,
    )
    path_final = _rollout_checkpoint_identity(
        fd, parent_fd, name, path_after, allow_append=False, phase=phase
    )
    return path_final, path_final, advanced_proof, verified_snapshot


def _capture_active_rollout_candidate_identity_from_parent_fd(
    parent_fd: int,
    name: str,
    inventory_identity: RolloutInventoryIdentity,
) -> RolloutCandidateIdentity:
    phase = "during prefix proof capture"
    observed_inventory_identity = _validated_rollout_inventory_identity_from_parent_fd(
        parent_fd,
        name,
        inventory_identity,
        allow_append=False,
        phase="after enumeration",
    )
    try:
        fd = os.open(name, _regular_file_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError as error:
        raise ValueError(f"rollout identity changed {phase}") from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError(f"rollout identity changed {phase}") from error
        raise
    try:
        initial_stat = os.fstat(fd)
        initial_inventory_identity = _rollout_inventory_identity_from_stat(initial_stat)
        _assert_rollout_inventory_identity(
            initial_inventory_identity,
            observed_inventory_identity,
            allow_append=False,
            phase=phase,
        )
        initial = _rollout_candidate_identity_from_stat(initial_stat)
        initial_proof, _snapshot = _read_rollout_prefix_proof(
            fd,
            min(initial.snapshot.size, MAX_SESSION_META_SCAN_BYTES),
            phase=phase,
        )
        descriptor_after_proof = _rollout_inventory_identity_from_stat(os.fstat(fd))
        _assert_rollout_inventory_identity(
            descriptor_after_proof,
            inventory_identity,
            allow_append=False,
            phase=phase,
        )
        _validated_rollout_inventory_identity_from_parent_fd(
            parent_fd,
            name,
            inventory_identity,
            allow_append=False,
            phase=phase,
        )
        current, _snapshot_identity, proof, _verified_snapshot = (
            _assert_append_only_rollout_checkpoint(
                fd,
                parent_fd,
                name,
                initial.snapshot,
                initial_proof,
                phase=phase,
            )
        )
        return RolloutCandidateIdentity(
            snapshot=current,
            stable=RolloutStableIdentity(
                device=current.device,
                inode=current.inode,
            ),
            prefix_proof=proof,
        )
    finally:
        os.close(fd)


def _assert_append_only_rollout_checkpoint(
    fd: int,
    parent_fd: int,
    name: str,
    expected: RolloutIdentity,
    prefix_proof: RolloutPrefixProof | None,
    *,
    phase: str,
) -> tuple[RolloutIdentity, RolloutIdentity, RolloutPrefixProof, bytes]:
    if prefix_proof is None:
        raise ValueError(f"rollout identity changed {phase}")
    current = _rollout_checkpoint_identity(
        fd, parent_fd, name, expected, allow_append=True, phase=phase
    )
    advanced_proof, _snapshot = _read_rollout_prefix_proof(
        fd,
        min(current.size, MAX_SESSION_META_SCAN_BYTES),
        expected_prefix=prefix_proof,
        phase=phase,
    )
    current_after = _rollout_checkpoint_identity(
        fd, parent_fd, name, current, allow_append=True, phase=phase
    )
    _verified_proof, verified_snapshot = _read_rollout_prefix_proof(
        fd,
        advanced_proof.length,
        expected_prefix=advanced_proof,
        phase=phase,
    )
    current_final = _rollout_checkpoint_identity(
        fd, parent_fd, name, current_after, allow_append=True, phase=phase
    )
    if current_final != current_after:
        _reverified_proof, verified_snapshot = _read_rollout_prefix_proof(
            fd,
            advanced_proof.length,
            expected_prefix=advanced_proof,
            phase=phase,
        )
        _rollout_checkpoint_identity(
            fd,
            parent_fd,
            name,
            current_final,
            allow_append=False,
            phase=phase,
        )
    return current_final, current, advanced_proof, verified_snapshot


def _open_pinned_regular_file_from_fd(
    parent_fd: int,
    name: str,
    *,
    expected_identity: RolloutCandidateIdentity | None = None,
    allow_append: bool = False,
) -> tuple[
    int,
    RolloutIdentity,
    RolloutIdentity | None,
    RolloutPrefixProof | None,
    bytes | None,
]:
    if name in ("", ".", "..") or "/" in name:
        raise ValueError("rollout path has an invalid file name")
    try:
        observed_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as error:
        if expected_identity is not None:
            raise ValueError("rollout identity changed after enumeration") from error
        raise
    if stat.S_ISLNK(observed_stat.st_mode):
        raise ValueError("rollout path is a symlink")
    observed = _rollout_identity_from_stat(observed_stat)
    if expected_identity is not None:
        if allow_append:
            _assert_append_only_rollout_identity(
                observed,
                expected_identity.snapshot,
                phase="after enumeration",
            )
        else:
            _assert_immutable_rollout_identity(
                observed,
                expected_identity.snapshot,
                phase="after enumeration",
            )
    try:
        fd = os.open(name, _regular_file_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError as error:
        raise ValueError("rollout changed during open") from error
    try:
        opened_stat = os.fstat(fd)
        opened = _rollout_identity_from_stat(opened_stat)
        if expected_identity is None:
            _assert_rollout_identity(opened, observed, phase="during open")
        elif allow_append:
            current, snapshot_identity, prefix_proof, verified_snapshot = (
                _assert_append_only_rollout_checkpoint(
                    fd,
                    parent_fd,
                    name,
                    observed,
                    expected_identity.prefix_proof,
                    phase="during open",
                )
            )
            return fd, current, snapshot_identity, prefix_proof, verified_snapshot
        else:
            current, snapshot_identity, prefix_proof, verified_snapshot = (
                _assert_immutable_rollout_checkpoint(
                    fd,
                    parent_fd,
                    name,
                    expected_identity.snapshot,
                    expected_identity.prefix_proof,
                    phase="during open",
                )
            )
            return fd, current, snapshot_identity, prefix_proof, verified_snapshot
        try:
            current_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as error:
            raise ValueError("rollout changed during open") from error
        current = _rollout_identity_from_stat(current_stat)
        if expected_identity is None:
            _assert_rollout_identity(current, opened, phase="during open")
        elif allow_append:
            _assert_append_only_rollout_identity(
                current,
                opened,
                phase="during open",
            )
        return fd, current, None, None, None
    except Exception:
        os.close(fd)
        raise


class _PinnedRolloutHandle:
    def __init__(
        self,
        fd: int,
        parent_fd: int,
        name: str,
        open_identity: RolloutIdentity,
        verified_snapshot_identity: RolloutIdentity | None,
        prefix_proof: RolloutPrefixProof | None,
        verified_snapshot: bytes | None,
    ) -> None:
        try:
            self._handle = os.fdopen(fd, "rb")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            os.close(parent_fd)
            raise
        self._parent_fd = parent_fd
        self._name = name
        self._open_identity = open_identity
        self._verified_snapshot_identity = verified_snapshot_identity
        self._prefix_proof = prefix_proof
        self._verified_snapshot = verified_snapshot

    def __enter__(self) -> _PinnedRolloutHandle:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._handle, name)

    def close(self) -> None:
        try:
            close = getattr(self._handle, "close", None)
            if close is not None:
                close()
            else:
                self._handle.__exit__(None, None, None)
        finally:
            if self._parent_fd != -1:
                os.close(self._parent_fd)
                self._parent_fd = -1

    def assert_identity(self, expected: RolloutIdentity, *, phase: str) -> None:
        _assert_rollout_identity(
            _rollout_identity_from_stat(os.fstat(self.fileno())),
            expected,
            phase=phase,
        )
        try:
            current = _rollout_identity_from_stat(
                os.stat(
                    self._name,
                    dir_fd=self._parent_fd,
                    follow_symlinks=False,
                )
            )
        except (FileNotFoundError, ValueError) as error:
            raise ValueError(f"rollout identity changed {phase}") from error
        _assert_rollout_identity(current, expected, phase=phase)

    def assert_append_only_identity(
        self,
        expected: RolloutIdentity,
        *,
        phase: str,
    ) -> RolloutIdentity:
        current, snapshot_identity, prefix_proof, verified_snapshot = (
            _assert_append_only_rollout_checkpoint(
                self.fileno(),
                self._parent_fd,
                self._name,
                expected,
                self._prefix_proof,
                phase=phase,
            )
        )
        self._verified_snapshot_identity = snapshot_identity
        self._prefix_proof = prefix_proof
        self._verified_snapshot = verified_snapshot
        return current

    def assert_immutable_identity(
        self,
        expected: RolloutIdentity,
        *,
        phase: str,
    ) -> RolloutIdentity:
        current, snapshot_identity, prefix_proof, verified_snapshot = (
            _assert_immutable_rollout_checkpoint(
                self.fileno(),
                self._parent_fd,
                self._name,
                expected,
                self._prefix_proof,
                phase=phase,
            )
        )
        self._verified_snapshot_identity = snapshot_identity
        self._prefix_proof = prefix_proof
        self._verified_snapshot = verified_snapshot
        return current

    @property
    def open_identity(self) -> RolloutIdentity:
        return self._open_identity

    @property
    def verified_snapshot(self) -> bytes | None:
        return self._verified_snapshot

    @property
    def verified_snapshot_identity(self) -> RolloutIdentity | None:
        return self._verified_snapshot_identity


def _open_pinned_rollout_text_from_parent_fd(
    parent_fd: int,
    name: str,
    *,
    expected_identity: RolloutCandidateIdentity | None = None,
    allow_append: bool = False,
) -> _PinnedRolloutHandle:
    fd, open_identity, snapshot_identity, prefix_proof, verified_snapshot = (
        _open_pinned_regular_file_from_fd(
            parent_fd,
            name,
            expected_identity=expected_identity,
            allow_append=allow_append,
        )
    )
    try:
        pinned_parent_fd = os.dup(parent_fd)
    except Exception:
        os.close(fd)
        raise
    return _PinnedRolloutHandle(
        fd,
        pinned_parent_fd,
        name,
        open_identity,
        snapshot_identity,
        prefix_proof,
        verified_snapshot,
    )


def _open_pinned_rollout_text(
    codex_root: pathlib.Path,
    rollout_relative_path: pathlib.PurePosixPath,
) -> _PinnedRolloutHandle:
    parts = _validate_relative_path_parts(rollout_relative_path)
    if not parts:
        raise ValueError("rollout path must name a file")
    root_fd = _open_pinned_codex_root(codex_root)
    try:
        parent_fd = _open_pinned_directory_from_fd(
            root_fd,
            pathlib.PurePosixPath(*parts[:-1]),
        )
        try:
            return _open_pinned_rollout_text_from_parent_fd(parent_fd, parts[-1])
        finally:
            os.close(parent_fd)
    finally:
        os.close(root_fd)


class _HashingReader:
    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self.hasher = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self.handle.read(size)
        if not isinstance(data, bytes):
            raise TypeError("rollout hashing reader requires binary input")
        self.hasher.update(data)
        self.bytes_read += len(data)
        return data

    def tell(self) -> int:
        return self.handle.tell()

    def hexdigest(self) -> str:
        return self.hasher.hexdigest()


def _open_local_rollout_text(
    codex_root: pathlib.Path | int | EnumeratedRolloutParent,
    rollout_relative_path: pathlib.PurePosixPath,
):
    if isinstance(codex_root, EnumeratedRolloutParent):
        return _open_pinned_rollout_text_from_parent_fd(
            codex_root.fd,
            rollout_relative_path.name,
            expected_identity=codex_root.expected_identity,
            allow_append=codex_root.allow_append,
        )
    if isinstance(codex_root, int):
        return _open_pinned_rollout_text_from_parent_fd(
            codex_root,
            rollout_relative_path.name,
        )
    return _open_pinned_rollout_text(codex_root, rollout_relative_path)


def _file_sha256(path: pathlib.Path) -> str:
    parent_fd = _open_pinned_codex_root(path.parent)
    try:
        try:
            handle = _open_pinned_rollout_text_from_parent_fd(parent_fd, path.name)
        except ValueError as error:
            raise OSError(str(error)) from error
    finally:
        os.close(parent_fd)
    digest = hashlib.sha256()
    with handle:
        identity = _rollout_identity_from_stat(os.fstat(handle.fileno()))
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        handle.assert_identity(identity, phase="after hash")
    return digest.hexdigest()


def _read_local_rollout_bytes(
    codex_root: pathlib.Path,
    rollout_relative_path: pathlib.PurePosixPath,
    *,
    max_bytes: int,
) -> bytes:
    with _open_pinned_rollout_text(codex_root, rollout_relative_path) as handle:
        identity = _rollout_identity_from_stat(os.fstat(handle.fileno()))
        if max_bytes and identity.size > max_bytes:
            raise ValueError(f"rollout too large: {identity.size} bytes > {max_bytes}")
        data = handle.read(identity.size + 1)
        handle.assert_identity(identity, phase="after read")
        if len(data) != identity.size:
            raise ValueError(
                "rollout read did not match snapshot size: "
                f"{len(data)} bytes != {identity.size}"
            )
        return data


def _write_private_bytes(output: pathlib.Path, data: bytes) -> None:
    private_output.write_private_bytes(output, data)


def _flat_archived_rollout_matches_date(
    rollout_path: pathlib.Path, date_value: dt.date
) -> bool:
    return rollout_path.name.startswith(f"rollout-{date_value.strftime('%Y-%m-%d')}")


def _flat_archived_rollout_matches_date_or_unknown(
    rollout_path: pathlib.Path, date_value: dt.date
) -> bool:
    return (
        _flat_archived_rollout_matches_date(
            rollout_path,
            date_value,
        )
        or _session_meta_rollout_filename_date(rollout_path.name) is None
    )


def _flat_archived_rollout_matches_bounds_or_unknown(
    rollout_path: pathlib.Path,
    rollout_start: dt.datetime | None,
    rollout_end: dt.datetime | None,
    *,
    filename_mode: str,
) -> bool:
    if _session_meta_rollout_filename_date(rollout_path.name) is None:
        return filename_mode != "known"
    return _rollout_matches_bounds(
        rollout_path,
        rollout_start,
        rollout_end,
        filename_mode=filename_mode,
    )


def _is_raw_rollout_file(path: pathlib.Path) -> bool:
    return path.name.startswith("rollout-") and not path.name.startswith(
        "rollout-summary"
    )


def _session_meta_rollout_filename_date(name: str) -> dt.date | None:
    window = _rollout_filename_window(pathlib.PurePosixPath(name))
    if window is None:
        return None
    return window[0].date()


def _session_meta_rollout_dedupe_key(relative_path: pathlib.PurePosixPath) -> str:
    return relative_path.as_posix()


def _session_meta_flat_undated_alias(
    relative_path: pathlib.PurePosixPath,
) -> str | None:
    parts = relative_path.parts
    if not parts:
        return None
    name = parts[-1]
    if not (name.startswith("rollout-") and name.endswith(".jsonl")):
        return None
    if _session_meta_rollout_filename_date(name) is not None:
        return None
    if (
        len(parts) == 1
        or parts[0] == "sessions"
        or (len(parts) == 2 and parts[0] == "archived_sessions")
    ):
        return f"{SESSION_META_FLAT_UNDATED_ALIAS_PREFIX}:{name}"
    return None


def _session_meta_is_flat_archived_undated(
    relative_path: pathlib.PurePosixPath,
) -> bool:
    return (
        relative_path.parts[:1] == ("archived_sessions",)
        and _session_meta_flat_undated_alias(relative_path) is not None
    )


def _session_meta_allows_append(
    relative_path: pathlib.PurePosixPath,
) -> bool:
    return len(relative_path.parts) == 1 or relative_path.parts[0] == "sessions"


def _session_meta_record_timestamp(row: dict[str, Any]) -> dt.datetime | None:
    timestamp = row.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    try:
        return _parse_rollout_bound(timestamp, "session_meta.timestamp")
    except (ValueError, OverflowError):
        return None


def _session_meta_record_matches_window(
    row: dict[str, Any],
    date_value: dt.date,
    rollout_start: dt.datetime | None,
    rollout_end: dt.datetime | None,
) -> bool:
    timestamp = _session_meta_record_timestamp(row)
    if timestamp is None:
        return False
    if timestamp.date() != date_value:
        return False
    if rollout_start is not None and timestamp < rollout_start:
        return False
    if rollout_end is not None and timestamp >= rollout_end:
        return False
    return True


def _session_meta_snapshot_reader(
    identity: RolloutIdentity,
    verified_snapshot: bytes | None,
) -> io.BytesIO:
    phase = "before session-meta scan"
    if (
        verified_snapshot is None
        or len(verified_snapshot) > MAX_SESSION_META_SCAN_BYTES
        or identity.size < len(verified_snapshot)
    ):
        raise ValueError(f"rollout identity changed {phase}")
    source_has_unread_bytes = identity.size > len(verified_snapshot)
    if source_has_unread_bytes and len(verified_snapshot) < MAX_SESSION_META_SCAN_BYTES:
        raise ValueError(f"rollout identity changed {phase}")
    unread_sentinel = b"\0" if source_has_unread_bytes else b""
    return io.BytesIO(verified_snapshot + unread_sentinel)


def _session_meta_date_overlaps_window(
    date_value: dt.date,
    rollout_start: dt.datetime | None,
    rollout_end: dt.datetime | None,
) -> bool:
    day_start = dt.datetime.combine(date_value, dt.time.min, tzinfo=dt.timezone.utc)
    day_end = day_start + dt.timedelta(days=1)
    if rollout_start is not None and day_end <= rollout_start:
        return False
    if rollout_end is not None and day_start >= rollout_end:
        return False
    return True


def _decode_session_meta_line(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("session-meta record is not valid UTF-8") from error


def _parse_session_meta_snapshot(
    scan_handle: Any,
    *,
    date_value: dt.date | None,
    require_record_date_match: bool,
    rollout_start: dt.datetime | None,
    rollout_end: dt.datetime | None,
) -> tuple[dt.date | None, str, str, dt.datetime | None] | None:
    for line in _bounded_session_meta_lines(
        scan_handle,
        MAX_SESSION_META_SCAN_BYTES,
    ):
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "session_meta":
            continue
        timestamp = _session_meta_record_timestamp(obj)
        if require_record_date_match:
            if date_value is None or not _session_meta_record_matches_window(
                obj,
                date_value,
                rollout_start,
                rollout_end,
            ):
                continue
        elif timestamp is None:
            if date_value is None or not _session_meta_date_overlaps_window(
                date_value,
                rollout_start,
                rollout_end,
            ):
                continue
        else:
            if rollout_start is not None and timestamp < rollout_start:
                continue
            if rollout_end is not None and timestamp >= rollout_end:
                continue
        payload = obj.get("payload", {})
        if not isinstance(payload, dict):
            continue
        session_id_value = payload.get("id")
        if not isinstance(session_id_value, str) or not session_id_value:
            continue
        session_id = session_id_value
        cwd = str(payload.get("cwd", ""))
        return (
            timestamp.date() if timestamp is not None else date_value,
            session_id,
            cwd,
            timestamp,
        )
    return None


def _session_meta_from_rollout(
    codex_root: pathlib.Path,
    rollout_relative_path: pathlib.PurePosixPath,
    *,
    parent_fd: int | None = None,
    expected_identity: RolloutCandidateIdentity | None = None,
    date_value: dt.date | None = None,
    require_record_date_match: bool = False,
    rollout_start: dt.datetime | None = None,
    rollout_end: dt.datetime | None = None,
) -> tuple[dt.date | None, str, str, dt.datetime | None] | None:
    allow_append = _session_meta_allows_append(rollout_relative_path)
    rollout_source: pathlib.Path | int | EnumeratedRolloutParent
    if parent_fd is not None and expected_identity is not None:
        rollout_source = EnumeratedRolloutParent(
            parent_fd,
            expected_identity,
            allow_append,
        )
    else:
        rollout_source = parent_fd if parent_fd is not None else codex_root
    try:
        handle = _open_local_rollout_text(
            rollout_source,
            rollout_relative_path,
        )
    except FileNotFoundError as error:
        if expected_identity is not None:
            raise SessionMetaRolloutError(
                "rollout identity changed after enumeration",
                rollout=rollout_relative_path.as_posix(),
            ) from error
        return None
    except OSError as exc:
        raise SessionMetaRolloutError(
            "rollout unreadable",
            rollout=rollout_relative_path.as_posix(),
        ) from exc
    except ValueError as exc:
        raise SessionMetaRolloutError(
            str(exc),
            rollout=rollout_relative_path.as_posix(),
        ) from exc
    try:
        with handle:
            if expected_identity is not None:
                if allow_append:
                    identity = handle.assert_append_only_identity(
                        handle.open_identity,
                        phase="before session-meta scan",
                    )
                else:
                    identity = handle.assert_immutable_identity(
                        handle.open_identity,
                        phase="before session-meta scan",
                    )
                snapshot_identity = handle.verified_snapshot_identity
                if snapshot_identity is None:
                    raise ValueError(
                        "rollout identity changed before session-meta scan"
                    )
                snapshot_bytes = handle.verified_snapshot
                scan_handle = _session_meta_snapshot_reader(
                    snapshot_identity,
                    snapshot_bytes,
                )
            else:
                identity = _rollout_identity_from_stat(os.fstat(handle.fileno()))
                scan_handle = handle
            result = _parse_session_meta_snapshot(
                scan_handle,
                date_value=date_value,
                require_record_date_match=require_record_date_match,
                rollout_start=rollout_start,
                rollout_end=rollout_end,
            )
            if expected_identity is None:
                handle.assert_identity(identity, phase="after session-meta scan")
            elif allow_append:
                refreshed_identity = handle.assert_append_only_identity(
                    identity,
                    phase="after session-meta scan",
                )
                refreshed_snapshot_identity = handle.verified_snapshot_identity
                if refreshed_snapshot_identity is None:
                    raise ValueError("rollout identity changed after session-meta scan")
                refreshed_snapshot_bytes = handle.verified_snapshot
                same_verified_snapshot = (
                    refreshed_snapshot_identity.size == snapshot_identity.size
                    and refreshed_snapshot_bytes == snapshot_bytes
                )
                if (
                    result is None
                    and same_verified_snapshot
                    and refreshed_identity.size != refreshed_snapshot_identity.size
                ):
                    raise ValueError("rollout identity changed after session-meta scan")
                if result is None and not same_verified_snapshot:
                    result = _parse_session_meta_snapshot(
                        _session_meta_snapshot_reader(
                            refreshed_snapshot_identity,
                            refreshed_snapshot_bytes,
                        ),
                        date_value=date_value,
                        require_record_date_match=require_record_date_match,
                        rollout_start=rollout_start,
                        rollout_end=rollout_end,
                    )
                    final_identity = handle.assert_append_only_identity(
                        refreshed_identity,
                        phase="after refreshed session-meta scan",
                    )
                    final_snapshot_identity = handle.verified_snapshot_identity
                    if final_snapshot_identity is None:
                        raise ValueError(
                            "rollout identity changed after session-meta scan"
                        )
                    final_snapshot_bytes = handle.verified_snapshot
                    if result is None and (
                        final_snapshot_identity.size != refreshed_snapshot_identity.size
                        or final_snapshot_bytes != refreshed_snapshot_bytes
                        or final_identity.size != final_snapshot_identity.size
                    ):
                        raise ValueError(
                            "rollout identity changed after session-meta scan"
                        )
            else:
                handle.assert_immutable_identity(
                    identity,
                    phase="after session-meta scan",
                )
            return result
    except OSError as error:
        raise SessionMetaRolloutError(
            "rollout unreadable",
            rollout=rollout_relative_path.as_posix(),
        ) from error
    except ValueError as error:
        raise SessionMetaRolloutError(
            str(error),
            rollout=rollout_relative_path.as_posix(),
        ) from error


def _session_meta_rollout_sort_key(
    relative_path: pathlib.PurePosixPath,
    cached_timestamp: dt.datetime | None = None,
) -> tuple[dt.datetime, str]:
    window = _rollout_filename_window(relative_path)
    timestamp = cached_timestamp or (
        window[0]
        if window is not None
        else dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    )
    return (timestamp, relative_path.as_posix())


def _parse_kv_lines(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def _run_subprocess_text(
    argv: list[str],
    *,
    input_text: str | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        if timeout_seconds is None:
            raise RuntimeError("command timed out") from exc
        raise RuntimeError(f"command timed out after {timeout_seconds}s") from exc


def _run_subprocess_text_bounded(
    argv: list[str],
    *,
    input_text: str | None = None,
    timeout_seconds: int,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> subprocess.CompletedProcess[str]:
    if max_stdout_bytes < 1 or max_stderr_bytes < 1:
        raise ValueError("bounded subprocess output limits must be positive")
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"command not found: {argv[0]}") from exc

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    input_bytes = (input_text or "").encode("utf-8")
    input_offset = 0
    stdout = bytearray()
    stderr = bytearray()
    selector = selectors.DefaultSelector()
    for stream, events, label in (
        (process.stdout, selectors.EVENT_READ, "stdout"),
        (process.stderr, selectors.EVENT_READ, "stderr"),
    ):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, events, label)
    if input_bytes:
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        process.stdin.close()

    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"command timed out after {timeout_seconds}s")
            for key, _ in selector.select(min(0.25, remaining)):
                stream = key.fileobj
                if key.data == "stdin":
                    try:
                        written = os.write(
                            stream.fileno(),
                            input_bytes[input_offset : input_offset + 65536],
                        )
                    except BrokenPipeError:
                        written = 0
                        input_offset = len(input_bytes)
                    else:
                        input_offset += written
                    if input_offset >= len(input_bytes):
                        selector.unregister(stream)
                        stream.close()
                    continue

                try:
                    chunk = os.read(stream.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                buffer = stdout if key.data == "stdout" else stderr
                limit = max_stdout_bytes if key.data == "stdout" else max_stderr_bytes
                if len(buffer) + len(chunk) > limit:
                    raise RuntimeError(
                        f"command {key.data} exceeded {limit}-byte capture limit"
                    )
                buffer.extend(chunk)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"command timed out after {timeout_seconds}s")
        returncode = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise RuntimeError(f"command timed out after {timeout_seconds}s") from exc
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed:
                stream.close()

    return subprocess.CompletedProcess(
        argv,
        returncode,
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
    )


def _local_preflight_row(alias: str) -> dict[str, str]:
    codex_root = _local_codex_root()
    return {
        "host": alias,
        "hostname": socket.gethostname(),
        "user": os.getenv("USER", ""),
        "home": str(pathlib.Path.home()),
        "codex": "present" if codex_root.is_dir() else "missing",
        "rg": "present" if _which("rg") else "missing",
        "python3": "present" if _which("python3") else "missing",
    }


def _which(binary: str) -> str | None:
    for directory in os.getenv("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = pathlib.Path(directory) / binary
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _relay_canonical_remote_helper(
    arguments: list[str],
    *,
    max_stdout_bytes: int,
) -> int:
    from retrospective_v2 import transport

    try:
        transport.relay_remote_host_context_cli(
            arguments,
            max_output_bytes=max_stdout_bytes,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


def _validated_session_meta_output_item(
    *,
    date: str,
    session_id: str,
    cwd: str,
    rollout: str,
) -> dict[str, str]:
    item = {"date": date, "session_id": session_id, "cwd": cwd, "rollout": rollout}
    serialized = json.dumps(item, separators=(",", ":"), sort_keys=True)
    if len(serialized.encode("utf-8")) > MAX_REMOTE_SESSION_META_SERIALIZED_ROW_BYTES:
        raise ValueError(SESSION_META_OUTPUT_ROW_TOO_LARGE_ERROR)
    return item


def _scan_session_meta_records(
    *,
    codex_root: pathlib.Path,
    dates: list[dt.date],
    limit: int,
    host: str,
    rollout_start: dt.datetime | None = None,
    rollout_end: dt.datetime | None = None,
    rollout_filename_mode: str = "all",
) -> SessionMetaScan:
    try:
        root_fd = _open_pinned_codex_root(codex_root)
    except FileNotFoundError:
        return SessionMetaScan(rows=[], truncated=False)
    except OSError as exc:
        raise SessionMetaRolloutError("session directory unreadable") from exc
    rows: list[dict[str, str]] = []
    seen_rollout_paths: set[str] = set()
    opened_directories: dict[str, int] = {}
    prefix_proof_candidate_limit = MAX_SESSION_META_CANDIDATE_LIMIT
    prefix_proof_candidate_captures = 0

    def open_directory(relative_dir: pathlib.PurePosixPath) -> int | None:
        key = relative_dir.as_posix()
        if key in opened_directories:
            return opened_directories[key]
        try:
            directory_fd = _open_pinned_directory_from_fd(root_fd, relative_dir)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SessionMetaRolloutError("session directory unreadable") from exc
        opened_directories[key] = directory_fd
        return directory_fd

    def close_directory(relative_dir: pathlib.PurePosixPath) -> None:
        key = relative_dir.as_posix()
        directory_fd = opened_directories.pop(key, None)
        if directory_fd is not None:
            os.close(directory_fd)

    def prepare_candidate_for_consumption(
        parent_fd: int,
        relative_path: pathlib.PurePosixPath,
        inventory_identity: RolloutInventoryIdentity,
    ) -> RolloutCandidateIdentity | None:
        nonlocal prefix_proof_candidate_captures
        try:
            if _session_meta_allows_append(relative_path):
                if prefix_proof_candidate_captures >= prefix_proof_candidate_limit:
                    return None
                prefix_proof_candidate_captures += 1
                return _capture_active_rollout_candidate_identity_from_parent_fd(
                    parent_fd,
                    relative_path.name,
                    inventory_identity,
                )
            return _capture_rollout_candidate_identity_from_parent_fd(
                parent_fd,
                relative_path.name,
                inventory_identity,
            )
        except ValueError as exc:
            raise SessionMetaRolloutError(
                str(exc),
                rollout=relative_path.as_posix(),
            ) from exc
        except OSError as exc:
            raise SessionMetaRolloutError(
                "rollout unreadable",
                rollout=relative_path.as_posix(),
            ) from exc

    def sorted_rollout_candidates(
        relative_dir: pathlib.PurePosixPath,
        predicate: Any,
    ) -> tuple[
        int | None,
        list[tuple[str, RolloutInventoryIdentity]],
    ]:
        directory_fd = open_directory(relative_dir)
        if directory_fd is None:
            return None, []
        try:
            candidates: list[tuple[str, RolloutInventoryIdentity]] = []
            with os.scandir(directory_fd) as entries:
                for entry in entries:
                    name = entry.name
                    if not RAW_ROLLOUT_BASENAME_RE.fullmatch(name):
                        continue
                    relative_path = relative_dir / name
                    if not predicate(relative_path):
                        continue
                    try:
                        inventory_identity = (
                            _capture_rollout_inventory_identity_from_parent_fd(
                                directory_fd,
                                name,
                            )
                        )
                    except ValueError as exc:
                        raise SessionMetaRolloutError(
                            str(exc),
                            rollout=relative_path.as_posix(),
                        ) from exc
                    except OSError as exc:
                        raise SessionMetaRolloutError(
                            "rollout unreadable",
                            rollout=relative_path.as_posix(),
                        ) from exc
                    candidates.append((name, inventory_identity))
        except OSError as exc:
            raise SessionMetaRolloutError("session directory unreadable") from exc
        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        return directory_fd, candidates

    def add_directory_candidates(
        selected: dict[
            str,
            tuple[
                pathlib.PurePosixPath,
                int,
                RolloutInventoryIdentity,
            ],
        ],
        relative_dir: pathlib.PurePosixPath,
        predicate: Any,
    ) -> None:
        directory_fd, candidates = sorted_rollout_candidates(
            relative_dir,
            predicate,
        )
        if directory_fd is None:
            return
        for name, inventory_identity in candidates:
            relative_path = relative_dir / name
            key = _session_meta_rollout_dedupe_key(relative_path)
            selected.setdefault(
                key,
                (relative_path, directory_fd, inventory_identity),
            )

    flat_archived_unknown_by_date: dict[
        dt.date,
        dict[str, tuple[str, str, dt.datetime | None]],
    ] = {}
    flat_archived_inventory_identities: dict[
        str,
        RolloutInventoryIdentity,
    ] = {}
    try:
        if rollout_filename_mode != "known":
            flat_archived_relative_dir = pathlib.PurePosixPath("archived_sessions")
            flat_archived_fd, flat_archived_candidates = sorted_rollout_candidates(
                flat_archived_relative_dir,
                lambda relative_path: _session_meta_rollout_filename_date(
                    relative_path.name
                )
                is None,
            )
            date_set = set(dates)
            if flat_archived_fd is not None:
                for name, inventory_identity in flat_archived_candidates:
                    rollout_relative_path = flat_archived_relative_dir / name
                    consumed_identity = prepare_candidate_for_consumption(
                        flat_archived_fd,
                        rollout_relative_path,
                        inventory_identity,
                    )
                    meta = _session_meta_from_rollout(
                        codex_root,
                        rollout_relative_path,
                        parent_fd=flat_archived_fd,
                        expected_identity=consumed_identity,
                        rollout_start=rollout_start,
                        rollout_end=rollout_end,
                    )
                    if meta is None:
                        continue
                    meta_date, session_id, cwd, timestamp = meta
                    if meta_date in date_set:
                        flat_archived_unknown_by_date.setdefault(meta_date, {})[
                            rollout_relative_path.as_posix()
                        ] = (session_id, cwd, timestamp)
                        flat_archived_inventory_identities[
                            rollout_relative_path.as_posix()
                        ] = inventory_identity

        for date_value in reversed(dates):
            date_text = date_value.strftime(DATE_FORMAT)
            date_relative_dirs = (
                pathlib.PurePosixPath("sessions") / date_text,
                pathlib.PurePosixPath("archived_sessions") / date_text,
            )
            selected_rollout_paths: dict[
                str,
                tuple[
                    pathlib.PurePosixPath,
                    int,
                    RolloutInventoryIdentity,
                ],
            ] = {}
            for relative_dir in date_relative_dirs:
                add_directory_candidates(
                    selected_rollout_paths,
                    relative_dir,
                    lambda relative_path: _rollout_matches_bounds(
                        relative_path,
                        rollout_start,
                        rollout_end,
                        filename_mode=rollout_filename_mode,
                    ),
                )
            flat_archived_relative_dir = pathlib.PurePosixPath("archived_sessions")
            add_directory_candidates(
                selected_rollout_paths,
                flat_archived_relative_dir,
                lambda relative_path: _flat_archived_rollout_matches_date(
                    pathlib.Path(relative_path.name),
                    date_value,
                )
                and _flat_archived_rollout_matches_bounds_or_unknown(
                    pathlib.Path(relative_path.name),
                    rollout_start,
                    rollout_end,
                    filename_mode=rollout_filename_mode,
                ),
            )
            flat_archived_fd = open_directory(flat_archived_relative_dir)
            if flat_archived_fd is not None:
                for relative_key in flat_archived_unknown_by_date.get(
                    date_value,
                    {},
                ):
                    relative_path = pathlib.PurePosixPath(relative_key)
                    selected_rollout_paths.setdefault(
                        relative_key,
                        (
                            relative_path,
                            flat_archived_fd,
                            flat_archived_inventory_identities[relative_key],
                        ),
                    )
            root_relative_dir = pathlib.PurePosixPath()
            add_directory_candidates(
                selected_rollout_paths,
                root_relative_dir,
                lambda relative_path: _flat_archived_rollout_matches_date(
                    pathlib.Path(relative_path.name),
                    date_value,
                )
                and _rollout_matches_bounds(
                    relative_path,
                    rollout_start,
                    rollout_end,
                    filename_mode=rollout_filename_mode,
                ),
            )
            cached_rollout_meta = flat_archived_unknown_by_date.get(date_value, {})
            selected_rollouts = sorted(
                selected_rollout_paths.values(),
                key=lambda candidate: _session_meta_rollout_sort_key(
                    candidate[0],
                    cached_rollout_meta.get(
                        candidate[0].as_posix(),
                        ("", "", None),
                    )[2],
                ),
                reverse=True,
            )
            for (
                rollout_relative_path,
                parent_fd,
                inventory_identity,
            ) in selected_rollouts:
                rollout_relative_key = rollout_relative_path.as_posix()
                if rollout_relative_key in seen_rollout_paths:
                    continue
                seen_rollout_paths.add(rollout_relative_key)
                require_record_date_match = _session_meta_is_flat_archived_undated(
                    rollout_relative_path
                )
                cached_meta = cached_rollout_meta.get(rollout_relative_key)
                if cached_meta is not None:
                    session_id, cwd, _timestamp = cached_meta
                else:
                    consumed_identity = prepare_candidate_for_consumption(
                        parent_fd,
                        rollout_relative_path,
                        inventory_identity,
                    )
                    if consumed_identity is None:
                        return SessionMetaScan(rows=rows, truncated=True)
                    meta = _session_meta_from_rollout(
                        codex_root,
                        rollout_relative_path,
                        parent_fd=parent_fd,
                        expected_identity=consumed_identity,
                        date_value=date_value,
                        require_record_date_match=require_record_date_match,
                        rollout_start=rollout_start,
                        rollout_end=rollout_end,
                    )
                    if meta is None:
                        continue
                    _meta_date, session_id, cwd, _timestamp = meta
                if not session_id:
                    continue
                if limit and len(rows) >= limit:
                    return SessionMetaScan(rows=rows, truncated=True)
                try:
                    item = _validated_session_meta_output_item(
                        date=date_value.strftime(DATE_FORMAT),
                        session_id=session_id,
                        cwd=cwd,
                        rollout=rollout_relative_key,
                    )
                except ValueError as exc:
                    raise SessionMetaRolloutError(
                        str(exc),
                        rollout=rollout_relative_key,
                    ) from exc
                rows.append({"host": host, **item})
            for relative_dir in date_relative_dirs:
                close_directory(relative_dir)
        return SessionMetaScan(rows=rows, truncated=False)
    finally:
        for directory_fd in opened_directories.values():
            os.close(directory_fd)
        os.close(root_fd)


def _iter_session_meta_records(
    *,
    codex_root: pathlib.Path,
    dates: list[dt.date],
    limit: int,
    host: str,
    rollout_start: dt.datetime | None = None,
    rollout_end: dt.datetime | None = None,
    rollout_filename_mode: str = "all",
) -> list[dict[str, str]]:
    return _scan_session_meta_records(
        codex_root=codex_root,
        dates=dates,
        limit=limit,
        host=host,
        rollout_start=rollout_start,
        rollout_end=rollout_end,
        rollout_filename_mode=rollout_filename_mode,
    ).rows


def _fetch_local_rollout(
    codex_root: pathlib.Path, rollout_relative_path: pathlib.PurePosixPath
) -> bytes:
    return _read_local_rollout_bytes(
        codex_root,
        rollout_relative_path,
        max_bytes=MAX_FETCH_ROLLOUT_BYTES,
    )


def _print_tsv(rows: list[dict[str, str]], columns: list[str]) -> None:
    print("\t".join(columns))
    for row in rows:
        print("\t".join(row.get(column, "") for column in columns))


def _sort_session_meta_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("date", ""),
            row.get("rollout", ""),
            row.get("session_id", ""),
            row.get("host", ""),
        ),
        reverse=True,
    )


def _json_line_to_dict(line: str, *, host: str) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except (ValueError, RecursionError) as exc:
        raise ValueError(
            f"remote helper returned a non-JSON line for host {host}: {line!r}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(
            f"remote helper returned a non-object JSON value for host {host}"
        )
    return value


def _extract_framed_lines(
    text: str,
    *,
    begin_marker: str,
    end_marker: str,
    host: str,
    command: str,
) -> list[str]:
    started = False
    payload_lines: list[str] = []
    for line in text.splitlines():
        if not started:
            if line == begin_marker:
                started = True
            continue
        if line == end_marker:
            return payload_lines
        payload_lines.append(line)
    raise ValueError(
        f"remote {command} output on host {host} was missing framed payload markers"
    )


def _extract_framed_fetch_rollout_payload(
    text: str,
    *,
    begin_marker: str,
    end_marker: str,
    host: str,
    command: str,
) -> bytes:
    payload_lines = _extract_framed_lines(
        text,
        begin_marker=begin_marker,
        end_marker=end_marker,
        host=host,
        command=command,
    )
    if not payload_lines:
        raise ValueError(
            f"remote {command} output on host {host} was missing payload header"
        )
    try:
        header = _json_line_to_dict(payload_lines[0], host=host)
    except ValueError as exc:
        raise ValueError(
            f"remote {command} output on host {host} had an invalid payload header"
        ) from exc
    if not bool(header.get("ok")):
        error = str(header.get("error", "")).strip() or "remote fetch failed"
        if error == "rollout not found":
            raise FileNotFoundError(error)
        raise ValueError(error)
    try:
        expected_bytes = int(header["bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"remote {command} output on host {host} had an invalid payload size"
        ) from exc
    if expected_bytes < 0:
        raise ValueError(
            f"remote {command} output on host {host} had a negative payload size"
        )
    payload = "".join(line.strip() for line in payload_lines[1:] if line.strip())
    if not payload:
        if expected_bytes != 0:
            raise ValueError(
                f"remote {command} output on host {host} was truncated or mismatched its payload size"
            )
        return b""
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            f"remote {command} output on host {host} contained invalid base64 payload"
        ) from exc
    if len(data) != expected_bytes:
        raise ValueError(
            f"remote {command} output on host {host} was truncated or mismatched its payload size"
        )
    if len(data) > MAX_FETCH_ROLLOUT_BYTES:
        raise ValueError(
            f"rollout too large: {len(data)} bytes > {MAX_FETCH_ROLLOUT_BYTES}"
        )
    return data


def _extract_framed_rollout_summary_records(
    text: str,
    *,
    begin_marker: str,
    end_marker: str,
    host: str,
    command: str,
) -> list[dict[str, Any]]:
    payload_lines = _extract_framed_lines(
        text,
        begin_marker=begin_marker,
        end_marker=end_marker,
        host=host,
        command=command,
    )
    if not payload_lines:
        raise ValueError(
            f"remote {command} output on host {host} was missing payload header"
        )
    try:
        header = _json_line_to_dict(payload_lines[0], host=host)
    except ValueError as exc:
        raise ValueError(
            f"remote {command} output on host {host} had an invalid payload header"
        ) from exc
    if not bool(header.get("ok")):
        error = str(header.get("error", "")).strip() or "remote rollout summary failed"
        if error == "rollout not found":
            raise FileNotFoundError(error)
        raise ValueError(error)

    records: list[dict[str, Any]] = []
    for line in payload_lines[1:]:
        if not line.strip():
            continue
        item = _json_line_to_dict(line, host=host)
        records.append(item)
    return records


def _session_meta_row_from_item(item: dict[str, Any], *, host: str) -> dict[str, str]:
    required_keys = ("date", "session_id", "cwd", "rollout")
    missing = [key for key in required_keys if key not in item]
    if missing:
        raise ValueError(
            f"remote helper returned incomplete session-meta payload for host {host}: missing {', '.join(missing)}"
        )
    validated = _validated_session_meta_output_item(
        date=str(item["date"]),
        session_id=str(item["session_id"]),
        cwd=str(item["cwd"]),
        rollout=str(item["rollout"]),
    )
    return {"host": host, **validated}


def _is_session_meta_truncation_item(item: dict[str, Any]) -> bool:
    return item.get("kind") == "truncation" and item.get("reason") in {
        SESSION_META_LIMIT_TRUNCATED_REASON,
        SESSION_META_CANDIDATE_LIMIT_TRUNCATED_REASON,
    }


def _session_meta_error_from_item(
    item: dict[str, Any],
) -> SessionMetaRolloutError | None:
    if item.get("kind") != "error":
        return None
    error = str(item.get("error", "")).strip() or "remote session-meta failed"
    rollout = item.get("rollout")
    rollout_text = str(rollout) if isinstance(rollout, str) and rollout else None
    return SessionMetaRolloutError(error, rollout=rollout_text)


def _session_meta_limit_error(host: str, limit: int) -> int:
    print(f"host={host}", file=sys.stderr)
    print(
        f"error=session-meta result exceeded --limit={limit}; narrow the date/host scope, use --auto-split, or raise --limit up to {MAX_SESSION_META_LIMIT}",
        file=sys.stderr,
    )
    return 1


def _scan_host_session_meta(
    alias: str,
    *,
    dates: list[dt.date],
    limit: int,
    rollout_start: dt.datetime | None,
    rollout_end: dt.datetime | None,
    rollout_filename_mode: str = "all",
) -> SessionMetaScan:
    if alias != LOCAL_HOST:
        raise RuntimeError("remote session metadata requires remote-host-context")
    return _scan_session_meta_records(
        codex_root=_local_codex_root(),
        dates=dates,
        limit=limit,
        host=alias,
        rollout_start=rollout_start,
        rollout_end=rollout_end,
        rollout_filename_mode=rollout_filename_mode,
    )


def _session_meta_split_windows(
    windows: list[tuple[dt.date, dt.datetime, dt.datetime]],
    step: dt.timedelta,
) -> list[tuple[dt.date, dt.datetime, dt.datetime]]:
    split: list[tuple[dt.date, dt.datetime, dt.datetime]] = []
    for date_value, window_start, window_end in windows:
        current = window_start
        while current < window_end:
            next_value = min(current + step, window_end)
            split.append((date_value, current, next_value))
            current = next_value
    return split


def _dedupe_session_meta_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in _sort_session_meta_rows(rows):
        key = (row.get("host", ""), row.get("rollout", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _auto_split_host_session_meta(
    alias: str,
    *,
    dates: list[dt.date],
    limit: int,
    rollout_start: dt.datetime | None = None,
    rollout_end: dt.datetime | None = None,
) -> SessionMetaScan:
    rows: list[dict[str, str]] = []
    for date_value in reversed(dates):
        unknown_scan = _scan_host_session_meta(
            alias,
            dates=[date_value],
            limit=limit,
            rollout_start=rollout_start,
            rollout_end=rollout_end,
            rollout_filename_mode="unknown",
        )
        rows.extend(unknown_scan.rows)
        if unknown_scan.truncated:
            return SessionMetaScan(rows=_dedupe_session_meta_rows(rows), truncated=True)

    pending: list[tuple[dt.date, dt.datetime, dt.datetime]] = []
    for date_value in reversed(dates):
        day_start = dt.datetime.combine(date_value, dt.time.min, tzinfo=dt.timezone.utc)
        day_end = day_start + dt.timedelta(days=1)
        window_start = (
            max(day_start, rollout_start) if rollout_start is not None else day_start
        )
        window_end = min(day_end, rollout_end) if rollout_end is not None else day_end
        if window_end <= window_start:
            continue
        pending.append((date_value, window_start, window_end))

    for step in (
        dt.timedelta(hours=1),
        dt.timedelta(minutes=15),
        dt.timedelta(minutes=1),
    ):
        next_pending: list[tuple[dt.date, dt.datetime, dt.datetime]] = []
        for date_value, rollout_start, rollout_end in _session_meta_split_windows(
            pending, step
        ):
            scan = _scan_host_session_meta(
                alias,
                dates=[date_value],
                limit=limit,
                rollout_start=rollout_start,
                rollout_end=rollout_end,
                rollout_filename_mode="known",
            )
            if scan.truncated:
                next_pending.append((date_value, rollout_start, rollout_end))
                continue
            rows.extend(scan.rows)
        if not next_pending:
            return SessionMetaScan(
                rows=_dedupe_session_meta_rows(rows), truncated=False
            )
        pending = next_pending
    return SessionMetaScan(rows=_dedupe_session_meta_rows(rows), truncated=True)


def _scan_host_session_meta_with_auto_split(
    alias: str,
    *,
    dates: list[dt.date],
    limit: int,
    rollout_start: dt.datetime | None = None,
    rollout_end: dt.datetime | None = None,
) -> SessionMetaScan:
    rows: list[dict[str, str]] = []
    truncated = False
    for date_value in dates:
        scan = _scan_host_session_meta(
            alias,
            dates=[date_value],
            limit=limit,
            rollout_start=rollout_start,
            rollout_end=rollout_end,
        )
        if scan.truncated:
            scan = _auto_split_host_session_meta(
                alias,
                dates=[date_value],
                limit=limit,
                rollout_start=rollout_start,
                rollout_end=rollout_end,
            )
        rows.extend(scan.rows)
        truncated = truncated or scan.truncated
    return SessionMetaScan(rows=_dedupe_session_meta_rows(rows), truncated=truncated)


def _canonical_hosts_arguments(command: str, hosts: Iterable[str]) -> list[str]:
    arguments = [command]
    for host in hosts:
        arguments.extend(("--host", host))
    return arguments


def _canonical_session_meta_arguments(
    args: argparse.Namespace,
    hosts: Iterable[str],
) -> list[str]:
    arguments = _canonical_hosts_arguments("session-meta", hosts)
    for date_value in getattr(args, "date", ()):
        arguments.extend(("--date", date_value))
    for option, value in (
        ("--from", getattr(args, "from_date", None)),
        ("--to", getattr(args, "to_date", None)),
        ("--rollout-start", getattr(args, "rollout_start", None)),
        ("--rollout-end", getattr(args, "rollout_end", None)),
    ):
        if value:
            arguments.extend((option, str(value)))
    arguments.extend(("--limit", str(args.limit)))
    if getattr(args, "auto_split", False):
        arguments.append("--auto-split")
    return arguments


def cmd_preflight(args: argparse.Namespace) -> int:
    try:
        hosts = _resolve_hosts(args.host)
    except ValueError as error:
        return _error(str(error))

    if any(alias != LOCAL_HOST for alias in hosts):
        return _relay_canonical_remote_helper(
            _canonical_hosts_arguments("preflight", hosts),
            max_stdout_bytes=MAX_REMOTE_STDOUT_BYTES,
        )

    rows: list[dict[str, str]] = []
    for alias in hosts:
        try:
            row = _local_preflight_row(alias)
        except RuntimeError as error:
            print(f"host={alias}", file=sys.stderr)
            print(f"error={error}", file=sys.stderr)
            return 1
        row.setdefault("hostname", "")
        row.setdefault("user", "")
        row.setdefault("home", "")
        row.setdefault("codex", "missing")
        row.setdefault("rg", "missing")
        row.setdefault("python3", "missing")
        rows.append(row)

    _print_tsv(
        rows,
        ["host", "hostname", "user", "home", "codex", "rg", "python3"],
    )
    return 0


def cmd_session_meta(args: argparse.Namespace) -> int:
    try:
        hosts = _resolve_hosts(args.host)
        dates = _resolve_dates(args)
        rollout_start, rollout_end = _resolve_rollout_bounds(args)
        if args.limit < 1 or args.limit > MAX_SESSION_META_LIMIT:
            raise ValueError(
                f"--limit must stay between 1 and {MAX_SESSION_META_LIMIT}"
            )
    except ValueError as error:
        return _error(str(error))

    if any(alias != LOCAL_HOST for alias in hosts):
        return _relay_canonical_remote_helper(
            _canonical_session_meta_arguments(args, hosts),
            max_stdout_bytes=MAX_REMOTE_SESSION_META_STDOUT_BYTES,
        )

    rows: list[dict[str, str]] = []
    auto_split = bool(getattr(args, "auto_split", False))
    for alias in hosts:
        try:
            if auto_split:
                scan = _scan_host_session_meta_with_auto_split(
                    alias,
                    dates=dates,
                    limit=args.limit,
                    rollout_start=rollout_start,
                    rollout_end=rollout_end,
                )
            else:
                scan = _scan_host_session_meta(
                    alias,
                    dates=dates,
                    limit=args.limit,
                    rollout_start=rollout_start,
                    rollout_end=rollout_end,
                )
        except SessionMetaRolloutError as error:
            print(f"host={alias}", file=sys.stderr)
            if error.rollout:
                print(f"rollout={error.rollout}", file=sys.stderr)
            print(f"error={error.error}", file=sys.stderr)
            return 1
        except (RuntimeError, ValueError) as error:
            print(f"host={alias}", file=sys.stderr)
            print(f"error={error}", file=sys.stderr)
            return 1
        if scan.truncated:
            return _session_meta_limit_error(alias, args.limit)
        host_rows = scan.rows
        rows.extend(host_rows)
        if not auto_split and len(rows) > args.limit:
            return _session_meta_limit_error("all", args.limit)
    rows = _sort_session_meta_rows(rows)

    _print_tsv(rows, ["host", "date", "session_id", "cwd", "rollout"])
    return 0


def cmd_fetch_rollout(args: argparse.Namespace) -> int:
    try:
        hosts = _resolve_hosts([args.host])
        alias = hosts[0]
        rollout_relative_path = _resolve_rollout_relative_path(args.rollout)
        output = _resolve_output_path(args.output)
    except ValueError as error:
        return _error(str(error))

    if alias != LOCAL_HOST:
        return _relay_canonical_remote_helper(
            [
                "fetch-rollout",
                "--host",
                alias,
                "--rollout",
                args.rollout,
                "--output",
                args.output,
            ],
            max_stdout_bytes=MAX_REMOTE_STDOUT_BYTES,
        )

    try:
        data = _fetch_local_rollout(_local_codex_root(), rollout_relative_path)
    except FileNotFoundError:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_relative_path.as_posix()}", file=sys.stderr)
        print("error=rollout not found", file=sys.stderr)
        return 1
    except OSError:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_relative_path.as_posix()}", file=sys.stderr)
        print("error=rollout unreadable", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_relative_path.as_posix()}", file=sys.stderr)
        print(f"error={error}", file=sys.stderr)
        return 1

    try:
        _write_private_bytes(output, data)
    except (OSError, ValueError) as error:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_relative_path.as_posix()}", file=sys.stderr)
        print(f"error={error}", file=sys.stderr)
        for note in getattr(error, "__notes__", ()):
            print(f"error_note={note}", file=sys.stderr)
        return 1
    print(f"host={alias}")
    print(f"rollout={rollout_relative_path.as_posix()}")
    print(f"output={output}")
    print(f"bytes={len(data)}")
    return 0


def _normalize_summary_text(value: str, *, max_text_chars: int) -> str:
    collapsed = " ".join(str(value).replace("\r", "\n").split())
    if max_text_chars > 3 and len(collapsed) > max_text_chars:
        return collapsed[: max_text_chars - 3] + "..."
    return collapsed


def _message_content_is_valid(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            return False
        item_type = item.get("type")
        if not isinstance(item_type, str):
            return False
        if item_type in ("input_text", "output_text", "text") and not isinstance(
            item.get("text"), str
        ):
            return False
    return True


def _message_payload_is_valid(payload: dict[str, Any]) -> bool:
    role = payload.get("role")
    return (
        isinstance(role, str)
        and role in ("assistant", "developer", "system", "user")
        and _message_content_is_valid(payload.get("content"))
    )


def _message_summary(payload: dict[str, Any]) -> tuple[str, str]:
    role = str(payload.get("role", ""))
    if role not in {"assistant", "user"}:
        return "", ""
    parts: list[str] = []
    for item in payload.get("content", []):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if not isinstance(item_type, str):
            continue
        if item_type not in ("input_text", "output_text", "text"):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    kind = "user_message" if role == "user" else "assistant_message"
    return kind, "\n".join(parts).strip()


def _meaningful_prompt_text(text: str) -> str:
    stripped = str(text).strip()
    if not stripped:
        return ""
    if any(stripped.startswith(prefix) for prefix in WRAPPER_PREFIXES):
        for marker in WRAPPER_END_MARKERS:
            index = stripped.rfind(marker)
            if index >= 0:
                candidate = stripped[index + len(marker) :].strip()
                if candidate and not any(
                    candidate.startswith(prefix) for prefix in WRAPPER_PREFIXES
                ):
                    return candidate
        return ""
    return stripped


def _meaningful_user_message_text(text: str) -> str:
    stripped = _meaningful_prompt_text(text)
    if not stripped:
        return ""
    if any(pattern.search(stripped) for pattern in AUTOMATION_PROMPT_PATTERNS):
        return ""
    marker_count = sum(1 for marker in AUTOMATION_PROMPT_MARKERS if marker in stripped)
    if marker_count >= 2:
        return ""
    return stripped


def _summary_signal_chunks(text: str) -> Iterable[str]:
    value = str(text)
    if len(value) <= SUMMARY_SIGNAL_CHUNK_CHARS:
        yield value
        return
    step = max(1, SUMMARY_SIGNAL_CHUNK_CHARS - SUMMARY_SIGNAL_CHUNK_OVERLAP)
    offset = 0
    while offset < len(value):
        yield value[offset : offset + SUMMARY_SIGNAL_CHUNK_CHARS]
        if offset + SUMMARY_SIGNAL_CHUNK_CHARS >= len(value):
            break
        offset += step


def _summary_regex_search(pattern: str, text: str, flags: int = re.I) -> bool:
    return _summary_pattern_search(re.compile(pattern, flags), text)


def _summary_pattern_search(pattern: re.Pattern[str], text: str) -> bool:
    return any(pattern.search(chunk) for chunk in _summary_signal_chunks(text))


def _summary_category_signals(chunks: tuple[str, ...]) -> list[str]:
    matched: set[str] = set()
    for label, pattern in SUMMARY_SIGNAL_CATEGORY_RES:
        for chunk in chunks:
            if pattern.search(chunk):
                matched.add(label)
                break
        if len(matched) == len(SUMMARY_SIGNAL_CATEGORY_LABELS):
            break
    return [label for label in SUMMARY_SIGNAL_CATEGORY_LABELS if label in matched]


def _summary_has_sensitive_signal_chunks(chunks: tuple[str, ...]) -> bool:
    return any(SUMMARY_SENSITIVE_SIGNAL_RE.search(chunk) for chunk in chunks)


def _summary_has_sensitive_signal(text: str) -> bool:
    return _summary_has_sensitive_signal_chunks(tuple(_summary_signal_chunks(text)))


def _summary_signal_text(kind: str, text: str) -> str:
    chunks = tuple(_summary_signal_chunks(text))
    signals = _summary_category_signals(chunks)
    if _summary_has_sensitive_signal_chunks(chunks):
        signals.append("secret")
    return " ".join(signals) if signals else f"{kind.replace('_', ' ')} present"


def _safe_summary_text(kind: str, text: str) -> str:
    return _summary_signal_text(kind, text)


def _summary_matches_keywords(text: str, search_keywords: list[str]) -> bool:
    if not search_keywords:
        return False
    normalized = _normalize_summary_text(text, max_text_chars=0).casefold()
    return any(keyword in normalized for keyword in search_keywords)


def _summary_record_has_signal(record: dict[str, Any] | None) -> bool:
    if record is None or str(record.get("kind", "")) in {"session_meta", "scan_meta"}:
        return False
    text = str(record.get("text", ""))
    return any(marker in text for marker in SUMMARY_SIGNAL_MARKERS)


def _event_user_message_text(payload: dict[str, Any]) -> str:
    message_present = "message" in payload
    message = payload.get("message")
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, dict):
        kind, text = _message_summary(message)
        if kind == "user_message" and text:
            return text.strip()
    if not message_present:
        text = payload.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _build_summary_record(
    *,
    kind: str,
    text: str,
    line_no: int,
    timestamp: str,
    max_text_chars: int,
    session_id: str = "",
    search_keywords: list[str] | None = None,
) -> dict[str, Any] | None:
    signal_text = text
    if kind == "user_message":
        signal_text = _meaningful_user_message_text(text)
        if not signal_text:
            return None
    normalized = _normalize_summary_text(
        _safe_summary_text(kind, signal_text),
        max_text_chars=max_text_chars,
    )
    if not normalized:
        return None
    record = {
        "kind": kind,
        "line": line_no,
        "text": normalized,
        "timestamp": timestamp,
    }
    if session_id:
        record["session_id"] = session_id
    if _summary_matches_keywords(signal_text, search_keywords or []):
        record["_keyword_matched"] = True
    return record


def _bounded_session_meta_lines(handle: Any, max_scan_bytes: int) -> Iterable[str]:
    if max_scan_bytes < 1:
        raise ValueError("session metadata scan budget must be positive")
    try:
        file_descriptor = handle.fileno()
    except (AttributeError, OSError, ValueError):
        file_descriptor = None
    scanned = 0
    buffer = bytearray()
    buffer_offset = 0
    while True:
        remaining = max_scan_bytes - scanned
        if remaining <= 0:
            return
        read_size = min(SESSION_META_READ_CHUNK_BYTES, remaining)
        chunk = (
            os.read(file_descriptor, read_size)
            if file_descriptor is not None
            else handle.read(read_size)
        )
        if not chunk:
            if buffer:
                yield _decode_session_meta_line(bytes(buffer))
            return
        raw_bytes = (
            chunk.encode("utf-8", "surrogatepass")
            if isinstance(chunk, str)
            else bytes(chunk)
        )
        if len(raw_bytes) > read_size:
            raise ValueError("session metadata reader exceeded requested byte count")
        scanned += len(raw_bytes)
        buffer.extend(raw_bytes)
        cap_has_unread_bytes = False
        if scanned == max_scan_bytes:
            try:
                if file_descriptor is not None:
                    position = os.lseek(file_descriptor, 0, os.SEEK_CUR)
                    cap_has_unread_bytes = os.fstat(file_descriptor).st_size > position
                else:
                    cap_has_unread_bytes = len(handle.getbuffer()) > handle.tell()
            except (AttributeError, OSError, TypeError, ValueError):
                cap_has_unread_bytes = True
        while True:
            line_end = buffer.find(b"\n")
            if line_end < 0:
                break
            line_size = line_end + 1
            absolute_line_end = buffer_offset + line_size
            if cap_has_unread_bytes and absolute_line_end == max_scan_bytes:
                raise ValueError(
                    f"session metadata scan truncated at {max_scan_bytes} bytes"
                )
            line = bytes(buffer[:line_size])
            del buffer[:line_size]
            buffer_offset = absolute_line_end
            yield _decode_session_meta_line(line)
        if scanned == max_scan_bytes:
            if cap_has_unread_bytes:
                raise ValueError(
                    f"session metadata scan truncated at {max_scan_bytes} bytes"
                )
            if buffer:
                yield _decode_session_meta_line(bytes(buffer))
            return


def _decode_summary_line(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "\n"


def _bounded_text_lines(
    handle: Any,
    max_scan_bytes: int,
    source_size: int,
) -> Iterable[str]:
    try:
        start_offset = handle.tell()
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise ValueError("rollout summary reader offset is unavailable") from error
    if (
        isinstance(start_offset, bool)
        or not isinstance(start_offset, int)
        or start_offset < 0
        or start_offset > source_size
    ):
        raise ValueError("rollout summary reader offset is invalid")
    if start_offset != 0:
        raise ValueError("rollout summary reader must start at byte 0")
    scanned = 0
    buffer = bytearray()
    dropping_oversized_line = False
    chunk_bytes = 64 * 1024
    scan_limit = min(max_scan_bytes, source_size) if max_scan_bytes else source_size

    while scanned < scan_limit:
        read_size = min(chunk_bytes, scan_limit - scanned)
        chunk = handle.read(read_size)
        if not chunk:
            break
        if isinstance(chunk, str):
            raw_bytes = chunk.encode("utf-8", "surrogatepass")
        else:
            raw_bytes = bytes(chunk)
        scanned += len(raw_bytes)
        offset = 0
        while offset < len(raw_bytes):
            line_end = raw_bytes.find(b"\n", offset)
            part_end = len(raw_bytes) if line_end < 0 else line_end + 1
            part = raw_bytes[offset:part_end]
            if dropping_oversized_line:
                if line_end >= 0:
                    yield "\n"
                    dropping_oversized_line = False
            elif len(buffer) + len(part) > MAX_ROLLOUT_SUMMARY_LINE_BYTES:
                buffer.clear()
                dropping_oversized_line = True
                if line_end >= 0:
                    yield "\n"
                    dropping_oversized_line = False
            else:
                buffer.extend(part)
                if line_end >= 0:
                    yield _decode_summary_line(bytes(buffer))
                    buffer.clear()
            offset = part_end

    if scanned == source_size:
        if dropping_oversized_line:
            yield "\n"
        elif buffer:
            yield _decode_summary_line(bytes(buffer))


def _summarize_rollout_records(
    *,
    lines: Iterable[str],
    keywords: list[str],
    limit: int,
    tail_records: int,
    max_text_chars: int,
) -> list[dict[str, Any]]:
    records, _meta = _summarize_rollout_records_with_meta(
        lines=lines,
        keywords=keywords,
        limit=limit,
        tail_records=tail_records,
        max_text_chars=max_text_chars,
    )
    return records


def _summarize_rollout_records_with_meta(
    *,
    lines: Iterable[str],
    keywords: list[str],
    limit: int,
    tail_records: int,
    max_text_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    search_keywords = [value.casefold() for value in keywords if value]
    matched: list[dict[str, Any]] = []
    matched_seen: set[tuple[str, int]] = set()
    signal_records: list[dict[str, Any]] = []
    signal_seen: set[tuple[str, int]] = set()
    signal_record_limit_reached = False
    matched_record_limit_reached = False
    json_error_count = 0
    summary_record_count = 0
    tail: collections.deque[dict[str, Any]] = collections.deque(maxlen=tail_records)
    session_meta_record: dict[str, Any] | None = None
    last_assistant_record: dict[str, Any] | None = None
    last_user_record: dict[str, Any] | None = None
    last_task_complete_record: dict[str, Any] | None = None

    for line_no, line in enumerate(lines, 1):
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            json_error_count += 1
            continue
        if not isinstance(obj, dict):
            json_error_count += 1
            continue
        timestamp_value = obj.get("timestamp")
        if "timestamp" in obj and not isinstance(timestamp_value, str):
            json_error_count += 1
            continue
        timestamp = timestamp_value if isinstance(timestamp_value, str) else ""
        record: dict[str, Any] | None = None
        record_type = obj.get("type")
        if not isinstance(record_type, str):
            json_error_count += 1
            continue
        payload = obj.get("payload")
        if record_type in (
            "session_meta",
            "response_item",
            "event_msg",
        ) and not isinstance(payload, dict):
            json_error_count += 1
            continue

        if record_type == "session_meta":
            session_id_value = payload.get("id")
            if not isinstance(session_id_value, str) or not session_id_value:
                json_error_count += 1
                continue
            cwd_value = payload.get("cwd")
            if "cwd" in payload and not isinstance(cwd_value, str):
                json_error_count += 1
                continue
            cwd_present = isinstance(cwd_value, str) and bool(cwd_value)
            if session_meta_record is None:
                session_meta_record = _build_summary_record(
                    kind="session_meta",
                    text=f"session_id={session_id_value} cwd_present={str(cwd_present).lower()}",
                    line_no=line_no,
                    timestamp=timestamp,
                    max_text_chars=max_text_chars,
                    session_id=session_id_value,
                    search_keywords=search_keywords,
                )
            continue

        if record_type == "response_item":
            payload_type = payload.get("type")
            if not isinstance(payload_type, str):
                json_error_count += 1
                continue
            if payload_type == "message":
                if not _message_payload_is_valid(payload):
                    json_error_count += 1
                    continue
                kind, text = _message_summary(payload)
                if text:
                    record = _build_summary_record(
                        kind=kind,
                        text=text,
                        line_no=line_no,
                        timestamp=timestamp,
                        max_text_chars=max_text_chars,
                        search_keywords=search_keywords,
                    )
                    if kind == "assistant_message":
                        last_assistant_record = record
                    elif kind == "user_message" and record is not None:
                        last_user_record = record
            elif payload_type == "function_call_output":
                output = payload.get("output")
                if not isinstance(output, str):
                    json_error_count += 1
                    continue
                if output.strip():
                    record = _build_summary_record(
                        kind="function_call_output",
                        text=output,
                        line_no=line_no,
                        timestamp=timestamp,
                        max_text_chars=max_text_chars,
                        search_keywords=search_keywords,
                    )
        elif record_type == "event_msg":
            payload_type = payload.get("type")
            if not isinstance(payload_type, str):
                json_error_count += 1
                continue
            if payload_type == "task_complete":
                text = payload.get("last_agent_message")
                if not isinstance(text, str):
                    json_error_count += 1
                    continue
                if text.strip():
                    record = _build_summary_record(
                        kind="task_complete",
                        text=text,
                        line_no=line_no,
                        timestamp=timestamp,
                        max_text_chars=max_text_chars,
                        search_keywords=search_keywords,
                    )
                    last_task_complete_record = record
            elif payload_type == "user_message":
                message = payload.get("message")
                if "message" in payload:
                    if isinstance(message, dict):
                        if message.get(
                            "role"
                        ) != "user" or not _message_content_is_valid(
                            message.get("content")
                        ):
                            json_error_count += 1
                            continue
                    elif not isinstance(message, str):
                        json_error_count += 1
                        continue
                elif not isinstance(payload.get("text"), str):
                    json_error_count += 1
                    continue
                text = _event_user_message_text(payload)
                if text:
                    record = _build_summary_record(
                        kind="user_message",
                        text=text,
                        line_no=line_no,
                        timestamp=timestamp,
                        max_text_chars=max_text_chars,
                        search_keywords=search_keywords,
                    )
                    if record is not None:
                        last_user_record = record

        if record is None:
            continue

        summary_record_count += 1
        if _summary_record_has_signal(record):
            key = (str(record.get("kind", "")), int(record.get("line", 0)))
            if key not in signal_seen:
                if limit <= 0 or len(signal_records) < limit:
                    signal_records.append(record)
                    signal_seen.add(key)
                else:
                    signal_record_limit_reached = True

        if search_keywords:
            if record.get("_keyword_matched") is True:
                key = (str(record.get("kind", "")), int(record.get("line", 0)))
                if key not in matched_seen:
                    if limit <= 0 or len(matched) < limit:
                        matched.append(record)
                        matched_seen.add(key)
                    else:
                        matched_record_limit_reached = True

        if tail_records > 0:
            tail.append(record)

    emitted: set[tuple[str, int]] = set()
    result: list[dict[str, Any]] = []

    def append(record: dict[str, Any] | None) -> None:
        if record is None:
            return
        key = (str(record.get("kind", "")), int(record.get("line", 0)))
        if key in emitted:
            return
        emitted.add(key)
        safe_record = dict(record)
        safe_record.pop("_keyword_matched", None)
        result.append(safe_record)

    append(session_meta_record)
    for record in signal_records:
        append(record)
    for record in matched:
        append(record)
    if not search_keywords:
        for record in tail:
            append(record)
    append(last_user_record)
    append(last_assistant_record)
    if last_assistant_record is None:
        append(last_task_complete_record)
    keyword_filter_applied = bool(search_keywords)
    emitted_summary_record_count = sum(
        1 for record in result if record.get("kind") != "session_meta"
    )
    return result, {
        "keyword_filter_applied": keyword_filter_applied,
        "json_error_count": json_error_count,
        "matched_record_limit_reached": matched_record_limit_reached,
        "record_limit_reached": signal_record_limit_reached
        or matched_record_limit_reached,
        "signal_record_limit_reached": signal_record_limit_reached,
        "summary_record_count": summary_record_count,
        "summary_limit": limit,
        "tail_record_limit_reached": not keyword_filter_applied
        and summary_record_count > emitted_summary_record_count,
        "tail_records": tail_records,
    }


def _rollout_summary_scan_meta(
    *,
    source_bytes: int,
    source_sha256: str | None = None,
    scan_bytes: int,
    summary_limit: int,
    record_limit_reached: bool = False,
    signal_record_limit_reached: bool = False,
    matched_record_limit_reached: bool = False,
    tail_record_limit_reached: bool = False,
    keyword_filter_applied: bool = False,
    json_error_count: int = 0,
    tail_records: int = 0,
    summary_record_count: int = 0,
) -> dict[str, Any]:
    scan_truncated = bool(scan_bytes and source_bytes > scan_bytes)
    record_limit_reached = bool(
        record_limit_reached
        or signal_record_limit_reached
        or matched_record_limit_reached
    )
    row = {
        "kind": "scan_meta",
        "json_error_count": json_error_count,
        "keyword_filter_applied": keyword_filter_applied,
        "line": 0,
        "matched_record_limit_reached": matched_record_limit_reached,
        "record_limit_reached": record_limit_reached,
        "scan_bytes": scan_bytes,
        "scan_truncated": scan_truncated,
        "signal_record_limit_reached": signal_record_limit_reached,
        "source_bytes": source_bytes,
        "summary_record_count": summary_record_count,
        "summary_limit": summary_limit,
        "tail_record_limit_reached": tail_record_limit_reached,
        "tail_records": tail_records,
        "text": (
            f"scan_truncated={str(scan_truncated).lower()} "
            f"keyword_filter_applied={str(keyword_filter_applied).lower()} "
            f"record_limit_reached={str(record_limit_reached).lower()} "
            f"signal_record_limit_reached={str(signal_record_limit_reached).lower()} "
            f"matched_record_limit_reached={str(matched_record_limit_reached).lower()} "
            f"tail_record_limit_reached={str(tail_record_limit_reached).lower()} "
            f"scan_bytes={scan_bytes} json_error_count={json_error_count} "
            f"summary_limit={summary_limit} tail_records={tail_records} "
            f"summary_record_count={summary_record_count} source_bytes={source_bytes}"
        ),
        "timestamp": "",
    }
    if source_sha256 is not None:
        row["source_sha256"] = source_sha256
    return row


def _scan_meta_allows_remote_generated_source_identity_proof(
    row: dict[str, Any],
) -> bool:
    source_bytes = row.get("source_bytes")
    scan_bytes = row.get("scan_bytes")
    summary_limit = row.get("summary_limit")
    source_sha256 = row.get("source_sha256")
    return (
        row.get("scan_truncated") is False
        and type(summary_limit) is int
        and summary_limit >= 0
        and type(row.get("json_error_count")) is int
        and row["json_error_count"] == 0
        and row.get("keyword_filter_applied") is False
        and row.get("record_limit_reached") is False
        and row.get("signal_record_limit_reached") is False
        and row.get("matched_record_limit_reached") is False
        and type(source_bytes) is int
        and source_bytes >= 0
        and type(scan_bytes) is int
        and scan_bytes >= source_bytes
        and isinstance(source_sha256, str)
        and SOURCE_SHA256_RE.fullmatch(source_sha256) is not None
    )


def _scan_meta_allows_remote_generated_coverage_proof(row: dict[str, Any]) -> bool:
    return (
        _scan_meta_allows_remote_generated_source_identity_proof(row)
        and row.get("tail_record_limit_reached") is False
    )


def cmd_rollout_summary(args: argparse.Namespace) -> int:
    try:
        hosts = _resolve_hosts([args.host])
        alias = hosts[0]
        rollout_relative_path = _resolve_rollout_relative_path(args.rollout)
        if args.limit < 1 or args.limit > MAX_ROLLOUT_SUMMARY_LIMIT:
            raise ValueError(
                f"--limit must stay between 1 and {MAX_ROLLOUT_SUMMARY_LIMIT}"
            )
        if (
            args.tail_records < 0
            or args.tail_records > MAX_ROLLOUT_SUMMARY_TAIL_RECORDS
        ):
            raise ValueError(
                f"--tail-records must stay between 0 and {MAX_ROLLOUT_SUMMARY_TAIL_RECORDS}"
            )
        if args.max_text_chars < 40:
            raise ValueError("--max-text-chars must be at least 40")
        if args.max_text_chars > MAX_ROLLOUT_SUMMARY_TEXT_CHARS:
            raise ValueError(
                f"--max-text-chars must stay at or below {MAX_ROLLOUT_SUMMARY_TEXT_CHARS}"
            )
    except ValueError as error:
        return _error(str(error))

    if alias != LOCAL_HOST:
        arguments = [
            "rollout-summary",
            "--host",
            alias,
            "--rollout",
            args.rollout,
            "--limit",
            str(args.limit),
            "--tail-records",
            str(args.tail_records),
            "--max-text-chars",
            str(args.max_text_chars),
        ]
        for keyword in args.keyword:
            arguments.extend(("--keyword", keyword))
        return _relay_canonical_remote_helper(
            arguments,
            max_stdout_bytes=MAX_REMOTE_ROLLOUT_SUMMARY_STDOUT_BYTES,
        )

    rollout_ref = rollout_relative_path.as_posix()
    try:
        codex_root = _local_codex_root()
        with _open_local_rollout_text(codex_root, rollout_relative_path) as handle:
            identity = _rollout_identity_from_stat(os.fstat(handle.fileno()))
            handle.assert_identity(identity, phase="before summary scan")
            effective_summary_scan_bytes = (
                MAX_ROLLOUT_SUMMARY_SCAN_BYTES or identity.size
            )
            hashing_reader = _HashingReader(handle)
            records, summary_meta = _summarize_rollout_records_with_meta(
                lines=_bounded_text_lines(
                    hashing_reader,
                    effective_summary_scan_bytes,
                    identity.size,
                ),
                keywords=args.keyword,
                limit=args.limit,
                tail_records=args.tail_records,
                max_text_chars=args.max_text_chars,
            )
            handle.assert_identity(identity, phase="after summary scan")
        source_sha256 = (
            hashing_reader.hexdigest()
            if hashing_reader.bytes_read == identity.size
            else None
        )
        records.insert(
            0,
            _rollout_summary_scan_meta(
                source_bytes=identity.size,
                source_sha256=source_sha256,
                scan_bytes=effective_summary_scan_bytes,
                summary_limit=args.limit,
                record_limit_reached=bool(summary_meta["record_limit_reached"]),
                signal_record_limit_reached=bool(
                    summary_meta["signal_record_limit_reached"]
                ),
                matched_record_limit_reached=bool(
                    summary_meta["matched_record_limit_reached"]
                ),
                tail_record_limit_reached=bool(
                    summary_meta["tail_record_limit_reached"]
                ),
                keyword_filter_applied=bool(summary_meta["keyword_filter_applied"]),
                json_error_count=int(summary_meta["json_error_count"]),
                tail_records=int(summary_meta["tail_records"]),
                summary_record_count=int(summary_meta["summary_record_count"]),
            ),
        )
        if _scan_meta_allows_remote_generated_source_identity_proof(records[0]):
            records[0]["source_identity_proof"] = (
                REMOTE_GENERATED_SUMMARY_SOURCE_IDENTITY_PROOF
            )
        if _scan_meta_allows_remote_generated_coverage_proof(records[0]):
            records[0]["coverage_proof"] = REMOTE_GENERATED_SUMMARY_COVERAGE_PROOF
        records = [dict(record, rollout=rollout_ref) for record in records]
    except FileNotFoundError:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_ref}", file=sys.stderr)
        print("error=rollout not found", file=sys.stderr)
        return 1
    except OSError:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_ref}", file=sys.stderr)
        print("error=rollout unreadable", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"host={alias}", file=sys.stderr)
        print(f"rollout={rollout_ref}", file=sys.stderr)
        print(f"error={error}", file=sys.stderr)
        return 1

    # Normalize the host and backing ref after both local and remote paths.
    for record in records:
        item = dict(record)
        item["host"] = alias
        item["rollout"] = rollout_ref
        print(json.dumps(item, separators=(",", ":"), sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read bounded Codex session evidence from Joey's default hosts without ad hoc SSH literals."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight",
        help="Check reachability and bounded prerequisites on the allowed hosts.",
    )
    preflight.add_argument("--host", action="append", required=True)
    preflight.set_defaults(func=cmd_preflight)

    session_meta = subparsers.add_parser(
        "session-meta",
        help="List session ids, cwd, and rollout paths from bounded date trees.",
    )
    session_meta.add_argument("--host", action="append", required=True)
    session_meta.add_argument("--date", action="append", default=[])
    session_meta.add_argument("--from", dest="from_date")
    session_meta.add_argument("--to", dest="to_date")
    session_meta.add_argument("--limit", type=int, default=200)
    session_meta.add_argument(
        "--rollout-start",
        help="Inclusive UTC filename timestamp lower bound, e.g. 2026-05-21T10:00:00Z.",
    )
    session_meta.add_argument(
        "--rollout-end",
        help="Exclusive UTC filename timestamp upper bound, e.g. 2026-05-21T11:00:00Z.",
    )
    session_meta.add_argument(
        "--auto-split",
        action="store_true",
        help="When a date overflows --limit, retry by hour, then 15-minute, then 1-minute rollout filename windows and merge rows.",
    )
    session_meta.set_defaults(func=cmd_session_meta)

    fetch_rollout = subparsers.add_parser(
        "fetch-rollout",
        help="Copy one validated rollout file from an allowed host to a local path.",
    )
    fetch_rollout.add_argument("--host", required=True)
    fetch_rollout.add_argument(
        "--rollout",
        required=True,
        help="Relative rollout path under the remote Codex root (sessions/..., archived_sessions/..., or root rollout-*.jsonl).",
    )
    fetch_rollout.add_argument(
        "--output",
        required=True,
        help=(
            "Output path must resolve under .codex-tmp/remote-host-context/ or "
            "an owner-private subdirectory of /tmp; direct /tmp files are rejected."
        ),
    )
    fetch_rollout.set_defaults(func=cmd_fetch_rollout)

    rollout_summary = subparsers.add_parser(
        "rollout-summary",
        help="Read a bounded redacted prefix summary from one rollout without copying the full file.",
    )
    rollout_summary.add_argument("--host", required=True)
    rollout_summary.add_argument(
        "--rollout",
        required=True,
        help="Relative rollout path under the remote Codex root (sessions/..., archived_sessions/..., or root rollout-*.jsonl).",
    )
    rollout_summary.add_argument("--keyword", action="append", default=[])
    rollout_summary.add_argument("--limit", type=int, default=40)
    rollout_summary.add_argument("--tail-records", type=int, default=8)
    rollout_summary.add_argument("--max-text-chars", type=int, default=400)
    rollout_summary.set_defaults(func=cmd_rollout_summary)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
