import { useEffect, useState } from "react";
import { supabase, configMissing } from "./lib/supabase.js";
import LoginPage from "./pages/LoginPage.jsx";
import QueuePage from "./pages/QueuePage.jsx";
import ReviewQueuePage from "./pages/ReviewQueuePage.jsx";

function ConfigMissingScreen() {
  return (
    <div className="config-missing">
      <h2>Almost there — set up your .env</h2>
      <p>
        This admin panel needs your Supabase project's URL and <strong>anon</strong> key (not the
        service_role key the Python pipeline uses). Copy <code>.env.example</code> to{" "}
        <code>.env</code> in the <code>admin-panel/</code> folder and fill in both values from
        Supabase Dashboard → Project Settings → API. See{" "}
        <code>docs/09_ADMIN_PANEL.md</code> for the full walkthrough.
      </p>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(undefined);
  const [tab, setTab] = useState("queue");

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  if (configMissing) return <ConfigMissingScreen />;
  if (session === undefined) return <div className="empty-state">Loading…</div>;
  if (!session) return <LoginPage />;

  return (
    <div className="app-shell">
      <div className="topbar">
        <h1>Daily History Shorts — Admin</h1>
        <div className="tabs">
          <button className={`tab-btn ${tab === "queue" ? "active" : ""}`} onClick={() => setTab("queue")}>
            Video Queue
          </button>
          <button className={`tab-btn ${tab === "review" ? "active" : ""}`} onClick={() => setTab("review")}>
            Review Queue
          </button>
        </div>
        <button className="logout-btn" onClick={() => supabase.auth.signOut()}>
          Sign out
        </button>
      </div>
      <div className="main">
        {tab === "queue" ? <QueuePage /> : <ReviewQueuePage />}
      </div>
    </div>
  );
}
