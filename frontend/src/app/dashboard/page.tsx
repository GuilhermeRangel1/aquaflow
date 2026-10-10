"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Brand, ThemeToggle } from "../../components/brand";
import { resolveActivePropertyId, resolveDashboardView } from "./dashboard-state.mjs";

type Property = {
  id: string;
  name: string;
  address: string | null;
  timezone: string;
  volume_unit: string;
  notification_threshold_liters: number | null;
  continuous_flow_threshold_liters_minute: number;
  continuous_flow_duration_minutes: number;
  late_reading_window_days: number;
};
type PropertyPatch = Pick<
  Property,
  | "name"
  | "address"
  | "timezone"
  | "volume_unit"
  | "continuous_flow_threshold_liters_minute"
  | "continuous_flow_duration_minutes"
  | "late_reading_window_days"
>;
type PropertySettingsDraft = {
  name: string;
  address: string;
  timezone: string;
  flowThreshold: string;
  flowDuration: string;
  lateWindow: string;
};
type Device = {
  id: string;
  property_id: string;
  serial_number: string;
  name: string;
  expected_interval_seconds: number;
  last_seen_at: string | null;
};
type DeviceReading = {
  recorded_at: string;
  quality: string;
  battery_percent: number | null;
  signal_dbm: number | null;
  firmware_version: string | null;
};
type DeviceHealth = {
  connectivity: "online" | "offline" | "never_connected";
  last_seen_at: string | null;
  latest_reading: DeviceReading | null;
};
type Bucket = { bucket_start: string; volume_liters: number; sample_count: number };
type Consumption = {
  items: Bucket[];
  summary: {
    total_volume_liters: number;
    valid_interval_count: number;
    previous_period_total_volume_liters: number | null;
    change_volume_liters: number | null;
    change_percent: number | null;
  };
};
type Alert = {
  id: string;
  device_id: string;
  detector_type: string;
  severity: "low" | "medium" | "high";
  reason: string;
  status: "open" | "acknowledged" | "resolved" | "false_positive";
  evidence: Record<string, unknown>;
  detected_at: string;
  window_start: string;
  window_end: string;
};
type DashboardHealth = {
  checked_at: string;
  ingestion: {
    api_status: "healthy";
    readings_last_24h: number;
    last_reading_at: string | null;
    mqtt_status: "connected" | "disconnected" | "unavailable";
    mqtt_messages_received: number;
    mqtt_messages_forwarded: number;
    mqtt_messages_rejected: number;
    mqtt_retries: number;
    mqtt_last_message_at: string | null;
  };
  model_pipeline: {
    status: "healthy" | "degraded" | "unavailable";
    model_name: string | null;
    model_version: string | null;
    last_check_at: string | null;
    processed_records: number;
    failed_batches: number;
    scored_inferences_last_24h: number;
    skipped_inferences_last_24h: number;
    positive_predictions_last_24h: number;
  };
  rules_fallback: { status: "active"; alerts_last_24h: number; explanation: string };
};
type ApiError = { code?: string; message?: string; detail?: { code?: string; message?: string } };

function getTimezoneOptions(currentTimezone: string): string[] {
  const zones = new Set<string>(["UTC"]);
  if (typeof Intl.supportedValuesOf === "function") {
    Intl.supportedValuesOf("timeZone").forEach((timezone) => zones.add(timezone));
  } else {
    [
      "America/Manaus",
      "America/Belem",
      "America/Fortaleza",
      "America/Recife",
      "America/Sao_Paulo",
      "America/Cuiaba",
      "America/Porto_Velho",
      "America/Rio_Branco",
      "Europe/Lisbon",
      "Europe/London",
      "Europe/Paris",
      "America/New_York",
      "America/Chicago",
      "America/Denver",
      "America/Los_Angeles",
      "Asia/Tokyo",
      "Asia/Shanghai",
      "Asia/Kolkata",
      "Australia/Sydney",
    ].forEach((timezone) => zones.add(timezone));
  }
  zones.add(currentTimezone);
  return [...zones].sort((left, right) => left.localeCompare(right));
}

function timezoneOffsetLabel(timezone: string): string {
  try {
    const offset = new Intl.DateTimeFormat("en", {
      timeZone: timezone,
      timeZoneName: "shortOffset",
    })
      .formatToParts(new Date())
      .find((part) => part.type === "timeZoneName")
      ?.value.replace("GMT", "UTC");
    return offset ?? "UTC";
  } catch {
    return "UTC";
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  const data = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("aquaflow:unauthorized"));
    throw new Error(
      data.message ?? data.detail?.message ?? "Não foi possível concluir a solicitação.",
    );
  }
  return data;
}

