import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, apiUrl, slug } from "../api.js";
import { useAuth } from "../auth.jsx";
import { EmptyState, Icon, Loading, PATHS, SearchBox } from "../components/Ui.jsx";

const LONG_TEXT = ["description", "message", "purpose", "additional_info"];

function StatusForm({ kind, row, statuses, onChanged }) {
  const { setFlash } = useAuth();
  const [value, setValue] = useState(row.status);
  useEffect(() => setValue(row.status), [row.status]);

  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/records/${kind}/${row.id}/status`, { method: "POST", json: { status: value } });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) {
      setFlash({ text: err.message, kind: "error" });
    }
    onChanged();
  }

  return (
    <form className="inline" onSubmit={save}>
      <select id={`status-${kind}-${row.id}`} aria-label="New status" value={value} onChange={(e) => setValue(e.target.value)}>
        {statuses.map((s) => <option key={s}>{s}</option>)}
      </select>{" "}
      <button className="btn small" type="submit">Save</button>
    </form>
  );
}

function AssignmentForm({ row, kind, assignees, onChanged }) {
  const { setFlash } = useAuth();
  const [value, setValue] = useState(row.assigned_admin_email || "");
  useEffect(() => setValue(row.assigned_admin_email || ""), [row.assigned_admin_email]);
  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/records/${kind}/${row.id}/assign`, {
        method: "POST", json: { assigned_admin_email: value || null },
      });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) {
      setFlash({ text: err.message, kind: "error" });
    }
    onChanged();
  }
  return (
    <form className="inline" onSubmit={save} style={{ marginTop: 6 }}>
      <input aria-label={`Assign report ${row.id} to a department or administrator`} list={`assignees-${kind}-${row.id}`}
        value={value} onChange={(e) => setValue(e.target.value)} placeholder="Department or admin email" />
      <datalist id={`assignees-${kind}-${row.id}`}>
        {assignees.map((email) => <option key={email} value={email} />)}
      </datalist>
      {row.assigned_admin_email && <button className="btn small ghost" type="button" onClick={() => setValue("")}>Clear</button>}
      <button className="btn small" type="submit" disabled={value === (row.assigned_admin_email || "")}>Assign</button>
    </form>
  );
}

