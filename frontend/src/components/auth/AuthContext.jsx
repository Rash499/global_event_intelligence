import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getCurrentAccount,
  loginAccount,
  logoutAccount,
  registerAccount,
} from "../../services/api.jsx";
import { getAuthToken, setAuthToken } from "../../services/authSession.jsx";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const restoreSession = async () => {
      if (!getAuthToken()) {
        if (active) setLoading(false);
        return;
      }

      try {
        const account = await getCurrentAccount();
        if (active) setUser(account);
      } catch (error) {
        if (error?.response?.status === 401) setAuthToken(null);
      } finally {
        if (active) setLoading(false);
      }
    };

    restoreSession();
    return () => {
      active = false;
    };
  }, []);

  const establishSession = useCallback((session) => {
    setAuthToken(session.access_token);
    setUser(session.user);
  }, []);

  const login = useCallback(async (credentials) => {
    const session = await loginAccount(credentials);
    establishSession(session);
  }, [establishSession]);

  const register = useCallback(async (account) => {
    const session = await registerAccount(account);
    establishSession(session);
  }, [establishSession]);

  const logout = useCallback(async () => {
    try {
      if (getAuthToken()) await logoutAccount();
    } catch {
      // Clear the local session even when the server is unavailable.
    } finally {
      setAuthToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}