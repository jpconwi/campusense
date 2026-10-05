import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Donut, HBars, Trend } from "../components/Charts.jsx";

const short = (text, n = 90) => (text && text.length > n ? text.slice(0, n - 1) + "…" : text || "");

export default function AdminDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { document.title = "Admin Dashboard | NEMSU"; api("/api/admin/dashboard").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="page" />;
  const c = d.charts;

  return (
    <div className="page">
      <h2 className="page-title">Admin Dashboard</h2>
      <p className="page-intro">All numbers below are real counts from the database.</p>

      <div className="grid">
        {d.stats.map(([label, number]) => (
          <div className="stat" key={label}><div className="num">{number}</div><div className="lbl">{label}</div></div>
        ))}
      </div>

      <div className="card chart-card">
        <h3>Submissions in the last {c.trend.days} days</h3>
        <Trend t={c.trend} />
      </div>

      <div className="chart-grid">
        <div className="card chart-card"><h3>Concerns by status</h3><Donut chart={c.concern_status} /></div>
        <div className="card chart-card"><h3>Reports by status</h3><Donut chart={c.report_status} /></div>
        <div className="card chart-card"><h3>Faculty reports</h3><Donut chart={c.faculty_status} /></div>
        <div className="card chart-card"><h3>Concerns by type</h3><HBars items={c.concern_types} /></div>
        <div className="card chart-card"><h3>Reports by type</h3><HBars items={c.report_types} /></div>
        <div className="card chart-card"><h3>Top locations (concerns + reports)</h3><HBars items={c.locations} /></div>
      </div>

      <div className="card">
        <h3>Pending concerns</h3>
        {d.recent_concerns.length ? (
          <>
            <div className="table-wrap"><table>
              <thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Location</th><th>Room</th><th>Description</th><th>Submitted</th></tr></thead>
              <tbody>{d.recent_concerns.map((r) => (
                <tr key={r.id}><td>{r.id}</td><td>{r.reporter_name}</td><td>{r.concern_type}</td><td>{r.location}</td><td>{r.room || ""}</td><td className="desc">{short(r.description)}</td><td>{r.created_at}</td></tr>
              ))}</tbody>
            </table></div>
            <p style={{ marginTop: 10 }}><Link to="/admin/concerns?status=Pending">See all pending concerns</Link></p>
          </>
        ) : <p className="empty">No pending concerns.</p>}
      </div>

      <div className="card">
        <h3>Pending reports</h3>
        {d.recent_reports.length ? (
          <>
            <div className="table-wrap"><table>
              <thead><tr><th>ID</th><th>Reporter</th><th>Type</th><th>Location</th><th>Description</th><th>Submitted</th></tr></thead>
              <tbody>{d.recent_reports.map((r) => (
                <tr key={r.id}><td>{r.id}</td><td>{r.reporter_name}</td><td>{r.report_type}</td><td>{r.location}</td><td className="desc">{short(r.description)}</td><td>{r.created_at}</td></tr>
              ))}</tbody>
            </table></div>
            <p style={{ marginTop: 10 }}><Link to="/admin/reports?status=Pending">See all pending reports</Link></p>
          </>
        ) : <p className="empty">No pending reports.</p>}
      </div>
    </div>
  );
}
