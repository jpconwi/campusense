import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Loading } from "../components/Ui.jsx";

/** Rooms, Campus Information and Announcements: add a row, list rows, delete a row. */
export default function AdminDataset({ kind }) {            // kind = "rooms" | "campus" | "announcements"
  const { setFlash } = useAuth();
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});
  const [editing, setEditing] = useState(null);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (kind === "rooms") {
      params.set("page", String(page)); params.set("page_size", "100");
      if (search.trim()) params.set("search", search.trim());
      if (department) params.set("department", department);
    }
    const query = params.toString();
    const suffix = query ? `?${query}` : "";
    api(`/api/admin/${kind}${suffix}`).then(setData).catch(() => {});
  }, [kind, page, search, department]);
  useEffect(() => { setData(null); setValues({}); setSearch(""); setDepartment(""); setPage(1); }, [kind]);
  useEffect(() => { const timer = setTimeout(load, kind === "rooms" ? 250 : 0); return () => clearTimeout(timer); }, [load, kind]);
  useEffect(() => { if (data) document.title = `${data.title} | NEMSU`; }, [data]);

  async function save(e) {
    e.preventDefault();
    try {
      const r = await api(editing ? `/api/admin/${kind}/${editing.id}` : `/api/admin/${kind}`, {
        method: editing ? "PUT" : "POST", json: values,
      });
      setFlash({ text: r.message, kind: "info" });
      setValues({});
      setEditing(null);
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function importRooms(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData(); form.append("file", file);
    try {
      const result = await api("/api/admin/rooms/import", { method: "POST", form });
      setFlash({ text: result.message, kind: "info" });
      if (page === 1) load(); else setPage(1);
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    event.target.value = "";
  }

  function edit(row) {
    setEditing(row);
    setValues(Object.fromEntries(fields.map(([name]) => [name, row[name] ?? ""])));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function remove(row) {
    if (!window.confirm("Delete this row?")) return;
    try {
      const r = await api(`/api/admin/${kind}/${row.id}`, { method: "DELETE" });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  const title = data?.title || "";
  const fields = data?.fields || [];
  const rows = data?.rows || [];
  const empty = data?.empty || "No entries yet.";
  const searchable = kind === "rooms" || kind === "campus";
  const departments = useMemo(() => {
    const values = [
      ...(data?.department_options || []).map((option) => typeof option === "string"
        ? { value: option, label: option } : option),
      ...rows.map((row) => row.department || row.building).filter(Boolean)
        .map((value) => ({ value, label: value })),
    ];
    return [...new Map(values.map((option) => [option.value, option])).values()]
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [rows, data?.department_options]);
  const visibleRows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return rows.filter((row) => {
      const rowDepartment = row.department || row.building || "";
      if (kind === "rooms" && department && rowDepartment !== department) return false;
      if (!query) return true;
      return kind === "rooms" || fields.some(([field]) => String(row[field] ?? "").toLocaleLowerCase().includes(query))
        || (kind === "rooms" && String(rowDepartment).toLocaleLowerCase().includes(query));
    });
  }, [rows, fields, kind, search, department]);
  if (!data) return <Loading label="Loading..." wide={1300} />;
  // announcements carry a computed Active / Scheduled / Expired status (rooms already have their own field)
  const extraStatus = rows.length > 0 && rows[0].status !== undefined && !fields.some(([n]) => n === "status");

  return (
    <div className="page" style={{ maxWidth: 1300 }}>
      <h2 className="page-title">{title}</h2>
      <div className="card">
        <h3>{editing ? "Edit room" : "Add"}</h3>
        <form className="inline-form" style={{ width: "100%" }} onSubmit={save}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: "0 14px" }}>
            {fields.map(([name, label, required, type, options]) => {
              const set = (e) => setValues((v) => ({ ...v, [name]: e.target.value }));
              const selectOptions = type === "select" ? [...new Map((options || []).map((option) => {
                const normalized = typeof option === "string"
                  ? { value: option, label: option } : option;
                return [normalized.value, normalized];
              })).values()] : [];
              if (type === "select" && values[name]
                  && !selectOptions.some((option) => option.value === values[name])) {
                selectOptions.push({ value: values[name], label: values[name] });
              }
              return (
                <div key={name} style={type === "textarea" || type === "multiselect" ? { gridColumn: "1 / -1" } : undefined}>
                  <label>{label}{required ? " *" : ""}</label>
                  {type === "textarea" ? (
                    <textarea rows={4} required={required} value={values[name] || ""} onChange={set} />
                  ) : type === "select" ? (
                    <select required={required} value={values[name] || ""} onChange={set}>
                      <option value="">Choose...</option>
                      {selectOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  ) : type === "multiselect" ? (
                    <div className="equipment-options">
                      {[...new Set([...(options || []), ...String(values[name] || "").split(",").map((item) => item.trim()).filter((item) => item && !(options || []).includes(item))])].map((option) => {
                        const selected = String(values[name] || "").split(",").map((item) => item.trim()).filter(Boolean);
                        return <label className="equipment-option" key={option}>
                          <input type="checkbox" checked={selected.includes(option)} onChange={(event) => {
                            const next = event.target.checked
                              ? option === "None" ? [option] : [...selected.filter((item) => item !== "None"), option]
                              : selected.filter((item) => item !== option);
                            setValues((v) => ({ ...v, [name]: next.join(", ") }));
                          }} />{option}
                        </label>;
                      })}
                    </div>
                  ) : (
                    <input type={type === "date" ? "date" : "text"} required={required}
                           value={values[name] || ""} onChange={set} />
                  )}
                </div>
              );
            })}
          </div>
          <button className="btn" style={{ marginTop: 14 }} type="submit">{editing ? "Save changes" : "Add"}</button>
          {editing && <button className="btn secondary" style={{ margin: "14px 0 0 8px" }} type="button" onClick={() => { setEditing(null); setValues({}); }}>Cancel</button>}
        </form>
        {kind === "rooms" && <div className="dataset-toolbar" style={{ marginTop: 16 }}>
          <label>Import rooms from CSV <input type="file" accept=".csv,text/csv" onChange={importRooms} /></label>
          <span className="muted">CSV columns: room_id, name, building, department, room_type, capacity, equipment, status. Up to 25,000 rows per import.</span>
        </div>}
      </div>

      {searchable && (
        <section className="card dataset-list-card">
          <div className="dataset-list-heading">
            <div>
              <h3>{kind === "rooms" ? "Room directory" : "Campus knowledge"}</h3>
              <p>{kind === "rooms"
                ? "Find a room by name, room ID, department, or building. Select a row to edit it."
                : "Search campus topics, keywords, and answers."}</p>
            </div>
            <span className="dataset-count">{kind === "rooms" ? data.pagination?.total ?? rows.length : `${visibleRows.length} of ${rows.length}`}</span>
          </div>
          <div className="dataset-toolbar">
            <label className="dataset-search">
              <span className="sr-only">{kind === "rooms" ? "Search rooms" : "Search campus information"}</span>
              <input type="search" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }}
                placeholder={kind === "rooms" ? "Search room name or ID..." : "Search topics, keywords, or answers..."} />
            </label>
            {kind === "rooms" && <label className="dataset-department-filter">
              <span>Department</span>
              <select value={department} onChange={(event) => { setDepartment(event.target.value); setPage(1); }}>
                <option value="">All departments</option>
                {departments.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>}
            {(search || department) && <button className="btn secondary dataset-clear" type="button"
              onClick={() => { setSearch(""); setDepartment(""); setPage(1); }}>Clear filters</button>}
          </div>
          {rows.length === 0 ? <p className="empty">{kind === "rooms" && (search || department)
            ? "No rooms match this search and department." : empty}</p>
            : visibleRows.length === 0 ? <p className="empty">No entries match this search and department.</p>
              : <div className="table-wrap"><table>
                <thead><tr>{fields.map(([name, label]) => <th key={name}>{label.split(" (")[0]}</th>)}{kind === "announcements" && <th>Posted by</th>}{extraStatus && <th>Status</th>}<th>Actions</th></tr></thead>
                <tbody>
                  {visibleRows.map((r) => (
                    <tr key={r.id}>
                      {fields.map(([name]) => <td key={name} className="desc">{r[name] || "-"}</td>)}
                      {kind === "announcements" && <td>{r.created_by_name || "Administration"} ({r.created_by_role === "super_admin" ? "Super Admin" : "Admin"})</td>}
                      {extraStatus && <td>{r.status}</td>}
                      <td className="dataset-actions">{kind === "rooms" && <button className="btn small" type="button" onClick={() => edit(r)}>Edit</button>} <button className="btn small danger" type="button" onClick={() => remove(r)}>Delete</button></td>
                    </tr>
                  ))}
                </tbody>
              </table></div>}
          {kind === "rooms" && data.pagination?.total > 0 && <div className="dataset-toolbar" aria-label="Room pages">
            <span className="muted">Page {page} of {data.pagination.pages}</span>
            <div><button className="btn secondary" type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button>{" "}
              <button className="btn secondary" type="button" disabled={page >= data.pagination.pages} onClick={() => setPage((value) => value + 1)}>Next</button></div>
          </div>}
        </section>
      )}

      {!searchable && rows.length ? (
        <div className="table-wrap"><table>
          <thead><tr>{fields.map(([name, label]) => <th key={name}>{label.split(" (")[0]}</th>)}{kind === "announcements" && <th>Posted by</th>}{extraStatus && <th>Status</th>}<th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                {fields.map(([name]) => <td key={name} className="desc">{r[name]}</td>)}
                {kind === "announcements" && <td>{r.created_by_name || "Administration"} ({r.created_by_role === "super_admin" ? "Super Admin" : "Admin"})</td>}
                {extraStatus && <td>{r.status}</td>}
                <td>{kind === "rooms" && <button className="btn small" type="button" onClick={() => edit(r)}>Edit</button>} <button className="btn small danger" type="button" onClick={() => remove(r)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : !searchable && <p className="empty">{empty}</p>}
    </div>
  );
}
