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
  const readyFramesRef = useRef(0);
  const [started, setStarted] = useState(false);
  const [starting, setStarting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [capture, setCapture] = useState(null);
  const [instruction, setInstruction] = useState("Start the camera, then center your face inside the circle.");
  const [poseState, setPoseState] = useState("waiting");
  const [error, setError] = useState("");
  const [guidanceUnavailable, setGuidanceUnavailable] = useState(false);
  const preview = useMemo(() => capture ? URL.createObjectURL(capture) : "", [capture]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    if (!started || disabled || capture) return undefined;
    checkPoseRef.current?.();
    const timer = window.setInterval(() => checkPoseRef.current?.(), 900);
    return () => window.clearInterval(timer);
  }, [started, disabled, capture]);

  async function start() {
    setError("");
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 1280 } }, audio: false,
      });
      streamRef.current = stream;
      readyFramesRef.current = 0;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setInstruction("Center your face inside the circle and look at the camera.");
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

  async function checkPose() {
    if (capture || !videoRef.current?.videoWidth || busyRef.current || disabled) return;
    busyRef.current = true;
    setChecking(true);
    if (readyFramesRef.current === 0) {
      setPoseState("checking");
      setInstruction("Checking face position and visibility…");
    }
    setError("");
    try {
      const frame = await photo(videoRef.current);
      const form = new FormData();
      form.append("frame", frame);
      form.append("consent", "true");
      const result = await api("/api/auth/face-guidance", { method: "POST", form });
      if (!result.ready) {
        readyFramesRef.current = 0;
        if (!result.available) {
          setGuidanceUnavailable(true);
          setInstruction("Face guidance is unavailable. Save a selfie for administrator review when your face is centered.");
          setPoseState("review");
          return;
        }
        setGuidanceUnavailable(false);
        setInstruction(result.instruction || "Adjust your position and try again.");
        setPoseState("unclear");
        return;
      }
      if (!result.available) {
        readyFramesRef.current = 0;
        setGuidanceUnavailable(true);
        setInstruction("Face guidance is unavailable. Save a selfie for administrator review when your face is centered.");
        setPoseState("review");
        return;
      }
      setGuidanceUnavailable(false);
      readyFramesRef.current += 1;
      if (readyFramesRef.current >= 2) {
        await capturePose(frame);
      } else {
        setInstruction("Face is centered. Hold still—the selfie will capture when the guide stays green.");
        setPoseState("ready");
      }
    } catch (e) {
      readyFramesRef.current = 0;
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
  checkPoseRef.current = checkPose;

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
    <p className="registration-scan-help">Start the camera and center your face inside the circle. When the guide stays green, your selfie captures automatically.</p>
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
            {guidanceUnavailable && <div className="face-scan-actions">
              <button className="btn" type="button" disabled={disabled || checking} onClick={saveForReview}>
                Save for administrator review
              </button>
            </div>}
          </>}
  </section>;
}
