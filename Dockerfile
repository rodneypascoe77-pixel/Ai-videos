FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/

ENV PYTHONPATH=/app/src
# Phase 1: initialise the DB. A scheduler/run entrypoint lands in a later phase.
CMD ["uv", "run", "python", "-m", "db.init"]
