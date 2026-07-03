FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY config ./config
COPY data ./data

RUN python -m pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "wcpa.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
