#!/bin/bash
# Taskbolt Cloud Run Entry Point
# Minimal startup script for Cloud Run deployment

set -e

# Set default port (Cloud Run uses 8080)
export TASKBOLT_PORT="${TASKBOLT_PORT:-8080}"
export PORT="${PORT:-$TASKBOLT_PORT}"

# Create working directories if they don't exist
mkdir -p ${TASKBOLT_WORKING_DIR:-/app/working}
mkdir -p ${TASKBOLT_SECRET_DIR:-/app/working.secret}

# Initialize if not already done
if [ ! -f "${TASKBOLT_WORKING_DIR:-/app/working}/config.json" ]; then
    taskbolt init --defaults --accept-security
fi

# Start the application
echo "Starting Taskbolt on port ${PORT}..."
exec taskbolt app --host 0.0.0.0 --port ${PORT}
