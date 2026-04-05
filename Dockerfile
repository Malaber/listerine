FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG LISTERINE_VERSION=0.0.0.dev0

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
RUN mkdir /data && chown app:app /data

COPY pyproject.toml README.md alembic.ini ./
COPY docker/export_runtime_requirements.py ./docker/export_runtime_requirements.py

RUN python docker/export_runtime_requirements.py > docker/runtime-requirements.txt \
    && pip install -r docker/runtime-requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY docker ./docker
COPY scripts/export_seed_passkeys.py ./scripts/export_seed_passkeys.py
COPY scripts/create_passkey_reset_link.py ./scripts/create_passkey_reset_link.py

RUN SETUPTOOLS_SCM_PRETEND_VERSION=${LISTERINE_VERSION} pip install --no-deps . \
    && printf '%s\n' "${LISTERINE_VERSION}" > VERSION \
    && chmod +x /app/docker/start.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENV UVICORN_FORWARDED_ALLOW_IPS=127.0.0.1

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health')"

CMD ["/app/docker/start.sh"]
