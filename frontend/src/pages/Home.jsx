import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { api } from "../api.js";
import { Icon, PATHS } from "../components/Ui.jsx";
import { Sk } from "../components/Skeletons.jsx";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function Home() {
  const { user } = useAuth();
  const [counts, setCounts] = useState(null);   // null = still loading

  useEffect(() => { document.title = "Home | NEMSU"; }, []);
  useEffect(() => {
    if (user.role !== "admin") api("/api/home").then((d) => setCounts(d.counts)).catch(() => setCounts({ concerns: 0, reports: 0, reservations: 0 }));
  }, [user.role]);

  if (user.role === "admin") return <Navigate to="/admin" replace />;

  const instructor = user.role === "instructor";
  const tiles = [
    { to: "/ai", title: "Campus AI", icon: PATHS.chat, tone: "blue", wide: true,
      text: "Ask about rooms, facilities, locations and instructors. You can type, speak or send a photo." },
    { to: "/concerns", title: "My Concerns", icon: PATHS.concern, tone: "amber", track: true, pending: counts && counts.concerns,
      text: "Report a problem." },
    { to: "/reports", title: "My Reports", icon: PATHS.report, tone: "teal", track: true, pending: counts && counts.reports,
      text: "Submit a campus report." },
    { to: "/feedback", title: "Feedback", icon: PATHS.feedback, tone: "violet",
      text: "Share your thoughts about a campus area." },
    ...(instructor ? [
      { to: "/reservations", title: "Reservations", icon: PATHS.reserve, tone: "green", track: true, pending: counts && counts.reservations,
        text: "Request a room or facility." },
      { to: "/faculty", title: "Faculty Availability", icon: PATHS.faculty, tone: "blue",
        text: "Report an absence or mark yourself available." },
    ] : []),
    { to: "/profile", title: "Profile", icon: PATHS.profile, tone: "slate", text: "Your account details." },
  ];

  return (
    <div className="page home">
      <section className="hero">
        <div className="hero-text">
          <p className="hero-eyebrow">{greeting()}</p>
          <h2 className="page-title">Welcome, {user.name.split(" ")[0]}</h2>
          <p className="page-intro">What would you like to do today?</p>
          <div className="hero-actions">
            <Link className="btn gold" to="/ai"><Icon d={PATHS.chat} size={18} /> Ask Campus AI</Link>
            <Link className="btn ghost-light" to="/concerns"><Icon d={PATHS.concern} size={18} /> Report a problem</Link>
          </div>
        </div>
        <img className="hero-logo" src="/logo.png" alt="" />
      </section>

      <div className="tiles">
        {tiles.map((t) => (
          <Link key={t.to} className={`tile2 tone-${t.tone}` + (t.wide ? " wide" : "")} to={t.to}>
            <span className="tile-ico"><Icon d={t.icon} size={22} /></span>
            <span className="tile-body">
              <strong>{t.title}</strong>
              <span>{t.text}</span>
            </span>
            {t.track && !counts && <Sk className="pill-sk" h={20} w={64} r={999} />}
            {t.pending > 0 && <span className="pill" title="Waiting for an administrator">{t.pending} pending</span>}
            <span className="tile-go" aria-hidden="true"><Icon d={PATHS.arrow} size={18} /></span>
          </Link>
        ))}
      </div>
    </div>
  );
}
