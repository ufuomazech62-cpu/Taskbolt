# Taskbolt SaaS - Multi-Tenant Docker Image for Google Cloud Run
# 
# This Dockerfile creates a production-ready image with:
# - Python 3.11 backend with FastAPI
# - Node.js frontend with React (built at image creation)
# - Optimized for Cloud Run

# ============================================================================
# Stage 1: Build Frontend
# ============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY saas/frontend/package*.json ./

# Install dependencies
RUN npm ci --include=dev

# Copy frontend source
COPY saas/frontend/ ./

# Build for production
RUN npm run build

# ============================================================================
# Stage 2: Python Backend with Frontend
# ============================================================================
FROM python:3.11-slim AS backend

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_ENV=production \
    TASKBOLT_RUNNING_IN_CONTAINER=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    chromium \
    chromium-sandbox \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libglib2.0-0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Playwright configuration
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

# Install Python dependencies
COPY requirements-saas.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Prisma CLI and generate client
RUN pip install prisma
COPY saas/prisma ./prisma/
RUN prisma generate

# Copy backend source
COPY saas/backend ./backend

# Copy frontend build from previous stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set frontend static directory
ENV TASKBOLT_FRONTEND_DIR=/app/frontend/dist

# Create non-root user for security
RUN useradd -m -u 1000 taskbolt && \
    chown -R taskbolt:taskbolt /app
USER taskbolt

# Expose port (Cloud Run uses PORT env var)
EXPOSE 8088
ENV TASKBOLT_PORT=8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${TASKBOLT_PORT}/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8088"]
