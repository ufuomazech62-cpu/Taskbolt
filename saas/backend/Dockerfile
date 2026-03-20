# Taskbolt License Backend - Minimal Docker Image
# Only includes the license validation API, no frontend

FROM python:3.11-slim

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python dependencies
COPY saas/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY saas/backend/app.py ./

# Create non-root user
RUN useradd -m -u 1000 taskbolt && chown -R taskbolt:taskbolt /app
USER taskbolt

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start the application
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
