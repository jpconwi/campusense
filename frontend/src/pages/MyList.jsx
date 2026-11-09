import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiUrl, slug } from "../api.js";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";
import { EmptyState, Loading, SearchBox, matches } from "../components/Ui.jsx";

const LONG_TEXT = ["description", "message", "purpose", "additional_info", "admin_response"];

function WorkflowProgress({ row }) {
  const status = row.status || "Pending";
  const normalizedStatus = status.trim().toLowerCase();
  if (normalizedStatus === "rejected") return (
    <div className="user-report-progress is-rejected" aria-label="Report rejected">
      <span className="user-report-track" aria-hidden="true" />
      <span className="user-report-step rejected"><span className="user-report-node">×</span><strong>Rejected</strong></span>
      {row.admin_feedback && <p className="user-report-rejection-note">{row.admin_feedback}</p>}
    </div>
  );
  const isResolved = normalizedStatus === "resolved";
  const current = isResolved ? 3 : normalizedStatus === "in progress" ? 2 : normalizedStatus === "under review" ? 1 : 0;
  const steps = [
    "Pending",
    "Under review",
    "In progress",
    "Resolved",
  ];
  return (
    <div className="user-report-progress" aria-label={`Report status: ${status}`}>
      <span className="user-report-track" aria-hidden="true">
        <span style={{ width: `${(current / (steps.length - 1)) * 100}%` }} />
      </span>
      <ol>{steps.map((step, index) => {
        const complete = index < current || (isResolved && index === current);
        return <li key={step} className={complete ? "complete" : index === current ? "current" : ""}>
          <span className="user-report-node" aria-hidden="true">{complete ? "✓" : ""}</span>
          <span>{step}</span>
        </li>;
      })}</ol>
      {row.admin_feedback && <p className="user-report-update"><strong>Admin update:</strong> {row.admin_feedback}</p>}
    </div>
  );
}

function UserReportDetails({ row, onClose }) {
  const isConcern = row.record_kind === "concern";
  const kind = isConcern ? "concerns" : "reports";
  const reference = `${isConcern ? "NEMSAI-C-" : "NEMSAI-"}${String(row.id).padStart(4, "0")}`;
  const photoUrl = row.image_filename ? apiUrl(`/api/uploads/${encodeURIComponent(row.image_filename)}`) : "";

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  return (
    <div className="user-report-dialog-backdrop" onClick={onClose}>
      <section className="user-report-dialog" role="dialog" aria-modal="true"
               aria-labelledby="user-report-dialog-title" onClick={(event) => event.stopPropagation()}>
        <header className="user-report-dialog-head">
          <div><span>Report details</span><h3 id="user-report-dialog-title">{reference}</h3></div>
          <button className="user-report-dialog-close" type="button" aria-label="Close report details" onClick={onClose}>×</button>
        </header>
        <div className="user-report-dialog-body">
          <div className="user-report-detail-grid">
            <div><span>Type</span><strong>{row.record_category || (isConcern ? "Concern" : "Problem")}</strong></div>
            <div><span>Status</span><strong><span className={`badge s-${slug(row.status)}`}>{row.status || "Pending"}</span></strong></div>
            <div><span>Submitted</span><strong>{row.created_at || "Not available"}</strong></div>
            <div><span>Location</span><strong>{row.location || "Not provided"}</strong></div>
            {row.room && <div><span>Room</span><strong>{row.room}</strong></div>}
            {row.area && <div><span>Area</span><strong>{row.area}</strong></div>}
          </div>
          <section className="user-report-detail-section">
            <h4>Your description</h4>
            <p>{row.description || row.message || "No description provided."}</p>
          </section>
          {row.admin_feedback && <section className={`user-report-detail-section ${row.status === "Rejected" ? "is-rejected" : "is-update"}`}>
            <h4>{row.status === "Rejected" ? "Reason from the administrator" : "Admin update"}</h4>
            <p>{row.admin_feedback}</p>
          </section>}
          {photoUrl && <section className="user-report-detail-section">
            <h4>Attached photo</h4>
            <a href={photoUrl} target="_blank" rel="noopener noreferrer">
              <img className="user-report-detail-photo" src={photoUrl} alt="Photo attached to your report" />
              <span className="muted">Open full-size photo</span>
            </a>
          </section>}
          <div className="user-report-dialog-actions">
            <a className="btn small ghost" href={apiUrl(`/api/pdf/${kind}/${row.id}`)} target="_blank" rel="noopener noreferrer">Download PDF</a>
            <button className="btn small" type="button" onClick={onClose}>Close details</button>
          </div>
        </div>
      </section>
    </div>
  );
}

