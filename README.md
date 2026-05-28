# PERT & CPM Scheduler

A Flask-based web application for project scheduling and critical path analysis using **CPM (Critical Path Method)** and optional **PERT (Program Evaluation and Review Technique)** estimates.

It lets you:

- upload a project task list from Excel
- enter tasks manually in the browser
- calculate ES, EF, LS, LF, and Slack
- identify the critical path
- visualize the dependency network
- generate a Gantt chart
- download the computed results as Excel and PNG files

## Live Demo

Render deployment: [https://pertandcpm.onrender.com/](https://pertandcpm.onrender.com/)

## What This Project Does

This app helps turn a list of project tasks and dependencies into an analyzed schedule.

You provide:

- task names
- task durations or PERT estimates
- task dependencies

The app then:

1. validates the input
2. builds a dependency graph
3. computes the schedule using CPM
4. applies PERT expected-time calculation when `O`, `M`, and `P` values are provided
5. highlights the critical path
6. renders both a dependency network and a Gantt chart

## Features

- Excel `.xlsx` upload support
- Manual task entry from the browser
- Optional PERT estimation using `O`, `M`, and `P`
- CPM forward pass and backward pass calculations
- Critical path detection
- Slack calculation for every task
- Dependency network graph generation
- Gantt chart generation
- Downloadable Excel summary
- Downloadable chart images as PNG
- Built-in sample workbook for quick testing
- Validation for duplicate tasks, missing dependencies, cycles, and invalid values

## Tech Stack

- **Backend:** Flask
- **Data processing:** pandas
- **Graph processing:** networkx
- **Charting:** matplotlib
- **Excel I/O:** openpyxl
- **Production server:** gunicorn
- **Frontend:** Jinja2 templates + Bootstrap 5

## Project Structure

```text
PERT & CPM/
|-- app.py
|-- requirements.txt
|-- test_file.xlsx
|-- core/
|   |-- cpm.py
|   |-- graph.py
|   `-- pert.py
|-- routes/
|   `-- main_routes.py
|-- utils/
|   `-- excel_handler.py
|-- templates/
|   |-- base.html
|   |-- index.html
|   |-- upload.html
|   `-- result.html
`-- static/
    |-- styles.css
    `-- images/
```

## How the App Works

### 1. Input

The application supports three ways to start analysis:

- **Sample run:** uses the bundled `test_file.xlsx`
- **Excel upload:** upload a `.xlsx` file with the required columns
- **Manual entry:** type tasks directly into the form

### 2. PERT Processing

If a task includes:

- `O` = Optimistic time
- `M` = Most likely time
- `P` = Pessimistic time

the app computes the expected duration using:

```text
Expected Time = (O + 4M + P) / 6
```

If PERT values are provided, all three must be present together.

### 3. CPM Scheduling

The app computes:

- **ES**: Earliest Start
- **EF**: Earliest Finish
- **LS**: Latest Start
- **LF**: Latest Finish
- **Slack**: `LS - ES`

Tasks with zero slack are treated as **critical tasks**.

### 4. Output

After processing, the app shows:

- total project duration
- critical path
- full CPM schedule table
- dependency network chart
- Gantt chart
- download links for Excel and PNG outputs

## Excel Input Format

The uploaded workbook must be an `.xlsx` file.

### Required columns

| Column | Description |
| --- | --- |
| `Task` | Unique task/activity name |
| `Duration` | Task duration |
| `Depends_On` | Comma-separated predecessor task names |

### Optional PERT columns

| Column | Description |
| --- | --- |
| `O` | Optimistic estimate |
| `M` | Most likely estimate |
| `P` | Pessimistic estimate |

### Notes

- `Task` names must be unique.
- `Depends_On` can be blank if the task has no predecessor.
- Dependencies should be written as comma-separated task names, for example: `A, B`
- If `Duration` is left empty, the app can derive it from `O`, `M`, and `P`.
- If any one of `O`, `M`, or `P` is provided, the other two must also be provided.

### Example

| Task | Duration | Depends_On | O | M | P |
| --- | --- | --- | --- | --- | --- |
| A | 4 |  |  |  |  |
| B | 6 | A |  |  |  |
| C |  | A | 2 | 3 | 8 |
| D | 5 | B, C |  |  |  |

## Manual Entry

The manual input page supports the same fields as the Excel upload:

- `Task`
- `Duration`
- `Depends_On`
- `O`
- `M`
- `P`

You can:

- enter fixed durations directly
- leave `Duration` empty and use PERT estimates instead
- add more rows dynamically from the UI

## Local Setup

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd "PERT & CPM"
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## Run the App Locally

### Option 1: Run with Python

```bash
python app.py
```

### Option 2: Run with Flask

```bash
flask --app app run
```

The app will be available at:

```text
http://127.0.0.1:5000/
```

## Production / Deployment

This project includes `gunicorn` in `requirements.txt`, which makes it suitable for deployment on platforms like Render.

Typical startup command:

```bash
gunicorn app:app
```

Current live deployment:

- [https://pertandcpm.onrender.com/](https://pertandcpm.onrender.com/)

## Main Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | `GET` | Landing page |
| `/upload` | `GET` | Excel/manual input page |
| `/sample-run` | `POST` | Runs analysis using the bundled sample file |
| `/process` | `POST` | Processes Excel or manual submission |
| `/download/excel/<analysis_id>` | `GET` | Downloads result workbook |
| `/download/graph/<analysis_id>/<chart_kind>` | `GET` | Downloads network or Gantt PNG |

## Output Files

The result page provides downloadable output generated in memory:

- **Excel workbook**
  - `Schedule` sheet
  - `Summary` sheet
- **Network PNG**
- **Gantt PNG**

## Validation Rules

The application checks for common input problems before calculating the schedule.

### Graph and scheduling validation

- missing task name
- duplicate task name
- missing duration when no valid PERT fallback exists
- negative duration
- self-dependency
- dependency on a task that does not exist
- circular dependencies in the task network
- invalid numeric values

### Excel validation

- missing required columns
- unreadable or invalid `.xlsx` file
- blank workbook with no valid task rows

## Sample Data

A sample workbook is included:

```text
test_file.xlsx
```

From the home page, use **Run Sample Test File** to see the full workflow without preparing your own data first.

## Key Modules

### `core/pert.py`

- validates PERT inputs
- computes expected duration
- injects derived duration into task data

### `core/cpm.py`

- performs CPM calculations
- computes project duration
- identifies the critical path
- creates the Gantt chart

### `core/graph.py`

- normalizes task data
- parses dependencies
- builds the directed acyclic graph
- performs topological sorting
- generates the dependency network image

### `utils/excel_handler.py`

- reads Excel input
- validates workbook structure
- exports results back to Excel

### `routes/main_routes.py`

- defines the web routes
- handles sample, upload, manual entry, and downloads
- caches generated analysis outputs in memory for download

## Current Behavior Notes

- Maximum upload size is **10 MB**.
- Downloadable analysis artifacts are stored in an in-memory cache during runtime.
- No database is required.
- The app is best suited for task networks that can be represented as a DAG.

## Possible Improvements

- persistent storage for analysis history
- user authentication
- editable saved projects
- CSV support
- import/export templates
- richer project reporting
- duration units and calendars
- Docker setup
- automated tests

## Requirements

Dependencies listed in `requirements.txt`:

- Flask
- pandas
- networkx
- matplotlib
- openpyxl
- gunicorn

## License

Add your preferred license here if you plan to distribute or open-source the project.
