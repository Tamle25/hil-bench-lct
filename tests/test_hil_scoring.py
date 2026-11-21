import unittest

from hil_bench.utils.compute_hil_metrics import apply_ask_human_gate, compute_hil_metrics


def attempt(*matches):
    return {
        "questions": [{"blocker_name": name} for name in matches],
        "n_blockers": 3,
        "blockers": {"a": False, "b": False, "c": False},
    }


class HilScoringTest(unittest.TestCase):
    def test_precision_counts_relevant_questions_and_recall_counts_distinct_blockers(self):
        result = compute_hil_metrics({"asked": attempt("a", "a", "b", None), "silent": attempt()})

        self.assertEqual(result["n_questions"], 4)
        self.assertEqual(result["n_relevant_questions"], 3)
        self.assertEqual(result["n_blockers_present"], 6)
        self.assertEqual(result["n_blockers_discovered"], 2)
        self.assertAlmostEqual(result["precision"], 3 / 4)
        self.assertAlmostEqual(result["recall"], 1 / 3)
        self.assertAlmostEqual(result["ask_f1"], 6 / 13)
        self.assertEqual(result["instances"]["silent"]["recall"], 0)

    def test_only_correct_artifacts_with_all_registered_blockers_pass(self):
        clarification = compute_hil_metrics(
            {
                "guessed": attempt("a", "b", "unregistered"),
                "passed": attempt("a", "b", "c"),
                "incorrect": attempt("a", "b", "c"),
            }
        )
        verifier = {
            "total_instances": 3,
            "resolved_instances": ["guessed", "passed"],
            "pass_at_1_count": 2,
            "pass_at_1_rate": 200 / 3,
        }

        apply_ask_human_gate(verifier, clarification)

        self.assertEqual(verifier["artifact_resolved_instances"], ["guessed", "passed"])
        self.assertEqual(verifier["artifact_pass_at_1_count"], 2)
        self.assertEqual(verifier["resolved_instances"], ["passed"])
        self.assertEqual(verifier["pass_at_1_count"], 1)
        self.assertAlmostEqual(verifier["pass_at_1_rate"], 100 / 3)
        self.assertFalse(clarification["instances"]["guessed"]["all_blockers_resolved"])

    def test_logs_with_no_questions_still_include_registered_blockers(self):
        scored = compute_hil_metrics({"silent": attempt()})

        self.assertEqual(scored["n_blockers_present"], 3)
        self.assertEqual(scored["precision"], 0)
        self.assertEqual(scored["recall"], 0)
        self.assertEqual(scored["ask_f1"], 0)


if __name__ == "__main__":
    unittest.main()
