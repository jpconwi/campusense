/*
 * PhotoReportCard.jsx - shown in the chat after a student sends a photo.
 * Shows what NEMSAI noticed, asks the follow-up questions, lets the student
 * correct everything (by typing) and sends the report to the administrators.
 */
import { useState } from "react";
import { api } from "../api.js";

const FIELDS = [
  ["location", "Where did this happen?", "e.g. CITE building, 2nd floor"],
  ["noticed_when", "When did you notice it?", "e.g. this morning"],
  ["observed_cause", "Do you know what caused it?", "or write \"I don't know\""],
];
const ASKED = { location: "location", noticed_when: "when", observed_cause: "cause" };
const CONFIDENCE = { high: "fairly sure", medium: "somewhat sure", low: "not sure" };
// photos that are clearly not a campus problem: show a short card instead of a report form
const NOT_A_REPORT = {
  people: "This looks like a photo of people.",
  meme_or_screenshot: "This looks like a picture, meme or screenshot.",
  unrelated: "I can't see anything related to the campus in this photo.",
};

export default function PhotoReportCard({ result: first, preview, onMessage, onSent, onDiscarded }) {
  const [result, setResult] = useState(first);
  const [vals, setVals] = useState(() => {
    try { return { ...first.values, ...JSON.parse(sessionStorage.getItem(`photo-draft-${first.draft_id}`) || "{}") }; }
    catch { return first.values; }
  });
  const [destination, setDestination] = useState(() => {
    try { return sessionStorage.getItem(`photo-destination-${first.draft_id}`) || first.analysis?.destination || "report"; }
    catch { return first.analysis?.destination || "report"; }
  });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [state, setState] = useState("open");           // open | sent | discarded
  const [expanded, setExpanded] = useState(false);       // "report a problem anyway"

  const set = (k, v) => setVals((x) => {
    const next = { ...x, [k]: v };
    try { sessionStorage.setItem(`photo-draft-${result.draft_id}`, JSON.stringify(next)); } catch { /* storage is optional */ }
    return next;
  });
  const dirty = Object.keys(vals).some((k) => (vals[k] || "") !== (result.values[k] || ""));
  const asked = new Set(result.questions.map((q) => q.key));
  const question = (key) => (result.questions.find((q) => q.key === ASKED[key]) || {}).question;
  const a = result.analysis;

  function body() {
    const f = new FormData();
    Object.entries(vals).forEach(([k, v]) => f.append(k, (v || "").trim()));
    f.append("destination", destination);
    return f;
  }

  function chooseDestination(value) {
    setDestination(value);
    try { sessionStorage.setItem(`photo-destination-${result.draft_id}`, value); } catch { /* storage is optional */ }
  }

  async function check() {
    setBusy("check"); setError("");
    try {
      const f = body(); f.append("draft_id", result.draft_id);
      const data = await api("/api/reports/photo/analyze", { method: "POST", form: f });
      setResult(data); setVals(data.values);
      onMessage(data.message);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  async function send() {
    setBusy("send"); setError("");
    try {
      const data = await api(`/api/reports/photo/${result.draft_id}/submit`, { method: "POST", form: body() });
      try { sessionStorage.removeItem(`photo-draft-${result.draft_id}`); } catch { /* storage is optional */ }
      try { sessionStorage.removeItem(`photo-destination-${result.draft_id}`); } catch { /* storage is optional */ }
      setResult((current) => ({ ...current, destination: data.destination }));
      setState("sent"); onSent(data);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }

  async function discard() {
    setBusy("discard"); setError("");
    try {
      await api(`/api/reports/photo/${result.draft_id}`, { method: "DELETE" });
      try { sessionStorage.removeItem(`photo-draft-${result.draft_id}`); } catch { /* storage is optional */ }
      try { sessionStorage.removeItem(`photo-destination-${result.draft_id}`); } catch { /* storage is optional */ }
      setState("discarded"); onDiscarded();
    } catch (e) { setError(e.message); setBusy(""); }
  }

  if (state === "sent") return <div className="bubble rich photo-card done"><strong>{result.destination === "concern" ? "Concern sent." : "Report sent."}</strong> An administrator will review it.</div>;
  if (state === "discarded") return <div className="bubble rich photo-card done">Photo removed. Nothing was sent.</div>;

  const a0 = result.analysis || {};
  if (result.outcome === "no_issue" && NOT_A_REPORT[a0.image_kind] && !expanded) {
    return (
      <div className="bubble rich photo-card compact">
        <div className="photo-head">
          {preview && <img className="photo-thumb" src={preview} alt="The photo you sent" />}
          <div>
            <h3>Not a campus report</h3>
            <p className="desc">{NOT_A_REPORT[a0.image_kind]} Nothing was sent to the administrators.</p>
          </div>
        </div>
        <p className="form-error" role="alert">{error}</p>
        <div className="photo-actions">
          <button type="button" className="btn" disabled={!!busy} onClick={discard}>
            {busy === "discard" ? "Removing..." : "Remove photo"}
          </button>
          <button type="button" className="btn ghost" disabled={!!busy} onClick={() => setExpanded(true)}>
            It is a campus problem
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bubble rich photo-card">
      <div className="photo-head">
        {preview && <img className="photo-thumb" src={preview} alt="The photo you sent" />}
        <div>
          <h3>Your photo {destination === "concern" ? "concern" : "report"}</h3>
          <p className="desc">NEMSAI's image check is only a suggestion. Choose how to submit it; nothing is sent until you press the button below.</p>
        </div>
      </div>

      <label htmlFor="pr-destination">Submit this as</label>
      <select id="pr-destination" value={destination} disabled={!!busy}
              onChange={(e) => chooseDestination(e.target.value)}>
        <option value="concern">Concern — a campus facility or service problem</option>
        <option value="report">Report — an incident or safety/security issue</option>
      </select>
      <p className="muted">NEMSAI suggests: {a.destination === "concern" ? "Concern" : "Report"}. You can change this.</p>

      {a.urgent && (
        <div className="urgent-note" role="alert">
          <strong>Possible safety hazard.</strong> Keep away from it and tell campus security or the nearest staff
          member now if anyone is in danger. This report will be marked for priority review.
        </div>
      )}

      {(a.observations.length > 0 || a.issue_title) && (
        <details className="ai-notes">
          <summary>What NEMSAI noticed <span className="badge ai-guess">NEMSAI guess, not verified</span></summary>
          {a.issue_title && <p><strong>{a.issue_title}</strong> <span className="muted">({CONFIDENCE[a.confidence] || "not sure"})</span></p>}
          <ul>{a.observations.map((o, i) => <li key={i}>{o}</li>)}</ul>
          {a.check_explanation && <p className="muted">{a.check_explanation}</p>}
        </details>
      )}

      <label htmlFor="pr-desc">{asked.has("description") ? result.questions.find((q) => q.key === "description").question : "Your description"}</label>
      <div className="with-mic">
        <textarea id="pr-desc" rows={3} maxLength={2000} disabled={!!busy} value={vals.description}
                  placeholder="Type what happened" onChange={(e) => set("description", e.target.value)} />
      </div>

      {FIELDS.map(([key, label, placeholder]) => (
        <div key={key} className={asked.has(ASKED[key]) ? "asked" : ""}>
          <label htmlFor={"pr-" + key}>{question(key) || label}</label>
          <div className="with-mic">
            <input id={"pr-" + key} type="text" maxLength={key === "observed_cause" ? 500 : 120} disabled={!!busy}
                   value={vals[key]} placeholder={placeholder} onChange={(e) => set(key, e.target.value)} />
          </div>
        </div>
      ))}

      <p className="form-error" role="alert">{error}</p>
      <div className="photo-actions">
        <button type="button" className="btn" disabled={!!busy || !result.can_submit} onClick={send}>
          {busy === "send" ? "Sending..." : destination === "concern" ? "Send concern" : "Send report"}
        </button>
        <button type="button" className="btn ghost" disabled={!!busy || !dirty || result.checks_left < 1} onClick={check}>
          {busy === "check" ? "Checking..." : "Check again"}
        </button>
        <button type="button" className="btn ghost" disabled={!!busy} onClick={discard}>Discard photo</button>
      </div>
      {!result.can_submit && <p className="muted">Add a short description above and press <em>Check again</em> to continue.</p>}
    </div>
  );
}
