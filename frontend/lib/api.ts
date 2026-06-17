import type {
  CreateIncidentBody,
  Deployment,
  DrEvent,
  DrStatus,
  Incident,
  IncidentDetail,
  LoginResponse,
  Me,
  MemoryResult,
  MemorySearchBody,
  Metric,
  MissionControlReport,
  MissionControlRunBody,
  Overview,
  ScenarioInfo,
  SimulationResult,
  SimulationRunBody,
  AvailableConnector,
  ConnectConnectorBody,
  ConnectedApp,
  ConnectorEvent,
  ImportResult,
  SyncResult,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const TOKEN_KEY = "deployhub_token";
const ROLE_KEY = "deployhub_role";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function getRole(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ROLE_KEY);
}

export function setRole(role: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ROLE_KEY, role);
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(ROLE_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query } = opts;

  let url = `${API_BASE}/api${path}`;
  if (query) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        params.append(k, String(v));
      }
    });
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      `Cannot reach API at ${API_BASE}. Is the backend running?`,
      0
    );
  }

  if (res.status === 401) {
    clearAuth();
    throw new ApiError("Unauthorized. Please log in again.", 401);
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || data.message || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail || `Request failed (${res.status})`, res.status);
  }

  if (res.status === 204) return undefined as T;

  return (await res.json()) as T;
}

// ---- Auth ----
export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  const data = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
  });
  setToken(data.access_token);
  setRole(data.role);
  return data;
}

export function getMe(): Promise<Me> {
  return request<Me>("/auth/me");
}

// ---- Overview ----
export function getOverview(): Promise<Overview> {
  return request<Overview>("/overview");
}

export function getServices(): Promise<string[]> {
  return request<string[]>("/services");
}

// ---- Pipelines ----
export function getPipelines(): Promise<import("./types").Pipeline[]> {
  return request<import("./types").Pipeline[]>("/pipelines");
}

// ---- Metrics ----
export function getMetrics(params?: {
  service?: string;
  limit?: number;
}): Promise<Metric[]> {
  return request<Metric[]>("/metrics", { query: params });
}

// ---- Incidents ----
export function getIncidents(params?: {
  status?: string;
  limit?: number;
}): Promise<Incident[]> {
  return request<Incident[]>("/incidents", { query: params });
}

export function getIncident(id: number | string): Promise<IncidentDetail> {
  return request<IncidentDetail>(`/incidents/${id}`);
}

export function createIncident(body: CreateIncidentBody): Promise<Incident> {
  return request<Incident>("/incidents", { method: "POST", body });
}

// ---- Deployments ----
export function getDeployments(params?: {
  limit?: number;
}): Promise<Deployment[]> {
  return request<Deployment[]>("/deployments", { query: params });
}

// ---- Disaster Recovery ----
export function getDrStatus(): Promise<DrStatus> {
  return request<DrStatus>("/dr/status");
}

export function getDrEvents(params?: { limit?: number }): Promise<DrEvent[]> {
  return request<DrEvent[]>("/dr/events", { query: params });
}

// ---- Memory ----
export function memorySearch(
  body: MemorySearchBody
): Promise<{ results: MemoryResult[] }> {
  return request<{ results: MemoryResult[] }>("/memory/search", {
    method: "POST",
    body,
  });
}

// ---- Mission Control ----
export function runMissionControl(
  body: MissionControlRunBody
): Promise<MissionControlReport> {
  return request<MissionControlReport>("/mission-control/run", {
    method: "POST",
    body,
  });
}

export function getMissionControlReports(params?: {
  limit?: number;
}): Promise<MissionControlReport[]> {
  return request<MissionControlReport[]>("/mission-control/reports", {
    query: params,
  });
}

// ---- Simulation ----
export function getSimulationScenarios(): Promise<ScenarioInfo[]> {
  return request<ScenarioInfo[]>("/simulation/scenarios");
}

export function runSimulation(
  body: SimulationRunBody
): Promise<SimulationResult> {
  return request<SimulationResult>("/simulation/run", {
    method: "POST",
    body,
  });
}

// ---- App Connector Hub ----
export function getAvailableConnectors(): Promise<AvailableConnector[]> {
  return request<AvailableConnector[]>("/connectors/available");
}

export function getConnectedApps(): Promise<ConnectedApp[]> {
  return request<ConnectedApp[]>("/connectors");
}

export function connectConnector(body: ConnectConnectorBody): Promise<SyncResult> {
  return request<SyncResult>("/connectors/connect", { method: "POST", body });
}

export function syncConnector(id: number): Promise<SyncResult> {
  return request<SyncResult>(`/connectors/${id}/sync`, { method: "POST" });
}

export function deleteConnector(id: number): Promise<void> {
  return request<void>(`/connectors/${id}`, { method: "DELETE" });
}

export function getConnectorEvents(
  id: number,
  limit = 5
): Promise<ConnectorEvent[]> {
  return request<ConnectorEvent[]>(`/connectors/${id}/events`, {
    query: { limit },
  });
}

// Multipart upload — uses fetch directly (the JSON request() helper can't send FormData).
export async function importProject(
  file: File,
  replace = true
): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("replace", String(replace));
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/connectors/import`, {
      method: "POST",
      headers,
      body: form,
    });
  } catch {
    throw new ApiError(`Cannot reach API at ${API_BASE}.`, 0);
  }
  if (res.status === 401) {
    clearAuth();
    throw new ApiError("Unauthorized. Please log in again.", 401);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as ImportResult;
}
