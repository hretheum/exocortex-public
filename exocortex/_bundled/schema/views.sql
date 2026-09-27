-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- Analytical views

-- FRP: session summary with aggregated metadata
CREATE OR REPLACE VIEW frp_session_summary AS
SELECT
  s.id, s.tenant_id, s.frame, s.level, s.resonance,
  s.status, s.created_at, s.revisit_due, s.revisited_at,
  cq.score_total, cq.ai_tags, cq.scenario_sentence,
  rs.title        AS story_title,
  rs.uri          AS story_url,
  rs.source_name,
  COUNT(t.id)     AS thought_count,
  BOOL_OR(t.metadata->>'signal_today' = 'true') AS signal_today
FROM frp_sessions s
JOIN content_queue cq ON cq.id = s.content_id
JOIN raw_sources rs ON rs.id = cq.source_id
LEFT JOIN edges e ON e.src_type = 'frp_session'
  AND e.src_id = s.id AND e.type = 'session_contains'
LEFT JOIN thoughts t ON t.id = e.dst_id
GROUP BY s.id, cq.id, rs.id;

-- CROSS-DOMAIN: thought distribution per domain
CREATE OR REPLACE VIEW domain_distribution AS
SELECT
  metadata->>'domain' AS domain,
  thought_type,
  COUNT(*) AS count,
  MAX(created_at) AS last_entry
FROM thoughts
WHERE tenant_id = current_setting('app.tenant_id')::uuid
GROUP BY metadata->>'domain', thought_type;

-- 3D: material history
CREATE OR REPLACE VIEW material_history AS
SELECT
  ent.canonical_name AS material,
  t.body AS print_log,
  (t.metadata->>'quality_score')::integer AS quality,
  t.metadata->>'printer' AS printer,
  t.created_at
FROM entities ent
JOIN edges e ON e.dst_id = ent.id AND e.type = 'printed_with'
JOIN thoughts t ON t.id = e.src_id AND t.thought_type = 'print_log'
WHERE ent.type = 'material';

-- CROSS-DOMAIN: materializing signals
CREATE OR REPLACE VIEW frp_materializing AS
SELECT
  t.body          AS fiction_signal,
  t.created_at    AS session_date,
  rs2.uri         AS real_source_url,
  rs2.title       AS real_source_title,
  e.created_at    AS materialized_at,
  (e.created_at::date - t.created_at::date) AS days_elapsed
FROM edges e
JOIN thoughts t ON t.id = e.src_id AND e.type = 'materializes_as'
JOIN raw_sources rs2 ON rs2.id = e.dst_id
ORDER BY e.created_at DESC;

