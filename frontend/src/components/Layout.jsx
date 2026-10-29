import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { api } from "../api.js";
import { HistorySkeleton } from "./Skeletons.jsx";

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
  "/admin/users": "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20a6 6 0 0 1 12 0M16 11a2.5 2.5 0 1 0 0-5M17 15a5 5 0 0 1 4 5",
  "/admin/concerns": "M12 3l10 18H2zM12 10v5M12 18v.5",
  "/admin/reports": "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6",
  "/admin/faculty": "M3 9l9-5 9 5-9 5zM7 12v5c3 2 7 2 10 0v-5",
  "/admin/feedback": "M4 5h16v11H9l-5 4zM8 9h8M8 12h5",
  "/admin/reservations": "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  "/admin/rooms": "M5 21V4l10-1.5V21M3 21h18M12 12v.5",
  "/admin/campus": "M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21zM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  "/admin/announcements": "M3 11v3l12 5V6zM15 8a4 4 0 0 1 0 8M6 14l1.5 6h3L9 15",
};
const FALLBACK_ICON = "M12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0";

function Icon({ d }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
  );
}

const TRASH = "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3";
const CHAT = "M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.5A8 8 0 1 1 21 12z";
const SEARCH = "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.5-4.5";

/** Which group of the history list a chat belongs to. */
function bucket(iso) {
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const age = Math.round((day(new Date()) - day(new Date(iso))) / 86400000);
  if (age <= 0) return "Today";
  if (age === 1) return "Yesterday";
  if (age < 7) return "Previous 7 days";
  return "Earlier";
}
const BUCKETS = ["Today", "Yesterday", "Previous 7 days", "Earlier"];

