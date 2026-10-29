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
  const [idFile, setIdFile] = useState(null);
  const [idBackFile, setIdBackFile] = useState(null);
  const [corFile, setCorFile] = useState(null);
  const [aiConsent, setAiConsent] = useState(false);
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
    if (!idFile && !corFile) return setError("Capture or choose an ID-front or COR image. The ID back alone is not enough.");
    if ([idFile, idBackFile, corFile].filter(Boolean).some((file) => file.size > 5 * 1024 * 1024)) {
      return setError("Each image must be 5 MB or smaller.");
    }

    const form = new FormData();
    form.append("full_name", fullName);
    form.append("student_id", studentId);
    if (idFile) form.append("school_id_document", idFile);
    if (idBackFile) form.append("school_id_back_document", idBackFile);
    if (corFile) form.append("cor_document", corFile);
    form.append("ai_review_consent", aiConsent ? "true" : "false");
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
                  <p className="registration-scan-help">Capture with your camera or choose saved images. Submit the ID front or COR; add the ID back to include its QR code.</p>
                  <label>
                    School ID photo
                    <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
                      onChange={(e) => setIdFile(e.target.files?.[0] || null)} />
                    <small>{idFile ? `Selected: ${idFile.name}` : "JPG, PNG, or WEBP; maximum 5 MB. Camera opens when supported."}</small>
                  </label>
                  <label>
                    School ID back (optional)
                    <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
                      onChange={(e) => setIdBackFile(e.target.files?.[0] || null)} />
                    <small>{idBackFile ? `Selected: ${idBackFile.name}` : "Add the reverse side so AI can check whether a QR code is visible and readable-looking."}</small>
                  </label>
                  <label>
                    Certificate of Registration (COR, optional)
                    <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
                      onChange={(e) => setCorFile(e.target.files?.[0] || null)} />
                    <small>{corFile ? `Selected: ${corFile.name}` : "Add a COR image for the same visual-structure review."}</small>
                  </label>
                  <label className="registration-consent">
                    <input type="checkbox" checked={aiConsent} onChange={(e) => setAiConsent(e.target.checked)} />
                    <span>I agree to send my scan images to the configured AI provider for a visual-structure review of NEMSU branding, campus label, layout, and ID-back QR visibility. AI must ignore names, ID numbers, faces, courses, and other personal fields. It does not decode the QR or verify authenticity against an official template. Image metadata is removed first. Administrators can view the stored scans. AI results may be wrong and do not approve or reject my account. If unchecked, an administrator reviews my documents manually.</span>
                  </label>
                  <button className="btn" type="submit" disabled={busy}>
                    {busy ? "Scanning and submitting..." : "Submit for admin approval"}
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
