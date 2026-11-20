"use client";

import { type FormEvent, useState } from "react";
import Image from "next/image";
import "./auth.css";
import { useRouter } from "next/navigation";
import { Brand, ThemeToggle } from "../components/brand";

type ApiError = { message?: string; detail?: { message?: string } };

export default function Home() {
  const router = useRouter();
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
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
        <ThemeToggle />
      </header>
      <div className="auth-layout">
        <section className="auth-story" aria-labelledby="story-title">
          <div className="story-copy">
            <p className="story-title" id="story-title">
              Cuide da água.
              <br />
              Acompanhe
              <br />
              sua casa.
            </p>
            <p className="story-description">
              Seu consumo e seus avisos
              <br />
              em um só lugar.
            </p>
          </div>
          <div className="auth-water" aria-hidden="true">
            <div className="auth-water-back" />
            <div className="auth-water-front" />
            <Image
              className="auth-water-outer"
              src="/design/water-ripple-outer.svg"
              alt=""
              width={256}
              height={60}
            />
            <Image
              className="auth-water-inner"
              src="/design/water-ripple-inner.svg"
              alt=""
              width={220}
              height={48}
            />
            <div className="auth-water-mascot">
              <Image src="/design/water-drop.svg" alt="" width={152} height={190} />
            </div>
          </div>
        </section>
        <section className="auth-panel" aria-labelledby="auth-title">
          <div
            key={registering ? "register" : "login"}
            className={`auth-card${registering ? " auth-card--register" : ""}`}
          >
            <div className="auth-brand">
              <Brand
                lightArtwork="/design/aquaflow-logo-login.png"
                darkArtwork="/design/aquaflow-logo-login.png"
              />
            </div>
            <h1 id="auth-title">{registering ? "Crie sua conta" : "Bem-vindo de volta"}</h1>
            <p className="auth-description">
              {registering
                ? "Configure seu espaço e conecte seu primeiro medidor."
                : "Acompanhe a água da sua casa."}
            </p>
            <form onSubmit={submit} className="auth-form">
              {registering && <Field label="Seu nome" name="name" autoComplete="name" required />}
              <Field
                label="E-mail"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="seu@email.com"
                required
              />
              <label className="field">
                Senha
                <span className="password-control">
                  <input
                    name="password"
                    placeholder={registering ? undefined : "••••••••••"}
                    type={showPassword ? "text" : "password"}
                    autoComplete={registering ? "new-password" : "current-password"}
                    minLength={registering ? 12 : 1}
                    required
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((visible) => !visible)}
                    aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                    aria-pressed={showPassword}
                  >
                    <EyeIcon crossed={!showPassword} />
                  </button>
                </span>
              </label>
              {registering && <p className="field-hint">Use pelo menos 12 caracteres.</p>}
              {error && (
                <p role="alert" aria-atomic="true" className="notice notice--error">
                  {error}
                </p>
              )}
              <button
                disabled={busy}
                aria-busy={busy}
                className="button button--primary auth-submit"
              >
                {busy
                  ? registering
                    ? "Criando conta…"
                    : "Entrando…"
                  : registering
                    ? "Criar conta"
                    : "Entrar"}
              </button>
            </form>
            <p className="auth-switch">
              {registering ? "Já tem uma conta?" : "Ainda não tem conta?"}{" "}
              <button
                onClick={() => {
                  setRegistering(!registering);
                  setError("");
                }}
              >
                {registering ? "Entrar" : "Criar conta"}
              </button>
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}

function EyeIcon({ crossed }: { crossed: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.7" />
      {crossed && <path d="m4 4 16 16" />}
    </svg>
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
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="field">
      {label}
      <input name={name} type={type} {...props} />
    </label>
  );
}
