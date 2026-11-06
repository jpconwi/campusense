import { useCallback, useEffect, useState } from "react";
import { api, slug } from "../api.js";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";
import { EmptyState, Loading, SearchBox, matches } from "../components/Ui.jsx";

const LONG_TEXT = ["description", "message", "purpose", "additional_info"];

function WorkflowProgress({ row }) {
  const status = row.status || "Pending";
  if (status === "Rejected") return <div className="workflow-rejected"><strong>Report not approved</strong><span>Please contact the report manager if you need more information.</span>
    {row.admin_feedback && <p>{row.admin_feedback}</p>}</div>;
  let current = status === "Resolved" ? 4 : status === "In Progress" ? 3 : status === "Under Review" ? 1 : 0;
  if (row.assigned_admin_email) current = Math.max(current, 2);
  const steps = [
    "Report submitted",
    "Admin reviewed",
    row.assigned_admin_email ? `Forwarded to ${row.assigned_admin_email}` : "Waiting for department assignment",
    "Work in progress",
    "Problem repaired",
  ];
  return <div className="workflow-progress">
    <ol>{steps.map((step, index) => {
      const complete = index < current && (index !== 2 || Boolean(row.assigned_admin_email));
      return <li key={step} className={complete ? "complete" : index === current ? "current" : ""}>
      <span className="workflow-dot" aria-hidden="true" />{step}
    </li>;
    })}</ol>
    {row.admin_feedback && <div className="workflow-update"><strong>Admin update</strong><p>{row.admin_feedback}</p></div>}
  </div>;
}

/** My Concerns / My Reports / Feedback / Reservations (one page, four kinds). */
export default function MyList({ kind }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState(null);
  const [q, setQ] = useState("");
  const [recordFilter, setRecordFilter] = useState("all");
  const [formKind, setFormKind] = useState("report");
  const combined = kind === "reports";

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
  useEffect(() => { if (data) document.title = `${data.spec.title} | NEMSU`; }, [data]);

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
      <h2 className="page-title">{spec.title}</h2>
      <p className="page-intro">{spec.intro}</p>

      <p><button className="btn" type="button" onClick={() => setOpen((o) => !o)}>
        {open ? "Close form" : combined ? "New report" : `New ${spec.form}`}
      </button></p>
      {open && (
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
      {rows.length ? (
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
                {combined && <td data-label="Progress and updates"><WorkflowProgress row={r} /></td>}
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : (q || (combined && recordFilter !== "all")) && allRows.length ? (
        <EmptyState title="No matches">Nothing matches "{q}".</EmptyState>
      ) : (
        <EmptyState title="Nothing yet"
                    action={<button className="btn" type="button" onClick={() => setOpen(true)}>{combined ? "New report" : `New ${spec.form}`}</button>}>
          You have not submitted anything here yet.
        </EmptyState>
      )}
    </div>
  );
}
