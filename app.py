# app.py
# This is the main application factory.

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

# Create the database instance. It is not attached to an app yet.
db = SQLAlchemy()

def create_app():
    """
    Application factory function.
    Initializes and configures the Flask application.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions with the app
    db.init_app(app)

    # Import and register the blueprint from the project directory.
    from project.routes import project_bp
    app.register_blueprint(project_bp)

    # Create the instance directory if it doesn't exist.
    # This is where the SQLite database will be stored.
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)

    # Create the database tables if they don't already exist.
    with app.app_context():
        db.create_all()

    return app
