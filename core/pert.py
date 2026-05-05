from typing import Any, Dict, List, Optional


def _to_optional_float(value: Any, field_name: str, task_name: str) -> Optional[float]:
    """Convert an optional numeric input into a float."""
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Task '{task_name}' has an invalid {field_name} value: {value!r}."
        ) from exc


def compute_expected_time(optimistic: float, most_likely: float, pessimistic: float) -> float:
    """Compute the PERT expected duration for a task."""
    if optimistic < 0 or most_likely < 0 or pessimistic < 0:
        raise ValueError("PERT values must be non-negative.")

    if optimistic > pessimistic:
        raise ValueError("PERT optimistic value cannot be greater than pessimistic value.")

    return (optimistic + 4 * most_likely + pessimistic) / 6


def apply_pert_estimates(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply PERT duration calculation when O, M, and P values are provided."""
    prepared_tasks: List[Dict[str, Any]] = []

    for index, task in enumerate(tasks, start=1):
        task_name = str(task.get("task") or f"Task {index}").strip()
        optimistic = _to_optional_float(task.get("optimistic"), "optimistic", task_name)
        most_likely = _to_optional_float(task.get("most_likely"), "most likely", task_name)
        pessimistic = _to_optional_float(task.get("pessimistic"), "pessimistic", task_name)

        prepared_task = dict(task)
        prepared_task["optimistic"] = optimistic
        prepared_task["most_likely"] = most_likely
        prepared_task["pessimistic"] = pessimistic

        if any(value is not None for value in (optimistic, most_likely, pessimistic)):
            if None in (optimistic, most_likely, pessimistic):
                raise ValueError(
                    f"Task '{task_name}' must provide O, M, and P together to use PERT."
                )

            prepared_task["duration"] = compute_expected_time(
                optimistic, most_likely, pessimistic
            )

        prepared_tasks.append(prepared_task)

    return prepared_tasks
