-- Supabase role/bootstrap for application logins
-- Usage: run in the SQL editor on a new project before applying schema seeds.
-- Replace {{PASSWORD_HERE}} with a strong secret unique to the environment.

-- 1) Ensure the `checkin_app` role exists with login credentials
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'checkin_app'
    ) THEN
        CREATE ROLE checkin_app LOGIN PASSWORD '{{PASSWORD_HERE}}';
    ELSE
        ALTER ROLE checkin_app WITH LOGIN PASSWORD '{{PASSWORD_HERE}}' LOGIN;
    END IF;
END$$;

ALTER ROLE checkin_app VALID UNTIL 'infinity';

-- 2) Grant database access + schema privileges (run once per database)
-- Supabase projects use the "postgres" database by default. Replace if you have a custom DB name.
GRANT CONNECT ON DATABASE postgres TO checkin_app;
GRANT USAGE ON SCHEMA public TO checkin_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO checkin_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO checkin_app;

-- 3) Future-proof privileges for newly created tables/sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO checkin_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO checkin_app;

-- 4) Optional: verify role status
-- SELECT rolname, rolcanlogin, rolvaliduntil FROM pg_roles WHERE rolname = 'checkin_app';
