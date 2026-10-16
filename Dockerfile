# Campus Guide Kiosk - production image
# Build:  docker build -t campus-guide-kiosk .
# Run:    docker compose up -d   (mounts ./firebase read-only, reads .env)

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

# Runtime libraries only (libgomp1 is required by torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local

# Run as an unprivileged user. A home directory is needed for the
# sentence-transformers and NLTK caches.
RUN useradd --create-home --uid 1000 app

COPY --chown=app:app . .
RUN mkdir -p logs && chown app:app logs

USER app

ENV PYTHONUNBUFFERED=1 \
    # Each worker loads its own embedding model; keep this low on small hosts.
    WEB_CONCURRENCY=2

EXPOSE 5000

# Uses the standard library only, so no extra package is needed in the image.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/health', timeout=5)" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
