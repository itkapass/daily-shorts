const LABELS = {
  approved: "Approved",
  published: "Published",
  rendering: "Rendering",
  failed: "Failed",
  held: "Held",
  regenerate_requested: "Regen requested",
};

export default function StatusBadge({ status }) {
  const cls = `badge badge-${status || "rendering"}`;
  return <span className={cls}>{LABELS[status] || status || "unknown"}</span>;
}
