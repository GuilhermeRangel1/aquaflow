"use client";

import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Brand, ThemeToggle } from "../../components/brand";
import { resolveActivePropertyId, resolveDashboardRoute } from "./dashboard-state.mjs";

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
  id: string;
  event_id: string;
  recorded_at: string;
  received_at: string;
  cumulative_volume_liters: number | string | null;
  flow_rate_liters_minute: number | string | null;
  quality: string;
  battery_percent: number | null;
  signal_dbm: number | null;
  firmware_version: string | null;
};
type DeviceReadings = { items: DeviceReading[]; cursor: string | null; has_more: boolean };
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
type DashboardRefresh = { checked_at: string };
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

function PropertyPicker({
  properties,
  selectedId,
  onChange,
}: {
  properties: Property[];
  selectedId: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selected = properties.find((property) => property.id === selectedId);
  const listId = useId();

  useEffect(() => {
    if (!open) return;

    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };

    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="shell-property-picker" ref={pickerRef}>
      <span className="shell-property-picker__label">Sua casa</span>
      <button
        ref={triggerRef}
        type="button"
        className="shell-property-picker__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="shell-property-picker__current">
          {selected?.name ?? "Selecione uma casa"}
        </span>
        <svg aria-hidden="true" viewBox="0 0 20 20">
          <path d="m5.5 7.5 4.5 4.5 4.5-4.5" />
        </svg>
      </button>
      {open && (
        <div
          className="shell-property-picker__menu"
          id={listId}
          role="menu"
          aria-label="Propriedades"
        >
          {properties.map((property) => {
            const isSelected = property.id === selectedId;
            return (
              <button
                key={property.id}
                type="button"
                role="menuitemradio"
                aria-checked={isSelected}
                className={`shell-property-picker__option${isSelected ? " shell-property-picker__option--selected" : ""}`}
                onClick={() => {
                  onChange(property.id);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
              >
                <span className="shell-property-picker__option-copy">
                  <span>{property.name}</span>
                  {isSelected && <small>Selecionada</small>}
                </span>
                <span className="shell-property-picker__check" aria-hidden="true">
                  {isSelected ? "✓" : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [view, setView] = useState<"overview" | "meters" | "alerts" | "settings">("overview");
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceHealth, setDeviceHealth] = useState<Record<string, DeviceHealth>>({});
  const [deviceReadings, setDeviceReadings] = useState<DeviceReading[]>([]);
  const [deviceReadingsLoading, setDeviceReadingsLoading] = useState(false);
  const [deviceReadingsError, setDeviceReadingsError] = useState("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertVisibleLimit, setAlertVisibleLimit] = useState(5);
  const [alertsCursor, setAlertsCursor] = useState<string | null>(null);
  const [alertsHasMore, setAlertsHasMore] = useState(false);
  const [loadingMoreAlerts, setLoadingMoreAlerts] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [periodDays, setPeriodDays] = useState<7 | 30 | 90>(7);
  const [consumption, setConsumption] = useState<Consumption | null>(null);
  const [loadedPeriod, setLoadedPeriod] = useState(periodDays);
  const [consumptionFailed, setConsumptionFailed] = useState(false);
  const consumptionPending = !consumptionFailed && (!consumption || loadedPeriod !== periodDays);
  const [hourlyConsumption, setHourlyConsumption] = useState<Consumption | null>(null);
  const [hourlyWindowEnd, setHourlyWindowEnd] = useState<number | null>(null);
  const [hourlyConsumptionError, setHourlyConsumptionError] = useState("");
  const [dashboardRefresh, setDashboardRefresh] = useState<DashboardRefresh | null>(null);
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
  const [alertFilter, setAlertFilter] = useState<"open" | "acknowledged" | "resolved" | "all">(
    "open",
  );
  const [showDeviceForm, setShowDeviceForm] = useState(false);
  const [showPropertyForm, setShowPropertyForm] = useState(false);
  const selected = properties.find((item) => item.id === selectedId);
  const selectedAlert = alerts.find((alert) => alert.id === selectedAlertId);
  const selectedAlertDevice = selectedAlert
    ? (devices.find((device) => device.id === selectedAlert.device_id)?.name ?? "Medidor")
    : "Medidor";
  const selectedDevices = useMemo(
    () => devices.filter((item) => item.property_id === selectedId),
    [devices, selectedId],
  );
  const latestMeterContact = selectedDevices.reduce<string | null>((latest, device) => {
    const seen = device.last_seen_at;
    if (!seen) return latest;
    return latest === null || Date.parse(seen) > Date.parse(latest) ? seen : latest;
  }, null);
  const selectedDevice = selectedDevices.find((item) => item.id === selectedDeviceId);
  const openAlertCount = alerts.filter((alert) => alert.status === "open").length;
  const acknowledgedAlertCount = alerts.filter((alert) => alert.status === "acknowledged").length;
  const activeAlertCount = openAlertCount + acknowledgedAlertCount;
  const visibleAlerts = alerts.filter(
    (alert) => alertFilter === "all" || alert.status === alertFilter,
  );
  const firstActiveAlert = alerts.find(
    (alert) => alert.status === "open" || alert.status === "acknowledged",
  );
  const changePercent = consumption?.summary.change_percent;
  const comparison =
    changePercent == null
      ? "Sem dados para comparar com o período anterior"
      : changePercent === 0
        ? "Mesmo consumo que no período anterior"
        : `${Math.abs(changePercent).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% a ${changePercent > 0 ? "mais" : "menos"} que no período anterior`;

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
      const availableIds = propertyResult.items.map((property) => property.id);
      setSelectedId((currentId) => resolveActivePropertyId(propertyId, currentId, availableIds));
      if (availableIds.length === 0) {
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
  }, []);

  useEffect(() => {
    const syncView = () => {
      const params = new URLSearchParams(window.location.search);
      const route = resolveDashboardRoute(params.get("view"), params.get("device"));
      setView(route.view);
      setSelectedDeviceId(route.selectedDeviceId);
      setSelectedAlertId(params.get("alert"));
    };
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
        if (!cancelled) {
          setConsumption(result);
          setLoadedPeriod(periodDays);
          setConsumptionFailed(false);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setConsumptionFailed(true);
          setError(caught instanceof Error ? caught.message : "Falha ao carregar consumo.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, loading, periodDays]);
  useEffect(() => {
    if (!selectedId || loading || view !== "overview") return;
    let cancelled = false;
    const refreshDashboard = () =>
      api<DashboardRefresh>(`properties/${selectedId}/dashboard-health`)
        .then((result) => {
          if (!cancelled) setDashboardRefresh(result);
        })
        .catch(() => undefined);
    void refreshDashboard();
    const timer = window.setInterval(refreshDashboard, 30_000);
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
    if (view !== "meters" || !selectedDeviceId) return;
    let cancelled = false;
    setDeviceReadings([]);
    setDeviceReadingsError("");
    setDeviceReadingsLoading(true);
    api<DeviceReadings>(`devices/${selectedDeviceId}/readings?limit=100`)
      .then((result) => {
        if (!cancelled) setDeviceReadings(result.items);
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setDeviceReadingsError(
            caught instanceof Error ? caught.message : "Não foi possível carregar as leituras.",
          );
      })
      .finally(() => {
        if (!cancelled) setDeviceReadingsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view, selectedDeviceId]);
  useEffect(() => {
    if (!selectedId || loading) return;
    let cancelled = false;
    setAlerts([]);
    setAlertsLoading(true);
    setAlertVisibleLimit(5);
    setAlertsCursor(null);
    setAlertsHasMore(false);
    api<{ items: Alert[]; cursor: string | null; has_more: boolean }>(
      `properties/${selectedId}/alerts?limit=200`,
    )
      .then((alertResult) => {
        if (!cancelled) {
          setAlerts(alertResult.items);
          setAlertsLoading(false);
          setAlertsCursor(alertResult.cursor);
          setAlertsHasMore(alertResult.has_more);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setAlertsLoading(false);
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
      setShowPropertyForm(false);
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
      if (selectedDeviceId === device.id) {
        setSelectedDeviceId(null);
        window.history.replaceState({}, "", "/dashboard?view=meters");
      }
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
    if (alertVisibleLimit < visibleAlerts.length) {
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

  async function archiveSelectedProperty() {
    if (!selected) return;
    await api(`properties/${selected.id}`, { method: "DELETE" });
    await load();
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
    setSelectedDeviceId(null);
    setSelectedAlertId(null);
    setEditingDeviceId("");
    setRetiringDeviceId("");
    window.scrollTo({ top: 0, behavior: "instant" });
    window.history.pushState(
      {},
      "",
      destination === "overview" ? "/dashboard" : `/dashboard?view=${destination}`,
    );
  }

  function openMeter(device: Device) {
    setView("meters");
    setSelectedDeviceId(device.id);
    setEditingDeviceId("");
    setRetiringDeviceId("");
    window.scrollTo({ top: 0, behavior: "instant" });
    window.history.pushState(
      {},
      "",
      `/dashboard?view=meters&device=${encodeURIComponent(device.id)}`,
    );
  }

  function closeMeter() {
    setSelectedDeviceId(null);
    setEditingDeviceId("");
    setRetiringDeviceId("");
    window.scrollTo({ top: 0, behavior: "instant" });
    window.history.pushState({}, "", "/dashboard?view=meters");
  }

  function openAlert(alert: Alert) {
    setView("alerts");
    setSelectedAlertId(alert.id);
    window.scrollTo({ top: 0, behavior: "instant" });
    window.history.pushState(
      {},
      "",
      `/dashboard?view=alerts&alert=${encodeURIComponent(alert.id)}`,
    );
  }

  function closeAlert() {
    setSelectedAlertId(null);
    window.scrollTo({ top: 0, behavior: "instant" });
    window.history.pushState({}, "", "/dashboard?view=alerts");
  }

  function changePeriod(days: 7 | 30 | 90) {
    setConsumptionFailed(false);
    setPeriodDays(days);
  }

  function selectProperty(id: string) {
    if (id === selectedId) return;

    setConsumptionFailed(false);
    setConsumption(null);
    setDashboardRefresh(null);
    setHourlyConsumption(null);
    setHourlyWindowEnd(null);
    setHourlyConsumptionError("");
    setAlerts([]);
    setAlertNotice("");
    setSelectedAlertId(null);
    if (view === "alerts" || selectedDeviceId)
      window.history.replaceState({}, "", `/dashboard?view=${view}`);
    setSelectedDeviceId(null);
    setSelectedId(id);
  }

  const chartData = (consumption?.items ?? []).map((item) => ({
    ...item,
    day: new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit",
      month: "short",
      timeZone: selected?.timezone,
    }).format(new Date(item.bucket_start)),
  }));
  const meterLatestReading = selectedDeviceId
    ? (deviceReadings[0] ?? deviceHealth[selectedDeviceId]?.latest_reading)
    : undefined;
  const meterCurrentFlow =
    meterLatestReading?.quality === "valid" ? meterLatestReading.flow_rate_liters_minute : null;
  const meterFlowChartData = useMemo(
    () =>
      [...deviceReadings]
        .reverse()
        .filter(
          (reading) => reading.quality === "valid" && reading.flow_rate_liters_minute !== null,
        )
        .map((reading) => ({
          time: new Intl.DateTimeFormat("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: selected?.timezone,
          }).format(new Date(reading.recorded_at)),
          flow: reading.flow_rate_liters_minute,
        })),
    [deviceReadings, selected?.timezone],
  );
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
  const propertyCreationForm = (
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
  );

  const propertyPicker =
    properties.length > 0 ? (
      <PropertyPicker properties={properties} selectedId={selectedId} onChange={selectProperty} />
    ) : null;

  return (
    <main className="dashboard-page">
      <div className="dashboard-shell">
        <aside className="app-sidebar" aria-label="Menu da aplicação">
          <div className="sidebar-brand">
            <Brand lightArtwork="/design/aquaflow-logo-dashboard.png" />
          </div>
          {propertyPicker}
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
                <span className="nav-link-label">{label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-footer">
            <button onClick={logout} className="button button--quiet">
              Sair da conta
            </button>
          </div>
        </aside>
        <div className="dashboard-main">
          <header className="app-header">
            <div className="app-header-inner">
              <div className="app-header-context">
                <div className="mobile-header-brand">
                  <Brand compact />
                </div>
                <span className="app-context-property">
                  {selected?.name ?? "Acompanhamento da sua água"}
                </span>
              </div>
              <div className="header-actions">
                {view === "overview" && dashboardRefresh && (
                  <span className="health-updated">
                    {formatRelativeUpdate(dashboardRefresh.checked_at)}
                  </span>
                )}
                <ThemeToggle />
                <button onClick={logout} className="button button--quiet mobile-logout">
                  Sair
                </button>
              </div>
            </div>
          </header>
          <div className="dashboard-content" id="overview">
            <section className="dashboard-heading">
              <div>
                <h1 id={view === "meters" && selectedDeviceId ? "meter-detail-title" : undefined}>
                  {view === "meters"
                    ? (selectedDevice?.name ?? "Seus medidores")
                    : view === "alerts"
                      ? selectedAlert
                        ? alertTitle(selectedAlert.detector_type)
                        : "O que merece atenção"
                      : view === "settings"
                        ? "Sua casa, do seu jeito"
                        : "Sua água, de perto"}
                </h1>
                <p>
                  {view === "meters"
                    ? selectedDevice
                      ? `${selected?.name ?? "Sua casa"} · ${selectedDevice.serial_number}`
                      : "Veja onde a água está sendo acompanhada."
                    : view === "alerts"
                      ? selectedAlert
                        ? `${selectedAlertDevice} · ${formatDate(selectedAlert.detected_at)}`
                        : "Entenda os avisos e acompanhe cada situação."
                      : view === "settings"
                        ? "Ajuste os dados e o acompanhamento da sua casa."
                        : "Acompanhe o consumo e o que merece atenção."}
                </p>
              </div>
              <div className="mobile-property-picker">{propertyPicker}</div>
              {view === "meters" && selected && !selectedDeviceId && (
                <button
                  className="button button--primary add-meter-button add-meter-button--desktop"
                  onClick={() => {
                    setShowDeviceForm(true);
                    requestAnimationFrame(() =>
                      document
                        .getElementById("new-meter-form")
                        ?.scrollIntoView({ block: "center" }),
                    );
                  }}
                >
                  Adicionar medidor
                </button>
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
                    Organize medidores e leituras por local. Depois, você pode conectar um
                    dispositivo e acompanhar o consumo aqui.
                  </p>
                  {propertyCreationForm}
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
                    onArchive={
                      selected.name === "Casa da Administração"
                        ? undefined
                        : archiveSelectedProperty
                    }
                  />
                )}
                {view === "settings" && (
                  <section
                    className="surface settings-card property-create-card"
                    aria-labelledby="new-property-title"
                  >
                    <div className="section-heading property-create-heading">
                      <div>
                        <h2 id="new-property-title">Propriedades</h2>
                        <p className="section-subtitle">
                          Cadastre outro local para acompanhar seus medidores.
                        </p>
                      </div>
                      {!showPropertyForm && (
                        <button
                          type="button"
                          className="button button--primary"
                          onClick={() => setShowPropertyForm(true)}
                        >
                          Adicionar propriedade <span aria-hidden="true">→</span>
                        </button>
                      )}
                    </div>
                    {showPropertyForm && (
                      <div className="property-create-form">
                        {propertyCreationForm}
                        <button
                          type="button"
                          className="button button--quiet"
                          onClick={() => {
                            setShowPropertyForm(false);
                            setNewProperty("");
                          }}
                        >
                          Cancelar
                        </button>
                      </div>
                    )}
                  </section>
                )}
                {view === "overview" && (
                  <section className="metrics-grid" aria-label="Resumo de consumo">
                    <Metric
                      featured
                      label={`Seu consumo · Últimos ${consumption ? loadedPeriod : periodDays} dias`}
                      value={
                        consumption?.summary.valid_interval_count
                          ? consumption.summary.total_volume_liters.toLocaleString("pt-BR", {
                              maximumFractionDigits: 1,
                            })
                          : "—"
                      }
                      unit={consumption?.summary.valid_interval_count ? "litros" : undefined}
                      note={
                        consumption?.summary.valid_interval_count
                          ? comparison
                          : consumption
                            ? "Ainda faltam leituras para calcular o consumo"
                            : "Buscando o consumo…"
                      }
                    />
                    <Metric
                      label="Medidores"
                      value={`${selectedDevices.length}`}
                      note={
                        latestMeterContact
                          ? `Última comunicação · ${formatDate(latestMeterContact)}`
                          : selectedDevices.length
                            ? "Aguardando a primeira leitura"
                            : "Nenhum medidor cadastrado"
                      }
                      actionLabel="Ver medidores"
                      onAction={() => navigateView("meters")}
                    />
                    <Metric
                      label="Avisos para acompanhar"
                      value={`${activeAlertCount}`}
                      unit="avisos"
                      note={`${openAlertCount} ${openAlertCount === 1 ? "aberto" : "abertos"} · ${acknowledgedAlertCount} ${acknowledgedAlertCount === 1 ? "reconhecido" : "reconhecidos"}`}
                      actionLabel={firstActiveAlert ? "Ver alertas" : undefined}
                      onAction={firstActiveAlert ? () => navigateView("alerts") : undefined}
                    />
                  </section>
                )}
                {view === "meters" &&
                  selectedDeviceId &&
                  (selectedDevice ? (
                    <section className="meter-detail-page" aria-labelledby="meter-detail-title">
                      <button
                        type="button"
                        className="button button--quiet meter-detail-back"
                        onClick={closeMeter}
                      >
                        <span aria-hidden="true">←</span> Seus medidores
                      </button>
                      <section className="meter-current-card" aria-label="Última leitura">
                        <span className="eyebrow">
                          {meterLatestReading
                            ? `Última leitura · ${formatDate(meterLatestReading.recorded_at)}`
                            : "Aguardando a primeira leitura"}
                        </span>
                        <strong className="meter-current-value">
                          {meterCurrentFlow == null
                            ? "—"
                            : `${Number(meterCurrentFlow).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} L/min`}
                        </strong>
                        <span>Vazão registrada na atualização mais recente</span>
                      </section>
                      <section className="surface chart-card meter-history-card">
                        <div>
                          <h2>Vazão nas leituras recentes</h2>
                          <p className="section-subtitle">Litros por minuto</p>
                        </div>
                        {deviceReadingsError ? (
                          <p role="alert" className="notice notice--error">
                            {deviceReadingsError}
                          </p>
                        ) : deviceReadingsLoading ? (
                          <p role="status" className="meter-history-empty">
                            Carregando as leituras do medidor…
                          </p>
                        ) : meterFlowChartData.length ? (
                          <div
                            className="chart-wrap meter-detail-chart"
                            role="img"
                            aria-label="Vazão nas últimas leituras recebidas do medidor"
                          >
                            <p className="sr-only">
                              {[...deviceReadings]
                                .filter(
                                  (reading) =>
                                    reading.quality === "valid" &&
                                    reading.flow_rate_liters_minute !== null,
                                )
                                .slice(0, 20)
                                .map(
                                  (reading) =>
                                    `${formatDate(reading.recorded_at)}: ${Number(reading.flow_rate_liters_minute).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} litros por minuto`,
                                )
                                .join(". ")}
                            </p>
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart
                                data={meterFlowChartData}
                                margin={{ top: 14, right: 12, left: -18, bottom: 0 }}
                              >
                                <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                                <XAxis
                                  dataKey="time"
                                  axisLine={false}
                                  tickLine={false}
                                  tick={{ fill: "var(--muted)", fontSize: 12 }}
                                  minTickGap={30}
                                />
                                <YAxis
                                  axisLine={false}
                                  tickLine={false}
                                  tick={{ fill: "var(--muted)", fontSize: 12 }}
                                />
                                <Tooltip
                                  formatter={(value) => [
                                    `${Number(value).toLocaleString("pt-BR")} L/min`,
                                    "Vazão",
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
                                  dataKey="flow"
                                  stroke="var(--accent)"
                                  strokeWidth={3}
                                  fill="none"
                                  activeDot={{
                                    r: 5,
                                    fill: "var(--accent-strong)",
                                    stroke: "var(--surface)",
                                    strokeWidth: 2,
                                  }}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        ) : (
                          <p className="meter-history-empty">
                            Ainda não há leituras suficientes para mostrar o histórico.
                          </p>
                        )}
                      </section>
                      {editingDeviceId === selectedDevice.id ? (
                        <form
                          className="surface meter-detail-edit-form"
                          onSubmit={(event) => void saveDevice(event, selectedDevice)}
                        >
                          <label className="field">
                            Nome do medidor
                            <input
                              value={editingDeviceName}
                              onChange={(event) => setEditingDeviceName(event.target.value)}
                              required
                              maxLength={120}
                            />
                          </label>
                          <label className="field">
                            Intervalo de leitura (segundos)
                            <input
                              type="number"
                              min={30}
                              max={86400}
                              step={1}
                              value={editingDeviceInterval}
                              onChange={(event) => setEditingDeviceInterval(event.target.value)}
                              required
                            />
                          </label>
                          <div className="meter-actions">
                            <button
                              className="button button--primary"
                              disabled={deviceActionId === selectedDevice.id}
                            >
                              {deviceActionId === selectedDevice.id ? "Salvando…" : "Salvar"}
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
                      ) : retiringDeviceId === selectedDevice.id ? (
                        <section
                          className="surface meter-detail-retire-confirm"
                          role="group"
                          aria-label={`Confirmar retirada de ${selectedDevice.name}`}
                        >
                          <div>
                            <strong>Retirar este medidor?</strong>
                            <p>O histórico de leituras será preservado.</p>
                          </div>
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
                              disabled={deviceActionId === selectedDevice.id}
                              onClick={() => void retireDevice(selectedDevice)}
                            >
                              {deviceActionId === selectedDevice.id
                                ? "Retirando…"
                                : "Confirmar retirada"}
                            </button>
                          </div>
                        </section>
                      ) : (
                        <div className="meter-detail-actions">
                          <button
                            type="button"
                            className="button button--quiet"
                            disabled={deviceActionId === selectedDevice.id}
                            onClick={() => beginDeviceEdit(selectedDevice)}
                          >
                            Editar medidor
                          </button>
                          <button
                            type="button"
                            className="button button--quiet meter-retire"
                            disabled={deviceActionId === selectedDevice.id}
                            onClick={() => setRetiringDeviceId(selectedDevice.id)}
                          >
                            Retirar medidor
                          </button>
                        </div>
                      )}
                    </section>
                  ) : loading ? (
                    <LoadingCard />
                  ) : (
                    <section className="surface alert-not-found">
                      <p>Este medidor não está disponível nesta propriedade.</p>
                      <button className="button button--quiet" onClick={closeMeter}>
                        Voltar aos medidores
                      </button>
                    </section>
                  ))}
                {view !== "alerts" && view !== "settings" && !selectedDeviceId && (
                  <section
                    className={`dashboard-grid${view !== "overview" ? " dashboard-grid--single" : ""}`}
                  >
                    {view === "overview" && (
                      <article className="surface chart-card">
                        <div className="section-heading">
                          <div>
                            <h2>Consumo ao longo dos dias</h2>
                          </div>
                          <fieldset className="consumption-period">
                            <legend className="sr-only">Período do gráfico</legend>
                            {([7, 30, 90] as const).map((days) => (
                              <label key={days}>
                                <input
                                  className="sr-only"
                                  type="radio"
                                  name="consumption-period"
                                  checked={periodDays === days}
                                  onChange={() => changePeriod(days)}
                                />
                                <span>{days} dias</span>
                              </label>
                            ))}
                          </fieldset>
                        </div>
                        <p className="section-subtitle">Litros por dia</p>
                        <div
                          className={`chart-wrap consumption-chart${consumptionPending ? " consumption-chart--pending" : ""}`}
                          aria-busy={consumptionPending}
                          role="img"
                          aria-label={`Gráfico do consumo diário nos últimos ${consumption ? loadedPeriod : periodDays} dias`}
                        >
                          {consumptionPending && (
                            <div className="consumption-chart-progress" aria-hidden="true" />
                          )}
                          <p className="sr-only">
                            {chartData.length
                              ? chartData
                                  .map((point) => `${point.day}: ${point.volume_liters} litros`)
                                  .join(". ")
                              : !consumption && !error
                                ? "Carregando consumo."
                                : "Ainda não há leituras suficientes para exibir o gráfico."}
                          </p>
                          {chartData.length ? (
                            <ResponsiveContainer
                              key={loadedPeriod}
                              className="consumption-chart-enter"
                              width="100%"
                              height="100%"
                            >
                              <AreaChart
                                data={chartData}
                                margin={{ top: 12, right: 8, left: -18, bottom: 0 }}
                              >
                                <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
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
                                  type="linear"
                                  isAnimationActive={false}
                                  dataKey="volume_liters"
                                  stroke="var(--accent)"
                                  strokeWidth={3}
                                  fill="none"
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
                              {consumptionPending ? (
                                <span className="sr-only">Carregando consumo…</span>
                              ) : (
                                <>
                                  <span className="empty-chart-icon" aria-hidden="true">
                                    ≈
                                  </span>
                                  <p>Ainda não há consumo para exibir</p>
                                  <span>Conecte um medidor e envie leituras para começar.</span>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      </article>
                    )}
                    {view === "meters" && (
                      <article
                        className="surface meters-card"
                        id="meters"
                        aria-label={`Medidores de ${selected?.name ?? "esta propriedade"}`}
                      >
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
                                <li key={device.id} className="meter-row">
                                  <span className="meter-icon" aria-hidden="true">
                                    <svg viewBox="0 0 24 24">
                                      <path d="M4 16a8 8 0 1 1 16 0v2H4z" />
                                      <path d="m12 12 3-3M7 18h10" />
                                    </svg>
                                  </span>
                                  <div className="meter-info">
                                    <strong>{device.name}</strong>
                                    <small>
                                      {reading
                                        ? `Última leitura ${formatDate(reading.recorded_at)}`
                                        : lastSeen
                                          ? `Último contato ${formatDate(lastSeen)}`
                                          : "Aguardando a primeira leitura"}
                                    </small>
                                  </div>
                                  <span
                                    className={`meter-status${connected ? " meter-status--online" : " meter-status--offline"}`}
                                  >
                                    {connected
                                      ? "Recebendo leituras"
                                      : neverConnected
                                        ? "Ainda sem leituras"
                                        : "Sem comunicação"}
                                  </span>
                                  <button
                                    type="button"
                                    className="alert-view-button meter-open-button"
                                    onClick={() => openMeter(device)}
                                  >
                                    Ver detalhes <span aria-hidden="true">→</span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        ) : (
                          <div className="empty-meter">
                            <strong>Ainda não há medidores nesta casa</strong>
                            <span>Adicione um medidor para começar a acompanhar as leituras.</span>
                          </div>
                        )}
                        {!showDeviceForm && (
                          <button
                            type="button"
                            className="button button--primary add-meter-button add-meter-button--mobile"
                            onClick={() => {
                              setShowDeviceForm(true);
                              requestAnimationFrame(() =>
                                document
                                  .getElementById("new-meter-form")
                                  ?.scrollIntoView({ block: "center" }),
                              );
                            }}
                          >
                            Adicionar medidor
                          </button>
                        )}
                        <form
                          hidden={!showDeviceForm}
                          id="new-meter-form"
                          onSubmit={createDevice}
                          className="device-form"
                        >
                          <h3>Adicionar medidor</h3>
                          <p className="form-help">
                            Cadastre o número de série do dispositivo que vai enviar as leituras.
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
                          <button
                            type="button"
                            className="button button--quiet"
                            disabled={provisioning}
                            onClick={() => setShowDeviceForm(false)}
                          >
                            Cancelar
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
                      <p>
                        A chave é exibida apenas nesta sessão. Copie-a e configure no dispositivo.
                      </p>
                      <code>{provisioned.key}</code>
                      <button
                        onClick={() => void copyDeviceKey()}
                        className="button button--quiet copy-key"
                      >
                        {copiedKey ? "Chave copiada" : "Copiar chave"}
                      </button>
                    </div>
                  </section>
                )}
                {view === "alerts" &&
                  (selectedAlert ? (
                    <AlertDetail
                      alert={selectedAlert}
                      notice={alertNotice}
                      busy={alertActionId === selectedAlert.id}
                      onBack={closeAlert}
                      onAcknowledge={() => void updateAlert(selectedAlert, "acknowledge")}
                      onResolve={() => void updateAlert(selectedAlert, "resolve")}
                      onFalsePositive={() => void updateAlert(selectedAlert, "false-positive")}
                    />
                  ) : alertsLoading ? (
                    <LoadingCard />
                  ) : selectedAlertId ? (
                    <section className="surface alert-not-found">
                      <p>Este aviso não está disponível nesta propriedade.</p>
                      <button className="button button--quiet" onClick={closeAlert}>
                        Voltar aos avisos
                      </button>
                    </section>
                  ) : (
                    <section
                      className="surface alerts-card"
                      id="alerts"
                      aria-label="Avisos da propriedade"
                    >
                      {alertNotice && (
                        <p role="status" className="form-notice form-notice--success">
                          {alertNotice}
                        </p>
                      )}
                      <div className="alert-filters" aria-label="Filtrar avisos">
                        {(
                          [
                            ["open", "Ativos", openAlertCount],
                            ["acknowledged", "Reconhecidos", acknowledgedAlertCount],
                            [
                              "resolved",
                              "Resolvidos",
                              alerts.filter((item) => item.status === "resolved").length,
                            ],
                            ["all", "Todos", alertsHasMore ? `${alerts.length}+` : alerts.length],
                          ] as const
                        ).map(([filter, label, count]) => (
                          <button
                            key={filter}
                            type="button"
                            className="button button--quiet"
                            aria-pressed={alertFilter === filter}
                            onClick={() => {
                              setAlertFilter(filter);
                              setAlertVisibleLimit(5);
                            }}
                          >
                            {label} <span>{count}</span>
                          </button>
                        ))}
                      </div>
                      {visibleAlerts.length || alertsHasMore ? (
                        <>
                          <ul className="alert-list" id="alerts-list">
                            {visibleAlerts.slice(0, alertVisibleLimit).map((alert) => {
                              const deviceName =
                                devices.find((device) => device.id === alert.device_id)?.name ??
                                "Medidor";
                              const statusLabel =
                                alert.status === "acknowledged"
                                  ? "Reconhecido"
                                  : alert.status === "resolved"
                                    ? "Resolvido"
                                    : alert.status === "false_positive"
                                      ? "Marcado como falso positivo"
                                      : null;
                              const description =
                                alert.detector_type === "ml_anomaly"
                                  ? "A análise encontrou uma possível mudança no consumo. Confira as leituras para entender o que aconteceu."
                                  : alert.reason;
                              return (
                                <li className="alert-row" key={alert.id}>
                                  <div className="alert-main">
                                    <div className="alert-title-line">
                                      <strong>{alertTitle(alert.detector_type)}</strong>
                                      {statusLabel && (
                                        <span
                                          className={`alert-status alert-status--${alert.status}`}
                                        >
                                          {statusLabel}
                                        </span>
                                      )}
                                    </div>
                                    <p>{description}</p>
                                    <small>
                                      {deviceName} · {formatDate(alert.detected_at)}
                                    </small>
                                  </div>
                                  <button
                                    type="button"
                                    className="button button--quiet alert-view-button"
                                    aria-label={`Ver aviso: ${alertTitle(alert.detector_type)}`}
                                    onClick={() => openAlert(alert)}
                                  >
                                    Ver aviso <span aria-hidden="true">→</span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                          {(alertVisibleLimit < visibleAlerts.length || alertsHasMore) && (
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
                        <div className="alert-empty">
                          <strong>Nenhum aviso para mostrar</strong>
                          <p>Quando houver algo para acompanhar, ele aparecerá aqui.</p>
                        </div>
                      )}
                    </section>
                  ))}
                {view === "overview" && (
                  <details className="surface overview-insights">
                    <summary className="overview-insights-toggle">Detalhes do consumo</summary>
                    <div className="overview-insights-content">
                      <OverviewInsights
                        hourlyData={hourlyChartData}
                        hourlyLoading={!hourlyConsumption && !hourlyConsumptionError}
                        hourlyError={hourlyConsumptionError}
                      />
                    </div>
                  </details>
                )}
              </>
            )}
          </div>
        </div>
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

function formatRelativeUpdate(value: string): string {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (!Number.isFinite(elapsedSeconds)) return "Atualização indisponível";
  if (elapsedSeconds < 60) return "Atualizado agora";
  if (elapsedSeconds < 3600) {
    const minutes = Math.floor(elapsedSeconds / 60);
    return `Atualizado há ${minutes} ${minutes === 1 ? "minuto" : "minutos"}`;
  }
  if (elapsedSeconds < 86400) {
    const hours = Math.floor(elapsedSeconds / 3600);
    return `Atualizado há ${hours} ${hours === 1 ? "hora" : "horas"}`;
  }
  const days = Math.floor(elapsedSeconds / 86400);
  return `Atualizado há ${days} ${days === 1 ? "dia" : "dias"}`;
}

function alertTitle(detectorType: string): string {
  if (detectorType === "continuous_flow") return "Consumo contínuo";
  if (detectorType === "night_consumption") return "Consumo à noite";
  if (detectorType === "device_offline") return "Medidor sem comunicação";
  if (detectorType === "ml_anomaly") return "Mudança no consumo";
  return "Aviso de consumo";
}

function OverviewInsights({
  hourlyData,
  hourlyLoading,
  hourlyError,
}: {
  hourlyData: Array<{ hour: string; volume_liters: number | null }>;
  hourlyLoading: boolean;
  hourlyError: string;
}) {
  const hourlyPlot = hourlyData.map((point) => ({
    ...point,
    chartValue: point.volume_liters ?? 0,
  }));

  const observedHours = hourlyData.filter((point) => point.volume_liters !== null).length;
  let recordedTotal = 0;
  const cumulative = hourlyData.map((point) => {
    recordedTotal += point.volume_liters ?? 0;
    return { hour: point.hour, total: point.volume_liters === null ? null : recordedTotal };
  });
  const periods = ["Madrugada", "Manhã", "Tarde", "Noite"].map((label, index) => {
    const observed = hourlyData.filter(
      (point) => Math.floor(Number(point.hour) / 6) === index && point.volume_liters !== null,
    );
    const value = observed.reduce((sum, point) => sum + (point.volume_liters ?? 0), 0);
    return {
      label,
      value,
      display: observed.length ? `${formatLiters(value)} · ${observed.length}/6 h` : "Sem dados",
    };
  });

  return (
    <div className="overview-insights-grid">
      <article className="overview-insight-card">
        <div className="overview-insight-heading">
          <h3>Consumo por horário</h3>
          <span>Últimas 24 horas · litros</span>
        </div>
        {hourlyLoading ? (
          <p className="overview-insight-message" role="status">
            Carregando consumo…
          </p>
        ) : hourlyError ? (
          <p className="overview-insight-message" role="alert">
            Não foi possível carregar o consumo por horário.
          </p>
        ) : hourlyPlot.length === 0 ? (
          <p className="overview-insight-message">Sem leituras nas últimas 24 horas.</p>
        ) : (
          <div
            className="overview-insight-chart"
            role="img"
            aria-label="Consumo em litros por hora nas últimas 24 horas. Marcas cinza indicam horas sem dados suficientes."
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hourlyPlot} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 6" />
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
                  cursor={false}
                  formatter={(value, _name, item) => [
                    item.payload?.volume_liters == null
                      ? "Sem dados suficientes"
                      : Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " L",
                    "Consumo",
                  ]}
                  labelFormatter={(hour) => hour + "h"}
                  contentStyle={{
                    borderRadius: 12,
                    borderColor: "var(--line)",
                    background: "var(--surface)",
                    color: "var(--ink)",
                  }}
                />
                <Bar
                  dataKey="chartValue"
                  fill="var(--accent)"
                  minPointSize={(value) => (value === 0 ? 3 : 0)}
                  activeBar={false}
                  radius={[4, 4, 0, 0]}
                >
                  {hourlyPlot.map((point, index) => (
                    <Cell
                      key={index}
                      fill={point.volume_liters === null ? "var(--muted)" : "var(--accent)"}
                      fillOpacity={point.volume_liters === null ? 0.45 : 1}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {hourlyPlot.some((point) => point.volume_liters === null) && !hourlyError && (
          <small>Marcas cinza indicam horas sem dados suficientes.</small>
        )}
      </article>
      {!hourlyLoading && !hourlyError && hourlyData.length > 0 && (
        <>
          <article className="overview-insight-card">
            <div className="overview-insight-heading">
              <h3>Consumo acumulado</h3>
              <span>Últimas 24 horas · litros</span>
            </div>
            {observedHours === 0 ? (
              <p className="overview-insight-message">
                Sem dados suficientes para somar o consumo.
              </p>
            ) : (
              <>
                <div
                  className="overview-insight-chart"
                  role="img"
                  aria-label={`Total registrado: ${formatLiters(recordedTotal)}`}
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={cumulative}
                      margin={{ top: 8, right: 4, left: -20, bottom: 0 }}
                    >
                      <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                      <XAxis
                        dataKey="hour"
                        axisLine={false}
                        tickLine={false}
                        interval={3}
                        tick={{ fill: "var(--muted)", fontSize: 11 }}
                      />
                      <YAxis
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: "var(--muted)", fontSize: 11 }}
                      />
                      <Area
                        type="stepAfter"
                        dataKey="total"
                        stroke="var(--accent-strong)"
                        fill="var(--accent-soft)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <small>{formatLiters(recordedTotal)} somados nas horas com dados.</small>
              </>
            )}
          </article>
          <InsightBreakdown title="Consumo por período do dia" rows={periods} />
          <InsightBreakdown
            title="Horas com dados de consumo"
            rows={[
              { label: "Com dados", value: observedHours, display: `${observedHours} h` },
              {
                label: "Dados insuficientes",
                value: hourlyData.length - observedHours,
                display: `${hourlyData.length - observedHours} h`,
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
function formatLiters(value: number) {
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} L`;
}

function InsightBreakdown({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ label: string; value: number; display: string }>;
}) {
  const maximum = Math.max(1, ...rows.map((row) => row.value));
  return (
    <article className="overview-insight-card">
      <div className="overview-insight-heading">
        <h3>{title}</h3>
        <span>Últimas 24 horas</span>
      </div>
      <ul className="insight-breakdown">
        {rows.map((row) => (
          <li key={row.label}>
            <div>
              <span>{row.label}</span>
              <strong>{row.display}</strong>
            </div>
            <span className="insight-breakdown-track" aria-hidden="true">
              <span style={{ width: `${(row.value / maximum) * 100}%` }} />
            </span>
          </li>
        ))}
      </ul>
    </article>
  );
}

function Metric({
  label,
  value,
  note,
  unit,
  featured = false,
  actionLabel,
  onAction,
}: {
  label: string;
  value: string;
  note: string;
  unit?: string;
  featured?: boolean;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const metricValue = (
    <p className="metric-value">
      {value}
      {unit && <span>{unit}</span>}
    </p>
  );

  return (
    <article className={`metric-card${featured ? " metric-card--featured" : ""}`}>
      <span className="metric-label">{label}</span>
      {actionLabel && onAction ? (
        <div className="metric-value-row">
          {metricValue}
          <button type="button" className="metric-action" onClick={onAction}>
            {actionLabel}
          </button>
        </div>
      ) : (
        metricValue
      )}
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
  onArchive,
}: {
  property: Property;
  onArchive?: () => Promise<void>;
  onSave: (patch: PropertyPatch) => Promise<Property>;
}) {
  const [confirmArchive, setConfirmArchive] = useState(false);
  const archiveDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (confirmArchive) archiveDialog.current?.showModal();
    else archiveDialog.current?.close();
  }, [confirmArchive]);
  const [archiving, setArchiving] = useState(false);

  async function archive() {
    if (!onArchive || archiving) return;
    setFeedback(null);
    setArchiving(true);
    try {
      await onArchive();
      setConfirmArchive(false);
    } catch (caught) {
      setFeedback({
        kind: "error",
        message:
          caught instanceof Error ? caught.message : "Não foi possível arquivar a propriedade.",
      });
    } finally {
      setArchiving(false);
    }
  }

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
      <h2 id="settings-title">Sobre a propriedade</h2>
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
            Vazão mínima para acompanhamento (L/min)
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
            Avisar após quanto tempo?
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
          {onArchive && (
            <button
              type="button"
              className="button button--quiet"
              disabled={saving || archiving}
              aria-expanded={confirmArchive}
              aria-controls={confirmArchive ? "property-archive-confirm" : undefined}
              onClick={() => setConfirmArchive(true)}
            >
              Arquivar propriedade
            </button>
          )}
          <button
            type="button"
            className="button button--quiet"
            disabled={saving || archiving}
            onClick={() => {
              setDraft(toSettingsDraft(property));
              setFeedback(null);
            }}
          >
            Descartar alterações
          </button>
          <button type="submit" className="button button--primary" disabled={saving || archiving}>
            {saving ? "Salvando…" : "Salvar configurações"}
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </form>
      {onArchive && (
        <dialog
          ref={archiveDialog}
          onCancel={(event) => {
            if (archiving) event.preventDefault();
            else setConfirmArchive(false);
          }}
          onClose={() => setConfirmArchive(false)}
          id="property-archive-confirm"
          className="property-archive-dialog"
          aria-labelledby="property-archive-title"
          aria-describedby="property-archive-question"
        >
          <h2 id="property-archive-title">Arquivar propriedade?</h2>
          <p id="property-archive-question">
            <strong>{property.name}</strong> deixará de aparecer na lista de propriedades. O
            histórico será preservado.
          </p>
          <div className="property-archive-dialog-actions">
            <button
              type="button"
              className="button button--quiet"
              autoFocus
              disabled={archiving}
              onClick={() => setConfirmArchive(false)}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="button property-archive-confirm"
              disabled={archiving || saving}
              onClick={() => void archive()}
            >
              {archiving ? "Arquivando…" : "Confirmar arquivamento"}
            </button>
          </div>
        </dialog>
      )}
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
          derivation === "cumulative_volume_5min_window"
            ? "Vazão média na janela de cinco minutos"
            : derivation === "flow_rate_from_cumulative_volume"
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

function AlertDetail({
  alert,
  notice,
  busy,
  onBack,
  onAcknowledge,
  onResolve,
  onFalsePositive,
}: {
  alert: Alert;
  notice: string;
  busy: boolean;
  onBack: () => void;
  onAcknowledge: () => void;
  onResolve: () => void;
  onFalsePositive: () => void;
}) {
  const evidence = alert.evidence;
  const latestSignals = evidence.latest_signals;
  const signalFlow =
    typeof latestSignals === "object" && latestSignals !== null
      ? (latestSignals as Record<string, unknown>).flow_rate_liters_minute
      : null;
  const flowRate =
    typeof evidence.observed_flow_rate_liters_minute === "number"
      ? evidence.observed_flow_rate_liters_minute
      : typeof signalFlow === "number"
        ? signalFlow
        : null;
  const duration =
    typeof evidence.observed_duration_minutes === "number"
      ? evidence.observed_duration_minutes
      : null;
  const statusText =
    alert.status === "open"
      ? "Precisa de atenção"
      : alert.status === "acknowledged"
        ? "Aviso reconhecido"
        : alert.status === "resolved"
          ? "Aviso resolvido"
          : "Marcado como falso positivo";
  const nextStep =
    alert.detector_type === "device_offline"
      ? "Confira se o medidor está ligado e se a conexão está funcionando."
      : "Veja se alguma torneira ou equipamento estava em uso nesse período. O aviso merece verificação, mas sozinho não confirma um problema.";

  return (
    <div className="alert-detail-page">
      <button type="button" className="button button--quiet alert-back-button" onClick={onBack}>
        <span aria-hidden="true">←</span> Voltar aos avisos
      </button>
      {notice && (
        <p role="status" className="form-notice form-notice--success alert-detail-notice">
          {notice}
        </p>
      )}
      <section className="surface alert-detail-card" aria-labelledby="alert-detail-title">
        <span className={`alert-detail-status alert-detail-status--${alert.status}`}>
          {statusText}
        </span>
        <h2 id="alert-detail-title">O que aconteceu</h2>
        <p className="alert-detail-description">
          {alert.detector_type === "ml_anomaly"
            ? "A análise encontrou uma possível mudança no consumo. Confira as leituras do período para entender o que aconteceu."
            : alert.reason}
        </p>
        {(flowRate !== null || duration !== null) && (
          <div className="alert-detail-metrics">
            {flowRate !== null && (
              <div>
                <strong>
                  {flowRate.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} L/min
                </strong>
                <span>Vazão registrada</span>
              </div>
            )}
            {duration !== null && (
              <div>
                <strong>
                  {duration.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} min
                </strong>
                <span>Duração observada</span>
              </div>
            )}
          </div>
        )}
        <div className="alert-detail-next-step">
          <h3>{alert.detector_type === "device_offline" ? "Vale conferir" : "Vale verificar"}</h3>
          <p>{nextStep}</p>
        </div>
        <AlertEvidence alert={alert} />
      </section>
      {(alert.status === "open" || alert.status === "acknowledged") && (
        <div className="alert-detail-actions">
          {alert.status === "open" && (
            <button
              type="button"
              className="button button--primary"
              disabled={busy}
              onClick={onAcknowledge}
            >
              {busy ? "Salvando…" : "Reconhecer aviso"}
            </button>
          )}
          <button
            type="button"
            className="button button--outline"
            disabled={busy}
            onClick={onResolve}
          >
            Marcar como resolvido
          </button>
          <button
            type="button"
            className="button button--quiet alert-false-positive"
            disabled={busy}
            onClick={onFalsePositive}
          >
            Marcar como falso positivo
          </button>
        </div>
      )}
    </div>
  );
}
