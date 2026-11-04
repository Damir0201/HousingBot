FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies layer (cached while pyproject.toml is unchanged)
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install ".[dev]" \
    && rm -rf app

COPY . .
RUN pip install --no-deps . \
    && useradd --create-home --uid 1000 domik \
    && mkdir -p /app/data && chown -R domik:domik /app

USER domik

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
