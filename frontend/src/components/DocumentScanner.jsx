import { useEffect, useMemo, useRef, useState } from "react";

function cropRect(video, stage, kind) {
  const scale = Math.max(stage.clientWidth / video.videoWidth, stage.clientHeight / video.videoHeight);
  const offsetX = (stage.clientWidth - video.videoWidth * scale) / 2;
  const offsetY = (stage.clientHeight - video.videoHeight * scale) / 2;
  const insetX = stage.clientWidth * (kind === "cor" ? 0.07 : 0.045);
  const insetY = stage.clientHeight * (kind === "cor" ? 0.045 : 0.07);
  const left = Math.max(0, (insetX - offsetX) / scale);
  const top = Math.max(0, (insetY - offsetY) / scale);
  const right = Math.min(video.videoWidth, (stage.clientWidth - insetX - offsetX) / scale);
  const bottom = Math.min(video.videoHeight, (stage.clientHeight - insetY - offsetY) / scale);
  return { left, top, width: right - left, height: bottom - top };
}

function inspectFrame(video, stage, sampleCanvas, previous, kind) {
  const rect = cropRect(video, stage, kind);
  if (rect.width <= 0 || rect.height <= 0) return { state: "unclear", previous };
  const context = sampleCanvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(video, rect.left, rect.top, rect.width, rect.height, 0, 0, 80, 56);
  const pixels = context.getImageData(0, 0, 80, 56).data;
  const gray = new Uint8Array(80 * 56);
  let luminance = 0;
  let edges = 0;
  for (let y = 1; y < 55; y += 1) {
    for (let x = 1; x < 79; x += 1) {
      const i = (y * 80 + x) * 4;
      const value = Math.round(pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114);
      gray[y * 80 + x] = value;
      luminance += value;
      if (Math.abs(value - gray[y * 80 + x - 1]) + Math.abs(value - gray[(y - 1) * 80 + x]) > 42) {
        edges += 1;
      }
    }
  }
  const average = luminance / (78 * 54);
  const detailRatio = edges / (78 * 54);
  if (average < 38 || average > 228 || detailRatio < 0.018) return { state: "unclear", previous: gray };
  if (!previous) return { state: "checking", previous: gray };
  let difference = 0;
  for (let i = 0; i < gray.length; i += 1) difference += Math.abs(gray[i] - previous[i]);
  return { state: difference / gray.length < 8 ? "ready" : "checking", previous: gray };
}

async function makePhoto(video, stage, kind) {
  const rect = cropRect(video, stage, kind);
  const canvas = document.createElement("canvas");
  const maxEdge = 1600;
  const scale = Math.min(1, maxEdge / Math.max(rect.width, rect.height));
  canvas.width = Math.round(rect.width * scale);
  canvas.height = Math.round(rect.height * scale);
  canvas.getContext("2d").drawImage(video, rect.left, rect.top, rect.width, rect.height, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve, reject) => canvas.toBlob(
    (image) => image ? resolve(image) : reject(new Error("Could not save the document photo. Try again.")),
    "image/jpeg", 0.88,
  ));
  if (blob.size > 5 * 1024 * 1024) throw new Error("The document photo is over 5 MB. Move the camera farther away and try again.");
  const prefix = kind === "cor" ? "nemsu-cor" : "nemsu-id";
  return new File([blob], `${prefix}-${Date.now()}.jpg`, { type: "image/jpeg" });
}

