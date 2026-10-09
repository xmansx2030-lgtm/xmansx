import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
worker_class = "gthread" if threads > 1 else "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "10"))
backlog = int(os.environ.get("GUNICORN_BACKLOG", "512"))
worker_connections = int(os.environ.get("GUNICORN_WORKER_CONNECTIONS", "512"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "10000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "1000"))
accesslog = None
errorlog = "-"
