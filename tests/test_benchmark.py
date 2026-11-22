import unittest

from benchmark.capture import (
    classify_terminal_outcome,
    deduplicate_by_id,
    detect_prior_foreign_reviews,
    extract_atomic_findings,
)
from benchmark.score import build_summary_markdown, score_observation


class BenchmarkHarnessTests(unittest.TestCase):
    def test_deduplicate_webhook_retries(self):
        comments = [
            {"id": 101, "user": {"login": "prooflinedev[bot]"}, "body": "Bug A", "path": "reports.py"},
            {"id": 101, "user": {"login": "prooflinedev[bot]"}, "body": "Bug A", "path": "reports.py"},
        ]
        findings = extract_atomic_findings(
            reviews=[],
            inline_comments=comments,
            issue_comments=[],
            bot_logins={"prooflinedev[bot]"},
        )
        self.assertEqual(len(deduplicate_by_id(comments)), 1)
        self.assertEqual(len(findings), 1)

    def test_provider_isolation_filters_foreign_bots_and_flags_non_blind(self):
        comments = [
            {"id": 1, "user": {"login": "prooflinedev[bot]"}, "body": "Proofline note", "path": "reports.py"},
            {"id": 2, "user": {"login": "coderabbitai[bot]"}, "body": "CodeRabbit note", "path": "reports.py"},
        ]
        findings = extract_atomic_findings(
            reviews=[],
            inline_comments=comments,
            issue_comments=[],
            bot_logins={"coderabbitai[bot]"},
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["author"], "coderabbitai[bot]")
        foreign = detect_prior_foreign_reviews([], comments, {"coderabbitai[bot]"})
        self.assertEqual(foreign, ["prooflinedev[bot]"])

    def test_requested_no_response_and_quota_classification(self):
        self.assertEqual(classify_terminal_outcome([], [], [], {"greptile-apps[bot]"}, "greptile"), "unattempted")
        trigger = [{"id": 5, "user": {"login": "Pratik8445"}, "body": "@greptileai"}]
        self.assertEqual(
            classify_terminal_outcome([], [], trigger, {"greptile-apps[bot]"}, "greptile"),
            "requested_no_response",
        )
        # Finding mentioning rate limit must not trigger quota_stopped
        inline_rate_limit = [{"id": 7, "user": {"login": "prooflinedev[bot]"}, "path": "reports.py", "body": "Missing rate limit check"}]
        self.assertEqual(
            classify_terminal_outcome([], inline_rate_limit, [], {"prooflinedev[bot]"}, "proofline"),
            "completed",
        )

    def test_adjudications_keyed_by_stable_source_id_survive_reordering(self):
        obs = {
            "provider": "proofline",
            "case_id": "02",
            "terminal_outcome": "completed",
            "findings": [
                {"source_type": "inline_comment", "source_id": 200, "path": "reports.py", "body": "Lock held during stdout"},
                {"source_type": "inline_comment", "source_id": 100, "path": "reports.py", "body": "Missing CSV quoting/escaping"},
            ],
        }
        spec = {
            "case_id": "02",
            "has_defect": True,
            "expected_defect": {
                "file": "reports.py",
                "keywords": ["csv", "quoting", "escaping"],
            },
        }
        overrides = {
            "proofline:02": {
                "inline_comment:200": {"label": "valid_extra", "reason": "Valid lock warning"}
            }
        }
        grade = score_observation(obs, spec, overrides=overrides)
        self.assertTrue(grade.defect_caught)
        self.assertEqual(grade.true_positives, 1)
        self.assertEqual(grade.valid_extra_warnings, 1)

    def test_clean_control_flags_count_as_false_positives(self):
        obs = {
            "provider": "coderabbit",
            "case_id": "07",
            "terminal_outcome": "completed",
            "findings": [
                {"source_type": "inline_comment", "source_id": 10, "path": "migrations/002_pending_by_queue.sql", "body": "Consider adding CONCURRENTLY"}
            ],
        }
        spec = {"case_id": "07", "has_defect": False, "expected_defect": None}
        grade = score_observation(obs, spec)
        self.assertFalse(grade.defect_caught)
        self.assertEqual(grade.false_positives, 1)

        md = build_summary_markdown([grade], ["coderabbit"], ["07"])
        self.assertIn("NOISE (1 FP)", md)


if __name__ == "__main__":
    unittest.main()
