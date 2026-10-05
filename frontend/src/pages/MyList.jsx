import { useCallback, useEffect, useState } from "react";
import { api, slug } from "../api.js";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";

const LONG_TEXT = ["description", "message", "purpose", "additional_info"];

/** My Concerns / My Reports / Feedback / Reservations (one page, four kinds). */
export default function MyList({ kind }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(() => {
    api(`/api/me/records/${kind}`).then(setData).catch((e) => setError(e.message));
  }, [kind]);

  useEffect(() => { setData(null); setOpen(false); setResult(null); load(); }, [load]);
  useEffect(() => { if (data) document.title = `${data.spec.title} | NEMSU`; }, [data]);

  if (error) return <div className="page"><p className="empty">{error}</p></div>;
  if (!data) return <div className="page" />;
  const { spec, rows, columns } = data;

  function done(res) {
    setResult(res);
    setTimeout(() => { load(); setOpen(false); setResult(null); }, 1600);   // refresh the list
  }

  return (
    <div className="page">
      <h2 className="page-title">{spec.title}</h2>
      <p className="page-intro">{spec.intro}</p>

      <p><button className="btn" type="button" onClick={() => setOpen((o) => !o)}>
        {open ? "Close form" : `New ${spec.form}`}
      </button></p>
      {open && (
        <div className="card" style={{ marginTop: 14 }}>
          <RecordForm kind={spec.form} onSuccess={done} />
          {result && <div style={{ marginTop: 12 }}><SuccessCard result={result} /><p className="desc">Reloading your list...</p></div>}
        </div>
      )}

      <h3 style={{ fontFamily: "var(--serif)", color: "var(--blue-deep)", margin: "20px 0 8px" }}>Your submissions</h3>
      {rows.length ? (
        <div className="table-wrap"><table>
          <thead><tr>
            {columns.map(([header]) => <th key={header}>{header}</th>)}
            {spec.image && <th>Photo</th>}
            {data.pdf && <th>PDF</th>}
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                {columns.map(([header, key]) => key === "status"
                  ? <td key={key}><span className={"badge s-" + slug(r[key])}>{r[key]}</span></td>
                  : <td key={key} className={LONG_TEXT.includes(key) ? "desc" : undefined}>{r[key] || ""}</td>)}
                {spec.image && <td>{r.image_filename && <a href={`/api/uploads/${r.image_filename}`} target="_blank" rel="noopener noreferrer">View</a>}</td>}
                {data.pdf && <td><a href={`/api/pdf/${kind}/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>}
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : <p className="empty">You have not submitted anything here yet.</p>}
    </div>
  );
}
