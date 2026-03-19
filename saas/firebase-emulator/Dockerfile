# Firebase Emulator for Development
FROM node:18-slim

# Install Java (required for Firebase emulators)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Install Firebase CLI
RUN npm install -g firebase-tools

WORKDIR /opt/firebase

# Copy Firebase configuration
COPY firebase.json .
COPY firestore.rules .
COPY firestore.indexes.json .
COPY storage.rules .

# Create emulator data directory
RUN mkdir -p /opt/firebase/data

# Expose emulator ports
# 4000 - Emulator UI
# 9099 - Auth Emulator
# 8080 - Firestore Emulator
# 9199 - Storage Emulator
EXPOSE 4000 9099 8080 9199

# Start emulators
CMD ["firebase", "emulators:start", "--project", "taskbolt-dev", "--only", "auth,firestore,storage"]
