CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS uploaded_data;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'shopquery_reader') THEN
        CREATE ROLE shopquery_reader LOGIN PASSWORD 'readonly_password';
    END IF;
END
$$;

ALTER ROLE shopquery_reader SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE shopquery TO shopquery_reader;
GRANT USAGE ON SCHEMA public TO shopquery_reader;
GRANT USAGE ON SCHEMA uploaded_data TO shopquery_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA uploaded_data GRANT SELECT ON TABLES TO shopquery_reader;

-- Application tables are created by setup_database.py. The case-insensitive
-- dataset-name index is added there after the datasets table exists.
