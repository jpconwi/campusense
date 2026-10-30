/* IdScanner.jsx - camera scanner for a school ID (front/back) or a COR.
 *
 * <IdScanner kind="id-front" file={file} onChange={setFile} required />
 *
 * - "Scan" opens a full-screen camera with a frame, corner brackets and a red scan line (rear camera on phones).
 * - The photo is cropped to the frame, so only the document is saved (JPEG, well under the server's 5 MB limit).
 * - Desktop: upload only (no camera button).
 * - Phone with camera access: the in-page scanner. The phone's own camera app is never opened.
 * - Phone without camera access (plain http, Messenger/Facebook in-app browser, permission blocked): upload only,
 *   with a short note. Camera access in browsers needs HTTPS (or localhost).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import "./scanner.css";

export const KINDS = {
  "id-front": { title: "School ID - front", short: "ID SCAN", ratio: 1.586, hint: "Fit the front of your ID inside the frame", file: "school-id-front.jpg" },
  "id-back": { title: "School ID - back", short: "ID SCAN", ratio: 1.586, hint: "Fit the back of your ID inside the frame", file: "school-id-back.jpg" },
  cor: { title: "Certificate of Registration (COR)", short: "COR SCAN", ratio: 0.72, hint: "Fit the whole COR page inside the frame", file: "cor.jpg" },
};
/** Phones/tablets (touch first). Desktop browsers get upload only. */
function isMobileDevice() {
  if (typeof window === "undefined") return false;
  const ua = navigator.userAgent || "";
  const coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
  return coarse || /Android|iPhone|iPad|iPod|Mobi/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
}
/** Can this page open an in-page camera right now? */
function cameraApiReady() {
  return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}
const IN_APP = /FBAN|FBAV|FB_IAB|Messenger|Instagram|Line\/|MicroMessenger/i;

const MAX_BYTES = 5 * 1024 * 1024;
const OK_TYPES = ["image/jpeg", "image/png", "image/webp"];

const I = {
  cam: "M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  up: "M12 16V4M7 9l5-5 5 5M5 20h14",
  x: "M6 6l12 12M18 6L6 18",
  redo: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
};
const Ico = ({ d }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);

/** Rough quality check on a small grayscale copy: blur (Laplacian variance), too dark, glare. */
function quality(canvas) {
  const w = 240, h = Math.max(1, Math.round((canvas.height / canvas.width) * w));
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(canvas, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  const g = new Float32Array(w * h); let sum = 0;
  for (let i = 0; i < w * h; i++) { g[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]; sum += g[i]; }
  const mean = sum / (w * h);
  let acc = 0, n = 0;
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
    const i = y * w + x;
    const lap = g[i - 1] + g[i + 1] + g[i - w] + g[i + w] - 4 * g[i];
    acc += lap * lap; n++;
  }
  const sharp = n ? acc / n : 0;
  const warns = [];
  if (mean < 45) warns.push("The photo looks dark. Move to a brighter place.");
  else if (mean > 232) warns.push("There may be glare. Tilt the card slightly and retake.");
  if (sharp < 18) warns.push("The text may be blurry. Hold steady and retake if you cannot read it.");
  return warns;
}

