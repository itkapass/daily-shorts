-- ════════════════════════════════════════════════════════════════
-- Daily History Shorts — Supabase schema
--
-- HOW TO RUN:
--   1. Supabase Dashboard -> SQL Editor -> paste this whole file -> Run
--   2. That's it — no users/auth needed. The Python pipeline connects
--      with the service_role key, which bypasses Row Level Security
--      entirely by design (that's what SUPABASE_SERVICE_KEY is for).
--      RLS is enabled below with NO policies, which locks the public
--      anon key out completely — exactly what you want, since this
--      project ships no admin panel that would need anon access.
-- ════════════════════════════════════════════════════════════════

-- ── Settings (key/value: budgets, failure counters) ─────────────────
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    description TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Videos (the generation + publish queue) ──────────────────────────
CREATE TABLE IF NOT EXISTS videos (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT UNIQUE NOT NULL,
    category        TEXT NOT NULL,          -- born_today | died_today | born_died_india |
                                             -- history | history_world | history_india
    part_number     INT,                     -- NULL when the day didn't need splitting
    scheduled_date  DATE NOT NULL,           -- the calendar date this video is ABOUT
    scheduled_at    TIMESTAMPTZ,             -- when it's slotted to actually publish
    title           TEXT,
    description     TEXT,
    hashtags        JSONB DEFAULT '[]',
    duration        FLOAT,
    storyboard      JSONB,
    status          TEXT DEFAULT 'rendering', -- rendering | approved | published | failed
    review_flag     BOOLEAN DEFAULT FALSE,    -- quality-gate warning or near-duplicate match
    llm_provider    TEXT,                     -- gemini | groq | github_models
    voice_engine    TEXT,                     -- google_tts | azure_tts | kokoro | xtts_clone | elevenlabs | gtts
    srt_content     TEXT,
    storage_url     TEXT,
    storage_backend TEXT,
    youtube_id      TEXT,
    youtube_url     TEXT,
    error_log       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    published_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Playlists (one row per category/part -> YouTube playlist id) ────
CREATE TABLE IF NOT EXISTS playlists (
    id                  BIGSERIAL PRIMARY KEY,
    category            TEXT NOT NULL,
    part_number         INT,
    youtube_playlist_id TEXT NOT NULL,
    title               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (category, part_number)
);

-- ── Lunar / shifting festival dates (Diwali, Eid, Gurpurab, ...) ─────
-- Deliberately ships EMPTY. See engine/observances.py's module docstring
-- for why no dates are hardcoded here — run the yearly refresh job
-- (docs/07) or insert this year's real dates yourself as a one-time
-- bootstrap.
CREATE TABLE IF NOT EXISTS observances_lunar (
    id         BIGSERIAL PRIMARY KEY,
    year       INT NOT NULL,
    month      INT NOT NULL,
    day        INT NOT NULL,
    name       TEXT NOT NULL,
    tone       TEXT DEFAULT 'celebratory',
    source     TEXT DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (year, month, day, name)
);

-- ── Review queue (Section 4: source-disagreement candidates) ────────
CREATE TABLE IF NOT EXISTS review_queue (
    id               BIGSERIAL PRIMARY KEY,
    date             DATE NOT NULL,
    category         TEXT,
    subject          TEXT,
    wikipedia_title  TEXT,
    conflict_detail  TEXT,
    status           TEXT DEFAULT 'pending',  -- pending | cleared | discarded
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── Evergreen fallback videos (Section 10) ───────────────────────────
-- Ships EMPTY. One slot failing twice in a row substitutes a row from
-- here instead of leaving the slot empty — see docs/START_HERE.md for
-- how to record at least one fallback per category before relying on
-- this in production.
CREATE TABLE IF NOT EXISTS fallback_videos (
    id           BIGSERIAL PRIMARY KEY,
    category     TEXT,
    part_number  INT,
    storage_url  TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT DEFAULT '',
    is_generic   BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_scheduled_at ON videos(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_videos_category_date ON videos(category, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_observances_lunar_date ON observances_lunar(year, month, day);

-- ── Row Level Security ────────────────────────────────────────────
-- Enabled with NO policies -> the anon/public key gets nothing. The
-- Python engine's service_role key bypasses RLS entirely and needs no
-- policy at all.
ALTER TABLE settings          ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos            ENABLE ROW LEVEL SECURITY;
ALTER TABLE playlists         ENABLE ROW LEVEL SECURITY;
ALTER TABLE observances_lunar ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_queue      ENABLE ROW LEVEL SECURITY;
ALTER TABLE fallback_videos   ENABLE ROW LEVEL SECURITY;
