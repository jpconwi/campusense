import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, slug } from "../api.js";
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

/** "2026-10-29 11:26:02" -> date on one line, time (smaller) below it. */
function DateCell({ value }) {
  const [date, ...time] = String(value || "").split(" ");
  return <span>{date}{time.length > 0 && <><br /><small className="muted">{time.join(" ")}</small></>}</span>;
}

const CONF = { high: "fairly sure", medium: "somewhat sure", low: "not sure" };
const CHECK = { supports: "matches the photo", partly: "partly matches the photo",
                contradicts: "does not match the photo", cannot_tell: "cannot tell from the photo" };

function Flags({ r }) {
  return (
    <>
      {r.urgent && <span className="badge urgent" title="Possible safety hazard, not confirmed">Possible hazard</span>}{" "}
      {r.source === "photo" && <span className="badge ai-guess" title="Sent with a photo and checked by AI">Photo + AI</span>}{" "}
      {r.source === "photo" && r.verification && r.verification !== "Unverified" &&
        <span className={"badge ver-" + slug(r.verification)}>{r.verification}</span>}
    </>
  );
}

/** Everything about one photo report: photo, student's words, AI notes, verification. */
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
      {row.image_filename && <a href={`/api/uploads/${row.image_filename}`} target="_blank" rel="noopener noreferrer">
        <img src={`/api/uploads/${row.image_filename}`} alt="Photo from the student" /></a>}
      <div className="photo-detail-text">
        {row.urgent && <div className="urgent-note"><strong>Possible safety hazard (not confirmed).</strong> {ai.urgent_reason}</div>}
        <h4>Student's report</h4>
        <p>{row.description}</p>
        <p className="muted">Location: {row.location}{row.noticed_when ? ` · Noticed: ${row.noticed_when}` : ""}{row.observed_cause ? ` · Cause mentioned: ${row.observed_cause}` : ""}</p>
        <h4>AI analysis <span className="badge ai-guess">unverified</span></h4>
        {ai.status === "unavailable" || !row.ai ? <p>The AI check was not available. Please review the photo by hand.</p> : (
          <>
            <p><strong>{ai.issue_title || "No clear problem named"}</strong> · category {row.report_type} · {CONF[ai.confidence] || "not sure"}</p>
            {ai.observations && ai.observations.length > 0 && <ul>{ai.observations.map((o, i) => <li key={i}>{o}</li>)}</ul>}
            {row.description && !row.description.startsWith("(The student did not") &&
              <p className="muted">Description {CHECK[ai.description_check] || "was not compared"}. {ai.check_explanation}</p>}
          </>
        )}
        <form className="verify-form" onSubmit={save}>
          <label htmlFor={`v-${row.id}`}>Your verdict on the AI's findings</label>
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

  if (!data) return <Loading />;
  const { spec, rows: allRows, columns, statuses, current } = data;
  const rows = allRows.filter((r) => matches(r, q));
  const showImage = !!spec.image && allRows.some((r) => r.image_filename);       // no empty Photo column
  // the status badge sits with the status form; email + "From" are shown small under the name
  const nameCol = columns.find(([h]) => h === "Name");
  const emailKey = (columns.find(([h]) => h === "Email") || [])[1];
  const fromKey = (columns.find(([h]) => h === "From") || [])[1];
  const mergeWho = !!(nameCol && emailKey);
  const shownColumns = columns.filter(([h, key]) => key !== "status" && !(mergeWho && (h === "Email" || h === "From")));
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
      {rows.length ? (
        <div className="table-wrap"><table className="data-table">
          <thead><tr>
            {shownColumns.map(([header]) => <th key={header}>{header}</th>)}
            {showImage && <th>Photo</th>}{spec.pdf && <th>PDF</th>}<th>Status</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (<Fragment key={r.id}>
              <tr className={r.urgent ? "row-urgent" : undefined}>
                {shownColumns.map(([header, key]) => key === "flags"
                  ? <td key={key} data-label={header}><Flags r={r} /></td>
                  : key === "sentiment"
                  ? <td key={key} data-label={header}>{r.sentiment && <span className={"badge sent-" + slug(r.sentiment)} title={`Score ${r.sentiment_score} (-100 to 100)`}>{r.sentiment}</span>}</td>
                  : mergeWho && header === "Name"
                  ? <td key={key} data-label={header}><span><strong>{r[key]}</strong><br />
                      <small className="muted">{[r[emailKey], fromKey && r[fromKey]].filter(Boolean).join(" · ")}</small></span></td>
                  : key === "created_at"
                  ? <td key={key} data-label={header} className="when"><DateCell value={r[key]} /></td>
                  : <td key={key} data-label={header} className={LONG_TEXT.includes(key) ? "desc" : undefined}>{r[key] || ""}</td>)}
                {showImage && <td data-label="Photo">{r.image_filename && <a href={`/api/uploads/${r.image_filename}`} target="_blank" rel="noopener noreferrer">View</a>}</td>}
                {spec.pdf && <td data-label="PDF"><a href={`/api/pdf/${kind}/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>}
                <td data-label="Status" className="status-cell">
                  <span className={"badge s-" + slug(r.status)}>{r.status}</span>
                  <StatusForm kind={kind} row={r} statuses={statuses} onChanged={load} />
                  {r.source === "photo" && (
                    <button type="button" className="btn small ghost" style={{ marginTop: 6 }} aria-expanded={open === r.id}
                            onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide details" : "AI details"}</button>
                  )}
                </td>
              </tr>
              {open === r.id && (
                <tr className="detail-row"><td colSpan={shownColumns.length + (showImage ? 1 : 0) + (spec.pdf ? 1 : 0) + 1}>
                  <PhotoDetail row={r} onChanged={load} />
                </td></tr>
              )}
            </Fragment>))}
          </tbody>
        </table></div>
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
