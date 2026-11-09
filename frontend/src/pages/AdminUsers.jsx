import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading, SearchBox } from "../components/Ui.jsx";
import AdminOnlineUsers from "./AdminOnlineUsers.jsx";

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
  const [params] = useSearchParams();
  const viewParam = params.get("view");
  const view = viewParam === "online" ? viewParam : "users";
  const [rows, setRows] = useState(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState(() => params.get("filter") || "all");
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

  async function softDelete(user) {
    if (!window.confirm(`Disable ${user.name}'s account now? It will be permanently deleted after 7 days.`)) return;
    try {
      const result = await api(`/api/admin/users/${user.id}`, { method: "DELETE" });
      setFlash({ text: result.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  if (view === "users" && !rows) return <Loading label="Loading users..." wide={1300} />;
  return <div className="page admin-users-page">
    <h2 className="page-title">Users</h2>
    <p className="page-intro">Manage accounts and check student and instructor presence.</p>
    <nav className="admin-view-switch" aria-label="User management views">
      <Link to="/admin/users?view=users" className={view === "users" ? "selected" : ""}>All users</Link>
      <Link to="/admin/users?view=online" className={view === "online" ? "selected" : ""}>Online users</Link>
      <Link to="/admin/accounts?status=Pending">Review pending accounts</Link>
    </nav>
    {view === "online" ? <AdminOnlineUsers embedded /> : <>
    <p className="admin-section-note">Users are sorted A-Z. Deleted accounts are disabled immediately and permanently removed after seven days.</p>
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
    <section className="admin-user-card-list" aria-label="User accounts">
      {visibleRows.map((user) => <article className="admin-user-card" key={user.id}>
        <div className="admin-user-card-head">
          <div><h3>{user.name}</h3><a href={`mailto:${user.email}`}>{user.email}</a></div>
          <div className="admin-user-card-badges">
            <span className={'badge ' + (user.approval_status === 'Approved' ? 's-available' : user.deleted_at ? 's-rejected' : 's-pending')}>{user.approval_status || 'Approved'}</span>
            <span className={'badge ' + (user.is_active ? 's-available' : 's-rejected')}>{user.deleted_at ? 'Soft deleted' : user.is_active ? 'Active' : 'Deactivated'}</span>
          </div>
        </div>
        <div className="admin-user-card-meta">
          <span><b>Role</b>{user.role || 'Not chosen'}</span>
          <span><b>ID / Department</b>{user.student_id || '-'}{user.department ? ` / ${user.department}` : ''}</span>
          <span><b>Created</b>{user.created_at}</span>
        </div>
        <div className="admin-user-card-documents">
          <b>Verification files</b>
          <div className="admin-user-document-links">
            {user.has_verification_document && <a href={`${API_BASE}/api/admin/users/${user.id}/verification-document`} target="_blank" rel="noreferrer">View {user.verification_document_kind === 'cor' ? 'COR' : 'school ID front'}</a>}
            {user.has_cor_document && <a href={`${API_BASE}/api/admin/users/${user.id}/verification-document/cor`} target="_blank" rel="noreferrer">View COR</a>}
            {user.has_id_back_document && <a href={`${API_BASE}/api/admin/users/${user.id}/verification-document/id-back`} target="_blank" rel="noreferrer">View ID back</a>}
            {!user.has_verification_document && !user.has_cor_document && !user.has_id_back_document && <span>None uploaded</span>}
          </div>
          {user.verification_ai_note && <details className="admin-user-review"><summary>View AI review</summary><small className="registration-review-note">{user.verification_ai_note}</small></details>}
          {user.has_face_image && <div className="admin-user-review">
            <b>Face scan: {user.face_review_status === "AI Pose Passed" ? "Selfie framing passed; identity not matched by AI" : user.face_review_status || "Pending"}</b>
            <div className="admin-user-document-links">
              <a href={`${API_BASE}/api/admin/users/${user.id}/face-image`} target="_blank" rel="noreferrer">View selfie</a>
              {user.has_face_scan_pdf && <a href={`${API_BASE}/api/admin/users/${user.id}/face-scan-pdf`} target="_blank" rel="noreferrer">View selfie PDF</a>}
            </div>
          </div>}
        </div>
        <div className="admin-user-actions">
          {user.deleted_at ? <small>Permanent deletion: {user.purge_after}</small> : !['admin', 'super_admin'].includes(user.role) && user.id !== me.id && <>
            {user.approval_status === 'Pending' ? <Link className="btn small" to="/admin/accounts?status=Pending">Review in Account Checks</Link> : <>
              {user.approval_status === 'Approved' && <RoleForm user={user} onChanged={load} />}
              <button className={'btn small' + (user.is_active ? ' danger' : '')} type="button" onClick={() => toggle(user)}>{user.is_active ? 'Deactivate' : 'Activate'}</button>
            </>}
            <button className="btn small danger" type="button" onClick={() => softDelete(user)}>Delete account</button>
          </>}
        </div>
      </article>)}
      {visibleRows.length === 0 && <div className="admin-users-empty">No users match this search and filter.</div>}
    </section>
    </>}
  </div>;
}
