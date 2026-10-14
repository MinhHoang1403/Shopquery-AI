CREATE EXTENSION IF NOT EXISTS vector;

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
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO shopquery_reader;
