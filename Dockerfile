# API Health Monitor — production-ish image
# Multi-stage: build deps in a throwaway layer, copy into a slim runtime.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install build deps for psycopg2 (binary wheel usually suffices, but be safe).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# --- Runtime stage -----------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AHM_DATABASE_URL=postgresql+psycopg2://ahm:ahm@db:5432/ahm \
    AHM_POLL_INTERVAL_SECONDS=60

# libpq needed by psycopg2 at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder.
COPY --from=builder /install /usr/local

WORKDIR /app
COPY app ./app

EXPOSE 8000

# Run via uvicorn. The scheduler starts inside the app lifespan.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