function AdminUpdateForm({ row, kind, onChanged }) {
  const { setFlash } = useAuth();
  const [message, setMessage] = useState(row.admin_feedback || "");
  useEffect(() => setMessage(row.admin_feedback || ""), [row.admin_feedback]);
  async function save(event) {
    event.preventDefault();
    try {
      const result = await api(`/api/admin/records/${kind}/${row.id}/feedback`, {
        method: "POST", json: { message },
      });
      setFlash({ text: result.message, kind: "info" });
      onChanged();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }
  return <form className="admin-update-form" onSubmit={save}>
    <label htmlFor={`admin-update-${kind}-${row.id}`}>Update for reporter</label>
    <textarea id={`admin-update-${kind}-${row.id}`} rows={2} maxLength={2000} value={message}
      onChange={(event) => setMessage(event.target.value)} placeholder="Share a status update or resolution details." />
    <button className="btn small" type="submit">Send update</button>
  </form>;
}

function FeedbackAdminTools({ row, onChanged }) {
  const { user, setFlash } = useAuth();
  const [message, setMessage] = useState(row.admin_response || "");
  useEffect(() => setMessage(row.admin_response || ""), [row.admin_response]);
  async function save(event) {
    event.preventDefault();
    try {
      const result = await api(`/api/admin/feedback/${row.id}/response`, {
        method: "POST", json: { message },
      });
      setFlash({ text: result.message, kind: "info" }); onChanged();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }
  async function forward() {
    if (!window.confirm("Forward this feedback to the Super Admin for system review?")) return;
    try {
      const result = await api(`/api/admin/feedback/${row.id}/forward`, { method: "POST", json: {} });
      setFlash({ text: result.message, kind: "info" }); onChanged();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }
  return <div className="feedback-admin-tools">
    <form className="feedback-response-form" onSubmit={save}>
      <label htmlFor={`feedback-response-${row.id}`}>Response to student or faculty</label>
      <textarea id={`feedback-response-${row.id}`} rows={3} maxLength={2000} value={message}
        onChange={(event) => setMessage(event.target.value)} placeholder="Write a response or follow-up." />
      <button className="btn small" type="submit">Save response</button>
    </form>
    {user?.role === "admin" && row.feedback_scope === "campus" && <button className="btn small ghost" type="button" onClick={forward}>
      Forward to Super Admin
    </button>}
  </div>;
}

function adminActivityLabel(admin) {
  if (!admin.account_active) return "Admin account inactive";
  if (admin.online) return "Active now";
  if (!admin.last_active_at) return "No activity recorded";
  const elapsed = Math.max(0, Date.now() - new Date(admin.last_active_at).getTime());
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "Last active less than a minute ago";
  if (minutes < 60) return `Last active ${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Last active ${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  return `Last active ${days} ${days === 1 ? "day" : "days"} ago`;
}

function AdminPicker({ id, admins, value, onChange }) {
  const [open, setOpen] = useState(false);
  const selected = admins.find((admin) => admin.email === value);
  return <div className="admin-picker">
    <button id={id} className="admin-picker-trigger" type="button" aria-haspopup="listbox" aria-expanded={open}
      onClick={() => setOpen((current) => !current)}>
      {selected ? <><i className={`admin-picker-dot${selected.online ? " is-online" : ""}`} />{selected.name}</> : "Choose an administrator"}
      <span aria-hidden="true">⌄</span>
    </button>
    {open && <div className="admin-picker-options" role="listbox" aria-label="Available administrators">
      {admins.length ? admins.map((admin) => <button key={admin.id} type="button" role="option"
        aria-selected={admin.email === value} disabled={!admin.account_active}
        className="admin-picker-option" onClick={() => { onChange(admin.email); setOpen(false); }}>
        <i className={`admin-picker-dot${admin.online ? " is-online" : ""}`} />
        <span className="admin-picker-person"><strong>{admin.name}</strong><small>{admin.email}</small></span>
        <span className="admin-picker-activity">{adminActivityLabel(admin)}</span>
      </button>) : <p className="muted admin-picker-empty">No configured admin accounts were found.</p>}
    </div>}
    {selected && <small className="admin-picker-selected-activity">{adminActivityLabel(selected)}</small>}
  </div>;
}

function ReviewWorkflow({ row, kind, assignees, onChanged }) {
  const { setFlash } = useAuth();
  const [note, setNote] = useState(row.workflow_review_note || "");
  const [assignee, setAssignee] = useState(row.assigned_admin_email || "");
  const [priority, setPriority] = useState(row.priority || "Medium");
  useEffect(() => setPriority(row.priority || "Medium"), [row.priority]);
  const canAssign = assignees.some((admin) => admin.email === assignee && admin.account_active);
  async function savePriority() {
    try {
      const result = await api(`/api/admin/records/${kind}/${row.id}/priority`, {
        method: "POST", json: { priority },
      });
      setFlash({ text: result.message, kind: "info" }); onChanged();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }
  async function decide(decision) {
    try {
      const result = await api(`/api/admin/records/${kind}/${row.id}/decision`, {
        method: "POST", json: { decision, note },
      });
      setFlash({ text: result.message, kind: "info" }); onChanged();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }
  async function assign(event) {
    event.preventDefault();
    try {
      const result = await api(`/api/admin/records/${kind}/${row.id}/assign`, {
        method: "POST", json: { assigned_admin_email: assignee },
      });
      setFlash({ text: result.message, kind: "info" }); onChanged();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }
  return <section className="report-review-workflow">
    <h4>Super Admin review</h4>
    <p><b>Review status:</b> {row.workflow_review || "Pending"}</p>
    <div className="report-priority-control">
      <label htmlFor={`priority-${kind}-${row.id}`}>Set work priority</label>
      <select id={`priority-${kind}-${row.id}`} value={priority} onChange={(event) => setPriority(event.target.value)}>
        {["Urgent", "High", "Medium", "Low"].map((level) => <option key={level}>{level}</option>)}
      </select>
      <button className="btn small" type="button" disabled={priority === (row.priority || "Medium")} onClick={savePriority}>Save priority</button>
    </div>
    {row.workflow_reviewed_by && <p className="muted">Reviewed by {row.workflow_reviewed_by}{row.workflow_reviewed_at ? ` on ${row.workflow_reviewed_at}` : ""}</p>}
    {row.workflow_review_note && <p>{row.workflow_review_note}</p>}
    {row.workflow_review === "Pending" ? <>
      <label htmlFor={`review-note-${kind}-${row.id}`}>Review note (optional)</label>
      <textarea id={`review-note-${kind}-${row.id}`} rows={2} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />
      <div className="report-review-actions">
        <button className="btn small" type="button" onClick={() => decide("Accepted")}>Accept report</button>
        <button className="btn small danger" type="button" onClick={() => decide("Rejected")}>Reject report</button>
      </div>
    </> : row.workflow_review === "Accepted" && <form className="admin-assignment-form" onSubmit={assign}>
      <label htmlFor={`assign-review-${kind}-${row.id}`}>Assign to administrator</label>
      <AdminPicker id={`assign-review-${kind}-${row.id}`} admins={assignees} value={assignee} onChange={setAssignee} />
      <button className="btn small" type="submit" disabled={!canAssign}>Assign</button>
    </form>}
  </section>;
}

function DeleteRecordButton({ row, onChanged }) {
  const { setFlash } = useAuth();
  const [busy, setBusy] = useState(false);
  const recordKind = row.record_kind === "concern" ? "concerns" : "reports";
  const label = row.record_kind === "concern" ? "concern" : "report";
  async function remove() {
    if (!window.confirm(`Permanently delete ${label} #${row.id}? Its photo and generated PDF will also be deleted.`)) return;
    setBusy(true);
    try {
      const result = await api(`/api/admin/${recordKind}/${row.id}`, { method: "DELETE" });
      setFlash({ text: result.message, kind: "info" });
      onChanged();
    } catch (err) {
      setFlash({ text: err.message, kind: "error" });
    } finally {
      setBusy(false);
    }
  }
  return <button className="btn small danger" type="button" disabled={busy} onClick={remove}>
    {busy ? "Deleting..." : `Delete ${label}`}
  </button>;
}

/** "2026-10-29 11:26:02" -> date on one line, time (smaller) below it. */
function DateCell({ value }) {
  const [date, ...time] = String(value || "").split(" ");
  return <span>{date}{time.length > 0 && <><br /><small className="muted">{time.join(" ")}</small></>}</span>;
}

function RecordCard({ row, columns, kind, spec, statuses, assignees = [], onChanged }) {
  const scopeLabels = { campus: "Campus services", system: "NEMSAI / application", technical: "Technical issue" };
  const reference = row.record_kind === "concern" ? `NEMSAI-C-${String(row.id).padStart(4, "0")}`
    : kind === "feedback" ? `FB-${String(row.id).padStart(4, "0")}` : `NEMSAI-${String(row.id).padStart(4, "0")}`;
  const nameKey = ["reporter_name", "name", "requester_name"].find((key) => row[key] !== undefined);
  const emailKey = ["reporter_email", "email", "requester_email"].find((key) => row[key] !== undefined);
  const details = columns.filter(([, key]) => !["id", "created_at", "status", "assigned_admin_email",
    nameKey, emailKey, "submitter_role"].includes(key) && row[key]);
  return <article className={`record-card${row.record_kind === "concern" ? " report-concern-card" : ""}`}>
    <div className="record-card-head">
      <div><span className={`badge record-kind-badge ${row.record_kind === "concern" || kind === "concerns" ? "record-kind-concern" : "record-kind-problem"}`}>{row.record_kind === "concern" || kind === "concerns" ? "Concern" : "Problem"}</span><strong>{reference}</strong><DateCell value={row.created_at} /></div>
      <span className={"badge s-" + slug(row.status)}>{row.status}</span>
    </div>
    <div className="record-card-person">
      <strong>{row[nameKey] || "Unknown sender"}</strong>
      {row[emailKey] && <a href={`mailto:${row[emailKey]}`}>{row[emailKey]}</a>}
      {row.submitter_role && <small>{row.submitter_role}</small>}
      {row.source === "photo" && <span className="badge ai-guess">Photo + NEMSAI · unverified</span>}
    {(kind === "concerns" || kind === "reports") && <span className={`badge priority-${slug(row.priority || "Medium")}`}>{row.priority || "Medium"} priority</span>}
    </div>
    {row.source === "photo" && row.ai && <div className="record-card-fields">
      {row.ai.urgent && <div><b>Priority flag</b><span>Possible hazard · needs administrator review</span></div>}
      {row.ai.issue_title && <div><b>NEMSAI suggestion</b><span>{row.ai.issue_title} ({row.ai.confidence || "low"} confidence)</span></div>}
      {row.ai.status === "analyzed" && <div className="record-card-long"><b>Repair planning estimate (admin only · unverified)</b><span>
        {row.ai.image_kind === "campus_issue" && ["yes", "possible"].includes(row.ai.shows_issue) ? <>
          Cost: {row.ai.estimated_budget_php_min != null && row.ai.estimated_budget_php_max != null
            ? `${PESO.format(row.ai.estimated_budget_php_min)} to ${PESO.format(row.ai.estimated_budget_php_max)} (${row.ai.estimate_confidence || "low"} confidence)`
            : "not estimable from the photo; inspect onsite"}. Workers: {row.ai.estimated_staff ?? "needs onsite assessment"}. Working days: {row.ai.estimated_days_min != null && row.ai.estimated_days_max != null
              ? `${row.ai.estimated_days_min} to ${row.ai.estimated_days_max}` : "needs onsite assessment"}.
          {row.ai.estimate_assumptions && ` ${row.ai.estimate_assumptions}`}
        </> : "No repair estimate: the image check did not identify a clear campus repair issue."}
      </span></div>}
      {row.ai.observations?.length > 0 && <div className="record-card-long"><b>Photo notes</b><span>{row.ai.observations.join(" · ")}</span></div>}
    </div>}
    <div className="record-card-fields">
      {details.map(([label, key]) => <div className={LONG_TEXT.includes(key) ? "record-card-long" : ""} key={key}>
        <b>{label}</b>
        <span>{key === "feedback_scope" ? scopeLabels[row[key]] || row[key] : row[key]}</span>
      </div>)}
    </div>
    {(kind === "concerns" || kind === "reports") && <div className="report-workflow-controls">
      <div><label>Assigned department or administrator</label><AssignmentForm row={row} kind={kind} assignees={assignees} onChanged={onChanged} /></div>
      <AdminUpdateForm row={row} kind={kind} onChanged={onChanged} />
    </div>}
    {kind === "feedback" && <FeedbackAdminTools row={row} onChanged={onChanged} />}
    <div className="record-card-links">
      {row.image_filename && <ReportPhoto filename={row.image_filename} />}
      {spec.pdf && <a href={`/api/pdf/${kind}/${row.id}`} target="_blank" rel="noopener noreferrer">Download PDF</a>}
    </div>
    <div className="record-card-footer">
      <div className="record-card-status"><label htmlFor={`status-${kind}-${row.id}`}>Update status</label>
        <StatusForm kind={kind} row={row} statuses={statuses} onChanged={onChanged} />
      </div>
      {row.record_kind && <DeleteRecordButton row={row} onChanged={onChanged} />}
    </div>
  </article>;
}

const CONF = { high: "fairly sure", medium: "somewhat sure", low: "not sure" };
const CHECK = { supports: "matches the photo", partly: "partly matches the photo",
                contradicts: "does not match the photo", cannot_tell: "cannot tell from the photo" };
const PESO = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 0 });

