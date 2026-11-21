"""Evaluate the configured judge against reviewed Vietnamese questions."""

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from .jira_dataset import load_jira_rows


class CalibrationCase(NamedTuple):
    task_id: str
    question: str
    expected_blocker: str | None


def load_cases(path: Path, blocker_ids: dict[str, set[str]]) -> list[CalibrationCase]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError("Calibration file must contain a non-empty list of cases")

    cases = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict) or not {"task_id", "question", "expected_blocker"} <= item.keys():
            raise ValueError(f"Calibration case {index} needs task_id, question and expected_blocker")
        task_id, question, expected = item["task_id"], item["question"], item["expected_blocker"]
        if not isinstance(task_id, str) or task_id not in blocker_ids:
            raise ValueError(f"Calibration case {index} references an unknown task")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Calibration case {index} needs a non-empty question")
        if expected is not None and (not isinstance(expected, str) or expected not in blocker_ids[task_id]):
            raise ValueError(f"Calibration case {index} references an unknown blocker")
        cases.append(CalibrationCase(task_id, question, expected))
    return cases


def evaluate_cases(
    cases: list[CalibrationCase],
    classify: Callable[[str, str], tuple[str | None, bool]],
) -> dict:
    results = []
    counts = {"match": 0, "no_match": 0}
    correct = counts.copy()
    for index, case in enumerate(cases, start=1):
        predicted, judge_error = classify(case.task_id, case.question)
        is_correct = not judge_error and predicted == case.expected_blocker
        kind = "match" if case.expected_blocker is not None else "no_match"
        counts[kind] += 1
        correct[kind] += int(is_correct)
        results.append({
            "case": index,
            "task_id": case.task_id,
            "expected_blocker": case.expected_blocker,
            "predicted_blocker": predicted,
            "correct": is_correct,
            "judge_error": judge_error,
        })
    return {
        "total": len(cases),
        "accuracy": sum(correct.values()) / len(cases),
        "match_accuracy": correct["match"] / counts["match"] if counts["match"] else None,
        "no_match_accuracy": correct["no_match"] / counts["no_match"] if counts["no_match"] else None,
        "judge_errors": sum(result["judge_error"] for result in results),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jira-export", type=Path, required=True)
    parser.add_argument("--jira-annotations", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--judge-config", type=Path, required=True)
    parser.add_argument("--min-accuracy", type=float, help="Optional acceptance threshold between 0 and 1.")
    args = parser.parse_args()
    if args.min_accuracy is not None and not 0 <= args.min_accuracy <= 1:
        parser.error("--min-accuracy must be between 0 and 1")

    try:
        rows = load_jira_rows(args.jira_export, args.jira_annotations)
        registries = {row["task_id"]: row["blocker_registry"] for row in rows}
        cases = load_cases(args.cases, {
            task_id: {blocker["id"] for blocker in registry["blockers"]}
            for task_id, registry in registries.items()
        })

        from dotenv import load_dotenv

        from .ask_human_server import CANT_ANSWER, AskHuman, parse_blocker_registry
        from .utils.config_mapping import load_and_apply_judge_config

        load_dotenv()
        load_and_apply_judge_config(args.judge_config)
        judges = {
            task_id: AskHuman(parse_blocker_registry(registries[task_id]))
            for task_id in dict.fromkeys(case.task_id for case in cases)
        }
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    def classify(task_id: str, question: str) -> tuple[str | None, bool]:
        judge = judges[task_id]
        response = judge.ask_human(question)
        return judge.log["questions"][-1]["blocker_name"], response == CANT_ANSWER

    report = evaluate_cases(cases, classify)
    print(json.dumps(report, indent=2))
    if report["judge_errors"]:
        return 2
    return int(args.min_accuracy is not None and report["accuracy"] < args.min_accuracy)


if __name__ == "__main__":
    raise SystemExit(main())
