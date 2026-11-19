import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Header } from "../components/Layout.jsx";
import { useAuth } from "../auth.jsx";
import { api } from "../api.js";
import { landingFor } from "./Login.jsx";

export default function RoleSelect() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [department, setDepartment] = useState("");
  const [departmentOptions, setDepartmentOptions] = useState([]);

  useEffect(() => {
    api("/api/auth/department-options")
      .then((data) => setDepartmentOptions(data.department_options || []))
      .catch((err) => setError(err.message));
  }, []);

  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== null) return <Navigate to={landingFor(user)} replace />;

  async function choose(role) {
    if (department.trim().length < 2) {
      setError("Enter your department.");
      return;
    }
    try {
      const result = await api("/api/auth/role", { method: "POST", json: { role, department: department.trim() } });
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
          <label>
            Department
            <select value={department} onChange={(event) => setDepartment(event.target.value)} required>
              <option value="">Select department</option>
              {departmentOptions.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>

          <div className="role-card">
            <h3>Student</h3>
            <p>Ask campus questions, report concerns and give feedback.</p>
            <button className="btn" type="button" onClick={() => choose("student")}>Continue</button>
          </div>
          <div className="role-card">
            <h3>Instructor</h3>
            <p>Everything students can do, plus room reservations, faculty availability and absence reports.</p>
            <button className="btn" type="button" onClick={() => choose("instructor")}>Continue</button>
          </div>
          <button className="btn ghost small" type="button" onClick={logout}>Use a different account</button>
        </div>
      </div>
    </>
  );
}
