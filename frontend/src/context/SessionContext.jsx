import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getStoredUserId, setStoredUserId } from "../api/client.js";
import { orbyteApi } from "../api/inventory.js";

// SIMULATED Orbyte session: which business and which user is using the module.
// In a real integration Orbyte would provide this. Here the user picks a demo
// user from the top bar. The BACKEND still checks permissions on every request.

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [state, setState] = useState({ status: "loading", users: [], context: null, error: null });

  const load = useCallback(async (preferredUserId, { silent = false } = {}) => {
    if (!silent) setState((current) => ({ ...current, status: "loading", error: null }));
    try {
      const { users } = await orbyteApi.listDemoUsers();
      if (!users.length) throw new Error("No demo users found. Check that the backend created its demo data.");

      const storedId = Number(getStoredUserId());
      const wantedId = preferredUserId ?? storedId;
      const chosen = users.find((user) => user.id === wantedId) ?? users[0];
      setStoredUserId(chosen.id);

      const context = await orbyteApi.getContext();
      setState({ status: "ready", users, context, error: null });
    } catch (error) {
      setState({ status: "error", users: [], context: null, error: error.message });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const value = useMemo(() => {
    const permissions = state.context?.permissions ?? [];
    return {
      status: state.status,
      error: state.error,
      users: state.users,
      user: state.context?.user ?? null,
      business: state.context?.business ?? null,
      permissions,
      can: (permission) => permissions.includes(permission),
      switchUser: (userId) => load(userId, { silent: true }),
      retry: () => load(),
    };
  }, [state, load]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
