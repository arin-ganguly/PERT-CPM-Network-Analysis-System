import logging
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from core.pert import compute_expected_time


logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"Task", "Duration", "Depends_On"}
OPTIONAL_COLUMNS = {"O", "M", "P"}
EMPTY_TOKENS = {"", "-", "na", "n/a", "null", "none"}


class ExcelValidationError(ValueError):
    """Raised when uploaded Excel content is invalid."""


def parse_dependencies(value: Any) -> List[str]:
    """Parse a dependency cell into a clean list of task names."""
    if _is_empty_value(value):
        return []

    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = str(value).split(",")

    dependencies: List[str] = []
    seen_dependencies = set()

    for item in raw_items:
        if _is_empty_value(item):
            continue

        dependency_name = str(item).strip()
        if not dependency_name:
            continue

        dependency_key = dependency_name.casefold()
        if dependency_key in EMPTY_TOKENS or dependency_name in seen_dependencies:
            continue

        dependencies.append(dependency_name)
        seen_dependencies.add(dependency_name)

    logger.debug("Parsed dependencies from %r to %s", value, dependencies)
    return dependencies


def read_tasks_from_excel(file_stream: Any) -> List[Dict[str, Any]]:
    """Read, clean, and validate task definitions from an Excel file."""
    try:
        dataframe = pd.read_excel(
            file_stream,
            dtype=object,
            keep_default_na=False,
        )
    except ImportError as exc:
        raise ExcelValidationError(
            "Excel support requires the 'openpyxl' package for .xlsx files."
        ) from exc
    except Exception as exc:
        raise ExcelValidationError("Unable to read the uploaded Excel file.") from exc

    dataframe = _normalize_dataframe(dataframe)
    _validate_required_columns(dataframe.columns)

    has_pert_columns = OPTIONAL_COLUMNS.issubset(set(dataframe.columns))
    tasks: List[Dict[str, Any]] = []

    for row_number, row in enumerate(dataframe.to_dict(orient="records"), start=2):
        if _is_blank_row(row.values()):
            logger.debug("Skipping blank Excel row %s", row_number)
            continue

        task_name = _parse_task_name(row.get("Task"), row_number)
        optimistic = _parse_optional_float(
            row.get("O") if "O" in dataframe.columns else None,
            "O",
            task_name,
        )
        most_likely = _parse_optional_float(
            row.get("M") if "M" in dataframe.columns else None,
            "M",
            task_name,
        )
        pessimistic = _parse_optional_float(
            row.get("P") if "P" in dataframe.columns else None,
            "P",
            task_name,
        )
        duration = _parse_duration(
            row.get("Duration"),
            task_name,
            optimistic=optimistic,
            most_likely=most_likely,
            pessimistic=pessimistic,
            allow_pert_fallback=has_pert_columns,
        )

        task_record = {
            "task": task_name,
            "duration": duration,
            "depends_on": parse_dependencies(row.get("Depends_On")),
            "optimistic": optimistic,
            "most_likely": most_likely,
            "pessimistic": pessimistic,
        }
        tasks.append(task_record)
        logger.debug("Parsed Excel task on row %s: %s", row_number, task_record)

    if not tasks:
        raise ExcelValidationError("The uploaded Excel file does not contain any tasks.")

    _validate_tasks(tasks)
    return tasks


def export_results_to_excel(results: Dict[str, Any], output_path: Path) -> None:
    """Export computed schedule results to an Excel workbook."""
    schedule_rows = [
        {
            "Task": row["task"],
            "Duration": row["duration"],
            "Depends_On": row["depends_on"],
            "ES": row["es"],
            "EF": row["ef"],
            "LS": row["ls"],
            "LF": row["lf"],
            "Slack": row["slack"],
            "Critical": "Yes" if row["critical"] else "No",
        }
        for row in results["schedule"]
    ]

    schedule_frame = pd.DataFrame(schedule_rows)
    summary_frame = pd.DataFrame(
        [
            {
                "Project_Duration": results["project_duration"],
                "Critical_Path": " -> ".join(results["critical_path"]),
            }
        ]
    )

    try:
        with pd.ExcelWriter(output_path) as writer:
            schedule_frame.to_excel(writer, sheet_name="Schedule", index=False)
            summary_frame.to_excel(writer, sheet_name="Summary", index=False)
    except ImportError as exc:
        raise ExcelValidationError(
            "Excel export requires the 'openpyxl' package for .xlsx files."
        ) from exc


