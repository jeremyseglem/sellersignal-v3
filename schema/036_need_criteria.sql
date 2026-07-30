-- 036: New buyer-need criteria unlocked by structure enrichment (035).
-- waterfront (tri-state: NULL = don't care), minimum view rating,
-- minimum stories, renovated-since.

ALTER TABLE buyer_needs_v3 ADD COLUMN IF NOT EXISTS waterfront         BOOLEAN;
ALTER TABLE buyer_needs_v3 ADD COLUMN IF NOT EXISTS view_min           SMALLINT;
ALTER TABLE buyer_needs_v3 ADD COLUMN IF NOT EXISTS stories_min        NUMERIC(4,1);
ALTER TABLE buyer_needs_v3 ADD COLUMN IF NOT EXISTS year_renovated_min INT;
