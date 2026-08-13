FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements-bot.txt .
RUN pip install --no-cache-dir --requirement requirements-bot.txt

COPY analysis ./analysis
COPY data ./data
COPY telegram_utils ./telegram_utils
COPY bot.py bot_webhook.py ./

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/matplotlib \
    && chown -R appuser:appuser /app /tmp/matplotlib
USER appuser

CMD exec uvicorn bot_webhook:api --host 0.0.0.0 --port "${PORT:-8080}"

