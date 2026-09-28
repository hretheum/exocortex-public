-- deploy/postgres-init/02_graph.sql — create the default Apache AGE graph on a
-- fresh database volume. No schema/*.sql migration creates it, and every
-- edge write (cypher('exocortex', ...)) fails without it. The name matches
-- the PG_AGE_GRAPH default ('exocortex'); a deployment that uses another
-- graph name creates that graph itself. Runs only on first initialisation.
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'exocortex') THEN
    PERFORM ag_catalog.create_graph('exocortex');
  END IF;
END
$$;
