# Dockerfile for the minimal fraud detection example
# Used by docker-compose.yml at the project root for local demos.
#
# Build context should be the project root:
#   docker build -f examples/minimal/Dockerfile -t template-example .

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY examples/minimal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy example code
COPY examples/minimal/ .

# Train model at build time (uses synthetic data)
RUN python train.py

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with single worker (template invariant)
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
