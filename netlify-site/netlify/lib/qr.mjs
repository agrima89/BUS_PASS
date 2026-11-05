// Readable, signed offline QR text. Identical format to the Flask version
// (app/services/qr.py), so cards from either verify in both with the same key.
//
//   CHANDIGARH UNIVERSITY BUS PASS
//   Pass No: CU-2026-K7Q2XZ
//   Name: ...            UID: ...           Class: ...
//   Pickup: ...          (only if set)
//   Valid upto: 31-12-2026   ("-" if none)
//   Sig: <22-char base64url HMAC-SHA256, first 16 bytes>
import crypto from "node:crypto";

const SIG_LABEL = "Sig: ";

const b64url = buf => buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export const dmy = iso => (/^\d{4}-\d{2}-\d{2}$/.test(iso || "") ? iso.split("-").reverse().join("-") : iso || "");
const iso = d => (/^\d{2}-\d{2}-\d{4}$/.test(d || "") ? d.split("-").reverse().join("-") : d || "");

function canonical({ code, name, uid, program, pickup, validIso }) {
  return ["UPG2", code, name, uid, program, pickup, validIso].join("\x1f");
}

function sign(message, key) {
  return b64url(crypto.createHmac("sha256", key).update(message, "utf8").digest().subarray(0, 16));
}

export function offlinePayload(f, key, universityName) {
  const fields = { code: f.code, name: f.name || "", uid: f.uid || "", program: f.program || "",
                   pickup: f.pickup || "", validIso: f.validIso || "" };
  const lines = [`${universityName.toUpperCase()} BUS PASS`, `Pass No: ${fields.code}`,
                 `Name: ${fields.name}`, `UID: ${fields.uid}`, `Class: ${fields.program}`];
  if (fields.pickup) lines.push(`Pickup: ${fields.pickup}`);
  lines.push(`Valid upto: ${dmy(fields.validIso) || "-"}`, `${SIG_LABEL}${sign(canonical(fields), key)}`);
  return lines.join("\n");
}

export function isOfflinePayload(text) {
  const t = (text || "").trim().replace(/\r\n/g, "\n");
  return t.startsWith("UPG1.") || t.includes(`\n${SIG_LABEL}`);
}

/** Returns {code,name,uid,program,pickup,validIso} when the signature is valid, else null. */
export function verifyOffline(text, key) {
  const t = (text || "").trim().replace(/\r\n/g, "\n");
  if (t.startsWith("UPG1.")) return verifyLegacy(t, key);
  const f = {};
  for (const line of t.split("\n").slice(1)) {
    const i = line.indexOf(": ");
    if (i > 0) f[line.slice(0, i).trim()] = line.slice(i + 2).trim();
  }
  if (!f.Sig || !f["Pass No"] || f.Name === undefined || f.UID === undefined) return null;
  const fields = { code: f["Pass No"], name: f.Name, uid: f.UID, program: f.Class ?? "",
                   pickup: f.Pickup ?? "", validIso: f["Valid upto"] && f["Valid upto"] !== "-" ? iso(f["Valid upto"]) : "" };
  const expected = sign(canonical(fields), key);
  if (f.Sig.length !== expected.length ||
      !crypto.timingSafeEqual(Buffer.from(f.Sig), Buffer.from(expected))) return null;
  return fields;
}

function verifyLegacy(t, key) {     // "UPG1.<base64url json>.<sig>" from early Flask versions
  const parts = t.split(".");
  if (parts.length !== 3) return null;
  const expected = sign(`${parts[0]}.${parts[1]}`, key);
  if (parts[2].length !== expected.length ||
      !crypto.timingSafeEqual(Buffer.from(parts[2]), Buffer.from(expected))) return null;
  try {
    const d = JSON.parse(Buffer.from(parts[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8"));
    return { code: d.c, name: d.n, uid: d.r, program: d.p, pickup: "", validIso: d.v || "" };
  } catch { return null; }
}
