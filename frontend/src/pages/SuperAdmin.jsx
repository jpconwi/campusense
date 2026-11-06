import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading } from "../components/Ui.jsx";

export default function SuperAdmin() {
  const { user: me, setFlash } = useAuth();
  const [data, setData] = useState(null);
  const [users, setUsers] = useState([]);
  const [departmentName, setDepartmentName] = useState("");
  const [office, setOffice] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [loadError, setLoadError] = useState("");
  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [system, people] = await Promise.all([api("/api/admin/system"), api("/api/admin/users")]);
      setData(system);
      setUsers(Array.isArray(people.rows) ? people.rows : []);
    } catch (error) {
      setLoadError(error.message || "Could not load system control.");
      throw error;
    }
  }, []);
  useEffect(() => { document.title = "System Control | NEMSU"; load().catch(() => {}); }, [load]);

  async function setRole(person, role) {
    try {
      const result = await api(`/api/admin/system/users/${person.id}/role`, { method: "POST", json: { role } });
      setFlash({ text: result.message, kind: "info" });
      await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  async function createAdmin(event) {
    event.preventDefault();
    try {
      const result = await api("/api/admin/system/admins", { method: "POST", json: { name: adminName, email: adminEmail } });
      setFlash({ text: result.message, kind: "info" });
      setAdminName(""); setAdminEmail(""); await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  async function deleteAdmin(person) {
    if (!window.confirm(`Disable the report-manager account for ${person.email}?`)) return;
    try {
      const result = await api(`/api/admin/system/admins/${person.id}`, { method: "DELETE" });
      setFlash({ text: result.message, kind: "info" }); await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  async function addDepartment(event) {
    event.preventDefault();
    try {
      const result = await api("/api/admin/system/departments", { method: "POST", json: { name: departmentName, office } });
      setFlash({ text: result.message, kind: "info" });
      setDepartmentName(""); setOffice(""); await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  async function removeDepartment(department) {
    try {
      const result = await api(`/api/admin/system/departments/${department.id}`, { method: "DELETE" });
      setFlash({ text: result.message, kind: "info" }); await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  async function setProvider(provider, enabled) {
    try {
      const result = await api(`/api/admin/system/ai-provider/${provider.provider}`, {
        method: "POST", json: { enabled },
      });
      setFlash({ text: result.message, kind: "info" }); await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  if (!data && loadError) return <div className="page"><h2 className="page-title">System Control</h2><p role="alert" className="error">{loadError}</p><button className="btn" type="button" onClick={() => load().catch(() => {})}>Try again</button></div>;
  if (!data) return <Loading label="Loading system control..." wide={1200} />;
  return <div className="page">
    <h2 className="page-title">System Control</h2>
    <p className="page-intro">Manage privileged access, review system activity, and monitor campus-wide services.</p>

    <section className="record-card-list" aria-label="Campus-wide account totals">
      {data.role_counts.map(([role, count]) => <article className="record-card" key={role}>
        <strong>{role.replaceAll("_", " ")}</strong><h3>{count}</h3>
      </article>)}
    </section>
    <h3>Campus-wide records</h3>
    <section className="record-card-list" aria-label="Campus-wide record totals">
      {data.record_counts.map(([label, count]) => <article className="record-card" key={label}>
        <strong>{label}</strong><h3>{count}</h3>
      </article>)}
    </section>

    <h3>Administrator accounts and roles</h3>
    <p className="muted">Admins are report managers and sign in with their NEMSU Google account. They do not get a separate app password. Keep at least one super administrator configured in SUPER_ADMIN_EMAILS.</p>
    <form className="inline" onSubmit={createAdmin}>
      <input aria-label="Admin full name" required minLength={2} maxLength={120} placeholder="Admin full name" value={adminName} onChange={(event) => setAdminName(event.target.value)} />
      <input aria-label="Admin NEMSU email" type="email" required maxLength={255} placeholder="admin@nemsu.edu.ph" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} />
      <button className="btn small" type="submit">Create admin account</button>
    </form>
    <div className="table-wrap"><table className="data-table">
      <thead><tr><th>Name</th><th>Email</th><th>Department</th><th>Access</th><th>Update access</th><th>Admin account</th></tr></thead>
      <tbody>{users.map((person) => <tr key={person.id}>
        <td>{person.name}</td><td>{person.email}</td><td>{person.department || "—"}</td>
        <td>{(person.role || "No role").replaceAll("_", " ")}</td>
        <td>{person.id === me.id || person.is_allowlisted_admin || person.deleted_at || person.approval_status !== "Approved"
          ? <span className="muted">{person.is_allowlisted_admin ? "Protected by deployment settings" : person.id === me.id ? "Your own account" : "Account must be approved and active"}</span> :
          <select aria-label={`Access for ${person.email}`} value={person.role || ""} onChange={(event) => setRole(person, event.target.value)}>
            <option value="" disabled>No role</option>
            <option value="student">student</option><option value="instructor">instructor</option>
            <option value="admin">admin</option>
          </select>}</td>
        <td>{person.role === "admin" && !person.is_allowlisted_admin && person.id !== me.id && !person.deleted_at
          ? <button className="btn small danger" type="button" onClick={() => deleteAdmin(person)}>Delete admin</button>
          : person.role === "admin" ? <span className="muted">Configured account</span> : "—"}</td>
      </tr>)}</tbody>
    </table></div>

    <h3>AI integrations</h3>
    <p className="muted">Provider keys and model names remain in server configuration. Disable a provider here to remove it from both text and photo-analysis fallback chains.</p>
    <div className="record-card-list">{data.ai_providers.map((provider) => <article className="record-card" key={provider.name}>
      <strong>{provider.name}</strong><span>{provider.has_credentials ? "Credentials configured" : "No credentials"}</span>
      <label><input type="checkbox" checked={provider.enabled} onChange={(event) => setProvider(provider, event.target.checked)} /> Enabled</label>
    </article>)}</div>

    <h3>Departments and offices</h3>
    <form className="inline" onSubmit={addDepartment}>
      <input aria-label="Department name" required minLength={2} maxLength={120} placeholder="Department" value={departmentName} onChange={(event) => setDepartmentName(event.target.value)} />
      <input aria-label="Office name" maxLength={160} placeholder="Office (optional)" value={office} onChange={(event) => setOffice(event.target.value)} />
      <button className="btn small" type="submit">Add</button>
    </form>
    {data.departments.length ? <ul>{data.departments.map((department) => <li key={department.id}>
      {department.name}{department.office ? ` — ${department.office}` : ""} <button className="btn small danger" type="button" onClick={() => removeDepartment(department)}>Remove</button>
    </li>)}</ul> : <p className="muted">No departments have been added.</p>}

    <h3>Privileged activity</h3>
    {data.activity.length ? <div className="table-wrap"><table className="data-table">
      <thead><tr><th>Time</th><th>Administrator</th><th>Action</th><th>Account</th><th>Details</th></tr></thead>
      <tbody>{data.activity.map((entry) => <tr key={entry.id}><td>{entry.created_at}</td><td>{entry.actor_email}</td>
        <td>{entry.action.replaceAll("_", " ")}</td><td>{entry.target_email || "—"}</td><td>{entry.details || "—"}</td></tr>)}</tbody>
    </table></div> : <p className="muted">No privileged changes have been recorded yet.</p>}
  </div>;
}
