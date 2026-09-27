-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/27_notify_triggers.sql — F31.1.4: pg_notify triggers for urgent events
-- consumed by workers.notify_listener (sync to Telegram push).
--
-- Channels emitted:
--   - contradiction_detected : new edges row with type='contradicts'
--
-- Action items live as raw markdown in thoughts.metadata->>'action_items'
-- (parsed on-demand by exocortex.action_items). There is no action_items
-- table or due_date column at the SQL layer, so a due-date trigger would
-- have nothing concrete to fire on. Surfacing overdue action items is
-- therefore left to a cron-driven path (find_action_items + push), not to
-- pg_notify. Channel name 'action_item_due' is reserved here for that
-- future producer so the listener daemon can subscribe to it pre-emptively.

CREATE OR REPLACE FUNCTION fn_notify_contradiction() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify(
    'contradiction_detected',
    json_build_object(
      'edge_id',  NEW.id,
      'src_id',   NEW.src_id,
      'src_type', NEW.src_type,
      'dst_id',   NEW.dst_id,
      'dst_type', NEW.dst_type,
      'tenant_id', NEW.tenant_id,
      'created_at', NEW.created_at
    )::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_notify_contradiction ON edges;
CREATE TRIGGER tg_notify_contradiction
  AFTER INSERT ON edges
  FOR EACH ROW
  WHEN (NEW.type = 'contradicts')
  EXECUTE FUNCTION fn_notify_contradiction();
