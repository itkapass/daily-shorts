import { useEffect, useState, useCallback } from "react";
import { supabase } from "../lib/supabase.js";

export default function ReviewQueuePage() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const { data, error: fetchError } = await supabase
      .from("review_queue")
      .select("*")
      .eq("status", "pending")
      .order("created_at", { ascending: false });
    if (fetchError) {
      setError(fetchError.message);
      return;
    }
    setError("");
    setRows(data || []);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function setStatus(id, status) {
    const { error: updateError } = await supabase.from("review_queue").update({ status }).eq("id", id);
    if (updateError) {
      alert(`Update failed: ${updateError.message}`);
      return;
    }
    load();
  }

  if (error) return <div className="empty-state">Couldn't load review queue: {error}</div>;
  if (rows === null) return <div className="empty-state">Loading…</div>;

  return (
    <div>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
        Candidates where two sources disagreed on a date/fact, so they were held back from any
        video rather than aired as unverified. Clear one once you've checked it's fine, or discard
        it permanently.
      </p>
      {rows.length === 0 ? (
        <div className="empty-state">Nothing pending — every candidate's facts checked out.</div>
      ) : (
        <div className="video-list">
          {rows.map((r) => (
            <div className="video-row" key={r.id} style={{ cursor: "default" }}>
              <div className="video-row-head">
                <div className="video-row-title">{r.subject || r.wikipedia_title || "(unknown subject)"}</div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>{r.date} · {r.category}</div>
              </div>
              <div className="video-row-meta">{r.conflict_detail}</div>
              <div className="action-row">
                <button className="action-btn" onClick={() => setStatus(r.id, "cleared")}>
                  Clear — looks fine
                </button>
                <button className="action-btn danger" onClick={() => setStatus(r.id, "discarded")}>
                  Discard
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
