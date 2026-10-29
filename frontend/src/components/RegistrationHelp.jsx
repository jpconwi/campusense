import { useState } from "react";
import { api } from "../api.js";

export default function RegistrationHelp() {
  const [form, setForm] = useState({ name: "", email: "", applicant_type: "student", message: "" });
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setNotice("");
    setError("");
    setBusy(true);
    try {
      const result = await api("/api/auth/registration-help", { method: "POST", json: form });
      setNotice(result.message || "Your message was sent to the admin inbox.");
      setForm({ name: "", email: "", applicant_type: form.applicant_type, message: "" });
    } catch (err) {
      setError(err.message || "Your message could not be sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="registration-help">
      <summary>Having trouble creating an account? Message an admin</summary>
      <form className="registration-form" onSubmit={submit}>
        <label>Name<input name="name" value={form.name} onChange={update} maxLength={120} required /></label>
        <label>Email for reply<input name="email" type="email" value={form.email} onChange={update} maxLength={255} required /></label>
        <label>Applying as
          <select name="applicant_type" value={form.applicant_type} onChange={update}>
            <option value="student">Student</option><option value="instructor">Instructor</option>
          </select>
        </label>
        <label>How can we help?
          <textarea name="message" value={form.message} onChange={update} maxLength={2000} rows={4} required />
        </label>
        {error && <div className="flash error" role="alert">{error}</div>}
        {notice && <div className="flash info" role="status">{notice}</div>}
        <button className="btn" type="submit" disabled={busy}>{busy ? "Sending..." : "Send message"}</button>
        <small className="registration-scan-help">An administrator can review your message and reply to the email you provide.</small>
      </form>
    </details>
  );
}
