-- Run once as the PostgreSQL cluster administrator after replacing passwords.
-- Keep this file free of real credentials; psql variables are supplied by the operator.
\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'health_app_owner') THEN
    CREATE ROLE health_app_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'health_app_migrator') THEN
    CREATE ROLE health_app_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'health_app_runtime') THEN
    CREATE ROLE health_app_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END
$$;

ALTER ROLE health_app_migrator PASSWORD :'migrator_password';
ALTER ROLE health_app_runtime PASSWORD :'runtime_password';
GRANT health_app_owner TO health_app_migrator;

DO $$
BEGIN
  EXECUTE format(
    'GRANT CONNECT ON DATABASE %I TO health_app_migrator, health_app_runtime',
    current_database()
  );
END
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO health_app_owner;
GRANT USAGE, CREATE ON SCHEMA public TO health_app_owner;
GRANT USAGE ON SCHEMA public TO health_app_runtime;

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('ALTER TABLE %I.%I OWNER TO health_app_owner', item.schemaname, item.tablename);
  END LOOP;
  FOR item IN SELECT sequence_schema, sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public'
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO health_app_owner', item.sequence_schema, item.sequence_name);
  END LOOP;
END
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO health_app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO health_app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE health_app_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO health_app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE health_app_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO health_app_runtime;
