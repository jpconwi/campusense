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
  const [started, setStarted] = useState(false);
  const [starting, setStarting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [capture, setCapture] = useState(null);
  const [instruction, setInstruction] = useState("Start the camera, center your face, then capture.");
  const [poseState, setPoseState] = useState("waiting");
  const [error, setError] = useState("");
  const [guidanceUnavailable, setGuidanceUnavailable] = useState(false);
  const preview = useMemo(() => capture ? URL.createObjectURL(capture) : "", [capture]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function start() {
    setError("");
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 1280 } }, audio: false,
      });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setInstruction("Center your face inside the circle, look at the camera, then capture.");
      setStarted(true);
    } catch {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setError("Camera access is unavailable. Allow camera access in your browser or try again on HTTPS.");
    } finally {
      setStarting(false);
    }
  }

  async function capturePose(frame, reviewOnly = false) {
    setInstruction(reviewOnly
      ? "Selfie saved for administrator review because automatic guidance was unavailable."
      : "Face is clear. Selfie captured.");
    setPoseState(reviewOnly ? "review" : "ready");
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCapture(frame);
    onComplete({ front: frame });
  }

  async function captureCurrentFrame() {
    if (capture || !videoRef.current?.videoWidth || busyRef.current || disabled) return;
    busyRef.current = true;
    setChecking(true);
    setGuidanceUnavailable(false);
    setPoseState("checking");
    setInstruction("Checking the captured frame…");
    setError("");
    try {
      const frame = await photo(videoRef.current);
      const form = new FormData();
      form.append("frame", frame);
      form.append("consent", "true");
      const result = await api("/api/auth/face-guidance", { method: "POST", form });
      if (!result.ready) {
        if (!result.available) {
          setGuidanceUnavailable(true);
          setInstruction("Face guidance is unavailable. Re-center your face, capture again, or save the current selfie for administrator review.");
          setPoseState("review");
          return;
        }
        setInstruction(result.instruction || "Adjust your position and try again.");
        setPoseState("unclear");
        return;
      }
      await capturePose(frame, !result.available);
    } catch (e) {
      const isServerResponse = Number.isInteger(e.status);
      setError(isServerResponse ? "" : (e.message || "Could not check this selfie."));
      setInstruction(isServerResponse
        ? (e.message || "Face guidance could not check this selfie.")
        : "Could not reach face guidance. Check your connection and try again.");
      setPoseState("error");
    }
    finally {
      busyRef.current = false;
      setChecking(false);
    }
  }

  async function saveForReview() {
    if (capture || !videoRef.current?.videoWidth || busyRef.current || disabled) return;
    busyRef.current = true;
    setChecking(true);
    setError("");
    setInstruction("Saving the current selfie for administrator review…");
    try {
      const frame = await photo(videoRef.current);
      const form = new FormData();
      form.append("frame", frame);
      form.append("consent", "true");
      form.append("manual", "true");
      await api("/api/auth/face-guidance", { method: "POST", form });
      await capturePose(frame, true);
    } catch (e) {
      setError(e.message || "Could not save this selfie. Try again.");
      setInstruction("The selfie could not be saved. Re-center your face and try again.");
      setPoseState("error");
    } finally {
      busyRef.current = false;
      setChecking(false);
    }
  }

  return <section className="face-scan" aria-label="Guided face scan">
    <h3>Face scan</h3>
    <p className="registration-scan-help">Start the camera, center your face in the circle, then press Capture selfie. The selected frame is checked before it is saved.</p>
    {error && <p className="flash error" role="alert">{error}</p>}
    <div className={`face-scan-stage${started && !capture ? "" : " idle"}`}>
      {capture
        ? <img className="face-scan-captured-image" src={preview} alt="Captured front-facing selfie" />
        : <video ref={videoRef} playsInline muted autoPlay aria-label="Front-facing camera preview" />}
      {!capture && <div className={`face-scan-circle ${poseState}`} aria-hidden="true" />}
      {!started && !capture && <span>Face guide</span>}
    </div>
    {!started && !capture
      ? <button className="btn" type="button" disabled={disabled || starting} onClick={start}>
          {starting ? "Starting camera…" : "Start face scan"}
        </button>
      : capture
        ? <p className={`face-scan-instruction ${poseState}`} role="status">
            {poseState === "review" ? "Selfie saved for administrator review." : "Selfie captured. Continue with registration."}
          </p>
        : <>
            <p className={`face-scan-instruction ${poseState}`} role="status" aria-live="polite">
              {instruction}
            </p>
            <div className="face-scan-actions">
              <button className="btn" type="button" disabled={disabled || checking} onClick={captureCurrentFrame}>
                {checking ? "Checking selfie…" : "Capture selfie"}
              </button>
              {guidanceUnavailable && <button className="btn secondary" type="button"
                disabled={disabled || checking} onClick={saveForReview}>
                Save for administrator review
              </button>}
            </div>
          </>}
  </section>;
}
