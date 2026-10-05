import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { Header } from "../components/Layout.jsx";
import NotFound from "./NotFound.jsx";
import { useAuth } from "../auth.jsx";
import { api } from "../api.js";

/** /admin/login/<secret> - email + password. A wrong secret shows the normal 404 page. */
export default function AdminLogin() {
  const { secret } = useParams();
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState("checking");     // checking | ok | missing | admin
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Admin sign in | NEMSU";
    api(`/api/admin/login/${encodeURIComponent(secret)}`)
      .then((r) => setState(r.already_admin ? "admin" : "ok"))
      .catch(() => setState("missing"));
  }, [secret]);

  if (state === "checking") return null;
  if (state === "missing") return <NotFound />;
  if (state === "admin") return <Navigate to="/admin" replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api(`/api/admin/login/${encodeURIComponent(secret)}`,
        { method: "POST", json: { email, password } });
      await refresh();
      navigate(result.next, { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const input = { width: "100%", padding: 10, border: "1px solid var(--line)", borderRadius: 8, font: "inherit" };
  return (
    <>
      <Header />
      <div className="center-wrap">
        <div className="login-card">
          <img src="/logo.png" alt="NEMSU seal" />
          <h1>Admin sign in</h1>
          <p className="sub">Authorized administrators only</p>
          {error && <div className="flash error" role="alert">{error}</div>}
          <form onSubmit={submit} autoComplete="off" style={{ textAlign: "left" }}>
            <label htmlFor="email" style={{ fontWeight: 700 }}>Email</label>
            <input id="email" type="email" required autoFocus maxLength={200} value={email}
                   onChange={(e) => setEmail(e.target.value)} style={{ ...input, margin: "4px 0 14px" }} />
            <label htmlFor="password" style={{ fontWeight: 700 }}>Password</label>
            <input id="password" type="password" required maxLength={200} autoComplete="current-password"
                   value={password} onChange={(e) => setPassword(e.target.value)} style={{ ...input, margin: "4px 0 18px" }} />
            <button className="btn" type="submit" disabled={busy} style={{ width: "100%", padding: 12 }}>Sign in</button>
          </form>
        </div>
      </div>
    </>
  );
}
