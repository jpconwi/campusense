import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Header } from "../components/Layout.jsx";
import RegistrationHelp from "../components/RegistrationHelp.jsx";
import FaceScanner from "../components/FaceScanner.jsx";

/** NEMSU students/instructors complete the guided face scan, then sign in right away. */
export default function NemsuRegister() {
  const { loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("student");
  const [fullName, setFullName] = useState("");
  const [faceFiles, setFaceFiles] = useState(null);
  const [faceConsent, setFaceConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    document.title = "NEMSU account setup | NEMSU";
    if (loading || user) return;
    api("/api/auth/nemsu-registration")
      .then((data) => { setEmail(data.email); setFullName(data.google_name || ""); })
      .catch((err) => setError(err.message || "Your registration session expired. Start again from sign in."));
  }, [loading, user]);

  if (!loading && user) return <Navigate to="/" replace />;

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!faceFiles?.front) return setError("Complete the front-facing selfie scan.");
    if (faceFiles.front.size > 5 * 1024 * 1024) return setError("The selfie must be 5 MB or smaller.");
    if (!faceConsent) return setError("Consent is required to store your selfie for administrator review.");
    if (fullName.trim().length < 3) return setError("Enter your full name.");
    const form = new FormData();
    form.append("full_name", fullName);
    form.append("role", role);
    form.append("face_photo_front", faceFiles.front);
    form.append("face_photo_consent", "true");
    setBusy(true);
    try {
      const result = await api("/api/auth/nemsu-registration", { method: "POST", form });
      window.location.assign(result.next || "/");      // already signed in; reload as the new user
    } catch (err) {
      setError(err.message || "Registration could not be submitted.");
      setBusy(false);
    }
  }

  return (
    <>
      <Header />
      <div className="center-wrap registration-page">
        <section className="login-card register-card">
          <img src="/logo.png" alt="NEMSU seal" />
          <h1>NEMSU account setup</h1>
          <p className="sub">NEMSU Tandag Main Campus</p>
          <p className="registration-email">NEMSU Google account: <strong>{email || "verifying..."}</strong></p>
          <p className="note">
            Complete the guided face scan to activate your NEMSU account. You can sign in right after the scan.
            A report manager then checks your account before the super admin reviews it.
          </p>
          {error && <div className="flash error" role="alert">{error}</div>}
          {email && (
            <form className="registration-form" onSubmit={submit}>
              <label>
                Register as
                <select value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="student">Student</option>
                  <option value="instructor">Instructor</option>
                </select>
              </label>
              <label>
                Full name
                <input value={fullName} onChange={(event) => setFullName(event.target.value)} maxLength={120} required />
              </label>
              <label className="registration-consent">
                <input type="checkbox" checked={faceConsent} required onChange={(event) => setFaceConsent(event.target.checked)} />
                <span>I consent to the configured AI provider checking only face visibility and framing during capture. One front-facing selfie is saved with my account for administrator review. The AI does not identify me or compare my face to any document.</span>
              </label>
              <FaceScanner onComplete={setFaceFiles} disabled={busy || !faceConsent} />
              <button className="btn" type="submit" disabled={busy}>
                {busy ? "Activating account..." : "Finish and sign in"}
              </button>
            </form>
          )}
          <p className="note"><Link to="/login">Return to sign in</Link></p>
        </section>
        <RegistrationHelp />
      </div>
    </>
  );
}
