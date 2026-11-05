// Live buggy-pass preview: mirrors the student form into the card templates
// (the same HTML used for printing) as you type. Uses textContent only, so
// nothing typed can inject HTML.
(() => {
  const form = document.getElementById("studentForm");
  if (!form) return;
  const panel = document.querySelector(".preview-panel");
  const $ = name => form.querySelector(`[name="${name}"]`);
  const outs = key => panel.querySelectorAll(`[data-out="${key}"]`);
  const dmy = iso => (/^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.split("-").reverse().join("-") : iso);

  const setText = (key, value) => outs(key).forEach(el => (el.textContent = value));

  function sync() {
    setText("name", $("full_name").value.trim());
    setText("relation", $("guardian_relation").value);
    setText("guardian", $("guardian_name").value.trim());
    setText("class_line1", $("program").value.trim());
    setText("class_line2", $("department").value.trim());
    setText("uid", $("roll_number").value.trim());
    setText("pickup", $("pickup_point").value.trim());
    setText("valid", dmy($("valid_until").value));
    setText("emergency", $("emergency_contact").value.trim());
    outs("address").forEach(el => {
      el.replaceChildren();
      $("address").value.split("\n").map(l => l.trim()).filter(Boolean).forEach((line, i) => {
        if (i) el.append(document.createElement("br"));
        el.append(line);
      });
    });
    window.BuggyCard?.fitCards(panel);
  }
  form.addEventListener("submit", e => {
    if (!photoError.hidden) { e.preventDefault(); photoError.scrollIntoView({ block: "center" }); }
  });
  form.addEventListener("input", sync);
  form.addEventListener("change", sync);

  // Photo: show the chosen file immediately (local object URL, never uploaded until Save).
  const img = panel.querySelector("[data-out-photo]");
  const original = img.getAttribute("src");
  let objectUrl = null;
  const showPhoto = src => {
    if (src) { img.src = src; img.hidden = false; } else { img.removeAttribute("src"); img.hidden = true; }
  };
  // Shrink big photos in the browser before upload (phone photos are often 5-15 MB).
  // The server re-crops to 600x800 anyway, so 1600 px on the long side is plenty.
  const MAX_SIDE = 1600, SHRINK_OVER = 1.5 * 1024 * 1024;
  async function shrinkIfLarge(input) {
    const file = input.files[0];
    if (!file || !file.type.startsWith("image/") || file.size <= SHRINK_OVER) return;
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: "from-image" }); // honours phone rotation
      const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(bmp.width * scale); canvas.height = Math.round(bmp.height * scale);
      canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.9));
      if (!blob) return;
      const dt = new DataTransfer();
      dt.items.add(new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }));
      input.files = dt.files;
    } catch { /* unsupported format in this browser: upload the original */ }
  }

  // Clear, inline photo errors -- checked before anything is sent to the server.
  const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
  const MAX_UPLOAD = 20 * 1024 * 1024;
  const photoError = document.getElementById("photoError");
  const showError = msg => {
    photoError.textContent = msg || "";
    photoError.hidden = !msg;
    document.getElementById("photoInput").classList.toggle("invalid", !!msg);
  };

  document.getElementById("photoInput")?.addEventListener("change", async e => {
    const input = e.target;
    showError("");
    const picked = input.files[0];
    if (picked && !ALLOWED.includes(picked.type)) {
      showError(`“${picked.name}” is not a supported photo. Please choose a JPG, PNG or WEBP image.`);
      input.value = "";
    }
    const save = form.querySelector(".save-bar .btn-primary");
    if (save) save.disabled = true;           // don't submit while the photo is being shrunk
    try { await shrinkIfLarge(input); } finally { if (save) save.disabled = false; }
    if (input.files[0] && input.files[0].size > MAX_UPLOAD) {
      showError(`This photo is too large (${(input.files[0].size / 1048576).toFixed(1)} MB) and couldn't be reduced. ` +
                "Please choose a smaller photo (under 20 MB).");
      input.value = "";
    }
    const file = input.files[0];
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = file && file.type.startsWith("image/") ? URL.createObjectURL(file) : null;
    showPhoto(objectUrl || original);
  });
  document.getElementById("removePhoto")?.addEventListener("change", e => {
    if (!objectUrl) showPhoto(e.target.checked ? null : original);
  });

  // Front / back toggle.
  panel.querySelectorAll(".seg-btn").forEach(btn => btn.addEventListener("click", () => {
    panel.querySelectorAll(".seg-btn").forEach(b => b.classList.toggle("active", b === btn));
    panel.querySelectorAll("[data-side-panel]").forEach(p => (p.hidden = p.dataset.sidePanel !== btn.dataset.side));
    window.BuggyCard?.zoomCards(panel);
    window.BuggyCard?.fitCards(panel);
  }));

  sync();
})();

// After a save with missing details, jump to the banner so it's obvious what to do next.
document.getElementById("pendingBanner")?.scrollIntoView({ block: "start", behavior: "smooth" });
