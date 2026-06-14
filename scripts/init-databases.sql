-- Create the Langfuse analytics database alongside the main application database.
-- This script runs automatically on first postgres container initialisation (empty data volume).
-- For existing setups where the volume is already populated, run once manually:
--   docker compose exec db psql -U postgres -c "CREATE DATABASE langfuse;"
CREATE DATABASE langfuse;
