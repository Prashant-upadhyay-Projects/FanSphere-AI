-- =============================================================================
-- FanSphere AI — PostgreSQL schema
-- Run: psql -U fansphere -d fansphere_ai -f sql/schema.sql
-- =============================================================================

-- Drop in safe order (children first) -----------------------------------------
DROP VIEW  IF EXISTS v_executive_overview;
DROP TABLE IF EXISTS engagement_metrics;
DROP TABLE IF EXISTS fan_sentiment;
DROP TABLE IF EXISTS matches;

-- =============================================================================
-- matches
-- =============================================================================
CREATE TABLE matches (
    match_id      BIGINT       PRIMARY KEY,
    home_team     VARCHAR(120) NOT NULL,
    away_team     VARCHAR(120) NOT NULL,
    competition   VARCHAR(120),
    season        VARCHAR(20),
    match_date    DATE,
    home_score    INTEGER,
    away_score    INTEGER,
    total_goals   INTEGER GENERATED ALWAYS AS
                  (COALESCE(home_score, 0) + COALESCE(away_score, 0)) STORED,
    is_rivalry    BOOLEAN      DEFAULT FALSE,
    ingested_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matches_date        ON matches (match_date);
CREATE INDEX idx_matches_competition ON matches (competition);

-- =============================================================================
-- fan_sentiment
-- =============================================================================
CREATE TABLE fan_sentiment (
    id              BIGSERIAL    PRIMARY KEY,
    source          VARCHAR(50)  NOT NULL,        -- e.g. 'reddit:Barca'
    external_id     VARCHAR(50),                  -- post / comment id
    comment         TEXT         NOT NULL,
    upvotes         INTEGER      DEFAULT 0,
    sentiment_score NUMERIC(5,4) NOT NULL,        -- VADER compound, [-1, 1]
    sentiment_label VARCHAR(20)  NOT NULL,        -- positive / neutral / negative
    emotion         VARCHAR(20),                  -- excitement / frustration / optimism
    match_id        BIGINT       REFERENCES matches(match_id) ON DELETE SET NULL,
    posted_at       TIMESTAMP    NOT NULL,
    ingested_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source, external_id)
);

CREATE INDEX idx_sentiment_posted_at ON fan_sentiment (posted_at);
CREATE INDEX idx_sentiment_match     ON fan_sentiment (match_id);
CREATE INDEX idx_sentiment_label     ON fan_sentiment (sentiment_label);

-- =============================================================================
-- engagement_metrics
-- =============================================================================
CREATE TABLE engagement_metrics (
    id                BIGSERIAL    PRIMARY KEY,
    match_id          BIGINT       REFERENCES matches(match_id) ON DELETE CASCADE,
    comment_volume    INTEGER      DEFAULT 0,
    upvote_total      INTEGER      DEFAULT 0,
    goal_events       INTEGER      DEFAULT 0,
    avg_sentiment     NUMERIC(5,4),
    engagement_score  NUMERIC(8,2),                -- weighted composite
    excitement_index  NUMERIC(8,2),                -- 0.4·comments + 0.3·upvotes + 0.3·goals
    match_hype_score  NUMERIC(8,2),                -- 0.5·social + 0.3·goals + 0.2·rivalry
    computed_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (match_id)
);

CREATE INDEX idx_engagement_match ON engagement_metrics (match_id);

-- =============================================================================
-- Executive overview view (feeds Power BI Page 1)
-- =============================================================================
CREATE VIEW v_executive_overview AS
SELECT
    m.match_id,
    m.home_team,
    m.away_team,
    m.competition,
    m.match_date,
    m.total_goals,
    m.is_rivalry,
    e.comment_volume,
    e.upvote_total,
    e.avg_sentiment,
    e.engagement_score,
    e.excitement_index,
    e.match_hype_score
FROM matches m
LEFT JOIN engagement_metrics e USING (match_id);
