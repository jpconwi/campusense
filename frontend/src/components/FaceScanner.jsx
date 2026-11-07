import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import "./face-scanner.css";

function photo(video) {
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 900 / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => canvas.toBlob((blob) => {
    if (blob) resolve(new File([blob], "face-selfie.jpg", { type: "image/jpeg" }));
    else reject(new Error("Could not capture the selfie. Try again."));
  }, "image/jpeg", 0.86));
}

export default function FaceScanner({ onComplete, disabled = false }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const busyRef = useRef(false);
  const checkPoseRef = useRef(null);
  const retryAfterRef = useRef(0);
  const [started, setStarted] = useState(false);
  const [capture, setCapture] = useState(null);
  const [instruction, setInstruction] = useState("Start the camera to capture one selfie.");
  const [poseState, setPoseState] = useState("waiting");
  const [error, setError] = useState("");
  const preview = useMemo(() => capture ? URL.createObjectURL(capture) : "", [capture]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    if (!started || disabled || capture) return undefined;
    checkPoseRef.current?.();
    const timer = window.setInterval(() => checkPoseRef.current?.(), 1400);
    return () => window.clearInterval(timer);
  }, [started, disabled, capture]);

  async function start() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 1280 } }, audio: false,
      });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setInstruction("Center your face inside the circle and look at the camera.");
      setStarted(true);
    } catch {
      setError("Camera access is unavailable. Allow camera access in your browser or try again on HTTPS.");
    }
  }

  async function capturePose(frame, reviewOnly = false) {
    setInstruction(reviewOnly
      ? "Selfie saved for administrator review because automatic guidance was unavailable."
      : "Face is clear. Hold still, capturing automatically…");
    setPoseState(reviewOnly ? "review" : "ready");
    await new Promise((resolve) => window.setTimeout(resolve, 450));
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCapture(frame);
    onComplete({ front: frame });
  }

  async function checkPose() {
    if (capture || !videoRef.current?.videoWidth || busyRef.current || disabled
        || Date.now() < retryAfterRef.current) return;
    busyRef.current = true;
    setPoseState("checking");
    setInstruction("Checking face position and visibility…");
    setError("");
    try {
      const frame = await photo(videoRef.current);
      const form = new FormData();
      form.append("frame", frame);
      form.append("consent", "true");
      const result = await api("/api/auth/face-guidance", { method: "POST", form });
      if (!result.ready) {
        if (!result.available) {
          setInstruction("Guidance is unavailable. Saving the selfie for administrator review…");
          const fallback = new FormData();
          fallback.append("frame", frame);
          fallback.append("consent", "true"); fallback.append("manual", "true");
          await api("/api/auth/face-guidance", { method: "POST", form: fallback });
          await capturePose(frame, true);
          return;
        }
        setInstruction(result.instruction || "Adjust your position and try again.");
        setPoseState("unclear");
        return;
      }
      await capturePose(frame);
    } catch (e) {
      setError(e.message || "Could not check this selfie.");
      setInstruction("Could not reach face guidance. Retrying automatically in a few seconds.");
      setPoseState("error");
      retryAfterRef.current = Date.now() + 4000;
    }
    finally {
      busyRef.current = false;
    }
  }
  checkPoseRef.current = checkPose;

  return <section className="face-scan" aria-label="Guided face scan">
    <h3>Face scan</h3>
    <p className="registration-scan-help">Center your face in the circle and look at the camera. It checks visibility and framing, then captures one selfie automatically.</p>
    {error && <p className="flash error" role="alert">{error}</p>}
    <div className={`face-scan-stage${started && !capture ? "" : " idle"}`}>
      {capture
        ? <img className="face-scan-captured-image" src={preview} alt="Captured front-facing selfie" />
        : <video ref={videoRef} playsInline muted autoPlay aria-label="Front-facing camera preview" />}
      {!capture && <div className={`face-scan-circle ${poseState}`} aria-hidden="true" />}
      {!started && !capture && <span>Face guide</span>}
    </div>
    {!started && !capture
      ? <button className="btn" type="button" disabled={disabled} onClick={start}>Start face scan</button>
      : capture
        ? <p className={`face-scan-instruction ${poseState}`} role="status">
            {poseState === "review" ? "Selfie saved for administrator review." : "Front-facing selfie captured."}
          </p>
        : <>
            <p className={`face-scan-instruction ${poseState}`} role="status" aria-live="polite">
              {poseState === "checking" ? "Checking face position and visibility…" : instruction}
            </p>
            <p className="face-scan-legend">
              <span className="not-ready">Red: face or framing needs adjustment.</span>
              <span className="is-ready">Green: clear, capturing automatically.</span>
            </p>
          </>}
  </section>;
}
