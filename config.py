# config.py
# This file holds the application configuration.
import os
class Config:
    """Base configuration class."""
    # SQLite database URI. The `../instance/database.db` path
    # places the database file in the `instance` folder,
    # which is standard practice for Flask applications.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///../instance/database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
