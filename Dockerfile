FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WECKERLE_DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# openssh-client für das spätere Ausschalten per SSH, iputils-ping für den Online-Status
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 1000 weckerle \
    && mkdir -p /data && chown weckerle:weckerle /data
USER weckerle

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
