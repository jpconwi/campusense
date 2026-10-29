import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Header } from "../components/Layout.jsx";
import RegistrationHelp from "../components/RegistrationHelp.jsx";

export default function Register() {
  const { loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [registrationType, setRegistrationType] = useState("student");
  const [fullName, setFullName] = useState("");
  const [studentId, setStudentId] = useState("");
  const [department, setDepartment] = useState("");
  const [studentDocumentType, setStudentDocumentType] = useState("school_id");
  const [idFile, setIdFile] = useState(null);
  const [idBackFile, setIdBackFile] = useState(null);
  const [corFile, setCorFile] = useState(null);
  const [aiConsent, setAiConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submissionMessage, setSubmissionMessage] = useState("");

  useEffect(() => {
    document.title = "Personal Gmail registration | NEMSU";
    if (loading || user) return;
    api("/api/auth/personal-registration")
      .then((data) => { setEmail(data.email); setFullName(data.google_name || ""); })
      .catch((err) => setError(err.message || "Your registration session expired. Start again from sign in."));
  }, [loading, user]);

  if (!loading && user) return <Navigate to="/" replace />;

  async function submit(event) {
    event.preventDefault();
    setError("");
    const form = new FormData();
    form.append("full_name", fullName);
    if (registrationType === "instructor") {
      if (studentId.trim().length < 3) return setError("Enter your instructor ID number.");
      if (department.trim().length < 2) return setError("Enter your department.");
      form.append("instructor_id", studentId);
      form.append("department", department);
    } else {
      if (studentDocumentType === "school_id" && !idFile) return setError("Capture or choose a photo of your school ID.");
      if (studentDocumentType === "cor" && !corFile) return setError("Capture or choose a photo of your Certificate of Registration.");
      const selectedFiles = studentDocumentType === "school_id" ? [idFile, idBackFile] : [corFile];
      if (selectedFiles.filter(Boolean).some((file) => file.size > 5 * 1024 * 1024)) {
        return setError("Each image must be 5 MB or smaller.");
      }
      form.append("student_id", studentId);
      if (studentDocumentType === "school_id") {
        form.append("school_id_document", idFile);
        if (idBackFile) form.append("school_id_back_document", idBackFile);
      } else {
        form.append("cor_document", corFile);
      }
      form.append("ai_review_consent", aiConsent ? "true" : "false");
    }
    setBusy(true);
    try {
      const result = await api(registrationType === "instructor" ? "/api/auth/instructor-registration" : "/api/auth/student-registration",
        { method: "POST", form });
      setSubmissionMessage(result.message || "Registration submitted.");
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
          <h1>Personal Gmail registration</h1>
          <p className="sub">NEMSU Tandag Main Campus</p>

          {submitted ? (
            <div className="registration-success" role="status">
              <h2>Application submitted</h2>
              <p>{submissionMessage}</p>
              <p>Sign in with <strong>{email}</strong> to continue or check your account status.</p>
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
                    Register as
                    <select value={registrationType} onChange={(e) => setRegistrationType(e.target.value)}>
                      <option value="student">Student</option>
                      <option value="instructor">Instructor</option>
                    </select>
                  </label>
                  <label>
                    Full name
                    <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={120} required />
                  </label>
                  {registrationType === "instructor" ? (
                    <>
                      <label>
                        Instructor ID number
                        <input value={studentId} onChange={(e) => setStudentId(e.target.value)} maxLength={50} required />
                      </label>
                      <label>
                        Department
                        <input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={120} required />
                      </label>
                      <p className="registration-scan-help">Your instructor account will remain pending until an administrator reviews your details.</p>
                    </>
                  ) : (
                    <>
                      <label>
                        NEMSU school ID number
                        <input value={studentId} onChange={(e) => setStudentId(e.target.value)} maxLength={50} required />
                      </label>
                      <label>
                        Document to scan
                        <select value={studentDocumentType} onChange={(e) => {
                          setStudentDocumentType(e.target.value);
                          setIdFile(null); setIdBackFile(null); setCorFile(null);
                        }}>
                          <option value="school_id">NEMSU School ID</option>
                          <option value="cor">Certificate of Registration (COR)</option>
                        </select>
                      </label>
                      <p className="registration-scan-help">Choose either your school ID or your COR, then capture it with your camera or select an image. School ID automatic screening requires front and back; a COR can be screened by itself.</p>
                      {studentDocumentType === "school_id" ? (
                        <>
                          <label>
                            School ID front
                            <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" required
                              onChange={(e) => setIdFile(e.target.files?.[0] || null)} />
                            <small>{idFile ? `Selected: ${idFile.name}` : "JPG, PNG, or WEBP; maximum 5 MB."}</small>
                          </label>
                          <label>
                            School ID back (required for automatic screening)
                            <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
                              onChange={(e) => setIdBackFile(e.target.files?.[0] || null)} />
                            <small>{idBackFile ? `Selected: ${idBackFile.name}` : "Without the back, the application stays pending for admin review."}</small>
                          </label>
                        </>
                      ) : (
                        <label>
                          Certificate of Registration (COR)
                          <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" required
                            onChange={(e) => setCorFile(e.target.files?.[0] || null)} />
                          <small>{corFile ? `Selected: ${corFile.name}` : "JPG, PNG, or WEBP; maximum 5 MB."}</small>
                        </label>
                      )}
                      <label className="registration-consent">
                        <input type="checkbox" checked={aiConsent} onChange={(e) => setAiConsent(e.target.checked)} />
                        <span>I agree to send my scan images to the configured AI provider for visual screening of the NEMSU logo, colors, Tandag campus name, and university president/campus director signature areas. AI ignores names, ID numbers, faces, courses, QR codes, and other personal fields. It does not verify signatures or prove authenticity, so a false match is possible. If all required visual checks pass, my account may be activated automatically; otherwise it stays pending for admin review. Image metadata is removed first, and administrators can view the stored scans.</span>
                      </label>
                    </>
                  )}
                  <button className="btn" type="submit" disabled={busy}>
                    {busy ? "Submitting..." : "Submit registration"}
                  </button>
                </form>
              )}
              <p className="note"><Link to="/login">Return to sign in</Link></p>
            </>
          )}
        </section>
        <RegistrationHelp />
      </div>
    </>
  );
}
