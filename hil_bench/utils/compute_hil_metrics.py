"""Compute HiL-Bench clarification scores from the ask_human server logs."""

from __future__ import annotations

from typing import Any, TypedDict


class GlobalMetrics(TypedDict):
    instances: dict[str, dict[str, Any]]
    precision: float
    recall: float
    ask_f1: float
    n_questions: int
    n_relevant_questions: int
    n_blockers_present: int
    n_blockers_discovered: int


def calculate_ask_scores(
    questions: int, relevant: int, blockers: int, resolved: int
) -> dict[str, float]:
    precision = relevant / questions if questions else 0.0
    recall = resolved / blockers if blockers else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "ask_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def compute_hil_metrics(logs: dict[str, dict[str, Any]]) -> GlobalMetrics:
    """Score per-attempt logs, including attempts that did not ask any questions."""
    instances = {}
    total_questions = 0
    total_relevant_questions = 0
    total_blockers_present = 0
    total_blockers_discovered = 0
    for instance_id, log_data in logs.items():
        n_blockers = int(log_data["n_blockers"])
        # Older logs used "entries" for the raw question records.
        questions = log_data.get("questions") or log_data.get("entries", [])
        registered = log_data.get("blockers")
        matched = [
            name
            for question in questions
            if (name := question.get("blocker_name")) and (not registered or name in registered)
        ]
        n_questions = len(questions)
        n_relevant = len(matched)
        n_discovered = len(set(matched))
        instances[instance_id] = {
            **log_data,
            **calculate_ask_scores(n_questions, n_relevant, n_blockers, n_discovered),
            "n_questions": n_questions,
            "n_relevant_questions": n_relevant,
            "n_blockers_discovered": n_discovered,
            "all_blockers_resolved": n_blockers > 0 and n_discovered == n_blockers,
        }

        total_questions += n_questions
        total_relevant_questions += n_relevant
        total_blockers_present += n_blockers
        total_blockers_discovered += n_discovered

    scores = calculate_ask_scores(
        total_questions, total_relevant_questions, total_blockers_present, total_blockers_discovered
    )
    return {
        "instances": instances,
        "precision": scores["precision"],
        "recall": scores["recall"],
        "ask_f1": scores["ask_f1"],
        "n_questions": total_questions,
        "n_relevant_questions": total_relevant_questions,
        "n_blockers_present": total_blockers_present,
        "n_blockers_discovered": total_blockers_discovered,
    }


def apply_ask_human_gate(metrics: dict[str, Any], hil_metrics: GlobalMetrics) -> None:
    """Retain verifier correctness and require registered blockers for benchmark pass."""
    artifact_resolved = metrics.get("artifact_resolved_instances", metrics["resolved_instances"])
    instances = hil_metrics["instances"]
    resolved = [
        instance_id
        for instance_id in artifact_resolved
        if instances.get(instance_id, {}).get("all_blockers_resolved")
    ]
    total = metrics["total_instances"]
    metrics.update(
        artifact_resolved_instances=artifact_resolved,
        artifact_pass_at_1_count=len(artifact_resolved),
        artifact_pass_at_1_rate=100 * len(artifact_resolved) / total if total else 0.0,
        resolved_instances=resolved,
        pass_at_1_count=len(resolved),
        pass_at_1_rate=100 * len(resolved) / total if total else 0.0,
    )


def print_hil_metrics_summary(metrics: GlobalMetrics):
    """Print a summary of HIL metrics."""
    print()
    print("=" * 80)
    print("HIL-Bench Metrics Summary")
    print("=" * 80)

    print(f"# questions asked:\t{metrics['n_questions']}")
    print(f"# relevant questions:\t{metrics['n_relevant_questions']}")
    print(f"# blockers:\t\t{metrics['n_blockers_present']}")
    print(f"# blockers discovered:\t{metrics['n_blockers_discovered']}")

    print()
    print(f"Ask Precision:\t{metrics['precision']:.2%}")
    print(f"Ask Recall:\t{metrics['recall']:.2%}")
    print(f"Ask F1 Score:\t{metrics['ask_f1']:.2%}")
    print("=" * 80)
    print()
