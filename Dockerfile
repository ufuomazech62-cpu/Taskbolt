# -----------------------------------------------------------------------------
# Taskbolt - Cloud Run Deployment Dockerfile
# Multi-stage build for optimized production image
# -----------------------------------------------------------------------------

# Stage 1: Build console frontend
FROM node:20-slim AS console-builder
WORKDIR /app
COPY console /app/console
RUN cd /app/console && npm ci --include=dev && npm run build

# Stage 2: Python runtime with minimal dependencies for Cloud Run
FROM python:3.11-slim

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKSPACE_DIR=/app \
    TASKBOLT_WORKING_DIR=/app/working \
    TASKBOLT_SECRET_DIR=/app/working.secret \
    TASKBOLT_PORT=8080 \
    TASKBOLT_RUNNING_IN_CONTAINER=1

WORKDIR ${WORKSPACE_DIR}

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python project files
COPY pyproject.toml setup.py README.md ./
COPY src ./src

# Inject console dist from build stage
COPY --from=console-builder /app/console/dist/ ./src/taskbolt/console/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .[ollama]

# Initialize Taskbolt with defaults
RUN taskbolt init --defaults --accept-security

# Create non-root user for security
RUN useradd -m -u 1000 taskbolt && \
    chown -R taskbolt:taskbolt /app
USER taskbolt

# Expose port (Cloud Run uses 8080)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start the application
CMD ["taskbolt", "app", "--host", "0.0.0.0", "--port", "8080"]
