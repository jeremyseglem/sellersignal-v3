# Railway build for SellerSignal.
#
# Switched from Nixpacks to an explicit Dockerfile so we can reliably install
# the OCR system toolchain the Maricopa Recorder harvester needs at RUNTIME
# (Nixpacks aptPkgs installed them only in a build layer that didn't reach the
# runtime image — verified false via /api/harvest/diag/ocr-check, 2026-06).
#
# Mirrors the previous Nixpacks build exactly:
#   - Python 3.11 (matches runtime.txt)
#   - pip install -r requirements.txt
#   - start: uvicorn backend.main:app --host 0.0.0.0 --port $PORT  (was the Procfile)
#   - frontend/dist is committed and served by FastAPI static — no Node build here
#
# Rollback if a build ever fails: `git rm Dockerfile .dockerignore && git push`
# (Railway falls back to Nixpacks). A failed build leaves the last good deploy live.

FROM python:3.11-slim

# OCR runtime tools: tesseract (engine + English data) and poppler-utils (pdftoppm)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (includes committed frontend/dist served by FastAPI)
COPY . .

# Railway injects $PORT at runtime; default for local docker run
ENV PORT=8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
