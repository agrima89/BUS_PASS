// Shared code for every page of the CU Bus Pass site (Netlify + Supabase).
// Loaded as an ES module. Depends on vendor/supabase-2.45.4.js and
// vendor/qrcode-generator-1.4.4.js being loaded first (classic scripts).

/* ------------------------------------------------------------------ helpers */
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Escape text for safe insertion into HTML. Use for EVERY user-supplied value. */
export const esc = v => String(v ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const dmy = iso => (/^\d{4}-\d{2}-\d{2}/.test(iso || "") ? iso.slice(0, 10).split("-").reverse().join("-") : iso || "");
export const today = () => new Date().toISOString().slice(0, 10);
export const params = new URLSearchParams(location.search);

/* ------------------------------------------------------------- flash messages */
export function flash(msg, type = "success", { persist = false } = {}) {
  if (persist) {
    try { sessionStorage.setItem("flash", JSON.stringify({ msg, type })); } catch {}
    return;
  }
  const box = $("#flash");
  if (!box) return alert(msg);
  const div = document.createElement("div");
  div.className = `flash flash-${type}`;
  div.textContent = msg;
  const x = document.createElement("button");
  x.className = "flash-x"; x.textContent = "×"; x.setAttribute("aria-label", "Dismiss");
  x.onclick = () => div.remove();
  div.append(x);
  box.append(div);
  div.scrollIntoView({ block: "nearest" });
}
function showPersistedFlash() {
  try {
    const f = JSON.parse(sessionStorage.getItem("flash") || "null");
    sessionStorage.removeItem("flash");
    if (f) flash(f.msg, f.type);
  } catch {}
}

/** Turn Supabase / network errors into plain-English messages. */
export function errText(e) {
  const m = e?.message || String(e);
  if (/duplicate key.*roll_number/i.test(m)) return "A student with that UID already exists.";
  if (/duplicate key.*buggy_pass_no/i.test(m)) return "That buggy pass number is already given to another student.";
  if (/column .*buggy_pass_no|pass_term.*does not exist|schema cache/i.test(m)) return "The database needs updating: run supabase/update-1-buggy-number.sql in Supabase (see SETUP.md).";
  if (/Failed to fetch|NetworkError/i.test(m)) return "Can't reach the server. Check the internet connection and try again.";
  if (/JWT|not authenticated|401/i.test(m)) return "Your session expired. Please sign in again.";
  return m;
}

/* ------------------------------------------------------------- config & auth */
let _cfg, _sb;
export async function loadConfig() {
  if (_cfg) return _cfg;
  const r = await fetch("/api/config", { cache: "no-store" });
  const c = await r.json().catch(() => ({}));
  if (!r.ok || c.error) throw new Error(c.error || "Site isn't configured yet: set SUPABASE_URL and SUPABASE_ANON_KEY in Netlify.");
  return (_cfg = c);
}
export async function client() {
  if (_sb) return _sb;
  const c = await loadConfig();
  _sb = window.supabase.createClient(c.supabaseUrl, c.supabaseAnonKey, {
    auth: { persistSession: true, autoRefreshToken: true },
  });
  return _sb;
}

/**
 * Start a page. Staff pages require a signed-in user (redirects to login).
 * Returns { sb, cfg, user }.
 */
export async function boot({ active = "", auth = true } = {}) {
  let cfg;
  try { cfg = await loadConfig(); }
  catch (e) { document.body.innerHTML = `<div class="center-page"><div class="card login-card"><h2>Setup needed</h2><p>${esc(e.message)}</p><p class="hint">See SETUP.md in the project.</p></div></div>`; throw e; }
  const sb = await client();
  let user = null;
  if (auth) {
    const { data } = await sb.auth.getSession();
    user = data.session?.user || null;
    if (!user) { location.replace(`/login.html?next=${encodeURIComponent(location.pathname + location.search)}`); throw new Error("redirecting"); }
    sb.auth.onAuthStateChange((ev, session) => { if (!session) location.replace("/login.html"); });
    renderSidebar(active, cfg, user);
  }
  document.title = document.title.replace("{short}", cfg.universityShort);
  showPersistedFlash();
  return { sb, cfg, user };
}

/** Authenticated call to a Netlify Function. */
export async function api(path, body) {
  const sb = await client();
  const { data } = await sb.auth.getSession();
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${data.session?.access_token || ""}` },
    body: JSON.stringify(body || {}),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.error) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}

/* ------------------------------------------------------------------ sidebar */
const NAV = [
  ["Overview"], ["dashboard", "/", "▦", "Dashboard"],
  ["Students"], ["students", "/students.html", "👥", "Students"], ["new", "/student.html", "＋", "New bus pass"],
  ["Passes"], ["passes", "/passes.html", "🪪", "Issued passes"], ["scan", "/scan.html", "📷", "Scan QR"],
  ["Configuration"], ["settings", "/settings.html", "⚙", "Card settings & stops"],
];
function renderSidebar(active, cfg, user) {
  const side = $("#sidebar");
  if (!side) return;
  side.innerHTML = `
    <div class="brand">
      <img class="brand-emblem" src="/img/cu-emblem.png" alt="${esc(cfg.universityShort)} logo">
      <div><div class="brand-name">${esc(cfg.universityName)}</div><div class="brand-sub">Transport Dept. · Bus Pass</div></div>
    </div>
    <nav class="nav">${NAV.map(n => n.length === 1
      ? `<div class="nav-section">${esc(n[0])}</div>`
      : `<a href="${n[1]}" class="${n[0] === active ? "active" : ""}"><span class="ico">${n[2]}</span> ${esc(n[3])}</a>`).join("")}
    </nav>
    <div class="sidebar-foot">
      <div class="logout"><span>Signed in as <b>${esc(user.email)}</b></span>
      <button class="btn btn-sm btn-ghost" id="signOut">Sign out</button></div>
      <div>${esc(cfg.universityName)} · Transport Department</div>
    </div>`;
  $("#signOut").onclick = async () => { await (await client()).auth.signOut(); location.replace("/login.html"); };
  $("#menuBtn")?.addEventListener("click", () => side.classList.toggle("open"));
}

/* ---------------------------------------------------------------- settings */
export const SETTING_FIELDS = {
  // key: [default, maxLength, multiline, section, label]
  uni_name:        [null, 80, false, "front", "University name"],
  tagline:         ["Discover. Learn. Empower.", 80, false, "front", "Tagline under the name"],
  name_color_1:    ["#CE1A19", 7, false, "front", "Colour: first word of name"],
  name_color_2:    ["#332F2B", 7, false, "front", "Colour: rest of name"],
  tagline_color:   ["#CE1A19", 7, false, "front", "Colour: tagline"],
  card_title:      ["Buggy Pass No.", 40, false, "front", "Card title (next to the pass number)"],
  label_name:      ["Name:", 30, false, "front", "Label: name"],
  label_class:     ["Class/Branch:", 30, false, "front", "Label: class/branch"],
  label_uid:       ["UID:", 30, false, "front", "Label: UID"],
  label_pickup:    ["Pickup Point:", 30, false, "front", "Label: pickup point"],
  print_pass_no:   ["no", 3, false, "front", "Also print the system pass code? (yes / no; normally no)"],
  seal_position:   ["front", 5, false, "front", "Where to print the seal: front / back / both / none"],
  footer_text:     ["Transport Department", 40, false, "front", "Text beside the logo at the bottom of the front"],
  signatory_label: ["", 40, false, "front", "Signatory title under the front seal (e.g. Assistant General Manager)"],
  label_valid:     ["Valid Upto :", 30, false, "back", "Label: valid upto"],
  label_emergency: ["Emergency Contact No.", 40, false, "back", "Label: emergency contact"],
  label_address:   ["Address :", 30, false, "back", "Label: address"],
  return_text:     ["If found Please return to :-\nTransport Deptt. Chandigarh\nUniversity, Gharuan, Mohali, Punjab", 400, true, "back", "Return instructions (one line per row)"],
  contact_label:   ["Contact No.", 40, false, "back", "Label: contact number"],
  contact_value:   ["0160-3044444 Ext. 416", 40, false, "back", "Contact number"],
  helpline_label:  ["Transport Helpline number:", 50, false, "back", "Label: helpline"],
  helpline_value:  ["7087039349", 40, false, "back", "Helpline number"],
  note_label:      ["Note:", 20, false, "back", "Label: note"],
  note_lines:      ["Must carry pass while travelling in buggy.\nPass is not transferable.", 300, true, "back", "Note lines (one per row)"],
  qr_caption:      ["Scan with any phone", 30, false, "back", "Caption under the QR code"],
  pass_prefix:     ["CU", 8, false, "back", "Pass number prefix"],
};
export async function loadSettings() {
  const sb = await client();
  const cfg = await loadConfig();
  const s = Object.fromEntries(Object.entries(SETTING_FIELDS).map(([k, v]) => [k, v[0]]));
  s.uni_name = cfg.universityName;
  s.seal_image = "";
  const { data, error } = await sb.from("settings").select("key,value");
  if (error) throw error;
  for (const r of data || []) if (r.key in s && r.value !== null) s[r.key] = r.value;
  return s;
}

/* -------------------------------------------------------- pass requirements */
export const REQUIRED = [
  ["buggy_pass_no", "buggy pass number"], ["photo_path", "photograph"], ["guardian_name", "guardian name"], ["pickup_point_id", "pickup point"],
  ["emergency_contact", "emergency contact"], ["address", "address"], ["valid_until", "valid-until date"],
];
export const missingFor = st => REQUIRED.filter(([k]) => !st?.[k]).map(([, label]) => label);

/* ------------------------------------------------------------------- photos */
export async function photoUrls(paths) {
  const list = [...new Set(paths.filter(Boolean))];
  if (!list.length) return {};
  const { data } = await (await client()).storage.from("photos").createSignedUrls(list, 3600);
  return Object.fromEntries((data || []).filter(d => d.signedUrl).map(d => [d.path, d.signedUrl]));
}

/* ------------------------------------------------------------------- QR svg */
export function qrSvg(text) {
  const long = text.length > 120;
  const qr = window.qrcode(0, long ? "L" : "M");   // lower correction keeps long text scannable
  window.qrcode.stringToBytes = window.qrcode.stringToBytesFuncs["UTF-8"];
  qr.addData(text, "Byte");
  qr.make();
  const n = qr.getModuleCount(), m = 2;               // 2-module quiet zone
  let d = "";
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += `M${c + m},${r + m}h1v1h-1z`;
  return `<svg viewBox="0 0 ${n + 2 * m} ${n + 2 * m}" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><path d="${d}" fill="#000"/></svg>`;
}

/* ---------------------------------------------------------------- the card */
/** Card data from a pass row joined with student + pickup point. */
export function cardData(p, photoUrl, qrText) {
  const s = p.students || p;
  return {
    pass_code: p.pass_code || "",
    buggy_no: s.buggy_pass_no || "", term: s.pass_term || "",
    name: s.full_name || "", relation: s.guardian_relation || "S/O", guardian: s.guardian_name || "",
    class_line1: s.program || "", class_line2: s.department || "", uid: s.roll_number || "",
    pickup: s.pickup_points?.name || s.pickup || "",
    valid: dmy(p.expires_at ?? s.valid_until), emergency: s.emergency_contact || "",
    address: (s.address || "").split("\n").filter(Boolean),
    photo_url: photoUrl || "", qr_svg: qrText ? qrSvg(qrText) : "",
  };
}

const row = (label, key, val) =>
  `<div class="bp-row">${label !== null ? `<span class="bp-label">${label}</span>` : ""}<span class="bp-val fit" data-out="${key}">${esc(val)}</span></div>`;

export function cardFront(c, s) {
  const [w1, ...rest] = String(s.uni_name || "").split(" ");
  return `<div class="bp-card bp-front">
    <div class="bp-logo"><img src="/img/cu-emblem.png" alt="Logo"></div>
    <div class="bp-uni">
      <div class="bp-uni-name fit-box"><span class="fit-inner"><span style="color:${esc(s.name_color_1)}">${esc(w1)}</span>${rest.length ? ` <span style="color:${esc(s.name_color_2)}">${esc(rest.join(" "))}</span>` : ""}</span></div>
      ${s.tagline ? `<div class="bp-tagline fit" style="color:${esc(s.tagline_color)}">${esc(s.tagline)}</div>` : ""}
    </div>
    <div class="bp-title fit">${esc(s.card_title)} <span data-out="buggy_no">${esc(c.buggy_no)}</span></div>
    <div class="bp-term fit-box" data-out="term">${esc(c.term)}</div>
    ${/^y/i.test(s.print_pass_no) ? `<div class="bp-passno fit">${esc(c.pass_code)}</div>` : ""}
    ${/^(front|both)$/i.test(s.seal_position) ? `<div class="bp-front-seal">${s.seal_image ? `<img src="${esc(s.seal_image)}" alt="Seal">` : ""}</div>` : ""}
    ${s.signatory_label ? `<div class="bp-signatory fit">${esc(s.signatory_label)}</div>` : ""}
    ${s.footer_text ? `<div class="bp-footer"><img src="/img/cu-emblem.png" alt=""><span class="fit">${esc(s.footer_text)}</span></div>` : ""}
    <div class="bp-photo"><img alt="" data-out-photo ${c.photo_url ? `src="${esc(c.photo_url)}"` : "hidden"}></div>
    <div class="bp-fields">
      ${row(esc(s.label_name), "name", c.name)}
      ${row(`<span data-out="relation">${esc(c.relation)}</span>:`, "guardian", c.guardian)}
      ${row(esc(s.label_class), "class_line1", c.class_line1)}
      ${row(null, "class_line2", c.class_line2)}
      ${row(esc(s.label_uid), "uid", c.uid)}
      ${row(esc(s.label_pickup), "pickup", c.pickup)}
    </div>
  </div>`;
}

export function cardBack(c, s) {
  const lines = t => String(t || "").split("\n").map(l => l.trim()).filter(Boolean);
  const ret = lines(s.return_text).map(l => `<div>${esc(l)}</div>`);
  if (s.contact_label || s.contact_value) ret.push(`<div>${esc(s.contact_label)} ${esc(s.contact_value)}</div>`);
  if (s.helpline_label || s.helpline_value) ret.push(`<div>${esc(s.helpline_label)} ${esc(s.helpline_value)}</div>`);
  const notes = lines(s.note_lines);
  return `<div class="bp-card bp-back">
    <div class="bp-frame"></div>
    <div class="bp-valid fit"><span>${esc(s.label_valid)}</span> <b data-out="valid">${esc(c.valid)}</b></div>
    <div class="bp-emergency fit"><span>${esc(s.label_emergency)}</span> <span data-out="emergency">${esc(c.emergency)}</span></div>
    <div class="bp-addr-label">${esc(s.label_address)}</div>
    <div class="bp-address fit-box" data-out="address">${c.address.map(esc).join("<br>")}</div>
    <div class="bp-return fit-box">${ret.join("")}</div>
    ${notes.length ? `<div class="bp-note fit-box"><span class="bp-note-label">${esc(s.note_label)}</span><div class="bp-note-lines">${notes.map(n => `<div>${esc(n)}</div>`).join("")}</div></div>` : ""}
    ${/^(back|both)$/i.test(s.seal_position || "") ? `<div class="bp-seal">${s.seal_image ? `<img src="${esc(s.seal_image)}" alt="Seal">` : "<span>SEAL</span>"}</div>` : ""}
    <div class="bp-qr">${c.qr_svg || `<div class="bp-qr-placeholder">QR</div>`}${s.qr_caption ? `<div class="bp-qr-caption">${esc(s.qr_caption)}</div>` : ""}</div>
  </div>`;
}

export function cropMarks(slots) {
  let l = "";
  for (const [x, y] of slots) for (const cx of [x, x + 85.6]) for (const cy of [y, y + 54]) {
    const sx = cx === x ? -1 : 1, sy = cy === y ? -1 : 1;
    l += `<line x1="${cx + sx * 1.5}" y1="${cy}" x2="${cx + sx * 5.5}" y2="${cy}"/><line x1="${cx}" y1="${cy + sy * 1.5}" x2="${cx}" y2="${cy + sy * 5.5}"/>`;
  }
  return `<svg class="bp-marks" viewBox="0 0 210 297" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${l}</svg>`;
}

/** Fetch passes (+student +pickup) and their QR text, ready for cardData(). */
export async function loadCards(ids) {
  const sb = await client();
  const { data, error } = await sb.from("passes")
    .select("*, students(*, pickup_points(name))").in("id", ids);
  if (error) throw error;
  const offline = data.filter(p => p.qr_mode === "offline").map(p => p.id);
  const { payloads } = offline.length ? await api("/api/sign", { passIds: offline }) : { payloads: {} };
  const urls = await photoUrls(data.map(p => p.students?.photo_path));
  const order = Object.fromEntries(ids.map((id, i) => [id, i]));
  return data.sort((a, b) => order[a.id] - order[b.id]).map(p => ({
    pass: p,
    card: cardData(p, urls[p.students?.photo_path],
      p.qr_mode === "offline" ? payloads[p.id] : `${location.origin}/verify.html?t=${p.qr_token}`),
  }));
}

/* A4 "pairs" layout: each row = front | back, joined at a fold line (171.2 x 54 mm strip).
   Cut the strip out, fold on the dashed line, laminate -> a double-sided card.
   4 rows per A4 page. Coordinates in mm. */
export const PAIR = { x0: 19.4, y0: 16, rowGap: 9, rows: 4 };
export function pairSlots(n) {
  return Array.from({ length: n }, (_, i) => [PAIR.x0, +(PAIR.y0 + i * (54 + PAIR.rowGap)).toFixed(1)]);
}
export function pairMarks(slots) {
  // crop marks around each 171.2 x 54 strip + a dashed fold line in the middle
  let l = "";
  for (const [x, y] of slots) {
    const W = 171.2;
    for (const cx of [x, x + W]) for (const cy of [y, y + 54]) {
      const sx = cx === x ? -1 : 1, sy = cy === y ? -1 : 1;
      l += `<line x1="${cx + sx * 1.5}" y1="${cy}" x2="${cx + sx * 5.5}" y2="${cy}"/><line x1="${cx}" y1="${cy + sy * 1.5}" x2="${cx}" y2="${cy + sy * 4}"/>`;
    }
    const fx = x + 85.6;
    l += `<line x1="${fx}" y1="${y - 4}" x2="${fx}" y2="${y - 1.5}"/><line x1="${fx}" y1="${y + 55.5}" x2="${fx}" y2="${y + 58}"/>`;
  }
  return `<svg class="bp-marks" viewBox="0 0 210 297" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${l}</svg>`;
}
