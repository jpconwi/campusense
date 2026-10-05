import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth.jsx";

/** Header + navigation + flash messages around every signed-in page. */
export function Header({ children }) {
  const { user } = useAuth();
  return (
    <header>
      <div className="header-inner">
        <img src="/logo.png" alt="North Eastern Mindanao State University seal" />
        <div className="header-text">
          <h1>CampusSense AI</h1>
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

export default function Layout() {
  const { user, nav, logout } = useAuth();
  const location = useLocation();
  const [chatKey, setChatKey] = useState(0);
  const onChat = location.pathname === "/ai";

  return (
    <>
      <Header>
        {onChat && <button className="header-btn" type="button" onClick={() => setChatKey((k) => k + 1)}>New chat</button>}
      </Header>
      {user && user.role && (
        <nav className="topnav" aria-label="Main navigation">
          <div className="topnav-inner">
            {nav.map((item) => (
              <NavLink key={item.path} to={item.path} end className={({ isActive }) => (isActive ? "active" : "")}>
                {item.label}
              </NavLink>
            ))}
            <form onSubmit={(e) => { e.preventDefault(); logout(); }}>
              <button type="submit">Logout</button>
            </form>
          </div>
        </nav>
      )}
      <Flashes />
      <Outlet context={{ chatKey }} />
    </>
  );
}