function ReportPhoto({ filename }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [filename]);
  if (!filename) return null;
  const url = apiUrl(`/api/uploads/${encodeURIComponent(filename)}`);
  return failed ? <span className="muted">Photo unavailable</span> : (
    <a className="report-photo-link" href={url} target="_blank" rel="noopener noreferrer"
       title="Open the student's uploaded photo">
      <img className="report-photo-thumb" src={url} alt="Student's uploaded report photo"
           loading="lazy" onError={() => setFailed(true)} />
    </a>
  );
}

function Flags({ r }) {
  return (
    <>
      {r.urgent && <span className="badge urgent" title="Possible safety hazard, not confirmed">Possible hazard</span>}{" "}
      {r.source === "photo" && <span className="badge ai-guess" title="Sent with a photo and checked by NEMSAI">Photo + NEMSAI</span>}{" "}
      {r.source === "photo" && r.verification && r.verification !== "Unverified" &&
        <span className={"badge ver-" + slug(r.verification)}>{r.verification}</span>}
    </>
  );
}

/** Everything about one photo report: photo, student's words, NEMSAI notes, verification. */
function PhotoDetail({ row, apiKind, onChanged }) {
  const { setFlash } = useAuth();
  const { user } = useAuth();
  const ai = row.ai || {};
  const [choice, setChoice] = useState(row.verification || "Unverified");
  const [note, setNote] = useState(row.verification_note || "");
  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/${apiKind}/${row.id}/verify`, { method: "POST", json: { verification: choice, note } });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    onChanged();
  }
  return (
    <div className="photo-detail">
      {row.image_filename && <ReportPhoto filename={row.image_filename} />}
      <div className="photo-detail-text">
        {row.urgent && <div className="urgent-note"><strong>Possible safety hazard (not confirmed).</strong> {ai.urgent_reason}</div>}
        <h4>Student's report</h4>
        <p>{row.description}</p>
        <p className="muted">Location: {row.location}{row.noticed_when ? ` · Noticed: ${row.noticed_when}` : ""}{row.observed_cause ? ` · Cause mentioned: ${row.observed_cause}` : ""}</p>
        <h4>NEMSAI analysis <span className="badge ai-guess">unverified</span></h4>
        {ai.status === "unavailable" || !row.ai ? <p>{ai.unavailable_reason === "no_provider_configured"
          ? "No NEMSAI vision provider key is configured for this backend. Add a supported key to the backend environment to enable photo analysis."
          : "The configured NEMSAI providers could not analyze this photo. Please review it by hand."}</p> : (
          <>
            <p><strong>{ai.issue_title || "No clear problem named"}</strong> · category {row.report_type} · {CONF[ai.confidence] || "not sure"}</p>
            {ai.observations && ai.observations.length > 0 && <ul>{ai.observations.map((o, i) => <li key={i}>{o}</li>)}</ul>}
            {row.description && !row.description.startsWith("(The student did not") &&
              <p className="muted">Description {CHECK[ai.description_check] || "was not compared"}. {ai.check_explanation}</p>}
            <section className="photo-admin-estimate">
              <h4>Preliminary severity and repair estimate <span className="badge ai-guess">NEMSAI estimate · unverified</span></h4>
              <p><strong>Severity:</strong> <span className={`badge severity-${ai.severity || "unclear"}`}>{(ai.severity || "unclear").toUpperCase()}</span>
                {ai.severity_reason ? ` ${ai.severity_reason}` : " Needs onsite review."}</p>
              <p><strong>Planning cost:</strong> {ai.estimated_budget_php_min != null && ai.estimated_budget_php_max != null
                ? <>{PESO.format(ai.estimated_budget_php_min)} to {PESO.format(ai.estimated_budget_php_max)} <small>({ai.estimate_confidence || "low"} confidence)</small></>
                : "Not estimable from available evidence; inspect onsite."}</p>
              <p><strong>Workers:</strong> {ai.estimated_staff != null ? `${ai.estimated_staff} (preliminary)` : "Needs onsite scope assessment."}</p>
              <p><strong>Working days:</strong> {ai.estimated_days_min != null && ai.estimated_days_max != null
                ? `${ai.estimated_days_min} to ${ai.estimated_days_max} (preliminary)` : "Needs onsite scope assessment."}</p>
              {ai.repair_approach && <p><strong>Possible repair approach:</strong> {ai.repair_approach}</p>}
              {ai.repair_steps?.length > 0 && <ul>{ai.repair_steps.map((step, i) => <li key={i}>{step}</li>)}</ul>}
              {ai.estimate_assumptions && <p className="muted"><strong>Assumptions:</strong> {ai.estimate_assumptions}</p>}
              {ai.pricing_basis && <p className="muted"><strong>Price basis:</strong> {ai.pricing_basis}</p>}
              {ai.pricing_sources?.length > 0 && <div><strong>Price sources:</strong><ul>{ai.pricing_sources.map((source, i) => (
                <li key={`${source.url}-${i}`}><a href={source.url} target="_blank" rel="noreferrer">{source.title || source.url}</a></li>
              ))}</ul></div>}
              <small className="muted">NEMSAI screening only, not a diagnosis, quotation, or approved budget. Confirm onsite and price with current local supplier/labor rates.</small>
            </section>
          </>
        )}
        {user?.role === "admin" && <form className="verify-form" onSubmit={save}>
          <label htmlFor={`v-${row.id}`}>Your verdict on NEMSAI's findings</label>
          <select id={`v-${row.id}`} value={choice} onChange={(e) => setChoice(e.target.value)}>
            <option>Unverified</option><option>Confirmed</option><option>Not confirmed</option>
          </select>
          <textarea rows={2} maxLength={500} placeholder="Reason or onsite observations (optional)" aria-label="Reason for your verdict" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn small" type="submit">Save verdict</button>
          {row.verified_by && <span className="muted">Last set by {row.verified_by}</span>}
        </form>}
      </div>
    </div>
  );
}

const shortText = (text, limit = 110) => {
  const value = String(text || "").trim();
  return value.length > limit ? value.slice(0, limit - 1) + "…" : value;
};

/**
 * Everything an admin needs for one record, rendered only after the row is opened.
 * Photo reports keep the richer verification view; every other record shows its fields.
 */
function RecordDetail({ row, apiKind, assignees, statuses, onChanged, superAdmin }) {
  const photoReport = ["reports", "concerns"].includes(apiKind) && row.source === "photo";
  return (
    <div className="report-detail">
      {photoReport ? <PhotoDetail row={row} apiKind={apiKind} onChanged={onChanged} /> : (
        <div className="report-detail-body">
          <section className="report-detail-main">
            <h4>What was reported</h4>
            <p className="report-card-description">{row.description || "No description provided."}</p>
            <div className="report-card-meta">
              <span><b>Location</b>{row.location || "Not provided"}</span>
              {row.area && <span><b>Area</b>{row.area}</span>}
              {row.room && <span><b>Room</b>{row.room}</span>}
              {row.noticed_when && <span><b>When noticed</b>{row.noticed_when}</span>}
              {row.observed_cause && <span><b>Cause mentioned</b>{row.observed_cause}</span>}
            </div>
          </section>
          <aside className="report-card-reporter">
            <b>Submitted by</b>
            <strong>{row.reporter_name || "Unknown"}</strong>
            {row.reporter_email && <a href={`mailto:${row.reporter_email}`}>{row.reporter_email}</a>}
            {row.submitter_role && <small>{row.submitter_role}</small>}
            {row.image_filename && <ReportPhoto filename={row.image_filename} />}
          </aside>
        </div>
      )}
      {superAdmin ? <ReviewWorkflow row={row} kind={apiKind} assignees={assignees} onChanged={onChanged} /> : <section className="report-review-workflow">
        <h4>Admin actions</h4>
        <div className="report-admin-status"><label>Update status</label><StatusForm kind={apiKind} row={row} statuses={statuses} onChanged={onChanged} /></div>
        <div className="report-review-actions">
          <a className="btn small ghost" href={`/api/pdf/${apiKind}/${row.id}`} target="_blank" rel="noopener noreferrer">Download PDF</a>
          <DeleteRecordButton row={row} onChanged={onChanged} />
        </div>
        <AdminUpdateForm row={row} kind={apiKind} onChanged={onChanged} />
        {row.admin_feedback && <p className="report-last-update">Last update sent to the reporter: {row.admin_feedback}</p>}
      </section>}
    </div>
  );
}

/** Concerns / Reports / Feedback / Reservations for admins. */
export default function AdminList({ kind }) {
  const { user } = useAuth();
  const superAdmin = user?.role === "super_admin";
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const urgent = params.get("urgent") || "";
  const availableFeedbackScopes = superAdmin ? ["all", "campus", "suggestions", "system-technical"] : ["campus", "suggestions"];
  const requestedFeedbackScope = params.get("scope") || (superAdmin ? "all" : "campus");
  const feedbackScope = availableFeedbackScopes.includes(requestedFeedbackScope)
    ? requestedFeedbackScope : (superAdmin ? "all" : "campus");
  const requestedType = params.get("type") || "all";
  const typeFilter = ["concern", "problem"].includes(requestedType) ? requestedType : "all";
  const page = Math.max(1, Number(params.get("page") || 1));
  const selectedPriority = ["Urgent", "High", "Medium", "Low"].includes(params.get("priority")) ? params.get("priority") : "";
  const openOnly = params.get("open_only") === "true";
  const priorityRelevant = kind === "reports" && typeFilter !== "concern";
  const activeUrgent = priorityRelevant ? urgent : "";
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);                 // "<kind>-<id>" of the record whose details are shown
  const [q, setQ] = useState("");                         // search box
  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setOpen(null);
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const load = useCallback(() => {
    const query = new URLSearchParams({ page: String(page), page_size: "100" });
    if (status) query.set("status", status);
    if (activeUrgent) query.set("urgent", activeUrgent);
    if (kind === "feedback") query.set("scope", feedbackScope);
    if (kind === "reports" && typeFilter !== "all") query.set("record_type", typeFilter);
    if (selectedPriority) query.set("priority", selectedPriority);
    if (openOnly) query.set("open_only", "true");
    if (q.trim()) query.set("search", q.trim());
    api(`/api/admin/records/${kind}?${query}`).then(setData).catch(() => {});
  }, [kind, status, activeUrgent, feedbackScope, page, typeFilter, q, selectedPriority, openOnly]);
  useEffect(() => { setData(null); setQ(""); }, [kind, status, activeUrgent, feedbackScope, typeFilter, selectedPriority, openOnly]);
  useEffect(() => { const timer = window.setTimeout(load, 250); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => {
    if (!superAdmin || !["reports", "feedback"].includes(kind)) return undefined;
    const timer = window.setInterval(load, 30_000);
    return () => window.clearInterval(timer);
  }, [load, superAdmin, kind]);
  const feedbackTitles = { all: "All Feedback", campus: "Campus Feedback", suggestions: "Campus Suggestions",
    "system-technical": "System & Technical Feedback" };
  const pageTitle = kind === "feedback" ? feedbackTitles[feedbackScope] : data?.spec.title;
  useEffect(() => { if (data) document.title = `${pageTitle || data.spec.title} | NEMSU`; }, [data, pageTitle]);
  useEffect(() => {
    if (data?.pagination?.pages && page > data.pagination.pages) {
      const next = new URLSearchParams(params); next.set("page", String(data.pagination.pages)); setParams(next, { replace: true });
    }
  }, [data, page, params, setParams]);

  if (!data) return <Loading wide={1400} />;
  const { spec, rows: allRows, columns, statuses, current } = data;
  const visibleStatuses = kind === "feedback" && user?.role === "admin"
    ? statuses.filter((value) => value !== "Forwarded") : statuses;
  const assignees = data.assignees || [];
  const typeRows = allRows;
  const rows = allRows;
  const openedRecord = kind === "reports" ? rows.find((r) => {
    const apiKind = r.record_kind === "concern" ? "concerns" : "reports";
    return open === `${apiKind}-${r.id}`;
  }) : null;
  const base = `/admin/${kind}`;
  const filterHref = ({ nextStatus = "", nextUrgent = "" } = {}) => {
    const next = new URLSearchParams();
    if (nextStatus) next.set("status", nextStatus);
    if (kind === "reports" && typeFilter !== "all") next.set("type", typeFilter);
    if (kind === "feedback") next.set("scope", feedbackScope);
    if (priorityRelevant && nextUrgent) next.set("urgent", nextUrgent);
    if (selectedPriority) next.set("priority", selectedPriority);
    if (openOnly && (!nextStatus || ["Pending", "Under Review", "In Progress"].includes(nextStatus))) next.set("open_only", "true");
    return `${base}${next.toString() ? `?${next}` : ""}`;
  };

  return (
    <div className="page" style={{ maxWidth: 1400 }}>
      <h2 className="page-title">{pageTitle || spec.title}</h2>
      {kind === "feedback" && <label className="admin-filter-label" htmlFor="admin-feedback-scope">
        Feedback view
        <select id="admin-feedback-scope" value={feedbackScope} onChange={(event) => {
          const next = new URLSearchParams(params);
          next.set("scope", event.target.value);
          next.delete("status");
          next.delete("page");
          setParams(next);
        }}>
          {superAdmin && <>
            <option value="all">All feedback</option>
            <option value="system-technical">System &amp; technical feedback</option>
          </>}
          <option value="campus">Campus feedback</option><option value="suggestions">Campus suggestions</option>
        </select>
      </label>}
      {kind === "reports" && <label className="admin-filter-label" htmlFor="admin-record-type">
        Record type
        <select id="admin-record-type" value={typeFilter} onChange={(e) => {
          const next = new URLSearchParams(params);
          if (e.target.value === "all") next.delete("type"); else next.set("type", e.target.value);
          if (e.target.value === "concern") next.delete("urgent");
          next.delete("page");
          setParams(next);
        }}>
          <option value="all">All records</option><option value="concern">Concerns</option><option value="problem">Reports</option>
        </select>
      </label>}
      <div className="filters">
        <Link to={filterHref()} className={!current ? "on" : ""}>All statuses</Link>
        {visibleStatuses.map((s) => <Link key={s} to={filterHref({ nextStatus: s, nextUrgent: urgent })} className={current === s ? "on" : ""}>{s}</Link>)}
      </div>
      {priorityRelevant && (
        <div className="filters" aria-label="Filter possible safety hazards">
          <span className="filter-label">AI safety flag:</span>
          <Link to={filterHref({ nextStatus: status })} className={!urgent ? "on" : ""}>All flags</Link>
          <Link to={filterHref({ nextStatus: status, nextUrgent: "1" })} className={urgent ? "on" : ""}>Possible hazards only</Link>
        </div>
      )}
      {kind === "reports" && <div className="filters" aria-label="Filter by assigned priority">
        <span className="filter-label">Work priority:</span>
        {["", "Urgent", "High", "Medium", "Low"].map((level) => <button key={level || "all"} type="button"
          className={selectedPriority === level ? "on" : ""} onClick={() => {
            const next = new URLSearchParams(params);
            if (level) next.set("priority", level); else next.delete("priority");
            next.delete("page"); setParams(next);
          }}>{level || "All priorities"}</button>)}
      </div>}
      {(["reports", "concerns", "feedback", "reservations"].includes(kind)) && (
        <SearchBox value={q} onChange={(value) => {
          setQ(value);
          if (page !== 1) { const next = new URLSearchParams(params); next.delete("page"); setParams(next, { replace: true }); }
        }} shown={rows.length} total={data.pagination?.total || 0}
                   placeholder={`Search ${spec.title.toLowerCase()}...`} />
      )}
      {rows.length ? kind === "reports" ? (
        <>
          <p className="report-list-note">{superAdmin
            ? `Priority is set by the Super Admin. Select a row to review, assign, or update its work priority.`
            : `${rows.length} assigned ${rows.length === 1 ? "report" : "reports"} shown. Select one to update its status or send the reporter an update.`}</p>
          <div className="report-table-wrap">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">Reference</th>
                  <th scope="col">Submitted</th>
                  <th scope="col">Type</th>
                  <th scope="col">Location</th>
                  <th scope="col">Reporter</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Status</th>
                  <th scope="col">Flags</th>
                  <th scope="col">Assigned</th>
                  <th scope="col" aria-label="Details" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const isConcern = r.record_kind === "concern";
                  const apiKind = isConcern ? "concerns" : "reports";
                  const rowKey = `${apiKind}-${r.id}`;
                  const expanded = open === rowKey;
                  const reference = `${isConcern ? "NEMSAI-C-" : "NEMSAI-"}${String(r.id).padStart(4, "0")}`;
                  return (
                    <Fragment key={rowKey}>
                      <tr className={`report-row${r.urgent ? " is-urgent" : ""}${expanded ? " is-open" : ""}`}
                          onClick={() => setOpen(expanded ? null : rowKey)}>
                        <td className="report-ref"><strong>{reference}</strong></td>
                        <td className="report-when"><DateCell value={r.created_at} /></td>
                        <td className="report-type">
                          <span className={`badge record-kind-badge ${isConcern ? "record-kind-concern" : "record-kind-problem"}`}>{isConcern ? "Concern" : "Problem"}</span>
                          <strong>{r.concern_type || r.report_type || (isConcern ? "Campus concern" : "Campus report")}</strong>
                          <small className="report-snippet">{shortText(r.description) || "No description provided."}</small>
                        </td>
                        <td className="report-where">{r.location || "Not provided"}
                          {r.room && <small className="muted">{r.room}</small>}</td>
                        <td className="report-who"><span>{r.reporter_name || "Unknown"}</span>
                          {r.reporter_email && <small className="muted">{r.reporter_email}</small>}</td>
                        <td><span className={`badge priority-${slug(r.priority || "Medium")}`}>{r.priority || "Medium"}</span></td>
                        <td><span className={"badge s-" + slug(r.status)}>{r.status}</span></td>
                        <td className="report-flags"><Flags r={r} />
                          {r.ai?.status === "analyzed" && <span className={`badge severity-${r.ai.severity || "unclear"}`}>{(r.ai.severity || "unclear").toUpperCase()}</span>}</td>
                        <td className="report-assignee">{r.assigned_admin_email || <span className="muted">Unassigned</span>}</td>
                        <td className="report-toggle-cell">
                          <button type="button" className={`report-toggle${expanded ? " is-open" : ""}`} aria-expanded={expanded}
                            aria-label={`${expanded ? "Hide" : "Show"} details for ${reference}`}
                            onClick={(event) => { event.stopPropagation(); setOpen(expanded ? null : rowKey); }}>
                            <Icon d={PATHS.arrow} size={16} />
                          </button>
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          {openedRecord && (() => {
            const apiKind = openedRecord.record_kind === "concern" ? "concerns" : "reports";
            const reference = `${apiKind === "concerns" ? "NEMSAI-C-" : "NEMSAI-"}${String(openedRecord.id).padStart(4, "0")}`;
            return (
              <div className="report-dialog-backdrop" onClick={() => setOpen(null)}>
                <section className="report-dialog" role="dialog" aria-modal="true" aria-labelledby="report-dialog-title"
                         onClick={(event) => event.stopPropagation()}>
                  <header className="report-dialog-header">
                    <div>
                      <span className="report-dialog-eyebrow">{apiKind === "concerns" ? "Concern details" : "Problem report details"}</span>
                      <h3 id="report-dialog-title">{reference}</h3>
                    </div>
                    <button type="button" className="report-dialog-close" onClick={() => setOpen(null)}
                            aria-label="Close report details" autoFocus>×</button>
                  </header>
                  <div className="report-dialog-content">
                    <RecordDetail row={openedRecord} apiKind={apiKind} assignees={assignees} statuses={statuses} onChanged={load} superAdmin={superAdmin} />
                  </div>
                </section>
              </div>
            );
          })()}
        </>
      ) : (
        <section className="record-card-list" aria-label={spec.title}>
          {rows.map((row) => <RecordCard key={row.id} row={row} columns={columns} kind={kind}
            spec={spec} statuses={visibleStatuses} assignees={assignees} onChanged={load} />)}
        </section>
      ) : q ? (
        <EmptyState title="No matches">Nothing matches "{q}". Try fewer or different words.</EmptyState>
      ) : (
        <EmptyState title="Nothing here">
          Nothing here{activeUrgent ? " marked as a possible hazard" : ""}{current ? " with status " + current : ""}.
        </EmptyState>
      )}
      {data.pagination?.total > 0 && data.pagination.pages > 1 && <div className="dataset-toolbar" aria-label="Record pages">
        <span className="muted">Page {page} of {data.pagination.pages} ({data.pagination.total} records)</span>
        <div><button className="btn secondary" type="button" disabled={page <= 1} onClick={() => {
          const next = new URLSearchParams(params); next.set("page", String(page - 1)); setParams(next);
        }}>Previous</button>{" "}
          <button className="btn secondary" type="button" disabled={page >= data.pagination.pages} onClick={() => {
            const next = new URLSearchParams(params); next.set("page", String(page + 1)); setParams(next);
          }}>Next</button></div>
      </div>}
    </div>
  );
}
