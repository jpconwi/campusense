import { createContext, useContext, useState } from "react";

const ThemeContext = createContext(null);
const STORAGE_KEY = "nemsai-theme";

function readTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const initial = readTheme();
    if (typeof document !== "undefined") document.documentElement.dataset.theme = initial;
    return initial;
  });

  function toggleTheme() {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem(STORAGE_KEY, next); } catch { /* Theme still works for this session. */ }
      return next;
    });
  }

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function ThemeToggle({ className = "" }) {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const dark = theme === "dark";
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
      title={dark ? "Turn dark mode off" : "Turn dark mode on"}
      onClick={toggleTheme}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {dark
          ? <path d="M20.2 15.2A8.5 8.5 0 0 1 8.8 3.8 8.5 8.5 0 1 0 20.2 15.2Z" />
          : <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></>}
      </svg>
      <span className="theme-toggle-label">Dark mode</span>
      <span className="theme-toggle-track" aria-hidden="true"><span /></span>
    </button>
  );
}
