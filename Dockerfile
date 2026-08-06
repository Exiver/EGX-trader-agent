FROM python:3.11-slim

# Don't buffer stdout/stderr (so `docker logs` / Cloud Run logs show output immediately)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Now copy the actual application code
COPY app ./app

# Cloud Run injects $PORT at runtime (defaults to 8080); we honor it here.
# Locally (docker run -p 8000:8000) you can override with -e PORT=8000.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
