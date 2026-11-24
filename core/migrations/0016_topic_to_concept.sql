-- 0016: copy topic aliases and topic marks onto the concept model (D53, D54). Data only:
-- migration 0015 made the schema. Topics, topic_aliases and marks are left untouched.
-- Idempotent: every insert has an ON CONFLICT guard, so a rerun adds no rows.

-- Visibility rule, as the old topic code applies it: a shared topic (owner NULL) takes
-- every row; a private topic takes only rows written by its owner. A private row never
-- moves to another user.

-- Step 1: each topic with a known mark or an alias gets one concept named like the topic,
-- under that topic, with the topic's owner. An existing concept with that label is kept.
INSERT INTO concepts (topic_id, label, owner_user_id)
SELECT t.id, t.label, t.owner_user_id
FROM topics t
WHERE EXISTS (
        SELECT 1 FROM marks m
        WHERE m.topic_id = t.id AND m.status = 'known'
          AND (t.owner_user_id IS NULL OR m.user_id = t.owner_user_id)
    )
   OR EXISTS (
        SELECT 1 FROM topic_aliases a
        WHERE a.topic_id = t.id
          AND (t.owner_user_id IS NULL OR a.owner_user_id = t.owner_user_id)
    )
ON CONFLICT (topic_id, lower(label), coalesce(owner_user_id, 0)) DO NOTHING;

-- Step 2: a known topic mark becomes a known concept mark on the topic-named concept.
-- A mark already on that concept keeps its state.
INSERT INTO concept_marks (user_id, concept_id, state)
SELECT m.user_id, c.id, 'known'
FROM marks m
JOIN topics t ON t.id = m.topic_id
JOIN concepts c
  ON c.topic_id = t.id
 AND lower(c.label) = lower(t.label)
 AND c.owner_user_id IS NOT DISTINCT FROM t.owner_user_id
WHERE m.status = 'known'
  AND (t.owner_user_id IS NULL OR m.user_id = t.owner_user_id)
ON CONFLICT (user_id, concept_id) DO NOTHING;

-- Step 3: each topic alias becomes a concept alias on the topic-named concept. An alias
-- that clashes with one already there (same topic, alias and owner, any case) is skipped.
INSERT INTO concept_aliases (concept_id, topic_id, alias, owner_user_id)
SELECT c.id, t.id, a.alias, a.owner_user_id
FROM topic_aliases a
JOIN topics t ON t.id = a.topic_id
JOIN concepts c
  ON c.topic_id = t.id
 AND lower(c.label) = lower(t.label)
 AND c.owner_user_id IS NOT DISTINCT FROM t.owner_user_id
WHERE t.owner_user_id IS NULL OR a.owner_user_id = t.owner_user_id
ON CONFLICT (topic_id, lower(alias), coalesce(owner_user_id, 0)) DO NOTHING;
