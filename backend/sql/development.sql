CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS uploaded_data;
CREATE ROLE shopquery_reader LOGIN PASSWORD 'readonly_password';
ALTER ROLE shopquery_reader SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE shopquery_dev TO shopquery_reader;
CREATE DATABASE shopquery_test_stage1 OWNER shopquery_setup;
GRANT CONNECT ON DATABASE shopquery_test_stage1 TO shopquery_reader;
