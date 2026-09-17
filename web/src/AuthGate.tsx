import { useEffect, useState } from "react";
import App from "./App";
import { api } from "./types";

export type User = { id: string; email: string };
export default function AuthGate() {
  const [session, setSession] = useState<{ auth_required: boolean; user: User | null } | null>(null);
  const [error, setError] = useState("");
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    api<{ auth_required: boolean; user: User | null }>("auth/me")
      .then(value => { if (active) { setSession(value); setError(""); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [retry]);
  if (session && (!session.auth_required || session.user)) return <App user={session.user} onLogout={async () => {
    await api("auth/logout", {});
    setSession({ auth_required: true, user: null });
  }} />;
  return <main className="auth-page"><section className="auth-card">
    <span className="eyebrow">CARTOLLM · PRIVATE BETA</span>
    <h1>New Jersey, mapped by you.</h1>
    <p>Explore population, income, and open space. Your maps and conversations stay in your private workspace.</p>
    {!session ? <><p role="status">{error || "Connecting…"}</p>{error && <button onClick={() => setRetry(n => n + 1)}>Try again</button>}</> : <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError("");
      const fields = new FormData(event.currentTarget);
      try {
        const result = await api<{ user: User }>(register ? "auth/register" : "auth/login", {
          email: fields.get("email"), password: fields.get("password"),
          ...(register ? { invitation: fields.get("invitation") } : {}),
        });
        setSession({ auth_required: true, user: result.user });
      } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
    }}>
      <h2>{register ? "Accept your invitation" : "Welcome back"}</h2>
      <label>Email<input name="email" type="email" autoComplete="username" required maxLength={254} /></label>
      <label>Password<input name="password" type="password" autoComplete={register ? "new-password" : "current-password"} minLength={12} maxLength={128} required /></label>
      {register && <><small>Use at least 12 characters.</small><label>Invitation code<input name="invitation" autoComplete="off" required maxLength={100} /></label></>}
      {error && <p role="alert">{error}</p>}
      <button className="export-button" disabled={busy}>{busy ? "Please wait…" : register ? "Create private workspace" : "Sign in"}</button>
      <button type="button" disabled={busy} onClick={() => { setRegister(!register); setError(""); }}>{register ? "Already registered? Sign in" : "Have an invitation? Join the beta"}</button>
    </form>}
  </section></main>;
}
