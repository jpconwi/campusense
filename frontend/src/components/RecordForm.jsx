/*
 * RecordForm.jsx - one place that defines every form (concern, report, feedback,
 * reservation, faculty). The chat window and the normal pages both use it.
 * Name and email are NOT typed by the user: the server takes them from the
 * signed-in Google account.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const CONCERN_TYPES = ["Equipment", "Electrical", "Plumbing", "Furniture", "Building / Structure", "Cleanliness", "Safety", "Other"];
const REPORT_TYPES = ["Maintenance", "Safety", "Security", "Cleanliness", "Equipment", "Lost & Found", "Other"];
const FEEDBACK_TYPES = ["Compliment", "Suggestion", "Complaint", "Other"];

export const FORMS = {
  concern: {
    title: "Concern Form", endpoint: "/api/concerns", desc: "Describe the problem so it can be checked.",
    fields: [
      { name: "location", label: "Location / Area", type: "text", required: true, placeholder: "e.g. CITE building" },
      { name: "room", label: "Room", type: "text", placeholder: "e.g. Room 204 (optional)" },
      { name: "concern_type", label: "Concern type", type: "select", options: CONCERN_TYPES, required: true },
      { name: "description", label: "Description", type: "textarea", required: true, placeholder: "What is the problem?" },
      { name: "concern_date", label: "Date", type: "date", required: true, today: true },
      { name: "image", label: "Photo (optional, PNG/JPG/WEBP, max 5 MB)", type: "file" },
    ],
  },
  report: {
    title: "Report Form", endpoint: "/api/reports", desc: "Submit a campus report.",
    fields: [
      { name: "location", label: "Location", type: "text", required: true },
      { name: "area", label: "Area", type: "text", placeholder: "optional" },
      { name: "room", label: "Room", type: "text", placeholder: "optional" },
      { name: "report_type", label: "Report type", type: "select", options: REPORT_TYPES, required: true },
      { name: "description", label: "Description", type: "textarea", required: true },
      { name: "report_date", label: "Date", type: "date", required: true, today: true },
      { name: "image", label: "Photo (optional, PNG/JPG/WEBP, max 5 MB)", type: "file" },
    ],
  },
  feedback: {
    title: "Feedback & Suggestions", endpoint: "/api/feedback",
    desc: "Campus feedback goes to an admin. NEMSAI and technical feedback goes to the Super Admin.",
    fields: [
      { name: "feedback_scope", label: "What is your feedback about?", type: "select", options: ["Campus services", "NEMSAI / application", "Technical issue"], required: true },
      { name: "area", label: "Campus area or feature", type: "text", required: true, placeholder: "e.g. Library or NEMSAI Assistant" },
      { name: "feedback_type", label: "Feedback type", type: "select", options: FEEDBACK_TYPES, required: true },
      { name: "message", label: "Message", type: "textarea", required: true },
      { name: "feedback_date", label: "Date", type: "date", required: true, today: true },
    ],
  },
  reservation: {
    title: "Reservation Form", endpoint: "/api/reservations",
    desc: "Your request stays Pending until an administrator approves it.",
    fields: [
      { name: "facility", label: "Facility / Room", type: "text", required: true, list: true },
      { name: "purpose", label: "Purpose", type: "text", required: true },
      { name: "reservation_date", label: "Date", type: "date", required: true, today: true },
      { name: "start_time", label: "Start time", type: "time", required: true, half: true },
      { name: "duration_minutes", label: "Duration", type: "duration", required: true, half: true },
      { name: "additional_info", label: "Additional information", type: "textarea", placeholder: "optional" },
    ],
  },
  faculty: {
    title: "Faculty Availability Form", endpoint: "/api/faculty/submit",
    desc: "Fill in all fields so your availability report can be recorded.",
    fields: [
      { name: "reason", label: "Reason", type: "textarea", required: true, placeholder: "Why are you unable to attend?" },
      { name: "start_date", label: "Date of absence", type: "date", required: true, today: true, half: true },
      { name: "expected_return", label: "Expected date to return", type: "date", required: true, half: true },
    ],
  },
};

export function todayISO() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

function dateLimits(kind, field) {
  if (field.type !== "date" || !field.today) return {};
  if (kind === "reservation" || field.name === "start_date") return { min: todayISO() };
  if (field.name !== "expected_return") return { max: todayISO() };
  return {};
}

function initialValues(kind, prefill) {
  const values = {};
  FORMS[kind].fields.forEach((f) => {
    if (f.type === "file") return;
    values[f.name] = f.today && f.type === "date" ? todayISO() : "";
    if (prefill && prefill[f.name]) values[f.name] = prefill[f.name];
  });
  return values;
}

export function SuccessCard({ result }) {
  return (
    <div className="bubble success-card">
      <strong>{result.message}</strong>
      Reference: #{result.id}<br />Status: {result.status}
      {result.expected_return && <><br />Expected return: {result.expected_return}</>}
      {result.pdf_url && <><br /><a href={result.pdf_url} target="_blank" rel="noopener noreferrer">Open PDF report</a></>}
    </div>
  );
}

function ReportPhotoPicker({ disabled, file, onChange }) {
  const [mode, setMode] = useState("");
  const [error, setError] = useState("");
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const uploadRef = useRef(null);
  const preview = useMemo(() => file ? URL.createObjectURL(file) : "", [file]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    if (mode !== "scan" || file || disabled) return undefined;
    let cancelled = false;
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((track) => track.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play().catch(() => {}); }
      })
      .catch(() => setError("Camera access is unavailable. Allow camera access or choose Upload instead."));
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [mode, file, disabled]);

  function pick(fileValue) {
    if (!fileValue) return;
    if (!/^image\/(png|jpeg|webp)$/.test(fileValue.type)) { setError("Choose a PNG, JPG, or WEBP image."); return; }
    if (fileValue.size > 5 * 1024 * 1024) { setError("The photo must be 5 MB or smaller."); return; }
    setError(""); onChange(fileValue);
  }
  async function capture() {
    const video = videoRef.current;
    if (!video?.videoWidth) { setError("The camera is still starting. Try again in a moment."); return; }
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", .88));
    if (!blob) { setError("Could not capture the photo. Please try again."); return; }
    pick(new File([blob], `campus-report-${Date.now()}.jpg`, { type: "image/jpeg" }));
  }

  return <div className="record-photo-picker">
    {!mode && <div className="record-photo-actions">
      <button type="button" className="btn ghost" disabled={disabled} onClick={() => { setMode("upload"); uploadRef.current?.click(); }}>Upload photo</button>
      <button type="button" className="btn ghost" disabled={disabled} onClick={() => { setError(""); setMode("scan"); }}>Scan with camera</button>
    </div>}
    <input ref={uploadRef} type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" hidden disabled={disabled}
      onChange={(event) => { pick(event.target.files?.[0]); event.target.value = ""; }} />
    {mode === "upload" && !file && <div className="record-photo-actions"><span className="muted">Choose an image from your device.</span>
      <button type="button" className="btn ghost" disabled={disabled} onClick={() => uploadRef.current?.click()}>Choose photo</button>
      <button type="button" className="chip" onClick={() => setMode("")}>Back</button></div>}
    {mode === "scan" && !file && <div className="report-camera-scan">
      <video ref={videoRef} playsInline muted autoPlay aria-label="Camera preview for campus report photo" />
      <div className="record-photo-actions"><button type="button" className="btn" disabled={disabled} onClick={capture}>Capture photo</button>
        <button type="button" className="btn ghost" onClick={() => { setMode(""); setError(""); }}>Back</button></div>
    </div>}
    {file && <div className="record-photo-preview"><img src={preview} alt="Preview of attached report photo" />
      <p className="document-scan-status captured">Photo ready to attach.</p>
      <div className="record-photo-actions"><button type="button" className="btn ghost" disabled={disabled} onClick={() => { onChange(null); setMode("scan"); }}>Retake / scan again</button>
        <button type="button" className="btn ghost" disabled={disabled} onClick={() => { onChange(null); setMode("upload"); uploadRef.current?.click(); }}>Choose another upload</button>
        <button type="button" className="chip" disabled={disabled} onClick={() => { onChange(null); setMode(""); }}>Remove</button></div>
    </div>}
    {error && <p className="document-scan-error" role="alert">{error}</p>}
  </div>;
}

/** props: kind, prefill, onSuccess(result) */
export default function RecordForm({ kind, prefill, onSuccess }) {
  const { user, facilities } = useAuth();
  const spec = FORMS[kind];
  const [values, setValues] = useState(() => initialValues(kind, prefill));
  const [file, setFile] = useState(null);
  const [invalid, setInvalid] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const set = (name, value) => setValues((v) => ({ ...v, [name]: value }));

  async function submit() {
    const missing = {};
    let message = "";
    const data = new FormData();
    spec.fields.forEach((f) => {
      if (f.type === "file") {
        if (file) {
          if (file.size > 5 * 1024 * 1024) { missing[f.name] = true; message = "The photo must be 5 MB or smaller."; }
          data.append(f.name, file);
        }
      } else {
        const value = (values[f.name] || "").trim();
        if (f.required && !value) missing[f.name] = true;
        if (kind !== "reservation" || f.name !== "duration_minutes") data.append(f.name, value);
        if (f.type === "select" && value === "Other") {        // "Other": the user types what it is
          const typed = (values[f.name + "_other"] || "").trim();
          if (!typed) missing[f.name + "_other"] = true;
          data.append(f.name + "_other", typed);
        }
      }
    });
    if (kind === "reservation" && values.start_time && values.duration_minutes) {
      const timeParts = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(values.start_time);
      const duration = Number(values.duration_minutes);
      if (!timeParts || !Number.isFinite(duration) || duration <= 0) {
        missing.start_time = !timeParts;
        missing.duration_minutes = !Number.isFinite(duration) || duration <= 0;
      } else {
        const endMinutes = Number(timeParts[1]) * 60 + Number(timeParts[2]) + duration;
        if (endMinutes >= 24 * 60) {
          missing.duration_minutes = true;
          message = "The selected duration must end before midnight.";
        } else {
          data.append("end_time", `${String(Math.floor(endMinutes / 60)).padStart(2, "0")}:${String(endMinutes % 60).padStart(2, "0")}`);
        }
      }
    }
    setInvalid(missing);
    if (Object.keys(missing).length) {
      setError(message || "Please complete all required fields.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const result = await api(spec.endpoint, { method: "POST", form: data });
      setDone(true);
      onSuccess && onSuccess(result);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  function control(f) {
    const common = {
      disabled: done, className: invalid[f.name] ? "invalid" : "",
      placeholder: f.placeholder, ...dateLimits(kind, f),
    };
    if (f.type === "textarea")
      return <textarea {...common} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} />;
    if (f.type === "select")
      return (
        <>
          <select {...common} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}>
            <option value="">Choose...</option>
            {f.options.map((o) => <option key={o}>{o}</option>)}
          </select>
          {values[f.name] === "Other" && (
            <input type="text" disabled={done} maxLength={50} style={{ marginTop: 8 }}
                   className={invalid[f.name + "_other"] ? "invalid" : ""}
                   placeholder={`Type your ${f.label.toLowerCase()} *`}
                   aria-label={`Other ${f.label.toLowerCase()}`}
                   value={values[f.name + "_other"] || ""}
                   onChange={(e) => set(f.name + "_other", e.target.value)} />
          )}
        </>
      );
    if (f.type === "duration")
      return (
        <select {...common} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}>
          <option value="">Choose duration...</option>
          {[30, 60, 90, 120, 180, 240, 360, 480].map((minutes) => (
            <option key={minutes} value={minutes}>
              {minutes < 60 ? `${minutes} minutes` : `${minutes / 60} hour${minutes === 60 ? "" : "s"}`}
            </option>
          ))}
        </select>
      );
    if (f.type === "file") return <ReportPhotoPicker disabled={done || busy} file={file} onChange={setFile} />;
    return (
      <input {...common} type={f.type} value={values[f.name]} list={f.list ? "facility-list" : undefined}
             onChange={(e) => set(f.name, e.target.value)} />
    );
  }

  function field(f) {
    return (
      <>
        <label>{f.label}{f.required ? " *" : ""}</label>
        {control(f)}
        {kind === "reservation" && f.name === "start_time" &&
          <small className="muted">Choose the start time using the clock. The end time is calculated from your selected duration.</small>}
        {f.list && <datalist id="facility-list">{facilities.map((n) => <option key={n} value={n} />)}</datalist>}
      </>
    );
  }

  // two "half" fields in a row share one line
  const body = [];
  for (let i = 0; i < spec.fields.length; i++) {
    const f = spec.fields[i];
    const next = spec.fields[i + 1];
    if (f.half && next && next.half) {
      body.push(<div className="two" key={f.name}><div>{field(f)}</div><div>{field(next)}</div></div>);
      i++;
    } else {
      body.push(<div key={f.name}>{field(f)}</div>);
    }
  }

  return (
    <div className={"inline-form" + (done ? " done" : "")}>
      <h3>{spec.title}</h3>
      <p className="desc">{spec.desc}</p>
      <label>Signed in as</label>
      <input type="text" readOnly value={`${user.name} (${user.email})`} />
      {body}
      <p className="form-error" role="alert">{error}</p>
      <button className="form-submit" type="button" disabled={busy || done} onClick={submit}>
        {done ? "Submitted" : busy ? "Submitting..." : "Submit"}
      </button>
    </div>
  );
}
