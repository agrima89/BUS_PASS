// Tests for the Netlify Functions, with Supabase simulated by a fake fetch().
// Run: npm test   (Node 18+; no dependencies)
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

import config from "../netlify/functions/config.mjs";
import sign from "../netlify/functions/sign.mjs";
import check from "../netlify/functions/check.mjs";
import { offlinePayload, verifyOffline } from "../netlify/lib/qr.mjs";

const KEY = "test-qr-key";
Object.assign(process.env, {
  SUPABASE_URL: "https://demo.supabase.co", SUPABASE_ANON_KEY: "anon-key",
  QR_SIGNING_KEY: KEY, UNIVERSITY_NAME: "Chandigarh University",
});

// ---- fake Supabase -------------------------------------------------------------
const DB = {
  passes: [
    { id: 1, pass_code: "CU-2026-AAAAAA", status: "valid", expires_at: "2099-12-31", qr_token: "tok_valid_000000000000",
      students: { id: 1, full_name: "Riya Sharma", roll_number: "23BCS1", program: "B.Tech CSE", status: "active",
                  photo_path: "p.jpg", guardian_name: "SECRET-G", address: "SECRET-ADDR", pickup_points: { name: "Kharar" } } },
    { id: 2, pass_code: "CU-2026-BBBBBB", status: "revoked", expires_at: "2099-12-31", qr_token: "tok_revoked_00000000000",
      students: { id: 2, full_name: "Aman", roll_number: "23BCS2", program: "BBA", status: "active", photo_path: null, pickup_points: null } },
  ],
};
let logged = [];
beforeEach(() => { logged = []; });

globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url);
  const auth = init.headers?.authorization || "";
  if (u.pathname === "/auth/v1/user") return new Response("{}", { status: auth === "Bearer good-token" ? 200 : 401 });
  if (u.pathname === "/rest/v1/verifications") { logged.push(JSON.parse(init.body)); return new Response("", { status: 201 }); }
  if (u.pathname === "/rest/v1/passes") {
    const q = u.searchParams;
    let rows = DB.passes;
    if (q.get("id")) { const ids = q.get("id").replace(/^in\.\(|\)$/g, "").split(",").map(Number); rows = rows.filter(r => ids.includes(r.id)); }
    if (q.get("pass_code")) rows = rows.filter(r => r.pass_code === q.get("pass_code").slice(3));
    if (q.get("qr_token")) rows = rows.filter(r => r.qr_token === q.get("qr_token").slice(3));
    return new Response(JSON.stringify(rows), { status: 200 });
  }
  return new Response("not mocked", { status: 500 });
};

const post = (body, token = "good-token") => new Request("https://site/api/x", {
  method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${token}` }, body: JSON.stringify(body) });

// ---- tests ----------------------------------------------------------------------
test("config exposes only public settings", async () => {
  const j = await (await config()).json();
  assert.equal(j.supabaseUrl, "https://demo.supabase.co");
  assert.equal(j.supabaseAnonKey, "anon-key");
  assert.ok(!JSON.stringify(j).includes(KEY), "signing key must never be sent to browsers");
});

test("sign and check reject requests without a valid session", async () => {
  assert.equal((await sign(post({ passIds: [1] }, "bad"))).status, 401);
  assert.equal((await check(post({ text: "x" }, "bad"))).status, 401);
  assert.equal((await sign(new Request("https://site/api/sign"))).status, 405);
});

test("sign builds readable QR text from the database, with no private fields", async () => {
  const { payloads } = await (await sign(post({ passIds: [1, "x", 1] }))).json();
  const text = payloads[1];
  assert.match(text, /^CHANDIGARH UNIVERSITY BUS PASS\nPass No: CU-2026-AAAAAA\nName: Riya Sharma\nUID: 23BCS1\nClass: B.Tech CSE\nPickup: Kharar\nValid upto: 31-12-2099\nSig: [\w-]{22}$/);
  assert.ok(!/SECRET/.test(text));
  assert.ok(verifyOffline(text, KEY));
});

test("check: valid offline QR, with photo path for the staff view", async () => {
  const { payloads } = await (await sign(post({ passIds: [1] }))).json();
  const r = await (await check(post({ text: payloads[1] }))).json();
  assert.equal(r.status, "valid"); assert.equal(r.name, "Riya Sharma"); assert.equal(r.photo_path, "p.jpg");
  assert.deepEqual(logged, [{ pass_id: 1, result: "valid", method: "offline" }]);
  assert.ok(!JSON.stringify(r).includes("SECRET"));
});

test("check: edited or forged offline QR is rejected", async () => {
  const { payloads } = await (await sign(post({ passIds: [1] }))).json();
  assert.equal((await (await check(post({ text: payloads[1].replace("Riya", "Rina") }))).json()).status, "invalid");
  const forged = offlinePayload({ code: "CU-2026-AAAAAA", name: "X", uid: "Y", program: "Z" }, "wrong-key", "Chandigarh University");
  assert.equal((await (await check(post({ text: forged }))).json()).status, "invalid");
});

test("check: revoked and expired passes", async () => {
  const revoked = offlinePayload({ code: "CU-2026-BBBBBB", name: "Aman", uid: "23BCS2", program: "BBA", validIso: "2099-12-31" }, KEY, "Chandigarh University");
  assert.equal((await (await check(post({ text: revoked }))).json()).status, "revoked");
  const expired = offlinePayload({ code: "CU-2026-AAAAAA", name: "Riya Sharma", uid: "23BCS1", program: "B.Tech CSE", validIso: "2020-01-01" }, KEY, "Chandigarh University");
  assert.equal((await (await check(post({ text: expired }))).json()).status, "expired");
});

test("check: online QR by token, and unknown codes", async () => {
  assert.equal((await (await check(post({ text: "https://site/verify.html?t=tok_valid_000000000000" }))).json()).status, "valid");
  assert.equal((await (await check(post({ text: "https://old/verify/tok_revoked_00000000000" }))).json()).status, "revoked");
  assert.equal((await (await check(post({ text: "hello world" }))).json()).status, "not_found");
});

test("legacy UPG1 offline codes from the first Flask version still verify", async () => {
  const crypto = await import("node:crypto");
  const b64 = b => b.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const body = b64(Buffer.from(JSON.stringify({ c: "CU-2026-AAAAAA", n: "Riya Sharma", r: "23BCS1", p: "B.Tech CSE", v: "2099-12-31" })));
  const sig = b64(crypto.createHmac("sha256", KEY).update(`UPG1.${body}`).digest().subarray(0, 16));
  assert.equal((await (await check(post({ text: `UPG1.${body}.${sig}` }))).json()).status, "valid");
});
