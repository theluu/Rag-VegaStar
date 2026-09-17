# API FastAPI
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
COPY scripts ./scripts
COPY scenarios ./scenarios

EXPOSE 8000
CMD ["sh", "-c", "uvicorn vessel_chat.api.app:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000}"]
