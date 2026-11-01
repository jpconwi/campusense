import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, apiUrl, slug } from "../api.js";
import { useAuth } from "../auth.jsx";
import { EmptyState, Loading, SearchBox, matches } from "../components/Ui.jsx";

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
      <select aria-label="New status" value={value} onChange={(e) => setValue(e.target.value)}>
        {statuses.map((s) => <option key={s}>{s}</option>)}
      </select>{" "}
      <button className="btn small" type="submit">Save</button>
    </form>
  );
}

function AssignmentForm({ row, assignees, onChanged }) {
  const { setFlash } = useAuth();
  const [value, setValue] = useState(row.assigned_admin_email || "");
  useEffect(() => setValue(row.assigned_admin_email || ""), [row.assigned_admin_email]);
  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/reports/${row.id}/assign`, {
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
      <select aria-label={`Assign report ${row.id} to administrator`} value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">Unassigned</option>
        {assignees.map((email) => <option key={email} value={email}>{email}</option>)}
      </select>
      <button className="btn small" type="submit" disabled={value === (row.assigned_admin_email || "")}>Assign</button>
    </form>
  );
}

/** "2026-10-29 11:26:02" -> date on one line, time (smaller) below it. */
function DateCell({ value }) {
  const [date, ...time] = String(value || "").split(" ");
  return <span>{date}{time.length > 0 && <><br /><small className="muted">{time.join(" ")}</small></>}</span>;
}

function RecordCard({ row, columns, kind, spec, statuses, onChanged }) {
  const nameKey = ["reporter_name", "name", "requester_name"].find((key) => row[key] !== undefined);
  const emailKey = ["reporter_email", "email", "requester_email"].find((key) => row[key] !== undefined);
  const details = columns.filter(([, key]) => !["id", "created_at", "status", "assigned_admin_email",
    nameKey, emailKey, "submitter_role"].includes(key) && row[key]);
  return <article className="record-card">
    <div className="record-card-head">
      <div><strong>#{row.id}</strong><DateCell value={row.created_at} /></div>
      <span className={"badge s-" + slug(row.status)}>{row.status}</span>
    </div>
    <div className="record-card-person">
      <strong>{row[nameKey] || "Unknown sender"}</strong>
      {row[emailKey] && <a href={`mailto:${row[emailKey]}`}>{row[emailKey]}</a>}
      {row.submitter_role && <small>{row.submitter_role}</small>}
    </div>
    <div className="record-card-fields">
      {details.map(([label, key]) => <div className={LONG_TEXT.includes(key) ? "record-card-long" : ""} key={key}>
        <b>{label}</b>
        {key === "sentiment" ? <span className={"badge sent-" + slug(row[key])}>{row[key]}</span> : <span>{row[key]}</span>}
      </div>)}
    </div>
    <div className="record-card-links">
      {row.image_filename && <ReportPhoto filename={row.image_filename} />}
      {spec.pdf && <a href={`/api/pdf/${kind}/${row.id}`} target="_blank" rel="noopener noreferrer">Download PDF</a>}
    </div>
    <div className="record-card-footer">
      <label>Update status</label>
      <StatusForm kind={kind} row={row} statuses={statuses} onChanged={onChanged} />
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
function PhotoDetail({ row, onChanged }) {
  const { setFlash } = useAuth();
  const ai = row.ai || {};
  const [choice, setChoice] = useState(row.verification || "Unverified");
  const [note, setNote] = useState(row.verification_note || "");
  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/reports/${row.id}/verify`, { method: "POST", json: { verification: choice, note } });
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
        <form className="verify-form" onSubmit={save}>
          <label htmlFor={`v-${row.id}`}>Your verdict on NEMSAI's findings</label>
          <select id={`v-${row.id}`} value={choice} onChange={(e) => setChoice(e.target.value)}>
            <option>Unverified</option><option>Confirmed</option><option>Not confirmed</option>
          </select>
          <input type="text" maxLength={500} placeholder="Note (optional)" aria-label="Verification note" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn small" type="submit">Save verdict</button>
          {row.verified_by && <span className="muted">Last set by {row.verified_by}</span>}
        </form>
      </div>
    </div>
  );
}

