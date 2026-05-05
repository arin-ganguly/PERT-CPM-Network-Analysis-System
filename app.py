from pathlib import Path

from flask import Flask

from routes.main_routes import main_bp


BASE_DIR = Path(__file__).resolve().parent


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "project-scheduling-secret-key"
    app.config["BASE_DIR"] = BASE_DIR
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    app.register_blueprint(main_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
