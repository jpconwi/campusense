import { useCallback, useEffect, useState } from "react";
import { api, padId, slug } from "../api.js";
import { useAuth } from "../auth.jsx";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";

export default function Faculty() {
  const { setFlash } = useAuth();
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(() => { api("/api/me/faculty").then((d) => setRows(d.rows)).catch(() => setRows([])); }, []);
  useEffect(() => { document.title = "Faculty Availability | NEMSU"; load(); }, [load]);

  async function markAvailable() {
    try {
      await api("/api/faculty/available", { method: "POST" });
      load();
    } catch {
      setFlash({ text: "Could not update your status.", kind: "error" });
    }
  }

  function done(res) {
    setResult(res);
    setTimeout(() => { load(); setOpen(false); setResult(null); }, 1600);
  }

  return (
    <div className="page">
      <h2 className="page-title">Faculty Availability</h2>
      <p className="page-intro">Report when you cannot come to school. Students asking the AI will see your recorded status and expected return date (not your reason).</p>
      <p>
        <button className="btn" type="button" onClick={() => setOpen((o) => !o)}>{open ? "Close form" : "New absence report"}</button>{" "}
        <button className="btn ghost" type="button" onClick={markAvailable}>I am back - mark me available</button>
      </p>
      {open && (
        <div className="card" style={{ marginTop: 14 }}>
          <RecordForm kind="faculty" onSuccess={done} />
          {result && <div style={{ marginTop: 12 }}><SuccessCard result={result} /></div>}
        </div>
      )}

      <h3 style={{ fontFamily: "var(--serif)", color: "var(--blue-deep)", margin: "20px 0 8px" }}>Your reports</h3>
      {rows && rows.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>ID</th><th>Reason</th><th>Absence date</th><th>Expected return</th><th>Submitted</th><th>Status</th><th>PDF</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{padId(r.id)}</td><td className="desc">{r.reason}</td><td>{r.start_date}</td><td>{r.expected_return}</td>
                <td>{r.submitted_at}</td><td><span className={"badge s-" + slug(r.status)}>{r.status}</span></td>
                <td><a href={`/api/pdf/faculty/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : rows && <p className="empty">No faculty reports yet.</p>}
    </div>
  );
}
