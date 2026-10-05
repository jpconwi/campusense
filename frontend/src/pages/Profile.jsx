import { useEffect } from "react";
import { useAuth } from "../auth.jsx";

export default function Profile() {
  const { user } = useAuth();
  useEffect(() => { document.title = "Profile | NEMSU"; }, []);
  return (
    <div className="page">
      <h2 className="page-title">Profile</h2>
      <p className="page-intro">Your details come from your NEMSU Google account.</p>
      <div className="card">
        <dl className="profile">
          <dt>Name</dt><dd>{user.name}</dd>
          <dt>Email</dt><dd>{user.email}</dd>
          <dt>Account type</dt><dd><span className="role-pill">{user.role}</span></dd>
          <dt>Member since</dt><dd>{user.created_at}</dd>
          <dt>Last login</dt><dd>{user.last_login}</dd>
        </dl>
        <p className="page-intro" style={{ margin: "14px 0 0" }}>Need a different account type? Ask an administrator to change it.</p>
      </div>
    </div>
  );
}
