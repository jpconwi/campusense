import { useCallback, useEffect, useState } from "react";
import { api, padId, slug } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading } from "../components/Ui.jsx";

export default function AdminFaculty() {
  const { setFlash } = useAuth();
  const [rows, setRows] = useState(null);
  const load = useCallback(() => { api("/api/admin/faculty").then((d) => setRows(d.rows)).catch(() => {}); }, []);
  useEffect(() => { document.title = "Faculty Reports | NEMSU"; load(); }, [load]);

  async function review(id, decision) {
    try {
      const r = await api(`/api/admin/faculty/${id}/review`, { method: "POST", json: { decision } });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function markAvailable(id) {
    try {
      const r = await api(`/api/admin/faculty/${id}/available`, { method: "POST" });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  if (!rows) return <Loading label="Loading faculty reports..." wide={1300} />;
  return (
    <div className="page" style={{ maxWidth: 1300 }}>
      <h2 className="page-title">Faculty Reports</h2>
      <p className="page-intro">Review faculty absence reports before they affect availability shown by NEMSAI.</p>
      {rows.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>ID</th><th>Instructor</th><th>Email</th><th>Reason</th><th>Absence date</th><th>Expected return</th><th>Submitted</th><th>Review</th><th>Availability</th><th>Handled by</th><th>PDF</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{padId(r.id)}</td><td>{r.instructor}</td><td>{r.instructor_email}</td><td className="desc">{r.reason}</td>
                <td>{r.start_date}</td><td>{r.expected_return}</td><td>{r.submitted_at}</td>
                <td><span className={"badge s-" + slug(r.review_status || "Approved")}>{r.review_status || "Approved"}</span>
                  {r.reviewed_at && <small className="muted" style={{ display: "block" }}>{r.reviewed_at}</small>}
                  {r.review_note && <small style={{ display: "block" }}>{r.review_note}</small>}</td>
                <td><span className={"badge s-" + slug(r.status)}>{r.status}</span></td>
                <td>{r.reviewed_by || "—"}</td>
                <td><a href={`/api/pdf/faculty/${r.id}`} target="_blank" rel="noopener noreferrer">PDF</a></td>
                <td>{r.review_status === "Pending" ? <div className="inline">
                  <button className="btn small" type="button" onClick={() => review(r.id, "Approved")}>Approve</button>
                  <button className="btn small danger" type="button" onClick={() => review(r.id, "Rejected")}>Reject</button>
                </div> : r.review_status === "Approved" && r.status === "Absent" &&
                  <button className="btn small" type="button" onClick={() => markAvailable(r.id)}>Mark available</button>}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : <p className="empty">No faculty reports yet.</p>}
    </div>
  );
}
