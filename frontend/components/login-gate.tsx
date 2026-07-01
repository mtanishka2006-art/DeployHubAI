"use client";

import * as React from "react";
import { Activity, Lock, UserPlus, Loader2 } from "lucide-react";
import { login, register, ApiError } from "@/lib/api";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Mode = "login" | "signup";

export function LoginGate({ children }: { children: React.ReactNode }) {
  const { authed, ready, refresh } = useAuth();
  const [mode, setMode] = React.useState<Mode>("login");
  const [username, setUsername] = React.useState("admin");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (authed) return <>{children}</>;

  const isSignup = mode === "signup";

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setPassword("");
    setConfirm("");
    setUsername(next === "login" ? "admin" : "");
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (isSignup && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      if (isSignup) {
        await register(username.trim(), password);
      } else {
        await login(username, password);
      }
      refresh();
    } catch (err) {
      const fallback = isSignup
        ? "Sign up failed. Please try again."
        : "Login failed. Check credentials and backend.";
      setError(err instanceof ApiError ? err.message : fallback);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div className="absolute inset-0 grid-glow opacity-40" />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-xl border border-primary/40 bg-primary/10 text-primary shadow-lg shadow-primary/20">
            <Activity className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">DeployHub AI</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Infrastructure Observability &amp; Mission Control
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-xl border border-border bg-card/80 p-6 shadow-2xl shadow-black/40 backdrop-blur"
        >
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            {isSignup ? (
              <>
                <UserPlus className="h-4 w-4" /> Create your account
              </>
            ) : (
              <>
                <Lock className="h-4 w-4" /> Operator Sign In
              </>
            )}
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Username
            </label>
            <Input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={isSignup ? "choose a username" : "admin"}
              autoComplete="username"
              required
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Password
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••"
              autoComplete={isSignup ? "new-password" : "current-password"}
              required
            />
          </div>
          {isSignup && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Confirm password
              </label>
              <Input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••"
                autoComplete="new-password"
                required
              />
            </div>
          )}

          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {isSignup ? "Create account" : "Sign In"}
          </Button>

          {isSignup ? (
            <p className="text-center text-xs text-muted-foreground">
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => switchMode("login")}
                className="font-medium text-primary hover:underline"
              >
                Sign in
              </button>
            </p>
          ) : (
            <p className="text-center text-xs text-muted-foreground">
              New here?{" "}
              <button
                type="button"
                onClick={() => switchMode("signup")}
                className="font-medium text-primary hover:underline"
              >
                Create an account
              </button>
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
