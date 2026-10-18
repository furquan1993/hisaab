import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Session } from "@supabase/supabase-js";
import { z } from "zod";
import { client, storageKey } from "./client";
import { monthRange } from "./domain";
import Workspace from "./Workspace";

export default function App() {
  const previousUser = useRef<string | null>(null);
  const [mode, setMode] = useState<"login" | "demo" | "account">("login");
  const [session, setSession] = useState<Session | null>(null);
  const [owner, setOwner] = useState(""),
    [range, setRange] = useState<readonly [string, string]>([
      "2026-01-01",
      "2026-01-31",
    ]);
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (!client) return;
    // Do not await SDK calls inside the auth callback.
    // https://supabase.com/docs/reference/javascript/auth-onauthstatechange
    const { data } = client.auth.onAuthStateChange((_event, next) => {
      if (previousUser.current !== next?.user.id) {
        setOwner("");
        setError("");
      }
      previousUser.current = next?.user.id ?? null;
      setSession(next);
      setMode((current) =>
        current === "demo" ? "demo" : next ? "account" : "login",
      );
    });
    return () => data.subscription.unsubscribe();
  }, []);
  useEffect(() => {
    if (!session || !client || mode !== "account") return;
    const api = client,
      controller = new AbortController();
    (async () => {
      const { data, error } = await api
        .from("profile")
        .select("id,display_name")
        .abortSignal(controller.signal);
      if (controller.signal.aborted) return;
      const profile = z
        .array(z.object({ id: z.string(), display_name: z.string() }))
        .safeParse(data);
      if (error || !profile.success)
        throw Error("Could not load your profile. Check the API setup.");
      if (profile.data.length !== 1)
        throw Error(
          "Signed in, but no owner is linked. Complete the trusted owner-linking step.",
        );
      const latest = await api
        .from("entries")
        .select("statement_date")
        .eq("is_selected", true)
        .not("statement_date", "is", null)
        .order("statement_date", { ascending: false })
        .limit(1)
        .abortSignal(controller.signal);
      if (controller.signal.aborted) return;
      if (latest.error)
        throw Error("Could not load your workspace. Check the API setup.");
      const today = new Date();
      const fallback = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
      const date =
        z.array(z.object({ statement_date: z.string() })).parse(latest.data)[0]
          ?.statement_date ?? fallback;
      setRange(monthRange(date));
      setOwner(profile.data[0].display_name);
    })().catch((cause) => {
      if (!controller.signal.aborted)
        setError(
          cause instanceof Error ? cause.message : "Workspace unavailable.",
        );
    });
    return () => controller.abort();
  }, [session?.user.id, mode]);
  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (!client) return;
    setBusy(true);
    setError("");
    try {
      const result = await client.auth.signInWithPassword({ email, password });
      if (result.error)
        setError(
          "Sign-in failed. Check your email/password or project availability.",
        );
    } catch {
      setError("Sign-in unavailable. Check your connection and retry.");
    } finally {
      setPassword("");
      setBusy(false);
    }
  }
  async function signOut() {
    setOwner("");
    setSession(null);
    setMode("login");
    setError("");
    setPassword("");
    if (!client) return;
    try {
      await client.auth.signOut({ scope: "local" });
    } finally {
      sessionStorage.removeItem(storageKey);
      window.location.reload();
    }
  }
  if (mode === "demo")
    return (
      <Workspace
        api={null}
        owner="Demo workspace"
        initialRange={["2026-01-01", "2026-01-31"]}
        onExit={() => setMode(session ? "account" : "login")}
      />
    );
  if (mode === "account" && session && client && owner)
    return (
      <Workspace
        key={session.user.id}
        api={client}
        owner={owner}
        initialRange={range}
        onExit={signOut}
      />
    );
  return (
    <main className="login-page">
      <div className="login-art">
        <a className="brand" href="#">
          <span className="brand-mark">h.</span> hisaab
        </a>
        <div>
          <span className="eyebrow">A LITTLE CLARITY GOES A LONG WAY</span>
          <h1>
            Your statements.
            <br />
            Your evidence.
            <br />
            <span>Your peace of mind.</span>
          </h1>
          <p>
            A private place to make sense of your credit-card entries, one clear
            row at a time.
          </p>
        </div>
        <small>Original facts preserved. Decisions kept separate.</small>
      </div>
      <section className="login-card">
        <span className="eyebrow">WELCOME TO HISAAB</span>
        <h2>
          {session ? "Preparing your workspace" : "A clearer view starts here."}
        </h2>
        <p className="muted">
          Sign in to your private workspace. Your bank and database passwords
          are never needed here.
        </p>
        {!session && (
          <form onSubmit={signIn}>
            <label>
              Email
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button
              type="submit"
              className="primary"
              disabled={!client || busy}
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}
        {!client && (
          <p className="notice">
            Supabase is not configured. Fill web/.env.local using the
            public-settings template, then restart the build.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {session && <button onClick={signOut}>Sign out</button>}
        <div className="demo-invite">
          <span>No setup needed to take a look.</span>
          <button
            onClick={() => {
              setPassword("");
              setMode("demo");
            }}
          >
            Explore synthetic demo
          </button>
        </div>
        <small className="muted">
          Read-only preview · No signup · No transfers
        </small>
      </section>
    </main>
  );
}
