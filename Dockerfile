FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/

ENV PYTHONPATH=/app/src
# Phase 1: run the 24/7 discovery scheduler (fetch + classify on an interval).
CMD ["uv", "run", "python", "-m", "scheduler"]