/** Sidebar list of saved chats (kept for a few days, then deleted automatically). */
function ChatHistory({ activeId, tick, onOpen, onDeleted }) {
  const [data, setData] = useState({ chats: [], keep_days: 3 });
  const [loading, setLoading] = useState(true);       // skeleton only on the first load
  const [failed, setFailed] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    let alive = true;
    api("/api/chats")
      .then((d) => { if (alive) { setData(d); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tick]);

  async function remove(e, id) {
    e.stopPropagation();
    try { await api(`/api/chats/${id}`, { method: "DELETE" }); } catch { /* already gone */ }
    setData((d) => ({ ...d, chats: d.chats.filter((c) => c.id !== id) }));
    onDeleted(id);
  }
  async function clearAll() {
    if (!window.confirm("Delete all of your saved chats?")) return;
    try { await api("/api/chats", { method: "DELETE" }); } catch { /* ignore */ }
    setData((d) => ({ ...d, chats: [] }));
    onDeleted(null);
  }

  const shown = data.chats.filter((c) => c.title.toLowerCase().includes(q.trim().toLowerCase()));
  const groups = BUCKETS.map((name) => [name, shown.filter((c) => bucket(c.updated_at) === name)]).filter(([, l]) => l.length);

  return (
    <section className="sb-history lbl" aria-label="Chat history">
      <div className="sb-history-head">
        <strong>Recent chats</strong>
        {data.chats.length > 0 && <button type="button" className="sb-clear" onClick={clearAll}>Clear all</button>}
      </div>

      {data.chats.length > 5 && (
        <label className="sb-search">
          <Icon d={SEARCH} />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" aria-label="Search chats" />
        </label>
      )}

      {loading ? (
        <HistorySkeleton />
      ) : failed && data.chats.length === 0 ? (
        <p className="sb-history-empty">Could not load your chats.</p>
      ) : data.chats.length === 0 ? (
        <div className="sb-history-empty-box">
          <Icon d={CHAT} />
          <p>No saved chats yet.<br />Ask something and it shows up here.</p>
        </div>
      ) : groups.length === 0 ? (
        <p className="sb-history-empty">No chats match "{q}".</p>
      ) : (
        <div className="sb-history-scroll">
          {groups.map(([name, list]) => (
            <div className="sb-bucket" key={name}>
              <h4>{name}</h4>
              <ul className="sb-history-list">
                {list.map((c) => (
                  <li key={c.id}>
                    <button type="button" className={"sb-chat" + (c.id === activeId ? " active" : "")}
                            onClick={() => onOpen(c.id)} title={c.title} aria-current={c.id === activeId ? "true" : undefined}>
                      <span className="sb-chat-title">{c.title}</span>
                      <span className="sb-chat-del" role="button" tabIndex={0} aria-label={`Delete chat ${c.title}`}
                            onClick={(e) => remove(e, c.id)}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); remove(e, c.id); } }}>
                        <Icon d={TRASH} />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className="sb-history-note">Chats are deleted automatically after {data.keep_days} days.</p>
    </section>
  );
}

// Sidebar sections. The server sends a flat list; the groups are decided here by path.
const GROUPS = {
  "/": "Menu", "/ai": "Menu", "/admin": "Overview",
  "/reports": "My records", "/concerns": "My records", "/feedback": "My records",
  "/reservations": "My records", "/faculty": "My records",
  "/profile": "Account",
  "/admin/concerns": "Inbox", "/admin/reports": "Inbox", "/admin/faculty": "Inbox",
  "/admin/feedback": "Inbox", "/admin/reservations": "Inbox",
  "/admin/users": "Manage", "/admin/rooms": "Manage", "/admin/campus": "Manage", "/admin/announcements": "Manage",
};
function groupNav(nav, role) {
  const out = [];
  for (const item of nav) {
    // Campus AI sits with the overview for admins
    const name = item.path === "/ai" && role === "admin" ? "Overview" : GROUPS[item.path] || "More";
    let g = out.find((x) => x.name === name);
    if (!g) { g = { name, items: [] }; out.push(g); }
    g.items.push(item);
  }
  const ORDER = ["Menu", "Overview", "Inbox", "Manage", "My records", "Account", "More"];
  return out.sort((a, b) => ORDER.indexOf(a.name) - ORDER.indexOf(b.name));
}

export default function Layout() {
  const { user, nav, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [chat, setChat] = useState({ key: 0, id: null });   // key changes = open / reset the chat window
  const [historyTick, setHistoryTick] = useState(0);          // bump = reload the history list
  const [collapsed, setCollapsed] = useState(false);   // desktop: icons only
  const [open, setOpen] = useState(false);             // mobile: drawer

  useEffect(() => { setOpen(false); }, [location.pathname]);

  function openChat(id) {                // id = null starts a new chat
    setChat((c) => ({ key: c.key + 1, id }));
    if (location.pathname !== "/ai") navigate("/ai");
    setOpen(false);
  }
  const newChat = () => openChat(null);
  const afterDelete = (id) => { if (id === null || id === chat.id) setChat((c) => ({ key: c.key + 1, id: null })); };

  const showNav = user && user.role;
  const groups = showNav ? groupNav(nav, user.role) : [];
  const pageLabel = (nav.find((n) => n.path === location.pathname) || {}).label || "NEMSAI";
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
          <div className="sb-scroll">
            <nav className="sb-nav" aria-label="Pages">
              {groups.map((g) => (
                <div className="sb-group" key={g.name} role="group" aria-label={g.name}>
                  <p className="sb-group-name lbl">{g.name}</p>
                  {g.items.map((item) => (
                    <NavLink key={item.path} to={item.path} end title={item.label}
                             className={({ isActive }) => (isActive ? "active" : "")}>
                      <span className="sb-ico"><Icon d={ICONS[item.path] || FALLBACK_ICON} /></span>
                      <span className="lbl">{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              ))}
            </nav>
            <ChatHistory activeId={chat.id} tick={historyTick} onOpen={openChat} onDeleted={afterDelete} />
          </div>
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
          <span className="mb-title"><img src="/logo.png" alt="" /><strong>{pageLabel}</strong></span>
          <button type="button" className="mb-profile" onClick={() => navigate("/profile")} aria-label="Profile">
            <span className="sb-avatar">{initials}</span>
          </button>
        </div>
        <Flashes />
        <Outlet context={{ chatKey: chat.key, openId: chat.id, onSaved: () => setHistoryTick((t) => t + 1) }} />
      </div>
    </div>
  );
}