export default function Dashboard() {
  const router = useRouter();
  const [view, setView] = useState<"overview" | "meters" | "alerts" | "settings">("overview");
  const [properties, setProperties] = useState<Property[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceHealth, setDeviceHealth] = useState<Record<string, DeviceHealth>>({});
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertVisibleLimit, setAlertVisibleLimit] = useState(5);
  const [alertsCursor, setAlertsCursor] = useState<string | null>(null);
  const [alertsHasMore, setAlertsHasMore] = useState(false);
  const [loadingMoreAlerts, setLoadingMoreAlerts] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [periodDays, setPeriodDays] = useState<7 | 30 | 90>(7);
  const [consumption, setConsumption] = useState<Consumption | null>(null);
  const [hourlyConsumption, setHourlyConsumption] = useState<Consumption | null>(null);
  const [hourlyWindowEnd, setHourlyWindowEnd] = useState<number | null>(null);
  const [hourlyConsumptionError, setHourlyConsumptionError] = useState("");
  const [dashboardHealth, setDashboardHealth] = useState<DashboardHealth | null>(null);
  const [dashboardHealthError, setDashboardHealthError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newProperty, setNewProperty] = useState("");
  const [newDevice, setNewDevice] = useState("");
  const [newSerial, setNewSerial] = useState("");
  const [provisioned, setProvisioned] = useState<{ key: string; serial: string } | null>(null);
  const [deviceNotice, setDeviceNotice] = useState<{
    kind: "success" | "error";
    message: string;
  } | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [editingDeviceId, setEditingDeviceId] = useState("");
  const [editingDeviceName, setEditingDeviceName] = useState("");
  const [editingDeviceInterval, setEditingDeviceInterval] = useState("300");
  const [deviceActionId, setDeviceActionId] = useState("");
  const [retiringDeviceId, setRetiringDeviceId] = useState("");
  const [alertActionId, setAlertActionId] = useState("");
  const [alertNotice, setAlertNotice] = useState("");
  const [simulating, setSimulating] = useState(false);
  const selected = properties.find((item) => item.id === selectedId);
  const selectedDevices = useMemo(
    () => devices.filter((item) => item.property_id === selectedId),
    [devices, selectedId],
  );
  const openAlertCount = alerts.filter((alert) => alert.status === "open").length;
  const acknowledgedAlertCount = alerts.filter((alert) => alert.status === "acknowledged").length;
  const activeAlertCount = openAlertCount + acknowledgedAlertCount;

  const load = useCallback(
    async (propertyId?: string) => {
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
        if (!activeId) {
          setConsumption(null);
          setAlerts([]);
          setAlertVisibleLimit(5);
          setAlertsCursor(null);
          setAlertsHasMore(false);
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Falha ao carregar os dados.");
      } finally {
        setLoading(false);
      }
    },
    [selectedId],
  );

  useEffect(() => {
    const syncView = () =>
      setView(resolveDashboardView(new URLSearchParams(window.location.search).get("view")));
    syncView();
    window.addEventListener("popstate", syncView);
    return () => window.removeEventListener("popstate", syncView);
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
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
    const start = new Date(end.getTime() - periodDays * 24 * 60 * 60 * 1000);
    const params = new URLSearchParams({
      start: start.toISOString(),
      end: end.toISOString(),
      granularity: "day",
    });
    api<Consumption>(`properties/${selectedId}/consumption?${params}`)
      .then((result) => {
        if (!cancelled) setConsumption(result);
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setError(caught instanceof Error ? caught.message : "Falha ao carregar consumo.");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, loading, periodDays]);
  useEffect(() => {
    if (!selectedId || loading || view !== "overview") return;
    let cancelled = false;
    const refreshHealth = () =>
      api<DashboardHealth>(`properties/${selectedId}/dashboard-health`)
        .then((result) => {
          if (!cancelled) {
            setDashboardHealth(result);
            setDashboardHealthError("");
          }
        })
        .catch((caught: unknown) => {
          if (!cancelled)
            setDashboardHealthError(
              caught instanceof Error ? caught.message : "Falha ao consultar a saúde do sistema.",
            );
        });
    void refreshHealth();
    const timer = window.setInterval(refreshHealth, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedId, loading, view]);
  useEffect(() => {
    if (!selectedId || loading || view !== "overview") return;
    let cancelled = false;
    const refreshHourlyConsumption = () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
      const params = new URLSearchParams({
        start: start.toISOString(),
        end: end.toISOString(),
        granularity: "hour",
        limit: "48",
      });
      api<Consumption>(`properties/${selectedId}/consumption?${params}`)
        .then((result) => {
          if (!cancelled) {
            setHourlyConsumption(result);
            setHourlyWindowEnd(end.getTime());
            setHourlyConsumptionError("");
          }
        })
        .catch((caught: unknown) => {
          if (!cancelled)
            setHourlyConsumptionError(
              caught instanceof Error ? caught.message : "Não foi possível carregar este gráfico.",
            );
        });
    };
    void refreshHourlyConsumption();
    const timer = window.setInterval(refreshHourlyConsumption, 5 * 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedId, loading, view]);
  useEffect(() => {
    if (view !== "meters" || selectedDevices.length === 0) return;
    let cancelled = false;
    Promise.all(
      selectedDevices.map(async (device) => {
        const health = await api<DeviceHealth>(`devices/${device.id}/health`);
        return [device.id, health] as const;
      }),
    )
      .then((results) => {
        if (!cancelled) setDeviceHealth(Object.fromEntries(results));
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setError(caught instanceof Error ? caught.message : "Falha ao consultar os medidores.");
      });
    return () => {
      cancelled = true;
    };
  }, [view, selectedDevices]);
  useEffect(() => {
    if (!selectedId || loading) return;
    let cancelled = false;
    setAlerts([]);
    setAlertVisibleLimit(5);
    setAlertsCursor(null);
    setAlertsHasMore(false);
    api<{ items: Alert[]; cursor: string | null; has_more: boolean }>(
      `properties/${selectedId}/alerts?limit=200`,
    )
      .then((alertResult) => {
        if (!cancelled) {
          setAlerts(alertResult.items);
          setAlertsCursor(alertResult.cursor);
          setAlertsHasMore(alertResult.has_more);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Falha ao carregar alertas.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, loading]);

  async function createProperty(event: FormEvent) {
    event.preventDefault();
    if (!newProperty.trim()) return;
    try {
      const result = await api<Property>("properties", {
        method: "POST",
        body: JSON.stringify({ name: newProperty.trim() }),
      });
      setNewProperty("");
      await load(result.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Não foi possível criar o imóvel.");
    }
  }

  async function createDevice(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !newDevice.trim() || !newSerial.trim()) return;
    setProvisioning(true);
    setDeviceNotice(null);
    setProvisioned(null);
    try {
      const result = await api<Device & { device_key: string }>("devices", {
        method: "POST",
        body: JSON.stringify({
          property_id: selectedId,
          name: newDevice.trim(),
          serial_number: newSerial.trim(),
        }),
      });
      setProvisioned({ key: result.device_key, serial: result.serial_number });
      setCopiedKey(false);
      setNewDevice("");
      setNewSerial("");
      await load(selectedId);
      setDeviceNotice({ kind: "success", message: `${result.name} foi adicionado à propriedade.` });
    } catch (caught) {
      setDeviceNotice({
        kind: "error",
        message: caught instanceof Error ? caught.message : "Não foi possível adicionar o medidor.",
      });
    } finally {
      setProvisioning(false);
    }
  }

  function beginDeviceEdit(device: Device) {
    setRetiringDeviceId("");
    setEditingDeviceId(device.id);
    setEditingDeviceName(device.name);
    setEditingDeviceInterval(String(device.expected_interval_seconds));
    setDeviceNotice(null);
  }

  async function saveDevice(event: FormEvent, device: Device) {
    event.preventDefault();
    const interval = Number(editingDeviceInterval);
    if (
      !editingDeviceName.trim() ||
      !Number.isInteger(interval) ||
      interval < 30 ||
      interval > 86400
    ) {
      setDeviceNotice({
        kind: "error",
        message: "Informe um nome e um intervalo entre 30 e 86.400 segundos.",
      });
      return;
    }
    setDeviceActionId(device.id);
    setDeviceNotice(null);
    try {
      const updated = await api<Device>(`devices/${device.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: editingDeviceName.trim(),
          expected_interval_seconds: interval,
        }),
      });
      setDevices((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditingDeviceId("");
      setDeviceNotice({ kind: "success", message: `${updated.name} foi atualizado.` });
    } catch (caught) {
      setDeviceNotice({
        kind: "error",
        message: caught instanceof Error ? caught.message : "Não foi possível atualizar o medidor.",
      });
    } finally {
      setDeviceActionId("");
    }
  }

  async function retireDevice(device: Device) {
    setDeviceActionId(device.id);
    setRetiringDeviceId("");
    setDeviceNotice(null);
    try {
      await api<void>(`devices/${device.id}`, { method: "DELETE" });
      setDevices((current) => current.filter((item) => item.id !== device.id));
      setDeviceHealth((current) => {
        const next = { ...current };
        delete next[device.id];
        return next;
      });
      if (editingDeviceId === device.id) setEditingDeviceId("");
      setDeviceNotice({
        kind: "success",
        message: `${device.name} foi retirado. O histórico foi preservado.`,
      });
    } catch (caught) {
      setDeviceNotice({
        kind: "error",
        message: caught instanceof Error ? caught.message : "Não foi possível retirar o medidor.",
      });
    } finally {
      setDeviceActionId("");
    }
  }

  async function updateAlert(alert: Alert, action: "acknowledge" | "resolve" | "false-positive") {
    setAlertActionId(alert.id);
    setAlertNotice("");
    try {
      const updated = await api<Alert>(`alerts/${alert.id}/${action}`, { method: "POST" });
      setAlerts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setAlertNotice(
        action === "acknowledge"
          ? "Alerta reconhecido."
          : action === "resolve"
            ? "Alerta resolvido."
            : "Alerta marcado como falso positivo.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Não foi possível atualizar o alerta.");
    } finally {
      setAlertActionId("");
    }
  }

  async function loadMoreAlerts() {
    if (alertVisibleLimit < alerts.length) {
      setAlertVisibleLimit((current) => current + 5);
      return;
    }
    if (!alertsHasMore || !alertsCursor || !selectedId) return;
    setLoadingMoreAlerts(true);
    try {
      const page = await api<{ items: Alert[]; cursor: string | null; has_more: boolean }>(
        `properties/${selectedId}/alerts?limit=200&cursor=${encodeURIComponent(alertsCursor)}`,
      );
      setAlerts((current) => [...current, ...page.items]);
      setAlertsCursor(page.cursor);
      setAlertsHasMore(page.has_more);
      setAlertVisibleLimit((current) => current + 5);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Não foi possível carregar mais alertas.",
      );
    } finally {
      setLoadingMoreAlerts(false);
    }
  }

  async function simulateReadings() {
    if (!provisioned) return;
    setSimulating(true);
    setError("");
    setDeviceNotice(null);
    try {
      const now = Date.now();
      const points = [
        { minutesAgo: 10, liters: 1000 },
        { minutesAgo: 5, liters: 1002 },
        { minutesAgo: 0, liters: 1006 },
      ];
      for (const point of points) {
        await api("ingestion/telemetry", {
          method: "POST",
          headers: { "X-Device-Key": provisioned.key },
          body: JSON.stringify({
            device_serial: provisioned.serial,
            event_id: `demo-${now}-${point.minutesAgo}`,
            recorded_at: new Date(now - point.minutesAgo * 60_000).toISOString(),
            cumulative_volume_liters: point.liters,
          }),
        });
      }
      await load(selectedId);
      setDeviceNotice({
        kind: "success",
        message: "Leituras de demonstração enviadas; o painel foi atualizado.",
      });
    } catch (caught) {
      setDeviceNotice({
        kind: "error",
        message: caught instanceof Error ? caught.message : "Não foi possível enviar as leituras.",
      });
    } finally {
      setSimulating(false);
    }
  }

  async function copyDeviceKey() {
    if (!provisioned) return;
    try {
      await navigator.clipboard.writeText(provisioned.key);
      setCopiedKey(true);
    } catch {
      setDeviceNotice({
        kind: "error",
        message: "Não foi possível copiar automaticamente. Selecione e copie a chave exibida.",
      });
    }
  }

  async function logout() {
    try {
      await api("auth/logout", { method: "POST", body: "{}" });
    } finally {
      router.replace("/");
    }
  }

  async function savePropertySettings(patch: PropertyPatch) {
    if (!selectedId) throw new Error("Selecione uma propriedade para editar.");
    const updated = await api<Property>(`properties/${selectedId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    setProperties((current) =>
      current.map((property) => (property.id === updated.id ? updated : property)),
    );
    return updated;
  }

  function navigateView(destination: "overview" | "meters" | "alerts" | "settings") {
    setView(destination);
    window.scrollTo({ top: 0, behavior: "instant" });
    window.history.pushState(
      {},
      "",
      destination === "overview" ? "/dashboard" : `/dashboard?view=${destination}`,
    );
  }

  const chartData = (consumption?.items ?? []).map((item) => ({
    ...item,
    day: new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(
      new Date(item.bucket_start),
    ),
  }));
  const hourlyChartData = useMemo(() => {
    if (hourlyWindowEnd === null) return [];
    const hourMs = 60 * 60 * 1000;
    const end = hourlyWindowEnd;
    const firstHour = Math.floor((end - 24 * hourMs) / hourMs) * hourMs;
    const volumeByHour = new Map(
      (hourlyConsumption?.items ?? []).map((item) => [
        Math.floor(new Date(item.bucket_start).getTime() / hourMs) * hourMs,
        item.volume_liters,
      ]),
    );
    const hourLabel = new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      timeZone: selected?.timezone ?? "UTC",
      hourCycle: "h23",
    });
    return Array.from({ length: 24 }, (_, index) => {
      const timestamp = firstHour + index * hourMs;
      return {
        hour: hourLabel.format(timestamp),
        volume_liters: volumeByHour.get(timestamp) ?? null,
      };
    });
  }, [hourlyConsumption, hourlyWindowEnd, selected?.timezone]);
  const recentAlertChartData = useMemo(() => {
    if (!dashboardHealth) return [];
    const since = new Date(dashboardHealth.checked_at).getTime() - 24 * 60 * 60 * 1000;
    const labels: Record<string, string> = {
      continuous_flow: "Fluxo contínuo",
      night_consumption: "Consumo à noite",
      device_offline: "Medidor sem comunicação",
      ml_anomaly: "Mudança no consumo",
    };
    const totals = new Map<string, number>();
    for (const alert of alerts) {
      if (new Date(alert.detected_at).getTime() < since) continue;
      const label = labels[alert.detector_type] ?? "Outros avisos";
      totals.set(label, (totals.get(label) ?? 0) + 1);
    }
    return [...totals].map(([reason, count]) => ({ reason, count }));
  }, [alerts, dashboardHealth]);

  return (
    <main className="dashboard-page">
      <header className="app-header">
        <div className="app-header-inner">
          <Brand />
          <nav className="app-nav" aria-label="Navegação principal">
            {(
              [
                ["overview", "Visão geral"],
                ["meters", "Medidores"],
                ["alerts", "Alertas"],
                ["settings", "Configurações"],
              ] as const
            ).map(([destination, label]) => (
              <button
                key={destination}
                type="button"
                aria-current={view === destination ? "page" : undefined}
                className={`nav-link${view === destination ? " nav-link--active" : ""}`}
                onClick={() => navigateView(destination)}
              >
                {label}
                {destination === "alerts" && activeAlertCount > 0 && (
                  <span className="nav-count" aria-label="alertas em acompanhamento">
                    {activeAlertCount}
                  </span>
                )}
              </button>
            ))}
          </nav>
          <div className="header-actions">
            <ThemeToggle />
            <button onClick={logout} className="button button--quiet">
              Sair
            </button>
          </div>
        </div>
      </header>
      <div className="dashboard-content" id="overview">
        <section className="dashboard-heading">
          <div>
            {view === "overview" && (
              <span className="eyebrow">
                <span className="eyebrow-dot" />
                Sua casa, em perspectiva
              </span>
            )}
            <h1>
              {view === "meters"
                ? "Seus medidores"
                : view === "alerts"
                  ? "Acompanhamento"
                  : view === "settings"
                    ? "Configurações"
                    : "Sua água, de perto"}
            </h1>
            <p>
              {view === "meters"
                ? "Acompanhe cada ponto de consumo da sua propriedade."
                : view === "alerts"
                  ? "Veja o que mudou e acompanhe o que precisa da sua atenção."
                  : view === "settings"
                    ? "Deixe o acompanhamento do seu jeito."
                    : "Entenda seus hábitos. Perceba mudanças. Cuide do que importa."}
            </p>
          </div>
          {properties.length > 0 && (
            <label className="property-picker">
              <span>Propriedade</span>
              <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </section>
        {error && (
          <p role="alert" className="notice notice--error dashboard-notice">
            {error}
          </p>
        )}
        {properties.length === 0 && !loading ? (
          <section className="onboarding-card">
            <div className="onboarding-art" aria-hidden="true">
              <span className="onboarding-drop">⌁</span>
              <span className="onboarding-ring onboarding-ring--one" />
              <span className="onboarding-ring onboarding-ring--two" />
            </div>
            <div className="onboarding-copy">
              <span className="eyebrow">Vamos começar</span>
              <h2>Crie sua primeira propriedade</h2>
              <p>
                Organize medidores e leituras por local. Depois, você pode conectar um dispositivo e
                acompanhar o consumo aqui.
              </p>
              <form onSubmit={createProperty} className="inline-form">
                <label className="field">
                  Nome da propriedade
                  <input
                    value={newProperty}
                    onChange={(event) => setNewProperty(event.target.value)}
                    placeholder="Ex.: Minha casa"
                    required
                  />
                </label>
                <button className="button button--primary">
                  Criar propriedade <span aria-hidden="true">→</span>
                </button>
              </form>
            </div>
          </section>
        ) : loading && properties.length === 0 ? (
          <LoadingCard />
        ) : (
          <>
            {view === "settings" && selected && (
              <PropertySettingsForm
                key={selected.id}
                property={selected}
                onSave={savePropertySettings}
              />
            )}
            {view === "overview" && (
              <section className="metrics-grid" aria-label="Resumo de consumo">
                <Metric
                  featured
                  label="Seu consumo"
                  value={`${(consumption?.summary.total_volume_liters ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}`}
                  unit="L"
                  note={`nos últimos ${periodDays} dias`}
                />
                <Metric
                  label="Em relação ao período anterior"
                  value={
                    consumption?.summary.change_percent === null ||
                    consumption?.summary.change_percent === undefined
                      ? "—"
                      : `${consumption.summary.change_percent > 0 ? "+" : ""}${consumption.summary.change_percent.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
                  }
                  note={
                    consumption?.summary.change_volume_liters == null
                      ? "sem dados do período anterior"
                      : `${consumption.summary.change_volume_liters > 0 ? "+" : ""}${consumption.summary.change_volume_liters.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} L vs. período anterior`
                  }
                />
                <Metric
                  label="Medidores"
                  value={`${selectedDevices.length}`}
                  note={
                    selectedDevices.length
                      ? `${selectedDevices.filter((device) => device.last_seen_at).length} receberam leitura`
                      : "aguardando conexão"
                  }
                />
                <Metric
                  label="Para acompanhar"
                  value={`${activeAlertCount}`}
                  note={`${openAlertCount} ${openAlertCount === 1 ? "aberto" : "abertos"} · ${acknowledgedAlertCount} ${acknowledgedAlertCount === 1 ? "reconhecido" : "reconhecidos"}`}
                />
              </section>
            )}
            {view !== "alerts" && view !== "settings" && (
              <section
                className={`dashboard-grid${view !== "overview" ? " dashboard-grid--single" : ""}`}
              >
                {view === "overview" && (
                  <article className="surface chart-card">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">Ao longo dos dias</span>
                        <h2>Consumo diário</h2>
                      </div>
                      <label className="sr-only" htmlFor="consumption-period">
                        Período do gráfico
                      </label>
                      <select
                        id="consumption-period"
                        className="period-select"
                        value={periodDays}
                        onChange={(event) =>
                          setPeriodDays(Number(event.target.value) as 7 | 30 | 90)
                        }
                      >
                        <option value={7}>7 dias</option>
                        <option value={30}>30 dias</option>
                        <option value={90}>90 dias</option>
                      </select>
                    </div>
                    <p className="section-subtitle">Quanto você consumiu a cada dia, em litros</p>
                    <div
                      className="chart-wrap"
                      role="img"
                      aria-label={`Gráfico do consumo diário nos últimos ${periodDays} dias`}
                    >
                      <p className="sr-only">
                        {chartData.length
                          ? chartData
                              .map((point) => `${point.day}: ${point.volume_liters} litros`)
                              .join(". ")
                          : "Ainda não há leituras suficientes para exibir o gráfico."}
                      </p>
                      {chartData.length ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart
                            data={chartData}
                            margin={{ top: 12, right: 8, left: -18, bottom: 0 }}
                          >
                            <defs>
                              <linearGradient id="consumptionFill" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.34} />
                                <stop offset="95%" stopColor="var(--accent)" stopOpacity={0.015} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid
                              vertical={false}
                              stroke="var(--chart-grid)"
                              strokeDasharray="3 6"
                            />
                            <XAxis
                              dataKey="day"
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "var(--muted)", fontSize: 12 }}
                              dy={10}
                            />
                            <YAxis
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "var(--muted)", fontSize: 12 }}
                            />
                            <Tooltip
                              formatter={(value) => [
                                `${Number(value).toLocaleString("pt-BR")} L`,
                                "Consumo",
                              ]}
                              contentStyle={{
                                borderRadius: 14,
                                borderColor: "var(--line)",
                                background: "var(--surface)",
                                color: "var(--ink)",
                              }}
                            />
                            <Area
                              type="monotone"
                              dataKey="volume_liters"
                              stroke="var(--accent)"
                              strokeWidth={3}
                              fill="url(#consumptionFill)"
                              activeDot={{
                                r: 5,
                                fill: "var(--accent-strong)",
                                stroke: "var(--surface)",
                                strokeWidth: 2,
                              }}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="empty-chart">
                          <span className="empty-chart-icon" aria-hidden="true">
                            ≈
                          </span>
                          <p>Ainda não há consumo para exibir</p>
                          <span>Conecte um medidor e envie leituras para começar.</span>
                        </div>
                      )}
                    </div>
                    <div className="chart-foot">
                      <span>
                        <i aria-hidden="true" />
                        Consumo calculado
                      </span>
                      <span>Períodos sem leitura não são contabilizados como zero.</span>
                    </div>
                  </article>
                )}
                {view === "meters" && (
                  <article className="surface meters-card" id="meters">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">Dispositivos</span>
                        <h2>Seus medidores</h2>
                      </div>
                      <span className="count-chip">
                        {selectedDevices.length.toString().padStart(2, "0")}
                      </span>
                    </div>
                    <p className="section-subtitle">
                      Associados a {selected?.name ?? "esta propriedade"}
                    </p>
                    {deviceNotice && (
                      <p
                        role={deviceNotice.kind === "error" ? "alert" : "status"}
                        className={`form-notice form-notice--${deviceNotice.kind}`}
                      >
                        {deviceNotice.message}
                      </p>
                    )}
                    {selectedDevices.length ? (
                      <ul className="meter-list">
                        {selectedDevices.map((device) => {
                          const health = deviceHealth[device.id];
                          const lastSeen = health?.last_seen_at ?? device.last_seen_at;
                          const connected = health
                            ? health.connectivity === "online"
                            : lastSeen !== null &&
                              Date.now() - new Date(lastSeen).getTime() <=
                                device.expected_interval_seconds * 2 * 1000;
                          const neverConnected =
                            health?.connectivity === "never_connected" ||
                            (!health && lastSeen === null);
                          const reading = health?.latest_reading;
                          return (
                            <li
                              key={device.id}
                              className={`meter-row${editingDeviceId === device.id ? " meter-row--editing" : ""}`}
                            >
                              <span className="meter-icon" aria-hidden="true">
                                <svg viewBox="0 0 24 24" fill="none">
                                  <path
                                    d="M4 15.5a8 8 0 1 1 16 0M12 12l4-4M5 19h14"
                                    stroke="currentColor"
                                    strokeWidth="1.7"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                  />
                                </svg>
                              </span>
                              {editingDeviceId === device.id ? (
                                <form
                                  className="meter-edit-form"
                                  onSubmit={(event) => void saveDevice(event, device)}
                                >
                                  <label>
                                    Nome
                                    <input
                                      value={editingDeviceName}
                                      onChange={(event) => setEditingDeviceName(event.target.value)}
                                      required
                                      maxLength={120}
                                    />
                                  </label>
                                  <label>
                                    Intervalo de leitura (segundos)
                                    <input
                                      type="number"
                                      min={30}
                                      max={86400}
                                      step={1}
                                      value={editingDeviceInterval}
                                      onChange={(event) =>
                                        setEditingDeviceInterval(event.target.value)
                                      }
                                      required
                                    />
                                  </label>
                                  <div className="meter-actions">
                                    <button
                                      className="button button--outline"
                                      disabled={deviceActionId === device.id}
                                    >
                                      {deviceActionId === device.id ? "Salvando…" : "Salvar"}
                                    </button>
                                    <button
                                      type="button"
                                      className="button button--quiet"
                                      onClick={() => setEditingDeviceId("")}
                                    >
                                      Cancelar
                                    </button>
                                  </div>
                                </form>
                              ) : (
                                <>
                                  <div className="meter-info">
                                    <strong>{device.name}</strong>
                                    <small>
                                      {device.serial_number} ·{" "}
                                      {device.serial_number.startsWith("AF-DEMO-")
                                        ? "Demonstração"
                                        : "Dispositivo cadastrado"}
                                    </small>
                                    {reading && (
                                      <small>
                                        Última leitura:{" "}
                                        {new Intl.DateTimeFormat("pt-BR", {
                                          dateStyle: "short",
                                          timeStyle: "short",
                                        }).format(new Date(reading.recorded_at))}
                                      </small>
                                    )}
                                    {reading && (
                                      <details className="device-details">
                                        <summary>Informações do medidor</summary>
                                        <small>
                                          {reading.battery_percent !== null
                                            ? `Bateria ${reading.battery_percent}% · `
                                            : ""}
                                          {reading.signal_dbm !== null
                                            ? `Sinal ${reading.signal_dbm} dBm · `
                                            : ""}
                                          {reading.firmware_version
                                            ? `Firmware ${reading.firmware_version}`
                                            : ""}
                                        </small>
                                      </details>
                                    )}
                                  </div>
                                  <span
                                    className={`meter-status${connected ? " meter-status--online" : " meter-status--offline"}`}
                                  >
                                    {connected
                                      ? "Recebendo"
                                      : neverConnected
                                        ? "Nunca conectado"
                                        : "Sem comunicação"}
                                  </span>
                                  {retiringDeviceId === device.id ? (
                                    <div
                                      className="meter-retire-confirm"
                                      role="group"
                                      aria-label={`Confirmar retirada de ${device.name}`}
                                    >
                                      <p>
                                        Retirar <strong>{device.name}</strong>? O histórico será
                                        preservado.
                                      </p>
                                      <div className="meter-actions">
                                        <button
                                          type="button"
                                          className="button button--quiet"
                                          onClick={() => setRetiringDeviceId("")}
                                        >
                                          Cancelar
                                        </button>
                                        <button
                                          type="button"
                                          className="button button--quiet meter-retire"
                                          disabled={deviceActionId === device.id}
                                          onClick={() => void retireDevice(device)}
                                        >
                                          {deviceActionId === device.id
                                            ? "Retirando…"
                                            : "Confirmar retirada"}
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <div className="meter-actions">
                                      <button
                                        type="button"
                                        className="button button--quiet"
                                        disabled={deviceActionId === device.id}
                                        onClick={() => beginDeviceEdit(device)}
                                      >
                                        Editar
                                      </button>
                                      <button
                                        type="button"
                                        className="button button--quiet meter-retire"
                                        disabled={deviceActionId === device.id}
                                        onClick={() => setRetiringDeviceId(device.id)}
                                      >
                                        Retirar
                                      </button>
                                    </div>
                                  )}
                                </>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <div className="empty-meter">Nenhum medidor conectado ainda.</div>
                    )}
                    <form onSubmit={createDevice} className="device-form">
                      <h3>Adicionar medidor de teste</h3>
                      <p className="form-help">
                        Experimente o acompanhamento com leituras simuladas.
                      </p>
                      <label className="field">
                        <span className="sr-only">Nome do medidor</span>
                        <input
                          value={newDevice}
                          onChange={(event) => setNewDevice(event.target.value)}
                          placeholder="Nome do medidor"
                          required
                        />
                      </label>
                      <label className="field">
                        <span className="sr-only">Número de série</span>
                        <input
                          value={newSerial}
                          onChange={(event) => setNewSerial(event.target.value)}
                          placeholder="Número de série"
                          required
                        />
                      </label>
                      <button disabled={provisioning} className="button button--outline">
                        {provisioning ? "Adicionando medidor…" : "Adicionar medidor"}{" "}
                        <span aria-hidden="true">→</span>
                      </button>
                    </form>
                  </article>
                )}
              </section>
            )}
            {view === "meters" && provisioned && (
              <section className="provision-card">
                <div>
                  <span className="eyebrow">Credencial do dispositivo</span>
                  <h2>Medidor pronto para configurar</h2>
                  <p>A chave é exibida apenas nesta sessão. Copie-a e configure no dispositivo.</p>
                  <code>{provisioned.key}</code>
                  <button
                    onClick={() => void copyDeviceKey()}
                    className="button button--quiet copy-key"
                  >
                    {copiedKey ? "Chave copiada" : "Copiar chave"}
                  </button>
                </div>
                <button
                  disabled={simulating}
                  onClick={() => void simulateReadings()}
                  className="button button--primary"
                >
                  {simulating ? "Enviando leituras…" : "Simular leituras"}
                </button>
              </section>
            )}
            {view === "alerts" && (
              <>
                <section className="surface alerts-card" id="alerts" aria-labelledby="alerts-title">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">Acompanhamento</span>
                      <h2 id="alerts-title">Alertas da propriedade</h2>
                    </div>
                    <span className="count-chip" aria-label="alertas em acompanhamento">
                      {activeAlertCount.toString().padStart(2, "0")}
                    </span>
                  </div>
                  <p className="section-subtitle">
                    Avisos de consumo, conexão e análises experimentais, com os detalhes do período
                    observados.
                  </p>
                  {alertNotice && (
                    <p role="status" className="form-notice form-notice--success">
                      {alertNotice}
                    </p>
                  )}
                  {alerts.length ? (
                    <>
                      <ul className="alert-list" id="alerts-list">
                        {alerts.slice(0, alertVisibleLimit).map((alert) => {
                          const observedRate = alert.evidence.observed_flow_rate_liters_minute;
                          const observedDuration = alert.evidence.observed_duration_minutes;
                          const isDemoSample = alert.evidence.is_demo_sample === true;
                          const detectorLabel =
                            alert.detector_type === "continuous_flow"
                              ? "Fluxo contínuo"
                              : alert.detector_type === "night_consumption"
                                ? "Consumo noturno"
                                : alert.detector_type === "device_offline"
                                  ? "Medidor sem comunicação"
                                  : alert.detector_type === "ml_anomaly"
                                    ? "Possível mudança de consumo"
                                    : alert.detector_type === "demo_sample"
                                      ? "Alerta demonstrativo"
                                      : alert.detector_type;
                          return (
                            <li className="alert-row" key={alert.id}>
                              <div className="alert-main">
                                <div className="alert-title-line">
                                  <strong>{detectorLabel}</strong>
                                  <span
                                    className={`severity-badge severity-badge--${alert.severity}`}
                                  >
                                    {alert.severity === "high"
                                      ? "Alta"
                                      : alert.severity === "medium"
                                        ? "Média"
                                        : "Baixa"}
                                  </span>
                                  <span className={`alert-status alert-status--${alert.status}`}>
                                    {alert.status === "open"
                                      ? "Aberto"
                                      : alert.status === "acknowledged"
                                        ? "Reconhecido"
                                        : alert.status === "resolved"
                                          ? "Resolvido"
                                          : "Falso positivo"}
                                  </span>
                                  {isDemoSample && <span className="demo-badge">Simulado</span>}
                                  {alert.detector_type === "ml_anomaly" && (
                                    <span className="demo-badge">Experimental</span>
                                  )}
                                </div>
                                <p>
                                  {alert.detector_type === "ml_anomaly"
                                    ? "A análise experimental encontrou uma possível mudança no padrão de consumo. Confira as leituras para entender o que aconteceu."
                                    : alert.reason}
                                </p>
                                <small>
                                  {typeof observedRate === "number"
                                    ? `${observedRate.toLocaleString("pt-BR")} L/min · `
                                    : ""}
                                  {typeof observedDuration === "number"
                                    ? `${observedDuration} min · `
                                    : ""}
                                  {devices.find((device) => device.id === alert.device_id)?.name ??
                                    "Medidor"}{" "}
                                  ·{" "}
                                  {new Intl.DateTimeFormat("pt-BR", {
                                    dateStyle: "short",
                                    timeStyle: "short",
                                  }).format(new Date(alert.detected_at))}
                                </small>
                                <AlertEvidence alert={alert} />
                              </div>
                              <div className="alert-actions">
                                {alert.status === "open" && (
                                  <button
                                    disabled={alertActionId === alert.id}
                                    className="button button--outline"
                                    onClick={() => void updateAlert(alert, "acknowledge")}
                                  >
                                    Estou ciente
                                  </button>
                                )}
                                {(alert.status === "open" || alert.status === "acknowledged") && (
                                  <>
                                    <button
                                      disabled={alertActionId === alert.id}
                                      className="button button--quiet"
                                      onClick={() => void updateAlert(alert, "resolve")}
                                    >
                                      Marcar resolvido
                                    </button>
                                    <button
                                      disabled={alertActionId === alert.id}
                                      className="button button--quiet"
                                      onClick={() => void updateAlert(alert, "false-positive")}
                                    >
                                      Não é um problema
                                    </button>
                                  </>
                                )}
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                      {(alertVisibleLimit < alerts.length || alertsHasMore) && (
                        <button
                          className="button button--outline alert-load-more"
                          aria-controls="alerts-list"
                          disabled={loadingMoreAlerts}
                          onClick={() => void loadMoreAlerts()}
                        >
                          {loadingMoreAlerts ? "Carregando…" : "Carregar mais"}
                        </button>
                      )}
                    </>
                  ) : (
                    <div className="empty-meter alert-empty">
                      Nenhum alerta registrado para esta propriedade.
                    </div>
                  )}
                </section>
              </>
            )}
            {view === "overview" && (
              <section className="surface system-health-card" aria-labelledby="system-health-title">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">Resumo</span>
                    <h2 id="system-health-title">Acompanhamento da sua água</h2>
                  </div>
                  <span className="health-updated">
                    {dashboardHealth
                      ? `Atualizado ${formatDate(dashboardHealth.checked_at)}`
                      : "Atualizando…"}
                  </span>
                </div>
                {dashboardHealthError ? (
                  <p className="notice notice--error" role="alert">
                    {dashboardHealthError}
                  </p>
                ) : dashboardHealth ? (
                  <OperationalHealth
                    health={dashboardHealth}
                    hourlyData={hourlyChartData}
                    hourlyLoading={!hourlyConsumption && !hourlyConsumptionError}
                    hourlyError={hourlyConsumptionError}
                    alertData={recentAlertChartData}
                    alertDataMayBePartial={alertsHasMore}
                  />
                ) : (
                  <p className="section-subtitle">Buscando as últimas atualizações…</p>
                )}
              </section>
            )}
            {view === "overview" && (
              <section className="overview-shortcuts" aria-label="Acessos rápidos">
                <button className="surface shortcut-card" onClick={() => navigateView("meters")}>
                  <span className="eyebrow">Dispositivos</span>
                  <strong>{selectedDevices.length} medidores</strong>
                  <span>Veja as últimas leituras de cada medidor</span>
                  <b aria-hidden="true">→</b>
                </button>
                <button className="surface shortcut-card" onClick={() => navigateView("alerts")}>
                  <span className="eyebrow">Acompanhamento</span>
                  <strong>{activeAlertCount} alertas em acompanhamento</strong>
                  <span>Entenda os avisos e acompanhe a resolução</span>
                  <b aria-hidden="true">→</b>
                </button>
              </section>
            )}
            <p className="dashboard-footnote">
              O consumo é estimado entre leituras recebidas. Uma anomalia indica um comportamento
              fora do padrão, não a localização física de um vazamento.
            </p>
          </>
        )}
      </div>
    </main>
  );
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function mqttStatusLabel(status: DashboardHealth["ingestion"]["mqtt_status"]): string {
  if (status === "connected") return "Conectado";
  if (status === "disconnected") return "Desconectado";
  return "Sem resposta do serviço";
}

function modelStatusLabel(status: DashboardHealth["model_pipeline"]["status"]): string {
  if (status === "healthy") return "Operando";
  if (status === "degraded") return "Com falhas recentes";
  return "Indisponível";
}

function ServiceStatus({
  label,
  status,
  tone,
}: {
  label: string;
  status: string;
  tone: "ok" | "warning" | "offline";
}) {
  return (
    <li className={`health-service health-service--${tone}`}>
      <span className="health-service__dot" aria-hidden="true" />
      <span>{label}</span>
      <strong>{status}</strong>
    </li>
  );
}

function HealthBar({ label, value, maximum }: { label: string; value: number; maximum: number }) {
  return (
    <div className="health-bar">
      <div className="health-bar__label">
        <span>{label}</span>
        <strong>{value.toLocaleString("pt-BR")}</strong>
      </div>
      <div className="health-bar__track" aria-hidden="true">
        <span style={{ width: `${maximum > 0 ? (value / maximum) * 100 : 0}%` }} />
      </div>
    </div>
  );
}

function OperationalHealth({
  health,
  hourlyData,
  hourlyLoading,
  hourlyError,
  alertData,
  alertDataMayBePartial,
}: {
  health: DashboardHealth;
  hourlyData: Array<{ hour: string; volume_liters: number | null }>;
  hourlyLoading: boolean;
  hourlyError: string;
  alertData: Array<{ reason: string; count: number }>;
  alertDataMayBePartial: boolean;
}) {
  const mqtt = health.ingestion;
  const model = health.model_pipeline;
  const mqttMaximum = Math.max(
    mqtt.mqtt_messages_received,
    mqtt.mqtt_messages_forwarded,
    mqtt.mqtt_messages_rejected,
  );
  const scored = model.scored_inferences_last_24h;
  const positive = Math.min(scored, model.positive_predictions_last_24h);
  const positiveShare = scored > 0 ? (positive / scored) * 100 : 0;

  return (
    <div className="health-content">
      <div className="health-grid">
        <article className="health-panel health-panel--readings">
          <span className="health-panel__eyebrow">Últimas 24 horas</span>
          <div className="health-panel__metric">
            <strong>{mqtt.readings_last_24h.toLocaleString("pt-BR")}</strong>
            <span>leituras recebidas</span>
          </div>
          <p className="health-panel__foot">
            {mqtt.last_reading_at
              ? `Última leitura: ${formatDate(mqtt.last_reading_at)}`
              : "Nenhuma leitura registrada ainda"}
          </p>
        </article>
        <article className="health-panel health-panel--model">
          <div className="health-panel__heading">
            <h3>Mudanças no consumo</h3>
            <span>Últimas 24 horas</span>
          </div>
          <div className="health-model-chart">
            <div
              className="health-donut"
              style={{
                background:
                  scored > 0
                    ? `conic-gradient(var(--warm) 0 ${positiveShare}%, var(--accent) ${positiveShare}% 100%)`
                    : "var(--line)",
              }}
            >
              <div className="health-donut__center">
                <strong>{scored.toLocaleString("pt-BR")}</strong>
                <span>análises</span>
              </div>
            </div>
            <div className="health-model-legend">
              <p>
                <i
                  className="health-model-legend__dot health-model-legend__dot--positive"
                  aria-hidden="true"
                />
                <span>Com sinal de mudança</span>
                <strong>{positive.toLocaleString("pt-BR")}</strong>
              </p>
              <p>
                <i className="health-model-legend__dot" aria-hidden="true" />
                <span>Sem sinal identificado</span>
                <strong>{(scored - positive).toLocaleString("pt-BR")}</strong>
              </p>
            </div>
          </div>
          <p className="health-panel__foot">
            {model.status !== "healthy"
              ? "A análise precisa de atenção. Os avisos de consumo e conexão continuam ativos; estes são os últimos resultados disponíveis."
              : scored === 0
                ? "As primeiras análises aparecerão quando houver leituras suficientes."
                : "Um sinal merece verificação e não confirma, sozinho, que há um problema."}
          </p>
        </article>
        <article className="health-panel health-panel--rules">
          <div className="health-panel__heading">
            <h3>Avisos automáticos</h3>
            <span>Últimas 24 h</span>
          </div>
          <div className="health-panel__metric">
            <strong>{health.rules_fallback.alerts_last_24h.toLocaleString("pt-BR")}</strong>
            <span>avisos criados</span>
          </div>
          <p className="health-panel__foot">
            Os avisos continuam ativos mesmo quando a análise de consumo está indisponível.
          </p>
        </article>
      </div>
      <div className="health-charts">
        <article className="health-chart-card">
          <div className="health-panel__heading">
            <h3>Consumo por horário</h3>
            <span>Últimas 24 horas · litros</span>
          </div>
          {hourlyLoading ? (
            <p className="health-chart-message" role="status">
              Carregando o histórico por horário…
            </p>
          ) : hourlyError ? (
            <p className="health-chart-message" role="alert">
              Não foi possível carregar o histórico por horário.
            </p>
          ) : hourlyData.every((point) => point.volume_liters === null) ? (
            <p className="health-chart-message">
              Ainda não há leituras suficientes para mostrar o consumo por horário.
            </p>
          ) : (
            <div
              className="health-chart-wrap"
              role="img"
              aria-label="Consumo em litros por hora nas últimas 24 horas. Horários sem barra não têm leituras suficientes."
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hourlyData} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid
                    vertical={false}
                    stroke="var(--chart-grid)"
                    strokeDasharray="3 6"
                  />
                  <XAxis
                    dataKey="hour"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--muted)", fontSize: 11 }}
                    interval={3}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--muted)", fontSize: 11 }}
                  />
                  <Tooltip
                    formatter={(value) => [
                      value === undefined || value === null
                        ? "Sem dados suficientes"
                        : `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} L`,
                      "Consumo",
                    ]}
                    labelFormatter={(hour) => `${hour}h`}
                    contentStyle={{
                      borderRadius: 12,
                      borderColor: "var(--line)",
                      background: "var(--surface)",
                      color: "var(--ink)",
                    }}
                  />
                  <Bar dataKey="volume_liters" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="health-chart-foot">
            Horários sem leitura suficiente ficam sem barra; não significam consumo zero.
          </p>
        </article>
        <article className="health-chart-card">
          <div className="health-panel__heading">
            <h3>Avisos por motivo</h3>
            <span>Últimas 24 horas</span>
          </div>
          {alertData.length === 0 ? (
            <p className="health-chart-message">Nenhum aviso foi criado nas últimas 24 horas.</p>
          ) : (
            <div
              className="health-chart-wrap health-chart-wrap--alerts"
              role="img"
              aria-label={`Avisos criados nas últimas 24 horas: ${alertData.map((item) => `${item.reason}, ${item.count}`).join("; ")}`}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={alertData}
                  layout="vertical"
                  margin={{ top: 4, right: 12, left: 8, bottom: 0 }}
                >
                  <CartesianGrid
                    horizontal={false}
                    stroke="var(--chart-grid)"
                    strokeDasharray="3 6"
                  />
                  <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} />
                  <YAxis
                    type="category"
                    dataKey="reason"
                    width={155}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--muted)", fontSize: 11 }}
                  />
                  <Tooltip
                    formatter={(value) => [
                      `${Number(value)} ${Number(value) === 1 ? "aviso" : "avisos"}`,
                      "Total",
                    ]}
                    contentStyle={{
                      borderRadius: 12,
                      borderColor: "var(--line)",
                      background: "var(--surface)",
                      color: "var(--ink)",
                    }}
                  />
                  <Bar dataKey="count" fill="var(--warm)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="health-chart-foot">
            {alertDataMayBePartial
              ? "Contagem dos avisos mais recentes carregados."
              : "Inclui avisos experimentais e avisos das regras de acompanhamento."}
          </p>
        </article>
      </div>
      <details className="health-details">
        <summary>Detalhes técnicos</summary>
        <ul className="health-services" aria-label="Estado dos serviços">
          <ServiceStatus label="Aplicação" status="Pronta" tone="ok" />
          <ServiceStatus
            label="Medidores"
            status={mqttStatusLabel(mqtt.mqtt_status)}
            tone={mqtt.mqtt_status === "connected" ? "ok" : "offline"}
          />
          <ServiceStatus
            label="Análise de consumo"
            status={modelStatusLabel(model.status)}
            tone={
              model.status === "healthy"
                ? "ok"
                : model.status === "degraded"
                  ? "warning"
                  : "offline"
            }
          />
          <ServiceStatus label="Avisos automáticos" status="Ativos" tone="ok" />
        </ul>
        <article className="health-panel health-panel--mqtt">
          <div className="health-panel__heading">
            <h3>Mensagens dos medidores</h3>
            <span>Desde que a conexão iniciou</span>
          </div>
          <div className="health-bars">
            <HealthBar
              label="Recebidas"
              value={mqtt.mqtt_messages_received}
              maximum={mqttMaximum}
            />
            <HealthBar
              label="Encaminhadas"
              value={mqtt.mqtt_messages_forwarded}
              maximum={mqttMaximum}
            />
            <HealthBar
              label="Rejeitadas"
              value={mqtt.mqtt_messages_rejected}
              maximum={mqttMaximum}
            />
          </div>
          <p className="health-panel__foot">
            {mqttMaximum === 0
              ? "Nenhuma mensagem MQTT recebida nesta sessão."
              : "Contadores globais do ingestor, separados das leituras da propriedade."}
          </p>
        </article>

        <p>
          Mensagens reenviadas: {mqtt.mqtt_retries.toLocaleString("pt-BR")} · Leituras avaliadas:{" "}
          {model.processed_records.toLocaleString("pt-BR")} · Falhas recentes:{" "}
          {model.failed_batches.toLocaleString("pt-BR")}.
        </p>
        {model.model_version && (
          <p>
            Versão da análise {model.model_name ?? "experimental"} ·{" "}
            <code>{model.model_version.slice(0, 12)}</code>
          </p>
        )}
      </details>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  unit,
  featured = false,
}: {
  label: string;
  value: string;
  note: string;
  unit?: string;
  featured?: boolean;
}) {
  return (
    <article className={`metric-card${featured ? " metric-card--featured" : ""}`}>
      <span className="metric-label">{label}</span>
      <p className="metric-value">
        {value}
        {unit && <span>{unit}</span>}
      </p>
      <span className="metric-note">{note}</span>
      {featured && (
        <span className="metric-spark" aria-hidden="true">
          ↗
        </span>
      )}
    </article>
  );
}

function LoadingCard() {
  return (
    <div className="surface loading-card" role="status">
      <span className="loading-wave" aria-hidden="true">
        ≈
      </span>
      Carregando seus dados…
    </div>
  );
}

function toSettingsDraft(property: Property): PropertySettingsDraft {
  return {
    name: property.name,
    address: property.address ?? "",
    timezone: property.timezone,
    flowThreshold: String(property.continuous_flow_threshold_liters_minute),
    flowDuration: String(property.continuous_flow_duration_minutes),
    lateWindow: String(property.late_reading_window_days),
  };
}

function PropertySettingsForm({
  property,
  onSave,
}: {
  property: Property;
  onSave: (patch: PropertyPatch) => Promise<Property>;
}) {
  const [draft, setDraft] = useState(() => toSettingsDraft(property));
  const [timezoneOptions, setTimezoneOptions] = useState([property.timezone]);
  const [timezoneOptionsLoaded, setTimezoneOptionsLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string } | null>(
    null,
  );
  const update = (field: keyof PropertySettingsDraft, value: string) =>
    setDraft((current) => ({ ...current, [field]: value }));

  useEffect(() => {
    setTimezoneOptions(getTimezoneOptions(property.timezone));
    setTimezoneOptionsLoaded(true);
  }, [property.timezone]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await onSave({
        name: draft.name.trim(),
        address: draft.address.trim() || null,
        timezone: draft.timezone.trim(),
        volume_unit: property.volume_unit,
        continuous_flow_threshold_liters_minute: Number(draft.flowThreshold),
        continuous_flow_duration_minutes: Number(draft.flowDuration),
        late_reading_window_days: Number(draft.lateWindow),
      });
      setDraft(toSettingsDraft(updated));
      setFeedback({ kind: "success", message: "Configurações da propriedade salvas." });
    } catch (caught) {
      setFeedback({
        kind: "error",
        message:
          caught instanceof Error ? caught.message : "Não foi possível salvar as configurações.",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface settings-card" aria-labelledby="settings-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Propriedade</span>
          <h2 id="settings-title">Sobre a propriedade</h2>
        </div>
      </div>
      <p className="section-subtitle">Personalize como você acompanha {property.name}.</p>
      {feedback && (
        <p
          role={feedback.kind === "error" ? "alert" : "status"}
          className={`form-notice form-notice--${feedback.kind}`}
        >
          {feedback.message}
        </p>
      )}
      <form className="settings-form" onSubmit={(event) => void submit(event)}>
        <div className="settings-grid">
          <label className="field">
            Nome da propriedade
            <input
              value={draft.name}
              onChange={(event) => update("name", event.target.value)}
              maxLength={120}
              required
            />
          </label>
          <label className="field">
            <span className="field-label-row">
              Endereço <span className="settings-optional">(opcional)</span>
            </span>
            <input
              value={draft.address}
              onChange={(event) => update("address", event.target.value)}
              maxLength={300}
              placeholder="Rua, número, cidade"
            />
          </label>
          <label className="field">
            Fuso horário
            <select
              value={draft.timezone}
              onChange={(event) => update("timezone", event.target.value)}
              required
            >
              {!timezoneOptions.includes(draft.timezone) && (
                <option value={draft.timezone}>{draft.timezone} (atual)</option>
              )}
              {timezoneOptions.map((timezone) => (
                <option key={timezone} value={timezone}>
                  {timezone}
                  {timezoneOptionsLoaded && " (" + timezoneOffsetLabel(timezone) + ")"}
                </option>
              ))}
            </select>
            <span className="field-hint">
              Define o horário local dos gráficos e do acompanhamento noturno.
            </span>
          </label>
          <label className="field">
            Unidade de volume
            <input value="Litros (L)" readOnly aria-readonly="true" />
            <span className="field-hint">O consumo é apresentado em litros.</span>
          </label>
          <label className="field">
            Fluxo mínimo para acompanhar (L/min)
            <input
              className="settings-number"
              type="number"
              min="0.001"
              max="999999999.999"
              step="0.001"
              value={draft.flowThreshold}
              onChange={(event) => update("flowThreshold", event.target.value)}
              required
            />
            <span className="field-hint">
              Uma vazão acima deste valor é avaliada pela duração configurada ao lado.
            </span>
          </label>
          <label className="field">
            Avisar após quantos minutos?
            <input
              className="settings-number"
              type="number"
              min="1"
              max="10080"
              step="1"
              value={draft.flowDuration}
              onChange={(event) => update("flowDuration", event.target.value)}
              required
            />
          </label>
          <label className="field">
            Aceitar leituras anteriores (dias)
            <input
              className="settings-number"
              type="number"
              min="1"
              max="30"
              step="1"
              value={draft.lateWindow}
              onChange={(event) => update("lateWindow", event.target.value)}
              required
            />
            <span className="field-hint">
              Por quanto tempo uma leitura enviada com atraso ainda pode ser considerada.
            </span>
          </label>
        </div>
        <div className="settings-actions">
          <button
            type="button"
            className="button button--quiet"
            disabled={saving}
            onClick={() => {
              setDraft(toSettingsDraft(property));
              setFeedback(null);
            }}
          >
            Descartar alterações
          </button>
          <button type="submit" className="button button--primary" disabled={saving}>
            {saving ? "Salvando…" : "Salvar configurações"}
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </form>
    </section>
  );
}

function AlertEvidence({ alert }: { alert: Alert }) {
  const evidence = alert.evidence;
  const rows: Array<[string, string]> = [];
  const addNumber = (key: string, label: string, unit: string) => {
    const value = evidence[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      rows.push([label, `${value.toLocaleString("pt-BR", { maximumFractionDigits: 3 })} ${unit}`]);
    }
  };
  const addText = (key: string, label: string) => {
    const value = evidence[key];
    if (typeof value === "string" && value.trim()) rows.push([label, value]);
  };
  const formatDate = (value: string) =>
    new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));

  rows.push([
    "Período observado",
    `${formatDate(alert.window_start)} – ${formatDate(alert.window_end)}`,
  ]);
  if (alert.detector_type === "ml_anomaly") {
    if (typeof evidence.anomaly_probability === "number") {
      rows.push([
        "Probabilidade na leitura mais recente",
        `${(evidence.anomaly_probability * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`,
      ]);
    }
    if (typeof evidence.maximum_anomaly_probability === "number") {
      rows.push([
        "Maior probabilidade registrada",
        `${(evidence.maximum_anomaly_probability * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`,
      ]);
    }
    if (typeof evidence.classification_threshold === "number") {
      rows.push([
        "Limite usado pelo modelo",
        `${(evidence.classification_threshold * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`,
      ]);
    }
    addNumber("occurrence_count", "Previsões positivas agrupadas", "leituras");
    addText("model_version", "Versão do modelo");
    const latestSignals = evidence.latest_signals;
    if (typeof latestSignals === "object" && latestSignals !== null) {
      const signals = latestSignals as Record<string, unknown>;
      for (const [key, label, unit] of [
        ["flow_rate_liters_minute", "Vazão observada", "L/min"],
        ["volume_delta_liters", "Variação do volume", "L"],
        ["elapsed_minutes", "Intervalo entre leituras", "min"],
      ]) {
        const value = signals[key];
        if (typeof value === "number" && Number.isFinite(value)) {
          rows.push([
            label,
            `${value.toLocaleString("pt-BR", { maximumFractionDigits: 3 })} ${unit}`,
          ]);
        }
      }
      const derivation = signals.input_derivation;
      if (typeof derivation === "string") {
        rows.push([
          "Origem da vazão",
          derivation === "flow_rate_from_cumulative_volume"
            ? "Calculada pela variação do volume acumulado"
            : derivation === "cumulative_volume"
              ? "Informada pelo medidor"
              : "Estimativa a partir da vazão informada",
        ]);
      }
    }
  } else if (alert.detector_type === "continuous_flow") {
    addNumber("minimum_flow_rate_liters_minute", "Limite de fluxo", "L/min");
    addNumber("observed_flow_rate_liters_minute", "Fluxo observado", "L/min");
    addNumber("required_duration_minutes", "Duração necessária", "min");
    addNumber("observed_duration_minutes", "Duração observada", "min");
    addNumber("measured_interval_count", "Intervalos medidos", "amostras");
    addNumber("max_sample_gap_seconds", "Maior intervalo entre amostras", "s");
  } else if (alert.detector_type === "night_consumption") {
    addNumber("baseline_daytime_median_liters_minute", "Mediana diurna", "L/min");
    addNumber("minimum_increase_liters_minute", "Aumento mínimo", "L/min");
    addNumber("threshold_liters_minute", "Limite noturno calculado", "L/min");
    addNumber("observed_flow_rate_liters_minute", "Fluxo observado", "L/min");
    addNumber("required_duration_minutes", "Duração necessária", "min");
    addNumber("observed_duration_minutes", "Duração observada", "min");
    addText("night_window", "Janela noturna");
    addText("timezone", "Fuso da propriedade");
  } else if (alert.detector_type === "device_offline") {
    const lastSeen = evidence.last_seen_at;
    if (typeof lastSeen === "string" && !Number.isNaN(Date.parse(lastSeen))) {
      rows.push(["Último contato registrado", formatDate(lastSeen)]);
    }
    addNumber("expected_interval_seconds", "Intervalo esperado", "s");
    addNumber("offline_threshold_seconds", "Limite para considerar offline", "s");
    addNumber("seconds_since_last_seen", "Tempo sem comunicação", "s");
  }

  return (
    <details className="alert-evidence">
      <summary>Entender este aviso</summary>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
