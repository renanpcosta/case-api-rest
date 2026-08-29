FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
RUN pip install --no-cache-dir .

COPY data/catalog.json data/events.jsonl data/events.sample.jsonl /app/data/

ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 5050

CMD ["uvicorn", "pool_selector.app:app", "--host", "0.0.0.0", "--port", "5050"]
