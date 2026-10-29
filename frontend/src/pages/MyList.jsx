import { useCallback, useEffect, useState } from "react";
import { api, slug } from "../api.js";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";
import { EmptyState, Loading, SearchBox, matches } from "../components/Ui.jsx";

const LONG_TEXT = ["description", "message", "purpose", "additional_info"];

/** My Concerns / My Reports / Feedback / Reservations (one page, four kinds). */
export default function MyList({ kind }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState(null);
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    api(`/api/me/records/${kind}`).then(setData).catch((e) => setError(e.message));
  }, [kind]);

  useEffect(() => { setData(null); setOpen(false); setResult(null); setQ(""); load(); }, [load]);
  useEffect(() => { if (data) document.title = `${data.spec.title} | NEMSU`; }, [data]);

  if (error) return <div className="page"><p className="empty">{error}</p></div>;
  if (!data) return <Loading />;
  const { spec, rows: allRows, columns } = data;
  const rows = allRows.filter((r) => matches(r, q));

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
      {allRows.length > 4 && <SearchBox value={q} onChange={setQ} shown={rows.length} total={allRows.length} placeholder="Search your submissions..." />}
      {rows.length ? (
        <div className="table-wrap"><table className="data-table">
          <thead><tr>
            {columns.map(([header]) => <th key={header}>{header}</th>)}
            {spec.image && <th>Photo</th>}
            {data.pdf && <th>PDF</th>}
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                {columns.map(([header, key]) => key === "status"
                  ? <td key={key} data-label={header}><span className={"badge s-" + slug(r[key])}>{r[key]}</span></td>
                  : <td key={key} data-label={header} className={LONG_TEXT.includes(key) ? "desc" : undefined}>{r[key] || ""}</td>)}
                {spec.image && <td data-label="Photo">{r.image_filename && <a href={`/api/uploads/${r.image_filename}`} target="_blank" rel="noopener noreferrer">View</a>}</td>}
                {data.pdf && <td data-label="PDF"><a href={`/api/pdf/${kind}/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>}
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : q && allRows.length ? (
        <EmptyState title="No matches">Nothing matches "{q}".</EmptyState>
      ) : (
        <EmptyState title="Nothing yet"
                    action={<button className="btn" type="button" onClick={() => setOpen(true)}>{`New ${spec.form}`}</button>}>
          You have not submitted anything here yet.
        </EmptyState>
      )}
    </div>
  );
}