/** Concerns / Reports / Feedback / Reservations for admins. */
export default function AdminList({ kind }) {
  const [params] = useSearchParams();
  const status = params.get("status") || "";
  const sentiment = params.get("sentiment") || "";
  const urgent = params.get("urgent") || "";
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);                 // id of the report whose details are shown
  const [q, setQ] = useState("");                         // search box

  const load = useCallback(() => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (sentiment) q.set("sentiment", sentiment);
    if (urgent) q.set("urgent", urgent);
    api(`/api/admin/records/${kind}` + (q.toString() ? `?${q}` : "")).then(setData).catch(() => {});
  }, [kind, status, sentiment, urgent]);
  useEffect(() => { setData(null); setQ(""); load(); }, [load]);
  useEffect(() => { if (data) document.title = `${data.spec.title} | NEMSU`; }, [data]);

  if (!data) return <Loading wide={1400} />;
  const { spec, rows: allRows, columns, statuses, current } = data;
  const assignees = data.assignees || [];
  const rows = allRows.filter((r) => matches(r, q));
  const base = `/admin/${kind}`;
  const withSent = (s) => (sentiment ? `&sentiment=${sentiment}` : "");

  return (
    <div className="page" style={{ maxWidth: 1400 }}>
      <h2 className="page-title">{spec.title}</h2>
      <div className="filters">
        <Link to={base} className={!current ? "on" : ""}>All</Link>
        {statuses.map((s) => <Link key={s} to={`${base}?status=${encodeURIComponent(s)}${withSent(s)}`} className={current === s ? "on" : ""}>{s}</Link>)}
      </div>
      {kind === "reports" && (
        <div className="filters" aria-label="Filter by priority">
          <span className="filter-label">Priority:</span>
          <Link to={base} className={!urgent ? "on" : ""}>All reports</Link>
          <Link to={`${base}?urgent=1`} className={urgent ? "on" : ""}>Possible hazards only</Link>
        </div>
      )}
      {data.has_sentiment && (
        <div className="filters" aria-label="Filter by sentiment">
          <span className="filter-label">Sentiment:</span>
          <Link to={current ? `${base}?status=${encodeURIComponent(current)}` : base} className={!sentiment ? "on" : ""}>Any</Link>
          {["Negative", "Mixed", "Neutral", "Positive"].map((s) => (
            <Link key={s} to={`${base}?${current ? `status=${encodeURIComponent(current)}&` : ""}sentiment=${s}`}
                  className={sentiment === s ? "on" : ""}>{s}</Link>
          ))}
        </div>
      )}
      {allRows.length > 0 && (
        <SearchBox value={q} onChange={setQ} shown={rows.length} total={allRows.length}
                   placeholder={`Search ${spec.title.toLowerCase()}...`} />
      )}
      {rows.length ? kind === "reports" ? (
        <section className="report-card-list" aria-label="Campus reports">
          {rows.map((r) => <article className={`report-card${r.urgent ? " is-urgent" : ""}`} key={r.id}>
            <div className="report-card-top">
              <div><span className="report-number">Report #{r.id}</span><DateCell value={r.created_at} /></div>
              <div className="report-card-badges"><span className={"badge s-" + slug(r.status)}>{r.status}</span><Flags r={r} />
                {r.ai?.status === "analyzed" && <span className={`badge severity-${r.ai.severity || "unclear"}`}>NEMSAI severity: {(r.ai.severity || "unclear").toUpperCase()}</span>}
              </div>
            </div>
            <div className="report-card-main">
              <section>
                <h3>{r.report_type || "Campus report"}</h3>
                <p className="report-card-description">{r.description || "No description provided."}</p>
                <div className="report-card-meta">
                  <span><b>Location</b>{r.location || "Not provided"}</span>
                  {r.area && <span><b>Area</b>{r.area}</span>}
                  {r.room && <span><b>Room</b>{r.room}</span>}
                  {r.noticed_when && <span><b>When noticed</b>{r.noticed_when}</span>}
                  {r.sentiment && <span><b>Sentiment</b><span className={"badge sent-" + slug(r.sentiment)}>{r.sentiment}</span></span>}
                </div>
              </section>
              <aside className="report-card-reporter">
                <b>Submitted by</b><strong>{r.reporter_name || "Unknown"}</strong>
                {r.reporter_email && <a href={`mailto:${r.reporter_email}`}>{r.reporter_email}</a>}
                <small>{r.submitter_role || ""}</small>
                {r.image_filename && <ReportPhoto filename={r.image_filename} />}
                {spec.pdf && <a href={`/api/pdf/${kind}/${r.id}`} target="_blank" rel="noopener noreferrer">Download PDF</a>}
              </aside>
            </div>
            <div className="report-card-actions">
              <div><label>Assigned administrator</label><AssignmentForm row={r} assignees={assignees} onChanged={load} /></div>
              <div><label>Update status</label><StatusForm kind={kind} row={r} statuses={statuses} onChanged={load} /></div>
              {r.source === "photo" && <button type="button" className="btn small ghost" aria-expanded={open === r.id}
                onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide NEMSAI details" : "View NEMSAI details"}</button>}
            </div>
            {open === r.id && <div className="report-card-detail"><PhotoDetail row={r} onChanged={load} /></div>}
          </article>)}
        </section>
      ) : (
        <section className="record-card-list" aria-label={spec.title}>
          {rows.map((row) => <RecordCard key={row.id} row={row} columns={columns} kind={kind}
            spec={spec} statuses={statuses} onChanged={load} />)}
        </section>
      ) : q && allRows.length ? (
        <EmptyState title="No matches">Nothing matches "{q}". Try fewer or different words.</EmptyState>
      ) : (
        <EmptyState title="Nothing here">
          Nothing here{urgent ? " marked as a possible hazard" : ""}{current ? " with status " + current : ""}{sentiment ? " with " + sentiment.toLowerCase() + " sentiment" : ""}.
        </EmptyState>
      )}
    </div>
  );
}