def _normalize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and replace scalar NaN values with None."""
    normalized = dataframe.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    normalized = normalized.apply(lambda column: column.map(_normalize_cell_value))
    logger.debug("Normalized Excel columns: %s", list(normalized.columns))
    return normalized


def _validate_required_columns(columns: Iterable[str]) -> None:
    """Validate that required Excel columns are present."""
    missing_columns = REQUIRED_COLUMNS - set(columns)
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ExcelValidationError(
            f"Excel file is missing required columns: {missing_text}."
        )


def _validate_tasks(tasks: List[Dict[str, Any]]) -> None:
    """Validate parsed tasks before returning them to CPM processing."""
    seen_tasks = set()

    for task in tasks:
        task_name = task["task"]
        if task_name in seen_tasks:
            raise ExcelValidationError(f"Duplicate task found: '{task_name}'.")
        seen_tasks.add(task_name)

    for task in tasks:
        task_name = task["task"]
        duration = task["duration"]
        if not isinstance(duration, float) or not math.isfinite(duration):
            raise ExcelValidationError(f"Task '{task_name}' has invalid duration.")

        for dependency in task["depends_on"]:
            if dependency == task_name:
                raise ExcelValidationError(
                    f"Task '{task_name}' cannot depend on itself."
                )
            if dependency not in seen_tasks:
                raise ExcelValidationError(
                    f"Task '{task_name}' depends on unknown task '{dependency}'."
                )


def _parse_task_name(value: Any, row_number: int) -> str:
    """Parse and validate a task name cell."""
    if _is_empty_value(value):
        raise ExcelValidationError(f"Row {row_number} is missing a task name.")

    task_name = str(value).strip()
    if not task_name or task_name.casefold() in EMPTY_TOKENS:
        raise ExcelValidationError(f"Row {row_number} has an invalid task name.")

    return task_name


def _parse_duration(
    value: Any,
    task_name: str,
    optimistic: Optional[float],
    most_likely: Optional[float],
    pessimistic: Optional[float],
    allow_pert_fallback: bool,
) -> float:
    """Parse duration as a finite float, with optional PERT fallback."""
    if _is_empty_value(value):
        if allow_pert_fallback and any(
            estimate is not None for estimate in (optimistic, most_likely, pessimistic)
        ):
            if None in (optimistic, most_likely, pessimistic):
                raise ExcelValidationError(
                    f"Task '{task_name}' must provide O, M, and P together when Duration is empty."
                )
            logger.debug("Using PERT fallback duration for task %s", task_name)
            return compute_expected_time(optimistic, most_likely, pessimistic)

        raise ExcelValidationError(f"Task '{task_name}' has invalid duration: missing value.")

    duration_text = str(value).strip() if isinstance(value, str) else value

    try:
        duration = float(duration_text)
    except (TypeError, ValueError) as exc:
        raise ExcelValidationError(
            f"Task '{task_name}' has invalid duration: {value!r}."
        ) from exc

    if not math.isfinite(duration):
        raise ExcelValidationError(
            f"Task '{task_name}' has invalid duration: {value!r}."
        )

    return duration


def _parse_optional_float(value: Any, field_name: str, task_name: str) -> Optional[float]:
    """Parse an optional numeric field as a finite float."""
    if _is_empty_value(value):
        return None

    numeric_text = str(value).strip() if isinstance(value, str) else value

    try:
        numeric_value = float(numeric_text)
    except (TypeError, ValueError) as exc:
        raise ExcelValidationError(
            f"Task '{task_name}' has invalid {field_name} value: {value!r}."
        ) from exc

    if not math.isfinite(numeric_value):
        raise ExcelValidationError(
            f"Task '{task_name}' has invalid {field_name} value: {value!r}."
        )

    return numeric_value


def _normalize_cell_value(value: Any) -> Any:
    """Normalize individual Excel cell values into plain Python scalars."""
    if _is_scalar_nan(value):
        return None

    if isinstance(value, str):
        stripped_value = value.strip()
        return stripped_value

    return value


def _is_blank_row(values: Iterable[Any]) -> bool:
    """Check whether a row contains any meaningful data."""
    for value in values:
        if not _is_empty_value(value):
            return False
    return True


def _is_empty_value(value: Any) -> bool:
    """Determine whether a cell should be treated as empty."""
    if _is_scalar_nan(value):
        return True

    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().casefold() in EMPTY_TOKENS

    return False


def _is_scalar_nan(value: Any) -> bool:
    """Safely identify scalar pandas/NumPy NaN-like values."""
    if isinstance(value, (list, tuple, set, dict)):
        return False

    try:
        return bool(pd.isna(value))
    except TypeError:
        return False
