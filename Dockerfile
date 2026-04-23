FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    APP_BASE_URL=http://localhost:8080 \
    DATABASE_URL=sqlite:////app/var/network_king.db \
    LOCAL_MEDIA_ROOT=/app/var/uploads

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/var/uploads \
    && chown -R appuser:appuser /app/var

COPY --chown=appuser:appuser pyproject.toml README.md /app/
COPY --chown=appuser:appuser app /app/app

RUN pip install --upgrade pip \
    && pip install ".[gcp]"

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
