import json
import shutil
import sqlite3
import tarfile
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hil_bench.jira_dataset import load_jira_rows


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "jira_vi"


class JiraDatasetTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.pack = Path(temporary.name) / "pack"
        shutil.copytree(SAMPLE, self.pack)
        self.export = self.pack / "jira_export.json"
        self.annotations = self.pack / "annotations.json"
        self.annotation_data = json.loads(self.annotations.read_text(encoding="utf-8"))

    def write_annotations(self):
        self.annotations.write_text(json.dumps(self.annotation_data, ensure_ascii=False), encoding="utf-8")

    def test_sample_adf_and_read_only_oracle(self):
        [row] = load_jira_rows(self.export, self.annotations)
        self.assertEqual(row["task_id"], "DEMO-101")
        self.assertEqual(row["language"], "vi")
        self.assertIn("Chỉ tính đơn đã hoàn tất.", row["problem"])
        self.assertEqual(len(row["blocker_registry"]["blockers"]), 3)
        with closing(sqlite3.connect(row["repo_or_db_download_link"])) as connection:
            result = connection.execute(row["ground_truth_answer"]).fetchall()
        self.assertCountEqual(result, [("DN", 1), ("HN", 1)])

    def test_reviewed_problem_replaces_raw_jira_description(self):
        annotation = self.annotation_data["tasks"][0]
        annotation.pop("problem_source")
        annotation["problem"] = "Đề báo cáo đã được duyệt."
        self.write_annotations()
        [row] = load_jira_rows(self.export, self.annotations)
        self.assertEqual(row["problem"], annotation["problem"])

    def test_rejects_duplicate_blockers_and_path_traversal(self):
        annotation = self.annotation_data["tasks"][0]
        first, second, _ = annotation["blockers"]
        original_id = second["id"]
        second["id"] = first["id"]
        self.write_annotations()
        with self.assertRaisesRegex(ValueError, "unique lowercase identifier"):
            load_jira_rows(self.export, self.annotations)

        second["id"] = original_id
        annotation["sql"]["database_path"] = "../outside.sqlite"
        self.write_annotations()
        with self.assertRaisesRegex(ValueError, "local relative path"):
            load_jira_rows(self.export, self.annotations)

    def test_rejects_mutating_sql_oracle(self):
        reference = self.pack / "assets" / "expected.sql"
        reference.write_text("DELETE FROM orders RETURNING *;", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "read-only SQLite query"):
            load_jira_rows(self.export, self.annotations)

    def test_swe_adapter_preserves_patch_whitespace(self):
        assets = self.pack / "assets"
        with tarfile.open(assets / "image.tar", mode="w"):
            pass
        patch = "diff --git a/test_app.py b/test_app.py\n@@ -1,2 +1,2 @@\n-old\n+new\n \n"
        (assets / "test.patch").write_bytes(patch.encode("utf-8"))
        annotation = self.annotation_data["tasks"][0]
        annotation["task_type"] = "swe"
        annotation.pop("sql")
        annotation["swe"] = {
            "repository_name": "example/app",
            "image_archive": "assets/image.tar",
            "test_patch": "assets/test.patch",
            "tests_to_pass": ["test_app.py::test_delivery"],
            "test_files": ["test_app.py"],
        }
        self.write_annotations()
        [row] = load_jira_rows(self.export, self.annotations)
        self.assertEqual(row["task_type"], "swe")
        self.assertEqual(row["test_patch"], patch)
        self.assertEqual(row["tests_to_pass"], ["test_app.py::test_delivery"])


if __name__ == "__main__":
    unittest.main()
