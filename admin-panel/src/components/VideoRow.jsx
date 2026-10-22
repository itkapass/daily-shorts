import { useState } from "react";
import StatusBadge from "./StatusBadge.jsx";
import { supabase } from "../lib/supabase.js";

const VISUAL_LABELS = {
  wikidata_qid: "📷 Photo",
  ai_abstract: "🎨 AI art",
  text_card: "🅰 Text card",
  none: "⚠ None",
};

function visualClass(source) {
  if (source === "wikidata_qid") return "photo";
  if (source === "ai_abstract") return "ai_abstract";
  if (source === "text_card") return "text_card";
  return "none";
}

export default function VideoRow({ video, onChanged }) {
  const [open, setOpen] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [showNoteBox, setShowNoteBox] = useState(false);
  const [busy, setBusy] = useState(false);

  const scenes = video.storyboard?.scenes || [];
  const photoCount = scenes.filter((s) => s.visual_source === "wikidata_qid").length;

  async function update(fields) {
    setBusy(true);
    const { error } = await supabase.from("videos").update(fields).eq("job_id", video.job_id);
    setBusy(false);
    if (error) {
      alert(`Update failed: ${error.message}`);
      return;
    }
    onChanged();
  }

  async function handleHold() {
    await update({ status: "held" });
  }

  async function handleRelease() {
    await update({ status: "approved" });
  }

  async function handleClearReviewFlag() {
    await update({ review_flag: false });
  }

  async function submitRegenerate() {
    if (!noteDraft.trim()) return;
    await update({ status: "regenerate_requested", admin_note: noteDraft.trim() });
    setShowNoteBox(false);
    setNoteDraft("");
  }

  return (
    <div className="video-row" onClick={() => setOpen((o) => !o)}>
      <div className="video-row-head">
        <StatusBadge status={video.status} />
        {video.review_flag && <span className="badge badge-review">Needs review</span>}
        <div className="video-row-title">{video.title || "(no title yet)"}</div>
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          {video.category}
          {video.part_number ? ` · part ${video.part_number}` : ""}
        </div>
      </div>
      <div className="video-row-meta">
        For {video.scheduled_date}
        {video.scheduled_at ? ` · posts ${new Date(video.scheduled_at).toLocaleString()}` : ""}
        {" · "}
        {photoCount}/{scenes.length || "?"} scenes used a real photo
        {video.admin_note ? ` · note: "${video.admin_note}"` : ""}
      </div>

      {open && (
        <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
          {video.storage_url && (
            <video controls src={video.storage_url} preload="metadata" />
          )}

          {video.description && (
            <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 0 }}>{video.description}</p>
          )}

          {scenes.length > 0 && (
            <div className="scene-list">
              {scenes.map((s, i) => (
                <div className="scene-item" key={i}>
                  <div className="scene-meta">
                    <span className={`visual-chip ${visualClass(s.visual_source)}`}>
                      {VISUAL_LABELS[s.visual_source] || "⚠ Unknown"}
                    </span>
                    {s.subject_qid && s.subject_qid !== "null" && (
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>{s.subject_qid}</span>
                    )}
                  </div>
                  {s.voice_text}
                </div>
              ))}
            </div>
          )}

          {video.error_log && (
            <p style={{ fontSize: 12, color: "var(--bad)" }}>Last error: {video.error_log}</p>
          )}

          <div className="action-row">
            {video.status === "approved" && (
              <button className="action-btn" disabled={busy} onClick={handleHold}>
                Hold (don't publish yet)
              </button>
            )}
            {video.status === "held" && (
              <button className="action-btn primary" disabled={busy} onClick={handleRelease}>
                Release (allow publish)
              </button>
            )}
            {video.review_flag && (
              <button className="action-btn" disabled={busy} onClick={handleClearReviewFlag}>
                Clear review flag — looks fine
              </button>
            )}
            {video.status !== "regenerate_requested" && video.status !== "published" && (
              <button
                className="action-btn danger"
                disabled={busy}
                onClick={() => setShowNoteBox((v) => !v)}
              >
                Regenerate with a note…
              </button>
            )}
          </div>

          {showNoteBox && (
            <div className="note-box">
              <textarea
                placeholder="What should be different next time? e.g. 'wrong photo used for the boxer scene' or 'double-check the 1980 date'"
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
              />
              <div className="action-row">
                <button className="action-btn primary" disabled={busy || !noteDraft.trim()} onClick={submitRegenerate}>
                  Submit — regenerate on next run
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
