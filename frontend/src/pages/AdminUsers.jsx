import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading } from "../components/Ui.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "";

function RoleForm({ user, onChanged }) {
  const { setFlash } = useAuth();
  const [role, setRole] = useState(user.role || "student");
  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/users/${user.id}/role`, { method: "POST", json: { role } });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    onChanged();
  }
  return (
    <form className="inline" onSubmit={save}>
      <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="student">student</option><option value="instructor">instructor</option>
      </select>{" "}
      <button className="btn small" type="submit">Set role</button>
    </form>
  );
}

export default function AdminUsers() {
  const { user: me, setFlash } = useAuth();
  const [rows, setRows] = useState(null);
  const [helpMessages, setHelpMessages] = useState([]);
  const load = useCallback(() => {
    Promise.all([api("/api/admin/users"), api("/api/admin/registration-help")])
      .then(([users, messages]) => { setRows(users.rows); setHelpMessages(messages.rows); })
      .catch(() => {});
  }, []);
  useEffect(() => { document.title = "Users | NEMSU"; load(); }, [load]);

  async function toggle(u) {
    try {
      const r = await api(`/api/admin/users/${u.id}/active`, { method: "POST", json: { active: !u.is_active } });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function decide(u, action) {
    try {
      const r = await api(`/api/admin/users/${u.id}/${action}`, { method: "POST", json: {} });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function softDelete(u) {
    if (!window.confirm(`Disable ${u.name}'s account now? It will be permanently deleted after 7 days.`)) return;
    try {
      const r = await api(`/api/admin/users/${u.id}`, { method: "DELETE" });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function resolveHelpMessage(message) {
    try {
      const r = await api(`/api/admin/registration-help/${message.id}/resolve`, { method: "POST", json: {} });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  if (!rows) return <Loading label="Loading users..." wide={1300} />;
  return (
    <div className="page" style={{ maxWidth: 1300 }}>
      <h2 className="page-title">Users</h2>
      <p className="page-intro">Review accounts and applicant help requests. Deleted accounts are disabled immediately and permanently removed after seven days.</p>
      <section className="card registration-help-inbox">
        <h3>Registration help messages</h3>
        {helpMessages.length === 0 ? <p className="empty">No applicant messages.</p> : (
          <div className="registration-help-list">
            {helpMessages.map((message) => (
              <article className="registration-help-message" key={message.id}>
                <div><strong>{message.name}</strong> · {message.applicant_type} · {message.created_at}</div>
                <a href={`mailto:${message.email}`}>{message.email}</a>
                <p>{message.message}</p>
                {message.status === "New" ? (
                  <button className="btn small" type="button" onClick={() => resolveHelpMessage(message)}>Mark resolved</button>
                ) : <span className="badge s-available">Resolved</span>}
              </article>
            ))}
          </div>
        )}
      </section>
      <div className="table-wrap admin-users-table-wrap"><table className="data-table admin-users-table">
        <thead><tr><th>Name</th><th>Email</th><th>ID / Department</th><th>Verification</th><th>Approval</th><th>Role</th><th>Created</th><th>Active</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              <td data-label="Name">{u.name}</td><td data-label="Email">{u.email}</td><td data-label="ID / Department">{u.student_id || "—"}{u.department && <><br /><small>{u.department}</small></>}</td>
              <td data-label="Verification">{u.has_verification_document ? (
                <a href={`${API_BASE}/api/admin/users/${u.id}/verification-document`}
                  target="_blank" rel="noreferrer">View {u.verification_document_kind === "cor" ? "COR" : "school ID"}</a>
              ) : "—"}
                {u.has_cor_document && <><br /><a href={`${API_BASE}/api/admin/users/${u.id}/verification-document/cor`}
                  target="_blank" rel="noreferrer">View COR</a></>}
                {u.has_id_back_document && <><br /><a href={`${API_BASE}/api/admin/users/${u.id}/verification-document/id-back`}
                  target="_blank" rel="noreferrer">View ID back</a></>}
                {u.verification_ai_note && <small className="registration-review-note">{u.verification_ai_note}</small>}
              </td>
              <td data-label="Approval"><span className={"badge " + (u.approval_status === "Approved" ? "s-available" : u.deleted_at ? "s-rejected" : "s-pending")}>
                {u.approval_status || "Approved"}</span></td>
              <td data-label="Role">{u.role ? <span className="role-pill" style={{ background: "var(--blue-soft)" }}>{u.role}</span> : <em>not chosen</em>}</td>
              <td data-label="Created">{u.created_at}</td>
              <td data-label="Active"><span className={"badge " + (u.is_active ? "s-available" : "s-rejected")}>{u.deleted_at ? "Soft deleted" : u.is_active ? "Active" : "Deactivated"}</span></td>
              <td data-label="Actions">
                {u.deleted_at ? (
                  <small>Permanent deletion: {u.purge_after}</small>
                ) : u.role !== "admin" && u.id !== me.id && (
                  <>
                    {u.approval_status === "Pending" ? (
                      <>
                        <button className="btn small" type="button" onClick={() => decide(u, "approve")}>Approve {u.registration_type === "instructor" ? "instructor" : "student"}</button>{" "}
                        <button className="btn small danger" type="button" onClick={() => decide(u, "reject")}>Reject</button>
                      </>
                    ) : (
                      <>
                        {u.approval_status === "Approved" && <RoleForm user={u} onChanged={load} />}{" "}
                        <button className={"btn small" + (u.is_active ? " danger" : "")} type="button" onClick={() => toggle(u)}>
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </>
                    )}
                    <br /><button className="btn small danger" type="button" onClick={() => softDelete(u)}>Delete account</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </div>
  );
}
