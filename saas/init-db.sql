-- Taskbolt SaaS Database Initialization
-- This script is run when the PostgreSQL container is first created

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS public;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA public TO taskbolt;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO taskbolt;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO taskbolt;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO taskbolt;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO taskbolt;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Taskbolt SaaS database initialized successfully';
END $$;
