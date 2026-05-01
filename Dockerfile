FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libgomp1 cho onnxruntime (mbbank-lib dùng OCR captcha qua onnxruntime).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# Service nào chạy tuỳ command override trong docker-compose:
#   - app:     uvicorn app.main:app --host 0.0.0.0 --port 8000
#   - worker:  python -m app.worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
