import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading, SearchBox } from "../components/Ui.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "";

function RoleForm({ user, onChanged }) {
  const { setFlash } = useAuth();
  const [role, setRole] = useState(user.role || "student");
  async function save(event) {
    event.preventDefault();
    try {
      const result = await api(`/api/admin/users/${user.id}/role`, { method: "POST", json: { role } });
      setFlash({ text: result.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    onChanged();
  }
  return <form className="inline" onSubmit={save}>
    <select aria-label="Role" value={role} onChange={(event) => setRole(event.target.value)}>
      <option value="student">student</option><option value="instructor">instructor</option>
    </select>
    <button className="btn small" type="submit">Set role</button>
  </form>;
}

export default function AdminUsers() {
  const { user: me, setFlash } = useAuth();
  const [rows, setRows] = useState(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const load = useCallback(() => { api("/api/admin/users").then((data) => setRows(data.rows)).catch(() => {}); }, []);
  useEffect(() => { document.title = "Users | NEMSU"; load(); }, [load]);

  const visibleRows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (rows || []).filter((user) => {
      const matchesSearch = !query || [user.name, user.email, user.student_id, user.department, user.role]
        .some((value) => String(value || "").toLocaleLowerCase().includes(query));
      const matchesFilter = filter === "all"
        || (filter === "pending" && user.approval_status === "Pending")
        || (filter === "deleted" && Boolean(user.deleted_at))
        || (filter === "active" && user.is_active && !user.deleted_at)
        || (filter === "student" && (user.role === "student" || user.registration_type === "student"))
        || (filter === "instructor" && (user.role === "instructor" || user.registration_type === "instructor"));
      return matchesSearch && matchesFilter;
    }).sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
  }, [rows, search, filter]);

  async function toggle(user) {
    try {
      const result = await api(`/api/admin/users/${user.id}/active`, { method: "POST", json: { active: !user.is_active } });
      setFlash({ text: result.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function decide(user, action) {
    try {
      const result = await api(`/api/admin/users/${user.id}/${action}`, { method: "POST", json: {} });
      setFlash({ text: result.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function softDelete(user) {
    if (!window.confirm(`Disable ${user.name}'s account now? It will be permanently deleted after 7 days.`)) return;
    try {
      const result = await api(`/api/admin/users/${user.id}`, { method: "DELETE" });
      setFlash({ text: result.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  if (!rows) return <Loading label="Loading users..." wide={1300} />;
  return <div className="page admin-users-page">
    <h2 className="page-title">Users</h2>
    <p className="page-intro">Users are sorted A-Z. Search by name, email, ID, department, or role. Deleted accounts are disabled immediately and permanently removed after seven days.</p>
    <div className="admin-users-controls">
      <SearchBox value={search} onChange={setSearch} shown={visibleRows.length}
        total={search || filter !== "all" ? visibleRows.length : rows.length} placeholder="Search users..." />
      <label className="admin-filter-label">Filter
        <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All users</option><option value="student">Students</option>
          <option value="instructor">Instructors</option><option value="pending">Pending approval</option>
          <option value="active">Active</option><option value="deleted">Deleted</option>
        </select>
      </label>
    </div>
    <div className="table-wrap admin-users-table-wrap"><table className="data-table admin-users-table">
      <thead><tr><th>Name</th><th>Email</th><th>ID / Department</th><th>Verification</th><th>Approval</th><th>Role</th><th>Created</th><th>Active</th><th>Actions</th></tr></thead>
      <tbody>
        {visibleRows.map((user) => <tr key={user.id}>
          <td data-label="Name">{user.name}</td>
          <td data-label="Email">{user.email}</td>
          <td data-label="ID / Department">{user.student_id || "-"}{user.department && <><br /><small>{user.department}</small></>}</td>
          <td data-label="Verification">
            <div className="admin-user-document-links">
              {user.has_verification_document && <a href={`${API_BASE}/api/admin/users/${user.id}/verification-document`} target="_blank" rel="noreferrer">View {user.verification_document_kind === "cor" ? "COR" : "school ID"}</a>}
              {user.has_cor_document && <a href={`${API_BASE}/api/admin/users/${user.id}/verification-document/cor`} target="_blank" rel="noreferrer">View COR</a>}
              {user.has_id_back_document && <a href={`${API_BASE}/api/admin/users/${user.id}/verification-document/id-back`} target="_blank" rel="noreferrer">View ID back</a>}
              {!user.has_verification_document && !user.has_cor_document && !user.has_id_back_document && <span>-</span>}
            </div>
            {user.verification_ai_note && <details className="admin-user-review">
              <summary>View AI review</summary><small className="registration-review-note">{user.verification_ai_note}</small>
            </details>}
          </td>
          <td data-label="Approval"><span className={"badge " + (user.approval_status === "Approved" ? "s-available" : user.deleted_at ? "s-rejected" : "s-pending")}>{user.approval_status || "Approved"}</span></td>
          <td data-label="Role">{user.role || <em>Not chosen</em>}</td>
          <td data-label="Created">{user.created_at}</td>
          <td data-label="Active"><span className={"badge " + (user.is_active ? "s-available" : "s-rejected")}>{user.deleted_at ? "Soft deleted" : user.is_active ? "Active" : "Deactivated"}</span></td>
          <td data-label="Actions">
            {user.deleted_at ? <small>Permanent deletion: {user.purge_after}</small> : user.role !== "admin" && user.id !== me.id && <div className="admin-user-actions">
              {user.approval_status === "Pending" ? <>
                <button className="btn small" type="button" onClick={() => decide(user, "approve")}>Approve {user.registration_type === "instructor" ? "instructor" : "student"}</button>
                <button className="btn small danger" type="button" onClick={() => decide(user, "reject")}>Reject</button>
              </> : <>
                {user.approval_status === "Approved" && <RoleForm user={user} onChanged={load} />}
                <button className={"btn small" + (user.is_active ? " danger" : "")} type="button" onClick={() => toggle(user)}>{user.is_active ? "Deactivate" : "Activate"}</button>
              </>}
              <button className="btn small danger" type="button" onClick={() => softDelete(user)}>Delete account</button>
            </div>}
          </td>
        </tr>)}
        {visibleRows.length === 0 && <tr><td colSpan="9" className="admin-users-empty">No users match this search and filter.</td></tr>}
      </tbody>
    </table></div>
  </div>;
}
