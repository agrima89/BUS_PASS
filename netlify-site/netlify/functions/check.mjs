// POST /api/check {text} -> verdict for a scanned QR (staff scanner page).
// Offline QR: signature check + current status from the database.
// Online QR (".../verify?t=<token>" or legacy ".../verify/<token>"): status by token.
import { isOfflinePayload, verifyOffline } from "../lib/qr.mjs";
import { env, json, requireUser, rest } from "../lib/supabase.mjs";

const today = () => new Date().toISOString().slice(0, 10);

function statusOf(row, validIso) {
  if (row && (row.status === "revoked" || row.students?.status !== "active")) return "revoked";
  if (validIso && validIso < today()) return "expired";
  return "valid";
}

export default async (req) => {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  try {
    const token = await requireUser(req);
    if (!token) return json({ error: "Please sign in again." }, 401);
    const { text } = await req.json().catch(() => ({}));
    const t = String(text || "").trim().slice(0, 4096);
    const select = "id,pass_code,status,expires_at,qr_token,students(id,full_name,roll_number,program,status,photo_path)";
    const log = (pass_id, result, method) =>
      rest(token, "verifications", { method: "POST", body: JSON.stringify({ pass_id, result, method }) });

    if (isOfflinePayload(t)) {
      const f = verifyOffline(t, env("QR_SIGNING_KEY"));
      if (!f) { await log(null, "invalid", "offline"); return json({ status: "invalid", method: "offline" }); }
      const [row] = await rest(token, `passes?pass_code=eq.${encodeURIComponent(f.code)}&select=${select}`);
      const status = statusOf(row, f.validIso);
      await log(row?.id ?? null, status, "offline");
      return json({ status, method: "offline", pass_code: f.code, name: f.name, uid: f.uid,
                    program: f.program, pickup: f.pickup, valid_until: f.validIso || null,
                    photo_path: row?.students?.photo_path || null });
    }

    const m = t.match(/[?&]t=([A-Za-z0-9_-]{16,64})/) || t.match(/\/verify\/([A-Za-z0-9_-]{16,64})\/?$/);
    const [row] = m ? await rest(token, `passes?qr_token=eq.${m[1]}&select=${select}`) : [];
    if (!row) { await log(null, "not_found", "online"); return json({ status: "not_found", method: "online" }); }
    const status = statusOf(row, row.expires_at);
    await log(row.id, status, "online");
    const s = row.students || {};
    return json({ status, method: "online", pass_code: row.pass_code, name: s.full_name, uid: s.roll_number,
                  program: s.program, valid_until: row.expires_at, photo_path: s.photo_path || null });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
};

export const config = { path: "/api/check" };
