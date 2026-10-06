import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", max(2, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_class = "gthread"
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 2000            # recycle workers to bound memory growth
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "*")  # set to your proxy's address in production
