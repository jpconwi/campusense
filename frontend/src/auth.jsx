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

  const logout = useCallback(async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already signed out */ }
    await refresh();
    setFlash({ text: "You have been signed out.", kind: "info" });
  }, [refresh]);

  const value = useMemo(() => ({ ...state, refresh, logout, flash, setFlash }),
    [state, refresh, logout, flash]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
