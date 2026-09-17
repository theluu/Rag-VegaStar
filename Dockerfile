# API FastAPI
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install . \
    && useradd --create-home --uid 10001 app
COPY scripts ./scripts
COPY scenarios ./scenarios
COPY knowledge ./knowledge
COPY evals ./evals
COPY results/eval_report.json ./results/eval_report.json

# Chạy bằng user không có quyền root
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"API_PORT\",\"8000\")}/health', timeout=4)"
CMD ["sh", "-c", "uvicorn vessel_chat.api.app:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000} --proxy-headers --no-server-header"]
