"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

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
    const payload: Record<string, string> = { email: String(form.get("email")), password: String(form.get("password")) };
    if (registering) payload.name = String(form.get("name"));
    try {
      const response = await fetch(`/api/backend/auth/${registering ? "register" : "login"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const result = (await response.json()) as ApiError;
      if (!response.ok) throw new Error(result.message ?? result.detail?.message ?? "Não foi possível entrar.");
      router.replace("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha de conexão com a API.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-[#f4f7f4] lg:grid-cols-[1.05fr_.95fr]">
      <section className="relative hidden overflow-hidden bg-[#123c35] p-12 text-white lg:flex lg:flex-col lg:justify-between xl:p-20">
        <div className="absolute -right-32 -top-32 h-[32rem] w-[32rem] rounded-full border border-white/10" />
        <div className="absolute -right-10 -top-10 h-[22rem] w-[22rem] rounded-full border border-white/10" />
        <div className="relative flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#c5ed73] text-xl font-bold text-[#123c35]">a</div><span className="text-xl font-semibold tracking-tight">aquaflow</span></div>
        <div className="relative max-w-xl pb-10"><p className="mb-5 text-xs font-semibold uppercase tracking-[.22em] text-[#c5ed73]">Água bem cuidada começa com clareza</p><h1 className="text-5xl font-semibold leading-[1.08] tracking-tight xl:text-6xl">Entenda o consumo da sua casa.</h1><p className="mt-6 max-w-md text-lg leading-8 text-white/70">Acompanhe leituras, encontre mudanças no padrão e tenha mais controle do que acontece em cada ambiente.</p></div>
        <p className="relative text-sm text-white/45">Monitoramento responsável. Dados claros. Decisões melhores.</p>
      </section>
      <section className="flex items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-12 flex items-center gap-3 lg:hidden"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#123c35] text-xl font-bold text-[#c5ed73]">a</div><span className="text-xl font-semibold text-[#123c35]">aquaflow</span></div>
          <p className="text-sm font-medium text-[#638078]">{registering ? "Comece por aqui" : "Bem-vindo de volta"}</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[#183b35]">{registering ? "Crie sua conta" : "Acesse sua conta"}</h2>
          <p className="mt-3 text-sm leading-6 text-[#71827c]">{registering ? "Configure seu espaço e conecte o primeiro medidor." : "Entre para acompanhar os dados de consumo."}</p>
          <form onSubmit={submit} className="mt-9 space-y-5">
            {registering && <Field label="Seu nome" name="name" autoComplete="name" required />}
            <Field label="E-mail" name="email" type="email" autoComplete="email" required />
            <Field label="Senha" name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={registering ? 12 : 1} required />
            {registering && <p className="-mt-2 text-xs text-[#71827c]">Use pelo menos 12 caracteres.</p>}
            {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
            <button disabled={busy} className="flex h-12 w-full items-center justify-center rounded-xl bg-[#17483f] px-4 text-sm font-semibold text-white transition hover:bg-[#103a33] disabled:cursor-wait disabled:opacity-60">{busy ? "Aguarde…" : registering ? "Criar conta" : "Entrar"}<span className="ml-2" aria-hidden="true">→</span></button>
          </form>
          <p className="mt-7 text-center text-sm text-[#71827c]">{registering ? "Já tem uma conta?" : "Ainda não tem uma conta?"}{" "}<button onClick={() => { setRegistering(!registering); setError(""); }} className="font-semibold text-[#17483f] underline-offset-4 hover:underline">{registering ? "Entrar" : "Criar conta"}</button></p>
          <p className="mt-12 text-center text-xs leading-5 text-[#98a59f]">Ao continuar, você concorda em usar o AquaFlow para monitoramento do consumo de água.</p>
        </div>
      </section>
    </main>
  );
}

function Field({ label, name, type = "text", ...props }: { label: string; name: string; type?: string; autoComplete?: string; minLength?: number; required?: boolean }) {
  return <label className="block text-sm font-medium text-[#294a43]">{label}<input name={name} type={type} {...props} className="mt-2 h-12 w-full rounded-xl border border-[#d8e2dc] bg-white px-4 text-[#183b35] outline-none transition placeholder:text-[#a4b0ab] focus:border-[#528b70] focus:ring-4 focus:ring-[#528b70]/10" /></label>;
}
