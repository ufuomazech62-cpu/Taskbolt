#!/bin/bash
# Taskbolt Desktop - License Backend Deployment
# Run this script to deploy the license validation backend to Cloud Run
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - Docker installed
# - Access to the taskbolt-490722 Google Cloud project

set -e

# Configuration
PROJECT_ID="taskbolt-490722"
REGION="us-central1"
SERVICE_NAME="taskbolt-license"
REPO_NAME="taskbolt-repo"

echo "=== Taskbolt License Backend Deployment ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Authenticate
echo "Checking gcloud authentication..."
gcloud auth list

# Configure Docker
echo "Configuring Docker..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Build container
echo "Building container..."
cd "$(dirname "$0")/.."
docker build \
    -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest" \
    -f saas/backend/Dockerfile \
    .

# Push container
echo "Pushing container..."
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 5 \
    --set-env-vars "FIREBASE_PROJECT_ID=${PROJECT_ID}" \
    --set-secrets "FIREBASE_CONFIG=firebase-config:latest"

# Get URL
URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format 'value(status.url)')
echo ""
echo "=== Deployment Complete ==="
echo "License Backend URL: ${URL}"
echo ""
echo "Test the endpoint:"
echo "  curl ${URL}/health"
echo "  curl -X POST ${URL}/api/license/validate -H 'Content-Type: application/json' -d '{\"license_key\":\"TEST\",\"device_id\":\"test\"}'"
