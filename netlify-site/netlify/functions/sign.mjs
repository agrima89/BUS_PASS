// POST /api/sign {passIds: [1,2,...]} -> {payloads: {id: "<readable signed QR text>"}}
// Staff only. The QR text is built from the DATABASE row, never from the request,
// so a browser can't get arbitrary data signed. The key lives only in Netlify env.
import { offlinePayload } from "../lib/qr.mjs";
import { env, json, requireUser, rest } from "../lib/supabase.mjs";

export default async (req) => {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  try {
    const token = await requireUser(req);
    if (!token) return json({ error: "Please sign in again." }, 401);

    const { passIds } = await req.json().catch(() => ({}));
    const ids = [...new Set((Array.isArray(passIds) ? passIds : []).map(Number).filter(Number.isInteger))].slice(0, 200);
    if (!ids.length) return json({ payloads: {} });

    const rows = await rest(token,
      `passes?id=in.(${ids.join(",")})&select=id,pass_code,expires_at,` +
      `students(full_name,roll_number,program,pickup_points(name))`);
    const key = env("QR_SIGNING_KEY");
    const uni = process.env.UNIVERSITY_NAME || "Chandigarh University";
    const payloads = {};
    for (const p of rows) {
      const s = p.students || {};
      payloads[p.id] = offlinePayload({
        code: p.pass_code, name: s.full_name, uid: s.roll_number, program: s.program,
        pickup: s.pickup_points?.name || "", validIso: p.expires_at || "",
      }, key, uni);
    }
    return json({ payloads });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
};

export const config = { path: "/api/sign" };
