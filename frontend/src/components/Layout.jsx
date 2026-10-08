import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

/** Header + navigation + flash messages around every signed-in page. */
export function Header({ children }) {
  const { user } = useAuth();
  return (
    <header>
      <div className="header-inner">
        <img src="/logo.png" alt="North Eastern Mindanao State University seal" />
        <div className="header-text">
          <h1>NEMSAI</h1>
          <p>NEMSU Tandag Main Campus Assistant</p>
        </div>
        {children}
        {user && (
          <div className="userbox">
            <strong>{user.name}</strong>
            <span>{user.email}</span><br />
            {user.role && <span className="role-pill">{user.role}</span>}
          </div>
        )}
      </div>
    </header>
  );
}

export function Flashes() {
  const { flash, setFlash } = useAuth();
  const location = useLocation();
  // a message disappears when the person moves to another page
  useEffect(() => { setFlash(null); }, [location.pathname]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!flash) return null;
  return <div className="flashes"><div className={"flash " + flash.kind}>{flash.text}</div></div>;
}

const ICONS = {
  "/": "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  "/ai": "M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.5A8 8 0 1 1 21 12z",
  "/reports": "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6",
  "/concerns": "M12 3l10 18H2zM12 10v5M12 18v.5",
  "/feedback": "M4 5h16v11H9l-5 4zM8 9h8M8 12h5",
  "/reservations": "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  "/profile": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  "/faculty": "M3 9l9-5 9 5-9 5zM7 12v5c3 2 7 2 10 0v-5",
  "/admin": "M4 4h7v7H4zM13 4h7v4h-7zM13 11h7v9h-7zM4 14h7v6H4z",
};
const FALLBACK_ICON = "M12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0";

function Icon({ d }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
  );
}

export default function Layout() {
  const { user, nav, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [chatKey, setChatKey] = useState(0);
  const [collapsed, setCollapsed] = useState(false);   // desktop: icons only
  const [open, setOpen] = useState(false);             // mobile: drawer

  useEffect(() => { setOpen(false); }, [location.pathname]);

  function newChat() {
    setChatKey((k) => k + 1);
    if (location.pathname !== "/ai") navigate("/ai");
    setOpen(false);
  }

  const showNav = user && user.role;
  const initials = (user?.name || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className={"shell" + (collapsed ? " collapsed" : "") + (open ? " drawer-open" : "")}>
      <div className="scrim" onClick={() => setOpen(false)} />
      <aside className="sidebar" aria-label="Main navigation">
        <div className="sb-top">
          <img src="/logo.png" alt="NEMSU seal" />
          <div className="sb-brand"><strong>NEMSAI</strong><span>NEMSU Tandag</span></div>
          <button type="button" className="sb-toggle" onClick={() => setCollapsed((c) => !c)}
                  aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
            <Icon d={collapsed ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"} />
          </button>
        </div>
        {showNav && (
          <button type="button" className="sb-new" onClick={newChat} title="New chat">
            <Icon d="M12 5v14M5 12h14" /><span className="lbl">New chat</span>
          </button>
        )}
        {showNav && (
          <nav className="sb-nav">
            {nav.map((item) => (
              <NavLink key={item.path} to={item.path} end title={item.label}
                       className={({ isActive }) => (isActive ? "active" : "")}>
                <Icon d={ICONS[item.path] || FALLBACK_ICON} /><span className="lbl">{item.label}</span>
              </NavLink>
            ))}
          </nav>
        )}
        {user && (
          <div className="sb-bottom">
            <div className="sb-user" title={user.email}>
              <span className="sb-avatar">{initials}</span>
              <span className="lbl sb-userinfo">
                <strong>{user.name}</strong>
                <small>{user.email}</small>
                {user.role && <em className="role-pill">{user.role}</em>}
              </span>
            </div>
            <button type="button" className="sb-logout" onClick={() => logout()} title="Logout">
              <Icon d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9" /><span className="lbl">Logout</span>
            </button>
          </div>
        )}
      </aside>

      <div className="main">
        <div className="mobilebar">
          <button type="button" onClick={() => setOpen(true)} aria-label="Open menu"><Icon d="M4 6h16M4 12h16M4 18h16" /></button>
          <strong>NEMSU AI</strong>
          <button type="button" className="mb-profile" onClick={() => navigate("/profile")} aria-label="Profile">
            <span className="sb-avatar">{initials}</span>
          </button>
        </div>
        <Flashes />
        <Outlet context={{ chatKey }} />
      </div>
    </div>
  );
}
