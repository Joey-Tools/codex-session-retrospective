from __future__ import annotations

from collections.abc import Iterator
import copy
import hashlib
from itertools import chain
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import retrospective_v2.result_validation as result_validation_module  # noqa: E402
import retrospective_v2.source_overlap as source_overlap_module  # noqa: E402
from retrospective_v2.episode_review import (  # noqa: E402
    construct_episodes,
    create_episode_revision,
    derive_corrected_episode_ref,
    derive_episode_correction_generation,
    derive_episode_meaningfulness,
    material_review_conflict,
    plan_episode_review_jobs,
)
from retrospective_v2.contracts import JobKind  # noqa: E402
from retrospective_v2.identity import IdentityKey  # noqa: E402
from retrospective_v2.result_validation import (  # noqa: E402
    ADJUDICATION_RESULT_SCHEMA,
    EPISODE_REVIEW_RESULT_SCHEMA,
    EXTRACTOR_RESULT_SCHEMA,
    QUESTION_IDS,
    SYNTHESIS_RESULT_SCHEMA,
    TOPIC_INPUT_SCHEMA,
    TOPIC_RESULT_SCHEMA,
    ResultValidationError,
    build_synthesis_prompt_rewrite_commitment,
    build_synthesis_prompt_rewrite_exemplars,
    build_synthesis_signal_exemplars,
    build_synthesis_signal_commitments,
    build_synthesis_topic_result_commitment,
    build_hierarchical_reduction_commitment,
    build_hierarchical_topic_result,
    build_topic_result,
    canonical_result_hash,
    scan_for_leaks,
    validate_adjudication_result,
    validate_episode_review_result,
    validate_extractor_result,
    validate_hierarchical_episode_review_result,
    validate_hierarchical_topic_result,
    validate_synthesis_result,
    validate_topic_input,
    validate_topic_result,
)


# Review helper synthetic-token catalog IDs: access-a, api-key-a, bearer-a,
# and refresh-a.
SYNTHETIC_ACCESS_TOKEN = "codex_synth_v1_access_a"
SYNTHETIC_API_KEY = "codex_synth_v1_api_key_a"
SYNTHETIC_BEARER_TOKEN = "codex_synth_v1_bearer_a"
SYNTHETIC_REFRESH_TOKEN = "codex_synth_v1_refresh_a"


def ref(kind: str, marker: str) -> str:
    digest = hashlib.sha256(f"{kind}:{marker}".encode("ascii")).hexdigest()
    return f"{kind}_ref_v2:{digest}"


SESSION_A = ref("session", "a")
SESSION_B = ref("session", "b")
TURN_A = ref("turn", "c")
TURN_B = ref("turn", "d")
TURN_C = ref("turn", "e")
SOURCE = ref("source_unit", "f")
EVIDENCE_A = ref("evidence", "g")
EVIDENCE_B = ref("evidence", "h")
SPAN_A = ref("span_commitment", "i")
SPAN_B = ref("span_commitment", "j")
GOAL_A = ref("goal", "k")
GOAL_B = ref("goal", "l")
WORKSTREAM_A = ref("workstream", "m")
WORKSTREAM_B = ref("workstream", "n")
EPISODE = ref("episode", "o")
REVISION_A = ref("episode_revision", "p")
REVISION_B = ref("episode_revision", "q")
TOPIC = ref("topic", "r")
TOPIC_CANDIDATE = ref("topic_candidate", "candidate")
MODEL = ref("model_configuration", "s")
EPISODE_B = ref("episode", "second")
ATTEMPT_PRIMARY = ref("attempt", "primary")
ATTEMPT_SECONDARY = ref("attempt", "secondary")
REVIEWER_PRIMARY = ref("reviewer", "primary")
REVIEWER_SECONDARY = ref("reviewer", "secondary")

ALL_REFS = {
    SESSION_A,
    SESSION_B,
    TURN_A,
    TURN_B,
    TURN_C,
    SOURCE,
    EVIDENCE_A,
    EVIDENCE_B,
    SPAN_A,
    SPAN_B,
    GOAL_A,
    GOAL_B,
    WORKSTREAM_A,
    WORKSTREAM_B,
    EPISODE,
    REVISION_A,
    REVISION_B,
    TOPIC,
    TOPIC_CANDIDATE,
    MODEL,
    EPISODE_B,
    ATTEMPT_PRIMARY,
    ATTEMPT_SECONDARY,
    REVIEWER_PRIMARY,
    REVIEWER_SECONDARY,
}


def signal(kind: str, evidence_ref: str = EVIDENCE_A) -> dict:
    return {"kind": kind, "evidence_refs": [evidence_ref], "confidence": "high"}


def extractor_result() -> dict:
    return {
        "schema": EXTRACTOR_RESULT_SCHEMA,
        "source_unit_ref": SOURCE,
        "turns": [
            {
                "turn_ref": TURN_A,
                "generalized_working_text": "A bounded verification completed.",
                "events": [signal("verification_completed")],
                "findings": [],
                "strengths": [signal("complete_verification")],
                "risk_flags": [],
                "outcome": "completed",
                "confidence": "high",
                "evidence_refs": [EVIDENCE_A],
                "span_commitments": [SPAN_A],
                "goal_ref": GOAL_A,
                "workstream_ref": WORKSTREAM_A,
                "goal_change": "continues",
                "workstream_change": False,
                "task_completed": False,
                "user_redirect": False,
                "meaningfulness_hint": "meaningful",
                "conflicting_signals": False,
            }
        ],
    }


def high_impact(turn_ref: str = TURN_A) -> dict:
    return {
        "turn_ref": turn_ref,
        "problem_statement": "The request left a destructive operation ambiguous.",
        "cause": "The desired recovery boundary was not explicit.",
        "rewritten_prompt": "Inspect state first and require confirmation before destructive changes.",
        "expected_effect": "The operation remains reversible until intent is confirmed.",
        "evidence_refs": [EVIDENCE_A],
        "confidence": "high",
        "severity": "high",
    }


def adjudication_item_decisions(
    candidates: list[dict], adjudication: dict
) -> list[dict]:
    fields = (
        "events",
        "findings",
        "strengths",
        "risk_flags",
        "high_impact_turns",
        "evidence_refs",
    )

    def canonical(value: object) -> str:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    rows = []
    for candidate in candidates:
        candidate_hash = canonical_result_hash(candidate)
        for field in fields:
            retained = {canonical(item) for item in adjudication[field]}
            codes = []
            for item in candidate[field]:
                item_value = canonical(item)
                duplicate = (
                    sum(
                        item_value
                        in {canonical(other) for other in other_candidate[field]}
                        for other_candidate in candidates
                    )
                    > 1
                )
                is_retained = item_value in retained
                codes.append(
                    "M" if is_retained and duplicate else "S" if is_retained else "L"
                )
            rows.append(
                {
                    "candidate_result_hash": candidate_hash,
                    "decision_codes": "".join(codes),
                    "field": field,
                    "reviewer_slot": candidate["reviewer_slot"],
                }
            )
    return rows


def episode_review(
    *,
    episode_ref: str = EPISODE,
    revision_ref: str = REVISION_A,
    reviewer_slot: str = "primary",
    findings: list[dict] | None = None,
    risks: list[str] | None = None,
    high_impact_turns: list[dict] | None = None,
    attempt_ref: str | None = None,
    reviewer_ref: str | None = None,
) -> dict:
    if attempt_ref is None:
        attempt_ref = (
            ATTEMPT_PRIMARY if reviewer_slot == "primary" else ATTEMPT_SECONDARY
        )
    if reviewer_ref is None:
        reviewer_ref = (
            REVIEWER_PRIMARY if reviewer_slot == "primary" else REVIEWER_SECONDARY
        )
    return {
        "schema": EPISODE_REVIEW_RESULT_SCHEMA,
        "episode_ref": episode_ref,
        "episode_revision_ref": revision_ref,
        "disposition": "reviewed",
        "events": [signal("verification_completed")],
        "findings": [] if findings is None else findings,
        "strengths": [signal("complete_verification")],
        "risk_flags": [] if risks is None else risks,
        "high_impact_turns": [] if high_impact_turns is None else high_impact_turns,
        "evidence_refs": [EVIDENCE_A],
        "confidence": "high",
        "reviewer_slot": reviewer_slot,
        "attempt_ref": attempt_ref,
        "reviewer_ref": reviewer_ref,
        "second_review_recommended": False,
        "conflicting_signals": False,
    }


def episode_review_gap(
    *,
    episode_ref: str,
    revision_ref: str,
    reviewer_slot: str,
    gap_reason: str = "review_failure",
) -> dict:
    result = episode_review(
        episode_ref=episode_ref,
        revision_ref=revision_ref,
        reviewer_slot=reviewer_slot,
    )
    result.update(
        {
            "disposition": "review_gap",
            "events": [],
            "findings": [],
            "strengths": [],
            "risk_flags": [],
            "high_impact_turns": [],
            "evidence_refs": [],
            "confidence": "low",
            "gap_reason": gap_reason,
        }
    )
    return result


def turn(
    turn_ref: str,
    *,
    session_ref: str = SESSION_A,
    timestamp: str,
    goal_ref: str = GOAL_A,
    workstream_ref: str = WORKSTREAM_A,
    meaningfulness: str = "meaningful",
    sequence: int = 0,
    **overrides: object,
) -> dict:
    row = {
        "turn_ref": turn_ref,
        "session_ref": session_ref,
        "canonical_time": timestamp,
        "sequence": sequence,
        "goal_ref": goal_ref,
        "workstream_ref": workstream_ref,
        "meaningfulness": meaningfulness,
        "risk_flags": [],
        "confidence": "high",
    }
    row.update(overrides)
    return row


def synthesis_result() -> dict:
    return {
        "schema": SYNTHESIS_RESULT_SCHEMA,
        "question_answers": [
            {
                "question_id": question_id,
                "disposition": "not_observed",
                "event_kinds": [],
                "finding_kinds": [],
                "strength_kinds": [],
                "evidence_refs": [],
                "confidence": "high",
            }
            for question_id in QUESTION_IDS
        ],
        "events": [],
        "findings": [],
        "strengths": [],
        "prompt_rewrites": [],
        "prompt_rewrite_commitment": (build_synthesis_prompt_rewrite_commitment(())),
        "guidance_candidates": [],
        "skill_candidates": [],
        "signal_commitments": build_synthesis_signal_commitments(()),
        "follow_up_actions": [],
        "confidence": {
            "coverage": "high",
            "extraction": "high",
            "review": "high",
            "comparability": "high",
        },
        "evidence_refs": [],
        "era_comparison": {"status": "compatible", "change": "unchanged"},
        "topic_result_commitment": build_synthesis_topic_result_commitment(()),
    }


