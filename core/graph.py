import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib
import networkx as nx

matplotlib.use("Agg")

import matplotlib.pyplot as plt


class GraphValidationError(ValueError):
    """Raised when the task dependency graph is invalid."""


EMPTY_DEPENDENCY_TOKENS = {"", "-", "na", "n/a", "null", "none", "nan"}


def parse_dependencies(depends_on: Any) -> List[str]:
    """Parse dependency values into a normalized list of task names."""
    if depends_on is None:
        return []

    if isinstance(depends_on, list):
        raw_dependencies = depends_on
    else:
        depends_text = str(depends_on).strip()
        if not depends_text or depends_text.casefold() in EMPTY_DEPENDENCY_TOKENS:
            return []
        raw_dependencies = depends_text.split(",")

    normalized_dependencies: List[str] = []
    seen_dependencies = set()

    for dependency in raw_dependencies:
        dependency_name = str(dependency).strip()
        if not dependency_name or dependency_name.casefold() in EMPTY_DEPENDENCY_TOKENS:
            continue
        if dependency_name not in seen_dependencies:
            normalized_dependencies.append(dependency_name)
            seen_dependencies.add(dependency_name)

    return normalized_dependencies


def normalize_tasks(tasks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate raw tasks and convert them into a consistent internal structure."""
    normalized_tasks: List[Dict[str, Any]] = []
    seen_tasks = set()

    for index, task in enumerate(tasks, start=1):
        task_name = str(task.get("task", "")).strip()
        if not task_name:
            raise GraphValidationError(f"Row {index} is missing a task name.")

        if task_name in seen_tasks:
            raise GraphValidationError(f"Duplicate task name found: '{task_name}'.")

        duration_value = task.get("duration")
        if duration_value is None or duration_value == "":
            raise GraphValidationError(
                f"Task '{task_name}' is missing a duration or PERT estimate."
            )

        try:
            duration = float(duration_value)
        except (TypeError, ValueError) as exc:
            raise GraphValidationError(
                f"Task '{task_name}' has an invalid duration: {duration_value!r}."
            ) from exc

        if not math.isfinite(duration):
            raise GraphValidationError(
                f"Task '{task_name}' has an invalid duration: {duration_value!r}."
            )

        if duration < 0:
            raise GraphValidationError(f"Task '{task_name}' cannot have a negative duration.")

        dependencies = parse_dependencies(task.get("depends_on"))
        if task_name in dependencies:
            raise GraphValidationError(
                f"Task '{task_name}' cannot depend on itself."
            )

        normalized_tasks.append(
            {
                "task": task_name,
                "duration": duration,
                "depends_on": dependencies,
                "optimistic": task.get("optimistic"),
                "most_likely": task.get("most_likely"),
                "pessimistic": task.get("pessimistic"),
            }
        )
        seen_tasks.add(task_name)

    if not normalized_tasks:
        raise GraphValidationError("Please provide at least one task.")

    return normalized_tasks


def build_dag(tasks: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    """Build a DAG representation from normalized task input."""
    task_map = {task["task"]: task for task in tasks}
    successors = {task["task"]: [] for task in tasks}

    for task in tasks:
        for dependency in task["depends_on"]:
            if dependency not in task_map:
                raise GraphValidationError(
                    f"Task '{task['task']}' references missing dependency '{dependency}'."
                )
            successors[dependency].append(task["task"])

    return task_map, successors


def topological_sort(task_map: Dict[str, Dict[str, Any]]) -> List[str]:
    """Return a topological ordering for the task DAG."""
    in_degree = {task_name: len(task_data["depends_on"]) for task_name, task_data in task_map.items()}
    ready = sorted(task_name for task_name, degree in in_degree.items() if degree == 0)
    order: List[str] = []

    while ready:
        current_task = ready.pop(0)
        order.append(current_task)

        for task_name, task_data in task_map.items():
            if current_task in task_data["depends_on"]:
                in_degree[task_name] -= 1
                if in_degree[task_name] == 0:
                    ready.append(task_name)
                    ready.sort()

    if len(order) != len(task_map):
        raise GraphValidationError("Circular dependency detected in the task network.")

    return order


def build_networkx_graph(task_map: Dict[str, Dict[str, Any]]) -> nx.DiGraph:
    """Create a networkx DiGraph for visualization."""
    graph = nx.DiGraph()

    for task_name in task_map:
        graph.add_node(task_name)

    for task_name, task_data in task_map.items():
        for dependency in task_data["depends_on"]:
            graph.add_edge(dependency, task_name)

    return graph


def draw_network_graph(
    task_map: Dict[str, Dict[str, Any]],
    schedule_map: Dict[str, Dict[str, Any]],
    topological_order: List[str],
    critical_edges: List[Tuple[str, str]],
    output_path: Path,
) -> None:
    """Draw the dependency network and highlight the critical path."""
    graph = build_networkx_graph(task_map)

    levels: Dict[str, int] = {}
    for task_name in topological_order:
        dependencies = task_map[task_name]["depends_on"]
        levels[task_name] = (
            0 if not dependencies else max(levels[dependency] for dependency in dependencies) + 1
        )

    nx.set_node_attributes(graph, levels, "layer")
    positions = nx.multipartite_layout(graph, subset_key="layer", align="horizontal")
    critical_tasks = {
        task_name
        for task_name, metrics in schedule_map.items()
        if abs(metrics["slack"]) < 1e-9
    }

    labels = {
        task_name: (
            f"{task_name}\n"
            f"Dur={task_map[task_name]['duration']:g}\n"
            f"ES={schedule_map[task_name]['es']:g} EF={schedule_map[task_name]['ef']:g}"
        )
        for task_name in graph.nodes
    }

    plt.figure(figsize=(14, 8))
    nx.draw_networkx_edges(
        graph,
        positions,
        edge_color="#a0aec0",
        width=2.0,
        arrows=True,
        arrowsize=18,
        connectionstyle="arc3,rad=0.05",
    )
    nx.draw_networkx_edges(
        graph,
        positions,
        edgelist=critical_edges,
        edge_color="#dc2626",
        width=3.0,
        arrows=True,
        arrowsize=20,
        connectionstyle="arc3,rad=0.05",
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        node_color=[
            "#fecaca" if task_name in critical_tasks else "#bfdbfe" for task_name in graph.nodes
        ],
        edgecolors="#1f2937",
        linewidths=1.5,
        node_size=3200,
    )
    nx.draw_networkx_labels(graph, positions, labels=labels, font_size=9, font_weight="bold")

    plt.title("Project Dependency Network", fontsize=16, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
