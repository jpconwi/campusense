import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { EmptyState, Loading, SearchBox } from "../components/Ui.jsx";

export default function AdminHelpMessages() {
  const { setFlash } = useAuth();
  const [rows, setRows] = useState(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const load = useCallback(() => {
    api("/api/admin/help-messages").then((data) => setRows(data.rows)).catch(() => {});
  }, []);
  useEffect(() => { document.title = "Help Messages | NEMSU"; load(); }, [load]);

  const visibleRows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (rows || []).filter((message) => {
      const matchesSearch = !query || [message.name, message.email, message.category,
        message.applicant_type, message.message].some((value) => String(value || "").toLocaleLowerCase().includes(query));
      return matchesSearch && (filter === "all" || message.status.toLowerCase() === filter);
    });
  }, [rows, search, filter]);

  async function resolve(message) {
    try {
      const result = await api(`/api/admin/help-messages/${message.id}/resolve`, { method: "POST", json: {} });
      setFlash({ text: result.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  if (!rows) return <Loading label="Loading help messages..." wide={900} />;
  return <div className="page help-messages-page">
    <h2 className="page-title">Help Messages</h2>
    <p className="page-intro">Messages from students and instructors about registration, login, account deletion, and other issues. Reply using the sender's email.</p>
    <div className="help-messages-controls">
      <SearchBox value={search} onChange={setSearch} shown={visibleRows.length}
        total={search || filter !== "all" ? visibleRows.length : rows.length} placeholder="Search help messages..." />
      <label className="admin-filter-label">Status
        <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All messages</option><option value="new">New</option><option value="resolved">Resolved</option>
        </select>
      </label>
    </div>
    {visibleRows.length === 0 ? <EmptyState title="No help messages found">Try another search or status filter.</EmptyState> : (
      <section className="help-message-list" aria-label="Help messages">
        {visibleRows.map((message) => <article className="help-message-card" key={message.id}>
          <header className="help-message-head">
            <div><h3>{message.category}</h3><p>{message.name} · {message.applicant_type} · {message.created_at.replace("T", " ")}</p></div>
            <span className={"badge " + (message.status === "New" ? "s-pending" : "s-available")}>{message.status}</span>
          </header>
          <a href={`mailto:${message.email}`}>{message.email}</a>
          <p className="help-message-body">{message.message}</p>
          {message.status === "New" && <button className="btn small" type="button" onClick={() => resolve(message)}>Mark resolved</button>}
        </article>)}
      </section>
    )}
  </div>;
}