/** My Concerns / My Reports / Feedback / Reservations (one page, four kinds). */
export default function MyList({ kind, hideForm = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState(null);
  const [q, setQ] = useState("");
  const [recordFilter, setRecordFilter] = useState("all");
  const [formKind, setFormKind] = useState("report");
  const [selectedRecord, setSelectedRecord] = useState(null);
  const combined = kind === "reports";
  const pageTitle = kind === "feedback" ? (hideForm ? "My Feedback" : "Feedback & Suggestions") : "";

  const load = useCallback(() => {
    if (combined) {
      Promise.all([api("/api/me/records/concerns"), api("/api/me/records/reports")])
        .then(([concerns, reports]) => {
          const tag = (rows, type) => rows.map((row) => ({ ...row, record_kind: type, record_category: row.concern_type || row.report_type || "" }));
          const rows = [...tag(concerns.rows, "concern"), ...tag(reports.rows, "problem")]
            .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
          setData({ spec: { title: "My Reports", intro: "Submit and track campus concerns or problems." }, rows,
            columns: [["ID", "id"], ["Submitted", "created_at"], ["Type", "record_category"], ["Location", "location"], ["Description", "description"], ["Status", "status"]], image: true, pdf: true });
        }).catch((e) => setError(e.message));
    } else api(`/api/me/records/${kind}`).then(setData).catch((e) => setError(e.message));
  }, [kind, combined]);

  useEffect(() => { setData(null); setOpen(false); setResult(null); setQ(""); load(); }, [load]);
  useEffect(() => { if (data) document.title = `${pageTitle || data.spec.title} | NEMSU`; }, [data, pageTitle]);
  useEffect(() => {
    if (!combined) return undefined;
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    const timer = window.setInterval(load, 30_000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [combined, load]);

  if (error) return <div className="page"><p className="empty">{error}</p></div>;
  if (!data) return <Loading variant="form" />;
  const { spec, rows: allRows, columns } = data;
  const rows = allRows.filter((r) => matches(r, q) && (!combined || recordFilter === "all" || r.record_kind === recordFilter));

  function done(res) {
    setResult(res);
    setTimeout(() => { load(); setOpen(false); setResult(null); }, 1600);   // refresh the list
  }

  return (
    <div className="page">
      <h2 className="page-title">{pageTitle || spec.title}</h2>
      <p className="page-intro">{kind === "feedback" && !hideForm
        ? "Share campus feedback, suggest improvements, or report an issue with NEMSAI or the app."
        : spec.intro}{combined && " Status updates refresh automatically."}</p>

      {!hideForm && <p><button className="btn" type="button" onClick={() => setOpen((o) => !o)}>
        {open ? "Close form" : combined ? "New report" : kind === "feedback" ? "New feedback or suggestion" : `New ${spec.form}`}
      </button></p>}
      {!hideForm && open && (
        <div className="card" style={{ marginTop: 14 }}>
          {combined && <div style={{ maxWidth: 420, marginBottom: 14 }}>
            <label htmlFor="record-kind">Submit as</label>
            <select id="record-kind" value={formKind} onChange={(e) => setFormKind(e.target.value)}>
              <option value="concern">Concern &mdash; facility or service problem</option>
              <option value="report">Problem &mdash; incident or safety/security issue</option>
            </select>
          </div>}
          <RecordForm key={combined ? formKind : kind} kind={combined ? formKind : spec.form} onSuccess={done} />
          {result && <div style={{ marginTop: 12 }}><SuccessCard result={result} /><p className="desc">Reloading your list...</p></div>}
        </div>
      )}

      <h3 style={{ fontFamily: "var(--serif)", color: "var(--blue-deep)", margin: "20px 0 8px" }}>Your submissions</h3>
      {combined && <div className="filter-row" style={{ marginBottom: 12 }}>
        <label htmlFor="record-filter">Filter by type</label>
        <select id="record-filter" value={recordFilter} onChange={(e) => setRecordFilter(e.target.value)}>
          <option value="all">All records</option><option value="concern">Concerns</option><option value="problem">Problems</option>
        </select>
      </div>}
      {(allRows.length > 4 || q) && <SearchBox value={q} onChange={setQ} shown={rows.length} total={allRows.length} placeholder="Search your submissions..." />}
      {rows.length ? combined ? (
        <section className="user-report-list" aria-label="Your reports">
          {rows.map((r) => {
            const isConcern = r.record_kind === "concern";
            const reference = `${isConcern ? "NEMSAI-C-" : "NEMSAI-"}${String(r.id).padStart(4, "0")}`;
            return (
              <article className="user-report-card" key={`${r.record_kind}-${r.id}`}>
                <header className="user-report-card-head">
                  <div>
                    <span className="user-report-reference">{reference}</span>
                    <span className={`badge ${isConcern ? "s-pending" : "s-in-progress"}`}>{isConcern ? "Concern" : "Problem"}</span>
                  </div>
                  <span className={"badge s-" + slug(r.status)}>{r.status || "Pending"}</span>
                </header>
                <div className="user-report-summary">
                  <strong>{r.record_category || (isConcern ? "Concern" : "Problem")}</strong>
                  <span>{r.location || "Location not provided"}</span>
                  <p>{r.description || "No description provided."}</p>
                </div>
                <WorkflowProgress row={r} />
                <footer className="user-report-card-foot">
                  <span>{r.created_at || ""}</span>
                  <button className="btn small ghost" type="button" onClick={() => setSelectedRecord(r)}>View details</button>
                </footer>
              </article>
            );
          })}
        </section>
      ) : (
        <div className="table-wrap"><table className="data-table">
          <thead><tr>
            {combined && <th>Record type</th>}
            {columns.map(([header]) => <th key={header}>{header}</th>)}
            {(combined ? data.image : spec.image) && <th>Photo</th>}
            {data.pdf && <th>PDF</th>}
            {combined && <th>Progress and updates</th>}
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={combined ? `${r.record_kind}-${r.id}` : r.id}>
                {combined && <td data-label="Record type"><span className={`badge ${r.record_kind === "concern" ? "s-pending" : "s-in-progress"}`}>{r.record_kind === "concern" ? "Concern" : "Problem"}</span></td>}
                {columns.map(([header, key]) => key === "status"
                  ? <td key={key} data-label={header}><span className={"badge s-" + slug(r[key])}>{r[key]}</span></td>
                  : combined && key === "id"
                    ? <td key={key} data-label={header}>{r.record_kind === "concern" ? `NEMSAI-C-${String(r[key]).padStart(4, "0")}` : `NEMSAI-${String(r[key]).padStart(4, "0")}`}</td>
                  : <td key={key} data-label={header} className={LONG_TEXT.includes(key) ? "desc" : undefined}>{r[key] || ""}</td>)}
                {(combined ? data.image : spec.image) && <td data-label="Photo">{r.image_filename && <a href={`/api/uploads/${r.image_filename}`} target="_blank" rel="noopener noreferrer">View</a>}</td>}
                {data.pdf && <td data-label="PDF"><a href={`/api/pdf/${combined ? r.record_kind === "concern" ? "concerns" : "reports" : kind}/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>}
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : (q || (combined && recordFilter !== "all")) && allRows.length ? (
        <EmptyState title="No matches">Nothing matches "{q}".</EmptyState>
      ) : (
        <EmptyState title="Nothing yet"
                    action={hideForm ? <Link className="btn" to="/feedback">Send feedback</Link>
                      : <button className="btn" type="button" onClick={() => setOpen(true)}>{combined ? "New report" : `New ${spec.form}`}</button>}>
          You have not submitted anything here yet.
        </EmptyState>
      )}
      {selectedRecord && <UserReportDetails row={selectedRecord} onClose={() => setSelectedRecord(null)} />}
    </div>
  );
}
