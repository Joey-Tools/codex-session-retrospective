from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from retrospective_v2 import privacy_locators  # noqa: E402
from retrospective_v2.episode_review import (  # noqa: E402
    construct_episodes,
    create_episode_revision,
)
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
    build_synthesis_signal_exemplars,
    build_synthesis_signal_commitments,
    build_synthesis_topic_result_commitment,
    canonical_result_hash,
    scan_for_leaks,
    validate_adjudication_result,
    validate_episode_review_result,
    validate_extractor_result,
    validate_synthesis_result,
    validate_topic_input,
)


def ref(kind: str, marker: str) -> str:
    digest = hashlib.sha256(f"{kind}:{marker}".encode("ascii")).hexdigest()
    return f"{kind}_ref_v2:{digest}"


SESSION = ref("session", "audit-session")
SESSION_TWO = ref("session", "audit-session-two")
TURN_A = ref("turn", "audit-a")
TURN_B = ref("turn", "audit-b")
SOURCE = ref("source_unit", "audit-source")
EVIDENCE_A = ref("evidence", "audit-evidence-a")
EVIDENCE_B = ref("evidence", "audit-evidence-b")
SPAN = ref("span_commitment", "audit-span")
GOAL = ref("goal", "audit-goal")
WORKSTREAM = ref("workstream", "audit-workstream")
EPISODE = ref("episode", "audit-episode")
EPISODE_TWO = ref("episode", "audit-episode-two")
EPISODE_THREE = ref("episode", "audit-episode-three")
REVISION = ref("episode_revision", "audit-revision")
TOPIC = ref("topic", "audit-topic")
MODEL = ref("model_configuration", "audit-model")
PRIMARY_ATTEMPT = ref("attempt", "audit-primary-attempt")
SECONDARY_ATTEMPT = ref("attempt", "audit-secondary-attempt")
PRIMARY_REVIEWER = ref("reviewer", "audit-primary-reviewer")
SECONDARY_REVIEWER = ref("reviewer", "audit-secondary-reviewer")

ALL_REFS = {
    SESSION,
    SESSION_TWO,
    TURN_A,
    TURN_B,
    SOURCE,
    EVIDENCE_A,
    EVIDENCE_B,
    SPAN,
    GOAL,
    WORKSTREAM,
    EPISODE,
    EPISODE_TWO,
    EPISODE_THREE,
    REVISION,
    TOPIC,
    MODEL,
}


def signal(
    kind: str = "verification_completed", *, severity: str | None = None
) -> dict:
    value = {"kind": kind, "evidence_refs": [EVIDENCE_A], "confidence": "high"}
    if severity is not None:
        value["severity"] = severity
    return value


def high_impact(*, severity: str = "high") -> dict:
    return {
        "turn_ref": TURN_A,
        "problem_statement": "The requested action had material safety impact.",
        "cause": "The intended safety boundary was not explicit.",
        "rewritten_prompt": "Inspect the state and preserve reversible options before acting.",
        "expected_effect": "The action remains bounded until intent is confirmed.",
        "evidence_refs": [EVIDENCE_A],
        "confidence": "high",
        "severity": severity,
    }