export default function IdScanner({ kind = "id-front", file, onChange, required = false, disabled = false }) {
  const K = KINDS[kind] || KINDS["id-front"];
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [flash, setFlash] = useState(0);
  const [error, setError] = useState("");
  const [warns, setWarns] = useState([]);
  const [url, setUrl] = useState("");
  const [mobile] = useState(isMobileDevice);
  const [camOk] = useState(cameraApiReady);
  const [blocked, setBlocked] = useState(false);          // camera permission was refused
  const videoRef = useRef(null);
  const frameRef = useRef(null);
  const uploadRef = useRef(null);
  const openerRef = useRef(null);

  // preview URL for the chosen file
  useEffect(() => {
    if (!file) { setUrl(""); return undefined; }
    const u = URL.createObjectURL(file); setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  // camera on/off with the overlay
  useEffect(() => {
    if (!open) return undefined;
    let stopped = false, stream = null;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
        if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
        const v = videoRef.current; v.srcObject = stream; await v.play(); setReady(true);
      } catch (e) {
        if (stopped) return;
        setOpen(false); setBlocked(true);
        setError(e && e.name === "NotAllowedError"
          ? "Camera permission was blocked. Allow the camera in your browser settings, or upload a photo."
          : "The camera could not start. Upload a photo instead.");
      }
    })();
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => {
      stopped = true; setReady(false);
      if (stream) stream.getTracks().forEach((t) => t.stop());
      window.removeEventListener("keydown", onKey); document.body.style.overflow = prev;
      if (openerRef.current) openerRef.current.focus();
    };
  }, [open]);

  const accept = useCallback((f) => {
    setError("");
    if (!f) return;
    if (!OK_TYPES.includes(f.type)) { setError("Choose a JPG, PNG or WEBP photo."); return; }
    if (f.size > MAX_BYTES) { setError("That photo is over 5 MB. Take it again or choose a smaller one."); return; }
    onChange(f);
    // quality check on the chosen image
    const img = new Image(); const u = URL.createObjectURL(f);
    img.onload = () => {
      const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext("2d").drawImage(img, 0, 0); setWarns(quality(c)); URL.revokeObjectURL(u);
    };
    img.onerror = () => URL.revokeObjectURL(u);
    img.src = u;
  }, [onChange]);

  function start(e) {
    openerRef.current = e.currentTarget; setError(""); setBlocked(false);
    setOpen(true);
  }

  function shoot() {
    const v = videoRef.current, fr = frameRef.current;
    if (!v || !fr || !v.videoWidth) return;
    const vr = v.getBoundingClientRect(), f = fr.getBoundingClientRect();
    const scale = Math.max(vr.width / v.videoWidth, vr.height / v.videoHeight);
    const offX = vr.left + (vr.width - v.videoWidth * scale) / 2;
    const offY = vr.top + (vr.height - v.videoHeight * scale) / 2;
    const pad = 0.03;                                // a little margin so the card edge is not cut
    let sx = (f.left - offX) / scale - f.width / scale * pad, sy = (f.top - offY) / scale - f.height / scale * pad;
    let sw = f.width / scale * (1 + pad * 2), sh = f.height / scale * (1 + pad * 2);
    sx = Math.max(0, sx); sy = Math.max(0, sy); sw = Math.min(v.videoWidth - sx, sw); sh = Math.min(v.videoHeight - sy, sh);
    const k = Math.min(1, 1800 / Math.max(sw, sh));
    const c = document.createElement("canvas"); c.width = Math.round(sw * k); c.height = Math.round(sh * k);
    c.getContext("2d").drawImage(v, sx, sy, sw, sh, 0, 0, c.width, c.height);
    setFlash((n) => n + 1);
    c.toBlob((blob) => {
      if (!blob) { setError("Could not save the photo. Try again."); return; }
      setWarns(quality(c));
      onChange(new File([blob], K.file, { type: "image/jpeg" }));
      setOpen(false);
    }, "image/jpeg", 0.9);
  }

  const portrait = K.ratio < 1;
  const canScan = mobile && camOk && !blocked;            // phone + camera available: show the scanner button
  const inApp = IN_APP.test(navigator.userAgent || "");
  const note = mobile && !canScan
    ? (inApp ? "This in-app browser blocks the camera. Open the page in Safari or Chrome to scan, or upload a photo."
             : !camOk ? "Camera scanning needs a secure (https) page. You can upload a photo instead." : "")
    : "";
  return (
    <div className="ids ids-card" style={{ "--r": K.ratio }}>
      <div className="ids-card-head">
        <strong>{K.title}</strong>
        <span className={"ids-req" + (file ? " ok" : "")}>{file ? "Captured" : required ? "Required" : "Optional"}</span>
      </div>

      <div className={"ids-stage" + (portrait ? " portrait" : "")}>
        {url ? (
          <>
            <img className="ids-shot" src={url} alt={`${K.title} preview`} />
          </>
        ) : (
          <>
            <div className="ids-brackets" aria-hidden="true"><i /><i /><i /><i /></div>
            <svg className="ids-idle-art" viewBox="0 0 200 130" aria-hidden="true">
              <rect x="10" y="12" width="180" height="106" rx="12" fill="#fff" />
              <rect x="22" y="26" width="52" height="60" rx="8" fill="#00e68a" />
              <circle cx="48" cy="48" r="11" fill="#1d2a47" /><path d="M28 86c3-14 14-20 20-20s17 6 20 20z" fill="#7a1f2b" />
              <rect x="88" y="30" width="82" height="7" rx="3.5" fill="#00e68a" /><rect x="88" y="48" width="86" height="6" rx="3" fill="#00e68a" opacity=".85" />
              <rect x="88" y="64" width="78" height="6" rx="3" fill="#00e68a" opacity=".7" /><rect x="88" y="80" width="60" height="6" rx="3" fill="#00e68a" opacity=".55" />
            </svg>
            <span className="ids-line" aria-hidden="true" />
          </>
        )}
      </div>

      {error && <p className="ids-err" role="alert">{error}</p>}
      {!error && note && !file && <p className="ids-warn">{note}</p>}
      {!error && warns.length > 0 && file && warns.map((w) => <p className="ids-warn" key={w}>{w}</p>)}

      <div className="ids-actions">
        {canScan && (
          <button type="button" className="ids-btn primary" onClick={start} disabled={disabled}>
            <Ico d={file ? I.redo : I.cam} />{file ? "Retake" : "Scan with camera"}
          </button>
        )}
        <button type="button" className={"ids-btn " + (canScan ? "ghost" : "primary")} onClick={() => uploadRef.current.click()} disabled={disabled}>
          <Ico d={I.up} />{file && !canScan ? "Choose another" : "Upload"}
        </button>
        {file && (
          <button type="button" className="ids-btn danger" onClick={() => { onChange(null); setWarns([]); setError(""); }} disabled={disabled}>
            <Ico d={I.x} />Remove
          </button>
        )}
      </div>

      <input ref={uploadRef} type="file" accept="image/jpeg,image/png,image/webp" hidden
             onChange={(e) => { accept(e.target.files[0]); e.target.value = ""; }} />

      {open && (
        <div className="ids ids-overlay" style={{ "--r": K.ratio }} role="dialog" aria-modal="true" aria-label={`Scan ${K.title}`}>
          <video ref={videoRef} className="ids-video" playsInline muted autoPlay />
          {!ready && <div className="ids-starting" role="status">Starting camera...</div>}
          <div className="ids-top">
            <button type="button" className="ids-x" onClick={() => setOpen(false)} aria-label="Close scanner"><Ico d={I.x} /></button>
            <h2>{K.title}</h2>
            <span className="ids-spacer" />
          </div>
          <div className="ids-mid">
            <div className="ids-frame" ref={frameRef}>
              <i /><i /><i /><i />
              {ready && <span className="ids-sweep" aria-hidden="true" />}
              <p className="ids-hint">{K.hint}</p>
            </div>
          </div>
          <div className="ids-bottom">
            <div className="ids-shutter-row">
              <button type="button" className="ids-shutter" onClick={shoot} disabled={!ready} aria-label="Take photo" autoFocus />
            </div>
            <div className="ids-band" aria-hidden="true">{K.short}</div>
          </div>
          {flash > 0 && <span key={flash} className="ids-flash" aria-hidden="true" />}
        </div>
      )}
    </div>
  );
}
