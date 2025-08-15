# run.py
# This script is the entry point for running the Flask application.

from app import create_app

# Create the application instance.
app = create_app()

if __name__ == '__main__':
    # Run the application in debug mode for development.
    # The port is set to 5000 by default.
    app.run(debug=True)
