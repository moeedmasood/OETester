from pathlib import Path
from flask import Flask

from .config import Config


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["OUTPUT_FOLDER"]).mkdir(parents=True, exist_ok=True)

    from .routes import bp
    app.register_blueprint(bp)

    return app
