import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const configMissing = !url || !anonKey || url.includes("your-project-id");

// A deliberately dumb placeholder client when config is missing, so the
// app can render a clear "set up your .env" screen instead of a blank
// crash — see App.jsx.
export const supabase = configMissing ? null : createClient(url, anonKey);
