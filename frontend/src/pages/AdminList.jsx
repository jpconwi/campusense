import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, slug } from "../api.js";
import { useAuth } from "../auth.jsx";

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

/** Concerns / Reports / Feedback / Reservations for admins. */
export default function AdminList({ kind }) {
  const [params] = useSearchParams();
  const status = params.get("status") || "";
  const sentiment = params.get("sentiment") || "";
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (sentiment) q.set("sentiment", sentiment);
    api(`/api/admin/records/${kind}` + (q.toString() ? `?${q}` : "")).then(setData).catch(() => {});
  }, [kind, status, sentiment]);
  useEffect(() => { setData(null); load(); }, [load]);
  useEffect(() => { if (data) document.title = `${data.spec.title} | NEMSU`; }, [data]);

  if (!data) return <div className="page" style={{ maxWidth: 1400 }} />;
  const { spec, rows, columns, statuses, current } = data;
  const base = `/admin/${kind}`;
  const withSent = (s) => (sentiment ? `&sentiment=${sentiment}` : "");

  return (
    <div className="page" style={{ maxWidth: 1400 }}>
      <h2 className="page-title">{spec.title}</h2>
      <div className="filters">
        <Link to={base} className={!current ? "on" : ""}>All</Link>
        {statuses.map((s) => <Link key={s} to={`${base}?status=${encodeURIComponent(s)}${withSent(s)}`} className={current === s ? "on" : ""}>{s}</Link>)}
      </div>
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
      {rows.length ? (
        <div className="table-wrap"><table>
          <thead><tr>
            {columns.map(([header]) => <th key={header}>{header}</th>)}
            {spec.image && <th>Photo</th>}{spec.pdf && <th>PDF</th>}<th>Change status</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                {columns.map(([header, key]) => key === "status"
                  ? <td key={key}><span className={"badge s-" + slug(r[key])}>{r[key]}</span></td>
                  : key === "sentiment"
                  ? <td key={key}>{r.sentiment && <span className={"badge sent-" + slug(r.sentiment)} title={`Score ${r.sentiment_score} (-100 to 100)`}>{r.sentiment}</span>}</td>
                  : <td key={key} className={LONG_TEXT.includes(key) ? "desc" : undefined}>{r[key] || ""}</td>)}
                {spec.image && <td>{r.image_filename && <a href={`/api/uploads/${r.image_filename}`} target="_blank" rel="noopener noreferrer">View</a>}</td>}
                {spec.pdf && <td><a href={`/api/pdf/${kind}/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>}
                <td><StatusForm kind={kind} row={r} statuses={statuses} onChanged={load} /></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : <p className="empty">Nothing here{current ? " with status " + current : ""}{sentiment ? " with " + sentiment.toLowerCase() + " sentiment" : ""}.</p>}
    </div>
  );
}
