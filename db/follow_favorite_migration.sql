-- Follow / favorite migration. Two small join tables, idempotent.

CREATE TABLE IF NOT EXISTS user_follow (
    follower_id   UUID NOT NULL REFERENCES contributor(contributor_id) ON DELETE CASCADE,
    following_id  UUID NOT NULL REFERENCES contributor(contributor_id) ON DELETE CASCADE,
    followed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_id, following_id),
    CHECK (follower_id <> following_id)
);
CREATE INDEX IF NOT EXISTS user_follow_following_idx
    ON user_follow (following_id);

CREATE TABLE IF NOT EXISTS tree_favorite (
    contributor_id UUID NOT NULL REFERENCES contributor(contributor_id) ON DELETE CASCADE,
    tree_id        UUID NOT NULL REFERENCES tree(tree_id) ON DELETE CASCADE,
    favorited_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (contributor_id, tree_id)
);
CREATE INDEX IF NOT EXISTS tree_favorite_tree_idx
    ON tree_favorite (tree_id);
