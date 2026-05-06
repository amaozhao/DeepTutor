"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [nextPath, setNextPath] = useState("/");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setNextPath(params.get("next") || "/");
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      if (mode === "register") {
        await register(email, password, displayName);
      } else {
        await login(email, password);
      }
      router.replace(nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--background)] px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-5 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm"
      >
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">
            {mode === "register" ? "Create account" : "Sign in"}
          </h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            DeepTutor private workspace
          </p>
        </div>

        {mode === "register" ? (
          <label className="block text-sm">
            <span className="text-[var(--muted-foreground)]">Name</span>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 outline-none focus:border-[var(--primary)]"
              autoComplete="name"
            />
          </label>
        ) : null}

        <label className="block text-sm">
          <span className="text-[var(--muted-foreground)]">Email</span>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 outline-none focus:border-[var(--primary)]"
            autoComplete="email"
            type="email"
            required
          />
        </label>

        <label className="block text-sm">
          <span className="text-[var(--muted-foreground)]">Password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 outline-none focus:border-[var(--primary)]"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            type="password"
            required
            minLength={mode === "register" ? 6 : 1}
          />
        </label>

        {error ? (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-[var(--primary)] px-3 py-2 text-sm font-medium text-[var(--primary-foreground)] disabled:opacity-60"
        >
          {submitting
            ? "Working..."
            : mode === "register"
              ? "Create account"
              : "Sign in"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "register" ? "login" : "register");
            setError("");
          }}
          className="w-full text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          {mode === "register"
            ? "Already have an account? Sign in"
            : "Need an account? Register"}
        </button>
      </form>
    </main>
  );
}
