FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/uploads && chown -R app:app /app
USER app
ENV FLASK_APP=wsgi.py APP_ENV=production
EXPOSE 5000
# Web process. Worker/beat override the command in docker-compose / your orchestrator.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
