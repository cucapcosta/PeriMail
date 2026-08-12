FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY . .

CMD ["python", "-m", "peribot.bot"]
