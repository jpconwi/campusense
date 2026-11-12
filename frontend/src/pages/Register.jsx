import { useEffect, useRef, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Header } from "../components/Layout.jsx";
import RegistrationHelp from "../components/RegistrationHelp.jsx";
import FaceScanner from "../components/FaceScanner.jsx";
import DocumentScanner from "../components/DocumentScanner.jsx";

export default function Register() {
  const { loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [registrationType, setRegistrationType] = useState("student");
  const [fullName, setFullName] = useState("");
  const [studentId, setStudentId] = useState("");
  const [department, setDepartment] = useState("");
  const [faceFiles, setFaceFiles] = useState(null);
  const [faceConsent, setFaceConsent] = useState(false);
  const [studentDocumentType, setStudentDocumentType] = useState("school_id");
  const [idFile, setIdFile] = useState(null);
  const [idBackFile, setIdBackFile] = useState(null);
  const [corFile, setCorFile] = useState(null);
  const [aiConsent, setAiConsent] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractionMessage, setExtractionMessage] = useState("");
  const extractionRequest = useRef(0);
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

  async function extractStudentInfo(file, consentGranted = aiConsent, type = registrationType) {
    if (!file || !consentGranted || type !== "student") return;
    const requestId = ++extractionRequest.current;
    setExtracting(true);
    setFullName("");
    setStudentId("");
    setExtractionMessage("Reading the name and student ID from your document...");
    const form = new FormData();
    form.append("scan_document", file);
    form.append("consent", "true");
    try {
      const result = await api("/api/auth/student-registration/extract", { method: "POST", form });
      if (requestId !== extractionRequest.current) return;
      if (result.full_name) setFullName(result.full_name);
      if (result.student_id) setStudentId(result.student_id);
      setExtractionMessage(result.message || "Check the detected values before submitting.");
    } catch (err) {
      if (requestId === extractionRequest.current) setExtractionMessage(err.message || "Could not read this document. Enter the values manually.");
    } finally {
      if (requestId === extractionRequest.current) setExtracting(false);
    }
  }

  function captureIdFront(file) {
    setIdFile(file);
    if (!file) setIdBackFile(null);
    extractionRequest.current += 1;
    setExtracting(false);
    if (file) extractStudentInfo(file);
  }

  function captureIdBack(file) {
    setIdBackFile(file);
  }

  function captureCor(file) {
    setCorFile(file);
    extractionRequest.current += 1;
    setExtracting(false);
    if (file) extractStudentInfo(file);
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    const form = new FormData();
    form.append("full_name", fullName);
    if (!faceFiles?.front) return setError("Complete the front-facing selfie scan.");
    if (faceFiles.front.size > 5 * 1024 * 1024) return setError("The selfie must be 5 MB or smaller.");
    if (!faceConsent) return setError("Consent is required to store your selfie for administrator review.");
    form.append("face_photo_front", faceFiles.front);
    form.append("face_photo_consent", "true");
    if (registrationType === "instructor") {
      if (studentId.trim().length < 3) return setError("Enter your instructor ID number.");
      if (department.trim().length < 2) return setError("Enter your department.");
      form.append("instructor_id", studentId);
      form.append("department", department);
    } else {
      if (fullName.trim().length < 3) return setError("Check the full name detected from your document.");
      if (studentId.trim().length < 3) return setError("Check the student ID detected from your document.");
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
      <div className="center-wrap registration-page">
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
                    <select value={registrationType} onChange={(e) => {
                      const next = e.target.value;
                      setRegistrationType(next);
                      setStudentId("");
                      extractionRequest.current += 1;
                      setExtracting(false);
                      if (next === "student") extractStudentInfo(studentDocumentType === "school_id" ? idFile : corFile, aiConsent, next);
                    }}>
                      <option value="student">Student</option>
                      <option value="instructor">Instructor</option>
                    </select>
                  </label>
                  <label className="registration-consent">
                    <input type="checkbox" checked={faceConsent} required onChange={(e) => setFaceConsent(e.target.checked)} />
                    <span>I consent to an AI check for face visibility and framing. One selfie will be saved for administrator review; the AI does not identify me or compare my face with my ID.</span>
                  </label>
                  <FaceScanner onComplete={setFaceFiles} disabled={busy || !faceConsent} />
                  {registrationType === "instructor" ? (
                    <>
                      <label>
                        Full name
                        <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={120} required />
                      </label>
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
                        Document to scan
                        <select value={studentDocumentType} onChange={(e) => {
                          setStudentDocumentType(e.target.value);
                          setIdFile(null); setIdBackFile(null); setCorFile(null);
                          setStudentId(""); setFullName(""); setExtractionMessage(""); setExtracting(false);
                          extractionRequest.current += 1;
                        }}>
                          <option value="school_id">NEMSU School ID</option>
                          <option value="cor">Certificate of Registration (COR)</option>
                        </select>
                      </label>
                      <p className="registration-scan-help">To autofill your name and student ID, choose a document and agree to AI reading below. The fields remain editable if the result needs correction.</p>
                      <p className="registration-scan-help">Center the full document inside the guide. The camera captures automatically when the image is clear and steady. School ID screening uses front and back; a COR can be screened by itself.</p>
                      {studentDocumentType === "school_id" ? (
                        <>
                          <div className="document-scan-field">
                            <strong>School ID front</strong>
                            <DocumentScanner label="school ID front" kind="id" value={idFile}
                              enabled={Boolean(faceFiles?.front) && !busy} onCapture={captureIdFront} />
                            {!idFile && <small>JPG, PNG, or WEBP; maximum 5 MB.</small>}
                          </div>
                          <div className="document-scan-field">
                            <strong>School ID back (needed for automatic screening)</strong>
                            <DocumentScanner label="school ID back" kind="id" value={idBackFile}
                              enabled={Boolean(faceFiles?.front && idFile) && !busy} onCapture={captureIdBack} />
                            {!idBackFile && <small>Without the back, the application stays pending for admin review.</small>}
                          </div>
                        </>
                      ) : (
                        <div className="document-scan-field">
                          <strong>Certificate of Registration (COR)</strong>
                          <DocumentScanner label="certificate of registration" kind="cor" value={corFile}
                            enabled={Boolean(faceFiles?.front) && !busy} onCapture={captureCor} />
                          {!corFile && <small>JPG, PNG, or WEBP; maximum 5 MB.</small>}
                        </div>
                      )}
                      <label className="registration-consent">
                        <input type="checkbox" checked={aiConsent} onChange={(e) => {
                          const consent = e.target.checked;
                          setAiConsent(consent);
                          if (consent) extractStudentInfo(studentDocumentType === "school_id" ? idFile : corFile, true, "student");
                          else { extractionRequest.current += 1; setExtracting(false); setExtractionMessage("AI autofill is off. You can enter your name and student ID manually."); }
                        }} />
                        <span>I consent to AI screening my ID/COR and extracting my printed name and student ID for autofill. Clear matches may be auto-approved; unclear or mismatched results go to an administrator. This screening does not verify document authenticity or signatures. Metadata is removed before processing, and administrators can view my scans.</span>
                      </label>
                      {extracting && <p className="registration-scan-help" role="status">Reading your document...</p>}
                      {extractionMessage && <p className="registration-scan-help" role="status">{extractionMessage}</p>}
                      <h3 className="registration-scan-result-title">Scan result</h3>
                      <p className="registration-scan-help">Check the detected values and correct them if needed.</p>
                      <label>
                        Full name
                        <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={120} required />
                      </label>
                      <label>
                        Student ID number
                        <input value={studentId} onChange={(e) => setStudentId(e.target.value)} maxLength={50} required />
                      </label>
                    </>
                  )}
                  <button className="btn" type="submit" disabled={busy || extracting}>
                    {busy ? "Submitting..." : extracting ? "Reading document..." : "Submit registration"}
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
