import json
import tempfile
import unittest
from pathlib import Path

from hil_bench.jira_dataset import load_jira_rows
from hil_bench.judge_calibration import CalibrationCase, evaluate_cases, load_cases


class TestJudgeCalibration(unittest.TestCase):
    def test_sample_labels_refer_to_registered_blockers(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "jira_vi"
        rows = load_jira_rows(sample / "jira_export.json", sample / "annotations.json")
        blocker_ids = {
            row["task_id"]: {blocker["id"] for blocker in row["blocker_registry"]["blockers"]}
            for row in rows
        }
        cases = load_cases(sample / "calibration.json", blocker_ids)
        self.assertEqual(
            {case.expected_blocker for case in cases if case.expected_blocker is not None},
            blocker_ids["DEMO-101"],
        )
        self.assertTrue(any(case.expected_blocker is None for case in cases))

    def test_service_error_is_not_a_correct_rejection(self):
        cases = [
            CalibrationCase("DEMO-101", "Kỳ báo cáo bắt đầu khi nào?", "period"),
            CalibrationCase("DEMO-101", "Ai phụ trách nhóm này?", None),
            CalibrationCase("DEMO-101", "Tên người nhận là gì?", None),
        ]
        results = iter([("period", False), (None, False), (None, True)])
        report = evaluate_cases(cases, lambda task_id, question: next(results))
        self.assertEqual(report["accuracy"], 2 / 3)
        self.assertEqual(report["match_accuracy"], 1)
        self.assertEqual(report["no_match_accuracy"], 0.5)
        self.assertEqual(report["judge_errors"], 1)

    def test_unknown_label_is_rejected_before_model_calls(self):
        data = [{"task_id": "DEMO-101", "question": "Kỳ báo cáo?", "expected_blocker": "other"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown blocker"):
                load_cases(path, {"DEMO-101": {"period"}})
