import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    send_file,
)

from core.cpm import calculate_cpm, draw_gantt_chart
from core.graph import GraphValidationError, draw_network_graph
from core.pert import apply_pert_estimates
from utils.excel_handler import (
    ExcelValidationError,
    export_results_to_excel,
    read_tasks_from_excel,
)


main_bp = Blueprint("main", __name__)
ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}


@main_bp.route("/")
def index() -> str:
    """Render the landing page."""
    return render_template("index.html", sample_error=None)


@main_bp.route("/upload")
def upload() -> str:
    """Render the upload and manual-entry page."""
    return render_template("upload.html", error=None, manual_rows=_blank_manual_rows())


@main_bp.route("/sample-run", methods=["POST"])
def sample_run() -> Any:
    """Run analysis using the bundled sample Excel file."""
    sample_file = Path(current_app.config["BASE_DIR"]) / "test_file.xlsx"

    try:
        if not sample_file.exists():
            raise FileNotFoundError("Bundled sample file was not found.")

        raw_tasks = read_tasks_from_excel(sample_file)
        return _render_analysis_results(raw_tasks)
    except (FileNotFoundError, ValueError, GraphValidationError, ExcelValidationError) as exc:
        return render_template("index.html", sample_error=str(exc)), 400


@main_bp.route("/process", methods=["POST"])
def process() -> Any:
    """Process uploaded Excel or manual task input."""
    source = request.form.get("source", "").strip().lower()
    manual_rows = _manual_rows_from_form() if source == "manual" else _blank_manual_rows()

    try:
        if source == "excel":
            raw_tasks = _read_excel_submission()
        elif source == "manual":
            raw_tasks = _read_manual_submission()
        else:
            raise ValueError("Please choose either Excel upload or manual task input.")
        return _render_analysis_results(raw_tasks)
    except (ValueError, GraphValidationError, ExcelValidationError) as exc:
        return (
            render_template("upload.html", error=str(exc), manual_rows=manual_rows),
            400,
        )


