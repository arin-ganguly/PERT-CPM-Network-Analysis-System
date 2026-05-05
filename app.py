from pathlib import Path

from flask import Flask

from routes.main_routes import main_bp


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "project-scheduling-secret-key"
    app.config["BASE_DIR"] = BASE_DIR
    app.config["OUTPUT_DIR"] = OUTPUT_DIR
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    app.register_blueprint(main_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
