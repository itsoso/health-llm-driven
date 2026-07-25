WITH ranked_posts AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, source_type, source_id
            ORDER BY created_at DESC, id DESC
        ) AS duplicate_rank
    FROM community_posts
    WHERE status <> 'deleted'
)
UPDATE community_posts AS post
SET
    status = 'deleted',
    updated_at = NOW()
FROM ranked_posts
WHERE post.id = ranked_posts.id
  AND ranked_posts.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_community_posts_active_source
ON community_posts(user_id, source_type, source_id)
WHERE status <> 'deleted';
