import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { api } from "../api.js";

export default function Home() {
  const { user } = useAuth();
  const [counts, setCounts] = useState({ concerns: 0, reports: 0, reservations: 0 });

  useEffect(() => { document.title = "Home | NEMSU"; }, []);
  useEffect(() => {
    if (user.role !== "admin") api("/api/home").then((d) => setCounts(d.counts)).catch(() => {});
  }, [user.role]);

  if (user.role === "admin") return <Navigate to="/admin" replace />;

  return (
    <div className="page">
      <h2 className="page-title">Welcome, {user.name.split(" ")[0]}</h2>
      <p className="page-intro">What would you like to do today?</p>
      <div className="grid">
        <Link className="tile" to="/ai"><strong>Campus AI</strong><span>Ask about rooms, facilities, locations and instructors.</span></Link>
        <Link className="tile" to="/concerns"><strong>My Concerns</strong><span>Report a problem. {counts.concerns} pending.</span></Link>
        <Link className="tile" to="/reports"><strong>My Reports</strong><span>Submit a campus report. {counts.reports} pending.</span></Link>
        <Link className="tile" to="/feedback"><strong>Feedback</strong><span>Share your thoughts about a campus area.</span></Link>
        <Link className="tile" to="/reservations"><strong>Reservations</strong><span>Request a room or facility. {counts.reservations} pending.</span></Link>
        {user.role === "instructor" && (
          <Link className="tile" to="/faculty"><strong>Faculty Availability</strong><span>Report an absence or mark yourself available.</span></Link>
        )}
        <Link className="tile" to="/profile"><strong>Profile</strong><span>Your account details.</span></Link>
      </div>
    </div>
  );
}
