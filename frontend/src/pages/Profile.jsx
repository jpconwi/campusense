import { useEffect } from "react";
import { useAuth } from "../auth.jsx";
import RegistrationHelp from "../components/RegistrationHelp.jsx";

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
      <section className="card profile-help">
        <h3>Help messages</h3>
        <p className="page-intro">Ask about account access, registration, account deletion, or another issue. An admin can reply to your email.</p>
        <RegistrationHelp defaultName={user.name} defaultEmail={user.email} defaultApplicantType={user.role} />
      </section>
    </div>
  );
}
