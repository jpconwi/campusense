/*
 * RecordForm.jsx - one place that defines every form (concern, report, feedback,
 * reservation, faculty). The chat window and the normal pages both use it.
 * Name and email are NOT typed by the user: the server takes them from the
 * signed-in Google account.
 */
import { useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const CONCERN_TYPES = ["Equipment", "Electrical", "Plumbing", "Furniture", "Building / Structure", "Cleanliness", "Safety", "Other"];
const REPORT_TYPES = ["Maintenance", "Safety", "Security", "Cleanliness", "Equipment", "Other"];
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
    title: "Feedback Form", endpoint: "/api/feedback", desc: "Share your feedback about a campus area or facility.",
    fields: [
      { name: "area", label: "Area / Facility", type: "text", required: true, placeholder: "e.g. Library" },
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
      { name: "end_time", label: "End time", type: "time", required: true, half: true },
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
        data.append(f.name, value);
      }
    });
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
        <select {...common} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}>
          <option value="">Choose...</option>
          {f.options.map((o) => <option key={o}>{o}</option>)}
        </select>
      );
    if (f.type === "file")
      return <input {...common} type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
                    onChange={(e) => setFile(e.target.files[0] || null)} />;
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
