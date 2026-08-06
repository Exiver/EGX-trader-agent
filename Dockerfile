FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Run as a non-root user — a container running as root is unnecessary
# attack surface for no real benefit here. Also create the SQLite data
# directory now, as root, so the non-root user can actually write to it —
# without this, os.makedirs("data") inside database.py would fail with a
# permission error the first time the app tries to write.
RUN useradd --create-home appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app
USER appuser

# Cloud Run injects $PORT at runtime (defaults to 8080 here for local use).
ENV PORT=8080
EXPOSE 8080

# Container-level health check, separate from Cloud Run's own probing —
# useful for local `docker run` and docker-compose too. Uses Python's
# built-in urllib rather than curl, since curl isn't in the slim base image
# and installing it just for this would bloat the image for no reason.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]