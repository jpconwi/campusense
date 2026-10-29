import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Header } from "../components/Layout.jsx";

export default function Register() {
  const { loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [studentId, setStudentId] = useState("");
  const [evidenceFile, setEvidenceFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    document.title = "Student registration | NEMSU";
    if (loading || user) return;
    api("/api/auth/student-registration")
      .then((data) => setEmail(data.email))
      .catch((err) => setError(err.message || "Your registration session expired. Start again from sign in."));
  }, [loading, user]);

  if (!loading && user) return <Navigate to="/" replace />;

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!evidenceFile) return setError("Choose a clear photo or PDF of your school ID or COR.");
    if (evidenceFile.size > 5 * 1024 * 1024) return setError("The file must be 5 MB or smaller.");

    const form = new FormData();
    form.append("full_name", fullName);
    form.append("student_id", studentId);
    form.append("document", evidenceFile);
    setBusy(true);
    try {
      await api("/api/auth/student-registration", { method: "POST", form });
      setSubmitted(true);
    } catch (err) {
      setError(err.message || "Registration could not be submitted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Header />
      <div className="center-wrap">
        <section className="login-card register-card">
          <img src="/logo.png" alt="NEMSU seal" />
          <h1>Student registration</h1>
          <p className="sub">NEMSU Tandag Main Campus</p>

          {submitted ? (
            <div className="registration-success" role="status">
              <h2>Application submitted</h2>
              <p>Your account is pending admin review. You can sign in with <strong>{email}</strong> after it is approved.</p>
              <Link className="btn" to="/login">Back to sign in</Link>
            </div>
          ) : (
            <>
              {email && <p className="registration-email">Personal Gmail: <strong>{email}</strong></p>}
              {error && <div className="flash error" role="alert">{error}</div>}
              {!email ? (
                <p className="note">Start registration from the sign-in page using a verified personal Gmail account.</p>
              ) : (
                <form className="registration-form" onSubmit={submit}>
                  <label>
                    Full name as shown on your school ID or COR
                    <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={120} required />
                  </label>
                  <label>
                    NEMSU school ID number
                    <input value={studentId} onChange={(e) => setStudentId(e.target.value)} maxLength={50} required />
                  </label>
                  <label>
                    NEMSU Tandag Main Campus school ID or Certificate of Registration
                    <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf,.jpg,.jpeg,.png,.webp,.pdf"
                      onChange={(e) => setEvidenceFile(e.target.files?.[0] || null)} required />
                    <small>JPG, PNG, WEBP, or PDF. Maximum 5 MB. Only administrators can view this file.</small>
                  </label>
                  <button className="btn" type="submit" disabled={busy}>
                    {busy ? "Submitting..." : "Submit for admin approval"}
                  </button>
                </form>
              )}
              <p className="note"><Link to="/login">Return to sign in</Link></p>
            </>
          )}
        </section>
      </div>
    </>
  );
}
