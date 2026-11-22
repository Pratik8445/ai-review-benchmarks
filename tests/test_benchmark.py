import unittest

from benchmark.capture import classify_terminal_outcome, deduplicate_by_id, extract_atomic_findings
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

    def test_provider_isolation_filters_foreign_bots(self):
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

    def test_quota_and_unattempted_classification(self):
        self.assertEqual(classify_terminal_outcome([], [], [], {"greptile-apps[bot]"}), "unattempted")
        quota_comment = [{"id": 9, "user": {"login": "greptile-apps[bot]"}, "body": "Rate limit / credits exhausted"}]
        self.assertEqual(classify_terminal_outcome([], [], quota_comment, {"greptile-apps[bot]"}), "quota_stopped")

    def test_scoring_deduplicates_multiple_comments_for_same_defect(self):
        obs = {
            "provider": "proofline",
            "case_id": "03",
            "terminal_outcome": "completed",
            "findings": [
                {"source_id": 1, "path": "reports.py", "body": "range drops remainder when jobs < batch_size 20"},
                {"source_id": 2, "path": "reports.py", "body": "second note about batch_size 20 remainder"},
            ],
        }
        spec = {
            "case_id": "03",
            "has_defect": True,
            "expected_defect": {
                "file": "reports.py",
                "keywords": ["remainder", "batch_size", "20", "range"],
            },
        }
        grade = score_observation(obs, spec)
        self.assertTrue(grade.defect_caught)
        self.assertEqual(grade.true_positives, 1)
        self.assertEqual(grade.false_positives, 0)

    def test_clean_control_flags_count_as_false_positives(self):
        obs = {
            "provider": "coderabbit",
            "case_id": "07",
            "terminal_outcome": "completed",
            "findings": [
                {"source_id": 10, "path": "migrations/002_pending_by_queue.sql", "body": "Consider adding CONCURRENTLY"}
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
