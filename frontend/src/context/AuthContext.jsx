import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi } from "../api/auth.js";
import { SESSION_ENDED_EVENT, getToken, setToken } from "../api/client.js";

// Is someone signed in to the demo workspace? Decides between the sign-in page and the app.
// The backend checks the token on every request; this only decides what to show.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "checking", email: null, expiresAt: null, notice: null });

  // On page load: is the saved token still valid?
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setState({ status: "signed_out", email: null, expiresAt: null, notice: null });
      return undefined;
    }
    authApi
      .session()
      .then((session) => {
        if (!cancelled) setState({ status: "signed_in", email: session.email, expiresAt: session.expires_at, notice: null });
      })
      .catch((error) => {
        if (cancelled) return;
        if (error.status === 401) {
          setToken(null);
          setState({ status: "signed_out", email: null, expiresAt: null, notice: "Your session has ended. Please sign in again." });
        } else {
          setState({ status: "error", email: null, expiresAt: null, notice: error.message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Any request that gets "please sign in" ends the session here too
  useEffect(() => {
    const onEnded = () => {
      setToken(null);
      setState((current) =>
        current.status === "signed_in"
          ? { status: "signed_out", email: null, expiresAt: null, notice: "Your session has ended. Please sign in again." }
          : current
      );
    };
    window.addEventListener(SESSION_ENDED_EVENT, onEnded);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, onEnded);
  }, []);

  const login = useCallback(async (email, password) => {
    const result = await authApi.login(email, password);
    setToken(result.token);
    setState({ status: "signed_in", email: result.email, expiresAt: result.expires_at, notice: null });
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout(); // the token stops working on the server too
    } catch {
      /* already ended or server unreachable: signing out locally is still correct */
    }
    setToken(null);
    setState({ status: "signed_out", email: null, expiresAt: null, notice: "You have signed out." });
  }, []);

  const value = useMemo(() => ({ ...state, login, logout }), [state, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
