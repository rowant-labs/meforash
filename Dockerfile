FROM python:3.13.1-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TINKER_TELEMETRY=0

WORKDIR /app

COPY requirements-inference.lock.txt requirements-deployment-linux.txt ./
RUN python -m pip install --upgrade "pip==26.2.1" \
    && python -m pip install --only-binary=:all: -r requirements-deployment-linux.txt \
    && python -m pip check

COPY bibleprep/ ./bibleprep/
COPY web/beta/ ./web/beta/
COPY manifests/instruction-target-revision-training-v3.json \
     manifests/preparation-inkling-v1.json \
     manifests/comparison-large-models-v1.json \
     manifests/oshb.json \
     manifests/sblgnt.json \
     manifests/chat-versification-v1.json ./manifests/

EXPOSE 8877
CMD ["python", "-m", "bibleprep.railway_deployment", "serve"]
