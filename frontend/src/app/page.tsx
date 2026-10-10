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
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const payload: Record<string, string> = {
      email: String(form.get("email")),
      password: String(form.get("password")),
    };
    if (registering) payload.name = String(form.get("name"));
    try {
      const response = await fetch(`/api/backend/auth/${registering ? "register" : "login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = (await response.json()) as ApiError;
      if (!response.ok)
        throw new Error(result.message ?? result.detail?.message ?? "Não foi possível entrar.");
      router.replace("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Não foi possível conectar. Tente novamente.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-topbar">
        <Brand />
        <ThemeToggle />
      </header>
      <div className="auth-layout">
        <section className="auth-story" aria-labelledby="story-title">
          <div className="story-orbit story-orbit--one" />
          <div className="story-orbit story-orbit--two" />
          <div className="story-copy">
            <span className="eyebrow">
              <span className="eyebrow-dot" />
              Bem-vindo ao AquaFlow
            </span>
            <h1 id="story-title">Mais clareza. Menos desperdício.</h1>
            <p>
              Leituras organizadas, consumo visível e contexto para entender o que acontece na sua
              casa.
            </p>
            <div className="water-illustration" aria-hidden="true">
              <div className="water-ripple water-ripple--back" />
              <div className="water-ripple water-ripple--front" />
              <span className="water-drop">
                <svg viewBox="0 0 84 96" fill="none">
                  <defs>
                    <linearGradient
                      id="water-drop-fill"
                      x1="22"
                      y1="12"
                      x2="63"
                      y2="82"
                      gradientUnits="userSpaceOnUse"
                    >
                      <stop stopColor="#B9F8F1" />
                      <stop offset=".48" stopColor="#55D6DE" />
                      <stop offset="1" stopColor="#16A9C4" />
                    </linearGradient>
                    <linearGradient
                      id="water-drop-edge"
                      x1="20"
                      y1="16"
                      x2="63"
                      y2="80"
                      gradientUnits="userSpaceOnUse"
                    >
                      <stop stopColor="#E2FFFA" stopOpacity=".9" />
                      <stop offset="1" stopColor="#42D7E7" stopOpacity=".55" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M42 5C32 21 16 39 16 57c0 18 11 32 26 33 15-1 26-15 26-33C68 39 52 21 42 5Z"
                    fill="url(#water-drop-fill)"
                    stroke="url(#water-drop-edge)"
                    strokeWidth="2"
                  />
                  <path
                    d="M30 37c2-6 6-12 9-17"
                    stroke="#F5FFFC"
                    strokeWidth="5"
                    strokeLinecap="round"
                    opacity=".88"
                  />
                  <circle cx="34" cy="47" r="2.4" fill="#F5FFFC" opacity=".8" />
                  <path
                    d="M25 65c2 9 8 15 16 16"
                    stroke="#D5FFFA"
                    strokeWidth="2"
                    strokeLinecap="round"
                    opacity=".35"
                  />
                </svg>
              </span>
            </div>
          </div>
          <p className="story-footnote">Monitoramento responsável, com dados que fazem sentido.</p>
        </section>
        <section className="auth-panel" aria-labelledby="auth-title">
          <div className="auth-card">
            <div className="mobile-brand">
              <Brand />
            </div>
            <span className="eyebrow auth-eyebrow">
              {registering ? "Um novo começo" : "Seu consumo, com clareza"}
            </span>
            <h2 id="auth-title">{registering ? "Crie sua conta" : "Bom ter você aqui"}</h2>
            <p className="auth-description">
              {registering
                ? "Configure seu espaço e conecte seu primeiro medidor."
                : "Entre na sua conta para acompanhar seu consumo."}
            </p>
            <form onSubmit={submit} className="auth-form">
              {registering && <Field label="Seu nome" name="name" autoComplete="name" required />}
              <Field label="E-mail" name="email" type="email" autoComplete="email" required />
              <Field
                label="Senha"
                name="password"
                type="password"
                autoComplete={registering ? "new-password" : "current-password"}
                minLength={registering ? 12 : 1}
                required
              />
              {registering && <p className="field-hint">Use pelo menos 12 caracteres.</p>}
              {error && (
                <p role="alert" className="notice notice--error">
                  {error}
                </p>
              )}
              <button disabled={busy} className="button button--primary auth-submit">
                {busy ? "Aguarde…" : registering ? "Criar conta" : "Entrar"}
                <span aria-hidden="true">↗</span>
              </button>
            </form>
            <p className="auth-switch">
              {registering ? "Já tem uma conta?" : "Ainda não tem uma conta?"}{" "}
              <button
                onClick={() => {
                  setRegistering(!registering);
                  setError("");
                }}
              >
                {registering ? "Entrar" : "Criar conta"}
              </button>
            </p>
            <p className="auth-legal">Seu consumo, seus espaços, tudo em um só lugar.</p>
          </div>
        </section>
      </div>
    </main>
  );
}

function Field({
  label,
  name,
  type = "text",
  ...props
}: {
  label: string;
  name: string;
  type?: string;
  autoComplete?: string;
  minLength?: number;
  required?: boolean;
}) {
  return (
    <label className="field">
      {label}
      <input name={name} type={type} {...props} />
    </label>
  );
}
