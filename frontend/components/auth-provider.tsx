"use client";

import * as React from "react";
import { clearAuth, getRole, isAuthenticated } from "@/lib/api";

interface AuthState {
  authed: boolean;
  role: string | null;
  ready: boolean;
  refresh: () => void;
  logout: () => void;
}

const AuthContext = React.createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = React.useState(false);
  const [role, setRoleState] = React.useState<string | null>(null);
  const [ready, setReady] = React.useState(false);

  const refresh = React.useCallback(() => {
    setAuthed(isAuthenticated());
    setRoleState(getRole());
    setReady(true);
  }, []);

  const logout = React.useCallback(() => {
    clearAuth();
    setAuthed(false);
    setRoleState(null);
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ authed, role, ready, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
