// Camera QR scanner. Uses the browser's native BarcodeDetector when available
// (Chrome on Android), otherwise the bundled jsQR library. Decoding happens
// locally; only the decoded text is sent to the server for checking.
(() => {
  const video = document.getElementById("video");
  const msg = document.getElementById("scanMsg");
  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const camSelect = document.getElementById("camSelect");
  const body = document.getElementById("resultBody");
  const card = document.getElementById("resultCard");
  const checkUrl = document.getElementById("scanScript").dataset.checkUrl;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let stream = null, raf = null, busy = false, lastText = "", lastAt = 0, detector = null;

  if ("BarcodeDetector" in window) {
    try { detector = new BarcodeDetector({ formats: ["qr_code"] }); } catch { detector = null; }
  }

  const LABELS = {
    valid: "✔ VALID PASS", expired: "⚠ PASS EXPIRED", revoked: "✖ PASS REVOKED",
    not_found: "✖ UNKNOWN PASS", invalid: "✖ INVALID / TAMPERED QR", error: "✖ CHECK FAILED",
  };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text; // textContent only: never inject HTML
    return e;
  }

  function show(r) {
    body.replaceChildren();
    card.className = `card scan-result result-${r.status}`;
    body.append(el("div", `verdict verdict-${r.status}`, LABELS[r.status] || r.status));
    if (r.photo_url) {
      const img = el("img", "verify-photo");
      img.src = r.photo_url; img.alt = "Card holder photo";
      body.append(img);
    }
    if (r.pass_code) {
      const dl = el("dl", "dl");
      [["Name", r.name], ["UID", r.roll], ["Program", r.program], ["Pass No.", r.pass_code],
       ["Valid until", r.valid_until || "—"], ["QR type", r.method]].forEach(([k, v]) => {
        dl.append(el("dt", null, k), el("dd", null, v));
      });
      body.append(dl);
    }
    document.getElementById("resultTime").textContent = new Date().toLocaleTimeString();
    if (navigator.vibrate) navigator.vibrate(r.status === "valid" ? 80 : [80, 60, 80]);
  }

  async function check(text) {
    const now = Date.now();
    if (busy || (text === lastText && now - lastAt < 4000)) return; // ignore repeat scans
    busy = true; lastText = text; lastAt = now;
    msg.textContent = "Checking…";
    try {
      const res = await fetch(checkUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ text }),
        credentials: "same-origin",
      });
      if (res.redirected || res.status === 401) { location.reload(); return; } // session expired
      show(res.ok ? await res.json() : { status: "error" });
    } catch {
      show({ status: "error" });
    } finally {
      busy = false;
      msg.textContent = "Point the camera at a pass QR code.";
    }
  }

  async function tick() {
    if (!stream) return;
    if (video.readyState >= 2 && !busy) {
      try {
        let text = null;
        if (detector) {
          const codes = await detector.detect(video);
          text = codes[0]?.rawValue || null;
        } else {
          const w = video.videoWidth, h = video.videoHeight;
          const scale = Math.min(1, 640 / Math.max(w, h)); // downscale for speed
          canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale);
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
          text = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" })?.data || null;
        }
        if (text) check(text);
      } catch { /* frame not ready; skip */ }
    }
    raf = requestAnimationFrame(tick);
  }

  async function listCameras() {
    const cams = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "videoinput");
    if (cams.length < 2) return;
    camSelect.replaceChildren(...cams.map((c, i) => {
      const o = el("option", null, c.label || `Camera ${i + 1}`); o.value = c.deviceId; return o;
    }));
    const active = stream?.getVideoTracks()[0]?.getSettings().deviceId;
    if (active) camSelect.value = active;
    camSelect.hidden = false;
  }

  async function start(deviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      msg.textContent = "Camera not available. Use https:// or localhost, or paste the text instead.";
      return;
    }
    stop();
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "environment" } },
        audio: false,
      });
    } catch (e) {
      msg.textContent = e.name === "NotAllowedError" ? "Camera permission was denied." : "Could not open the camera.";
      return;
    }
    video.srcObject = stream;
    await video.play();
    startBtn.disabled = true; stopBtn.disabled = false;
    msg.textContent = "Point the camera at a pass QR code.";
    listCameras();
    tick();
  }

  function stop() {
    cancelAnimationFrame(raf);
    stream?.getTracks().forEach(t => t.stop());
    stream = null; video.srcObject = null;
    startBtn.disabled = false; stopBtn.disabled = true;
  }

  startBtn.addEventListener("click", () => start());
  stopBtn.addEventListener("click", () => { stop(); msg.textContent = "Camera stopped."; });
  camSelect.addEventListener("change", () => start(camSelect.value));
  window.addEventListener("pagehide", stop);
})();
