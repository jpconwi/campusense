import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import "./face-scanner.css";

const POSES = [
  { key: "front", title: "Look straight ahead" },
  { key: "left", title: "Turn your head left" },
  { key: "right", title: "Turn your head right" },
];

function photo(video, stage) {
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 900 / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => canvas.toBlob((blob) => {
    if (blob) resolve(new File([blob], `face-${stage}.jpg`, { type: "image/jpeg" }));
    else reject(new Error("Could not capture this pose. Try again."));
  }, "image/jpeg", 0.86));
}

export default function FaceScanner({ onComplete, disabled = false }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [started, setStarted] = useState(false);
  const [index, setIndex] = useState(0);
  const [captures, setCaptures] = useState({});
  const [instruction, setInstruction] = useState("Start the camera to scan three poses.");
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pose = POSES[index];
  const thumbs = useMemo(() => Object.fromEntries(POSES.filter((item) => captures[item.key])
    .map((item) => [item.key, URL.createObjectURL(captures[item.key])])), [captures]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => () => Object.values(thumbs).forEach((url) => URL.revokeObjectURL(url)), [thumbs]);

  async function start() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 1280 } }, audio: false,
      });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setStarted(true);
    } catch {
      setError("Camera access is unavailable. Allow camera access in your browser or try again on HTTPS.");
    }
  }

  async function checkPose(forceManual = false) {
    if (!pose || !videoRef.current?.videoWidth || busy) return;
    setBusy(true); setError("");
    try {
      const frame = await photo(videoRef.current, pose.key);
      const form = new FormData();
      form.append("stage", pose.key); form.append("frame", frame);
      form.append("consent", "true");
      if (forceManual) form.append("manual", "true");
      const result = await api("/api/auth/face-guidance", { method: "POST", form });
      setInstruction(result.instruction || "Adjust your pose and try again.");
      if (!result.ready) {
        setManual(!result.available);
        return;
      }
      const next = { ...captures, [pose.key]: frame };
      setCaptures(next);
      setManual(false);
      if (index === POSES.length - 1) {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setIndex(POSES.length);
        onComplete(next);
      } else setIndex(index + 1);
    } catch (e) { setError(e.message || "Could not check this pose. Try again."); }
    finally { setBusy(false); }
  }

  return <section className="face-scan" aria-label="Guided face scan">
    <h3>Face scan</h3>
    <p className="registration-scan-help">Follow the circle prompts. The camera checks framing and pose, then captures front, left, and right views.</p>
    {error && <p className="flash error" role="alert">{error}</p>}
    <div className={`face-scan-stage${started ? "" : " idle"}`}>
      <video ref={videoRef} playsInline muted autoPlay aria-label="Front-facing camera preview" />
      <div className="face-scan-circle" aria-hidden="true" />
      {!started && <span>Face guide</span>}
    </div>
    {!started ? <button className="btn" type="button" disabled={disabled} onClick={start}>Start face scan</button> : pose ? <>
      <p className="face-scan-step">Pose {index + 1} of 3: <strong>{pose.title}</strong></p>
      <p className="face-scan-instruction" role="status">{busy ? "Checking pose…" : instruction}</p>
      <button className="btn" type="button" disabled={busy || disabled} onClick={() => checkPose(false)}>
        {busy ? "Checking…" : "Check pose and capture"}
      </button>{" "}
      {manual && <button className="btn ghost" type="button" disabled={busy || disabled} onClick={() => checkPose(true)}>
        Capture for admin review
      </button>}
    </> : <p className="face-scan-instruction" role="status">All three poses captured.</p>}
    <div className="face-scan-thumbs" aria-label="Captured face poses">
      {POSES.map((item) => <div key={item.key} className={captures[item.key] ? "captured" : ""}>
        {captures[item.key] ? <><img src={thumbs[item.key]} alt={`${item.key} face pose captured`} /><small>{item.key} captured</small></>
          : <small>{item.key}</small>}
      </div>)}
    </div>
  </section>;
}
