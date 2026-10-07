"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Brand, ThemeToggle } from "../../components/brand";
import { resolveActivePropertyId, resolveDashboardView } from "./dashboard-state.mjs";

type Property = { id: string; name: string; timezone: string; volume_unit: string };
type Device = { id: string; property_id: string; serial_number: string; name: string; expected_interval_seconds: number; last_seen_at: string | null };
type Bucket = { bucket_start: string; volume_liters: number; sample_count: number };
type Consumption = { items: Bucket[]; summary: { total_volume_liters: number; valid_interval_count: number } };
type Alert = { id: string; device_id: string; detector_type: string; severity: "low" | "medium" | "high"; reason: string; status: "open" | "acknowledged" | "resolved" | "false_positive"; evidence: Record<string, unknown>; detected_at: string; window_start: string; window_end: string };
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
  const [view, setView] = useState<"overview" | "meters" | "alerts">("overview");
  const [properties, setProperties] = useState<Property[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [consumption, setConsumption] = useState<Consumption | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newProperty, setNewProperty] = useState("");
  const [newDevice, setNewDevice] = useState("");
  const [newSerial, setNewSerial] = useState("");
  const [provisioned, setProvisioned] = useState<{ key: string; serial: string } | null>(null);
  const [deviceNotice, setDeviceNotice] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [alertActionId, setAlertActionId] = useState("");
  const [alertNotice, setAlertNotice] = useState("");
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
      const activeId = resolveActivePropertyId(
        propertyId,
        selectedId,
        propertyResult.items.map((property) => property.id),
      );
      setSelectedId(activeId);
      if (!activeId) { setConsumption(null); setAlerts([]); }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha ao carregar os dados.");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    const syncView = () => setView(resolveDashboardView(new URLSearchParams(window.location.search).get("view")));
    syncView();
    window.addEventListener("popstate", syncView);
    return () => window.removeEventListener("popstate", syncView);
  }, []);
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
  useEffect(() => {
    if (!selectedId || loading) return;
    let cancelled = false;
    api<{ items: Alert[] }>(`properties/${selectedId}/alerts?limit=50`).then((result) => {
      if (!cancelled) setAlerts(result.items);
    }).catch((caught: unknown) => {
      if (!cancelled) setError(caught instanceof Error ? caught.message : "Falha ao carregar alertas.");
    });
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
    setProvisioning(true);
    setDeviceNotice(null);
    setProvisioned(null);
    try {
      const result = await api<Device & { device_key: string }>("devices", {
        method: "POST", body: JSON.stringify({ property_id: selectedId, name: newDevice.trim(), serial_number: newSerial.trim() }),
      });
      setProvisioned({ key: result.device_key, serial: result.serial_number });
      setCopiedKey(false);
      setNewDevice(""); setNewSerial("");
      await load(selectedId);
      setDeviceNotice({ kind: "success", message: `${result.name} foi adicionado à propriedade.` });
    } catch (caught) {
      setDeviceNotice({ kind: "error", message: caught instanceof Error ? caught.message : "Não foi possível adicionar o medidor." });
    } finally { setProvisioning(false); }
  }

  async function updateAlert(alert: Alert, action: "acknowledge" | "resolve" | "false-positive") {
    setAlertActionId(alert.id);
    setAlertNotice("");
    try {
      const updated = await api<Alert>(`alerts/${alert.id}/${action}`, { method: "POST" });
      setAlerts((current) => current.map((item) => item.id === updated.id ? updated : item));
      setAlertNotice(action === "acknowledge" ? "Alerta reconhecido." : action === "resolve" ? "Alerta resolvido." : "Alerta marcado como falso positivo.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Não foi possível atualizar o alerta.");
    } finally { setAlertActionId(""); }
  }

  async function simulateReadings() {
    if (!provisioned) return;
    setSimulating(true); setError(""); setDeviceNotice(null);
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
      setDeviceNotice({ kind: "success", message: "Leituras de demonstração enviadas; o painel foi atualizado." });
    } catch (caught) {
      setDeviceNotice({ kind: "error", message: caught instanceof Error ? caught.message : "Não foi possível enviar as leituras." });
    }
    finally { setSimulating(false); }
  }

  async function copyDeviceKey() {
    if (!provisioned) return;
    try {
      await navigator.clipboard.writeText(provisioned.key);
      setCopiedKey(true);
    } catch {
      setDeviceNotice({ kind: "error", message: "Não foi possível copiar automaticamente. Selecione e copie a chave exibida." });
    }
  }

  async function logout() {
    try { await api("auth/logout", { method: "POST", body: "{}" }); } finally { router.replace("/"); }
  }

  function navigateView(destination: "overview" | "meters" | "alerts") {
    setView(destination);
    window.history.pushState(
      {},
      "",
      destination === "overview" ? "/dashboard" : `/dashboard?view=${destination}`,
    );
  }

  const chartData = (consumption?.items ?? []).map((item) => ({
    ...item,
    day: new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(new Date(item.bucket_start)),
  }));

  return (
    <main className="dashboard-page">
      <header className="app-header"><div className="app-header-inner"><Brand /><nav className="app-nav" aria-label="Navegação principal">{([ ["overview", "Visão geral"], ["meters", "Medidores"], ["alerts", "Alertas"] ] as const).map(([destination, label]) => <button key={destination} type="button" aria-current={view === destination ? "page" : undefined} className={`nav-link${view === destination ? " nav-link--active" : ""}`} onClick={() => navigateView(destination)}>{label}{destination === "alerts" && alerts.some((alert) => alert.status === "open") && <span className="nav-count" aria-label="alertas abertos">{alerts.filter((alert) => alert.status === "open").length}</span>}</button>)}</nav><div className="header-actions"><ThemeToggle /><button onClick={logout} className="button button--quiet">Sair</button></div></div></header>
      <div className="dashboard-content" id="overview">
        <section className="dashboard-heading"><div><span className="eyebrow"><span className="eyebrow-dot" />Painel de consumo</span><h1>{view === "meters" ? "Seus medidores." : view === "alerts" ? "Acompanhamento." : "Água em movimento."}</h1><p>{view === "meters" ? "Veja a comunicação dos dispositivos e envie leituras de teste." : view === "alerts" ? "Revise os comportamentos observados e atualize o tratamento dos alertas." : "Uma visão clara das leituras e do consumo registrado na sua propriedade."}</p></div>{properties.length > 0 && <label className="property-picker"><span>Propriedade</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label>}</section>
        {error && <p role="alert" className="notice notice--error dashboard-notice">{error}</p>}
        {properties.length === 0 && !loading ? <section className="onboarding-card"><div className="onboarding-art" aria-hidden="true"><span className="onboarding-drop">⌁</span><span className="onboarding-ring onboarding-ring--one"/><span className="onboarding-ring onboarding-ring--two"/></div><div className="onboarding-copy"><span className="eyebrow">Vamos começar</span><h2>Crie sua primeira propriedade</h2><p>Organize medidores e leituras por local. Depois, você pode conectar um dispositivo e acompanhar o consumo aqui.</p><form onSubmit={createProperty} className="inline-form"><label className="field">Nome da propriedade<input value={newProperty} onChange={(event) => setNewProperty(event.target.value)} placeholder="Ex.: Minha casa" required /></label><button className="button button--primary">Criar propriedade <span aria-hidden="true">→</span></button></form></div></section> : loading && properties.length === 0 ? <LoadingCard /> : <>
          {view === "overview" && <section className="metrics-grid" aria-label="Resumo de consumo"><Metric featured label="Consumo registrado" value={`${(consumption?.summary.total_volume_liters ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}`} unit="L" note="nos últimos 7 dias" /><Metric label="Intervalos calculados" value={`${consumption?.summary.valid_interval_count ?? 0}`} note="com leituras compatíveis" /><Metric label="Medidores" value={`${selectedDevices.length}`} note={selectedDevices.length ? `${selectedDevices.filter((device) => device.last_seen_at).length} receberam leitura` : "aguardando conexão"} /><Metric label="Alertas abertos" value={`${alerts.filter((alert) => alert.status === "open").length}`} note="precisam de acompanhamento" /></section>}
          {view !== "alerts" && <section className={`dashboard-grid${view !== "overview" ? " dashboard-grid--single" : ""}`}>
            {view === "overview" && <article className="surface chart-card"><div className="section-heading"><div><span className="eyebrow">Histórico recente</span><h2>Consumo diário</h2></div><span className="period-chip">7 dias <span aria-hidden="true">⌄</span></span></div><p className="section-subtitle">Volume estimado entre leituras recebidas · litros</p><div className="chart-wrap" role="img" aria-label="Gráfico do consumo diário nos últimos sete dias"><p className="sr-only">{chartData.length ? chartData.map((point) => `${point.day}: ${point.volume_liters} litros`).join(". ") : "Ainda não há leituras suficientes para exibir o gráfico."}</p>{chartData.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 12, right: 8, left: -18, bottom: 0 }}><defs><linearGradient id="consumptionFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#32bad0" stopOpacity={0.34} /><stop offset="95%" stopColor="#32bad0" stopOpacity={0.015} /></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 6" /><XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: "var(--muted)", fontSize: 12 }} dy={10} /><YAxis axisLine={false} tickLine={false} tick={{ fill: "var(--muted)", fontSize: 12 }} /><Tooltip formatter={(value) => [`${Number(value).toLocaleString("pt-BR")} L`, "Consumo"]} contentStyle={{ borderRadius: 14, borderColor: "var(--line)", background: "var(--surface)", color: "var(--ink)" }} /><Area type="monotone" dataKey="volume_liters" stroke="#159bb7" strokeWidth={3} fill="url(#consumptionFill)" activeDot={{ r: 5, fill: "#087d9b", stroke: "var(--surface)", strokeWidth: 2 }} /></AreaChart></ResponsiveContainer> : <div className="empty-chart"><span className="empty-chart-icon" aria-hidden="true">≈</span><p>Ainda não há consumo para exibir</p><span>Conecte um medidor e envie leituras para começar.</span></div>}</div><div className="chart-foot"><span><i aria-hidden="true"/>Consumo calculado</span><span>Períodos sem leitura não são contabilizados como zero.</span></div></article>}
            {view === "meters" && <article className="surface meters-card" id="meters"><div className="section-heading"><div><span className="eyebrow">Dispositivos</span><h2>Seus medidores</h2></div><span className="count-chip">{selectedDevices.length.toString().padStart(2, "0")}</span></div><p className="section-subtitle">Associados a {selected?.name ?? "esta propriedade"}</p>{selectedDevices.length ? <ul className="meter-list">{selectedDevices.map((device) => { const lastSeen = device.last_seen_at ? new Date(device.last_seen_at).getTime() : null; const connected = lastSeen !== null && Date.now() - lastSeen <= device.expected_interval_seconds * 2 * 1000; return <li key={device.id} className="meter-row"><span className="meter-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M4 15.5a8 8 0 1 1 16 0M12 12l4-4M5 19h14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg></span><span className="meter-info"><strong>{device.name}</strong><small>{device.serial_number} · {device.serial_number.startsWith("AF-DEMO-") ? "Demonstração" : "Dispositivo cadastrado"}</small></span><span className={`meter-status${connected ? " meter-status--online" : " meter-status--offline"}`}>{connected ? "Recebendo" : "Sem comunicação"}</span></li>; })}</ul> : <div className="empty-meter">Nenhum medidor conectado ainda.</div>}
              <form onSubmit={createDevice} className="device-form"><h3>Adicionar medidor de teste</h3><p className="form-help">Cadastre um medidor simulado e envie leituras sem precisar de um ESP32.</p><label className="field"><span className="sr-only">Nome do medidor</span><input value={newDevice} onChange={(event) => setNewDevice(event.target.value)} placeholder="Nome do medidor" required /></label><label className="field"><span className="sr-only">Número de série</span><input value={newSerial} onChange={(event) => setNewSerial(event.target.value)} placeholder="Número de série" required /></label>{deviceNotice && <p role={deviceNotice.kind === "error" ? "alert" : "status"} className={`form-notice form-notice--${deviceNotice.kind}`}>{deviceNotice.message}</p>}<button disabled={provisioning} className="button button--outline">{provisioning ? "Adicionando medidor…" : "Adicionar medidor"} <span aria-hidden="true">→</span></button></form></article>}</section>}
          {view === "meters" && provisioned && <section className="provision-card"><div><span className="eyebrow">Credencial do dispositivo</span><h2>Medidor pronto para configurar</h2><p>A chave é exibida apenas nesta sessão. Copie-a e configure no dispositivo.</p><code>{provisioned.key}</code><button onClick={() => void copyDeviceKey()} className="button button--quiet copy-key">{copiedKey ? "Chave copiada" : "Copiar chave"}</button></div><button disabled={simulating} onClick={() => void simulateReadings()} className="button button--primary">{simulating ? "Enviando leituras…" : "Simular leituras"}</button></section>}
          {view === "alerts" && <section className="surface alerts-card" id="alerts" aria-labelledby="alerts-title"><div className="section-heading"><div><span className="eyebrow">Acompanhamento</span><h2 id="alerts-title">Alertas da propriedade</h2></div><span className="count-chip">{alerts.filter((alert) => alert.status === "open" || alert.status === "acknowledged").length.toString().padStart(2, "0")}</span></div><p className="section-subtitle">Comportamentos que merecem verificação, com dados e período observados.</p>{alertNotice && <p role="status" className="form-notice form-notice--success">{alertNotice}</p>}{alerts.length ? <ul className="alert-list">{alerts.map((alert) => { const observedRate = alert.evidence.observed_flow_rate_liters_minute; const observedDuration = alert.evidence.observed_duration_minutes; const isDemoSample = alert.evidence.is_demo_sample === true; return <li className="alert-row" key={alert.id}><div className="alert-main"><div className="alert-title-line"><strong>{isDemoSample ? "Amostra demonstrativa" : alert.detector_type === "continuous_flow" ? "Fluxo contínuo" : alert.detector_type}</strong><span className={`severity-badge severity-badge--${alert.severity}`}>{alert.severity === "high" ? "Alta" : alert.severity === "medium" ? "Média" : "Baixa"}</span><span className={`alert-status alert-status--${alert.status}`}>{alert.status === "open" ? "Aberto" : alert.status === "acknowledged" ? "Reconhecido" : alert.status === "resolved" ? "Resolvido" : "Falso positivo"}</span>{isDemoSample && <span className="demo-badge">Exemplo</span>}</div><p>{alert.reason}</p><small>{typeof observedRate === "number" ? `${observedRate.toLocaleString("pt-BR")} L/min · ` : ""}{typeof observedDuration === "number" ? `${observedDuration} min · ` : ""}{devices.find((device) => device.id === alert.device_id)?.name ?? "Medidor"} · {new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(alert.detected_at))}</small></div><div className="alert-actions">{alert.status === "open" && <button disabled={alertActionId === alert.id} className="button button--outline" onClick={() => void updateAlert(alert, "acknowledge")}>Reconhecer</button>}{(alert.status === "open" || alert.status === "acknowledged") && <><button disabled={alertActionId === alert.id} className="button button--quiet" onClick={() => void updateAlert(alert, "resolve")}>Resolver</button><button disabled={alertActionId === alert.id} className="button button--quiet" onClick={() => void updateAlert(alert, "false-positive")}>Falso positivo</button></>}</div></li>; })}</ul> : <div className="empty-meter alert-empty">Nenhum alerta registrado para esta propriedade.</div>}</section>}
          {view === "overview" && <section className="overview-shortcuts" aria-label="Acessos rápidos"><button className="surface shortcut-card" onClick={() => navigateView("meters")}><span className="eyebrow">Dispositivos</span><strong>{selectedDevices.length} medidores</strong><span>Consultar comunicação ou enviar leituras de teste</span><b aria-hidden="true">→</b></button><button className="surface shortcut-card" onClick={() => navigateView("alerts")}><span className="eyebrow">Acompanhamento</span><strong>{alerts.filter((alert) => alert.status === "open" || alert.status === "acknowledged").length} alertas em acompanhamento</strong><span>Revisar evidências e atualizar o estado dos alertas</span><b aria-hidden="true">→</b></button></section>}
          <p className="dashboard-footnote">O consumo é estimado entre leituras recebidas. Uma anomalia indica um comportamento fora do padrão, não a localização física de um vazamento.</p>
        </>}
      </div>
    </main>
  );
}

function Metric({ label, value, note, unit, featured = false }: { label: string; value: string; note: string; unit?: string; featured?: boolean }) {
  return <article className={`metric-card${featured ? " metric-card--featured" : ""}`}><span className="metric-label">{label}</span><p className="metric-value">{value}{unit && <span>{unit}</span>}</p><span className="metric-note">{note}</span>{featured && <span className="metric-spark" aria-hidden="true">↗</span>}</article>;
}

function LoadingCard() {
  return <div className="surface loading-card" role="status"><span className="loading-wave" aria-hidden="true">≈</span>Carregando seus dados…</div>;
}
