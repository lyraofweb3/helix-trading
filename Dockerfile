FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIGNAL_DIR=/app/signals \
    HELIX_POLL_SECONDS=300 \
    HELIX_AUTO_MARKET=1 \
    HELIX_MAX_TRADES_PER_DAY=3 \
    HELIX_TRADE_STYLE=swing \
    HELIX_V1_LLM=0 \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY helix ./helix
COPY helix_v1 ./helix_v1
COPY app ./app
COPY cli_main.py ./cli_main.py
COPY start.py ./start.py
COPY mq5 ./mq5
RUN mkdir -p /app/signals

EXPOSE 8080

# Railway sets $PORT; default 8080 locally
CMD ["python", "start.py"]
