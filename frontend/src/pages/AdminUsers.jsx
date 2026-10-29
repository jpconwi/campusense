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
  const load = useCallback(() => { api("/api/admin/users").then((d) => setRows(d.rows)).catch(() => {}); }, []);
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

  if (!rows) return <Loading label="Loading users..." wide={1300} />;
  return (
    <div className="page" style={{ maxWidth: 1300 }}>
      <h2 className="page-title">Users</h2>
      <p className="page-intro">Administrators are set only through ADMIN_EMAILS in backend/.env. Review personal-Gmail student applications here; official NEMSU Gmail accounts are approved automatically.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Email</th><th>School ID</th><th>Verification</th><th>Approval</th><th>Role</th><th>Created</th><th>Active</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              <td>{u.name}</td><td>{u.email}</td><td>{u.student_id || "—"}</td>
              <td>{u.has_verification_document ? (
                <a href={`${API_BASE}/api/admin/users/${u.id}/verification-document`}
                  target="_blank" rel="noreferrer">View ID/COR</a>
              ) : "—"}</td>
              <td><span className={"badge " + (u.approval_status === "Approved" ? "s-available" : "s-pending")}>
                {u.approval_status || "Approved"}</span></td>
              <td>{u.role ? <span className="role-pill" style={{ background: "var(--blue-soft)" }}>{u.role}</span> : <em>not chosen</em>}</td>
              <td>{u.created_at}</td>
              <td><span className={"badge " + (u.is_active ? "s-available" : "s-rejected")}>{u.is_active ? "Active" : "Deactivated"}</span></td>
              <td>
                {u.role !== "admin" && u.id !== me.id && (
                  <>
                    {u.approval_status === "Pending" ? (
                      <>
                        <button className="btn small" type="button" onClick={() => decide(u, "approve")}>Approve student</button>{" "}
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
