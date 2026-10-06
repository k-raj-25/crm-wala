-- Local/dev bootstrap. The application connects as a NON-superuser role so that
-- Postgres row-level security (tenant isolation) is always enforced.
CREATE ROLE crm_app LOGIN PASSWORD 'crm_app_dev' NOSUPERUSER NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE crm OWNER crm_app;
CREATE DATABASE crm_test OWNER crm_app;
