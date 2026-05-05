from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from core.graph import build_dag, normalize_tasks, topological_sort


def calculate_cpm(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run CPM analysis for the provided task list."""
    normalized_tasks = normalize_tasks(tasks)
    task_map, successors = build_dag(normalized_tasks)
    topological_order = topological_sort(task_map)

    schedule_map: Dict[str, Dict[str, float]] = {}

    for task_name in topological_order:
        dependencies = task_map[task_name]["depends_on"]
        earliest_start = 0.0
        if dependencies:
            earliest_start = max(schedule_map[dependency]["ef"] for dependency in dependencies)

        duration = task_map[task_name]["duration"]
        earliest_finish = earliest_start + duration
        schedule_map[task_name] = {"es": earliest_start, "ef": earliest_finish}

    project_duration = max(metrics["ef"] for metrics in schedule_map.values())

    for task_name in reversed(topological_order):
        task_successors = successors[task_name]
        latest_finish = (
            project_duration
            if not task_successors
            else min(schedule_map[successor]["ls"] for successor in task_successors)
        )

        latest_start = latest_finish - task_map[task_name]["duration"]
        slack = latest_start - schedule_map[task_name]["es"]

        schedule_map[task_name]["ls"] = latest_start
        schedule_map[task_name]["lf"] = latest_finish
        schedule_map[task_name]["slack"] = slack

    critical_path = [
        task_name
        for task_name in topological_order
        if abs(schedule_map[task_name]["slack"]) < 1e-9
    ]
    critical_edges = _find_critical_edges(task_map, schedule_map, successors)
    schedule_rows = _build_schedule_rows(task_map, schedule_map, topological_order)

    return {
        "task_map": task_map,
        "schedule_map": schedule_map,
        "schedule": schedule_rows,
        "successors": successors,
        "topological_order": topological_order,
        "critical_path": critical_path,
        "critical_edges": critical_edges,
        "project_duration": project_duration,
    }


def _find_critical_edges(
    task_map: Dict[str, Dict[str, Any]],
    schedule_map: Dict[str, Dict[str, float]],
    successors: Dict[str, List[str]],
) -> List[Tuple[str, str]]:
    """Find edges that belong to the critical path."""
    critical_edges: List[Tuple[str, str]] = []

    for task_name, task_successors in successors.items():
        for successor in task_successors:
            task_metrics = schedule_map[task_name]
            successor_metrics = schedule_map[successor]

            if (
                abs(task_metrics["slack"]) < 1e-9
                and abs(successor_metrics["slack"]) < 1e-9
                and abs(task_metrics["ef"] - successor_metrics["es"]) < 1e-9
            ):
                critical_edges.append((task_name, successor))

    return critical_edges


def _build_schedule_rows(
    task_map: Dict[str, Dict[str, Any]],
    schedule_map: Dict[str, Dict[str, float]],
    topological_order: List[str],
) -> List[Dict[str, Any]]:
    """Transform schedule metrics into template-friendly row dictionaries."""
    rows: List[Dict[str, Any]] = []

    for task_name in topological_order:
        task_details = task_map[task_name]
        metrics = schedule_map[task_name]
        rows.append(
            {
                "task": task_name,
                "duration": task_details["duration"],
                "depends_on": ", ".join(task_details["depends_on"]) or "-",
                "es": metrics["es"],
                "ef": metrics["ef"],
                "ls": metrics["ls"],
                "lf": metrics["lf"],
                "slack": metrics["slack"],
                "critical": abs(metrics["slack"]) < 1e-9,
            }
        )

    return rows


def draw_gantt_chart(schedule_rows: List[Dict[str, Any]], project_duration: float, output_path: Path) -> None:
    """Generate a Gantt chart image for the project schedule."""
    figure_height = max(4, len(schedule_rows) * 0.65)
    fig, ax = plt.subplots(figsize=(14, figure_height))

    y_positions = list(range(len(schedule_rows)))
    bar_colors = ["#dc2626" if row["critical"] else "#2563eb" for row in schedule_rows]

    bars = ax.barh(
        y_positions,
        [row["duration"] for row in schedule_rows],
        left=[row["es"] for row in schedule_rows],
        color=bar_colors,
        edgecolor="#1f2937",
        alpha=0.9,
    )

    for bar, row in zip(bars, schedule_rows):
        center_x = row["es"] + (row["duration"] / 2 if row["duration"] else 0.1)
        center_y = bar.get_y() + bar.get_height() / 2
        ax.text(
            center_x,
            center_y,
            f"{row['es']:g}-{row['ef']:g}",
            ha="center",
            va="center",
            color="white",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels([row["task"] for row in schedule_rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(project_duration, 1) * 1.1)
    ax.set_xlabel("Timeline")
    ax.set_ylabel("Tasks")
    ax.set_title("Project Gantt Chart", fontsize=16, fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
