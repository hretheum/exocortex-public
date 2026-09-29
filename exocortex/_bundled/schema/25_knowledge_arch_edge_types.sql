-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/25_knowledge_arch_edge_types.sql — F27.2: extend edge_type ENUM for the
-- 3-layer knowledge architecture (source → graph → wiki).
--
-- Adds 8 edge types used by the source parser rewrite (F27.1), wiki compiler
-- refactor (F27.3), and cross-ACME cluster edges (F27.4):
--
--   Core (named in design doc + F27.2 task):
--     - belongs_to_pillar      (SourceFile → Pillar entity; frontmatter tag pillar/p*)
--     - cross_cuts             (SourceFile → Pillar/Section entity; multi-inheritance,
--                               LLM-detected "this doc also touches X")
--     - informed_by_decision   (SourceFile → Decision entity; content references a decision)
--     - references_metric      (SourceFile → Metric entity; content cites a metric)
--     - implements_roadmap     (SourceFile / kanban task → roadmap-item entity)
--
--   Siblings required by the L1→L2 parse (knowledge-architecture.md):
--     - belongs_to_section     (SourceFile → Section entity; from numbered folder path)
--     - wikilink_to            (SourceFile → SourceFile; explicit user-curated [[link]])
--     - defines_metric         (SourceFile → Metric entity; canonical metric definition)
--
-- NAMING: lowercase snake_case to match the existing edge_type ENUM convention
-- (classified_as_client, mentions_person, …). The AGE Cypher layer uses the
-- literal ENUM value as the relationship label (workers/db/graph.py::_age_upsert_edge),
-- so values MUST be valid Cypher identifiers — snake_case satisfies that.
--
-- Idempotent: safe to re-run. PG 16 supports `ALTER TYPE … ADD VALUE IF NOT EXISTS`.
-- Note: ADD VALUE cannot run inside a transaction block in PG <12; on PG 16 it can,
-- but each ADD VALUE is its own implicit commit — keeping them outside an explicit
-- BEGIN/COMMIT matches schema/09_edge_types.sql is fine either way on PG 16.
--
-- Apply on the server:
--   ssh second-brain-pg 'sudo -u postgres psql -d second_brain -f /opt/second-brain/schema/25_knowledge_arch_edge_types.sql'

ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'belongs_to_pillar';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'belongs_to_section';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'cross_cuts';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'wikilink_to';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'informed_by_decision';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'references_metric';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'defines_metric';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'implements_roadmap';

-- Reference: edge endpoint conventions for the new types (src_type / dst_type are
-- free-text TEXT columns on `edges`, not enforced — documented here for parsers).
--
--   belongs_to_pillar    : src='thought'|'raw_source' (SourceFile node)  → dst='entity' (type='pillar')
--   belongs_to_section   : src='thought'|'raw_source'                    → dst='entity' (type='coe_section')
--   cross_cuts           : src='thought'|'raw_source'                    → dst='entity' (type='pillar'|'coe_section'|'concept')
--   wikilink_to          : src='thought'|'raw_source'                    → dst='thought'|'raw_source'
--   informed_by_decision : src='thought'|'raw_source'                    → dst='entity' (type='decision')|'thought'
--   references_metric    : src='thought'|'raw_source'                    → dst='entity' (type='metric')
--   defines_metric       : src='thought'|'raw_source'                    → dst='entity' (type='metric')
--   implements_roadmap   : src='thought'|'raw_source'                    → dst='entity' (type='roadmap_item')
--
-- New entity `type` values these reference (entities.type is also free-text TEXT):
--   'pillar', 'coe_section', 'decision', 'metric', 'roadmap_item'
-- (consistent with the Entity Type Registry style in docs/schema.md — no ENUM to alter).
