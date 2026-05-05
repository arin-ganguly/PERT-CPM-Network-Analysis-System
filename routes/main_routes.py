from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    send_from_directory,
    session,
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


@main_bp.route("/download")
def download() -> Any:
    """Download the latest generated Excel output."""
    filename = session.get("download_file")
    if not filename:
        return render_template(
            "upload.html",
            error="No processed result is available for download yet.",
            manual_rows=_blank_manual_rows(),
        ), 404

    return send_from_directory(
        current_app.config["OUTPUT_DIR"],
        filename,
        as_attachment=True,
    )


@main_bp.route("/outputs/<path:filename>")
def output_file(filename: str) -> Any:
    """Serve generated output images from the outputs directory."""
    return send_from_directory(current_app.config["OUTPUT_DIR"], filename)


def _render_analysis_results(raw_tasks: List[Dict[str, Any]]) -> str:
    """Run scheduling analysis and render the result page."""
    prepared_tasks = apply_pert_estimates(raw_tasks)
    results = calculate_cpm(prepared_tasks)

    output_dir = Path(current_app.config["OUTPUT_DIR"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    graph_filename = f"network_{timestamp}.png"
    gantt_filename = f"gantt_{timestamp}.png"
    excel_filename = f"schedule_{timestamp}.xlsx"

    draw_network_graph(
        results["task_map"],
        results["schedule_map"],
        results["topological_order"],
        results["critical_edges"],
        output_dir / graph_filename,
    )
    draw_gantt_chart(results["schedule"], results["project_duration"], output_dir / gantt_filename)
    export_results_to_excel(results, output_dir / excel_filename)

    session["download_file"] = excel_filename

    return render_template(
        "result.html",
        result=results,
        graph_filename=graph_filename,
        gantt_filename=gantt_filename,
    )


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
