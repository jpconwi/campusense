import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

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

  if (!rows) return <div className="page" style={{ maxWidth: 1300 }} />;
  return (
    <div className="page" style={{ maxWidth: 1300 }}>
      <h2 className="page-title">Users</h2>
      <p className="page-intro">Administrators are set only through ADMIN_EMAILS in backend/.env. Here you can change Student/Instructor roles and deactivate accounts.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Created</th><th>Last login</th><th>Active</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              <td>{u.name}</td><td>{u.email}</td>
              <td>{u.role ? <span className="role-pill" style={{ background: "var(--blue-soft)" }}>{u.role}</span> : <em>not chosen</em>}</td>
              <td>{u.created_at}</td><td>{u.last_login}</td>
              <td><span className={"badge " + (u.is_active ? "s-available" : "s-rejected")}>{u.is_active ? "Active" : "Deactivated"}</span></td>
              <td>
                {u.role !== "admin" && u.id !== me.id && (
                  <>
                    <RoleForm user={u} onChanged={load} />{" "}
                    <button className={"btn small" + (u.is_active ? " danger" : "")} type="button" onClick={() => toggle(u)}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
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
