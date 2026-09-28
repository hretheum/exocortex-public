-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/45_gate_edge_type.sql — edge from a gate decision to the
-- hypothesis version it decides (roadmap task F2.5).

ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'decides';
