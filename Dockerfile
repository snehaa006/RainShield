# Container image for the RainShield inference API.
#
# Built for Hugging Face Spaces (Docker SDK) but host-agnostic: it listens on
# $PORT, defaulting to 7860, which is what Spaces expects and what Render and
# Fly both override.
#
# The image is small because the serving package deliberately has no PyTorch —
# models/numpy_backend.py runs the trained network in NumPy alone. The weights
# and rasters are 6.9 MB and live in the repo, so nothing is fetched at build
# or at boot.

FROM python:3.11-slim

# tzdata comes from requirements.txt rather than apt: service.py formats every
# timestamp in the region's own IANA zone and slim images ship no zone database.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a source change does not reinstall them.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# The commands run from the repository root rather than from backend/, so the
# committed weights and rasters under processed_data/ stay on the path.
COPY backend/ ./backend/
COPY processed_data/ ./processed_data/

# Spaces runs containers as a non-root user; matching that here means the image
# behaves the same locally as it does deployed. Nothing in the serving package
# writes to disk, so the filesystem can stay read-only.
RUN useradd --create-home --uid 1000 rainshield && chown -R rainshield:rainshield /app
USER rainshield

ENV PORT=7860
EXPOSE 7860

# Single worker on purpose. Scoring an observation is CPU-bound NumPy that
# already releases the GIL in BLAS, and a second worker would double the
# resident set and re-run every forward pass in its own cache for no gain.
CMD ["sh", "-c", "uvicorn rainshield.api.app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-7860}"]
