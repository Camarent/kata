-- 0007: device token scope. 'api' tokens reach the JSON API; 'mcp' tokens reach only the MCP surface.
-- Existing rows get 'api' from the default, so every token issued before this migration keeps working.

ALTER TABLE devices
    ADD COLUMN scope text NOT NULL DEFAULT 'api' CHECK (scope IN ('api', 'mcp'));
