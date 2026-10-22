-- ════════════════════════════════════════════════════════════════
-- Migration 001 — admin panel support
--
-- HOW TO RUN: Supabase Dashboard -> SQL Editor -> paste this whole
-- file -> Run. Safe to run on an already-running project (everything
-- is IF NOT EXISTS / CREATE OR REPLACE).
--
-- WHAT THIS ADDS
--   1. videos.admin_note — a human reviewer's note attached when they
--      mark a video for regeneration (engine/orchestrator.py picks
--      this up on the next generation run for that date/category and
--      feeds it to the script-writing prompt as extra guidance).
--   2. RLS policies for the 'authenticated' role (NOT 'anon') on the
--      tables the admin panel needs — SELECT everywhere it reads,
--      UPDATE only on videos/review_queue (the two things the panel
--      actually changes). The 'anon'/'public' role still gets ZERO
--      access, exactly as the original schema intended — the admin
--      panel's Supabase client uses the public anon key, but every
--      query runs as a signed-in user (Supabase Auth), which is what
--      'authenticated' actually means here. See
--      docs/08_ADMIN_PANEL.md for the one-time step to create that
--      one admin login.
--
-- STATUS VALUES: the admin panel introduces two new values for
-- videos.status beyond the engine's own rendering/approved/published/
-- failed — 'held' (approved content, deliberately paused before
-- publish) and 'regenerate_requested' (flagged for a redo with a
-- note). Nothing else needs to change for these to work: scheduler.py's
-- due_for_publish() already filters strictly on status='approved', so
-- a held or regenerate-requested video is automatically skipped by
-- publish_queue.py with zero code changes there.
-- ════════════════════════════════════════════════════════════════

ALTER TABLE videos ADD COLUMN IF NOT EXISTS admin_note TEXT;

-- ── videos: admin panel can read everything, and change only the
--    handful of fields a human reviewer should be able to touch ──────
DROP POLICY IF EXISTS admin_panel_select_videos ON videos;
CREATE POLICY admin_panel_select_videos ON videos
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS admin_panel_update_videos ON videos;
CREATE POLICY admin_panel_update_videos ON videos
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- ── review_queue: read + change status (pending/cleared/discarded) ──
DROP POLICY IF EXISTS admin_panel_select_review_queue ON review_queue;
CREATE POLICY admin_panel_select_review_queue ON review_queue
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS admin_panel_update_review_queue ON review_queue;
CREATE POLICY admin_panel_update_review_queue ON review_queue
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- ── playlists / fallback_videos: read-only, informational ──────────
DROP POLICY IF EXISTS admin_panel_select_playlists ON playlists;
CREATE POLICY admin_panel_select_playlists ON playlists
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS admin_panel_select_fallback_videos ON fallback_videos;
CREATE POLICY admin_panel_select_fallback_videos ON fallback_videos
    FOR SELECT TO authenticated USING (true);

-- settings / observances_lunar deliberately get NO authenticated
-- policy — the admin panel has no page for either yet, and the
-- Python engine (service_role) doesn't need RLS policies at all since
-- service_role bypasses RLS entirely by design.
