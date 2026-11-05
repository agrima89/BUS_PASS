// Minimal Supabase REST helpers for Netlify Functions.
// Every call is made WITH THE SIGNED-IN USER'S token, so database row-level
// security applies exactly as in the browser. No service-role key is needed.

export function env(name) {
  const v = process.env[name];
  if (!v) throw new Error(`Missing environment variable ${name} (set it in Netlify > Site configuration > Environment variables).`);
  return v;
}

export const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

/** Returns the bearer token if it belongs to a signed-in Supabase user, else null. */
export async function requireUser(req) {
  const auth = req.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return null;
  const r = await fetch(`${env("SUPABASE_URL")}/auth/v1/user`, {
    headers: { apikey: env("SUPABASE_ANON_KEY"), authorization: `Bearer ${token}` },
  });
  return r.ok ? token : null;
}

export async function rest(token, path, init = {}) {
  const r = await fetch(`${env("SUPABASE_URL")}/rest/v1/${path}`, {
    ...init,
    headers: { apikey: env("SUPABASE_ANON_KEY"), authorization: `Bearer ${token}`,
               "content-type": "application/json", ...(init.headers || {}) },
  });
  if (!r.ok) throw new Error(`Supabase ${r.status}: ${await r.text()}`);
  const text = await r.text();
  return text ? JSON.parse(text) : null;
}
