
# Gunicorn configuration file
import os

port = os.environ.get("PORT", "8000")
bind = f"0.0.0.0:{port}"
workers = 2  # Adjust based on available resources
threads = 4
timeout = 120
worker_class = "gthread"
loglevel = "info"
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