class ResultValidationTests(unittest.TestCase):
    def test_result_envelope_rejects_hidden_characters(self) -> None:
        hidden_characters = (
            "\x00",
            "\x1b",
            "\x7f",
            "\u034f",
            "\u200b",
            "\ufe0f",
            "\U000e0100",
        )
        for hidden in hidden_characters:
            with self.subTest(hidden=ascii(hidden), location="value"):
                result = extractor_result()
                result["turns"][0]["generalized_working_text"] = (
                    f"Generalized{hidden}working text"
                )
                with self.assertRaisesRegex(
                    ResultValidationError,
                    "forbidden invisible character",
                ):
                    validate_extractor_result(result, ALL_REFS)

            with self.subTest(hidden=ascii(hidden), location="key"):
                with self.assertRaisesRegex(
                    ResultValidationError,
                    "forbidden invisible field name",
                ):
                    result_validation_module.validate_result_envelope(
                        {f"safe{hidden}field": "value"}
                    )

        result = extractor_result()
        result["turns"][0]["generalized_working_text"] = "Generalized\nworking\ttext"
        validated = validate_extractor_result(result, ALL_REFS)
        self.assertEqual(
            "Generalized working text",
            validated["turns"][0]["generalized_working_text"],
        )

    def test_source_overlap_ignores_hidden_character_insertions(self) -> None:
        for hidden in ("\x00", "\x1b", "\u034f", "\u200b", "\ufe0f"):
            with self.subTest(hidden=ascii(hidden), location="result"):
                self.assertTrue(
                    scan_for_leaks(
                        {"text": f"private{hidden} project detail"},
                        original_prompts=("private project detail",),
                    )
                )

            with self.subTest(hidden=ascii(hidden), location="source"):
                self.assertTrue(
                    scan_for_leaks(
                        {"text": "private project detail"},
                        original_prompts=(f"private{hidden} project detail",),
                    )
                )

    def test_source_overlap_windows_preserve_normalized_boundaries(self) -> None:
        phrase = "cross window phrase"
        source = "AA  " + "x" * 10 + phrase.upper() + "y" * 20
        payload = json.dumps({"content": source}, separators=(",", ":"))
        windows = list(
            source_overlap_module.json_string_value_batches(
                (payload[:13], payload[13:31], payload[31:]),
                query_chars=len(phrase),
                maximum_batch_chars=24,
                maximum_batch_items=2,
            )
        )

        self.assertTrue(windows)
        self.assertTrue(all(len(batch) == 1 for batch in windows))
        self.assertTrue(all(len(batch[0]) == 24 for batch in windows))
        self.assertTrue(any(phrase in batch[0] for batch in windows))
        self.assertTrue(
            any(window.startswith("aa x") for batch in windows for window in batch)
        )

    def test_source_overlap_windows_preserve_sensitive_label_context(self) -> None:
        source = "x" * 19 + "password: abc\n" + "y" * 50
        payload = json.dumps({"content": source}, separators=(",", ":"))
        batches = tuple(
            source_overlap_module.json_string_value_batches(
                (payload,),
                query_chars=3,
                maximum_batch_chars=24,
                maximum_batch_items=4,
            )
        )
        windows = tuple(chain.from_iterable(batches))
        labeled = tuple(
            chain.from_iterable(
                map(
                    result_validation_module.privacy_locators.sensitive_labeled_values,
                    windows,
                )
            )
        )

        self.assertIn("abc", labeled)
        self.assertTrue(
            any(
                scan_for_leaks(
                    {"text": "abc was used"},
                    original_prompts=batch,
                )
                for batch in batches
            )
        )

    def test_json_value_batches_skip_keys_and_bound_memory(self) -> None:
        long_key = "never-retain-this-key-" * 3
        batches = list(
            source_overlap_module.json_string_value_batches(
                (
                    '{"role":"us',
                    f'er","{long_key}":"Acme","escaped":"line\\nvalue",',
                    '"oversized":"xxxxxxxxxxxxxxxx","unicode":"\\ud83d\\ude00",'
                    '"status":"complete","session_id":"session-value"}',
                ),
                query_chars=4,
                maximum_batch_chars=20,
                maximum_batch_items=2,
            )
        )
        values = [value for batch in batches for value in batch]

        self.assertNotIn("user", values)
        self.assertIn("acme", values)
        self.assertIn("line value", values)
        self.assertIn("😀", values)
        self.assertNotIn("complete", values)
        self.assertIn("session-value", values)
        self.assertNotIn("role", values)
        self.assertFalse(any("never-retain" in value for value in values))
        self.assertTrue(any(value == "x" * 16 for value in values))
        self.assertTrue(all(len(batch) <= 2 for batch in batches))
        self.assertTrue(all(sum(map(len, batch)) <= 20 for batch in batches))

        whitespace_dense = list(
            source_overlap_module.json_string_value_batches(
                ('{"content":"                        x"}',),
                query_chars=4,
                maximum_batch_chars=8,
                maximum_batch_items=2,
            )
        )
        self.assertEqual([("x",)], whitespace_dense)
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            list(
                source_overlap_module.json_string_value_batches(
                    ('{"content":"safe",}',),
                    query_chars=4,
                    maximum_batch_chars=8,
                    maximum_batch_items=2,
                )
            )

        malformed_primitives = (
            '{"content":oops"secret"}',
            '{"content":tru,"next":"secret"}',
            '{"content":01,"next":"secret"}',
            '{"content":1.,"next":"secret"}',
            '{"content":1e+,"next":"secret"}',
        )
        for payload in malformed_primitives:
            with (
                self.subTest(payload=payload),
                self.assertRaisesRegex(
                    ValueError,
                    "primitive",
                ),
            ):
                list(
                    source_overlap_module.json_string_value_batches(
                        (payload,),
                        query_chars=4,
                        maximum_batch_chars=16,
                        maximum_batch_items=2,
                    )
                )

    def test_normalized_windows_batch_single_character_parser_feeds(self) -> None:
        class CountingWindows(source_overlap_module._NormalizedValueWindows):
            __slots__ = ("append_calls",)

            def __init__(self, **kwargs: int) -> None:
                super().__init__(**kwargs)
                self.append_calls = 0

            def _append_chunk(self, value: str) -> list[str]:
                self.append_calls += 1
                return super()._append_chunk(value)

        maximum_chars = result_validation_module.MAX_SOURCE_OVERLAP_CHARS
        source_chars = maximum_chars * 2
        windows = CountingWindows(query_chars=4, maximum_chars=maximum_chars)
        emitted = 0

        for _ in range(source_chars):
            emitted += len(windows.feed("x"))
        emitted += len(windows.finish())

        maximum_chunk_appends = source_chars // min(8_192, maximum_chars) + 2
        self.assertLessEqual(windows.append_calls, maximum_chunk_appends)
        self.assertGreaterEqual(emitted, 2)
        self.assertLess(windows._buffered_chars, maximum_chars)
        self.assertEqual(0, windows._pending_chars)
        self.assertLessEqual(
            len(windows._chunks),
            maximum_chars // min(8_192, maximum_chars) + 1,
        )

    def test_source_overlap_excludes_safe_metadata_but_keeps_instance_values(
        self,
    ) -> None:
        batches = list(
            source_overlap_module.json_string_value_batches(
                ('{"role":"user","content":"Acme"}',),
                query_chars=4,
                maximum_batch_chars=16,
                maximum_batch_items=2,
            )
        )
        candidates = [candidate for batch in batches for candidate in batch]

        self.assertEqual(["acme"], candidates)
        self.assertEqual(
            (), scan_for_leaks({"safe": "user"}, original_prompts=candidates)
        )
        self.assertTrue(scan_for_leaks({"unsafe": "Acme"}, original_prompts=candidates))
        self.assertTrue(
            scan_for_leaks(
                {"unsafe": "Acme rollout failed"},
                original_prompts=candidates,
            )
        )
        self.assertEqual(
            (),
            scan_for_leaks(
                {"safe": "Acmeology rollout failed"},
                original_prompts=candidates,
            ),
        )
        embedded = extractor_result()
        embedded["turns"][0]["generalized_working_text"] = "Acme rollout failed"
        validated = validate_extractor_result(
            embedded,
            ALL_REFS,
            original_prompts=candidates,
        )
        self.assertEqual(
            "[REDACTED_ORIGINAL_PROMPT] rollout failed",
            validated["turns"][0]["generalized_working_text"],
        )

        nested_control_batches = list(
            source_overlap_module.json_string_value_batches(
                (
                    '{"request_id":{"content":"Nested secret"},'
                    '"evidence_ref":["Array secret"]}',
                ),
                query_chars=4,
                maximum_batch_chars=32,
                maximum_batch_items=2,
            )
        )
        nested_control_candidates = [
            candidate for batch in nested_control_batches for candidate in batch
        ]

        self.assertIn("nested secret", nested_control_candidates)
        self.assertIn("array secret", nested_control_candidates)
        self.assertTrue(
            scan_for_leaks(
                {"unsafe": "Nested secret"},
                original_prompts=nested_control_candidates,
            )
        )

        untrusted_suffix_batches = list(
            source_overlap_module.json_string_value_batches(
                (
                    '{"customer_ref":"Discuss frosted meadow launch carefully",'
                    '"session_id":"valid-session",'
                    '"timestamp":"2026-07-06T01:00:00Z",'
                    '"STATUS":"uppercase-secret",'
                    '"\\u017ftatus":"unicode-secret",'
                    '"created_at":"2026-99-01T01:00:00Z",'
                    '"started_at":"2026-01-01T99:00:00Z",'
                    '"updated_at":"2026-01-01T01:00:00+99:00",'
                    '"completed_at":"2025-02-29T01:00:00Z",'
                    '"request_id":"Raw prompt hidden as a request id"}',
                ),
                query_chars=8,
                maximum_batch_chars=64,
                maximum_batch_items=4,
            )
        )
        untrusted_suffix_candidates = [
            candidate for batch in untrusted_suffix_batches for candidate in batch
        ]

        self.assertIn(
            "discuss frosted meadow launch carefully",
            untrusted_suffix_candidates,
        )
        self.assertIn(
            "raw prompt hidden as a request id",
            untrusted_suffix_candidates,
        )
        self.assertIn("valid-session", untrusted_suffix_candidates)
        self.assertNotIn("2026-07-06t01:00:00z", untrusted_suffix_candidates)
        self.assertIn("uppercase-secret", untrusted_suffix_candidates)
        self.assertIn("unicode-secret", untrusted_suffix_candidates)
        self.assertIn(
            "2026-99-01t01:00:00z",
            untrusted_suffix_candidates,
        )
        self.assertIn(
            "2026-01-01t99:00:00z",
            untrusted_suffix_candidates,
        )
        self.assertIn(
            "2026-01-01t01:00:00+99:00",
            untrusted_suffix_candidates,
        )
        self.assertIn(
            "2025-02-29t01:00:00z",
            untrusted_suffix_candidates,
        )
        self.assertTrue(
            scan_for_leaks(
                {"finding": "valid-session"},
                original_prompts=untrusted_suffix_candidates,
            )
        )

        instance_values = {
            "id": "customer-secret-42",
            "call_id": "call-secret-42",
            "event_id": "event-secret-42",
            "item_id": "item-secret-42",
            "request_id": "request-secret-42",
            "response_id": "response-secret-42",
            "session_id": "session-secret-42",
            "host": "private-host-42",
            "cwd": "/private/workspace-42",
            "attempt_ref": "attempt_ref_v2:" + "0" * 64,
            "bundle_digest": "sha256:" + "a" * 64,
        }
        instance_batches = list(
            source_overlap_module.json_string_value_batches(
                (json.dumps(instance_values, separators=(",", ":")),),
                query_chars=8,
                maximum_batch_chars=128,
                maximum_batch_items=8,
            )
        )
        instance_candidates = [
            candidate for batch in instance_batches for candidate in batch
        ]
        for value in instance_values.values():
            with self.subTest(value=value):
                self.assertIn(value.casefold(), instance_candidates)
        findings = scan_for_leaks(
            {"generalized_working_text": "customer-secret-42"},
            original_prompts=instance_candidates,
        )
        self.assertIn("original_prompt", {finding.category for finding in findings})
        attempt_ref = "attempt_ref_v2:" + "0" * 64
        unallowed_reference_findings = scan_for_leaks(
            {"attempt_ref": attempt_ref},
            original_prompts=instance_candidates,
        )
        self.assertIn(
            "original_prompt",
            {finding.category for finding in unallowed_reference_findings},
        )
        self.assertEqual(
            (),
            scan_for_leaks(
                {"attempt_ref": attempt_ref},
                original_prompts=instance_candidates,
                allowed_reference_values={attempt_ref},
            ),
        )
        malformed_reference_findings = scan_for_leaks(
            {"attempt_ref": "customer-secret-42"},
            original_prompts=instance_candidates,
        )
        self.assertIn(
            "original_prompt",
            {finding.category for finding in malformed_reference_findings},
        )

    def test_source_overlap_classifier_values_use_closed_field_semantics(
        self,
    ) -> None:
        unknown_values = {
            key: f"private-{key}-value"
            for key in source_overlap_module._CONTROL_CLASSIFIER_VALUES
        }
        payload = {
            **unknown_values,
            "nested": {
                "approval_policy": "never",
                "provider": "openai",
                "sandbox_policy": "read-only",
                "state": "present",
                "status": "completed",
                "type": "response_item",
            },
        }
        candidates = [
            candidate
            for batch in source_overlap_module.json_string_value_batches(
                (json.dumps(payload, separators=(",", ":")),),
                query_chars=8,
                maximum_batch_chars=512,
                maximum_batch_items=32,
            )
            for candidate in batch
        ]

        for value in unknown_values.values():
            with self.subTest(value=value):
                self.assertIn(value, candidates)
        for value in payload["nested"].values():
            with self.subTest(closed_value=value):
                self.assertNotIn(value, candidates)

    def test_source_overlap_rejects_twelve_through_fifteen_character_substrings(
        self,
    ) -> None:
        source_fragment = "FrostedMeadowLaunch"

        for length in range(12, 16):
            fragment = source_fragment[:length]
            source = f"prefix{fragment}suffix"
            with self.subTest(length=length):
                self.assertEqual(length, len(fragment))
                self.assertIn(
                    "original_prompt",
                    {
                        finding.category
                        for finding in scan_for_leaks(
                            {"unsafe": fragment},
                            original_prompts=(source,),
                        )
                    },
                )

    def test_source_overlap_extracts_sensitive_labeled_values(self) -> None:
        cases = (
            (
                "password: winter123",
                "winter123 was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"DatabaseSecret was {SYNTHETIC_BEARER_TOKEN}",
                f"{SYNTHETIC_BEARER_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"DatabaseSecret WAS {SYNTHETIC_BEARER_TOKEN}.",
                f"{SYNTHETIC_BEARER_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"DatabaseSecret was {SYNTHETIC_BEARER_TOKEN}, status ok",
                f"{SYNTHETIC_BEARER_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"DatabaseSecret was unavailable: {SYNTHETIC_BEARER_TOKEN}, status ok",
                f"{SYNTHETIC_BEARER_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"ServiceRefreshToken was {SYNTHETIC_REFRESH_TOKEN} before continuing.",
                f"{SYNTHETIC_REFRESH_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"ServiceRefreshToken was {SYNTHETIC_REFRESH_TOKEN} in production.",
                f"{SYNTHETIC_REFRESH_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                f"ServiceRefreshToken was {SYNTHETIC_REFRESH_TOKEN}, while production was active.",
                f"{SYNTHETIC_REFRESH_TOKEN} was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                "employee name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "customer full name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "The customer's name is Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "The customer address was 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "The employee DOB set to 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Full name is Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Full name is Smith, John",
                "John was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "**Full name is Alice Smith**",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "**Full name is Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "First name was Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Last name set to Smith",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address was 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "__Address was 123 Main Street__",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "__Address was 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "__Address was 123 Main Street, state: CA, zip: 94105__",
                "94105 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address is present at 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Full name is unavailable for Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Full name is unavailable: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "**Customer name:** Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Observed **Full name:** Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "employee full name: Bob",
                "Bob was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "user first name: Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "user last name: Smith",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "customerFullName: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "employeeFirstName: Bob",
                "Bob was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "userLastName: Smith",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Full name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "First name: Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Last name: Smith",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "client name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer's full name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "tenant name: Example Tenant",
                "Example Tenant was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "organization name: Example Organization",
                "Example Organization was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "- Full name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                '"firstName: Alice"',
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                '{"fullName": "Alice Smith"}',
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                '{"fullName": "Alice \\"Ace\\" Smith"}',
                'Alice "Ace" Smith was referenced',
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "{'fullName': 'Alice \\'Ace\\' Smith'}",
                "Alice 'Ace' Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                '{"ssn": "000-00-0000"}',
                "000-00-0000 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "passport number: X0000000",
                "X0000000 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "credit card: 4111 1111 1111 1111",
                "4111 1111 1111 1111 was referenced",
                "[REDACTED_PERSONAL_IDENTIFIER] was referenced",
            ),
            (
                "bank account number: 00012345",
                "00012345 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Medical record number: 12345678",
                "12345678 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "MRN: 12345678",
                "12345678 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Payment sent to DE89370400440532013000 before continuing.",
                "DE89370400440532013000 was referenced",
                "[REDACTED_PERSONAL_IDENTIFIER] was referenced",
            ),
            (
                "Payment sent to GB82 WEST 1234 5698 7654 32 before continuing.",
                "GB82 WEST 1234 5698 7654 32 was referenced",
                "[REDACTED_PERSONAL_IDENTIFIER] was referenced",
            ),
            (
                "Payment sent to gb82 west 1234 5698 7654 32 before continuing.",
                "gb82 west 1234 5698 7654 32 was referenced",
                "[REDACTED_PERSONAL_IDENTIFIER] was referenced",
            ),
            (
                "Payment sent to Gb82 WeSt 1234 5698 7654 32 before continuing.",
                "Gb82 WeSt 1234 5698 7654 32 was referenced",
                "[REDACTED_PERSONAL_IDENTIFIER] was referenced",
            ),
            (
                "Payment sent to KZ86 125K ZT50 0410 0100 then continued.",
                "KZ86 125K ZT50 0410 0100 was referenced",
                "[REDACTED_PERSONAL_IDENTIFIER] was referenced",
            ),
            (
                "customer address: 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: Alice Smith, 123 Main Street",
                "Alice Smith, 123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: Alice Smith, 123 Main Street",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: Alice Smith, 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: 123 Main Street, City: London, Postal Code: SW1A 1AA",
                "London was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: 123 Main Street, City: London, Postal Code: SW1A 1AA",
                "SW1A 1AA was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                'Address: 123 Main Street, City: "London"',
                "London was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: 123 Main Street, Apt: 4B",
                "4B was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Address: 123 Main Street, Unit: 5",
                "5 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer's address: 123 Main Street",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer's address: 123 Main Street before continuing.",
                "123 Main Street was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "date of birth: 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Birthday: 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Birth date: 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Birthdate: 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "DOB: 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "DOB: 1990-01-02 before continuing.",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "DOB: 1990-01-02, status verified",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                r'DOB: "\u0031\u0039\u0039\u0030-\u0030\u0031-\u0030\u0032"',
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "DateOfBirth: 1990-01-02.",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "CustomerDateOfBirth: `1990-01-02`",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "**DOB: 1990-01-02**",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Observed **Full name: Alice**",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "DOB: \u20181990-01-02\u2019",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "DOB: [REDACTED_PERSONAL_IDENTIFIER] 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                'DOB: "[REDACTED_PERSONAL_IDENTIFIER]" 1990-01-02',
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "**DOB: [REDACTED_PERSONAL_IDENTIFIER]** 1990-01-02",
                "1990-01-02 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer name: [REDACTED_PERSONAL_IDENTIFIER] 张三丰",
                "张三丰 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                '{"ssn": 123456789, "status":"ok"}',
                "123456789 was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                'password: "winter123"',
                "winter123 was rejected",
                "[REDACTED_ORIGINAL_PROMPT] was rejected",
            ),
            (
                'employee name: "Alice Smith"',
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "password: abc",
                "abc was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "passphrase: purple",
                "purple was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "pass phrase: purple",
                "purple was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "pass-phrase: purple",
                "purple was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "pass_phrase: purple",
                "purple was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "passcode: 839201",
                "839201 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "pass code: 839201",
                "839201 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "pass-code: 839201",
                "839201 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "pass_code: 839201",
                "839201 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "PIN: 8392",
                "8392 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "keyPassphrase: purple",
                "purple was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "devicePasscode: 839201",
                "839201 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "userPin: 8392",
                "8392 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "employee name: Bob",
                "Bob was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Employee middle name: Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer surname: Smith",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer family name: Smith",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer given name: Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer legal name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Nickname: Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Display name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "customer.displayName: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "user.display_name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "customer displayName: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Observed display name: Alice Smith",
                "Alice Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Profile loaded. Nickname: Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer full name: Smith, John",
                "John was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Customer display name: Smith, John",
                "John was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "customerDisplayName: Smith, John",
                "John was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "Preferred name is Alice",
                "Alice was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "**Maiden name: Smith**",
                "Smith was referenced",
                "[REDACTED_ORIGINAL_PROMPT] was referenced",
            ),
            (
                "password: ßx",
                "SSX was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "password: SSX",
                "ßx was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "password: ßxy",
                "SSXY was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "Phone number: 6123 4567",
                "6123 4567 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                'Phone: "1234567890123"',
                "1234567890123 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
            (
                "phoneNumber: 1234567890123",
                "1234567890123 was used",
                "[REDACTED_ORIGINAL_PROMPT] was used",
            ),
        )
        for source, output, expected in cases:
            with self.subTest(source=source):
                direct_categories = {
                    finding.category for finding in scan_for_leaks({"text": output})
                }
                self.assertEqual(
                    {"personal_identifier"}
                    if "[REDACTED_PERSONAL_IDENTIFIER]" in expected
                    else set(),
                    direct_categories,
                )
                findings = scan_for_leaks(
                    {"text": output},
                    original_prompts=(source,),
                )
                self.assertIn(
                    "original_prompt", {finding.category for finding in findings}
                )

                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = output
                result = validate_extractor_result(
                    value,
                    ALL_REFS,
                    original_prompts=(source,),
                )
                self.assertEqual(
                    expected,
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(
                    (),
                    scan_for_leaks(result, original_prompts=(source,)),
                )

        for tool_source, tool_output, expected in (
            (
                "password: abc",
                "abc was rejected",
                "[REDACTED_TOOL_OUTPUT] was rejected",
            ),
            (
                "Telephone number: 6123 4567",
                "6123 4567 was rejected",
                "[REDACTED_TOOL_OUTPUT] was rejected",
            ),
        ):
            with self.subTest(tool_source=tool_source):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = tool_output
                result = validate_extractor_result(
                    value,
                    ALL_REFS,
                    tool_outputs=(tool_source,),
                )
                self.assertEqual(
                    expected,
                    result["turns"][0]["generalized_working_text"],
                )
        for safe_source in (
            "status: winter123",
            "password: missing",
            "Customer's address book: shared",
            "DOB status: unavailable",
            "date of birth policy: enabled",
            "birthday policy: enabled",
            "Birth date status: unavailable",
            "**Customer status:** Alice Smith",
            "DOB: [REDACTED_PERSONAL_IDENTIFIER]",
            'DOB: "[REDACTED_PERSONAL_IDENTIFIER]"',
            "**DOB:** [REDACTED_PERSONAL_IDENTIFIER]",
            "(DOB: [REDACTED_PERSONAL_IDENTIFIER])",
            "DOB: [REDACTED_PERSONAL_IDENTIFIER]]",
            r"DOB: \"[REDACTED_PERSONAL_IDENTIFIER]\"",
            "DOB: [REDACTED_PERSONAL_IDENTIFIER]" + " " * 32_768 + "!",
            "Address: [REDACTED_PERSONAL_IDENTIFIER]",
            "Address: 0x1000",
            "Address: 0x1000, status: active",
            "Address: 0x1000, 0x2000",
            'Address: 0x1000, City: "0x2000"',
            "Address: [REDACTED_PERSONAL_IDENTIFIER], status: active",
            "Phone number: 12345",
            "Phone number: 2026-08-18",
            "Phone number: 1234567890123456",
            "Full name is required",
            "First name was missing",
            "Last name is unavailable",
            "Middle name is required",
            "Middle name was missing",
            "Address is unavailable",
            "Address was 0x1000",
            "Full name is [REDACTED_PERSONAL_IDENTIFIER]",
            "CancellationToken = active",
            "CancellationToken was cancelled",
            "DesignToken = color.primary",
            "UserPassword = missing",
            "DatabaseSecret was not present",
            "UserPasswordCount = 12",
            "Payment sent to gb91 test 1234 5678 before continuing.",
            "Payment sent to zz86 test 1234 5678 90 before continuing.",
        ):
            with self.subTest(safe_source=safe_source):
                self.assertEqual(
                    (),
                    tuple(
                        result_validation_module.privacy_locators.sensitive_labeled_values(
                            safe_source
                        )
                    ),
                )
        self.assertEqual(
            ("123-45-6789",),
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    "Identifier 123-45-6789 was referenced."
                )
            ),
        )
        self.assertEqual(
            ("4111 1111 1111 1111",),
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    "Payment used 4111 1111 1111 1111 before continuing."
                )
            ),
        )
        self.assertEqual(
            (SYNTHETIC_BEARER_TOKEN,),
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    f"DatabaseSecret was {SYNTHETIC_BEARER_TOKEN}"
                )
            ),
        )
        self.assertIn(
            "John",
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    "Full name is Smith, John"
                )
            ),
        )
        name_with_status_values = tuple(
            result_validation_module.privacy_locators.sensitive_labeled_values(
                "Full name is Smith, John, status ok"
            )
        )
        self.assertIn("John", name_with_status_values)
        self.assertNotIn("status ok", name_with_status_values)
        markdown_name_with_status_values = tuple(
            result_validation_module.privacy_locators.sensitive_labeled_values(
                "**Full name is Smith, John, status ok**"
            )
        )
        self.assertIn("John", markdown_name_with_status_values)
        self.assertNotIn("status ok", markdown_name_with_status_values)
        qualified_markdown_name_with_status_values = tuple(
            result_validation_module.privacy_locators.sensitive_labeled_values(
                "**Customer display name: Smith, John, status ok**"
            )
        )
        self.assertIn("Smith", qualified_markdown_name_with_status_values)
        self.assertIn("John", qualified_markdown_name_with_status_values)
        self.assertNotIn("status ok", qualified_markdown_name_with_status_values)
        quoted_metadata_values = tuple(
            result_validation_module.privacy_locators.sensitive_labeled_values(
                '**Customer display name: Smith, John, "status": "ok"**'
            )
        )
        self.assertIn("Smith", quoted_metadata_values)
        self.assertIn("John", quoted_metadata_values)
        self.assertNotIn('"status": "ok"', quoted_metadata_values)
        escaped_metadata_values = tuple(
            result_validation_module.privacy_locators.sensitive_labeled_values(
                r"Display name was Smith, John, \"status\": \"ok\""
            )
        )
        self.assertIn("Smith", escaped_metadata_values)
        self.assertIn("John", escaped_metadata_values)
        self.assertNotIn(r"\"status\": \"ok\"", escaped_metadata_values)
        markdown_address_with_status_values = tuple(
            result_validation_module.privacy_locators.sensitive_labeled_values(
                "__Address was 123 Main Street, status ok__"
            )
        )
        self.assertIn("123 Main Street", markdown_address_with_status_values)
        self.assertNotIn("status ok", markdown_address_with_status_values)
        self.assertEqual(
            (),
            scan_for_leaks(
                {"text": "status ok"},
                original_prompts=("Full name is Smith, John, status ok",),
            ),
        )
        self.assertEqual(
            (),
            scan_for_leaks(
                {"text": "status ok"},
                original_prompts=("**Customer display name: Smith, John, status ok**",),
            ),
        )
        self.assertEqual(
            ("GB82 WEST 1234 5698 7654 32",),
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    "Payment sent to GB82 WEST 1234 5698 7654 32."
                )
            ),
        )
        self.assertEqual(
            ("KZ86 125K ZT50 0410 0100",),
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    "Payment sent to KZ86 125K ZT50 0410 0100 then continued."
                )
            ),
        )
        self.assertEqual(
            (),
            scan_for_leaks(
                {"text": "abc was used"},
                original_prompts=("abc",),
            ),
        )
        self.assertEqual(
            (),
            scan_for_leaks({"text": "Pin the dependency version before continuing."}),
        )
        overlap_sources = tuple(
            f"customer name: Person{index:03d}" for index in range(103)
        )
        self.assertEqual(
            (),
            scan_for_leaks({"text": "safe"}, original_prompts=overlap_sources),
        )
        self.assertEqual(
            {"unredactable_secret"},
            {
                finding.category
                for finding in scan_for_leaks(
                    {"text": "[REDACTED_PERSONAL_IDENTIFIER_ALICE_SMITH]"}
                )
            },
        )
        self.assertEqual(
            '{[REDACTED_PERSONAL_IDENTIFIER], "status":"ok"}',
            result_validation_module.privacy_locators.redact_personal_identifiers(
                '{"ssn": 123456789, "status":"ok"}'
            ),
        )
        self.assertEqual(
            "Observed [REDACTED_PERSONAL_IDENTIFIER]",
            result_validation_module.privacy_locators.redact_personal_identifiers(
                "Observed **Full name: Alice**"
            ),
        )
        for middle_name in (
            "Employee middle name: Alice",
            "Employee middle_name: Alice",
            "Employee middle-name: Alice",
            "employeeMiddleName: Alice",
            "middleName: Alice",
            "MiddleName: Alice",
        ):
            with self.subTest(middle_name=middle_name):
                self.assertEqual(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        middle_name
                    ),
                )
        for name_label in (
            "Customer surname: Smith",
            "Customer family name: Smith",
            "Customer family_name: Smith",
            "Customer family-name: Smith",
            "Customer given name: Alice",
            "Customer given_name: Alice",
            "Customer given-name: Alice",
            "customerSurname: Smith",
            "customerFamilyName: Smith",
            "customerGivenName: Alice",
            "Surname: Smith",
            "familyName: Smith",
            "givenName: Alice",
            "Customer legal name: Alice Smith",
            "Customer legal_name: Alice Smith",
            "Customer legal-name: Alice Smith",
            "Customer preferred name: Alice",
            "Customer preferred_name: Alice",
            "Customer preferred-name: Alice",
            "Customer maiden name: Smith",
            "Customer maiden_name: Smith",
            "Customer maiden-name: Smith",
            "Customer nickname: Alice",
            "Customer display name: Alice Smith",
            "Customer display_name: Alice Smith",
            "Customer display-name: Alice Smith",
            "customer.displayName: Alice Smith",
            "user.display_name: Alice Smith",
            "customer displayName: Alice Smith",
            "Customer full name: Smith, John",
            "Customer display name: Smith, John",
            "customerLegalName: Alice Smith",
            "customerPreferredName: Alice",
            "customerMaidenName: Smith",
            "customerNickname: Alice",
            "customerDisplayName: Alice Smith",
            "customerDisplayName: Smith, John",
            "Legal name: Alice Smith",
            "preferredName: Alice",
            "maidenName: Smith",
            "Nickname: Alice",
            "displayName: Alice Smith",
            "**Legal name: Alice Smith**",
            "**Display name: Alice Smith**",
            "Preferred name is Alice",
            "Maiden name was Smith",
            "Nickname is Alice",
            "Display name was Alice Smith",
        ):
            with self.subTest(name_label=name_label):
                self.assertEqual(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        name_label
                    ),
                )
        for narrative_name, expected in (
            (
                "Observed display name: Alice Smith",
                "Observed [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Profile loaded. Nickname: Alice",
                "Profile loaded. [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Profile loaded. Display name was Alice Smith",
                "Profile loaded. [REDACTED_PERSONAL_IDENTIFIER]",
            ),
        ):
            with self.subTest(narrative_name=narrative_name):
                self.assertEqual(
                    expected,
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        narrative_name
                    ),
                )
        for product_label in (
            "The service display name is Gateway",
            "The release nickname was Canary",
            "service.displayName: Gateway",
            "release: nickname is Canary",
            '{"service":{"displayName":"Gateway"}}',
            "release: nickname: Canary",
        ):
            with self.subTest(product_label=product_label):
                self.assertEqual(
                    product_label,
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        product_label
                    ),
                )
                self.assertEqual(
                    (),
                    scan_for_leaks(
                        {
                            "text": (
                                "Gateway" if "Gateway" in product_label else "Canary"
                            )
                        },
                        original_prompts=(product_label,),
                    ),
                )
        self.assertEqual(
            '**[REDACTED_PERSONAL_IDENTIFIER], "status": "ok"**',
            result_validation_module.privacy_locators.redact_personal_identifiers(
                '**Display name was Smith, John, "status": "ok"**'
            ),
        )
        self.assertEqual(
            r"[REDACTED_PERSONAL_IDENTIFIER], \"status\": \"ok\"",
            result_validation_module.privacy_locators.redact_personal_identifiers(
                r"Display name was Smith, John, \"status\": \"ok\""
            ),
        )
        for birth_date in (
            "Birthday: 1990-01-02",
            "Birth date: 1990-01-02",
            "Birthdate: 1990-01-02",
            "Birth_date: 1990-01-02",
            "Birth-date: 1990-01-02",
            "birthDate: 1990-01-02",
        ):
            with self.subTest(birth_date=birth_date):
                self.assertEqual(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        birth_date
                    ),
                )
        for medical_record in (
            "Medical record number: 12345678",
            "medical_record_no: 12345678",
            "medicalRecordId: 12345678",
            "MRN: 12345678",
            "Patient ID: 12345678",
            "patient_identifier: 12345678",
            "patientIdentifier: 12345678",
        ):
            with self.subTest(medical_record=medical_record):
                self.assertEqual(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        medical_record
                    ),
                )
        for subject_identifier in (
            "Customer identifier: CUST-12345",
            "User identifier: alice-12345",
            "Account identifier: A1234567",
            "customerIdentifier: CUST-12345",
            "userIdentifier: alice-12345",
            "accountIdentifier: A1234567",
        ):
            with self.subTest(subject_identifier=subject_identifier):
                self.assertEqual(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    result_validation_module.privacy_locators.redact_personal_identifiers(
                        subject_identifier
                    ),
                )
                self.assertEqual(
                    {"personal_identifier"},
                    {
                        finding.category
                        for finding in scan_for_leaks({"text": subject_identifier})
                    },
                )
        for safe_pin_text in (
            "Inspect pin=GPIO17 before continuing.",
            "Run with --pin requests==2.32.5.",
            "The pin is bent.",
        ):
            with self.subTest(safe_pin_text=safe_pin_text):
                self.assertEqual((), scan_for_leaks({"text": safe_pin_text}))
        self.assertEqual(
            {"text": "abc was used"},
            result_validation_module.post_redact(
                {"text": "abc was used"},
                original_prompts=("abc",),
            ),
        )
        self.assertEqual(
            (),
            scan_for_leaks(
                {"text": "Bobby was referenced"},
                original_prompts=("employee name: Bob",),
            ),
        )
        self.assertEqual(
            {"text": "Bobby was referenced"},
            result_validation_module.post_redact(
                {"text": "Bobby was referenced"},
                original_prompts=("employee name: Bob",),
            ),
        )
        self.assertEqual(
            (),
            tuple(
                result_validation_module.privacy_locators.sensitive_labeled_values(
                    "password: ab"
                )
            ),
        )

        expanded_sources = [
            f"password: winter{index:03d}"
            for index in range(result_validation_module.MAX_SOURCE_OVERLAP_ITEMS)
        ]
        expanded_sources[-1] += "\npassword: additional-secret"
        with self.assertRaisesRegex(ResultValidationError, "expanded_source_overlap"):
            scan_for_leaks(
                {"safe": "bounded"},
                original_prompts=expanded_sources,
            )

    def test_placeholder_suffix_overlap_needs_no_separator(self) -> None:
        for source, output in (
            (
                "Full name: [REDACTED_PERSONAL_IDENTIFIER]Alice Smith",
                "Alice Smith was retained",
            ),
            (
                "Full name: [REDACTED_PERSONAL_IDENTIFIER]王小明",
                "王小明 was retained",
            ),
        ):
            with self.subTest(source=source):
                categories = {
                    finding.category
                    for finding in scan_for_leaks(
                        {"text": output}, original_prompts=(source,)
                    )
                }
                self.assertIn("original_prompt", categories)

    def test_noncanonical_placeholder_is_rejected_inside_retained_text(self) -> None:
        findings = scan_for_leaks(
            {"text": "Observed [REDACTED_PERSONAL_IDENTIFIER_ALICE] safely"}
        )

        self.assertEqual(
            {"unredactable_secret"}, {finding.category for finding in findings}
        )
        self.assertEqual(
            (), scan_for_leaks({"text": "Observed [REDACTED_PERSONAL_IDENTIFIER]"})
        )

    def test_sensitive_expansion_stops_consuming_at_the_requested_bound(self) -> None:
        consumed: list[str] = []

        def sources() -> Iterator[str]:
            for value in ("Full name: Alice Smith", "Full name: Bob Jones"):
                consumed.append(value)
                yield value

        expanded, _short = (
            result_validation_module.privacy_locators.expand_sensitive_labeled_values(
                sources(), maximum_items=1
            )
        )

        self.assertEqual(("Full name: Alice Smith", "Alice Smith"), expanded)
        self.assertEqual(["Full name: Alice Smith"], consumed)

    def test_source_overlap_cannot_remove_short_phone_context(self) -> None:
        for source, source_kwargs, source_marker in (
            (
                "Phone:",
                {"original_prompts": ("Phone:",)},
                "[REDACTED_ORIGINAL_PROMPT]",
            ),
            (
                "Phone :",
                {"tool_outputs": ("Phone :",)},
                "[REDACTED_TOOL_OUTPUT]",
            ),
        ):
            with self.subTest(source=source):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"{source}  61234567 before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS, **source_kwargs)
                text = result["turns"][0]["generalized_working_text"]

                self.assertIn(source_marker, text)
                self.assertIn("[REDACTED_PERSONAL_IDENTIFIER]", text)
                self.assertNotIn("61234567", text)
                self.assertEqual((), scan_for_leaks(result, **source_kwargs))

        for source_kwargs in (
            {"original_prompts": ("-",)},
            {"tool_outputs": ("-",)},
        ):
            with self.subTest(source_kwargs=source_kwargs):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    "Phone: 6123-4567 before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS, **source_kwargs)
                text = result["turns"][0]["generalized_working_text"]

                self.assertIn("[REDACTED_PERSONAL_IDENTIFIER]", text)
                self.assertNotIn("6123", text)
                self.assertNotIn("4567", text)
                self.assertEqual((), scan_for_leaks(result, **source_kwargs))

        complete_source = "Phone: 61234567 before continuing."
        for source_kwargs, expected in (
            (
                {"original_prompts": (complete_source,)},
                "[REDACTED_ORIGINAL_PROMPT]",
            ),
            (
                {"tool_outputs": (complete_source,)},
                "[REDACTED_TOOL_OUTPUT]",
            ),
        ):
            with self.subTest(source_kwargs=source_kwargs):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = complete_source

                result = validate_extractor_result(value, ALL_REFS, **source_kwargs)
                text = result["turns"][0]["generalized_working_text"]

                self.assertEqual(expected, text)
                self.assertEqual((), scan_for_leaks(result, **source_kwargs))

        credential_source = "password: Phone: 61234567 before continuing."
        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = credential_source

        result = validate_extractor_result(value, ALL_REFS)
        text = result["turns"][0]["generalized_working_text"]

        self.assertIn("[REDACTED_CREDENTIAL]", text)
        self.assertIn("[REDACTED_PERSONAL_IDENTIFIER]", text)
        self.assertNotIn("61234567", text)
        self.assertEqual((), scan_for_leaks(result))

    def test_result_complexity_is_bounded_before_privacy_processing(self) -> None:
        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = "x" * (
            result_validation_module.MAX_RESULT_STRING_CHARS + 1
        )

        with (
            mock.patch.object(
                result_validation_module,
                "_post_redact_text",
                side_effect=AssertionError("privacy processing started"),
            ),
            self.assertRaisesRegex(ResultValidationError, "must be at most 4096"),
        ):
            validate_extractor_result(value, ALL_REFS)

        with self.assertRaisesRegex(
            ResultValidationError,
            "source characters",
        ):
            scan_for_leaks(
                {"safe": "bounded"},
                original_prompts=[
                    "x" * (result_validation_module.MAX_SOURCE_OVERLAP_CHARS + 1)
                ],
            )

    def test_overlap_scan_preindexes_large_nonmatching_source(self) -> None:
        source = "".join(
            chr(0x400 + index % 1024)
            for index in range(result_validation_module.MAX_SOURCE_OVERLAP_CHARS)
        )
        with mock.patch.object(
            result_validation_module,
            "_build_source_overlap_index",
            wraps=result_validation_module._build_source_overlap_index,
        ) as build_index:
            findings = scan_for_leaks(
                {"safe": "z" * result_validation_module.MAX_RESULT_STRING_CHARS},
                original_prompts=[source],
            )

        self.assertEqual((), findings)
        self.assertEqual(2, build_index.call_count)

    def test_extractor_accepts_closed_structured_result(self) -> None:
        result = validate_extractor_result(extractor_result(), ALL_REFS)

        self.assertEqual(
            result["turns"][0]["events"][0]["kind"], "verification_completed"
        )
        self.assertEqual(scan_for_leaks(result), ())

    def test_extractor_binds_two_goal_and_workstream_pairs_per_turn(self) -> None:
        value = extractor_result()
        second = copy.deepcopy(value["turns"][0])
        second.update(
            {
                "turn_ref": TURN_B,
                "events": [signal("verification_completed", EVIDENCE_B)],
                "strengths": [signal("complete_verification", EVIDENCE_B)],
                "evidence_refs": [EVIDENCE_B],
                "span_commitments": [SPAN_B],
                "goal_ref": GOAL_B,
                "workstream_ref": WORKSTREAM_B,
            }
        )
        value["turns"].append(second)
        bindings = {
            TURN_A: {
                "evidence_refs": [EVIDENCE_A],
                "span_refs": [SPAN_A],
                "goal_ref": GOAL_A,
                "workstream_ref": WORKSTREAM_A,
            },
            TURN_B: {
                "evidence_refs": [EVIDENCE_B],
                "span_refs": [SPAN_B],
                "goal_ref": GOAL_B,
                "workstream_ref": WORKSTREAM_B,
            },
        }

        result = validate_extractor_result(
            value,
            ALL_REFS,
            turn_bindings=bindings,
        )

        self.assertEqual(
            [(turn["goal_ref"], turn["workstream_ref"]) for turn in result["turns"]],
            [(GOAL_A, WORKSTREAM_A), (GOAL_B, WORKSTREAM_B)],
        )

    def test_extractor_rejects_goal_or_workstream_from_shard_union(self) -> None:
        value = extractor_result()
        bindings = {
            TURN_A: {
                "evidence_refs": [EVIDENCE_A],
                "span_refs": [SPAN_A],
                "goal_ref": GOAL_A,
                "workstream_ref": WORKSTREAM_A,
            }
        }
        value["turns"][0]["goal_ref"] = GOAL_B

        with self.assertRaisesRegex(ResultValidationError, "allow-list"):
            validate_extractor_result(
                value,
                ALL_REFS,
                turn_bindings=bindings,
            )

        value["turns"][0]["goal_ref"] = GOAL_A
        value["turns"][0]["workstream_ref"] = WORKSTREAM_B
        with self.assertRaisesRegex(ResultValidationError, "allow-list"):
            validate_extractor_result(
                value,
                ALL_REFS,
                turn_bindings=bindings,
            )

    def test_post_redaction_removes_all_deterministic_leak_families(self) -> None:
        value = extractor_result()
        original_prompt = "Deploy the service with the emergency override."
        tool_output = "command failed with private diagnostic text"
        value["turns"][0]["generalized_working_text"] = (
            "token=abcdefgh12345678 at https://build.corp/run from "
            "/Users/operator/private/repo with id 550e8400-e29b-41d4-a716-446655440000. "
            f"Prompt: {original_prompt} Output: {tool_output}"
        )

        result = validate_extractor_result(
            value,
            ALL_REFS,
            original_prompts=[original_prompt],
            tool_outputs=[tool_output],
        )

        text = result["turns"][0]["generalized_working_text"]
        self.assertIn("[REDACTED_CREDENTIAL]", text)
        self.assertIn("[REDACTED_URL]", text)
        self.assertIn("[REDACTED_PATH]", text)
        self.assertIn("[REDACTED_RAW_ID]", text)
        self.assertIn("[REDACTED_ORIGINAL_PROMPT]", text)
        self.assertIn("[REDACTED_TOOL_OUTPUT]", text)
        self.assertEqual(
            scan_for_leaks(
                result, original_prompts=[original_prompt], tool_outputs=[tool_output]
            ),
            (),
        )

    def test_changed_camelcase_credential_label_is_redacted_below_overlap_window(
        self,
    ) -> None:
        original_prompt = f"serviceAuthToken: {SYNTHETIC_ACCESS_TOKEN}"
        rewritten = f"githubToken: {SYNTHETIC_ACCESS_TOKEN}"
        self.assertLess(len(f": {SYNTHETIC_ACCESS_TOKEN}"), 32)

        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = rewritten
        result = validate_extractor_result(
            value,
            ALL_REFS,
            original_prompts=[original_prompt],
        )

        text = result["turns"][0]["generalized_working_text"]
        self.assertEqual("[REDACTED_CREDENTIAL]", text)
        self.assertNotIn(SYNTHETIC_ACCESS_TOKEN, text)
        self.assertEqual(
            (),
            scan_for_leaks(result, original_prompts=[original_prompt]),
        )

        for safe_text in (
            "tokenCount: 12",
            "githubTokenCount: 12",
            "cacheKey=stable-cache-entry",
            "primaryKey=turn_ref",
            "githubtoken=missing",
            "githubToken=missing",
            "serviceAuthToken=[REDACTED_CREDENTIAL]",
        ):
            with self.subTest(safe_text=safe_text):
                self.assertEqual((), scan_for_leaks(safe_text))

    def test_post_redaction_removes_one_time_and_recovery_codes(self) -> None:
        for source in (
            "OTP: 123456",
            "MFA code: 123456",
            "2FA code: 123456",
            "two_factor_code: 123456",
            "Recovery code: RECOVERY-TEST-0000",
            "Backup code: BACKUP-TEST-0000",
            "deviceOtp: 123456",
            "AccountMFACode: 123456",
            "UserRecoveryCode: RECOVERY-TEST-0000",
        ):
            with self.subTest(source=source):
                self.assertIn(
                    "credential",
                    {finding.category for finding in scan_for_leaks(source)},
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source
                result = validate_extractor_result(value, ALL_REFS)
                self.assertEqual(
                    "[REDACTED_CREDENTIAL]",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual((), scan_for_leaks(result))

    def test_post_redaction_preserves_only_unambiguous_dotted_versions(self) -> None:
        for source in (
            "The release used version v1.2.3.4 before rollback.",
            "Release v1.2.3.4 completed.",
        ):
            with self.subTest(source=source):
                self.assertEqual((), scan_for_leaks(source))
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source
                result = validate_extractor_result(value, ALL_REFS)
                self.assertEqual(
                    source,
                    result["turns"][0]["generalized_working_text"],
                )

        for unsafe in (
            "The release server was 1.2.3.4.",
            "The release used version 1.2.3.4 before rollback.",
            "Release 1.2.3.4 completed.",
            "Connect to version 54.23.12.1 before continuing.",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertIn(
                    "ip_address",
                    {finding.category for finding in scan_for_leaks(unsafe)},
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = unsafe
                result = validate_extractor_result(value, ALL_REFS)
                self.assertIn(
                    "[REDACTED_IP_ADDRESS]",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual((), scan_for_leaks(result))

    def test_post_redaction_removes_labeled_identifier_forms(self) -> None:
        for source in (
            "Session identifier: 01JABCDEFGHJKMNPQRSTVWXYZ0",
            "Thread identifier: opaque-thread-12345",
            "Tool call identifier: call_ABCDEFG123456",
        ):
            with self.subTest(source=source):
                self.assertIn(
                    "raw_id",
                    {finding.category for finding in scan_for_leaks(source)},
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                result = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "[REDACTED_RAW_ID]",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual((), scan_for_leaks(result))

    def test_shared_credential_policy_redacts_legacy_retained_families(self) -> None:
        jwt_segment = "".join(("eyJ", "A" * 8))
        stateless_github = "".join(
            ("ghs_", "123456_", jwt_segment, ".", "B" * 12, ".", "C" * 16)
        )
        multiword_value = " ".join(("correct", "horse", "battery", "staple"))
        punctuation_value = "".join(("!@#", "$%^", "&*()"))
        long_authorization = "".join(("Authorization: Basic ", "D" * 1200, "TAIL"))
        truncated_private_key = "".join(("-----BEGIN ", "PRIVATE KEY-----\n", "E" * 96))
        truncated_dsa_private_key = "".join(
            ("-----BEGIN DSA ", "PRIVATE KEY-----\n", "F" * 96)
        )
        private_key_label = " ".join(("PRI" + "VATE", "K" + "EY"))
        rsa_label = f"RSA {private_key_label}"
        ec_label = f"EC {private_key_label}"
        rsa_begin = f"-----BEGIN {rsa_label}-----"
        rsa_end = f"-----END {rsa_label}-----"
        ec_begin = f"-----BEGIN {ec_label}-----"
        ec_end = f"-----END {ec_label}-----"
        mismatched_private_key = (
            f"{rsa_begin}\n{'G' * 48}\n{ec_end}\n{'H' * 48}\n{rsa_end}"
        )
        nested_private_key = (
            f"{rsa_begin}\n{'I' * 48}\n{ec_begin}\n{'J' * 48}\n"
            f"{ec_end}\n{'K' * 48}\n{rsa_end}"
        )
        unmatched_private_key = f"{rsa_begin}\n{'L' * 48}\n{ec_end}\n{'M' * 48}"
        quoted_head = "N" * 20
        quoted_suffix = "O" * 12
        probes = (
            *(
                ("".join((prefix, "A" * 16)), ("A" * 16,), "[REDACTED_CREDENTIAL]")
                for prefix in ("gho_", "ghr_", "ghs_", "ghu_")
            ),
            (stateless_github, ("C" * 16,), "[REDACTED_CREDENTIAL]"),
            (long_authorization, ("D" * 64, "TAIL"), "[REDACTED_CREDENTIAL]"),
            (truncated_private_key, ("E" * 64,), "[REDACTED_SECRET]"),
            (truncated_dsa_private_key, ("F" * 64,), "[REDACTED_SECRET]"),
            (
                mismatched_private_key,
                ("G" * 48, "H" * 48, "END EC PRIVATE KEY"),
                "[REDACTED_SECRET]",
            ),
            (
                nested_private_key,
                ("I" * 48, "J" * 48, "K" * 48),
                "[REDACTED_SECRET]",
            ),
            (
                unmatched_private_key,
                ("L" * 48, "M" * 48, "END EC PRIVATE KEY"),
                "[REDACTED_SECRET]",
            ),
            (
                "".join(("Proxy-Authorization: Basic ", "A" * 16)),
                ("A" * 16,),
                "[REDACTED_CREDENTIAL]",
            ),
            ("".join(("sk-", "A" * 12)), ("A" * 12,), "[REDACTED_CREDENTIAL]"),
            ("".join(("rk-", "B" * 12)), ("B" * 12,), "[REDACTED_CREDENTIAL]"),
            (
                f"client_secret={SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"pwd={SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"credential={SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"refreshToken={SYNTHETIC_REFRESH_TOKEN}",
                (SYNTHETIC_REFRESH_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"UserPassword = {SYNTHETIC_BEARER_TOKEN}",
                (SYNTHETIC_BEARER_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"DatabaseSecret was {SYNTHETIC_BEARER_TOKEN}",
                (SYNTHETIC_BEARER_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"UserPIN = {SYNTHETIC_BEARER_TOKEN}",
                (SYNTHETIC_BEARER_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"ServiceAPIKey = {SYNTHETIC_API_KEY}",
                (SYNTHETIC_API_KEY,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"DatabaseCredential was {SYNTHETIC_BEARER_TOKEN}",
                (SYNTHETIC_BEARER_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"DatabaseSecret WAS {SYNTHETIC_BEARER_TOKEN}.",
                (SYNTHETIC_BEARER_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"DatabaseSecret was {SYNTHETIC_BEARER_TOKEN}, status ok",
                (SYNTHETIC_BEARER_TOKEN, "status ok"),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"DatabaseSecret was unavailable: {SYNTHETIC_BEARER_TOKEN}, status ok",
                (SYNTHETIC_BEARER_TOKEN, "status ok"),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"DatabaseAccessToken = {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"ServiceRefreshToken was {SYNTHETIC_REFRESH_TOKEN}",
                (SYNTHETIC_REFRESH_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"ServiceRefreshToken was {SYNTHETIC_REFRESH_TOKEN} in production.",
                (SYNTHETIC_REFRESH_TOKEN, "production"),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"ServiceRefreshToken was {SYNTHETIC_REFRESH_TOKEN}, while production was active.",
                (SYNTHETIC_REFRESH_TOKEN, "production"),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"run deploy --token {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            *(
                (
                    f"token={placeholder}{SYNTHETIC_ACCESS_TOKEN}",
                    (SYNTHETIC_ACCESS_TOKEN,),
                    "[REDACTED_CREDENTIAL]",
                )
                for placeholder in (
                    "[REDACTED_CREDENTIAL]",
                    "<REDACTED_CREDENTIAL>",
                    "(MASKED_CREDENTIAL)",
                    "{REDACTED_CREDENTIAL}",
                    "missing]",
                    "[REDACTED_CREDENTIAL] ",
                    '"[REDACTED_CREDENTIAL]" ',
                    "[REDACTED_CREDENTIAL]\v",
                    "[REDACTED_CREDENTIAL]\u00a0",
                    "[REDACTED_CREDENTIAL]\n",
                    "[REDACTED_CREDENTIAL] # : ",
                )
            ),
            (
                f"Authorization: [REDACTED_CREDENTIAL] {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"run deploy --token [REDACTED_CREDENTIAL] {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"credential is missing {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"credential is required {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            *(
                (
                    f"credential is {status} {SYNTHETIC_ACCESS_TOKEN}",
                    (SYNTHETIC_ACCESS_TOKEN,),
                    "[REDACTED_CREDENTIAL]",
                )
                for status in ("not required", "not present", "not available")
            ),
            (
                f"Bearer [REDACTED_CREDENTIAL] {SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                "run deploy --token\u00a0[REDACTED_CREDENTIAL]\u00a0"
                f"{SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"credential\u00a0is\u00a0missing\u00a0{SYNTHETIC_ACCESS_TOKEN}",
                (SYNTHETIC_ACCESS_TOKEN,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f'password="{multiword_value}"',
                tuple(multiword_value.split()),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f'password="[REDACTED_CREDENTIAL] {multiword_value}"',
                tuple(multiword_value.split()),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f"password='{punctuation_value}'",
                (punctuation_value,),
                "[REDACTED_CREDENTIAL]",
            ),
            (
                f'password="[REDACTED_CREDENTIAL] {punctuation_value}"',
                (punctuation_value,),
                "[REDACTED_CREDENTIAL]",
            ),
            *(
                (
                    probe,
                    (quoted_head, quoted_suffix),
                    "[REDACTED_CREDENTIAL]",
                )
                for probe in (
                    f'password="{quoted_head}"{quoted_suffix}',
                    f'Authorization: "{quoted_head}"{quoted_suffix}',
                    f'run deploy --token "{quoted_head}"{quoted_suffix}',
                    f'credential is "{quoted_head}"{quoted_suffix}',
                    f'password="{quoted_head}""{quoted_suffix}"',
                    f'password="{quoted_head}"{quoted_suffix}\\ continued',
                    f'password="{quoted_head}\n{quoted_suffix}"',
                )
            ),
        )

        for probe, forbidden_fragments, replacement in probes:
            with self.subTest(probe=probe):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Inspect {probe} before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS)

                text = result["turns"][0]["generalized_working_text"]
                self.assertNotIn(probe, text)
                for fragment in forbidden_fragments:
                    self.assertNotIn(fragment, text)
                self.assertIn(replacement, text)
                self.assertEqual(scan_for_leaks(result), ())

        for safe_probe in (
            "token=[REDACTED]",
            'token = "[REDACTED_CREDENTIAL]"',
            "refreshToken=missing",
            "credential is required",
            "credential is  required",
            "credential is required before deployment",
            "credential was missing during dry run",
            "credential is redacted in report",
            "credential is not required",
            "credential is not required before deployment",
            "credential was not present during dry run",
            "credential is not available in this environment",
            'credential is "required before deployment"',
            'credential is "not required before deployment"',
            "run deploy --token [REDACTED_CREDENTIAL]",
            "run deploy --token  [REDACTED_CREDENTIAL]",
            "Authorization:  [REDACTED_CREDENTIAL]",
            "Bearer  [REDACTED_CREDENTIAL]",
            "token=\u00a0[REDACTED_CREDENTIAL]",
            "credential\u00a0is\u00a0required",
            "run deploy --token\u00a0[REDACTED_CREDENTIAL]",
            "token=[REDACTED_CREDENTIAL]\n",
            'password=""',
            "Keep token budget under control.",
            "Token is a label.",
        ):
            with self.subTest(safe_probe=safe_probe):
                self.assertFalse(
                    result_validation_module.privacy_locators.contains_credential_material(
                        safe_probe
                    )
                )

    def test_quoted_credential_redaction_consumes_complete_shell_value(self) -> None:
        quoted_head = "N" * 20
        quoted_suffix = "O" * 12
        cases = (
            (f'password="{quoted_head}"{quoted_suffix}', ""),
            (f'Authorization: "{quoted_head}"{quoted_suffix}', ""),
            (f'run deploy --token "{quoted_head}"{quoted_suffix}', "run deploy "),
            (f'credential is "{quoted_head}"{quoted_suffix}', ""),
            (f'password="{quoted_head}""{quoted_suffix}"', ""),
            (f'password="{quoted_head}"{quoted_suffix}\\ continued', ""),
            (f'password="{quoted_head}\n{quoted_suffix}"', ""),
        )
        for probe, preserved_prefix in cases:
            with self.subTest(probe=probe):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Inspect {probe} before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "Inspect "
                    + preserved_prefix
                    + "[REDACTED_CREDENTIAL] before continuing.",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(result), ())

    def test_safe_credential_prefix_cannot_leave_punctuation_only_value(self) -> None:
        punctuation_value = "!@#$%^&*()"
        cases = (
            (f"password=[REDACTED_CREDENTIAL] {punctuation_value}", ""),
            (f"Authorization: [REDACTED_CREDENTIAL] {punctuation_value}", ""),
            (
                f"run deploy --token [REDACTED_CREDENTIAL] {punctuation_value}",
                "run deploy ",
            ),
            (f"credential is redacted {punctuation_value}", ""),
        )
        for probe, preserved_prefix in cases:
            with self.subTest(probe=probe):
                self.assertTrue(
                    result_validation_module.privacy_locators.contains_credential_material(
                        probe
                    )
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = probe

                result = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    preserved_prefix + "[REDACTED_CREDENTIAL]",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(result), ())

    def test_private_key_redaction_requires_matching_normalized_end_label(
        self,
    ) -> None:
        private_key_label = " ".join(("PRI" + "VATE", "K" + "EY"))
        rsa_label = f"RSA {private_key_label}"
        ec_label = f"EC {private_key_label}"
        rsa_begin = f"-----BEGIN {rsa_label}-----"
        rsa_spaced_begin = f"-----BEGIN RSA   {private_key_label}-----"
        rsa_lower_end = f"-----END rsa {private_key_label.lower()}-----"
        rsa_end = f"-----END {rsa_label}-----"
        ec_begin = f"-----BEGIN {ec_label}-----"
        ec_end = f"-----END {ec_label}-----"
        cases = {
            "mismatch_then_match": (
                f"{rsa_spaced_begin}\nouter-a\n{ec_end}\nouter-b\n"
                f"{rsa_lower_end} after",
                "[REDACTED_SECRET] after",
            ),
            "mismatch_without_match": (
                f"{rsa_begin}\nouter-a\n{ec_end}\nouter-b",
                "[REDACTED_SECRET]",
            ),
            "nested": (
                f"{rsa_begin}\n{ec_begin}\nnested\n{ec_end}\nouter\n{rsa_end} after",
                "[REDACTED_SECRET] after",
            ),
            "same_label_nested": (
                f"{rsa_begin}\nouter-a\n{rsa_begin}\nnested\n{rsa_end}\n"
                f"outer-b\n{rsa_end} after",
                "[REDACTED_SECRET] after",
            ),
        }
        for name, (probe, expected) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    expected,
                    result_validation_module.privacy_locators.redact_private_key_blocks(
                        probe
                    ),
                )

    def test_credential_placeholder_suffix_preserves_independent_signals(self) -> None:
        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = (
            "token=[REDACTED_CREDENTIAL] "
            f"{SYNTHETIC_ACCESS_TOKEN} at https://build.corp/run from "
            "/Users/operator/private/repo"
        )

        result = validate_extractor_result(value, ALL_REFS)

        text = result["turns"][0]["generalized_working_text"]
        self.assertNotIn(SYNTHETIC_ACCESS_TOKEN, text)
        self.assertIn("[REDACTED_CREDENTIAL]", text)
        self.assertIn("[REDACTED_URL]", text)
        self.assertIn("[REDACTED_PATH]", text)
        self.assertEqual(scan_for_leaks(result), ())

    def test_post_redaction_removes_non_http_uri_schemes(self) -> None:
        long_scheme_uri = f"{'a' * 33}://nas/jobs"
        prefixed_mixed_scheme_uri = f"locator_a{'9' * 32}+.-x://?prod-build-queue"
        self.assertIn(
            "url",
            {
                finding.category
                for finding in scan_for_leaks({"unsafe": prefixed_mixed_scheme_uri})
            },
        )
        self.assertEqual(scan_for_leaks({"safe": "9abc://?not-a-uri"}), ())
        for uri in (
            "x://private-endpoint/resource",
            "HtTp+S://private-endpoint/resource",
            "wss://build.internal/events",
            "s3://private-bucket/report",
            "postgresql://database.internal/history",
            long_scheme_uri,
            prefixed_mixed_scheme_uri,
        ):
            with self.subTest(uri=uri):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Inspect {uri} before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS)

                expected_prefix = "locator_" if uri == prefixed_mixed_scheme_uri else ""
                self.assertEqual(
                    result["turns"][0]["generalized_working_text"],
                    f"Inspect {expected_prefix}[REDACTED_URL] before continuing.",
                )
                self.assertEqual(scan_for_leaks(result), ())

    def test_post_redaction_removes_scp_locators_with_non_git_usernames(self) -> None:
        for locator in (
            "alice@buildbox:repo",
            "reviewer@internal-host:projects/session-retrospective",
        ):
            with self.subTest(locator=locator):
                findings = scan_for_leaks({"unsafe": locator})
                self.assertIn("internal_url", {item.category for item in findings})

                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Inspect {locator} before continuing."
                )
                result = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "Inspect [REDACTED_URL] before continuing.",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(result), ())

    def test_post_redaction_removes_single_label_host_emails(self) -> None:
        for email in (
            '"john doe"@example.com',
            '"john\\"doe"@example.com',
            '"john doe"@example.xn--p1ai',
            "alice@example.xn--p1ai",
            "alice@buildhost",
            "release.bot+alerts@localhost",
            "reviewer@internal-host",
        ):
            with self.subTest(email=email):
                findings = scan_for_leaks({"unsafe": email})
                self.assertIn(
                    "personal_identifier",
                    {item.category for item in findings},
                )

                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Notify {email} before continuing."
                )
                result = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "Notify [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(result), ())

        for invalid in ("alice@-buildhost", "alice@buildhost."):
            with self.subTest(invalid=invalid):
                self.assertNotIn(
                    "personal_identifier",
                    {item.category for item in scan_for_leaks({"safe": invalid})},
                )

        for narrative_email in (
            "Owner alice@dev approved it.",
            "alice@latest was referenced.",
            "Owner alice@123 approved it.",
            "We tested alice@dev without package syntax.",
            "Installed alice@dev dependency.",
            "The alice@stable release failed.",
            "The react@latest upgrade failed.",
            "The foo@next dependency remained pinned.",
            "The @scope/react@canary test was explicit.",
            "Upgrade react@latest: it fixes the issue.",
            "We tested foo@next: this failed.",
        ):
            with self.subTest(narrative_email=narrative_email):
                self.assertIn(
                    "personal_identifier",
                    {
                        item.category
                        for item in scan_for_leaks({"unsafe": narrative_email})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = narrative_email
                result = validate_extractor_result(value, ALL_REFS)
                self.assertIn(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    result["turns"][0]["generalized_working_text"],
                )

        for labeled_email in ("Email: react@latest", "Notify foo@next"):
            with self.subTest(labeled_email=labeled_email):
                self.assertIn(
                    "personal_identifier",
                    {
                        item.category
                        for item in scan_for_leaks({"unsafe": labeled_email})
                    },
                )

    def test_iana_root_tld_snapshot_is_pinned(self) -> None:
        privacy = result_validation_module.privacy_locators

        self.assertEqual("2026082000", privacy.IANA_ROOT_TLD_SNAPSHOT_VERSION)
        self.assertEqual(
            "aa0a75a9860b2cba07d7fe8172f4546d981be3674bf6764fb0d5f39a45940d25",
            privacy.IANA_ROOT_TLD_CANONICAL_SHA256,
        )
        self.assertEqual(1438, len(privacy._IANA_ROOT_TLDS))
        self.assertIn("technology", privacy._IANA_ROOT_TLDS)
        self.assertIn("xn--p1ai", privacy._IANA_ROOT_TLDS)
        self.assertNotIn("notarealtld", privacy._IANA_ROOT_TLDS)

    def test_dotted_code_and_slash_compounds_remain_reviewable_prose(self) -> None:
        safe_texts = (
            "The input/output boundary was unclear.",
            "The before/after comparison lacked evidence.",
            "The source/target mapping was explicit.",
            "The home/away comparison was irrelevant.",
            "The read/write/execute policy was reviewed.",
            "The json.loads call rejected the payload.",
            "The package.json.loads call rejected the payload.",
            "The config.toml setting was explicit.",
            "The foo.bar attribute remained stable.",
            "The foo.bar method remained stable.",
            "The api.customer.notarealtld token remained ambiguous.",
        )
        for safe_text in safe_texts:
            with self.subTest(safe_text=safe_text):
                self.assertEqual((), scan_for_leaks({"text": safe_text}))

                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = safe_text
                result = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    safe_text,
                    result["turns"][0]["generalized_working_text"],
                )
                self.assertEqual((), scan_for_leaks(result))

        for locator in (
            "docs.example.com",
            "customer.technology",
            "api.customer.technology",
            "api.customer.xn--p1ai",
            "API.Customer.TECHNOLOGY",
            "customer.technology method",
            "foo.technology attribute",
            "company.technology:8443",
            "jira.cisco.example",
            "Domain: company.technology",
            "src/a.py",
            "docs/reference",
            "team/docs/reference",
        ):
            with self.subTest(locator=locator):
                self.assertTrue(scan_for_leaks({"text": f"Inspect {locator}."}))

    def test_uri_scheme_matching_does_not_unicode_casefold(self) -> None:
        for uri_like_text in (
            "\u0130ttp://host",
            "\u0131ttp://host",
            "\u017fsh://host",
            "\u212ahttp://host",
        ):
            with self.subTest(uri_like_text=uri_like_text):
                self.assertIsNone(
                    result_validation_module.privacy_locators.URI_LOCATOR_RE.search(
                        uri_like_text
                    )
                )
                self.assertEqual(
                    result_validation_module.privacy_locators.URI_LOCATOR_RE.sub(
                        "[REDACTED_URL]", uri_like_text
                    ),
                    uri_like_text,
                )
                self.assertTrue(
                    {"url", "internal_url"}.isdisjoint(
                        finding.category
                        for finding in scan_for_leaks({"safe": uri_like_text})
                    )
                )

    def test_post_redaction_covers_posix_paths_under_unlisted_roots(self) -> None:
        for source_path in (
            "/root/acme/customer.txt",
            "/usr/local/share/private.dat",
            "/workspace/project/review.log",
        ):
            with self.subTest(source_path=source_path):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Read {source_path} before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS)

                text = result["turns"][0]["generalized_working_text"]
                self.assertEqual(text, "Read [REDACTED_PATH] before continuing.")
                self.assertEqual(scan_for_leaks(result), ())

    def test_post_redaction_covers_paths_with_spaced_intermediate_components(
        self,
    ) -> None:
        for source_path in (
            "/Users/alice/My Private Folder/secrets",
            "/Users/alice/John's Private Folder/secrets",
            "/Users/alice/Finance, Legal/secrets",
            "/Users/alice/Jane Smith Folder/Customer Notes.txt",
            "/Users/alice/Jane (Smith) & [Partners] Folder/Customer [Draft] & Notes.txt",
            (
                '/Users/alice/Jane "Smith" {#1}?!|<> Folder/'
                'Customer "Draft" {#1}?!|<> Notes.txt'
            ),
            "~/My Private Folder/secrets",
            "~/private/customer.txt",
            "~/private/Customer Notes.txt",
            "~/private/Customer.v1 Notes.txt",
            "~/Jane Smith Folder/Customer Notes.txt",
            "~/Jane (Smith) & [Partners] Folder/Customer [Draft] & Notes.txt",
            r"C:\Users\alice\My Private Folder\secrets",
            r"C:\Users\alice\John's Private Folder\secrets",
            r"C:\private\customer.txt",
            r"C:\private\Customer Notes.txt",
            r"C:\private\Customer.v1 Notes.txt",
            r"C:\Users\alice\Jane Smith Folder\Customer Notes.txt",
            r"\\server\share\My Private Folder\secrets",
            r"\\server\share\customer.txt",
            r"\\server\share\Customer Notes.txt",
            r"\\server\share\Customer.v1 Notes.txt",
            r"\\server\share\Jane Smith Folder\Customer Notes.txt",
        ):
            with self.subTest(source_path=source_path):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Read {source_path} before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS)

                text = result["turns"][0]["generalized_working_text"]
                self.assertEqual(text, "Read [REDACTED_PATH] before continuing.")
                self.assertEqual(scan_for_leaks(result), ())

    def test_post_redaction_covers_paths_with_spaced_terminal_components(
        self,
    ) -> None:
        for source_path, suffix in (
            ("/Users/alice/My Private Folder", ""),
            ("/Users/alice/My Private Folder.", "."),
            ("~/My Private Folder", ""),
            ("~/My Private Folder!", "!"),
            (r"C:\Users\alice\My Private Folder", ""),
            (r"C:\Users\alice\My Private Folder;", ";"),
            (r"\\server\share\My Private Folder", ""),
            (r"\\server\share\My Private Folder?", "?"),
        ):
            with self.subTest(source_path=source_path):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = f"Read {source_path}"

                result = validate_extractor_result(value, ALL_REFS)

                text = result["turns"][0]["generalized_working_text"]
                self.assertEqual(
                    text,
                    f"Read [REDACTED_PATH]{suffix}",
                )
                self.assertEqual(scan_for_leaks(result), ())

    def test_post_redaction_covers_relative_source_paths(self) -> None:
        for source_path in (
            "src/a.py",
            "./src/a.py",
            "../src/a.py",
            r"src\a.py",
            "src/My Private Notes.txt",
            "src/Release.v1 Private Notes.txt",
            "src/My Private Folder/secrets.txt",
            "src/Jane (Smith) & [Partners] Folder/Customer [Draft] & Notes.txt",
            "./My Private Notes.txt",
            r"src\My Private Notes.txt",
        ):
            with self.subTest(source_path=source_path):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = (
                    f"Read {source_path} before continuing."
                )

                result = validate_extractor_result(value, ALL_REFS)

                text = result["turns"][0]["generalized_working_text"]
                self.assertEqual(text, "Read [REDACTED_PATH] before continuing.")
                self.assertEqual(scan_for_leaks(result), ())

    def test_leak_scan_reports_locations_without_secret_values(self) -> None:
        secret = "s" + "k-abcdefghijklmnopqrstuvwxyz123456"
        findings = scan_for_leaks({"safe": f"credential {secret}"})

        self.assertEqual({finding.category for finding in findings}, {"credential"})
        self.assertTrue(all(secret not in repr(finding) for finding in findings))

    def test_original_prompt_is_removed_before_embedded_path_redaction(self) -> None:
        original_prompt = (
            "Inspect /Users/operator/private/repo and report the exact state."
        )
        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = original_prompt

        result = validate_extractor_result(
            value, ALL_REFS, original_prompts=[original_prompt]
        )

        self.assertEqual(
            result["turns"][0]["generalized_working_text"],
            "[REDACTED_ORIGINAL_PROMPT]",
        )

    def test_substantial_original_prompt_excerpt_is_rejected_after_redaction(
        self,
    ) -> None:
        original_prompt = (
            "First inspect the current state and preserve every reversible recovery option "
            "before proposing a narrowly scoped change."
        )
        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = (
            "The user said to inspect the current state and preserve every reversible recovery "
            "option before acting."
        )

        with self.assertRaisesRegex(ResultValidationError, "original_prompt"):
            validate_extractor_result(
                value, ALL_REFS, original_prompts=[original_prompt]
            )

    def test_private_key_block_and_bare_internal_url_are_fully_redacted(self) -> None:
        value = extractor_result()
        key_label = " ".join(("PRI" + "VATE", "K" + "EY"))
        value["turns"][0]["generalized_working_text"] = (
            f"-----BEGIN {key_label}-----\nZmFrZS1rZXktbWF0ZXJpYWw=\n"
            f"-----END {key_label}----- "
            "at build.internal/job/42"
        )

        result = validate_extractor_result(value, ALL_REFS)

        text = result["turns"][0]["generalized_working_text"]
        self.assertEqual(text, "[REDACTED_SECRET] at [REDACTED_URL]")
        self.assertEqual(scan_for_leaks(result), ())

        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = (
            "The failure involved jira.cisco.example before retry."
        )

        result = validate_extractor_result(value, ALL_REFS)

        text = result["turns"][0]["generalized_working_text"]
        self.assertEqual(
            text,
            "The failure involved [REDACTED_URL] before retry.",
        )
        self.assertEqual(scan_for_leaks(result), ())

    def test_raw_and_excerpt_fields_are_rejected_recursively(self) -> None:
        for forbidden_field in (
            "raw_text",
            "excerpt",
            "tool_output",
            "original_prompt",
        ):
            with self.subTest(forbidden_field=forbidden_field):
                value = extractor_result()
                value["turns"][0][forbidden_field] = "must not survive"
                with self.assertRaises(ResultValidationError):
                    validate_extractor_result(value, ALL_REFS)

    def test_unknown_structured_taxonomy_is_rejected(self) -> None:
        value = extractor_result()
        value["turns"][0]["events"] = [signal("approval_word_match_only")]

        with self.assertRaisesRegex(ResultValidationError, "must be one of"):
            validate_extractor_result(value, ALL_REFS)

    def test_reference_allow_list_is_enforced(self) -> None:
        value = extractor_result()
        value["turns"][0]["evidence_refs"] = [ref("evidence", "z")]

        with self.assertRaisesRegex(ResultValidationError, "allow-list"):
            validate_extractor_result(value, ALL_REFS)

    def test_episode_review_requires_every_high_impact_rewrite_field(self) -> None:
        value = episode_review(high_impact_turns=[high_impact()])
        del value["high_impact_turns"][0]["cause"]

        with self.assertRaisesRegex(
            ResultValidationError, "missing required fields: cause"
        ):
            validate_episode_review_result(value, ALL_REFS, allowed_turn_refs={TURN_A})

    def test_episode_review_post_redacts_original_prompt_from_rewrite(self) -> None:
        original_prompt = "Delete every environment immediately without asking."
        value = episode_review(high_impact_turns=[high_impact()])
        value["high_impact_turns"][0]["rewritten_prompt"] = original_prompt

        result = validate_episode_review_result(
            value,
            ALL_REFS,
            allowed_turn_refs={TURN_A},
            original_prompts=[original_prompt],
        )

        self.assertEqual(
            result["high_impact_turns"][0]["rewritten_prompt"],
            "[REDACTED_ORIGINAL_PROMPT]",
        )

    def test_episode_review_redacts_relative_paths_from_all_rewrite_fields(
        self,
    ) -> None:
        for field in (
            "problem_statement",
            "cause",
            "rewritten_prompt",
            "expected_effect",
        ):
            with self.subTest(field=field):
                value = episode_review(high_impact_turns=[high_impact()])
                value["high_impact_turns"][0][field] = "Inspect src/a.py first."

                result = validate_episode_review_result(
                    value,
                    ALL_REFS,
                    allowed_turn_refs={TURN_A},
                    original_prompts=["Please edit src/a.py."],
                )

                self.assertEqual(
                    result["high_impact_turns"][0][field],
                    "Inspect [REDACTED_PATH] first.",
                )
                self.assertEqual(scan_for_leaks(result), ())

    def test_hierarchical_episode_review_rejects_wrong_child_tree_commitment(
        self,
    ) -> None:
        child = episode_review(
            findings=[
                {
                    **signal("verification_gap", EVIDENCE_B),
                    "severity": "critical",
                }
            ],
            risks=["safety"],
            high_impact_turns=[high_impact(TURN_B)],
        )
        child["evidence_refs"] = [EVIDENCE_A, EVIDENCE_B]
        parent = episode_review()
        parent["reduction_commitment"] = build_hierarchical_reduction_commitment(
            [child], result_schema=EPISODE_REVIEW_RESULT_SCHEMA
        )
        parent["reduction_commitment"]["source_item_counts"]["findings"] += 1

        with self.assertRaisesRegex(
            ResultValidationError,
            "complete recursive child review tree",
        ):
            validate_hierarchical_episode_review_result(
                parent,
                [child],
                ALL_REFS,
                allowed_turn_refs={TURN_A, TURN_B},
                expected_child_result_hashes=[canonical_result_hash(child)],
                expected_reviewer_slot="primary",
            )

    def test_hierarchical_episode_review_conserves_child_risk_provenance(self) -> None:
        finding = {
            **signal("verification_gap", EVIDENCE_B),
            "severity": "critical",
        }
        rewrite = high_impact(TURN_B)
        child = episode_review(
            findings=[finding],
            risks=["safety"],
            high_impact_turns=[rewrite],
        )
        child["evidence_refs"] = [EVIDENCE_A, EVIDENCE_B]
        child["second_review_recommended"] = True
        child["conflicting_signals"] = True
        parent = episode_review(
            findings=[finding],
            risks=["safety"],
            high_impact_turns=[rewrite],
        )
        parent["evidence_refs"] = [EVIDENCE_A, EVIDENCE_B]
        parent["second_review_recommended"] = True
        parent["conflicting_signals"] = True
        parent["reduction_commitment"] = build_hierarchical_reduction_commitment(
            [child], result_schema=EPISODE_REVIEW_RESULT_SCHEMA
        )

        result = validate_hierarchical_episode_review_result(
            parent,
            [child],
            ALL_REFS,
            allowed_turn_refs={TURN_A, TURN_B},
            expected_child_result_hashes=[canonical_result_hash(child)],
            expected_reviewer_slot="primary",
        )

        self.assertEqual([finding], result["findings"])
        self.assertEqual([rewrite], result["high_impact_turns"])
        self.assertEqual(["safety"], result["risk_flags"])

    def test_hierarchical_episode_review_compacts_two_maximum_child_rewrite_sets(
        self,
    ) -> None:
        turn_refs = [ref("turn", f"hierarchy-{index}") for index in range(40)]
        first = episode_review(
            high_impact_turns=[high_impact(turn_ref) for turn_ref in turn_refs[:20]]
        )
        second = episode_review(
            high_impact_turns=[high_impact(turn_ref) for turn_ref in turn_refs[20:]]
        )
        parent = episode_review(
            high_impact_turns=copy.deepcopy(first["high_impact_turns"])
        )
        parent["reduction_commitment"] = build_hierarchical_reduction_commitment(
            [first, second], result_schema=EPISODE_REVIEW_RESULT_SCHEMA
        )

        validated = validate_hierarchical_episode_review_result(
            parent,
            [first, second],
            {*ALL_REFS, *turn_refs},
            allowed_turn_refs=turn_refs,
            expected_child_result_hashes=[
                canonical_result_hash(first),
                canonical_result_hash(second),
            ],
            expected_reviewer_slot="primary",
        )

        self.assertEqual(20, len(validated["high_impact_turns"]))
        self.assertEqual(
            40,
            validated["reduction_commitment"]["source_item_counts"][
                "high_impact_turns"
            ],
        )

    def test_adjudication_compact_codes_fit_two_maximum_evidence_sets(self) -> None:
        evidence_refs = [
            ref("evidence", f"adjudication-{index}") for index in range(256)
        ]
        primary = episode_review()
        primary["evidence_refs"] = evidence_refs[:128]
        secondary = episode_review(reviewer_slot="secondary")
        secondary["evidence_refs"] = evidence_refs[128:]
        adjudication = {
            "schema": ADJUDICATION_RESULT_SCHEMA,
            "episode_ref": EPISODE,
            "episode_revision_ref": REVISION_A,
            "resolution": "primary_supported",
            **{
                field: copy.deepcopy(primary[field])
                for field in (
                    "events",
                    "findings",
                    "strengths",
                    "risk_flags",
                    "high_impact_turns",
                    "evidence_refs",
                    "confidence",
                )
            },
            "candidate_result_hashes": [
                canonical_result_hash(primary),
                canonical_result_hash(secondary),
            ],
        }
        adjudication["candidate_item_decisions"] = adjudication_item_decisions(
            [primary, secondary], adjudication
        )

        validated = validate_adjudication_result(
            adjudication,
            {*ALL_REFS, *evidence_refs},
            candidate_results=[primary, secondary],
        )

        self.assertEqual(12, len(validated["candidate_item_decisions"]))
        self.assertLess(
            len(json.dumps(validated, separators=(",", ":")).encode("utf-8")),
            result_validation_module.MAX_RESULT_BYTES,
        )

    def test_adjudication_cannot_invent_structured_findings(self) -> None:
        primary = episode_review(findings=[signal("verification_gap")])
        secondary = episode_review(
            reviewer_slot="secondary",
            findings=[signal("verification_gap")],
        )
        adjudication = {
            "schema": ADJUDICATION_RESULT_SCHEMA,
            "episode_ref": EPISODE,
            "episode_revision_ref": REVISION_A,
            "resolution": "merged_supported",
            "events": [signal("verification_completed")],
            "findings": [signal("over_exploration")],
            "strengths": [signal("complete_verification")],
            "risk_flags": [],
            "high_impact_turns": [],
            "evidence_refs": [EVIDENCE_A],
            "confidence": "high",
            "candidate_result_hashes": [
                canonical_result_hash(primary),
                canonical_result_hash(secondary),
            ],
        }
        adjudication["candidate_item_decisions"] = adjudication_item_decisions(
            [primary, secondary], adjudication
        )

        with self.assertRaisesRegex(ResultValidationError, "invented"):
            validate_adjudication_result(
                adjudication,
                ALL_REFS,
                candidate_results=[primary, secondary],
            )

    def test_adjudication_accounts_for_candidate_unique_items_and_provenance(
        self,
    ) -> None:
        primary = episode_review(findings=[signal("verification_gap")])
        secondary_rewrite = high_impact(TURN_B)
        secondary_rewrite["severity"] = "low"
        secondary = episode_review(
            reviewer_slot="secondary",
            findings=[
                {
                    **signal("prompt_ambiguity", EVIDENCE_B),
                    "severity": "low",
                }
            ],
            high_impact_turns=[secondary_rewrite],
        )
        secondary["strengths"] = [signal("clear_communication", EVIDENCE_B)]
        adjudication = {
            "schema": ADJUDICATION_RESULT_SCHEMA,
            "episode_ref": EPISODE,
            "episode_revision_ref": REVISION_A,
            "resolution": "primary_supported",
            **{
                field: copy.deepcopy(primary[field])
                for field in (
                    "events",
                    "findings",
                    "strengths",
                    "risk_flags",
                    "high_impact_turns",
                    "evidence_refs",
                    "confidence",
                )
            },
            "candidate_result_hashes": [
                canonical_result_hash(primary),
                canonical_result_hash(secondary),
            ],
        }
        adjudication["candidate_item_decisions"] = adjudication_item_decisions(
            [primary, secondary], adjudication
        )

        validated = validate_adjudication_result(
            adjudication,
            ALL_REFS,
            allowed_turn_refs={TURN_A, TURN_B},
            candidate_results=[primary, secondary],
        )
        self.assertEqual(
            {"findings", "strengths", "high_impact_turns"},
            {
                row["field"]
                for row in validated["candidate_item_decisions"]
                if row["candidate_result_hash"] == canonical_result_hash(secondary)
                and "L" in row["decision_codes"]
            },
        )

        for field in ("findings", "strengths", "high_impact_turns"):
            with self.subTest(field=field):
                omitted = copy.deepcopy(adjudication)
                omitted["candidate_item_decisions"] = [
                    row
                    for row in omitted["candidate_item_decisions"]
                    if not (
                        row["candidate_result_hash"] == canonical_result_hash(secondary)
                        and row["field"] == field
                    )
                ]
                with self.assertRaisesRegex(
                    ResultValidationError, "one ordered decision-code row"
                ):
                    validate_adjudication_result(
                        omitted,
                        ALL_REFS,
                        allowed_turn_refs={TURN_A, TURN_B},
                        candidate_results=[primary, secondary],
                    )

        forged_provenance = copy.deepcopy(adjudication)
        forged_provenance["candidate_item_decisions"][-1]["reviewer_slot"] = "primary"
        with self.assertRaisesRegex(ResultValidationError, "provenance"):
            validate_adjudication_result(
                forged_provenance,
                ALL_REFS,
                allowed_turn_refs={TURN_A, TURN_B},
                candidate_results=[primary, secondary],
            )

        topic_input = {
            "adjudication_candidate_results": {REVISION_A: [primary, secondary]},
            "adjudication_required_episode_revision_refs": [REVISION_A],
            "episode_contexts": [
                {
                    "episode_ref": EPISODE,
                    "episode_revision_ref": REVISION_A,
                    "session_ref": SESSION_A,
                }
            ],
            "episode_reviews": [adjudication],
            "expected_episode_revision_refs": [REVISION_A],
            "schema": TOPIC_INPUT_SCHEMA,
            "topic_ref": TOPIC,
            "workstream_ref": WORKSTREAM_A,
        }
        downstream = validate_topic_input(
            topic_input,
            ALL_REFS,
            allowed_turn_refs={TURN_A, TURN_B},
        )
        self.assertEqual(
            secondary["high_impact_turns"],
            downstream["adjudication_candidate_results"][REVISION_A][1][
                "high_impact_turns"
            ],
        )
        self.assertEqual(
            adjudication["candidate_item_decisions"],
            downstream["episode_reviews"][0]["candidate_item_decisions"],
        )

    def test_topic_input_requires_exact_episode_revision_coverage(self) -> None:
        first = episode_review(revision_ref=REVISION_A)
        second = episode_review(revision_ref=REVISION_B)
        value = {
            "adjudication_candidate_results": {},
            "schema": TOPIC_INPUT_SCHEMA,
            "workstream_ref": WORKSTREAM_A,
            "topic_ref": TOPIC,
            "episode_contexts": [
                {
                    "episode_ref": EPISODE,
                    "episode_revision_ref": REVISION_A,
                    "session_ref": SESSION_A,
                },
                {
                    "episode_ref": EPISODE,
                    "episode_revision_ref": REVISION_B,
                    "session_ref": SESSION_A,
                },
            ],
            "model_configuration_ref": MODEL,
            "episode_reviews": [first, second],
            "expected_episode_revision_refs": [REVISION_A],
            "adjudication_required_episode_revision_refs": [],
        }

        with self.assertRaisesRegex(ResultValidationError, "exactly cover"):
            validate_topic_input(value, ALL_REFS)

    def test_topic_input_accepts_validated_redacted_reviews(self) -> None:
        value = {
            "adjudication_candidate_results": {},
            "schema": TOPIC_INPUT_SCHEMA,
            "workstream_ref": WORKSTREAM_A,
            "topic_ref": TOPIC,
            "episode_contexts": [
                {
                    "episode_ref": EPISODE,
                    "episode_revision_ref": REVISION_A,
                    "session_ref": SESSION_A,
                }
            ],
            "episode_reviews": [episode_review()],
            "expected_episode_revision_refs": [REVISION_A],
            "adjudication_required_episode_revision_refs": [],
        }

        result = validate_topic_input(value, ALL_REFS)

        self.assertEqual(result["expected_episode_revision_refs"], [REVISION_A])

    def test_topic_result_supports_existing_topic_ref_input(self) -> None:
        topic_input = validate_topic_input(
            {
                "adjudication_candidate_results": {},
                "schema": TOPIC_INPUT_SCHEMA,
                "workstream_ref": WORKSTREAM_A,
                "topic_ref": TOPIC,
                "episode_contexts": [
                    {
                        "episode_ref": EPISODE,
                        "episode_revision_ref": REVISION_A,
                        "session_ref": SESSION_A,
                    }
                ],
                "episode_reviews": [episode_review()],
                "expected_episode_revision_refs": [REVISION_A],
                "adjudication_required_episode_revision_refs": [],
            },
            ALL_REFS,
        )

        result = build_topic_result(topic_input, topic_ref=TOPIC)
        validated = validate_topic_result(
            result,
            topic_input,
            ALL_REFS,
            expected_topic_ref=TOPIC,
        )

        self.assertEqual(TOPIC, validated["topic_ref"])
        self.assertNotIn("topic_candidate_ref", validated)
        with self.assertRaises(ResultValidationError):
            build_topic_result(topic_input, topic_ref=ref("topic", "other"))

    def test_topic_result_is_real_cross_session_aggregation_consumed_by_synthesis(
        self,
    ) -> None:
        secondary = episode_review(
            episode_ref=EPISODE_B,
            revision_ref=REVISION_B,
            reviewer_slot="secondary",
            findings=[
                {
                    "kind": "production_risk",
                    "severity": "high",
                    "evidence_refs": [EVIDENCE_A],
                    "confidence": "low",
                }
            ],
        )
        resolved = episode_review(
            episode_ref=EPISODE_B,
            revision_ref=REVISION_B,
            findings=copy.deepcopy(secondary["findings"]),
        )
        topic_input = {
            "adjudication_candidate_results": {},
            "schema": TOPIC_INPUT_SCHEMA,
            "workstream_ref": WORKSTREAM_A,
            "topic_candidate_ref": TOPIC_CANDIDATE,
            "episode_contexts": [
                {
                    "episode_ref": EPISODE,
                    "episode_revision_ref": REVISION_A,
                    "session_ref": SESSION_A,
                },
                {
                    "episode_ref": EPISODE_B,
                    "episode_revision_ref": REVISION_B,
                    "session_ref": SESSION_B,
                },
            ],
            "episode_reviews": [
                episode_review(
                    episode_ref=EPISODE,
                    revision_ref=REVISION_A,
                    findings=[
                        {
                            "kind": "production_risk",
                            "severity": "medium",
                            "evidence_refs": [EVIDENCE_B],
                            "confidence": "medium",
                        }
                    ],
                ),
                resolved,
            ],
            "expected_episode_revision_refs": [REVISION_A, REVISION_B],
            "adjudication_required_episode_revision_refs": [],
        }
        validated_input = validate_topic_input(topic_input, ALL_REFS)
        result = build_topic_result(validated_input, topic_ref=TOPIC)
        validated = validate_topic_result(
            result,
            validated_input,
            ALL_REFS,
            expected_topic_ref=TOPIC,
        )

        self.assertEqual(TOPIC_RESULT_SCHEMA, validated["schema"])
        self.assertTrue(validated["cross_session"])
        self.assertEqual([SESSION_A, SESSION_B], validated["session_refs"])
        self.assertEqual([REVISION_A, REVISION_B], validated["episode_revision_refs"])
        self.assertEqual(2, len(validated["review_result_hashes"]))
        with self.assertRaises(ResultValidationError):
            validate_topic_result(
                validated_input,
                validated_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
            )
        invented = dict(result)
        invented["cross_session"] = False
        with self.assertRaisesRegex(ResultValidationError, "exactly preserve"):
            validate_topic_result(
                invented,
                validated_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
            )

        synthesis = synthesis_result()
        synthesis["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            [validated]
        )
        synthesis["signal_commitments"] = build_synthesis_signal_commitments(
            [validated]
        )
        synthesis.update(build_synthesis_signal_exemplars([validated]))
        synthesis["evidence_refs"] = list(validated["episode_refs"])
        validated_synthesis = validate_synthesis_result(
            synthesis,
            ALL_REFS,
            independent_review_results=[secondary],
            topic_results=[validated],
        )
        self.assertEqual(
            {(EVIDENCE_A,), (EVIDENCE_B,)},
            {
                tuple(finding["evidence_refs"])
                for finding in validated_synthesis["findings"]
            },
        )
        substituted = copy.deepcopy(synthesis)
        substituted["findings"][0]["confidence"] = "high"
        with self.assertRaisesRegex(
            ResultValidationError,
            "deterministic bounded topic-signal exemplars",
        ):
            validate_synthesis_result(
                substituted,
                ALL_REFS,
                independent_review_results=[secondary],
                topic_results=[validated],
            )
        over_attributed = copy.deepcopy(synthesis)
        original_refs = over_attributed["findings"][0]["evidence_refs"]
        extra_ref = EVIDENCE_A if original_refs == [EVIDENCE_B] else EVIDENCE_B
        original_refs.append(extra_ref)
        with self.assertRaisesRegex(
            ResultValidationError,
            "deterministic bounded topic-signal exemplars",
        ):
            validate_synthesis_result(
                over_attributed,
                ALL_REFS,
                independent_review_results=[secondary],
                topic_results=[validated],
            )
        synthesis["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            ()
        )
        with self.assertRaisesRegex(ResultValidationError, "every validated topic"):
            validate_synthesis_result(
                synthesis,
                ALL_REFS,
                topic_results=[validated],
            )

    def test_topic_reducer_accepts_supported_semantics_and_rejects_bad_lineage(
        self,
    ) -> None:
        topic_input = validate_topic_input(
            {
                "adjudication_candidate_results": {},
                "adjudication_required_episode_revision_refs": [],
                "episode_contexts": [
                    {
                        "episode_ref": EPISODE,
                        "episode_revision_ref": REVISION_A,
                        "session_ref": SESSION_A,
                    },
                    {
                        "episode_ref": EPISODE_B,
                        "episode_revision_ref": REVISION_B,
                        "session_ref": SESSION_B,
                    },
                ],
                "episode_reviews": [
                    episode_review(),
                    episode_review(
                        episode_ref=EPISODE_B,
                        revision_ref=REVISION_B,
                    ),
                ],
                "expected_episode_revision_refs": [REVISION_A, REVISION_B],
                "schema": TOPIC_INPUT_SCHEMA,
                "topic_candidate_ref": TOPIC_CANDIDATE,
                "workstream_ref": WORKSTREAM_A,
            },
            ALL_REFS,
        )
        result = build_topic_result(topic_input, topic_ref=TOPIC)
        result.update(
            {
                "guidance_candidates": [
                    {
                        "confidence": "high",
                        "episode_lineage": [
                            {"episode_ref": EPISODE, "session_ref": SESSION_A},
                            {"episode_ref": EPISODE_B, "session_ref": SESSION_B},
                        ],
                        "evidence_refs": [EVIDENCE_A],
                        "kind": "verification",
                    }
                ],
                "open_work": [
                    {
                        "confidence": "medium",
                        "evidence_refs": [EVIDENCE_B],
                        "kind": "rerun_verification",
                    }
                ],
                "prompt_rewrites": [high_impact()],
                "recurrences": [
                    {
                        "confidence": "high",
                        "episode_revision_refs": [REVISION_A, REVISION_B],
                        "evidence_refs": [EVIDENCE_A],
                        "kind": "verification_completed",
                        "session_refs": [SESSION_A, SESSION_B],
                        "signal_type": "event",
                    }
                ],
                "skill_candidates": [
                    {
                        "confidence": "medium",
                        "episode_lineage": [
                            {"episode_ref": EPISODE, "session_ref": SESSION_A}
                        ],
                        "evidence_refs": [EVIDENCE_A],
                        "kind": "workflow_hygiene",
                    }
                ],
            }
        )

        validated = validate_topic_result(
            result,
            topic_input,
            ALL_REFS,
            expected_topic_ref=TOPIC,
            allowed_turn_refs={TURN_A},
        )
        self.assertEqual(result, validated)

        wrong_kind = copy.deepcopy(result)
        wrong_kind["recurrences"][0]["kind"] = "production_risk"
        with self.assertRaisesRegex(ResultValidationError, "must be one of"):
            validate_topic_result(
                wrong_kind,
                topic_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
                allowed_turn_refs={TURN_A},
            )

        wrong_sessions = copy.deepcopy(result)
        wrong_sessions["recurrences"][0]["session_refs"] = [SESSION_A]
        with self.assertRaisesRegex(ResultValidationError, "sessions owning"):
            validate_topic_result(
                wrong_sessions,
                topic_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
                allowed_turn_refs={TURN_A},
            )

        unsupported_signal = copy.deepcopy(result)
        unsupported_signal["recurrences"][0]["kind"] = "task_completion"
        with self.assertRaisesRegex(ResultValidationError, "support the recurrence"):
            validate_topic_result(
                unsupported_signal,
                topic_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
                allowed_turn_refs={TURN_A},
            )

        unsupported_evidence = copy.deepcopy(result)
        unsupported_evidence["recurrences"][0]["evidence_refs"] = [EVIDENCE_B]
        with self.assertRaisesRegex(ResultValidationError, "support the recurrence"):
            validate_topic_result(
                unsupported_evidence,
                topic_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
                allowed_turn_refs={TURN_A},
            )

        bad_lineage = copy.deepcopy(result)
        bad_lineage["skill_candidates"][0]["episode_lineage"] = [
            {"episode_ref": EPISODE_B, "session_ref": SESSION_A}
        ]
        with self.assertRaisesRegex(ResultValidationError, "outside the topic lineage"):
            validate_topic_result(
                bad_lineage,
                topic_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
                allowed_turn_refs={TURN_A},
            )

        duplicate = copy.deepcopy(result)
        duplicate["open_work"].append(copy.deepcopy(duplicate["open_work"][0]))
        with self.assertRaisesRegex(ResultValidationError, "duplicate semantic"):
            validate_topic_result(
                duplicate,
                topic_input,
                ALL_REFS,
                expected_topic_ref=TOPIC,
                allowed_turn_refs={TURN_A},
            )

    def test_hierarchical_topic_reducer_commits_omitted_child_semantics(self) -> None:
        topic_input = validate_topic_input(
            {
                "adjudication_candidate_results": {},
                "adjudication_required_episode_revision_refs": [],
                "episode_contexts": [
                    {
                        "episode_ref": EPISODE,
                        "episode_revision_ref": REVISION_A,
                        "session_ref": SESSION_A,
                    }
                ],
                "episode_reviews": [episode_review()],
                "expected_episode_revision_refs": [REVISION_A],
                "schema": TOPIC_INPUT_SCHEMA,
                "topic_candidate_ref": TOPIC_CANDIDATE,
                "workstream_ref": WORKSTREAM_A,
            },
            ALL_REFS,
        )
        child = build_topic_result(topic_input, topic_ref=TOPIC)
        child["open_work"] = [
            {
                "confidence": "high",
                "evidence_refs": [EVIDENCE_A],
                "kind": "repair_gap",
            }
        ]
        child = validate_topic_result(
            child,
            topic_input,
            ALL_REFS,
            expected_topic_ref=TOPIC,
        )
        parent = build_hierarchical_topic_result(
            [child],
            topic_candidate_ref=TOPIC_CANDIDATE,
            topic_ref=TOPIC,
            workstream_ref=WORKSTREAM_A,
        )
        validated = validate_hierarchical_topic_result(
            parent,
            [child],
            ALL_REFS,
            expected_topic_candidate_ref=TOPIC_CANDIDATE,
            expected_topic_ref=TOPIC,
            expected_workstream_ref=WORKSTREAM_A,
        )
        self.assertEqual(parent, validated)

        dropped = copy.deepcopy(parent)
        dropped["open_work"] = []
        compacted = validate_hierarchical_topic_result(
            dropped,
            [child],
            ALL_REFS,
            expected_topic_candidate_ref=TOPIC_CANDIDATE,
            expected_topic_ref=TOPIC,
            expected_workstream_ref=WORKSTREAM_A,
        )
        self.assertEqual(
            1,
            compacted["reduction_commitment"]["source_item_counts"]["open_work"],
        )

        empty_lineage = copy.deepcopy(dropped)
        for field in (
            "episode_lineage",
            "episode_revision_lineage",
            "episode_refs",
            "episode_revision_refs",
            "review_result_hashes",
            "session_refs",
        ):
            empty_lineage[field] = []
        with self.assertRaisesRegex(ResultValidationError, "at least"):
            validate_hierarchical_topic_result(
                empty_lineage,
                [child],
                ALL_REFS,
                expected_topic_candidate_ref=TOPIC_CANDIDATE,
                expected_topic_ref=TOPIC,
                expected_workstream_ref=WORKSTREAM_A,
            )

        invented = copy.deepcopy(dropped)
        invented["open_work"] = [
            {
                "confidence": "high",
                "evidence_refs": [EVIDENCE_A],
                "kind": "update_guidance",
            }
        ]
        with self.assertRaisesRegex(ResultValidationError, "invented or altered"):
            validate_hierarchical_topic_result(
                invented,
                [child],
                ALL_REFS,
                expected_topic_candidate_ref=TOPIC_CANDIDATE,
                expected_topic_ref=TOPIC,
                expected_workstream_ref=WORKSTREAM_A,
            )

        duplicated_signal = copy.deepcopy(dropped)
        duplicated_signal["events"].append(
            copy.deepcopy(duplicated_signal["events"][0])
        )
        with self.assertRaisesRegex(ResultValidationError, "invented or altered"):
            validate_hierarchical_topic_result(
                duplicated_signal,
                [child],
                ALL_REFS,
                expected_topic_candidate_ref=TOPIC_CANDIDATE,
                expected_topic_ref=TOPIC,
                expected_workstream_ref=WORKSTREAM_A,
            )

    def test_hierarchical_topic_reducer_compacts_two_maximum_semantic_sets(
        self,
    ) -> None:
        topic_input = validate_topic_input(
            {
                "adjudication_candidate_results": {},
                "adjudication_required_episode_revision_refs": [],
                "episode_contexts": [
                    {
                        "episode_ref": EPISODE,
                        "episode_revision_ref": REVISION_A,
                        "session_ref": SESSION_A,
                    }
                ],
                "episode_reviews": [episode_review()],
                "expected_episode_revision_refs": [REVISION_A],
                "schema": TOPIC_INPUT_SCHEMA,
                "topic_candidate_ref": TOPIC_CANDIDATE,
                "workstream_ref": WORKSTREAM_A,
            },
            ALL_REFS,
        )
        evidence_refs = [
            ref("evidence", f"topic-open-work-{index}") for index in range(128)
        ]
        allowed_refs = ALL_REFS | set(evidence_refs)
        children = []
        for child_index in range(2):
            child = build_topic_result(topic_input, topic_ref=TOPIC)
            child["open_work"] = [
                {
                    "confidence": "high",
                    "evidence_refs": [evidence_refs[index]],
                    "kind": "repair_gap",
                }
                for index in range(child_index * 64, (child_index + 1) * 64)
            ]
            children.append(
                validate_topic_result(
                    child,
                    topic_input,
                    allowed_refs,
                    expected_topic_ref=TOPIC,
                )
            )

        exhaustive = build_hierarchical_topic_result(
            children,
            topic_candidate_ref=TOPIC_CANDIDATE,
            topic_ref=TOPIC,
            workstream_ref=WORKSTREAM_A,
        )
        with self.assertRaisesRegex(ResultValidationError, "at most 64"):
            validate_hierarchical_topic_result(
                exhaustive,
                children,
                allowed_refs,
                expected_topic_candidate_ref=TOPIC_CANDIDATE,
                expected_topic_ref=TOPIC,
                expected_workstream_ref=WORKSTREAM_A,
            )

        compacted = copy.deepcopy(exhaustive)
        compacted["open_work"] = copy.deepcopy(children[0]["open_work"])
        validated = validate_hierarchical_topic_result(
            compacted,
            children,
            allowed_refs,
            expected_topic_candidate_ref=TOPIC_CANDIDATE,
            expected_topic_ref=TOPIC,
            expected_workstream_ref=WORKSTREAM_A,
        )
        self.assertEqual(64, len(validated["open_work"]))
        self.assertEqual(
            128,
            validated["reduction_commitment"]["source_item_counts"]["open_work"],
        )

    def test_synthesis_requires_all_ten_closed_questions(self) -> None:
        value = synthesis_result()
        value["question_answers"].pop()

        with self.assertRaisesRegex(
            ResultValidationError, "ten retrospective questions"
        ):
            validate_synthesis_result(value, ALL_REFS)

    def test_hierarchical_synthesis_separates_source_and_output_refs(self) -> None:
        topic_result = {
            "episode_lineage": [{"episode_ref": EPISODE, "session_ref": SESSION_A}],
            "episode_refs": [EPISODE],
            "events": [],
            "findings": [],
            "schema": TOPIC_RESULT_SCHEMA,
            "session_refs": [SESSION_A],
            "strengths": [],
        }
        value = synthesis_result()
        value["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            [topic_result]
        )
        value["signal_commitments"] = build_synthesis_signal_commitments([topic_result])

        with self.assertRaises(ResultValidationError):
            validate_synthesis_result(value, set(), topic_results=[topic_result])
        validated = validate_synthesis_result(
            value,
            set(),
            source_allowed_refs={EPISODE, SESSION_A},
            topic_results=[topic_result],
        )

        self.assertEqual(value, validated)

    def test_synthesis_separates_authenticated_source_turn_refs_from_output_refs(
        self,
    ) -> None:
        secondary = episode_review(
            reviewer_slot="secondary",
            high_impact_turns=[high_impact(TURN_A)],
        )
        value = synthesis_result()

        with self.assertRaisesRegex(
            ResultValidationError,
            "reference is not in the job allow-list",
        ):
            validate_synthesis_result(
                value,
                ALL_REFS,
                allowed_turn_refs={TURN_B},
                independent_review_results=[secondary],
            )
        validated = validate_synthesis_result(
            value,
            ALL_REFS,
            allowed_turn_refs=set(),
            independent_review_results=[secondary],
            source_allowed_turn_refs={TURN_A},
        )

        self.assertEqual(value, validated)

    def test_synthesis_commits_129_distinct_topic_roots_and_signals(self) -> None:
        topic_results = []
        allowed_refs = set(ALL_REFS)
        for index in range(129):
            episode_ref = ref("episode", f"many-signals-episode-{index}")
            evidence_ref = ref("evidence", f"many-signals-evidence-{index}")
            session_ref = ref("session", f"many-signals-session-{index}")
            allowed_refs.update({episode_ref, evidence_ref, session_ref})
            topic_results.append(
                {
                    "episode_lineage": [
                        {
                            "episode_ref": episode_ref,
                            "session_ref": session_ref,
                        }
                    ],
                    "episode_refs": [episode_ref],
                    "events": [
                        {
                            "confidence": "high",
                            "evidence_refs": [evidence_ref],
                            "kind": "verification_completed",
                        }
                    ],
                    "findings": [],
                    "schema": TOPIC_RESULT_SCHEMA,
                    "strengths": [],
                }
            )
        synthesis = synthesis_result()
        synthesis["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            topic_results
        )
        synthesis["signal_commitments"] = build_synthesis_signal_commitments(
            topic_results
        )
        synthesis.update(build_synthesis_signal_exemplars(topic_results))

        validated = validate_synthesis_result(
            synthesis,
            allowed_refs,
            topic_results=topic_results,
        )

        self.assertEqual(64, len(validated["events"]))
        self.assertEqual(
            129,
            validated["signal_commitments"]["events"]["canonical_count"],
        )
        self.assertEqual(
            129,
            validated["topic_result_commitment"]["canonical_count"],
        )
        wrong_topic_count_type = copy.deepcopy(synthesis)
        wrong_topic_count_type["topic_result_commitment"]["canonical_count"] = 129.0
        with self.assertRaisesRegex(ResultValidationError, "every validated topic"):
            validate_synthesis_result(
                wrong_topic_count_type,
                allowed_refs,
                topic_results=topic_results,
            )
        wrong_signal_count_type = copy.deepcopy(synthesis)
        wrong_signal_count_type["signal_commitments"]["events"]["canonical_count"] = (
            129.0
        )
        with self.assertRaisesRegex(ResultValidationError, "canonical topic signal"):
            validate_synthesis_result(
                wrong_signal_count_type,
                allowed_refs,
                topic_results=topic_results,
            )
        tampered = copy.deepcopy(synthesis)
        tampered["signal_commitments"]["events"]["canonical_count"] = 64
        with self.assertRaisesRegex(ResultValidationError, "every canonical topic"):
            validate_synthesis_result(
                tampered,
                allowed_refs,
                topic_results=topic_results,
            )

    def test_synthesis_commits_all_rewrites_beyond_the_exemplar_bound(self) -> None:
        turn_refs = [ref("turn", f"synthesis-rewrite-{index}") for index in range(21)]
        source_rewrites = [
            {
                **high_impact(turn_ref),
                "evidence_refs": [EPISODE],
            }
            for turn_ref in turn_refs
        ]
        value = synthesis_result()
        value["prompt_rewrite_commitment"] = build_synthesis_prompt_rewrite_commitment(
            source_rewrites
        )
        value["prompt_rewrites"] = build_synthesis_prompt_rewrite_exemplars(
            source_rewrites
        )

        validated = validate_synthesis_result(
            value,
            {EPISODE},
            allowed_turn_refs=turn_refs,
            source_prompt_rewrites=source_rewrites,
        )

        self.assertEqual(20, len(validated["prompt_rewrites"]))
        self.assertEqual(
            21,
            validated["prompt_rewrite_commitment"]["canonical_count"],
        )
        omitted = copy.deepcopy(value)
        omitted["prompt_rewrites"].pop()
        with self.assertRaisesRegex(ResultValidationError, "bounded source-rewrite"):
            validate_synthesis_result(
                omitted,
                {EPISODE},
                allowed_turn_refs=turn_refs,
                source_prompt_rewrites=source_rewrites,
            )
        incomplete = copy.deepcopy(value)
        incomplete["prompt_rewrite_commitment"] = (
            build_synthesis_prompt_rewrite_commitment(source_rewrites[:20])
        )
        with self.assertRaisesRegex(ResultValidationError, "every source prompt"):
            validate_synthesis_result(
                incomplete,
                {EPISODE},
                allowed_turn_refs=turn_refs,
                source_prompt_rewrites=source_rewrites,
            )

    def test_synthesis_rejects_under_supported_durable_guidance(self) -> None:
        topic_result = {
            "episode_lineage": [{"episode_ref": EPISODE, "session_ref": SESSION_A}],
            "episode_refs": [EPISODE],
            "events": [],
            "findings": [],
            "schema": TOPIC_RESULT_SCHEMA,
            "session_refs": [SESSION_A],
            "strengths": [],
        }
        value = synthesis_result()
        value["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            [topic_result]
        )
        value["signal_commitments"] = build_synthesis_signal_commitments([topic_result])
        value["guidance_candidates"] = [
            {
                "kind": "verification",
                "episode_lineage": [{"episode_ref": EPISODE, "session_ref": SESSION_A}],
                "confidence": "high",
                "exception": "none",
            }
        ]

        with self.assertRaisesRegex(ResultValidationError, "three episode lineages"):
            validate_synthesis_result(value, ALL_REFS, topic_results=[topic_result])

    def test_durable_candidate_requires_exact_episode_session_lineage(self) -> None:
        episode_three = ref("episode", "candidate-three")
        session_three = ref("session", "candidate-unrelated")
        lineage = [
            {"episode_ref": EPISODE, "session_ref": SESSION_A},
            {"episode_ref": EPISODE_B, "session_ref": SESSION_A},
            {"episode_ref": episode_three, "session_ref": SESSION_B},
        ]
        topic_result = {
            "episode_lineage": lineage,
            "episode_refs": [EPISODE, EPISODE_B, episode_three],
            "events": [],
            "findings": [],
            "schema": TOPIC_RESULT_SCHEMA,
            "session_refs": [SESSION_A, SESSION_B],
            "strengths": [],
        }
        allowed_refs = set(ALL_REFS) | {episode_three, session_three}
        value = synthesis_result()
        value["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            [topic_result]
        )
        value["signal_commitments"] = build_synthesis_signal_commitments([topic_result])
        value["guidance_candidates"] = [
            {
                "confidence": "high",
                "episode_lineage": copy.deepcopy(lineage),
                "exception": "none",
                "kind": "verification",
            }
        ]
        validate_synthesis_result(
            value,
            allowed_refs,
            topic_results=[topic_result],
        )

        mismatched = copy.deepcopy(value)
        mismatched["guidance_candidates"][0]["episode_lineage"][2]["session_ref"] = (
            session_three
        )
        with self.assertRaisesRegex(ResultValidationError, "does not match"):
            validate_synthesis_result(
                mismatched,
                allowed_refs,
                topic_results=[topic_result],
            )

        unrelated = copy.deepcopy(value)
        unrelated["guidance_candidates"][0]["episode_lineage"][2]["episode_ref"] = ref(
            "episode", "not-in-topic"
        )
        allowed_refs.add(
            unrelated["guidance_candidates"][0]["episode_lineage"][2]["episode_ref"]
        )
        with self.assertRaisesRegex(ResultValidationError, "does not match"):
            validate_synthesis_result(
                unrelated,
                allowed_refs,
                topic_results=[topic_result],
            )


class EpisodeConstructionTests(unittest.TestCase):
    def test_72_hour_gap_is_candidate_not_boundary(self) -> None:
        rows = [
            turn(
                TURN_A,
                timestamp="2026-07-01T00:00:00Z",
                sequence=0,
                archive_state="active",
                mtime="2026-07-01T00:01:00Z",
            ),
            turn(
                TURN_B,
                timestamp="2026-07-05T00:00:00Z",
                sequence=1,
                archive_state="archived",
                mtime="2026-07-14T23:59:00Z",
                goal_change="continues",
            ),
        ]

        episodes = construct_episodes(rows)

        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["turn_refs"], [TURN_A, TURN_B])
        self.assertEqual(
            episodes[0]["internal_boundary_candidates"][0]["candidate_reasons"],
            ["elapsed_72h_candidate"],
        )
        self.assertFalse(
            episodes[0]["internal_boundary_candidates"][0]["accepted_boundary"]
        )

    def test_goal_change_splits_inside_one_thread(self) -> None:
        rows = [
            turn(TURN_A, timestamp="2026-07-01T00:00:00Z", sequence=0),
            turn(
                TURN_B,
                timestamp="2026-07-01T01:00:00Z",
                sequence=1,
                goal_ref=GOAL_B,
                goal_change="new_goal",
            ),
        ]

        episodes = construct_episodes(rows)

        self.assertEqual(
            [episode["turn_refs"] for episode in episodes], [[TURN_A], [TURN_B]]
        )
        self.assertEqual(
            episodes[1]["boundary_before"]["accepted_reasons"], ["goal_change"]
        )

    def test_contradictory_goal_continuity_becomes_a_segmentation_failure(self) -> None:
        rows = [
            turn(TURN_A, timestamp="2026-07-01T00:00:00Z", sequence=0),
            turn(
                TURN_B,
                timestamp="2026-07-01T01:00:00Z",
                sequence=1,
                goal_ref=GOAL_B,
                goal_change="continues",
            ),
        ]

        with self.assertRaisesRegex(ResultValidationError, "conflicts"):
            construct_episodes(rows)

    def test_same_goal_in_different_threads_remains_distinct(self) -> None:
        rows = [
            turn(TURN_A, timestamp="2026-07-01T00:00:00Z", sequence=0),
            turn(
                TURN_B,
                session_ref=SESSION_B,
                timestamp="2026-07-01T01:00:00Z",
                sequence=0,
            ),
        ]

        episodes = construct_episodes(rows)

        self.assertEqual(len(episodes), 2)
        self.assertEqual(
            {episode["session_ref"] for episode in episodes}, {SESSION_A, SESSION_B}
        )

    def test_archive_and_mtime_changes_never_create_candidates(self) -> None:
        rows = [
            turn(
                TURN_A,
                timestamp="2026-07-01T00:00:00Z",
                sequence=0,
                archive_state="active",
                archive_time="2026-07-02T00:00:00Z",
                mtime="2026-07-03T00:00:00Z",
            ),
            turn(
                TURN_B,
                timestamp="2026-07-01T01:00:00Z",
                sequence=1,
                archive_state="archived",
                archive_time="2026-07-14T00:00:00Z",
                mtime="2026-07-14T00:00:00Z",
            ),
        ]

        episodes = construct_episodes(rows)

        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["internal_boundary_candidates"], [])

    def test_meaningfulness_gap_cannot_be_review_not_required(self) -> None:
        rows = [
            turn(
                TURN_A,
                timestamp="2026-07-01T00:00:00Z",
                meaningfulness="context_only",
            ),
            turn(
                TURN_B,
                timestamp="2026-07-01T01:00:00Z",
                meaningfulness="meaningfulness_gap",
                sequence=1,
            ),
        ]

        result = derive_episode_meaningfulness(rows)

        self.assertEqual(result["disposition"], "meaningfulness_gap")
        self.assertEqual(result["semantic_coverage"], "gap")
        self.assertNotEqual(result["disposition"], "review_not_required")


class EpisodeLineageAndPlanningTests(unittest.TestCase):
    identity_key = IdentityKey(b"k" * 32)

    def episode(self, turn_refs: list[str]) -> dict:
        return {
            "session_ref": SESSION_A,
            "turn_refs": turn_refs,
            "goal_refs": [GOAL_A],
            "workstream_refs": [WORKSTREAM_A],
            "boundary_before": None,
            "internal_boundary_candidates": [],
            "meaningfulness": {
                "disposition": "meaningful",
                "semantic_coverage": "complete",
                "review_required": True,
                "meaningful_turn_refs": turn_refs,
                "context_only_turn_refs": [],
                "gap_turn_refs": [],
            },
            "risk_flags": [],
            "extraction_confidence": "high",
            "segmentation_confidence": "high",
        }

    def test_earlier_backfill_preserves_anchor_and_appends_revision(self) -> None:
        initial = create_episode_revision(
            self.episode([TURN_B]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        backfilled = create_episode_revision(
            self.episode([TURN_A, TURN_B]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
            previous_revision=initial,
        )

        self.assertEqual(backfilled["episode_ref"], initial["episode_ref"])
        self.assertNotEqual(
            backfilled["episode_revision_ref"], initial["episode_revision_ref"]
        )
        self.assertEqual(
            backfilled["supersedes_episode_revision_ref"],
            initial["episode_revision_ref"],
        )
        self.assertEqual(backfilled["lineage_kind"], "extension")

    def test_noop_revision_is_idempotent(self) -> None:
        initial = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        replay = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
            previous_revision=initial,
        )

        self.assertEqual(replay, initial)

    def test_review_planning_verifies_closed_revision_before_using_decisions(
        self,
    ) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        opened = {**revision, "unexpected_risk_override": True}
        with self.assertRaisesRegex(ResultValidationError, "unknown fields"):
            plan_episode_review_jobs(opened, identity_key=self.identity_key)

        tampered_revisions = {
            "risk": {**revision, "risk_flags": ["privacy"]},
            "meaningfulness": {
                **revision,
                "meaningfulness": {
                    "disposition": "review_not_required",
                    "semantic_coverage": "complete",
                    "review_required": False,
                    "meaningful_turn_refs": [],
                    "context_only_turn_refs": [TURN_A],
                    "gap_turn_refs": [],
                },
            },
            "confidence": {**revision, "extraction_confidence": "low"},
        }
        for field, tampered in tampered_revisions.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(ResultValidationError, "does not commit"):
                    plan_episode_review_jobs(tampered, identity_key=self.identity_key)

        with self.assertRaisesRegex(ResultValidationError, "identity key"):
            plan_episode_review_jobs(
                revision,
                identity_key=IdentityKey(b"z" * 32),
            )

    def test_revision_ref_binds_ordinal_and_lineage(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        tampered = {
            **revision,
            "revision_ordinal": 2,
            "lineage_kind": "extension",
            "supersedes_episode_revision_ref": REVISION_A,
        }

        with self.assertRaisesRegex(ResultValidationError, "does not commit"):
            create_episode_revision(
                self.episode([TURN_A, TURN_B]),
                identity_key=self.identity_key,
                previous_revision=tampered,
            )
        with self.assertRaisesRegex(ResultValidationError, "does not commit"):
            plan_episode_review_jobs(tampered, identity_key=self.identity_key)

    def test_ordinary_revision_cannot_remove_membership(self) -> None:
        initial = create_episode_revision(
            self.episode([TURN_A, TURN_B]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        with self.assertRaisesRegex(ResultValidationError, "cannot remove"):
            create_episode_revision(
                self.episode([TURN_B]),
                identity_key=self.identity_key,
                key_id=self.identity_key.key_id,
                previous_revision=initial,
            )

    def test_ordinary_revision_cannot_reorder_membership(self) -> None:
        initial = create_episode_revision(
            self.episode([TURN_A, TURN_B]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        with self.assertRaisesRegex(ResultValidationError, "cannot reorder"):
            create_episode_revision(
                self.episode([TURN_B, TURN_A, TURN_C]),
                identity_key=self.identity_key,
                key_id=self.identity_key.key_id,
                previous_revision=initial,
            )

    def test_correction_generation_is_order_independent_and_successor_is_new(
        self,
    ) -> None:
        generation_a = derive_episode_correction_generation(
            self.identity_key,
            [EPISODE, ref("episode", "t")],
            [[TURN_A], [TURN_B]],
            correction_ordinal=1,
        )
        generation_b = derive_episode_correction_generation(
            self.identity_key,
            [ref("episode", "t"), EPISODE],
            [[TURN_B], [TURN_A]],
            correction_ordinal=1,
        )
        successor = derive_corrected_episode_ref(
            self.identity_key,
            generation_a,
            [TURN_A],
        )

        self.assertEqual(generation_a, generation_b)
        self.assertNotEqual(successor, EPISODE)

    def test_risk_schedules_primary_and_independent_secondary_reviews(self) -> None:
        revision = create_episode_revision(
            {**self.episode([TURN_A]), "risk_flags": ["privacy"]},
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        plan = plan_episode_review_jobs(revision, identity_key=self.identity_key)

        self.assertTrue(plan["second_review_required"])
        self.assertEqual(
            [(job["kind"], job.get("reviewer_slot")) for job in plan["jobs"]],
            [
                (JobKind.EPISODE_REVIEWER.value, "primary"),
                (JobKind.INDEPENDENT_RISK_REVIEWER.value, "secondary"),
            ],
        )
        self.assertIn("privacy_risk", plan["second_review_reason_codes"])

    def test_low_risk_episode_schedules_only_primary_review(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            screening_results=[
                {
                    "turn_ref": TURN_A,
                    "decision": "not_high_impact",
                    "risk_flags": [],
                }
            ],
        )

        self.assertFalse(plan["second_review_required"])
        self.assertEqual(len(plan["jobs"]), 1)
        self.assertEqual(plan["jobs"][0]["reviewer_slot"], "primary")

    def test_screening_must_exactly_cover_every_episode_turn(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A, TURN_B]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            screening_results=[
                {
                    "turn_ref": TURN_A,
                    "decision": "not_high_impact",
                    "risk_flags": [],
                }
            ],
        )

        self.assertEqual("high_impact_screen_gap", plan["blocked_reason"])
        self.assertEqual([TURN_B], plan["high_impact_screen_gap_turn_refs"])
        self.assertEqual(
            [
                {
                    "kind": "high_impact_screen_gap",
                    "turn_ref": TURN_B,
                    "gap_reason": "missing_decision",
                }
            ],
            plan["screening_gaps"],
        )
        self.assertTrue(plan["second_review_required"])
        self.assertIn("high_impact_screen_gap", plan["second_review_reason_codes"])

    def test_failed_screening_is_an_explicit_gap_not_a_negative_result(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            screening_results={
                "schema": "agent_failure_v2",
                "failure_kind": "timeout",
            },
        )

        self.assertEqual("high_impact_screen_gap", plan["blocked_reason"])
        self.assertEqual([TURN_A], plan["high_impact_screen_gap_turn_refs"])
        self.assertEqual("screening_failure", plan["screening_gaps"][0]["gap_reason"])
        self.assertTrue(plan["second_review_required"])
        self.assertIn("high_impact_screen_gap", plan["second_review_reason_codes"])

    def test_primary_review_gap_is_typed_and_blocks_completion(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        primary = episode_review_gap(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            reviewer_slot="primary",
        )

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            screening_results=[
                {
                    "turn_ref": TURN_A,
                    "decision": "not_high_impact",
                    "risk_flags": [],
                }
            ],
            primary_review=primary,
        )

        self.assertFalse(plan["primary_review_completed"])
        self.assertEqual(plan["blocked_reason"], "primary_review_gap")
        self.assertEqual(plan["jobs"], [])
        self.assertEqual(
            plan["review_gaps"],
            [
                {
                    "kind": "episode_review_gap",
                    "reviewer_slot": "primary",
                    "gap_reason": "review_failure",
                    "attempt_ref": ATTEMPT_PRIMARY,
                }
            ],
        )

    def test_secondary_review_gap_is_typed_and_blocks_completion(self) -> None:
        revision = create_episode_revision(
            {**self.episode([TURN_A]), "risk_flags": ["privacy"]},
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        primary = episode_review(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
        )
        secondary = episode_review_gap(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            reviewer_slot="secondary",
            gap_reason="insufficient_support",
        )

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            screening_results=[
                {
                    "turn_ref": TURN_A,
                    "decision": "not_high_impact",
                    "risk_flags": [],
                }
            ],
            primary_review=primary,
            secondary_review=secondary,
        )

        self.assertTrue(plan["primary_review_completed"])
        self.assertFalse(plan["secondary_review_completed"])
        self.assertTrue(plan["second_review_required"])
        self.assertEqual(plan["blocked_reason"], "secondary_review_gap")
        self.assertEqual(plan["jobs"], [])
        self.assertEqual(plan["review_gaps"][0]["gap_reason"], "insufficient_support")

    def test_reviewer_escalation_forces_secondary_and_adjudication(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        primary = episode_review(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            high_impact_turns=[high_impact()],
        )
        secondary = episode_review(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            reviewer_slot="secondary",
            high_impact_turns=[high_impact()],
        )
        screens = [
            {"turn_ref": TURN_A, "decision": "not_high_impact", "risk_flags": []},
            {"turn_ref": TURN_A, "decision": "not_high_impact", "risk_flags": []},
        ]

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            screening_results=screens,
            primary_review=primary,
            secondary_review=secondary,
        )

        self.assertTrue(plan["second_review_required"])
        self.assertTrue(plan["adjudication_required"])
        self.assertEqual(plan["reviewer_escalation_turn_refs"], [TURN_A])
        self.assertEqual(plan["jobs"][0]["kind"], JobKind.ADJUDICATOR.value)

    def test_material_review_conflict_schedules_adjudication(self) -> None:
        revision = create_episode_revision(
            {**self.episode([TURN_A]), "risk_flags": ["privacy"]},
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        primary = episode_review(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            findings=[signal("verification_gap")],
            risks=["privacy"],
        )
        secondary = episode_review(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            reviewer_slot="secondary",
            findings=[signal("assumption_risk")],
            risks=["privacy"],
        )

        self.assertTrue(material_review_conflict(primary, secondary))
        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            primary_review=primary,
            secondary_review=secondary,
        )

        self.assertTrue(plan["adjudication_required"])
        self.assertIn("material_review_conflict", plan["adjudication_reason_codes"])

    def test_review_binding_to_another_episode_is_rejected(self) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        with self.assertRaisesRegex(ResultValidationError, "not bound"):
            plan_episode_review_jobs(
                revision,
                identity_key=self.identity_key,
                primary_review=episode_review(),
            )

    def test_primary_high_impact_failsafe_schedules_secondary_without_screen_signal(
        self,
    ) -> None:
        revision = create_episode_revision(
            self.episode([TURN_A]),
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )
        primary = episode_review(
            episode_ref=revision["episode_ref"],
            revision_ref=revision["episode_revision_ref"],
            high_impact_turns=[high_impact()],
        )

        plan = plan_episode_review_jobs(
            revision,
            identity_key=self.identity_key,
            primary_review=primary,
        )

        self.assertTrue(plan["second_review_required"])
        self.assertEqual(
            plan["jobs"][0]["kind"], JobKind.INDEPENDENT_RISK_REVIEWER.value
        )

    def test_context_only_episode_has_no_review_jobs(self) -> None:
        episode = self.episode([TURN_A])
        episode["meaningfulness"] = {
            "disposition": "review_not_required",
            "semantic_coverage": "complete",
            "review_required": False,
            "meaningful_turn_refs": [],
            "context_only_turn_refs": [TURN_A],
            "gap_turn_refs": [],
        }
        revision = create_episode_revision(
            episode,
            identity_key=self.identity_key,
            key_id=self.identity_key.key_id,
        )

        plan = plan_episode_review_jobs(revision, identity_key=self.identity_key)

        self.assertFalse(plan["review_required"])
        self.assertEqual(plan["jobs"], [])


if __name__ == "__main__":
    unittest.main()
