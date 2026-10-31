/* auth.jsx - who is signed in (loaded from GET /api/auth/me) + flash messages. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setCsrfToken, setUnauthorizedHandler } from "./api.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, user: null, nav: [], facilities: [] });
  const [flash, setFlash] = useState(null);        // { text, kind }

  const refresh = useCallback(async () => {
    try {
      const data = await api("/api/auth/me");
      setCsrfToken(data.csrf_token);
      setState({ loading: false, user: data.user, nav: data.nav, facilities: data.facilities });
      return data.user;
    } catch {
      setState({ loading: false, user: null, nav: [], facilities: [] });
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
    // a 401 from any request means the session ended -> show the sign-in page
    setUnauthorizedHandler(() => setState((s) => ({ ...s, user: null, nav: [] })));
  }, [refresh]);

  // Count time only while the signed-in site is open in a foreground tab.
  useEffect(() => {
    if (!state.user) return undefined;
    const send = () => {
      if (document.visibilityState === "visible") api("/api/activity/heartbeat", { method: "POST" }).catch(() => {});
    };
    send();
    const timer = window.setInterval(send, 60_000);
    document.addEventListener("visibilitychange", send);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", send);
    };
  }, [state.user]);

  const logout = useCallback(async () => {
    try { await api("/api/activity/offline", { method: "POST" }); } catch { /* presence expires automatically */ }
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already signed out */ }
    await refresh();
    setFlash({ text: "You have been signed out.", kind: "info" });
  }, [refresh]);

  const value = useMemo(() => ({ ...state, refresh, logout, flash, setFlash }),
    [state, refresh, logout, flash]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
