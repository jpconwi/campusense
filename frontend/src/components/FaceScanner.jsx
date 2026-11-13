import { useEffect, useMemo, useRef, useState } from "react";
import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";
import { api } from "../api.js";
import "./face-scanner.css";

let detectorPromise;
function getFaceDetector() {
  if (!detectorPromise) {
    detectorPromise = FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.3/wasm",
    ).then((vision) => FaceDetector.createFromOptions(vision, {
      baseOptions: { modelAssetPath: "/models/blaze_face_short_range.tflite" },
      runningMode: "VIDEO",
      minDetectionConfidence: 0.55,
    })).catch((error) => {
      detectorPromise = null;
      throw error;
    });
  }
  return detectorPromise;
}

function faceFitsGuide(detections, video) {
  if (detections.length !== 1) return false;
  const detection = detections[0];
  if ((detection.categories?.[0]?.score ?? 0) < 0.55) return false;
  const box = detection.boundingBox;
  const cropSize = Math.min(video.videoWidth, video.videoHeight);
  const cropX = (video.videoWidth - cropSize) / 2;
  const cropY = (video.videoHeight - cropSize) / 2;
  const left = (box.originX - cropX) / cropSize;
  const top = (box.originY - cropY) / cropSize;
  const right = left + box.width / cropSize;
  const bottom = top + box.height / cropSize;
  const centerX = (left + right) / 2;
  const centerY = (top + bottom) / 2;
  return left >= 0.06 && top >= 0.06 && right <= 0.94 && bottom <= 0.94
    && Math.abs(centerX - 0.5) <= 0.12 && Math.abs(centerY - 0.5) <= 0.12
    && right - left >= 0.18 && right - left <= 0.88
    && bottom - top >= 0.2 && bottom - top <= 0.9;
}

function photo(video) {
  const canvas = document.createElement("canvas");
  // Match the square object-fit: cover preview and submit the same composition.
  const sourceSize = Math.min(video.videoWidth, video.videoHeight);
  const sourceX = (video.videoWidth - sourceSize) / 2;
  const sourceY = (video.videoHeight - sourceSize) / 2;
  const outputSize = Math.min(900, sourceSize);
  canvas.width = outputSize;
  canvas.height = outputSize;
  canvas.getContext("2d").drawImage(
    video, sourceX, sourceY, sourceSize, sourceSize, 0, 0, outputSize, outputSize,
  );
  return new Promise((resolve, reject) => canvas.toBlob((blob) => {
    if (blob) resolve(new File([blob], "face-selfie.jpg", { type: "image/jpeg" }));
    else reject(new Error("Could not capture the selfie. Try again."));
  }, "image/jpeg", 0.86));
}

export default function FaceScanner({ onComplete, disabled = false }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const busyRef = useRef(false);
  const readyFramesRef = useRef(0);
  const [started, setStarted] = useState(false);
  const [starting, setStarting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [capture, setCapture] = useState(null);
  const [instruction, setInstruction] = useState("Start the camera, then center your face inside the circle.");
  const [poseState, setPoseState] = useState("waiting");
  const [error, setError] = useState("");
  const preview = useMemo(() => capture ? URL.createObjectURL(capture) : "", [capture]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function persistAndComplete(frame) {
    const form = new FormData();
    form.append("frame", frame);
    form.append("consent", "true");
    // The local detector has already checked framing. Store the frame without
    // blocking on the optional remote AI guidance service.
    form.append("manual", "true");
    await api("/api/auth/face-guidance", { method: "POST", form });
    setInstruction("Selfie captured. Continue with registration.");
    setPoseState("ready");
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCapture(frame);
    onComplete({ front: frame });
  }

  useEffect(() => {
    if (!started || capture) return undefined;
    let cancelled = false;
    let timer;
    let detecting = false;
    setChecking(true);
    setInstruction("Loading the on-device face detector…");
    getFaceDetector().then((detector) => {
      if (cancelled) return;
      setChecking(false);
      setInstruction("Center your face inside the circle.");
      setPoseState("waiting");
      timer = window.setInterval(async () => {
        const video = videoRef.current;
        if (cancelled || detecting || busyRef.current || disabled || !video?.videoWidth) return;
        detecting = true;
        try {
          const result = detector.detectForVideo(video, performance.now());
          if (faceFitsGuide(result.detections, video)) {
            readyFramesRef.current += 1;
            setPoseState("ready");
            setInstruction("Face is centered. Hold still for a moment…");
            if (readyFramesRef.current >= 4) {
              busyRef.current = true;
              setChecking(true);
              setInstruction("Face centered. Capturing your selfie…");
              const frame = await photo(video);
              await persistAndComplete(frame);
            }
          } else {
            readyFramesRef.current = 0;
            setPoseState("unclear");
            const count = result.detections.length;
            setInstruction(count === 0 ? "Move your face into the circle."
              : count > 1 ? "Make sure only your face is in the frame."
                : "Adjust your distance or center your face inside the circle.");
          }
        } catch {
          if (!cancelled) {
            busyRef.current = false;
            readyFramesRef.current = 0;
            setChecking(false);
            setError("Could not save the captured selfie. You can try again or save it for administrator review.");
            setInstruction("The selfie could not be saved. Keep your face centered and try again.");
            setPoseState("error");
          }
        } finally {
          detecting = false;
        }
      }, 120);
    }).catch(() => {
      if (!cancelled) {
        setChecking(false);
        setError("Could not load the on-device face detector. You can still save a selfie for administrator review.");
        setInstruction("Automatic capture is unavailable. Save a selfie for administrator review.");
        setPoseState("error");
      }
    });
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
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
      setInstruction("Center your face inside the circle.");
      setStarted(true);
    } catch {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setError("Camera access is unavailable. Allow camera access in your browser or try again on HTTPS.");
    } finally {
      setStarting(false);
    }
  }

  async function saveForReview() {
    if (capture || !videoRef.current?.videoWidth || busyRef.current || disabled) return;
    busyRef.current = true;
    setChecking(true);
    setError("");
    setInstruction("Saving your selfie for administrator review…");
    try {
      await persistAndComplete(await photo(videoRef.current));
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
    <p className="registration-scan-help">Start the camera and center your face inside the circle. The selfie captures automatically when your face stays centered.</p>
    {error && <p className="flash error" role="alert">{error}</p>}
    <div className={`face-scan-stage${started && !capture ? "" : " idle"}`}>
      {capture
        ? <img className="face-scan-captured-image" src={preview} alt="Captured front-facing selfie" />
        : <video ref={videoRef} playsInline muted autoPlay aria-label="Front-facing camera preview" />}
      {!capture && <div className={`face-scan-circle ${checking ? "checking" : poseState}`} aria-hidden="true" />}
      {!started && !capture && <span>Face guide</span>}
    </div>
    {!started && !capture
      ? <button className="btn" type="button" disabled={disabled || starting} onClick={start}>
          {starting ? "Starting camera…" : "Start face scan"}
        </button>
      : capture
        ? <p className="face-scan-instruction ready" role="status">Selfie captured. Continue with registration.</p>
        : <>
            <p className={`face-scan-instruction ${poseState}`} role="status" aria-live="polite">{instruction}</p>
            <div className="face-scan-actions">
              <button className="btn" type="button" disabled={disabled || checking} onClick={saveForReview}>
                Save for administrator review
              </button>
            </div>
          </>}
  </section>;
}
