// GET /api/config -> public settings for the browser (the anon key is public by design;
// row-level security in Supabase is what protects the data).
import { env, json } from "../lib/supabase.mjs";

export default async () => {
  try {
    return json({
      supabaseUrl: env("SUPABASE_URL"),
      supabaseAnonKey: env("SUPABASE_ANON_KEY"),
      universityName: process.env.UNIVERSITY_NAME || "Chandigarh University",
      universityShort: process.env.UNIVERSITY_SHORT || "CU",
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
};

export const config = { path: "/api/config" };