export default function DocumentScanner({ label, kind = "id", value, enabled = true, onCapture }) {
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const streamRef = useRef(null);
  const previousRef = useRef(null);
  const readyCountRef = useRef(0);
  const capturingRef = useRef(false);
  const onCaptureRef = useRef(onCapture);
  const uploadRef = useRef(null);
  const scanActiveRef = useRef(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [status, setStatus] = useState("waiting");
  const [mode, setMode] = useState("");
  const preview = useMemo(() => value ? URL.createObjectURL(value) : "", [value]);
  onCaptureRef.current = onCapture;

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);

  async function startCamera() {
    setCameraError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1600 }, height: { ideal: 1200 } },
        audio: false,
      });
      if (!scanActiveRef.current) { stream.getTracks().forEach((track) => track.stop()); return; }
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setCameraOn(true);
        setStatus("unclear");
      }
    } catch {
      setCameraError("Camera access was blocked. Allow camera access or choose a photo instead.");
    }
  }

  useEffect(() => {
    scanActiveRef.current = mode === "scan" && enabled && !value;
    if (mode === "scan" && enabled && !value) startCamera();
    return () => {
      scanActiveRef.current = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraOn(false);
    };
  }, [enabled, value, mode]);

  useEffect(() => {
    if (!cameraOn || !enabled || value) return undefined;
    const sample = document.createElement("canvas");
    sample.width = 80;
    sample.height = 56;
    const timer = window.setInterval(async () => {
      const video = videoRef.current;
      const stage = stageRef.current;
      if (!video?.videoWidth || !stage || capturingRef.current) return;
      try {
        const result = inspectFrame(video, stage, sample, previousRef.current, kind);
        previousRef.current = result.previous;
        setStatus(result.state);
        readyCountRef.current = result.state === "ready" ? readyCountRef.current + 1 : 0;
        if (readyCountRef.current < 3) return;
        capturingRef.current = true;
        setStatus("capturing");
        const image = await makePhoto(video, stage, kind);
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        onCaptureRef.current(image);
      } catch (error) {
        setCameraError(error.message || "Could not capture the document. Try again.");
        setStatus("unclear");
        readyCountRef.current = 0;
        capturingRef.current = false;
      }
    }, 350);
    return () => window.clearInterval(timer);
  }, [cameraOn, enabled, value, kind]);

  function choosePhoto(event) {
    const file = event.target.files?.[0] || null;
    event.target.value = "";
    if (file) onCapture(file);
  }

  function retake() {
    capturingRef.current = false;
    previousRef.current = null;
    readyCountRef.current = 0;
    setStatus("waiting");
    setMode("scan");
    onCapture(null);
  }

  const message = value ? "Photo captured." : !enabled
    ? "Complete the selfie scan to enable document capture."
    : ({
      waiting: "Starting the camera…",
      unclear: "Fit the full document in the guide. Improve the light if needed.",
      checking: "Hold the document steady inside the guide…",
      ready: "Document is clear. Capturing automatically…",
      capturing: "Saving document photo…",
    }[status] || "Fit the full document in the guide.");

  return (
    <div className={`document-scanner${value ? " is-captured" : ""}`} aria-label={`${label} camera scanner`}>
      {!value && !mode && <div className="document-scan-options">
        <button className="btn small ghost" type="button" disabled={!enabled}
          onClick={() => { setMode("upload"); uploadRef.current?.click(); }}>Upload file</button>
        <button className="btn small ghost" type="button" disabled={!enabled} onClick={() => { setCameraError(""); setMode("scan"); }}>Scan with camera</button>
      </div>}
      <input ref={uploadRef} type="file" accept="image/jpeg,image/png,image/webp" hidden disabled={!enabled}
        onChange={choosePhoto} />
      {mode === "upload" && !value && <div className="document-scan-options">
        <span className="document-scan-status">Choose an existing ID or COR image from your device.</span>
        <button className="btn small ghost" type="button" disabled={!enabled} onClick={() => uploadRef.current?.click()}>Choose file</button>
        <button className="btn small ghost" type="button" onClick={() => setMode("")}>Back</button>
      </div>}
      {(mode === "scan" || value) && <>
      <div className={`document-scan-stage kind-${kind} ${value ? "captured" : status}`} ref={stageRef}>
        {value
          ? <img src={preview} alt={`Captured ${label}`} />
          : <video ref={videoRef} playsInline muted autoPlay aria-label={`${label} camera preview`} />}
        {!value && <div className="document-scan-guide" aria-hidden="true" />}
        {!value && !enabled && <span className="document-scan-placeholder">Complete the selfie scan to enable the document camera.</span>}
        {!value && enabled && !cameraOn && <span className="document-scan-placeholder">Camera view</span>}
      </div>
      <p className={`document-scan-status ${value ? "captured" : status}`} role="status" aria-live="polite">{message}</p>
      {cameraError && <p className="document-scan-error" role="alert">{cameraError}</p>}
      <div className="document-scan-actions">
        {value ? (
          <>
            <button className="btn small ghost" type="button" disabled={!enabled} onClick={retake}>Scan again</button>
            <button className="btn small ghost" type="button" disabled={!enabled} onClick={() => { setMode("upload"); uploadRef.current?.click(); }}>Upload another file</button>
          </>
        ) : (
          <>
            {!cameraOn && <button className="btn small ghost" type="button" disabled={!enabled} onClick={startCamera}>Start camera</button>}
            <button className="btn small ghost" type="button" disabled={!enabled} onClick={() => { setMode("upload"); uploadRef.current?.click(); }}>Upload file instead</button>
            <button className="btn small ghost" type="button" onClick={() => setMode("")}>Back</button>
          </>
        )}
      </div>
      </>}
    </div>
  );
}