@main_bp.route("/download/excel/<analysis_id>")
def download_excel(analysis_id: str) -> Any:
    """Download the in-memory Excel result for an analysis."""
    analysis = ANALYSIS_CACHE.get(analysis_id)
    if analysis is None:
        return (
            render_template(
                "upload.html",
                error="The requested analysis is no longer available. Please run it again.",
                manual_rows=_blank_manual_rows(),
            ),
            404,
        )

    return send_file(
        BytesIO(analysis["excel_bytes"]),
        as_attachment=True,
        download_name="schedule_results.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@main_bp.route("/download/graph/<analysis_id>/<chart_kind>")
def download_graph(analysis_id: str, chart_kind: str) -> Any:
    """Download an in-memory PNG graph for an analysis."""
    analysis = ANALYSIS_CACHE.get(analysis_id)
    if analysis is None:
        return (
            render_template(
                "upload.html",
                error="The requested analysis is no longer available. Please run it again.",
                manual_rows=_blank_manual_rows(),
            ),
            404,
        )

    if chart_kind not in {"network", "gantt"}:
        return (
            render_template(
                "upload.html",
                error="The requested chart type is invalid.",
                manual_rows=_blank_manual_rows(),
            ),
            400,
        )

    graph_bytes = analysis[f"{chart_kind}_bytes"]
    return send_file(
        BytesIO(graph_bytes),
        as_attachment=True,
        download_name=f"{chart_kind}_chart.png",
        mimetype="image/png",
    )


def _render_analysis_results(raw_tasks: List[Dict[str, Any]]) -> str:
    """Run scheduling analysis and render the result page."""
    prepared_tasks = apply_pert_estimates(raw_tasks)
    results = calculate_cpm(prepared_tasks)

    network_bytes = draw_network_graph(
        results["task_map"],
        results["schedule_map"],
        results["topological_order"],
        results["critical_edges"],
    )
    gantt_bytes = draw_gantt_chart(results["schedule"], results["project_duration"])
    excel_buffer = export_results_to_excel(results)
    analysis_id = uuid4().hex

    ANALYSIS_CACHE[analysis_id] = {
        "excel_bytes": excel_buffer.getvalue(),
        "network_bytes": network_bytes,
        "gantt_bytes": gantt_bytes,
    }

    return render_template(
        "result.html",
        result=results,
        analysis_id=analysis_id,
        graph_data=_to_base64_image(network_bytes),
        gantt_data=_to_base64_image(gantt_bytes),
    )


def _to_base64_image(image_bytes: bytes) -> str:
    """Convert PNG bytes into a base64 string for inline HTML rendering."""
    return base64.b64encode(image_bytes).decode("utf-8")


def _read_excel_submission() -> List[Dict[str, Any]]:
    """Validate and read uploaded Excel input."""
    uploaded_file = request.files.get("excel_file")

    if uploaded_file is None or not uploaded_file.filename:
        raise ValueError("Please choose an Excel file to upload.")

    if not uploaded_file.filename.lower().endswith(".xlsx"):
        raise ValueError("Only .xlsx Excel files are supported.")

    return read_tasks_from_excel(uploaded_file)


def _read_manual_submission() -> List[Dict[str, Any]]:
    """Extract manual task input from the HTML form."""
    task_names = request.form.getlist("task")
    durations = request.form.getlist("duration")
    dependencies = request.form.getlist("depends_on")
    optimistic_values = request.form.getlist("optimistic")
    most_likely_values = request.form.getlist("most_likely")
    pessimistic_values = request.form.getlist("pessimistic")

    row_count = max(
        len(task_names),
        len(durations),
        len(dependencies),
        len(optimistic_values),
        len(most_likely_values),
        len(pessimistic_values),
    )

    tasks: List[Dict[str, Any]] = []
    for index in range(row_count):
        task = {
            "task": _value_at(task_names, index),
            "duration": _value_at(durations, index),
            "depends_on": _value_at(dependencies, index),
            "optimistic": _value_at(optimistic_values, index),
            "most_likely": _value_at(most_likely_values, index),
            "pessimistic": _value_at(pessimistic_values, index),
        }

        if _row_is_empty(task):
            continue

        tasks.append(task)

    if not tasks:
        raise ValueError("Please provide at least one manual task.")

    return tasks


def _manual_rows_from_form() -> List[Dict[str, str]]:
    """Rebuild manual rows for redisplay after validation errors."""
    task_names = request.form.getlist("task")
    durations = request.form.getlist("duration")
    dependencies = request.form.getlist("depends_on")
    optimistic_values = request.form.getlist("optimistic")
    most_likely_values = request.form.getlist("most_likely")
    pessimistic_values = request.form.getlist("pessimistic")

    row_count = max(
        len(task_names),
        len(durations),
        len(dependencies),
        len(optimistic_values),
        len(most_likely_values),
        len(pessimistic_values),
        5,
    )

    rows: List[Dict[str, str]] = []
    for index in range(row_count):
        rows.append(
            {
                "task": _value_at(task_names, index),
                "duration": _value_at(durations, index),
                "depends_on": _value_at(dependencies, index),
                "optimistic": _value_at(optimistic_values, index),
                "most_likely": _value_at(most_likely_values, index),
                "pessimistic": _value_at(pessimistic_values, index),
            }
        )

    return rows


def _blank_manual_rows(count: int = 5) -> List[Dict[str, str]]:
    """Create blank form rows for manual input."""
    return [
        {
            "task": "",
            "duration": "",
            "depends_on": "",
            "optimistic": "",
            "most_likely": "",
            "pessimistic": "",
        }
        for _ in range(count)
    ]


def _value_at(values: List[str], index: int) -> str:
    """Safely read a form value by index."""
    if index >= len(values):
        return ""
    return values[index].strip()


def _row_is_empty(task: Dict[str, str]) -> bool:
    """Check whether a manual form row is empty."""
    return not any(str(value).strip() for value in task.values())
