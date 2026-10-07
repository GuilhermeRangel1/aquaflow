"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Property = { id: string; name: string; timezone: string; volume_unit: string };
type Device = { id: string; property_id: string; serial_number: string; name: string; last_seen_at: string | null };
type Bucket = { bucket_start: string; volume_liters: number; sample_count: number };
type Consumption = { items: Bucket[]; summary: { total_volume_liters: number; valid_interval_count: number } };
type ApiError = { code?: string; message?: string; detail?: { code?: string; message?: string } };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers }, cache: "no-store" });
  const data = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("aquaflow:unauthorized"));
    throw new Error(data.message ?? data.detail?.message ?? "Não foi possível concluir a solicitação.");
  }
  return data;
}

export default function Dashboard() {
  const router = useRouter();
  const [properties, setProperties] = useState<Property[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [consumption, setConsumption] = useState<Consumption | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newProperty, setNewProperty] = useState("");
  const [newDevice, setNewDevice] = useState("");
  const [newSerial, setNewSerial] = useState("");
  const [provisioned, setProvisioned] = useState<{ key: string; serial: string } | null>(null);
  const [simulating, setSimulating] = useState(false);
  const selected = properties.find((item) => item.id === selectedId);
  const selectedDevices = useMemo(() => devices.filter((item) => item.property_id === selectedId), [devices, selectedId]);

  const load = useCallback(async (propertyId?: string) => {
    setLoading(true);
    setError("");
    try {
      const [propertyResult, deviceResult] = await Promise.all([
        api<{ items: Property[] }>("properties"),
        api<{ items: Device[] }>("devices"),
      ]);
      setProperties(propertyResult.items);
      setDevices(deviceResult.items);
      const activeId = propertyId ?? selectedId ?? propertyResult.items[0]?.id ?? "";
      setSelectedId(activeId);
      if (!activeId) setConsumption(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha ao carregar os dados.");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    const redirect = () => router.replace("/");
    window.addEventListener("aquaflow:unauthorized", redirect);
    return () => window.removeEventListener("aquaflow:unauthorized", redirect);
  }, [router]);
  useEffect(() => {
    if (!selectedId || loading) return;
    let cancelled = false;
    const end = new Date();
    const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
    const params = new URLSearchParams({ start: start.toISOString(), end: end.toISOString(), granularity: "day" });
    api<Consumption>(`properties/${selectedId}/consumption?${params}`).then((result) => { if (!cancelled) setConsumption(result); }).catch((caught: unknown) => { if (!cancelled) setError(caught instanceof Error ? caught.message : "Falha ao carregar consumo."); });
    return () => { cancelled = true; };
  }, [selectedId, loading]);

  async function createProperty(event: FormEvent) {
    event.preventDefault();
    if (!newProperty.trim()) return;
    try {
      const result = await api<Property>("properties", { method: "POST", body: JSON.stringify({ name: newProperty.trim() }) });
      setNewProperty("");
      await load(result.id);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Não foi possível criar o imóvel."); }
  }

  async function createDevice(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !newDevice.trim() || !newSerial.trim()) return;
    try {
      const result = await api<Device & { device_key: string }>("devices", {
        method: "POST", body: JSON.stringify({ property_id: selectedId, name: newDevice.trim(), serial_number: newSerial.trim() }),
      });
      setProvisioned({ key: result.device_key, serial: result.serial_number });
      setNewDevice(""); setNewSerial("");
      await load(selectedId);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Não foi possível conectar o medidor."); }
  }

  async function simulateReadings() {
    if (!provisioned) return;
    setSimulating(true); setError("");
    try {
      const now = Date.now();
      const points = [
        { minutesAgo: 10, liters: 1000 },
        { minutesAgo: 5, liters: 1002 },
        { minutesAgo: 0, liters: 1006 },
      ];
      for (const point of points) {
        await api("ingestion/telemetry", {
          method: "POST", headers: { "X-Device-Key": provisioned.key },
          body: JSON.stringify({
            device_serial: provisioned.serial,
            event_id: `demo-${now}-${point.minutesAgo}`,
            recorded_at: new Date(now - point.minutesAgo * 60_000).toISOString(),
            cumulative_volume_liters: point.liters,
          }),
        });
      }
      await load(selectedId);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Não foi possível enviar as leituras."); }
    finally { setSimulating(false); }
  }

  async function logout() {
    try { await api("auth/logout", { method: "POST", body: "{}" }); } finally { router.replace("/"); }
  }

  const chartData = (consumption?.items ?? []).map((item) => ({
    ...item,
    day: new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(new Date(item.bucket_start)),
  }));

  return (
    <main className="min-h-screen bg-[#f4f7f4] text-[#183b35]">
      <header className="border-b border-[#e0e8e2] bg-white/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#17483f] text-lg font-bold text-[#c5ed73]">a</div><div><p className="font-semibold tracking-tight">aquaflow</p><p className="text-xs text-[#7b8b84]">Monitoramento de consumo</p></div></div>
          <div className="flex items-center gap-3"><span className="hidden text-sm text-[#71827c] sm:block">Visão geral</span><button onClick={logout} className="rounded-lg px-3 py-2 text-sm font-medium text-[#557068] hover:bg-[#f1f5f1]">Sair</button></div>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-5 py-9 sm:px-8 sm:py-12">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-[#638078]">Seu espaço</p><h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">Consumo de água</h1><p className="mt-2 text-sm text-[#71827c]">Acompanhe as leituras recentes e o volume registrado.</p></div>
          {properties.length > 0 && <label className="text-xs font-semibold uppercase tracking-wide text-[#71827c]">Imóvel<select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} className="mt-2 block h-11 min-w-52 rounded-xl border border-[#d8e2dc] bg-white px-3 text-sm font-medium normal-case tracking-normal text-[#183b35] outline-none focus:border-[#528b70]">{properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label>}
        </div>

        {error && <p role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

        {properties.length === 0 && !loading ? (
          <section className="mt-8 grid gap-8 rounded-3xl border border-[#e0e8e2] bg-white p-6 shadow-sm sm:p-10 lg:grid-cols-[1fr_.8fr]">
            <div><p className="text-sm font-semibold text-[#638078]">Primeiro passo</p><h2 className="mt-2 text-2xl font-semibold">Cadastre seu imóvel</h2><p className="mt-2 max-w-lg text-sm leading-6 text-[#71827c]">As leituras e os medidores ficam organizados por imóvel. Você pode ajustar o fuso horário e outras opções depois.</p></div>
            <form onSubmit={createProperty} className="flex flex-col gap-3 sm:flex-row sm:items-end"><label className="flex-1 text-sm font-medium">Nome do imóvel<input value={newProperty} onChange={(event) => setNewProperty(event.target.value)} placeholder="Ex.: Minha casa" required className="mt-2 h-12 w-full rounded-xl border border-[#d8e2dc] px-4 outline-none focus:border-[#528b70]" /></label><button className="h-12 rounded-xl bg-[#17483f] px-5 text-sm font-semibold text-white hover:bg-[#103a33]">Criar imóvel</button></form>
          </section>
        ) : loading && properties.length === 0 ? <LoadingCard /> : (
          <>
            <section className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Consumo registrado · 7 dias" value={`${(consumption?.summary.total_volume_liters ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} L`} note="Soma dos intervalos com leitura válida" />
              <Metric label="Intervalos calculados" value={`${consumption?.summary.valid_interval_count ?? 0}`} note="Entre leituras compatíveis" />
              <Metric label="Medidores conectados" value={`${selectedDevices.length}`} note={selectedDevices.length ? `${selectedDevices.filter((device) => device.last_seen_at).length} com leitura recebida` : "Adicione seu primeiro medidor"} />
              <Metric label="Imóvel monitorado" value={selected?.name ?? "—"} note={selected?.timezone ?? "Fuso horário local"} />
            </section>

            <section className="mt-5 grid gap-5 xl:grid-cols-[1.65fr_1fr]">
              <div className="rounded-3xl border border-[#e0e8e2] bg-white p-5 shadow-sm sm:p-7">
                <div className="flex items-start justify-between gap-4"><div><h2 className="font-semibold">Consumo diário</h2><p className="mt-1 text-sm text-[#829089]">Últimos 7 dias · litros</p></div><span className="rounded-full bg-[#eef6e6] px-3 py-1 text-xs font-semibold text-[#466a41]">Atualizado agora</span></div>
                <div className="mt-7 h-64 w-full" role="img" aria-label="Gráfico do consumo diário nos últimos sete dias">
                  {chartData.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 5, right: 5, left: -18, bottom: 0 }}><defs><linearGradient id="consumptionFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#73a977" stopOpacity={0.25} /><stop offset="95%" stopColor="#73a977" stopOpacity={0.02} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#edf1ed" /><XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: "#829089", fontSize: 12 }} dy={10} /><YAxis axisLine={false} tickLine={false} tick={{ fill: "#829089", fontSize: 12 }} /><Tooltip formatter={(value) => [`${Number(value).toLocaleString("pt-BR")} L`, "Consumo"]} contentStyle={{ borderRadius: 12, borderColor: "#e0e8e2" }} /><Area type="monotone" dataKey="volume_liters" stroke="#4c8962" strokeWidth={2.5} fill="url(#consumptionFill)" activeDot={{ r: 5, fill: "#17483f" }} /></AreaChart></ResponsiveContainer> : <div className="grid h-full place-items-center rounded-2xl bg-[#f8faf8] text-center"><div><p className="font-medium text-[#557068]">Ainda não há consumo para exibir</p><p className="mt-1 text-sm text-[#89958f]">Conecte um medidor e envie leituras.</p></div></div>}
                </div>
              </div>

              <div className="rounded-3xl border border-[#e0e8e2] bg-white p-5 shadow-sm sm:p-7">
                <h2 className="font-semibold">Medidores</h2><p className="mt-1 text-sm text-[#829089]">Dispositivos desta propriedade</p>
                {selectedDevices.length ? <ul className="mt-5 divide-y divide-[#edf1ed]">{selectedDevices.map((device) => <li key={device.id} className="flex items-center gap-3 py-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef6e6] text-[#47734d]" aria-hidden="true">◉</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{device.name}</p><p className="text-xs text-[#829089]">{device.serial_number}</p></div><span className="h-2 w-2 rounded-full bg-[#80b96c]" aria-label="Medidor registrado" /></li>)}</ul> : <div className="mt-5 rounded-2xl bg-[#f8faf8] px-4 py-5 text-sm text-[#71827c]">Nenhum medidor conectado.</div>}
                <form onSubmit={createDevice} className="mt-5 space-y-3 border-t border-[#edf1ed] pt-5"><p className="text-sm font-semibold">Adicionar medidor</p><input aria-label="Nome do medidor" value={newDevice} onChange={(event) => setNewDevice(event.target.value)} placeholder="Nome (ex.: Medidor principal)" required className="h-11 w-full rounded-xl border border-[#d8e2dc] px-3 text-sm outline-none focus:border-[#528b70]" /><input aria-label="Número de série" value={newSerial} onChange={(event) => setNewSerial(event.target.value)} placeholder="Número de série" required className="h-11 w-full rounded-xl border border-[#d8e2dc] px-3 text-sm outline-none focus:border-[#528b70]" /><button className="h-11 w-full rounded-xl border border-[#b9cfc1] text-sm font-semibold text-[#285b49] hover:bg-[#f2f7f2]">Provisionar medidor</button></form>
              </div>
            </section>

            {provisioned && <section className="mt-5 rounded-3xl border border-[#d8e7c8] bg-[#f1f8e9] p-5 sm:p-7"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><p className="text-sm font-semibold text-[#466a41]">Chave criada para {provisioned.serial}</p><p className="mt-1 max-w-xl text-sm leading-6 text-[#5e7358]">Copie e configure esta chave no dispositivo. Ela aparece apenas nesta sessão e não pode ser recuperada depois.</p><code className="mt-3 block break-all rounded-xl border border-[#d7e4cb] bg-white px-4 py-3 font-mono text-sm text-[#294a43]">{provisioned.key}</code></div><button disabled={simulating} onClick={simulateReadings} className="shrink-0 rounded-xl bg-[#17483f] px-4 py-3 text-sm font-semibold text-white hover:bg-[#103a33] disabled:opacity-60">{simulating ? "Enviando leituras…" : "Simular leituras de demonstração"}</button></div></section>}
            <p className="mt-5 text-center text-xs leading-5 text-[#89958f]">O consumo é estimado entre leituras recebidas. Um intervalo sem dados não é contabilizado como zero.</p>
          </>
        )}
      </div>
    </main>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="rounded-2xl border border-[#e0e8e2] bg-white p-5 shadow-sm"><p className="text-xs font-medium text-[#71827c]">{label}</p><p className="mt-3 truncate text-2xl font-semibold tracking-tight">{value}</p><p className="mt-1 text-xs text-[#89958f]">{note}</p></article>;
}

function LoadingCard() {
  return <div className="mt-8 rounded-3xl border border-[#e0e8e2] bg-white p-10 text-center text-sm text-[#71827c]" role="status">Carregando seus dados…</div>;
}
