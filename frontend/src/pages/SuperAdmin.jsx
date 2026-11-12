import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading } from "../components/Ui.jsx";

export default function SuperAdmin() {
  const { setFlash } = useAuth();
  const [data, setData] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [showAdminForm, setShowAdminForm] = useState(false);
  const [loadError, setLoadError] = useState("");
  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [system, people] = await Promise.all([api("/api/admin/system"), api("/api/admin/system/admins")]);
      setData(system);
      setAdmins(Array.isArray(people.rows) ? people.rows : []);
    } catch (error) {
      setLoadError(error.message || "Could not load system control.");
      throw error;
    }
  }, []);
  useEffect(() => { document.title = "System Control | NEMSU"; load().catch(() => {}); }, [load]);

  async function createAdmin(event) {
    event.preventDefault();
    try {
      const result = await api("/api/admin/system/admins", { method: "POST", json: { name: adminName, email: adminEmail, password: adminPassword } });
      setFlash({ text: result.message, kind: "info" });
      setAdminName(""); setAdminEmail(""); setAdminPassword(""); setShowAdminForm(false); await load();
    } catch (error) { setFlash({ text: error.message, kind: "error" }); }
  }

  async function deleteAdmin(person) {
    if (!window.confirm(`Disable the report-manager account for ${person.email}?`)) return;
    try {
      const result = await api(`/api/admin/system/admins/${person.id}`, { method: "DELETE" });
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
  const formatBytes = (bytes) => {
    if (bytes == null) return "Unavailable";
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / (1024 ** unit)).toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
  };
  const storage = data.storage || {};
  const diskPercent = storage.disk_total_bytes ? Math.min(100, Math.round(storage.disk_used_bytes * 100 / storage.disk_total_bytes)) : 0;
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
    
    <button className="btn" type="button" onClick={() => setShowAdminForm(true)}>Create admin account</button>
    <div className="table-wrap"><table className="data-table">
      <thead><tr><th>Name</th><th>Email</th><th>Department</th><th>Role</th><th>Admin account</th></tr></thead>
      <tbody>{admins.map((person) => <tr key={person.id}>
        <td>{person.name}</td><td>{person.email}</td><td>{person.department || "—"}</td>
        <td>{(person.role || "").replaceAll("_", " ")}</td>
        <td>{person.deleted_at || !person.is_active ? <span className="muted">Disabled</span> : person.role === "super_admin" || person.is_allowlisted_admin
          ? <span className="muted">Protected</span> : person.role === "admin"
          ? <button className="btn small danger" type="button" onClick={() => deleteAdmin(person)}>Delete admin</button>
          : <span className="muted">Configured account</span>}</td>
      </tr>)}</tbody>
    </table></div>

    <h3>Storage</h3>
    <p className="muted">Monitor storage used by uploaded files, generated reports, and the database on this server.</p>
    <section className="record-card-list" aria-label="Storage usage">
      <article className="record-card"><strong>Uploaded files</strong><h3>{formatBytes(storage.uploads_bytes)}</h3></article>
      <article className="record-card"><strong>Generated reports</strong><h3>{formatBytes(storage.generated_files_bytes)}</h3></article>
      <article className="record-card"><strong>Database</strong><h3>{formatBytes(storage.database_bytes)}</h3></article>
      <article className="record-card"><strong>Registration files in database</strong><h3>{formatBytes(storage.registration_database_file_bytes)}</h3></article>
      <article className="record-card"><strong>Registration files offloaded</strong><h3>{storage.registration_offloaded_file_count} / {storage.registration_file_count}</h3></article>
      <article className="record-card"><strong>Server disk free</strong><h3>{formatBytes(storage.disk_free_bytes)}</h3></article>
    </section>
    <section className="card" aria-label="Server disk capacity">
      <strong>Server disk usage</strong><p>{formatBytes(storage.disk_used_bytes)} used of {formatBytes(storage.disk_total_bytes)} ({diskPercent}%)</p>
      <progress max="100" value={diskPercent} style={{ width: "100%" }} aria-label={`Server disk ${diskPercent}% used`} />
      {storage.cloud_storage_note && <p className="muted">{storage.cloud_storage_note}</p>}
    </section>

    <h3>AI integrations</h3>
    <p className="muted">Provider keys and model names remain in server configuration. Disable a provider here to remove it from both text and photo-analysis fallback chains.</p>
    <div className="record-card-list">{data.ai_providers.map((provider) => <article className="record-card" key={provider.name}>
      <strong>{provider.name}</strong><span>{provider.has_credentials ? "Credentials configured" : "No credentials"}</span>
      <label><input type="checkbox" checked={provider.enabled} onChange={(event) => setProvider(provider, event.target.checked)} /> Enabled</label>
    </article>)}</div>

    <h3>Privileged activity</h3>
    {data.activity.length ? <div className="table-wrap"><table className="data-table">
      <thead><tr><th>Time</th><th>Administrator</th><th>Action</th><th>Account</th><th>Details</th></tr></thead>
      <tbody>{data.activity.map((entry) => <tr key={entry.id}><td>{entry.created_at}</td><td>{entry.actor_email}</td>
        <td>{entry.action.replaceAll("_", " ")}</td><td>{entry.target_email || "â€”"}</td><td>{entry.details || "â€”"}</td></tr>)}</tbody>
    </table></div> : <p className="muted">No privileged changes have been recorded yet.</p>}
    <h3>Faculty reports and reservation reviews</h3>
    <p className="muted">Review status, assigned administrator, and decision notes for the latest submissions.</p>
    {data.review_audit?.length ? <div className="table-wrap"><table className="data-table">
      <thead><tr><th>Type</th><th>Reference</th><th>Submitted</th><th>Requester</th><th>Status</th><th>Handled by</th><th>Reviewed</th><th>Note</th></tr></thead>
      <tbody>{data.review_audit.map((entry) => <tr key={`${entry.kind}-${entry.id}`}>
        <td>{entry.kind}</td><td>#{String(entry.id).padStart(4, "0")}</td><td>{entry.submitted_at || "â€”"}</td>
        <td>{entry.requester || "â€”"}</td><td><span className={`badge s-${String(entry.status || "").toLowerCase().replaceAll(" ", "-")}`}>{entry.status || "Pending"}</span></td>
        <td>{entry.handler || <span className="muted">Awaiting review</span>}</td><td>{entry.reviewed_at || "â€”"}</td><td>{entry.note || "â€”"}</td>
      </tr>)}</tbody>
    </table></div> : <p className="muted">No faculty reports or reservation requests have been submitted.</p>}
    {showAdminForm && <div className="system-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowAdminForm(false); }}>
      <section className="system-modal" role="dialog" aria-modal="true" aria-labelledby="create-admin-title">
        <h3 id="create-admin-title">Create admin account</h3>
        <p className="muted">Choose a unique password with at least 10 characters. It will be stored as a secure hash.</p>
        <form className="system-admin-form" onSubmit={createAdmin}>
          <label>Full name<input required minLength={2} maxLength={120} autoComplete="name" value={adminName} onChange={(event) => setAdminName(event.target.value)} /></label>
          <label>NEMSU email<input type="email" required maxLength={255} autoComplete="email" placeholder="admin@nemsu.edu.ph" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} /></label>
          <label>Admin password<input type="password" required minLength={10} maxLength={200} autoComplete="new-password" value={adminPassword} onChange={(event) => setAdminPassword(event.target.value)} /></label>
          <div className="system-modal-actions"><button className="btn ghost" type="button" onClick={() => setShowAdminForm(false)}>Cancel</button><button className="btn" type="submit">Create account</button></div>
        </form>
      </section>
    </div>}
  </div>;
}
