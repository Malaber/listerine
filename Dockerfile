FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
RUN mkdir /data && chown app:app /data

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY alembic ./alembic
COPY docker ./docker

RUN pip install --upgrade pip && pip install . && chmod +x /app/docker/start.sh && chown -R app:app /app

USER app

EXPOSE 8000

ENV UVICORN_FORWARDED_ALLOW_IPS=127.0.0.1

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health')"

CMD ["/app/docker/start.sh"]
