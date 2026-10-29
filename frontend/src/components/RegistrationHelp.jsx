import { useState } from "react";
import { api } from "../api.js";

export default function RegistrationHelp({ defaultName = "", defaultEmail = "", defaultApplicantType = "student" }) {
  const [form, setForm] = useState({ name: defaultName, email: defaultEmail,
    applicant_type: defaultApplicantType, category: "Registration", message: "" });
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
      const result = await api("/api/auth/help-messages", { method: "POST", json: form });
      setNotice(result.message || "Your message was sent to the admin inbox.");
      setForm({ name: defaultName, email: defaultEmail, applicant_type: defaultApplicantType,
        category: "Registration", message: "" });
    } catch (err) {
      setError(err.message || "Your message could not be sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="registration-help">
      <summary>Need help? Send a message to an admin</summary>
      <form className="registration-form" onSubmit={submit}>
        <label>Name<input name="name" value={form.name} onChange={update} maxLength={120} required /></label>
        <label>Email for reply<input name="email" type="email" value={form.email} onChange={update} maxLength={255} required /></label>
        <label>Account type
          <select name="applicant_type" value={form.applicant_type} onChange={update}>
            <option value="student">Student</option><option value="instructor">Instructor</option>
          </select>
        </label>
        <label>Help topic
          <select name="category" value={form.category} onChange={update}>
            <option>Registration</option><option>Login or access</option>
            <option>Account deletion</option><option>Other</option>
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