def adjudication_item_decisions(
    candidates: list[dict], adjudication_result: dict
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
            retained = {canonical(item) for item in adjudication_result[field]}
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


def extractor_result() -> dict:
    return {
        "schema": EXTRACTOR_RESULT_SCHEMA,
        "source_unit_ref": SOURCE,
        "turns": [
            {
                "turn_ref": TURN_A,
                "generalized_working_text": "A bounded verification completed.",
                "events": [signal()],
                "findings": [],
                "strengths": [],
                "risk_flags": [],
                "outcome": "completed",
                "confidence": "high",
                "evidence_refs": [EVIDENCE_A],
                "span_commitments": [SPAN],
                "goal_ref": GOAL,
                "workstream_ref": WORKSTREAM,
            }
        ],
    }


def review(
    slot: str,
    *,
    episode_ref: str = EPISODE,
    revision_ref: str = REVISION,
    attempt_ref: str | None = None,
    reviewer_ref: str | None = None,
    severity: str = "high",
    safety: bool = False,
) -> dict:
    primary = slot == "primary"
    return {
        "schema": EPISODE_REVIEW_RESULT_SCHEMA,
        "episode_ref": episode_ref,
        "episode_revision_ref": revision_ref,
        "disposition": "reviewed",
        "events": [signal(severity=severity)],
        "findings": [],
        "strengths": [],
        "risk_flags": ["safety"] if safety else [],
        "high_impact_turns": [high_impact(severity=severity)],
        "evidence_refs": [EVIDENCE_A],
        "confidence": "high",
        "reviewer_slot": slot,
        "attempt_ref": attempt_ref
        or (PRIMARY_ATTEMPT if primary else SECONDARY_ATTEMPT),
        "reviewer_ref": reviewer_ref
        or (PRIMARY_REVIEWER if primary else SECONDARY_REVIEWER),
        "second_review_recommended": False,
        "conflicting_signals": False,
    }


def adjudication(
    primary: dict, secondary: dict, *, resolution: str = "primary_supported"
) -> dict:
    selected = primary if resolution != "secondary_supported" else secondary
    result = {
        "schema": ADJUDICATION_RESULT_SCHEMA,
        "episode_ref": selected["episode_ref"],
        "episode_revision_ref": selected["episode_revision_ref"],
        "resolution": resolution,
        **{
            field: copy.deepcopy(selected[field])
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
    result["candidate_item_decisions"] = adjudication_item_decisions(
        [primary, secondary], result
    )
    return result


def episode_metadata(turn_refs: list[str]) -> dict:
    return {
        "session_ref": SESSION,
        "turn_refs": turn_refs,
        "goal_refs": [GOAL],
        "workstream_refs": [WORKSTREAM],
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


class AuditedEpisodeContractTests(unittest.TestCase):
    identity_key = IdentityKey(b"a" * 32)

    def test_audit_revision_ref_commits_all_metadata_and_boundary_provenance(
        self,
    ) -> None:
        initial_episode = episode_metadata([TURN_A, TURN_B])
        initial = create_episode_revision(
            initial_episode, identity_key=self.identity_key
        )
        changed_episode = copy.deepcopy(initial_episode)
        changed_episode["internal_boundary_candidates"] = [
            {
                "left_turn_ref": TURN_A,
                "right_turn_ref": TURN_B,
                "candidate_reasons": ["elapsed_72h_candidate"],
                "accepted_boundary": False,
                "accepted_reasons": [],
            }
        ]

        revised = create_episode_revision(
            changed_episode,
            identity_key=self.identity_key,
            previous_revision=initial,
        )

        self.assertNotEqual(
            revised["episode_revision_ref"], initial["episode_revision_ref"]
        )
        self.assertEqual(
            revised["internal_boundary_candidates"],
            changed_episode["internal_boundary_candidates"],
        )
        tampered = copy.deepcopy(revised)
        tampered["risk_flags"] = ["privacy"]
        with self.assertRaisesRegex(ResultValidationError, "does not commit"):
            create_episode_revision(
                changed_episode,
                identity_key=self.identity_key,
                previous_revision=tampered,
            )

    def test_audit_equal_timestamps_and_input_permutations_have_stable_order_and_ids(
        self,
    ) -> None:
        rows = [
            {
                "turn_ref": turn_ref,
                "session_ref": SESSION,
                "canonical_time": "2026-07-14T00:00:00Z",
                "goal_ref": GOAL,
                "workstream_ref": WORKSTREAM,
                "meaningfulness": "meaningful",
                "risk_flags": [],
                "confidence": "high",
            }
            for turn_ref in (TURN_A, TURN_B)
        ]

        first = construct_episodes(rows)[0]
        second = construct_episodes(list(reversed(rows)))[0]
        first_revision = create_episode_revision(first, identity_key=self.identity_key)
        second_revision = create_episode_revision(
            second, identity_key=self.identity_key
        )

        self.assertEqual(first["turn_refs"], second["turn_refs"])
        self.assertEqual(first_revision["episode_ref"], second_revision["episode_ref"])
        self.assertEqual(
            first_revision["episode_revision_ref"],
            second_revision["episode_revision_ref"],
        )

    def test_audit_mixed_or_insufficient_ordering_fails_closed(self) -> None:
        ordered = [
            {
                "turn_ref": TURN_A,
                "session_ref": SESSION,
                "canonical_time": "2026-07-14T00:00:00Z",
                "sequence": 0,
                "goal_ref": GOAL,
                "workstream_ref": WORKSTREAM,
                "meaningfulness": "meaningful",
                "risk_flags": [],
            },
            {
                "turn_ref": TURN_B,
                "session_ref": SESSION,
                "canonical_time": "2026-07-14T00:01:00Z",
                "goal_ref": GOAL,
                "workstream_ref": WORKSTREAM,
                "meaningfulness": "meaningful",
                "risk_flags": [],
            },
        ]
        with self.assertRaisesRegex(
            ResultValidationError, "mixed canonical turn ordering"
        ):
            construct_episodes(ordered)
        del ordered[0]["sequence"]
        del ordered[1]["canonical_time"]
        with self.assertRaisesRegex(
            ResultValidationError, "complete canonical ordering"
        ):
            construct_episodes(ordered)


class AuditedResultContractTests(unittest.TestCase):
    def test_audit_primary_and_independent_review_require_distinct_slot_attempt_reviewer(
        self,
    ) -> None:
        primary = review("primary")
        secondary = review(
            "secondary",
            attempt_ref=primary["attempt_ref"],
            reviewer_ref=primary["reviewer_ref"],
        )
        for field in ("reviewer_slot", "attempt_ref", "reviewer_ref"):
            with self.subTest(missing=field):
                candidate = review("primary")
                del candidate[field]
                with self.assertRaisesRegex(
                    ResultValidationError, "missing required fields"
                ):
                    validate_episode_review_result(
                        candidate, ALL_REFS, allowed_turn_refs={TURN_A}
                    )
        with self.assertRaisesRegex(ResultValidationError, "distinct attempts"):
            validate_adjudication_result(
                adjudication(primary, secondary),
                ALL_REFS,
                allowed_turn_refs={TURN_A},
                candidate_results=[primary, secondary],
            )

    def test_audit_adjudication_binds_exactly_two_valid_candidate_hashes(self) -> None:
        primary = review("primary")
        secondary = review("secondary")
        value = adjudication(primary, secondary)
        validate_adjudication_result(
            value,
            ALL_REFS,
            allowed_turn_refs={TURN_A},
            candidate_results=[secondary, primary],
        )
        for hashes in (
            [value["candidate_result_hashes"][0]],
            list(reversed(value["candidate_result_hashes"])),
        ):
            with self.subTest(hashes=hashes):
                changed = copy.deepcopy(value)
                changed["candidate_result_hashes"] = hashes
                with self.assertRaises(ResultValidationError):
                    validate_adjudication_result(
                        changed,
                        ALL_REFS,
                        allowed_turn_refs={TURN_A},
                        candidate_results=[primary, secondary],
                    )

    def test_audit_adjudication_cannot_alter_evidence_severity_confidence_or_rewrite(
        self,
    ) -> None:
        primary = review("primary")
        secondary = review("secondary")
        base = adjudication(primary, secondary)
        mutations = {
            "evidence": lambda value: value["events"][0].update(
                evidence_refs=[EVIDENCE_B]
            ),
            "severity": lambda value: value["events"][0].update(severity="critical"),
            "confidence": lambda value: value["events"][0].update(confidence="low"),
            "rewrite": lambda value: value["high_impact_turns"][0].update(
                rewritten_prompt="Perform a different action."
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(base)
                mutate(changed)
                with self.assertRaisesRegex(ResultValidationError, "preserve"):
                    validate_adjudication_result(
                        changed,
                        ALL_REFS,
                        allowed_turn_refs={TURN_A},
                        candidate_results=[primary, secondary],
                    )

    def test_audit_topic_input_accepts_only_resolved_adjudication_where_required(
        self,
    ) -> None:
        primary = review("primary")
        secondary = review("secondary")
        resolved = adjudication(primary, secondary)
        value = {
            "adjudication_candidate_results": {REVISION: [primary, secondary]},
            "schema": TOPIC_INPUT_SCHEMA,
            "workstream_ref": WORKSTREAM,
            "topic_ref": TOPIC,
            "episode_contexts": [
                {
                    "episode_ref": EPISODE,
                    "episode_revision_ref": REVISION,
                    "session_ref": SESSION,
                }
            ],
            "model_configuration_ref": MODEL,
            "episode_reviews": [primary],
            "expected_episode_revision_refs": [REVISION],
            "adjudication_required_episode_revision_refs": [REVISION],
        }
        with self.assertRaisesRegex(ResultValidationError, "resolved adjudication"):
            validate_topic_input(value, ALL_REFS, allowed_turn_refs={TURN_A})
        value["episode_reviews"] = [resolved]
        validated = validate_topic_input(
            value,
            ALL_REFS,
            allowed_turn_refs={TURN_A},
            adjudication_candidate_results={REVISION: [primary, secondary]},
        )
        self.assertEqual(
            validated["episode_reviews"][0]["resolution"], "primary_supported"
        )

    def test_audit_empty_outputs_require_explicit_typed_gaps(self) -> None:
        with self.assertRaisesRegex(ResultValidationError, "explicit gap_reason"):
            validate_extractor_result({"schema": EXTRACTOR_RESULT_SCHEMA, "turns": []})
        validate_extractor_result(
            {
                "schema": EXTRACTOR_RESULT_SCHEMA,
                "turns": [],
                "gap_reason": "insufficient_evidence",
            }
        )
        empty_review = review("primary")
        for field in (
            "events",
            "findings",
            "strengths",
            "risk_flags",
            "high_impact_turns",
            "evidence_refs",
        ):
            empty_review[field] = []
        with self.assertRaisesRegex(ResultValidationError, "explicit review_gap"):
            validate_episode_review_result(empty_review)
        empty_review.update(
            disposition="review_gap",
            gap_reason="insufficient_support",
            confidence="low",
        )
        validate_episode_review_result(empty_review)

        primary = review("primary")
        secondary = review("secondary", severity="medium")
        gap = adjudication(primary, secondary)
        for field in (
            "events",
            "findings",
            "strengths",
            "risk_flags",
            "high_impact_turns",
            "evidence_refs",
        ):
            gap[field] = []
        gap.update(
            resolution="review_gap", gap_reason="conflicting_evidence", confidence="low"
        )
        gap["candidate_item_decisions"] = adjudication_item_decisions(
            [primary, secondary], gap
        )
        validate_adjudication_result(gap, candidate_results=[primary, secondary])

        critical_secondary = review("secondary", severity="critical", safety=True)
        critical_gap = adjudication(primary, critical_secondary)
        for field in (
            "events",
            "findings",
            "strengths",
            "risk_flags",
            "high_impact_turns",
            "evidence_refs",
        ):
            critical_gap[field] = []
        critical_gap.update(
            resolution="review_gap",
            gap_reason="conflicting_evidence",
            confidence="low",
        )
        critical_gap["candidate_item_decisions"] = adjudication_item_decisions(
            [primary, critical_secondary], critical_gap
        )
        with self.assertRaisesRegex(
            ResultValidationError,
            "cannot drop high-severity independent-review risk",
        ):
            validate_adjudication_result(
                critical_gap,
                candidate_results=[primary, critical_secondary],
            )

        high_secondary = review("secondary", severity="high")
        high_gap = adjudication(primary, high_secondary)
        for field in (
            "events",
            "findings",
            "strengths",
            "risk_flags",
            "high_impact_turns",
            "evidence_refs",
        ):
            high_gap[field] = []
        high_gap.update(
            resolution="review_gap",
            gap_reason="conflicting_evidence",
            confidence="low",
        )
        high_gap["candidate_item_decisions"] = adjudication_item_decisions(
            [primary, high_secondary], high_gap
        )
        with self.assertRaisesRegex(
            ResultValidationError,
            "cannot drop high-severity independent-review risk",
        ):
            validate_adjudication_result(
                high_gap,
                candidate_results=[primary, high_secondary],
            )

    def test_audit_gap_disposition_and_reason_combinations_are_closed(self) -> None:
        populated = extractor_result()
        populated["gap_reason"] = "insufficient_evidence"
        with self.assertRaisesRegex(ResultValidationError, "only allowed"):
            validate_extractor_result(populated, ALL_REFS)
        reviewed = review("primary")
        reviewed["gap_reason"] = "review_failure"
        with self.assertRaisesRegex(ResultValidationError, "only allowed"):
            validate_episode_review_result(
                reviewed, ALL_REFS, allowed_turn_refs={TURN_A}
            )
        gap = review("primary")
        gap["disposition"] = "review_gap"
        gap["confidence"] = "low"
        for field in (
            "events",
            "findings",
            "strengths",
            "risk_flags",
            "high_impact_turns",
            "evidence_refs",
        ):
            gap[field] = []
        with self.assertRaisesRegex(ResultValidationError, "explicit gap_reason"):
            validate_episode_review_result(gap)

    def test_audit_each_ref_field_rejects_the_wrong_prefix(self) -> None:
        extractor_mutations = {
            "source_unit_ref": lambda value: value.update(source_unit_ref=EPISODE),
            "turn_ref": lambda value: value["turns"][0].update(turn_ref=EPISODE),
            "evidence_refs": lambda value: value["turns"][0].update(
                evidence_refs=[EPISODE]
            ),
            "span_commitments": lambda value: value["turns"][0].update(
                span_commitments=[EPISODE]
            ),
            "goal_ref": lambda value: value["turns"][0].update(goal_ref=SESSION),
            "workstream_ref": lambda value: value["turns"][0].update(
                workstream_ref=SESSION
            ),
        }
        for field, mutate in extractor_mutations.items():
            with self.subTest(field=field):
                value = extractor_result()
                mutate(value)
                with self.assertRaisesRegex(ResultValidationError, "must use the"):
                    validate_extractor_result(value)
        value = review("primary")
        value["attempt_ref"] = PRIMARY_REVIEWER
        with self.assertRaisesRegex(ResultValidationError, "attempt_ref_v2"):
            validate_episode_review_result(value)

    def test_audit_durable_threshold_requires_real_episode_and_session_refs(
        self,
    ) -> None:
        value = synthesis_result()
        value["guidance_candidates"] = [
            {
                "kind": "verification",
                "episode_lineage": [
                    {"episode_ref": SESSION, "session_ref": EPISODE},
                    {"episode_ref": SESSION_TWO, "session_ref": EPISODE_TWO},
                ],
                "confidence": "high",
                "exception": "none",
            }
        ]
        with self.assertRaisesRegex(ResultValidationError, "episode_ref_v2"):
            validate_synthesis_result(value)

    def test_audit_safety_exception_requires_bound_independent_high_severity_review(
        self,
    ) -> None:
        independent = review("secondary", safety=True, severity="high")
        topic_result = {
            "episode_lineage": [{"episode_ref": EPISODE, "session_ref": SESSION}],
            "episode_refs": [EPISODE],
            "events": copy.deepcopy(independent["events"]),
            "findings": copy.deepcopy(independent["findings"]),
            "schema": TOPIC_RESULT_SCHEMA,
            "session_refs": [SESSION],
            "strengths": copy.deepcopy(independent["strengths"]),
        }
        value = synthesis_result()
        value["topic_result_commitment"] = build_synthesis_topic_result_commitment(
            [topic_result]
        )
        value["signal_commitments"] = build_synthesis_signal_commitments([topic_result])
        value.update(build_synthesis_signal_exemplars([topic_result]))
        value["guidance_candidates"] = [
            {
                "kind": "privacy_guardrail",
                "episode_lineage": [{"episode_ref": EPISODE, "session_ref": SESSION}],
                "confidence": "high",
                "exception": "high_severity_safety",
                "independent_review_hash": canonical_result_hash(independent),
            }
        ]
        with self.assertRaisesRegex(
            ResultValidationError, "supplied validated independent review"
        ):
            validate_synthesis_result(
                value,
                ALL_REFS,
                allowed_turn_refs={TURN_A},
                topic_results=[topic_result],
            )
        validate_synthesis_result(
            value,
            ALL_REFS,
            allowed_turn_refs={TURN_A},
            independent_review_results=[independent],
            topic_results=[topic_result],
        )
        low = review("secondary", safety=True, severity="medium")
        value["guidance_candidates"][0]["independent_review_hash"] = (
            canonical_result_hash(low)
        )
        with self.assertRaisesRegex(ResultValidationError, "high-severity safety"):
            validate_synthesis_result(
                value,
                ALL_REFS,
                allowed_turn_refs={TURN_A},
                independent_review_results=[low],
                topic_results=[topic_result],
            )
        positive = review("secondary", safety=True, severity="medium")
        positive["strengths"] = [
            {
                "kind": "safe_tool_use",
                "evidence_refs": [EVIDENCE_A],
                "confidence": "high",
                "severity": "critical",
            }
        ]
        value["guidance_candidates"][0]["independent_review_hash"] = (
            canonical_result_hash(positive)
        )
        with self.assertRaisesRegex(ResultValidationError, "high-severity safety"):
            validate_synthesis_result(
                value,
                ALL_REFS,
                allowed_turn_refs={TURN_A},
                independent_review_results=[positive],
                topic_results=[topic_result],
            )

    def test_audit_leak_detection_covers_pkcs8_asia_personal_ipv6_and_internal_hosts(
        self,
    ) -> None:
        value = extractor_result()
        key_label = " ".join(("PRI" + "VATE", "K" + "EY"))
        aws_access_key = "AS" + "IA1234567890ABCDEF"
        value["turns"][0]["generalized_working_text"] = (
            f"-----BEGIN ENCRYPTED {key_label}-----\nZmFrZQ==\n"
            f"-----END ENCRYPTED {key_label}----- "
            f"{aws_access_key} operator@example.com +1-415-555-0123 "
            "fd00::1234 server=build-node-7"
        )
        validated = validate_extractor_result(value, ALL_REFS)
        text = validated["turns"][0]["generalized_working_text"]
        self.assertIn("[REDACTED_SECRET]", text)
        self.assertIn("[REDACTED_CREDENTIAL]", text)
        self.assertIn("[REDACTED_PERSONAL_IDENTIFIER]", text)
        self.assertIn("[REDACTED_IP_ADDRESS]", text)
        self.assertIn("[REDACTED_INTERNAL_HOST]", text)
        self.assertEqual(scan_for_leaks(validated), ())

    def test_audit_redacts_grouped_and_compact_international_phone_numbers(
        self,
    ) -> None:
        for phone in (
            "+44 20 7946 0958",
            "+44 (0)20 7946 0958",
            "+442079460958",
            "020 7946 0958",
            "(020) 7946 0958",
            "02079460958",
        ):
            with self.subTest(phone=phone):
                source = f"Call {phone} before continuing."
                findings = scan_for_leaks({"summary": source})
                self.assertEqual(
                    {finding.category for finding in findings},
                    {"personal_identifier"},
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "Call [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for safe in (
            "Release 2026-08-18 uses Python 3.13.12 and build 123456.",
            "Build 61234567 remains an unlabeled numeric identifier.",
            "Bounds +12 34 56 and +1234-5678-9012-3456-7890 stay numeric labels.",
            "Order 1234567890123456 remains an overlong numeric label.",
        ):
            with self.subTest(safe=safe):
                self.assertEqual(scan_for_leaks({"summary": safe}), ())

    def test_audit_redacts_short_domestic_numbers_in_phone_context(self) -> None:
        for source in (
            "Call 6123 4567 before continuing.",
            "Phone: 61234567 before continuing.",
            "Phone:  61234567 before continuing.",
            "Phone : 61234567 before continuing.",
            "Phone number: 6123 4567 before continuing.",
            "Telephone number: 6123 4567 before continuing.",
            "Tel: (612) 3456 before continuing.",
            "Phone: 1234567890123 before continuing.",
            'Phone: "1234567890123" before continuing.',
            "**Phone:** 1234567890123 before continuing.",
            "**Phone: 1234567890123**",
            '{"phone":"1234567890123"}',
            "phoneNumber: 1234567890123 before continuing.",
            "**Phone no:** 1234567890123 before continuing.",
            '{"contact_phone":"1234567890123"}',
        ):
            with self.subTest(source=source):
                findings = scan_for_leaks({"summary": source})
                self.assertEqual(
                    {finding.category for finding in findings},
                    {"personal_identifier"},
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertIn(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

    def test_audit_redacts_bare_address_ssn_and_luhn_card_values(self) -> None:
        for source, expected in (
            (
                "Address: 123 Main Street",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Address: Alice Smith, 123 Main Street",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Observed: Address: 123 Main Street, City: London, "
                "Postal Code: SW1A 1AA",
                "Observed: [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                'Observed: Address: 123 Main Street, City: "London"',
                "Observed: [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Observed: Address: 123 Main Street",
                "Observed: [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                '{"address": "123 Main Street"}',
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
            (
                "**Address:** 123 Main Street",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Address: 123 Main Street**",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Identifier 123-45-6789 was referenced.",
                "Identifier [REDACTED_PERSONAL_IDENTIFIER] was referenced.",
            ),
            (
                "Payment used 4111 1111 1111 1111 before continuing.",
                "Payment used [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
            (
                "Payment used 4012888888881881 before continuing.",
                "Payment used [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
            (
                "Payment used 4000-0000-0000-0000-006 before continuing.",
                "Payment used [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    {"personal_identifier"},
                    {
                        finding.category
                        for finding in scan_for_leaks({"summary": source})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    expected,
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for safe_source in (
            "Inspect memory address: 0x1000.",
            "The address matcher passed.",
            "Address: 0x1000",
            '{"address": "0x1000"}',
            "Address: 0x1000, status: active",
            "Address: 0x1000, 0x2000",
            'Address: 0x1000, City: "0x2000"',
            '{"address": "0x1000, 0x2000"}',
            "Address: [REDACTED_PERSONAL_IDENTIFIER], status: active",
            "Address: [REDACTED_PERSONAL_IDENTIFIER]",
            "Identifier 000-00-0000 was referenced.",
            "Identifier 666-45-6789 was referenced.",
            "Identifier 900-45-6789 was referenced.",
            "Identifier 123-00-6789 was referenced.",
            "Identifier 123-45-0000 was referenced.",
            "Identifier x123-45-6789 was referenced.",
            "Identifier 123-45-6789x was referenced.",
            "Payment used 4111 1111 1111 1112 before continuing.",
            "Payment used 4111 1111 1111 1111 1111 before continuing.",
            "Payment used x4111 1111 1111 1111 before continuing.",
            "Payment used 4111 1111 1111 1111x before continuing.",
            "Payment used 9 4111 1111 1111 1111 before continuing.",
            "Payment used 4111 1111 1111 1111 9 before continuing.",
            "Payment used 40000000000000000002 before continuing.",
            "Order 1234567890123 remains a numeric identifier.",
            "Order 12345678901234 remains a numeric identifier.",
            "Order 123456789012345 remains a numeric identifier.",
        ):
            with self.subTest(safe_source=safe_source):
                self.assertEqual((), scan_for_leaks({"summary": safe_source}))
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = safe_source
                validated = validate_extractor_result(value, ALL_REFS)
                self.assertEqual(
                    safe_source,
                    validated["turns"][0]["generalized_working_text"],
                )

        for ssn_boundary in (
            "0123-45-6789",
            "123-45-67890",
            "1-123-45-6789",
            "123-45-6789-0",
        ):
            with self.subTest(ssn_boundary=ssn_boundary):
                self.assertIsNone(
                    privacy_locators.BARE_STANDARD_SSN_RE.search(ssn_boundary)
                )

    def test_audit_redacts_the_complete_labeled_personal_value(self) -> None:
        for source in (
            "Observed employee name: Alice Smith before continuing.",
            "Observed customer full name: Alice Smith before continuing.",
            "Observed client's full name: Alice Smith before continuing.",
            "Observed Customer's full name: Alice Smith before continuing.",
            "Observed Customer\u2019s full name: Alice Smith before continuing.",
            "Observed client name: Alice Smith before continuing.",
            "Observed tenant name: Example Tenant before continuing.",
            "Observed organization name: Example Organization before continuing.",
            "Observed employee full name: Bob before continuing.",
            "Observed user first name: Alice before continuing.",
            "Observed user last name: Smith before continuing.",
            "Observed customerFullName: Alice Smith before continuing.",
            "Observed employeeFirstName: Bob before continuing.",
            "Observed userLastName: Smith before continuing.",
            "Observed billing address: 123 Main Street before continuing.",
            "Observed customer address: 123 Main Street before continuing.",
            "Observed Customer's address: 123 Main Street before continuing.",
            "Observed Customer\u2019s address: 123 Main Street before continuing.",
            "Observed client address: 123 Main Street before continuing.",
            "Observed employee address: 123 Main Street before continuing.",
            "Observed home address: 123 Main Street before continuing.",
            "Observed mailing address: 123 Main Street before continuing.",
            "Observed person address: 123 Main Street before continuing.",
            "Observed postal address: 123 Main Street before continuing.",
            "Observed residential address: 123 Main Street before continuing.",
            "Observed shipping address: 123 Main Street before continuing.",
            "Observed tenant address: 123 Main Street before continuing.",
            "Observed user address: 123 Main Street before continuing.",
            "Observed date of birth: 1990-01-02 before continuing.",
            "Observed DOB: 1990-01-02 before continuing.",
            "Observed customer's DOB: 1990-01-02 before continuing.",
            "Observed customerDateOfBirth: 1990-01-02 before continuing.",
            "Observed CustomerDateOfBirth: 1990-01-02 before continuing.",
            "Observed DateOfBirth: 1990-01-02 before continuing.",
            "Observed DOB: [REDACTED_PERSONAL_IDENTIFIER] 1990-01-02.",
            'Observed DOB: "[REDACTED_PERSONAL_IDENTIFIER]" 1990-01-02.',
            "Observed DOB: [REDACTED_PERSONAL_IDENTIFIER_19900102].",
            "Observed **Customer name:** Alice Smith before continuing.",
            "Observed **Full name:** Alice before continuing.",
            "Observed SSN: 000-00-0000 before continuing.",
            "Observed social security number: 000-00-0000 before continuing.",
            "Observed national insurance number: QQ 00 00 00 C before continuing.",
            "Observed tax ID: 00-0000000 before continuing.",
            "Observed passport number: X0000000 before continuing.",
            "Observed driver's license number: X0000000 before continuing.",
            "Observed credit card: 4111 1111 1111 1111 before continuing.",
            "Observed payment card number: 4111 1111 1111 1111 before continuing.",
            "Observed bank account number: 00012345 before continuing.",
            "Observed account number: 00012345 before continuing.",
            "Observed routing number: 000000000 before continuing.",
            "Observed IBAN: GB00 TEST 0000 0000 0000 00 before continuing.",
        ):
            with self.subTest(source=source):
                expected_categories = {"personal_identifier"}
                if source == ("Observed DOB: [REDACTED_PERSONAL_IDENTIFIER_19900102]."):
                    expected_categories.add("unredactable_secret")
                self.assertEqual(
                    expected_categories,
                    {
                        finding.category
                        for finding in scan_for_leaks({"summary": source})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "Observed [REDACTED_PERSONAL_IDENTIFIER]",
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for source in (
            "Full name: Alice Smith",
            "First name: Alice",
            "Last name: Smith",
            "full_name: Alice Smith",
            "last-name: Smith",
            "fullName: Alice Smith",
            "firstName: Alice",
            "lastName: Smith",
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    {"personal_identifier"},
                    {
                        finding.category
                        for finding in scan_for_leaks({"summary": source})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "[REDACTED_PERSONAL_IDENTIFIER]",
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        source = "Observed: Full name: Alice Smith"
        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = source

        validated = validate_extractor_result(value, ALL_REFS)

        self.assertEqual(
            "Observed: [REDACTED_PERSONAL_IDENTIFIER]",
            validated["turns"][0]["generalized_working_text"],
        )
        self.assertEqual(scan_for_leaks(validated), ())

        for source, expected in (
            (
                "The customer's name is Alice Smith",
                "The [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "The customer address was 123 Main Street",
                "The [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "The employee DOB set to 1990-01-02",
                "The [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            ("Full name is Alice Smith", "[REDACTED_PERSONAL_IDENTIFIER]"),
            ("Full name is Smith, John", "[REDACTED_PERSONAL_IDENTIFIER]"),
            (
                "Full name is Smith, John, status ok",
                "[REDACTED_PERSONAL_IDENTIFIER], status ok",
            ),
            ("First name was Alice", "[REDACTED_PERSONAL_IDENTIFIER]"),
            ("Last name set to Smith", "[REDACTED_PERSONAL_IDENTIFIER]"),
            (
                "Address was 123 Main Street",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "- Full name is Alice Smith",
                "- [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Observed: Full name is Alice Smith",
                "Observed: [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Recorded Full name is Alice Smith",
                "Recorded [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Recorded Address was 123 Main Street",
                "Recorded [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "(Full name is Alice Smith)",
                "([REDACTED_PERSONAL_IDENTIFIER])",
            ),
            (
                "Full name is Alice (Ace) Smith",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Full name is Alice Smith**",
                "**[REDACTED_PERSONAL_IDENTIFIER]**",
            ),
            (
                "*Full name is Alice Smith*",
                "*[REDACTED_PERSONAL_IDENTIFIER]*",
            ),
            (
                "**Full name is Smith, John, status ok**",
                "**[REDACTED_PERSONAL_IDENTIFIER], status ok**",
            ),
            (
                "**Full name is Alice (alias, status pending) Smith**",
                "**[REDACTED_PERSONAL_IDENTIFIER]**",
            ),
            (
                "__Address was 123 Main Street__",
                "__[REDACTED_PERSONAL_IDENTIFIER]__",
            ),
            (
                "_Address was 123 Main Street_",
                "_[REDACTED_PERSONAL_IDENTIFIER]_",
            ),
            (
                "__Address was 123 Main Street, status ok__",
                "__[REDACTED_PERSONAL_IDENTIFIER], status ok__",
            ),
            (
                "__Address was 123 Main Street, state: CA, zip: 94105__",
                "__[REDACTED_PERSONAL_IDENTIFIER]__",
            ),
            (
                "Address is present at 123 Main Street",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Full name is unavailable for Alice Smith",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Full name is unavailable: Alice Smith",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Full name is Alice Smith",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Full name is required** then Full name is Alice Smith",
                "**Full name is required** then [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Full name is Alice (Ace Smith**",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Full name is (Alice Smith",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "__Address was 123 Main Street",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "**Full name is " + "(alias)" * 512,
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "The phone number is 6123 4567",
                "The phone number is [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "Payment sent to DE89370400440532013000 before continuing.",
                "Payment sent to [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
            (
                "Payment sent to GB82 WEST 1234 5698 7654 32 before continuing.",
                "Payment sent to [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
            (
                "Payment sent to gb82 west 1234 5698 7654 32 before continuing.",
                "Payment sent to [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
            (
                "Payment sent to Gb82 WeSt 1234 5698 7654 32 before continuing.",
                "Payment sent to [REDACTED_PERSONAL_IDENTIFIER] before continuing.",
            ),
            (
                "Payment sent to KZ86 125K ZT50 0410 0100 then continued.",
                "Payment sent to [REDACTED_PERSONAL_IDENTIFIER] then continued.",
            ),
        ):
            with self.subTest(narrative_source=source):
                self.assertEqual(
                    {"personal_identifier"},
                    {
                        finding.category
                        for finding in scan_for_leaks({"summary": source})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    expected,
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for source, expected in (
            (
                "- Full name: Alice Smith",
                "- [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "> firstName: Alice",
                "> [REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                '"Full name: Alice Smith"',
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                '{"fullName": "Alice Smith"}',
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
            (
                '{"fullName": "Alice \\"Ace\\" Smith"}',
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
            (
                "{'fullName': 'Alice \\'Ace\\' Smith'}",
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
            (
                "**Customer name:** Alice Smith",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                "__DOB:__ 1990-01-02",
                "[REDACTED_PERSONAL_IDENTIFIER]",
            ),
            (
                '{"clientName": "Alice Smith"}',
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
            (
                '{"ssn": "000-00-0000"}',
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
            (
                '{"creditCardNumber": "4111 1111 1111 1111"}',
                "{[REDACTED_PERSONAL_IDENTIFIER]}",
            ),
        ):
            with self.subTest(structured_source=source):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    expected,
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for safe_source in (
            "Inspect memory address: 0x1000.",
            "Inspect memory full name: stack frame.",
            "Inspect memory  full name: stack frame.",
            "Inspect memory\tfull name: stack frame.",
            "Inspect memory-full name: stack frame.",
            "The client name matcher passed.",
            "The organization name policy passed.",
            "Customer's address book: shared.",
            "The customer address matcher passed.",
            "DOB status: unavailable.",
            "The date of birth policy passed.",
            "**Customer status:** active.",
            "DOB: [REDACTED_PERSONAL_IDENTIFIER]",
            'DOB: "[REDACTED_PERSONAL_IDENTIFIER]"',
            "**DOB:** [REDACTED_PERSONAL_IDENTIFIER]",
            "(DOB: [REDACTED_PERSONAL_IDENTIFIER])",
            "DOB: [REDACTED_PERSONAL_IDENTIFIER]]",
            r"DOB: \"[REDACTED_PERSONAL_IDENTIFIER]\"",
            '{"DOB":"[REDACTED_PERSONAL_IDENTIFIER]","status":"ok"}',
            "Passport status: unavailable.",
            "Credit card support is unavailable.",
            "The account number of failures is three.",
            "Full name is required.",
            "First name was missing.",
            "Last name is unavailable.",
            "Address is unavailable.",
            "**Full name is required, status ok",
            "__Address is unavailable, status ok",
            "Recorded Address is unavailable, status ok",
            "Address was 0x1000.",
            "Full name is [REDACTED_PERSONAL_IDENTIFIER].",
            "Payment sent to DE88370400440532013000 before continuing.",
            "Payment sent to XDE89370400440532013000 before continuing.",
            "Payment sent to DE893704004405 before continuing.",
            "Payment sent to GB81 WEST 1234 5698 7654 32 before continuing.",
            "Inspect pin=GPIO17 before continuing.",
            "Run with --pin requests==2.32.5.",
            "The pin is bent.",
        ):
            with self.subTest(safe_source=safe_source):
                self.assertEqual((), scan_for_leaks({"summary": safe_source}))

    def test_audit_redacts_split_passphrase_and_passcode_labels(self) -> None:
        for source in (
            "pass phrase: purple",
            "pass-phrase: purple",
            "pass_phrase: purple",
            "pass code: 839201",
            "pass-code: 839201",
            "pass_code: 839201",
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    {"credential"},
                    {
                        finding.category
                        for finding in scan_for_leaks({"summary": source})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "[REDACTED_CREDENTIAL]",
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for safe_source in (
            "Checks pass\nphrase: purple",
            "Checks pass\ncode: 839201",
        ):
            with self.subTest(safe_source=safe_source):
                self.assertEqual((), scan_for_leaks({"summary": safe_source}))

    def test_audit_redacts_pascalcase_credential_fields(self) -> None:
        # Keep these helper-catalog fixtures literal so exact-secret admission
        # can prove their complete raw-byte identity.
        for source in (
            "UserPassword = codex_synth_v1_bearer_a",
            "DatabaseSecret was codex_synth_v1_bearer_a",
            "UserPIN = codex_synth_v1_bearer_a",
            "ServiceAPIKey = codex_synth_v1_api_key_a",
            "DatabaseCredential was codex_synth_v1_bearer_a",
            "DatabaseSecret WAS codex_synth_v1_bearer_a",
            "ServiceAPIKey Is codex_synth_v1_api_key_a",
            "DatabaseAccessToken = codex_synth_v1_access_a",
            "ServiceRefreshToken was codex_synth_v1_refresh_a",
            "DatabaseSecret was codex_synth_v1_bearer_a, status ok",
            "DatabaseSecret was unavailable: codex_synth_v1_bearer_a, status ok",
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    {"credential"},
                    {
                        finding.category
                        for finding in scan_for_leaks({"summary": source})
                    },
                )
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    "[REDACTED_CREDENTIAL]",
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

        for safe_source in (
            "CancellationToken = active",
            "CancellationToken was cancelled",
            "DesignToken = color.primary",
            "UserPassword" + " = missing",
            "DatabaseSecret was not present",
            "UserPasswordCount = 12",
        ):
            with self.subTest(safe_source=safe_source):
                self.assertFalse(
                    privacy_locators.contains_credential_material(safe_source)
                )

    def test_audit_shared_sensitive_text_policy_covers_retained_gaps(self) -> None:
        cases = (
            ("home path ~/private/file.txt", "path", "[REDACTED_PATH]"),
            ("drive path C:\\private\\file.txt", "path", "[REDACTED_PATH]"),
            ("host path \\\\server\\share", "path", "[REDACTED_PATH]"),
            ("session id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("thread ref: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("conversation id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("turn id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("message id: raw_123456", "raw_id", "[REDACTED_RAW_ID]"),
            ("tool call id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("request id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("run id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("job id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            ("attempt id: abcdef12", "raw_id", "[REDACTED_RAW_ID]"),
            (
                "The response embeds ```secret_code``` inline.",
                "code",
                "[REDACTED_CODE]",
            ),
            (
                "The response embeds ```secret_code inline.",
                "code",
                "[REDACTED_CODE]",
            ),
            (
                "Inspect host: build-node-7 before continuing.",
                "internal_host",
                "[REDACTED_INTERNAL_HOST]",
            ),
            (
                "Inspect identifier abcdefabcdefabcdefabcdef before continuing.",
                "raw_id",
                "[REDACTED_RAW_ID]",
            ),
            (
                "Inspect identifier 01890f3e-7b12-7cc2-bf79-123456789abc.",
                "raw_id",
                "[REDACTED_RAW_ID]",
            ),
            (f"Inspect identifier {'a' * 65}.", "raw_id", "[REDACTED_RAW_ID]"),
        )
        for source, category, replacement in cases:
            with self.subTest(source=source):
                findings = scan_for_leaks({"summary": source})
                self.assertIn(category, {finding.category for finding in findings})
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertIn(
                    replacement,
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

    def test_audit_ipv4_redaction_covers_public_ports_without_matching_versions(
        self,
    ) -> None:
        raw_text = (
            "Resolvers 8.8.8.8:53 and 203.0.113.7 were queried; "
            "versions v1.2.3.4, 3.12.4, and 2026.07.14.4 plus invalid "
            "999.1.1.1 remain labels."
        )
        findings = scan_for_leaks({"summary": raw_text})
        self.assertEqual(
            len([finding for finding in findings if finding.category == "ip_address"]),
            2,
        )

        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = raw_text
        validated = validate_extractor_result(value, ALL_REFS)
        text = validated["turns"][0]["generalized_working_text"]

        self.assertEqual(text.count("[REDACTED_IP_ADDRESS]"), 2)
        self.assertNotIn(":53", text)
        self.assertIn("v1.2.3.4", text)
        self.assertIn("3.12.4", text)
        self.assertIn("2026.07.14.4", text)
        self.assertIn("999.1.1.1", text)
        self.assertEqual(scan_for_leaks(validated), ())

    def test_audit_redacts_bare_unspecified_ipv6(self) -> None:
        for source, expected in (
            (
                "Inspect :: before continuing.",
                "Inspect [REDACTED_IP_ADDRESS] before continuing.",
            ),
            (
                'He wrote "Inspect ::."',
                'He wrote "Inspect [REDACTED_IP_ADDRESS]."',
            ),
            (
                "Inspect (::.)",
                "Inspect ([REDACTED_IP_ADDRESS].)",
            ),
        ):
            with self.subTest(source=source):
                value = extractor_result()
                value["turns"][0]["generalized_working_text"] = source

                validated = validate_extractor_result(value, ALL_REFS)

                self.assertEqual(
                    expected,
                    validated["turns"][0]["generalized_working_text"],
                )
                self.assertEqual(scan_for_leaks(validated), ())

    def test_audit_does_not_extract_ipv6_suffix_from_syntax_tokens(self) -> None:
        source = "Keep Python 3.13:: section and field:1:: marker unchanged."
        self.assertEqual(scan_for_leaks({"summary": source}), ())

        value = extractor_result()
        value["turns"][0]["generalized_working_text"] = source
        validated = validate_extractor_result(value, ALL_REFS)

        self.assertEqual(source, validated["turns"][0]["generalized_working_text"])
        self.assertEqual(scan_for_leaks(validated), ())

    def test_audit_redaction_consumes_truncated_private_key_blocks(self) -> None:
        value = extractor_result()
        key_label = " ".join(("PRI" + "VATE", "K" + "EY"))
        value["turns"][0]["generalized_working_text"] = (
            f"-----BEGIN ENCRYPTED {key_label}-----\ntruncated-sensitive-material"
        )

        validated = validate_extractor_result(value, ALL_REFS)

        self.assertEqual(
            "[REDACTED_SECRET]",
            validated["turns"][0]["generalized_working_text"],
        )
        self.assertEqual(scan_for_leaks(validated), ())


if __name__ == "__main__":
    unittest.main()
