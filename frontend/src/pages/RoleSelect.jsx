import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Header } from "../components/Layout.jsx";
import { useAuth } from "../auth.jsx";
import { api } from "../api.js";
import { landingFor } from "./Login.jsx";

export default function RoleSelect() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");

  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== null) return <Navigate to={landingFor(user)} replace />;

  async function choose(role) {
    try {
      const result = await api("/api/auth/role", { method: "POST", json: { role } });
      await refresh();
      navigate(result.next, { replace: true });
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <Header />
      <div className="center-wrap">
        <div className="login-card">
          <h1>Select your account type</h1>
          <p className="sub">Welcome, {user.name}. Choose one to continue.</p>
          {error && <div className="flash error" role="alert">{error}</div>}

          <div className="role-card">
            <h3>Student</h3>
            <p>Ask campus questions, report concerns, give feedback and request reservations.</p>
            <button className="btn" type="button" onClick={() => choose("student")}>Continue</button>
          </div>
          <div className="role-card">
            <h3>Instructor</h3>
            <p>Everything students can do, plus faculty availability and absence reports.</p>
            <button className="btn" type="button" onClick={() => choose("instructor")}>Continue</button>
          </div>
          <button className="btn ghost small" type="button" onClick={logout}>Use a different account</button>
        </div>
      </div>
    </>
  );
}
