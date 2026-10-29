/* Ui.jsx - small shared pieces used by several pages (icons, loading, empty states, search). */
import { PageSkeleton } from "./Skeletons.jsx";

export const PATHS = {
  chat: "M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.5A8 8 0 1 1 21 12z",
  concern: "M12 3l10 18H2zM12 10v5M12 18v.5",
  report: "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6",
  feedback: "M4 5h16v11H9l-5 4zM8 9h8M8 12h5",
  reserve: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  faculty: "M3 9l9-5 9 5-9 5zM7 12v5c3 2 7 2 10 0v-5",
  profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  users: "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20a6 6 0 0 1 12 0M16 11a2.5 2.5 0 1 0 0-5M17 15a5 5 0 0 1 4 5",
  dashboard: "M4 4h7v7H4zM13 4h7v4h-7zM13 11h7v9h-7zM4 14h7v6H4z",
  alert: "M12 8v5M12 16.5v.5M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  smile: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 14s1.5 2 4 2 4-2 4-2M9 9.5v.5M15 9.5v.5",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.5-4.5",
  inbox: "M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5",
  check: "M5 12.5l4.5 4.5L19 7.5",
  arrow: "M5 12h14M13 6l6 6-6 6",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z",
};

export function Icon({ d, size = 20 }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
  );
}

/** Shown while a page loads: a skeleton shaped like the page (see Skeletons.jsx). */
export function Loading({ label = "Loading...", variant = "table", wide }) {
  return <PageSkeleton variant={variant} label={label} wide={wide} />;
}

/** Friendly "nothing here yet" box. */
export function EmptyState({ icon = PATHS.inbox, title, children, action }) {
  return (
    <div className="empty-state">
      <span className="empty-ico"><Icon d={icon} size={26} /></span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/** Search box with a result counter. Filtering itself is done by the page (see matches()). */
export function SearchBox({ value, onChange, shown, total, placeholder = "Search..." }) {
  return (
    <div className="search-row">
      <label className="search-box">
        <Icon d={PATHS.search} size={18} />
        <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
               aria-label={placeholder} />
      </label>
      <span className="search-count" aria-live="polite">
        {value ? `${shown} of ${total}` : `${total} ${total === 1 ? "item" : "items"}`}
      </span>
    </div>
  );
}

/** True when every word typed in the search box appears somewhere in the row. */
export function matches(row, query) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const text = Object.values(row).filter((v) => typeof v === "string" || typeof v === "number")
    .join(" ").toLowerCase();
  return words.every((w) => text.includes(w));
}
