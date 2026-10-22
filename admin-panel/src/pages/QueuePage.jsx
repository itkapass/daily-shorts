import { useEffect, useState, useCallback } from "react";
import { supabase } from "../lib/supabase.js";
import VideoRow from "../components/VideoRow.jsx";

const STATUS_FILTERS = [
  { value: "", label: "All statuses" },
  { value: "approved", label: "Approved" },
  { value: "published", label: "Published" },
  { value: "held", label: "Held" },
  { value: "regenerate_requested", label: "Regen requested" },
  { value: "rendering", label: "Rendering" },
  { value: "failed", label: "Failed" },
];

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

export default function QueuePage() {
  const [videos, setVideos] = useState(null);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [upcomingOnly, setUpcomingOnly] = useState(true);

  const load = useCallback(async () => {
    let query = supabase.from("videos").select("*").order("scheduled_date", { ascending: true });
    if (upcomingOnly) query = query.gte("scheduled_date", todayStr());
    const { data, error: fetchError } = await query;
    if (fetchError) {
      setError(fetchError.message);
      return;
    }
    setError("");
    setVideos(data || []);
  }, [upcomingOnly]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return <div className="empty-state">Couldn't load videos: {error}</div>;
  }
  if (videos === null) {
    return <div className="empty-state">Loading…</div>;
  }

  const readyDates = videos
    .filter((v) => v.status === "approved" || v.status === "published")
    .map((v) => v.scheduled_date)
    .sort();
  const readyThrough = readyDates.length ? readyDates[readyDates.length - 1] : "—";
  const needsReviewCount = videos.filter((v) => v.review_flag).length;
  const pendingRegenCount = videos.filter((v) => v.status === "regenerate_requested").length;

  const filtered = videos.filter((v) => {
    if (statusFilter && v.status !== statusFilter) return false;
    if (reviewOnly && !v.review_flag) return false;
    return true;
  });

  return (
    <div>
      <div className="summary-bar">
        <div className="summary-card">
          <div className="label">Ready through</div>
          <div className="value">{readyThrough}</div>
        </div>
        <div className="summary-card">
          <div className="label">Videos {upcomingOnly ? "upcoming" : "total"}</div>
          <div className="value">{videos.length}</div>
        </div>
        <div className="summary-card">
          <div className="label">Needs review</div>
          <div className="value">{needsReviewCount}</div>
        </div>
        <div className="summary-card">
          <div className="label">Regen requested</div>
          <div className="value">{pendingRegenCount}</div>
        </div>
      </div>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {STATUS_FILTERS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)} />
          Needs review only
        </label>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={upcomingOnly} onChange={(e) => setUpcomingOnly(e.target.checked)} />
          Upcoming only (hide past dates)
        </label>
        <button className="action-btn" onClick={load}>Refresh</button>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">No videos match these filters.</div>
      ) : (
        <div className="video-list">
          {filtered.map((v) => (
            <VideoRow key={v.job_id} video={v} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
