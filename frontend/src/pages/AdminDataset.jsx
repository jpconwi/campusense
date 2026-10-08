import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

/** Rooms, Campus Information and Announcements: add a row, list rows, delete a row. */
export default function AdminDataset({ kind }) {            // kind = "rooms" | "campus" | "announcements"
  const { setFlash } = useAuth();
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});

  const load = useCallback(() => { api(`/api/admin/${kind}`).then(setData).catch(() => {}); }, [kind]);
  useEffect(() => { setData(null); setValues({}); load(); }, [load]);
  useEffect(() => { if (data) document.title = `${data.title} | NEMSU`; }, [data]);

  async function add(e) {
    e.preventDefault();
    try {
      const r = await api(`/api/admin/${kind}`, { method: "POST", json: values });
      setFlash({ text: r.message, kind: "info" });
      setValues({});
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  async function remove(row) {
    if (!window.confirm("Delete this row?")) return;
    try {
      const r = await api(`/api/admin/${kind}/${row.id}`, { method: "DELETE" });
      setFlash({ text: r.message, kind: "info" });
    } catch (err) { setFlash({ text: err.message, kind: "error" }); }
    load();
  }

  if (!data) return <div className="page" style={{ maxWidth: 1300 }} />;
  const { title, fields, rows, empty } = data;
  // announcements carry a computed Active / Scheduled / Expired status (rooms already have their own field)
  const extraStatus = rows.length > 0 && rows[0].status !== undefined && !fields.some(([n]) => n === "status");

  return (
    <div className="page" style={{ maxWidth: 1300 }}>
      <h2 className="page-title">{title}</h2>
      <div className="card">
        <h3>Add</h3>
        <form className="inline-form" style={{ width: "100%" }} onSubmit={add}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: "0 14px" }}>
            {fields.map(([name, label, required, type, options]) => {
              const set = (e) => setValues((v) => ({ ...v, [name]: e.target.value }));
              return (
                <div key={name} style={type === "textarea" ? { gridColumn: "1 / -1" } : undefined}>
                  <label>{label}{required ? " *" : ""}</label>
                  {type === "textarea" ? (
                    <textarea rows={4} required={required} value={values[name] || ""} onChange={set} />
                  ) : type === "select" ? (
                    <select required={required} value={values[name] || ""} onChange={set}>
                      <option value="">Choose...</option>
                      {options.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input type={type === "date" ? "date" : "text"} required={required}
                           value={values[name] || ""} onChange={set} />
                  )}
                </div>
              );
            })}
          </div>
          <button className="btn" style={{ marginTop: 14 }} type="submit">Add</button>
        </form>
      </div>

      {rows.length ? (
        <div className="table-wrap"><table>
          <thead><tr>{fields.map(([name, label]) => <th key={name}>{label.split(" (")[0]}</th>)}{extraStatus && <th>Status</th>}<th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                {fields.map(([name]) => <td key={name} className="desc">{r[name]}</td>)}
                {extraStatus && <td>{r.status}</td>}
                <td><button className="btn small danger" type="button" onClick={() => remove(r)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : <p className="empty">{empty}</p>}
    </div>
  );
}
