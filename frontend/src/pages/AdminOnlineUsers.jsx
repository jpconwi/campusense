import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Loading } from "../components/Ui.jsx";

function since(value, online) {
  if (online) return "Online now";
  if (!value) return "Never online";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(`${value}Z`).getTime()) / 60000));
  if (minutes < 1) return "Last seen just now";
  if (minutes < 60) return `Last seen ${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Last seen ${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `Last seen ${days} ${days === 1 ? "day" : "days"} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `Last seen ${months} ${months === 1 ? "month" : "months"} ago`;
  const years = Math.floor(days / 365);
  return `Last seen ${years} ${years === 1 ? "year" : "years"} ago`;
}

export default function AdminOnlineUsers({ embedded = false }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!embedded) document.title = "Online Users | NEMSU";
    let alive = true;
    const load = () => api("/api/admin/user-activity").then((result) => { if (alive) setData(result); }).catch(() => {});
    load();
    const timer = window.setInterval(load, 30_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [embedded]);

  if (!data) return <Loading label="Loading online users..." />;
  const top = [...data.rows].filter((u) => u.minutes_30d > 0)
    .sort((a, b) => b.minutes_30d - a.minutes_30d).slice(0, 3);
  const content = (
    <>
      {!embedded && <><h2 className="page-title">Online Users</h2>
        <p className="page-intro">Green means online now; gray means offline. Activity totals show foreground use across web and mobile.</p></>}
      <section className="card">
        <div className="user-activity-heading">
          <div><h3>Most active · past 30 days</h3><p className="muted">Ranked by tracked active minutes.</p></div>
          <strong>{data.online_count} online now</strong>
        </div>
        {top.length ? <div className="activity-top-three">
          {top.map((u, index) => <article className="activity-top-user" key={u.id}>
            <span className={`activity-rank rank-${index + 1}`}>Top {index + 1}</span>
            <strong>{u.name}</strong><small>{u.role} · {u.minutes_30d} active min</small>
            <span className={`user-presence ${u.online ? "is-online" : ""}`}><i />{since(u.last_seen_at, u.online)}</span>
          </article>)}
        </div> : <p className="empty">No active student or instructor accounts.</p>}
      </section>

      <section className="card user-activity-card">
        <div className="user-activity-heading"><h3>All students and instructors</h3>{!embedded && <Link to="/admin/users?view=users">Manage users</Link>}</div>
        {data.rows.length ? <div className="table-wrap"><table>
          <thead><tr><th>Status</th><th>User</th><th>Role</th><th>Last online</th></tr></thead>
          <tbody>{data.rows.map((u) => <tr key={u.id}>
            <td><span className={`user-presence ${u.online ? "is-online" : ""}`}><i />{u.online ? "Online" : "Offline"}</span></td>
            <td><strong>{u.name}</strong><br /><small>{u.email}</small></td><td>{u.role}</td>
            <td>{since(u.last_seen_at, u.online)}</td>
          </tr>)}</tbody>
        </table></div> : <p className="empty">No active student or instructor accounts.</p>}
        <small className="muted activity-refresh-note">Updates every 30 seconds. Offline status appears after two minutes without a heartbeat.</small>
      </section>
    </>
  );
  return embedded ? content : <div className="page">{content}</div>;
}
