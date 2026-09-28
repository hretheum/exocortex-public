-- Create legacy role aliases so schema/*.sql GRANT statements don't fail.
-- The `second_brain` role is the original system user from bare-metal deployments;
-- in Docker we run as `exocortex` but retain the role for schema compatibility.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'second_brain') THEN
    CREATE ROLE second_brain;
    EXECUTE format('GRANT second_brain TO %I', current_user);  -- the POSTGRES_USER role
  END IF;
END
$$;
