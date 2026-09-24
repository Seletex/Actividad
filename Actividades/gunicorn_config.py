
# Gunicorn configuration file
import os

port = os.environ.get("PORT", "8000")
bind = f"0.0.0.0:{port}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = 4
timeout = 120
worker_class = "gthread"
loglevel = "info"
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
