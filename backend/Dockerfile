# FitAI backend image.
#
# Build context MUST be the repository root (the image needs /requirements.txt):
#   docker build -f backend/Dockerfile -t fitai-backend:latest .
#
# Runtime configuration comes entirely from environment variables; no secrets,
# local databases or development data are copied into the image (.dockerignore).

# ---- builder: resolve and install Python dependencies into a venv ----------
FROM python:3.10-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only PyTorch (the default PyPI wheel drags in several GB of CUDA libraries).
# The versions match the pins in requirements.txt, so the next step keeps them.
RUN pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# ---- runtime ----------------------------------------------------------------
FROM python:3.10-slim-bookworm AS runtime

# libgomp1: onnxruntime/torch threading. libgl1 + libglib2.0-0: opencv, which
# rapidocr-onnxruntime imports for image OCR. libsndfile1: audio decoding.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app \
    ANONYMIZED_TELEMETRY=False \
    ENVIRONMENT=production \
    PORT=8000 \
    DOCUMENT_STORAGE_BACKEND=local \
    CHROMADB_PERSIST_DIR=/var/data/chroma \
    UPLOAD_DIR=/var/data/uploads \
    HF_HOME=/var/data/hf-cache

# backend/ keeps its layout so settings, Alembic and the app resolve paths the
# same way as in development (paths are anchored to this directory).
WORKDIR /srv/fitai/backend
COPY backend/alembic.ini backend/pyproject.toml ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /var/data \
    && chown -R app:app /var/data /srv/fitai

# Best effort: bake the default Chroma embedding model into the image so the
# first document upload does not depend on a runtime download. A failure here
# must not fail the build; the model is then fetched on first use instead.
USER app
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as D; D()(['warm-up'])" \
    || echo "embedding model pre-download skipped"
USER root

# Persistent data lives under /var/data: mount a Render disk or a Docker volume there.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,sys,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)" || exit 1

# Starts as root only to prepare mounted volumes, then drops to user `app`.
ENTRYPOINT ["docker-entrypoint.sh"]
