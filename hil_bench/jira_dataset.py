"""Validate reviewed Vietnamese Jira tasks and adapt them to HiL-Bench rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any


ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*")
BLOCKER_ID = re.compile(r"[a-z][a-z0-9_-]*")
DATABASE_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
BLOCKER_TYPES = {"missing_information", "ambiguity", "contradiction"}
ADF_BLOCKS = {"blockquote", "codeBlock", "heading", "listItem", "paragraph", "tableRow"}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _strings(value: Any, label: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"{label} must be {'a nonempty' if required else 'an'} array of strings")
    return [_text(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _adf_text(value: Any, label: str) -> str:
    node = _object(value, label)
    node_type = node.get("type")
    if not isinstance(node_type, str):
        raise ValueError(f"{label} contains an ADF node without a type")
    if node_type == "text":
        text = node.get("text")
        if not isinstance(text, str):
            raise ValueError(f"{label} contains an ADF text node without text")
        return text
    if node_type == "hardBreak":
        return "\n"
    if node_type == "mention":
        return _text(_object(node.get("attrs"), label).get("text"), label)
    children = node.get("content", [])
    if not isinstance(children, list):
        raise ValueError(f"{label} contains a node with invalid ADF content")
    text = "".join(_adf_text(child, label) for child in children)
    return text + "\n" if node_type in ADF_BLOCKS else text


def _problem_text(value: Any, label: str) -> str:
    if isinstance(value, dict) and value.get("type") == "doc" and value.get("version") == 1:
        value = _adf_text(value, label)
    return _text(value, label)


def _issue_key(value: Any, label: str) -> str:
    key = _text(value, label)
    if not ISSUE_KEY.fullmatch(key) or "__" in key:
        raise ValueError(f"{label} must be a Jira issue key such as DEMO-101")
    return key


def _read_issues(path: Path) -> dict[str, dict[str, Any]]:
    export = _read_json(path)
    if isinstance(export, dict):
        export = export.get("issues", [export] if "key" in export else None)
    if not isinstance(export, list) or not export:
        raise ValueError("Jira export must contain at least one issue")
    issues = {}
    for index, issue in enumerate(export):
        issue = _object(issue, f"issues[{index}]")
        key = _issue_key(issue.get("key"), f"issues[{index}].key")
        if key in issues:
            raise ValueError(f"Duplicate Jira issue key: {key}")
        issues[key] = issue
    return issues


def _problem(annotation: dict[str, Any], issue: dict[str, Any]) -> str:
    source = annotation.get("problem_source")
    if source is None:
        return _problem_text(annotation.get("problem"), "problem")
    if source != "jira_description" or "problem" in annotation:
        raise ValueError("Set problem or problem_source='jira_description', with one source per task")
    fields = _object(issue.get("fields"), "Jira issue fields")
    return _problem_text(fields.get("description"), "Jira issue description")


def _blockers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 3 <= len(value) <= 5:
        raise ValueError("blockers must contain 3 to 5 reviewed entries")
    blockers = []
    seen_ids: set[str] = set()
    seen_descriptions: set[str] = set()
    seen_questions: set[str] = set()
    for index, value in enumerate(value):
        label = f"blockers[{index}]"
        entry = _object(value, label)
        blocker_id = _text(entry.get("id"), f"{label}.id")
        if not BLOCKER_ID.fullmatch(blocker_id) or blocker_id in seen_ids:
            raise ValueError(f"{label}.id must be a unique lowercase identifier")
        blocker_type = _text(entry.get("type"), f"{label}.type")
        if blocker_type not in BLOCKER_TYPES:
            raise ValueError(f"{label}.type must be one of {', '.join(sorted(BLOCKER_TYPES))}")
        description = _text(entry.get("description"), f"{label}.description")
        description_key = " ".join(description.casefold().split())
        if description_key in seen_descriptions:
            raise ValueError(f"{label}.description duplicates another blocker")
        questions = _strings(entry.get("example_questions"), f"{label}.example_questions", required=True)
        for question in questions:
            question_key = " ".join(question.casefold().split())
            if question_key in seen_questions:
                raise ValueError(f"{label}.example_questions contains a duplicate question")
            seen_questions.add(question_key)
        blockers.append(
            {
                "id": blocker_id,
                "type": blocker_type,
                "description": description,
                "example_questions": questions,
                "resolution": _text(entry.get("resolution"), f"{label}.resolution"),
            }
        )
        seen_ids.add(blocker_id)
        seen_descriptions.add(description_key)
    return blockers


def _relative_path(value: Any, label: str) -> PurePosixPath:
    name = _text(value, label).replace("\\", "/")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or ".." in path.parts or ":" in name:
        raise ValueError(f"{label} must be a local relative path")
    return path


def _artifact(root: Path, value: Any, label: str, extensions: tuple[str, ...]) -> Path:
    relative_path = _relative_path(value, label)
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"{label} must reference an existing local file under {root}: {relative_path}")
    if not path.name.lower().endswith(extensions):
        raise ValueError(f"{label} must use one of these extensions: {', '.join(extensions)}")
    return path


def _check_schema_csv(path: Path, required_fields: set[str]) -> None:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        fields = set(csv.DictReader(stream).fieldnames or ())
    if missing := required_fields - fields:
        raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")


def _check_sql_query(database: Path, query: str) -> None:
    # Compile the oracle without scanning rows or allowing access to other databases.
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorize(action, _detail, function, _database, _trigger):
        if action not in allowed or (action == sqlite3.SQLITE_FUNCTION and function == "load_extension"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.set_authorizer(authorize)
            connection.execute(f"EXPLAIN QUERY PLAN {query}")
    except sqlite3.Error as exc:
        raise ValueError(f"ground_truth_path must contain one read-only SQLite query: {exc}") from exc


def _sql_fields(value: Any, root: Path) -> dict[str, Any]:
    sql = _object(value, "sql")
    database_name = _text(sql.get("database_name"), "sql.database_name")
    if not DATABASE_NAME.fullmatch(database_name):
        raise ValueError("sql.database_name must be a filename-safe identifier")
    database = _artifact(root, sql.get("database_path"), "sql.database_path", (".sqlite", ".sqlite3", ".db"))
    schema_paths = [
        _artifact(root, name, "sql.schema_paths", (".csv",))
        for name in _strings(sql.get("schema_paths"), "sql.schema_paths", required=True)
    ]
    names = [path.name.casefold() for path in schema_paths]
    if len(names) != len(set(names)) or not any(path.name == "table_descriptions.csv" for path in schema_paths):
        raise ValueError("sql.schema_paths must include table_descriptions.csv and use distinct filenames")
    for path in schema_paths:
        columns = (
            {"table_name", "table_description"}
            if path.name == "table_descriptions.csv"
            else {"original_column_name", "combined_description", "data_format"}
        )
        _check_schema_csv(path, columns)
    query_path = _artifact(root, sql.get("ground_truth_path"), "sql.ground_truth_path", (".sql",))
    query = _text(query_path.read_text(encoding="utf-8-sig"), "reference query")
    _check_sql_query(database, query)
    return {
        "repo_or_db_name": database_name,
        "repo_or_db_download_link": str(database),
        "schema_descriptions_download_links": [str(path) for path in schema_paths],
        "ground_truth_answer": query,
        "business_info": _strings(sql.get("business_info", []), "sql.business_info"),
    }


def _swe_fields(value: Any, root: Path) -> dict[str, Any]:
    swe = _object(value, "swe")
    archive = _artifact(root, swe.get("image_archive"), "swe.image_archive", (".tar", ".tar.gz", ".tar.zst"))
    test_patch = _artifact(root, swe.get("test_patch"), "swe.test_patch", (".patch", ".diff"))
    ground_truth_patch = ""
    if "ground_truth_patch" in swe:
        patch = _artifact(root, swe["ground_truth_patch"], "swe.ground_truth_patch", (".patch", ".diff"))
        ground_truth_patch = _read_patch(patch, "ground truth patch")
    test_files = _strings(swe.get("test_files", []), "swe.test_files")
    return {
        "repo_or_db_name": _text(swe.get("repository_name"), "swe.repository_name"),
        "repo_or_db_download_link": str(archive),
        "ground_truth_answer": ground_truth_patch,
        "test_patch": _read_patch(test_patch, "test patch"),
        "tests_to_pass": _strings(swe.get("tests_to_pass"), "swe.tests_to_pass", required=True),
        "test_files": [_relative_path(name, "swe.test_files").as_posix() for name in test_files],
    }


def _read_patch(path: Path, label: str) -> str:
    # Patch whitespace is significant, including the prefix for a blank context line.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        text = stream.read()
    _text(text, label)
    return text


def load_jira_rows(jira_export: Path, annotations: Path) -> list[dict[str, Any]]:
    """Join reviewed annotations to a local Jira export and prepare runner inputs."""
    issues = _read_issues(jira_export)
    pack = _object(_read_json(annotations), "annotation pack")
    annotations_list = pack.get("tasks")
    if pack.get("language") != "vi" or not isinstance(annotations_list, list) or not annotations_list:
        raise ValueError("Annotation pack must have language='vi' and a nonempty tasks array")
    asset_root = annotations.resolve().parent
    rows = []
    seen_keys: set[str] = set()
    for index, task in enumerate(annotations_list):
        task = _object(task, f"tasks[{index}]")
        key = _issue_key(task.get("key"), f"tasks[{index}].key")
        if key in seen_keys or key not in issues:
            raise ValueError(f"{key}: task must refer to one Jira issue and have exactly one annotation")
        try:
            task_type = _text(task.get("task_type"), "task_type").lower()
            if task_type not in {"sql", "swe"}:
                raise ValueError("task_type must be 'sql' or 'swe'")
            problem = _problem(task, issues[key])
            blockers = _blockers(task.get("blockers"))
            artifact_fields = (
                _sql_fields(task.get("sql"), asset_root)
                if task_type == "sql"
                else _swe_fields(task.get("swe"), asset_root)
            )
        except (OSError, ValueError, RecursionError) as exc:
            raise ValueError(f"{key}: {exc}") from exc
        seen_keys.add(key)
        rows.append(
            {
                "task_id": key,
                "uid": key,
                "task_type": task_type,
                "language": "vi",
                "problem": problem,
                "blocker_registry": {"blockers": blockers},
                **artifact_fields,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a reviewed Vietnamese HiL-Bench Jira pack")
    parser.add_argument("jira_export", type=Path)
    parser.add_argument("annotations", type=Path)
    args = parser.parse_args()
    try:
        rows = load_jira_rows(args.jira_export, args.annotations)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    counts = Counter(row["task_type"] for row in rows)
    print(f"Validated {len(rows)} Jira task(s): {counts['swe']} SWE, {counts['sql']} SQL.")


if __name__ == "__main__":
    main()
