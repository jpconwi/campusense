import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Loading } from "../components/Ui.jsx";

export default function Notifications() {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    document.title = "Notifications | NEMSU";
    let alive = true;
    const load = () => api("/api/announcements").then((data) => { if (alive) setRows(data.rows || []); }).catch(() => {});
    load();
    const timer = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  if (rows === null) return <Loading label="Loading notifications..." />;
  return (
    <div className="page">
      <h2 className="page-title">Notifications</h2>
      <p className="page-intro">Current announcements from the administration. This list refreshes automatically.</p>
      {rows.length ? <div className="announcement-list">{rows.map((item) => (
        <article className="card announcement-item" key={item.id}>
          <div><strong>{item.title}</strong><span className="announcement-category">{item.category}</span></div>
          <p>{item.body}</p>
          {(item.start_date || item.end_date) && <small>{item.start_date ? `Date: ${item.start_date}` : ""}{item.start_date && item.end_date ? " · " : ""}{item.end_date ? `Until: ${item.end_date}` : ""}</small>}
        </article>
      ))}</div> : <section className="card"><p className="empty">You’re all caught up. There are no current announcements.</p></section>}
    </div>
  );
}
