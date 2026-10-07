"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Brand, ThemeToggle } from "../components/brand";

type ApiError = { message?: string; detail?: { message?: string } };

export default function Home() {
  const router = useRouter();
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    const payload: Record<string, string> = { email: String(form.get("email")), password: String(form.get("password")) };
    if (registering) payload.name = String(form.get("name"));
    try {
      const response = await fetch(`/api/backend/auth/${registering ? "register" : "login"}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const result = (await response.json()) as ApiError;
      if (!response.ok) throw new Error(result.message ?? result.detail?.message ?? "Não foi possível entrar.");
      router.replace("/dashboard");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Falha de conexão com a API."); }
    finally { setBusy(false); }
  }

  return (
    <main className="auth-page">
      <header className="auth-topbar"><Brand /><ThemeToggle /></header>
      <div className="auth-layout">
        <section className="auth-story" aria-labelledby="story-title">
          <div className="story-orbit story-orbit--one" /><div className="story-orbit story-orbit--two" />
          <div className="story-copy">
            <span className="eyebrow"><span className="eyebrow-dot" />Água, em perspectiva</span>
            <h1 id="story-title">Cada gota conta uma história.</h1>
            <p>Leituras organizadas, consumo visível e contexto para entender o que acontece na sua casa.</p>
            <div className="water-illustration" aria-hidden="true"><div className="water-ripple water-ripple--back" /><div className="water-ripple water-ripple--front" /><span className="water-drop"><svg viewBox="0 0 40 48" fill="none"><path d="M20 3C15 11 6 21 6 29a14 14 0 0 0 28 0C34 21 25 11 20 3Z" fill="currentColor"/><path d="M13 29c.3 4 3 6.5 7 6.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" opacity=".75"/></svg></span></div>
          </div>
          <p className="story-footnote">Monitoramento responsável, com dados que fazem sentido.</p>
        </section>
        <section className="auth-panel" aria-labelledby="auth-title">
          <div className="auth-card">
            <div className="mobile-brand"><Brand /></div>
            <span className="eyebrow auth-eyebrow">{registering ? "Um novo começo" : "Seu consumo, com clareza"}</span>
            <h2 id="auth-title">{registering ? "Crie sua conta" : "Acompanhe sua água."}</h2>
            <p className="auth-description">{registering ? "Configure seu espaço e conecte seu primeiro medidor." : "Entre para visualizar as leituras da sua propriedade."}</p>
            <form onSubmit={submit} className="auth-form">
              {registering && <Field label="Seu nome" name="name" autoComplete="name" required />}
              <Field label="E-mail" name="email" type="email" autoComplete="email" required />
              <Field label="Senha" name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={registering ? 12 : 1} required />
              {registering && <p className="field-hint">Use pelo menos 12 caracteres.</p>}
              {error && <p role="alert" className="notice notice--error">{error}</p>}
              <button disabled={busy} className="button button--primary auth-submit">{busy ? "Aguarde…" : registering ? "Criar conta" : "Entrar"}<span aria-hidden="true">↗</span></button>
            </form>
            <p className="auth-switch">{registering ? "Já tem uma conta?" : "Ainda não tem uma conta?"}{" "}<button onClick={() => { setRegistering(!registering); setError(""); }}>{registering ? "Entrar" : "Criar conta"}</button></p>
            <p className="auth-legal">Ao continuar, você concorda em usar o aquaflow para monitorar o consumo de água.</p>
          </div>
        </section>
      </div>
    </main>
  );
}

function Field({ label, name, type = "text", ...props }: { label: string; name: string; type?: string; autoComplete?: string; minLength?: number; required?: boolean }) {
  return <label className="field">{label}<input name={name} type={type} {...props} /></label>;
}
