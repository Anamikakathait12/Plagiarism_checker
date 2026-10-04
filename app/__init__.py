import os
from flask import Flask
from app.config import Config
from app.extensions import login_manager
from app.db import init_db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    login_manager.init_app(app)

    with app.app_context():
        init_db()

    from app import models  # noqa: F401  (registers the user_loader)
    from app.routes import register_blueprints
    register_blueprints(app)

    return app
